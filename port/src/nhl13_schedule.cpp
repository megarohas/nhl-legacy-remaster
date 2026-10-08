// Календарь НХЛ со второго сезона франшизы при 32 командах (docs/franchise-seasons.md).
//
// Первый сезон берёт nhlschedule из базы (tools/nhl32.py: 32 × 84 игры на игровых днях 2012/13). Со
// второго сезона 828DE2C8 (календарь лиг на сезон) для НХЛ зовёт 8286AD88 с типом лиги 0, а тот —
// генератор игры: 8286A148 (таблицы пар) + 82859E48 (раскладка по сетке 7 месяцев × 6 недель × 7 дней).
// Генератор рассчитан на 6 дивизионов по 5 команд: у объекта таблицы на 30 команд по 200 игровых
// мест ([30][200] с +1512 и +7542, цикл `li r10, 30`), для 32 команд он не годится вовсе (команды 30/31
// без игр, записи за край таблиц). Остальные лиги (АХЛ и др.) 8286AD88 берёт из базы (827AF770,
// ahlschedule) с поворотом команд внутри дивизионов (8285A020) — это общее и для АХЛ на 32 работает.
//
// Подмена 8286AD88 для НХЛ (тип 0) при nhl_teams = 32 и nhl_schedule32 = true — генератор
// tools/nhl32.py, перенесённый сюда: 84 игры (4 в дивизионе, 3 в конференции, 2 с другой конференцией),
// 42 дома, нынешние 4 дивизиона по 8; «третья» игра внутри конференции — хозяин по эйлерову циклу
// (у каждой команды 4 лишних домашних из 8); игры раскладываются по 177 игровым дням регулярки
// 2012/13 (те же дни, что у первого сезона из базы) с числом игр в день пропорционально 2012/13,
// без трёх игр за три дня подряд у команды, по возможности без двух подряд и без повторной встречи
// пары чаще раза в 10 игровых дней. Зерно — год сезона: тот же сезон даёт тот же календарь. Если у лиги
// есть сборные (32 НХЛ + 30 АХЛ, состояние 52 ≠ 0), Матч звёзд — 27 января, как в базе первого сезона;
// при АХЛ на 32 сборных нет (docs/ahl32.md) — и Матча звёзд нет.
//
// Запись календаря (28 байт, как у 82859E48 и загрузчика базы 827B2300; поля читает 828D8038 →
// leaguescheduletable): +0 месяц (с 0), +4 день (с 0), +8 гости, +12 хозяева (номер франшизы = первый
// номер лиги + номер внутри лиги), +16 и +20 — группа и лига (аргументы r5/r6), +24 раунд (0).

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <random>
#include <set>
#include <string>
#include <utility>
#include <vector>

// Самопроверка генератора без игры: clang++ -std=c++23 -O2 -DNHL13_SCHEDULE_SELFTEST
// src/nhl13_schedule.cpp -o schedule_test.exe && schedule_test.exe (20 сезонов, проверки как Valid ниже).
#if !defined(NHL13_SCHEDULE_SELFTEST)
#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ppc.h>
#include <rex/runtime.h>
#include <rex/system/xmemory.h>

REXCVAR_DEFINE_BOOL(nhl_schedule32, false, "NHL13",
                    "NHL schedule from the 2nd franchise season with nhl_teams = 32: own 84-game generator "
                    "(tools/nhl32.py ported, 4 divisions of 8); false = game's generator (6 divisions of 5, "
                    "breaks with 32 teams)")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

REXCVAR_DEFINE_BOOL(nhl_preseason_september, false, "NHL13",
                    "Franchise preseason only in September: the game counts preseason games played in October "
                    "as regular-season games (standings GP/points, player stats); with 32 teams SEA/VGK have no "
                    "preseason, so the others got 2-3 extra games. true = drop October preseason games")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

bool Nhl13ThirtyTwo();  // src/nhl13_teams.cpp

