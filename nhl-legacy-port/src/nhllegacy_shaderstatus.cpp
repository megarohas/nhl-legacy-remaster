// Надпись «Compiling shaders» со спиннером (nhl_shader_status; docs/legacy-port.md, «Надпись о сборке шейдеров»).
//
// Шейдеры собираются в двух местах:
// - при старте: InitializeShaderStorage идёт на потоке UI, окно чёрное. С тёплым кэшем драйвера это 0,1 с, с холодным —
//   секунды. Вилка — OnPreLaunchModule / OnPostLaunchModule (nhllegacy_app.h);
// - в игре: фоновые потоки, когда встретился новый шейдер. IsCreatingPipelines закрыт внутри rexgpu-xenos.dll, поэтому
//   смотрим на то, что видно снаружи: файлы хранилища shaders/shareable растут в конце кадра с новым шейдером.
// Рисуем своим окном поверх игры, а не окном ImGui: при старте поток UI занят, а окно ImGui переводит вывод кадра в поток
// UI (задержка и рывки, см. nhllegacy_app.h). Окно прозрачно для мыши и фокуса, лежит сразу над окном игры в Z-порядке,
// поэтому другие окна его закрывают. Скрытый владелец нужен, чтобы окно не считалось главным окном процесса.
// Этот же поток рисует заставку первой загрузки (nhllegacy_splash.cpp) и держит порядок: игра, заставка, надпись. Поток
// запускается при открытии окна (NhlLegacyOverlayStart из OnCreateDialogs), папку хранилища получает позже, в Begin.

#include <filesystem>

#if defined(_WIN32)
#include <windows.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <mutex>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <string_view>
#include <system_error>
#include <thread>
#include <vector>
#endif

#include <rex/cvar.h>
#include <rex/logging.h>

#include "nhllegacy_splash.h"

REXCVAR_DEFINE_BOOL(nhl_shader_status, true, "NHLLegacy",
                    "Show a \"Compiling shaders\" badge with a spinner over the game window while shaders compile");

#if defined(_WIN32)

namespace {

using Clock = std::chrono::steady_clock;
using std::chrono::milliseconds;

constexpr wchar_t kText[] = L"Compiling shaders";
constexpr auto kFrame = milliseconds(33);        // шаг, пока надпись видна
constexpr auto kPoll = milliseconds(250);        // шаг опроса файлов
constexpr auto kStartupShow = milliseconds(400); // быстрый старт (тёплый кэш) не показываем
constexpr auto kHold = milliseconds(1500);       // столько держим после последнего роста файлов
constexpr int kMinGrowths = 2;                   // один новый шейдер собирается незаметно, надпись не нужна
constexpr double kTurnSeconds = 1.1;             // оборот спиннера
constexpr float kPillAlpha = 0.68f;
constexpr int kMarginAt720 = 18;
constexpr int kFontAt720 = 17;
constexpr int kPadAt720 = 11;
constexpr int kGapAt720 = 10;

std::atomic<bool> g_stop{false};
std::atomic<int64_t> g_startup_since{0};  // Clock в мс, 0 — не старт
std::thread g_thread;
std::mutex g_thread_mutex;
std::mutex g_dir_mutex;
std::filesystem::path g_dir;  // shaders/shareable; пусто — ещё не известна (до OnPreLaunchModule)

int64_t NowMs() {
  return std::chrono::duration_cast<milliseconds>(Clock::now().time_since_epoch()).count();
}

float Clamp01(float v) {
  return std::clamp(v, 0.0f, 1.0f);
}

// Белый с покрытием a поверх предумноженного BGRA.
uint32_t WhiteOver(uint32_t dst, float a) {
  const auto mix = [a](uint32_t c) { return uint32_t(float(c) * (1.0f - a) + 255.0f * a + 0.5f); };
  return mix(dst & 0xFF) | (mix((dst >> 8) & 0xFF) << 8) | (mix((dst >> 16) & 0xFF) << 16) | (mix(dst >> 24) << 24);
}

uint64_t StorageBytes(const std::filesystem::path& dir) {
  uint64_t total = 0;
  std::error_code ec;
  for (std::filesystem::directory_iterator it(dir, ec), end; !ec && it != end; it.increment(ec)) {
    // Открываем файл: в записи каталога размер обновится только при закрытии у SDK.
    HANDLE file = CreateFileW(it->path().c_str(), FILE_READ_ATTRIBUTES,
                              FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr, OPEN_EXISTING, 0,
                              nullptr);
    if (file == INVALID_HANDLE_VALUE) {
      continue;
    }
    LARGE_INTEGER size{};
    if (GetFileSizeEx(file, &size)) {
      total += uint64_t(size.QuadPart);
    }
    CloseHandle(file);
  }
  return total;
}

BOOL CALLBACK FindGameWindow(HWND hwnd, LPARAM param) {
  DWORD pid = 0;
  GetWindowThreadProcessId(hwnd, &pid);
  char name[64] = {};
  if (pid != GetCurrentProcessId() || !IsWindowVisible(hwnd) || !GetClassNameA(hwnd, name, sizeof(name)) ||
      std::string_view(name) != "SDL_app") {
    return TRUE;
  }
  *reinterpret_cast<HWND*>(param) = hwnd;
  return FALSE;
}

class Badge {
 public:
  Badge() {
    const HINSTANCE instance = GetModuleHandleW(nullptr);
    WNDCLASSW wc{};
    wc.lpfnWndProc = DefWindowProcW;
    wc.hInstance = instance;
    wc.lpszClassName = L"NhlLegacyShaderStatus";
    RegisterClassW(&wc);
    owner_ = CreateWindowExW(0, wc.lpszClassName, L"", WS_POPUP, 0, 0, 0, 0, nullptr, nullptr, instance, nullptr);
    wnd_ = CreateWindowExW(WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW, wc.lpszClassName,
                           L"", WS_POPUP, 0, 0, 1, 1, owner_, nullptr, instance, nullptr);
    dc_ = CreateCompatibleDC(nullptr);
  }

