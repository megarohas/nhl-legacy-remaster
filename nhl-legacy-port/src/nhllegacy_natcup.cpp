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

#include <cstdint>
#include <cstring>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ppc.h>

REXCVAR_DEFINE_BOOL(nhl_natcup, false, "NHLLegacy",
                    "Nations Cup experiment: an August franchise calendar task (logged for now)")
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
extern "C" void sub_82AE9DD8(PPCContext& ctx, uint8_t* base);         // итератор команд: создать
extern "C" void sub_82AE9E28(PPCContext& ctx, uint8_t* base);         // итератор команд: удалить
extern "C" void sub_82AF6570(PPCContext& ctx, uint8_t* base);         // сведения о команде франшизы (+8 teamid)
extern "C" void sub_82A1BB18(PPCContext& ctx, uint8_t* base);         // удалить состав команды
extern "C" void __imp__RtlEnterCriticalSection(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__RtlLeaveCriticalSection(PPCContext& ctx, uint8_t* base);

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

// teamid (байт +8 сведений) команды франшизы номер n.
uint32_t TeamIdOf(PPCContext& ctx, uint8_t* base, uint32_t n) {
  const uint64_t saved_r1 = ctx.r1.u64;
  const uint32_t iter = (ctx.r1.u32 - 0x200) & ~0xFu;
  const uint32_t info = iter + 0x20;
  std::memset(Host(base, iter), 0, 0x140);
  ctx.r1.u64 = iter - 0x80;
  ctx.r3.u64 = iter;
  sub_82AE9DD8(ctx, base);
  ctx.r3.u64 = iter;
  ctx.r4.u64 = n;
  ctx.r5.u64 = info;
  sub_82AF6570(ctx, base);
  const uint32_t id = *Host(base, info + 8);
  ctx.r3.u64 = iter;
  sub_82AE9E28(ctx, base);
  ctx.r1.u64 = saved_r1;
  return id;
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
// курсора — 827B3008/827B3030(курсор, номер таблицы, номер поля, 1, &значение, 0); номер поля — место поля среди полей
// таблицы по возрастанию хеша имени (juniorteam = 11, как у оригинала; juniorleague = 6), номер таблицы — по
// дескриптору 827B5D40(база+8, хеш таблицы).
constexpr uint32_t kTablePlayerBio = 0xF97F5A5Au;     // leagueplayerbiotable
constexpr uint32_t kFieldJuniorLeague = 0x1A86215Au;  // juniorleague (для условия запроса)
constexpr uint32_t kColJuniorTeam = 11;
constexpr uint32_t kColJuniorLeague = 6;
constexpr uint32_t kJuniorLock = 0x83DA3A00u;         // критическая секция цикла (как у оригинала)

uint32_t TableIndex(PPCContext& ctx, uint8_t* base, uint32_t db, uint32_t hash) {
  ctx.r3.u64 = Load32(base, db + 8);
  ctx.r4.u64 = hash;
  sub_827B5D40(ctx, base);
  const uint32_t desc = ctx.r3.u32;
  return (desc - Load32(base, Load32(base, desc + 4) + 28)) / 68;
}

}  // namespace

// 82B099E0(создание) — juniorteam юниоров CHL в номера франшизы. Оригинал вычитает у всех (juniorleague 9, 10, 11)
// сдвиг OHL 82975B50(9) — верно, только пока OHL, QMJHL и WHL идут подряд. Без QMJHL (лига сборных на её уровне):
// OHL и WHL — каждый своим сдвигом 82975B50(лига), юниоры QMJHL — без юниорского клуба (juniorleague 0, juniorteam
// −1, как у прочих). Затем — пустые составы сборных: при создании им пишутся стоковые (дубли игроков клубов), до
// 1 августа они не нужны.
extern "C" void sub_82B099E0(PPCContext& ctx, uint8_t* base) {
  if (!Enabled() || LevelOf(ctx, base, kQmjhl) >= 0 || LevelOf(ctx, base, kNationsLeague) < 0) {
    __imp__sub_82B099E0(ctx, base);
    return;
  }
  const uint32_t self = ctx.r3.u32;
  const uint64_t saved_r1 = ctx.r1.u64;
  const uint32_t f = (ctx.r1.u32 - 0x300) & ~0xFu;  // кадр как у оригинала: f+80…f+175
  std::memset(Host(base, f), 0, 0x300);
  ctx.r1.u64 = f;
  sub_8289F5B0(ctx, base);
  const uint32_t mgr = ctx.r3.u32;
  ctx.r3.u64 = Load32(base, self + 48);
  sub_82974FA0(ctx, base);
  int counts[4] = {0, 0, 0, 0};
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
          put(kColJuniorTeam, -1);
          put(kColJuniorLeague, 0);
          ++counts[1];
        }
        ctx.r3.u64 = cur;
        ctx.r4.u64 = 1;
        ctx.r5.u64 = 1;
        sub_827B2D08(ctx, base);
      }
      ctx.r3.u64 = kJuniorLock;
      __imp__RtlLeaveCriticalSection(ctx, base);
      REXLOG_INFO("[nhllegacy] natcup: junior teams: OHL {} (offset {}), WHL {} (offset {}), QMJHL {} -> no junior team",
                  counts[0], off_ohl, counts[2], off_whl, counts[1]);
    }
    ctx.r3.u64 = cur;
    sub_827B2C40(ctx, base);
  }
  // составы сборных — пустые до турнира
  for (uint32_t t = 0; t < 126; ++t) {
    if (IsNation(TeamIdOf(ctx, base, t))) {
      ctx.r3.u64 = 0;
      ctx.r4.u64 = t;
      sub_82A1BB18(ctx, base);
      ++counts[3];
    }
  }
  REXLOG_INFO("[nhllegacy] natcup: national teams in the franchise: {}, stock rosters cleared", counts[3]);
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

// 82B4BBC0(лига, тип, уровень, под-лига, &дата) — диспетчер задач; свой тип — только в лог (шаг 1).
extern "C" void sub_82B4BBC0(PPCContext& ctx, uint8_t* base) {
  if (Enabled() && ctx.r4.u32 == kTaskType) {
    const uint32_t day = ctx.r7.u32 ? Load32(base, ctx.r7.u32) : 0;
    const Ymd t = ToYmd(day);
    REXLOG_INFO("[nhllegacy] natcup: task day {} ({:04}-{:02}-{:02}), tier {} sub {}", day, t.y, t.m, t.d, ctx.r5.u32,
                ctx.r6.u32);
    ctx.r3.u64 = 1;
    return;
  }
  __imp__sub_82B4BBC0(ctx, base);
}
