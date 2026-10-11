// Страховка симуляции матча (сим CPU-матчей календаря; docs/legacy-port.md, «Неполная пятёрка в симе матча»).
//
// Объект симуляции матча (vtable 0x82038818; 8298D450 — подготовка, 82995C00 — ход матча): команда t — с +200 +
// 8740·t (+0 — номер команды во франшизе, +4 — 20), в ней 20 записей состава матча по 392 байта с +900 (+0 playerindex;
// +8 тип: 0 центр, 1 крайний, 2 защитник, 3 вратарь; +16 роль на льду: 0 C, 1 LW, 2 RW, 3 LD, 4 RD; +20 позиция
// игрока; +24 — у полевых всегда > 0). Пустая запись — все эти поля нули: playerindex 0 сам по себе — настоящий игрок
// (в базе legacy-data это Judd Caulfield, проспект Анахайма: в предсезонке он в составе матча ANA). На льду — указатели на записи
// в +17964 + 24·t (6 мест), их число в +18036 + 4·t (заполняют 82984668 в начале и 8298E678 по ходу матча),
// положенное число полевых — +18260 + 4·t.
//
// На сейве BE A GM4 (DYNASTY 20261008222931, сделан сборкой до исправлений) в составе матча Бостона две пустые
// записи; на лёд выходила неполная пятёрка:
//   - 2 защитника без нападающих — розыгрыш вбрасывания 8298A438 бесконечно ищет на льду центра или крайнего
//     (роль от 82A5C4D0, сравнение с +16) — вечное зависание сима;
//   - никого — событие 829937F8 берёт указатель за концом пустого списка: падение (чтение 0x00020005).
// Страховка (cvar nhl_sim_guard, по умолчанию вкл.):
//   - после 82984668/8298E678 и на входе в 8298A438/829937F8 из списка на льду убираются пустые записи и чужие
//     указатели; полевых меньше положенного — добавляются из своего состава матча на недостающие роли (центр,
//     крайние, защитники; без пустых записей, вратарь — только если больше некого);
//   - вбрасывание: после 200 неудачных попыток роль берётся у первого игрока команды на льду.
// Срабатывания — в лог с номером (первые 20, дальше каждое 100-е).
//
// Сим из живого матча (Be a Pro, «сим до следующей смены»; docs/legacy-port.md, «Be a Pro: падение в симе чужих смен»).
// Матч симулируется кусками (82996CD8 → 82996908): подготовка из живого матча 8298D450 → 82984668 (звенья живого
// матча, команда +874 = 1), затем 8298E4C8 раздаёт игрокам списка на льду места смен по флагам мест команды +860[6] и
// пишет указатели событий смен в +876[6]. Кусок кончается на первой же смене звена (8298E678 ставит код остановки
// sim+28852 = 3, неполный список — норма: смену делает живой матч). Быстрый сим франшизы (82997BF0 → 82997498 →
// 82996B48, звенья — 8298B060) идёт без 82984668, без остановок (+874 = 0) — его это не касается.
// 11.10 у пользователя дважды: кусок начался в меньшинстве (на льду 4, поле +18260 ещё 5) — страховка добавила пятого
// без флага места, 8298E4C8 дал ему место 6: указатель события лёг в playerindex записи 0 команды (+900), событие с
// ролью 6 ушло живому матчу → на льду живого матча «игрок» −2 → 834096A0 → 835A2E88 → вызов по адресу 0.
// Поэтому (cvar nhl_sim_guard_live, по умолчанию вкл.; false — как в сборке №8):
//   - после 82984668 игроки не добавляются: пустые записи и чужие указатели — заменяются на том же месте списка;
//   - после 8298E678, если сим остановлен ради живого матча (код sim+28852), — так же, без добавлений;
//   - 829798C0 с местом смены вне 0…5 пропускается (иначе запись поверх состава матча).
// Быстрый сим франшизы (пустые звенья, вбрасыватель) — как раньше: Repair, вбрасывание и события не менялись.

#include <atomic>
#include <cstdint>
#include <cstring>
#include <string>

