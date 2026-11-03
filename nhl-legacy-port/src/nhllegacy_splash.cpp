// Заставка первой загрузки (nhl_splash; docs/legacy-port.md, «Заставка загрузки»).
//
// От открытия окна до первого настоящего кадра игры окно чёрное: SDK собирает хранилище шейдеров (с тёплым кэшем драйвера
// секунды, с холодным — дольше), игра запускается и выводит первые кадры чёрными. Всё это время поверх окна стоит заставка:
// каток сверху, шайба кружит по центральному кругу со шлейфом, подпись «Loading». Графика своя, рисуется кодом при старте:
// ни картинок, ни логотипов EA и НХЛ (репозиторий публичный).
//
// Признак первого кадра — первая нечёрная картинка в окне игры. После первого VdSwap игра 0,4–0,9 с выводит чёрные кадры,
// потом свою загрузочную картинку (облака и логотип игры, из архива, открытого ещё до первого кадра: файла-признака нет),
// затем выбор языка и юридический экран. Поэтому после первого VdSwap отдельный поток раз в kProbeMs снимает окно игры
// (PrintWindow, как gameshot.ps1: заставка — другое окно, на снимке её нет): хоть одна точка ярче kPictureLuma — картинка
// есть, заставка за kFadeOut гаснет поверх неё. До первого VdSwap не снимаем: поток UI занят сборкой хранилища шейдеров, а
// PrintWindow ждал бы его.
// Паузы загрузки до главного меню: если после картинки окно игры снова чёрное дольше kBlackShow, заставка возвращается и
// гаснет на следующей картинке. Главное меню (игра открыла kMainMenu) — заставка больше не нужна, снимки и перехваты
// кончаются. Предел — kBootLimit после открытия окна.
// Запасные признаки первой картинки: игра открыла выбор языка, юридический экран, «press start» или ролик (импорт
// NtCreateFile / NtOpenFile) и после этого вывела kSwapsAfterScreen кадров; kFallbackAfterSwap после первого VdSwap. Окно
// SDK (сообщение, F4, консоль) рисуется в окне игры: пока оно открыто, заставки нет.
// Импорты перехватываются, как в nhllegacy_input_lock.cpp: определение __imp__* в exe сильнее библиотеки импорта, оригинал —
// из DLL рантайма. После заставки перехват только передаёт вызов дальше.
//
// Окно — своё, как у надписи о шейдерах (nhllegacy_shaderstatus.cpp, оттуда и зовётся): слоистое, прозрачное для мыши и
// фокуса, сразу над окном игры в Z-порядке, надпись — над ним. Перерисовывается только кусок с шайбой и точками
// (UpdateLayeredWindowIndirect с прямоугольником), фон с катком строится один раз на размер окна. Когда заставка ушла, окна
// нет: вывод кадров игры как без неё.
//
// Превью без игры: scripts/splash_preview.cmd собирает этот же файл с NHLLEGACY_SPLASH_PREVIEW и пишет кадры в BMP.

#include "nhllegacy_splash.h"

#if defined(_WIN32)

#include <algorithm>
#include <atomic>
#include <cctype>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <string_view>
#include <thread>

#if !defined(NHLLEGACY_SPLASH_PREVIEW)
#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ppc.h>

REXCVAR_DEFINE_BOOL(nhl_splash, true, "NHLLegacy",
                    "Show an animated loading splash over the black window until the game draws its first screen");

bool NhlLegacySdkDialogOpen();  // nhllegacy_cursor.cpp
#endif

namespace {

using Clock = std::chrono::steady_clock;

int64_t NowMs() {
  return std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now().time_since_epoch()).count();
}

// ─── Признак первого кадра ─────────────────────────────────────────────────────────────────────────────────────────

// Запасной признак — экраны с картинкой. Порядок при старте (журнал и снимки 03.11.2026): загрузочная картинка игры (файла
// нет), empty, blackbg, blank, languageselect (ждёт кнопку или ~30 с), 01_legal, ролик EA, 03_pressstart.
constexpr std::string_view kFirstScreens[] = {"\\bootflow\\languageselect", "\\bootflow\\01_legal",
                                              "\\bootflow\\03_pressstart", "\\movies\\"};
// Главное меню: игра просит магазин (журнал старта) — загрузка кончилась, заставка больше не нужна.
constexpr std::string_view kMainMenu = "\\dime\\nhlstorecfg";
constexpr uint32_t kSwapsAfterScreen = 30;     // ~1 с: при старте игра выводит ~30 кадров/с
constexpr int kProbeMs = 200;                  // шаг снимка окна игры
constexpr int kPictureLuma = 40;               // яркость точки 0–255: чёрные кадры игры — 0, её картинка — 90–255
// Заставка снова — только на долгой чёрной паузе загрузки. Переходы между экранами при старте чёрные 0,2–1,0 с (снимки
// 03.11.2026); при пороге 1 с заставка мигнула на 0,07 с после START. Поэтому порог 3 с, а показанная заставка держится
// не меньше kMinShow: короткой вспышки не бывает.
constexpr int64_t kBlackShow = 3000;           // мс чёрного окна после картинки
constexpr int64_t kMinShow = 800;              // мс: столько заставка стоит после появления (сверх kFadeIn)
constexpr int64_t kFallbackAfterSwap = 40000;  // мс после первого VdSwap без картинки (обычно картинка — через 1 с)
constexpr int64_t kBootLimit = 600000;         // мс после открытия окна: дальше заставки нет, даже без главного меню
constexpr int64_t kFadeIn = 250;               // мс
constexpr int64_t kFadeOut = 300;              // мс
constexpr int kLogScreens = 12;                // сколько первых экранов и роликов записать в журнал (для сверки)

