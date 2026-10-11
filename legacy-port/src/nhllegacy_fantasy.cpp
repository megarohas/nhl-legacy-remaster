// Фэнтези-драфт на 32 клуба (cvar nhl_fd32, по умолчанию вкл., действует только при nhl_teams = 32;
// docs/legacy-port.md, «Фэнтези-драфт на 32»).
//
// FantasyDraftLogic — одиночка 0x83BDC6A0, создаёт её меню франшизы 829CCE78 (указатель — меню +9252) через фабрику
// 82B80C10: 82E53E80(15892, 9, «FantasyDraftLogic::mInstance»), конструктор 82B80898(объект, лиг, список НХЛ,
// клубов НХЛ = N (+48), список АХЛ, клубов АХЛ, флаг). Всё, что «на клуб», рассчитано ровно на 30 мест:
//   +324  [30] u32   порядок: позиция в раунде → место клуба (индекс в слове: 81 + i)
//   +444  [30] u32   teamid места (111 + i)
//   +564        u32   маска клубов пользователя (бит места)
//   +568  [30] ×236  данные клуба: +0 полевых, +4 вратарей, +8 полевые[45], +188 вратари[6], +212 число по типу[6]
//   +7648 [30][50]   пики по раундам (1912 + 50·i + раунд)
//   +13648 [30]      деньги (3412 + i)
//   +13768 [30]      тип AI клуба (3442 + i)
//   +13888 [30][4]   нужды по типу игрока (16·(868 + i) + 4·тип)
//   +14368 [30][4]   ещё по типу (16·(898 + i) + 4·тип)
//   +14848 пул, +14852 его размер, +14856 под-объект AI (fe/fantasy.bin), до 15892.
// С меню на 32 (nhl_menu32) N = 32: места 30/31 каждого массива ложатся на начало следующего (порядок на teamid,
// teamid на маску и данные клуба 0, …, вторая таблица «по типу» — на указатель пула и под-объект AI). На экране порядка
// драфта «Zlín» и логотип s65535, через ~2 с после старта доски — падение (82B81150 / 82B792B8, 11.10, legacy-fe).
//
// Исправление: объект на 16896 байт, места 30/31 всех восьми массивов — в его хвосте (kX*). Мелкие методы класса
// подменены целиком (ниже), в больших — врезки nhllegacy_fantasy_hooks.toml: после вычисления индекса/смещения места
// (addi 81/111/3412/3442/868/898, mulli 236/59/50) место 30/31 переводится в хвост; поиск места по teamid (в оригинале
// до 30) — до N; цикл конструктора по местам — до 30, места 30/31 заполняет подмена конструктора тем же способом.
// Места < 30 и вне 0…31 (−1 «не найдено») — как в оригинале, так что при 30 клубах поведение прежнее.

#include <atomic>
#include <cmath>
#include <cstdint>
#include <cstring>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ppc.h>
#include <rex/runtime.h>
#include <rex/system/xmemory.h>

REXCVAR_DEFINE_BOOL(nhl_fd32, true, "NHLLegacy",
                    "Fantasy draft on 32 teams (only with nhl_teams = 32): places of teams 30/31 in a bigger "
                    "FantasyDraftLogic object (draft order, team ids, team data, picks) - no wrong teams in the "
                    "order and no crash on the fantasy draft board")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

bool NhlLegacyThirtyTwo();

