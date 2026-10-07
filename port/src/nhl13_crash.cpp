// Отчёт о падении процесса: необработанное исключение -> код, адрес и стек с
// именами функций (sub_XXXXXXXX — гостевые функции игры) в nhl13_crash.txt рядом
// с exe. Без него процесс при нарушении доступа умирает молча: лог рантайма
// буферизован и не успевает сброситься.
//
// Стеки всех потоков по требованию — для зависаний («вечная загрузка»): положить
// рядом с exe пустой файл nhl13_dump.flag — порт допишет в nhl13_stacks.txt три
// снимка стеков всех потоков с интервалом 0,3 с и удалит флаг. Поток на время
// снимка приостанавливается, стек раскручивается без выделения памяти
// (RtlVirtualUnwind), имена ищутся уже после возобновления.

#if defined(_WIN32)

#include <windows.h>
#include <dbghelp.h>
#include <tlhelp32.h>

#include <cstdio>
#include <cstring>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace {

std::mutex g_dbghelp_mutex;  // dbghelp не потокобезопасен

std::wstring ExeDir() {
  wchar_t exe[MAX_PATH];
  GetModuleFileNameW(nullptr, exe, MAX_PATH);
  std::wstring path(exe);
  return path.substr(0, path.find_last_of(L"\\/") + 1);
}

void EnsureSymbols() {
  static bool ready = false;
  if (!ready) {
    SymSetOptions(SYMOPT_UNDNAME | SYMOPT_DEFERRED_LOADS | SYMOPT_LOAD_LINES);
    SymInitialize(GetCurrentProcess(), nullptr, TRUE);
    ready = true;
  }
}

void WriteFrame(FILE* f, int i, DWORD64 addr) {
  HANDLE proc = GetCurrentProcess();
  char module[MAX_PATH] = "?";
  HMODULE hm = nullptr;
  if (GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                             GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                         reinterpret_cast<LPCSTR>(addr), &hm)) {
    GetModuleFileNameA(hm, module, MAX_PATH);
  }
  const char* m = strrchr(module, '\\');
  m = m ? m + 1 : module;

  alignas(SYMBOL_INFO) char buf[sizeof(SYMBOL_INFO) + 512] = {};
  auto* sym = reinterpret_cast<SYMBOL_INFO*>(buf);
  sym->SizeOfStruct = sizeof(SYMBOL_INFO);
  sym->MaxNameLen = 511;
  DWORD64 disp = 0;
  if (SymFromAddr(proc, addr, &disp, sym)) {
    IMAGEHLP_LINE64 line{};
    line.SizeOfStruct = sizeof(line);
    DWORD ldisp = 0;
    if (SymGetLineFromAddr64(proc, addr, &ldisp, &line)) {
      fprintf(f, "#%02d %s!%s+0x%llX (%s:%lu)\n", i, m, sym->Name,
              static_cast<unsigned long long>(disp), line.FileName, line.LineNumber);
    } else {
      fprintf(f, "#%02d %s!%s+0x%llX\n", i, m, sym->Name, static_cast<unsigned long long>(disp));
    }
  } else {
    fprintf(f, "#%02d %s+0x%llX\n", i, m,
            static_cast<unsigned long long>(addr - reinterpret_cast<DWORD64>(hm)));
  }
}

// Раскрутка стека по .pdata без выделения памяти (можно при остановленном потоке).
int CaptureStack(CONTEXT ctx, DWORD64* out, int max) {
  int n = 0;
  while (n < max && ctx.Rip) {
    out[n++] = ctx.Rip;
    DWORD64 image_base = 0;
    PRUNTIME_FUNCTION fn = RtlLookupFunctionEntry(ctx.Rip, &image_base, nullptr);
    if (!fn) {  // листовая функция: адрес возврата на вершине стека
      ctx.Rip = *reinterpret_cast<DWORD64*>(ctx.Rsp);
      ctx.Rsp += 8;
    } else {
      PVOID handler_data = nullptr;
      DWORD64 establisher = 0;
      RtlVirtualUnwind(UNW_FLAG_NHANDLER, image_base, ctx.Rip, fn, &ctx, &handler_data,
                       &establisher, nullptr);
    }
  }
  return n;
}

