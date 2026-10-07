// Сторож кучи мелких блоков гостя («dynamicsba», таблица методов 0x82098FCC):
// 82A9B108 и 82A9AE28 — выделить, 82A9B538 — освободить (вызываются через таблицу).
// Блоки до 256 байт лежат в страницах по 4 КБ одного размера: у страницы +0x00 — сдвиг
// ещё не выданного места, +0x0C — голова списка свободных (первое слово свободного блока —
// следующий), +0x10 — занято (u16), +0x12 — размер в словах (< 0 — страница полная,
// тогда + 257). Объект кучи: +8 — критическая секция, +40 — пустые страницы, +40 + 4 ×
// (класс + 2) — текущая страница класса, +312 — размер страницы, +364/+368 — область.
// Проверок у игры нет: двойное освобождение или запись в освобождённый блок незаметно
// портят список, и падает потом чужое выделение (07.10.2026: после экрана ушедших на
// пенсию голова списка 64-байтных блоков стала 0x004D0061, упал поток загрузки).
//
// Сторож держит для каждого блока стек последнего выделения и освобождения (гостевые
// адреса возврата) и пишет в nhl13_heap.log рядом с exe (строка и в лог рантайма):
//  * двойное освобождение — и пропускает его (иначе блок окажется в списке дважды);
//  * запись в свободный блок — при его повторной выдаче (сумма содержимого без первого
//    слова не сошлась);
//  * испорченную голову списка — до и после выдачи — и обнуляет её (остаток свободных
//    блоков страницы теряется, зато игра не падает).
// Первое двойное освобождение или порча головы снимает слепок процесса (игра замирает
// секунд на 30); запись в свободный блок — только в журнал.
// Всё под критической секцией самой кучи: она рекурсивная, гостевой код войдёт повторно.
//
// Поиск писателя: страницы, где освобождаются узлы дерева лиги (82809330 → 828095A8, порча
// 07.10.2026), ставятся под сторож памяти (nhl13_watch.cpp, до 8 страниц): запись в свободный
// блок попадает в nhl13_watch.log со стеком.

#if defined(_WIN32)

#include <windows.h>

#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <string>

#include <rex/logging.h>
#include <rex/ppc.h>

#include "nhl13_debug.h"

