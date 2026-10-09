// НХЛ на 32 команды во франшизе NHL Legacy — перенос порта NHL 13 (port/src/nhl13_teams.cpp,
// docs/teams.md). Карта адресов NHL 13 → Legacy — legacy-port/analysis/team32 (локально), итог —
// docs/legacy-port.md.
//
// База (tools/nhl32.py --game legacy, агент legacy-data): новые клубы Сиэтл и Вегас — строки 30/31
// exhibitionteams (на заготовках Custom), сборные Матча звёзд — строки Custom 222/223, дивизионы 8/8/8/8
// (Pacific + SEA/VGK, Аризона/Юта — в Central), календари nhlschedule и nhlfutureschedule на 32 × 84.
//
// 1. Состав и дивизионы НХЛ задаёт код, не база: 82A1E910 (в NHL 13 — 82809330) добавляет в список
//    команд 0…29 (82AEB120 — добавить в список на 60) и строит дерево «лига → 2 конференции →
//    4 дивизиона» с зашитыми номерами: массив команд на стеке r1+80 (8 мест), узел — 82AEBEF0 (узел,
//    число, массив). Врезки NhlLegacyNhlDivision перед четырьмя вызовами 82AEBEF0 подставляют
//    дивизионы на 32 (Pacific и Central — по 8), подмена дописывает в список 30 и 31. Меню выбора
//    команды (829CCA18) остаётся на 30, как в NHL 13: его массивы на 30/60.
// 2. Календарь: генератора в Legacy нет — первый сезон nhlschedule, со второго nhlfutureschedule из базы
//    (перестановка команд внутри дивизионов 82AFA838, предсезонка ≤ 4 дивизионов по ≤ 8). Буферы лиги —
//    на 1350 игр по 28 байт (как в NHL 13): врезки поднимают вместимость до 1600.
// 3. Номера франшизы при 32: НХЛ 0…31, АХЛ 32…61 (номер = teamid), проспекты 62/63, юниоры CHL 64+,
//    сборные — в самом конце (создаются после юниоров, номера проспектов и юниоров как в оригинале).
//    Объект лиги: +520 фарм-клубы[30], +640 «загружены», +644 teamid[30] — элементы 30/31 снаружи
//    (LeagueExtra), как в NHL 13. Функции 8289AB80, 8289B040, 8289AF40 компилятор Legacy частично
//    встроил: подмена 82B0A178 и врезки чтения +520.
// 4. Кэш сводок команд (0x83BDC414): записи по 332 байта на 30 команд, флаги +9960, счётчик +9992,
//    всего 9996 — записи 30/31 за ним (+9996).
// 5. АХЛ на 32 (nhl_ahl_teams = 32, только вместе с nhl_teams = 32; база legacy-data --ahl32): фарм-клубы
//    Сиэтла и Вегаса — Coachella Valley / Henderson на Custom 224/225 (220/221 — EASHL), номера франшизы 62/63,
//    проспекты 64/65, CHL 66…125 — всего 126, сборных нет, Матч звёзд выключен. Дерево АХЛ 82A1EE18 (= 82809848):
//    дивизионы 8/8/8/8 врезками NhlLegacyAhlDivision, подмена дописывает 224/225 и их порядковые 30/31; объекты
//    клубов АХЛ league+772[30] (82AFC418) — 30/31 снаружи (docs/ahl32.md, docs/legacy-port.md).

#include <algorithm>
#include <array>
#include <atomic>
#include <bitset>
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
#include "nhllegacy_debug.h"
#endif

REXCVAR_DEFINE_INT32(nhl_teams, 30, "NHLLegacy",
                     "NHL teams in franchise: 30 = original, 32 = teams 30/31 of the DB are NHL clubs")
    .range(30, 32)
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

REXCVAR_DEFINE_INT32(nhl_ahl_teams, 30, "NHLLegacy",
                     "AHL teams in franchise: 30 or 32 (Coachella Valley / Henderson; only with nhl_teams = 32 "
                     "and the --ahl32 database)")
    .range(30, 32)
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

REXCVAR_DEFINE_BOOL(nhl_guest_print_log, false, "NHLLegacy",
                    "Log what the game passes to its empty stub 833FBEA0 (first 200 texts): slow, the stub "
                    "is called from thousands of places every frame - only for crash hunts")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

extern "C" void __imp__sub_82A2F2B8(PPCContext& ctx, uint8_t* base);  // фабрика структуры лиги
extern "C" void __imp__sub_82A1E910(PPCContext& ctx, uint8_t* base);  // дерево НХЛ
extern "C" void __imp__sub_82974F20(PPCContext& ctx, uint8_t* base);  // «команда НХЛ?»
extern "C" void __imp__sub_82AFBC80(PPCContext& ctx, uint8_t* base);  // сборные Матча звёзд
extern "C" void __imp__sub_82B43DA0(PPCContext& ctx, uint8_t* base);  // запись команд группы лиг
extern "C" void __imp__sub_82B28FB0(PPCContext& ctx, uint8_t* base);  // запись команд (список из меню)
extern "C" void __imp__sub_82B3DFC8(PPCContext& ctx, uint8_t* base);  // то же, быстрый путь
extern "C" void __imp__sub_82AFC298(PPCContext& ctx, uint8_t* base);  // фарм-клуб команды НХЛ
extern "C" void __imp__sub_82AFC2C0(PPCContext& ctx, uint8_t* base);  // команды НХЛ с фарм-клубом
extern "C" void __imp__sub_82AFC398(PPCContext& ctx, uint8_t* base);  // фарм-клуб / хозяева
extern "C" void __imp__sub_82B0A178(PPCContext& ctx, uint8_t* base);  // номер НХЛ по teamid (+644)
extern "C" void __imp__sub_82AFBED0(PPCContext& ctx, uint8_t* base);  // фарм-клубы из leagueteams
extern "C" void __imp__sub_82B0C1F0(PPCContext& ctx, uint8_t* base);  // фарм-клубы из базы
extern "C" void __imp__sub_829CCA18(PPCContext& ctx, uint8_t* base);  // меню франшизы: списки
extern "C" void __imp__sub_82B07C08(PPCContext& ctx, uint8_t* base);  // teamid → номер франшизы
extern "C" void __imp__sub_82B63708(PPCContext& ctx, uint8_t* base);  // конструктор кэша сводок
extern "C" void __imp__sub_82B57FC8(PPCContext& ctx, uint8_t* base);  // сброс флагов кэша
extern "C" void __imp__sub_82B6E6B8(PPCContext& ctx, uint8_t* base);  // сортировка таблицы статистики
extern "C" void __imp__sub_82B72040(PPCContext& ctx, uint8_t* base);  // заполнение таблицы статистики
extern "C" void __imp__sub_82A58D08(PPCContext& ctx, uint8_t* base);  // средние 7 показателей
extern "C" void __imp__sub_8271B450(PPCContext& ctx, uint8_t* base);  // ошибка кучи гостя
extern "C" void sub_82AEB120(PPCContext& ctx, uint8_t* base);  // список команд: добавить
extern "C" void __imp__sub_82A1EE18(PPCContext& ctx, uint8_t* base);  // дерево АХЛ
extern "C" void __imp__sub_82AFC418(PPCContext& ctx, uint8_t* base);  // объекты клубов АХЛ league+772[30]
extern "C" void sub_82AEBE50(PPCContext& ctx, uint8_t* base);  // дерево: teamid → порядковый
extern "C" void sub_82E53E80(PPCContext& ctx, uint8_t* base);  // выделение памяти (размер, …)
extern "C" void sub_829748A0(PPCContext& ctx, uint8_t* base);  // конструктор объекта клуба АХЛ (3244 б)
extern "C" void sub_82AFC310(PPCContext& ctx, uint8_t* base);  // фарм-клуб общий у 2+ команд?
extern "C" void sub_82AE9DD8(PPCContext& ctx, uint8_t* base);  // итератор команд: создать
extern "C" void sub_82AE9E28(PPCContext& ctx, uint8_t* base);  // итератор команд: удалить
extern "C" void sub_82AF6570(PPCContext& ctx, uint8_t* base);  // сведения о команде франшизы
extern "C" void sub_82AEF510(PPCContext& ctx, uint8_t* base);  // сведения о команде базы
extern "C" void sub_82B5F320(PPCContext& ctx, uint8_t* base);  // конструктор записи кэша (332 б)

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