std::atomic<int64_t> g_window_ms{0};
std::atomic<uint32_t> g_swaps{0};
std::atomic<int64_t> g_first_swap_ms{0};
std::atomic<uint32_t> g_screen_swap{0};  // номер VdSwap + 1 на открытии первого экрана с картинкой, 0 — ещё нет
std::atomic<bool> g_screen_ready{false};  // запасной признак: после такого экрана прошло kSwapsAfterScreen кадров
std::atomic<int64_t> g_menu_ms{0};        // игра открыла главное меню
std::atomic<bool> g_seen_picture{false};  // снимок хоть раз показал картинку игры
std::atomic<int64_t> g_black_since{0};    // с какого снимка окно игры чёрное, 0 — на последнем снимке картинка
std::atomic<bool> g_done{false};          // заставки больше нет, перехваты только передают вызов
std::atomic<int> g_logged_screens{0};
std::atomic<HWND> g_game{nullptr};        // окно игры для снимка
std::atomic<bool> g_probe_stop{false};

#if !defined(NHLLEGACY_SPLASH_PREVIEW)

double SinceWindow(int64_t ms) {
  const int64_t w = g_window_ms.load();
  return w ? double(ms - w) / 1000.0 : 0.0;
}

void OnSwap() {
  const uint32_t n = g_swaps.fetch_add(1) + 1;
  if (n == 1) {
    g_first_swap_ms.store(NowMs());
    REXLOG_INFO("[nhllegacy] splash: first VdSwap {:.2f} s after the window opened", SinceWindow(NowMs()));
  }
  const uint32_t at = g_screen_swap.load(std::memory_order_relaxed);
  if (at && n >= at - 1 + kSwapsAfterScreen && !g_screen_ready.load(std::memory_order_relaxed)) {
    g_screen_ready.store(true);
  }
}

uint8_t* Guest(uint8_t* base, uint32_t a) {
  return base + a + (a >= 0xE0000000u ? 0x1000u : 0u);
}

uint32_t Be32(const uint8_t* p) {
  return (uint32_t(p[0]) << 24) | (uint32_t(p[1]) << 16) | (uint32_t(p[2]) << 8) | uint32_t(p[3]);
}

bool ContainsNoCase(std::string_view hay, std::string_view needle) {
  if (needle.size() > hay.size()) {
    return false;
  }
  for (size_t i = 0; i + needle.size() <= hay.size(); ++i) {
    size_t j = 0;
    while (j < needle.size() && std::tolower(static_cast<unsigned char>(hay[i + j])) ==
                                    std::tolower(static_cast<unsigned char>(needle[j]))) {
      ++j;
    }
    if (j == needle.size()) {
      return true;
    }
  }
  return false;
}

// NtCreateFile / NtOpenFile: r5 — X_OBJECT_ATTRIBUTES {root, name_ptr → X_ANSI_STRING {u16 len, u16 max, u32 ptr}}.
void OnOpen(PPCContext& ctx, uint8_t* base) {
  const bool marked = g_screen_swap.load(std::memory_order_relaxed) != 0;
  if (ctx.r5.u32 == 0) {
    return;
  }
  const uint32_t name = Be32(Guest(base, ctx.r5.u32) + 4);
  if (name == 0) {
    return;
  }
  const uint8_t* ansi = Guest(base, name);
  const uint32_t len = (uint32_t(ansi[0]) << 8) | ansi[1];
  const uint32_t ptr = Be32(ansi + 4);
  if (ptr == 0 || len == 0 || len > 512) {
    return;
  }
  const std::string_view path(reinterpret_cast<const char*>(Guest(base, ptr)), len);
  const bool screen = ContainsNoCase(path, "\\screens\\") || ContainsNoCase(path, "\\movies\\");
  if (screen && g_logged_screens.fetch_add(1) < kLogScreens) {
    REXLOG_INFO("[nhllegacy] splash: open {} at {:.2f} s, {} swaps", path, SinceWindow(NowMs()), g_swaps.load());
  }
  if (!g_menu_ms.load(std::memory_order_relaxed) && ContainsNoCase(path, kMainMenu)) {
    g_menu_ms.store(NowMs());
    REXLOG_INFO("[nhllegacy] splash: main menu at {:.2f} s", SinceWindow(NowMs()));
  }
  for (std::string_view s : kFirstScreens) {
    if (!marked && ContainsNoCase(path, s)) {
      uint32_t expected = 0;
      g_screen_swap.compare_exchange_strong(expected, g_swaps.load() + 1);
      return;
    }
  }
}

// Снимок окна игры (PrintWindow): 1 — картинка (хоть одна точка ярче kPictureLuma; смотрим каждую вторую точку каждой второй
// строки, чтобы не пропустить мелкий текст на тёмном), 0 — чёрное, −1 — снимка нет.
int GamePicture(HWND game, int* brightest) {
  RECT c{};
  if (!GetClientRect(game, &c) || c.right < 16 || c.bottom < 16) {
    return -1;
  }
  HDC dc = CreateCompatibleDC(nullptr);
  BITMAPINFO info{};
  info.bmiHeader.biSize = sizeof(info.bmiHeader);
  info.bmiHeader.biWidth = c.right;
  info.bmiHeader.biHeight = -c.bottom;
  info.bmiHeader.biPlanes = 1;
  info.bmiHeader.biBitCount = 32;
  info.bmiHeader.biCompression = BI_RGB;
  void* bits = nullptr;
  HBITMAP bmp = CreateDIBSection(dc, &info, DIB_RGB_COLORS, &bits, nullptr, 0);
  if (!bmp) {
    DeleteDC(dc);
    return -1;
  }
  HGDIOBJ old = SelectObject(dc, bmp);
  std::memset(bits, 0, size_t(c.right) * size_t(c.bottom) * 4);
  constexpr UINT kClientOnly = 0x1, kRenderFullContent = 0x2;  // PW_CLIENTONLY | PW_RENDERFULLCONTENT
  const bool ok = PrintWindow(game, dc, kClientOnly | kRenderFullContent) != FALSE;
  GdiFlush();
  int best = 0;
  if (ok) {
    const uint32_t* px = static_cast<const uint32_t*>(bits);
    for (int y = 0; y < c.bottom && best < kPictureLuma; y += 2) {
      const uint32_t* row = px + size_t(y) * size_t(c.right);
      for (int x = 0; x < c.right; x += 2) {
        const uint32_t p = row[x];
        const int luma = (int((p >> 16) & 0xFF) * 77 + int((p >> 8) & 0xFF) * 150 + int(p & 0xFF) * 29) >> 8;
        best = std::max(best, luma);
      }
    }
  }
  SelectObject(dc, old);
  DeleteObject(bmp);
  DeleteDC(dc);
  *brightest = best;
  return !ok ? -1 : best >= kPictureLuma ? 1 : 0;
}

