// Настройки новой карьеры — из профиля (cvar nhl_settings_from_profile, по умолчанию выкл.; docs/legacy-port.md,
// «Настройки по умолчанию для новых карьер»).
//
// Менеджер настроек игры — объект *(0x83BD3074) (конструктор 829F4158). В нём четыре копии блока настроек по 656
// байт (раскладка — tools/legacy_settings.py): +4 — заводские (заполняет 829FDFA8 при запуске игры), +660 — профиль,
// +1316 — карьера (франшиза, Be a Pro, сезон, плей-офф, турнир), +1972 — действующие. Блок SETTINGS_MGR_CHUNK
// (82BE49E8 — загрузка, 82BE4110 — запись) профиль читает в +660, а сейв карьеры пишет из +1316. При загрузке карьеры
// игра собирает +1316 из профиля и своих правил и слайдеров карьеры. Новая карьера +1316 не трогает. Если до неё в
// этом запуске не загружали карьеру, там заводские значения. Общие (громкость, камеры, визуальные) правка пишет и в
// профиль, и в +1316, а правила и слайдеры — только в +1316.
//
// С переключателем при входе в режим карьеры (смена режима 8298B570) копия «карьера» становится копией профиля.
// Условие — карьера в этом заходе ещё не загружалась. Режимы карьеры — те, что 82987018 считает режимами со своими
// настройками: 5, 6, 51…53, 62…65. Копия делается до 829FEBF8, поэтому значения, которые режим задаёт сам (у Be a Pro —
// длина периода, овертайм…), ставятся поверх, как в игре. Загрузка существующей карьеры идёт после входа в режим
// и переписывает копию её собственными настройками — как без переключателя. «Заход» кончается возвратом в главное
// меню (режим 0, там игра сама переводит действующие настройки на профиль).

#include <atomic>
#include <cstdint>
#include <cstring>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ppc.h>

REXCVAR_DEFINE_BOOL(nhl_settings_from_profile, false, "NHLLegacy",
                    "New career (Be a GM, Be a Pro, season, playoffs, tournament) starts with the profile settings "
                    "(main menu: gameplay sliders, rules, volume, cameras, visual) instead of the factory ones")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

namespace {

constexpr uint32_t kManagerPtr = 0x83BD3074;  // *(…) — менеджер настроек
constexpr uint32_t kModeStatePtr = 0x83BCE468;  // *(…) — состояние режима игры, +0 — текущий режим
constexpr uint32_t kProfile = 660;
constexpr uint32_t kCareer = 1316;
constexpr uint32_t kBlock = 656;
constexpr uint32_t kHandlerCareer = 48;  // у обработчика SETTINGS_MGR_CHUNK: 0 — профиль, 1 — сейв карьеры

bool On() {
  static const bool on = REXCVAR_GET(nhl_settings_from_profile);
  return on;
}

uint8_t* Host(uint8_t* base, uint32_t a) {
  return base + a + (a >= 0xE0000000u ? 0x1000u : 0u);
}

uint32_t Ld(uint8_t* base, uint32_t a) {
  uint32_t v;
  std::memcpy(&v, Host(base, a), 4);
  return __builtin_bswap32(v);
}

bool Plausible(uint32_t a) {
  return a >= 0x40000000u && a < 0xFFF00000u;
}

// 82987018: режимы со своей копией настроек.
bool CareerMode(uint32_t m) {
  return m == 5 || m == 6 || (m >= 51 && m <= 53) || (m >= 62 && m <= 65);
}

// Карьера в текущем заходе уже есть (вошли в режим карьеры или загрузили её сейв); сбрасывается в главном меню.
std::atomic<bool> g_career{false};

uint32_t CurrentMode(uint8_t* base) {
  const uint32_t state = Ld(base, kModeStatePtr);
  return Plausible(state) ? Ld(base, state) : 0xFFFFFFFFu;
}

void CareerFromProfile(uint8_t* base, uint32_t from, uint32_t to) {
  const uint32_t mgr = Ld(base, kManagerPtr);
  if (!Plausible(mgr)) {
    REXLOG_WARN("[nhllegacy] settings: mode {} -> {}: no settings manager ({:08X}), career settings unchanged", from,
                to, mgr);
    return;
  }
  uint8_t* profile = Host(base, mgr + kProfile);
  uint8_t* career = Host(base, mgr + kCareer);
  int diff = 0;
  for (uint32_t i = 0; i < kBlock; ++i) {
    diff += profile[i] != career[i];
  }
  std::memmove(career, profile, kBlock);
  REXLOG_INFO("[nhllegacy] settings: mode {} -> {}: new career settings = profile settings ({} of {} bytes differed)",
              from, to, diff, kBlock);
}

}  // namespace

// Смена режима игры: r3 — состояние режима (+0 — текущий), r4 — новый режим.
extern "C" void __imp__sub_8298B570(PPCContext& ctx, uint8_t* base);
extern "C" void sub_8298B570(PPCContext& ctx, uint8_t* base) {
  if (On()) {
    const uint32_t state = ctx.r3.u32;
    const uint32_t to = ctx.r4.u32;
    const uint32_t from = Plausible(state) ? Ld(base, state) : 0xFFFFFFFFu;
    if (to == 0) {
      g_career = false;
    } else if (CareerMode(to) && !CareerMode(from) && !g_career.exchange(true)) {
      CareerFromProfile(base, from, to);
    }
  }
  __imp__sub_8298B570(ctx, base);
}

// Загрузка блока SETTINGS_MGR_CHUNK (r3 — обработчик). Сейв карьеры, загруженный вне режима карьеры, тоже начинает
// заход: при входе в режим его настройки не затираются.
extern "C" void __imp__sub_82BE49E8(PPCContext& ctx, uint8_t* base);
extern "C" void sub_82BE49E8(PPCContext& ctx, uint8_t* base) {
  const uint32_t handler = ctx.r3.u32;
  __imp__sub_82BE49E8(ctx, base);
  if (On() && Plausible(handler) && Ld(base, handler + kHandlerCareer) == 1) {
    const uint32_t mode = CurrentMode(base);
    if (!g_career.exchange(true)) {
      REXLOG_INFO("[nhllegacy] settings: career save loaded in mode {}: its own settings kept", mode);
    }
  }
}
