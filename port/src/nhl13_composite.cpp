// Шлемы, перчатки, вратарская амуниция (и формы Custom Team): синхронное чтение resolve только
// для композиции текстур экипировки. Разбор — docs/graphics-settings.md, раздел «Шлемы».
//
// Как игра красит экипировку (по коду, 08.10.2026). Шаблон зон (helmet_0_<модель>_tm,
// glove_<модель>_<n>_tm, …) и цвета зон из базы игра при загрузке собирает в текстуру сама —
// CompositeOp, машина состояний 83328380 (запускает 83328B78, данные — composite_* в 83311F80…):
//   2  рисует композицию в EDRAM и EndTiling-resolve 832B22A8 в CompositeOp:TargetTexture —
//      A8R8G8B8, одна на размер (кэш 83328220; после каждой композиции освобождается и тут же
//      выделяется снова — скорее всего, по тому же адресу; длина resolve та же);
//   3  ждёт забор GPU (EndTiling:AsyncOp; опрос 832B0250 ставит объекту resolve состояние 2);
//   4  Linearizer — задание на процессоре 82A6F368: LockRect + XGUntile из памяти TargetTexture;
//   5…14 гамма, мипы, DXT-сжатие (IMAGE::*) — тоже процессор — в итоговую текстуру.
// То есть результат resolve читает процессор, из гостевой памяти.
//
// SDK кладёт resolve в свою копию памяти на GPU; в память гостя его копирует readback_resolve:
// full — каждый resolve синхронно (верно, но GPU останавливается на каждом resolve кадра — ~25
// кадров); some — только при «промахе»: первый resolve с этим адресом и длиной (или после 60
// кадров без него). Вторая и следующие композиции того же размера — попадание, копии нет, и
// Linearizer читает то, что лежало там раньше: прошлую композицию (чужой шлем, не те цвета) или
// данные, которые процессор писал в этот блок, пока он был свободен (куски, серо-чёрные вставки,
// нулевая альфа — сквозь шлем видна голова). fast — копия от прошлого resolve с тем же ключом,
// то есть тоже прошлая композиция.
//
// Здесь: на время одной композиции — от выдачи её resolve (вход в 832B22A8, до записи пакетов) до
// того, как игра увидела забор, — readback_resolve = "full", потом прежнее значение. Забор GPU
// игра видит только после того, как поток команд SDK выполнил resolve, а в режиме full он к этому
// моменту уже синхронно скопировал данные в память гостя. В остальное время — значение из
// nhl13.toml (some), скорость не меняется. Работает в обеих сборках (port и port-ffx), D3D12 и
// Vulkan: cvar общий. Сторож: если забор не увиден за 5 с (композицию бросили), значение
// возвращается само. nhl_composite_readback = false — выключить (сравнение из консоли).

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

REXCVAR_DEFINE_BOOL(nhl_composite_readback, true, "NHL13",
                    "Equipment composites (helmets, gloves, goalie gear): switch readback_resolve "
                    "to full only while a composite resolve is in flight, so the game's CPU stages "
                    "read the current pixels (with some/fast they read a previous composite)")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

extern "C" void __imp__sub_832B22A8(PPCContext& ctx, uint8_t* base);  // EndTiling-resolve композиции
extern "C" void __imp__sub_832B0250(PPCContext& ctx, uint8_t* base);  // опрос забора resolve

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
          REXLOG_WARN("[nhl13] composite readback: no fence seen for resolve 0x{:08X} in 5 s, "
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
  REXLOG_INFO("[nhl13] composite readback #{}: resolve 0x{:08X}, texture 0x{:08X} at 0x{:08X} "
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
      REXLOG_INFO("[nhl13] composite readback: resolve 0x{:08X} fenced after {} ms, {} back to "
                  "'{}'",
                  resolver, ms, kCvar, s.saved);
    } else {
      REXLOG_INFO("[nhl13] composite readback: resolve 0x{:08X} fenced after {} ms", resolver,
                  ms);
    }
  }
  if (s.active.empty()) {
    RestoreLocked(s);
  }
}

}  // namespace

// EndTiling-resolve композиции (только из 83328380, состояние 2): r3 — объект resolve (56 байт,
// +0 — состояние 0/1/2, +4 — AsyncOp забора), r4 — устройство, r5 — CompositeOp:TargetTexture,
// r6 — 1: EndTiling в текстуру +52, 0: resolve цветовой цели (ResolveColorTarget:AsyncOp).
// Переключение — до вызова: пакеты resolve пишутся внутри.
extern "C" void sub_832B22A8(PPCContext& ctx, uint8_t* base) {
  if (REXCVAR_GET(nhl_composite_readback) && ctx.r3.u32) {
    Begin(base, ctx.r3.u32, ctx.r5.u32, (ctx.r6.u32 & 0xFF) != 0);
  }
  __imp__sub_832B22A8(ctx, base);
}

// Опрос забора: состояние 1 → 2, когда AsyncOp выполнен. Им же пользуются снимки экрана и
// карточки игроков — здесь реагируем только на resolve, выданные через 832B22A8.
extern "C" void sub_832B0250(PPCContext& ctx, uint8_t* base) {
  const uint32_t resolver = ctx.r3.u32;
  __imp__sub_832B0250(ctx, base);
  if (g_active.load(std::memory_order_relaxed) && resolver && Load32(base, resolver) == 2) {
    End(resolver);
  }
}