uint8_t Load8(uint8_t* base, uint32_t addr) {
  return *Host(base, addr);
}

uint8_t* GuestBase() {
  return rex::Runtime::instance()->memory()->TranslateVirtual<uint8_t*>(0);
}

// Разведка: стек первого вызова — в nhllegacy_teams.log рядом с exe.
void LogStackOnce(const char* tag) {
#if defined(_WIN32)
  CONTEXT c{};
  RtlCaptureContext(&c);
  DWORD64 frames[40];
  const int n = NhlLegacyCaptureStack(c, frames, 40);
  wchar_t exe[MAX_PATH];
  GetModuleFileNameW(nullptr, exe, MAX_PATH);
  std::wstring path(exe);
  path = path.substr(0, path.find_last_of(L"\\/") + 1) + L"nhllegacy_teams.log";
  std::lock_guard<std::mutex> lock(NhlLegacyDbghelpMutex());
  if (FILE* f = _wfopen(path.c_str(), L"a")) {
    NhlLegacyEnsureSymbols();
    fprintf(f, "== %s\n", tag);
    for (int i = 0; i < n; ++i) {
      NhlLegacyWriteFrame(f, i, frames[i]);
    }
    fclose(f);
  }
#else
  (void)tag;
#endif
}

bool ThirtyTwo() {
  static const bool on = [] {
    const bool v = REXCVAR_GET(nhl_teams) == 32;
    REXLOG_INFO("[nhllegacy] franchise NHL teams: {}", v ? 32 : 30);
    return v;
  }();
  return on;
}

// АХЛ на 32 — только вместе с НХЛ на 32.
bool AhlThirtyTwo() {
  static const bool on = [] {
    const bool v = ThirtyTwo() && REXCVAR_GET(nhl_ahl_teams) == 32;
    if (REXCVAR_GET(nhl_ahl_teams) == 32 && !v) {
      REXLOG_WARN("[nhllegacy] nhl_ahl_teams = 32 needs nhl_teams = 32, using 30");
    }
    REXLOG_INFO("[nhllegacy] franchise AHL teams: {}", v ? 32 : 30);
    return v;
  }();
  return on;
}

// Новые клубы АХЛ (строки базы --ahl32): Coachella Valley, Henderson — порядковые 30/31, номера 62/63.
constexpr uint32_t kAhlNewTeams[] = {224, 225};

// Номер франшизы клуба АХЛ по teamid при ahl32: 32…61 — тот же, 224 → 62, 225 → 63; остальное как есть.
int32_t AhlNumberOfTeamid(int32_t teamid) {
  for (int k = 0; k < 2; ++k) {
    if (teamid == static_cast<int32_t>(kAhlNewTeams[k])) {
      return 62 + k;
    }
  }
  return teamid;
}

int32_t NhlTeams() {
  return ThirtyTwo() ? 32 : 30;
}

int32_t AhlTeams() {
  return AhlThirtyTwo() ? 32 : 30;
}

// Знаковый байт сведений (+190 ahlaffiliate, extsb): байт без знака, кроме −1 («нет»).
int32_t UnsignedTeamByte(int32_t v) {
  return v == -1 ? -1 : (v & 0xFF);
}

// Дивизионы НХЛ на 32 (номера строк базы; 30 — Сиэтл, 31 — Вегас, 22 — Аризона/Юта). id узлов —
// как у игры: 3 Pacific, 4 Central (конференция 1, Запад), 5 Atlantic, 6 Metropolitan (2, Восток).
struct Division {
  uint32_t id;
  uint32_t count;
  uint32_t teams[8];
};
constexpr Division kDivisions[] = {
    {3, 8, {0, 4, 11, 13, 25, 28, 30, 31}},  // ANA CGY EDM LA SJ VAN SEA VGK
    {4, 8, {6, 7, 9, 14, 16, 24, 1, 22}},    // CHI COL DAL MIN NSH STL WPG ARI/UTA
    {5, 8, {2, 3, 10, 12, 15, 20, 26, 27}},  // BOS BUF DET FLA MTL OTT TB TOR (как в игре)
    {6, 8, {5, 8, 17, 18, 19, 21, 23, 29}},  // CAR CBJ NJ NYI NYR PHI PIT WSH (как в игре)
};

// Дивизионы АХЛ на 32 (teamid; как AHL_DIVISIONS у tools/nhl32.py --game legacy --ahl32). id узлов — как у
// игры: 12 Central, 13 Pacific (конференция 8, Запад), 10 Atlantic, 11 North (9, Восток). Texas — в Central,
// Lake Erie — в North, как в нынешней АХЛ.
constexpr Division kAhlDivisions[] = {
    {12, 8, {36, 37, 38, 41, 44, 45, 50, 58}},    // CHA CHW GRA IOW MAN MIL RFD TEX
    {13, 8, {33, 46, 52, 53, 54, 56, 224, 225}},  // BAK ONT SAN SD SJ STO + CV HSK
    {10, 8, {35, 39, 40, 43, 47, 48, 55, 61}},    // BRI HAR HER LVP POR PRO SPR WBS
    {11, 8, {32, 34, 42, 49, 51, 57, 59, 60}},    // ALB BNG LEM RCH STJ SYR TOA UTI
};

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

// Байт из сведений о команде (франшизы — 82AF6570 по номеру, базы — 82AEF510 по teamid): +8 — teamid,
// +190 — фарм-клуб. Итератор и структура (200 б) — во временной области гостевого стека ниже кадра.
int8_t GuestTeamInfoByte(PPCContext& ctx, uint8_t* base, bool franchise, uint32_t team, uint32_t offset) {
  const uint64_t saved_r1 = ctx.r1.u64;
  const uint32_t iter = (ctx.r1.u32 - 0x200) & ~0xFu;
  const uint32_t info = iter + 0x20;  // до 0x120 байт
  std::memset(Host(base, iter), 0, 0x140);
  ctx.r1.u64 = iter - 0x80;
  ctx.r3.u64 = iter;
  sub_82AE9DD8(ctx, base);
  ctx.r3.u64 = iter;
  ctx.r4.u64 = team;
  ctx.r5.u64 = info;
  if (franchise) {
    sub_82AF6570(ctx, base);
  } else {
    sub_82AEF510(ctx, base);
  }
  const int8_t v = static_cast<int8_t>(Load8(base, info + offset));
  ctx.r3.u64 = iter;
  sub_82AE9E28(ctx, base);
  ctx.r1.u64 = saved_r1;
  return v;
}

