// Камера матча: журнал выбора (nhl_camera_trace, по умолчанию выкл.; docs/legacy-port.md, «Камера матча»).
//
// Жалоба пользователя 05.11.2026: камера в матче всё время Action, хотя в настройках выбран Ice и в сейвах (блок
// настроек PROFILE, DYNASTY, BEAPRO) записан Ice. Разбор статический (агент, 05.11):
// - глобальные опции 0x83BEF4E0: Camera +392 (0x83BEF668), ShootoutCamera +396, GoalieCamera +400, BapCamera +428,
//   OnlineSkaterCamera +432, OnlineGoalieCamera +436, GoalieMode +444; менеджер настроек *(0x83BD3074): копии блока
//   +4 заводские, +660 профиль, +1316 карьера, +1972 действующие (GoalieMode — байт +40 блока);
// - правка в меню: 829FE078(mgr, индекс, значение, …) пишет действующие и, если настройка не заблокирована режимом
//   (829FC378), профиль и карьеру; 829F97F8(индекс, значение) — в глобальные опции и директору камер;
// - старт матча: директор камер *(0x83B6DD00), 834633B0 берёт Camera, а при особых условиях — GoalieCamera
//   (режим вратаря), BapCamera (байт 0x83AC5F63) или OnlineSkaterCamera; при GoalieMode ≠ 0 Ice и Classic дают Action3D.
// Журнал показывает, какая ветка срабатывает у пользователя.

#include <cstdint>
#include <cstring>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ppc.h>

REXCVAR_DEFINE_BOOL(nhl_camera_trace, true, "NHLLegacy",
                    "Log the match camera choice: settings values, the director branch and who changes them");

namespace {

constexpr uint32_t kOptions = 0x83BEF4E0;
constexpr uint32_t kManagerPtr = 0x83BD3074;
constexpr uint32_t kDirectorPtr = 0x83B6DD00;
constexpr uint32_t kModeStatePtr = 0x83BCE468;
constexpr uint32_t kBapFlag = 0x83AC5F63;
constexpr uint32_t kSpecialA = 0x83BFE998, kSpecialB = 0x83BFE99C;

uint8_t* Host(uint8_t* base, uint32_t a) {
  return base + a + (a >= 0xE0000000u ? 0x1000u : 0u);
}

uint32_t Ld(uint8_t* base, uint32_t a) {
  uint32_t v;
  std::memcpy(&v, Host(base, a), 4);
  return __builtin_bswap32(v);
}

uint8_t Lb(uint8_t* base, uint32_t a) {
  return *Host(base, a);
}

bool Plausible(uint32_t a) {
  return a >= 0x40000000u && a < 0xFFF00000u;
}

bool On() {
  return REXCVAR_GET(nhl_camera_trace);
}

uint32_t Mode(uint8_t* base) {
  const uint32_t state = Ld(base, kModeStatePtr);
  return Plausible(state) ? Ld(base, state) : 0xFFFFFFFFu;
}

// Индексы общих настроек, которые касаются камеры: 0 Camera, 1 Shootout, 2 Goalie, 3 BeAPro, 40 GoalieMode,
// 42 OnlineSkater.
bool CameraIndex(uint32_t i) {
  return i <= 3 || i == 40 || i == 42;
}

void LogState(uint8_t* base, const char* when) {
  const uint32_t mgr = Ld(base, kManagerPtr);
  uint32_t act = 0xFF, prof = 0xFF, car = 0xFF, gm_act = 0xFF, gm_prof = 0xFF, gm_car = 0xFF;
  if (Plausible(mgr)) {
    act = Lb(base, mgr + 1972);
    prof = Lb(base, mgr + 660);
    car = Lb(base, mgr + 1316);
    gm_act = Lb(base, mgr + 1972 + 40);
    gm_prof = Lb(base, mgr + 660 + 40);
    gm_car = Lb(base, mgr + 1316 + 40);
  }
  REXLOG_INFO(
      "[nhllegacy] camera {}: mode {}, options Camera {} Shootout {} Goalie {} BeAPro {} OnlineSkater {} GoalieMode {}; "
      "settings Camera active/profile/career {}/{}/{}, GoalieMode {}/{}/{}; special {:08X} {:08X}, BeAPro flag {}",
      when, Mode(base), Ld(base, kOptions + 392), Ld(base, kOptions + 396), Ld(base, kOptions + 400),
      Ld(base, kOptions + 428), Ld(base, kOptions + 432), Ld(base, kOptions + 444), act, prof, car, gm_act, gm_prof,
      gm_car, Ld(base, kSpecialA), Ld(base, kSpecialB), Lb(base, kBapFlag));
}

}  // namespace

// Директор камер, выбор камеры матча (v88; зовёт старт матча и смена камеры в меню).
extern "C" void __imp__sub_834633B0(PPCContext& ctx, uint8_t* base);
extern "C" void sub_834633B0(PPCContext& ctx, uint8_t* base) {
  if (!On()) {
    __imp__sub_834633B0(ctx, base);
    return;
  }
  const uint32_t lr = static_cast<uint32_t>(ctx.lr);
  LogState(base, "director before");
  __imp__sub_834633B0(ctx, base);
  const uint32_t dir = Ld(base, kDirectorPtr);
  if (Plausible(dir)) {
    REXLOG_INFO("[nhllegacy] camera director after: type {} (+444), +496 {}, special branch {} (+511), from {:08X}",
                Ld(base, dir + 444), Ld(base, dir + 496), Lb(base, dir + 511), lr);
  }
}

// Правка настройки: r3 — менеджер, r4 — индекс общей настройки, r5 — значение, r6 — флаг.
extern "C" void __imp__sub_829FE078(PPCContext& ctx, uint8_t* base);
extern "C" void sub_829FE078(PPCContext& ctx, uint8_t* base) {
  const uint32_t index = ctx.r4.u32, value = ctx.r5.u32, flag = ctx.r6.u32;
  const uint32_t lr = static_cast<uint32_t>(ctx.lr);
  __imp__sub_829FE078(ctx, base);
  if (On() && CameraIndex(index)) {
    REXLOG_INFO("[nhllegacy] camera setting {} = {} (flag {}), mode {}, from {:08X}", index, value, flag, Mode(base),
                lr);
    LogState(base, "after setting");
  }
}

// В глобальные опции: r3 — индекс, r4 — значение.
extern "C" void __imp__sub_829F97F8(PPCContext& ctx, uint8_t* base);
extern "C" void sub_829F97F8(PPCContext& ctx, uint8_t* base) {
  const uint32_t index = ctx.r3.u32, value = ctx.r4.u32;
  const uint32_t lr = static_cast<uint32_t>(ctx.lr);
  __imp__sub_829F97F8(ctx, base);
  if (On() && CameraIndex(index)) {
    REXLOG_INFO("[nhllegacy] camera option {} = {}, mode {}, from {:08X}", index, value, Mode(base), lr);
  }
}
