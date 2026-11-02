// Проверка и добавление файла ROSTER (кнопка «Обновить ростеры», --import-roster, docs/launcher.md).
//
// Всё здесь, без Python и внешних библиотек: CRC, inflate, разбор базы TDB. То же в tools/tdb.py (SaveFile, ZlibV4),
// сверено на всех сейвах ROSTER пользователя. Файл только читается, пишет один AddRoster: сначала во временную папку
// рядом, потом переименование.
//
// Что сверяет игра (docs/launcher.md, «Как игра проверяет ростер»): подпись, версию и суммы, причём читает файл ровно на ту
// длину, которую занимает в памяти группа таблиц rosters. Длина складывается из мест (max) всех таблиц, а места у игры свои:
// число seats из её кода, если строк в базе не больше него, иначе строки + maxinsert схемы. Файл другой длины игра называет
// «appears to be damaged». Лаунчер сверяет места по каждой таблице, это строже: файл, который сделала сама игра, проходит.

#pragma once

#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <map>
#include <string>
#include <vector>

namespace roster {

// Коды возврата --import-roster и --check-roster.
enum Code {
  kOk = 0,
  kBadArgs = 1,
  kCannotRead = 2,
  kNotASave = 3,
  kWrongSaveType = 4,
  kDamaged = 5,
  kIncompatible = 6,
  kGameRunning = 7,
  kNoBase = 8,
  kWriteFailed = 9,
};

struct Result {
  Code code = kOk;
  std::wstring en, ru;
  const std::wstring& Text(int lang) const { return lang == 1 ? ru : en; }
};

inline Result Fail(Code code, std::wstring en, std::wstring ru) {
  Result r;
  r.code = code;
  r.en = std::move(en);
  r.ru = std::move(ru);
  return r;
}

// ─── Суммы ─────────────────────────────────────────────────────────────────────────────────

inline uint32_t Crc32Ieee(const uint8_t* p, size_t n) {
  static uint32_t table[256];
  if (table[1] == 0) {
    for (uint32_t i = 0; i < 256; ++i) {
      uint32_t c = i;
      for (int k = 0; k < 8; ++k) c = (c & 1) ? 0xEDB88320u ^ (c >> 1) : c >> 1;
      table[i] = c;
    }
  }
  uint32_t c = 0xFFFFFFFFu;
  for (size_t i = 0; i < n; ++i) c = table[(c ^ p[i]) & 0xFF] ^ (c >> 8);
  return c ^ 0xFFFFFFFFu;
}

// CRC-32/MPEG-2: старшим битом вперёд, начало FFFFFFFF, без инверсии в конце. BZIP2 — то же с инверсией.
inline uint32_t Crc32Mpeg2(const uint8_t* p, size_t n) {
  static uint32_t table[256];
  if (table[1] == 0) {
    for (uint32_t i = 0; i < 256; ++i) {
      uint32_t c = i << 24;
      for (int k = 0; k < 8; ++k) c = (c & 0x80000000u) ? (c << 1) ^ 0x04C11DB7u : c << 1;
      table[i] = c;
    }
  }
  uint32_t c = 0xFFFFFFFFu;
  for (size_t i = 0; i < n; ++i) c = (c << 8) ^ table[((c >> 24) ^ p[i]) & 0xFF];
  return c;
}
inline uint32_t Crc32Bzip2(const uint8_t* p, size_t n) { return Crc32Mpeg2(p, n) ^ 0xFFFFFFFFu; }

inline uint32_t Adler32(const uint8_t* p, size_t n) {
  uint32_t a = 1, b = 0;
  while (n > 0) {
    const size_t m = std::min<size_t>(n, 5552);
    for (size_t i = 0; i < m; ++i) {
      a += p[i];
      b += a;
    }
    a %= 65521;
    b %= 65521;
    p += m;
    n -= m;
  }
  return (b << 16) | a;
}

inline uint32_t Be32(const uint8_t* p) {
  return (uint32_t(p[0]) << 24) | (uint32_t(p[1]) << 16) | (uint32_t(p[2]) << 8) | p[3];
}
inline uint32_t Le32(const uint8_t* p) {
  return (uint32_t(p[3]) << 24) | (uint32_t(p[2]) << 16) | (uint32_t(p[1]) << 8) | p[0];
}
inline uint16_t Be16(const uint8_t* p) { return static_cast<uint16_t>((p[0] << 8) | p[1]); }

// ─── Inflate (RFC 1951) ────────────────────────────────────────────────────────────────────

class Inflate {
 public:
  Inflate(const uint8_t* in, size_t size, std::vector<uint8_t>& out, size_t limit)
      : in_(in), size_(size), out_(out), limit_(limit) {}

  // Разжать поток deflate; false — поток испорчен или длиннее limit.
  bool Run() {
    for (;;) {
      int last = 0, type = 0;
      if (!Bits(1, last) || !Bits(2, type)) return false;
      bool ok = false;
      if (type == 0) {
        ok = Stored();
      } else if (type == 1) {
        ok = Fixed();
      } else if (type == 2) {
        ok = Dynamic();
      }
      if (!ok) return false;
      if (last) return true;
    }
  }

  size_t Used() const { return pos_; }  // байт потока прочитано (неполный байт считается целым)

 private:
  static constexpr int kMaxBits = 15;
  struct Huffman {
    short count[kMaxBits + 1];
    short symbol[288];
  };

