// Свободные агенты франшизы на 32 команды (docs/franchise-seasons.md, «Свободные агенты»). Перенос
// nhl-legacy-port/src/nhllegacy_fa.cpp (NHL Legacy 82B69EB8 / 82B640B0) на адреса NHL 13 (tools/xmatch.py).
//
// Объект данных свободных агентов (r3): +4656 u16 — число записей, +4660 — записи по 116 байт (до 6000),
// +0xB0FD1 — «загружено» (иначе 82920CE8), +0xB0FD3 и +0xB0FD4[номер] — флаги «изменено», +0xB2764 — число команд
// НХЛ (при nhl_teams = 32 — 32). Запись: +0 playerid (s16), +45…+74 места[30] (команды по убыванию интереса),
// +75…+104 интерес[30] (по номеру команды), дальше — другие поля. В базе (leaguefreeagentdata) тоже только
// playerinterestrank0…29 / playerinterestinteam0…29.
//
// 82928C60(объект, запись, флаг) считает интерес игрока ко всем n командам (82928B38) и места (qsort с 829102F8:
// интерес по убыванию, при равенстве — номер команды по убыванию). При n = 32 интерес команд 30/31 ложится в
// +105/+106 (следующее поле записи), а места 30/31 — в +75/+76: затирают интерес команд 0 и 1 номерами команд
// (по сейву 1-го сезона 2026/27: у 1194 из 1302 агентов interest0 = 4, interest1 = 2). Подмена (nhl_fa32): в
// запись — места 0…29 и интерес команд 0…29, команды 30/31 — в боковой таблице по адресу записи (с playerid для
// проверки); экран 82923320 (i-е место и интерес) берёт 30/31 из неё. В базу боковая таблица не пишется — игра
// пересчитывает интерес сама.

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <mutex>
#include <unordered_map>
#include <utility>
#include <vector>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ppc.h>

REXCVAR_DEFINE_BOOL(nhl_fa32, false, "NHL13",
                    "Free agency on 32 teams: interest/ranks of teams 30/31 kept beside the 30-team FA record "
                    "(no corruption of the next field and of teams 0/1 interest)")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

bool Nhl13ThirtyTwo();  // src/nhl13_teams.cpp

extern "C" void __imp__sub_82928C60(PPCContext& ctx, uint8_t* base);  // интерес и места одного агента
extern "C" void __imp__sub_82923320(PPCContext& ctx, uint8_t* base);  // i-е место и интерес (экран)
extern "C" void sub_82920CE8(PPCContext& ctx, uint8_t* base);         // загрузка записей
extern "C" void sub_82740F10(PPCContext& ctx, uint8_t* base);         // AI-объект GM
extern "C" void sub_828D3C78(PPCContext& ctx, uint8_t* base);         // лига
extern "C" void sub_82928B38(PPCContext& ctx, uint8_t* base);         // интерес к команде

namespace {

constexpr uint32_t kRecords = 4660;
constexpr uint32_t kRecordBytes = 116;
constexpr uint32_t kCount = 4656;
constexpr uint32_t kLoaded = 0xB0FD1;
constexpr uint32_t kDirtyAll = 0xB0FD3;
constexpr uint32_t kDirty = 0xB0FD4;
constexpr uint32_t kTeams = 0xB2764;
constexpr uint32_t kRank = 45;
constexpr uint32_t kInterest = 75;
constexpr int kStored = 30;  // мест в записи
constexpr int kExtra = 2;    // команды 30/31

uint8_t* Host(uint8_t* base, uint32_t addr) {
  return base + addr + (addr >= 0xE0000000u ? 0x1000u : 0u);
}
uint32_t Load32(uint8_t* base, uint32_t a) {
  uint32_t v;
  std::memcpy(&v, Host(base, a), 4);
  return __builtin_bswap32(v);
}
uint16_t Load16(uint8_t* base, uint32_t a) {
  uint16_t v;
  std::memcpy(&v, Host(base, a), 2);
  return __builtin_bswap16(v);
}
int16_t Load16s(uint8_t* base, uint32_t a) {
  return static_cast<int16_t>(Load16(base, a));
}
uint8_t Load8(uint8_t* base, uint32_t a) {
  return *Host(base, a);
}
void Store8(uint8_t* base, uint32_t a, uint8_t v) {
  *Host(base, a) = v;
}
void Store32(uint8_t* base, uint32_t a, uint32_t v) {
  v = __builtin_bswap32(v);
  std::memcpy(Host(base, a), &v, 4);
}

bool Enabled() {
  static const bool on = [] {
    const bool v = Nhl13ThirtyTwo() && REXCVAR_GET(nhl_fa32);
    REXLOG_INFO("[nhl13] free agency on 32 teams (nhl_fa32): {}", v ? "on" : "off");
    return v;
  }();
  return on;
}

struct Side {
  int16_t playerid = 0;
  uint8_t interest[kExtra] = {};
  int8_t rank[kExtra] = {-1, -1};
};
std::mutex g_mutex;
std::unordered_map<uint32_t, Side> g_side;  // адрес записи → команды 30/31

uint32_t FindRecord(uint8_t* base, uint32_t obj, int32_t playerid) {
  const uint32_t n = Load16(base, obj + kCount);
  for (uint32_t k = 0; k < n && k < 6000; ++k) {
    const uint32_t rec = obj + kRecords + k * kRecordBytes;
    if (Load16s(base, rec) == playerid) {
      return rec;
    }
  }
  return 0;
}

}  // namespace