extern "C" void __imp__sub_82A9B108(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_82A9AE28(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_82A9B538(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__RtlEnterCriticalSection(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__RtlLeaveCriticalSection(PPCContext& ctx, uint8_t* base);

namespace {

constexpr int kFrames = 6;       // гостевых адресов возврата на стек
constexpr int kMaxReports = 40;  // на вид отчёта за запуск

struct Rec {
  uint32_t addr;            // блок записи (0 — пусто; блоки меньше 16 байт делят запись)
  uint32_t size;            // размер блока при последней операции
  uint32_t free;            // 1 — освобождён
  uint32_t sum;             // сумма содержимого без первого слова при освобождении
  uint32_t alloc[kFrames];  // стек последнего выделения
  uint32_t freed[kFrames];  // стек последнего освобождения
};

struct HeapTable {
  std::atomic<uint32_t> heap{0};
  uint32_t start = 0;
  uint32_t end = 0;
  uint32_t mask = 0;               // размер страницы − 1
  Rec* recs = nullptr;             // по записи на 16 байт области
  uint32_t* last = nullptr;        // последний выданный блок страницы
  bool tracked = false;
};

HeapTable g_heaps[8];
std::mutex g_heaps_mutex;
std::mutex g_log_mutex;
std::atomic<int> g_reports[4];
std::atomic<bool> g_snapshot_taken{false};

uint8_t* Host(uint8_t* base, uint32_t addr) {
  return base + addr + (addr >= 0xE0000000u ? 0x1000u : 0u);
}

uint32_t Load32(uint8_t* base, uint32_t addr) {
  uint32_t v;
  std::memcpy(&v, Host(base, addr), 4);
  return __builtin_bswap32(v);
}

uint16_t Load16(uint8_t* base, uint32_t addr) {
  uint16_t v;
  std::memcpy(&v, Host(base, addr), 2);
  return __builtin_bswap16(v);
}

void Store32(uint8_t* base, uint32_t addr, uint32_t v) {
  v = __builtin_bswap32(v);
  std::memcpy(Host(base, addr), &v, 4);
}

HeapTable* Table(uint8_t* base, uint32_t heap) {
  for (auto& t : g_heaps) {
    const uint32_t h = t.heap.load(std::memory_order_acquire);
    if (h == heap) {
      return t.tracked ? &t : nullptr;
    }
    if (h == 0) {
      break;
    }
  }
  std::lock_guard<std::mutex> lock(g_heaps_mutex);
  for (auto& t : g_heaps) {
    const uint32_t h = t.heap.load(std::memory_order_relaxed);
    if (h == heap) {
      return t.tracked ? &t : nullptr;
    }
    if (h != 0) {
      continue;
    }
    const uint32_t start = Load32(base, heap + 364);
    const uint32_t end = Load32(base, heap + 368);
    const uint32_t page = Load32(base, heap + 312);
    if (start && end > start && end - start <= (256u << 20) && page >= 0x400 && !(page & (page - 1))) {
      const size_t nrec = (end - start) / 16 + 1;
      const size_t npage = (end - start) / page + 1;
      t.recs = static_cast<Rec*>(
          VirtualAlloc(nullptr, nrec * sizeof(Rec), MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE));
      t.last = static_cast<uint32_t*>(
          VirtualAlloc(nullptr, npage * sizeof(uint32_t), MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE));
      t.start = start;
      t.end = end;
      t.mask = page - 1;
      t.tracked = t.recs && t.last;
      REXLOG_INFO("[nhl13] heap guard: heap {:08X} region {:08X}..{:08X} page {:X}", heap, start, end, page);
    }
    t.heap.store(heap, std::memory_order_release);
    return t.tracked ? &t : nullptr;
  }
  return nullptr;
}

bool Inside(const HeapTable* t, uint32_t a) {
  return a >= t->start && a < t->end;
}

uint32_t BlockSize(uint8_t* base, uint32_t page) {
  int32_t cls = static_cast<int16_t>(Load16(base, page + 18));
  if (cls < 0) {
    cls += 257;
  }
  return cls > 0 && cls <= 64 ? static_cast<uint32_t>(cls) * 4 : 0;
}

bool HeadOk(const HeapTable* t, uint32_t page, uint32_t head) {
  return head == 0 || ((head & ~t->mask) == page && (head & t->mask) >= 0x14);
}

uint32_t Sum(uint8_t* base, uint32_t block, uint32_t size) {
  uint32_t h = 2166136261u;  // FNV-1a без первого слова (там ссылка списка)
  const uint8_t* p = Host(base, block);
  for (uint32_t i = 4; i < size; ++i) {
    h = (h ^ p[i]) * 16777619u;
  }
  return h;
}

// Стек гостя на входе в метод кучи: lr — возврат в вызвавшего, дальше по цепочке r1
// (сохранённый LR функции лежит на −8 от её кадра у вызывающего).
void GuestStack(uint8_t* base, const PPCContext& ctx, uint32_t* out) {
  std::memset(out, 0, kFrames * sizeof(uint32_t));
  out[0] = static_cast<uint32_t>(ctx.lr);
  uint32_t sp = ctx.r1.u32;
  for (int i = 1; i < kFrames; ++i) {
    if (sp < 0x70000000u || sp >= 0x7FFF0000u) {
      return;
    }
    const uint32_t back = Load32(base, sp);
    if (back <= sp || back - sp > 0x100000u || back >= 0x80000000u) {
      return;
    }
    out[i] = Load32(base, back - 8);
    sp = back;
  }
}

// Вход/выход в критическую секцию кучи (heap + 8) тем же гостевым потоком.
void HeapLock(PPCContext& ctx, uint8_t* base, uint32_t heap, bool enter) {
  // аргументы метода (r3–r8) ещё нужны: сохранить всё изменяемое вызовом
  const PPCRegister r0 = ctx.r0, r3 = ctx.r3, r4 = ctx.r4, r5 = ctx.r5, r6 = ctx.r6, r7 = ctx.r7,
                    r8 = ctx.r8, r9 = ctx.r9, r10 = ctx.r10, r11 = ctx.r11, r12 = ctx.r12, ctr = ctx.ctr;
  const uint64_t lr = ctx.lr;
  ctx.r3.u64 = heap + 8;
  if (enter) {
    __imp__RtlEnterCriticalSection(ctx, base);
  } else {
    __imp__RtlLeaveCriticalSection(ctx, base);
  }
  ctx.r0 = r0;
  ctx.r3 = r3;
  ctx.r4 = r4;
  ctx.r5 = r5;
  ctx.r6 = r6;
  ctx.r7 = r7;
  ctx.r8 = r8;
  ctx.r9 = r9;
  ctx.r10 = r10;
  ctx.r11 = r11;
  ctx.r12 = r12;
  ctx.ctr = ctr;
  ctx.lr = lr;
}

std::wstring ExeDir() {
  wchar_t exe[MAX_PATH];
  GetModuleFileNameW(nullptr, exe, MAX_PATH);
  std::wstring path(exe);
  return path.substr(0, path.find_last_of(L"\\/") + 1);
}

void WriteStack(FILE* f, const char* what, const uint32_t* s) {
  fprintf(f, "  %s:", what);
  for (int i = 0; i < kFrames && s[i]; ++i) {
    fprintf(f, " %08X", s[i]);
  }
  fprintf(f, "\n");
}

void WriteBlock(FILE* f, uint8_t* base, const char* what, uint32_t block, uint32_t size) {
  fprintf(f, "  %s %08X (%u байт):\n", what, block, size);
  const uint8_t* p = Host(base, block);
  for (uint32_t o = 0; o < size; o += 16) {
    fprintf(f, "    +%02X ", o);
    for (uint32_t i = o; i < o + 16 && i < size; i += 4) {
      fprintf(f, " %08X", Load32(base, block + i));
    }
    fprintf(f, "  |");
    for (uint32_t i = o; i < o + 16 && i < size; ++i) {
      fputc(p[i] >= 32 && p[i] < 127 ? p[i] : '.', f);
    }
    fprintf(f, "|  u16:");
    for (uint32_t i = o; i + 1 < o + 16 && i + 1 < size; i += 2) {
      const uint16_t c = static_cast<uint16_t>(p[i] << 8 | p[i + 1]);
      fputc(c >= 32 && c < 127 ? static_cast<int>(c) : '.', f);
    }
    fprintf(f, "\n");
  }
}

void WriteRec(FILE* f, const HeapTable* t, uint32_t block, const char* what) {
  if (!Inside(t, block)) {
    return;
  }
  const Rec& r = t->recs[(block - t->start) >> 4];
  if (r.addr != block) {
    fprintf(f, "  %s %08X: записи нет (в записи %08X)\n", what, block, r.addr);
    return;
  }
  fprintf(f, "  %s %08X: %s, размер %u\n", what, block, r.free ? "свободен" : "выдан", r.size);
  WriteStack(f, "    выделен", r.alloc);
  WriteStack(f, "    освобождён", r.freed);
}

// kind: 0 — двойное освобождение, 1 — запись в свободный, 2 — голова до выдачи, 3 — после.
FILE* BeginReport(int kind, const char* title) {
  if (g_reports[kind].fetch_add(1) >= kMaxReports) {
    return nullptr;
  }
  REXLOG_ERROR("[nhl13] heap guard: {}", title);
  FILE* f = _wfopen((ExeDir() + L"nhl13_heap.log").c_str(), L"a");
  if (!f) {
    return nullptr;
  }
  SYSTEMTIME st;
  GetLocalTime(&st);
  fprintf(f, "== %02u:%02u:%02u.%03u поток %lu: %s\n", st.wHour, st.wMinute, st.wSecond,
          st.wMilliseconds, GetCurrentThreadId(), title);
  return f;
}

void EndReport(FILE* f) {
  fprintf(f, "\n");
  fclose(f);
}

void SnapshotOnce() {
  if (!g_snapshot_taken.exchange(true)) {
    Nhl13WriteSnapshot("heap");
  }
}

// Фильтр сторожа памяти (вызывается из обработчика исключений): гостевой адрес — внутри
// блока, который сейчас свободен. Запись блока — по его первым 16 байтам, поэтому ищем назад.
bool InsideFreeBlock(uint32_t guest) {
  for (auto& t : g_heaps) {
    if (!t.heap.load(std::memory_order_acquire)) {
      break;
    }
    if (!t.tracked || guest < t.start || guest >= t.end) {
      continue;
    }
    const uint32_t g = (guest - t.start) >> 4;
    for (uint32_t k = 0; k < 16 && k <= g; ++k) {
      const Rec& r = t.recs[g - k];
      if (r.addr && r.addr <= guest && guest < r.addr + r.size) {
        return r.free != 0;
      }
    }
    return false;
  }
  return false;
}

bool StackHas(const uint32_t* s, uint32_t addr) {
  for (int i = 0; i < kFrames; ++i) {
    if (s[i] == addr) {
      return true;
    }
  }
  return false;
}

// Голова списка текущей страницы класса до выдачи (её порча обрушила бы выделение).
bool CheckClassHead(uint8_t* base, HeapTable* t, uint32_t heap, uint32_t rounded, const uint32_t* stack) {
  const uint32_t cls = (rounded + 3) >> 2;
  if (cls == 0 || cls > 64) {
    return false;
  }
  const uint32_t page = Load32(base, heap + 40 + (cls + 2) * 4);
  if (!Inside(t, page) || (page & t->mask)) {
    return false;
  }
  const uint32_t head = Load32(base, page + 12);
  if (HeadOk(t, page, head)) {
    return false;
  }
  std::lock_guard<std::mutex> lock(g_log_mutex);
  if (FILE* f = BeginReport(2, "free list head corrupted before alloc")) {
    fprintf(f, "  страница %08X класса %u: голова %08X — обнуляю\n", page, cls, head);
    WriteStack(f, "выделяет", stack);
    const uint32_t size = BlockSize(base, page);
    const uint32_t last = t->last[(page - t->start) / (t->mask + 1)];
    if (last && size) {
      WriteRec(f, t, last, "последний выданный");
      WriteBlock(f, base, "его содержимое", last, size);
    }
    WriteBlock(f, base, "заголовок страницы", page, 0x40);
    EndReport(f);
  }
  Store32(base, page + 12, 0);
  return true;
}

// После выдачи: запись в свободный блок и голова списка его страницы (true — голова
// была испорчена).
bool AfterAlloc(uint8_t* base, HeapTable* t, uint32_t block, const uint32_t* stack) {
  if (!Inside(t, block)) {
    return false;
  }
  bool found = false;
  const uint32_t page = block & ~t->mask;
  const uint32_t size = BlockSize(base, page);
  Rec& r = t->recs[(block - t->start) >> 4];
  if (size && r.addr == block && r.free && r.size == size && Sum(base, block, size) != r.sum) {
    std::lock_guard<std::mutex> lock(g_log_mutex);
    if (FILE* f = BeginReport(1, "write into freed block")) {
      fprintf(f, "  блок %08X (страница %08X) изменился после освобождения\n", block, page);
      WriteStack(f, "выдаётся снова", stack);
      WriteRec(f, t, block, "блок");
      WriteBlock(f, base, "содержимое сейчас", block, size);
      EndReport(f);
    }
  }
  const uint32_t head = Load32(base, page + 12);
  if (!HeadOk(t, page, head)) {
    std::lock_guard<std::mutex> lock(g_log_mutex);
    if (FILE* f = BeginReport(3, "free list head corrupted by popped block")) {
      fprintf(f, "  выдан %08X (страница %08X), его ссылка «следующий» = %08X — обнуляю голову\n",
              block, page, head);
      WriteStack(f, "выделяет", stack);
      WriteRec(f, t, block, "блок");
      WriteBlock(f, base, "содержимое", block, size ? size : 64);
      if (size && block - size >= page + 0x14) {
        WriteRec(f, t, block - size, "сосед перед ним");
        WriteBlock(f, base, "содержимое соседа", block - size, size);
      }
      EndReport(f);
    }
    Store32(base, page + 12, 0);
    found = true;
  }
  r.addr = block;
  r.size = size;
  r.free = 0;
  std::memcpy(r.alloc, stack, sizeof(r.alloc));
  t->last[(page - t->start) / (t->mask + 1)] = block;
  return found;
}

void Alloc(PPCContext& ctx, uint8_t* base, uint32_t rounded, void (*imp)(PPCContext&, uint8_t*)) {
  const uint32_t heap = ctx.r3.u32;
  HeapTable* t = Table(base, heap);
  if (!t) {
    imp(ctx, base);
    return;
  }
  uint32_t stack[kFrames];
  GuestStack(base, ctx, stack);
  HeapLock(ctx, base, heap, true);
  bool found = CheckClassHead(base, t, heap, rounded, stack);
  imp(ctx, base);
  found |= AfterAlloc(base, t, ctx.r3.u32, stack);
  HeapLock(ctx, base, heap, false);
  if (found) {
    SnapshotOnce();
  }
}

}  // namespace

// Выделить: r3 — куча, r5 — размер, r6 — флаги, r7 — выравнивание; вернёт блок или 0.
extern "C" void sub_82A9B108(PPCContext& ctx, uint8_t* base) {
  const uint32_t align = ctx.r7.u32 ? ctx.r7.u32 : 1;
  const uint32_t rounded = (ctx.r5.u32 + align - 1) & ~(align - 1);
  Alloc(ctx, base, rounded, __imp__sub_82A9B108);
}

// Выделить: r3 — куча, r4 — параметры (+28 — выравнивание − 1, +36 — флаги), r5 — размер.
extern "C" void sub_82A9AE28(PPCContext& ctx, uint8_t* base) {
  const uint32_t mask = Load32(base, ctx.r4.u32 + 28);
  const uint32_t rounded = (ctx.r5.u32 + mask) & ~mask;
  Alloc(ctx, base, rounded, __imp__sub_82A9AE28);
}

// Освободить: r3 — куча, r5 — блок; вернёт размер блока или 0 (не из этой кучи).
extern "C" void sub_82A9B538(PPCContext& ctx, uint8_t* base) {
  const uint32_t heap = ctx.r3.u32;
  const uint32_t block = ctx.r5.u32;
  HeapTable* t = Table(base, heap);
  if (!t || !Inside(t, block)) {
    __imp__sub_82A9B538(ctx, base);
    return;
  }
  uint32_t stack[kFrames];
  GuestStack(base, ctx, stack);
  HeapLock(ctx, base, heap, true);
  const uint32_t page = block & ~t->mask;
  const uint32_t size = BlockSize(base, page);
  Rec& r = t->recs[(block - t->start) >> 4];
  if (r.addr == block && r.free && r.size == size) {
    {
      std::lock_guard<std::mutex> lock(g_log_mutex);
      if (FILE* f = BeginReport(0, "double free (skipped)")) {
        fprintf(f, "  блок %08X (страница %08X) уже свободен — пропускаю\n", block, page);
        WriteStack(f, "освобождает снова", stack);
        WriteRec(f, t, block, "блок");
        WriteBlock(f, base, "содержимое", block, size ? size : 64);
        EndReport(f);
      }
    }
    HeapLock(ctx, base, heap, false);
    ctx.r3.u64 = size;
    SnapshotOnce();
    return;
  }
  r.addr = block;
  r.size = size;
  r.free = 0;
  std::memcpy(r.freed, stack, sizeof(r.freed));
  __imp__sub_82A9B538(ctx, base);
  r.sum = size ? Sum(base, block, size) : 0;
  r.free = 1;
  if (StackHas(stack, 0x828095A8u)) {  // узел дерева лиги со стека 82809330
    Nhl13WatchPage(block, InsideFreeBlock);  // занятые 8 страниц — откажет сам
  }
  if (Load16(base, page + 16) == 0) {
    // страница опустела и ушла в запас: её блоки получат другой размер
    for (uint32_t a = page; a < page + t->mask + 1; a += 16) {
      if (Inside(t, a)) {
        t->recs[(a - t->start) >> 4].addr = 0;
      }
    }
    t->last[(page - t->start) / (t->mask + 1)] = 0;
  }
  HeapLock(ctx, base, heap, false);
}

#endif
