// nhl13_snap.exe — полный слепок процесса игры (minidump со всей памятью) снаружи.
//
//     nhl13_snap.exe PID ФАЙЛ.dmp [TID АДРЕС_EXCEPTION_POINTERS]
//
// Порт (src/nhl13_crash.cpp) запускает его при падении, при std::abort() и по Ctrl+Alt+F12 и
// ждёт. Снимать себя изнутри нельзя: MiniDumpWriteDump приостанавливает остальные потоки и
// может навсегда встать на блокировке кучи, которую держит один из них (так и было).
// TID и адрес EXCEPTION_POINTERS (в памяти игры) — чтобы в слепке было само исключение.

#include <windows.h>
#include <dbghelp.h>

#include <cstdio>
#include <cstdlib>

int wmain(int argc, wchar_t** argv) {
  if (argc < 3) {
    fwprintf(stderr, L"usage: nhl13_snap PID FILE.dmp [TID EXCEPTION_POINTERS]\n");
    return 2;
  }
  const DWORD pid = static_cast<DWORD>(wcstoul(argv[1], nullptr, 10));
  HANDLE proc = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ | PROCESS_DUP_HANDLE, FALSE, pid);
  if (!proc) {
    fwprintf(stderr, L"OpenProcess(%lu): %lu\n", pid, GetLastError());
    return 1;
  }
  HANDLE file = CreateFileW(argv[2], GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
  if (file == INVALID_HANDLE_VALUE) {
    fwprintf(stderr, L"CreateFile: %lu\n", GetLastError());
    return 1;
  }
  MINIDUMP_EXCEPTION_INFORMATION mei{};
  const bool with_exception = argc >= 5;
  if (with_exception) {
    mei.ThreadId = static_cast<DWORD>(wcstoul(argv[3], nullptr, 10));
    mei.ExceptionPointers = reinterpret_cast<PEXCEPTION_POINTERS>(_wcstoui64(argv[4], nullptr, 16));
    mei.ClientPointers = TRUE;  // указатель — в памяти игры
  }
  const auto type = static_cast<MINIDUMP_TYPE>(MiniDumpWithFullMemory | MiniDumpWithHandleData |
                                               MiniDumpWithThreadInfo | MiniDumpWithUnloadedModules);
  const BOOL ok = MiniDumpWriteDump(proc, pid, file, type, with_exception ? &mei : nullptr, nullptr, nullptr);
  const DWORD err = ok ? 0 : GetLastError();
  CloseHandle(file);
  CloseHandle(proc);
  if (!ok) {
    fwprintf(stderr, L"MiniDumpWriteDump: 0x%08lX\n", err);
    DeleteFileW(argv[2]);
    return 1;
  }
  return 0;
}