extern "C" void __imp__sub_8286AD88(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_828DB828(PPCContext& ctx, uint8_t* base);
extern "C" void sub_828D3C78(PPCContext& ctx, uint8_t* base);  // GetLeague: +12 — год сезона
extern "C" void sub_827DFE00(PPCContext& ctx, uint8_t* base);  // номер сборной (0/1), −16 — нет
#endif

namespace {

constexpr int kTeams = 32;
constexpr int kGames = 84;
constexpr int kHome = 42;
constexpr uint32_t kEntryBytes = 28;

// Нынешние дивизионы (номера команд базы = номера франшизы НХЛ; 22 — Юта, 30/31 — Сиэтл/Вегас),
// как REAL_DIVISIONS в tools/nhl32.py. Конференции: 0 — Восток, 1 — Запад.
struct Division {
  int conference;
  int teams[8];
};
constexpr Division kDivisions[4] = {
    {0, {2, 3, 10, 12, 15, 20, 26, 27}},   // Atlantic: BOS BUF DET FLA MTL OTT TB TOR
    {0, {5, 8, 17, 18, 19, 21, 23, 29}},   // Metropolitan: CAR CBJ NJ NYI NYR PHI PIT WSH
    {1, {1, 6, 7, 9, 14, 16, 22, 24}},     // Central: WPG CHI COL DAL MIN NSH UTA STL
    {1, {0, 4, 11, 13, 25, 28, 30, 31}},   // Pacific: ANA CGY EDM LA SJ VAN SEA VGK
};

// Игровые дни регулярки 2012/13 (месяц с 0, день с 0) и сколько в них было игр (без Матча звёзд) —
// nhlschedule базы с диска (tools/nhl32.py game_days; 177 дней, 1230 игр, 11.10.2012 … 13.04.2013).
struct GameDay {
  uint8_t month, day, games;
};
constexpr GameDay kDays[] = {
#include "nhl13_schedule_days.inc"
};
constexpr int kNumDays = static_cast<int>(sizeof(kDays) / sizeof(kDays[0]));
constexpr uint8_t kAllStarMonth = 0, kAllStarDay = 26;  // 27 января, как строка Матча звёзд в базе

struct Game {
  uint8_t home, away;
};

class Rng {
 public:
  explicit Rng(uint32_t seed) : gen_(seed) {}
  double Real() { return static_cast<double>(gen_()) / 4294967296.0; }
  uint32_t Below(uint32_t n) { return static_cast<uint32_t>(Real() * n) % n; }
  template <typename T>
  void Shuffle(std::vector<T>& v) {
    for (size_t i = v.size(); i > 1; --i) {
      std::swap(v[i - 1], v[Below(static_cast<uint32_t>(i))]);
    }
  }

 private:
  std::mt19937 gen_;
};

// Пары с нечётным числом игр (граф чётной степени): лишняя игра — дома у того, кто ведёт по
// эйлерову циклу (Хирхольцер), — у каждой команды поровну лишних домашних и выездных.
void OrientEuler(std::array<std::vector<int>, kTeams> adj, Rng& rng, std::vector<Game>& games) {
  for (auto& v : adj) {
    rng.Shuffle(v);
  }
  std::set<std::pair<int, int>> used;
  auto key = [](int a, int b) { return a < b ? std::make_pair(a, b) : std::make_pair(b, a); };
  for (int start = 0; start < kTeams; ++start) {
    std::vector<int> stack{start}, path;
    while (!stack.empty()) {
      const int v = stack.back();
      while (!adj[v].empty() && used.count(key(v, adj[v].back()))) {
        adj[v].pop_back();
      }
      if (!adj[v].empty()) {
        const int w = adj[v].back();
        adj[v].pop_back();
        used.insert(key(v, w));
        stack.push_back(w);
      } else {
        path.push_back(v);
        stack.pop_back();
      }
    }
    for (size_t i = 0; i + 1 < path.size(); ++i) {
      games.push_back({static_cast<uint8_t>(path[i]), static_cast<uint8_t>(path[i + 1])});
    }
  }
}

// Пары и хозяева: 4 игры в дивизионе, 3 в конференции, 2 с другой конференцией (pair_games).
std::vector<Game> PairGames(Rng& rng) {
  int div_of[kTeams], conf_of[kTeams];
  for (int d = 0; d < 4; ++d) {
    for (int t : kDivisions[d].teams) {
      div_of[t] = d;
      conf_of[t] = kDivisions[d].conference;
    }
  }
  std::vector<Game> games;
  std::array<std::vector<int>, kTeams> odd;
  for (int x = 0; x < kTeams; ++x) {
    for (int y = x + 1; y < kTeams; ++y) {
      const Game xy{static_cast<uint8_t>(x), static_cast<uint8_t>(y)};
      const Game yx{static_cast<uint8_t>(y), static_cast<uint8_t>(x)};
      if (div_of[x] == div_of[y]) {
        games.insert(games.end(), {xy, yx, xy, yx});
      } else if (conf_of[x] == conf_of[y]) {
        games.insert(games.end(), {xy, yx});
        odd[x].push_back(y);
        odd[y].push_back(x);
      } else {
        games.insert(games.end(), {xy, yx});
      }
    }
  }
  OrientEuler(odd, rng, games);
  return games;
}

struct Planned {
  int day;  // номер игрового дня в kDays
  Game game;
};

// Три игры за три игровых дня подряд у команды (в НХЛ так не бывает, back-to-back — не больше двух):
// средняя игра тройки переезжает в ближайший день, где обе команды свободны и новой тройки нет.
void Repair(std::vector<Planned>& plan) {
  std::vector<std::array<int, kTeams>> at(kNumDays);
  for (auto& d : at) {
    d.fill(-1);
  }
  for (int i = 0; i < static_cast<int>(plan.size()); ++i) {
    at[plan[i].day][plan[i].game.home] = at[plan[i].day][plan[i].game.away] = i;
  }
  auto plays = [&](int d, int t) { return d >= 0 && d < kNumDays && at[d][t] >= 0; };
  auto triple = [&](int d, int t) {  // t играет в d и d входит в три дня подряд с играми
    return plays(d, t) && ((plays(d - 1, t) && plays(d - 2, t)) || (plays(d - 1, t) && plays(d + 1, t)) ||
                           (plays(d + 1, t) && plays(d + 2, t)));
  };
  auto clean = [&](int d, int t) {
    for (int k = d - 2; k <= d + 2; ++k) {
      if (triple(k, t)) {
        return false;
      }
    }
    return true;
  };
  for (int pass = 0; pass < 8; ++pass) {
    bool moved = false, left = false;
    for (int t = 0; t < kTeams; ++t) {
      for (int d = 1; d + 1 < kNumDays; ++d) {
        if (!(plays(d - 1, t) && plays(d, t) && plays(d + 1, t))) {
          continue;
        }
        const int i = at[d][t];
        const Game g = plan[i].game;
        bool done = false;
        for (int dist = 1; dist < kNumDays && !done; ++dist) {
          for (int nd : {d - dist, d + dist}) {
            if (done || nd < 0 || nd >= kNumDays || plays(nd, g.home) || plays(nd, g.away)) {
              continue;
            }
            at[d][g.home] = at[d][g.away] = -1;
            at[nd][g.home] = at[nd][g.away] = i;
            if (clean(nd, g.home) && clean(nd, g.away)) {
              plan[i].day = nd;
              done = moved = true;
            } else {
              at[nd][g.home] = at[nd][g.away] = -1;
              at[d][g.home] = at[d][g.away] = i;
            }
          }
        }
        left |= !done;
      }
    }
    if (!moved || !left) {
      break;
    }
  }
}

// Раскладка игр по игровым дням (schedule в tools/nhl32.py). false — не разложилось.
bool Schedule(std::vector<Game> pool, Rng& rng, std::vector<Planned>& plan) {
  const int total = static_cast<int>(pool.size());
  int sum = 0;
  for (const GameDay& d : kDays) {
    sum += d.games;
  }
  const double scale = static_cast<double>(total) / sum;
  std::vector<double> raw(kNumDays);
  std::vector<int> target(kNumDays);
  int placed = 0;
  for (int i = 0; i < kNumDays; ++i) {
    raw[i] = kDays[i].games * scale;
    target[i] = static_cast<int>(raw[i]);
    placed += target[i];
  }
  std::vector<int> order(kNumDays);
  for (int i = 0; i < kNumDays; ++i) {
    order[i] = i;
  }
  std::stable_sort(order.begin(), order.end(),
                   [&](int a, int b) { return raw[a] - target[a] > raw[b] - target[b]; });
  for (int k = 0; k < total - placed && k < kNumDays; ++k) {
    ++target[order[k]];
  }
  rng.Shuffle(pool);
  int left[kTeams] = {};
  for (const Game& g : pool) {
    ++left[g.home];
    ++left[g.away];
  }
  int last[kTeams], prev[kTeams];
  std::fill(std::begin(last), std::end(last), -99);
  std::fill(std::begin(prev), std::end(prev), -99);
  std::array<std::array<int, kTeams>, kTeams> met;
  for (auto& row : met) {
    row.fill(-99);
  }
  plan.clear();
  std::vector<std::pair<double, int>> cand;
  for (int di = 0; di < kNumDays; ++di) {
    cand.clear();
    for (int i = 0; i < static_cast<int>(pool.size()); ++i) {
      const Game g = pool[i];
      double score = left[g.home] + left[g.away] + rng.Real();
      for (int t : {static_cast<int>(g.home), static_cast<int>(g.away)}) {
        if (last[t] == di - 1) {
          score -= 30;
          if (prev[t] == di - 2) {
            score -= 200;
          }
        }
      }
      if (met[g.home][g.away] > di - 10) {
        score -= 15;
      }
      cand.emplace_back(score, i);
    }
    std::stable_sort(cand.begin(), cand.end(), [](const auto& a, const auto& b) { return a.first > b.first; });
    bool busy[kTeams] = {};
    std::vector<int> chosen;
    for (const auto& c : cand) {
      if (static_cast<int>(chosen.size()) >= target[di]) {
        break;
      }
      const Game g = pool[c.second];
      if (busy[g.home] || busy[g.away]) {
        continue;
      }
      chosen.push_back(c.second);
      busy[g.home] = busy[g.away] = true;
    }
    std::sort(chosen.rbegin(), chosen.rend());  // удалять с конца, чтобы номера не съезжали
    for (int i : chosen) {
      const Game g = pool[i];
      pool.erase(pool.begin() + i);
      plan.push_back({di, g});
      met[g.home][g.away] = met[g.away][g.home] = di;
      for (int t : {static_cast<int>(g.home), static_cast<int>(g.away)}) {
        --left[t];
        prev[t] = last[t];
        last[t] = di;
      }
    }
  }
  // хвост — в любые дни, где обе команды свободны
  std::vector<std::array<bool, kTeams>> day_busy(kNumDays);
  for (auto& b : day_busy) {
    b.fill(false);
  }
  for (const Planned& p : plan) {
    day_busy[p.day][p.game.home] = day_busy[p.day][p.game.away] = true;
  }
  // (у tools/nhl32.py — первый свободный день; здесь сперва день без игр у обеих накануне и назавтра,
  // потом без трёх игр за три дня, потом любой свободный)
  auto plays = [&](int di, int t) { return di >= 0 && di < kNumDays && day_busy[di][t]; };
  auto three_in_row = [&](int di, int t) {
    return (plays(di - 1, t) && plays(di - 2, t)) || (plays(di - 1, t) && plays(di + 1, t)) ||
           (plays(di + 1, t) && plays(di + 2, t));
  };
  for (size_t i = 0; i < pool.size();) {
    const Game g = pool[i];
    bool put = false;
    for (int pass = 0; pass < 3 && !put; ++pass) {
      for (int di = 0; di < kNumDays && !put; ++di) {
        if (day_busy[di][g.home] || day_busy[di][g.away]) {
          continue;
        }
        bool fits = true;
        for (int t : {static_cast<int>(g.home), static_cast<int>(g.away)}) {
          if (pass == 0 && (plays(di - 1, t) || plays(di + 1, t))) {
            fits = false;
          }
          if (pass == 1 && three_in_row(di, t)) {
            fits = false;
          }
        }
        if (fits) {
          plan.push_back({di, g});
          day_busy[di][g.home] = day_busy[di][g.away] = true;
          put = true;
        }
      }
    }
    if (!put) {
      return false;
    }
    pool.erase(pool.begin() + i);
  }
  Repair(plan);
  std::stable_sort(plan.begin(), plan.end(), [](const Planned& a, const Planned& b) { return a.day < b.day; });
  return true;
}

// Проверка: у каждой команды 84 игры, 42 дома, не больше одной игры в день.
bool Valid(const std::vector<Planned>& plan, int* max_three_in_row) {
  int games[kTeams] = {}, home[kTeams] = {};
  std::vector<std::array<int8_t, kTeams>> on(kNumDays);
  for (auto& d : on) {
    d.fill(0);
  }
  for (const Planned& p : plan) {
    if (++on[p.day][p.game.home] > 1 || ++on[p.day][p.game.away] > 1 || p.game.home == p.game.away) {
      return false;
    }
    ++games[p.game.home];
    ++games[p.game.away];
    ++home[p.game.home];
  }
  for (int t = 0; t < kTeams; ++t) {
    if (games[t] != kGames || home[t] != kHome) {
      return false;
    }
  }
  int three = 0;
  for (int t = 0; t < kTeams; ++t) {
    for (int d = 2; d < kNumDays; ++d) {
      three += on[d][t] && on[d - 1][t] && on[d - 2][t];
    }
  }
  *max_three_in_row = three;
  return static_cast<int>(plan.size()) == kTeams * kGames / 2;
}

#if defined(NHL13_SCHEDULE_SELFTEST)
}  // namespace
#else
uint32_t GuestCall(void (*fn)(PPCContext&, uint8_t*), PPCContext& ctx, uint8_t* base, uint32_t r3, uint32_t r4,
                   uint32_t r5) {
  ctx.r3.u64 = r3;
  ctx.r4.u64 = r4;
  ctx.r5.u64 = r5;
  fn(ctx, base);
  return ctx.r3.u32;
}

void Store32(uint8_t* base, uint32_t addr, uint32_t v) {
  v = __builtin_bswap32(v);
  std::memcpy(base + addr + (addr >= 0xE0000000u ? 0x1000u : 0u), &v, 4);
}

uint32_t Load32(uint8_t* base, uint32_t addr) {
  uint32_t v;
  std::memcpy(&v, base + addr + (addr >= 0xE0000000u ? 0x1000u : 0u), 4);
  return __builtin_bswap32(v);
}

}  // namespace

