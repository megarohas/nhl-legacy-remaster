// Заставка первой загрузки (nhl_splash; nhllegacy_splash.cpp, docs/legacy-port.md, «Заставка загрузки»).
//
// Рисует поток надписи о шейдерах (nhllegacy_shaderstatus.cpp): он один держит Z-порядок своих окон, поэтому надпись
// «Compiling shaders» всегда лежит над заставкой, а заставка — сразу над окном игры.

#pragma once

#if defined(_WIN32)
#include <windows.h>

#include <cstdint>
#include <thread>
#include <vector>

// Окно игры открыто (OnCreateDialogs): от этой точки считается время до первого кадра игры.
void NhlLegacySplashWindowOpened();

// Картинка заставки без окна: фон с катком строится один раз на размер, кадр — шайба со шлейфом и точки «Loading».
// Пиксели — BGRA, непрозрачные. Её же рисует превью без игры (scripts/splash_preview.cmd).
class NhlLegacySplashArt {
 public:
  void Build(int w, int h);
  // Кадр в момент t (секунды); dirty — что изменилось относительно фона.
  void Frame(double t, uint32_t* out, RECT* dirty) const;
  int width() const { return w_; }
  int height() const { return h_; }
  const std::vector<uint32_t>& background() const { return base_; }

 private:
  void PutText(std::vector<float>& rgb, const wchar_t* text, int font_px, int weight, int spacing, int cy, int x_shift,
               float r, float g, float b, float a, int* x_end);
  std::vector<uint32_t> base_;
  int w_ = 0, h_ = 0;
  float u_ = 1.0f;                // пикселей на единицу макета 1280×720
  float cx_ = 0, cy_ = 0, k_ = 1;  // центр катка, пикселей на фут
  float dots_x_ = 0, dots_y_ = 0;  // первая точка после «Loading»
};

// Окно заставки над окном игры. Update зовётся каждый шаг потока надписи.
class NhlLegacySplash {
 public:
  NhlLegacySplash();
  ~NhlLegacySplash();
  // Нужна ли заставка дальше (включена и первый кадр игры ещё не показан).
  bool Pending() const;
  // Кадр над окном игры; возвращает окно заставки, если оно видно (надпись кладётся над ним), иначе nullptr.
  HWND Update(HWND game);

 private:
  void Hide();
  void Destroy();
  HWND owner_ = nullptr;
  HWND wnd_ = nullptr;
  HDC dc_ = nullptr;
  HBITMAP bitmap_ = nullptr;
  HGDIOBJ old_bitmap_ = nullptr;
  uint32_t* pixels_ = nullptr;
  NhlLegacySplashArt art_;
  bool visible_ = false;
  bool full_update_ = true;
  bool finished_ = false;
  int64_t shown_ms_ = 0;
  int64_t last_ms_ = 0;       // прошлый шаг (для плавности)
  float alpha_ = 0.0f;        // прозрачность окна заставки 0–1
  bool first_done_ = false;   // первая картинка игры была (или сработал запасной признак)
  bool wanted_ = true;        // прошлое решение «нужна» — для журнала
  int64_t hold_until_ms_ = 0;  // показанная снова заставка стоит до этого времени
  std::thread probe_;         // снимки окна игры после первого VdSwap (картинка игры — заставка гаснет)
};

#endif