#include <fmt/format.h>
#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ppc.h>

REXCVAR_DEFINE_BOOL(nhl_sim_guard, true, "NHLLegacy",
                    "Game sim guard: a team with fewer skaters on the ice than it should have gets them from its game "
                    "roster, a faceoff without a center/winger on the ice takes any skater (no hang or crash in CPU "
                    "game sims)")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

REXCVAR_DEFINE_BOOL(nhl_sim_guard_live, true, "NHLLegacy",
                    "Sim guard in a sim started from a live match (Be a Pro 'sim to next shift'): no skaters added at "
                    "the sim start (penalty kill) or at the line change where the sim stops for the live match, and a "
                    "shift slot over 5 is skipped (no crash after a penalty); false - as in build 8")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

namespace {

constexpr uint32_t kSimVtable = 0x82038818;
constexpr uint32_t kTeam0 = 200;
constexpr uint32_t kTeamStride = 8740;
constexpr uint32_t kRecords = 900;  // от начала команды
constexpr uint32_t kRecordStride = 392;
constexpr int kRecordCount = 20;
constexpr uint32_t kOnIce = 17964;  // 4·4491
constexpr uint32_t kOnIceStride = 24;
constexpr int kOnIceSlots = 6;
constexpr uint32_t kOnIceCount = 18036;
constexpr uint32_t kStrength = 18260;
constexpr uint32_t kFaceoffCall = 0x8298A4D4;  // возврат из 82A5C4D0 в цикле вбрасывания 8298A438
constexpr int kFaceoffTries = 200;
constexpr uint32_t kStop = 28852;      // код остановки куска сима (0 — идёт дальше); 8298E678 пишет его по r7
constexpr int kShiftSlots = 6;         // места смен команды: флаги +860[6], события +876[6], за ними — состав (+900)

bool On() {
  static const bool on = REXCVAR_GET(nhl_sim_guard);
  return on;
}

bool LiveOn() {
  static const bool on = REXCVAR_GET(nhl_sim_guard_live);
  return on;
}

uint8_t* Host(uint8_t* base, uint32_t a) {
  return base + a + (a >= 0xE0000000u ? 0x1000u : 0u);
}

uint32_t Ld(uint8_t* base, uint32_t a) {
  uint32_t v;
  std::memcpy(&v, Host(base, a), 4);
  return __builtin_bswap32(v);
}

void St(uint8_t* base, uint32_t a, uint32_t v) {
  v = __builtin_bswap32(v);
  std::memcpy(Host(base, a), &v, 4);
}

bool IsSim(uint8_t* base, uint32_t sim) {
  return sim >= 0x40000000u && sim < 0xFFF00000u && Ld(base, sim) == kSimVtable;
}

std::atomic<uint32_t> g_events{0};

// Номер срабатывания (с 1); в лог — первые 20 и каждое 100-е, иначе 0.
uint32_t LogNumber() {
  const uint32_t k = g_events.fetch_add(1) + 1;
  return k <= 20 || k % 100 == 0 ? k : 0;
}

// Сим из живого матча: отдельный счёт заметок «оставлено как есть» (первые 10 и каждое 100-е), чтобы не съедать
// первые 20 настоящих срабатываний.
std::atomic<uint32_t> g_live_notes{0};

uint32_t LiveNoteNumber() {
  const uint32_t k = g_live_notes.fetch_add(1) + 1;
  return k <= 10 || k % 100 == 0 ? k : 0;
}

uint32_t TeamBase(uint32_t sim, int t) {
  return sim + kTeam0 + kTeamStride * static_cast<uint32_t>(t);
}

uint32_t Record(uint32_t sim, int t, int i) {
  return TeamBase(sim, t) + kRecords + kRecordStride * static_cast<uint32_t>(i);
}

bool IsRecord(uint32_t sim, int t, uint32_t p) {
  const uint32_t first = Record(sim, t, 0);
  return p >= first && p < first + kRecordStride * kRecordCount && (p - first) % kRecordStride == 0;
}

// Пустая запись состава матча: playerindex, тип, позиция и +24 — нули (у настоящего игрока с playerindex 0 тип/позиция/+24
// заполнены: крайний — тип 1, позиция 1/2, +24 > 0; вратарь — тип 3).
bool IsEmptyRecord(uint8_t* base, uint32_t rec) {
  return Ld(base, rec) == 0 && Ld(base, rec + 8) == 0 && Ld(base, rec + 20) == 0 && Ld(base, rec + 24) == 0;
}

// Роли полевых при положенном числе want (5 — полная пятёрка, 4/3 — меньшинство).
const int* RolesFor(int want, int* count) {
  static const int k5[] = {0, 1, 2, 3, 4};
  static const int k4[] = {0, 1, 3, 4};
  static const int k3[] = {0, 3, 4};
  static const int k2[] = {0, 3};
  static const int k1[] = {0};
  switch (want) {
    case 4: *count = 4; return k4;
    case 3: *count = 3; return k3;
    case 2: *count = 2; return k2;
    case 1: *count = 1; return k1;
    default: *count = 5; return k5;
  }
}

// Список на льду команды t (arr — 6 указателей, n — их число): убрать пустые записи и чужие указатели; полевых меньше
// положенного (+18260) — добавить из состава матча на недостающие роли (центр, крайние, защитники; без пустых записей,
// вратарь — только если больше некого). Возвращает новое число; arr и роли (+16) добавленных правит в памяти.
int Repair(uint8_t* base, uint32_t sim, int t, uint32_t arr, int n, const char* where) {
  const int n0 = n;
  if (n > kOnIceSlots) {
    n = kOnIceSlots;
  }
  bool on_ice[kRecordCount] = {};
  bool role_on[5] = {};
  int kept = 0;
  int dropped = 0;
  uint32_t first_bad = 0;
  for (int j = 0; j < (n > 0 ? n : 0); ++j) {
    const uint32_t p = Ld(base, arr + 4 * j);
    if (IsRecord(sim, t, p) && !IsEmptyRecord(base, p)) {
      St(base, arr + 4 * kept, p);
      ++kept;
      on_ice[(p - Record(sim, t, 0)) / kRecordStride] = true;
      const uint32_t role = Ld(base, p + 16);
      if (role < 5) {
        role_on[role] = true;
      }
    } else {
      if (dropped++ == 0) {
        first_bad = p;
      }
    }
  }
  int want = static_cast<int32_t>(Ld(base, sim + kStrength + 4 * static_cast<uint32_t>(t)));
  if (want < 1 || want > 5) {
    want = 5;
  }
  if (kept >= want && dropped == 0) {
    return kept;
  }
  int placed = 0;
  if (kept < want) {
    int roles_n = 0;
    const int* roles = RolesFor(want, &roles_n);
    // по роли — предпочтительные типы записей (0 центр, 1 крайний, 2 защитник), вратарь (3) — только если больше некого
    static const int kPrefC[] = {0, 1, 2, 3};
    static const int kPrefW[] = {1, 0, 2, 3};
    static const int kPrefD[] = {2, 1, 0, 3};
    // сначала роли, которых на льду нет, потом — любые (на льду меньше положенного при всех ролях)
    for (int pass = 0; pass < 2 && kept + placed < want; ++pass) {
      for (int k = 0; k < roles_n && kept + placed < want; ++k) {
        const int role = roles[k];
        if (pass == 0 && role_on[role]) {
          continue;
        }
        const int* pref = role == 0 ? kPrefC : (role <= 2 ? kPrefW : kPrefD);
        int pick = -1;
        for (int q = 0; q < 4 && pick < 0; ++q) {
          for (int i = 0; i < kRecordCount; ++i) {
            const uint32_t rec = Record(sim, t, i);
            if (!on_ice[i] && !IsEmptyRecord(base, rec) && static_cast<int32_t>(Ld(base, rec + 8)) == pref[q]) {
              pick = i;
              break;
            }
          }
        }
        if (pick < 0) {
          continue;
        }
        on_ice[pick] = true;
        role_on[role] = true;
        const uint32_t rec = Record(sim, t, pick);
        St(base, rec + 16, static_cast<uint32_t>(role));
        St(base, arr + 4 * (kept + placed), rec);
        ++placed;
      }
    }
  }
  for (int j = kept + placed; j < kOnIceSlots; ++j) {
    St(base, arr + 4 * j, 0);
  }
  if (const uint32_t k = LogNumber()) {
    int empty = 0;
    for (int i = 0; i < kRecordCount; ++i) {
      if (IsEmptyRecord(base, Record(sim, t, i))) {
        ++empty;
      }
    }
    std::string bad;
    if (dropped > 0) {
      if (IsRecord(sim, t, first_bad)) {
        bad = fmt::format("; first bad: record {} (pid {} type {} pos {} +24 {})",
                          (first_bad - Record(sim, t, 0)) / kRecordStride, Ld(base, first_bad), Ld(base, first_bad + 8),
                          Ld(base, first_bad + 20), Ld(base, first_bad + 24));
      } else {
        bad = fmt::format("; first bad: pointer {:08X}", first_bad);
      }
    }
    REXLOG_WARN("[nhllegacy] sim guard #{} ({}): sim {:08X} side {} (teamid {}): on the ice {} (bad {}), should be "
                "{} - added {} from the game roster ({} empty records in it){}",
                k, where, sim, t, static_cast<int32_t>(Ld(base, TeamBase(sim, t))), n0, dropped, want, placed, empty,
                bad);
  }
  return kept + placed;
}

// Замена для роли role: первая запись состава матча не на льду и не пустая, по типам в порядке предпочтения роли
// (вратарь — только если больше некого). -1 — некем.
int PickRecord(uint8_t* base, uint32_t sim, int t, int role, const bool* on_ice) {
  static const int kPrefC[] = {0, 1, 2, 3};
  static const int kPrefW[] = {1, 0, 2, 3};
  static const int kPrefD[] = {2, 1, 0, 3};
  const int* pref = role == 0 ? kPrefC : (role <= 2 ? kPrefW : kPrefD);
  for (int q = 0; q < 4; ++q) {
    for (int i = 0; i < kRecordCount; ++i) {
      const uint32_t rec = Record(sim, t, i);
      if (!on_ice[i] && !IsEmptyRecord(base, rec) && static_cast<int32_t>(Ld(base, rec + 8)) == pref[q]) {
        return i;
      }
    }
  }
  return -1;
}

// Сим из живого матча (nhl_sim_guard_live): список на льду после 82984668 и после смены, на которой сим остановлен ради
// живого матча. Неполный список здесь — норма (меньшинство, смену делает живой матч), а место в списке — это место смены
// с флагом +860: добавленный игрок без флага получил бы место 6 и затёр запись 0 состава. Поэтому игроки не добавляются:
// пустые записи и чужие указатели заменяются на том же месте (роль — недостающая; игрок пользователя, запись +8 команды,
// не берётся); кого заменить некем — убирается со сдвигом всех 6 мест (за числом может стоять шестой полевой 82983B48).
// Возвращает новое число.
int RepairInPlace(uint8_t* base, uint32_t sim, int t, uint32_t arr, int n, const char* where) {
  const int n0 = n;
  if (n > kOnIceSlots) {
    n = kOnIceSlots;
  }
  if (n < 0) {
    n = 0;
  }
  bool on_ice[kRecordCount] = {};
  bool role_on[5] = {};
  bool bad[kOnIceSlots] = {};
  int nbad = 0;
  uint32_t first_bad = 0;
  for (int j = 0; j < n; ++j) {
    const uint32_t p = Ld(base, arr + 4 * j);
    if (IsRecord(sim, t, p) && !IsEmptyRecord(base, p)) {
      on_ice[(p - Record(sim, t, 0)) / kRecordStride] = true;
      const uint32_t role = Ld(base, p + 16);
      if (role < 5) {
        role_on[role] = true;
      }
    } else {
      bad[j] = true;
      if (nbad++ == 0) {
        first_bad = p;
      }
    }
  }
  const int field = static_cast<int32_t>(Ld(base, sim + kStrength + 4 * static_cast<uint32_t>(t)));
  const int teamid = static_cast<int32_t>(Ld(base, TeamBase(sim, t)));
  if (nbad == 0) {
    // сборка №8 здесь добавляла бы игроков (полевых меньше поля +18260, а при 0 — меньше 5)
    if (n < (field >= 1 && field <= 5 ? field : 5)) {
      if (const uint32_t k = LiveNoteNumber()) {
        REXLOG_INFO("[nhllegacy] sim guard note {} ({}): sim {:08X} side {} (teamid {}): on the ice {}, strength field "
                    "{} - left as is (sim from the live match: penalty kill or a line change made by the live match)",
                    k, where, sim, t, teamid, n0, field);
      }
    }
    return n;
  }
  const int32_t user_rec = static_cast<int32_t>(Ld(base, TeamBase(sim, t) + 8));
  if (user_rec >= 0 && user_rec < kRecordCount) {
    on_ice[user_rec] = true;
  }
  int replaced = 0;
  for (int j = 0; j < n; ++j) {
    if (!bad[j]) {
      continue;
    }
    int role = 0;
    for (int r = 0; r < 5; ++r) {
      if (!role_on[r]) {
        role = r;
        break;
      }
    }
    const int pick = PickRecord(base, sim, t, role, on_ice);
    if (pick < 0) {
      continue;
    }
    on_ice[pick] = true;
    role_on[role] = true;
    const uint32_t rec = Record(sim, t, pick);
    St(base, rec + 16, static_cast<uint32_t>(role));
    St(base, arr + 4 * j, rec);
    bad[j] = false;
    ++replaced;
  }
  int m = n;
  if (replaced < nbad) {
    int w = 0;
    for (int j = 0; j < kOnIceSlots; ++j) {
      if (j < n && bad[j]) {
        continue;
      }
      St(base, arr + 4 * w, Ld(base, arr + 4 * j));
      ++w;
    }
    for (int j = w; j < kOnIceSlots; ++j) {
      St(base, arr + 4 * j, 0);
    }
    m = n - (nbad - replaced);
  }
  if (const uint32_t k = LogNumber()) {
    std::string what;
    if (IsRecord(sim, t, first_bad)) {
      what = fmt::format("record {} (pid {} type {} pos {} +24 {})", (first_bad - Record(sim, t, 0)) / kRecordStride,
                         Ld(base, first_bad), Ld(base, first_bad + 8), Ld(base, first_bad + 20),
                         Ld(base, first_bad + 24));
    } else {
      what = fmt::format("pointer {:08X}", first_bad);
    }
    REXLOG_WARN("[nhllegacy] sim guard #{} ({}): sim {:08X} side {} (teamid {}): on the ice {} (bad {}), strength field "
                "{} - replaced {} in place, removed {}, none added (sim from the live match); first bad: {}",
                k, where, sim, t, teamid, n0, nbad, field, replaced, nbad - replaced, what);
  }
  return m;
}

// Обе команды объекта симуляции: список на льду и число в самом объекте.
void RepairSim(uint8_t* base, uint32_t sim, const char* where) {
  for (int t = 0; t < 2; ++t) {
    const uint32_t count_at = sim + kOnIceCount + 4 * static_cast<uint32_t>(t);
    const int n = static_cast<int32_t>(Ld(base, count_at));
    const int m = Repair(base, sim, t, sim + kOnIce + kOnIceStride * static_cast<uint32_t>(t), n, where);
    if (m != n) {
      St(base, count_at, static_cast<uint32_t>(m));
    }
  }
}

// Заполнение списка на льду (82984668 — начало матча, массив в r9; 8298E678 — по ходу, массив в r5): r3 — команда.
void AfterFill(PPCContext& ctx, uint8_t* base, uint32_t team, uint32_t arr, const char* where) {
  for (int t = 0; t < 2; ++t) {
    const uint32_t sim = team - kTeam0 - kTeamStride * static_cast<uint32_t>(t);
    if (arr == sim + kOnIce + kOnIceStride * static_cast<uint32_t>(t) && IsSim(base, sim)) {
      ctx.r3.u64 = static_cast<uint32_t>(Repair(base, sim, t, arr, ctx.r3.s32, where));
      return;
    }
  }
}

// Объект симуляции и сторона по команде и массиву на льду (тот же признак, что в AfterFill).
bool FindSim(uint8_t* base, uint32_t team, uint32_t arr, uint32_t* sim_out, int* t_out) {
  for (int t = 0; t < 2; ++t) {
    const uint32_t sim = team - kTeam0 - kTeamStride * static_cast<uint32_t>(t);
    if (arr == sim + kOnIce + kOnIceStride * static_cast<uint32_t>(t) && IsSim(base, sim)) {
      *sim_out = sim;
      *t_out = t;
      return true;
    }
  }
  return false;
}

thread_local uint32_t g_fo_sim = 0;
thread_local int g_fo_team = -1;
thread_local int g_fo_tries = 0;

}  // namespace

