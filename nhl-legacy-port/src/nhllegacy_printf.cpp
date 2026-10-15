// Разведка: отладочная печать игры (printf CRT гостя, 83076D88) в лог порта — docs/legacy-port.md, «Порча текстур в первом
// матче сессии». В игре 101 вызов, среди них сообщения распределителя памяти: «XenonVideoAllocator memory allocation
// failed, size %d, type %s, MEMCAT_VIDEO», «Pre-allocator memory allocation (using malloc() instead)…», сводка памяти
// при запуске. cvar nhl_game_printf (по умолчанию выкл.): строка «[game] …» в лог. Формат разбирается здесь: %d %i %u
// %x %X %o %c %s %p %f %g %e (длина ll/l/h пропускается), целые и double — из r4…r10 по порядку (так их кладёт
// пролог вызываемой: std r4…r10 в область аргументов), дальше — со стека вызывающего.

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ppc.h>

REXCVAR_DEFINE_BOOL(nhl_game_printf, false, "NHLLegacy",
                    "Diagnostics: copy the game's own debug printf output (83076D88) to the log as [game] lines")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

extern "C" void __imp__sub_83076D88(PPCContext& ctx, uint8_t* base);

namespace {

uint8_t* Host(uint8_t* base, uint32_t a) {
  return base + a + (a >= 0xE0000000u ? 0x1000u : 0u);
}

bool Plausible(uint32_t a) {
  return a >= 0x40000000u && a < 0xFFFF0000u;
}

uint64_t Ld64(uint8_t* base, uint32_t a) {
  uint64_t v;
  std::memcpy(&v, Host(base, a), 8);
  return __builtin_bswap64(v);
}

std::string GuestString(uint8_t* base, uint32_t a, size_t max = 512) {
  std::string s;
  if (!Plausible(a)) {
    return "(null)";
  }
  for (size_t i = 0; i < max; ++i) {
    const char c = static_cast<char>(*Host(base, a + uint32_t(i)));
    if (!c) {
      break;
    }
    s += c;
  }
  return s;
}

struct Args {
  PPCContext& ctx;
  uint8_t* base;
  int next = 0;
  uint64_t Next() {
    const int i = next++;
    switch (i) {
      case 0: return ctx.r4.u64;
      case 1: return ctx.r5.u64;
      case 2: return ctx.r6.u64;
      case 3: return ctx.r7.u64;
      case 4: return ctx.r8.u64;
      case 5: return ctx.r9.u64;
      case 6: return ctx.r10.u64;
      default:
        // дальше — область аргументов вызывающего: слот r3 — r1 + 16, r4 — r1 + 24, …, аргумент i — r1 + 24 + 8·i
        return Ld64(base, ctx.r1.u32 + 24 + 8u * uint32_t(i));
    }
  }
};

std::string Format(uint8_t* base, PPCContext& ctx, const std::string& fmt) {
  Args args{ctx, base};
  std::string out;
  for (size_t i = 0; i < fmt.size(); ++i) {
    const char c = fmt[i];
    if (c != '%') {
      out += c;
      continue;
    }
    size_t j = i + 1;
    std::string spec = "%";
    while (j < fmt.size() && std::strchr("-+ #0123456789.*", fmt[j])) {
      if (fmt[j] == '*') {
        spec += std::to_string(static_cast<int32_t>(args.Next()));
      } else {
        spec += fmt[j];
      }
      ++j;
    }
    while (j < fmt.size() && std::strchr("hlLqjzt", fmt[j])) {
      ++j;  // длина: значение всё равно 64-битное из регистра
    }
    if (j >= fmt.size()) {
      out += spec;
      break;
    }
    const char conv = fmt[j];
    char buf[512];
    switch (conv) {
      case '%': out += '%'; break;
      case 'd': case 'i':
        std::snprintf(buf, sizeof(buf), (spec + "lld").c_str(), static_cast<long long>(static_cast<int32_t>(args.Next())));
        out += buf;
        break;
      case 'u': case 'x': case 'X': case 'o':
        std::snprintf(buf, sizeof(buf), (spec + "ll" + conv).c_str(),
                      static_cast<unsigned long long>(static_cast<uint32_t>(args.Next())));
        out += buf;
        break;
      case 'c':
        out += static_cast<char>(args.Next() & 0xFF);
        break;
      case 'p':
        std::snprintf(buf, sizeof(buf), "%08X", static_cast<uint32_t>(args.Next()));
        out += buf;
        break;
      case 's': {
        const std::string s = GuestString(base, static_cast<uint32_t>(args.Next()));
        std::snprintf(buf, sizeof(buf), (spec + "s").c_str(), s.c_str());
        out += buf;
        break;
      }
      case 'f': case 'F': case 'g': case 'G': case 'e': case 'E': {
        const uint64_t raw = args.Next();
        double d;
        std::memcpy(&d, &raw, 8);
        std::snprintf(buf, sizeof(buf), (spec + conv).c_str(), d);
        out += buf;
        break;
      }
      default:
        out += spec;
        out += conv;
        break;
    }
    i = j;
  }
  while (!out.empty() && (out.back() == '\n' || out.back() == '\r')) {
    out.pop_back();
  }
  return out;
}

}  // namespace

extern "C" void sub_83076D88(PPCContext& ctx, uint8_t* base) {
  static const bool on = REXCVAR_GET(nhl_game_printf);
  if (on && Plausible(ctx.r3.u32)) {
    const std::string line = Format(base, ctx, GuestString(base, ctx.r3.u32, 1024));
    if (!line.empty()) {
      REXLOG_INFO("[game] {} (lr {:08X})", line, static_cast<uint32_t>(ctx.lr));
    }
  }
  __imp__sub_83076D88(ctx, base);
}
