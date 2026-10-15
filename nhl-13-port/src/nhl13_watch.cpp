// Сторож памяти для разведки: какой код игры обращается к заданным гостевым адресам.
//
// Положить рядом с exe файл nhl13_watch.flag со строками «АДРЕС ДЛИНА» (гостевой адрес
// и длина, hex; # — комментарий). Порт закроет страницы с этими адресами (PAGE_NOACCESS),
// и каждое обращение к диапазону попадёт в nhl13_watch.log со стеком вызовов
// (__imp__sub_XXXXXXXX — функции игры). Одинаковые стеки сводятся в одну запись со
// счётчиком. Файл nhl13_unwatch.flag снимает сторожа и дописывает итог.
//
// Как работает: обработчик исключений (первый в цепочке, до рантайма) ловит нарушение
// доступа к своей странице, запоминает стек, возвращает странице исходную защиту и
// включает пошаговый режим (TF); после одной инструкции страница закрывается снова.
// Чужие исключения уходят дальше (MMIO и др. — рантайму). Пока страница открыта для
// одного потока, обращения других потоков могут проскочить — для разведки это
// допустимо. Гостевая память порта — одно отображение с базой 0x100000000.
//
// Программные страницы (Nhl13WatchPage, сторож кучи): до 8 страниц на ходу, в журнал — только
// записи, для которых фильтр вызывающего вернул true (сторож кучи: запись в свободный блок).

#if defined(_WIN32)

#include <windows.h>

#include <algorithm>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cwchar>
#include <map>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "nhl13_debug.h"