// 82984668 зовёт только подготовка из живого матча 8298D450 (vtable сима +60): звенья живого матча, места смен с флагами
// +860. Быстрый сим франшизы сюда не заходит (его звенья — 8298B060).
extern "C" void __imp__sub_82984668(PPCContext& ctx, uint8_t* base);
extern "C" void sub_82984668(PPCContext& ctx, uint8_t* base) {
  if (!On()) {
    __imp__sub_82984668(ctx, base);
    return;
  }
  const uint32_t team = ctx.r3.u32;
  const uint32_t arr = ctx.r9.u32;
  __imp__sub_82984668(ctx, base);
  if (!LiveOn()) {
    AfterFill(ctx, base, team, arr, "start of game");
    return;
  }
  uint32_t sim = 0;
  int t = 0;
  if (FindSim(base, team, arr, &sim, &t)) {
    ctx.r3.u64 = static_cast<uint32_t>(RepairInPlace(base, sim, t, arr, ctx.r3.s32, "sim start"));
  }
}

// Смена звеньев (r3 — команда, r5 — массив на льду, r7 — куда писать код остановки). Сим с остановками для живого
// матча (829935F0 при sim+18268) даёт r7 = sim+28852, быстрый сим — свою переменную на стеке; код 3 — на смене не
// нашлось следующего игрока (+874, сим из живого матча), 1 — на лёд вышел игрок пользователя. Тогда сим сейчас
// остановится и смену сделает живой матч: неполный список — норма, добавлять нельзя (RepairInPlace).
extern "C" void __imp__sub_8298E678(PPCContext& ctx, uint8_t* base);
extern "C" void sub_8298E678(PPCContext& ctx, uint8_t* base) {
  if (!On()) {
    __imp__sub_8298E678(ctx, base);
    return;
  }
  const uint32_t team = ctx.r3.u32;
  const uint32_t arr = ctx.r5.u32;
  const uint32_t out = ctx.r7.u32;
  __imp__sub_8298E678(ctx, base);
  if (LiveOn()) {
    uint32_t sim = 0;
    int t = 0;
    if (FindSim(base, team, arr, &sim, &t) && out == sim + kStop && Ld(base, out) != 0) {
      ctx.r3.u64 = static_cast<uint32_t>(RepairInPlace(base, sim, t, arr, ctx.r3.s32, "line change, sim stops"));
      return;
    }
  }
  AfterFill(ctx, base, team, arr, "line change");
}

