// Кубок наций во франшизе NHL Legacy — эксперимент (ветка nations-cup, docs/nations-cup.md, cvar nhl_natcup).
//
// Лига сборных: в новой франшизе Be a GM уровень QMJHL (лига 10, 18 клубов) отдаётся сборным (лига 8): создатель лиги
// 829DAEC8 добавляет уровни CHL вызовами 829DA768(настройки, уровень, лига) — подменяем 10 → 8 и оставляем в списках
// команд уровня (+6040 и +3136, шаг 484: [число, teamid…]) kNations — 16 сборных (предел франшизы — 126 команд:
// 64 НХЛ/АХЛ + OHL 20 + WHL 22 + проспекты 2 + 16). Решение пользователя 20.10: «убрать одну лигу CHL».
//
// Шаг 1: своя задача календаря франшизы в августе. Задачи сезона уровня ставит 82B3BDC8(уровень, сезон) —
// после оригинала у верхнего уровня (82975FA0(+4, +8) == 0) пишем задачу типа kTaskType на 1–20 августа года
// конца сезона (сезон: +16 начало, +20 конец — дни от эпохи движка) через 82AF5DB0(—, &начало, &конец, тип,
// +4, +8). Диспетчер задач 82B4BBC0(лига, тип, уровень, под-лига, &дата) у типов 0, 1 и ≥ 36 обработчика не имеет
// (ветка 82B4C3A0, r3 = 0) — тип kTaskType разбираем сами, остальные — оригиналу.

#include <algorithm>
#include <atomic>
#include <functional>
#include <cstdint>
#include <cstring>
#include <map>
#include <string>
#include <vector>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ppc.h>

REXCVAR_DEFINE_BOOL(nhl_natcup, false, "NHLLegacy",
                    "Nations Cup experiment: an August franchise calendar task (logged for now)")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);
REXCVAR_DEFINE_INT32(nhl_natcup_nation, 0, "NHLLegacy",
                     "Nations Cup: the user's national team (teamid 133-153; 0 = the strongest nation)")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

