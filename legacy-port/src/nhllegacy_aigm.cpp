// AI-объект GM NHL Legacy на 32 команды (docs/legacy-port.md, «AI-GM на 32: вариант (а)»).
// ВЕТКА legacy-aigm32, НЕ СОБИРАЛОСЬ И НЕ ПРОВЕРЯЛОСЬ (09.10, 05:10–06:00: пользователь играл, сборки были
// запрещены). По умолчанию выключено (nhl_aigm32 = false) — все врезки ничего не делают.
//
// AI-объект GM — одиночка *(0x83BC72E8) (конструктор 8295F820, 64084 байта); +668 — число команд (8295B788:
// из списка НХЛ лиги, при nhl_teams = 32 — 32), +8 — блок 0x10D08 байт:
//   +0…599     записи команд по 20 байт ×30: b0 номер, b1 состояние (2), b2 «команда игрока», b3/b4 — оценка
//              (829551E8), b5…b13 — нужды по позициям (829555B8), b14 — место (82973FB0), h16 — цель (−1),
//              b18 — счётчик, b19 — ?;
//   +600…629   байт на команду ×30 (829551E8, 829555B8, 829742B0);
//   +630 i16 — счётчик (из +632), +632 u32 (154), +636 u32 — номер команды игрока, +640/+641 — флаг/процент;
//   +642…      байты по playerid (65535);
//   +0x1043C   порядок команд ×30 (82973FB0), сразу за ним +0x1045A/+0x1045B — поля.
// При 32 командах записи 30/31 ложатся на +600…639, байты +600[30/31] — на +630/+631, порядок [30/31] — на
// +0x1045A/+0x1045B: init 829555B8 затирает +636 (номер команды игрока) записью 31, цикл 829742B0 обнуляет
// счётчик +630 (и процент +641) — это уже сейчас при nhl_teams = 32 (п. 3 в docs).
//
// Исправление (nhl_aigm32): записи 30/31, их байты +600 и порядок — в своём буфере (side) в памяти гостя:
//   side+0  запись 30, side+20 запись 31, side+40/41 — байты +600[30/31], side+42/43 — порядок [30/31].
// Врезки (nhllegacy_aigm_hooks.toml): после `add rec = блок + команда·20` (16 мест), в начале циклов с шагом
// 20 по записям (5 мест, указатель переводится в side один раз — дальше шаг идёт уже по side), после
// `add p = блок + i` перед доступом к +600[i] (6 мест) и к +0x1043C[i] (1 место); цикл AI межсезонья
// 82B214A8 (`cmpwi cr6, r28, 30` @82B2166C) — до 32: Сиэтл и Вегас начинают делать предложения свободным
// агентам (8295FC38 → 82955998 → 82B64C78) и подписывать из пула (82B77878).
// Проверить (утром): создание франшизы и загрузка сейва, межсезонье до 15.07 — предложения/подписания SEA/VGK
// (leaguecontractoffers, составы), поле +636 = номер команды игрока, +630/+641 не обнуляются; интерес
// агентов к SEA/VGK (82B69D78 ← 82B73068 ← 82955F68: b5…b13 записи) — ожидается как у остальных, не 95–96.

#include <cstdint>
#include <cstring>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ppc.h>
#include <rex/runtime.h>
#include <rex/system/xmemory.h>

REXCVAR_DEFINE_BOOL(nhl_aigm32, false, "NHLLegacy",
                    "AI GM on 32 teams: records of teams 30/31 (and their +600 / order bytes) beside the "
                    "30-team AI GM block; offseason AI loop over 32 teams (SEA/VGK sign free agents)")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

bool NhlLegacyThirtyTwo();