// Список АХЛ при создании франшизы — из меню (на 30): ровно teamid 32…61 по порядку.
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

// Перед записью команд лиги: в список НХЛ из меню (30) — 30 и 31, их teamid — в LeagueExtra.
void AppendExtraTeams(PPCContext& ctx, uint8_t* base, uint32_t league) {
  const uint32_t list = league + 16;
  if (!ThirtyTwo() || !IsMenuNhlList(base, list)) {
    return;
  }
  const SavedArgs args(ctx);
  for (uint32_t k = 0; k < kExtra; ++k) {
    ctx.r3.u64 = list;
    ctx.r4.u64 = 30 + k;
    sub_82AEB120(ctx, base);
  }
  EditExtra(league, [](LeagueExtra& e) {
    for (int k = 0; k < kExtra; ++k) {
      e.teamid[k] = 30 + k;
    }
  });
  args.Restore(ctx);
  static int logged = 0;
  if (logged++ < 4) {
    REXLOG_INFO("[nhllegacy] league {:08X}: NHL list 30 -> {} teams", league, Load32(base, list));
  }
}

void CompareInto(PPCCRRegister& cr, int32_t v, int32_t n) {
  cr.lt = v < n;
  cr.gt = v > n;
  cr.eq = v == n;
}

}  // namespace

// --- Условия мест из списка (nhllegacy_team_sites.cpp, tools/team_hooks.py) ---

void NhlLegacyAigmFranchiseLoaded();  // nhllegacy_aigm.cpp

bool NhlLegacyThirtyTwo() {
  return ThirtyTwo();
}

bool NhlLegacyAhl32() {
  return AhlThirtyTwo();
}

// Отметки x/y/z/e таблицы (82B6ECA8, в NHL 13 — 8292A8B8): правки «15 → 16» только у таблицы лиги на
// 16 + 16 — НХЛ (АХЛ — при ahl32). Объект таблицы в Legacy на 4 байта длиннее в начале: +100 — группа
// лиг (в NHL 13 +96), +104 — лига в группе (+100).
bool NhlLegacyStandingsWide(PPCRegister& table) {
  if (!ThirtyTwo()) {
    return false;
  }
  uint8_t* base = GuestBase();
  if (Load32(base, table.u32 + 100) != 0) {
    return false;
  }
  const uint32_t league = Load32(base, table.u32 + 104);
  return league == 0 || (league == 1 && AhlThirtyTwo());
}

// --- Календарь ---

// li rX, 1350 — число игр в буфере календаря (заполнение нулями и предел для вызовов).
void NhlLegacyScheduleCapacity(PPCRegister& r) {
  r.u64 = kScheduleCapacity;
}

// ori r3, r3, 0x93A8 — размер буфера календаря в байтах перед выделением.
void NhlLegacyScheduleBytes(PPCRegister& r) {
  r.u64 = kScheduleCapacity * kScheduleEntryBytes;
}

// --- Структура лиг ---

// Фабрика структуры лиги 82A2F2B8 (82819268). Меню франшизы 829CCA18 (через переходник 82BA9EC8 — lr
// указывает в 829CCA18) получает НХЛ на 30 команд: его массивы рассчитаны на 30/60. Лига франшизы
// (82B1EFD8 — пересборка при создании) строится на 32.
namespace {
thread_local bool t_menu_structure = false;
}  // namespace

extern "C" void sub_82A2F2B8(PPCContext& ctx, uint8_t* base) {
  const uint32_t lr = static_cast<uint32_t>(ctx.lr);
  const bool prev = t_menu_structure;
  t_menu_structure = lr >= 0x829CCA18 && lr < 0x829CCDE8;
  __imp__sub_82A2F2B8(ctx, base);
  t_menu_structure = prev;
}

// Дерево НХЛ: r3 — ?, r4 — корень дерева (может быть 0), r5 — список команд (может быть 0). Дивизионы
// строит сам оригинал (врезки NhlLegacyNhlDivision), здесь — команды 30/31 в список.
extern "C" void sub_82A1E910(PPCContext& ctx, uint8_t* base) {
  const uint32_t list = ctx.r5.u32;
  __imp__sub_82A1E910(ctx, base);
  if (!ThirtyTwo() || t_menu_structure) {
    return;
  }
  static int logged = 0;
  if (logged++ < 3) {
    REXLOG_INFO("[nhllegacy] NHL structure: 32 teams, divisions 8/8/8/8");
  }
  NhlLegacyAigmFranchiseLoaded();  // nhllegacy_aigm.cpp: записи AI-GM 30/31 — заново по образцу
  if (list) {
    const uint64_t saved_r3 = ctx.r3.u64;
    for (uint32_t team : {30u, 31u}) {
      ctx.r3.u64 = list;
      ctx.r4.u64 = team;
      sub_82AEB120(ctx, base);
    }
    ctx.r3.u64 = saved_r3;
  }
}

// bl 0x82AEBEF0 (узел, число, массив) в 82A1E910: дивизион по id узла (r3 — узел, id уже записан в +0;
// r4 — число команд; r5 — массив на стеке r1+80, места на 8 номеров).
void NhlLegacyNhlDivision(PPCRegister& r3, PPCRegister& r4, PPCRegister& r5) {
  if (!ThirtyTwo() || t_menu_structure) {
    return;
  }
  uint8_t* base = GuestBase();
  const uint32_t id = Load32(base, r3.u32);
  for (const Division& d : kDivisions) {
    if (d.id != id) {
      continue;
    }
    for (uint32_t i = 0; i < d.count; ++i) {
      Store32(base, r5.u32 + 4 * i, d.teams[i]);
    }
    r4.u64 = d.count;
    return;
  }
  REXLOG_WARN("[nhllegacy] NHL division {} unknown", id);
}

// АХЛ на 32 — в тех же вызовах фабрики, что и НХЛ на 32 (всё, кроме меню франшизы на 30 + 30).
bool AhlStructure() {
  return AhlThirtyTwo() && !t_menu_structure;
}

// Дерево АХЛ 82A1EE18 (= 82809848): r4 — корень (может быть 0), r5 — список команд (может быть 0). Оригинал
// дописывает в список teamid 32…61 и переводит их в дереве в порядковые (82AEBE50(корень, t, t − 32));
// подмена — то же для 224/225 (→ 30/31). Дальше пересборка франшизы сдвигает порядковые на первый номер
// лиги: 0…31 → 32…63. Дивизионы — врезки NhlLegacyAhlDivision перед четырьмя вызовами 82AEBEF0.
extern "C" void sub_82A1EE18(PPCContext& ctx, uint8_t* base) {
  const uint32_t root = ctx.r4.u32;
  const uint32_t list = ctx.r5.u32;
  __imp__sub_82A1EE18(ctx, base);
  if (!AhlStructure()) {
    return;
  }
  static int logged = 0;
  if (logged++ < 3) {
    REXLOG_INFO("[nhllegacy] AHL structure: 32 teams (+224/225 -> ordinals 30/31), divisions 8/8/8/8");
  }
  const SavedArgs args(ctx);
  if (list) {
    for (uint32_t team : kAhlNewTeams) {
      ctx.r3.u64 = list;
      ctx.r4.u64 = team;
      sub_82AEB120(ctx, base);
    }
  }
  if (root) {
    for (uint32_t k = 0; k < 2; ++k) {
      ctx.r3.u64 = root;
      ctx.r4.u64 = kAhlNewTeams[k];
      ctx.r5.u64 = 30 + k;
      sub_82AEBE50(ctx, base);
    }
  }
  args.Restore(ctx);
}

