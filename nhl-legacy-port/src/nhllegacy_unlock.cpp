// Всё закрытое — открыто с начала (docs/legacy-port.md, «Закрытое: предзаказ, маски, бусты, коды формы»).
//
// Закрытое в Legacy хранит менеджер UNLOCKABLE::ExtraContentManager — объект 1053 байт *(0x83BDD2D0)
// (создание 82BC3228, конструктор 82BC2A48, геттер 82BC1710). В нём два пространства номеров:
//  - экипировка 0…131 (имена — таблица 0x83A29788 по 12 байт, +8 — ключ строки): байт +0[id] — открыто игрой
//    (лежит в сейве профиля, блок 82BE7C50/82BE7CF8), +590[id] — открыто «снаружи» (в сейв не идёт; кроме
//    конструктора его никто не пишет — видимо, место раздач EA: предзаказ, онлайн), +295[id] — метка «новое».
//    Проверка — 82BC2238(m, id): 0 ≤ id < 132 и (+0[id] == 1 или +590[id] == 1). Номер записи стоит в каталогах
//    редактора (клюшки 27 × 124 байт, номер в +116; перчатки 20 × 32, +20; маски вратаря 87 × 36, +28;
//    коньки 11 × 28, +20 — 82BC22D8), −1 — свободно. Закрыто в каталогах Legacy 48 записей: 4 клюшки, 4 пары
//    перчаток и 3 пары коньков предзаказа (BAUER 0–2, CCM 3–5, EASTON 6–8, WARRIOR 9–10: коньки, клюшка,
//    перчатки) и 37 масок вратаря. Закрытое редактор не показывает (82ADE6E0, 82AE4228, 82A040E0, 82A05BA8),
//    а 829619D0 снимает с игрока клюшку/перчатки/коньки предзаказа (на 105 / 82 / 47), если они закрыты.
//    Второй замок — в самих списках редактора (82ADE6E0 — клюшки, перчатки, коньки, маски; 82A040E0,
//    82A05BA8): открытую вещь с номером они прячут, если состояние игры *(*(0x83BCE468)) — 8…11
//    (82986DD8: Notification.eState CREATEPLAYER, _DYNASTY, _TOURNAMENT, _SEASON — Create/Edit Player из
//    Creation Zone, «Стань GM», турнира и сезона) или 82975578() = 1 (есть System::BeAProLogic::Instance
//    *(0x83BD80F4), а у ProfileTracker::ProfileTrackerManager *(0x83BC8564) не стоит байт +55148). То есть
//    у EA предзаказ и маски — только для своего игрока (EDIT_PRO 14/15, «Стань профи»). Подмена: 82975578 → 0
//    (других вызовов у неё нет; в Edit Player из Creation Zone 23.10 она и так давала 0) и 82986DD8 → 0 только
//    на 7 местах этих списков (по адресу возврата; восьмой вызов, 829AFEC0, — не редактор, его не трогаем).
//    Остальные номера (flameskate, goldstick…) — наследство NHL 13, в каталогах Legacy их нет; золотые
//    вещи редактор прячет всегда (829F4650), их не трогаем.
//  - бусты Pro Shop 0…162 (Be a Pro и созданный игрок): 0…122 — 41 буст × 3 силы (+3 / +5 / +7),
//    123…149 — ячейки бустов (9 видов экипировки × 3), 150…162 — Max-бусты (+10). Открыто: +132[id] (сейв),
//    +722[id] (снаружи, никто не пишет) или купленный уровень +885[id] (82BC2918). Проверки — 82BC2B48(m, id)
//    и 82BC2B98(m, вид, ячейка) (ячейка → id (вид + 41) × 3 + ячейка, заодно ставит 4 бесплатные ячейки).
//    Открывались задачами TXT_UNLOCK_TASK_* (82BC2FA8, коды → 4 номера, таблица 0x8208CB40) и покупкой в
//    магазине Xbox Live. Счётчик «сколько в группе ещё закрыто» (82BC2600) нужен только экрану покупки
//    (жетоны против закрытых, 82A7F220) — магазина в порте нет, его не трогаем.
//  - коды формы: Unlockable::UnlockableManager *(0x83BDD2D4) — 17 байт, введённый код (до 16 знаков; экран
//    jerseyCodeUnlock, ION_Uniform.UnlockUniform/IsUniformUnlocked, в меню Legacy пункта нет). Код верен, если
//    «Lorem ipsum…» (0x82013A48), зашифрованный кодом (828A3028), совпадает со 125 байтами 0x82013AC8 (828AB7D0).
//    82BC1F20(manager) — «код верен»: от него зависят IsUniformUnlocked (82BCC058), загрузка кода из базы
//    (82A08410) и замок формы с islockable (82AEAB90). В базе Legacy (stockteamjerseys) islockable = 0 у всех
//    703 форм — подмена нужна только модам с замком.
//
// Подмены не пишут в сейвы: игра просто видит «открыто». Выключить — cvar false (вернётся как у EA; что
// игрок успел надеть, 829619D0 снимет так же, как без подмены).