// 8286AD88(генератор, тип лиги, группа, лига, первый номер лиги, буфер, вместимость, сколько уже) →
// сколько игр записано. Тип 0 — НХЛ.
extern "C" void sub_8286AD88(PPCContext& ctx, uint8_t* base) {
  static const bool on = REXCVAR_GET(nhl_schedule32);
  if (!on || !Nhl13ThirtyTwo() || ctx.r4.u32 != 0) {
    __imp__sub_8286AD88(ctx, base);
    return;
  }
  const uint32_t group = ctx.r5.u32;
  const uint32_t league = ctx.r6.u32;
  const uint32_t first = ctx.r7.u32;
  const uint32_t buf = ctx.r8.u32;
  const uint32_t cap = ctx.r9.u32;
  const uint32_t start = ctx.r10.u32;
  const uint64_t saved_r3 = ctx.r3.u64;

  const uint32_t league_obj = GuestCall(sub_828D3C78, ctx, base, 0, 0, 0);
  const uint32_t year = league_obj ? Load32(base, league_obj + 12) : 0;
  const int32_t allstar_a = static_cast<int32_t>(GuestCall(sub_827DFE00, ctx, base, 0, 0, 0));
  const int32_t allstar_b = static_cast<int32_t>(GuestCall(sub_827DFE00, ctx, base, 1, 0, 0));
  const bool allstar = allstar_a >= 0 && allstar_b >= 0;

  std::vector<Planned> plan;
  int three = 0, tries = 0;
  uint32_t seed = 0;
  bool ok = false;
  for (; tries < 32 && !ok; ++tries) {
    seed = 0x4E484C33u ^ (year * 2654435761u) ^ static_cast<uint32_t>(tries * 40503);
    Rng rng(seed);
    ok = Schedule(PairGames(rng), rng, plan) && Valid(plan, &three);
  }
  const uint32_t need = static_cast<uint32_t>(plan.size()) + (allstar ? 1 : 0);
  if (!ok || start + need > cap) {
    REXLOG_ERROR("[nhl13] schedule 32: season {} — generator failed (ok {}, {} games, capacity {}+{}); "
                 "falling back to the game's generator",
                 year, ok, plan.size(), start, cap);
    ctx.r3.u64 = saved_r3;
    ctx.r4.u64 = 0;
    ctx.r5.u64 = group;
    ctx.r6.u64 = league;
    ctx.r7.u64 = first;
    ctx.r8.u64 = buf;
    ctx.r9.u64 = cap;
    ctx.r10.u64 = start;
    __imp__sub_8286AD88(ctx, base);
    return;
  }
  // день календаря в порядке сезона (октябрь … апрель) — для места Матча звёзд
  auto season_order = [](uint8_t month, uint8_t day) { return ((month + 3) % 12) * 32 + day; };
  uint32_t n = 0;
  auto put = [&](uint8_t month, uint8_t day, uint32_t away, uint32_t home) {
    const uint32_t e = buf + (start + n) * kEntryBytes;
    Store32(base, e + 0, month);
    Store32(base, e + 4, day);
    Store32(base, e + 8, away);
    Store32(base, e + 12, home);
    Store32(base, e + 16, group);
    Store32(base, e + 20, league);
    Store32(base, e + 24, 0);
    ++n;
  };
  // Матч звёзд — как у 82859E48: хозяева — сборная 0, гости — сборная 1 (827DFE00)
  bool allstar_done = !allstar;
  for (const Planned& p : plan) {
    const GameDay& d = kDays[p.day];
    if (!allstar_done && season_order(d.month, d.day) > season_order(kAllStarMonth, kAllStarDay)) {
      put(kAllStarMonth, kAllStarDay, static_cast<uint32_t>(allstar_b), static_cast<uint32_t>(allstar_a));
      allstar_done = true;
    }
    put(d.month, d.day, first + p.game.away, first + p.game.home);
  }
  if (!allstar_done) {
    put(kAllStarMonth, kAllStarDay, static_cast<uint32_t>(allstar_b), static_cast<uint32_t>(allstar_a));
  }
  REXLOG_INFO("[nhl13] schedule 32: season {} - {} NHL games ({} per team, {} home) on {} days, seed {:08X} "
              "(try {}), 3 games in 3 days: {}, All-Star game: {}",
              year, plan.size(), kGames, kHome, kNumDays, seed, tries, three,
              allstar ? std::to_string(allstar_a) + "/" + std::to_string(allstar_b) + " on 27.01" : std::string("no"));
  ctx.r3.u64 = n;
}

