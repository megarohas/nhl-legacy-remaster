// Монеты без предела (nhl_coins_no_cap; docs/coins.md, «Как снять предел»).
//
// 829F7368 прибавляет бонус за матч к балансу и режет сумму по пределу из блока монет сейва PROFILE (+4, 2 500). EA
// обнуляла баланс переводом в HUT на своём сервере, без него счёт встаёт навсегда. Предел приходит из сейва, поэтому
// константа 0x820504A8 ничего не даёт: поднимаем поле перед каждым начислением, дальше игра сама пишет его в профиль.

#include <cstdint>
#include <cstring>

#include <rex/cvar.h>
#include <rex/ppc.h>

REXCVAR_DEFINE_BOOL(nhl_coins_no_cap, true, "NHLLegacy",
                    "Match coins keep adding up past the profile cap of 2500 (it was emptied by EA servers)");

extern "C" void __imp__sub_829F7368(PPCContext& ctx, uint8_t* base);  // начисление монет за матч

namespace {

constexpr uint32_t kRewardsOffset = 0x10204;  // объект бонуса за матч → блок монет
constexpr uint32_t kCapOffset = 4;
constexpr uint32_t kNoCap = 2000000000u;

uint32_t Load32(uint8_t* base, uint32_t a) {
  uint32_t v;
  std::memcpy(&v, base + a, 4);
  return __builtin_bswap32(v);
}

void Store32(uint8_t* base, uint32_t a, uint32_t v) {
  v = __builtin_bswap32(v);
  std::memcpy(base + a, &v, 4);
}

}  // namespace

extern "C" void sub_829F7368(PPCContext& ctx, uint8_t* base) {
  if (REXCVAR_GET(nhl_coins_no_cap)) {
    if (const uint32_t rewards = Load32(base, ctx.r3.u32 + kRewardsOffset)) {
      Store32(base, rewards + kCapOffset, kNoCap);
    }
  }
  __imp__sub_829F7368(ctx, base);
}