  ~Badge() {
    FreeLayer();
    DeleteDC(dc_);
    DestroyWindow(wnd_);
    DestroyWindow(owner_);
  }

  void Hide() {
    if (visible_) {
      ShowWindow(wnd_, SW_HIDE);
      visible_ = false;
    }
  }

  // base — окно, над которым лежит надпись: окно игры или заставка над ним.
  void Show(HWND game, HWND base, double seconds) {
    RECT client{};
    GetClientRect(game, &client);
    POINT origin{0, 0};
    ClientToScreen(game, &origin);
    if (client.bottom < 120 || IsIconic(game)) {
      Hide();
      return;
    }
    if (client.bottom != built_for_) {
      Build(client.bottom);
    }
    DrawFrame(seconds);
    const int margin = kMarginAt720 * client.bottom / 720;
    POINT pos{origin.x + client.right - w_ - margin, origin.y + margin};
    POINT src{0, 0};
    SIZE size{w_, h_};
    BLENDFUNCTION blend{AC_SRC_OVER, 0, 255, AC_SRC_ALPHA};
    UpdateLayeredWindow(wnd_, nullptr, &pos, &size, dc_, &src, 0, &blend, ULW_ALPHA);
    const bool topmost = (GetWindowLongW(game, GWL_EXSTYLE) & WS_EX_TOPMOST) != 0;
    HWND above = GetWindow(base, GW_HWNDPREV);
    if (topmost || above != wnd_ || !visible_) {
      SetWindowPos(wnd_, topmost ? HWND_TOPMOST : (above && above != wnd_ ? above : HWND_TOP), 0, 0, 0, 0,
                   SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW);
    }
    visible_ = true;
  }

 private:
  void FreeLayer() {
    if (bitmap_) {
      SelectObject(dc_, old_bitmap_);
      DeleteObject(bitmap_);
      bitmap_ = nullptr;
    }
  }

