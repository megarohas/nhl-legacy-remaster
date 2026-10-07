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
// 4. Номера франшизы (строки leagueteams) выдаются по порядку при создании: было НХЛ 0…29,
//    АХЛ 30…59 (teamid 32…61), сборные 60/61; при 32 командах — НХЛ 0…31, АХЛ 32…61
//    (номер = teamid). Списки лиг при создании приходят из меню (НХЛ на 30), поэтому
//    перед записью команд (828C0250, 828CD4E8) в список НХЛ дописываются 30 и 31.
//    Код, где зашиты 30 команд НХЛ и начало АХЛ с 30, правится подменами ниже и врезками:
//    827DFB40 «команда НХЛ?» (< 30); фарм-клубы — массив объекта лиги +520 на 30 команд
//    (номер франшизы фарм-клуба + 1; из базы — «teamid + 1 − 2»), +640 — «загружены»,
//    +644 — teamid[30]: элементы 30/31 хранятся снаружи (LeagueExtra); «фарм-клуб − 30»
//    при отправке лишних игроков в АХЛ (828CD928) → − 32; меню франшизы заполняет список
//    АХЛ номерами i + 30 (827C2BA8) → i + 32; 828A6080 ищет teamid среди 60 команд → 62.

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <random>
#include <string>
#include <unordered_map>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ppc.h>
#include <rex/runtime.h>
#include <rex/system/xmemory.h>

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
extern "C" void __imp__sub_8289AF40(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_8289AF68(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_8289B040(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_8289B070(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_8289AB80(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_8289AAA0(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_828A8338(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_828C0250(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_828CD4E8(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_827C2BA8(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_828A6080(PPCContext& ctx, uint8_t* base);
extern "C" void sub_828FD590(PPCContext& ctx, uint8_t* base);  // список команд: добавить
extern "C" void sub_828FD5D8(PPCContext& ctx, uint8_t* base);  // список команд: записать i-й
extern "C" void sub_828FE278(PPCContext& ctx, uint8_t* base);  // узел: задать команды
extern "C" void sub_8289AFB8(PPCContext& ctx, uint8_t* base);  // фарм-клуб общий у 2+ команд?
extern "C" void sub_828FC250(PPCContext& ctx, uint8_t* base);  // итератор команд: создать
extern "C" void sub_828FC2A0(PPCContext& ctx, uint8_t* base);  // итератор команд: удалить
extern "C" void sub_8290A8B8(PPCContext& ctx, uint8_t* base);  // сведения о команде франшизы
extern "C" void sub_829043C0(PPCContext& ctx, uint8_t* base);  // сведения о команде базы

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

uint8_t Load8(uint8_t* base, uint32_t addr) {
  return *Host(base, addr);
}

int32_t NhlTeams() {
  return ThirtyTwo() ? 32 : 30;
}

// Команды 30/31 в массивах объекта лиги на 30 команд (+520 фарм-клубы, +644 teamid).
constexpr int kExtra = 2;

struct LeagueExtra {
  int32_t affiliate[kExtra] = {0, 0};
  uint32_t teamid[kExtra] = {0xFFFFFFFFu, 0xFFFFFFFFu};
};

std::mutex g_extra_mutex;
std::unordered_map<uint32_t, LeagueExtra> g_extra;

LeagueExtra GetExtra(uint32_t league) {
  std::lock_guard<std::mutex> lock(g_extra_mutex);
  auto it = g_extra.find(league);
  return it == g_extra.end() ? LeagueExtra{} : it->second;
}

template <typename F>
void EditExtra(uint32_t league, F&& f) {
  std::lock_guard<std::mutex> lock(g_extra_mutex);
  f(g_extra[league]);
}

bool AffiliatesLoaded(uint8_t* base, uint32_t league) {
  return Load8(base, league + 640) != 0;
}

bool IsExtraIndex(int32_t idx) {
  return ThirtyTwo() && idx >= 30 && idx < 30 + kExtra;
}

// Байт из сведений о команде (франшизы — 8290A8B8 по номеру, базы — 829043C0 по teamid):
// +8 — teamid, +190 — фарм-клуб. Итератор и структура — во временной области гостевого
// стека ниже текущего кадра; регистры-результаты вызывающий восстанавливает сам.
int8_t GuestTeamInfoByte(PPCContext& ctx, uint8_t* base, bool franchise, uint32_t team, uint32_t offset) {
  const uint64_t saved_r1 = ctx.r1.u64;
  const uint32_t iter = (ctx.r1.u32 - 0x200) & ~0xFu;
  const uint32_t info = iter + 0x20;  // до 0x120 байт
  std::memset(Host(base, iter), 0, 0x140);
  ctx.r1.u64 = iter - 0x80;
  ctx.r3.u64 = iter;
  sub_828FC250(ctx, base);
  ctx.r3.u64 = iter;
  ctx.r4.u64 = team;
  ctx.r5.u64 = info;
  if (franchise) {
    sub_8290A8B8(ctx, base);
  } else {
    sub_829043C0(ctx, base);
  }
  const int8_t v = static_cast<int8_t>(Load8(base, info + offset));
  ctx.r3.u64 = iter;
  sub_828FC2A0(ctx, base);
  ctx.r1.u64 = saved_r1;
  return v;
}

// Список лиги при создании франшизы — НХЛ из меню: ровно teamid 0…29 по порядку.
bool IsMenuNhlList(uint8_t* base, uint32_t list) {
  if (Load32(base, list) != 30) {
    return false;
  }
  for (uint32_t i = 0; i < 30; ++i) {
    if (Load32(base, list + 4 + 4 * i) != i) {
      return false;
    }
  }
  return true;
}

// Аргументы r3…r10 подменённой функции — сохранить перед своими гостевыми вызовами.
struct SavedArgs {
  uint64_t r[8];
  explicit SavedArgs(const PPCContext& ctx)
      : r{ctx.r3.u64, ctx.r4.u64, ctx.r5.u64, ctx.r6.u64, ctx.r7.u64, ctx.r8.u64, ctx.r9.u64, ctx.r10.u64} {}
  void Restore(PPCContext& ctx) const {
    ctx.r3.u64 = r[0];
    ctx.r4.u64 = r[1];
    ctx.r5.u64 = r[2];
    ctx.r6.u64 = r[3];
    ctx.r7.u64 = r[4];
    ctx.r8.u64 = r[5];
    ctx.r9.u64 = r[6];
    ctx.r10.u64 = r[7];
  }
};

void AppendExtraTeams(PPCContext& ctx, uint8_t* base, uint32_t league) {
  const uint32_t list = league + 16;
  if (!ThirtyTwo() || !IsMenuNhlList(base, list)) {
    return;
  }
  const SavedArgs args(ctx);
  for (uint32_t k = 0; k < kExtra; ++k) {
    ctx.r3.u64 = list;
    ctx.r4.u64 = 30 + k;
    sub_828FD590(ctx, base);
  }
  EditExtra(league, [](LeagueExtra& e) {
    for (int k = 0; k < kExtra; ++k) {
      e.teamid[k] = 30 + k;
    }
  });
  args.Restore(ctx);
  static int logged = 0;
  if (logged++ < 4) {
    REXLOG_INFO("[nhl13] league {:08X}: NHL list 30 -> {} teams", league, Load32(base, list));
  }
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
  if (logged <= 3) {
    REXLOG_INFO("[nhl13] NHL structure: 32 teams, divisions 6+5+5");
  }
}

// Сборные Матча звёзд: 8289A868 добавляет во франшизу teamid 30/31 (зашито) сразу после АХЛ
// и пишет их номера в состояния 53/54. При 32 командах сборные — строки 86/87 базы
// (tools/nhl32.py), и создаются они в конце, после юниоров (номера 124/125), чтобы номера
// проспектов (62/63) и юниоров (64+) остались как в оригинале: вызов для лиги НХЛ
// откладывается и выполняется после 828E7AC0 последней группы лиг (юниоры).
namespace {
struct DeferredAllStars {
  bool pending = false;
  uint32_t league = 0, settings = 0;
  int call = 0;
};
DeferredAllStars g_allstars;
int g_league_group_calls = 0;
thread_local bool t_allstars_now = false;
}  // namespace

extern "C" void sub_8289A868(PPCContext& ctx, uint8_t* base) {
  if (ThirtyTwo() && !t_allstars_now) {
    if (Load32(base, ctx.r4.u32 + 600) == 2) {  // лига, у которой есть сборные (НХЛ)
      g_allstars = {true, ctx.r3.u32, ctx.r4.u32, g_league_group_calls};
    }
    return;
  }
  __imp__sub_8289A868(ctx, base);
}

// li r11, 30 / li r10, 31 в 8289A868 — teamid сборных.
void Nhl13AllStarTeamA(PPCRegister& r) {
  if (ThirtyTwo()) {
    r.u64 = 86;
  }
}

void Nhl13AllStarTeamB(PPCRegister& r) {
  if (ThirtyTwo()) {
    r.u64 = 87;
  }
}

extern "C" void __imp__sub_828E7AC0(PPCContext& ctx, uint8_t* base);
// 828E7AC0 зовут в цикле по группам лиг (828F8808: 828F8A34 и 828F8E24): r7 — номер группы,
// r19 вызывающего (на входе ещё не тронут) — число групп. Сборные — после последней группы.
extern "C" void sub_828E7AC0(PPCContext& ctx, uint8_t* base) {
  const int call = ++g_league_group_calls;
  const bool last_group = ctx.r7.s32 == ctx.r19.s32 - 1;
  __imp__sub_828E7AC0(ctx, base);
  if (!ThirtyTwo() || !g_allstars.pending || call <= g_allstars.call || !last_group) {
    return;
  }
  g_allstars.pending = false;
  const SavedArgs args(ctx);
  ctx.r3.u64 = g_allstars.league;
  ctx.r4.u64 = g_allstars.settings;
  t_allstars_now = true;
  __imp__sub_8289A868(ctx, base);
  t_allstars_now = false;
  args.Restore(ctx);
  REXLOG_INFO("[nhl13] All-Star teams (86/87) created after junior leagues");
}

// --- Номера франшизы при 32 командах (пункт 4 в начале файла) ---

// «Команда НХЛ?» по номеру франшизы: 0 ≤ номер < 30 → < 32.
extern "C" void sub_827DFB40(PPCContext& ctx, uint8_t* base) {
  (void)base;
  const int32_t idx = ctx.r3.s32;
  ctx.r3.u64 = (idx >= 0 && idx < NhlTeams()) ? 1 : 0;
}

// Список команды НХЛ перед записью команд франшизы — с 30 и 31.
extern "C" void sub_828C0250(PPCContext& ctx, uint8_t* base) {
  AppendExtraTeams(ctx, base, ctx.r3.u32);
  __imp__sub_828C0250(ctx, base);
}

extern "C" void sub_828CD4E8(PPCContext& ctx, uint8_t* base) {
  AppendExtraTeams(ctx, base, ctx.r3.u32);
  __imp__sub_828CD4E8(ctx, base);
}

// Фарм-клуб команды НХЛ (номер франшизы + 1; −1 — не загружены).
extern "C" void sub_8289AF40(PPCContext& ctx, uint8_t* base) {
  const uint32_t league = ctx.r3.u32;
  const int32_t idx = ctx.r4.s32;
  if (IsExtraIndex(idx)) {
    ctx.r3.s64 = AffiliatesLoaded(base, league) ? GetExtra(league).affiliate[idx - 30] : -1;
    return;
  }
  __imp__sub_8289AF40(ctx, base);
}

// Команды НХЛ с данным фарм-клубом: номера в out[], r3 — сколько.
extern "C" void sub_8289AF68(PPCContext& ctx, uint8_t* base) {
  const uint32_t league = ctx.r3.u32;
  const int32_t affiliate = ctx.r4.s32;
  const uint32_t out = ctx.r5.u32;
  __imp__sub_8289AF68(ctx, base);
  if (!ThirtyTwo() || !AffiliatesLoaded(base, league)) {
    return;
  }
  uint32_t n = ctx.r3.u32;
  const LeagueExtra e = GetExtra(league);
  for (int k = 0; k < kExtra; ++k) {
    if (e.affiliate[k] == affiliate) {
      Store32(base, out + 4 * n, 30 + k);
      ++n;
    }
  }
  ctx.r3.u64 = n;
}

// Общий ли фарм-клуб команды idx с другими (8289AFB8 по её фарм-клубу).
extern "C" void sub_8289B040(PPCContext& ctx, uint8_t* base) {
  const uint32_t league = ctx.r3.u32;
  const int32_t idx = ctx.r4.s32;
  if (IsExtraIndex(idx)) {
    if (!AffiliatesLoaded(base, league)) {
      ctx.r3.u64 = 0;
      return;
    }
    ctx.r4.s64 = GetExtra(league).affiliate[idx - 30];
    sub_8289AFB8(ctx, base);
    return;
  }
  __imp__sub_8289B040(ctx, base);
}

// Команда НХЛ — её фарм-клуб в *out (r3 = 1); иначе — команды НХЛ с фарм-клубом idx.
extern "C" void sub_8289B070(PPCContext& ctx, uint8_t* base) {
  const uint32_t league = ctx.r3.u32;
  const int32_t idx = ctx.r4.s32;
  const uint32_t out = ctx.r5.u32;
  if (IsExtraIndex(idx)) {
    if (!AffiliatesLoaded(base, league)) {
      ctx.r3.u64 = 0;
      return;
    }
    Store32(base, out, static_cast<uint32_t>(GetExtra(league).affiliate[idx - 30]));
    ctx.r3.u64 = 1;
    return;
  }
  __imp__sub_8289B070(ctx, base);
}

// Номер команды НХЛ по teamid (массив +644 на 30; −1 — нет).
extern "C" void sub_8289AB80(PPCContext& ctx, uint8_t* base) {
  const uint32_t league = ctx.r3.u32;
  const uint32_t teamid = ctx.r4.u32;
  __imp__sub_8289AB80(ctx, base);
  if (!ThirtyTwo() || ctx.r3.s32 != -1) {
    return;
  }
  const LeagueExtra e = GetExtra(league);
  for (int k = 0; k < kExtra; ++k) {
    if (e.teamid[k] == teamid) {
      ctx.r3.u64 = 30 + k;
      return;
    }
  }
}

// Фарм-клубы по командам франшизы (leagueteams.ahlaffiliate) — и для 30/31.
extern "C" void sub_8289AAA0(PPCContext& ctx, uint8_t* base) {
  const uint32_t league = ctx.r3.u32;
  __imp__sub_8289AAA0(ctx, base);
  if (!ThirtyTwo()) {
    return;
  }
  const uint64_t r3 = ctx.r3.u64;
  int32_t aff[kExtra];
  for (int k = 0; k < kExtra; ++k) {
    aff[k] = GuestTeamInfoByte(ctx, base, true, 30 + k, 190);
  }
  EditExtra(league, [&](LeagueExtra& e) {
    for (int k = 0; k < kExtra; ++k) {
      e.affiliate[k] = aff[k];
    }
  });
  ctx.r3.u64 = r3;
}

// Фарм-клубы по базе: exhibitionteams.ahlaffiliate = teamid + 1, во франшизе — номер + 1;
// оригинал вычитает 2 (АХЛ с 30), при 32 командах номер АХЛ = teamid — разницы нет.
extern "C" void sub_828A8338(PPCContext& ctx, uint8_t* base) {
  const uint32_t league = ctx.r3.u32;
  __imp__sub_828A8338(ctx, base);
  if (!ThirtyTwo()) {
    return;
  }
  const uint64_t r3 = ctx.r3.u64;
  for (uint32_t i = 0; i < 30; ++i) {
    const uint32_t a = league + 520 + 4 * i;
    Store32(base, a, Load32(base, a) + 2);
  }
  int32_t aff[kExtra];
  for (int k = 0; k < kExtra; ++k) {
    aff[k] = GuestTeamInfoByte(ctx, base, false, 30 + k, 190);
  }
  EditExtra(league, [&](LeagueExtra& e) {
    for (int k = 0; k < kExtra; ++k) {
      e.affiliate[k] = aff[k];
    }
  });
  ctx.r3.u64 = r3;
  static int logged = 0;
  if (logged++ < 2) {
    REXLOG_INFO("[nhl13] league {:08X}: affiliates +2, teams 30/31 -> {} {}", league, aff[0], aff[1]);
  }
}

// Меню франшизы: список АХЛ — номера франшизы i + 30 (и копия рядом) → i + 32.
extern "C" void sub_827C2BA8(PPCContext& ctx, uint8_t* base) {
  const uint32_t self = ctx.r3.u32;
  const int32_t league = ctx.r5.s32;
  __imp__sub_827C2BA8(ctx, base);
  if (!ThirtyTwo() || league != 1) {
    return;
  }
  for (const uint32_t list : {self + 5896 + 484, self + 2992 + 484}) {
    if (Load32(base, list) != 30) {
      continue;
    }
    bool shifted = true;
    for (uint32_t i = 0; i < 30 && shifted; ++i) {
      shifted = Load32(base, list + 4 + 4 * i) == i + 30;
    }
    if (shifted) {
      for (uint32_t i = 0; i < 30; ++i) {
        Store32(base, list + 4 + 4 * i, i + 32);
      }
    }
  }
}

// teamid → номер франшизы: перебор только первых 60 команд (последний клуб АХЛ — 61).
extern "C" void sub_828A6080(PPCContext& ctx, uint8_t* base) {
  const uint32_t teamid = ctx.r4.u32;
  __imp__sub_828A6080(ctx, base);
  if (ThirtyTwo() && ctx.r3.s32 == 60 && teamid == 61) {
    ctx.r3.u64 = 61;
  }
}

// Врезки (nhl13_team_hooks.toml): чтение фарм-клуба команды НХЛ из массива +520 в
// 828C0250 (r11 ← [r30 + 520 + 4·r29]) и 828CD4E8 (r11 ← [r29 + 520 + 4·r15]).
void Nhl13AffiliateAt(PPCRegister& value, PPCRegister& index, PPCRegister& league) {
  if (IsExtraIndex(index.s32)) {
    value.s64 = GetExtra(league.u32).affiliate[index.s32 - 30];
  }
}

// 828CD928 addi r23, r11, -30: номер АХЛ (с 1) фарм-клуба команды r16 — для лишних
// игроков; при 32 командах АХЛ начинается с 32.
void Nhl13AffiliateAhl(PPCRegister& ahl, PPCRegister& value, PPCRegister& index, PPCRegister& league) {
  if (!ThirtyTwo()) {
    return;
  }
  const int32_t idx = index.s32;
  const int32_t v = IsExtraIndex(idx) ? GetExtra(league.u32).affiliate[idx - 30] : value.s32;
  ahl.s64 = v - 32;
}

// Кэш сведений о командах НХЛ (0x83987B64): записи 30/31 — за счётчиком (+4116).
namespace {
constexpr uint32_t kTeamCacheRecord = 136;
constexpr uint32_t kTeamCacheExtra = 4116;  // исходный размер объекта
constexpr uint32_t kTeamCacheFlags = 4080;

uint32_t TeamCacheOffset(int32_t idx) {
  return kTeamCacheExtra + static_cast<uint32_t>(idx - 30) * kTeamCacheRecord;
}

void ClearExtraCacheFlags(uint8_t* base, uint32_t cache) {
  for (int k = 0; k < kExtra; ++k) {
    *Host(base, cache + kTeamCacheFlags + 30 + k) = 0;
  }
}
}  // namespace

extern "C" void __imp__sub_8291FFC0(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_82917CB0(PPCContext& ctx, uint8_t* base);

// 82920020: li r3, 4116 — размер объекта.
void Nhl13TeamCacheBytes(PPCRegister& r) {
  if (ThirtyTwo()) {
    r.u64 = kTeamCacheExtra + kExtra * kTeamCacheRecord;
  }
}

// mulli rX, rI, 136 — смещение записи команды.
void Nhl13TeamCacheOffset(PPCRegister& offset, PPCRegister& index) {
  if (IsExtraIndex(index.s32)) {
    offset.u64 = TeamCacheOffset(index.s32);
  }
}

// 82917CD8: mulli r10, r29, 34 — то же в словах (дальше + 9 + k, · 4).
void Nhl13TeamCacheWords(PPCRegister& words, PPCRegister& index) {
  if (IsExtraIndex(index.s32)) {
    words.u64 = TeamCacheOffset(index.s32) / 4;
  }
}

// Конструктор: обнулить и записи 30/31 с их флагами.
extern "C" void sub_8291FFC0(PPCContext& ctx, uint8_t* base) {
  const uint32_t cache = ctx.r3.u32;
  __imp__sub_8291FFC0(ctx, base);
  if (ThirtyTwo()) {
    std::memset(Host(base, cache + kTeamCacheExtra), 0, kExtra * kTeamCacheRecord);
    ClearExtraCacheFlags(base, cache);
  }
}

// Сброс флагов «посчитано» (30) — и для 30/31.
extern "C" void sub_82917CB0(PPCContext& ctx, uint8_t* base) {
  const uint32_t cache = ctx.r3.u32;
  __imp__sub_82917CB0(ctx, base);
  if (ThirtyTwo()) {
    ClearExtraCacheFlags(base, cache);
  }
}

// Врезки «АХЛ с 30» (nhl13_team_hooks.toml): при 32 командах АХЛ начинается с 32.
void Nhl13AhlShift(PPCRegister& r) {  // номер − 30 → − 32
  if (ThirtyTwo()) {
    r.s64 -= 2;
  }
}

void Nhl13AhlUnshift(PPCRegister& r) {  // teamid − 2 → teamid
  if (ThirtyTwo()) {
    r.s64 += 2;
  }
}

void Nhl13AhlBase(PPCRegister& r) {  // li 30 → 32
  if (ThirtyTwo()) {
    r.u64 = 32;
  }
}

// cmpwi crN, rX, 30 по командам НХЛ → сравнение с числом команд.
void Nhl13NhlBound(PPCRegister& r, PPCCRRegister& cr) {
  if (ThirtyTwo()) {
    const int32_t v = r.s32, n = NhlTeams();
    cr.lt = v < n;
    cr.gt = v > n;
    cr.eq = v == n;
  }
}

void Nhl13StatsCacheCount(PPCRegister& r) {
  if (ThirtyTwo() && r.s32 > 30) {
    static int logged = 0;
    if (logged++ < 2) {
      REXLOG_INFO("[nhl13] StatsCache: {} team rows -> 30", r.s32);
    }
    r.u64 = 30;
  }
}

namespace {
void CompareInto(PPCCRRegister& cr, int32_t v, int32_t n) {
  cr.lt = v < n;
  cr.gt = v > n;
  cr.eq = v == n;
}
}  // namespace

// cmpwi crN, rX, 60 по профи-командам (НХЛ + АХЛ) → НХЛ + 30.
void Nhl13ProBound(PPCRegister& r, PPCCRRegister& cr) {
  if (ThirtyTwo()) {
    CompareInto(cr, r.s32, NhlTeams() + 30);
  }
}

// Число команд НХЛ из списка меню (30) → число команд НХЛ франшизы.
void Nhl13NhlCount(PPCRegister& r) {
  if (ThirtyTwo() && r.s32 == 30) {
    r.u64 = static_cast<uint64_t>(NhlTeams());
  }
}

// li rX, 29 — последняя команда НХЛ.
void Nhl13NhlLast(PPCRegister& r) {
  if (ThirtyTwo()) {
    r.u64 = static_cast<uint64_t>(NhlTeams() - 1);
  }
}

// Для сгенерированных врезок (src/nhl13_team_sites.cpp, tools/team_hooks.py).
bool Nhl13ThirtyTwo() {
  return ThirtyTwo();
}

// 829470E8 (загрузка франшизы, 8294B068): средние и разброс 7 показателей по командам лиги —
// таблица 7 × 30 слов на стеке (шаг строки 120), цикл — по числу команд. При 32 командах
// последняя строка уходила на сохранённые регистры, и у вызывающего портились указатели
// (падение после создания сейва). Пока считаем по первым 30 командам.
extern "C" void __imp__sub_829470E8(PPCContext& ctx, uint8_t* base);
extern "C" void sub_829470E8(PPCContext& ctx, uint8_t* base) {
  if (ThirtyTwo() && ctx.r5.s32 > 30) {
    static int logged = 0;
    if (logged++ < 2) {
      REXLOG_INFO("[nhl13] 829470E8: {} teams -> 30", ctx.r5.s32);
    }
    ctx.r5.u64 = 30;
  }
  __imp__sub_829470E8(ctx, base);
}


// 828EF198: кадр на 16 байт больше (пара к addi r1, r1, 1136 в эпилоге).
void Nhl13StackGrow16(PPCRegister& r1) {
  if (ThirtyTwo()) {
    r1.u64 -= 16;
  }
}

// Порядок драфта первого сезона: статическая таблица 2012 года (0x83835200, 30 номеров) +
// команды 30/31 в конце — в системной куче гостя (выделяется один раз).
void Nhl13DraftOrderTable(PPCRegister& r9) {
  if (!ThirtyTwo()) {
    return;
  }
  static const uint32_t table = [] {
    auto* memory = rex::Runtime::instance()->memory();
    const uint32_t addr = memory->SystemHeapAlloc(4 * 32);
    auto* dst = memory->TranslateVirtual<uint8_t*>(addr);
    const auto* src = memory->TranslateVirtual<const uint8_t*>(0x83835200u);
    std::memcpy(dst, src, 4 * 30);
    for (uint32_t k = 0; k < 2; ++k) {
      const uint32_t v = __builtin_bswap32(30 + k);
      std::memcpy(dst + 4 * (30 + k), &v, 4);
    }
    REXLOG_INFO("[nhl13] draft order table 30 -> 32 at {:08X}", addr);
    return addr;
  }();
  r9.u64 = table;
}

// Лотерея драфта при 32 командах (82931EF8, вместо розыгрыша 2012 года): 16 команд вне
// плей-офф лежат на стеке r1+608 от худшей к лучшей. Правила НХЛ с 2022 года: два розыгрыша
// (1-й и 2-й пики), шансы по месту до лотереи, победитель поднимается не больше чем на 10
// мест, второй раз одна команда не выигрывает.
bool Nhl13DraftLottery(PPCRegister& r1, PPCRegister& r27, PPCRegister& r29) {
  if (!ThirtyTwo()) {
    return false;
  }
  static const uint32_t kOdds[16] = {185, 135, 115, 95, 85, 75, 65, 60, 50, 35, 30, 25, 20, 15, 5, 5};
  static std::mt19937 rng{std::random_device{}()};
  auto* order = rex::Runtime::instance()->memory()->TranslateVirtual<uint8_t*>(r1.u32 + 608);
  uint32_t teams[16];
  std::memcpy(teams, order, sizeof(teams));  // как есть, big-endian
  int cur[16];  // cur[место] = место до лотереи
  for (int i = 0; i < 16; ++i) {
    cur[i] = i;
  }
  bool won[16] = {};
  int winners[2];
  for (int draw = 0; draw < 2; ++draw) {
    uint32_t total = 0;
    for (int i = 0; i < 16; ++i) {
      total += won[i] ? 0 : kOdds[i];
    }
    uint32_t x = rng() % total;
    int w = 0;
    for (; w < 15; ++w) {
      if (won[w]) {
        continue;
      }
      if (x < kOdds[w]) {
        break;
      }
      x -= kOdds[w];
    }
    won[w] = true;
    winners[draw] = w;
    int p = 0;
    while (cur[p] != w) {
      ++p;
    }
    const int target = std::max(draw, p - 10);
    for (int k = p; k > target; --k) {
      cur[k] = cur[k - 1];
    }
    cur[target] = w;
  }
  for (int k = 0; k < 16; ++k) {
    std::memcpy(order + 4 * k, &teams[cur[k]], 4);
  }
  REXLOG_INFO("[nhl13] draft lottery: winners {} and {} (places before lottery, 0 = worst); team {} picks 1st",
              winners[0], winners[1], __builtin_bswap32(teams[cur[0]]));
  r27.u64 = 0;
  r29.u64 = 1;
  return true;
}

// 825F7C90 — ошибка менеджера памяти гостя: печатает [r3+12] и twi 31, r0, 22 (рантайм
// пишет «trap hit (type 22)» и продолжает). Сообщение и стек — в лог / nhl13_teams.log.
extern "C" void __imp__sub_825F7C90(PPCContext& ctx, uint8_t* base);
extern "C" void sub_825F7C90(PPCContext& ctx, uint8_t* base) {
  static int logged = 0;
  if (logged < 8) {
    ++logged;
    const uint32_t msg = Load32(base, ctx.r3.u32 + 12);
    std::string text;
    if (msg) {
      for (uint32_t i = 0; i < 160; ++i) {
        const char c = static_cast<char>(Load8(base, msg + i));
        if (!c) {
          break;
        }
        text += c;
      }
    }
    REXLOG_WARN("[nhl13] heap error: \"{}\" (lr {:08X})", text, static_cast<uint32_t>(ctx.lr));
    LogStackOnce("825F7C90 (ошибка кучи)");
  }
  __imp__sub_825F7C90(ctx, base);
}
