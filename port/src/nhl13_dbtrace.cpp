// Разведка: кто обращается к таблицам базы франшизы (32 команды, docs/teams.md).
//
// Таблицы и поля база ищет по хешу имени (826473A8: CRC-32 по таблице 0x822C2398,
// буквы — без бита 0x20, начальное значение 0). Подменяем две функции, которые
// получают хеш таблицы: 82647CA8 (найти таблицу, r4 = хеш; через неё и 826469E0) и
// 8264FFA8 (таблица запроса, r5 = хеш). Первое появление каждой тройки
// «функция, таблица, адрес возврата (lr)» пишется в nhl13_dbtrace.log рядом с exe —
// так видно, какой код создаёт и заполняет таблицы франшизы. Включено, только если
// рядом с exe есть файл nhl13_dbtrace.on (проверяется при запуске).

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

extern "C" void __imp__sub_82647CA8(PPCContext& ctx, uint8_t* base);
extern "C" void __imp__sub_8264FFA8(PPCContext& ctx, uint8_t* base);

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
    enabled = GetFileAttributesW((dir + L"nhl13_dbtrace.on").c_str()) != INVALID_FILE_ATTRIBUTES;
    if (enabled) {
      log = _wfopen((dir + L"nhl13_dbtrace.log").c_str(), L"a");
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

extern "C" void sub_82647CA8(PPCContext& ctx, uint8_t* base) {
  GetTrace().Note(0x82647CA8, ctx.r4.u32, static_cast<uint32_t>(ctx.lr));
  __imp__sub_82647CA8(ctx, base);
}

extern "C" void sub_8264FFA8(PPCContext& ctx, uint8_t* base) {
  GetTrace().Note(0x8264FFA8, ctx.r5.u32, static_cast<uint32_t>(ctx.lr));
  __imp__sub_8264FFA8(ctx, base);
}
