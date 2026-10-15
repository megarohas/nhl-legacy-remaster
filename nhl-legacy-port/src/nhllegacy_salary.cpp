// Финансы франшизы NHL Legacy под сезон season_year: потолок зарплат, нижний порог и минимальная
// зарплата первого сезона (docs/legacy-port.md, «Потолок зарплат»).
//
// Legacy берёт финансы не из базы, а из таблицы настроек (объект r3, строки по годам):
//  - 82BBCAE8(obj, col, years): col 0 — нижний порог, col 1 — потолок; база × 100 000 + годовые
//    прибавки × 1000 за годы 0…years (обёртки 82BBCB98 — порог, 82BBCBA8 — потолок, 82BBCC58 —
//    потолок / 5, наибольший контракт);
//  - 82BBCBB8(obj, col, years): значение года × 1000, col 3 — минимальная зарплата (обёртка 82BBCC48),
//    col 4 — наибольшая зарплата новичка (82BBCC38).
// Новая франшиза (82B5FAD8) считает их с years = 0 — 52,8 млн / 71,4 млн / 575 тыс., сезон 2015/16 —
// и кладёт в 0x83A15268 (порог, потолок) и leaguestates 15/18/19; новый сезон (82B6DF90 → 82B50388) —
// с years = номер сезона, и потолок не ниже «потолок + перерасход самой дорогой команды» (не выше
// 204,775 млн). Выключатель «Потолок зарплат» в настройках франшизы — байт 0x83A14D82: при 0 геттер
// 82B4F7A0 отдаёт порог 0 и потолок 1 млрд.
//
// Подмена: значение = заданное на первый сезон + (значение игры за years − значение игры за 0), то есть
// первый сезон — наш, годовой рост — как в игре. cvar 0 — значение игры (сезон 2015/16). В NHL 13 этого
// нет (открытый вопрос, docs/legacy-port.md).

#include <cstdint>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ppc.h>

REXCVAR_DEFINE_INT32(nhl_salary_cap, 0, "NHLLegacy",
                     "Franchise salary cap of the first season, $ (0 = game: 71400000, 2015/16)")
    .range(0, 200000000)
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

REXCVAR_DEFINE_INT32(nhl_salary_floor, 0, "NHLLegacy",
                     "Franchise payroll floor of the first season, $ (0 = game: 52800000)")
    .range(0, 200000000)
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

REXCVAR_DEFINE_INT32(nhl_salary_min, 0, "NHLLegacy",
                     "Franchise league minimum salary of the first season, $ (0 = game: 575000)")
    .range(0, 10000000)
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

extern "C" void __imp__sub_82BBCAE8(PPCContext& ctx, uint8_t* base);  // порог / потолок за years
extern "C" void __imp__sub_82BBCBB8(PPCContext& ctx, uint8_t* base);  // значение года (col 3, 4)

namespace {

using GuestFn = void (*)(PPCContext&, uint8_t*);

int32_t Target(uint32_t col, bool cumulative) {
  if (cumulative) {
    if (col == 0) {
      return REXCVAR_GET(nhl_salary_floor);
    }
    if (col == 1) {
      return REXCVAR_GET(nhl_salary_cap);
    }
    return 0;
  }
  return col == 3 ? REXCVAR_GET(nhl_salary_min) : 0;
}

uint32_t Call(GuestFn fn, PPCContext& ctx, uint8_t* base, uint32_t obj, uint32_t col, int32_t years) {
  ctx.r3.u64 = obj;
  ctx.r4.u64 = col;
  ctx.r5.s64 = years;
  fn(ctx, base);
  return ctx.r3.u32;
}

void Shift(GuestFn fn, bool cumulative, PPCContext& ctx, uint8_t* base) {
  const uint32_t obj = ctx.r3.u32;
  const uint32_t col = ctx.r4.u32;
  const int32_t years = ctx.r5.s32;
  const int32_t target = Target(col, cumulative);
  if (target <= 0) {
    fn(ctx, base);
    return;
  }
  const uint32_t at0 = Call(fn, ctx, base, obj, col, 0);
  const uint32_t at = years == 0 ? at0 : Call(fn, ctx, base, obj, col, years);
  const int64_t value = int64_t(target) + int64_t(at) - int64_t(at0);
  ctx.r3.u64 = static_cast<uint32_t>(value > 0 ? value : 0);
  static int logged[5] = {};
  if (col < 5 && logged[col]++ < 3) {
    REXLOG_INFO("[nhllegacy] salary col {} years {}: game {} -> {}", col, years, at, ctx.r3.u32);
  }
}

}  // namespace

extern "C" void sub_82BBCAE8(PPCContext& ctx, uint8_t* base) {
  Shift(__imp__sub_82BBCAE8, true, ctx, base);
}

extern "C" void sub_82BBCBB8(PPCContext& ctx, uint8_t* base) {
  Shift(__imp__sub_82BBCBB8, false, ctx, base);
}
