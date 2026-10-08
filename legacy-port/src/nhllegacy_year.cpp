// Сдвиг «текущего года» NHL Legacy: врезки [[midasm_hook]] из nhllegacy_year_hooks.toml
// (генерирует tools/year_hooks.py --game legacy; разбор мест — docs/legacy-port.md, по образцу
// NHL 13 — docs/year-and-date.md).
//
// NHL Legacy считает «сейчас» от зашитого 2015 (сезон 2015/16): дата «Играть сейчас», год новой
// франшизы, номер сезона = год − 2015, возраст проспектов 2015 − 18 и т. д. Врезки сдвигают все эти
// константы на season_year − 2015, так что игра целиком «переезжает» в выбранный сезон; 2015 — как
// в оригинале. Год намеренно не берётся по часам: франшиза хранит год лиги, и с другим
// season_year её номера сезонов поедут — сейв франшизы грузить с тем же season_year, с которым
// она создана.

#include <algorithm>
#include <cstdint>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ppc.h>

REXCVAR_DEFINE_INT32(season_year, 2015, "NHLLegacy",
                     "First year of the current season (2026 = 2026/27), 2015 = original")
    .range(1990, 2050)
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

namespace {

constexpr int32_t kGameYear = 2015;  // год, зашитый в игру

int32_t YearDelta() {
  static const int32_t delta = [] {
    // Франшиза идёт до 25 сезонов, а MakeDate игры режет года после 2077.
    int32_t year = std::clamp(REXCVAR_GET(season_year), 1990, 2050);
    REXLOG_INFO("[nhllegacy] season {}/{:02} (season_year = {}), year shift {:+}", year,
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
void NhlLegacyYearAdd(PPCRegister& r) {
  r.s64 += YearDelta();
}

// addi rD, rA, −Y (год → номер сезона): результат на delta меньше.
void NhlLegacyYearSub(PPCRegister& r) {
  r.s64 -= YearDelta();
}

#define NHLLEGACY_YEAR_CMP(Y)                                                   \
  void NhlLegacyYearCmpS##Y(PPCRegister& a, PPCCRRegister& cr) {                \
    Compare<int32_t>(cr, a.s32, Y + YearDelta());                               \
  }                                                                             \
  void NhlLegacyYearCmpU##Y(PPCRegister& a, PPCCRRegister& cr) {                \
    Compare<uint32_t>(cr, a.u32, static_cast<uint32_t>(Y + YearDelta()));       \
  }

// Года сравнений из nhllegacy_year_hooks.toml: 1965 = 2015 − 50 (год рождения), 2004 («недавний
// драфт», в Legacy не пересчитан с NHL 13), 2014, 2015.
NHLLEGACY_YEAR_CMP(1965)
NHLLEGACY_YEAR_CMP(2004)
NHLLEGACY_YEAR_CMP(2014)
NHLLEGACY_YEAR_CMP(2015)