// Начало смены игрока: r3 — команда, r4 — запись, r5 — место смены, r6 — время. Создаёт событие смены (роль = место) и
// кладёт указатель на него в команду +876 + 4·место. Мест 6 (+876…+899), сразу за ними — состав матча (+900): место 6
// затирает playerindex записи 0, а событие с ролью 6 живой матч не переносит (падение 11.10). Такое место даёт только
// рассогласование списка на льду с флагами мест (8298E4C8) — пропускаем.
extern "C" void __imp__sub_829798C0(PPCContext& ctx, uint8_t* base);
extern "C" void sub_829798C0(PPCContext& ctx, uint8_t* base) {
  const int32_t slot = ctx.r5.s32;
  if (LiveOn() && (slot < 0 || slot >= kShiftSlots)) {
    if (const uint32_t k = LogNumber()) {
      const uint32_t team = ctx.r3.u32;
      const uint32_t rec = ctx.r4.u32;
      REXLOG_WARN("[nhllegacy] sim guard #{} (shift slot): team {:08X} (teamid {}): player pid {} (record at {:08X}) "
                  "got shift slot {} - skipped, slots are 0..5 (nhl_sim_guard_live)",
                  k, team, static_cast<int32_t>(Ld(base, team)), Ld(base, rec), rec, slot);
    }
    return;
  }
  __imp__sub_829798C0(ctx, base);
}

