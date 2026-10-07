// НХЛ больше 30 команд во франшизе (разбор — docs/teams.md).
//
// 1. Календарь лиги во франшизе собирается в буферы ровно на 1350 игр — 37 800 байт по
//    28 на игру (828DE2C8, 827B2300): у НХЛ 2012 года было 1230 игр + Матч звёзд + 60
//    предсезонных. У 32 команд по 84 игры — 1344 + 64 предсезонных > 1350: буфер
//    переполнялся, портил кучу, и следующее выделение памяти зацикливалось («вечная
//    загрузка» при создании франшизы). Врезки nhl13_team_hooks.toml поднимают
//    вместимость (и размер буфера, и предел, который передаётся дальше).
// 2. Состав НХЛ во франшизе задан кодом, а не базой: 82809330 строит список команд
//    0…29 (828FD590 — добавить в список на 60) и дерево «лига → 2 конференции → 6
//    дивизионов по 5» с зашитыми номерами (узлы по 28 байт: id, число команд,
//    массив команд, …, число детей, дети — массивы выделяются по размеру, 828FE278 и
//    828FE540). С nhl_teams = 32 подмена вызывает оригинал, дописывает команды 30 и 31
//    и перестраивает дивизионы 6 + 5 + 5 в конференции.
// 3. 8289A868 добавлял во франшизу сборные Матча звёзд — строки 30 и 31 базы; при 32
//    командах там новые клубы, и подмена его пропускает (Матча звёзд в календаре нет).

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <string>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ppc.h>

#if defined(_WIN32)
#include "nhl13_debug.h"
#endif

REXCVAR_DEFINE_INT32(nhl_teams, 30, "NHL13",
                     "NHL teams in franchise: 30 = original, 32 = teams 30/31 of the DB are NHL clubs")
    .range(30, 32)
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

