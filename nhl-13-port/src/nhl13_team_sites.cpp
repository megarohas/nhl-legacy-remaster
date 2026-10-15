// Сгенерировано tools/team_hooks.py — не править руками.
// Врезки «30 команд НХЛ → 32» (nhl-13-port/nhl13_team_sites.toml); действуют при nhl_teams = 32.
// Варианты ahl32 (nhl_ahl_teams = 32, только вместе с nhl_teams = 32) — docs/ahl32.md.

#include <cstdint>

#include <rex/ppc.h>

bool Nhl13ThirtyTwo();
bool Nhl13Ahl32();
bool Nhl13StandingsWide(PPCRegister& r);

void Nhl13Add_m2(PPCRegister& d) {
  if (Nhl13ThirtyTwo()) {
    d.s64 += -2;
  }
}

void Nhl13Add_p16(PPCRegister& d) {
  if (Nhl13ThirtyTwo()) {
    d.s64 += 16;
  }
}

void Nhl13Add_p2(PPCRegister& d) {
  if (Nhl13ThirtyTwo()) {
    d.s64 += 2;
  }
}

void Nhl13CmpS_16(PPCRegister& a, PPCCRRegister& cr) {
  if (Nhl13ThirtyTwo()) {
    const int32_t v = a.s32, n = 16;
    cr.lt = v < n;
    cr.gt = v > n;
    cr.eq = v == n;
  }
}

void Nhl13CmpS_31(PPCRegister& a, PPCCRRegister& cr) {
  if (Nhl13ThirtyTwo()) {
    const int32_t v = a.s32, n = 31;
    cr.lt = v < n;
    cr.gt = v > n;
    cr.eq = v == n;
  }
}

void Nhl13CmpS_32(PPCRegister& a, PPCCRRegister& cr) {
  if (Nhl13ThirtyTwo()) {
    const int32_t v = a.s32, n = 32;
    cr.lt = v < n;
    cr.gt = v > n;
    cr.eq = v == n;
  }
}

void Nhl13CmpS_576_StandingsWide(PPCRegister& a, PPCCRRegister& cr, PPCRegister& g) {
  if (Nhl13StandingsWide(g)) {
    const int32_t v = a.s32, n = 576;
    cr.lt = v < n;
    cr.gt = v > n;
    cr.eq = v == n;
  }
}

void Nhl13CmpS_62_a64(PPCRegister& a, PPCCRRegister& cr) {
  int32_t n;
  if (Nhl13Ahl32()) {
    n = 64;
  } else if (Nhl13ThirtyTwo()) {
    n = 62;
  } else {
    return;
  }
  const int32_t v = a.s32;
  cr.lt = v < n;
  cr.gt = v > n;
  cr.eq = v == n;
}

void Nhl13CmpS_a32(PPCRegister& a, PPCCRRegister& cr) {
  int32_t n;
  if (Nhl13Ahl32()) {
    n = 32;
  } else {
    return;
  }
  const int32_t v = a.s32;
  cr.lt = v < n;
  cr.gt = v > n;
  cr.eq = v == n;
}

void Nhl13CmpU_32(PPCRegister& a, PPCCRRegister& cr) {
  if (Nhl13ThirtyTwo()) {
    const uint32_t v = a.u32, n = 32;
    cr.lt = v < n;
    cr.gt = v > n;
    cr.eq = v == n;
  }
}

void Nhl13Li_128(PPCRegister& d) {
  if (Nhl13ThirtyTwo()) {
    d.s64 = 128;
  }
}

void Nhl13Li_140(PPCRegister& d) {
  if (Nhl13ThirtyTwo()) {
    d.s64 = 140;
  }
}

void Nhl13Li_16(PPCRegister& d) {
  if (Nhl13ThirtyTwo()) {
    d.s64 = 16;
  }
}

void Nhl13Li_16_StandingsWide(PPCRegister& d, PPCRegister& g) {
  if (Nhl13StandingsWide(g)) {
    d.s64 = 16;
  }
}

void Nhl13Li_17(PPCRegister& d) {
  if (Nhl13ThirtyTwo()) {
    d.s64 = 17;
  }
}

void Nhl13Li_17_StandingsWide(PPCRegister& d, PPCRegister& g) {
  if (Nhl13StandingsWide(g)) {
    d.s64 = 17;
  }
}

void Nhl13Li_18(PPCRegister& d) {
  if (Nhl13ThirtyTwo()) {
    d.s64 = 18;
  }
}

void Nhl13Li_18_StandingsWide(PPCRegister& d, PPCRegister& g) {
  if (Nhl13StandingsWide(g)) {
    d.s64 = 18;
  }
}

void Nhl13Li_224(PPCRegister& d) {
  if (Nhl13ThirtyTwo()) {
    d.s64 = 224;
  }
}

void Nhl13Li_248_a256(PPCRegister& d) {
  int64_t n;
  if (Nhl13Ahl32()) {
    n = 256;
  } else if (Nhl13ThirtyTwo()) {
    n = 248;
  } else {
    return;
  }
  d.s64 = n;
}

void Nhl13Li_31(PPCRegister& d) {
  if (Nhl13ThirtyTwo()) {
    d.s64 = 31;
  }
}

void Nhl13Li_32(PPCRegister& d) {
  if (Nhl13ThirtyTwo()) {
    d.s64 = 32;
  }
}

void Nhl13Li_3584(PPCRegister& d) {
  if (Nhl13ThirtyTwo()) {
    d.s64 = 3584;
  }
}

void Nhl13Li_384(PPCRegister& d) {
  if (Nhl13ThirtyTwo()) {
    d.s64 = 384;
  }
}

void Nhl13Li_384_StandingsWide(PPCRegister& d, PPCRegister& g) {
  if (Nhl13StandingsWide(g)) {
    d.s64 = 384;
  }
}

void Nhl13Li_62_a64(PPCRegister& d) {
  int64_t n;
  if (Nhl13Ahl32()) {
    n = 64;
  } else if (Nhl13ThirtyTwo()) {
    n = 62;
  } else {
    return;
  }
  d.s64 = n;
}

void Nhl13Li_64(PPCRegister& d) {
  if (Nhl13ThirtyTwo()) {
    d.s64 = 64;
  }
}

void Nhl13MulSame_30_32(PPCRegister& d) {
  if (Nhl13ThirtyTwo()) {
    d.s64 = static_cast<int64_t>(d.s32 / 30) * 32;
  }
}

void Nhl13Mul_210_224(PPCRegister& d, PPCRegister& a) {
  if (Nhl13ThirtyTwo()) {
    d.s64 = static_cast<int64_t>(a.s32) * 224;
  }
}

