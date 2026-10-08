// Шлемы, перчатки, вратарская амуниция (и формы Custom Team): синхронное чтение resolve только
// для композиции текстур экипировки. Перенос подмены NHL 13 (port/src/nhl13_composite.cpp; разбор —
// docs/graphics-settings.md, раздел «Шлемы»).
//
// В NHL Legacy (по образу, 08.10.2026): EndTiling-resolve композиции — 836214A8 (в NHL 13 —
// 832B22A8), опрос забора resolve — 8361F3E0 (832B0250). Обе функции те же (356 и 76 байт),
// отличаются только адреса вызовов и данных. Машина состояний CompositeOp — 836A3088 (83328380;
// сходство 0,93), 836214A8 вызывается только из неё — как в NHL 13. 8361F3E0 зовут ещё 4 места
// (снимки экрана, карточки игроков) — реагируем только на resolve, выданные через 836214A8.
//
// Игра собирает шаблон зон и цвета экипировки рендером в текстуру (EDRAM → resolve в
// TargetTexture) и дочитывает результат процессором (Linearizer: LockRect + XGUntile, гамма,
// мипы, DXT). С readback_resolve = some вторая и следующие композиции того же размера — «попадание»
// без копии, и процессор читает прошлую композицию (чужой шлем, не те цвета, дыры с нулевой
// альфой). Здесь: на время одной композиции — от выдачи её resolve до того, как игра увидела
// забор, — readback_resolve = "full", потом прежнее значение. Сторож: если забор не увиден за 5 с,
// значение возвращается само. nhl_composite_readback = false — выключить.

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstring>
#include <mutex>
#include <string>
#include <thread>
#include <unordered_map>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ppc.h>

REXCVAR_DEFINE_BOOL(nhl_composite_readback, true, "NHLLegacy",
                    "Equipment composites (helmets, gloves, goalie gear): switch readback_resolve "
                    "to full only while a composite resolve is in flight, so the game's CPU stages "
                    "read the current pixels (with some/fast they read a previous composite)")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

extern "C" void __imp__sub_836214A8(PPCContext& ctx, uint8_t* base);  // EndTiling-resolve композиции
extern "C" void __imp__sub_8361F3E0(PPCContext& ctx, uint8_t* base);  // опрос забора resolve