// Розыгрыш вбрасывания: перед ним — обе команды с игроками на льду; счётчик попыток роли — заново.
extern "C" void __imp__sub_8298A438(PPCContext& ctx, uint8_t* base);
extern "C" void sub_8298A438(PPCContext& ctx, uint8_t* base) {
  if (On() && IsSim(base, ctx.r3.u32)) {
    RepairSim(base, ctx.r3.u32, "faceoff");
    g_fo_sim = ctx.r3.u32;
    g_fo_team = -1;
    g_fo_tries = 0;
  }
  __imp__sub_8298A438(ctx, base);
}

// Роль для вбрасывания (случайная по таблице). Из цикла 8298A438 (r31 — объект, r27 — команда): после 200 промахов —
// роль первого игрока команды на льду, иначе цикл вечный, если на льду нет центра/крайнего.
extern "C" void __imp__sub_82A5C4D0(PPCContext& ctx, uint8_t* base);
extern "C" void sub_82A5C4D0(PPCContext& ctx, uint8_t* base) {
  if (On() && static_cast<uint32_t>(ctx.lr) == kFaceoffCall) {
    const uint32_t sim = ctx.r31.u32;
    const int t = ctx.r27.s32;
    if ((t == 0 || t == 1) && IsSim(base, sim)) {
      if (sim != g_fo_sim || t != g_fo_team) {
        g_fo_sim = sim;
        g_fo_team = t;
        g_fo_tries = 0;
      }
      if (++g_fo_tries > kFaceoffTries) {
        const int n = static_cast<int32_t>(Ld(base, sim + kOnIceCount + 4 * static_cast<uint32_t>(t)));
        const uint32_t first = Ld(base, sim + kOnIce + kOnIceStride * static_cast<uint32_t>(t));
        if (n >= 1 && n <= kOnIceSlots && IsRecord(sim, t, first)) {
          const uint32_t role = Ld(base, first + 16);
          if (const uint32_t k = LogNumber()) {
            REXLOG_WARN("[nhllegacy] sim guard #{} (faceoff): sim {:08X} side {} (teamid {}): no center/winger among {} "
                        "on the ice after {} tries - faceoff by player {} (role {})",
                        k, sim, t, static_cast<int32_t>(Ld(base, TeamBase(sim, t))), n, kFaceoffTries, Ld(base, first),
                        role);
          }
          g_fo_tries = 0;
          ctx.r3.u64 = role;
          return;
        }
      }
    }
  }
  __imp__sub_82A5C4D0(ctx, base);
}

// Событие матча (бросок, борьба и т. п. — 829937F8): берёт игроков из списков на льду обеих команд.
extern "C" void __imp__sub_829937F8(PPCContext& ctx, uint8_t* base);
extern "C" void sub_829937F8(PPCContext& ctx, uint8_t* base) {
  if (On() && IsSim(base, ctx.r3.u32)) {
    RepairSim(base, ctx.r3.u32, "event");
  }
  __imp__sub_829937F8(ctx, base);
}