// Предсезонка франшизы: 828DB828(лига, *дата начала, буфер, вместимость, сколько уже) пишет 10 игровых дней
// по одной игре на дивизион (6 × 10 = 60 игр, раунд 6, команды — по модулю 5 в дивизионах дерева на 30) с
// даты «первая игра − 14» — у сезона 2026/27 это 27.09…06.10. Игра засчитывает в таблицу и статистику
// игроков игры, сыгранные с 1 октября, даже предсезонные (сверено по сейву: у всех 32 клубов лишние игры в
// таблице = их предсезонные игры в октябре; GP 86–87 вместо 84), а у SEA/VGK предсезонки нет совсем — у них
// 84, у остальных 86–87 (очки и P% неравны). При nhl_preseason_september = true октябрьские предсезонные
// игры не создаются: остаются игры 27–30 сентября (у клуба 0–2), в зачёт идёт ровно регулярка.
extern "C" void sub_828DB828(PPCContext& ctx, uint8_t* base) {
  static const bool on = REXCVAR_GET(nhl_preseason_september);
  const uint32_t buf = ctx.r5.u32;
  const uint32_t start = ctx.r7.u32;
  __imp__sub_828DB828(ctx, base);
  if (!on || !buf) {
    return;  // без буфера игра пишет предсезонку прямо в базу (828D82C8) — не трогаем
  }
  const uint32_t n = ctx.r3.u32;
  if (n > 200) {
    return;
  }
  uint32_t kept = 0;
  for (uint32_t i = 0; i < n; ++i) {
    const uint32_t src = buf + (start + i) * kEntryBytes;
    if (Load32(base, src) >= 9) {  // месяц с 0: 9 — октябрь
      continue;
    }
    if (kept != i) {
      std::memmove(base + buf + (start + kept) * kEntryBytes + (buf >= 0xE0000000u ? 0x1000u : 0u),
                   base + src + (src >= 0xE0000000u ? 0x1000u : 0u), kEntryBytes);
    }
    ++kept;
  }
  static int logged = 0;
  if (logged++ < 4) {
    REXLOG_INFO("[nhl13] preseason: {} games, kept {} in September (October ones would count as regular season)",
                n, kept);
  }
  ctx.r3.u64 = kept;
}
#endif  // !NHL13_SCHEDULE_SELFTEST

