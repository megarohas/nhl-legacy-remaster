// nhllegacy — хост порта NHL Legacy (по образцу порта NHL 13, nhl-13-port/src/nhl13_app.h).

#pragma once

#include <cstdlib>
#include <filesystem>
#include <memory>
#include <system_error>

#include <rex/cvar.h>
#include <rex/filesystem.h>
#include <rex/filesystem/devices/host_path_device.h>
#include <rex/filesystem/vfs.h>
#include <rex/logging.h>
#include <rex/rex_app.h>
#include <rex/runtime.h>
#include <rex/system/kernel_state.h>
#include <rex/ui/overlay/achievement_notification.h>

void NhlLegacyInstallCrashReporter();  // nhllegacy_crash.cpp
void NhlLegacyStartCursorHide(rex::ui::Window* window, rex::ui::ImGuiDrawer* drawer);  // nhllegacy_cursor.cpp
void NhlLegacyStopCursorHide();
void NhlLegacyCursorFocus(bool focused);
void NhlLegacyCursorMinimized(bool minimized);
void NhlLegacyReleaseCursor(const char* reason, bool ui_thread);
bool NhlLegacyCloseRequested();
void NhlLegacyConfigureSaves(const std::filesystem::path& exe_dir,
                             const std::filesystem::path& user_data_root);  // nhllegacy_saves.cpp
void NhlLegacyLogSaves();
const std::filesystem::path& NhlLegacySavesRoot();
bool NhlLegacyContentConfigure(const std::filesystem::path& exe_dir);  // nhllegacy_content.cpp
bool NhlLegacyContentOn();
std::filesystem::path NhlLegacyMountContent(rex::filesystem::VirtualFileSystem* vfs,
                                            const std::filesystem::path& game_cache,
                                            const std::filesystem::path& highlights);
void NhlLegacyOverlayStart();  // nhllegacy_shaderstatus.cpp: поток надписи о шейдерах и заставки
void NhlLegacyShaderStatusBegin(const std::filesystem::path& cache_root);
void NhlLegacyShaderStatusEnd();
void NhlLegacyShaderStatusStop();
void NhlLegacySplashWindowOpened();  // nhllegacy_splash.cpp
void NhlLegacyMasksSetRoot(const std::filesystem::path& guest_root);  // nhllegacy_masks.cpp

class NhlLegacyApp : public rex::ReXApp {
 public:
  using rex::ReXApp::ReXApp;

  static std::unique_ptr<rex::ui::WindowedApp> Create(
      rex::ui::WindowedAppContext& ctx) {
    return std::unique_ptr<NhlLegacyApp>(new NhlLegacyApp(ctx, "nhllegacy",
        PPCImageConfig));
  }

  // SDK вычисляет пути до чтения nhllegacy.toml, поэтому game_data_root/user_data_root из
  // конфига сами по себе не работают — загружаем конфиг здесь и берём их оттуда. Аргументы
  // командной строки, если заданы, остаются в силе. Без настроек (сборка для друзей) — папки
  // рядом с exe: game\ (содержимое диска) и userdata\ (сейвы, кэш шейдеров, раздел cache:).
  void OnConfigurePaths(rex::PathConfig& paths) override {
    std::error_code ec;
    if (std::filesystem::exists(paths.config_path, ec)) {
      rex::cvar::LoadConfig(paths.config_path);
    }
    const std::filesystem::path exe_dir = rex::filesystem::GetExecutableFolder();
    if (paths.game_data_root.empty()) {
      if (auto v = rex::cvar::GetFlagByName("game_data_root"); !v.empty()) {
        paths.game_data_root = v;
      } else if (std::filesystem::is_directory(exe_dir / "game", ec)) {
        paths.game_data_root = exe_dir / "game";
      }
    }
    if (auto v = rex::cvar::GetFlagByName("user_data_root"); !v.empty()) {
      paths.user_data_root = v;
    } else {
      paths.user_data_root = exe_dir / "userdata";
    }
    // Папка content рядом с exe (nhllegacy_content.cpp): cache: — её части, служебный кэш игры и шейдеров — cache
    // рядом с exe. Без неё — как раньше: cache: = <cache_root>/guest, cache_root = userdata/cache.
    const bool content = NhlLegacyContentConfigure(exe_dir);
    if (auto v = rex::cvar::GetFlagByName("cache_root"); !v.empty()) {
      paths.cache_root = v;
    } else {
      paths.cache_root = content ? exe_dir / "cache" : paths.user_data_root / "cache";
    }
    // Сейвы, ачивки, настройки профиля — в saves\ рядом с exe (nhllegacy_saves.cpp), старые оттуда переносятся.
    NhlLegacyConfigureSaves(exe_dir, std::filesystem::absolute(paths.user_data_root, ec));
  }

