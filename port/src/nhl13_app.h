// nhl13 - ReXGlue Recompiled Project
//
// Customize your app by overriding virtual hooks from rex::ReXApp.

#pragma once

#include <filesystem>
#include <memory>
#include <system_error>

#include <rex/filesystem/devices/host_path_device.h>
#include <rex/filesystem/vfs.h>
#include <rex/logging.h>
#include <rex/rex_app.h>
#include <rex/runtime.h>

class Nhl13App : public rex::ReXApp {
 public:
  using rex::ReXApp::ReXApp;

  static std::unique_ptr<rex::ui::WindowedApp> Create(
      rex::ui::WindowedAppContext& ctx) {
    return std::unique_ptr<Nhl13App>(new Nhl13App(ctx, "nhl13",
        PPCImageConfig));
  }

  // NHL 13 при загрузке открывает cache:\ (раздел кэша жёсткого диска 360), а
  // рантайм монтирует только game: и update:. Как в Xenia и nhl-legacy-recomp —
  // подкладываем записываемую папку хоста (cache_root/guest).
  void OnPostSetup() override {
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
  // void OnConfigurePaths(rex::PathConfig& paths) override {}
};
