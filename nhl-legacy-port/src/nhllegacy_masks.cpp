// Свои вратарские маски в каталоге редактора (nhl_extra_masks; docs/goalie-masks.md, «Свои маски в редакторе»,
// docs/legacy-port.md, «Каталог масок вратаря»).
//
// Список масок в выборе экипировки — не база, а каталог в образе игры: записи по 36 байт, 86 масок и запись-ограничитель
// NotAvailable (тип 99). В образе 21 копия каталога — по одной на модуль кода; статические конструкторы (837xxxxx) при
// старте вписывают в каждую указатели на строки имён. Запись: +0 номер, +4 masktype, +8 maskid, +12/+16/+20 ключи имени
// (бренд, бренд, цвет), +24 число для списка, +28 номер разблокировки (−1 — открыта), +32.
//
// Кто читает каталог (tools/xrefs.py refs по всем копиям, сверено по коду):
// - редактор 82ADE6E0, копия 83A0CE08: цикл 82AE30F0…82AE3498 по записям, r29 = запись + 28, конец — r19 + 3124 (запись 86),
//   r17 = 86 — число записей для списка (82AE3654); выбранная — по совпадению +4/+8 с маской игрока. Ограничитель берётся
//   отдельно, 3096(r29) у 82AE2D78 (маска 99), — это место не трогаем;
// - выбор → игрок, 82AC7048: номер строки списка → 82BEC578(29, i) = masktype (+4), 82BEC578(28, i, 1) = maskid (+8), копия
//   83A3B9B0, предел 87;
// - справочник модуля экипировки, копия 839E5310: 829F4BD0(вид 4) = 87 записей, 829F4C50(4, i) = +4 записи i,
//   829F4D10(4, v) — первая запись с +4 = v. Зовут их 829EF868, 829FB3D0, 829ED680, 829ED850;
// - 829FB4D0 (наборы «что открыто» для случайной экипировки, место на 52 маски) и 82BC22D8 (снять метки «новое» по +28) —
//   не трогаем: новым маскам там делать нечего.
//
// Своя таблица — в памяти гостя: 86 записей копии редактора, за ними записи из файла, в конце ограничитель. Номера записей
// 0…85 совпадают с образом, поэтому всё, что игра уже хранит или передаёт номером, читает то же самое. Редактор
// переводится на неё в начале своего цикла: первая запись цикла зовёт 82BC2238 (открыта ли вещь, подмена в
// nhllegacy_unlock.cpp) — оттуда NhlLegacyMasksEditorLoop меняет r29, r19 и r17 в контексте вызывающего (у
// перекомпилированного кода регистры — поля ctx, вызывающий читает их после вызова). Остальные три справочника и 82BEC578
// подменены целиком для своих видов.
//
// Файл — <cache_root>/guest/nhllegacy_masks.txt (рядом с модами cache:), строка «masktype maskid [preview_id] [подпись]», # —
// комментарий. preview_id — поле +0: по нему редактор берёт превью fe/ion/artassets/createplayer/mask/mask<preview_id>.big
// (проверено 03.11.2026: у новых записей игра просила mask200/201.big); не указан — 1000 + maskid (у EA 1…221). Четвёртое поле —
// ключ подписи +20 (ключи EA: white, red, blue…; что из них выйдет, решает локализация: red дал «BAUER White Middle»); без
// него ключ kNoLabel, и в списке пишется «BAUER».
// Нет файла, пустой или nhl_extra_masks = false — всё как у EA.

#include <atomic>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <set>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ppc.h>
#include <rex/runtime.h>
#include <rex/system/xmemory.h>

REXCVAR_DEFINE_BOOL(nhl_extra_masks, true, "NHLLegacy",
                    "Add goalie masks from cache/guest/nhllegacy_masks.txt (masktype maskid [name]) to the equipment "
                    "editor; without the file the editor is unchanged")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