// Снимки окна игры от первого VdSwap до конца заставки: есть ли картинка и с какого момента окно чёрное.
void ProbeLoop() {
  bool was_picture = false;
  while (!g_probe_stop.load()) {
    HWND game = g_game.load();
    if (game && IsWindow(game) && !IsIconic(game)) {
      int brightest = 0;
      const int shot = GamePicture(game, &brightest);
      const int64_t now = NowMs();
      if (shot == 1) {
        if (!g_seen_picture.exchange(true)) {
          REXLOG_INFO("[nhllegacy] splash: first game picture {:.2f} s after the window opened ({:.2f} s after the first "
                      "VdSwap, brightest {})",
                      SinceWindow(now), double(now - g_first_swap_ms.load()) / 1000.0, brightest);
        }
        g_black_since.store(0);
        was_picture = true;
      } else if (shot == 0) {
        int64_t expected = 0;
        if (g_black_since.compare_exchange_strong(expected, now) && was_picture) {
          REXLOG_INFO("[nhllegacy] splash: game window black at {:.2f} s", SinceWindow(now));
        }
        was_picture = false;
      }
    }
    Sleep(kProbeMs);
  }
}

using GuestFn = void (*)(PPCContext&, uint8_t*);

GuestFn RuntimeExport(const char* name) {
  HMODULE runtime = nullptr;
  for (const char* dll : {"rexruntimerd.dll", "rexruntime.dll", "rexruntimed.dll"}) {
    if ((runtime = GetModuleHandleA(dll)) != nullptr) {
      break;
    }
  }
  auto fn = runtime ? reinterpret_cast<GuestFn>(GetProcAddress(runtime, name)) : nullptr;
  if (!fn) {
    REXLOG_ERROR("[nhllegacy] splash: {} not found in rexruntime (module {})", name, static_cast<void*>(runtime));
  }
  return fn;
}

#endif  // !NHLLEGACY_SPLASH_PREVIEW

// ─── Картинка ──────────────────────────────────────────────────────────────────────────────────────────────────────

// Каток НХЛ в футах: 200 × 85, углы R 28, синие линии в 25 от центра, линии ворот в 11 от бортов, круги вбрасывания R 15
// (центр зон — 20 от линии ворот, ±22 по ширине), точки средней зоны — 5 от синих линий. Цвета — свои, тёмная тема.
constexpr float kRinkW = 200.0f, kRinkH = 85.0f, kCorner = 28.0f;
constexpr float kBlueX = 25.0f, kGoalX = 89.0f, kZoneX = 69.0f, kNeutralX = 20.0f, kDotY = 22.0f, kCircleR = 15.0f;
constexpr double kTurn = 1.4;  // оборот шайбы, с
constexpr float kTrail = 0.72f;  // длина шлейфа, доля оборота

struct Rgb {
  float r, g, b;
};
constexpr Rgb kTop{11, 20, 34}, kBottom{4, 8, 14}, kGlow{20, 44, 74};
constexpr Rgb kIce{24, 44, 68}, kBoard{226, 234, 244}, kRed{214, 52, 64}, kBlue{64, 124, 232};
constexpr Rgb kCrease{86, 150, 228}, kTrailRgb{214, 234, 255}, kPuck{16, 16, 20}, kPuckRim{176, 190, 206};
constexpr Rgb kTitle{236, 241, 248}, kSub{150, 168, 192};

float Clamp01(float v) {
  return std::clamp(v, 0.0f, 1.0f);
}

void Over(float* px, const Rgb& c, float a) {
  if (a <= 0.0f) {
    return;
  }
  px[0] += (c.r - px[0]) * a;
  px[1] += (c.g - px[1]) * a;
  px[2] += (c.b - px[2]) * a;
}

void OverPixel(uint32_t& px, const Rgb& c, float a) {
  if (a <= 0.0f) {
    return;
  }
  const auto mix = [a](uint32_t d, float s) { return uint32_t(float(d) + (s - float(d)) * a + 0.5f); };
  px = mix(px & 0xFF, c.b) | (mix((px >> 8) & 0xFF, c.g) << 8) | (mix((px >> 16) & 0xFF, c.r) << 16) | 0xFF000000u;
}

// Расстояние до скруглённого прямоугольника (отрицательное внутри).
float RoundRect(float x, float y, float hx, float hy, float r) {
  const float qx = std::abs(x) - (hx - r), qy = std::abs(y) - (hy - r);
  const float ox = std::max(qx, 0.0f), oy = std::max(qy, 0.0f);
  return std::sqrt(ox * ox + oy * oy) + std::min(std::max(qx, qy), 0.0f) - r;
}

float Stroke(float d, float half) {
  return Clamp01(half + 0.5f - std::abs(d));
}

float Fill(float d) {
  return Clamp01(0.5f - d);
}

}  // namespace