  bool Bits(int need, int& value) {
    uint32_t v = buf_;
    while (cnt_ < need) {
      if (pos_ >= size_) return false;
      v |= uint32_t(in_[pos_++]) << cnt_;
      cnt_ += 8;
    }
    buf_ = need == 32 ? 0 : v >> need;
    cnt_ -= need;
    value = static_cast<int>(v & ((1u << need) - 1));
    return true;
  }

  bool Decode(const Huffman& h, int& symbol) {
    int code = 0, first = 0, index = 0;
    for (int len = 1; len <= kMaxBits; ++len) {
      int bit = 0;
      if (!Bits(1, bit)) return false;
      code |= bit;
      const int count = h.count[len];
      if (code - count < first) {
        symbol = h.symbol[index + (code - first)];
        return true;
      }
      index += count;
      first += count;
      first <<= 1;
      code <<= 1;
    }
    return false;
  }

  // Канонический код из длин; false — кодов больше, чем помещается.
  static bool Build(Huffman& h, const short* length, int n) {
    std::memset(h.count, 0, sizeof(h.count));
    for (int i = 0; i < n; ++i) h.count[length[i]]++;
    int left = 1;
    for (int len = 1; len <= kMaxBits; ++len) {
      left <<= 1;
      left -= h.count[len];
      if (left < 0) return false;
    }
    short offs[kMaxBits + 1] = {};
    for (int len = 1; len < kMaxBits; ++len) offs[len + 1] = static_cast<short>(offs[len] + h.count[len]);
    for (int i = 0; i < n; ++i) {
      if (length[i] != 0) h.symbol[offs[length[i]]++] = static_cast<short>(i);
    }
    return true;
  }

  bool Stored() {
    buf_ = 0;
    cnt_ = 0;
    if (pos_ + 4 > size_) return false;
    const unsigned len = in_[pos_] | (in_[pos_ + 1] << 8);
    const unsigned nlen = in_[pos_ + 2] | (in_[pos_ + 3] << 8);
    pos_ += 4;
    if ((len ^ 0xFFFFu) != nlen || pos_ + len > size_ || out_.size() + len > limit_) return false;
    out_.insert(out_.end(), in_ + pos_, in_ + pos_ + len);
    pos_ += len;
    return true;
  }

  bool Codes(const Huffman& lens, const Huffman& dists) {
    static const short kLenBase[29] = {3,  4,  5,  6,  7,  8,  9,  10, 11,  13,  15,  17,  19,  23, 27,
                                       31, 35, 43, 51, 59, 67, 83, 99, 115, 131, 163, 195, 227, 258};
    static const short kLenExtra[29] = {0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 0};
    static const short kDistBase[30] = {1,   2,   3,   4,   5,   7,    9,    13,   17,   25,
                                        33,  49,  65,  97,  129, 193,  257,  385,  513,  769,
                                        1025, 1537, 2049, 3073, 4097, 6145, 8193, 12289, 16385, 24577};
    static const short kDistExtra[30] = {0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13};
    for (;;) {
      int symbol = 0;
      if (!Decode(lens, symbol)) return false;
      if (symbol < 256) {
        if (out_.size() >= limit_) return false;
        out_.push_back(static_cast<uint8_t>(symbol));
      } else if (symbol == 256) {
        return true;
      } else {
        symbol -= 257;
        if (symbol >= 29) return false;
        int extra = 0;
        if (!Bits(kLenExtra[symbol], extra)) return false;
        const size_t len = static_cast<size_t>(kLenBase[symbol] + extra);
        if (!Decode(dists, symbol) || symbol >= 30) return false;
        if (!Bits(kDistExtra[symbol], extra)) return false;
        const size_t dist = static_cast<size_t>(kDistBase[symbol] + extra);
        if (dist > out_.size() || out_.size() + len > limit_) return false;
        size_t from = out_.size() - dist;
        for (size_t i = 0; i < len; ++i) out_.push_back(out_[from++]);
      }
    }
  }

  bool Fixed() {
    short length[320];
    for (int i = 0; i < 144; ++i) length[i] = 8;
    for (int i = 144; i < 256; ++i) length[i] = 9;
    for (int i = 256; i < 280; ++i) length[i] = 7;
    for (int i = 280; i < 288; ++i) length[i] = 8;
    Huffman lens, dists;
    if (!Build(lens, length, 288)) return false;
    for (int i = 0; i < 30; ++i) length[i] = 5;
    if (!Build(dists, length, 30)) return false;
    return Codes(lens, dists);
  }

  bool Dynamic() {
    static const short kOrder[19] = {16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15};
    int nlen = 0, ndist = 0, ncode = 0;
    if (!Bits(5, nlen) || !Bits(5, ndist) || !Bits(4, ncode)) return false;
    nlen += 257;
    ndist += 1;
    ncode += 4;
    if (nlen > 286 || ndist > 30) return false;
    short length[320] = {};
    for (int i = 0; i < ncode; ++i) {
      int v = 0;
      if (!Bits(3, v)) return false;
      length[kOrder[i]] = static_cast<short>(v);
    }
    Huffman lens, dists;
    if (!Build(lens, length, 19)) return false;
    int index = 0;
    while (index < nlen + ndist) {
      int symbol = 0;
      if (!Decode(lens, symbol)) return false;
      if (symbol < 16) {
        length[index++] = static_cast<short>(symbol);
      } else {
        int prev = 0, extra = 0;
        if (symbol == 16) {
          if (index == 0) return false;
          prev = length[index - 1];
          if (!Bits(2, extra)) return false;
          extra += 3;
        } else if (symbol == 17) {
          if (!Bits(3, extra)) return false;
          extra += 3;
        } else {
          if (!Bits(7, extra)) return false;
          extra += 11;
        }
        if (index + extra > nlen + ndist) return false;
        while (extra-- > 0) length[index++] = static_cast<short>(prev);
      }
    }
    if (length[256] == 0) return false;
    if (!Build(lens, length, nlen) || !Build(dists, length + nlen, ndist)) return false;
    return Codes(lens, dists);
  }