namespace {

constexpr uint32_t kRecord = 36;
constexpr int kOriginal = 86;                // масок в каталоге EA (без ограничителя)
constexpr uint32_t kEditorCopy = 0x83A0CE08;  // копия редактора (82ADE6E0) — источник своей таблицы
constexpr uint32_t kEditorLoopReturn = 0x82AE3118;  // возврат из 82BC2238 в цикле редактора
constexpr int kKindPicker = 29;   // 82BEC578: masktype по номеру строки
constexpr int kKindMaskId = 28;   // 82BEC578: maskid по номеру строки (с флагом r5)
constexpr int kKindEquip = 4;     // 829F4BD0 / 829F4C50 / 829F4D10: вид «маска»
constexpr int kMaxExtra = 400;    // maskid — 9 бит, больше не нужно
constexpr int kMaxMaskId = 511;
const std::string kNoLabel = "nhllegacy";  // ключ подписи, которого нет в локализации: в списке одно «BAUER»
constexpr int kPreviewBase = 1000;  // preview_id по умолчанию — 1000 + maskid (решение 03.11.2026 вместе с «Моделями»)

std::filesystem::path g_root;  // cache_root/guest

struct Extra {
  int masktype;
  int maskid;
  int preview;  // поле +0: номер превью mask<preview>.big
  std::string name;
};

struct Table {
  uint32_t addr = 0;  // гостевой адрес своей таблицы, 0 — нет (как у EA)
  int count = 0;      // записей вместе с ограничителем
  int extra = 0;
};

std::once_flag g_once;
Table g_table;
std::atomic<bool> g_editor_logged{false};
std::atomic<bool> g_pick_logged{false};

uint32_t Ld(uint8_t* base, uint32_t a) {
  uint32_t v;
  std::memcpy(&v, base + a, 4);
  return __builtin_bswap32(v);
}

void St(uint8_t* base, uint32_t a, uint32_t v) {
  v = __builtin_bswap32(v);
  std::memcpy(base + a, &v, 4);
}

std::vector<Extra> ReadFile(const std::filesystem::path& path) {
  std::vector<Extra> out;
  std::ifstream f(path);
  if (!f) {
    return out;
  }
  std::string line;
  int n = 0;
  while (std::getline(f, line)) {
    ++n;
    if (const size_t hash = line.find('#'); hash != std::string::npos) {
      line.resize(hash);
    }
    std::istringstream s(line);
    Extra e{};
    if (!(s >> e.masktype)) {
      continue;  // пустая строка или комментарий
    }
    if (!(s >> e.maskid) || e.masktype < 0 || e.masktype > 3 || e.maskid < 0 || e.maskid > kMaxMaskId) {
      REXLOG_WARN("[nhllegacy] masks: {} line {}: need «masktype maskid [preview_id] [color]», masktype 0–3, maskid 0–{}",
                  path.string(), n, kMaxMaskId);
      continue;
    }
    std::string rest;
    std::getline(s >> std::ws, rest);
    e.preview = kPreviewBase + e.maskid;
    if (!rest.empty() && rest[0] >= '0' && rest[0] <= '9') {
      char* end = nullptr;
      const long v = std::strtol(rest.c_str(), &end, 10);
      e.preview = v > 0 && v < 100000 ? int(v) : e.preview;
      rest.erase(0, size_t(end - rest.c_str()));
      while (!rest.empty() && (rest[0] == ' ' || rest[0] == '\t')) {
        rest.erase(0, 1);
      }
    }
    e.name = rest;
    while (!e.name.empty() && (e.name.back() == ' ' || e.name.back() == '\t' || e.name.back() == '\r')) {
      e.name.pop_back();
    }
    if (e.name.size() > 31) {
      e.name.resize(31);
    }
    out.push_back(std::move(e));
  }
  return out;
}

void Build(uint8_t* base) {
  if (!REXCVAR_GET(nhl_extra_masks) || g_root.empty()) {
    return;
  }
  const std::filesystem::path path = g_root / "nhllegacy_masks.txt";
  std::vector<Extra> wanted = ReadFile(path);
  if (wanted.empty()) {
    return;
  }
  // Уже есть в каталоге или повтор в файле — пропустить.
  std::set<std::pair<int, int>> seen;
  for (int i = 0; i < kOriginal; ++i) {
    seen.insert({int(Ld(base, kEditorCopy + kRecord * i + 4)), int(Ld(base, kEditorCopy + kRecord * i + 8))});
  }
  std::vector<Extra> extra;
  for (Extra& e : wanted) {
    if (seen.insert({e.masktype, e.maskid}).second && int(extra.size()) < kMaxExtra) {
      extra.push_back(std::move(e));
    } else {
      REXLOG_WARN("[nhllegacy] masks: {}/{} is already in the catalog or listed twice, skipped", e.masktype, e.maskid);
    }
  }
  if (extra.empty()) {
    return;
  }
  const int count = kOriginal + int(extra.size()) + 1;
  const uint32_t strings = uint32_t(extra.size()) * 32;
  const uint32_t addr = rex::Runtime::instance()->memory()->SystemHeapAlloc(uint32_t(count) * kRecord + strings);
  if (!addr) {
    REXLOG_ERROR("[nhllegacy] masks: no guest memory for the catalog, editor unchanged");
    return;
  }
  // 0…85 — как в образе (имена уже вписаны конструктором модуля редактора), дальше свои, в конце ограничитель.
  std::memcpy(base + addr, base + kEditorCopy, kOriginal * kRecord);
  std::memcpy(base + addr + uint32_t(count - 1) * kRecord, base + kEditorCopy + kOriginal * kRecord, kRecord);
  for (size_t k = 0; k < extra.size(); ++k) {
    const Extra& e = extra[k];
    int tmpl = -1;  // образец — первая маска того же типа: те же ключи бренда, число для списка
    for (int i = 0; i < kOriginal && tmpl < 0; ++i) {
      if (int(Ld(base, kEditorCopy + kRecord * i + 4)) == e.masktype) {
        tmpl = i;
      }
    }
    const uint32_t rec = addr + uint32_t(kOriginal + k) * kRecord;
    std::memcpy(base + rec, base + kEditorCopy + kRecord * uint32_t(tmpl < 0 ? 0 : tmpl), kRecord);
    St(base, rec + 0, uint32_t(e.preview));
    St(base, rec + 4, uint32_t(e.masktype));
    St(base, rec + 8, uint32_t(e.maskid));
    St(base, rec + 28, 0xFFFFFFFFu);  // открыта
    // Ключ подписи +20: свой или kNoLabel. Подпись образца («BAUER White No Toe» у 0/119) у новой маски была бы неправдой,
    // а незнакомый ключ редактор не переводит и пишет одно «BAUER» (проверено 03.11.2026 на ключе «Hill»).
    const std::string& key = e.name.empty() ? kNoLabel : e.name;
    const uint32_t s = addr + uint32_t(count) * kRecord + uint32_t(k) * 32;
    std::memcpy(base + s, key.data(), key.size());
    base[s + key.size()] = 0;
    St(base, rec + 20, s);
  }
  g_table.addr = addr;
  g_table.extra = int(extra.size());
  g_table.count = count;
  REXLOG_INFO("[nhllegacy] masks: {} extra goalie masks from {} (editor catalog {} → {}), table at {:08X}", extra.size(),
              path.string(), kOriginal, kOriginal + extra.size(), addr);
}

const Table* Get(uint8_t* base) {
  std::call_once(g_once, Build, base);
  return g_table.addr ? &g_table : nullptr;
}

uint32_t Rec(const Table* t, int i) {
  return t->addr + uint32_t(i) * kRecord;
}

}  // namespace

