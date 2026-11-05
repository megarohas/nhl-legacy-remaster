// Курсор над окном игры (nhl_hide_cursor; docs/legacy-port.md, «Курсор над окном игры»).
//
// На 360 курсора нет, а на ПК стрелка Windows стоит поверх картинки, пока её не уведёшь. Флага у SDK нет, но есть
// Window::SetCursorVisibility (зовёт её только захват мыши в mnk_mode). kHidden прячет курсор лишь над клиентской частью
// окна: так SDL отвечает на WM_SETCURSOR, а заголовок, рамку и всё вне окна рисует Windows.
// Окна SDK (F3, F4, F7, консоль, сообщения и клавиатура Xam) нажимаются мышью: пока открыто хоть одно, курсор виден.
// Окно достижений в порте выключено (nhllegacy_app.h), поэтому HasDialogs не горит постоянно. Событий об открытии у
// ImGuiDrawer нет, отсюда таймер; он идёт в потоке UI, как и всё, что здесь трогается.
//
// Возврат курсора (05.11.2026, жалоба пользователя: после выхода из игры курсора нет, пока не откроешь программу):
// SDK выходит из игры std::_Exit прямо из обработчика закрытия окна (ReXApp::OnClosing), SDL при этом ничего не
// восстанавливает. Курсор Windows остаётся пустым (SetCursor(NULL) от SDL_HideCursor), а окно под ним уничтожает уже
// система при завершении процесса — новое окно под курсором WM_SETCURSOR не получает. У пользователя всегда включён один
// дисплей (Win+M+1 / Win+M+2), полноэкранное окно игры закрывает весь рабочий стол, поэтому курсор при выходе всегда над
// ним. Теперь:
// - перед закрытием (крестик, Alt+F4, EXIT в меню — всё идёт через запрос закрытия) и при падении:
//   NhlLegacyReleaseCursor — курсор виден, не зажат (ClipCursor(NULL)), захват мыши снят, стрелка, окно спрятано
//   (ShowWindow SW_HIDE: Windows сама выбирает окно под курсором и шлёт ему WM_SETCURSOR, пока процесс ещё жив);
// - без фокуса и свёрнутым курсор не прячется;
// - смена дисплеев (WM_DISPLAYCHANGE / новая геометрия рабочего стола): курсор на один шаг таймера виден и не зажат,
//   дальше — по общим правилам.

#if defined(_WIN32)
#include <windows.h>
#endif

#include <atomic>
#include <cwchar>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ui/imgui_drawer.h>
#include <rex/ui/window.h>

REXCVAR_DEFINE_BOOL(nhl_hide_cursor, true, "NHLLegacy",
                    "Hide the mouse cursor over the game window while it has focus; it stays visible outside the "
                    "window, without focus, minimized and while an SDK dialog or overlay (F3, F4, console, message "
                    "box) is open");
REXCVAR_DEFINE_BOOL(nhl_hide_cursor_unfocused, false, "NHLLegacy",
                    "Test stand only: hide the cursor over the game window even without focus (as before 0.17.0)");

