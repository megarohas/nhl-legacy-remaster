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
    REXLOG_INFO("[nhl13] input lock: {} -> rexruntime", name);
  } else {
    REXLOG_ERROR("[nhl13] input lock: {} not found in rexruntime (module {})", name,
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

#define NHL13_LOCKED_IMPORT(name)                      \
  extern "C" void name(PPCContext& ctx, uint8_t* base) { \
    static GuestFn original = nullptr;                   \
    CallLocked(#name, original, ctx, base);              \
  }

// port-fr (тесты): виртуальный геймпад из nhl13_pad.txt (src/nhl13_pad.cpp)
void Nhl13PadAfterGetState(PPCContext& ctx, uint8_t* base, uint32_t user, uint32_t state);
bool Nhl13PadKeystroke(PPCContext& ctx, uint8_t* base);

extern "C" void __imp__XamInputGetState(PPCContext& ctx, uint8_t* base) {
  static GuestFn original = nullptr;
  const uint32_t user = ctx.r3.u32;
  const uint32_t state = ctx.r5.u32;
  CallLocked("__imp__XamInputGetState", original, ctx, base);
  Nhl13PadAfterGetState(ctx, base, user, state);
}

extern "C" void __imp__XamInputGetKeystrokeEx(PPCContext& ctx, uint8_t* base) {
  static GuestFn original = nullptr;
  if (Nhl13PadKeystroke(ctx, base)) {
    return;
  }
  CallLocked("__imp__XamInputGetKeystrokeEx", original, ctx, base);
}

NHL13_LOCKED_IMPORT(__imp__XamInputGetCapabilities)
NHL13_LOCKED_IMPORT(__imp__XamInputSetState)

#endif