void NhlLegacyMasksSetRoot(const std::filesystem::path& guest_root) {
  g_root = guest_root;
}

// Из подмены 82BC2238 (nhllegacy_unlock.cpp), до неё: первая запись цикла редактора — перевести цикл на свою таблицу.
void NhlLegacyMasksEditorLoop(PPCContext& ctx, uint8_t* base) {
  if (static_cast<uint32_t>(ctx.lr) != kEditorLoopReturn || ctx.r19.u32 != kEditorCopy) {
    return;
  }
  const Table* t = Get(base);
  if (!t) {
    return;
  }
  const uint32_t offset = ctx.r29.u32 - (kEditorCopy + 28);  // в первой записи 0
  ctx.r29.u64 = t->addr + 28 + offset;
  ctx.r19.u64 = t->addr + uint32_t(t->extra) * kRecord;  // конец цикла r19 + 3124 → после последней своей записи
  ctx.r17.u64 = ctx.r17.u32 + uint32_t(t->extra);
  if (!g_editor_logged.exchange(true)) {
    REXLOG_INFO("[nhllegacy] masks: editor list uses {} masks", kOriginal + t->extra);
  }
}

// 82BEC578(вид r3, номер r4, флаг r5): поле записи каталога. 29 — masktype, 28 с флагом — maskid; остальное — как было.
extern "C" void __imp__sub_82BEC578(PPCContext& ctx, uint8_t* base);
extern "C" void sub_82BEC578(PPCContext& ctx, uint8_t* base) {
  const int kind = ctx.r3.s32, index = ctx.r4.s32;
  if (kind == kKindPicker || (kind == kKindMaskId && (ctx.r5.u32 & 0xFF))) {
    if (const Table* t = Get(base); t && index >= 0 && index < t->count) {
      ctx.r3.u64 = Ld(base, Rec(t, index) + (kind == kKindPicker ? 4 : 8));
      if (index >= kOriginal && !g_pick_logged.exchange(true)) {
        REXLOG_INFO("[nhllegacy] masks: picked extra mask #{} → {}/{}", index, Ld(base, Rec(t, index) + 4),
                    Ld(base, Rec(t, index) + 8));
      }
      return;
    }
  }
  __imp__sub_82BEC578(ctx, base);
}