void NhlLegacySplashArt::PutText(std::vector<float>& rgb, const wchar_t* text, int font_px, int weight, int spacing,
                                 int cy, int x_shift, float r, float g, float b, float a, int* x_end) {
  HDC dc = CreateCompatibleDC(nullptr);
  HFONT font = CreateFontW(-font_px, 0, 0, 0, weight, FALSE, FALSE, FALSE, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS,
                           CLIP_DEFAULT_PRECIS, ANTIALIASED_QUALITY, DEFAULT_PITCH, L"Segoe UI");
  HGDIOBJ old_font = SelectObject(dc, font);
  SetTextCharacterExtra(dc, spacing);
  const int len = int(std::wcslen(text));
  SIZE size{};
  GetTextExtentPoint32W(dc, text, len, &size);
  const int tw = std::max<int>(1, size.cx - spacing), th = std::max<int>(1, size.cy);
  BITMAPINFO info{};
  info.bmiHeader.biSize = sizeof(info.bmiHeader);
  info.bmiHeader.biWidth = tw;
  info.bmiHeader.biHeight = -th;
  info.bmiHeader.biPlanes = 1;
  info.bmiHeader.biBitCount = 32;
  info.bmiHeader.biCompression = BI_RGB;
  void* bits = nullptr;
  HBITMAP bmp = CreateDIBSection(dc, &info, DIB_RGB_COLORS, &bits, nullptr, 0);
  HGDIOBJ old_bmp = SelectObject(dc, bmp);
  std::memset(bits, 0, size_t(tw) * size_t(th) * 4);
  SetTextColor(dc, RGB(255, 255, 255));
  SetBkMode(dc, TRANSPARENT);
  TextOutW(dc, 0, 0, text, len);
  GdiFlush();
  const int x0 = (w_ - tw) / 2 + x_shift, y0 = cy - th / 2;
  const uint32_t* src = static_cast<const uint32_t*>(bits);
  const Rgb c{r, g, b};
  for (int y = 0; y < th; ++y) {
    const int py = y0 + y;
    if (py < 0 || py >= h_) {
      continue;
    }
    for (int x = 0; x < tw; ++x) {
      const int px = x0 + x;
      if (px < 0 || px >= w_) {
        continue;
      }
      const uint32_t s = src[size_t(y) * size_t(tw) + size_t(x)];
      const float cover = float(std::max({s & 0xFF, (s >> 8) & 0xFF, (s >> 16) & 0xFF})) / 255.0f;
      Over(&rgb[(size_t(py) * size_t(w_) + size_t(px)) * 3], c, cover * a);
    }
  }
  if (x_end) {
    *x_end = x0 + tw;
  }
  SelectObject(dc, old_bmp);
  DeleteObject(bmp);
  SelectObject(dc, old_font);
  DeleteObject(font);
  DeleteDC(dc);
}

