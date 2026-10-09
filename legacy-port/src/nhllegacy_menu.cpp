// Пункт главного меню «EXIT» NHL Legacy (nhl_menu_exit; docs/legacy-port.md, «Пункт EXIT в главном меню»).
//
// Подпись и место пункта — данные FE (legacy-fe): пункт меню с именем "XboxLiveMarketplace" в
// objMainMenu.MenuCallback (boot:fe/ion/game/menus/mainmenuitems.big) зовёт родную
// _global.ION_GameSetup.ShowMarketplaceUI(EA_ZONE.gControllerIDCurrentScreen); других вызовов этой
// функции нет ни в одном ролике fe Legacy, а магазин Xbox Live в порте всё равно мёртв.
// Обёртка ShowMarketplaceUI — 832EFE28 (регистрация natives GameSetup 833019C8 @83301A08, имя @82198C9C):
// аргумент 0 (82465270 → 8247AE78), объект *(0x83C1C728), vtable+44, возврат 82464AA0.
// При nhl_menu_exit = true вместо магазина — закрытие программы тем же путём, что крестик окна:
// WM_CLOSE главному окну → «Window closing, shutting down… Title terminated» (ReXApp::OnClosing).
// В главном меню сейвы в этот момент не пишутся. При false — магазин не открывается (возврат false, см. ниже).

#include <cstdint>
#include <string_view>

#if defined(_WIN32)
#include <windows.h>
#endif

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ppc.h>

REXCVAR_DEFINE_BOOL(nhl_menu_exit, false, "NHLLegacy",
                    "Main menu item XboxLiveMarketplace (labelled EXIT by the FE mod) closes the program like "
                    "the window close button instead of opening the Xbox Live Marketplace")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

extern "C" void sub_82465270(PPCContext& ctx, uint8_t* base);          // AS: аргумент i
extern "C" void sub_8247AE78(PPCContext& ctx, uint8_t* base);          // AS: значение → число
extern "C" void sub_82464AA0(PPCContext& ctx, uint8_t* base);          // AS: bool → объект true/false

namespace {

#if defined(_WIN32)
struct MainWindow {
  HWND sdl = nullptr;
  HWND any = nullptr;
};

BOOL CALLBACK FindMainWindow(HWND hwnd, LPARAM param) {
  DWORD pid = 0;
  GetWindowThreadProcessId(hwnd, &pid);
  if (pid != GetCurrentProcessId() || !IsWindowVisible(hwnd) || GetWindow(hwnd, GW_OWNER)) {
    return TRUE;
  }
  auto* found = reinterpret_cast<MainWindow*>(param);
  char name[64] = {};
  GetClassNameA(hwnd, name, sizeof(name));
  if (std::string_view(name) == "SDL_app") {
    found->sdl = hwnd;
    return FALSE;
  }
  if (!found->any) {
    found->any = hwnd;
  }
  return TRUE;
}
#endif

// Как крестик окна: WM_CLOSE главному окну (SDL → закрытие → ReXApp::OnClosing).
bool CloseLikeWindowButton() {
#if defined(_WIN32)
  MainWindow found;
  EnumWindows(FindMainWindow, reinterpret_cast<LPARAM>(&found));
  const HWND hwnd = found.sdl ? found.sdl : found.any;
  if (hwnd && PostMessageW(hwnd, WM_CLOSE, 0, 0)) {
    return true;
  }
  REXLOG_WARN("[nhllegacy] menu exit: main window not found");
#endif
  return false;
}

}  // namespace

// Оригинал (vtable+44) доходит до заглушки XamShowMarketplaceUI: она отвечает «успех», меню ждёт закрытия
// системного интерфейса магазина, которого нет, — список пунктов пропадает навсегда (проверил legacy-fe).
// Поэтому магазин не зовём никогда: при nhl_menu_exit = false — false, как без профиля Live (игра покажет
// «нужен вход» OSDK_SIGNIN_REQUIRED и вернётся в меню), при true — ещё и закрытие программы.
extern "C" void sub_832EFE28(PPCContext& ctx, uint8_t* base) {
  if (REXCVAR_GET(nhl_menu_exit)) {
    REXLOG_INFO("[nhllegacy] menu exit (ShowMarketplaceUI): closing like the window close button");
    CloseLikeWindowButton();
  } else {
    REXLOG_INFO("[nhllegacy] menu: ShowMarketplaceUI -> false (no Xbox Live Marketplace in the port)");
  }
  // Как у оригинала, только без вызова магазина: аргумент 0 прочитать, вернуть false (82464AA0(0) — объект
  // false ActionScript; у оригинала туда идёт итог vtable+44).
  ctx.r3.u64 = 0;
  sub_82465270(ctx, base);
  sub_8247AE78(ctx, base);
  ctx.r3.u64 = 0;
  sub_82464AA0(ctx, base);
}