// 829F4BD0(r3, вид r4): число записей каталога вида.
extern "C" void __imp__sub_829F4BD0(PPCContext& ctx, uint8_t* base);
extern "C" void sub_829F4BD0(PPCContext& ctx, uint8_t* base) {
  if (ctx.r4.u32 == kKindEquip) {
    if (const Table* t = Get(base)) {
      ctx.r3.u64 = uint32_t(t->count);
      return;
    }
  }
  __imp__sub_829F4BD0(ctx, base);
}

// 829F4C50(r3, вид r4, номер r5): +4 записи.
extern "C" void __imp__sub_829F4C50(PPCContext& ctx, uint8_t* base);
extern "C" void sub_829F4C50(PPCContext& ctx, uint8_t* base) {
  if (ctx.r4.u32 == kKindEquip) {
    if (const Table* t = Get(base); t && ctx.r5.s32 >= 0 && ctx.r5.s32 < t->count) {
      ctx.r3.u64 = Ld(base, Rec(t, ctx.r5.s32) + 4);
      return;
    }
  }
  __imp__sub_829F4C50(ctx, base);
}

// 829F4D10(r3, вид r4, значение r5): номер первой записи с +4 = значение, иначе 0. Оригинал берёт число записей у 829F4BD0
// и ходит по своей копии — с длинным числом он вышел бы за её конец, поэтому вид 4 — целиком здесь.
extern "C" void __imp__sub_829F4D10(PPCContext& ctx, uint8_t* base);
extern "C" void sub_829F4D10(PPCContext& ctx, uint8_t* base) {
  if (ctx.r4.u32 == kKindEquip) {
    if (const Table* t = Get(base)) {
      uint32_t found = 0;
      for (int i = 0; i < t->count; ++i) {
        if (Ld(base, Rec(t, i) + 4) == ctx.r5.u32) {
          found = uint32_t(i);
          break;
        }
      }
      ctx.r3.u64 = found;
      return;
    }
  }
  __imp__sub_829F4D10(ctx, base);
}
