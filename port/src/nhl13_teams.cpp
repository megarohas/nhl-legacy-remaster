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
//    828FE540). С nhl_teams = 32 дивизионы 6 + 5 + 5 в конференции строит сам оригинал:
//    врезки перед его вызовами 828FE278 подставляют команды (Nhl13NhlDivision), подмена
//    дописывает в список команды 30 и 31.
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
// 5. АХЛ на 32 (nhl_ahl_teams = 32, только вместе с nhl_teams = 32; база tools/nhl32.py --ahl32,
//    разбор — docs/ahl32.md): строки 220/221 (фарм-клубы Сиэтла и Вегаса) — клубы АХЛ с номерами
//    62/63, проспекты 64/65, CHL 66…125 — всего 126 команд, больше код не держит: сборных и Матча
//    звёзд нет. Структура и списки АХЛ при создании, объекты клубов АХЛ league+772[30] (30/31 —
//    снаружи), фарм-клубы 220/221 → 62/63 — подмены и врезки ниже (Ahl…, AhlThirtyTwo()).

#include <algorithm>
#include <atomic>
#include <array>
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

REXCVAR_DEFINE_BOOL(nhl_guest_print_log, false, "NHL13",
                    "Log what the game passes to its empty stub 832055C8 (first 200 texts): slow, the stub "
                    "is called from ~3400 places every frame - only for crash hunts")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

REXCVAR_DEFINE_INT32(nhl_ahl_teams, 30, "NHL13",
                     "AHL teams in franchise: 30 = original, 32 = DB rows 220/221 are AHL clubs "
                     "(tools/nhl32.py --ahl32); only with nhl_teams = 32")
    .range(30, 32)
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

