// Вратарь тренировки по умолчанию (nhl_practice_goalie), docs/special-rosters.md, «Вратарь тренировки».
//
// Когда вратарь тренировки не выбран (поле −1), 82AB0DE0 и 82AB2C88 ищут его по имени: sub_82B29980(запрос, имя,
// фамилия) — запрос к базе игроков по имени и фамилии — с зашитыми строками «Corey» (0x8207C174, место 8 байт) и
// «Crawford» (0x8207C17C, 12 байт). Кроуфорд не играет с 2020 года, в базе он только в старом составе Матча звёзд.
// Врезка перед первым таким запросом кладёт на место этих строк имя и фамилию из cvar (по умолчанию Андрей
// Василевский). Строки «Corey»/«Crawford» больше нигде в коде не используются (tools/xrefs.py: только эти функции).
// Имя длиннее 7 байт или фамилия длиннее 11 на место не встают: тогда остаётся Кроуфорд и в журнале ошибка.
// Полевой по умолчанию (82A86448 «Zdeno Chara», 82AB0DE0 «Jonathan Toews») не меняется.

#include <cstdint>
#include <cstring>
#include <string>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ppc.h>

REXCVAR_DEFINE_STRING(nhl_practice_goalie, "Andrei Vasilevskiy", "NHLLegacy",
                      "Default practice goalie, \"First Last\" as in the roster (first name up to 7 bytes, last name up "
                      "to 11); empty keeps the original Corey Crawford")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

#if defined(_WIN32)
#include <windows.h>

namespace {

constexpr uint32_t kFirst = 0x8207C174;  // "Corey"
constexpr uint32_t kFirstSize = 8;
constexpr uint32_t kLast = 0x8207C17C;  // "Crawford"
constexpr uint32_t kLastSize = 12;

void Put(uint8_t* base, uint32_t guest, uint32_t size, const std::string& text) {
  uint8_t* p = base + guest;
  MEMORY_BASIC_INFORMATION mbi{};
  DWORD old = 0;
  const bool writable = VirtualQuery(p, &mbi, sizeof(mbi)) &&
                        (mbi.Protect & (PAGE_READWRITE | PAGE_WRITECOPY | PAGE_EXECUTE_READWRITE)) != 0;
  if (!writable) {
    VirtualProtect(p, size, PAGE_READWRITE, &old);
  }
  std::memset(p, 0, size);
  std::memcpy(p, text.data(), text.size());
  if (!writable) {
    VirtualProtect(p, size, old, &old);
  }
}

void PatchOnce(uint8_t* base) {
  static bool done = false;
  if (done) {
    return;
  }
  done = true;
  std::string name = REXCVAR_GET(nhl_practice_goalie);
  if (name.empty()) {
    return;
  }
  const size_t space = name.find(' ');
  const std::string first = space == std::string::npos ? std::string() : name.substr(0, space);
  const std::string last = space == std::string::npos ? std::string() : name.substr(space + 1);
  if (first.empty() || last.empty() || first.size() >= kFirstSize || last.size() >= kLastSize) {
    REXLOG_ERROR("[nhllegacy] practice goalie \"{}\": need \"First Last\", first name up to {} bytes, last name up to {}"
                 " — keeping Corey Crawford", name, kFirstSize - 1, kLastSize - 1);
    return;
  }
  Put(base, kFirst, kFirstSize, first);
  Put(base, kLast, kLastSize, last);
  REXLOG_INFO("[nhllegacy] practice goalie: {} {}", first, last);
}

}  // namespace

// sub_82B29980(r3 — запрос, r4 — имя, r5 — фамилия): поиск игрока по имени. Подмена — только для зашитого Кроуфорда.
extern "C" void __imp__sub_82B29980(PPCContext& ctx, uint8_t* base);
extern "C" void sub_82B29980(PPCContext& ctx, uint8_t* base) {
  if (ctx.r4.u32 == kFirst && ctx.r5.u32 == kLast) {
    PatchOnce(base);
  }
  __imp__sub_82B29980(ctx, base);
}

#endif