  void Build(int client_h) {
    FreeLayer();
    const int font_px = std::max(11, kFontAt720 * client_h / 720);
    const int pad = std::max(6, kPadAt720 * client_h / 720);
    const int gap = std::max(5, kGapAt720 * client_h / 720);
    HFONT font = CreateFontW(-font_px, 0, 0, 0, FW_SEMIBOLD, FALSE, FALSE, FALSE, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS,
                             CLIP_DEFAULT_PRECIS, ANTIALIASED_QUALITY, DEFAULT_PITCH, L"Segoe UI");
    HGDIOBJ old_font = SelectObject(dc_, font);
    SIZE text{};
    const int text_len = int(std::size(kText)) - 1;
    GetTextExtentPoint32W(dc_, kText, text_len, &text);
    ring_d_ = font_px + font_px / 4;
    h_ = std::max<int>(ring_d_, text.cy) + pad * 2;
    w_ = pad + h_ / 4 + ring_d_ + gap + text.cx + pad + h_ / 4;
    ring_x_ = pad + h_ / 4;

    BITMAPINFO info{};
    info.bmiHeader.biSize = sizeof(info.bmiHeader);
    info.bmiHeader.biWidth = w_;
    info.bmiHeader.biHeight = -h_;
    info.bmiHeader.biPlanes = 1;
    info.bmiHeader.biBitCount = 32;
    info.bmiHeader.biCompression = BI_RGB;
    void* bits = nullptr;
    bitmap_ = CreateDIBSection(dc_, &info, DIB_RGB_COLORS, &bits, nullptr, 0);
    old_bitmap_ = SelectObject(dc_, bitmap_);
    pixels_ = static_cast<uint32_t*>(bits);
    std::memset(pixels_, 0, size_t(w_) * size_t(h_) * 4);

    // Текст — белым по чёрному: яркость становится покрытием.
    SetTextColor(dc_, RGB(255, 255, 255));
    SetBkColor(dc_, RGB(0, 0, 0));
    SetBkMode(dc_, TRANSPARENT);
    TextOutW(dc_, ring_x_ + ring_d_ + gap, (h_ - text.cy) / 2, kText, text_len);
    GdiFlush();
    SelectObject(dc_, old_font);
    DeleteObject(font);

    base_.resize(size_t(w_) * size_t(h_));
    const float half_w = float(w_) / 2.0f;
    const float half_h = float(h_) / 2.0f;
    for (int y = 0; y < h_; ++y) {
      for (int x = 0; x < w_; ++x) {
        const size_t i = size_t(y) * size_t(w_) + size_t(x);
        const float text_cover = float(pixels_[i] & 0xFF) / 255.0f;
        const float dx = std::max(std::abs(float(x) + 0.5f - half_w) - (half_w - half_h), 0.0f);
        const float dy = std::abs(float(y) + 0.5f - half_h);
        const float cover = Clamp01(0.5f + half_h - std::sqrt(dx * dx + dy * dy));
        const uint32_t alpha = uint32_t(cover * kPillAlpha * 255.0f + 0.5f);
        base_[i] = WhiteOver(alpha << 24, text_cover);
      }
    }
    built_for_ = client_h;
  }

  void DrawFrame(double seconds) {
    std::memcpy(pixels_, base_.data(), base_.size() * 4);
    const float head = float(std::fmod(seconds / kTurnSeconds, 1.0));
    const float radius = float(ring_d_) / 2.0f - 1.0f;
    const float half_width = std::max(1.0f, float(ring_d_) / 12.0f);
    const float cx = float(ring_x_) + float(ring_d_) / 2.0f;
    const float cy = float(h_) / 2.0f;
    const int y_end = std::min(h_, int(cy + radius + half_width) + 2);
    const int x_end = std::min(w_, int(cx + radius + half_width) + 2);
    for (int y = std::max(0, int(cy - radius - half_width) - 1); y < y_end; ++y) {
      for (int x = std::max(0, int(cx - radius - half_width) - 1); x < x_end; ++x) {
        const float dx = float(x) + 0.5f - cx;
        const float dy = float(y) + 0.5f - cy;
        const float ring = Clamp01(half_width + 0.5f - std::abs(std::sqrt(dx * dx + dy * dy) - radius));
        if (ring <= 0.0f) {
          continue;
        }
        const float at = std::atan2(dy, dx) / 6.2831853f + 0.5f;
        float behind = head - at;
        behind -= std::floor(behind);
        const float tail = std::max(0.0f, 1.0f - behind / 0.85f);
        uint32_t& pixel = pixels_[size_t(y) * size_t(w_) + size_t(x)];
        pixel = WhiteOver(pixel, ring * tail * tail);
      }
    }
    GdiFlush();
  }

