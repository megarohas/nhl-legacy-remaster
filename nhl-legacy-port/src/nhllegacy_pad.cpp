// Виртуальный геймпад из файла — для проверок агентами без фокуса окна (docs/legacy-port.md, «Проверки в игре без фокуса»; перенос из nhl-13-port/src/nhl13_pad.cpp, bfcd833).
// Только при cvar nhl_virtual_pad = true (по умолчанию выключен: у пользователя файл, оставшийся от
// прежних проверок, ничего не нажмёт). Ввод SendInput/keybd_event идёт в переднее окно — при двух играх
// на одном рабочем столе (NHL 13 и Legacy у разных агентов) нажатия уходили в чужую игру; здесь —
// только своему процессу. Рядом с exe файл nhllegacy_pad.txt, строки «номер кнопки удержание_мс пауза_мс», например
// «17 A 150 450» или «18 DOWN+RT 150 450». Порт читает новые строки (номер больше прежнего) и
// по очереди «жмёт» их пользователю 0: XamInputGetState — биты кнопок и курки, XamInputGetKeystrokeEx —
// события KEYDOWN/KEYUP (VK_PAD_*). Кнопки: A B X Y LB RB LT RT START BACK UP DOWN LEFT RIGHT LS RS, стики до упора
// LSL LSR LSU LSD (левый) и RSL RSR RSU RSD (правый).
// Журнал — nhllegacy_pad.log рядом с exe.
#if defined(_WIN32)
#include <windows.h>

#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <deque>
#include <mutex>
#include <sstream>
#include <string>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ppc.h>

REXCVAR_DEFINE_BOOL(nhl_virtual_pad, false, "NHLLegacy",
                    "Test input: press buttons for user 0 from nhllegacy_pad.txt next to the exe (no window focus "
                    "needed); off by default")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

namespace {

bool PadOn() {
  static const bool on = [] {
    const bool v = REXCVAR_GET(nhl_virtual_pad);
    if (v) {
      REXLOG_WARN("[nhllegacy] virtual pad: on (nhllegacy_pad.txt next to the exe)");
    }
    return v;
  }();
  return on;
}

struct Cmd {
  long seq;
  uint16_t buttons;
  bool lt, rt;
  int16_t lx, ly, rx, ry;  // стики: LSL/LSR/LSU/LSD, RSL/RSR/RSU/RSD (до упора)
  int hold_ms, gap_ms;
  std::string text;
};

struct Key {
  uint16_t vk;
  uint16_t flags;  // 1 down, 2 up
};

std::mutex g_mu;
std::deque<Cmd> g_queue;
std::deque<Key> g_keys;
long g_last_seq = 0;
long long g_file_pos = 0;
std::chrono::steady_clock::time_point g_last_poll{};
std::chrono::steady_clock::time_point g_cmd_start{};
bool g_cmd_active = false, g_cmd_down = false;
uint16_t g_buttons = 0;
bool g_lt = false, g_rt = false;
int16_t g_lx = 0, g_ly = 0, g_rx = 0, g_ry = 0;
uint32_t g_packet = 0;
std::wstring g_dir;

std::wstring Dir() {
  if (g_dir.empty()) {
    wchar_t exe[MAX_PATH];
    GetModuleFileNameW(nullptr, exe, MAX_PATH);
    g_dir = exe;
    g_dir = g_dir.substr(0, g_dir.find_last_of(L"\\/") + 1);
  }
  return g_dir;
}

void Log(const std::string& s) {
  if (FILE* f = _wfopen((Dir() + L"nhllegacy_pad.log").c_str(), L"a")) {
    SYSTEMTIME t;
    GetLocalTime(&t);
    fprintf(f, "%02d:%02d:%02d.%03d %s\n", t.wHour, t.wMinute, t.wSecond, t.wMilliseconds, s.c_str());
    fclose(f);
  }
}

bool Parse(const std::string& name, uint16_t& b, bool& lt, bool& rt, int16_t* sticks) {
  static const struct {
    const char* n;
    uint16_t m;
  } kMap[] = {{"UP", 0x0001},   {"DOWN", 0x0002}, {"LEFT", 0x0004}, {"RIGHT", 0x0008}, {"START", 0x0010},
              {"BACK", 0x0020}, {"LS", 0x0040},   {"RS", 0x0080},   {"LB", 0x0100},    {"RB", 0x0200},
              {"A", 0x1000},    {"B", 0x2000},    {"X", 0x4000},    {"Y", 0x8000}};
  std::stringstream ss(name);
  std::string part;
  while (std::getline(ss, part, '+')) {
    if (part == "LT") {
      lt = true;
      continue;
    }
    if (part == "RT") {
      rt = true;
      continue;
    }
    // стики до упора: sticks = {lx, ly, rx, ry}; вверх — +32767, как в XInput
    if (part == "LSL") { sticks[0] = -32767; continue; }
    if (part == "LSR") { sticks[0] = 32767; continue; }
    if (part == "LSU") { sticks[1] = 32767; continue; }
    if (part == "LSD") { sticks[1] = -32767; continue; }
    if (part == "RSL") { sticks[2] = -32767; continue; }
    if (part == "RSR") { sticks[2] = 32767; continue; }
    if (part == "RSU") { sticks[3] = 32767; continue; }
    if (part == "RSD") { sticks[3] = -32767; continue; }
    bool found = false;
    for (const auto& e : kMap) {
      if (part == e.n) {
        b |= e.m;
        found = true;
      }
    }
    if (!found) {
      return false;
    }
  }
  return true;
}

void Poll() {
  const auto now = std::chrono::steady_clock::now();
  if (now - g_last_poll < std::chrono::milliseconds(60)) {
    return;
  }
  g_last_poll = now;
  const std::wstring path = Dir() + L"nhllegacy_pad.txt";
  HANDLE h = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr,
                         OPEN_EXISTING, 0, nullptr);
  if (h == INVALID_HANDLE_VALUE) {
    return;
  }
  LARGE_INTEGER size{};
  GetFileSizeEx(h, &size);
  if (size.QuadPart < g_file_pos) {
    g_file_pos = 0;  // файл начат заново
  }
  if (size.QuadPart > g_file_pos) {
    std::string data(static_cast<size_t>(size.QuadPart - g_file_pos), '\0');
    LARGE_INTEGER pos;
    pos.QuadPart = g_file_pos;
    SetFilePointerEx(h, pos, nullptr, FILE_BEGIN);
    DWORD got = 0;
    ReadFile(h, data.data(), static_cast<DWORD>(data.size()), &got, nullptr);
    data.resize(got);
    const size_t last_nl = data.rfind('\n');
    if (last_nl != std::string::npos) {
      g_file_pos += static_cast<long long>(last_nl + 1);
      std::stringstream lines(data.substr(0, last_nl + 1));
      std::string line;
      while (std::getline(lines, line)) {
        std::stringstream ls(line);
        Cmd c{};
        std::string name;
        if (!(ls >> c.seq >> name >> c.hold_ms >> c.gap_ms) || c.seq <= g_last_seq) {
          continue;
        }
        int16_t sticks[4] = {0, 0, 0, 0};
        if (!Parse(name, c.buttons, c.lt, c.rt, sticks)) {
          Log("bad button " + name);
          continue;
        }
        g_last_seq = c.seq;
        c.lx = sticks[0];
        c.ly = sticks[1];
        c.rx = sticks[2];
        c.ry = sticks[3];
        c.text = name;
        g_queue.push_back(c);
      }
    }
  }
  CloseHandle(h);
}