  const uint8_t* in_;
  size_t size_;
  size_t pos_ = 0;
  uint32_t buf_ = 0;
  int cnt_ = 0;
  std::vector<uint8_t>& out_;
  size_t limit_;
};

// ─── База TDB ──────────────────────────────────────────────────────────────────────────────

constexpr uint32_t kTableHeader = 0x28;
constexpr uint32_t kFieldSize = 16;
constexpr uint32_t kIndexSize = 16;
constexpr char kIndexedTable[] = "caBZ";  // exhibitionplayers: в сейве у неё описание индекса, в базе его нет

struct Table {
  std::string id;
  uint32_t block = 0, records = 0, reclen = 0, end = 0;
  uint16_t max = 0, cur = 0, deleted = 0, head = 0;
  uint8_t fields = 0, indices = 0;
};

class Tdb {
 public:
  // Разбор заголовка и таблиц со всеми границами: файл может быть чем угодно. false — база не читается. exact — без дыр
  // между таблицами: так пишет игра, в сейве это проверяется, в nhlng.db незачем.
  bool Parse(const uint8_t* data, size_t size, bool exact) {
    d_ = data;
    n_ = size;
    tables_.clear();
    if (size < 0x1C || data[0] != 'D' || data[1] != 'B' || data[4] != 1) return false;  // только big-endian
    const uint32_t count = Be32(data + 0x10);
    if (count == 0 || count > 1024 || 0x18 + 8ull * count + 4 > size) return false;
    const uint32_t first = 0x18 + 8 * count;
    std::vector<std::pair<uint32_t, std::string>> order;
    for (uint32_t i = 0; i < count; ++i) {
      const uint8_t* e = data + 0x18 + 8 * i;
      const uint64_t block = uint64_t(first) + Be32(e + 4);
      if (block + kTableHeader > size) return false;
      order.push_back({static_cast<uint32_t>(block), std::string(reinterpret_cast<const char*>(e), 4)});
    }
    std::sort(order.begin(), order.end());
    for (size_t i = 0; i < order.size(); ++i) {
      Table t;
      t.id = order[i].second;
      t.block = order[i].first;
      const uint8_t* h = data + t.block;
      t.reclen = Be32(h + 8);
      t.max = Be16(h + 0x14);
      t.cur = Be16(h + 0x16);
      t.deleted = Be16(h + 0x18);
      t.head = Be16(h + 0x1A);
      t.fields = h[0x1C];
      t.indices = h[0x1D];
      t.end = i + 1 < order.size() ? order[i + 1].first : static_cast<uint32_t>(size - 4);
      const uint64_t records = uint64_t(t.block) + kTableHeader + uint64_t(kFieldSize) * t.fields;
      const uint64_t body = records + uint64_t(t.reclen) * t.max + uint64_t(kIndexSize) * t.indices;
      if (body > t.end || (exact && body != t.end) || t.cur > t.max) return false;
      t.records = static_cast<uint32_t>(records);
      by_id_[t.id] = tables_.size();
      tables_.push_back(t);
    }
    return true;
  }

  // Суммы базы: заголовок, у каждой таблицы тело предыдущей и свой заголовок, в конце тело последней.
  bool VerifySums() const {
    if (Be32(d_ + 0x14) != Crc32Mpeg2(d_, 0x14)) return false;
    const uint32_t first = 0x18 + 8 * static_cast<uint32_t>(tables_.size());
    uint32_t prev = 0x18, prev_end = first;
    for (const Table& t : tables_) {
      if (Be32(d_ + t.block) != Crc32Mpeg2(d_ + prev, prev_end - prev)) return false;
      if (Be32(d_ + t.block + 0x24) != Crc32Mpeg2(d_ + t.block + 4, 0x20)) return false;
      prev = t.block + kTableHeader;
      prev_end = t.end;
    }
    return Be32(d_ + n_ - 4) == Crc32Mpeg2(d_ + prev, prev_end - prev);
  }

  // Список удалённых записей: длина как в счётчике, без циклов, номера в пределах таблицы.
  bool VerifyFreeList(const Table& t) const {
    uint32_t r = t.head, steps = 0;
    std::vector<bool> seen(t.max, false);
    while (r != 0xFFFF) {
      if (r >= t.max || seen[r] || steps == t.deleted) return false;
      seen[r] = true;
      ++steps;
      if (t.reclen < 2) return false;
      r = Be16(d_ + t.records + uint64_t(r) * t.reclen);
    }
    return steps == t.deleted;
  }

  const Table* Find(const std::string& id) const {
    auto it = by_id_.find(id);
    return it == by_id_.end() ? nullptr : &tables_[it->second];
  }
  const std::vector<Table>& Tables() const { return tables_; }
  const uint8_t* Data() const { return d_; }