namespace {

constexpr uint32_t kRecordsEnd = 600;        // записи 0…29
constexpr uint32_t kSideRecordsEnd = 640;    // записи 30/31 — 600…639 в «блочных» смещениях
constexpr uint32_t kTeamBytes = 600;         // +600[команда]
constexpr uint32_t kOrderBytes = 0x1043C;    // +0x1043C[i]
constexpr uint32_t kSideTeamBytes = 40;
constexpr uint32_t kSideOrderBytes = 42;
constexpr uint32_t kSideSize = 64;

uint8_t* GuestBase() {
  return rex::Runtime::instance()->memory()->TranslateVirtual<uint8_t*>(0);
}

uint32_t Load32(uint8_t* base, uint32_t addr) {
  uint32_t v;
  std::memcpy(&v, base + addr + (addr >= 0xE0000000u ? 0x1000u : 0u), 4);
  return __builtin_bswap32(v);
}

uint16_t Load16(uint8_t* base, uint32_t addr) {
  uint16_t v;
  std::memcpy(&v, base + addr + (addr >= 0xE0000000u ? 0x1000u : 0u), 2);
  return __builtin_bswap16(v);
}

bool On() {
  static const bool on = REXCVAR_GET(nhl_aigm32) && NhlLegacyThirtyTwo();
  return on;
}

// Свой буфер в памяти гостя (один: AI-объект GM — одиночка). Записи 30/31 заполняет сама игра — инициализация
// 829555B8 и циклы «i < +668» идут через врезки; до первой инициализации — нули, как у свежего блока.
uint32_t Side() {
  static const uint32_t side = [] {
    auto* memory = rex::Runtime::instance()->memory();
    const uint32_t addr = memory->SystemHeapAlloc(kSideSize);
    std::memset(memory->TranslateVirtual<uint8_t*>(addr), 0, kSideSize);
    REXLOG_INFO("[nhllegacy] AI GM 32: records of teams 30/31 beside the block at {:08X}", addr);
    return addr;
  }();
  return side;
}

// «Блочное» смещение записи (команда·20 + поле) → адрес в side, если это записи 30/31.
bool SideRecord(uint32_t offset, uint32_t* out) {
  if (offset < kRecordsEnd || offset >= kSideRecordsEnd) {
    return false;
  }
  *out = Side() + (offset - kRecordsEnd);
  return true;
}

void Stride(PPCRegister& ptr, PPCRegister& obj, int32_t bias) {
  if (!On()) {
    return;
  }
  const uint32_t block = Load32(GuestBase(), obj.u32 + 8);
  const int32_t rel = static_cast<int32_t>(ptr.u32 - block) - bias;  // = 20·i у записи i
  uint32_t side;
  if (rel >= 0 && SideRecord(static_cast<uint32_t>(rel), &side)) {
    ptr.u64 = static_cast<uint32_t>(side + bias);
  }
}

void Bytes(PPCRegister& p, PPCRegister& i, uint32_t displacement, uint32_t side_offset) {
  if (!On() || i.u32 < 30 || i.u32 > 31) {
    return;
  }
  // дальше игра обращается к displacement(p): p = side + (i − 30) − displacement
  p.u64 = static_cast<uint32_t>(Side() + side_offset + (i.u32 - 30) - displacement);
}

}  // namespace

// После `add rec, …` — смещение (команда·20) в живом регистре off.
void NhlLegacyAigmRecOff(PPCRegister& rec, PPCRegister& off) {
  uint32_t side;
  if (On() && SideRecord(off.u32, &side)) {
    rec.u64 = side;
  }
}

// После `add rec, …` — регистр смещения затёрт результатом, жив регистр блока.
void NhlLegacyAigmRecBlock(PPCRegister& rec, PPCRegister& block) {
  uint32_t side;
  if (On() && SideRecord(rec.u32 - block.u32, &side)) {
    rec.u64 = side;
  }
}

// Начало тела цикла с шагом 20 по записям: ptr = блок + 20·i + bias (bias — в имени), obj — AI-объект.
void NhlLegacyAigmStrideM6(PPCRegister& ptr, PPCRegister& obj) { Stride(ptr, obj, -6); }
void NhlLegacyAigmStrideM4(PPCRegister& ptr, PPCRegister& obj) { Stride(ptr, obj, -4); }
void NhlLegacyAigmStride14(PPCRegister& ptr, PPCRegister& obj) { Stride(ptr, obj, 14); }
void NhlLegacyAigmStride18(PPCRegister& ptr, PPCRegister& obj) { Stride(ptr, obj, 18); }

// После `add p, блок, i` перед доступом 600(p) — байт +600[i].
void NhlLegacyAigmTeamByte(PPCRegister& p, PPCRegister& i) {
  Bytes(p, i, kTeamBytes, kSideTeamBytes);
}

// После `add p, i, блок` перед `stbx v, p, 0x1043C` — порядок команд +0x1043C[i].
void NhlLegacyAigmOrderByte(PPCRegister& p, PPCRegister& i) {
  Bytes(p, i, kOrderBytes, kSideOrderBytes);
}

// 8295B788 (число команд +668, команды игрока, затем init 829555B8): после — в лог поля блока, которые при
// 32 командах без nhl_aigm32 перекрывают записи 30/31 (+636 — номер команды игрока, +630/+632 — счётчик и
// знаменатель процента +641). Пишет и при выключенном nhl_aigm32 — для сравнения «до/после».
extern "C" void __imp__sub_8295B788(PPCContext& ctx, uint8_t* base);
extern "C" void sub_8295B788(PPCContext& ctx, uint8_t* base) {
  const uint32_t obj = ctx.r3.u32;
  __imp__sub_8295B788(ctx, base);
  static int logged = 0;
  if (logged < 4) {
    ++logged;
    const uint32_t block = Load32(base, obj + 8);
    REXLOG_INFO("[nhllegacy] AI GM: teams {}, user team (+636) {:08X}, counter (+630) {:04X}, denominator (+632) "
                "{:08X}, percent (+641) {}, nhl_aigm32 {}",
                Load32(base, obj + 668), Load32(base, block + 636), Load16(base, block + 630),
                Load32(base, block + 632), Load32(base, block + 640) >> 16 & 0xFF, On() ? "on" : "off");
  }
}

// 82B2166C `cmpwi cr6, r28, 30` (цикл AI межсезонья 82B214A8): true — следующая команда (→ 82B21504).
bool NhlLegacyAigmLoop32(PPCRegister& r28) {
  if (!On()) {
    return false;
  }
  static bool logged = false;
  if (r28.s32 == 30 && !logged) {
    logged = true;
    REXLOG_INFO("[nhllegacy] AI GM 32: offseason AI loop over 32 teams (SEA/VGK)");
  }
  return r28.s32 < 32;
}
