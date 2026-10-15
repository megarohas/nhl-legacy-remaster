// Шлемы, перчатки, вратарская амуниция (и формы Custom Team): синхронное чтение resolve только
// для композиции текстур экипировки. Перенос подмены NHL 13 (nhl-13-port/src/nhl13_composite.cpp; разбор —
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
//
// Разведка (nhl_composite_trace, по умолчанию выкл.; docs/legacy-port.md, «Порча текстур в первом матче сессии»): журнал
// nhllegacy_composite.log рядом с exe — каждая композиция: объект resolve, цель (CompositeOp:TargetTexture), её
// текстура (адрес, размер, формат по константе выборки), хеш памяти текстуры до resolve и после забора. «unchanged» —
// resolve не дошёл до памяти гостя (Linearizer прочтёт прежнее); «dup of #N» — те же байты, что у композиции N (другая
// композиция того же размера: рисование шаблона не попало в EDRAM, resolve взял остаток).

#if defined(_WIN32)
#include <windows.h>
#endif

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <deque>
#include <mutex>
#include <string>
#include <thread>
#include <unordered_map>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ppc.h>
#include <rex/runtime.h>
#include <rex/system/xmemory.h>

REXCVAR_DEFINE_BOOL(nhl_composite_readback, true, "NHLLegacy",
                    "Equipment composites (helmets, gloves, goalie gear): switch readback_resolve "
                    "to full only while a composite resolve is in flight, so the game's CPU stages "
                    "read the current pixels (with some/fast they read a previous composite)")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

REXCVAR_DEFINE_BOOL(nhl_composite_trace, false, "NHLLegacy",
                    "Diagnostics: log every equipment composite (resolve object, target texture, hash of its "
                    "memory before the resolve and after the fence) to nhllegacy_composite.log next to the exe")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

REXCVAR_DEFINE_BOOL(nhl_composite_dump, false, "NHLLegacy",
                    "Diagnostics (with nhl_composite_trace): also save the raw memory of every composite target "
                    "texture after the fence to composites\\cNNNN_WxH.bin next to the exe")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

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

// --- разведка (nhl_composite_trace) ---
// Текстура цели: TargetTexture (объект EA) +52 — D3DTexture, константа выборки с +0x1C: слово 1 — формат и
// физический адрес, слово 2 — размер. Композиции — A8R8G8B8 тайлами 32×32: размер — по выровненным ширине и высоте.
struct TexInfo {
  uint32_t tex = 0, addr = 0, w = 0, h = 0, fmt = 0, size = 0;
};

struct Pending {
  uint64_t n = 0;
  uint32_t target = 0;
  bool tiled = false;
  TexInfo tex;
  uint64_t h0 = 0;
  std::string mode;
  Clock::time_point t;
};

bool TraceOn() {
  static const bool on = REXCVAR_GET(nhl_composite_trace);
  return on;
}

FILE* TraceLog() {
  static FILE* f = [] {
    wchar_t exe[MAX_PATH];
    GetModuleFileNameW(nullptr, exe, MAX_PATH);
    std::wstring p(exe);
    p = p.substr(0, p.find_last_of(L"\\/") + 1) + L"nhllegacy_composite.log";
    return _wfopen(p.c_str(), L"a");
  }();
  return f;
}

void Stamp(FILE* f) {
  SYSTEMTIME t;
  GetLocalTime(&t);
  fprintf(f, "%02u:%02u:%02u.%03u ", t.wHour, t.wMinute, t.wSecond, t.wMilliseconds);
}

TexInfo ReadTex(uint8_t* base, uint32_t target) {
  TexInfo t;
  if (target < 0x40000000u || target >= 0xFFFF0000u) {
    return t;
  }
  t.tex = Load32(base, target + 52);
  if (t.tex < 0x40000000u || t.tex >= 0xFFFF0000u) {
    return t;
  }
  const uint32_t word1 = Load32(base, t.tex + 0x20);
  const uint32_t word2 = Load32(base, t.tex + 0x24);
  t.fmt = word1 & 0x3F;
  t.addr = word1 & 0xFFFFF000u;
  t.w = (word2 & 0x1FFF) + 1;
  t.h = ((word2 >> 13) & 0x1FFF) + 1;
  const uint64_t size = uint64_t((t.w + 31) & ~31u) * ((t.h + 31) & ~31u) * 4;
  t.size = uint32_t(size < (16u << 20) ? size : (16u << 20));
  return t;
}

