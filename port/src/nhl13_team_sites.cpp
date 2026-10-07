// Сгенерировано tools/team_hooks.py — не править руками.
// Врезки «30 команд НХЛ → 32» (port/nhl13_team_sites.toml); действуют при nhl_teams = 32.

#include <cstdint>

#include <rex/ppc.h>

bool Nhl13ThirtyTwo();

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

void Nhl13CmpS_576(PPCRegister& a, PPCCRRegister& cr) {
  if (Nhl13ThirtyTwo()) {
    const int32_t v = a.s32, n = 576;
    cr.lt = v < n;
    cr.gt = v > n;
    cr.eq = v == n;
  }
}

void Nhl13CmpS_62(PPCRegister& a, PPCCRRegister& cr) {
  if (Nhl13ThirtyTwo()) {
    const int32_t v = a.s32, n = 62;
    cr.lt = v < n;
    cr.gt = v > n;
    cr.eq = v == n;
  }
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

void Nhl13Li_17(PPCRegister& d) {
  if (Nhl13ThirtyTwo()) {
    d.s64 = 17;
  }
}

void Nhl13Li_18(PPCRegister& d) {
  if (Nhl13ThirtyTwo()) {
    d.s64 = 18;
  }
}

void Nhl13Li_224(PPCRegister& d) {
  if (Nhl13ThirtyTwo()) {
    d.s64 = 224;
  }
}

void Nhl13Li_248(PPCRegister& d) {
  if (Nhl13ThirtyTwo()) {
    d.s64 = 248;
  }
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

void Nhl13Li_62(PPCRegister& d) {
  if (Nhl13ThirtyTwo()) {
    d.s64 = 62;
  }
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