void NhlLegacySplashArt::Build(int w, int h) {
  w_ = w;
  h_ = h;
  u_ = float(h) / 720.0f;
  // Каток — 40 % высоты, в узком окне — не шире 80 % ширины.
  const float rink_h = std::min(0.40f * float(h), 0.80f * float(w) * kRinkH / kRinkW);
  k_ = rink_h / kRinkH;
  cx_ = float(w) / 2.0f;
  cy_ = float(h) * 0.47f;

  std::vector<float> rgb(size_t(w) * size_t(h) * 3);
  // Фон: вертикальный градиент и мягкое свечение под катком.
  const float glow_r = 0.62f * float(h);
  for (int y = 0; y < h; ++y) {
    const float t = float(y) / float(std::max(1, h - 1));
    const Rgb row{kTop.r + (kBottom.r - kTop.r) * t, kTop.g + (kBottom.g - kTop.g) * t,
                  kTop.b + (kBottom.b - kTop.b) * t};
    for (int x = 0; x < w; ++x) {
      const float dx = (float(x) - cx_) / glow_r, dy = (float(y) - cy_) / (glow_r * 0.8f);
      const float g = std::exp(-(dx * dx + dy * dy) * 1.6f);
      float* p = &rgb[(size_t(y) * size_t(w) + size_t(x)) * 3];
      p[0] = row.r + kGlow.r * g;
      p[1] = row.g + kGlow.g * g;
      p[2] = row.b + kGlow.b * g;
    }
  }

  // Каток.
  const float hx = kRinkW / 2.0f, hy = kRinkH / 2.0f;
  const float board = std::max(1.0f, 1.25f * u_);  // полутолщина борта, px
  const float thin = std::max(0.6f, 0.65f * u_);    // полутолщина тонких линий (круги, линии ворот)
  const float wide = std::max(1.0f, 0.5f * k_);     // полутолщина центральной и синих линий: 12 дюймов
  const int x_lo = std::max(0, int(cx_ - (hx * k_ + board + 3.0f)));
  const int x_hi = std::min(w, int(cx_ + (hx * k_ + board + 3.0f)) + 1);
  const int y_lo = std::max(0, int(cy_ - (hy * k_ + board + 3.0f)));
  const int y_hi = std::min(h, int(cy_ + (hy * k_ + board + 3.0f)) + 1);
  const float zones[4][2] = {{-kZoneX, -kDotY}, {-kZoneX, kDotY}, {kZoneX, -kDotY}, {kZoneX, kDotY}};
  const float neutral[4][2] = {{-kNeutralX, -kDotY}, {-kNeutralX, kDotY}, {kNeutralX, -kDotY}, {kNeutralX, kDotY}};
  for (int y = y_lo; y < y_hi; ++y) {
    for (int x = x_lo; x < x_hi; ++x) {
      float* p = &rgb[(size_t(y) * size_t(w) + size_t(x)) * 3];
      const float px = float(x) + 0.5f - cx_, py = float(y) + 0.5f - cy_;  // px
      const float fx = px / k_, fy = py / k_;                              // футы
      const float d_rink = RoundRect(px, py, hx * k_, hy * k_, kCorner * k_);
      const float ice = Fill(d_rink);
      if (ice > 0.0f) {
        // Лёд: чуть светлее к центру, как под светом арены.
        const float sheen = 1.0f - 0.35f * Clamp01((fx * fx) / (hx * hx) + (fy * fy) / (hy * hy));
        Over(p, Rgb{kIce.r * sheen + 6, kIce.g * sheen + 8, kIce.b * sheen + 10}, 0.78f * ice);
        // Вратарские площадки (полукруг R 6 за линией ворот) — заливка.
        for (float gx : {-kGoalX, kGoalX}) {
          const float dx = (fx - gx) * (gx < 0 ? -1.0f : 1.0f);  // в поле — отрицательное
          if (dx <= 0.5f) {
            const float d = std::sqrt((fx - gx) * (fx - gx) + fy * fy) * k_ - 6.0f * k_;
            Over(p, kCrease, 0.30f * Fill(d) * Fill(dx * k_) * ice);
            Over(p, kRed, 0.80f * Stroke(d, thin) * Fill(dx * k_) * ice);
          }
        }
        Over(p, kRed, 0.62f * Stroke(px, wide) * ice);                    // центральная красная
        Over(p, kBlue, 0.85f * Stroke(std::abs(px) - kBlueX * k_, wide) * ice);  // синие
        Over(p, kRed, 0.80f * Stroke(std::abs(px) - kGoalX * k_, thin) * ice);   // линии ворот
        const float d_center = std::sqrt(px * px + py * py);
        Over(p, kBlue, 0.85f * Stroke(d_center - kCircleR * k_, thin) * ice);
        Over(p, kBlue, 0.90f * Fill(d_center - 0.6f * k_));
        for (const auto& z : zones) {
          const float d = std::sqrt((fx - z[0]) * (fx - z[0]) + (fy - z[1]) * (fy - z[1])) * k_;
          Over(p, kRed, 0.78f * Stroke(d - kCircleR * k_, thin) * ice);
          Over(p, kRed, 0.85f * Fill(d - 1.0f * k_));
        }
        for (const auto& z : neutral) {
          const float d = std::sqrt((fx - z[0]) * (fx - z[0]) + (fy - z[1]) * (fy - z[1])) * k_;
          Over(p, kRed, 0.85f * Fill(d - 1.0f * k_));
        }
        // Ворота: рамка 6 × 3,3 фута за линией ворот.
        for (float gx : {-kGoalX, kGoalX}) {
          const float back = gx + (gx < 0 ? -3.3f : 3.3f);
          const float mx = (gx + back) / 2.0f;
          const float d = RoundRect((fx - mx) * k_, fy * k_, 1.65f * k_, 3.0f * k_, 0.8f * k_);
          Over(p, kRed, 0.75f * Stroke(d, thin) * ice);
        }
      }
      Over(p, kBoard, 0.88f * Stroke(d_rink, board));
    }
  }

  // Подписи: название сверху, под ним мелко автор (пользователь, 03.11.2026: «на загрузочный экран добавь @megarohas»),
  // «Loading» снизу (точки рисует кадр).
  const int title_px = std::max(12, int(30.0f * u_));
  PutText(rgb, L"NHL LEGACY REMASTER", title_px, FW_SEMIBOLD, int(title_px * 0.22f), int(cy_ - hy * k_ - 72.0f * u_), 0,
          kTitle.r, kTitle.g, kTitle.b, 0.95f, nullptr);
  const int author_px = std::max(9, int(14.0f * u_));
  PutText(rgb, L"@megarohas", author_px, FW_NORMAL, int(author_px * 0.10f), int(cy_ - hy * k_ - 38.0f * u_), 0, kSub.r,
          kSub.g, kSub.b, 0.85f, nullptr);
  const int sub_px = std::max(10, int(17.0f * u_));
  int loading_end = 0;
  const int loading_y = int(cy_ + hy * k_ + 52.0f * u_);
  // «LOADING» и три точки — по центру вместе: текст сдвинут влево на половину точек (10 + 2 × 10 + 2,6 единицы).
  PutText(rgb, L"LOADING", sub_px, FW_SEMIBOLD, int(sub_px * 0.32f), loading_y, -int(16.0f * u_), kSub.r, kSub.g, kSub.b,
          1.0f, &loading_end);
  dots_x_ = float(loading_end) + 10.0f * u_;
  dots_y_ = float(loading_y) + 3.5f * u_;

  // В целые пиксели с лёгким шумом (без полос в градиенте).
  base_.resize(size_t(w) * size_t(h));
  for (int y = 0; y < h; ++y) {
    for (int x = 0; x < w; ++x) {
      const size_t i = size_t(y) * size_t(w) + size_t(x);
      const float n = (float(((x * 7 + y * 13) ^ (x * y)) & 15) / 15.0f - 0.5f) * 0.9f;
      const auto q = [n](float v) { return uint32_t(std::clamp(v + n + 0.5f, 0.0f, 255.0f)); };
      base_[i] = q(rgb[i * 3 + 2]) | (q(rgb[i * 3 + 1]) << 8) | (q(rgb[i * 3]) << 16) | 0xFF000000u;
    }
  }
}

