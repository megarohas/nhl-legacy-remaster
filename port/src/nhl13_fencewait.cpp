// Поток рендера игры (XThread… (F8000064): создаёт устройство D3D, в нём же композиты шлемов)
// ждёт видеокарту в циклах D3D без единой паузы — и держит ядро на 100 % всё время, даже в меню.
// Разбор — docs/performance.md, раздел «Поток рендера».
//
// Что в игре (по коду, 08.10.2026; снимки стека tools/stackpeek.py в живом матче: в 15 из 16
// снимков поток стоял в 82672FF0 Swap → 8266EBA0 → 8266FBD0 BlockOnFence → 82663148).
// 82663148 — одна итерация ожидания D3D, r3 — состояние цикла на стеке гостя (+0 устройство,
// +8 последний виденный забор, +12 когда GPU последний раз продвинулся, +16 начало, +20 mftb
// при входе в цикл). Итерация: 32 × db16cyc (задержка на ядре Xenon) → байт флагов устройства
// +11069, бит 0x02 — вернуть 0 (ожидание бросить) → если забор в блоке записи GPU
// (*(устройство + 11024), +0) сдвинулся — запомнить время → сторож «GPU завис?»: 5000 тиков без
// продвижения → 82677F08 → вернуть 1, ждать дальше. Условие ожидания проверяет вызывающий после
// каждой итерации; таких циклов 7: забор кадра (8266FBD0), место в кольце команд (8266E718 и
// 8266ED80 — поля +4 и +60 того же блока записи), очередь кадров в Swap (82672FF0), заборы
// ресурсов (82678008, 82678B68), 82674A90. Рекомпилятор переводит db16cyc и cctpl/cctpm в пустое
// место (SDK: src/codegen/builders/system.cpp), поэтому цикл крутится вхолостую.
//
// Здесь: перед оригинальной итерацией — ожидание с откатом. Цикл ожидания узнаём по адресу его
// состояния и отметке mftb (+20); в нём:
//   * если с прошлой итерации изменился блок записи GPU (64 байта) или флаг устройства — сразу
//     дальше, без задержки: вызывающий тут же проверит своё условие;
//   * первые nhl_fence_wait_spin_us цикла — опрос с _mm_pause (как у Xenon, только пауза
//     настоящая; изменения видны через доли микросекунды);
//   * дальше — сон срезами по nhl_fence_wait_sleep_us (таймер высокого разрешения Windows) и после
//     каждого среза — итерация и проверка условия. Задержка конца ожидания — не больше одного
//     среза (по умолчанию 0,2 мс); в матче поток рендера опережает GPU на кадр, она не видна.
// Сама итерация 82663148 (флаг, отметка продвижения, сторож 5 с) выполняется как в игре, на
// каждом проходе. Раз в 30 с — строка «fence wait» в логе (сколько ждали и спали). Выключить —
// nhl_fence_wait = false (на лету из консоли или в nhl13.toml): поведение как было.

#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstring>

#include <immintrin.h>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ppc.h>

#if defined(_WIN32)
#include <windows.h>
#ifndef CREATE_WAITABLE_TIMER_HIGH_RESOLUTION
#define CREATE_WAITABLE_TIMER_HIGH_RESOLUTION 0x00000002
#endif
#else
#include <thread>
#endif

REXCVAR_DEFINE_BOOL(nhl_fence_wait, true, "NHL13",
                    "Render thread waiting for the GPU in D3D loops (82663148): pause and short "
                    "sleeps between checks instead of a busy spin (false = original busy wait)")
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

REXCVAR_DEFINE_INT32(nhl_fence_wait_spin_us, 100, "NHL13",
                     "nhl_fence_wait: microseconds of each wait spent polling with pause before "
                     "sleeping")
    .range(0, 100000)
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

REXCVAR_DEFINE_INT32(nhl_fence_wait_sleep_us, 200, "NHL13",
                     "nhl_fence_wait: sleep slice in microseconds after the spin phase "
                     "(0 = never sleep, only pause)")
    .range(0, 2000)
    .lifecycle(rex::cvar::Lifecycle::kHotReload);

extern "C" void __imp__sub_82663148(PPCContext& ctx, uint8_t* base);  // итерация ожидания D3D