uint64_t Hash(const TexInfo& t) {
  if (!t.addr || !t.size) {
    return 0;
  }
  const uint8_t* p = rex::Runtime::instance()->memory()->TranslatePhysical<const uint8_t*>(t.addr);
  uint64_t h = 1469598103934665603ull;
  for (uint32_t i = 0; i + 8 <= t.size; i += 8) {
    uint64_t v;
    std::memcpy(&v, p + i, 8);
    h = (h ^ v) * 1099511628211ull;
  }
  return h;
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
  // разведка
  std::unordered_map<uint32_t, Pending> pend;          // объект resolve → композиция в полёте
  std::deque<std::pair<uint64_t, uint64_t>> recent;    // (хеш после забора, номер) последних композиций
  std::unordered_map<uint32_t, bool> dumped;           // цели, чьи слова уже в журнале
  uint64_t unchanged = 0, dups = 0;
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
        if (TraceOn()) {
          if (FILE* f = TraceLog()) {
            Stamp(f);
            fprintf(f, "WATCHDOG: no fence for resolve %08X in 5 s, %s back to '%s'\n", it->first, kCvar,
                    s.saved.c_str());
            fflush(f);
          }
          s.pend.erase(it->first);
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
  if (TraceOn()) {
    Pending p;
    p.n = n;
    p.target = target;
    p.tiled = tiled;
    p.tex = ReadTex(base, target);
    p.h0 = Hash(p.tex);
    p.mode = s.forced ? s.saved : std::string("full");
    p.t = Clock::now();
    if (FILE* f = TraceLog(); f && !s.dumped[target] && target >= 0x40000000u && target < 0xFFFF0000u) {
      s.dumped[target] = true;
      Stamp(f);
      fprintf(f, "target %08X words:", target);
      for (uint32_t k = 0; k < 24; ++k) {
        fprintf(f, " %08X", Load32(base, target + 4 * k));
      }
      fprintf(f, "\n");
    }
    s.pend[resolver] = std::move(p);
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
  if (TraceOn()) {
    auto pit = s.pend.find(resolver);
    FILE* f = TraceLog();
    if (pit != s.pend.end() && f) {
      const Pending& p = pit->second;
      const uint64_t h1 = Hash(p.tex);
      const bool unchanged = h1 != 0 && h1 == p.h0;
      uint64_t dup = 0;
      for (const auto& [h, m] : s.recent) {
        if (h == h1 && h1 != 0) {
          dup = m;
        }
      }
      s.unchanged += unchanged;
      s.dups += dup != 0;
      Stamp(f);
      fprintf(f,
              "#%llu tid %lu resolver %08X target %08X tiled %d tex %08X @%08X %ux%u fmt %u size %u | mode '%s' | "
              "h0 %016llX h1 %016llX | fenced after %lld ms, active %zu%s",
              static_cast<unsigned long long>(p.n), GetCurrentThreadId(), resolver, p.target, p.tiled ? 1 : 0,
              p.tex.tex, p.tex.addr, p.tex.w, p.tex.h, p.tex.fmt, p.tex.size, p.mode.c_str(),
              static_cast<unsigned long long>(p.h0), static_cast<unsigned long long>(h1),
              static_cast<long long>(ms), s.active.size(), unchanged ? " | UNCHANGED" : "");
      if (dup) {
        fprintf(f, " | DUP of #%llu", static_cast<unsigned long long>(dup));
      }
      fprintf(f, " | totals unchanged %llu dup %llu\n", static_cast<unsigned long long>(s.unchanged),
              static_cast<unsigned long long>(s.dups));
      fflush(f);
      static const bool dump = REXCVAR_GET(nhl_composite_dump);
      if (dump && p.tex.addr && p.tex.size) {
        wchar_t exe[MAX_PATH];
        GetModuleFileNameW(nullptr, exe, MAX_PATH);
        std::wstring dir(exe);
        dir = dir.substr(0, dir.find_last_of(L"\\/") + 1) + L"composites\\";
        CreateDirectoryW(dir.c_str(), nullptr);
        wchar_t name[96];
        swprintf(name, 96, L"c%04llu_%ux%u.bin", static_cast<unsigned long long>(p.n), p.tex.w, p.tex.h);
        if (FILE* d = _wfopen((dir + name).c_str(), L"wb")) {
          fwrite(rex::Runtime::instance()->memory()->TranslatePhysical<const uint8_t*>(p.tex.addr), 1, p.tex.size, d);
          fclose(d);
        }
      }
      s.recent.emplace_back(h1, p.n);
      if (s.recent.size() > 512) {
        s.recent.pop_front();
      }
      s.pend.erase(pit);
    }
  }
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
