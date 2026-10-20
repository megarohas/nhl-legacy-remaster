// Кубок наций во франшизе NHL Legacy — эксперимент (ветка nations-cup, docs/nations-cup.md, cvar nhl_natcup).
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

namespace {

constexpr uint32_t kTaskType = 1;

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

// Дни ↔ дата (григорианский календарь, отсчёт как у leaguetasks: 30.12.1899 = 0; у движка, похоже, на день
// иначе — для своей задачи важна только разность с датами сезона, она от эпохи не зависит).
int64_t DaysFromCivil(int64_t y, unsigned m, unsigned d) {
  y -= m <= 2;
  const int64_t era = (y >= 0 ? y : y - 399) / 400;
  const unsigned yoe = static_cast<unsigned>(y - era * 400);
  const unsigned doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
  const unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
  return era * 146097 + static_cast<int64_t>(doe) - 719468;
}
const int64_t kEpoch = DaysFromCivil(1899, 12, 30);

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

}  // namespace

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