LONG WINAPI CrashFilter(EXCEPTION_POINTERS* info) {
  static volatile LONG once = 0;
  if (InterlockedExchange(&once, 1)) {
    return EXCEPTION_CONTINUE_SEARCH;
  }
  FILE* f = _wfopen((ExeDir() + L"nhl13_crash.txt").c_str(), L"w");
  if (!f) {
    return EXCEPTION_CONTINUE_SEARCH;
  }

  const EXCEPTION_RECORD* rec = info->ExceptionRecord;
  fprintf(f, "exception 0x%08lX at %p, thread %lu\n", rec->ExceptionCode, rec->ExceptionAddress,
          GetCurrentThreadId());
  if (rec->ExceptionCode == EXCEPTION_ACCESS_VIOLATION && rec->NumberParameters >= 2) {
    const ULONG_PTR kind = rec->ExceptionInformation[0];
    fprintf(f, "access violation: %s 0x%llX\n",
            kind == 0 ? "read" : kind == 1 ? "write" : "execute",
            static_cast<unsigned long long>(rec->ExceptionInformation[1]));
  }
  fflush(f);

  HANDLE proc = GetCurrentProcess();
  HANDLE thread = GetCurrentThread();
  EnsureSymbols();

  CONTEXT ctx = *info->ContextRecord;
  STACKFRAME64 frame{};
  frame.AddrPC.Offset = ctx.Rip;
  frame.AddrPC.Mode = AddrModeFlat;
  frame.AddrFrame.Offset = ctx.Rbp;
  frame.AddrFrame.Mode = AddrModeFlat;
  frame.AddrStack.Offset = ctx.Rsp;
  frame.AddrStack.Mode = AddrModeFlat;

  for (int i = 0; i < 64; ++i) {
    if (!StackWalk64(IMAGE_FILE_MACHINE_AMD64, proc, thread, &frame, &ctx, nullptr,
                     SymFunctionTableAccess64, SymGetModuleBase64, nullptr)) {
      break;
    }
    const DWORD64 addr = frame.AddrPC.Offset;
    if (!addr) {
      break;
    }
    WriteFrame(f, i, addr);
    fflush(f);
  }
  fclose(f);
  return EXCEPTION_CONTINUE_SEARCH;
}

void DumpAllThreads(FILE* f) {
  struct Sample {
    DWORD tid;
    std::wstring name;
    int n;
    DWORD64 frames[48];
  };
  std::vector<Sample> samples;
  const DWORD pid = GetCurrentProcessId();
  const DWORD self = GetCurrentThreadId();
  HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
  if (snap == INVALID_HANDLE_VALUE) {
    return;
  }
  THREADENTRY32 te{};
  te.dwSize = sizeof(te);
  for (BOOL ok = Thread32First(snap, &te); ok; ok = Thread32Next(snap, &te)) {
    if (te.th32OwnerProcessID != pid || te.th32ThreadID == self) {
      continue;
    }
    HANDLE th = OpenThread(THREAD_SUSPEND_RESUME | THREAD_GET_CONTEXT |
                               THREAD_QUERY_LIMITED_INFORMATION,
                           FALSE, te.th32ThreadID);
    if (!th) {
      continue;
    }
    Sample s{te.th32ThreadID, L"", 0, {}};
    PWSTR desc = nullptr;
    if (SUCCEEDED(GetThreadDescription(th, &desc)) && desc) {
      s.name = desc;
      LocalFree(desc);
    }
    if (SuspendThread(th) != static_cast<DWORD>(-1)) {
      CONTEXT ctx{};
      ctx.ContextFlags = CONTEXT_FULL;
      if (GetThreadContext(th, &ctx)) {
        s.n = CaptureStack(ctx, s.frames, 48);
      }
      ResumeThread(th);
    }
    CloseHandle(th);
    samples.push_back(std::move(s));
  }
  CloseHandle(snap);

  EnsureSymbols();
  for (const Sample& s : samples) {
    fprintf(f, "-- thread %lu %ls\n", s.tid, s.name.c_str());
    for (int i = 0; i < s.n; ++i) {
      WriteFrame(f, i, s.frames[i]);
    }
  }
}

void StackDumpWatcher() {
  const std::wstring flag = ExeDir() + L"nhl13_dump.flag";
  const std::wstring out = ExeDir() + L"nhl13_stacks.txt";
  for (;;) {
    Sleep(500);
    if (GetFileAttributesW(flag.c_str()) == INVALID_FILE_ATTRIBUTES) {
      continue;
    }
    DeleteFileW(flag.c_str());
    std::lock_guard<std::mutex> lock(g_dbghelp_mutex);
    FILE* f = _wfopen(out.c_str(), L"a");
    if (!f) {
      continue;
    }
    for (int k = 0; k < 3; ++k) {
      SYSTEMTIME t;
      GetLocalTime(&t);
      fprintf(f, "==== snapshot %d at %02u:%02u:%02u.%03u ====\n", k + 1, t.wHour, t.wMinute,
              t.wSecond, t.wMilliseconds);
      DumpAllThreads(f);
      fflush(f);
      Sleep(300);
    }
    fclose(f);
  }
}

struct Installer {
  Installer() { SetUnhandledExceptionFilter(CrashFilter); }
} installer;

}  // namespace

// Повторная установка после настройки рантайма (на случай, если SDK или SDL
// поставили свой фильтр) и запуск наблюдателя за флагом снимка стеков.
void Nhl13InstallCrashReporter() {
  SetUnhandledExceptionFilter(CrashFilter);
  static std::once_flag watcher;
  std::call_once(watcher, [] { std::thread(StackDumpWatcher).detach(); });
}

#else

void Nhl13InstallCrashReporter() {}

#endif