#include <atomic>
#include <cstdint>
#include <cstring>
#include <string>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ppc.h>

REXCVAR_DEFINE_BOOL(nhl_unlock_equipment, true, "NHLLegacy",
                    "All locked equipment is unlocked: BAUER / CCM / EASTON / WARRIOR preorder sticks, gloves and "
                    "skates, 37 goalie masks (ExtraContentManager items 0-131)")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

REXCVAR_DEFINE_BOOL(nhl_unlock_boosts, true, "NHLLegacy",
                    "All Pro Shop boosts are unlocked: attribute boosts, boost slots and Max boosts for Be a Pro "
                    "and created players (ExtraContentManager boosts 0-162)")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

REXCVAR_DEFINE_BOOL(nhl_unlock_jerseys, true, "NHLLegacy",
                    "Code-locked jerseys (islockable) count as unlocked, as if the jersey code had been entered")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

extern "C" void __imp__sub_82BC2238(PPCContext& ctx, uint8_t* base);  // экипировка: открыто?
extern "C" void __imp__sub_82975578(PPCContext& ctx, uint8_t* base);  // редактор: прятать открытое?
extern "C" void __imp__sub_82986DD8(PPCContext& ctx, uint8_t* base);  // состояние 8…11 (Create Player)?
extern "C" void __imp__sub_82BC2B48(PPCContext& ctx, uint8_t* base);  // буст: открыт?
extern "C" void __imp__sub_82BC2B98(PPCContext& ctx, uint8_t* base);  // ячейка буста: открыта?
extern "C" void __imp__sub_82BC1F20(PPCContext& ctx, uint8_t* base);  // код формы верен?

namespace {

constexpr int32_t kItems = 132;      // экипировка 0…131
constexpr int32_t kBoosts = 163;     // бусты 0…162
constexpr uint32_t kItemNames = 0x83A29788;  // 12 байт на номер, +8 — ключ имени
// Возвраты из 82986DD8 в списках редактора: «состояние Create Player — спрятать вещь с номером» (82A04120,
// 82A05BF4; в 82ADE6E0 — 82AE0AD8 клюшки, 82AE1C1C, 82AE3148, 82AE3790 — сброс выбора, 82AE382C).
constexpr uint32_t kEditorModeChecks[] = {0x82A04124, 0x82A05BF8, 0x82AE0ADC, 0x82AE1C20,
                                          0x82AE314C, 0x82AE3794, 0x82AE3830};

bool Equipment() {
  static const bool on = REXCVAR_GET(nhl_unlock_equipment);
  return on;
}

bool Boosts() {
  static const bool on = REXCVAR_GET(nhl_unlock_boosts);
  return on;
}

bool Jerseys() {
  static const bool on = REXCVAR_GET(nhl_unlock_jerseys);
  return on;
}

uint32_t Ld(uint8_t* base, uint32_t a) {
  uint32_t v;
  std::memcpy(&v, base + a, 4);
  return __builtin_bswap32(v);
}

std::string GuestString(uint8_t* base, uint32_t a) {
  std::string s;
  if (a < 0x82000000u || a >= 0x84000000u) {
    return s;
  }
  for (uint32_t i = 0; i < 48; ++i) {
    const char c = static_cast<char>(base[a + i]);
    if (c == 0) {
      break;
    }
    s.push_back(c);
  }
  return s;
}

// Журнал: каждый номер — один раз, при первом «открыто вместо закрыто».
std::atomic<uint64_t> g_items_logged[3];
std::atomic<uint64_t> g_boosts_logged[3];
std::atomic<bool> g_jersey_logged{false};
std::atomic<bool> g_editor_logged{false};
std::atomic<bool> g_mode_logged{false};

bool FirstTime(std::atomic<uint64_t>* bits, int32_t id) {
  const uint64_t m = uint64_t{1} << (id & 63);
  return (bits[id >> 6].fetch_or(m) & m) == 0;
}

}  // namespace