void PushKeys(uint16_t buttons, bool lt, bool rt, uint16_t flags, int16_t lx = 0, int16_t ly = 0, int16_t rx = 0,
              int16_t ry = 0) {
  static const struct {
    uint16_t m, vk;
  } kVk[] = {{0x1000, 0x5800}, {0x2000, 0x5801}, {0x4000, 0x5802}, {0x8000, 0x5803}, {0x0200, 0x5804},
             {0x0100, 0x5805}, {0x0001, 0x5810}, {0x0002, 0x5811}, {0x0004, 0x5812}, {0x0008, 0x5813},
             {0x0010, 0x5814}, {0x0020, 0x5815}, {0x0040, 0x5816}, {0x0080, 0x5817}};
  for (const auto& e : kVk) {
    if (buttons & e.m) {
      g_keys.push_back({e.vk, flags});
    }
  }
  if (lt) {
    g_keys.push_back({0x5806, flags});
  }
  if (rt) {
    g_keys.push_back({0x5807, flags});
  }
  // VK_PAD_LTHUMB_UP/DOWN/RIGHT/LEFT 0x5820…0x5823, VK_PAD_RTHUMB_* 0x5830…0x5833
  if (ly > 0) g_keys.push_back({0x5820, flags});
  if (ly < 0) g_keys.push_back({0x5821, flags});
  if (lx > 0) g_keys.push_back({0x5822, flags});
  if (lx < 0) g_keys.push_back({0x5823, flags});
  if (ry > 0) g_keys.push_back({0x5830, flags});
  if (ry < 0) g_keys.push_back({0x5831, flags});
  if (rx > 0) g_keys.push_back({0x5832, flags});
  if (rx < 0) g_keys.push_back({0x5833, flags});
}