// bl 0x82AEBEF0 (узел, число, массив) в 82A1EE18: дивизион АХЛ по id узла (массив на стеке на 8 номеров).
void NhlLegacyAhlDivision(PPCRegister& r3, PPCRegister& r4, PPCRegister& r5) {
  if (!AhlStructure()) {
    return;
  }
  uint8_t* base = GuestBase();
  const uint32_t id = Load32(base, r3.u32);
  for (const Division& d : kAhlDivisions) {
    if (d.id != id) {
      continue;
    }
    for (uint32_t i = 0; i < d.count; ++i) {
      Store32(base, r5.u32 + 4 * i, d.teams[i]);
    }
    r4.u64 = d.count;
    return;
  }
  REXLOG_WARN("[nhllegacy] AHL division {} unknown", id);
}

// --- Сборные Матча звёзд ---
// 82AFBC80 (8289A868) добавляет во франшизу teamid 30/31 (зашито: li r11,30 / li r10,31) сразу после АХЛ
// и пишет их номера в состояния 55/56. При 32 командах сборные — строки 222/223 базы (Custom), и
// создаются они в конце, после юниоров, чтобы номера проспектов (62/63) и юниоров (64+) остались как в
// оригинале: вызов для лиги НХЛ откладывается и выполняется после 82B43DA0 последней группы лиг.
namespace {
constexpr uint32_t kAllStarTeamA = 222;
constexpr uint32_t kAllStarTeamB = 223;

struct DeferredAllStars {
  bool pending = false;
  uint32_t league = 0, settings = 0;
  int call = 0;
};
DeferredAllStars g_allstars;
int g_league_group_calls = 0;
thread_local bool t_allstars_now = false;
}  // namespace

extern "C" void sub_82AFBC80(PPCContext& ctx, uint8_t* base) {
  if (AhlThirtyTwo()) {
    // АХЛ на 32: команд франшизы ровно 126 (0…125) — столько держит код (номер 126 — заглушка, массивы по
    // номеру на 126). Сборных нет, Матч звёзд выключен (NhlLegacyAllStarGame), в базе --ahl32 его тоже нет.
    static int logged = 0;
    if (logged++ < 1) {
      REXLOG_INFO("[nhllegacy] All-Star teams: not created (126 franchise teams with AHL 32)");
    }
    return;
  }
  if (ThirtyTwo() && !t_allstars_now) {
    if (Load32(base, ctx.r4.u32 + 604) == 2) {  // лига, у которой есть сборные (НХЛ)
      g_allstars = {true, ctx.r3.u32, ctx.r4.u32, g_league_group_calls};
    }
    return;
  }
  __imp__sub_82AFBC80(ctx, base);
}

// lwz r5, 604(r29) @82B0BF10 — состояние лиги 54 («есть сборные», 2 у НХЛ): при ahl32 сборных нет — 0, как у
// лиг без Матча звёзд (события выбора сборных и перерыва не ставятся).
void NhlLegacyAllStarGame(PPCRegister& r5) {
  if (AhlThirtyTwo() && r5.u32 != 0) {
    static int logged = 0;
    if (logged++ < 1) {
      REXLOG_INFO("[nhllegacy] All-Star game: off (league state 54: {} -> 0)", r5.u32);
    }
    r5.u64 = 0;
  }
}

void NhlLegacyAllStarTeamA(PPCRegister& r) {
  if (ThirtyTwo()) {
    r.u64 = kAllStarTeamA;
  }
}

void NhlLegacyAllStarTeamB(PPCRegister& r) {
  if (ThirtyTwo()) {
    r.u64 = kAllStarTeamB;
  }
}

// 82B43DA0 (828E7AC0) зовут в цикле по группам лиг (82B4A540: 82B4A7B0 и 82B4AC54): r7 — номер группы,
// r18 вызывающего (на входе ещё не тронут; в NHL 13 — r19) — число групп. Сборные — после последней.
extern "C" void sub_82B43DA0(PPCContext& ctx, uint8_t* base) {
  const int call = ++g_league_group_calls;
  const bool last_group = ctx.r7.s32 == ctx.r18.s32 - 1;
  __imp__sub_82B43DA0(ctx, base);
  if (!ThirtyTwo() || !g_allstars.pending || call <= g_allstars.call || !last_group) {
    return;
  }
  g_allstars.pending = false;
  const SavedArgs args(ctx);
  ctx.r3.u64 = g_allstars.league;
  ctx.r4.u64 = g_allstars.settings;
  t_allstars_now = true;
  __imp__sub_82AFBC80(ctx, base);
  t_allstars_now = false;
  args.Restore(ctx);
  REXLOG_INFO("[nhllegacy] All-Star teams ({}/{}) created after junior leagues", kAllStarTeamA,
              kAllStarTeamB);
}

// --- Номера франшизы при 32 командах ---

// «Команда НХЛ?» по номеру франшизы: 0 ≤ номер < 30 → < 32.
extern "C" void sub_82974F20(PPCContext& ctx, uint8_t* base) {
  if (!ThirtyTwo()) {
    __imp__sub_82974F20(ctx, base);
    return;
  }
  const int32_t idx = ctx.r3.s32;
  ctx.r3.u64 = (idx >= 0 && idx < NhlTeams()) ? 1 : 0;
}

// Перед записью команд лиги: в список АХЛ из меню (32…61) — 224, 225 (номера выдаются по порядку записи:
// 224 → 62, 225 → 63).
void AppendAhlTeams(PPCContext& ctx, uint8_t* base, uint32_t league) {
  const uint32_t list = league + 16;
  if (!AhlThirtyTwo() || !IsMenuAhlList(base, list)) {
    return;
  }
  const SavedArgs args(ctx);
  for (uint32_t team : kAhlNewTeams) {
    ctx.r3.u64 = list;
    ctx.r4.u64 = team;
    sub_82AEB120(ctx, base);
  }
  args.Restore(ctx);
  static int logged = 0;
  if (logged++ < 4) {
    REXLOG_INFO("[nhllegacy] league {:08X}: AHL list 30 -> {} teams (+224/225)", league, Load32(base, list));
  }
}

// Список команд НХЛ перед записью команд франшизы — с 30 и 31 (АХЛ при ahl32 — с 224/225).
extern "C" void sub_82B28FB0(PPCContext& ctx, uint8_t* base) {
  AppendExtraTeams(ctx, base, ctx.r3.u32);
  AppendAhlTeams(ctx, base, ctx.r3.u32);
  __imp__sub_82B28FB0(ctx, base);
}

extern "C" void sub_82B3DFC8(PPCContext& ctx, uint8_t* base) {
  AppendExtraTeams(ctx, base, ctx.r3.u32);
  AppendAhlTeams(ctx, base, ctx.r3.u32);
  __imp__sub_82B3DFC8(ctx, base);
}