void NhlLegacySplashArt::Frame(double t, uint32_t* out, RECT* dirty) const {
  // Шайба по центральному кругу, по часовой стрелке, шлейф — как у спиннера надписи о шейдерах.
  const float radius = kCircleR * k_;
  const float trail_half = std::max(1.2f, 1.1f * k_);
  const float puck_r = std::max(3.0f, 2.3f * k_);
  const float margin = puck_r + trail_half + 3.0f;
  RECT r1{std::max(0, int(cx_ - radius - margin)), std::max(0, int(cy_ - radius - margin)),
          std::min(w_, int(cx_ + radius + margin) + 1), std::min(h_, int(cy_ + radius + margin) + 1)};
  const float dot_r = std::max(1.5f, 2.6f * u_), dot_gap = 10.0f * u_;
  RECT r2{std::max(0, int(dots_x_ - dot_r - 2)), std::max(0, int(dots_y_ - dot_r - 2)),
          std::min(w_, int(dots_x_ + 2 * dot_gap + dot_r + 3)), std::min(h_, int(dots_y_ + dot_r + 3))};
  for (const RECT& r : {r1, r2}) {
    for (int y = r.top; y < r.bottom; ++y) {
      std::memcpy(out + size_t(y) * size_t(w_) + size_t(r.left), base_.data() + size_t(y) * size_t(w_) + size_t(r.left),
                  size_t(r.right - r.left) * 4);
    }
  }

  const float head = float(std::fmod(t / kTurn, 1.0));
  const float theta = 6.2831853f * (head - 0.5f);
  const float pcx = cx_ + radius * std::cos(theta), pcy = cy_ + radius * std::sin(theta);
  for (int y = r1.top; y < r1.bottom; ++y) {
    for (int x = r1.left; x < r1.right; ++x) {
      const float dx = float(x) + 0.5f - cx_, dy = float(y) + 0.5f - cy_;
      const float d = std::sqrt(dx * dx + dy * dy) - radius;
      uint32_t& px = out[size_t(y) * size_t(w_) + size_t(x)];
      if (std::abs(d) < trail_half + 1.0f) {
        const float at = std::atan2(dy, dx) / 6.2831853f + 0.5f;
        float behind = head - at;
        behind -= std::floor(behind);
        const float tail = std::max(0.0f, 1.0f - behind / kTrail);
        if (tail > 0.0f) {
          const float half = trail_half * (0.25f + 0.75f * tail);
          OverPixel(px, kTrailRgb, Stroke(d, half) * tail * tail * 0.85f);
        }
      }
      const float pd = std::sqrt((float(x) + 0.5f - pcx) * (float(x) + 0.5f - pcx) +
                                 (float(y) + 0.5f - pcy) * (float(y) + 0.5f - pcy)) - puck_r;
      if (pd < 1.5f) {
        OverPixel(px, kPuck, Fill(pd));
        OverPixel(px, kPuckRim, 0.9f * Stroke(pd + 0.9f * u_, std::max(0.5f, 0.55f * u_)));
      }
    }
  }

  // Точки после «LOADING»: волна слева направо.
  for (int i = 0; i < 3; ++i) {
    const double phase = std::fmod(t * 1.25 - i * 0.18, 1.0);
    const float pulse = float(0.5 - 0.5 * std::cos(6.2831853 * std::clamp(phase * 1.6, 0.0, 1.0)));
    const float a = 0.25f + 0.75f * pulse;
    const float dcx = dots_x_ + float(i) * dot_gap;
    for (int y = r2.top; y < r2.bottom; ++y) {
      for (int x = std::max(int(r2.left), int(dcx - dot_r - 2)); x < std::min(int(r2.right), int(dcx + dot_r + 2));
           ++x) {
        const float dd = std::sqrt((float(x) + 0.5f - dcx) * (float(x) + 0.5f - dcx) +
                                   (float(y) + 0.5f - dots_y_) * (float(y) + 0.5f - dots_y_)) - dot_r;
        OverPixel(out[size_t(y) * size_t(w_) + size_t(x)], kSub, a * Fill(dd));
      }
    }
  }
  if (dirty) {
    *dirty = RECT{std::min(r1.left, r2.left), std::min(r1.top, r2.top), std::max(r1.right, r2.right),
                  std::max(r1.bottom, r2.bottom)};
  }
}

#if !defined(NHLLEGACY_SPLASH_PREVIEW)

// ─── Окно ──────────────────────────────────────────────────────────────────────────────────────────────────────────

void NhlLegacySplashWindowOpened() {
  int64_t expected = 0;
  g_window_ms.compare_exchange_strong(expected, NowMs());
  if (REXCVAR_GET(nhl_splash)) {
    // Поток UI занят сборкой хранилища шейдеров секунды (с холодным кэшем драйвера — дольше): без этого Windows через 5 с
    // подменяет окно игры «призраком» «Не отвечает», и он ложится поверх заставки.
    DisableProcessWindowsGhosting();
  }
}

NhlLegacySplash::NhlLegacySplash() = default;

NhlLegacySplash::~NhlLegacySplash() {
  g_probe_stop.store(true);
  if (probe_.joinable()) {
    probe_.join();
  }
  Destroy();
}

bool NhlLegacySplash::Pending() const {
  return !finished_ && REXCVAR_GET(nhl_splash) && g_window_ms.load() != 0;
}

void NhlLegacySplash::Hide() {
  if (visible_) {
    ShowWindow(wnd_, SW_HIDE);
    visible_ = false;
    full_update_ = true;
  }
}

void NhlLegacySplash::Destroy() {
  if (bitmap_) {
    SelectObject(dc_, old_bitmap_);
    DeleteObject(bitmap_);
    bitmap_ = nullptr;
    pixels_ = nullptr;
  }
  if (dc_) {
    DeleteDC(dc_);
    dc_ = nullptr;
  }
  if (wnd_) {
    DestroyWindow(wnd_);
    wnd_ = nullptr;
  }
  if (owner_) {
    DestroyWindow(owner_);
    owner_ = nullptr;
  }
  visible_ = false;
}