namespace {

using Clock = std::chrono::steady_clock;
constexpr auto kTimeout = std::chrono::seconds(5);
constexpr char kCvar[] = "readback_resolve";

uint8_t* Host(uint8_t* base, uint32_t addr) {
  return base + addr + (addr >= 0xE0000000u ? 0x1000u : 0u);
}

uint32_t Load32(uint8_t* base, uint32_t addr) {
  uint32_t v;
  std::memcpy(&v, Host(base, addr), 4);
  return __builtin_bswap32(v);
}

struct State {
  std::mutex mu;
  std::condition_variable cv;
  std::unordered_map<uint32_t, Clock::time_point> active;  // объект resolve → когда выдан
  bool forced = false;  // readback_resolve переключён здесь на full
  std::string saved;    // что вернуть
  bool watchdog = false;
  uint64_t composites = 0;
  uint64_t timeouts = 0;
};

// Не разрушается при выходе: поток сторожа живёт до конца процесса.
State& S() {
  static State* s = new State();
  return *s;
}

std::atomic<uint32_t> g_active{0};

void RestoreLocked(State& s) {
  if (!s.forced) {
    return;
  }
  s.forced = false;
  // Если за время композиции значение сменили из консоли или F4 — оставить чужое.
  if (rex::cvar::GetFlagByName(kCvar) == "full") {
    rex::cvar::SetFlagByName(kCvar, s.saved);
  }
}

void WatchdogMain() {
  State& s = S();
  std::unique_lock lock(s.mu);
  for (;;) {
    s.cv.wait(lock, [&] { return !s.active.empty() || s.forced; });
    s.cv.wait_for(lock, std::chrono::milliseconds(250));
    const auto now = Clock::now();
    for (auto it = s.active.begin(); it != s.active.end();) {
      if (now - it->second > kTimeout) {
        if (s.timeouts++ < 5) {
          REXLOG_WARN("[nhllegacy] composite readback: no fence seen for resolve 0x{:08X} in 5 s, "
                      "{} back to '{}'",
                      it->first, kCvar, s.saved);
        }
        it = s.active.erase(it);
      } else {
        ++it;
      }
    }
    g_active.store(uint32_t(s.active.size()), std::memory_order_relaxed);
    if (s.active.empty()) {
      RestoreLocked(s);
    }
  }
}

// Только для лога: TargetTexture — объект EA, +52 — D3DTexture (его и берёт EndTiling, если
// tiled != 0), константа выборки с +0x1C: слово 1 — формат и адрес, слово 2 — размер.
void LogTarget(uint8_t* base, uint64_t n, uint32_t resolver, uint32_t target, bool tiled,
               const std::string& mode) {
  uint32_t tex = 0, format = 0, addr = 0, w = 0, h = 0;
  if (tiled && target) {
    tex = Load32(base, target + 52);
    if (tex >= 0x40000000u && tex < 0xFFFF0000u) {
      const uint32_t word1 = Load32(base, tex + 0x20);
      const uint32_t word2 = Load32(base, tex + 0x24);
      format = word1 & 0x3F;
      addr = word1 & 0xFFFFF000u;
      w = (word2 & 0x1FFF) + 1;
      h = ((word2 >> 13) & 0x1FFF) + 1;
    }
  }
  REXLOG_INFO("[nhllegacy] composite readback #{}: resolve 0x{:08X}, texture 0x{:08X} at 0x{:08X} "
              "{}x{} fmt {}; {} '{}' -> full",
              n, resolver, tex, addr, w, h, format, kCvar, mode);
}

void Begin(uint8_t* base, uint32_t resolver, uint32_t target, bool tiled) {
  State& s = S();
  std::lock_guard lock(s.mu);
  if (s.active.empty() && !s.forced) {
    std::string mode = rex::cvar::GetFlagByName(kCvar);
    if (mode != "full" && rex::cvar::SetFlagByName(kCvar, "full")) {
      s.forced = true;
      s.saved = std::move(mode);
    }
  }
  s.active[resolver] = Clock::now();
  g_active.store(uint32_t(s.active.size()), std::memory_order_relaxed);
  const uint64_t n = ++s.composites;
  if (n <= 6 || n % 100 == 0) {
    LogTarget(base, n, resolver, target, tiled, s.forced ? s.saved : std::string("full"));
  }
  if (!s.watchdog) {
    s.watchdog = true;
    std::thread(WatchdogMain).detach();
  }
  s.cv.notify_one();
}

void End(uint32_t resolver) {
  State& s = S();
  std::lock_guard lock(s.mu);
  auto it = s.active.find(resolver);
  if (it == s.active.end()) {
    return;
  }
  const auto ms =
      std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now() - it->second).count();
  s.active.erase(it);
  g_active.store(uint32_t(s.active.size()), std::memory_order_relaxed);
  if (s.composites <= 6) {
    if (s.active.empty() && s.forced) {
      REXLOG_INFO("[nhllegacy] composite readback: resolve 0x{:08X} fenced after {} ms, {} back to "
                  "'{}'",
                  resolver, ms, kCvar, s.saved);
    } else {
      REXLOG_INFO("[nhllegacy] composite readback: resolve 0x{:08X} fenced after {} ms", resolver,
                  ms);
    }
  }
  if (s.active.empty()) {
    RestoreLocked(s);
  }
}

}  // namespace

// EndTiling-resolve композиции (только из 836A3088, состояние 2): r3 — объект resolve (56 байт,
// +0 — состояние 0/1/2, +4 — AsyncOp забора), r4 — устройство, r5 — CompositeOp:TargetTexture,
// r6 — 1: EndTiling в текстуру +52, 0: resolve цветовой цели (ResolveColorTarget:AsyncOp).
// Переключение — до вызова: пакеты resolve пишутся внутри.
extern "C" void sub_836214A8(PPCContext& ctx, uint8_t* base) {
  if (REXCVAR_GET(nhl_composite_readback) && ctx.r3.u32) {
    Begin(base, ctx.r3.u32, ctx.r5.u32, (ctx.r6.u32 & 0xFF) != 0);
  }
  __imp__sub_836214A8(ctx, base);
}

// Опрос забора: состояние 1 → 2, когда AsyncOp выполнен. Им же пользуются снимки экрана и
// карточки игроков — здесь реагируем только на resolve, выданные через 836214A8.
extern "C" void sub_8361F3E0(PPCContext& ctx, uint8_t* base) {
  const uint32_t resolver = ctx.r3.u32;
  __imp__sub_8361F3E0(ctx, base);
  if (g_active.load(std::memory_order_relaxed) && resolver && Load32(base, resolver) == 2) {
    End(resolver);
  }
}
