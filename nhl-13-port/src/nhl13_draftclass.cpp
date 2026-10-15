// Класс драфта франшизы без переростков (docs/draft-pool.md, docs/franchise-seasons.md §8).
//
// Класс первого драфта игра собирает один раз — при создании франшизы (82934FB0) — и сразу пишет в сейв
// (leaguerookiedata). Реальных игроков даёт 8291F160: 828C91B8(список, год + 1) — «isdraftable = 1 и
// draftyear ≤ год драфта», каждому запись пула 8291BBE0 и счётчик его юниорской лиги (+1044 + 4·лига); по
// счётчикам 8285B2D0 потом догенерирует вымышленных до квот лиг. Флаг isdraftable при создании получают все
// игроки клубов CHL без прав НХЛ, возраст не проверяется, а составы CHL в базе — 2012 года: в класс шли
// ~1200 юниоров 1991–96 г. р. (30–35 лет), и вымышленные для CHL не создавались.
//
// Подмена (nhl_draftclass_age): тот же 8291F160, но без тех, кому к драфту больше 20 лет — их список даёт тот
// же запрос с годом драфта − 3 (draftyear ≤ год драфта − 3, т. е. 18 лет им исполнилось три и более драфта
// назад). Остаются draftyear год − 2 … год (18–20 лет, как у возрастного отсева 828DDD78 и у вымышленных игры);
// счётчики лиг считают только оставшихся, поэтому игра сама догенерирует CHL по квотам (draftpool, 09.10.2026:
// класс 262, из них вымышленных WHL 40 / OHL 40 / QMJHL 35).

#include <cstdint>
#include <cstring>
#include <unordered_set>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ppc.h>

REXCVAR_DEFINE_BOOL(nhl_draftclass_age, false, "NHL13",
                    "Franchise draft class: real players only up to 20 years old at the draft (draftyear >= draft "
                    "year - 2); the game generates the rest of the class by junior league quotas")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

extern "C" void __imp__sub_8291F160(PPCContext& ctx, uint8_t* base);  // реальные игроки класса
extern "C" void sub_828D3C78(PPCContext& ctx, uint8_t* base);         // лига (+12 — год)
extern "C" void sub_828AA010(PPCContext& ctx, uint8_t* base);         // список: создать
extern "C" void sub_828AA088(PPCContext& ctx, uint8_t* base);         // список: удалить
extern "C" void sub_828C91B8(PPCContext& ctx, uint8_t* base);         // запрос draftable, draftyear ≤ год
extern "C" void sub_8289C598(PPCContext& ctx, uint8_t* base);         // i-й элемент списка
extern "C" void sub_828CCAA0(PPCContext& ctx, uint8_t* base);         // запись игрока в буфер
extern "C" void sub_8290D288(PPCContext& ctx, uint8_t* base);
extern "C" void sub_8290D3A8(PPCContext& ctx, uint8_t* base);         // номер юниорской лиги
extern "C" void sub_8291BBE0(PPCContext& ctx, uint8_t* base);         // запись пула

namespace {

constexpr uint32_t kPoolObject = 0x83987B6C;  // указатель на объект пула
constexpr uint32_t kRecord = 1088;            // буфер записи игрока в объекте сборки
constexpr uint32_t kJuniorLeague = 1214;
constexpr int32_t kMaxPool = 1500;

uint8_t* Host(uint8_t* base, uint32_t addr) {
  return base + addr + (addr >= 0xE0000000u ? 0x1000u : 0u);
}
uint32_t Load32(uint8_t* base, uint32_t a) {
  uint32_t v;
  std::memcpy(&v, Host(base, a), 4);
  return __builtin_bswap32(v);
}
void Store32(uint8_t* base, uint32_t a, uint32_t v) {
  v = __builtin_bswap32(v);
  std::memcpy(Host(base, a), &v, 4);
}

bool Enabled() {
  static const bool on = [] {
    const bool v = REXCVAR_GET(nhl_draftclass_age);
    REXLOG_INFO("[nhl13] draft class without players older than 20 (nhl_draftclass_age): {}", v ? "on" : "off");
    return v;
  }();
  return on;
}

}  // namespace

