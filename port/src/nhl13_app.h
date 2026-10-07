// nhl13 - ReXGlue Recompiled Project
//
// Customize your app by overriding virtual hooks from rex::ReXApp.

#pragma once

#include <filesystem>
#include <memory>
#include <system_error>

#include <rex/cvar.h>
#include <rex/filesystem/devices/host_path_device.h>
#include <rex/filesystem/vfs.h>
#include <rex/logging.h>
#include <rex/rex_app.h>
#include <rex/runtime.h>

void Nhl13InstallCrashReporter();  // nhl13_crash.cpp

class Nhl13App : public rex::ReXApp {
 public:
  using rex::ReXApp::ReXApp;

  static std::unique_ptr<rex::ui::WindowedApp> Create(
      rex::ui::WindowedAppContext& ctx) {
    return std::unique_ptr<Nhl13App>(new Nhl13App(ctx, "nhl13",
        PPCImageConfig));
  }

  // SDK вычисляет пути до чтения nhl13.toml, поэтому game_data_root/user_data_root
  // из конфига сами по себе не работают — загружаем конфиг здесь и берём их оттуда.
  // Аргументы командной строки, если заданы, остаются в силе.
  void OnConfigurePaths(rex::PathConfig& paths) override {
    std::error_code ec;
    if (std::filesystem::exists(paths.config_path, ec)) {
      rex::cvar::LoadConfig(paths.config_path);
    }
    if (paths.game_data_root.empty()) {
      if (auto v = rex::cvar::GetFlagByName("game_data_root"); !v.empty()) {
        paths.game_data_root = v;
      }
    }
    if (auto v = rex::cvar::GetFlagByName("user_data_root"); !v.empty()) {
      paths.user_data_root = v;
      if (rex::cvar::GetFlagByName("cache_root").empty()) {
        paths.cache_root = paths.user_data_root / "cache";
      }
    }
  }

  // NHL 13 при загрузке открывает cache:\ (раздел кэша жёсткого диска 360), а
  // рантайм монтирует только game: и update:. Как в Xenia и nhl-legacy-recomp —
  // подкладываем записываемую папку хоста (cache_root/guest).
  void OnPostSetup() override {
    Nhl13InstallCrashReporter();
    const std::filesystem::path cache_dir = cache_root() / "guest";
    std::error_code ec;
    std::filesystem::create_directories(cache_dir, ec);
    auto device = std::make_unique<rex::filesystem::HostPathDevice>(
        "\\CACHE", cache_dir, /*read_only=*/false);
    auto* vfs = runtime()->file_system();
    if (device->Initialize() && vfs->RegisterDevice(std::move(device))) {
      vfs->RegisterSymbolicLink("cache:", "\\CACHE");
      REXLOG_INFO("[nhl13] cache: -> {}", cache_dir.string());
    } else {
      REXLOG_ERROR("[nhl13] failed to mount cache: at {}", cache_dir.string());
    }
  }

  // Override virtual hooks for customization:
  // void OnPostInitLogging() override {}
  // void OnPreSetup(rex::RuntimeConfig& config) override {}
  // void OnLoadXexImage(std::string& xex_image) override {}
  // void OnPostLoadXexImage() override {}
  // void OnCreateDialogs(rex::ui::ImGuiDrawer* drawer) override {}
  // std::unique_ptr<rex::ui::ImGuiDialog> CreateAchievementsOverlay() override;
  // std::unique_ptr<rex::ui::AchievementNotificationDialog>
  // CreateAchievementNotificationDialog() override;
  // void OnShutdown() override {}
};