extern "C" void __imp__sub_82809330(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_8289A868(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_82819268(PPCContext& ctx, uint8_t* base);
extern "C" void sub_828FD590(PPCContext& ctx, uint8_t* base);  // список команд: добавить
extern "C" void sub_828FE278(PPCContext& ctx, uint8_t* base);  // узел: задать команды

namespace {

constexpr uint32_t kScheduleCapacity = 1600;  // игр на лигу (34 команды × 84 + предсезонка)
constexpr uint32_t kScheduleEntryBytes = 28;

uint8_t* Host(uint8_t* base, uint32_t addr) {
  return base + addr + (addr >= 0xE0000000u ? 0x1000u : 0u);
}

uint32_t Load32(uint8_t* base, uint32_t addr) {
  uint32_t v;
  std::memcpy(&v, Host(base, addr), 4);
  return __builtin_bswap32(v);
}

void Store32(uint8_t* base, uint32_t addr, uint32_t v) {
  v = __builtin_bswap32(v);
  std::memcpy(Host(base, addr), &v, 4);
}

// Разведка: стек первого вызова подменённой функции — в nhl13_teams.log рядом с exe.
void LogStackOnce(const char* tag) {
#if defined(_WIN32)
  CONTEXT c{};
  RtlCaptureContext(&c);
  DWORD64 frames[40];
  const int n = Nhl13CaptureStack(c, frames, 40);
  wchar_t exe[MAX_PATH];
  GetModuleFileNameW(nullptr, exe, MAX_PATH);
  std::wstring path(exe);
  path = path.substr(0, path.find_last_of(L"\\/") + 1) + L"nhl13_teams.log";
  std::lock_guard<std::mutex> lock(Nhl13DbghelpMutex());
  if (FILE* f = _wfopen(path.c_str(), L"a")) {
    Nhl13EnsureSymbols();
    fprintf(f, "== %s\n", tag);
    for (int i = 0; i < n; ++i) {
      Nhl13WriteFrame(f, i, frames[i]);
    }
    fclose(f);
  }
#endif
}

bool ThirtyTwo() {
  static const bool on = [] {
    const bool v = REXCVAR_GET(nhl_teams) == 32;
    REXLOG_INFO("[nhl13] franchise NHL teams: {}", v ? 32 : 30);
    return v;
  }();
  return on;
}

// Дивизионы для 32 команд (номера строк базы; 30 — Tappara/«Сиэтл», 31 — TPS/«Вегас»,
// 22 — Phoenix/«Юта»). id узлов — как у игры: 3–5 Запад, 6–8 Восток.
struct Division {
  uint32_t id;
  uint32_t count;
  uint32_t teams[8];
};
constexpr Division kDivisions[] = {
    {3, 5, {1, 4, 11, 28, 30}},       // WPG CGY EDM VAN SEA
    {4, 5, {0, 13, 25, 22, 31}},      // ANA LA SJ UTA VGK
    {5, 6, {6, 7, 9, 14, 16, 24}},    // CHI COL DAL MIN NSH STL
    {6, 6, {5, 8, 10, 12, 26, 29}},   // CAR CBJ DET FLA TB WSH
    {7, 5, {17, 18, 19, 21, 23}},     // NJ NYI NYR PHI PIT
    {8, 5, {2, 3, 15, 20, 27}},       // BOS BUF MTL OTT TOR
};

// Найти узел с данным id в дереве (дети — массив указателей по +20, число — +16).
uint32_t FindNode(uint8_t* base, uint32_t node, uint32_t id, int depth = 0) {
  if (!node || depth > 4) {
    return 0;
  }
  if (Load32(base, node) == id && depth > 0) {
    return node;
  }
  const uint32_t n = Load32(base, node + 16);
  const uint32_t kids = Load32(base, node + 20);
  for (uint32_t i = 0; i < n && i < 16; ++i) {
    if (uint32_t hit = FindNode(base, Load32(base, kids + 4 * i), id, depth + 1)) {
      return hit;
    }
  }
  return 0;
}

}  // namespace

// li rX, 1350 — число игр в буфере календаря (заполнение нулями и предел для вызовов).
void Nhl13ScheduleCapacity(PPCRegister& r) {
  r.u64 = kScheduleCapacity;
}

// ori r3, r3, 0x93A8 — размер буфера календаря в байтах перед выделением.
void Nhl13ScheduleBytes(PPCRegister& r) {
  r.u64 = kScheduleCapacity * kScheduleEntryBytes;
}

// Фабрика структуры лиги. Меню выбора команды (827C2BA8, через переходник 828D12F0 —
// lr указывает в 827C2BA8) пока получает НХЛ на 30 команд: его массивы рассчитаны на
// 30/60 команд, и с 32 экран падал в скрипте; лига франшизы строится на 32.
thread_local bool t_menu_structure = false;

extern "C" void sub_82819268(PPCContext& ctx, uint8_t* base) {
  const uint32_t lr = static_cast<uint32_t>(ctx.lr);
  const bool prev = t_menu_structure;
  t_menu_structure = lr >= 0x827C2BA8 && lr < 0x827C2F70;
  __imp__sub_82819268(ctx, base);
  t_menu_structure = prev;
}

// Структура НХЛ: r3 — ?, r4 — корень дерева (может быть 0), r5 — список команд (может быть 0).
extern "C" void sub_82809330(PPCContext& ctx, uint8_t* base) {
  const uint32_t root = ctx.r4.u32;
  const uint32_t list = ctx.r5.u32;
  const uint32_t sp = ctx.r1.u32;
  __imp__sub_82809330(ctx, base);
  if (!ThirtyTwo() || t_menu_structure) {
    return;
  }
  static int logged = 0;
  if (logged++ < 3) {
    LogStackOnce("82809330 (структура НХЛ)");
  }
  const uint64_t saved_r3 = ctx.r3.u64;
  if (list) {
    for (uint32_t team : {30u, 31u}) {
      ctx.r3.u64 = list;
      ctx.r4.u64 = team;
      sub_828FD590(ctx, base);
    }
  }
  if (root) {
    // массив команд — во временной области гостевого стека ниже текущего кадра
    const uint32_t scratch = (sp - 0x200) & ~0xFu;
    ctx.r1.u64 = scratch - 0x100;
    for (const Division& d : kDivisions) {
      const uint32_t node = FindNode(base, root, d.id);
      if (!node) {
        REXLOG_WARN("[nhl13] NHL division {} not found", d.id);
        continue;
      }
      for (uint32_t i = 0; i < d.count; ++i) {
        Store32(base, scratch + 4 * i, d.teams[i]);
      }
      ctx.r3.u64 = node;
      ctx.r4.u64 = d.count;
      ctx.r5.u64 = scratch;
      sub_828FE278(ctx, base);
    }
    ctx.r1.u64 = sp;
  }
  ctx.r3.u64 = saved_r3;
  REXLOG_INFO("[nhl13] NHL structure: 32 teams, divisions 6+5+5");
}

// Сборные Матча звёзд (строки 30/31) во франшизу не добавляются при 32 командах.
extern "C" void sub_8289A868(PPCContext& ctx, uint8_t* base) {
  if (ThirtyTwo()) {
    return;
  }
  __imp__sub_8289A868(ctx, base);
}
