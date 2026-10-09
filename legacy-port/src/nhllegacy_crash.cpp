// Отчёт о падении процесса: необработанное исключение -> код, адрес и стек с
// именами функций (sub_XXXXXXXX — гостевые функции игры) в nhllegacy_crash.txt рядом
// с exe. Без него процесс при нарушении доступа умирает молча: лог рантайма
// буферизован и не успевает сброситься.
//
// Стеки всех потоков по требованию — для зависаний («вечная загрузка»): положить
// рядом с exe пустой файл nhllegacy_dump.flag — порт допишет в nhllegacy_stacks.txt три
// снимка стеков всех потоков с интервалом 0,3 с и удалит флаг. Поток на время
// снимка приостанавливается, стек раскручивается без выделения памяти
// (RtlVirtualUnwind), имена ищутся уже после возобновления.

#if defined(_WIN32)

#include <windows.h>
#include <dbghelp.h>
#include <tlhelp32.h>

#include <algorithm>
#include <csignal>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "nhllegacy_debug.h"

void NhlLegacyStartWatcher();  // nhllegacy_watch.cpp
void NhlLegacyAsTraceDump(FILE* f);  // nhllegacy_astrace.cpp

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

// Полный слепок процесса (minidump со всей памятью: гостевая память Xbox, стеки, потоки) в
// dumps\nhllegacy_<дата>_<время>_<причина>.dmp рядом с exe; хранятся последние kKeepDumps.
// Разбор без игры — tools/memscan.py --dump ФАЙЛ (те же команды, что для живого процесса).
constexpr int kKeepDumps = 3;

void RotateDumps(const std::wstring& dir) {
  std::vector<std::pair<FILETIME, std::wstring>> files;
  WIN32_FIND_DATAW fd;
  HANDLE h = FindFirstFileW((dir + L"nhllegacy_*.dmp").c_str(), &fd);
  if (h == INVALID_HANDLE_VALUE) {
    return;
  }
  do {
    files.push_back({fd.ftLastWriteTime, fd.cFileName});
  } while (FindNextFileW(h, &fd));
  FindClose(h);
  std::sort(files.begin(), files.end(), [](const auto& a, const auto& b) {
    return CompareFileTime(&a.first, &b.first) > 0;
  });
  for (size_t i = kKeepDumps; i < files.size(); ++i) {
    DeleteFileW((dir + files[i].second).c_str());
  }
}

void WriteSnapshot(const char* reason, EXCEPTION_POINTERS* info) {
  // Слепок пишет внешний nhllegacy_snap.exe (рядом с exe): снимать себя изнутри нельзя —
  // MiniDumpWriteDump в своём процессе встаёт на блокировках остановленных потоков.
  static std::mutex mutex;
  std::lock_guard<std::mutex> lock(mutex);
  const std::wstring dir = ExeDir() + L"dumps\\";
  CreateDirectoryW(dir.c_str(), nullptr);
  SYSTEMTIME t;
  GetLocalTime(&t);
  wchar_t name[128];
  swprintf(name, 128, L"nhllegacy_%04u%02u%02u_%02u%02u%02u_%hs.dmp", t.wYear, t.wMonth, t.wDay, t.wHour,
           t.wMinute, t.wSecond, reason);
  wchar_t cmd[1024];
  if (info) {
    swprintf(cmd, 1024, L"\"%snhllegacy_snap.exe\" %lu \"%s%s\" %lu %llX", ExeDir().c_str(),
             GetCurrentProcessId(), dir.c_str(), name, GetCurrentThreadId(),
             static_cast<unsigned long long>(reinterpret_cast<uintptr_t>(info)));
  } else {
    swprintf(cmd, 1024, L"\"%snhllegacy_snap.exe\" %lu \"%s%s\"", ExeDir().c_str(), GetCurrentProcessId(),
             dir.c_str(), name);
  }
  STARTUPINFOW si{sizeof(si)};
  PROCESS_INFORMATION pi{};
  if (!CreateProcessW(nullptr, cmd, nullptr, nullptr, FALSE, CREATE_NO_WINDOW, nullptr, nullptr, &si, &pi)) {
    return;
  }
  WaitForSingleObject(pi.hProcess, 180000);
  CloseHandle(pi.hThread);
  CloseHandle(pi.hProcess);
  RotateDumps(dir);
}