// Фарм-клуб команды НХЛ (номер франшизы + 1; −1 — не загружены).
extern "C" void sub_82AFC298(PPCContext& ctx, uint8_t* base) {
  const uint32_t league = ctx.r3.u32;
  const int32_t idx = ctx.r4.s32;
  if (IsExtraIndex(idx)) {
    ctx.r3.s64 = AffiliatesLoaded(base, league) ? GetExtra(league).affiliate[idx - 30] : -1;
    return;
  }
  __imp__sub_82AFC298(ctx, base);
}

// Команды НХЛ с данным фарм-клубом: номера в out[], r3 — сколько.
extern "C" void sub_82AFC2C0(PPCContext& ctx, uint8_t* base) {
  const uint32_t league = ctx.r3.u32;
  const int32_t affiliate = ctx.r4.s32;
  const uint32_t out = ctx.r5.u32;
  __imp__sub_82AFC2C0(ctx, base);
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

// Команда НХЛ — её фарм-клуб в *out (r3 = 1); иначе — команды НХЛ с фарм-клубом idx. Новая в Legacy
// проверка «номер < 60» (82AFC3C0) поднимается до 62 местом из списка.
extern "C" void sub_82AFC398(PPCContext& ctx, uint8_t* base) {
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
  __imp__sub_82AFC398(ctx, base);
}

// Номер команды НХЛ по teamid (+644[30]; встроенная 8289AB80): r3 — менеджер, r4 — группа, r5 — лига + 1,
// r6 — teamid; −1 — нет. Лига — [[[r3 + 40] + 4·r4] + 4·(r5 − 1)].
extern "C" void sub_82B0A178(PPCContext& ctx, uint8_t* base) {
  const uint32_t mgr = ctx.r3.u32;
  const uint32_t group = ctx.r4.u32;
  const uint32_t league1 = ctx.r5.u32;
  const uint32_t teamid = ctx.r6.u32;
  __imp__sub_82B0A178(ctx, base);
  if (!ThirtyTwo() || ctx.r3.s32 != -1 || !mgr || !league1) {
    return;
  }
  uint32_t p = Load32(base, mgr + 40);
  if (!p) {
    return;
  }
  p = Load32(base, p + 4 * group);
  if (!p) {
    return;
  }
  const uint32_t league = Load32(base, p + 4 * (league1 - 1));
  const LeagueExtra e = GetExtra(league);
  for (int k = 0; k < kExtra; ++k) {
    if (e.teamid[k] == teamid) {
      ctx.r3.u64 = 30 + k;
      return;
    }
  }
}

// Фарм-клубы по командам франшизы (leagueteams.ahlaffiliate) — и для 30/31.
extern "C" void sub_82AFBED0(PPCContext& ctx, uint8_t* base) {
  const uint32_t league = ctx.r3.u32;
  __imp__sub_82AFBED0(ctx, base);
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

// Фарм-клубы по базе: exhibitionteams.ahlaffiliate = teamid + 1, во франшизе — номер + 1; оригинал
// вычитает 2 (АХЛ с 30), при 32 командах номер АХЛ = teamid — «+ 2» ко всем 30 (особое значение 50 у
// Legacy → 52 — тот же teamid). Для 30/31 — из сведений базы (+190).
extern "C" void sub_82B0C1F0(PPCContext& ctx, uint8_t* base) {
  const uint32_t league = ctx.r3.u32;
  __imp__sub_82B0C1F0(ctx, base);
  if (!ThirtyTwo()) {
    return;
  }
  const uint64_t r3 = ctx.r3.u64;
  for (uint32_t i = 0; i < 30; ++i) {
    const uint32_t a = league + 520 + 4 * i;
    int32_t v = static_cast<int32_t>(Load32(base, a)) + 2;
    if (AhlThirtyTwo()) {
      v = AhlNumberOfTeamid(UnsignedTeamByte(v));  // 224/225 (в знаковом байте −32/−31) → 62/63
    }
    Store32(base, a, static_cast<uint32_t>(v));
  }
  int32_t aff[kExtra];
  for (int k = 0; k < kExtra; ++k) {
    aff[k] = UnsignedTeamByte(GuestTeamInfoByte(ctx, base, false, 30 + k, 190));
    if (AhlThirtyTwo()) {
      aff[k] = AhlNumberOfTeamid(aff[k]);
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
    REXLOG_INFO("[nhllegacy] league {:08X}: affiliates +2, teams 30/31 -> {} {}", league, aff[0], aff[1]);
  }
}

// Меню франшизы: список АХЛ — номера франшизы i + 30 (и копия рядом) → i + 32. Объект меню в Legacy
// на 144 байта длиннее: списки +6040 и +3136 (шаг 484), АХЛ — вторые.
extern "C" void sub_829CCA18(PPCContext& ctx, uint8_t* base) {
  const uint32_t self = ctx.r3.u32;
  const int32_t league = ctx.r5.s32;
  __imp__sub_829CCA18(ctx, base);
  if (!ThirtyTwo() || league != 1) {
    return;
  }
  for (const uint32_t list : {self + 6040 + 484, self + 3136 + 484}) {
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

// teamid → номер франшизы. Ветка онлайн-франшизы перебирает 0…59, «нет» — 60 (последний клуб АХЛ при
// 32 — 61).
extern "C" void sub_82B07C08(PPCContext& ctx, uint8_t* base) {
  const uint32_t teamid = ctx.r4.u32;
  __imp__sub_82B07C08(ctx, base);
  if (!ThirtyTwo() || ctx.r3.s32 != 60) {
    return;
  }
  if (!AhlThirtyTwo()) {
    if (teamid == 61) {
      ctx.r3.u64 = 61;
    }
    return;
  }
  // ahl32: перебор всех номеров (по сведениям франшизы, +8 — teamid), «нет» — 64 (как 60 у оригинала).
  for (uint32_t n = 60; n < 126; ++n) {
    const uint32_t t = static_cast<uint8_t>(GuestTeamInfoByte(ctx, base, true, n, 8));
    if (t == (teamid & 0xFFu)) {
      ctx.r3.u64 = n;
      return;
    }
  }
  ctx.r3.u64 = 64;
}

// Врезки чтения фарм-клуба команды НХЛ из массива +520 (82B291A0, 82B3E2E8 и встроенные 82B0A2B0,
// 82B0B80C): для 30/31 — из LeagueExtra.
void NhlLegacyAffiliateAt(PPCRegister& value, PPCRegister& index, PPCRegister& league) {
  if (IsExtraIndex(index.s32)) {
    value.s64 = GetExtra(league.u32).affiliate[index.s32 - 30];
  }
}

// 82B3E480 addi r24, r11, -30: номер АХЛ фарм-клуба команды r15 — для лишних игроков; при 32 командах
// АХЛ начинается с 32.
void NhlLegacyAffiliateAhl(PPCRegister& ahl, PPCRegister& value, PPCRegister& index, PPCRegister& league) {
  if (!ThirtyTwo()) {
    return;
  }
  const int32_t idx = index.s32;
  const int32_t v = IsExtraIndex(idx) ? GetExtra(league.u32).affiliate[idx - 30] : value.s32;
  ahl.s64 = v - 32;
}

// --- Кэш сводок команд НХЛ (0x83BDC414): записи 30/31 — за счётчиком (+9996) ---
namespace {
constexpr uint32_t kTeamCacheRecord = 332;
constexpr uint32_t kTeamCacheExtra = 9996;  // исходный размер объекта
constexpr uint32_t kTeamCacheFlags = 9960;

uint32_t TeamCacheOffset(int32_t idx) {
  return kTeamCacheExtra + static_cast<uint32_t>(idx - 30) * kTeamCacheRecord;
}

void ClearExtraCacheFlags(uint8_t* base, uint32_t cache) {
  for (int k = 0; k < kExtra; ++k) {
    *Host(base, cache + kTeamCacheFlags + 30 + k) = 0;
  }
}
}  // namespace

// li r3, 9996 @82B637A0 — размер объекта.
void NhlLegacyTeamCacheBytes(PPCRegister& r) {
  if (ThirtyTwo()) {
    r.u64 = kTeamCacheExtra + kExtra * kTeamCacheRecord;
  }
}

// mulli r11, r30, 332 — смещение записи команды.
void NhlLegacyTeamCacheOffset(PPCRegister& offset, PPCRegister& index) {
  if (IsExtraIndex(index.s32)) {
    offset.u64 = TeamCacheOffset(index.s32);
  }
}

// Конструктор: записи 30/31 — тем же конструктором записи (обнуление и три строки по 100 б), флаги.
extern "C" void sub_82B63708(PPCContext& ctx, uint8_t* base) {
  const uint32_t cache = ctx.r3.u32;
  __imp__sub_82B63708(ctx, base);
  if (!ThirtyTwo() || !cache) {
    return;
  }
  const uint64_t r3 = ctx.r3.u64;
  for (int k = 0; k < kExtra; ++k) {
    ctx.r3.u64 = cache + TeamCacheOffset(30 + k);
    sub_82B5F320(ctx, base);
  }
  ClearExtraCacheFlags(base, cache);
  ctx.r3.u64 = r3;
}

// Сброс флагов «посчитано» (30) — и для 30/31.
extern "C" void sub_82B57FC8(PPCContext& ctx, uint8_t* base) {
  const uint32_t cache = ctx.r3.u32;
  __imp__sub_82B57FC8(ctx, base);
  if (ThirtyTwo()) {
    ClearExtraCacheFlags(base, cache);
  }
}

// --- «АХЛ с 30» при 32 командах НХЛ ---

void NhlLegacyAhlShift(PPCRegister& r) {  // номер − 30 → − 32
  if (ThirtyTwo()) {
    r.s64 -= 2;
  }
}

void NhlLegacyAhlUnshift(PPCRegister& r) {  // порядковый + 30 → + 32
  if (ThirtyTwo()) {
    r.s64 += 2;
  }
}

void NhlLegacyAhlBase(PPCRegister& r) {  // li 30 → 32
  if (ThirtyTwo()) {
    r.u64 = 32;
  }
}

// 82B3E7E0 addi r3, r11, −2 (82B3DFC8, игроки клуба АХЛ): права на игрока без клуба НХЛ — номер текущей
// команды АХЛ: у оригинала teamid − 2; при 32 номер = teamid. r15 — номер текущей команды.
void NhlLegacyAhlOwnTeam(PPCRegister& r3, PPCRegister& r15) {
  if (ThirtyTwo()) {
    r3.u64 = r15.u32;
  }
}

// --- Объекты клубов АХЛ league+772[30] при ahl32 ---
// У объекта лиги АХЛ +772 — 30 указателей на объекты клубов (3244 б; выделяет 82AFC418 при создании команд,
// освобождает цикл по клубам АХЛ в 82B3EDC0), сразу за ними +892 — указатель пула игроков. Объекты 30/31
// (номера 62/63) — снаружи, ключ — объект лиги АХЛ; живут только во время создания франшизы.
namespace {
std::mutex g_ahl_objects_mutex;
std::unordered_map<uint32_t, std::array<uint32_t, 2>> g_ahl_objects;

uint32_t AhlObject(uint32_t league, int k) {
  std::lock_guard<std::mutex> lock(g_ahl_objects_mutex);
  auto it = g_ahl_objects.find(league);
  return it == g_ahl_objects.end() ? 0 : it->second[k];
}
}  // namespace

extern "C" void sub_82AFC418(PPCContext& ctx, uint8_t* base) {
  const uint32_t league = ctx.r3.u32;
  __imp__sub_82AFC418(ctx, base);
  if (!AhlThirtyTwo()) {
    return;
  }
  const SavedArgs args(ctx);
  std::array<uint32_t, 2> objs{};
  for (int k = 0; k < 2; ++k) {
    // как у оригинала: 82E53E80(3244, 9, «имя» 0x82080298, 0, 16, 0) и конструктор 829748A0
    ctx.r3.u64 = 3244;
    ctx.r4.u64 = 9;
    ctx.r5.u64 = 0x82080298u;
    ctx.r6.u64 = 0;
    ctx.r7.u64 = 16;
    ctx.r8.u64 = 0;
    sub_82E53E80(ctx, base);
    if (ctx.r3.u32) {
      sub_829748A0(ctx, base);
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
    REXLOG_INFO("[nhllegacy] AHL league {:08X}: team objects 30/31 outside +772: {:08X} {:08X}", league,
                objs[0], objs[1]);
  }
}

// lwzx rD, r11, rL — league+772[r11/4 − 193] (82B3EA3C, 82B3BCBC, 82B3EF50, 82B3F360): для 30/31 — снаружи.
void NhlLegacyAhlTeamObject(PPCRegister& obj, PPCRegister& offset, PPCRegister& league) {
  if (!AhlThirtyTwo()) {
    return;
  }
  const int32_t i = static_cast<int32_t>(offset.u32 / 4) - 193;
  if (i >= 30 && i < 32) {
    obj.u64 = AhlObject(league.u32, i - 30);
  }
}

// lwz r3, 4(r29) @82B3F580 в цикле освобождения (r30 = i).
void NhlLegacyAhlTeamObjectAt(PPCRegister& obj, PPCRegister& index, PPCRegister& league) {
  if (AhlThirtyTwo() && index.s32 >= 30 && index.s32 < 32) {
    obj.u64 = AhlObject(league.u32, index.s32 - 30);
  }
}

// stwu r27, 4(r29) @82B3F588 — обнуление освобождённого: для 30/31 указатель снаружи (запись ушла бы в
// +892/+896 — пул и буфер, нужные до конца цикла). true — пропустить запись.
bool NhlLegacyAhlTeamObjectFreed(PPCRegister& index, PPCRegister& league) {
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

// Вне франшизы (exhibitionteams) фарм-клуб Сиэтла/Вегаса — teamid 224/225 в знаковом байте (−32/−31):
// extsb (829CA780, 82A24A64, 82B8CA90) → байт без знака, −1 («нет») остаётся.
void NhlLegacyAffiliateByte(PPCRegister& r) {
  if (AhlThirtyTwo()) {
    r.s64 = UnsignedTeamByte(r.s32);
  }
}

// cmpwi cr6, r26, 61 @829CA754 (вне франшизы: «клуб АХЛ» = teamid 32…61) — и 224/225.
void NhlLegacyAhlTeamidRange(PPCRegister& r, PPCCRRegister& cr) {
  if (AhlThirtyTwo() && (r.u32 == kAhlNewTeams[0] || r.u32 == kAhlNewTeams[1])) {
    cr.lt = true;
    cr.gt = false;
    cr.eq = false;
  }
}

// cmpwi crN, rX, 30 по командам НХЛ → сравнение с числом команд.
void NhlLegacyNhlBound(PPCRegister& r, PPCCRRegister& cr) {
  if (ThirtyTwo()) {
    CompareInto(cr, r.s32, NhlTeams());
  }
}

// cmpwi crN, rX, 60 по профи-командам (НХЛ + АХЛ) → НХЛ + АХЛ.
void NhlLegacyProBound(PPCRegister& r, PPCCRRegister& cr) {
  if (ThirtyTwo()) {
    CompareInto(cr, r.s32, NhlTeams() + AhlTeams());
  }
}

// Число команд НХЛ из списка меню (30) → число команд НХЛ франшизы.
void NhlLegacyNhlCount(PPCRegister& r) {
  if (ThirtyTwo() && r.s32 == 30) {
    r.u64 = static_cast<uint64_t>(NhlTeams());
  }
}

// li rX, 29 — последняя команда НХЛ.
void NhlLegacyNhlLast(PPCRegister& r) {
  if (ThirtyTwo()) {
    r.u64 = static_cast<uint64_t>(NhlTeams() - 1);
  }
}

// StatsCache (829886B0): блоки рейтингов команд по статистике на 30 записей — пока предел 30.
void NhlLegacyStatsCacheCount(PPCRegister& r) {
  if (ThirtyTwo() && r.s32 > 30) {
    static int logged = 0;
    if (logged++ < 2) {
      REXLOG_INFO("[nhllegacy] StatsCache: {} team rows -> 30", r.s32);
    }
    r.u64 = 30;
  }
}

// 82B2D740 (места прошлого сезона): кадр на 16 байт больше (пара к эпилогу @82B2DCC8 из списка мест).
void NhlLegacyStackGrow16(PPCRegister& r1) {
  if (ThirtyTwo()) {
    r1.u64 -= 16;
  }
}

// --- Таблица статистики и сортировка ---

// 82B6BA58: при тройной ничьей все записи (по 24 байта) копируются в буфер на стеке r1+384, а с r1+1024
// поверх строятся временные объекты разбора — целы записи 0…25. Ошибка самой игры (та же, что в
// NHL 13); при 32 командах в общей таблице записи ≥ 26 приезжали бы мусором. Буфер — свой.
void NhlLegacyTieBuffer(PPCRegister& r) {
  thread_local uint32_t buffer = 0;
  if (!buffer) {
    buffer = rex::Runtime::instance()->memory()->SystemHeapAlloc(128 * 24);
  }
  r.u64 = buffer;
}

// 82B5C2F0: список номеров записей узла выделен на число его команд (r26), но пишется без проверки —
// при дублях в таблице за конец блока. true — список полон, запись пропустить (→ 82B5C43C).
bool NhlLegacyTeamListFull(PPCRegister& r31, PPCRegister& r26) {
  uint8_t* base = GuestBase();
  return static_cast<int32_t>(Load32(base, r31.u32 + 88)) >= r26.s32;
}

// 82B6C040: команды дерева нет среди записей (r9 = −1) — игра копировала бы 24 байта из-за края буфера.
// true — копирование пропустить (→ 82B6C05C).
bool NhlLegacyTreeTeamMissing(PPCRegister& r9) {
  return r9.s32 < 0;
}

namespace {
// Команд под узлом дерева лиги (как 82AEBCA8): +4 — свои, +16 — число детей, +20 — массив детей.
int32_t TreeTeamCount(uint8_t* base, uint32_t node, int depth = 0) {
  if (!node || depth > 4) {
    return 0;
  }
  int32_t n = static_cast<int32_t>(Load32(base, node + 4));
  const int32_t kids = static_cast<int32_t>(Load32(base, node + 16));
  const uint32_t arr = Load32(base, node + 20);
  for (int32_t i = 0; arr && i < kids && i < 16; ++i) {
    n += TreeTeamCount(base, Load32(base, arr + 4 * i), depth + 1);
  }
  return n;
}
}  // namespace

// 82B6C838 (ветка 131 сортировки 82B6BA58 — посев плей-офф АХЛ): при ahl32 дивизион на 8 в конференции без
// дивизиона на 7 — без перехода: 4 лучших в плей-офф, 5–8 в хвост таблицы. true — переход на 82B6C84C.
bool NhlLegacyAhlNoCrossover(PPCRegister& r27, PPCRegister& r17) {
  if (!AhlThirtyTwo() || r27.s32 != 8) {
    return false;
  }
  uint8_t* base = GuestBase();
  const uint32_t conf = r17.u32;
  const int32_t kids = static_cast<int32_t>(Load32(base, conf + 16));
  const uint32_t arr = Load32(base, conf + 20);
  for (int32_t i = 0; arr && i < kids && i < 16; ++i) {
    if (TreeTeamCount(base, Load32(base, arr + 4 * i)) == 7) {
      return false;  // есть дивизион на 7 — переход, как в оригинале
    }
  }
  static int logged = 0;
  if (logged++ < 4) {
    REXLOG_INFO("[nhllegacy] AHL playoffs: conference {} has no 7-team division - top 4 of each division, "
                "no crossover", Load32(base, conf));
  }
  return true;
}

namespace {
// Таблица статистики (объект Legacy): записи по 24 байта с +36, число — +48, объекты команд — массив с
// +40 по 200 байт (номер — байт +8). Цела, если каждая запись указывает на свой объект без повторов.
bool StatsTableOk(uint8_t* base, uint32_t self, std::string* teams = nullptr) {
  const uint32_t recs = Load32(base, self + 36);
  const uint32_t n = Load32(base, self + 48);
  const uint32_t objs = Load32(base, self + 40);
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
}  // namespace

// Сортировка таблицы статистики (диспетчер по типу +84): страховка, как в NHL 13 — если после вызова
// таблица испорчена (дубли/мусор), в лог и обратно прежний порядок.
extern "C" void sub_82B6E6B8(PPCContext& ctx, uint8_t* base) {
  const uint32_t self = ctx.r3.u32;
  const uint32_t stat = ctx.r4.u32;
  const uint32_t mode = ctx.r5.u32;
  const uint32_t recs = Load32(base, self + 36);
  const uint32_t n = Load32(base, self + 48);
  std::string before;
  const bool ok_before = recs && n && n <= 128 && StatsTableOk(base, self, &before);
  std::string saved;
  if (ok_before) {
    saved.assign(reinterpret_cast<const char*>(Host(base, recs)), n * 24);
  }
  __imp__sub_82B6E6B8(ctx, base);
  if (!ok_before) {
    return;
  }
  std::string after;
  if (StatsTableOk(base, self, &after)) {
    return;
  }
  static int logged = 0;
  if (logged++ < 10) {
    REXLOG_ERROR("[nhllegacy] stats sort broke the table: type {} stat {} mode {} n {}; before: {}; after: {}",
                 Load32(base, self + 84), stat, mode, n, before, after);
    if (logged == 1) {
      LogStackOnce("82B6E6B8 (сортировка испортила таблицу статистики)");
    }
  }
  std::memcpy(Host(base, recs), saved.data(), saved.size());
}

// Таблица статистики команд (82B72040 заполняет записи по командам дерева лиги): проверка повторов.
extern "C" void sub_82B72040(PPCContext& ctx, uint8_t* base) {
  const uint32_t self = ctx.r3.u32;
  __imp__sub_82B72040(ctx, base);
  const uint32_t recs = Load32(base, self + 36);
  const uint32_t n = Load32(base, self + 48);
  if (!recs || n > 128) {
    return;
  }
  // Номера франшизы — до 125 (юниоры CHL 64…123, сборные 124/125): битовая карта на 128.
  std::bitset<128> seen;
  std::string teams;
  bool bad = false;
  for (uint32_t k = 0; k < n; ++k) {
    const uint32_t obj = Load32(base, recs + 24 * k + 16);
    const uint32_t t = obj ? Load8(base, obj + 8) : 255;
    teams += std::to_string(t) + " ";
    if (t >= 128 || seen[t]) {
      bad = true;
    } else {
      seen[t] = true;
    }
  }
  static int logged = 0;
  if (bad && logged++ < 5) {
    REXLOG_ERROR("[nhllegacy] team stats table broken ({} records): {}", n, teams);
    LogStackOnce("82B72040 (таблица статистики с повторами)");
  }
}

// 82A58D08 (загрузка франшизы): средние и разброс 7 показателей по командам — таблица 7 × 30 на стеке.
// При 32 командах последняя строка ушла бы на сохранённые регистры: считаем по первым 30.
extern "C" void sub_82A58D08(PPCContext& ctx, uint8_t* base) {
  if (ThirtyTwo() && ctx.r5.s32 > 30) {
    static int logged = 0;
    if (logged++ < 2) {
      REXLOG_INFO("[nhllegacy] 82A58D08: {} teams -> 30", ctx.r5.s32);
    }
    ctx.r5.u64 = 30;
  }
  __imp__sub_82A58D08(ctx, base);
}

// --- Флаги «пересобрать сводку состава» объекта 82A56298 (+15817[30]) ---
// Сразу за флагами (+15848) — подобъект: 32 флага не помещаются, флаги 30/31 — снаружи, по объекту.
namespace {
std::mutex g_roster_flags_mutex;
std::unordered_map<uint32_t, std::array<uint8_t, 2>> g_roster_flags;
}  // namespace

// lbz r3, 15817(r11) @82A5905C, r11 = объект + i (r4 = i).
void NhlLegacyRosterFlagGet(PPCRegister& r3, PPCRegister& r4, PPCRegister& r11) {
  const int32_t i = r4.s32;
  if (!ThirtyTwo() || i < 30 || i >= 32) {
    return;
  }
  std::lock_guard<std::mutex> lock(g_roster_flags_mutex);
  auto it = g_roster_flags.find(r11.u32 - r4.u32);
  r3.u64 = it == g_roster_flags.end() ? 0 : it->second[i - 30];
}

// stb r10, 15817(r11) @82A59084 (r10 = 1): для 30/31 — снаружи, true — пропустить запись (→ blr).
bool NhlLegacyRosterFlagSet(PPCRegister& r4, PPCRegister& r11) {
  const int32_t i = r4.s32;
  if (!ThirtyTwo() || i < 30 || i >= 32) {
    return false;
  }
  std::lock_guard<std::mutex> lock(g_roster_flags_mutex);
  g_roster_flags[r11.u32 - r4.u32][i - 30] = 1;
  return true;
}

// Сброс всех флагов объекта (82A59090, конструктор 82A5E9BC) — и 30/31.
void NhlLegacyRosterFlagClear(PPCRegister& obj) {
  if (!ThirtyTwo()) {
    return;
  }
  std::lock_guard<std::mutex> lock(g_roster_flags_mutex);
  g_roster_flags[obj.u32] = {0, 0};
}

// --- Драфт ---

namespace {
// Своя копия статической таблицы порядка драфта (30 номеров) + команды 30/31 в конце.
uint32_t ExtendedDraftTable(uint32_t source) {
  auto* memory = rex::Runtime::instance()->memory();
  const uint32_t addr = memory->SystemHeapAlloc(4 * 32);
  auto* dst = memory->TranslateVirtual<uint8_t*>(addr);
  const auto* src = memory->TranslateVirtual<const uint8_t*>(source);
  std::memcpy(dst, src, 4 * 30);
  for (uint32_t k = 0; k < 2; ++k) {
    const uint32_t v = __builtin_bswap32(30 + k);
    std::memcpy(dst + 4 * (30 + k), &v, 4);
  }
  REXLOG_INFO("[nhllegacy] draft order table {:08X} 30 -> 32 at {:08X}", source, addr);
  return addr;
}
}  // namespace

// Порядок драфта первого сезона (82B741E8): две статические таблицы по 30 — 0x83A15178 (→ this+316) и
// 0x83A151F0 (→ this+320); число команд — this+336 (место 82B74248 из списка → 32).
void NhlLegacyDraftOrderTable(PPCRegister& r9) {
  if (!ThirtyTwo()) {
    return;
  }
  static const uint32_t table = ExtendedDraftTable(0x83A15178u);
  r9.u64 = table;
}

void NhlLegacyDraftOrderTableB(PPCRegister& r9) {
  if (!ThirtyTwo()) {
    return;
  }
  static const uint32_t table = ExtendedDraftTable(0x83A151F0u);
  r9.u64 = table;
}

// Лотерея драфта при 32 командах (82B7456C, вместо розыгрыша Legacy: один розыгрыш, победитель на 1-е
// место): 16 команд вне плей-офф на стеке r1+384 от худшей к лучшей. Правила НХЛ с 2022 года: два
// розыгрыша (1-й и 2-й пики), шансы по месту, победитель поднимается не больше чем на 10 мест, второй
// раз одна команда не выигрывает. Дальше игра (82B74680) пишет r9 в r1+384 — номер с 1-го места.
bool NhlLegacyDraftLottery(PPCRegister& r1, PPCRegister& r9) {
  if (!ThirtyTwo()) {
    return false;
  }
  static const uint32_t kOdds[16] = {185, 135, 115, 95, 85, 75, 65, 60, 50, 35, 30, 25, 20, 15, 5, 5};
  static std::mt19937 rng{std::random_device{}()};
  auto* order = rex::Runtime::instance()->memory()->TranslateVirtual<uint8_t*>(r1.u32 + 384);
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
  const uint32_t first = __builtin_bswap32(teams[cur[0]]);
  REXLOG_INFO("[nhllegacy] draft lottery: winners {} and {} (places before lottery, 0 = worst); team {} picks 1st",
              winners[0], winners[1], first);
  r9.u64 = first;
  return true;
}

// --- Отладка ---

// 833FBEA0 — вырезанный из релиза OutputDebugString (просто blr): через него игра печатает текст своих
// ассертов. По умолчанию — снова пустая (её зовут тысячи раз за кадр).
extern "C" void sub_833FBEA0(PPCContext& ctx, uint8_t* base) {
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
  REXLOG_WARN("[nhllegacy] guest debug print (lr {:08X}): {}", static_cast<uint32_t>(ctx.lr), text);
}

// 8271B450 — ошибка менеджера памяти гостя: печатает [r3+12] и twi (рантайм пишет «trap hit» и
// продолжает). Сообщение и стек — в лог / nhllegacy_teams.log.
extern "C" void sub_8271B450(PPCContext& ctx, uint8_t* base) {
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
    REXLOG_WARN("[nhllegacy] heap error: \"{}\" (lr {:08X})", text, static_cast<uint32_t>(ctx.lr));
    LogStackOnce("8271B450 (ошибка кучи)");
  }
  __imp__sub_8271B450(ctx, base);
}
