// Охота на падения в скриптах экранов (ActionScript): последние вызовы родных функций ION_* — по чтению их
// аргументов (82465270, «аргумент i со стека AS»: его зовут почти все обёртки родных функций, lr — адрес в
// обёртке). nhl_astrace = true — запоминать 256 последних вызовов; при падении — в nhllegacy_crash.txt.
// Имена по адресу обёртки — таблицы регистрации родных функций (8247DDF8(класс, имя, 82465408(обёртка))).

#include <atomic>
#include <cstdint>
#include <cstdio>

#include <rex/cvar.h>
#include <rex/ppc.h>

REXCVAR_DEFINE_BOOL(nhl_astrace, false, "NHLLegacy",
                    "Crash hunt: remember the last 256 ActionScript native calls (argument reads of ION_* "
                    "wrappers) and print them into nhllegacy_crash.txt")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

extern "C" void __imp__sub_82465270(PPCContext& ctx, uint8_t* base);  // AS: аргумент i

namespace {

constexpr uint32_t kSize = 256;
std::atomic<uint32_t> g_pos{0};
uint32_t g_lr[kSize];
uint32_t g_arg[kSize];
uint32_t g_value[kSize];

bool Enabled() {
  static const bool on = REXCVAR_GET(nhl_astrace);
  return on;
}

}  // namespace

extern "C" void sub_82465270(PPCContext& ctx, uint8_t* base) {
  if (!Enabled()) {
    __imp__sub_82465270(ctx, base);
    return;
  }
  const uint32_t lr = static_cast<uint32_t>(ctx.lr);
  const uint32_t arg = ctx.r3.u32;
  __imp__sub_82465270(ctx, base);
  const uint32_t p = g_pos.fetch_add(1, std::memory_order_relaxed) % kSize;
  g_lr[p] = lr;
  g_arg[p] = arg;
  g_value[p] = ctx.r3.u32;
}

void NhlLegacyAsTraceDump(FILE* f) {
  if (!Enabled()) {
    return;
  }
  const uint32_t end = g_pos.load(std::memory_order_relaxed);
  const uint32_t n = end < 160 ? end : 160;
  fprintf(f, "-- last %u ActionScript native argument reads (lr in wrapper, arg index, AS value), oldest first\n", n);
  for (uint32_t k = end - n; k != end; ++k) {
    const uint32_t p = k % kSize;
    fprintf(f, "as %08X arg %u value %08X\n", g_lr[p], g_arg[p], g_value[p]);
  }
}