  // NHL Legacy при загрузке открывает cache:\ (раздел кэша жёсткого диска 360): сначала ищет там
  // каждый файл (cache:\<путь>), потом берёт из архивов game:\*.big. Рантайм монтирует только
  // game: и update: — подкладываем записываемую папку хоста cache_root/guest (как в NHL 13 и
  // Xenia). Туда же кладутся моды-данные: файл в cache:\ главнее архива.
  void OnPostSetup() override {
    NhlLegacyInstallCrashReporter();
    NhlLegacyLogSaves();
    if (NhlLegacyContentOn()) {
      const auto& saves = NhlLegacySavesRoot();
      NhlLegacyMasksSetRoot(NhlLegacyMountContent(runtime()->file_system(), cache_root() / "game",
                                                  saves.empty() ? std::filesystem::path() : saves / "highlights"));
      return;
    }
    const std::filesystem::path cache_dir = cache_root() / "guest";
    std::error_code ec;
    std::filesystem::create_directories(cache_dir, ec);
    NhlLegacyMasksSetRoot(cache_dir);  // nhllegacy_masks.txt — свои маски в редакторе
    auto device = std::make_unique<rex::filesystem::HostPathDevice>(
        "\\CACHE", cache_dir, /*read_only=*/false);
    auto* vfs = runtime()->file_system();
    if (device->Initialize() && vfs->RegisterDevice(std::move(device))) {
      vfs->RegisterSymbolicLink("cache:", "\\CACHE");
      REXLOG_INFO("[nhllegacy] cache: -> {}", cache_dir.string());
    } else {
      REXLOG_ERROR("[nhllegacy] failed to mount cache: at {}", cache_dir.string());
    }
  }

  // Окно и ImGui уже есть, поток — UI: курсор над окном игры (nhllegacy_cursor.cpp), заставка первой загрузки поверх
  // чёрного окна до первого кадра игры (nhllegacy_splash.cpp, рисует поток надписи о шейдерах).
  void OnCreateDialogs(rex::ui::ImGuiDrawer* drawer) override {
    NhlLegacyStartCursorHide(window(), drawer);
    NhlLegacySplashWindowOpened();
    NhlLegacyOverlayStart();
  }

  void OnShutdown() override {
    NhlLegacyShaderStatusStop();
    NhlLegacyReleaseCursor("shutdown", true);
  }

  // Крестик, Alt+F4 и EXIT в меню (WM_CLOSE) идут через запрос закрытия. Выходим прямо здесь, тем же, чем выходит
  // ReXApp::OnClosing (TerminateTitle и std::_Exit), но без штатной разборки окна перед ним: потеря фокуса, отключение
  // ввода SDL и mnk. В ней закрытие иногда зависало — процесс оставался жить без окна, с музыкой (05.11.2026, у
  // пользователя и на стенде с фокусом на окне игры; «Window closing» в журнал так и не попадал). Перед выходом —
  // курсор Windows и страховка: процесс завершится сам, если и здесь что-то повиснет (nhllegacy_cursor.cpp).
  bool OnWindowCloseRequested() override {
    if (!NhlLegacyCloseRequested()) {
      return false;
    }
    REXLOG_INFO("[nhllegacy] exit: window close request, terminating the title");
    if (runtime() && runtime()->kernel_state()) {
      runtime()->kernel_state()->TerminateTitle();
    }
    REXLOG_INFO("[nhllegacy] exit: title terminated; exiting the process");
    rex::FlushLogging();
    std::_Exit(0);
  }

  void OnWindowFocusChanged(bool focused) override { NhlLegacyCursorFocus(focused); }
  void OnWindowMinimized() override { NhlLegacyCursorMinimized(true); }
  void OnWindowRestored() override { NhlLegacyCursorMinimized(false); }

  // Между этими вызовами SDK загружает хранилище шейдеров на потоке UI (nhllegacy_shaderstatus.cpp).
  void OnPreLaunchModule() override { NhlLegacyShaderStatusBegin(cache_root()); }

  void OnPostLaunchModule(rex::system::XThread*) override { NhlLegacyShaderStatusEnd(); }

  // Без окна уведомлений о достижениях: пока у презентера есть хоть одно окно интерфейса, кадр
  // игры выводится из потока UI по обновлению монитора — лишняя задержка и рывки (разбор:
  // docs/graphics-settings.md, как в NHL 13).
  std::unique_ptr<rex::ui::AchievementNotificationDialog>
  CreateAchievementNotificationDialog() override {
    return nullptr;
  }
};