namespace {

using Clock = std::chrono::steady_clock;

constexpr uint32_t kDeviceWriteback = 11024;  // устройство: указатель на блок записи GPU
constexpr uint32_t kDeviceFlags = 11069;      // байт флагов; 0x02 — ожидание бросить
constexpr uint32_t kStateStartTimebase = 20;  // состояние цикла: mftb при входе
constexpr size_t kWritebackBytes = 64;        // +0 забор, +4 и +60 — указатели кольца команд

uint8_t* Host(uint8_t* base, uint32_t addr) {
  return base + addr + (addr >= 0xE0000000u ? 0x1000u : 0u);
}

uint32_t Load32(uint8_t* base, uint32_t addr) {
  uint32_t v;
  std::memcpy(&v, Host(base, addr), 4);
  return __builtin_bswap32(v);
}

// Блок записи и флаги пишет поток эмуляции GPU (SDK) — читаем как volatile.
struct Snapshot {
  uint32_t words[kWritebackBytes / 4];
  uint8_t flags;
  bool operator==(const Snapshot& o) const {
    return flags == o.flags && std::memcmp(words, o.words, sizeof(words)) == 0;
  }
};

void Read(uint8_t* base, uint32_t dev, uint32_t writeback, Snapshot& s) {
  const volatile uint32_t* w = reinterpret_cast<const volatile uint32_t*>(Host(base, writeback));
  for (size_t i = 0; i < kWritebackBytes / 4; ++i) {
    s.words[i] = w[i];
  }
  s.flags = *reinterpret_cast<const volatile uint8_t*>(Host(base, dev + kDeviceFlags));
}

struct Episode {
  uint32_t state = 0;
  uint32_t start_tb = 0;
  uint32_t dev = 0;
  Clock::time_point first{};
  Clock::time_point last{};
  Snapshot snap{};
  bool valid = false;
};

#if defined(_WIN32)
struct SleepTimer {
  HANDLE h = nullptr;
  bool tried = false;
  ~SleepTimer() {
    if (h) {
      CloseHandle(h);
    }
  }
  // Сон на us микросекунд; false — таймера высокого разрешения нет (тогда только уступаем ядро).
  bool Wait(int us) {
    if (!tried) {
      tried = true;
      h = CreateWaitableTimerExW(nullptr, nullptr, CREATE_WAITABLE_TIMER_HIGH_RESOLUTION,
                                 TIMER_ALL_ACCESS);
    }
    if (!h) {
      SwitchToThread();
      return false;
    }
    LARGE_INTEGER due;
    due.QuadPart = -static_cast<LONGLONG>(us) * 10;  // относительное время, по 100 нс
    if (!SetWaitableTimer(h, &due, 0, nullptr, nullptr, FALSE)) {
      SwitchToThread();
      return false;
    }
    WaitForSingleObject(h, INFINITE);
    return true;
  }
};
#endif

struct Stats {
  std::atomic<uint64_t> episodes{0};
  std::atomic<uint64_t> episode_ns{0};
  std::atomic<uint64_t> sleeps{0};
  std::atomic<uint64_t> sleep_ns{0};
  std::atomic<uint64_t> sleep_max_ns{0};
  std::atomic<uint64_t> early{0};  // итерации без задержки: GPU успел что-то записать
  std::atomic<int64_t> last_log{0};
};

Stats g_stats;

void CloseEpisode(const Episode& ep) {
  if (!ep.valid) {
    return;
  }
  g_stats.episodes.fetch_add(1, std::memory_order_relaxed);
  g_stats.episode_ns.fetch_add(
      static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(ep.last - ep.first).count()),
      std::memory_order_relaxed);
}

