// Сгенерировано tools/team_hooks.py — не править руками.
// Врезки «30 команд НХЛ → 32» (legacy-port/nhllegacy_team_sites.toml); действуют при nhl_teams = 32.
// Варианты ahl32 (nhl_ahl_teams = 32, только вместе с nhl_teams = 32) — docs/ahl32.md.

#include <cstdint>

#include <rex/ppc.h>

bool NhlLegacyThirtyTwo();
bool NhlLegacyAhl32();
bool NhlLegacyStandingsWide(PPCRegister& r);

void NhlLegacyAdd_m2(PPCRegister& d) {
  if (NhlLegacyThirtyTwo()) {
    d.s64 += -2;
  }
}

void NhlLegacyAdd_p16(PPCRegister& d) {
  if (NhlLegacyThirtyTwo()) {
    d.s64 += 16;
  }
}

void NhlLegacyAdd_p2(PPCRegister& d) {
  if (NhlLegacyThirtyTwo()) {
    d.s64 += 2;
  }
}

void NhlLegacyCmpS_16(PPCRegister& a, PPCCRRegister& cr) {
  if (NhlLegacyThirtyTwo()) {
    const int32_t v = a.s32, n = 16;
    cr.lt = v < n;
    cr.gt = v > n;
    cr.eq = v == n;
  }
}

void NhlLegacyCmpS_31(PPCRegister& a, PPCCRRegister& cr) {
  if (NhlLegacyThirtyTwo()) {
    const int32_t v = a.s32, n = 31;
    cr.lt = v < n;
    cr.gt = v > n;
    cr.eq = v == n;
  }
}

void NhlLegacyCmpS_32(PPCRegister& a, PPCCRRegister& cr) {
  if (NhlLegacyThirtyTwo()) {
    const int32_t v = a.s32, n = 32;
    cr.lt = v < n;
    cr.gt = v > n;
    cr.eq = v == n;
  }
}

void NhlLegacyCmpS_576_StandingsWide(PPCRegister& a, PPCCRRegister& cr, PPCRegister& g) {
  if (NhlLegacyStandingsWide(g)) {
    const int32_t v = a.s32, n = 576;
    cr.lt = v < n;
    cr.gt = v > n;
    cr.eq = v == n;
  }
}

void NhlLegacyCmpS_62_a64(PPCRegister& a, PPCCRRegister& cr) {
  int32_t n;
  if (NhlLegacyAhl32()) {
    n = 64;
  } else if (NhlLegacyThirtyTwo()) {
    n = 62;
  } else {
    return;
  }
  const int32_t v = a.s32;
  cr.lt = v < n;
  cr.gt = v > n;
  cr.eq = v == n;
}

void NhlLegacyCmpS_a32(PPCRegister& a, PPCCRRegister& cr) {
  int32_t n;
  if (NhlLegacyAhl32()) {
    n = 32;
  } else {
    return;
  }
  const int32_t v = a.s32;
  cr.lt = v < n;
  cr.gt = v > n;
  cr.eq = v == n;
}

void NhlLegacyCmpU_32(PPCRegister& a, PPCCRRegister& cr) {
  if (NhlLegacyThirtyTwo()) {
    const uint32_t v = a.u32, n = 32;
    cr.lt = v < n;
    cr.gt = v > n;
    cr.eq = v == n;
  }
}

void NhlLegacyLi_128(PPCRegister& d) {
  if (NhlLegacyThirtyTwo()) {
    d.s64 = 128;
  }
}

void NhlLegacyLi_140(PPCRegister& d) {
  if (NhlLegacyThirtyTwo()) {
    d.s64 = 140;
  }
}

void NhlLegacyLi_16(PPCRegister& d) {
  if (NhlLegacyThirtyTwo()) {
    d.s64 = 16;
  }
}

void NhlLegacyLi_16_StandingsWide(PPCRegister& d, PPCRegister& g) {
  if (NhlLegacyStandingsWide(g)) {
    d.s64 = 16;
  }
}

void NhlLegacyLi_17_StandingsWide(PPCRegister& d, PPCRegister& g) {
  if (NhlLegacyStandingsWide(g)) {
    d.s64 = 17;
  }
}

void NhlLegacyLi_18_StandingsWide(PPCRegister& d, PPCRegister& g) {
  if (NhlLegacyStandingsWide(g)) {
    d.s64 = 18;
  }
}

void NhlLegacyLi_224(PPCRegister& d) {
  if (NhlLegacyThirtyTwo()) {
    d.s64 = 224;
  }
}

void NhlLegacyLi_248_a256(PPCRegister& d) {
  int64_t n;
  if (NhlLegacyAhl32()) {
    n = 256;
  } else if (NhlLegacyThirtyTwo()) {
    n = 248;
  } else {
    return;
  }
  d.s64 = n;
}

void NhlLegacyLi_31(PPCRegister& d) {
  if (NhlLegacyThirtyTwo()) {
    d.s64 = 31;
  }
}

void NhlLegacyLi_32(PPCRegister& d) {
  if (NhlLegacyThirtyTwo()) {
    d.s64 = 32;
  }
}

void NhlLegacyLi_384(PPCRegister& d) {
  if (NhlLegacyThirtyTwo()) {
    d.s64 = 384;
  }
}

void NhlLegacyLi_384_StandingsWide(PPCRegister& d, PPCRegister& g) {
  if (NhlLegacyStandingsWide(g)) {
    d.s64 = 384;
  }
}

void NhlLegacyLi_62_a64(PPCRegister& d) {
  int64_t n;
  if (NhlLegacyAhl32()) {
    n = 64;
  } else if (NhlLegacyThirtyTwo()) {
    n = 62;
  } else {
    return;
  }
  d.s64 = n;
}

void NhlLegacyLi_64(PPCRegister& d) {
  if (NhlLegacyThirtyTwo()) {
    d.s64 = 64;
  }
}

void NhlLegacyMulSame_30_32(PPCRegister& d) {
  if (NhlLegacyThirtyTwo()) {
    d.s64 = static_cast<int64_t>(d.s32 / 30) * 32;
  }
}

void NhlLegacyMul_210_224(PPCRegister& d, PPCRegister& a) {
  if (NhlLegacyThirtyTwo()) {
    d.s64 = static_cast<int64_t>(a.s32) * 224;
  }
}