namespace {

constexpr uintptr_t kGuestBase = 0x100000000ull;
constexpr uintptr_t kPage = 0x1000;
constexpr int kFrames = 14;
constexpr size_t kRing = 1 << 14;

struct Range {
  uintptr_t lo, hi;  // хост-адреса [lo, hi)
};

struct Event {
  std::atomic<uint32_t> ready{0};
  DWORD tid = 0;
  uintptr_t addr = 0;
  int write = 0;
  int n = 0;
  DWORD64 frames[kFrames] = {};
};

// Разделяемое с обработчиком исключений: меняется только при снятом стороже.
std::vector<Range> g_ranges;
std::vector<std::pair<uintptr_t, DWORD>> g_pages;  // страница и её исходная защита
std::atomic<bool> g_armed{false};
std::atomic<uint64_t> g_write_index{0};
Event g_ring[kRing];
PVOID g_veh = nullptr;

thread_local uintptr_t t_pending[4] = {};

// Программные страницы (хост-адреса), их исходная защита и фильтр записей (гостевой адрес).
constexpr int kProgPages = 8;
std::atomic<uintptr_t> g_prog_page[kProgPages];
std::atomic<DWORD> g_prog_protect[kProgPages];
std::atomic<bool (*)(uint32_t)> g_prog_filter{nullptr};
std::mutex g_prog_mutex;

int ProgSlot(uintptr_t page) {
  for (int i = 0; i < kProgPages; ++i) {
    if (g_prog_page[i].load(std::memory_order_acquire) == page) {
      return i;
    }
  }
  return -1;
}

std::wstring ExeDir() {
  wchar_t exe[MAX_PATH];
  GetModuleFileNameW(nullptr, exe, MAX_PATH);
  std::wstring path(exe);
  return path.substr(0, path.find_last_of(L"\\/") + 1);
}

DWORD OriginalProtect(uintptr_t page) {
  for (const auto& p : g_pages) {
    if (p.first == page) {
      return p.second;
    }
  }
  return 0;
}

LONG CALLBACK WatchHandler(EXCEPTION_POINTERS* ep) {
  const DWORD code = ep->ExceptionRecord->ExceptionCode;
  if (code == EXCEPTION_SINGLE_STEP) {
    bool ours = false;
    for (uintptr_t& page : t_pending) {
      if (page) {
        const bool still = ProgSlot(page) >= 0 ||
                           (g_armed.load(std::memory_order_acquire) && OriginalProtect(page));
        if (still) {
          DWORD old;
          VirtualProtect(reinterpret_cast<void*>(page), kPage, PAGE_NOACCESS, &old);
        }
        page = 0;
        ours = true;
      }
    }
    if (!ours) {
      return EXCEPTION_CONTINUE_SEARCH;
    }
    ep->ContextRecord->EFlags &= ~0x100u;
    return EXCEPTION_CONTINUE_EXECUTION;
  }
  if (code != EXCEPTION_ACCESS_VIOLATION || ep->ExceptionRecord->NumberParameters < 2) {
    return EXCEPTION_CONTINUE_SEARCH;
  }
  const uintptr_t addr = ep->ExceptionRecord->ExceptionInformation[1];
  const uintptr_t page = addr & ~(kPage - 1);
  const int slot = ProgSlot(page);
  const bool prog = slot >= 0;
  const DWORD orig = prog ? g_prog_protect[slot].load(std::memory_order_acquire)
                          : (g_armed.load(std::memory_order_acquire) ? OriginalProtect(page) : 0);
  if (!orig) {
    return EXCEPTION_CONTINUE_SEARCH;
  }
  bool (*filter)(uint32_t) = g_prog_filter.load(std::memory_order_acquire);
  const bool prog_hit = prog && ep->ExceptionRecord->ExceptionInformation[0] == 1 && filter &&
                        filter(static_cast<uint32_t>(addr - kGuestBase));
  if (prog_hit) {
    const uint64_t i = g_write_index.fetch_add(1, std::memory_order_relaxed);
    Event& e = g_ring[i % kRing];
    if (!e.ready.load(std::memory_order_acquire)) {
      e.tid = GetCurrentThreadId();
      e.addr = addr;
      e.write = 1;
      e.n = Nhl13CaptureStack(*ep->ContextRecord, e.frames, kFrames);
      e.ready.store(1, std::memory_order_release);
    }
  }
  for (size_t k = 0; !prog && k < g_ranges.size(); ++k) {
    const Range& r = g_ranges[k];
    if (addr >= r.lo && addr < r.hi) {
      const uint64_t i = g_write_index.fetch_add(1, std::memory_order_relaxed);
      Event& e = g_ring[i % kRing];
      if (!e.ready.load(std::memory_order_acquire)) {
        e.tid = GetCurrentThreadId();
        e.addr = addr;
        e.write = static_cast<int>(ep->ExceptionRecord->ExceptionInformation[0]);
        e.n = Nhl13CaptureStack(*ep->ContextRecord, e.frames, kFrames);
        e.ready.store(1, std::memory_order_release);
      }
      break;
    }
  }
  DWORD old;
  VirtualProtect(reinterpret_cast<void*>(page), kPage, orig, &old);
  for (uintptr_t& p : t_pending) {
    if (!p) {
      p = page;
      break;
    }
  }
  ep->ContextRecord->EFlags |= 0x100u;
  return EXCEPTION_CONTINUE_EXECUTION;
}

struct StackStat {
  uint64_t count = 0;
  uint64_t reads = 0;
  uint64_t writes = 0;
  uintptr_t first_addr = 0;
  DWORD first_tid = 0;
  SYSTEMTIME first{};
  int n = 0;
  DWORD64 frames[kFrames] = {};
};

void Arm(FILE* log, const std::wstring& flag) {
  FILE* f = _wfopen(flag.c_str(), L"r");
  if (!f) {
    return;
  }
  std::vector<Range> ranges;
  char line[256];
  while (fgets(line, sizeof(line), f)) {
    if (line[0] == '#') {
      continue;
    }
    unsigned long long a = 0, n = 0;
    if (sscanf(line, "%llx %llx", &a, &n) == 2 && n) {
      ranges.push_back({kGuestBase + a, kGuestBase + a + n});
    }
  }
  fclose(f);
  DeleteFileW(flag.c_str());
  if (*reinterpret_cast<const uint16_t*>(kGuestBase + 0x82000000) != 0x5A4D) {
    fprintf(log, "!! гостевая память не на 0x%llX — сторож не включён\n",
            static_cast<unsigned long long>(kGuestBase));
    return;
  }
  g_ranges = ranges;
  g_pages.clear();
  for (const Range& r : ranges) {
    for (uintptr_t p = r.lo & ~(kPage - 1); p < r.hi; p += kPage) {
      if (std::none_of(g_pages.begin(), g_pages.end(), [&](auto& x) { return x.first == p; })) {
        MEMORY_BASIC_INFORMATION mbi{};
        VirtualQuery(reinterpret_cast<void*>(p), &mbi, sizeof(mbi));
        g_pages.push_back({p, mbi.Protect});
      }
    }
  }
  if (!g_veh) {
    g_veh = AddVectoredExceptionHandler(1, WatchHandler);
  }
  g_armed.store(true, std::memory_order_release);
  for (const auto& p : g_pages) {
    DWORD old;
    VirtualProtect(reinterpret_cast<void*>(p.first), kPage, PAGE_NOACCESS, &old);
  }
  for (const Range& r : ranges) {
    fprintf(log, "== сторож: 0x%08llX..0x%08llX\n",
            static_cast<unsigned long long>(r.lo - kGuestBase),
            static_cast<unsigned long long>(r.hi - kGuestBase));
  }
  fflush(log);
}

void Disarm() {
  g_armed.store(false, std::memory_order_release);
  for (const auto& p : g_pages) {
    DWORD old;
    VirtualProtect(reinterpret_cast<void*>(p.first), kPage, p.second, &old);
  }
}

void WatchThread() {
  const std::wstring dir = ExeDir();
  const std::wstring flag = dir + L"nhl13_watch.flag";
  const std::wstring unflag = dir + L"nhl13_unwatch.flag";
  std::map<std::vector<DWORD64>, StackStat> stats;
  uint64_t read_index = 0;
  FILE* log = nullptr;
  for (;;) {
    Sleep(200);
    if (!log && g_write_index.load(std::memory_order_acquire) > read_index) {
      log = _wfopen((dir + L"nhl13_watch.log").c_str(), L"a");
    }
    if (GetFileAttributesW(flag.c_str()) != INVALID_FILE_ATTRIBUTES) {
      if (!log) {
        log = _wfopen((dir + L"nhl13_watch.log").c_str(), L"a");
      }
      if (log) {
        Arm(log, flag);
      }
    }
    // Новые события: первое появление стека пишется сразу, дальше — счётчик.
    while (read_index < g_write_index.load(std::memory_order_acquire)) {
      Event& e = g_ring[read_index % kRing];
      if (!e.ready.load(std::memory_order_acquire)) {
        break;
      }
      std::vector<DWORD64> key(e.frames, e.frames + std::min(e.n, 8));
      StackStat& s = stats[key];
      if (s.count == 0 && log) {
        s.n = e.n;
        std::copy(e.frames, e.frames + e.n, s.frames);
        s.first_addr = e.addr;
        s.first_tid = e.tid;
        GetLocalTime(&s.first);
        std::lock_guard<std::mutex> lock(Nhl13DbghelpMutex());
        Nhl13EnsureSymbols();
        fprintf(log, "-- %02u:%02u:%02u.%03u поток %lu, %s 0x%08llX\n", s.first.wHour,
                s.first.wMinute, s.first.wSecond, s.first.wMilliseconds, e.tid,
                e.write == 1 ? "запись" : "чтение",
                static_cast<unsigned long long>(e.addr - kGuestBase));
        for (int i = 0; i < e.n; ++i) {
          Nhl13WriteFrame(log, i, e.frames[i]);
        }
        fflush(log);
      }
      ++s.count;
      (e.write == 1 ? s.writes : s.reads) += 1;
      e.ready.store(0, std::memory_order_release);
      ++read_index;
    }
    if (GetFileAttributesW(unflag.c_str()) != INVALID_FILE_ATTRIBUTES) {
      DeleteFileW(unflag.c_str());
      Disarm();
      if (log) {
        fprintf(log, "== сторож снят; итог по стекам (обращений, чтений/записей, первый адрес):\n");
        std::lock_guard<std::mutex> lock(Nhl13DbghelpMutex());
        for (const auto& [key, s] : stats) {
          fprintf(log, "   %llu (%llu/%llu) 0x%08llX\n", static_cast<unsigned long long>(s.count),
                  static_cast<unsigned long long>(s.reads),
                  static_cast<unsigned long long>(s.writes),
                  static_cast<unsigned long long>(s.first_addr - kGuestBase));
          for (int i = 0; i < std::min(s.n, 4); ++i) {
            Nhl13WriteFrame(log, i, s.frames[i]);
          }
        }
        fflush(log);
      }
      stats.clear();
    }
  }
}

}  // namespace

