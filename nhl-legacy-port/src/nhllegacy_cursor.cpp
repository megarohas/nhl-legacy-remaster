// Курсор над окном игры (nhl_hide_cursor; docs/legacy-port.md, «Курсор над окном игры»).
//
// На 360 курсора нет, а на ПК стрелка Windows стоит поверх картинки, пока её не уведёшь. Флага у SDK нет, но есть
// Window::SetCursorVisibility (зовёт её только захват мыши в mnk_mode). kHidden прячет курсор лишь над клиентской частью
// окна: так SDL отвечает на WM_SETCURSOR, а заголовок, рамку и всё вне окна рисует Windows, и фокус тут ни при чём.
// Окна SDK (F3, F4, F7, консоль, сообщения и клавиатура Xam) нажимаются мышью: пока открыто хоть одно, курсор виден.
// Окно достижений в порте выключено (nhllegacy_app.h), поэтому HasDialogs не горит постоянно. Событий об открытии у
// ImGuiDrawer нет, отсюда таймер; он идёт в потоке UI, как и всё, что здесь трогается.

#if defined(_WIN32)
#include <windows.h>
#endif

#include <atomic>

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ui/imgui_drawer.h>
#include <rex/ui/window.h>

REXCVAR_DEFINE_BOOL(nhl_hide_cursor, true, "NHLLegacy",
                    "Hide the mouse cursor over the game window; it stays visible outside the window and while an "
                    "SDK dialog or overlay (F3, F4, console, message box) is open");

namespace {

rex::ui::Window* g_window = nullptr;
rex::ui::ImGuiDrawer* g_drawer = nullptr;
std::atomic<bool> g_dialogs{false};  // для заставки (nhllegacy_splash.cpp): окно SDK не должно оказаться под ней

void UpdateCursor() {
  using Visibility = rex::ui::Window::CursorVisibility;
  const bool dialogs = g_drawer->HasDialogs();
  g_dialogs.store(dialogs);
  const bool hide = REXCVAR_GET(nhl_hide_cursor) && !dialogs;
  const Visibility want = hide ? Visibility::kHidden : Visibility::kVisible;
  if (g_window->GetCursorVisibility() != want) {
    g_window->SetCursorVisibility(want);
    REXLOG_INFO("[nhllegacy] cursor over the window: {}", hide ? "hidden" : "visible");
  }
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
  UpdateCursor();
#if defined(_WIN32)
  g_timer = SetTimer(nullptr, 0, kPollMs, OnCursorTimer);
#endif
}

// Открыто ли окно SDK (F3, F4, консоль, сообщение, клавиатура Xam). Обновляется таймером потока UI раз в 200 мс.
bool NhlLegacySdkDialogOpen() {
  return g_dialogs.load();
}

void NhlLegacyStopCursorHide() {
#if defined(_WIN32)
  if (g_timer) {
    KillTimer(nullptr, g_timer);
    g_timer = 0;
  }
#endif
}
