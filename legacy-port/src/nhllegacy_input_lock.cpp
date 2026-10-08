// Обход гонки в InputSystem SDK (0.10.0 и nightly 0.10.0.24).
//
// Каждый XamInput* из потоков игры зовёт InputSystem::RefreshDevices, который
// пересобирает список устройств без блокировки. Два потока одновременно — и
// список рушится: падение в std::_Destroy_range<DeviceInfo> из RefreshDevices
// (nhllegacy_crash.txt) или повреждение кучи 0xC0000374 сразу после нажатия кнопки в
// меню. То же лечили патчем input-system-lock в 3on3NHL-recomp.
//
// Сгенерированный код вызывает импорты напрямую по имени (__imp__XamInputGetState
// и т. д.), а определение в exe сильнее библиотеки импорта rexruntime. Поэтому
// здесь — функции с теми же именами: общий мьютекс + вызов оригинала из DLL
// рантайма через GetProcAddress.

#include <mutex>

#include <rex/logging.h>
#include <rex/ppc.h>

#if defined(_WIN32)
#include <windows.h>

namespace {

using GuestFn = void (*)(PPCContext&, uint8_t*);

std::mutex g_input_mutex;

GuestFn RuntimeExport(const char* name) {
  // DLL рантайма по имени (зависит от конфигурации). Адрес функции SDK тут не
  // годится: в exe он указывает на переходник импорта, то есть на сам exe —
  // GetProcAddress ничего не находил, и геймпад «отключался».
  HMODULE runtime = nullptr;
  for (const char* dll : {"rexruntimerd.dll", "rexruntime.dll", "rexruntimed.dll"}) {
    if ((runtime = GetModuleHandleA(dll)) != nullptr) {
      break;
    }
  }
  auto fn = runtime ? reinterpret_cast<GuestFn>(GetProcAddress(runtime, name)) : nullptr;
  if (fn) {
    REXLOG_INFO("[nhllegacy] input lock: {} -> rexruntime", name);
  } else {
    REXLOG_ERROR("[nhllegacy] input lock: {} not found in rexruntime (module {})", name,
                 static_cast<void*>(runtime));
  }
  return fn;
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

#define NHLLEGACY_LOCKED_IMPORT(name)                      \
  extern "C" void name(PPCContext& ctx, uint8_t* base) { \
    static GuestFn original = nullptr;                   \
    CallLocked(#name, original, ctx, base);              \
  }

NHLLEGACY_LOCKED_IMPORT(__imp__XamInputGetState)
NHLLEGACY_LOCKED_IMPORT(__imp__XamInputGetCapabilities)
NHLLEGACY_LOCKED_IMPORT(__imp__XamInputGetKeystrokeEx)
NHLLEGACY_LOCKED_IMPORT(__imp__XamInputSetState)

#endif