// 82928C60(объект, запись, флаг): интерес ко всем командам и места.
extern "C" void sub_82928C60(PPCContext& ctx, uint8_t* base) {
  const uint32_t obj = ctx.r3.u32;
  const uint32_t fa = ctx.r4.u32;
  const uint64_t flag = ctx.r5.u64;
  if (!Enabled()) {
    __imp__sub_82928C60(ctx, base);
    return;
  }
  if (!Load8(base, obj + kLoaded)) {
    ctx.r3.u64 = obj;
    sub_82920CE8(ctx, base);
  }
  const int32_t n = static_cast<int32_t>(Load32(base, obj + kTeams));
  if (n <= kStored || n > kStored + kExtra) {
    ctx.r3.u64 = obj;
    ctx.r4.u64 = fa;
    ctx.r5.u64 = flag;
    __imp__sub_82928C60(ctx, base);
    return;
  }
  const uint32_t idx = (fa - obj - kRecords) / kRecordBytes;
  Store8(base, obj + kDirty + idx, 1);
  Store8(base, obj + kDirtyAll, 0);
  sub_82740F10(ctx, base);
  const uint64_t gm = ctx.r3.u64;
  sub_828D3C78(ctx, base);
  const uint64_t league = ctx.r3.u64;
  std::vector<std::pair<int32_t, int32_t>> order;  // (команда, интерес)
  order.reserve(n);
  Side side;
  side.playerid = Load16s(base, fa);
  for (int32_t t = 0; t < n; ++t) {
    ctx.r3.u64 = obj;
    ctx.r4.u64 = fa;
    ctx.r5.s64 = t;
    ctx.r6.u64 = gm;
    ctx.r7.u64 = league;
    ctx.r8.u64 = 0;
    ctx.r9.u64 = flag;
    sub_82928B38(ctx, base);
    const uint8_t v = static_cast<uint8_t>(ctx.r3.u32 & 0xFF);
    if (t < kStored) {
      Store8(base, fa + kInterest + t, v);
    } else {
      side.interest[t - kStored] = v;
    }
    order.emplace_back(t, v);
  }
  // Как qsort с 829102F8: интерес по убыванию, при равенстве — номер команды по убыванию.
  std::sort(order.begin(), order.end(), [](const auto& a, const auto& b) {
    return a.second != b.second ? a.second > b.second : a.first > b.first;
  });
  for (int32_t i = 0; i < n; ++i) {
    if (i < kStored) {
      Store8(base, fa + kRank + i, static_cast<uint8_t>(order[i].first));
    } else {
      side.rank[i - kStored] = static_cast<int8_t>(order[i].first);
    }
  }
  {
    std::lock_guard<std::mutex> lock(g_mutex);
    g_side[fa] = side;
  }
  static int logged = 0;
  if (logged++ < 3) {
    REXLOG_INFO("[nhl13] FA {} interest: teams {}, SEA {} VGK {}, top {} {}", side.playerid, n, side.interest[0],
                side.interest[1], order[0].first, order[1].first);
  }
}

// 82923320(объект, playerid, место i, &команда, &интерес) — экран свободного агента.
extern "C" void sub_82923320(PPCContext& ctx, uint8_t* base) {
  const uint32_t obj = ctx.r3.u32;
  const int32_t playerid = ctx.r4.s32;
  const int32_t i = ctx.r5.s32;
  const uint32_t out_team = ctx.r6.u32;
  const uint32_t out_interest = ctx.r7.u32;
  __imp__sub_82923320(ctx, base);
  if (!Enabled()) {
    return;
  }
  const uint32_t fa = FindRecord(base, obj, playerid);
  if (!fa || i < 0 || i >= kStored + kExtra) {
    return;
  }
  Side side;
  bool have = false;
  {
    std::lock_guard<std::mutex> lock(g_mutex);
    auto it = g_side.find(fa);
    if (it != g_side.end() && it->second.playerid == playerid) {
      side = it->second;
      have = true;
    }
  }
  int32_t team = i < kStored ? Load8(base, fa + kRank + i) : (have ? side.rank[i - kStored] : -1);
  if (team < 0 && i >= kStored) {
    // Нет боковой записи (сейв загружен, интерес ещё не пересчитан): команды, которых нет среди 30 мест.
    bool seen[kStored + kExtra] = {};
    for (int k = 0; k < kStored; ++k) {
      const uint8_t r = Load8(base, fa + kRank + k);
      if (r < kStored + kExtra) {
        seen[r] = true;
      }
    }
    int skip = i - kStored;
    for (int t = kStored + kExtra - 1; t >= 0; --t) {
      if (!seen[t] && skip-- == 0) {
        team = t;
        break;
      }
    }
  }
  if (team < 0 || team >= kStored + kExtra) {
    return;
  }
  const uint32_t interest =
      team < kStored ? Load8(base, fa + kInterest + team) : (have ? side.interest[team - kStored] : 0);
  Store32(base, out_team, static_cast<uint32_t>(team));
  Store32(base, out_interest, interest);
}