void Step() {
  Poll();
  const auto now = std::chrono::steady_clock::now();
  for (int guard = 0; guard < 4; ++guard) {
    if (!g_cmd_active) {
      if (g_queue.empty()) {
        return;
      }
      g_cmd_active = true;
      g_cmd_down = true;
      g_cmd_start = now;
      const Cmd& c = g_queue.front();
      g_buttons = c.buttons;
      g_lt = c.lt;
      g_rt = c.rt;
      g_lx = c.lx;
      g_ly = c.ly;
      g_rx = c.rx;
      g_ry = c.ry;
      ++g_packet;
      PushKeys(c.buttons, c.lt, c.rt, 1, c.lx, c.ly, c.rx, c.ry);
      Log("down " + std::to_string(c.seq) + " " + c.text);
      return;
    }
    const Cmd& c = g_queue.front();
    const auto t = now - g_cmd_start;
    if (g_cmd_down && t >= std::chrono::milliseconds(c.hold_ms)) {
      g_cmd_down = false;
      PushKeys(c.buttons, c.lt, c.rt, 2, c.lx, c.ly, c.rx, c.ry);
      g_buttons = 0;
      g_lt = g_rt = false;
      g_lx = g_ly = g_rx = g_ry = 0;
      ++g_packet;
      Log("up   " + std::to_string(c.seq) + " " + c.text);
    }
    if (!g_cmd_down && t >= std::chrono::milliseconds(c.hold_ms + c.gap_ms)) {
      g_queue.pop_front();
      g_cmd_active = false;
      continue;
    }
    return;
  }
}

uint8_t* H(uint8_t* base, uint32_t a) {
  return base + a + (a >= 0xE0000000u ? 0x1000u : 0u);
}
uint32_t Load32(uint8_t* base, uint32_t a) {
  uint32_t v;
  std::memcpy(&v, H(base, a), 4);
  return __builtin_bswap32(v);
}
void Store32(uint8_t* base, uint32_t a, uint32_t v) {
  v = __builtin_bswap32(v);
  std::memcpy(H(base, a), &v, 4);
}
void Store16(uint8_t* base, uint32_t a, uint16_t v) {
  v = __builtin_bswap16(v);
  std::memcpy(H(base, a), &v, 2);
}
uint16_t Load16(uint8_t* base, uint32_t a) {
  uint16_t v;
  std::memcpy(&v, H(base, a), 2);
  return __builtin_bswap16(v);
}

}  // namespace

// После XamInputGetState(user r3, flags r4, X_INPUT_STATE* r5): пользователю 0 — нажатые кнопки.
void NhlLegacyPadAfterGetState(PPCContext& ctx, uint8_t* base, uint32_t user, uint32_t state) {
  if (!PadOn() || user != 0 || !state) {
    return;
  }
  std::lock_guard<std::mutex> lock(g_mu);
  Step();
  if (!g_cmd_active && g_queue.empty() && g_packet == 0) {
    return;
  }
  if (ctx.r3.u32 != 0) {  // не подключён — подставить пустое состояние
    std::memset(H(base, state), 0, 16);
    ctx.r3.u64 = 0;
  }
  Store32(base, state, Load32(base, state) + g_packet * 1024);
  Store16(base, state + 4, Load16(base, state + 4) | g_buttons);
  if (g_lt) {
    *H(base, state + 6) = 255;
  }
  if (g_rt) {
    *H(base, state + 7) = 255;
  }
  if (g_lx || g_ly || g_rx || g_ry) {  // X_INPUT_STATE +8 sThumbLX, +10 LY, +12 RX, +14 RY (BE)
    if (g_lx) Store16(base, state + 8, static_cast<uint16_t>(g_lx));
    if (g_ly) Store16(base, state + 10, static_cast<uint16_t>(g_ly));
    if (g_rx) Store16(base, state + 12, static_cast<uint16_t>(g_rx));
    if (g_ry) Store16(base, state + 14, static_cast<uint16_t>(g_ry));
  }
}

// Перед XamInputGetKeystrokeEx(DWORD* user r3, flags r4, X_INPUT_KEYSTROKE* r5): своё событие, если есть.
bool NhlLegacyPadKeystroke(PPCContext& ctx, uint8_t* base) {
  if (!PadOn()) {
    return false;
  }
  const uint32_t puser = ctx.r3.u32;
  const uint32_t ks = ctx.r5.u32;
  if (!puser || !ks) {
    return false;
  }
  const uint32_t user = Load32(base, puser);
  if (user != 0 && user != 255) {
    return false;
  }
  std::lock_guard<std::mutex> lock(g_mu);
  Step();
  if (g_keys.empty()) {
    return false;
  }
  const Key k = g_keys.front();
  g_keys.pop_front();
  Store16(base, ks + 0, k.vk);
  Store16(base, ks + 2, 0);
  Store16(base, ks + 4, k.flags);
  *H(base, ks + 6) = 0;
  *H(base, ks + 7) = 0;
  Store32(base, puser, 0);
  ctx.r3.u64 = 0;
  return true;
}
#endif