HWND NhlLegacySplash::Update(HWND game) {
  if (finished_) {
    return nullptr;
  }
  const int64_t now = NowMs();
  const int64_t window_ms = g_window_ms.load();
  if (!REXCVAR_GET(nhl_splash) || window_ms == 0) {
    if (!REXCVAR_GET(nhl_splash) && window_ms != 0) {
      finished_ = true;  // выключили в F4 — больше не показываем
      g_done.store(true);
      Destroy();
    }
    return nullptr;
  }
  // Нужна ли заставка сейчас. До первого VdSwap окно чёрное всегда. До первой картинки игры — тоже (или до запасного
  // признака). После — только если окно игры чёрное дольше kBlackShow: паузы загрузки до главного меню. Окно SDK (сообщение
  // игры, F4, консоль) рисуется в окне игры — пока оно открыто, заставки нет.
  const int64_t first_swap = g_first_swap_ms.load();
  if (!first_done_) {
    const char* why = g_seen_picture.load()          ? "game picture"
                      : g_screen_ready.load()        ? "fallback: first screen file + 30 frames"
                      : first_swap && now - first_swap > kFallbackAfterSwap ? "fallback: 40 s after the first VdSwap"
                                                                            : nullptr;
    if (why) {
      first_done_ = true;
      REXLOG_INFO("[nhllegacy] splash: first game frame ({}), {:.2f} s after the window opened, {} swaps", why,
                  double(now - window_ms) / 1000.0, g_swaps.load());
    }
  }
  const int64_t black_since = g_black_since.load();
  // Снова — только если снимки уже видели картинку: иначе снимок не работает (чёрный всегда) и заставка легла бы на игру.
  const bool long_black = g_seen_picture.load() && black_since && now - black_since >= kBlackShow;
  if (first_done_ && long_black && !wanted_) {
    hold_until_ms_ = now + kFadeIn + kMinShow;
  }
  bool want = !first_done_ || long_black || now < hold_until_ms_;
  if (NhlLegacySdkDialogOpen()) {
    want = false;
  }
  // Конец: главное меню (или предел времени) и заставка уже погасла.
  const bool boot_over = (g_menu_ms.load() && first_done_) || now - window_ms > kBootLimit;
  if (boot_over && !want && alpha_ <= 0.0f) {
    REXLOG_INFO("[nhllegacy] splash: done at {:.2f} s ({})", double(now - window_ms) / 1000.0,
                g_menu_ms.load() ? "main menu" : "time limit");
    g_probe_stop.store(true);
    finished_ = true;
    g_done.store(true);
    Destroy();
    return nullptr;
  }
  if (boot_over) {
    want = false;
  }
  // Плавно: появление за kFadeIn, уход за kFadeOut.
  const float step = float(std::min<int64_t>(now - (last_ms_ ? last_ms_ : now), 100));
  last_ms_ = now;
  alpha_ = want ? std::min(1.0f, alpha_ + step / float(kFadeIn)) : std::max(0.0f, alpha_ - step / float(kFadeOut));
  if (!want && !first_done_) {
    alpha_ = 0.0f;
  }
  if (want != wanted_) {
    wanted_ = want;
    if (want && first_done_) {
      REXLOG_INFO("[nhllegacy] splash: shown again at {:.2f} s (game window black {:.1f} s)",
                  double(now - window_ms) / 1000.0, double(now - black_since) / 1000.0);
    } else if (!want) {
      REXLOG_INFO("[nhllegacy] splash: hidden at {:.2f} s", double(now - window_ms) / 1000.0);
    }
  }
  if (game) {
    g_game.store(game);
    if (first_swap && !probe_.joinable()) {
      probe_ = std::thread(ProbeLoop);  // после первого VdSwap поток UI свободен, PrintWindow его не ждёт
    }
  }
  if (!game || alpha_ <= 0.0f) {
    Hide();
    return nullptr;
  }
  float alpha = alpha_;
  RECT client{};
  GetClientRect(game, &client);
  POINT origin{0, 0};
  ClientToScreen(game, &origin);
  if (client.right < 64 || client.bottom < 64 || IsIconic(game)) {
    Hide();
    return nullptr;
  }
  if (!wnd_) {
    const HINSTANCE instance = GetModuleHandleW(nullptr);
    WNDCLASSW wc{};
    wc.lpfnWndProc = DefWindowProcW;
    wc.hInstance = instance;
    wc.lpszClassName = L"NhlLegacySplash";
    RegisterClassW(&wc);
    owner_ = CreateWindowExW(0, wc.lpszClassName, L"", WS_POPUP, 0, 0, 0, 0, nullptr, nullptr, instance, nullptr);
    wnd_ = CreateWindowExW(WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW, wc.lpszClassName,
                           L"", WS_POPUP, 0, 0, 1, 1, owner_, nullptr, instance, nullptr);
    dc_ = CreateCompatibleDC(nullptr);
  }
  if (client.right != art_.width() || client.bottom != art_.height()) {
    const int64_t t0 = NowMs();
    art_.Build(client.right, client.bottom);
    if (bitmap_) {
      SelectObject(dc_, old_bitmap_);
      DeleteObject(bitmap_);
    }
    BITMAPINFO info{};
    info.bmiHeader.biSize = sizeof(info.bmiHeader);
    info.bmiHeader.biWidth = client.right;
    info.bmiHeader.biHeight = -client.bottom;
    info.bmiHeader.biPlanes = 1;
    info.bmiHeader.biBitCount = 32;
    info.bmiHeader.biCompression = BI_RGB;
    void* bits = nullptr;
    bitmap_ = CreateDIBSection(dc_, &info, DIB_RGB_COLORS, &bits, nullptr, 0);
    old_bitmap_ = SelectObject(dc_, bitmap_);
    pixels_ = static_cast<uint32_t*>(bits);
    std::memcpy(pixels_, art_.background().data(), art_.background().size() * 4);
    full_update_ = true;
    REXLOG_INFO("[nhllegacy] splash: {}x{}, background {} ms", client.right, client.bottom, NowMs() - t0);
  }
  if (!shown_ms_) {
    shown_ms_ = now;
    REXLOG_INFO("[nhllegacy] splash: shown {:.2f} s after the window opened", double(now - window_ms) / 1000.0);
  }
  RECT dirty{};
  art_.Frame(double(now - shown_ms_) / 1000.0, pixels_, &dirty);
  GdiFlush();
  POINT pos{origin.x, origin.y};
  POINT src{0, 0};
  SIZE size{client.right, client.bottom};
  BLENDFUNCTION blend{AC_SRC_OVER, 0, BYTE(std::clamp(alpha, 0.0f, 1.0f) * 255.0f + 0.5f), AC_SRC_ALPHA};
  UPDATELAYEREDWINDOWINFO info{};
  info.cbSize = sizeof(info);
  info.pptDst = &pos;
  info.psize = &size;
  info.hdcSrc = dc_;
  info.pptSrc = &src;
  info.pblend = &blend;
  info.dwFlags = ULW_ALPHA;
  info.prcDirty = full_update_ ? nullptr : &dirty;
  if (!UpdateLayeredWindowIndirect(wnd_, &info) && !full_update_) {
    info.prcDirty = nullptr;  // окно сдвинули или сменился размер — целиком
    UpdateLayeredWindowIndirect(wnd_, &info);
  }
  full_update_ = false;
  // Z-порядок: сразу над окном игры (как надпись о шейдерах; надпись кладётся уже над заставкой).
  const bool topmost = (GetWindowLongW(game, GWL_EXSTYLE) & WS_EX_TOPMOST) != 0;
  HWND above = GetWindow(game, GW_HWNDPREV);
  if (topmost || above != wnd_ || !visible_) {
    SetWindowPos(wnd_, topmost ? HWND_TOPMOST : (above && above != wnd_ ? above : HWND_TOP), 0, 0, 0, 0,
                 SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW);
  }
  visible_ = true;
  return wnd_;
}