extern "C" void __imp__sub_82B80C10(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_82B80898(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_82B79850(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_82B798E0(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_82B79940(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_82B79970(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_82B79AF8(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_82B79B40(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_82B79B90(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_82B79BA0(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_82B79BB0(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_82B80C98(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_82B80DB8(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_82B80E00(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_829CD158(PPCContext& ctx, uint8_t* base);
extern "C" void sub_82E53E80(PPCContext& ctx, uint8_t* base);  // выделение (размер, куча, имя, 0, выравнивание, 0)
extern "C" void sub_82B80898(PPCContext& ctx, uint8_t* base);  // конструктор FantasyDraftLogic (подмена ниже)
extern "C" void sub_82B79268(PPCContext& ctx, uint8_t* base);  // тип AI места (под-объект, место): fantasy.bin + rand(4)
extern "C" void sub_82B79728(PPCContext& ctx, uint8_t* base);  // деньги по типу AI (под-объект, тип)
extern "C" void sub_8297B8A0(PPCContext& ctx, uint8_t* base);  // rand(0…n−1)

namespace {

constexpr uint32_t kSize = 15892;         // объект в оригинале
constexpr uint32_t kBigSize = 16896;      // с хвостом мест 30/31
constexpr uint32_t kTail = 15904;         // начало хвоста (за объектом, выровнено на 16)
constexpr uint32_t kXA4 = 15904;          // [2][4] «нужды по типу» (+13888), шаг 16 — выравнивание 16
constexpr uint32_t kXB4 = 15936;          // [2][4] вторая таблица по типу (+14368)
constexpr uint32_t kXOrder = 15968;       // [2] порядок (+324)
constexpr uint32_t kXIds = 15976;         // [2] teamid (+444)
constexpr uint32_t kXMoney = 15984;       // [2] деньги (+13648)
constexpr uint32_t kXAi = 15992;          // [2] тип AI (+13768)
constexpr uint32_t kXTeam = 16000;        // [2] ×236 данные клуба (+568)
constexpr uint32_t kXPicks = 16472;       // [2][50] пики (+7648)
static_assert(kXA4 == kTail && kXPicks + 400 <= kBigSize, "tail");
static_assert(kXA4 % 16 == 0 && kXB4 % 16 == 0 && kXTeam % 4 == 0 && kXPicks % 4 == 0, "align");

constexpr uint32_t kInstance = 0x83BDC6A0;   // FantasyDraftLogic::mInstance
constexpr uint32_t kAllocName = 0x82087DB8;  // «FantasyDraftLogic::mInstance»
constexpr uint32_t kMoneyFactor = 0x82087DB0;  // double — множитель денег в конструкторе (lfd f31)
constexpr uint32_t kSub = 14856;             // под-объект AI
constexpr int kOld = 30;
constexpr int kMax = 32;

bool On() {
  static const bool on = REXCVAR_GET(nhl_fd32) && NhlLegacyThirtyTwo();
  return on;
}

uint8_t* GuestBase() {
  return rex::Runtime::instance()->memory()->TranslateVirtual<uint8_t*>(0);
}

uint8_t* Host(uint8_t* base, uint32_t a) {
  return base + a + (a >= 0xE0000000u ? 0x1000u : 0u);
}

uint32_t Ld(uint8_t* base, uint32_t a) {
  uint32_t v;
  std::memcpy(&v, Host(base, a), 4);
  return __builtin_bswap32(v);
}

uint16_t Ld16(uint8_t* base, uint32_t a) {
  uint16_t v;
  std::memcpy(&v, Host(base, a), 2);
  return __builtin_bswap16(v);
}

uint8_t Ld8(uint8_t* base, uint32_t a) {
  return *Host(base, a);
}

void St(uint8_t* base, uint32_t a, uint32_t v) {
  v = __builtin_bswap32(v);
  std::memcpy(Host(base, a), &v, 4);
}

bool Extra(int32_t i) {
  return i >= kOld && i < kMax;
}

// Адреса элементов по месту i (места 30/31 — в хвосте, остальные, в том числе −1, — как в оригинале).
uint32_t OrderAt(uint32_t obj, int32_t i) {
  return Extra(i) ? obj + kXOrder + 4u * uint32_t(i - kOld) : obj + 324u + 4u * uint32_t(i);
}
uint32_t IdsAt(uint32_t obj, int32_t i) {
  return Extra(i) ? obj + kXIds + 4u * uint32_t(i - kOld) : obj + 444u + 4u * uint32_t(i);
}
uint32_t TeamAt(uint32_t obj, int32_t i) {
  return Extra(i) ? obj + kXTeam + 236u * uint32_t(i - kOld) : obj + 568u + 236u * uint32_t(i);
}
uint32_t PickAt(uint32_t obj, int32_t i, int32_t round) {
  return Extra(i) ? obj + kXPicks + 200u * uint32_t(i - kOld) + 4u * uint32_t(round)
                  : obj + 4u * uint32_t(1912 + 50 * i + round);
}

int32_t Places(uint8_t* base, uint32_t obj) {
  return static_cast<int32_t>(Ld(base, obj + 48));
}

// Предел поиска места по teamid: в оригинале 30 (и при N < 30 тоже), при 31–32 клубах — N.
int32_t SearchLimit(uint8_t* base, uint32_t obj) {
  const int32_t n = Places(base, obj);
  return n > kOld ? (n < kMax ? n : kMax) : kOld;
}

// Позиция в раунде с учётом «змейки» (как 82B79AF8 / 82B80C98: в нечётном раунде — с конца).
int32_t SnakePos(uint8_t* base, uint32_t obj, int32_t pos, int32_t round) {
  if (round - 2 * (round / 2) != 0) {
    return Places(base, obj) - pos - 1;
  }
  return pos;
}

int32_t FindPlace(uint8_t* base, uint32_t obj, int32_t teamid) {
  const int32_t lim = SearchLimit(base, obj);
  for (int32_t i = 0; i < lim; ++i) {
    if (static_cast<int32_t>(Ld(base, IdsAt(obj, i))) == teamid) {
      return i;
    }
  }
  return -1;
}

// Значения конструктора для мест 30/31 (врезка в его цикле по местам): r17 — деньги по умолчанию (82B4F6D8),
// r20 — флаг «+3 к нуждам», r23 — множитель второй таблицы (*0x83A1C794).
thread_local uint32_t t_r17 = 0;
thread_local uint32_t t_r20 = 0;
thread_local uint32_t t_r23 = 0;
thread_local bool t_ctor_seen = false;

int32_t Fctiwz(double v) {
  if (std::isnan(v)) {
    return INT32_MIN;
  }
  if (v >= 2147483648.0) {
    return INT32_MAX;
  }
  if (v <= -2147483649.0) {
    return INT32_MIN;
  }
  return static_cast<int32_t>(std::trunc(v));
}

double LdDouble(uint8_t* base, uint32_t a) {
  uint64_t v;
  std::memcpy(&v, Host(base, a), 8);
  v = __builtin_bswap64(v);
  double d;
  std::memcpy(&d, &v, 8);
  return d;
}

// Места 30…N−1 так же, как цикл конструктора 82B809AC…82B80B00 (порядок −1 не ставим: его уже раздал 82B79850).
void InitExtraPlaces(PPCContext& ctx, uint8_t* base, uint32_t obj, uint32_t nhl_list, int32_t n) {
  const uint32_t sub = obj + kSub;
  for (int32_t i = kOld; i < n && i < kMax; ++i) {
    const uint32_t j = uint32_t(i - kOld);
    St(base, obj + kXIds + 4 * j, Ld(base, nhl_list + 4u * uint32_t(i)));
    ctx.r3.u64 = sub;
    ctx.r4.u64 = uint32_t(i);
    sub_82B79268(ctx, base);
    const uint32_t ai = ctx.r3.u32;
    St(base, obj + kXAi + 4 * j, ai);
    uint32_t money = t_r17;
    if (Ld8(base, obj + 321) != 0) {
      ctx.r3.u64 = sub;
      ctx.r4.u64 = ai;
      sub_82B79728(ctx, base);
      const int32_t v = ctx.r3.s32;
      // fcfid/fmul f31/frsp, frsp(r17), fmuls, fctiwz
      const float a = static_cast<float>(static_cast<double>(v) * LdDouble(base, kMoneyFactor));
      const float c = static_cast<float>(static_cast<double>(static_cast<int32_t>(t_r17)));
      const float p = static_cast<float>(static_cast<double>(a) * static_cast<double>(c));
      money = static_cast<uint32_t>(Fctiwz(p));
    }
    St(base, obj + kXMoney + 4 * j, money);
    // запись fe/fantasy.bin по типу AI: u16 [337 + тип] → младший байт b → запись 116 байт с +210
    const uint32_t b = Ld16(base, sub + 2u * (337u + ai)) & 0xFFu;
    const uint32_t rec = sub + 210u + 116u * b;
    for (uint32_t k = 0; k < 4; ++k) {
      uint32_t need = Ld8(base, rec + 112 + k);
      if ((t_r20 & 0xFF) != 0 && k != 3) {
        need += 3;
      }
      St(base, obj + kXA4 + 16 * j + 4 * k, need);
      St(base, obj + kXB4 + 16 * j + 4 * k, uint32_t(Ld8(base, rec + 108 + k)) * t_r23);
    }
  }
}

void Remap4(PPCRegister& r, int32_t k, uint32_t tail) {
  const int32_t i = r.s32 - k;
  if (Extra(i)) {
    r.u64 = tail / 4 + uint32_t(i - kOld);
  }
}

void Remap16(PPCRegister& r, int32_t k, uint32_t tail) {
  const int32_t i = r.s32 - k;
  if (Extra(i)) {
    r.u64 = tail / 16 + uint32_t(i - kOld);
  }
}

// r = stride·i (после mulli): место 30/31 → значение, которое при прежних прибавках даёт адрес в хвосте.
void RemapMul(PPCRegister& r, int64_t stride, int64_t at30) {
  const int64_t v = r.s64;
  if (v % stride != 0) {
    return;
  }
  const int64_t i = v / stride;
  if (i >= kOld && i < kMax) {
    r.s64 = at30 + stride * (i - kOld);
  }
}

std::atomic<int> g_logged{0};

}  // namespace

// ---- Фабрика и конструктор ---------------------------------------------------------------------------------------

// 82B80C10(лиг, список НХЛ, клубов НХЛ, список АХЛ, клубов АХЛ, флаг) → объект (и в 0x83BDC6A0).
extern "C" void sub_82B80C10(PPCContext& ctx, uint8_t* base) {
  if (!On()) {
    __imp__sub_82B80C10(ctx, base);
    return;
  }
  const uint64_t a3 = ctx.r3.u64, a4 = ctx.r4.u64, a5 = ctx.r5.u64, a6 = ctx.r6.u64, a7 = ctx.r7.u64,
                 a8 = ctx.r8.u64;
  ctx.r3.u64 = kBigSize;
  ctx.r4.u64 = 9;
  ctx.r5.u64 = kAllocName;
  ctx.r6.u64 = 0;
  ctx.r7.u64 = 16;
  ctx.r8.u64 = 0;
  sub_82E53E80(ctx, base);
  uint32_t obj = ctx.r3.u32;
  if (obj != 0) {
    std::memset(Host(base, obj + kSize), 0, kBigSize - kSize);
    ctx.r3.u64 = obj;
    ctx.r4.u64 = a3;
    ctx.r5.u64 = a4;
    ctx.r6.u64 = a5;
    ctx.r7.u64 = a6;
    ctx.r8.u64 = a7;
    ctx.r9.u64 = a8;
    sub_82B80898(ctx, base);
    obj = ctx.r3.u32;
  }
  St(base, kInstance, obj);
  ctx.r3.u64 = obj;
}

// Конструктор: цикл по местам врезкой NhlLegacyFd32CtorLoop идёт до 30, места 30/31 — здесь, после.
extern "C" void sub_82B80898(PPCContext& ctx, uint8_t* base) {
  if (!On()) {
    __imp__sub_82B80898(ctx, base);
    return;
  }
  const uint32_t obj = ctx.r3.u32;
  const uint32_t nhl_list = ctx.r5.u32;
  t_ctor_seen = false;
  __imp__sub_82B80898(ctx, base);
  const int32_t n = Places(base, obj);
  if (n > kOld && t_ctor_seen) {
    InitExtraPlaces(ctx, base, obj, nhl_list, n);
    ctx.r3.u64 = obj;
    if (g_logged.fetch_add(1) < 4) {
      REXLOG_INFO("[nhllegacy] fantasy draft on {} teams (nhl_fd32): places 30/31 beside the 30-team object {:08X} "
                  "(team ids {} {}, AI {} {}, money {} {})",
                  n, obj, Ld(base, obj + kXIds), Ld(base, obj + kXIds + 4), Ld(base, obj + kXAi),
                  Ld(base, obj + kXAi + 4), static_cast<int32_t>(Ld(base, obj + kXMoney)),
                  static_cast<int32_t>(Ld(base, obj + kXMoney + 4)));
    }
  } else if (n > kOld) {
    REXLOG_WARN("[nhllegacy] fantasy draft on {} teams: constructor loop hook not seen - places 30/31 not set", n);
  }
}

// ---- Мелкие методы целиком -----------------------------------------------------------------------------------------

// 82B79850: случайный порядок мест (порядок[i] = −1, затем места N−1…0 на случайные свободные позиции).
extern "C" void sub_82B79850(PPCContext& ctx, uint8_t* base) {
  if (!On()) {
    __imp__sub_82B79850(ctx, base);
    return;
  }
  const uint32_t obj = ctx.r3.u32;
  int32_t n = Places(base, obj);
  for (int32_t i = 0; i < n; ++i) {
    St(base, OrderAt(obj, i), 0xFFFFFFFFu);
    n = Places(base, obj);
  }
  for (int32_t place = n - 1; place >= 0; --place) {
    int32_t pos;
    do {
      ctx.r3.u64 = Ld(base, obj + 48);
      sub_8297B8A0(ctx, base);
      pos = ctx.r3.s32;
    } while (Ld(base, OrderAt(obj, pos)) != 0xFFFFFFFFu);
    St(base, OrderAt(obj, pos), uint32_t(place));
  }
}

// 82B798E0(объект, список teamid, число): порядок[k] = место клуба list[k].
extern "C" void sub_82B798E0(PPCContext& ctx, uint8_t* base) {
  if (!On()) {
    __imp__sub_82B798E0(ctx, base);
    return;
  }
  const uint32_t obj = ctx.r3.u32;
  const uint32_t list = ctx.r4.u32;
  const int32_t count = ctx.r5.s32;
  for (int32_t k = 0; k < count; ++k) {
    const int32_t n = Places(base, obj);
    const int32_t teamid = static_cast<int32_t>(Ld(base, list + 4u * uint32_t(k)));
    for (int32_t i = 0; i < n; ++i) {
      if (static_cast<int32_t>(Ld(base, IdsAt(obj, i))) == teamid) {
        St(base, OrderAt(obj, k), uint32_t(i));
        break;
      }
    }
  }
}

// 82B79940: выбирает ли сейчас клуб пользователя (бит места в маске +564).
extern "C" void sub_82B79940(PPCContext& ctx, uint8_t* base) {
  if (!On()) {
    __imp__sub_82B79940(ctx, base);
    return;
  }
  const uint32_t obj = ctx.r3.u32;
  const uint32_t place = Ld(base, OrderAt(obj, static_cast<int32_t>(Ld(base, obj + 308))));
  const uint32_t bit = (place & 63) < 32 ? (1u << (place & 31)) : 0u;
  ctx.r3.u64 = (bit & Ld(base, obj + 564)) != 0 ? 1 : 0;
}

// 82B79970(объект, место) → teamid.
extern "C" void sub_82B79970(PPCContext& ctx, uint8_t* base) {
  if (!On()) {
    __imp__sub_82B79970(ctx, base);
    return;
  }
  ctx.r3.u64 = Ld(base, IdsAt(ctx.r3.u32, ctx.r4.s32));
}

// 82B79AF8(объект, позиция, раунд) → пик места на этой позиции.
extern "C" void sub_82B79AF8(PPCContext& ctx, uint8_t* base) {
  if (!On()) {
    __imp__sub_82B79AF8(ctx, base);
    return;
  }
  const uint32_t obj = ctx.r3.u32;
  const int32_t round = ctx.r5.s32;
  const int32_t place = static_cast<int32_t>(Ld(base, OrderAt(obj, SnakePos(base, obj, ctx.r4.s32, round))));
  ctx.r3.u64 = Ld(base, PickAt(obj, place, round));
}

// 82B79B40(объект, teamid, раунд) → пик клуба (поиск места: в оригинале до 30).
extern "C" void sub_82B79B40(PPCContext& ctx, uint8_t* base) {
  if (!On()) {
    __imp__sub_82B79B40(ctx, base);
    return;
  }
  const uint32_t obj = ctx.r3.u32;
  ctx.r3.u64 = Ld(base, PickAt(obj, FindPlace(base, obj, ctx.r4.s32), ctx.r5.s32));
}

// 82B79B90 / 82B79BA0(объект, место) → вратарей / полевых в клубе.
extern "C" void sub_82B79B90(PPCContext& ctx, uint8_t* base) {
  if (!On()) {
    __imp__sub_82B79B90(ctx, base);
    return;
  }
  ctx.r3.u64 = Ld(base, TeamAt(ctx.r3.u32, ctx.r4.s32) + 4);
}

extern "C" void sub_82B79BA0(PPCContext& ctx, uint8_t* base) {
  if (!On()) {
    __imp__sub_82B79BA0(ctx, base);
    return;
  }
  ctx.r3.u64 = Ld(base, TeamAt(ctx.r3.u32, ctx.r4.s32));
}

// 82B79BB0(объект, место, номер, вратарь?) → игрок клуба (вратари с +188, полевые с +8).
extern "C" void sub_82B79BB0(PPCContext& ctx, uint8_t* base) {
  if (!On()) {
    __imp__sub_82B79BB0(ctx, base);
    return;
  }
  const uint32_t at = TeamAt(ctx.r3.u32, ctx.r4.s32) + ((ctx.r6.u32 & 0xFF) != 0 ? 188u : 8u) + 4u * ctx.r5.u32;
  ctx.r3.u64 = Ld(base, at);
}

// 82B80C98(объект, позиция, раунд) → teamid клуба на позиции.
extern "C" void sub_82B80C98(PPCContext& ctx, uint8_t* base) {
  if (!On()) {
    __imp__sub_82B80C98(ctx, base);
    return;
  }
  const uint32_t obj = ctx.r3.u32;
  const int32_t place = static_cast<int32_t>(Ld(base, OrderAt(obj, SnakePos(base, obj, ctx.r4.s32, ctx.r5.s32))));
  ctx.r3.u64 = Ld(base, IdsAt(obj, place));
}

// 82B80DB8 / 82B80E00(объект, teamid) → вратарей / полевых клуба (поиск места: в оригинале до 30).
extern "C" void sub_82B80DB8(PPCContext& ctx, uint8_t* base) {
  if (!On()) {
    __imp__sub_82B80DB8(ctx, base);
    return;
  }
  const uint32_t obj = ctx.r3.u32;
  ctx.r3.u64 = Ld(base, TeamAt(obj, FindPlace(base, obj, ctx.r4.s32)) + 4);
}

extern "C" void sub_82B80E00(PPCContext& ctx, uint8_t* base) {
  if (!On()) {
    __imp__sub_82B80E00(ctx, base);
    return;
  }
  const uint32_t obj = ctx.r3.u32;
  ctx.r3.u64 = Ld(base, TeamAt(obj, FindPlace(base, obj, ctx.r4.s32)));
}

// 829CD158 (меню франшизы, объект драфта — меню +9252) → teamid клуба, который выбирает сейчас.
extern "C" void sub_829CD158(PPCContext& ctx, uint8_t* base) {
  if (!On()) {
    __imp__sub_829CD158(ctx, base);
    return;
  }
  const uint32_t obj = Ld(base, ctx.r3.u32 + 9252);
  const int32_t place = static_cast<int32_t>(Ld(base, OrderAt(obj, static_cast<int32_t>(Ld(base, obj + 308)))));
  ctx.r3.u64 = Ld(base, IdsAt(obj, place));
}

// ---- Врезки (nhllegacy_fantasy_hooks.toml) -----------------------------------------------------------------------

// Конструктор 82B80AFC `cmpw cr6, r21, r11` (конец цикла по местам): предел 30, значения для мест 30/31 — себе.
void NhlLegacyFd32CtorLoop(PPCRegister& r11, PPCRegister& r17, PPCRegister& r20, PPCRegister& r23) {
  if (!On()) {
    return;
  }
  t_r17 = r17.u32;
  t_r20 = r20.u32;
  t_r23 = r23.u32;
  t_ctor_seen = true;
  if (r11.s32 > kOld) {
    r11.s64 = kOld;
  }
}

// После `addi r, место, K` (индекс слова от объекта): порядок 81, teamid 111, деньги 3412, тип AI 3442.
void NhlLegacyFd32Order(PPCRegister& r) {
  if (On()) {
    Remap4(r, 81, kXOrder);
  }
}
void NhlLegacyFd32Ids(PPCRegister& r) {
  if (On()) {
    Remap4(r, 111, kXIds);
  }
}
void NhlLegacyFd32Money(PPCRegister& r) {
  if (On()) {
    Remap4(r, 3412, kXMoney);
  }
}
void NhlLegacyFd32Ai(PPCRegister& r) {
  if (On()) {
    Remap4(r, 3442, kXAi);
  }
}

// После `addi r, место, 868 / 898` (индекс 16-байтной строки по типу).
void NhlLegacyFd32Need(PPCRegister& r) {
  if (On()) {
    Remap16(r, 868, kXA4);
  }
}
void NhlLegacyFd32Need2(PPCRegister& r) {
  if (On()) {
    Remap16(r, 898, kXB4);
  }
}

// После `mulli r, место, 236` (дальше + объект и смещения от +568), `mulli r, место, 59` (дальше + тип + 195, ×4),
// `mulli r, место, 50` (дальше + раунд + 1912, ×4).
void NhlLegacyFd32Team(PPCRegister& r) {
  if (On()) {
    RemapMul(r, 236, int64_t(kXTeam) - 568);
  }
}
void NhlLegacyFd32Team59(PPCRegister& r) {
  if (On()) {
    RemapMul(r, 59, int64_t(kXTeam / 4) - 142);
  }
}
void NhlLegacyFd32Picks(PPCRegister& r) {
  if (On()) {
    RemapMul(r, 50, int64_t(kXPicks / 4) - 1912);
  }
}

// 82B8D1C8 перед поиском места по teamid (в оригинале до 30): при N > 30 — поиск до N, место → r11, переход на
// 82B8D210 (true); иначе — исходный цикл (false).
bool NhlLegacyFd32FindPlace(PPCRegister& r3, PPCRegister& r4, PPCRegister& r11) {
  if (!On()) {
    return false;
  }
  uint8_t* base = GuestBase();
  const uint32_t obj = r3.u32;
  if (Places(base, obj) <= kOld) {
    return false;
  }
  r11.s64 = FindPlace(base, obj, r4.s32);
  return true;
}
