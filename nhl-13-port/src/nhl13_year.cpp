// Сдвиг «текущего года»: врезки [[midasm_hook]] из nhl13_year_hooks.toml
// (генерирует tools/year_hooks.py, разбор мест — docs/year-and-date.md).
//
// NHL 13 считает «сейчас» от зашитого 2012 (сезон 2012/13): дата «Играть сейчас»,
// год новой франшизы, номер сезона = год − 2012, возраст проспектов 2012 − 18 и т. д.
// Врезки сдвигают все эти константы на season_year − 2012, так что игра целиком
// «переезжает» в выбранный сезон; 2012 — как в оригинале. Год намеренно не берётся
// по часам: франшиза хранит год лиги, и с другим season_year её номера сезонов
// поедут — сейв франшизы грузить с тем же season_year, с которым она создана.

#include <algorithm>
#include <cstdint>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ppc.h>

REXCVAR_DEFINE_INT32(season_year, 2012, "NHL13",
                     "First year of the current season (2026 = 2026/27), 2012 = original")
    .range(1990, 2050)
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

namespace {

constexpr int32_t kGameYear = 2012;  // год, зашитый в игру

int32_t YearDelta() {
  static const int32_t delta = [] {
    // Франшиза идёт до 25 сезонов, а MakeDate игры режет года после 2077.
    int32_t year = std::clamp(REXCVAR_GET(season_year), 1990, 2050);
    REXLOG_INFO("[nhl13] season {}/{:02} (season_year = {}), year shift {:+}", year,
                (year + 1) % 100, REXCVAR_GET(season_year), year - kGameYear);
    return year - kGameYear;
  }();
  return delta;
}

template <typename T>
void Compare(PPCCRRegister& cr, T left, T right) {
  // Пересчёт поля CR после cmpwi/cmplwi с годом; бит so остаётся от исходного сравнения.
  cr.lt = left < right;
  cr.gt = left > right;
  cr.eq = left == right;
}

}  // namespace

// li / subfic rD, …, Y и addi rD, rA, +Y: результат на delta больше.
void Nhl13YearAdd(PPCRegister& r) {
  r.s64 += YearDelta();
}

// addi rD, rA, −Y (год → номер сезона): результат на delta меньше.
void Nhl13YearSub(PPCRegister& r) {
  r.s64 -= YearDelta();
}

#define NHL13_YEAR_CMP(Y)                                                       \
  void Nhl13YearCmpS##Y(PPCRegister& a, PPCCRRegister& cr) {                    \
    Compare<int32_t>(cr, a.s32, Y + YearDelta());                               \
  }                                                                             \
  void Nhl13YearCmpU##Y(PPCRegister& a, PPCCRRegister& cr) {                    \
    Compare<uint32_t>(cr, a.u32, static_cast<uint32_t>(Y + YearDelta()));       \
  }

NHL13_YEAR_CMP(1962)
NHL13_YEAR_CMP(2004)
NHL13_YEAR_CMP(2011)
NHL13_YEAR_CMP(2012)