extern "C" void __imp__sub_82809330(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_82809848(PPCContext& ctx, uint8_t* base);
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
extern "C" void __imp__sub_8289B0E8(PPCContext& ctx, uint8_t* base);
extern "C" void sub_828FD590(PPCContext& ctx, uint8_t* base);  // список команд: добавить
extern "C" void sub_828FE1D8(PPCContext& ctx, uint8_t* base);  // дерево лиги: заменить номер команды
extern "C" void sub_82A92BE8(PPCContext& ctx, uint8_t* base);  // выделение памяти (размер, …)
extern "C" void sub_827DCC68(PPCContext& ctx, uint8_t* base);  // конструктор объекта клуба АХЛ (3244 б)
extern "C" void sub_828FD5D8(PPCContext& ctx, uint8_t* base);  // список команд: записать i-й
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

// АХЛ на 32 (база tools/nhl32.py --ahl32): клубы АХЛ — строки 32…61 и 220/221 (фарм-клубы
// Сиэтла и Вегаса на заготовках Custom Team 02/03). Только вместе с nhl_teams = 32.
bool AhlThirtyTwo() {
  static const bool on = [] {
    const bool v = ThirtyTwo() && REXCVAR_GET(nhl_ahl_teams) == 32;
    REXLOG_INFO("[nhl13] franchise AHL teams: {}", v ? 32 : 30);
    return v;
  }();
  return on;
}
constexpr uint32_t kAhlNewTeams[] = {220, 221};

int32_t AhlTeams() {
  return AhlThirtyTwo() ? 32 : 30;
}

// Номер франшизы клуба АХЛ по teamid при ahl32: 32…61 — тот же (номер = teamid), 220 → 62,
// 221 → 63. Остальное (−1 — нет, НХЛ, прочие лиги) — как есть.
int32_t AhlNumberOfTeamid(int32_t teamid) {
  for (int k = 0; k < 2; ++k) {
    if (teamid == static_cast<int32_t>(kAhlNewTeams[k])) {
      return 62 + k;
    }
  }
  return teamid;
}

// Знаковый байт сведений (+190 ahlaffiliate, extsb): teamid 220/221 в нём — −36/−35. Байт
// без знака, кроме −1 («нет»).
int32_t UnsignedTeamByte(int32_t v) {
  return v == -1 ? -1 : (v & 0xFF);
}

// Дивизионы для 32 команд (номера строк базы; 30 — Сиэтл, 31 — Вегас,
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

// Дивизионы АХЛ на 32 (как AHL_DIVISIONS в tools/nhl32.py): id узлов — как у игры (82809848),
// конференции 10 — Запад (14, 15, 17), 11 — Восток (12, 13, 16). Charlotte (37) — на Восток,
// фарм-клубы Сиэтла и Вегаса (220/221) — в West. Массив команд на стеке (r1+80) вмещает 8.
constexpr Division kAhlDivisions[] = {
    {14, 5, {38, 40, 46, 49, 53}},           // Midwest: CHW GRA MIL PEO RFD
    {15, 5, {32, 41, 44, 52, 59}},           // North: ABB HAM LEM RCH TOA
    {17, 6, {43, 48, 55, 58, 220, 221}},     // West: HOU OKC SAN TEX CV HSK
    {12, 5, {45, 50, 51, 54, 61}},           // Atlantic: MCH POR PRO STJ WOR
    {13, 6, {35, 37, 42, 47, 57, 60}},       // East: BNG CHA HER NRF SYR WBS
    {16, 5, {33, 34, 36, 39, 56}},           // Northeast: ADK ALB BRI CT SPR
};

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

// Список АХЛ при создании франшизы — из меню (структура меню на 30): ровно teamid 32…61.
bool IsMenuAhlList(uint8_t* base, uint32_t list) {
  if (Load32(base, list) != 30) {
    return false;
  }
  for (uint32_t i = 0; i < 30; ++i) {
    if (Load32(base, list + 4 + 4 * i) != 32 + i) {
      return false;
    }
  }
  return true;
}

// Перед записью команд лиги (828C0250, 828CD4E8): в список АХЛ (группа 0, лига 1) — 220, 221.
// Номера выдаются по порядку записи: 220 → 62, 221 → 63.
void AppendAhlTeams(PPCContext& ctx, uint8_t* base, uint32_t league) {
  const uint32_t list = league + 16;
  if (!AhlThirtyTwo() || Load32(base, league + 4) != 0 || Load32(base, league + 8) != 1 ||
      !IsMenuAhlList(base, list)) {
    return;
  }
  const SavedArgs args(ctx);
  for (uint32_t team : kAhlNewTeams) {
    ctx.r3.u64 = list;
    ctx.r4.u64 = team;
    sub_828FD590(ctx, base);
  }
  args.Restore(ctx);
  static int logged = 0;
  if (logged++ < 4) {
    REXLOG_INFO("[nhl13] league {:08X}: AHL list 30 -> {} teams (+220/221)", league, Load32(base, list));
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
// Вызов фабрики из 828CAA90 — пересборка структуры лиг франшизы при создании (828F8808 →
// 828F72C8 → 828D41F8). АХЛ на 32 строится только там: у меню массивы на 30/60, у режима
// «Плей-офф» (828B68F0) и 82911A48 — свои структуры.
thread_local bool t_franchise_structure = false;

extern "C" void sub_82819268(PPCContext& ctx, uint8_t* base) {
  const uint32_t lr = static_cast<uint32_t>(ctx.lr);
  const bool prev = t_menu_structure;
  const bool prev_franchise = t_franchise_structure;
  t_menu_structure = lr >= 0x827C2BA8 && lr < 0x827C2F70;
  t_franchise_structure = lr >= 0x828CAA90 && lr < 0x828CB058;
  __imp__sub_82819268(ctx, base);
  t_menu_structure = prev;
  t_franchise_structure = prev_franchise;
}

bool AhlStructure() {
  return AhlThirtyTwo() && t_franchise_structure;
}

// Структура НХЛ: r3 — ?, r4 — корень дерева (может быть 0), r5 — список команд (может быть 0).
// Дивизионы на 32 команды строит сам оригинал: врезки Nhl13NhlDivision перед шестью вызовами
// 828FE278 подставляют число и номера команд. Раньше дерево правилось после оригинала
// (828FE278 на готовых узлах), и таблица статистики команд (8292F258) порой собиралась с
// дырами и дублями — падения при загрузке матча (07.10.2026).
extern "C" void sub_82809330(PPCContext& ctx, uint8_t* base) {
  const uint32_t list = ctx.r5.u32;
  __imp__sub_82809330(ctx, base);
  if (!ThirtyTwo() || t_menu_structure) {
    return;
  }
  static int logged = 0;
  if (logged++ < 3) {
    REXLOG_INFO("[nhl13] NHL structure: 32 teams, divisions 6+5+5");
  }
  if (list) {
    const uint64_t saved_r3 = ctx.r3.u64;
    for (uint32_t team : {30u, 31u}) {
      ctx.r3.u64 = list;
      ctx.r4.u64 = team;
      sub_828FD590(ctx, base);
    }
    ctx.r3.u64 = saved_r3;
  }
}

// Подстановка дивизиона по id узла: r3 — узел (id уже записан), r4 — число команд, r5 — массив
// команд на стеке (r1+80, места на 8 номеров).
template <size_t N>
void PatchDivision(const Division (&table)[N], const char* league, PPCRegister& r3, PPCRegister& r4,
                   PPCRegister& r5) {
  auto* memory = rex::Runtime::instance()->memory();
  uint32_t id;
  std::memcpy(&id, memory->TranslateVirtual<const uint8_t*>(r3.u32), 4);
  id = __builtin_bswap32(id);
  for (const Division& d : table) {
    if (d.id != id) {
      continue;
    }
    auto* teams = memory->TranslateVirtual<uint8_t*>(r5.u32);
    for (uint32_t i = 0; i < d.count; ++i) {
      const uint32_t v = __builtin_bswap32(d.teams[i]);
      std::memcpy(teams + 4 * i, &v, 4);
    }
    r4.u64 = d.count;
    return;
  }
  REXLOG_WARN("[nhl13] {} division {} unknown", league, id);
}

// bl 0x828FE278 (узел, число, массив) в 82809330 — дивизионы НХЛ.
void Nhl13NhlDivision(PPCRegister& r3, PPCRegister& r4, PPCRegister& r5) {
  if (!ThirtyTwo() || t_menu_structure) {
    return;
  }
  PatchDivision(kDivisions, "NHL", r3, r4, r5);
}

// Структура АХЛ (82809848): r4 — корень дерева, r5 — список команд лиги (оба могут быть 0).
// Оригинал добавляет в список 32…61 и переводит их в дереве в порядковые (828FE1D8(корень,
// t, t − 32), 82809AC0…82809ADC); подмена — то же для 220/221 (→ 30/31). Потом 8289A950
// (828CAA90) сдвигает порядковые на первый номер лиги: 0…31 → 32…63. Дивизионы — врезки
// Nhl13AhlDivision перед шестью вызовами 828FE278. Только при создании франшизы.
extern "C" void sub_82809848(PPCContext& ctx, uint8_t* base) {
  const uint32_t root = ctx.r4.u32;
  const uint32_t list = ctx.r5.u32;
  __imp__sub_82809848(ctx, base);
  if (!AhlStructure()) {
    return;
  }
  static int logged = 0;
  if (logged++ < 3) {
    REXLOG_INFO("[nhl13] AHL structure: 32 teams (+220/221 -> ordinals 30/31), divisions 6+5+5");
  }
  const SavedArgs args(ctx);
  if (list) {
    for (uint32_t team : kAhlNewTeams) {
      ctx.r3.u64 = list;
      ctx.r4.u64 = team;
      sub_828FD590(ctx, base);
    }
  }
  if (root) {
    for (uint32_t k = 0; k < 2; ++k) {
      ctx.r3.u64 = root;
      ctx.r4.u64 = kAhlNewTeams[k];
      ctx.r5.u64 = 30 + k;
      sub_828FE1D8(ctx, base);
    }
  }
  args.Restore(ctx);
}

// bl 0x828FE278 в 82809848 — дивизионы АХЛ.
void Nhl13AhlDivision(PPCRegister& r3, PPCRegister& r4, PPCRegister& r5) {
  if (!AhlStructure()) {
    return;
  }
  PatchDivision(kAhlDivisions, "AHL", r3, r4, r5);
}

// 82925900 — сортировка таблицы статистики (тип 1, ключ — очки 828FDAF8). При тройной ничьей
// все записи (по 24 байта) копируются в буфер на стеке r1+400 (82925A2C), а после разбора личных
// встреч три записи берутся обратно по абсолютному номеру (82925C2C). Но с r1+496 поверх буфера
// строятся временные объекты разбора — целы только записи 0…3, дальше в таблицу приезжают мусор
// и копии других команд. Ошибка самой игры; с базой 2026/27 тройные ничьи частые: 829212E8 по
// дублям набирает команд больше, чем выделил (порча кучи, сторож 07.10.2026), мусорные записи —
// чтение по мусору и вызов по нулю при загрузке матча. Буфер — свой, на 128 записей, на поток.
void Nhl13TieBuffer(PPCRegister& r) {
  thread_local uint32_t buffer = 0;
  if (!buffer) {
    buffer = rex::Runtime::instance()->memory()->SystemHeapAlloc(128 * 24);
  }
  r.u64 = buffer;
}

// Число команд в узле дерева лиги вместе с детьми (как 828FE030): +4 — свои команды,
// +16 — число детей, +20 — массив указателей на детей.
uint32_t NodeTeams(uint8_t* base, uint32_t node, int depth = 0) {
  if (!node || depth > 6) {
    return 0;
  }
  uint32_t n = Load32(base, node + 4);
  const uint32_t kids = Load32(base, node + 16);
  const uint32_t arr = Load32(base, node + 20);
  for (uint32_t k = 0; k < kids && k < 32; ++k) {
    n += NodeTeams(base, Load32(base, arr + 4 * k), depth + 1);
  }
  return n;
}

// 82925900, виды 121/125/126 (таблица конференции: лидеры дивизионов, потом остальные):
// начало j-го дивизиона в конференции игра считает как «размер дивизиона j × j»
// (829264B0 mullw r11, r3, r25) — верно только при равных дивизионах. У нас 5+5+6 и 6+5+5:
// дивизионы налезали друг на друга и на соседнюю конференцию → дубли и пропавшие команды в
// таблице статистики (Чикаго — Монреаль, сетка плей-офф, драфт). Начало — сумма размеров
// предыдущих дивизионов (r24 — конференция, r25 — номер дивизиона). Найдено аудитом слепков.
void Nhl13DivisionStart(PPCRegister& r11, PPCRegister& r24, PPCRegister& r25) {
  auto* base = rex::Runtime::instance()->memory()->TranslateVirtual<uint8_t*>(0);
  const uint32_t arr = Load32(base, r24.u32 + 20);
  uint32_t start = 0;
  for (uint32_t k = 0; k < r25.u32 && k < 32; ++k) {
    start += NodeTeams(base, Load32(base, arr + 4 * k));
  }
  r11.u64 = start;
}

// 829212E8: список номеров записей для узла выделен на число его команд (r26), но пишется
// без проверки (82921410…82921428) — при дублях в таблице за конец блока (порча кучи
// «голова = 0x0F», вызов по нулю). true — список полон, запись пропустить (→ 8292142C).
bool Nhl13TeamListFull(PPCRegister& r31, PPCRegister& r26) {
  auto* base = rex::Runtime::instance()->memory()->TranslateVirtual<uint8_t*>(0);
  return static_cast<int32_t>(Load32(base, r31.u32 + 84)) >= r26.s32;
}

// 82925E7C: команды дерева нет среди записей (r9 = −1) — игра копировала бы 24 байта из-за
// края буфера на стеке (мусорная запись). true — копирование пропустить (→ 82925E98).
bool Nhl13TreeTeamMissing(PPCRegister& r9) {
  return r9.s32 < 0;
}

// Таблица статистики (объект 8205A920): записи по 24 байта с +32, число — +44; запись: +0 —
// номер объекта команды, +16 — объект команды (массив с +36, по 200 байт), +20 — сведения
// (массив с +40, по 296). Цела, если каждая запись указывает на свой объект и объекты не
// повторяются.
bool StatsTableOk(uint8_t* base, uint32_t self, std::string* teams = nullptr) {
  const uint32_t recs = Load32(base, self + 32);
  const uint32_t n = Load32(base, self + 44);
  const uint32_t objs = Load32(base, self + 36);
  if (!recs || !objs || n > 128) {
    return true;
  }
  uint64_t seen[2] = {};
  bool ok = true;
  for (uint32_t k = 0; k < n; ++k) {
    const uint32_t obj = Load32(base, recs + 24 * k + 16);
    const uint32_t i = (obj - objs) / 200;
    const bool valid = obj >= objs && i < n && (obj - objs) % 200 == 0;
    if (teams) {
      *teams += valid ? std::to_string(Load8(base, obj + 8)) + " " : "? ";
    }
    if (!valid || (seen[i >> 6] >> (i & 63) & 1)) {
      ok = false;
      continue;
    }
    seen[i >> 6] |= 1ull << (i & 63);
  }
  return ok;
}

// Сортировка таблицы статистики (диспетчер по типу +80: 82913330, 82925900, 829258B0,
// 8291C838; r4 — вид статистики). С 32 командами при загрузке матча (Чикаго — Монреаль)
// таблица выходила с дублями и мусором → чтение по мусору в 8291C220. Страховка: таблица до
// вызова запоминается; если после вызова она испорчена — в лог (тип, вид статистики, команды
// до/после) и обратно прежний порядок.
extern "C" void __imp__sub_8292A868(PPCContext& ctx, uint8_t* base);
extern "C" void sub_8292A868(PPCContext& ctx, uint8_t* base) {
  const uint32_t self = ctx.r3.u32;
  const uint32_t stat = ctx.r4.u32;
  const uint32_t mode = ctx.r5.u32;
  const uint32_t recs = Load32(base, self + 32);
  const uint32_t n = Load32(base, self + 44);
  std::string before;
  const bool ok_before = recs && n && n <= 128 && StatsTableOk(base, self, &before);
  std::string saved;
  if (ok_before) {
    saved.assign(reinterpret_cast<const char*>(Host(base, recs)), n * 24);
  }
  __imp__sub_8292A868(ctx, base);
  if (!ok_before) {
    return;
  }
  std::string after;
  if (StatsTableOk(base, self, &after)) {
    return;
  }
  static int logged = 0;
  if (logged++ < 10) {
    REXLOG_ERROR("[nhl13] stats sort broke the table: type {} stat {} mode {} n {}; before: {}; after: {}",
                 Load32(base, self + 80), stat, mode, n, before, after);
    if (logged == 1) {
      LogStackOnce("8292A868 (сортировка испортила таблицу статистики)");
    }
  }
  std::memcpy(Host(base, recs), saved.data(), saved.size());
}

// Таблица статистики команд (8292F258 заполняет записи по командам дерева лиги): проверка,
// что команды в ней не повторяются — повтор значит испорченное дерево (см. выше).
extern "C" void __imp__sub_8292F258(PPCContext& ctx, uint8_t* base);
extern "C" void sub_8292F258(PPCContext& ctx, uint8_t* base) {
  const uint32_t self = ctx.r3.u32;
  __imp__sub_8292F258(ctx, base);
  const uint32_t recs = Load32(base, self + 32);
  const uint32_t n = Load32(base, self + 44);
  if (!recs || n > 64) {
    return;
  }
  uint64_t seen = 0;
  std::string teams;
  bool bad = false;
  for (uint32_t k = 0; k < n; ++k) {
    const uint32_t obj = Load32(base, recs + 24 * k + 16);
    const uint32_t t = obj ? Load8(base, obj + 8) : 255;
    teams += std::to_string(t) + " ";
    if (t >= 64 || (seen >> t & 1)) {
      bad = true;
    } else {
      seen |= 1ull << t;
    }
  }
  static int logged = 0;
  if (bad && logged++ < 5) {
    REXLOG_ERROR("[nhl13] team stats table broken ({} records): {}", n, teams);
    LogStackOnce("8292F258 (таблица статистики с повторами)");
  }
}

// Сборные Матча звёзд: 8289A868 добавляет во франшизу teamid 30/31 (зашито) сразу после АХЛ
// и пишет их номера в состояния 53/54. При 32 командах сборные — строки 218/219 базы (места
// заготовок Custom Team 00/01, tools/nhl32.py; до 08.10.2026 — 86/87, где стояли Tappara и
// TPS), и создаются они в конце, после юниоров (номера 124/125), чтобы номера
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
  if (AhlThirtyTwo()) {
    // АХЛ на 32: команд франшизы ровно 126 (0…125) — столько держит код (номер 126 — заглушка,
    // массивы по номеру на 126, поле team статистики −1…126). Сборных нет, состояния 53/54
    // пустые (827DFE00 → −16, как в онлайн-франшизе), Матча звёзд нет (Nhl13AllStarGame).
    static int logged = 0;
    if (logged++ < 1) {
      REXLOG_INFO("[nhl13] All-Star teams: not created (126 franchise teams with AHL 32)");
    }
    return;
  }
  if (ThirtyTwo() && !t_allstars_now) {
    if (Load32(base, ctx.r4.u32 + 600) == 2) {  // лига, у которой есть сборные (НХЛ)
      g_allstars = {true, ctx.r3.u32, ctx.r4.u32, g_league_group_calls};
    }
    return;
  }
  __imp__sub_8289A868(ctx, base);
}

// Матч звёзд при ahl32 (docs/ahl32.md, «Матч звёзд»). 828A8060 (создание франшизы) пишет в
// состояние лиги 52 поле +600 настроек лиги (2 — у НХЛ: «есть сборные»). По состоянию 52 ≠ 0
// 828B5A50 ставит в календарь франшизы события 5 (выбор сборных, 82906DF0) и 6 (перерыв), а
// 82880318 показывает сборные в списках. 82906DF0 → 82900AD0 ищет Матч звёзд в календаре
// (828E0D88: игры сборной, leaguescheduletable) и переписывает найденную запись (828EA718: UPDATE
// leaguescheduletable … WHERE index = …); без такой игры запись остаётся неинициализированной
// (мусор стека) — так появлялся «матч с датой 0/0» (c7efd3d). Без сборных выбирать некого:
// lwz r5, 600(r29) @828A80A8 → 0, как у лиг без Матча звёзд — событий 5/6 не будет.
void Nhl13AllStarGame(PPCRegister& r5) {
  if (AhlThirtyTwo() && r5.u32 != 0) {
    static int logged = 0;
    if (logged++ < 1) {
      REXLOG_INFO("[nhl13] All-Star game: off (league state 52: {} -> 0)", r5.u32);
    }
    r5.u64 = 0;
  }
}

// li r11, 30 / li r10, 31 в 8289A868 — teamid сборных.
constexpr uint32_t kAllStarTeamA = 218;
constexpr uint32_t kAllStarTeamB = 219;

void Nhl13AllStarTeamA(PPCRegister& r) {
  if (ThirtyTwo()) {
    r.u64 = kAllStarTeamA;
  }
}

void Nhl13AllStarTeamB(PPCRegister& r) {
  if (ThirtyTwo()) {
    r.u64 = kAllStarTeamB;
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
  REXLOG_INFO("[nhl13] All-Star teams ({}/{}) created after junior leagues", kAllStarTeamA, kAllStarTeamB);
}

// --- Номера франшизы при 32 командах (пункт 4 в начале файла) ---

// «Команда НХЛ?» по номеру франшизы: 0 ≤ номер < 30 → < 32.
extern "C" void sub_827DFB40(PPCContext& ctx, uint8_t* base) {
  (void)base;
  const int32_t idx = ctx.r3.s32;
  ctx.r3.u64 = (idx >= 0 && idx < NhlTeams()) ? 1 : 0;
}

// Список команды НХЛ перед записью команд франшизы — с 30 и 31; АХЛ при ahl32 — с 220 и 221.
extern "C" void sub_828C0250(PPCContext& ctx, uint8_t* base) {
  AppendExtraTeams(ctx, base, ctx.r3.u32);
  AppendAhlTeams(ctx, base, ctx.r3.u32);
  __imp__sub_828C0250(ctx, base);
}

extern "C" void sub_828CD4E8(PPCContext& ctx, uint8_t* base) {
  AppendExtraTeams(ctx, base, ctx.r3.u32);
  AppendAhlTeams(ctx, base, ctx.r3.u32);
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

// Фарм-клубы по базе: exhibitionteams.ahlaffiliate = teamid + 1, во франшизе — номер + 1
// (в сведениях +190 — уже без «+ 1»: teamid / номер, −1 — нет); оригинал вычитает 2 (АХЛ с 30),
// при 32 командах номер АХЛ = teamid — разницы нет. Байт +190 знаковый (extsb): при ahl32 у
// Сиэтла/Вегаса там 220/221 → −36/−35; берётся байт без знака и teamid переводится в номер
// (220 → 62, 221 → 63).
extern "C" void sub_828A8338(PPCContext& ctx, uint8_t* base) {
  const uint32_t league = ctx.r3.u32;
  __imp__sub_828A8338(ctx, base);
  if (!ThirtyTwo()) {
    return;
  }
  const uint64_t r3 = ctx.r3.u64;
  for (uint32_t i = 0; i < 30; ++i) {
    const uint32_t a = league + 520 + 4 * i;
    int32_t v = static_cast<int32_t>(Load32(base, a)) + 2;
    if (AhlThirtyTwo()) {
      v = AhlNumberOfTeamid(UnsignedTeamByte(v));
    }
    Store32(base, a, static_cast<uint32_t>(v));
  }
  int32_t aff[kExtra];
  for (int k = 0; k < kExtra; ++k) {
    aff[k] = GuestTeamInfoByte(ctx, base, false, 30 + k, 190);
    if (AhlThirtyTwo()) {
      aff[k] = AhlNumberOfTeamid(UnsignedTeamByte(aff[k]));
    }
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

// teamid → номер франшизы. Обычная ветка — запрос к leagueteams (по любому teamid); ветка
// онлайн-франшизы (vfunc 8 у 8270CF30) перебирает 8290A8B8 по номерам 0…59, «нет» — 60
// (последний клуб АХЛ при 32 — 61). При ahl32 после неудачи перебор продолжается по всем
// номерам до 125, «нет» — 64 (не меньше числа профи-команд, как 60 у оригинала).
extern "C" void sub_828A6080(PPCContext& ctx, uint8_t* base) {
  const uint32_t teamid = ctx.r4.u32;
  __imp__sub_828A6080(ctx, base);
  if (!ThirtyTwo() || ctx.r3.s32 != 60) {
    return;
  }
  if (!AhlThirtyTwo()) {
    if (teamid == 61) {
      ctx.r3.u64 = 61;
    }
    return;
  }
  for (uint32_t n = 60; n < 126; ++n) {
    const uint32_t t = static_cast<uint8_t>(GuestTeamInfoByte(ctx, base, true, n, 8));
    if (t == (teamid & 0xFFu)) {
      ctx.r3.u64 = n;
      return;
    }
  }
  ctx.r3.u64 = 64;
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

// 828CDC30 addi r3, r11, −2 (828CD4E8, игроки клуба АХЛ): права на игрока без клуба НХЛ —
// номер текущей команды АХЛ: у оригинала teamid − 2; при 32 номер = teamid, а у 220/221 —
// 62/63. r16 — номер текущей команды (82905418 @828CD7D8, дальше не меняется).
void Nhl13AhlOwnTeam(PPCRegister& r3, PPCRegister& r16) {
  if (ThirtyTwo()) {
    r3.u64 = r16.u32;
  }
}

// --- Объекты клубов АХЛ league+772[30] при ahl32 ---
// У объекта лиги АХЛ +772 — 30 указателей на объекты клубов (3244 б; выделяет 8289B0E8 при
// создании команд НХЛ, освобождает цикл по клубам АХЛ в 828CEBF0), сразу за ними +892 —
// указатель пула игроков, +896 — буфер. Объекты 30/31 (номера 62/63) — снаружи, ключ — объект
// лиги АХЛ; живут только во время создания франшизы.
namespace {
std::mutex g_ahl_objects_mutex;
std::unordered_map<uint32_t, std::array<uint32_t, 2>> g_ahl_objects;

uint32_t AhlObject(uint32_t league, int k) {
  std::lock_guard<std::mutex> lock(g_ahl_objects_mutex);
  auto it = g_ahl_objects.find(league);
  return it == g_ahl_objects.end() ? 0 : it->second[k];
}
}  // namespace

extern "C" void sub_8289B0E8(PPCContext& ctx, uint8_t* base) {
  const uint32_t league = ctx.r3.u32;
  __imp__sub_8289B0E8(ctx, base);
  if (!AhlThirtyTwo()) {
    return;
  }
  const SavedArgs args(ctx);
  std::array<uint32_t, 2> objs{};
  for (int k = 0; k < 2; ++k) {
    // как у оригинала: 82A92BE8(3244, 12, «имя» 0x82057214, 0, 16, 0) и конструктор 827DCC68
    ctx.r3.u64 = 3244;
    ctx.r4.u64 = 12;
    ctx.r5.u64 = 0x82057214u;
    ctx.r6.u64 = 0;
    ctx.r7.u64 = 16;
    ctx.r8.u64 = 0;
    sub_82A92BE8(ctx, base);
    if (ctx.r3.u32) {
      sub_827DCC68(ctx, base);
    }
    objs[k] = ctx.r3.u32;
  }
  {
    std::lock_guard<std::mutex> lock(g_ahl_objects_mutex);
    g_ahl_objects[league] = objs;
  }
  args.Restore(ctx);
  static int logged = 0;
  if (logged++ < 2) {
    REXLOG_INFO("[nhl13] AHL league {:08X}: team objects 30/31 outside +772: {:08X} {:08X}", league, objs[0],
                objs[1]);
  }
}

// lwzx rD, r11, rL — league+772[r11/4 − 193] (828CDE10, 828CE8F4, 828CED80, 828CF190):
// для порядковых 30/31 — объект снаружи.
void Nhl13AhlTeamObject(PPCRegister& obj, PPCRegister& offset, PPCRegister& league) {
  if (!AhlThirtyTwo()) {
    return;
  }
  const int32_t i = static_cast<int32_t>(offset.u32 / 4) - 193;
  if (i >= 30 && i < 32) {
    obj.u64 = AhlObject(league.u32, i - 30);
  }
}

// 828CF3AC lwz r3, 4(r29) — объект i-го клуба (r30 = i) перед освобождением.
void Nhl13AhlTeamObjectAt(PPCRegister& obj, PPCRegister& index, PPCRegister& league) {
  if (AhlThirtyTwo() && index.s32 >= 30 && index.s32 < 32) {
    obj.u64 = AhlObject(league.u32, index.s32 - 30);
  }
}

// 828CF3B4 stwu r20, 4(r29) — обнуление освобождённого: для 30/31 указатель снаружи (запись
// пошла бы в +892/+896 — пул и буфер, которые нужны до конца 828CEBF0). true — пропустить.
bool Nhl13AhlTeamObjectFreed(PPCRegister& index, PPCRegister& league) {
  if (!AhlThirtyTwo() || index.s32 < 30 || index.s32 >= 32) {
    return false;
  }
  std::lock_guard<std::mutex> lock(g_ahl_objects_mutex);
  auto it = g_ahl_objects.find(league.u32);
  if (it != g_ahl_objects.end()) {
    it->second[index.s32 - 30] = 0;
  }
  return true;
}

// Вне франшизы (exhibitionteams) фарм-клуб Сиэтла/Вегаса — teamid 220/221 в знаковом байте:
// extsb (827C0E30, 8280F02C, 8283DEAC) → байт без знака, −1 («нет») остаётся.
void Nhl13AffiliateByte(PPCRegister& r) {
  if (AhlThirtyTwo()) {
    r.s64 = UnsignedTeamByte(r.s32);
  }
}

// 827C0E04 cmpwi cr6, r26, 61 (827C0D00, вне франшизы: «клуб АХЛ» = teamid 32…61) — и 220/221.
void Nhl13AhlTeamidRange(PPCRegister& r, PPCCRRegister& cr) {
  if (AhlThirtyTwo() && (r.u32 == kAhlNewTeams[0] || r.u32 == kAhlNewTeams[1])) {
    cr.lt = true;
    cr.gt = false;
    cr.eq = false;
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

// cmpwi crN, rX, 60 по профи-командам (НХЛ + АХЛ) → НХЛ + АХЛ.
void Nhl13ProBound(PPCRegister& r, PPCCRRegister& cr) {
  if (ThirtyTwo()) {
    CompareInto(cr, r.s32, NhlTeams() + AhlTeams());
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

bool Nhl13Ahl32() {
  return AhlThirtyTwo();
}

// Условие мест team32 класса STANDINGS (8292A8B8, отметки x/y/z/e: «15 → 16» и т. п.): функция
// общая для таблиц НХЛ и АХЛ (8292F920), а правки верны только для 16 + 16 — у НХЛ при 32, у
// АХЛ — при ahl32. r31 — таблица: +96 — группа лиг, +100 — лига в группе (0 НХЛ, 1 АХЛ).
bool Nhl13StandingsWide(PPCRegister& table) {
  if (!ThirtyTwo()) {
    return false;
  }
  auto* base = rex::Runtime::instance()->memory()->TranslateVirtual<uint8_t*>(0);
  if (Load32(base, table.u32 + 96) != 0) {
    return false;
  }
  const uint32_t league = Load32(base, table.u32 + 100);
  return league == 0 || (league == 1 && AhlThirtyTwo());
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

// 832055C8 — вырезанный из релиза OutputDebugString (просто blr): через него игра печатает,
// в частности, текст своих ассертов перед twi 31, r0, 22 (825F24E0) — в логе рантайма это
// только «trap hit (type 22)». Строка (r3) и адрес вызова — в лог; каждая строка один раз,
// не больше 200 разных (аудит 07.10.2026).
extern "C" void sub_832055C8(PPCContext& ctx, uint8_t* base) {
  // В игре это пустая функция (blr), её зовут из ~3400 мест — в том числе каждый кадр и не со
  // строкой (в r3 — что угодно). Разбор на каждый вызов (VirtualQuery, сборка строки, мьютекс)
  // ронял игру до ~10 кадров (08.10.2026): по умолчанию — снова пустая.
  static const bool enabled = REXCVAR_GET(nhl_guest_print_log);
  static std::atomic<bool> full{false};
  if (!enabled || full.load(std::memory_order_relaxed)) {
    return;
  }
  static std::mutex mutex;
  static std::unordered_map<std::string, int> seen;
  const uint32_t str = ctx.r3.u32;
  if (str < 0x40000000u || str >= 0xE0000000u) {
    return;
  }
  // r3 может оказаться не строкой: читать только из выделенных страниц
  auto readable = [&](uint32_t addr) {
#if defined(_WIN32)
    MEMORY_BASIC_INFORMATION mbi{};
    if (!VirtualQuery(Host(base, addr), &mbi, sizeof(mbi))) {
      return false;
    }
    return mbi.State == MEM_COMMIT && (mbi.Protect & (PAGE_READONLY | PAGE_READWRITE | PAGE_EXECUTE_READ |
                                                     PAGE_EXECUTE_READWRITE | PAGE_WRITECOPY)) &&
           !(mbi.Protect & PAGE_GUARD);
#else
    return true;
#endif
  };
  if (!readable(str) || !readable(str + 299)) {
    return;
  }
  std::string text;
  for (uint32_t i = 0; i < 300; ++i) {
    const char c = static_cast<char>(Load8(base, str + i));
    if (!c) {
      break;
    }
    text += (c >= 32 && c < 127) ? c : '?';
  }
  while (!text.empty() && (text.back() == '?' || text.back() == ' ')) {
    text.pop_back();
  }
  if (text.empty()) {
    return;
  }
  std::lock_guard<std::mutex> lock(mutex);
  if (seen.size() >= 200) {
    full.store(true, std::memory_order_relaxed);
    return;
  }
  if (seen.count(text)) {
    return;
  }
  seen[text] = 1;
  REXLOG_WARN("[nhl13] guest debug print (lr {:08X}): {}", static_cast<uint32_t>(ctx.lr), text);
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