LONG WINAPI CrashFilter(EXCEPTION_POINTERS* info) {
  static volatile LONG once = 0;
  if (InterlockedExchange(&once, 1)) {
    return EXCEPTION_CONTINUE_SEARCH;
  }
  FILE* f = _wfopen((ExeDir() + L"nhllegacy_crash.txt").c_str(), L"w");
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
  NhlLegacyAsTraceDump(f);  // nhllegacy_astrace.cpp (nhl_astrace)
  fclose(f);
  WriteSnapshot("crash", info);
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

// Слепок по требованию (зависание): Ctrl+Alt+F12 или файл nhllegacy_snapshot.flag рядом с exe.
void SnapshotWatcher() {
  const std::wstring flag = ExeDir() + L"nhllegacy_snapshot.flag";
  bool held = false;
  for (;;) {
    Sleep(100);
    const bool keys = (GetAsyncKeyState(VK_CONTROL) & 0x8000) && (GetAsyncKeyState(VK_MENU) & 0x8000) &&
                      (GetAsyncKeyState(VK_F12) & 0x8000);
    const bool by_flag = GetFileAttributesW(flag.c_str()) != INVALID_FILE_ATTRIBUTES;
    if (by_flag) {
      DeleteFileW(flag.c_str());
    }
    if ((keys && !held) || by_flag) {
      Beep(880, 120);
      WriteSnapshot(by_flag ? "flag" : "manual", nullptr);
      Beep(1320, 200);
    }
    held = keys;
  }
}

void StackDumpWatcher() {
  const std::wstring flag = ExeDir() + L"nhllegacy_dump.flag";
  const std::wstring out = ExeDir() + L"nhllegacy_stacks.txt";
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

// std::abort() — так рантайм завершает игру на REX_FATAL (например, «Call to invalid or
// unregistered function»): исключения нет, фильтр выше не срабатывает. Стек потока, где
// вызван abort, — в nhllegacy_crash.txt (гостевые функции видны как __imp__sub_XXXXXXXX).
void AbortHandler(int) {
  static volatile LONG once = 0;
  if (InterlockedExchange(&once, 1)) {
    return;
  }
  FILE* f = _wfopen((ExeDir() + L"nhllegacy_crash.txt").c_str(), L"w");
  if (!f) {
    return;
  }
  fprintf(f, "abort() on thread %lu (REX_FATAL or CRT abort)\n", GetCurrentThreadId());
  fflush(f);
  CONTEXT c{};
  RtlCaptureContext(&c);
  DWORD64 frames[64];
  std::unique_lock<std::mutex> lock(g_dbghelp_mutex, std::try_to_lock);
  EnsureSymbols();
  const int n = CaptureStack(c, frames, 64);
  for (int i = 0; i < n; ++i) {
    WriteFrame(f, i, frames[i]);
  }
  fclose(f);
  if (lock.owns_lock()) {
    lock.unlock();
  }
  WriteSnapshot("abort", nullptr);
}

struct Installer {
  Installer() { SetUnhandledExceptionFilter(CrashFilter); }
} installer;

}  // namespace

std::mutex& NhlLegacyDbghelpMutex() {
  return g_dbghelp_mutex;
}

void NhlLegacyEnsureSymbols() {
  EnsureSymbols();
}

void NhlLegacyWriteFrame(FILE* f, int i, DWORD64 addr) {
  WriteFrame(f, i, addr);
}

int NhlLegacyCaptureStack(CONTEXT ctx, DWORD64* out, int max) {
  return CaptureStack(ctx, out, max);
}

void NhlLegacyWriteSnapshot(const char* reason) {
  WriteSnapshot(reason, nullptr);
}

// Повторная установка после настройки рантайма (на случай, если SDK или SDL
// поставили свой фильтр) и запуск наблюдателя за флагом снимка стеков.
void NhlLegacyInstallCrashReporter() {
  SetUnhandledExceptionFilter(CrashFilter);
  signal(SIGABRT, AbortHandler);
  static std::once_flag watcher;
  std::call_once(watcher, [] {
    std::thread(StackDumpWatcher).detach();
    std::thread(SnapshotWatcher).detach();
    NhlLegacyStartWatcher();
  });
}

#else

void NhlLegacyInstallCrashReporter() {}

#endif