// 8291F160(объект сборки) → число реальных игроков в пуле.
extern "C" void sub_8291F160(PPCContext& ctx, uint8_t* base) {
  if (!Enabled()) {
    __imp__sub_8291F160(ctx, base);
    return;
  }
  const uint32_t self = ctx.r3.u32;
  const uint64_t saved_r1 = ctx.r1.u64;
  // два объекта-списка (по 0x40 байт, 828AA010) — во временной области гостевого стека ниже текущего кадра;
  // вызываемые функции пишут ниже frame
  const uint32_t frame = (ctx.r1.u32 - 0x200) & ~0xFu;
  const uint32_t list = frame + 0x40;
  const uint32_t old_list = frame + 0x100;
  std::memset(Host(base, frame), 0, 0x200);
  ctx.r1.u64 = frame;

  sub_828D3C78(ctx, base);
  const int32_t year = static_cast<int32_t>(Load32(base, ctx.r3.u32 + 12));
  ctx.r3.u64 = list;
  sub_828AA010(ctx, base);
  ctx.r3.u64 = list;
  ctx.r4.s64 = year + 1;
  sub_828C91B8(ctx, base);
  ctx.r3.u64 = old_list;
  sub_828AA010(ctx, base);
  ctx.r3.u64 = old_list;
  ctx.r4.s64 = year + 1 - 3;
  sub_828C91B8(ctx, base);

  std::unordered_set<uint32_t> old;
  {
    const int32_t n = static_cast<int32_t>(Load32(base, old_list + 12));
    const uint32_t items = Load32(base, old_list + 8);
    for (int32_t k = 0; k < n && items; ++k) {
      old.insert(Load32(base, items + 4u * static_cast<uint32_t>(k)));
    }
  }
  const int32_t n = static_cast<int32_t>(Load32(base, list + 12));
  const uint32_t pool = Load32(base, kPoolObject);
  const uint32_t rec = self + kRecord;
  int32_t added = 0;
  int32_t skipped = 0;
  for (int32_t i = 0; i < n && i < kMaxPool; ++i) {
    ctx.r3.u64 = list;
    ctx.r4.s64 = i;
    sub_8289C598(ctx, base);
    const uint32_t player = ctx.r3.u32;
    if (old.count(player)) {
      ++skipped;
      continue;
    }
    ctx.r3.u64 = list;
    ctx.r4.u64 = player;
    ctx.r5.u64 = rec;
    sub_828CCAA0(ctx, base);
    ctx.r3.u64 = self;
    sub_8290D288(ctx, base);
    const uint64_t kind = ctx.r3.u64;
    ctx.r3.u64 = self;
    ctx.r4.s64 = static_cast<int8_t>(*Host(base, self + kJuniorLeague));
    sub_8290D3A8(ctx, base);
    const uint64_t league = ctx.r3.u64;
    const uint32_t counter = self + ((static_cast<uint32_t>(league) + 261u) << 2);
    Store32(base, counter, Load32(base, counter) + 1);
    ctx.r3.u64 = pool;
    ctx.r4.u64 = kind;
    ctx.r5.u64 = league;
    ctx.r6.u64 = rec;
    sub_8291BBE0(ctx, base);
    ++added;
  }
  ctx.r3.u64 = old_list;
  sub_828AA088(ctx, base);
  ctx.r3.u64 = list;
  sub_828AA088(ctx, base);
  ctx.r1.u64 = saved_r1;
  REXLOG_INFO("[nhl13] draft class {}: real players {} of {} (older than 20 at the draft, draftyear <= {}: {} "
              "skipped)",
              year + 1, added, n, year + 1 - 3, skipped);
  ctx.r3.u64 = static_cast<uint64_t>(added);
}