// ─── Перехваты ─────────────────────────────────────────────────────────────────────────────────────────────────────

extern "C" void __imp__VdSwap(PPCContext& ctx, uint8_t* base) {
  static GuestFn original = RuntimeExport("__imp__VdSwap");
  if (!g_done.load(std::memory_order_relaxed)) {
    OnSwap();
  }
  if (original) {
    original(ctx, base);
  }
}

extern "C" void __imp__NtCreateFile(PPCContext& ctx, uint8_t* base) {
  static GuestFn original = RuntimeExport("__imp__NtCreateFile");
  if (!g_done.load(std::memory_order_relaxed)) {
    OnOpen(ctx, base);
  }
  if (original) {
    original(ctx, base);
  } else {
    ctx.r3.u64 = 0xC0000001;  // STATUS_UNSUCCESSFUL
  }
}

extern "C" void __imp__NtOpenFile(PPCContext& ctx, uint8_t* base) {
  static GuestFn original = RuntimeExport("__imp__NtOpenFile");
  if (!g_done.load(std::memory_order_relaxed)) {
    OnOpen(ctx, base);
  }
  if (original) {
    original(ctx, base);
  } else {
    ctx.r3.u64 = 0xC0000001;
  }
}

#endif  // !NHLLEGACY_SPLASH_PREVIEW

#if defined(NHLLEGACY_SPLASH_PREVIEW)
// Превью: splash_preview.exe ПАПКА ШИРИНА ВЫСОТА t1 t2 … → ПАПКА\splash_<ширина>x<высота>_<t>.bmp (24 бит).
#include <cstdio>
#include <string>

int wmain(int argc, wchar_t** argv) {
  if (argc < 5) {
    std::fprintf(stderr, "usage: splash_preview DIR WIDTH HEIGHT t1 [t2 ...]\n");
    return 2;
  }
  const std::wstring dir = argv[1];
  const int w = _wtoi(argv[2]), h = _wtoi(argv[3]);
  if (w < 64 || h < 64) {
    return 2;
  }
  NhlLegacySplashArt art;
  const auto t0 = Clock::now();
  art.Build(w, h);
  const double build_ms = std::chrono::duration<double, std::milli>(Clock::now() - t0).count();
  std::vector<uint32_t> px(art.background());
  double frame_ms = 0;
  for (int i = 4; i < argc; ++i) {
    const double t = _wtof(argv[i]);
    const auto f0 = Clock::now();
    art.Frame(t, px.data(), nullptr);
    frame_ms = std::max(frame_ms, std::chrono::duration<double, std::milli>(Clock::now() - f0).count());
    wchar_t name[64];
    std::swprintf(name, 64, L"\\splash_%dx%d_%.3f.bmp", w, h, t);
    FILE* f = nullptr;
    _wfopen_s(&f, (dir + name).c_str(), L"wb");
    if (!f) {
      return 1;
    }
    const int stride = (w * 3 + 3) & ~3;
    BITMAPFILEHEADER fh{};
    BITMAPINFOHEADER ih{};
    fh.bfType = 0x4D42;
    fh.bfOffBits = sizeof(fh) + sizeof(ih);
    fh.bfSize = fh.bfOffBits + DWORD(stride) * DWORD(h);
    ih.biSize = sizeof(ih);
    ih.biWidth = w;
    ih.biHeight = -h;
    ih.biPlanes = 1;
    ih.biBitCount = 24;
    std::fwrite(&fh, sizeof(fh), 1, f);
    std::fwrite(&ih, sizeof(ih), 1, f);
    std::vector<uint8_t> row(static_cast<size_t>(stride));
    for (int y = 0; y < h; ++y) {
      for (int x = 0; x < w; ++x) {
        const uint32_t p = px[size_t(y) * size_t(w) + size_t(x)];
        row[size_t(x) * 3] = uint8_t(p);
        row[size_t(x) * 3 + 1] = uint8_t(p >> 8);
        row[size_t(x) * 3 + 2] = uint8_t(p >> 16);
      }
      std::fwrite(row.data(), 1, row.size(), f);
    }
    std::fclose(f);
  }
  std::printf("background %.1f ms, slowest frame %.2f ms\n", build_ms, frame_ms);
  return 0;
}
#endif

#else

void NhlLegacySplashWindowOpened() {}

#endif  // _WIN32
