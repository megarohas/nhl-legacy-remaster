// Обход гонки в InputSystem SDK (0.10.0 и nightly 0.10.0.24).
//
// Каждый XamInput* из потоков игры зовёт InputSystem::RefreshDevices, который
// пересобирает список устройств без блокировки. Два потока одновременно — и
// список рушится: падение в std::_Destroy_range<DeviceInfo> из RefreshDevices
// (nhl13_crash.txt) или повреждение кучи 0xC0000374 сразу после нажатия кнопки в
// меню. То же лечили патчем input-system-lock в 3on3NHL-recomp.
//
// Сгенерированный код вызывает импорты напрямую по имени (__imp__XamInputGetState
// и т. д.), а определение в exe сильнее библиотеки импорта rexruntime. Поэтому
// здесь — функции с теми же именами: общий мьютекс + вызов оригинала из DLL
// рантайма через GetProcAddress.

#include <mutex>

#include <rex/cvar.h>
#include <rex/ppc.h>

#if defined(_WIN32)
#include <windows.h>

namespace {

using GuestFn = void (*)(PPCContext&, uint8_t*);

std::mutex g_input_mutex;

GuestFn RuntimeExport(const char* name) {
  // Модуль рантайма — тот, где живёт любая его функция (имя DLL зависит от
  // конфигурации: rexruntime / rexruntimed / rexruntimerd).
  HMODULE runtime = nullptr;
  GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                         GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                     reinterpret_cast<LPCSTR>(&rex::cvar::GetFlagByName), &runtime);
  return runtime ? reinterpret_cast<GuestFn>(GetProcAddress(runtime, name)) : nullptr;
}

void CallLocked(const char* name, GuestFn& cached, PPCContext& ctx, uint8_t* base) {
  if (!cached) {
    cached = RuntimeExport(name);
  }
  std::lock_guard<std::mutex> lock(g_input_mutex);
  if (cached) {
    cached(ctx, base);
  } else {
    ctx.r3.u64 = 0x48F;  // X_ERROR_DEVICE_NOT_CONNECTED, если экспорт не нашёлся
  }
}

}  // namespace

#define NHL13_LOCKED_IMPORT(name)                      \
  extern "C" void name(PPCContext& ctx, uint8_t* base) { \
    static GuestFn original = nullptr;                   \
    CallLocked(#name, original, ctx, base);              \
  }

NHL13_LOCKED_IMPORT(__imp__XamInputGetState)
NHL13_LOCKED_IMPORT(__imp__XamInputGetCapabilities)
NHL13_LOCKED_IMPORT(__imp__XamInputGetKeystrokeEx)
NHL13_LOCKED_IMPORT(__imp__XamInputSetState)

#endif
