// nhllegacy — хост порта NHL Legacy (по образцу порта NHL 13, nhl-13-port/src/nhl13_app.h).

#pragma once

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
#include <rex/ui/overlay/achievement_notification.h>

void NhlLegacyInstallCrashReporter();  // nhllegacy_crash.cpp
void NhlLegacyStartCursorHide(rex::ui::Window* window, rex::ui::ImGuiDrawer* drawer);  // nhllegacy_cursor.cpp
void NhlLegacyStopCursorHide();
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
    if (auto v = rex::cvar::GetFlagByName("cache_root"); !v.empty()) {
      paths.cache_root = v;
    } else {
      paths.cache_root = paths.user_data_root / "cache";
    }
  }

  // NHL Legacy при загрузке открывает cache:\ (раздел кэша жёсткого диска 360): сначала ищет там
  // каждый файл (cache:\<путь>), потом берёт из архивов game:\*.big. Рантайм монтирует только
  // game: и update: — подкладываем записываемую папку хоста cache_root/guest (как в NHL 13 и
  // Xenia). Туда же кладутся моды-данные: файл в cache:\ главнее архива.
  void OnPostSetup() override {
    NhlLegacyInstallCrashReporter();
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
    NhlLegacyStopCursorHide();
  }

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