namespace {

rex::ui::Window* g_window = nullptr;
rex::ui::ImGuiDrawer* g_drawer = nullptr;
std::atomic<bool> g_dialogs{false};  // для заставки (nhllegacy_splash.cpp): окно SDK не должно оказаться под ней
bool g_focused = true;     // OnWindowFocusChanged
bool g_minimized = false;  // OnWindowMinimized / OnWindowRestored
bool g_released = false;   // окно закрывается: курсор больше не прячем
const char* g_last_reason = nullptr;

#if defined(_WIN32)
HWND Hwnd() {
  return g_window ? static_cast<HWND>(g_window->GetNativeWindowHandle()) : nullptr;
}

// Рабочий стол: Win+M+1 / Win+M+2 пользователя (SetDisplayConfig, один дисплей) меняют размер и основной монитор.
struct DesktopGeometry {
  int x = 0, y = 0, w = 0, h = 0, monitors = 0;
  wchar_t primary[CCHDEVICENAME] = {};
  bool operator!=(const DesktopGeometry& o) const {
    return x != o.x || y != o.y || w != o.w || h != o.h || monitors != o.monitors || wcscmp(primary, o.primary) != 0;
  }
};

DesktopGeometry Geometry() {
  DesktopGeometry g;
  g.x = GetSystemMetrics(SM_XVIRTUALSCREEN);
  g.y = GetSystemMetrics(SM_YVIRTUALSCREEN);
  g.w = GetSystemMetrics(SM_CXVIRTUALSCREEN);
  g.h = GetSystemMetrics(SM_CYVIRTUALSCREEN);
  g.monitors = GetSystemMetrics(SM_CMONITORS);
  MONITORINFOEXW mi{};
  mi.cbSize = sizeof(mi);
  if (GetMonitorInfoW(MonitorFromPoint(POINT{0, 0}, MONITOR_DEFAULTTOPRIMARY), &mi)) {
    wcsncpy_s(g.primary, mi.szDevice, _TRUNCATE);
  }
  return g;
}

DesktopGeometry g_geometry;
bool g_display_changed = false;  // один шаг таймера после смены дисплеев курсор виден
std::atomic<bool> g_display_message{false};  // пришёл WM_DISPLAYCHANGE
HHOOK g_hook = nullptr;

// Сообщения, посланные окнам потока UI: WM_DISPLAYCHANGE (смена режима или набора дисплеев) — до SDL.
LRESULT CALLBACK OnCallWndProc(int code, WPARAM wparam, LPARAM lparam) {
  if (code == HC_ACTION) {
    const auto* m = reinterpret_cast<const CWPSTRUCT*>(lparam);
    if (m->message == WM_DISPLAYCHANGE) {
      g_display_message = true;
    }
  }
  return CallNextHookEx(g_hook, code, wparam, lparam);
}
#endif

void UpdateCursor() {
  using Visibility = rex::ui::Window::CursorVisibility;
  if (!g_window || !g_drawer) {
    return;
  }
  const bool dialogs = g_drawer->HasDialogs();
  g_dialogs.store(dialogs);
  bool display_changed = false;
#if defined(_WIN32)
  const DesktopGeometry now = Geometry();
  const bool message = g_display_message.exchange(false);
  if (now != g_geometry || message) {
    REXLOG_INFO("[nhllegacy] cursor: desktop changed{} ({}x{} at {},{}, {} monitor(s) -> {}x{} at {},{}, {} monitor(s))",
                message ? " (WM_DISPLAYCHANGE)" : "", g_geometry.w, g_geometry.h, g_geometry.x, g_geometry.y,
                g_geometry.monitors, now.w, now.h, now.x, now.y, now.monitors);
    g_geometry = now;
    g_display_changed = true;
    display_changed = true;
  } else if (g_display_changed) {
    g_display_changed = false;
  }
#endif
  const bool focused = (g_window->HasFocus() && g_focused) || REXCVAR_GET(nhl_hide_cursor_unfocused);
  const bool hide = REXCVAR_GET(nhl_hide_cursor) && !dialogs && focused && !g_minimized && !g_released &&
                    !display_changed;
  const Visibility want = hide ? Visibility::kHidden : Visibility::kVisible;
  const char* why = hide ? "" : !REXCVAR_GET(nhl_hide_cursor) ? " (nhl_hide_cursor off)" : g_released ? " (closing)"
                    : display_changed ? " (display change)" : dialogs ? " (SDK dialog)"
                    : g_minimized ? " (minimized)" : !focused ? " (no focus)" : "";
  static const char* last_why = nullptr;
  if (g_window->GetCursorVisibility() != want || why != last_why) {
    if (g_window->GetCursorVisibility() != want) {
      g_window->SetCursorVisibility(want);
    }
    if (why != last_why || hide) {
      REXLOG_INFO("[nhllegacy] cursor over the window: {}{}", hide ? "hidden" : "visible", why);
    }
    last_why = why;
  }
#if defined(_WIN32)
  if (display_changed) {
    // Рамка зажима могла остаться от прежнего рабочего стола; SDL снимает её только при потере фокуса.
    ClipCursor(nullptr);
    SetCursor(LoadCursor(nullptr, IDC_ARROW));
  }
#endif
}

#if defined(_WIN32)
constexpr UINT kPollMs = 200;
UINT_PTR g_timer = 0;

void CALLBACK OnCursorTimer(HWND, UINT, UINT_PTR, DWORD) {
  UpdateCursor();
}
#endif

}  // namespace

void NhlLegacyStartCursorHide(rex::ui::Window* window, rex::ui::ImGuiDrawer* drawer) {
  g_window = window;
  g_drawer = drawer;
#if defined(_WIN32)
  g_geometry = Geometry();
  g_hook = SetWindowsHookExW(WH_CALLWNDPROC, OnCallWndProc, nullptr, GetCurrentThreadId());
#endif
  UpdateCursor();
#if defined(_WIN32)
  g_timer = SetTimer(nullptr, 0, kPollMs, OnCursorTimer);
#endif
}

// Открыто ли окно SDK (F3, F4, консоль, сообщение, клавиатура Xam). Обновляется таймером потока UI раз в 200 мс.
bool NhlLegacySdkDialogOpen() {
  return g_dialogs.load();
}

// Поток UI: фокус окна (ReXApp::OnWindowFocusChanged) и свёртывание.
void NhlLegacyCursorFocus(bool focused) {
  g_focused = focused;
  UpdateCursor();
}

void NhlLegacyCursorMinimized(bool minimized) {
  g_minimized = minimized;
  UpdateCursor();
}

void NhlLegacyStopCursorHide() {
#if defined(_WIN32)
  if (g_timer) {
    KillTimer(nullptr, g_timer);
    g_timer = 0;
  }
  if (g_hook) {
    UnhookWindowsHookEx(g_hook);
    g_hook = nullptr;
  }
#endif
}

// Вернуть курсор Windows перед выходом. ui_thread = true — из потока UI (запрос закрытия окна): там можно трогать окно
// SDK и захват мыши. Из обработчика падения (любой поток) — только то, что не ждёт поток UI.
void NhlLegacyReleaseCursor(const char* reason, bool ui_thread) {
  g_released = true;
  if (!g_last_reason) {
    g_last_reason = reason;
  }
  if (ui_thread) {
    NhlLegacyStopCursorHide();
    if (g_window && g_window->GetCursorVisibility() != rex::ui::Window::CursorVisibility::kVisible) {
      g_window->SetCursorVisibility(rex::ui::Window::CursorVisibility::kVisible);
    }
  }
#if defined(_WIN32)
  ClipCursor(nullptr);
  if (ui_thread) {
    ReleaseCapture();
    SetCursor(LoadCursor(nullptr, IDC_ARROW));
  }
  if (HWND hwnd = Hwnd()) {
    // Окно под курсором меняется, пока процесс жив: Windows шлёт WM_SETCURSOR окну, которое теперь под курсором.
    if (ui_thread) {
      ShowWindow(hwnd, SW_HIDE);
    } else {
      ShowWindowAsync(hwnd, SW_HIDE);
    }
  }
#endif
  if (ui_thread) {
    REXLOG_INFO("[nhllegacy] cursor released ({}): visible, not clipped, game window hidden", reason);
  }
}
