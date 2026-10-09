// Разведка драфта франшизы (docs/legacy-port.md, «Второй драфт франшизы»): кого игра выбирает и откуда.
//
// Пул драфта — объект с +3372: до 1500 записей по 22 байта (+0 u16 playerid, +11 — команда, 255 — свободен), число —
// +3368 (u16). 82B60848 заполняет его из leaguerookiedata (82A341D0), если пул пуст (82B65C60). Выбор на драфте
// записывает 82B4A150 (r4 — индекс игрока в leagueplayerbiotable, r5 — команда, r6 — год, r7 — раунд, r8 — номер).
// cvar nhl_drafttrace (по умолчанию выкл.): журнал nhllegacy_draft.log рядом с exe — загрузка пула (объект, число,
// playerid), каждый выбор (игрок, команда, раунд, номер, есть ли игрок в пуле и в каком состоянии запись пула)
// и стек хоста для первых 12 выборов не из пула.

#if defined(_WIN32)
#include <windows.h>
#endif

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <string>
#include <unordered_map>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ppc.h>

#include "nhllegacy_debug.h"

REXCVAR_DEFINE_BOOL(nhl_drafttrace, false, "NHLLegacy",
                    "Diagnostics: log the franchise draft pool loads and every draft pick to nhllegacy_draft.log")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

extern "C" void __imp__sub_82B60848(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_82B4A150(PPCContext& ctx, uint8_t* base);

namespace {

constexpr uint32_t kPool = 3372;
constexpr uint32_t kPoolCount = 3368;
constexpr uint32_t kRec = 22;

bool On() {
  static const bool on = REXCVAR_GET(nhl_drafttrace);
  return on;
}

uint8_t* Host(uint8_t* base, uint32_t a) {
  return base + a + (a >= 0xE0000000u ? 0x1000u : 0u);
}

uint16_t Ld16(uint8_t* base, uint32_t a) {
  uint16_t v;
  std::memcpy(&v, Host(base, a), 2);
  return __builtin_bswap16(v);
}

std::mutex g_mu;
uint32_t g_pool_obj = 0;
int g_bad_stacks = 0;

FILE* Log() {
  static FILE* f = [] {
    wchar_t exe[MAX_PATH];
    GetModuleFileNameW(nullptr, exe, MAX_PATH);
    std::wstring p(exe);
    p = p.substr(0, p.find_last_of(L"\\/") + 1) + L"nhllegacy_draft.log";
    return _wfopen(p.c_str(), L"a");
  }();
  return f;
}

void Stamp(FILE* f) {
  SYSTEMTIME t;
  GetLocalTime(&t);
  fprintf(f, "%02u:%02u:%02u.%03u ", t.wHour, t.wMinute, t.wSecond, t.wMilliseconds);
}

// Где игрок в пуле: номер записи или −1; при obj = 0 — −2.
int FindInPool(uint8_t* base, uint32_t obj, uint32_t pid, uint8_t* team_byte) {
  if (!obj) {
    return -2;
  }
  const int n = Ld16(base, obj + kPoolCount);
  for (int i = 0; i < n && i < 1500; ++i) {
    const uint32_t rec = obj + kPool + kRec * static_cast<uint32_t>(i);
    if (Ld16(base, rec) == pid) {
      *team_byte = *Host(base, rec + 11);
      return i;
    }
  }
  return -1;
}

}  // namespace

extern "C" void sub_82B60848(PPCContext& ctx, uint8_t* base) {
  if (!On()) {
    __imp__sub_82B60848(ctx, base);
    return;
  }
  const uint32_t obj = ctx.r3.u32;
  __imp__sub_82B60848(ctx, base);
  std::lock_guard<std::mutex> lock(g_mu);
  g_pool_obj = obj;
  FILE* f = Log();
  if (!f) {
    return;
  }
  const int n = Ld16(base, obj + kPoolCount);
  Stamp(f);
  fprintf(f, "pool load: object %08X count %d lr %08X\n  pids:", obj, n, static_cast<uint32_t>(ctx.lr));
  for (int i = 0; i < n && i < 1500; ++i) {
    const uint32_t rec = obj + kPool + kRec * static_cast<uint32_t>(i);
    fprintf(f, " %u/%u", Ld16(base, rec), *Host(base, rec + 11));
  }
  fprintf(f, "\n");
  fflush(f);
}

extern "C" void sub_82B4A150(PPCContext& ctx, uint8_t* base) {
  if (On()) {
    std::lock_guard<std::mutex> lock(g_mu);
    if (FILE* f = Log()) {
      const uint32_t pid = ctx.r4.u32;
      uint8_t tb = 0;
      const int at = FindInPool(base, g_pool_obj, pid, &tb);
      Stamp(f);
      fprintf(f, "pick: player %u team %d year %d round %d pos %d flag %u lr %08X | pool %08X: %s", pid, ctx.r5.s32,
              ctx.r6.s32, ctx.r7.s32, ctx.r8.s32, ctx.r9.u32 & 0xFF, static_cast<uint32_t>(ctx.lr), g_pool_obj,
              at >= 0 ? "in pool" : (at == -1 ? "NOT IN POOL" : "no pool yet"));
      if (at >= 0) {
        fprintf(f, " (record %d, team byte %u)", at, tb);
      }
      fprintf(f, "\n");
      if (at == -1 && g_bad_stacks < 12) {
        ++g_bad_stacks;
        CONTEXT c{};
        RtlCaptureContext(&c);
        DWORD64 frames[32];
        const int k = NhlLegacyCaptureStack(c, frames, 32);
        std::lock_guard<std::mutex> dbg(NhlLegacyDbghelpMutex());
        NhlLegacyEnsureSymbols();
        for (int i = 0; i < k; ++i) {
          NhlLegacyWriteFrame(f, i, frames[i]);
        }
      }
      fflush(f);
    }
  }
  __imp__sub_82B4A150(ctx, base);
}