#if defined(NHL13_SCHEDULE_SELFTEST)
#include <cstdio>
int main() {
  int bad = 0;
  for (uint32_t year = 2026; year < 2046; ++year) {
    std::vector<Planned> plan;
    int three = 0, tries = 0;
    bool ok = false;
    uint32_t seed = 0;
    for (; tries < 32 && !ok; ++tries) {
      seed = 0x4E484C33u ^ (year * 2654435761u) ^ static_cast<uint32_t>(tries * 40503);
      Rng rng(seed);
      ok = Schedule(PairGames(rng), rng, plan) && Valid(plan, &three);
    }
    // встречи пар: в дивизионе 4, в конференции 3, иначе 2
    int meet[kTeams][kTeams] = {};
    int b2b = 0, per_day_max = 0;
    std::vector<int> per_day(kNumDays);
    for (const Planned& p : plan) {
      ++meet[p.game.home][p.game.away];
      ++meet[p.game.away][p.game.home];
      per_day_max = std::max(per_day_max, ++per_day[p.day]);
    }
    int div_of[kTeams], conf_of[kTeams];
    for (int d = 0; d < 4; ++d) {
      for (int t : kDivisions[d].teams) {
        div_of[t] = d;
        conf_of[t] = kDivisions[d].conference;
      }
    }
    int wrong = 0;
    for (int x = 0; x < kTeams; ++x) {
      for (int y = 0; y < kTeams; ++y) {
        if (x == y) continue;
        const int want = div_of[x] == div_of[y] ? 4 : conf_of[x] == conf_of[y] ? 3 : 2;
        wrong += meet[x][y] != want;
      }
    }
    for (int t = 0; t < kTeams; ++t) {
      int last = -9;
      for (const Planned& p : plan) {
        if (p.game.home == t || p.game.away == t) {
          b2b += p.day == last + 1;
          last = p.day;
        }
      }
    }
    std::printf("%u: ok %d tries %d seed %08X games %zu wrong-pairs %d three-in-3 %d b2b %d max/day %d\n", year, ok,
                tries, seed, plan.size(), wrong, three, b2b, per_day_max);
    bad += !ok || wrong || three;
  }
  return bad;
}
#endif
