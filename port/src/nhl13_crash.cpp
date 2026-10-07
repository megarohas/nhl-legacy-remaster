// Отчёт о падении процесса: необработанное исключение -> код, адрес и стек с
// именами функций (sub_XXXXXXXX — гостевые функции игры) в nhl13_crash.txt рядом
// с exe. Без него процесс при нарушении доступа умирает молча: лог рантайма
// буферизован и не успевает сброситься.

#if defined(_WIN32)

#include <windows.h>
#include <dbghelp.h>

#include <cstdio>
#include <cstring>
#include <string>

namespace {

LONG WINAPI CrashFilter(EXCEPTION_POINTERS* info) {
  static volatile LONG once = 0;
  if (InterlockedExchange(&once, 1)) {
    return EXCEPTION_CONTINUE_SEARCH;
  }
  wchar_t exe[MAX_PATH];
  GetModuleFileNameW(nullptr, exe, MAX_PATH);
  std::wstring path(exe);
  path = path.substr(0, path.find_last_of(L"\\/") + 1) + L"nhl13_crash.txt";
  FILE* f = _wfopen(path.c_str(), L"w");
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
  SymSetOptions(SYMOPT_UNDNAME | SYMOPT_DEFERRED_LOADS | SYMOPT_LOAD_LINES);
  SymInitialize(proc, nullptr, TRUE);

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
    fflush(f);
  }
  fclose(f);
  return EXCEPTION_CONTINUE_SEARCH;
}

struct Installer {
  Installer() { SetUnhandledExceptionFilter(CrashFilter); }
} installer;

}  // namespace

// Повторная установка после настройки рантайма (на случай, если SDK или SDL
// поставили свой фильтр).
void Nhl13InstallCrashReporter() {
  SetUnhandledExceptionFilter(CrashFilter);
}

#else

void Nhl13InstallCrashReporter() {}

#endif