void MaybeLog(Clock::time_point now) {
  const int64_t now_s =
      std::chrono::duration_cast<std::chrono::seconds>(now.time_since_epoch()).count();
  int64_t last = g_stats.last_log.load(std::memory_order_relaxed);
  if (last == 0) {
    g_stats.last_log.compare_exchange_strong(last, now_s, std::memory_order_relaxed);
    return;
  }
  if (now_s - last < 30 || !g_stats.last_log.compare_exchange_strong(last, now_s, std::memory_order_relaxed)) {
    return;
  }
  const double secs = static_cast<double>(now_s - last);
  const uint64_t episodes = g_stats.episodes.exchange(0, std::memory_order_relaxed);
  const uint64_t episode_ns = g_stats.episode_ns.exchange(0, std::memory_order_relaxed);
  const uint64_t sleeps = g_stats.sleeps.exchange(0, std::memory_order_relaxed);
  const uint64_t sleep_ns = g_stats.sleep_ns.exchange(0, std::memory_order_relaxed);
  const uint64_t sleep_max_ns = g_stats.sleep_max_ns.exchange(0, std::memory_order_relaxed);
  const uint64_t early = g_stats.early.exchange(0, std::memory_order_relaxed);
  REXLOG_INFO(
      "[nhl13] fence wait: {:.0f} waits/s, avg {:.2f} ms each, {:.0f}% of time waiting; {:.0f} sleeps/s "
      "of {} us asked, {:.0f} us actual (max {:.0f}); {:.0f} early checks/s",
      episodes / secs, episodes ? episode_ns / 1e6 / episodes : 0.0, episode_ns / 1e7 / secs, sleeps / secs,
      REXCVAR_GET(nhl_fence_wait_sleep_us), sleeps ? sleep_ns / 1e3 / sleeps : 0.0, sleep_max_ns / 1e3,
      early / secs);
}

}  // namespace

extern "C" void sub_82663148(PPCContext& ctx, uint8_t* base) {
  if (!REXCVAR_GET(nhl_fence_wait)) {
    __imp__sub_82663148(ctx, base);
    return;
  }
  thread_local Episode ep;
#if defined(_WIN32)
  thread_local SleepTimer timer;
#endif
  const uint32_t state = ctx.r3.u32;
  const uint32_t dev = Load32(base, state);
  const uint32_t writeback = Load32(base, dev + kDeviceWriteback);
  const uint32_t start_tb = Load32(base, state + kStateStartTimebase);
  const Clock::time_point now = Clock::now();

  Snapshot cur;
  Read(base, dev, writeback, cur);
  if (!ep.valid || ep.state != state || ep.start_tb != start_tb || ep.dev != dev) {
    // новый цикл ожидания: прежний закрыт
    CloseEpisode(ep);
    ep.state = state;
    ep.start_tb = start_tb;
    ep.dev = dev;
    ep.first = now;
    ep.snap = cur;
    ep.valid = true;
    MaybeLog(now);
  } else if (!(cur == ep.snap)) {
    // GPU что-то записал с прошлой итерации — без задержки к проверке условия
    ep.snap = cur;
    ep.last = now;
    g_stats.early.fetch_add(1, std::memory_order_relaxed);
    __imp__sub_82663148(ctx, base);
    return;
  }
  ep.last = now;

  if (!(cur.flags & 0x02)) {
    const auto age = std::chrono::duration_cast<std::chrono::microseconds>(now - ep.first).count();
    const int sleep_us = REXCVAR_GET(nhl_fence_wait_sleep_us);
    if (age < REXCVAR_GET(nhl_fence_wait_spin_us) || sleep_us <= 0) {
      // опрос с паузой: ~1–2 мкс, выход при первом изменении
      for (int i = 0; i < 64; ++i) {
        _mm_pause();
        if ((i & 7) == 7) {
          Read(base, dev, writeback, cur);
          if (!(cur == ep.snap)) {
            break;
          }
        }
      }
    } else {
      const Clock::time_point t0 = Clock::now();
#if defined(_WIN32)
      timer.Wait(sleep_us);
#else
      std::this_thread::sleep_for(std::chrono::microseconds(sleep_us));
#endif
      const Clock::time_point t1 = Clock::now();
      const uint64_t ns = static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(t1 - t0).count());
      g_stats.sleeps.fetch_add(1, std::memory_order_relaxed);
      g_stats.sleep_ns.fetch_add(ns, std::memory_order_relaxed);
      uint64_t prev = g_stats.sleep_max_ns.load(std::memory_order_relaxed);
      while (ns > prev && !g_stats.sleep_max_ns.compare_exchange_weak(prev, ns, std::memory_order_relaxed)) {
      }
      ep.last = t1;
    }
  }
  __imp__sub_82663148(ctx, base);
}