// 82BC2238(m, id) → открыта ли вещь id (0…131).
extern "C" void sub_82BC2238(PPCContext& ctx, uint8_t* base) {
  const int32_t id = ctx.r4.s32;
  __imp__sub_82BC2238(ctx, base);
  if (Equipment() && id >= 0 && id < kItems && ctx.r3.u32 == 0) {
    ctx.r3.u64 = 1;
    if (FirstTime(g_items_logged, id)) {
      REXLOG_INFO("[nhllegacy] unlock: equipment item {} ({}) unlocked (nhl_unlock_equipment)", id,
                  GuestString(base, Ld(base, kItemNames + 12 * id + 8)));
    }
  }
}

// 82975578() → прятать ли в списках редактора открытые вещи с номером (1 — вне своего игрока «Стань профи»).
extern "C" void sub_82975578(PPCContext& ctx, uint8_t* base) {
  __imp__sub_82975578(ctx, base);
  if (Equipment() && ctx.r3.u32 != 0) {
    ctx.r3.u64 = 0;
    if (!g_editor_logged.exchange(true)) {
      REXLOG_INFO("[nhllegacy] unlock: unlocked equipment shown in every editor, not only for the Be a Pro player "
                  "(nhl_unlock_equipment)");
    }
  }
}

// 82986DD8(состояние) → 1 для 8…11 (Create Player). На местах списков редактора — 0.
extern "C" void sub_82986DD8(PPCContext& ctx, uint8_t* base) {
  const uint32_t lr = static_cast<uint32_t>(ctx.lr);
  const uint32_t state = ctx.r3.u32;
  __imp__sub_82986DD8(ctx, base);
  if (!Equipment() || ctx.r3.u32 == 0) {
    return;
  }
  for (const uint32_t site : kEditorModeChecks) {
    if (lr == site) {
      ctx.r3.u64 = 0;
      if (!g_mode_logged.exchange(true)) {
        REXLOG_INFO("[nhllegacy] unlock: unlocked equipment shown in Create/Edit Player too (state {}, "
                    "nhl_unlock_equipment)", state);
      }
      return;
    }
  }
}

// 82BC2B48(m, id) → открыт ли буст id (0…162).
extern "C" void sub_82BC2B48(PPCContext& ctx, uint8_t* base) {
  const int32_t id = ctx.r4.s32;
  __imp__sub_82BC2B48(ctx, base);
  if (Boosts() && id >= 0 && id < kBoosts && ctx.r3.u32 == 0) {
    ctx.r3.u64 = 1;
    if (FirstTime(g_boosts_logged, id)) {
      REXLOG_INFO("[nhllegacy] unlock: boost {} unlocked (nhl_unlock_boosts)", id);
    }
  }
}

// 82BC2B98(m, вид, ячейка) → открыта ли ячейка буста (id (вид + 41) × 3 + ячейка). Оригинал зовём всегда:
// он ставит бесплатные ячейки.
extern "C" void sub_82BC2B98(PPCContext& ctx, uint8_t* base) {
  const int32_t id = (ctx.r4.s32 + 41) * 3 + ctx.r5.s32;
  __imp__sub_82BC2B98(ctx, base);
  if (Boosts() && id >= 0 && id < kBoosts && ctx.r3.u32 == 0) {
    ctx.r3.u64 = 1;
    if (FirstTime(g_boosts_logged, id)) {
      REXLOG_INFO("[nhllegacy] unlock: boost slot {} unlocked (nhl_unlock_boosts)", id);
    }
  }
}

// 82BC1F20(manager) → введённый код формы верен.
extern "C" void sub_82BC1F20(PPCContext& ctx, uint8_t* base) {
  if (!Jerseys()) {
    __imp__sub_82BC1F20(ctx, base);
    return;
  }
  ctx.r3.u64 = 1;
  if (!g_jersey_logged.exchange(true)) {
    REXLOG_INFO("[nhllegacy] unlock: jersey code counts as entered (nhl_unlock_jerseys)");
  }
}
