// Имя пользователя (nhl_user_name) и журнал сейвов (nhl_save_trace), docs/legacy-port.md, «Имя пользователя».
//
// У SDK имя зашито: UserProfile::UserProfile — name_ = "User", cvar и сеттера нет. Код игры берёт его только через
// два импорта, XamUserGetName и XamUserGetSigninInfo (остальные пути SDK, XamUserGetGamerTag, игра не импортирует).
// Как и в nhllegacy_input_lock.cpp, определение __imp__* в exe сильнее библиотеки импорта rexruntime: здесь зовём
// оригинал из DLL и поверх его ответа кладём своё имя. SDK не пересобирается.
//
// name_ в UserProfile остаётся "User", поэтому не меняется и путь ContentManager::ResolveGameUserContentPath
// (<root>/<title>/profile/User), а сейвы лежат по XUID и от имени не зависят.

#include <cstdint>
#include <cstring>
#include <string>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ppc.h>

REXCVAR_DEFINE_STRING(nhl_user_name, "", "NHLLegacy",
                      "Player name the game sees (gamertag, up to 15 UTF-8 bytes); empty keeps the SDK default, User")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);
REXCVAR_DEFINE_BOOL(nhl_save_trace, false, "NHLLegacy",
                    "Diagnostics: log every save the game opens or creates")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

#if defined(_WIN32)
#include <windows.h>

namespace {

using GuestFn = void (*)(PPCContext&, uint8_t*);

// Как у gamertag: 15 байт и нуль. Буфер X_USER_SIGNIN_INFO.name и XamUserGetName — 16 байт, текст игра читает как UTF-8.
constexpr uint32_t kNameBuffer = 16;
constexpr uint32_t kSigninInfoNameOffset = 0x18;

GuestFn RuntimeExport(const char* name) {
  HMODULE runtime = nullptr;
  for (const char* dll : {"rexruntimerd.dll", "rexruntime.dll", "rexruntimed.dll"}) {
    if ((runtime = GetModuleHandleA(dll)) != nullptr) {
      break;
    }
  }
  auto fn = runtime ? reinterpret_cast<GuestFn>(GetProcAddress(runtime, name)) : nullptr;
  if (!fn) {
    REXLOG_ERROR("[nhllegacy] user: {} not found in rexruntime (module {})", name, static_cast<void*>(runtime));
  }
  return fn;
}

uint8_t* Guest(uint8_t* base, uint32_t a) {
  return base + a + (a >= 0xE0000000u ? 0x1000u : 0u);
}

// Имя из cvar, обрезанное до буфера игры; пустое — оставить ответ SDK.
const std::string& UserName() {
  static const std::string name = [] {
    std::string s = REXCVAR_GET(nhl_user_name);
    if (s.size() >= kNameBuffer) {
      size_t n = kNameBuffer - 1;
      while (n > 0 && (static_cast<uint8_t>(s[n]) & 0xC0) == 0x80) {
        --n;  // UTF-8: не резать посреди буквы, игра понимает кириллицу
      }
      s.resize(n);
    }
    if (!s.empty()) {
      REXLOG_INFO("[nhllegacy] user name: {}", s);
    }
    return s;
  }();
  return name;
}

void PutName(uint8_t* base, uint32_t guest, uint32_t size) {
  const std::string& name = UserName();
  if (name.empty() || guest == 0 || size == 0) {
    return;
  }
  uint8_t* out = Guest(base, guest);
  const uint32_t n = std::min<uint32_t>(static_cast<uint32_t>(name.size()), size - 1);
  std::memcpy(out, name.data(), n);
  std::memset(out + n, 0, size - n);
}

}  // namespace

// XamUserGetName(user r3, char* buffer r4, buffer_len r5): r3 = 0 — успех.
extern "C" void __imp__XamUserGetName(PPCContext& ctx, uint8_t* base) {
  static GuestFn original = RuntimeExport("__imp__XamUserGetName");
  const uint32_t user = ctx.r3.u32, buffer = ctx.r4.u32, size = ctx.r5.u32;
  if (original) {
    original(ctx, base);
  } else {
    ctx.r3.u64 = 0x525;  // X_ERROR_NO_SUCH_USER
  }
  if (ctx.r3.u32 == 0 && user == 0) {
    PutName(base, buffer, std::min(size, kNameBuffer));
  }
}

// XamUserGetSigninInfo(user r3, flags r4, X_USER_SIGNIN_INFO* r5): имя — char[16] со смещения 0x18.
extern "C" void __imp__XamUserGetSigninInfo(PPCContext& ctx, uint8_t* base) {
  static GuestFn original = RuntimeExport("__imp__XamUserGetSigninInfo");
  const uint32_t user = ctx.r3.u32, info = ctx.r5.u32;
  if (original) {
    original(ctx, base);
  } else {
    ctx.r3.u64 = 0x525;
  }
  if (ctx.r3.u32 == 0 && user == 0 && info != 0) {
    PutName(base, info + kSigninInfoNameOffset, kNameBuffer);
  }
}

// Сейвы игра открывает не импортом, а через 836FB370: она сама находит XamContentCreateInternal по номеру экспорта.
// r4 — имя корня, r5 — XCONTENT_AGGREGATE_DATA, r6 — флаги: младшие 4 бита 3 — открыть, 1/2 — создать, 4 — открыть или создать.
extern "C" void __imp__sub_836FB370(PPCContext& ctx, uint8_t* base);
extern "C" void sub_836FB370(PPCContext& ctx, uint8_t* base) {
  if (REXCVAR_GET(nhl_save_trace) && ctx.r5.u32 != 0) {
    char file[43] = {};
    std::memcpy(file, Guest(base, ctx.r5.u32) + 0x108, 42);
    char root[33] = {};
    if (ctx.r4.u32 != 0) {
      std::memcpy(root, Guest(base, ctx.r4.u32), 32);
    }
    REXLOG_INFO("[nhllegacy] save: root {} flags {:X} file {}", root, ctx.r6.u32, file);
  }
  __imp__sub_836FB370(ctx, base);
}

#endif