 private:
  const uint8_t* d_ = nullptr;
  size_t n_ = 0;
  std::vector<Table> tables_;
  std::map<std::string, size_t> by_id_;
};

// ─── Таблицы ростера ───────────────────────────────────────────────────────────────────────

// Группа rosters схемы nhlng-meta.xml: 39 таблиц сейва. seats — число мест из кода игры (таблица 0x820574E0 в образе:
// при старте 82A07E58 ставит столько мест каждой таблице, где строк не больше), 0 — такого числа нет. maxinsert — схема,
// файл nhlng-meta.xml рядом с базой сильнее (ReadMaxInsert), значения здесь — на случай, если его нет.
struct RosterTable {
  const char* id;
  const char* name;
  int seats;
  int maxinsert;
};

constexpr RosterTable kRosterTables[] = {
    {"caBZ", "exhibitionplayers", 9955, 3000},
    {"ajmx", "exhibitionskaterequipment", 7331, 1500},
    {"yvSd", "exhibitionskaterai", 7331, 1500},
    {"cPbu", "exhibitionplayerbiotable", 7988, 1500},
    {"vuqu", "stockplayerheads", 1684, 50},
    {"FSzD", "stockplayerhelmetplacement", 2713, 600},
    {"QEoV", "exhibitionfreeagents", 1767, 1500},
    {"ulGe", "exhibitionrostertable", 10879, 5000},
    {"vbHh", "stockteamequipmenttable", 6000, 0},
    {"wgjx", "stockteamjerseys", 749, 60},
    {"Jckz", "stockplayervisorexempttable", 1879, 100},
    {"oYeE", "exhibitionteamstrategies", 252, 0},
    {"ttOk", "exhibitionteams", 252, 0},
    {"Iwiq", "favoriteteamschedule", 1431, 200},
    {"OEtS", "exhibitionarena", 192, 5},
    {"lVMf", "exhibitiongoalieequipment", 957, 300},
    {"yuHm", "exhibitiongoalieai", 957, 300},
    {"Vzjq", "customfacetable", 0, 0},
    {"RBQQ", "finnishschedule", 510, 60},
    {"sozv", "stockteamcolorstable", 230, 30},
    {"DlJk", "wcgoalieequipment", 11, 2},
    {"Njxh", "germanschedule", 424, 60},
    {"ihmS", "nhlschedule", 1291, 60},
    {"inlv", "swissschedule", 360, 60},
    {"RzQW", "czechschedule", 424, 60},
    {"byED", "nhlfutureschedule", 1291, 60},
    {"AJKN", "ahlschedule", 1180, 60},
    {"nAUy", "stockgoalieequipment", 876, 300},
    {"LScw", "stockretirednumbertable", 382, 60},
    {"LmeT", "swedishschedule", 424, 60},
    {"kTZD", "whlschedule", 852, 60},
    {"uiEj", "ohlschedule", 740, 60},
    {"ySfc", "qmjhlschedule", 672, 60},
    {"xieT", "stockteamsalaryextras", 30, 0},
    {"vaHq", "exhibitiondraftpick", 1260, 0},
    {"cTuP", "customteamjerseys", 0, 0},
    {"NDEo", "customteamequipmenttable", 0, 0},
    {"Roup", "custompalettetable", 0, 0},
    {"FxFG", "exhibitiondlcnew", 1, 0},
};

// Сколько мест таблица займёт в памяти этой игры: live — живых строк в базе.
inline uint32_t ExpectedSeats(int seats, int maxinsert, uint32_t live) {
  if (seats > 0 && live <= static_cast<uint32_t>(seats)) return static_cast<uint32_t>(seats);
  return live + static_cast<uint32_t>(maxinsert);
}

inline std::wstring Wide(const char* s) {
  std::wstring w;
  while (*s) w.push_back(static_cast<wchar_t>(static_cast<unsigned char>(*s++)));
  return w;
}

inline bool ReadFileAll(const std::wstring& path, size_t max_size, std::vector<uint8_t>& out, bool* too_big = nullptr) {
  HANDLE f = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr,
                         OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
  if (f == INVALID_HANDLE_VALUE) return false;
  LARGE_INTEGER size{};
  if (!GetFileSizeEx(f, &size)) {
    CloseHandle(f);
    return false;
  }
  if (static_cast<unsigned long long>(size.QuadPart) > max_size) {
    if (too_big) *too_big = true;
    CloseHandle(f);
    return false;
  }
  out.resize(static_cast<size_t>(size.QuadPart));
  DWORD got = 0;
  const BOOL ok = out.empty() || ReadFile(f, out.data(), static_cast<DWORD>(out.size()), &got, nullptr);
  CloseHandle(f);
  if (!ok || got != out.size()) return false;
  return true;
}

// maxinsert таблиц из nhlng-meta.xml: игра читает его из cache: и только потом с диска. Нет файла — останутся значения
// kRosterTables.
inline std::map<std::string, int> ReadMaxInsert(const std::wstring& path) {
  std::map<std::string, int> out;
  std::vector<uint8_t> raw;
  if (!ReadFileAll(path, 16 * 1024 * 1024, raw)) return out;
  const std::string text(reinterpret_cast<const char*>(raw.data()), raw.size());
  size_t pos = 0;
  while ((pos = text.find("<table ", pos)) != std::string::npos) {
    const size_t close = text.find('>', pos);
    if (close == std::string::npos) break;
    const std::string tag = text.substr(pos, close - pos);
    pos = close;
    const auto attr = [&tag](const char* name, std::string& value) {
      const std::string key = std::string(" ") + name + "=\"";
      const size_t a = tag.find(key);
      if (a == std::string::npos) return false;
      const size_t b = a + key.size(), e = tag.find('"', b);
      if (e == std::string::npos) return false;
      value = tag.substr(b, e - b);
      return true;
    };
    std::string shortname, maxinsert;
    if (attr("shortname", shortname)) {
      out[shortname] = attr("maxinsert", maxinsert) ? std::atoi(maxinsert.c_str()) : 0;
    }
  }
  return out;
}

// ─── Файл сейва ────────────────────────────────────────────────────────────────────────────

constexpr size_t kMaxFile = 32 * 1024 * 1024;     // ROSTER — 2,5 МБ, остальное в окне выбора случайно
constexpr size_t kMaxInflated = 32 * 1024 * 1024;  // как и база, разжатая
constexpr uint32_t kHeader = 0x2C;                 // заголовок файла и блока до сжатой области

struct SaveKind {
  const char* magic;
  const wchar_t* en;
  const wchar_t* ru;
};

// Подпись файла в первых 16 байтах (82BE6018, 8298EC10): что это за сейв, раз не ростер.
const SaveKind kOtherSaves[] = {
    {"Dynasty", L"a franchise (Be a GM) save", L"сейв франшизы (Be a GM)"},
    {"BeAPros", L"a Be a Pro save", L"сейв «Стань профи»"},
    {"UserProfileFile", L"a user profile", L"профиль пользователя"},
    {"NHLOldUserProfileFile", L"an old user profile", L"старый профиль пользователя"},
    {"DDPUserProfileFile", L"a user profile", L"профиль пользователя"},
    {"OnlineRosterFile", L"an online roster", L"онлайн-ростер"},
    {"HockeyCards", L"a hockey cards save", L"сейв карточек"},
    {"Season", L"a season save", L"сейв сезона"},
    {"Playoff", L"a playoff save", L"сейв плей-офф"},
    {"Tournament", L"a tournament save", L"сейв турнира"},
    {"TXT_BUILD_YOUR_", L"a Build Your AI save", L"сейв «Собери ИИ»"},
};

inline Result Damaged(const std::wstring& en, const std::wstring& ru) {
  return Fail(kDamaged, L"The roster file is damaged (" + en + L"). The game would refuse it.",
              L"Файл ростера повреждён (" + ru + L"). Игра его не примет.");
}

// Проверка файла. file — содержимое, base_dir — папка с nhlng.db (cache\guest\db). ok_info — короткая сводка.
inline Result Check(const std::vector<uint8_t>& file, const std::wstring& base_dir, std::wstring* summary) {
  const std::wstring pick_en = L" Pick the file from a ROSTER folder: ...\\00000001\\ROSTER <date>\\ROSTER <date>.";
  const std::wstring pick_ru = L" Выберите файл из папки ROSTER: ...\\00000001\\ROSTER <дата>\\ROSTER <дата>.";
  if (file.size() < 4) {
    return Fail(kNotASave, L"This is not an NHL Legacy save file." + pick_en,
                L"Это не файл сейва NHL Legacy." + pick_ru);
  }
  if (std::memcmp(file.data(), "CON ", 4) == 0 || std::memcmp(file.data(), "LIVE", 4) == 0 ||
      std::memcmp(file.data(), "PIRS", 4) == 0) {
    return Fail(kNotASave, L"This is an Xbox 360 package, not a save from the port." + pick_en,
                L"Это пакет Xbox 360, а не сейв порта." + pick_ru);
  }
  if (file.size() < kHeader + 8) {
    return Fail(kNotASave, L"This is not an NHL Legacy save file." + pick_en,
                L"Это не файл сейва NHL Legacy." + pick_ru);
  }
  char magic[17] = {};
  std::memcpy(magic, file.data(), 16);
  if (std::strcmp(magic, "RosterFile") != 0) {
    for (const SaveKind& k : kOtherSaves) {
      if (std::strcmp(magic, k.magic) == 0) {
        return Fail(kWrongSaveType, std::wstring(L"This is ") + k.en + L", not a roster." + pick_en,
                    std::wstring(L"Это ") + k.ru + L", а не ростер." + pick_ru);
      }
    }
    return Fail(kNotASave, L"This is not an NHL Legacy save file." + pick_en,
                L"Это не файл сейва NHL Legacy." + pick_ru);
  }

  // Заголовок: версия и один блок базы 1/1, область — до конца файла.
  const uint8_t* d = file.data();
  const uint32_t version = Be32(d + 0x14), chunk = Be32(d + 0x1C), chunk_version = Be32(d + 0x20);
  const uint32_t region = Be32(d + 0x24);
  if (version != 4 || chunk != 1 || chunk_version != 1) {
    return Damaged(L"unknown file version", L"неизвестная версия файла");
  }
  if (uint64_t(kHeader) + region != file.size()) {
    return Damaged(L"the file is cut or longer than it should be", L"файл обрезан или длиннее, чем должен быть");
  }
  if (Be32(d + 0x10) != Crc32Ieee(d + 0x1C, file.size() - 0x1C)) {
    return Damaged(L"file checksum", L"контрольная сумма файла");
  }
  if (Be32(d + 0x28) != Crc32Bzip2(d + kHeader, region)) {
    return Damaged(L"data checksum", L"контрольная сумма данных");
  }

  // Сжатая база: длина потока (little-endian), zlib, дальше нули до конца области.
  const uint32_t stream = Le32(d + kHeader);
  if (stream < 6 || uint64_t(stream) + 4 > region) {
    return Damaged(L"compressed data length", L"длина сжатых данных");
  }
  const uint8_t* z = d + kHeader + 4;
  if ((z[0] & 0x0F) != 8 || ((z[0] << 8) | z[1]) % 31 != 0 || (z[1] & 0x20) != 0) {
    return Damaged(L"compressed data header", L"заголовок сжатых данных");
  }
  for (size_t i = kHeader + 4ull + stream; i < file.size(); ++i) {
    if (d[i] != 0) return Damaged(L"junk after the compressed data", L"мусор после сжатых данных");
  }
  std::vector<uint8_t> db;
  db.reserve(region);
  Inflate inflate(z + 2, stream - 2, db, kMaxInflated);
  if (!inflate.Run() || inflate.Used() + 4 > stream - 2) {
    return Damaged(L"compressed data", L"сжатые данные");
  }
  if (Be32(z + 2 + inflate.Used()) != Adler32(db.data(), db.size())) {
    return Damaged(L"compressed data checksum", L"сумма сжатых данных");
  }

  // Разжатое: база и 4 байта 0xDB. Размер базы — поле 0x08; область равна разжатому.
  if (db.size() != region || db.size() < 0x20) {
    return Damaged(L"database size", L"размер базы");
  }
  const uint32_t db_size = Be32(db.data() + 8);
  if (uint64_t(db_size) + 4 != db.size() || Be32(db.data() + db_size) != 0xDBDBDBDBu) {
    return Damaged(L"end of the database", L"конец базы");
  }
  Tdb save;
  if (!save.Parse(db.data(), db_size, true)) {
    return Damaged(L"database structure", L"устройство базы");
  }
  if (!save.VerifySums()) {
    return Damaged(L"database checksums", L"контрольные суммы базы");
  }
  for (const Table& t : save.Tables()) {
    if (!save.VerifyFreeList(t)) {
      return Damaged(L"list of deleted records", L"список удалённых записей");
    }
  }

  // Сверка с базой этой игры.
  std::vector<uint8_t> base_raw;
  const std::wstring base_path = base_dir + L"\\nhlng.db";
  if (!ReadFileAll(base_path, kMaxFile, base_raw)) {
    return Fail(kNoBase, L"Game database not found, nothing to check the roster against: " + base_path,
                L"Не найдена база игры, не с чем сверить ростер: " + base_path);
  }
  Tdb base;
  if (!base.Parse(base_raw.data(), base_raw.size(), false)) {
    return Fail(kNoBase, L"Could not read the game database " + base_path, L"Не удалось прочитать базу игры " + base_path);
  }
  const std::map<std::string, int> meta = ReadMaxInsert(base_dir + L"\\nhlng-meta.xml");
  if (save.Tables().size() != std::size(kRosterTables)) {
    return Fail(kIncompatible,
                L"This roster has " + std::to_wstring(save.Tables().size()) + L" tables, the game expects " +
                    std::to_wstring(std::size(kRosterTables)) + L". The game would call it damaged.",
                L"В этом ростере таблиц: " + std::to_wstring(save.Tables().size()) + L", игра ждёт " +
                    std::to_wstring(std::size(kRosterTables)) + L". Она назовёт его повреждённым.");
  }
  const std::wstring tail_en = L" The game would call it damaged. Make the roster on a PC with the same game version and data.";
  const std::wstring tail_ru = L" Игра назовёт его повреждённым. Нужен ростер с ПК с той же версией игры и данных.";
  uint64_t want_size = 0x18 + 8ull * std::size(kRosterTables) + 4;  // размер базы, который ждёт игра
  for (const RosterTable& rt : kRosterTables) {
    const Table* s = save.Find(rt.id);
    const Table* b = base.Find(rt.id);
    const std::wstring name = Wide(rt.name);
    if (s == nullptr) {
      return Fail(kIncompatible, L"Table " + name + L" is missing in this roster." + tail_en,
                  L"В ростере нет таблицы " + name + L"." + tail_ru);
    }
    if (b == nullptr) {
      return Fail(kNoBase, L"Table " + name + L" is missing in the game database " + base_path,
                  L"В базе игры нет таблицы " + name + L": " + base_path);
    }
    // Поля записи: раскладка должна быть той же, иначе значения поедут.
    const bool same_fields = s->reclen == b->reclen && s->fields == b->fields &&
                             std::memcmp(save.Data() + s->block + kTableHeader, base.Data() + b->block + kTableHeader,
                                         size_t(kFieldSize) * s->fields) == 0;
    if (!same_fields) {
      return Fail(kIncompatible, L"Table " + name + L" has a different structure in this roster." + tail_en,
                  L"У таблицы " + name + L" в ростере другое устройство." + tail_ru);
    }
    int maxinsert = rt.maxinsert;
    auto mi = meta.find(rt.id);
    if (mi != meta.end()) maxinsert = mi->second;
    const uint32_t want = ExpectedSeats(rt.seats, maxinsert, uint32_t(b->cur) - b->deleted);
    if (s->max != want) {
      return Fail(kIncompatible,
                  L"Table " + name + L" has " + std::to_wstring(s->max) + L" places in this roster, this game has " +
                      std::to_wstring(want) + L"." + tail_en,
                  L"В таблице " + name + L" у ростера мест " + std::to_wstring(s->max) + L", у этой игры " +
                      std::to_wstring(want) + L"." + tail_ru);
    }
    want_size += kTableHeader + uint64_t(kFieldSize) * s->fields + uint64_t(s->reclen) * want;
    if (std::strcmp(rt.id, kIndexedTable) == 0) want_size += kIndexSize;
  }
  if (want_size != db_size) {
    return Fail(kIncompatible,
                L"This roster takes " + std::to_wstring(db_size) + L" bytes, the game expects " +
                    std::to_wstring(want_size) + L"." + tail_en,
                L"Ростер занимает " + std::to_wstring(db_size) + L" байт, игра ждёт " + std::to_wstring(want_size) +
                    L"." + tail_ru);
  }
  if (summary) {
    const Table* teams = save.Find("ulGe");
    *summary = std::to_wstring(file.size()) + L" bytes, " + std::to_wstring(save.Tables().size()) + L" tables, " +
               std::to_wstring(teams ? teams->cur : 0) + L" roster rows";
  }
  return Result{};
}

// ─── Добавление ────────────────────────────────────────────────────────────────────────────

// Сейвы лежат по XUID профиля SDK (он один на всех ПК) и игре 454109EC: тип 00000001 — сохранённые игры.
inline std::wstring SaveRoot(const std::wstring& userdata) { return userdata + L"\\B13EBABEBABEBABE\\454109EC"; }

constexpr uint64_t kXuid = 0xB13EBABEBABEBABEull;
constexpr uint32_t kTitle = 0x454109ECu;
constexpr wchar_t kDisplayName[] = L"ROSTER1";  // слот 1, как пишет игра (82BBA768): других слотов у ростера нет

// Имя в меню: «ROSTER ДД.ММ.ГГГГ», если дата есть в имени файла (так называет файл tools/legacy_data/roster_update.py: дата
// данных, а не время сборки), иначе как у игры. В самом файле места для даты нет, поэтому она живёт в имени и заголовке.
// Год 2000…2099, день и месяц настоящие: цифры подряд из имени папки игры ROSTER 20261024125927 датой не считаются.
inline std::wstring DisplayNameFor(const std::wstring& path) {
  const size_t cut = path.find_last_of(L"\\/");
  const std::wstring file = cut == std::wstring::npos ? path : path.substr(cut + 1);
  const auto digit = [&file](size_t i) { return i < file.size() && file[i] >= L'0' && file[i] <= L'9'; };
  const auto num = [&file](size_t i, size_t n) {
    int v = 0;
    for (size_t k = 0; k < n; ++k) v = v * 10 + (file[i + k] - L'0');
    return v;
  };
  for (size_t i = 0; i + 10 <= file.size(); ++i) {
    if (!(digit(i) && digit(i + 1) && file[i + 2] == L'.' && digit(i + 3) && digit(i + 4) && file[i + 5] == L'.' &&
          digit(i + 6) && digit(i + 7) && digit(i + 8) && digit(i + 9))) {
      continue;
    }
    if ((i > 0 && digit(i - 1)) || digit(i + 10)) continue;
    const int day = num(i, 2), month = num(i + 3, 2), year = num(i + 6, 4);
    if (day < 1 || day > 31 || month < 1 || month > 12 || year < 2000 || year > 2099) continue;
    return L"ROSTER " + file.substr(i, 10);
  }
  return kDisplayName;
}

// Имя папки: как у игры, «ROSTER» и время UTC. Новее всех, что уже есть: выигрывает самый свежий.
inline std::wstring NewName(const std::wstring& dir) {
  SYSTEMTIME now;
  GetSystemTime(&now);
  now.wMilliseconds = 0;  // в имени только секунды: иначе второй ростер в ту же секунду совпал бы с первым
  FILETIME ft;
  SystemTimeToFileTime(&now, &ft);
  ULARGE_INTEGER t;
  t.LowPart = ft.dwLowDateTime;
  t.HighPart = ft.dwHighDateTime;
  WIN32_FIND_DATAW fd;
  HANDLE h = FindFirstFileW((dir + L"\\ROSTER *").c_str(), &fd);
  if (h != INVALID_HANDLE_VALUE) {
    do {
      SYSTEMTIME st{};
      int y = 0, mo = 0, da = 0, ho = 0, mi = 0, se = 0;
      if (swscanf_s(fd.cFileName, L"ROSTER %4d%2d%2d%2d%2d%2d", &y, &mo, &da, &ho, &mi, &se) != 6) continue;
      st.wYear = static_cast<WORD>(y);
      st.wMonth = static_cast<WORD>(mo);
      st.wDay = static_cast<WORD>(da);
      st.wHour = static_cast<WORD>(ho);
      st.wMinute = static_cast<WORD>(mi);
      st.wSecond = static_cast<WORD>(se);
      FILETIME other;
      if (!SystemTimeToFileTime(&st, &other)) continue;
      ULARGE_INTEGER o;
      o.LowPart = other.dwLowDateTime;
      o.HighPart = other.dwHighDateTime;
      if (o.QuadPart >= t.QuadPart) t.QuadPart = o.QuadPart + 10000000ull;  // на секунду новее
    } while (FindNextFileW(h, &fd));
    FindClose(h);
  }
  ft.dwLowDateTime = t.LowPart;
  ft.dwHighDateTime = t.HighPart;
  FileTimeToSystemTime(&ft, &now);
  wchar_t name[40];
  std::swprintf(name, 40, L"ROSTER %04u%02u%02u%02u%02u%02u", now.wYear, now.wMonth, now.wDay, now.wHour, now.wMinute,
                now.wSecond);
  return name;
}

// Заголовок XCONTENT_AGGREGATE_DATA (0x148 байт): устройство, тип, имя в меню UTF-16 BE, имя папки, XUID, игра.
inline std::vector<uint8_t> MakeHeader(const std::wstring& folder, const std::wstring& display) {
  std::vector<uint8_t> h(0x148, 0);
  const auto put32 = [&h](size_t at, uint32_t v) {
    h[at] = static_cast<uint8_t>(v >> 24);
    h[at + 1] = static_cast<uint8_t>(v >> 16);
    h[at + 2] = static_cast<uint8_t>(v >> 8);
    h[at + 3] = static_cast<uint8_t>(v);
  };
  put32(0, 1);
  put32(4, 1);
  size_t at = 8;
  for (const wchar_t c : display) {
    h[at] = static_cast<uint8_t>(c >> 8);
    h[at + 1] = static_cast<uint8_t>(c);
    at += 2;
  }
  at = 0x108;
  for (wchar_t c : folder) h[at++] = static_cast<uint8_t>(c);
  put32(0x138, static_cast<uint32_t>(kXuid >> 32));
  put32(0x13C, static_cast<uint32_t>(kXuid));
  put32(0x140, kTitle);
  return h;
}

inline bool MakeDirs(const std::wstring& path) {
  if (CreateDirectoryW(path.c_str(), nullptr) || GetLastError() == ERROR_ALREADY_EXISTS) return true;
  const size_t cut = path.find_last_of(L"\\/");
  if (cut == std::wstring::npos || cut < 3) return false;
  if (!MakeDirs(path.substr(0, cut))) return false;
  return CreateDirectoryW(path.c_str(), nullptr) || GetLastError() == ERROR_ALREADY_EXISTS;
}

inline bool WriteAll(const std::wstring& path, const std::vector<uint8_t>& data) {
  HANDLE f = CreateFileW(path.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
  if (f == INVALID_HANDLE_VALUE) return false;
  DWORD put = 0;
  const BOOL ok = WriteFile(f, data.data(), static_cast<DWORD>(data.size()), &put, nullptr);
  const BOOL flushed = FlushFileBuffers(f);
  CloseHandle(f);
  return ok && flushed && put == data.size();
}

// Удалить папку и файлы в ней (подпапок там не бывает).
inline void ClearDir(const std::wstring& dir) {
  WIN32_FIND_DATAW fd;
  HANDLE h = FindFirstFileW((dir + L"\\*").c_str(), &fd);
  if (h != INVALID_HANDLE_VALUE) {
    do {
      if (!(fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)) DeleteFileW((dir + L"\\" + fd.cFileName).c_str());
    } while (FindNextFileW(h, &fd));
    FindClose(h);
  }
  RemoveDirectoryW(dir.c_str());
}

// Добавить проверенный файл. Порядок такой, что при сбое в любом месте игра прежних ростеров не потеряет и не увидит
// половины нового: файл и заголовок во временных именах, потом заголовок, последним — папка (SDK перечисляет папки).
// Временная папка лежит рядом с типом 00000001, а не в нём, иначе брошенную после сбоя игра показала бы как сейв.
inline Result AddRoster(const std::vector<uint8_t>& file, const std::wstring& userdata, const std::wstring& display,
                        std::wstring* name_out) {
  const std::wstring root = SaveRoot(userdata);
  const std::wstring saves = root + L"\\00000001", headers = root + L"\\Headers\\00000001";
  const auto failed = [&saves]() {
    const std::wstring code = std::to_wstring(GetLastError());
    return Fail(kWriteFailed, L"Could not write to " + saves + L" (error " + code + L"). Nothing was changed.",
                L"Не удалось записать в " + saves + L" (ошибка " + code + L"). Ничего не изменено.");
  };
  if (!MakeDirs(saves) || !MakeDirs(headers)) return failed();
  const std::wstring name = NewName(saves);
  const std::wstring tmp = root + L"\\import.tmp";
  const std::wstring tmp_file = tmp + L"\\" + name, final_dir = saves + L"\\" + name;
  const std::wstring header = headers + L"\\" + name + L".header", tmp_header = header + L".tmp";
  ClearDir(tmp);  // остаток прошлого сбоя
  if (!CreateDirectoryW(tmp.c_str(), nullptr)) return failed();
  const auto cleanup = [&]() {
    ClearDir(tmp);
    DeleteFileW(tmp_header.c_str());
  };
  std::vector<uint8_t> copy;
  if (!WriteAll(tmp_file, file) || !WriteAll(tmp_header, MakeHeader(name, display)) ||
      !ReadFileAll(tmp_file, kMaxFile, copy) || copy != file) {
    Result r = failed();
    cleanup();
    return r;
  }
  if (!MoveFileExW(tmp_header.c_str(), header.c_str(), MOVEFILE_WRITE_THROUGH)) {
    Result r = failed();
    cleanup();
    return r;
  }
  if (!MoveFileExW(tmp.c_str(), final_dir.c_str(), MOVEFILE_WRITE_THROUGH)) {
    Result r = failed();
    DeleteFileW(header.c_str());
    cleanup();
    return r;
  }
  if (name_out) *name_out = name;
  return Result{};
}

}  // namespace roster
