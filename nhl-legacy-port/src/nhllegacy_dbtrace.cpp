// Разведка: кто обращается к таблицам базы франшизы и календаря (перенос из порта NHL 13,
// nhl-13-port/src/nhl13_dbtrace.cpp; 32 команды и календарь — docs/legacy-port.md).
//
// Таблицы и поля база ищет по хешу имени (NHL Legacy: 827B6708, в NHL 13 — 826473A8; CRC-32 по
// обычной отражённой таблице, буквы — без бита 0x20, начальное значение 0). Подменяем две
// функции, которые получают хеш таблицы, — обе те же, что в NHL 13: 827B6FA8 (найти таблицу,
// r4 = хеш; в NHL 13 — 82647CA8) и 827B4818 (таблица запроса, r5 = хеш; 8264FFA8). Первое
// появление каждой тройки «функция, таблица, адрес возврата (lr)» пишется в
// nhllegacy_dbtrace.log рядом с exe — так видно, какой код создаёт и заполняет таблицы франшизы
// и откуда берётся календарь. Включено, только если рядом с exe есть файл nhllegacy_dbtrace.on
// (проверяется при запуске).

#include <cstdint>
#include <cstdio>
#include <ctime>
#include <mutex>
#include <set>
#include <tuple>

#include <rex/ppc.h>

#if defined(_WIN32)
#include <windows.h>
#endif

extern "C" void __imp__sub_827B6FA8(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_827B4818(PPCContext& ctx, uint8_t* base);

namespace {

const char* TableName(uint32_t hash) {
  switch (hash) {
    case 0xC7BCD146: return "leagueteams";
    case 0x5A148D17: return "leaguegmdata";
    case 0xD3D19BC7: return "leaguestaffdata";
    case 0xF30185E2: return "leaguedraftpick";
    case 0xE0A915B4: return "leaguescheduletable";
    case 0x1B620550: return "leaguetempscheduletable";
    case 0x7228E37B: return "exhibitionteams";
    case 0x22F0FB98: return "leaguestates";
    case 0xC8DCD770: return "nhlschedule";
    case 0x85864C9D: return "nhlfutureschedule";
    case 0x783C7E8A: return "favoriteteamschedule";
    case 0x37037571: return "nhlplayoffschedule";
    case 0x50E60568: return "leagueplayoffschedule";
    case 0x5ED9088F: return "leagueplayoffseries";
    default: return nullptr;
  }
}

struct Trace {
  bool enabled = false;
  FILE* log = nullptr;
  std::mutex mutex;
  std::set<std::tuple<uint32_t, uint32_t, uint32_t>> seen;
  uint64_t seq = 0;

  Trace() {
#if defined(_WIN32)
    wchar_t exe[MAX_PATH];
    GetModuleFileNameW(nullptr, exe, MAX_PATH);
    std::wstring dir(exe);
    dir = dir.substr(0, dir.find_last_of(L"\\/") + 1);
    enabled = GetFileAttributesW((dir + L"nhllegacy_dbtrace.on").c_str()) != INVALID_FILE_ATTRIBUTES;
    if (enabled) {
      log = _wfopen((dir + L"nhllegacy_dbtrace.log").c_str(), L"a");
    }
#endif
  }

  void Note(uint32_t fn, uint32_t hash, uint32_t lr) {
    const char* name = TableName(hash);
    if (!enabled || !log || !name) {
      return;
    }
    std::lock_guard<std::mutex> lock(mutex);
    ++seq;
    if (seen.insert({fn, hash, lr}).second) {
#if defined(_WIN32)
      SYSTEMTIME t;
      GetLocalTime(&t);
      fprintf(log, "%02u:%02u:%02u.%03u #%llu %08X %-24s lr=%08X\n", t.wHour, t.wMinute, t.wSecond,
              t.wMilliseconds, static_cast<unsigned long long>(seq), fn, name, lr);
#endif
      fflush(log);
    }
  }
};

Trace& GetTrace() {
  static Trace trace;
  return trace;
}

}  // namespace

extern "C" void sub_827B6FA8(PPCContext& ctx, uint8_t* base) {
  GetTrace().Note(0x827B6FA8, ctx.r4.u32, static_cast<uint32_t>(ctx.lr));
  __imp__sub_827B6FA8(ctx, base);
}

extern "C" void sub_827B4818(PPCContext& ctx, uint8_t* base) {
  GetTrace().Note(0x827B4818, ctx.r5.u32, static_cast<uint32_t>(ctx.lr));
  __imp__sub_827B4818(ctx, base);
}