extern "C" void __imp__sub_82B3BDC8(PPCContext& ctx, uint8_t* base);  // сезонные задачи уровня лиги
extern "C" void __imp__sub_82B4BBC0(PPCContext& ctx, uint8_t* base);  // диспетчер задач
extern "C" void sub_82AF5DB0(PPCContext& ctx, uint8_t* base);         // запись задачи в leaguetasks
extern "C" void sub_82975FA0(PPCContext& ctx, uint8_t* base);         // номер уровня лиги
extern "C" void __imp__sub_829DA768(PPCContext& ctx, uint8_t* base);  // создатель лиги: добавить уровень
extern "C" void __imp__sub_82B099E0(PPCContext& ctx, uint8_t* base);  // создание: juniorteam юниоров CHL
extern "C" void sub_8289F5B0(PPCContext& ctx, uint8_t* base);
extern "C" void sub_82974FA0(PPCContext& ctx, uint8_t* base);
extern "C" void sub_82A07D88(PPCContext& ctx, uint8_t* base);         // база
extern "C" void sub_827B5D40(PPCContext& ctx, uint8_t* base);         // поле по хешу
extern "C" void sub_827B10C8(PPCContext& ctx, uint8_t* base);         // ссылка на поле (хеш)
extern "C" void sub_827B1588(PPCContext& ctx, uint8_t* base);         // условие «поле == значение»
extern "C" void sub_827B2418(PPCContext& ctx, uint8_t* base);         // ИЛИ условий
extern "C" void sub_827B7D08(PPCContext& ctx, uint8_t* base);
extern "C" void sub_827B4818(PPCContext& ctx, uint8_t* base);         // запрос к таблице (хеш)
extern "C" void sub_827B4A48(PPCContext& ctx, uint8_t* base);         // фильтр запроса
extern "C" void sub_827B5568(PPCContext& ctx, uint8_t* base);         // курсор
extern "C" void sub_833FBEA0(PPCContext& ctx, uint8_t* base);
extern "C" void sub_827B11E0(PPCContext& ctx, uint8_t* base);
extern "C" void sub_827B2E10(PPCContext& ctx, uint8_t* base);         // число строк курсора
extern "C" void sub_827B3008(PPCContext& ctx, uint8_t* base);         // чтение поля строки
extern "C" void sub_827B3030(PPCContext& ctx, uint8_t* base);         // запись поля строки
extern "C" void sub_827B2D08(PPCContext& ctx, uint8_t* base);         // следующая строка
extern "C" void sub_827B2C40(PPCContext& ctx, uint8_t* base);         // курсор: удалить
extern "C" void sub_82975B50(PPCContext& ctx, uint8_t* base);         // сдвиг teamid лиги → номер франшизы
extern "C" void sub_82AF8BF0(PPCContext& ctx, uint8_t* base);         // менеджер лиги
extern "C" void sub_82AF9838(PPCContext& ctx, uint8_t* base);         // уровень лиги (−1 — нет)
extern "C" void sub_82A1BB18(PPCContext& ctx, uint8_t* base);         // удалить состав команды
extern "C" void __imp__RtlEnterCriticalSection(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__RtlLeaveCriticalSection(PPCContext& ctx, uint8_t* base);
extern "C" void sub_82BA65C8(PPCContext& ctx, uint8_t* base);         // временный объект записи (16 б): создать
extern "C" void sub_82BCC4A0(PPCContext& ctx, uint8_t* base);         // … удалить
extern "C" void sub_829748A0(PPCContext& ctx, uint8_t* base);         // структура состава R (3244 б): создать
extern "C" void sub_82657880(PPCContext& ctx, uint8_t* base);         // memset(адрес, байт, длина)
extern "C" void sub_82A29D48(PPCContext& ctx, uint8_t* base);         // записать состав (tmp, команда, &R)
extern "C" void sub_82BEC748(PPCContext& ctx, uint8_t* base);         // вставить игру в leaguescheduletable
extern "C" void sub_82B1B048(PPCContext& ctx, uint8_t* base);         // управление командой (менеджер, команда, флаг)
extern "C" void sub_82B4C958(PPCContext& ctx, uint8_t* base);         // удалить игрока (черновик, playerindex)
extern "C" void sub_82B87E80(PPCContext& ctx, uint8_t* base);         // список: убрать элемент
extern "C" void sub_828A3478(PPCContext& ctx, uint8_t* base);         // освободить память
extern "C" void __imp__sub_82B7E6E8(PPCContext& ctx, uint8_t* base);  // звенья: собрать (L)
extern "C" void __imp__sub_82B85F40(PPCContext& ctx, uint8_t* base);  // звенья: в объект состава (L)
extern "C" void __imp__sub_82B9AAC0(PPCContext& ctx, uint8_t* base);  // звенья по ручке команды (82B93C58)
extern "C" void __imp__sub_82B96838(PPCContext& ctx, uint8_t* base);  // … по ручке, со сбросом в базу
extern "C" void __imp__sub_82B94900(PPCContext& ctx, uint8_t* base);  // … по ручке: расчёт
extern "C" void __imp__sub_82B373C8(PPCContext& ctx, uint8_t* base);  // новичок драфта
extern "C" void __imp__sub_82B37598(PPCContext& ctx, uint8_t* base);  // новичок драфта

namespace {

constexpr uint32_t kTaskType = 1;
constexpr int32_t kQmjhl = 10;
constexpr int32_t kNationsLeague = 8;
constexpr uint32_t kModeBeAGm = 4;            // режим создателя (+3124): Be a GM 4, Be a Pro 5
// сборные лиги 8 (exhibitionteams): без Великобритании 141, Италии 142, Японии 143, Казахстана 144 и Польши 147 —
// у них во франшизе почти нет игроков (пулы natcup.franchise: 3, 6, 1, 0, 9)
constexpr uint32_t kNations[] = {133, 134, 135, 136, 137, 138, 139, 140, 145, 146, 148, 149, 150, 151, 152, 153};

uint8_t* Host(uint8_t* base, uint32_t addr) {
  return base + addr + (addr >= 0xE0000000u ? 0x1000u : 0u);
}
uint32_t Load32(uint8_t* base, uint32_t a) {
  uint32_t v;
  std::memcpy(&v, Host(base, a), 4);
  return __builtin_bswap32(v);
}
void Store32(uint8_t* base, uint32_t a, uint32_t v) {
  v = __builtin_bswap32(v);
  std::memcpy(Host(base, a), &v, 4);
}

bool Enabled() {
  static const bool on = [] {
    const bool v = REXCVAR_GET(nhl_natcup);
    REXLOG_INFO("[nhllegacy] Nations Cup experiment (nhl_natcup): {}", v ? "on" : "off");
    return v;
  }();
  return on;
}

// Дни ↔ дата (григорианский календарь). Эпоха движка — 1.01.1900 = 0: старт франшизы «NHL Entry Draft» в игре
// 19.06.2026 = 46190, 25.08.2026 в игре = 46257 (leaguestates type 0), 1.09 турнира = 46264 (прогоны 20.10).
int64_t DaysFromCivil(int64_t y, unsigned m, unsigned d) {
  y -= m <= 2;
  const int64_t era = (y >= 0 ? y : y - 399) / 400;
  const unsigned yoe = static_cast<unsigned>(y - era * 400);
  const unsigned doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
  const unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
  return era * 146097 + static_cast<int64_t>(doe) - 719468;
}
const int64_t kEpoch = DaysFromCivil(1900, 1, 1);

void CivilFromDays(int64_t z, int* y, unsigned* m, unsigned* d) {
  z += 719468;
  const int64_t era = (z >= 0 ? z : z - 146096) / 146097;
  const unsigned doe = static_cast<unsigned>(z - era * 146097);
  const unsigned yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
  const unsigned doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
  const unsigned mp = (5 * doy + 2) / 153;
  *d = doy - (153 * mp + 2) / 5 + 1;
  *m = mp < 10 ? mp + 3 : mp - 9;
  *y = static_cast<int>(static_cast<int64_t>(yoe) + era * 400 + (*m <= 2));
}

struct Ymd {
  int y;
  unsigned m, d;
};
Ymd ToYmd(uint32_t serial) {
  Ymd r{};
  CivilFromDays(static_cast<int64_t>(serial) + kEpoch, &r.y, &r.m, &r.d);
  return r;
}
uint32_t ToSerial(int y, unsigned m, unsigned d) {
  return static_cast<uint32_t>(DaysFromCivil(y, m, d) - kEpoch);
}

// Уровень лиги во франшизе (82AF9838(менеджер, лига, 0)); −1 — лиги нет.
int32_t LevelOf(PPCContext& ctx, uint8_t* base, int32_t league) {
  sub_82AF8BF0(ctx, base);
  if (!ctx.r3.u32) {
    return -1;
  }
  ctx.r4.s64 = league;
  ctx.r5.u64 = 0;
  sub_82AF9838(ctx, base);
  return ctx.r3.s32;
}

bool IsNation(uint32_t id) {
  for (const uint32_t k : kNations) {
    if (k == id) {
      return true;
    }
  }
  return false;
}

// Имена таблиц и полей база ищет по хешу (CRC-32, отражённая таблица, начальное 0, буквы — заглавные). Поле строки
// курсора — 827B3008/827B3030(курсор, номер таблицы, номер поля, 1, &значение, 0); номер поля — порядок полей таблицы
// в схеме nhlng-meta.xml (juniorteam = 11, как у оригинала; leagueteams: index 0, shortname 44, audioid 47 — как у
// 82A10640), номер таблицы — по дескриптору 827B5D40(база+8, хеш таблицы).
constexpr uint32_t kTablePlayerBio = 0xF97F5A5Au;     // leagueplayerbiotable
constexpr uint32_t kFieldJuniorLeague = 0x1A86215Au;  // juniorleague (для условия запроса)
constexpr uint32_t kColJuniorTeam = 11;
constexpr uint32_t kColJuniorLeague = 7;
constexpr uint32_t kJuniorLock = 0x83DA3A00u;         // критическая секция цикла (как у оригинала)

uint32_t TableIndex(PPCContext& ctx, uint8_t* base, uint32_t db, uint32_t hash) {
  ctx.r3.u64 = Load32(base, db + 8);
  ctx.r4.u64 = hash;
  sub_827B5D40(ctx, base);
  const uint32_t desc = ctx.r3.u32;
  return (desc - Load32(base, Load32(base, desc + 4) + 28)) / 68;
}

// ---------------------------------------------------------------- чтение таблиц (курсор, как у 82B099E0)

constexpr uint32_t kTableSchedule = 0xE0A915B4u;   // leaguescheduletable
constexpr uint32_t kTableGameStats = 0x5C32910Au;  // leaguegamestats
constexpr uint32_t kTableSkaterAi = 0xE5C10816u;   // leagueskaterai
constexpr uint32_t kTableGoalieAi = 0xEA50C5DAu;   // leaguegoalieai
constexpr uint32_t kTableTeams = 0xC7BCD146u;      // leagueteams
constexpr uint32_t kTableRoster = 0x32926EE1u;     // leaguerostertable
constexpr uint32_t kFieldTeam = 0xD33194B7u;
constexpr int32_t kContractActive = 0;  // contractstatus игрока по контракту (rangelow −1: в сейве 1), как у НХЛ
constexpr int32_t kStockContractYears = 3;
constexpr uint32_t kRosterCache = 0x83BDC550u;  // кэш объектов состава (82B61C80): +0 число, +4 голова; элемент:
                                                // +0 следующий, +8 команда, +12 счётчик ссылок
constexpr uint32_t kFieldMonth = 0xBFC025ABu;
// номера полей — порядок в схеме nhlng-meta.xml (см. выше)
namespace col {
constexpr uint32_t kSchIndex = 0, kSchStatus = 1, kSchHome = 2, kSchLeague = 3, kSchDay = 4, kSchAway = 5, kSchMonth = 6,
                   kSchRound = 7;
constexpr uint32_t kGsIndex = 0, kGsOt = 1, kGsShootout = 3, kGsScoreAway = 7, kGsScoreHome = 17;
constexpr uint32_t kBioIndex = 0, kBioCountry = 42, kBioPosition = 84, kBioTeam = 78, kBioInjury = 29, kBioJersey = 58;
constexpr uint32_t kBioYear = 56, kBioMonth = 70, kBioDay = 38, kBioHeight = 61, kBioWeight = 16;
constexpr uint32_t kBioContract = 36, kBioContractLen = 87;
constexpr uint32_t kSkIndex = 0, kSkStyle = 25;
constexpr uint32_t kGkIndex = 0, kGkStyle = 21;
constexpr uint32_t kTmIndex = 0, kTmTeamId = 3, kTmLeague = 30;
constexpr uint32_t kRsPlayer = 48, kRsTeam = 67, kRsG1 = 68;
}  // namespace col

// Строки таблицы (все или с условием «поле == значение»): fn(get, put) на каждую строку; get(номер поля) → значение,
// put(номер поля, значение) пишет в строку курсора (827B3030). Кадр f — свои 0x100 байт (f+80…f+200), вызываемые
// функции пишут ниже f.
template <typename Fn>
int32_t ForEachRow(PPCContext& ctx, uint8_t* base, uint32_t f, uint32_t table_hash, uint32_t where_field,
                   int32_t where_value, Fn&& fn) {
  const uint64_t saved_r1 = ctx.r1.u64;
  std::memset(Host(base, f), 0, 0x100);
  ctx.r1.u64 = f;
  sub_82A07D88(ctx, base);
  const uint32_t db = ctx.r3.u32;
  const uint32_t table = TableIndex(ctx, base, db, table_hash);
  uint32_t where = 0;
  if (where_field) {
    ctx.r3.u64 = f + 96;
    ctx.r4.u64 = where_field;
    sub_827B10C8(ctx, base);
    ctx.r4.s64 = where_value;
    sub_827B1588(ctx, base);
    where = ctx.r3.u32;
  }
  sub_82A07D88(ctx, base);
  ctx.r4.u64 = ctx.r3.u64;
  ctx.r3.u64 = f + 84;
  sub_827B7D08(ctx, base);
  ctx.r4.u64 = ctx.r3.u64;
  ctx.r3.u64 = f + 80;
  ctx.r5.u64 = table_hash;
  sub_827B4818(ctx, base);
  if (where) {
    ctx.r4.u64 = where;
    ctx.r5.u64 = 1;
    sub_827B4A48(ctx, base);
  }
  sub_827B5568(ctx, base);
  const uint32_t cur = ctx.r3.u32;
  ctx.r3.u64 = f + 80;
  sub_833FBEA0(ctx, base);
  ctx.r3.u64 = f + 84;
  sub_833FBEA0(ctx, base);
  if (where) {
    ctx.r3.u64 = f + 96;
    sub_827B11E0(ctx, base);
  }
  ctx.r3.u64 = cur;
  sub_827B2E10(ctx, base);
  const int32_t n = static_cast<int32_t>(ctx.r3.u32 & 0xFFFFu);
  auto get = [&](uint32_t c) {
    ctx.r3.u64 = cur;
    ctx.r4.u64 = table;
    ctx.r5.u64 = c;
    ctx.r6.u64 = 1;
    ctx.r7.u64 = f + 88;
    ctx.r8.u64 = 0;
    sub_827B3008(ctx, base);
    return static_cast<int32_t>(Load32(base, f + 88));
  };
  auto put = [&](uint32_t c, int32_t v) {
    Store32(base, f + 92, static_cast<uint32_t>(v));
    ctx.r3.u64 = cur;
    ctx.r4.u64 = table;
    ctx.r5.u64 = c;
    ctx.r6.u64 = 1;
    ctx.r7.u64 = f + 92;
    ctx.r8.u64 = 0;
    sub_827B3030(ctx, base);
  };
  if (n > 0) {
    ctx.r3.u64 = kJuniorLock;
    __imp__RtlEnterCriticalSection(ctx, base);
    for (int32_t i = 0; i < n; ++i) {
      fn(get, put);
      ctx.r3.u64 = cur;
      ctx.r4.u64 = 1;
      ctx.r5.u64 = 1;
      sub_827B2D08(ctx, base);
    }
    ctx.r3.u64 = kJuniorLock;
    __imp__RtlLeaveCriticalSection(ctx, base);
  }
  ctx.r3.u64 = cur;
  sub_827B2C40(ctx, base);
  ctx.r1.u64 = saved_r1;
  return n;
}

// Номера франшизы сборных (leagueteams: teamid → index). Итератор сведений о командах (82AE9DD8/82AF6570) при
// создании франшизы сборных не видит (прогон 20.10: 0 из 16) — читаем таблицу.
bool g_nation_team[128];  // номер франшизы → сборная (последний NationTeams)

std::map<uint32_t, uint32_t> NationTeams(PPCContext& ctx, uint8_t* base, uint32_t f) {
  std::map<uint32_t, uint32_t> out;
  ForEachRow(ctx, base, f, kTableTeams, 0, 0, [&](auto& get, auto&) {
    const uint32_t id = static_cast<uint32_t>(get(col::kTmTeamId));
    if (IsNation(id)) {
      out[id] = static_cast<uint32_t>(get(col::kTmIndex));
    }
  });
  std::memset(g_nation_team, 0, sizeof(g_nation_team));
  for (const auto& [id, t] : out) {
    if (t < 128) {
      g_nation_team[t] = true;
    }
  }
  return out;
}

// ---------------------------------------------------------------- Кубок наций

constexpr uint32_t kLevelGroup = 2, kLevelSub = 0;  // пара уровня сборных (+4, +8): 82975FA0(2, 0) = 3 (лог задач)
constexpr uint32_t kAugust = 7;                     // месяц с нуля
constexpr uint32_t kGroupDays[3] = {1, 3, 5};       // 2, 4, 6 августа (день с нуля)
constexpr uint32_t kSemiDay = 8, kFinalDay = 10;    // 9 и 11 августа
constexpr uint32_t kLastDay = 19;                   // 20 августа — уборка
constexpr uint32_t kStatusCancelled = 2;            // leaguescheduletable.status: 2 — отменена
constexpr int kQuota[5] = {4, 4, 4, 8, 3};          // C, LW, RW, D, G (крайние — 8 вместе)
constexpr int kDressed[3] = {12, 6, 2};             // в заявке на матч: нападающие, защитники, вратари
constexpr size_t kRosterSize = 23;
constexpr int kTeams = 8;

// intlcountry → teamid сборной (как tools/natcup/franchise.py NATIONS; только 16 сборных франшизы)
uint32_t NationOfCountry(int32_t c) {
  switch (c) {
    case 0: return 135;   // Canada
    case 14: return 153;  // USA
    case 67: return 138;  // Finland
    case 69: return 150;  // Sweden
    case 82: return 136;  // Czech Republic
    case 97: return 151;  // Switzerland
    case 85: return 140;  // Germany
    case 76: return 148;  // Russia
    case 95: return 149;  // Slovakia
    case 68: return 146;  // Norway
    case 70: return 134;  // Belarus
    case 74: return 145;  // Latvia
    case 66: return 137;  // Denmark
    case 84: return 139;  // France
    case 77: return 152;  // Ukraine
    case 78: return 133;  // Austria
    default: return 0;
  }
}

// OVR, который показывает игра (tools/roster/ovrformula.py, сверено с игрой на 61 полевом): c_overall в базе — 0
// (игра его не читает), OVR считается из атрибутов c_* (шкала 0…63 + 36) по таблицам worth2.brk: категория —
// Σ вес·атрибут, зажатая в [lo·W, hi·W], → 0…999; OVR = Σ категория·доля / 1000 в пределах 36…99. Номера колонок —
// порядок полей leagueskaterai / leaguegoalieai в nhlng-meta.xml.
struct OvrTerm {
  uint8_t col, w;
};
struct OvrCat {
  int share, lo, hi, n;
  OvrTerm t[7];
};
constexpr OvrCat kOvrF[] = {  // нападающие (таблица 9)
    {16, 40, 94, 4, {{111, 17}, {84, 17}, {144, 40}, {6, 26}}},
    {16, 20, 94, 4, {{126, 55}, {109, 23}, {30, 11}, {114, 11}}},
    {16, 20, 94, 3, {{36, 80}, {89, 19}, {32, 1}}},
    {20, 40, 93, 5, {{110, 25}, {82, 25}, {101, 25}, {60, 24}, {80, 1}}},
    {10, 40, 94, 5, {{103, 55}, {141, 35}, {86, 2}, {16, 2}, {79, 6}}},
    {22, 50, 93, 4, {{136, 69}, {116, 5}, {76, 25}, {28, 1}}},
};
constexpr OvrCat kOvrD[] = {  // защитники (таблица 6)
    {8, 40, 95, 4, {{111, 30}, {84, 55}, {144, 5}, {6, 10}}},
    {11, 40, 94, 4, {{126, 60}, {109, 25}, {30, 12}, {114, 3}}},
    {10, 45, 95, 2, {{36, 97}, {32, 3}}},
    {11, 40, 93, 5, {{110, 26}, {82, 21}, {101, 26}, {60, 26}, {80, 1}}},
    {10, 50, 95, 5, {{103, 55}, {141, 35}, {86, 2}, {16, 2}, {79, 6}}},
    {50, 30, 93, 5, {{136, 55}, {116, 13}, {76, 20}, {89, 11}, {28, 1}}},
};
constexpr OvrCat kOvrG[] = {  // вратари (таблица 13)
    {60, 27, 95, 7, {{70, 15}, {97, 12}, {45, 13}, {9, 15}, {14, 15}, {5, 15}, {6, 15}}},
    {20, 40, 95, 6, {{112, 1}, {80, 1}, {76, 46}, {91, 46}, {41, 1}, {83, 5}}},
    {20, 37, 94, 6, {{79, 15}, {96, 20}, {72, 15}, {74, 20}, {103, 15}, {104, 15}}},
};
constexpr int kAttrBase = 36;

template <size_t N, typename Get>
int GameOvr(const OvrCat (&cats)[N], Get&& attr) {
  int v = 0;
  for (const auto& c : cats) {
    int sum = 0, w = 0;
    for (int k = 0; k < c.n; ++k) {
      sum += c.t[k].w * (attr(c.t[k].col) + kAttrBase);
      w += c.t[k].w;
    }
    sum = std::min(std::max(sum, c.lo * w), c.hi * w);
    v += std::min(999, (sum - c.lo * w) * 1000 / ((c.hi - c.lo) * w)) * c.share;
  }
  return std::min(std::max(v / 1000, 36), 99);
}

struct Cand {
  int32_t index, pos, ovr, jersey, style;
  bool dressed = false;
  bool injured = false;
};

int Group(const Cand& c) {
  return c.pos == 4 ? 2 : c.pos == 3 ? 1 : 0;  // нападающие, защитники, вратари
}

// Заявка на матч (rosterstatus 1): 12 нападающих, 6 защитников, 2 вратаря — лучшие по c_overall; лучший — первым.
void MarkDressed(std::vector<Cand>& v) {
  std::stable_sort(v.begin(), v.end(), [](const Cand& a, const Cand& b) { return a.ovr > b.ovr; });
  int n[3] = {0, 0, 0};
  for (auto& c : v) {
    const int g = Group(c);
    c.dressed = !c.injured && n[g] < kDressed[g];
    n[g] += c.dressed ? 1 : 0;
  }
}

struct Players {
  std::map<uint32_t, std::vector<Cand>> real;   // teamid сборной → игроки клубов её страны (без травмированных)
  std::map<uint32_t, std::vector<Cand>> stock;  // номер франшизы сборной → её стоковые игроки (bio.team)
  std::map<int32_t, Cand> all;                  // все игроки с атрибутами
};

// Стоковые игроки сборной (82B3DFC8 при создании: свои записи, часть — дубли игроков клубов) числятся за ней
// (bio.team); в турнир идут игроки клубов, стоковые — только на недобор и обратно в состав после турнира.
Players ReadPlayers(PPCContext& ctx, uint8_t* base, uint32_t f, const std::map<uint32_t, uint32_t>& teams) {
  struct Ai {
    int f, d, style;  // OVR нападающего и защитника (у вратаря — оба), стиль
  };
  std::map<int32_t, Ai> sk, gk;
  ForEachRow(ctx, base, f, kTableSkaterAi, 0, 0, [&](auto& get, auto&) {
    int a[160];
    for (const auto* cats : {kOvrF, kOvrD}) {
      for (size_t k = 0; k < 6; ++k) {
        for (int j = 0; j < cats[k].n; ++j) {
          a[cats[k].t[j].col] = get(cats[k].t[j].col);
        }
      }
    }
    auto attr = [&](int c) { return a[c]; };
    sk[get(col::kSkIndex)] = {GameOvr(kOvrF, attr), GameOvr(kOvrD, attr), get(col::kSkStyle)};
  });
  ForEachRow(ctx, base, f, kTableGoalieAi, 0, 0, [&](auto& get, auto&) {
    const int g = GameOvr(kOvrG, [&](int c) { return get(c); });
    gk[get(col::kGkIndex)] = {g, g, get(col::kGkStyle)};
  });
  std::map<int32_t, bool> nation_team;
  for (const auto& [id, t] : teams) {
    nation_team[static_cast<int32_t>(t)] = true;
  }
  Players p;
  ForEachRow(ctx, base, f, kTablePlayerBio, 0, 0, [&](auto& get, auto&) {
    const int32_t idx = get(col::kBioIndex);
    const int32_t pos = get(col::kBioPosition);
    if (pos < 0 || pos > 4) {
      return;
    }
    const auto& m = pos == 4 ? gk : sk;
    auto it = m.find(idx);
    if (it == m.end()) {
      return;
    }
    Cand c{idx, pos, pos == 3 ? it->second.d : it->second.f, get(col::kBioJersey), it->second.style};
    c.injured = get(col::kBioInjury) > 0;
    p.all[idx] = c;
    const int32_t team = get(col::kBioTeam);
    if (nation_team.count(team)) {
      p.stock[static_cast<uint32_t>(team)].push_back(c);
      return;
    }
    const uint32_t nat = NationOfCountry(get(col::kBioCountry));
    if (nat && team >= 0 && !c.injured) {
      p.real[nat].push_back(c);
    }
  });
  return p;
}

// 4 C, 8 крайних, 8 D, 3 G: лучшие игроки клубов; недобор — стоковыми игроками сборной, затем любыми полевыми.
std::vector<Cand> PickRoster(std::vector<Cand> real, std::vector<Cand> stock) {
  auto by_ovr = [](const Cand& a, const Cand& b) { return a.ovr > b.ovr; };
  std::stable_sort(real.begin(), real.end(), by_ovr);
  std::stable_sort(stock.begin(), stock.end(), by_ovr);
  std::vector<Cand> out;
  int need[5] = {kQuota[0], kQuota[1], kQuota[2], kQuota[3], kQuota[4]};
  for (auto* v : {&real, &stock}) {
    for (auto& c : *v) {
      int p = c.pos;
      if ((p == 1 || p == 2) && need[p] == 0 && need[3 - p] > 0) {
        p = 3 - p;  // крайние — 8 вместе
      }
      if (need[p] > 0) {
        --need[p];
        out.push_back(c);
        c.index = -1;
      }
    }
  }
  for (auto* v : {&real, &stock}) {
    for (auto& c : *v) {
      if (out.size() < kRosterSize && c.index >= 0 && c.pos != 4) {
        out.push_back(c);
        c.index = -1;
      }
    }
  }
  MarkDressed(out);
  return out;
}

struct Game {
  int32_t index, day, home, away, round;
  bool played = false;
  int32_t gh = 0, ga = 0;
  bool ot = false;
};

// Игры августа между сборными (status ≠ 2) и их итоги (строка leaguegamestats с тем же index — игра сыграна).
std::vector<Game> ReadGames(PPCContext& ctx, uint8_t* base, uint32_t f, const std::map<uint32_t, uint32_t>& teams) {
  std::map<int32_t, bool> nation_team;
  for (const auto& [id, t] : teams) {
    nation_team[static_cast<int32_t>(t)] = true;
  }
  std::vector<Game> games;
  ForEachRow(ctx, base, f, kTableSchedule, kFieldMonth, kAugust, [&](auto& get, auto&) {
    const int32_t home = get(col::kSchHome), away = get(col::kSchAway);
    if (!nation_team.count(home) || !nation_team.count(away) ||
        static_cast<uint32_t>(get(col::kSchStatus)) == kStatusCancelled) {
      return;
    }
    games.push_back({get(col::kSchIndex), get(col::kSchDay), home, away, get(col::kSchRound)});
  });
  if (!games.empty()) {
    std::map<int32_t, Game*> by;
    for (auto& g : games) {
      by[g.index] = &g;
    }
    ForEachRow(ctx, base, f, kTableGameStats, 0, 0, [&](auto& get, auto&) {
      auto it = by.find(get(col::kGsIndex));
      if (it == by.end()) {
        return;
      }
      it->second->played = true;
      it->second->gh = get(col::kGsScoreHome);
      it->second->ga = get(col::kGsScoreAway);
      it->second->ot = get(col::kGsOt) || get(col::kGsShootout);
    });
  }
  return games;
}

void AddGame(PPCContext& ctx, uint8_t* base, uint32_t f, uint32_t day, uint32_t home, uint32_t away) {
  const uint64_t saved_r1 = ctx.r1.u64;
  std::memset(Host(base, f), 0, 0x100);
  const uint32_t g = f + 0x80;
  Store32(base, g + 0, 0x82046474u);  // vtable записи календаря
  Store32(base, g + 8, kAugust);
  Store32(base, g + 12, day);
  Store32(base, g + 16, home);
  Store32(base, g + 20, away);
  Store32(base, g + 28, 0);  // status
  Store32(base, g + 32, 0);  // round: 0 — как круг (буллиты вместо бесконечного ОТ — как у IIHF)
  Store32(base, g + 36, kLevelGroup);
  Store32(base, g + 40, kLevelSub);
  ctx.r1.u64 = f;
  ctx.r3.u64 = 0;
  ctx.r4.u64 = g;
  sub_82BEC748(ctx, base);
  const bool ok = ctx.r3.u8 != 0;
  ctx.r1.u64 = saved_r1;
  REXLOG_INFO("[nhllegacy] natcup: game Aug {}: {} - {} {}", day + 1, home, away, ok ? "added" : "NOT added");
}

void SetUserTeam(PPCContext& ctx, uint8_t* base, uint32_t team, bool user) {
  sub_82AF8BF0(ctx, base);
  ctx.r4.u64 = team;
  ctx.r5.u64 = user ? 0 : 1;
  sub_82B1B048(ctx, base);
  REXLOG_INFO("[nhllegacy] natcup: team {} {}", team, user ? "-> user" : "-> CPU");
}

// Поля звеньев leaguerostertable — байты R+404+71i+k (k — номер ниже; порядок — загрузки 82A1BBF8).
namespace ln {
enum : int {
  L1LW, L1C, L1RW, L2LW, L2C, L2RW, L3LW, L3C, L3RW, L4LW, L4C, L4RW,
  L1LD, L1RD, L2LD, L2RD, L3LD, L3RD,
  PP1LW, PP1C, PP1RW, PP1LD, PP1RD, PP2LW, PP2C, PP2RW, PP2LD, PP2RD,
  PP41C, PP41LW, PP41LD, PP41RD, PP42C, PP42LW, PP42LD, PP42RD,
  PK41C, PK41LW, PK41LD, PK41RD, PK42C, PK42LW, PK42LD, PK42RD,
  PK31C, PK31LD, PK31RD, PK32C, PK32LD, PK32RD,
  S1, S2, S3, S4, S5, G1, G2, X1, X2,
  OT1C, OT1LW, OT1LD, OT1RD, OT2C, OT2LW, OT2LD, OT2RD, OT3C, OT3LW, OT3LD, OT3RD,
  kCount
};
static_assert(kCount == 71, "71 поле звеньев");
}  // namespace ln

// Звенья из заявки (players отсортированы по OVR): 4 тройки (центр, левый и правый — по амплуа, если хватает),
// 3 пары защиты, большинство/меньшинство/ОТ — из первых звеньев, буллиты — 5 лучших нападающих. slot[k] — номер
// игрока в players (−1 — некого).
std::vector<int> BuildLines(const std::vector<Cand>& players, size_t n) {
  std::vector<int> c, w, d, g, f;
  for (size_t i = 0; i < n; ++i) {
    const Cand& p = players[i];
    if (!p.dressed) {
      continue;
    }
    auto& v = p.pos == 0 ? c : (p.pos == 1 || p.pos == 2) ? w : p.pos == 3 ? d : g;
    v.push_back(static_cast<int>(i));
    if (p.pos != 3 && p.pos != 4) {
      f.push_back(static_cast<int>(i));
    }
  }
  while (c.size() < 4 && w.size() > 8) {  // нехватка центров — лучшим лишним крайним
    c.push_back(w.back());
    w.pop_back();
  }
  std::vector<int> slot(ln::kCount, -1);
  auto at = [](const std::vector<int>& v, size_t i) { return i < v.size() ? v[i] : -1; };
  std::vector<bool> used(n, false);
  auto wing = [&](int side) {  // лучший свободный крайний своей стороны, иначе любой
    for (const int pass : {0, 1}) {
      for (const int i : w) {
        if (!used[i] && (pass == 1 || players[i].pos == side)) {
          used[i] = true;
          return i;
        }
      }
    }
    return -1;
  };
  int lw[4], rw[4];
  for (int k = 0; k < 4; ++k) {
    slot[ln::L1C + 3 * k] = at(c, k);
    lw[k] = slot[ln::L1LW + 3 * k] = wing(1);
    rw[k] = slot[ln::L1RW + 3 * k] = wing(2);
  }
  for (int k = 0; k < 3; ++k) {
    slot[ln::L1LD + 2 * k] = at(d, 2 * k);
    slot[ln::L1RD + 2 * k] = at(d, 2 * k + 1);
  }
  for (int k = 0; k < 2; ++k) {
    const int o = 5 * k;  // PP1 / PP2 — тройка k и пара k
    slot[ln::PP1LW + o] = lw[k];
    slot[ln::PP1C + o] = at(c, k);
    slot[ln::PP1RW + o] = rw[k];
    slot[ln::PP1LD + o] = at(d, 2 * k);
    slot[ln::PP1RD + o] = at(d, 2 * k + 1);
    const int q = 4 * k;  // PP 4 на 3, PK 4 на 5 (центры 2 и 3 тройки), PK 3 на 5
    slot[ln::PP41C + q] = at(c, k);
    slot[ln::PP41LW + q] = lw[k];
    slot[ln::PP41LD + q] = at(d, 2 * k);
    slot[ln::PP41RD + q] = at(d, 2 * k + 1);
    slot[ln::PK41C + q] = at(c, k + 1);
    slot[ln::PK41LW + q] = lw[k + 1];
    slot[ln::PK41LD + q] = at(d, 2 * k);
    slot[ln::PK41RD + q] = at(d, 2 * k + 1);
    const int t = 3 * k;
    slot[ln::PK31C + t] = at(c, k + 1);
    slot[ln::PK31LD + t] = at(d, 2 * k);
    slot[ln::PK31RD + t] = at(d, 2 * k + 1);
  }
  for (int k = 0; k < 3; ++k) {
    const int o = 4 * k;
    slot[ln::OT1C + o] = at(c, k);
    slot[ln::OT1LW + o] = lw[k];
    slot[ln::OT1LD + o] = at(d, 2 * k);
    slot[ln::OT1RD + o] = at(d, 2 * k + 1);
  }
  for (int k = 0; k < 5; ++k) {
    slot[ln::S1 + k] = at(f, k);
  }
  slot[ln::G1] = at(g, 0);
  slot[ln::G2] = at(g, 1);
  slot[ln::X1] = at(c, 1);
  slot[ln::X2] = lw[1];
  return slot;
}

// Объект состава команды в кэше 82B61C80 (элементы не освобождаются, пока 82B61D18 не очистит весь кэш): после
// записи состава старый объект остаётся, и построитель звеньев (82B87538 → 82B7E6E8 → 82B871F8) считает по нему —
// тест 6: у 4 из 8 сборных звенья обнулены до первых игр. Убираем элемент команды, если его никто не держит
// (так же, как 82B61D18): 1 — убран, 0 — не было, −1 — занят.
int DropCachedRoster(PPCContext& ctx, uint8_t* base, uint32_t team) {
  const uint32_t n = Load32(base, kRosterCache);
  uint32_t e = Load32(base, kRosterCache + 4);
  for (uint32_t i = 0; i < n && e; ++i, e = Load32(base, e)) {
    if (Load32(base, e + 8) != team) {
      continue;
    }
    if (Load32(base, e + 12) != 0) {
      return -1;
    }
    ctx.r3.u64 = kRosterCache;
    ctx.r4.u64 = e;
    sub_82B87E80(ctx, base);
    ctx.r3.u64 = e;
    sub_828A3478(ctx, base);
    return 1;
  }
  return 0;
}

// Удалить игрока, как игра удаляет ушедших (82B567B8 → 82B4C958: звенья, bio, атрибуты, экипировка, составы…);
// первый аргумент — черновик (+80, +132, +136).
void DeletePlayer(PPCContext& ctx, uint8_t* base, int32_t index) {
  const uint64_t saved_r1 = ctx.r1.u64;
  const uint32_t scratch = (ctx.r1.u32 - 0x200) & ~0xFu;
  std::memset(Host(base, scratch), 0, 0x100);
  ctx.r1.u64 = scratch;
  ctx.r3.u64 = scratch;
  ctx.r4.s64 = index;
  sub_82B4C958(ctx, base);
  ctx.r1.u64 = saved_r1;
}

void ClearRoster(PPCContext& ctx, uint8_t* base, uint32_t team) {
  ctx.r3.u64 = 0;
  ctx.r4.u64 = team;
  sub_82A1BB18(ctx, base);
}

// Состав команды (82A29D48 → 82A1BBF8: строки leaguerostertable с key = команда × 40 + i; bio.team игроков не
// меняет — игрок клуба одновременно в сборной, как у Матча звёзд) со своими звеньями (BuildLines): построитель
// звеньев 82B87538 → 82B7E6E8 → 82B871F8 берёт объект состава из кэша 82B61C80 и сборным звеньев не дал (тест 4:
// g1/l1c… = 0, «on the ice 0», зависание сима на финале).
void WriteRoster(PPCContext& ctx, uint8_t* base, uint32_t team, const std::vector<Cand>& players) {
  const uint64_t saved_r1 = ctx.r1.u64;
  const uint32_t f = (ctx.r1.u32 - 0x1000) & ~0xFu;  // R (3244 б) + tmp (16 б)
  const uint32_t r = f + 0x100;
  const uint32_t tmp = f + 0x100 + 3264;
  std::memset(Host(base, f), 0, 0x1000);
  ctx.r1.u64 = f;
  ClearRoster(ctx, base, team);
  if (players.empty()) {
    ctx.r1.u64 = saved_r1;
    REXLOG_INFO("[nhllegacy] natcup: roster of team {} cleared", team);
    return;
  }
  ctx.r3.u64 = r;
  sub_829748A0(ctx, base);
  ctx.r3.u64 = r;
  ctx.r4.u64 = 0;
  ctx.r5.u64 = 3244;
  sub_82657880(ctx, base);
  const size_t n = std::min<size_t>(players.size(), 40);
  *Host(base, r + 1) = static_cast<uint8_t>(n);
  bool taken[100] = {};
  int leaders = 0;  // капитан и два ассистента — лучшие полевые
  for (size_t i = 0; i < n; ++i) {
    const Cand& c = players[i];
    const uint32_t k = static_cast<uint32_t>(i);
    int jersey = c.jersey;
    if (jersey <= 0 || jersey > 99 || taken[jersey]) {
      jersey = 0;
      for (int j = c.pos == 4 ? 30 : 2; j < 100 && !jersey; ++j) {
        jersey = taken[j] ? 0 : j;
      }
    }
    taken[jersey] = true;
    *Host(base, r + 2 + 2 * k) = static_cast<uint8_t>(c.index >> 8);
    *Host(base, r + 3 + 2 * k) = static_cast<uint8_t>(c.index & 0xFF);
    Store32(base, r + 84 + 4 * k, c.dressed ? 1 : 0);
    *Host(base, r + 244 + k) = static_cast<uint8_t>(jersey);
    *Host(base, r + 284 + k) = static_cast<uint8_t>(c.style);
    if (c.pos != 4 && c.dressed && leaders < 3) {
      *Host(base, r + (leaders == 0 ? 324 : 325) + 2 * k) = 1;  // +324+2i — капитан, +325+2i — ассистент
      ++leaders;
    }
  }
  const auto slot = BuildLines(players, n);
  int filled = 0;
  for (int k = 0; k < ln::kCount; ++k) {
    if (slot[k] >= 0) {
      *Host(base, r + 404 + 71 * static_cast<uint32_t>(slot[k]) + static_cast<uint32_t>(k)) = 1;
      ++filled;
    }
  }
  ctx.r3.u64 = tmp;
  sub_82BA65C8(ctx, base);
  ctx.r3.u64 = tmp;
  ctx.r4.u64 = team;
  ctx.r5.u64 = r;
  sub_82A29D48(ctx, base);
  const bool ok = ctx.r3.u8 != 0;
  ctx.r3.u64 = tmp;
  sub_82BCC4A0(ctx, base);
  const int cache = DropCachedRoster(ctx, base, team);
  if (cache < 0) {
    REXLOG_INFO("[nhllegacy] natcup: team {}: cached roster object in use, not dropped", team);
  }
  ctx.r1.u64 = saved_r1;
  REXLOG_INFO("[nhllegacy] natcup: roster of team {}: {} players, {}/{} line slots, {}", team, n, filled,
              static_cast<int>(ln::kCount), ok ? "written" : "NOT written");
}

struct Nation {
  uint32_t teamid = 0, team = 0;  // teamid базы и номер франшизы
  std::vector<Cand> roster;
  double strength = 0;
};

struct Row {
  uint32_t team;
  int pts = 0, w = 0, gf = 0, ga = 0;
};

// Группы и таблица — по играм группового этапа (дни до kSemiDay): команды, игравшие друг с другом, — одна группа.
std::vector<std::vector<Row>> Standings(const std::vector<Game>& games) {
  std::map<uint32_t, uint32_t> grp;  // команда → представитель группы
  std::function<uint32_t(uint32_t)> find = [&](uint32_t t) { return grp[t] == t ? t : grp[t] = find(grp[t]); };
  for (const auto& g : games) {
    if (static_cast<uint32_t>(g.day) >= kSemiDay) {
      continue;
    }
    for (const uint32_t t : {static_cast<uint32_t>(g.home), static_cast<uint32_t>(g.away)}) {
      if (!grp.count(t)) {
        grp[t] = t;
      }
    }
    grp[find(g.home)] = find(g.away);
  }
  std::map<uint32_t, std::map<uint32_t, Row>> tables;
  for (auto& [t, _] : grp) {
    tables[find(t)][t].team = t;
  }
  for (const auto& g : games) {
    if (static_cast<uint32_t>(g.day) >= kSemiDay || !g.played) {
      continue;
    }
    auto& tb = tables[find(g.home)];
    Row& h = tb[g.home];
    Row& a = tb[g.away];
    h.gf += g.gh, h.ga += g.ga, a.gf += g.ga, a.ga += g.gh;
    Row& win = g.gh > g.ga ? h : a;
    Row& los = g.gh > g.ga ? a : h;
    win.pts += 2, win.w += 1;
    if (g.ot) {
      los.pts += 1;
    }
  }
  std::vector<std::vector<Row>> out;
  for (auto& [_, tb] : tables) {
    std::vector<Row> v;
    for (auto& [t, r] : tb) {
      v.push_back(r);
    }
    std::sort(v.begin(), v.end(), [](const Row& a, const Row& b) {
      if (a.pts != b.pts) return a.pts > b.pts;
      if (a.gf - a.ga != b.gf - b.ga) return a.gf - a.ga > b.gf - b.ga;
      return a.gf > b.gf;
    });
    out.push_back(std::move(v));
  }
  return out;
}

int32_t Winner(const Game& g) {
  return g.gh > g.ga ? g.home : g.away;
}
int32_t Loser(const Game& g) {
  return g.gh > g.ga ? g.away : g.home;
}

// Первый день: составы 16 сборных, 8 участников (сборная пользователя + сильнейшие), группы змейкой, игры круга.
// Перед турниром: стоковым игрокам сборных bio.team = сборная. У дублей игроков клубов (их создаёт 82B3DFC8 при
// создании франшизы) bio.team — клуб, хотя в его составе их нет: без этого Finish их не вернёт (тест 5: −37 строк
// у 8 участниц), а пул «игроков клубов» получает второго Кросби. Трогаем только тех, кого нет ни в одном составе
// клуба и у кого bio.team — сборная, НХЛ, АХЛ или −1 (сейв 20.10: 325 — своя сборная, 47 — клуб, 3 — −1); юниоры
// CHL в составах не числятся, свободные агенты в турнир не идут — повторный Setup их не заденет.
void AnchorStock(PPCContext& ctx, uint8_t* base, uint32_t f, const std::map<uint32_t, uint32_t>& teams) {
  std::map<int32_t, bool> nation_team, pro_team;
  for (const auto& [id, t] : teams) {
    nation_team[static_cast<int32_t>(t)] = true;
  }
  ForEachRow(ctx, base, f, kTableTeams, 0, 0, [&](auto& get, auto&) {
    const int32_t lg = get(col::kTmLeague);
    if (lg == 0 || lg == 1) {
      pro_team[get(col::kTmIndex)] = true;
    }
  });
  std::map<int32_t, int32_t> stock;  // игрок → сборная
  std::map<int32_t, bool> in_club;
  ForEachRow(ctx, base, f, kTableRoster, 0, 0, [&](auto& get, auto&) {
    const int32_t t = get(col::kRsTeam), pl = get(col::kRsPlayer);
    if (nation_team.count(t)) {
      stock[pl] = t;
    } else {
      in_club[pl] = true;
    }
  });
  int moved = 0;
  ForEachRow(ctx, base, f, kTablePlayerBio, 0, 0, [&](auto& get, auto& put) {
    const int32_t idx = get(col::kBioIndex);
    auto it = stock.find(idx);
    if (it == stock.end() || in_club.count(idx)) {
      return;
    }
    const int32_t team = get(col::kBioTeam);
    if (team != it->second && (team == -1 || nation_team.count(team) || pro_team.count(team))) {
      put(col::kBioTeam, it->second);
      ++moved;
    }
  });
  REXLOG_INFO("[nhllegacy] natcup: stock national players: {} on rosters, {} re-anchored (bio.team)", stock.size(),
              moved);
}

// Стоковым игрокам сборных — контракт со сборной на kStockContractYears лет: со сроком 1 при создании к июльскому
// рынку они становятся свободными агентами (сейв 30.07: 321 из 375 — contractstatus 5, 47 подписали клубы НХЛ).
int ProtectStock(PPCContext& ctx, uint8_t* base, uint32_t f, const std::map<uint32_t, uint32_t>& teams) {
  std::map<int32_t, bool> nation_team;
  for (const auto& [id, t] : teams) {
    nation_team[static_cast<int32_t>(t)] = true;
  }
  int n = 0;
  ForEachRow(ctx, base, f, kTablePlayerBio, 0, 0, [&](auto& get, auto& put) {
    if (!nation_team.count(get(col::kBioTeam))) {
      return;
    }
    if (get(col::kBioContract) != kContractActive) {
      put(col::kBioContract, kContractActive);
    }
    if (get(col::kBioContractLen) < kStockContractYears) {
      put(col::kBioContractLen, kStockContractYears);
    }
    ++n;
  });
  return n;
}

// Создание франшизы: стоковые составы сборных (82B3DFC8) — 375 своих записей, из них 89 — копии игроков клубов
// (та же дата рождения, страна, амплуа, рост и вес; сверено по именам на сейве 20.10 — все 89). Копии удаляем, как
// игра удаляет ушедших игроков; остальным — контракт со сборной, составам — звенья.
void CleanStock(PPCContext& ctx, uint8_t* base, uint32_t f, const std::map<uint32_t, uint32_t>& teams) {
  std::map<int32_t, bool> nation_team;
  for (const auto& [id, t] : teams) {
    nation_team[static_cast<int32_t>(t)] = true;
  }
  std::map<int32_t, bool> stock;
  ForEachRow(ctx, base, f, kTableRoster, 0, 0, [&](auto& get, auto&) {
    if (nation_team.count(get(col::kRsTeam))) {
      stock[get(col::kRsPlayer)] = true;
    }
  });
  std::map<uint64_t, bool> others;
  std::vector<std::pair<int32_t, uint64_t>> stock_keys;
  ForEachRow(ctx, base, f, kTablePlayerBio, 0, 0, [&](auto& get, auto&) {
    uint64_t key = 0;
    for (const uint32_t c : {col::kBioYear, col::kBioMonth, col::kBioDay, col::kBioCountry, col::kBioPosition,
                             col::kBioHeight, col::kBioWeight}) {
      key = key * 256 + static_cast<uint64_t>(get(c) & 0xFF);
    }
    const int32_t idx = get(col::kBioIndex);
    if (stock.count(idx)) {
      stock_keys.push_back({idx, key});
    } else {
      others[key] = true;
    }
  });
  int dups = 0;
  for (const auto& [idx, key] : stock_keys) {
    if (others.count(key)) {
      DeletePlayer(ctx, base, idx);
      ++dups;
    }
  }
  const int protected_n = ProtectStock(ctx, base, f, teams);
  auto players = ReadPlayers(ctx, base, f, teams);
  for (const auto& [id, t] : teams) {
    auto& v = players.stock[t];
    MarkDressed(v);
    WriteRoster(ctx, base, t, v);
  }
  REXLOG_INFO("[nhllegacy] natcup: stock national players: {}, copies of club players deleted {}, contracts {}",
              stock_keys.size(), dups, protected_n);
}

// Звенья команд турнира перед играми дня: если их стёрли (нет g1 ни у кого), — заново по тем же игрокам.
void RepairLines(PPCContext& ctx, uint8_t* base, uint32_t f, const std::map<uint32_t, uint32_t>& teams,
                 const std::map<uint32_t, bool>& playing) {
  std::map<int32_t, std::vector<int32_t>> rows;
  std::map<int32_t, int> g1;
  ForEachRow(ctx, base, f, kTableRoster, 0, 0, [&](auto& get, auto&) {
    const int32_t t = get(col::kRsTeam);
    if (playing.count(static_cast<uint32_t>(t))) {
      rows[t].push_back(get(col::kRsPlayer));
      g1[t] += get(col::kRsG1) ? 1 : 0;
    }
  });
  std::vector<int32_t> bad;
  for (const auto& [t, _] : playing) {
    if (!g1[static_cast<int32_t>(t)]) {
      bad.push_back(static_cast<int32_t>(t));
    }
  }
  if (bad.empty()) {
    return;
  }
  auto players = ReadPlayers(ctx, base, f, teams);
  for (const int32_t t : bad) {
    std::vector<Cand> v;
    for (const int32_t pl : rows[t]) {
      auto it = players.all.find(pl);
      if (it != players.all.end()) {
        v.push_back(it->second);
      }
    }
    MarkDressed(v);
    REXLOG_INFO("[nhllegacy] natcup: team {}: lines were wiped, rewriting", t);
    WriteRoster(ctx, base, static_cast<uint32_t>(t), v);
  }
}

void Setup(PPCContext& ctx, uint8_t* base, uint32_t f, const std::map<uint32_t, uint32_t>& teams) {
  AnchorStock(ctx, base, f, teams);
  auto players = ReadPlayers(ctx, base, f, teams);
  std::vector<Nation> nations;
  for (const uint32_t id : kNations) {
    auto it = teams.find(id);
    if (it == teams.end()) {
      continue;
    }
    Nation nn;
    nn.teamid = id;
    nn.team = it->second;
    nn.roster = PickRoster(players.real[id], players.stock[nn.team]);
    double sum = 0;
    for (const auto& c : nn.roster) {
      sum += c.ovr;
    }
    nn.strength = nn.roster.empty() ? 0 : sum / static_cast<double>(nn.roster.size());
    REXLOG_INFO("[nhllegacy] natcup: nation {} (team {}): club players {}, stock {}, roster {}, strength {:.1f}", id,
                nn.team, players.real[id].size(), players.stock[nn.team].size(), nn.roster.size(), nn.strength);
    nations.push_back(std::move(nn));
  }
  std::vector<Nation*> ok;
  for (auto& n : nations) {
    if (n.roster.size() >= 20) {
      ok.push_back(&n);
    }
  }
  std::sort(ok.begin(), ok.end(), [](Nation* a, Nation* b) { return a->strength > b->strength; });
  if (ok.size() < static_cast<size_t>(kTeams)) {
    REXLOG_INFO("[nhllegacy] natcup: only {} national teams with a full roster - no tournament", ok.size());
    return;
  }
  const int32_t want = REXCVAR_GET(nhl_natcup_nation);
  Nation* user = ok[0];
  for (auto* n : ok) {
    if (static_cast<int32_t>(n->teamid) == want) {
      user = n;
    }
  }
  std::vector<Nation*> field{user};
  for (auto* n : ok) {
    if (n != user && field.size() < static_cast<size_t>(kTeams)) {
      field.push_back(n);
    }
  }
  std::sort(field.begin(), field.end(), [](Nation* a, Nation* b) { return a->strength > b->strength; });
  for (auto* n : field) {
    WriteRoster(ctx, base, n->team, n->roster);
  }
  // змейка: A — 1, 4, 5, 8; B — 2, 3, 6, 7; круг на 4: (0-1, 2-3), (2-0, 3-1), (0-3, 1-2)
  const int ga[4] = {0, 3, 4, 7}, gb[4] = {1, 2, 5, 6};
  const int pairs[3][2][2] = {{{0, 1}, {2, 3}}, {{2, 0}, {3, 1}}, {{0, 3}, {1, 2}}};
  for (const int* g : {ga, gb}) {
    for (int d = 0; d < 3; ++d) {
      for (int k = 0; k < 2; ++k) {
        AddGame(ctx, base, f, kGroupDays[d], field[g[pairs[d][k][0]]]->team, field[g[pairs[d][k][1]]]->team);
      }
    }
  }
  SetUserTeam(ctx, base, user->team, true);
  std::string list;
  for (auto* n : field) {
    list += std::to_string(n->teamid) + "/" + std::to_string(n->team) + " ";
  }
  REXLOG_INFO("[nhllegacy] natcup: tournament set up: user nation {} (team {}), field {}", user->teamid, user->team, list);
}

// 20 августа: сборным — стоковые составы, управление — CPU, игры турнира — status 2 (через год их не видно).
void Finish(PPCContext& ctx, uint8_t* base, uint32_t f, const std::map<uint32_t, uint32_t>& teams,
            const std::vector<Game>& games) {
  std::map<uint32_t, bool> played;
  for (const auto& g : games) {
    played[g.home] = played[g.away] = true;
  }
  // стоковые составы — всем 16 (у не игравших — без тех, кого подписали клубы: тест 7, 8 игроков ушли в АХЛ)
  auto players = ReadPlayers(ctx, base, f, teams);
  for (const auto& [id, t] : teams) {
    auto& stock = players.stock[t];
    MarkDressed(stock);
    WriteRoster(ctx, base, t, stock);
  }
  for (auto& [t, _] : played) {
    SetUserTeam(ctx, base, t, false);
  }
  ProtectStock(ctx, base, f, teams);
  int closed = 0;
  ForEachRow(ctx, base, f, kTableSchedule, kFieldMonth, kAugust, [&](auto& get, auto& put) {
    if (played.count(static_cast<uint32_t>(get(col::kSchHome))) && played.count(static_cast<uint32_t>(get(col::kSchAway)))) {
      put(col::kSchStatus, static_cast<int32_t>(kStatusCancelled));
      ++closed;
    }
  });
  REXLOG_INFO("[nhllegacy] natcup: tournament over: {} national rosters restored ({} played), {} games closed",
              teams.size(), played.size(), closed);
}

void CupDay(PPCContext& ctx, uint8_t* base, uint32_t day0, uint32_t month0) {
  if (month0 != kAugust) {
    return;
  }
  const uint64_t saved_r1 = ctx.r1.u64;
  const uint32_t f = (ctx.r1.u32 - 0x400) & ~0xFu;
  const uint32_t fr = f - 0x200;  // кадр чтения таблиц и вставки игр
  ctx.r1.u64 = f;
  const auto teams = NationTeams(ctx, base, fr);
  const auto games = ReadGames(ctx, base, fr, teams);
  if (games.empty()) {
    if (day0 <= kGroupDays[0]) {
      Setup(ctx, base, fr, teams);
    }
    ctx.r1.u64 = saved_r1;
    return;
  }
  if (day0 >= kLastDay) {
    Finish(ctx, base, fr, teams, games);
    ctx.r1.u64 = saved_r1;
    return;
  }
  if (day0 <= kFinalDay) {
    std::map<uint32_t, bool> playing;
    for (const auto& g : games) {
      playing[g.home] = playing[g.away] = true;
    }
    RepairLines(ctx, base, fr, teams, playing);
  }
  int group_left = 0;
  std::vector<const Game*> semis, finals;
  for (const auto& g : games) {
    if (static_cast<uint32_t>(g.day) < kSemiDay) {
      group_left += g.played ? 0 : 1;
    } else if (static_cast<uint32_t>(g.day) < kFinalDay) {
      semis.push_back(&g);
    } else {
      finals.push_back(&g);
    }
  }
  if (group_left == 0 && semis.empty() && day0 < kSemiDay) {
    auto st = Standings(games);
    if (st.size() == 2 && st[0].size() >= 2 && st[1].size() >= 2) {
      for (int k = 0; k < 2; ++k) {
        std::string t;
        for (const auto& r : st[k]) {
          t += std::to_string(r.team) + " " + std::to_string(r.pts) + "pts " + std::to_string(r.gf) + "-" +
               std::to_string(r.ga) + "; ";
        }
        REXLOG_INFO("[nhllegacy] natcup: group {}: {}", k ? "B" : "A", t);
      }
      AddGame(ctx, base, fr, kSemiDay, st[0][0].team, st[1][1].team);
      AddGame(ctx, base, fr, kSemiDay, st[1][0].team, st[0][1].team);
    } else {
      REXLOG_INFO("[nhllegacy] natcup: group stage over, but {} groups found - no playoffs", st.size());
    }
  } else if (semis.size() == 2 && finals.empty() && semis[0]->played && semis[1]->played && day0 < kFinalDay) {
    AddGame(ctx, base, fr, kFinalDay, Winner(*semis[0]), Winner(*semis[1]));
    AddGame(ctx, base, fr, kFinalDay, Loser(*semis[0]), Loser(*semis[1]));
  } else if (semis.size() == 2 && finals.size() == 2) {
    const int32_t w0 = Winner(*semis[0]), w1 = Winner(*semis[1]);
    for (const Game* g : finals) {
      const bool is_final = (g->home == w0 || g->home == w1) && (g->away == w0 || g->away == w1);
      static int32_t announced[2] = {-1, -1};
      if (g->played && announced[is_final] != g->index) {
        announced[is_final] = g->index;
        REXLOG_INFO("[nhllegacy] natcup: {} team {} ({}-{}{} vs team {})", is_final ? "CHAMPION" : "bronze", Winner(*g),
                    std::max(g->gh, g->ga), std::min(g->gh, g->ga), g->ot ? " OT/SO" : "", Loser(*g));
      }
    }
  }
  ctx.r1.u64 = saved_r1;
}

// Новички драфта: генератор (82B373C8 / 82B37598 → 82B37120 → 82B009D8) делает по 40 на каждую лигу CHL, и на
// QMJHL тоже — с juniorteam = teamid QMJHL (174–191; в этой франшизе там места WHL). Раздаём их в OHL и WHL
// поочерёдно по командам (тест 7: 40 таких в новой франшизе).
bool g_juniors_remapped = false;  // juniorteam юниоров CHL — уже номера франшизы (после 82B099E0)

void FixQmjhlProspects(PPCContext& ctx, uint8_t* base) {
  const uint64_t saved_r1 = ctx.r1.u64;
  const uint32_t f = (ctx.r1.u32 - 0x400) & ~0xFu;
  ctx.r1.u64 = f;
  if (!g_juniors_remapped) {
    // при создании франшизы генератор работает и до пересчёта 82B099E0: juniorteam ещё teamid (OHL 154–173),
    // QMJHL разберёт сам пересчёт (тест 8: 25 юниоров получили teamid QMJHL минус сдвиг OHL/WHL)
    bool exhibition = false;
    ForEachRow(ctx, base, f - 0x200, kTablePlayerBio, kFieldJuniorLeague, 9, [&](auto& get, auto&) {
      exhibition = exhibition || get(kColJuniorTeam) >= 128;
    });
    if (exhibition) {
      ctx.r1.u64 = saved_r1;
      return;
    }
    g_juniors_remapped = true;
  }
  std::vector<int32_t> ohl, whl;
  ForEachRow(ctx, base, f - 0x200, kTableTeams, 0, 0, [&](auto& get, auto&) {
    const int32_t lg = get(col::kTmLeague);
    if (lg == 9 || lg == 11) {
      (lg == 9 ? ohl : whl).push_back(get(col::kTmIndex));
    }
  });
  int n = 0;
  if (!ohl.empty() && !whl.empty()) {
    ForEachRow(ctx, base, f - 0x200, kTablePlayerBio, kFieldJuniorLeague, kQmjhl, [&](auto&, auto& put) {
      const bool to_ohl = n % 2 == 0;
      const auto& v = to_ohl ? ohl : whl;
      put(kColJuniorTeam, v[static_cast<size_t>(n / 2) % v.size()]);  // поле условия — последним (тест 8:
      put(kColJuniorLeague, to_ohl ? 9 : 11);                          // после него вторая запись не проходит)
      ++n;
    });
  }
  ctx.r1.u64 = saved_r1;
  if (n) {
    REXLOG_INFO("[nhllegacy] natcup: {} QMJHL draft prospects moved to OHL/WHL", n);
  }
}

bool NationsLevelOn(PPCContext& ctx, uint8_t* base) {
  return Enabled() && LevelOf(ctx, base, kQmjhl) < 0 && LevelOf(ctx, base, kNationsLeague) >= 0;
}

}  // namespace

// Построитель звеньев движка (82B87538 → 82B7E6E8 → 82B85F40 → 82B57B98) правит объект состава в кэше, а общий
// сброс 82B57B98 пишет его в базу: сборным он оставляет пустые звенья (тесты 4, 6, 7 — «on the ice 0», зависание).
// Звенья сборных пишет модуль — для них сборку и правку объекта пропускаем (L+424 — объект состава, +0 команда;
// L+444 — команда).
namespace {
// Звенья сборной движок не строит (в журнал — первые вызовы с адресом возврата, кто пытался).
bool SkipEngineLines(PPCContext& ctx, uint32_t team, const char* fn) {
  if (!Enabled() || team >= 128 || !g_nation_team[team]) {
    return false;
  }
  static std::atomic<int> logged{0};
  if (logged.fetch_add(1) < 40) {
    REXLOG_INFO("[nhllegacy] natcup: engine lines {} for national team {} skipped (from {:08X})", fn, team,
                static_cast<uint32_t>(ctx.lr));
  }
  return true;
}
}  // namespace

extern "C" void sub_82B7E6E8(PPCContext& ctx, uint8_t* base) {
  const uint32_t obj = Load32(base, ctx.r3.u32 + 424);
  if (SkipEngineLines(ctx, obj ? Load32(base, obj) : 0xFFFFFFFFu, "82B7E6E8")) {
    return;
  }
  __imp__sub_82B7E6E8(ctx, base);
}

extern "C" void sub_82B85F40(PPCContext& ctx, uint8_t* base) {
  if (SkipEngineLines(ctx, Load32(base, ctx.r3.u32 + 444), "82B85F40")) {
    return;
  }
  __imp__sub_82B85F40(ctx, base);
}

// Ручка команды (82B93C58: +0 команда, +4 tag, +16 объект состава): автозвенья ИИ 82B9AAC0 (уборка ушедших
// 82B567B8, смена фазы 82B40810, Матч звёзд 82B445D0…), 82B96838 → 82B94900 + сброс 82B57B98.
extern "C" void sub_82B9AAC0(PPCContext& ctx, uint8_t* base) {
  if (SkipEngineLines(ctx, Load32(base, ctx.r3.u32), "82B9AAC0")) {
    return;
  }
  __imp__sub_82B9AAC0(ctx, base);
}

extern "C" void sub_82B96838(PPCContext& ctx, uint8_t* base) {
  if (SkipEngineLines(ctx, Load32(base, ctx.r3.u32), "82B96838")) {
    return;
  }
  __imp__sub_82B96838(ctx, base);
}

extern "C" void sub_82B94900(PPCContext& ctx, uint8_t* base) {
  if (SkipEngineLines(ctx, Load32(base, ctx.r3.u32), "82B94900")) {
    return;
  }
  __imp__sub_82B94900(ctx, base);
}

extern "C" void sub_82B373C8(PPCContext& ctx, uint8_t* base) {
  __imp__sub_82B373C8(ctx, base);
  const uint64_t r3 = ctx.r3.u64, r4 = ctx.r4.u64;
  if (NationsLevelOn(ctx, base)) {
    FixQmjhlProspects(ctx, base);
  }
  ctx.r3.u64 = r3;
  ctx.r4.u64 = r4;
}

extern "C" void sub_82B37598(PPCContext& ctx, uint8_t* base) {
  __imp__sub_82B37598(ctx, base);
  const uint64_t r3 = ctx.r3.u64, r4 = ctx.r4.u64;
  if (NationsLevelOn(ctx, base)) {
    FixQmjhlProspects(ctx, base);
  }
  ctx.r3.u64 = r3;
  ctx.r4.u64 = r4;
}

// 82B099E0(создание) — juniorteam юниоров CHL в номера франшизы. Оригинал вычитает у всех (juniorleague 9, 10, 11)
// сдвиг OHL 82975B50(9) — верно, только пока OHL, QMJHL и WHL идут подряд. Без QMJHL (лига сборных на её уровне):
// OHL и WHL — каждый своим сдвигом 82975B50(лига), юниоры QMJHL — поочерёдно в команды OHL и WHL. Затем — чистка
// стоковых составов сборных (CleanStock: копии игроков клубов удаляются, остальным — контракт со сборной).
extern "C" void sub_82B099E0(PPCContext& ctx, uint8_t* base) {
  const uint64_t arg = ctx.r3.u64;  // LevelOf портит r3
  if (!Enabled() || LevelOf(ctx, base, kQmjhl) >= 0 || LevelOf(ctx, base, kNationsLeague) < 0) {
    ctx.r3.u64 = arg;
    __imp__sub_82B099E0(ctx, base);
    return;
  }
  const uint32_t self = static_cast<uint32_t>(arg);
  const uint64_t saved_r1 = ctx.r1.u64;
  const uint32_t f = (ctx.r1.u32 - 0x300) & ~0xFu;  // кадр как у оригинала: f+80…f+175
  std::memset(Host(base, f), 0, 0x300);
  ctx.r1.u64 = f;
  std::vector<int32_t> ohl_teams, whl_teams;  // номера франшизы команд OHL и WHL — юниорам QMJHL
  ForEachRow(ctx, base, f - 0x200, kTableTeams, 0, 0, [&](auto& get, auto&) {
    const int32_t lg = get(col::kTmLeague);
    if (lg == 9 || lg == 11) {
      (lg == 9 ? ohl_teams : whl_teams).push_back(get(col::kTmIndex));
    }
  });
  sub_8289F5B0(ctx, base);
  const uint32_t mgr = ctx.r3.u32;
  ctx.r3.u64 = Load32(base, self + 48);
  sub_82974FA0(ctx, base);
  int counts[3] = {0, 0, 0};
  if ((ctx.r3.u32 & 0xFFu) != 0) {
    ctx.r3.u64 = mgr;
    rex::runtime::ResolveIndirectFunction(Load32(base, Load32(base, mgr) + 28))(ctx, base);  // vtable +28
    sub_82A07D88(ctx, base);
    const uint32_t db = ctx.r3.u32;
    const uint32_t table = TableIndex(ctx, base, db, kTablePlayerBio);
    // juniorleague ∈ {9, 10, 11}
    uint32_t pred[3];
    const uint32_t slot[3] = {f + 160, f + 128, f + 96};
    for (int k = 0; k < 3; ++k) {
      ctx.r3.u64 = slot[k];
      ctx.r4.u64 = kFieldJuniorLeague;
      sub_827B10C8(ctx, base);
      ctx.r4.u64 = static_cast<uint64_t>(11 - k);
      sub_827B1588(ctx, base);
      pred[k] = ctx.r3.u32;
    }
    ctx.r3.u64 = pred[2];
    ctx.r4.u64 = pred[1];
    sub_827B2418(ctx, base);
    ctx.r4.u64 = pred[0];
    sub_827B2418(ctx, base);
    const uint32_t where = ctx.r3.u32;
    sub_82A07D88(ctx, base);
    ctx.r4.u64 = ctx.r3.u64;
    ctx.r3.u64 = f + 84;
    sub_827B7D08(ctx, base);
    ctx.r4.u64 = ctx.r3.u64;
    ctx.r3.u64 = f + 80;
    ctx.r5.u64 = kTablePlayerBio;
    sub_827B4818(ctx, base);
    ctx.r4.u64 = where;
    ctx.r5.u64 = 1;
    sub_827B4A48(ctx, base);
    sub_827B5568(ctx, base);
    const uint32_t cur = ctx.r3.u32;
    ctx.r3.u64 = f + 80;
    sub_833FBEA0(ctx, base);
    ctx.r3.u64 = f + 84;
    sub_833FBEA0(ctx, base);
    for (const uint32_t o : {f + 96, f + 128, f + 160}) {
      ctx.r3.u64 = o;
      sub_827B11E0(ctx, base);
    }
    ctx.r3.u64 = cur;
    sub_827B2E10(ctx, base);
    const int32_t n = static_cast<int32_t>(ctx.r3.u32 & 0xFFFFu);
    if (n > 0) {
      ctx.r3.u64 = 9;
      sub_82975B50(ctx, base);
      const int32_t off_ohl = ctx.r3.s32;
      ctx.r3.u64 = 11;
      sub_82975B50(ctx, base);
      const int32_t off_whl = ctx.r3.s32;
      ctx.r3.u64 = kJuniorLock;
      __imp__RtlEnterCriticalSection(ctx, base);
      auto get = [&](uint32_t col) {
        ctx.r3.u64 = cur;
        ctx.r4.u64 = table;
        ctx.r5.u64 = col;
        ctx.r6.u64 = 1;
        ctx.r7.u64 = f + 88;
        ctx.r8.u64 = 0;
        sub_827B3008(ctx, base);
        return static_cast<int32_t>(Load32(base, f + 88));
      };
      auto put = [&](uint32_t col, int32_t v) {
        Store32(base, f + 92, static_cast<uint32_t>(v));
        ctx.r3.u64 = cur;
        ctx.r4.u64 = table;
        ctx.r5.u64 = col;
        ctx.r6.u64 = 1;
        ctx.r7.u64 = f + 92;
        ctx.r8.u64 = 0;
        sub_827B3030(ctx, base);
      };
      for (int32_t i = 0; i < n; ++i) {
        const int32_t league = get(kColJuniorLeague);
        const int32_t team = get(kColJuniorTeam);
        if (league == 9) {
          put(kColJuniorTeam, team - off_ohl);
          ++counts[0];
        } else if (league == 11) {
          put(kColJuniorTeam, team - off_whl);
          ++counts[2];
        } else {
          // QMJHL нет — в OHL и WHL поочерёдно (поле условия — последним)
          const bool to_ohl = counts[1] % 2 == 0;
          const auto& v = to_ohl ? ohl_teams : whl_teams;
          put(kColJuniorTeam, v.empty() ? -1 : v[static_cast<size_t>(counts[1] / 2) % v.size()]);
          put(kColJuniorLeague, v.empty() ? 0 : (to_ohl ? 9 : 11));
          ++counts[1];
        }
        ctx.r3.u64 = cur;
        ctx.r4.u64 = 1;
        ctx.r5.u64 = 1;
        sub_827B2D08(ctx, base);
      }
      ctx.r3.u64 = kJuniorLock;
      __imp__RtlLeaveCriticalSection(ctx, base);
      REXLOG_INFO("[nhllegacy] natcup: junior teams: OHL {} (offset {}), WHL {} (offset {}), QMJHL {} -> OHL/WHL",
                  counts[0], off_ohl, counts[2], off_whl, counts[1]);
    }
    ctx.r3.u64 = cur;
    sub_827B2C40(ctx, base);
  }
  // стоковые составы сборных (82B3DFC8) остаются до турнира, без копий игроков клубов и с контрактами
  const auto teams = NationTeams(ctx, base, f - 0x200);
  REXLOG_INFO("[nhllegacy] natcup: national teams in the franchise: {}", teams.size());
  CleanStock(ctx, base, f - 0x200, teams);
  g_juniors_remapped = true;
  ctx.r1.u64 = saved_r1;
}

// 829DA768(настройки создателя, уровень, лига) — добавить уровень лиги франшизы; QMJHL → сборные (только Be a GM).
// Список команд лиги 8 сборщик 829CCA18 оставляет пустым (прогон 20.10: «0 -> 0 teams», франшиза без уровня) —
// списки уровня (+6040 и +3136, шаг 484: +0 число, +4+4i teamid, +244+4i флаг: 1 — CPU) пишем сами.
extern "C" void sub_829DA768(PPCContext& ctx, uint8_t* base) {
  const uint32_t self = ctx.r3.u32;
  const uint32_t level = ctx.r4.u32;
  if (!Enabled() || ctx.r5.s32 != kQmjhl || Load32(base, self + 3124) != kModeBeAGm) {
    __imp__sub_829DA768(ctx, base);
    return;
  }
  ctx.r5.s64 = kNationsLeague;
  __imp__sub_829DA768(ctx, base);
  const uint64_t ret = ctx.r3.u64;
  for (const uint32_t list : {self + 6040 + 484 * level, self + 3136 + 484 * level}) {
    const uint32_t n = Load32(base, list);
    uint32_t i = 0;
    for (const uint32_t id : kNations) {
      Store32(base, list + 4 + 4 * i, id);
      Store32(base, list + 244 + 4 * i, 1);
      ++i;
    }
    Store32(base, list, i);
    REXLOG_INFO("[nhllegacy] natcup: league level {}: QMJHL (10) -> national teams (8), list +{}: {} -> {} teams", level,
                list - self, n, i);
  }
  ctx.r3.u64 = ret;
}

// 82B3BDC8(уровень лиги, сезон) — сезонные задачи уровня; после них — своя задача в августе (только верхний уровень).
extern "C" void sub_82B3BDC8(PPCContext& ctx, uint8_t* base) {
  const uint32_t level = ctx.r3.u32;
  const uint32_t season = ctx.r4.u32;
  const uint64_t saved_r1 = ctx.r1.u64;
  __imp__sub_82B3BDC8(ctx, base);
  if (!Enabled() || !level || !season) {
    return;
  }
  const uint64_t ret = ctx.r3.u64;
  const uint32_t lg = Load32(base, level + 4);
  const uint32_t sub = Load32(base, level + 8);
  ctx.r3.u64 = lg;
  ctx.r4.u64 = sub;
  sub_82975FA0(ctx, base);
  const uint32_t tier = ctx.r3.u32;
  const uint32_t s0 = Load32(base, season + 16);
  const uint32_t s1 = Load32(base, season + 20);
  const Ymd a = ToYmd(s0), b = ToYmd(s1);
  REXLOG_INFO("[nhllegacy] natcup: season tasks league {} sub {} tier {}: {} ({:04}-{:02}-{:02}) .. {} ({:04}-{:02}-{:02})",
              lg, sub, tier, s0, a.y, a.m, a.d, s1, b.y, b.m, b.d);
  if (tier == 0) {
    const uint32_t t0 = ToSerial(b.y, 8, 1);
    const uint32_t t1 = ToSerial(b.y, 8, 20);
    if (t0 > s0 && t1 < s1) {
      // даты задачи — во временной области гостевого стека ниже текущего кадра
      const uint32_t frame = (ctx.r1.u32 - 0x100) & ~0xFu;
      std::memset(Host(base, frame), 0, 0x100);
      Store32(base, frame + 0x40, t0);
      Store32(base, frame + 0x44, t1);
      ctx.r1.u64 = frame;
      ctx.r3.u64 = 0;
      ctx.r4.u64 = frame + 0x40;
      ctx.r5.u64 = frame + 0x44;
      ctx.r6.u64 = kTaskType;
      ctx.r7.u64 = lg;
      ctx.r8.u64 = sub;
      sub_82AF5DB0(ctx, base);
      ctx.r1.u64 = saved_r1;
      REXLOG_INFO("[nhllegacy] natcup: task {} set {} .. {} ({:04}-08-01 .. {:04}-08-20)", kTaskType, t0, t1, b.y, b.y);
    } else {
      REXLOG_INFO("[nhllegacy] natcup: August {} outside the season, no task", b.y);
    }
  }
  ctx.r3.u64 = ret;
}

// 82B4BBC0(лига, тип, уровень, под-лига, &дата) — диспетчер задач; свой тип — день Кубка наций (CupDay).
extern "C" void sub_82B4BBC0(PPCContext& ctx, uint8_t* base) {
  if (Enabled() && ctx.r4.u32 == kTaskType) {
    const uint32_t day = ctx.r7.u32 ? Load32(base, ctx.r7.u32) : 0;
    const Ymd t = ToYmd(day);
    REXLOG_INFO("[nhllegacy] natcup: task day {} ({:04}-{:02}-{:02}), tier {} sub {}", day, t.y, t.m, t.d, ctx.r5.u32,
                ctx.r6.u32);
    if (LevelOf(ctx, base, kNationsLeague) >= 0) {
      CupDay(ctx, base, t.d - 1, t.m - 1);
    }
    ctx.r3.u64 = 1;
    return;
  }
  __imp__sub_82B4BBC0(ctx, base);
}