  HWND owner_ = nullptr;
  HWND wnd_ = nullptr;
  HDC dc_ = nullptr;
  HBITMAP bitmap_ = nullptr;
  HGDIOBJ old_bitmap_ = nullptr;
  uint32_t* pixels_ = nullptr;
  std::vector<uint32_t> base_;
  int built_for_ = 0;
  int w_ = 0;
  int h_ = 0;
  int ring_d_ = 0;
  int ring_x_ = 0;
  bool visible_ = false;
};

std::filesystem::path StorageDir() {
  std::lock_guard<std::mutex> lock(g_dir_mutex);
  return g_dir;
}

void Run() {
  Badge badge;
  NhlLegacySplash splash;
  std::filesystem::path dir;
  const auto started = Clock::now();
  uint64_t bytes = 0;
  bool have_bytes = false;
  int growths = 0;
  Clock::time_point last_growth{};
  Clock::time_point next_poll{};
  bool shown = false;
  HWND game = nullptr;

  while (!g_stop.load()) {
    MSG msg;
    while (PeekMessageW(&msg, nullptr, 0, 0, PM_REMOVE)) {
      DispatchMessageW(&msg);
    }
    const auto now = Clock::now();
    const int64_t startup_since = g_startup_since.load();
    if (dir.empty()) {
      dir = StorageDir();
    }
    if (startup_since || dir.empty()) {
      have_bytes = false;  // файлы хранилища ещё открываются, за рост не считаем
    } else if (now >= next_poll) {
      next_poll = now + kPoll;
      const uint64_t size = StorageBytes(dir);
      if (have_bytes && size > bytes) {
        ++growths;
        last_growth = now;
      }
      bytes = size;
      have_bytes = true;
      if (now - last_growth > kHold) {
        growths = 0;
      }
    }
    const bool startup_long = startup_since && NowMs() - startup_since >= kStartupShow.count();
    const bool want = REXCVAR_GET(nhl_shader_status) && (startup_long || growths >= kMinGrowths);
    const bool splash_pending = splash.Pending();
    if ((want || splash_pending) && (!game || !IsWindow(game))) {
      game = nullptr;
      EnumWindows(FindGameWindow, reinterpret_cast<LPARAM>(&game));
    }
    // Сначала заставка (сразу над игрой), потом надпись над ней.
    HWND splash_wnd = splash_pending ? splash.Update(game) : nullptr;
    if (want && game) {
      badge.Show(game, splash_wnd ? splash_wnd : game, std::chrono::duration<double>(now - started).count());
    } else {
      badge.Hide();
    }
    if (want != shown) {
      shown = want;
      REXLOG_INFO("[nhllegacy] shaders: {}", want ? "compiling" : "idle");
    }
    Sleep(DWORD((want || splash_pending ? kFrame : kPoll).count()));
  }
}

}  // namespace

void NhlLegacyOverlayStart() {
  std::lock_guard<std::mutex> lock(g_thread_mutex);
  if (!g_thread.joinable() && !g_stop.load()) {
    g_thread = std::thread(Run);
  }
}

void NhlLegacyShaderStatusBegin(const std::filesystem::path& cache_root) {
  {
    std::lock_guard<std::mutex> lock(g_dir_mutex);
    g_dir = cache_root / "shaders" / "shareable";
  }
  g_startup_since.store(NowMs());
  NhlLegacyOverlayStart();
}

void NhlLegacyShaderStatusEnd() {
  g_startup_since.store(0);
}

void NhlLegacyShaderStatusStop() {
  std::lock_guard<std::mutex> lock(g_thread_mutex);
  g_stop.store(true);
  if (g_thread.joinable()) {
    g_thread.join();
  }
}

#else

void NhlLegacyOverlayStart() {}
void NhlLegacyShaderStatusBegin(const std::filesystem::path&) {}
void NhlLegacyShaderStatusEnd() {}
void NhlLegacyShaderStatusStop() {}

#endif