void Nhl13StartWatcher() {
  std::thread(WatchThread).detach();
}

bool Nhl13WatchPage(uint32_t guest, bool (*filter)(uint32_t)) {
  if (*reinterpret_cast<const uint16_t*>(kGuestBase + 0x82000000) != 0x5A4D) {
    return false;
  }
  const uintptr_t page = (kGuestBase + guest) & ~(kPage - 1);
  std::lock_guard<std::mutex> lock(g_prog_mutex);
  if (ProgSlot(page) >= 0) {
    return true;
  }
  if (std::any_of(g_pages.begin(), g_pages.end(), [&](auto& x) { return x.first == page; })) {
    return false;  // страница уже под сторожем по флагу
  }
  const int slot = ProgSlot(0);
  if (slot < 0) {
    return false;
  }
  MEMORY_BASIC_INFORMATION mbi{};
  VirtualQuery(reinterpret_cast<void*>(page), &mbi, sizeof(mbi));
  if (mbi.Protect != PAGE_READWRITE) {
    return false;
  }
  if (!g_veh) {
    g_veh = AddVectoredExceptionHandler(1, WatchHandler);
  }
  g_prog_filter.store(filter, std::memory_order_release);
  g_prog_protect[slot].store(mbi.Protect, std::memory_order_release);
  g_prog_page[slot].store(page, std::memory_order_release);
  DWORD old;
  VirtualProtect(reinterpret_cast<void*>(page), kPage, PAGE_NOACCESS, &old);
  return true;
}

#else

void Nhl13StartWatcher() {}
bool Nhl13WatchPage(uint32_t, bool (*)(uint32_t)) {
  return false;
}

#endif
