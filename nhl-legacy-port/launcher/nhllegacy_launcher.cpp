// nhllegacy_launcher — окно настроек перед запуском порта NHL Legacy (docs/launcher.md).
//
// Лежит рядом с nhllegacy.exe. Читает nhllegacy.toml (только чтение) и свой файл
// nhllegacy_launcher.toml, показывает графику и наши переключатели nhl_*, по «Играть» сохраняет
// свой файл и запускает nhllegacy.exe с аргументами --имя=значение: они сильнее nhllegacy.toml
// (docs/graphics-settings.md, «Источники и приоритет»), сам nhllegacy.toml не меняется.
//
// Сборка — build.cmd рядом (MSVC из BuildTools, статический CRT, без сторонних библиотек).
// Отладка без показа окна пользователю: --shot=файл.png [--shot-hint=N] — окно рисуется за
// пределами экрана без активации, снимок PrintWindow сохраняется в PNG, процесс выходит.

#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <commctrl.h>
#include <shellapi.h>
#include <tlhelp32.h>
#include <wincodec.h>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cwchar>
#include <map>
#include <string>
#include <vector>

// Версия проекта (файл VERSION) — build.cmd пишет nhl_version.h рядом с объектными файлами.
#if __has_include("nhl_version.h")
#include "nhl_version.h"
#endif
#ifndef NHL_VERSION
#define NHL_VERSION L"dev"
#endif

#pragma comment(lib, "user32.lib")
#pragma comment(lib, "gdi32.lib")
#pragma comment(lib, "comctl32.lib")
#pragma comment(lib, "shell32.lib")
#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "windowscodecs.lib")
#pragma comment(linker, "\"/manifestdependency:type='win32' name='Microsoft.Windows.Common-Controls' " \
                        "version='6.0.0.0' processorArchitecture='*' publicKeyToken='6595b64144ccf1df' language='*'\"")

namespace {

// ─── Файлы настроек ─────────────────────────────────────────────────────────────────────────

using Cvars = std::map<std::string, std::string>;

std::string Trim(const std::string& s) {
  size_t b = 0, e = s.size();
  while (b < e && (s[b] == ' ' || s[b] == '\t' || s[b] == '\r' || s[b] == '\n')) ++b;
  while (e > b && (s[e - 1] == ' ' || s[e - 1] == '\t' || s[e - 1] == '\r' || s[e - 1] == '\n')) --e;
  return s.substr(b, e - b);
}

bool ReadFileBytes(const std::wstring& path, std::string& out) {
  HANDLE f = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                         nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
  if (f == INVALID_HANDLE_VALUE) return false;
  LARGE_INTEGER size{};
  GetFileSizeEx(f, &size);
  if (size.QuadPart > 4 * 1024 * 1024) {
    CloseHandle(f);
    return false;
  }
  out.resize(static_cast<size_t>(size.QuadPart));
  DWORD got = 0;
  BOOL ok = out.empty() || ReadFile(f, out.data(), static_cast<DWORD>(out.size()), &got, nullptr);
  CloseHandle(f);
  if (!ok) return false;
  out.resize(got);
  if (out.size() >= 3 && static_cast<unsigned char>(out[0]) == 0xEF &&
      static_cast<unsigned char>(out[1]) == 0xBB && static_cast<unsigned char>(out[2]) == 0xBF) {
    out.erase(0, 3);
  }
  return true;
}

// Плоский TOML, как читает SDK (core/cvar.cpp): «ключ = значение», [таблица] склеивается через «_».
// Строки в кавычках, числа и true/false — как есть; комментарий после «#» вне кавычек.
void ParseToml(const std::wstring& path, Cvars& out) {
  std::string text;
  if (!ReadFileBytes(path, text)) return;
  std::string section;
  size_t pos = 0;
  while (pos <= text.size()) {
    size_t nl = text.find('\n', pos);
    if (nl == std::string::npos) nl = text.size();
    std::string line = Trim(text.substr(pos, nl - pos));
    pos = nl + 1;
    if (line.empty() || line[0] == '#') continue;
    if (line[0] == '[') {
      size_t close = line.find(']');
      section = close == std::string::npos ? std::string() : Trim(line.substr(1, close - 1));
      continue;
    }
    size_t eq = line.find('=');
    if (eq == std::string::npos) continue;
    std::string key = Trim(line.substr(0, eq));
    std::string rest = Trim(line.substr(eq + 1));
    std::string value;
    if (!rest.empty() && (rest[0] == '"' || rest[0] == '\'')) {
      const char q = rest[0];
      for (size_t i = 1; i < rest.size(); ++i) {
        if (q == '"' && rest[i] == '\\' && i + 1 < rest.size()) {
          value += rest[++i];
        } else if (rest[i] == q) {
          break;
        } else {
          value += rest[i];
        }
      }
    } else {
      size_t hash = rest.find('#');
      value = Trim(hash == std::string::npos ? rest : rest.substr(0, hash));
    }
    if (key.empty()) continue;
    out[section.empty() ? key : section + "_" + key] = value;
  }
}

// ─── Состояние окна и перевод в cvar'ы ─────────────────────────────────────────────────────

struct State {
  int render = 0;  // 0 — D3D12 ROV, 1 — D3D12 RTV, 2 — Vulkan FSI
  int scale = 1;   // resolution_scale 1–3
  int present = 0;  // 0 — bilinear, 1 — cas, 2 — fsr
  int sharp_fsr = 90;  // 0–100 → present_fsr_sharpness_reduction = (100 − x) / 50 стопа
  int sharp_cas = 0;   // 0–100 → present_cas_additional_sharpness = x / 100
  int aniso = 5;       // anisotropic_override: 0, 2, 3, 4, 5
  bool fullscreen = true;
  int window = 0;  // окно без полного экрана: 0 — 1280×720 (умолч.), 1 — 960×540, 2 — 1920×1080, 3 — 2560×1440, 4 — 3840×2160
  bool vsync = false;  // = !d3d12_allow_variable_refresh_rate_and_tearing, !vulkan_allow_present_mode_immediate
  bool mnk = false;
  bool vibration = true;
  int season = 2015;
  bool nhl32 = false, menu32 = false, ahl32 = false, aigm32 = false, fa32 = false, fd32 = true;
  bool draft_age = false;
  bool menu_exit = false, sim_guard = true, sim_guard_live = true;
  bool settings_profile = true;  // nhl_settings_from_profile: настройки главного меню — в новую карьеру
  long long cap = 0, floor = 0, min_salary = 0;  // $
};

struct Kv {
  std::string key, value;
  bool quoted;
  const char* group;  // заголовок блока в файле лаунчера
};

std::string Get(const Cvars& c, const char* key, const char* def) {
  auto it = c.find(key);
  return it == c.end() ? std::string(def) : it->second;
}
bool GetBool(const Cvars& c, const char* key, bool def) {
  auto it = c.find(key);
  if (it == c.end()) return def;
  return it->second == "true" || it->second == "1";
}
long long GetInt(const Cvars& c, const char* key, long long def) {
  auto it = c.find(key);
  if (it == c.end() || it->second.empty()) return def;
  return std::strtoll(it->second.c_str(), nullptr, 10);
}
double GetDouble(const Cvars& c, const char* key, double def) {
  auto it = c.find(key);
  if (it == c.end() || it->second.empty()) return def;
  return std::strtod(it->second.c_str(), nullptr);
}

State FromCvars(const Cvars& c) {
  State s;
  if (Get(c, "gpu_backend", "any") == "vulkan") {
    s.render = 2;
  } else {
    s.render = Get(c, "render_target_path_d3d12", "rov") == "rtv" ? 1 : 0;
  }
  s.scale = static_cast<int>(std::clamp<long long>(GetInt(c, "resolution_scale", 1), 1, 3));
  const std::string pe = Get(c, "present_effect", "bilinear");
  s.present = pe == "cas" ? 1 : (pe == "fsr" || pe == "fsr2" || pe == "fsr3") ? 2 : 0;
  s.sharp_fsr = std::clamp(static_cast<int>(std::lround(100.0 - GetDouble(c, "present_fsr_sharpness_reduction", 0.2) * 50.0)), 0, 100);
  s.sharp_cas = std::clamp(static_cast<int>(std::lround(GetDouble(c, "present_cas_additional_sharpness", 0.0) * 100.0)), 0, 100);
  const long long af = GetInt(c, "anisotropic_override", 3);
  s.aniso = af <= 1 ? (af < 0 ? 3 : 0) : static_cast<int>(std::min<long long>(af, 5));
  s.fullscreen = GetBool(c, "fullscreen", true);
  {
    const long long ww = GetInt(c, "window_width", 0), wh = GetInt(c, "window_height", 0);
    const long long sizes[][2] = {{0, 0}, {960, 540}, {1920, 1080}, {2560, 1440}, {3840, 2160}};
    for (int i = 1; i < 5; ++i)
      if (ww == sizes[i][0] && wh == sizes[i][1]) s.window = i;
  }
  s.vsync = !GetBool(c, "d3d12_allow_variable_refresh_rate_and_tearing", true);
  s.mnk = GetBool(c, "mnk_mode", false);
  s.vibration = GetBool(c, "vibration", true);
  s.season = static_cast<int>(std::clamp<long long>(GetInt(c, "season_year", 2015), 1990, 2050));
  s.nhl32 = GetInt(c, "nhl_teams", 30) == 32;
  s.ahl32 = GetInt(c, "nhl_ahl_teams", 30) == 32;
  s.menu32 = GetBool(c, "nhl_menu32", false);
  s.aigm32 = GetBool(c, "nhl_aigm32", false);
  s.fa32 = GetBool(c, "nhl_fa32", false);
  s.fd32 = GetBool(c, "nhl_fd32", true);
  s.draft_age = GetBool(c, "nhl_draftclass_age", false);
  s.menu_exit = GetBool(c, "nhl_menu_exit", false);
  s.sim_guard = GetBool(c, "nhl_sim_guard", true);
  s.sim_guard_live = GetBool(c, "nhl_sim_guard_live", true);
  s.settings_profile = GetBool(c, "nhl_settings_from_profile", true);
  s.cap = GetInt(c, "nhl_salary_cap", 0);
  s.floor = GetInt(c, "nhl_salary_floor", 0);
  s.min_salary = GetInt(c, "nhl_salary_min", 0);
  return s;
}

std::string Fmt2(double v) {
  char buf[32];
  std::snprintf(buf, sizeof(buf), "%.2f", v);
  return buf;
}

std::vector<Kv> ToCvars(const State& s) {
  const char* kGfx = "Графика";
  const char* kScreen = "Экран";
  const char* kInput = "Управление";
  const char* kLeague = "Сезон и лига";
  const char* kFix = "Исправления";
  auto b = [](bool v) { return std::string(v ? "true" : "false"); };
  std::vector<Kv> kv;
  kv.push_back({"gpu_backend", s.render == 2 ? "vulkan" : "d3d12", true, kGfx});
  kv.push_back({"render_target_path_d3d12", s.render == 1 ? "rtv" : "rov", true, kGfx});
  // RTV рисует матч только с этим флагом (docs/legacy-port.md, «Что работает»).
  kv.push_back({"execute_unclipped_draw_vs_on_cpu", b(s.render == 1), false, kGfx});
  kv.push_back({"render_target_path_vulkan", "fsi", true, kGfx});
  kv.push_back({"resolution_scale", std::to_string(s.scale), false, kGfx});
  kv.push_back({"present_effect", s.present == 2 ? "fsr" : s.present == 1 ? "cas" : "bilinear", true, kGfx});
  kv.push_back({"present_fsr_sharpness_reduction", Fmt2((100 - s.sharp_fsr) / 50.0), false, kGfx});
  kv.push_back({"present_cas_additional_sharpness", Fmt2(s.sharp_cas / 100.0), false, kGfx});
  kv.push_back({"anisotropic_override", std::to_string(s.aniso), false, kGfx});
  kv.push_back({"fullscreen", b(s.fullscreen), false, kScreen});
  {
    // Размер окна (только без полного экрана). SDK делает его и видеорежимом приставки (docs/graphics-settings.md):
    // 0 — умолчание, 1280×720.
    const int sizes[][2] = {{0, 0}, {960, 540}, {1920, 1080}, {2560, 1440}, {3840, 2160}};
    const int w = s.fullscreen ? 0 : std::clamp(s.window, 0, 4);
    kv.push_back({"window_width", std::to_string(sizes[w][0]), false, kScreen});
    kv.push_back({"window_height", std::to_string(sizes[w][1]), false, kScreen});
  }
  kv.push_back({"d3d12_allow_variable_refresh_rate_and_tearing", b(!s.vsync), false, kScreen});
  kv.push_back({"vulkan_allow_present_mode_immediate", b(!s.vsync), false, kScreen});
  kv.push_back({"mnk_mode", b(s.mnk), false, kInput});
  kv.push_back({"vibration", b(s.vibration), false, kInput});
  kv.push_back({"season_year", std::to_string(s.season), false, kLeague});
  kv.push_back({"nhl_teams", s.nhl32 ? "32" : "30", false, kLeague});
  kv.push_back({"nhl_menu32", b(s.menu32), false, kLeague});
  kv.push_back({"nhl_ahl_teams", s.ahl32 ? "32" : "30", false, kLeague});
  kv.push_back({"nhl_aigm32", b(s.aigm32), false, kLeague});
  kv.push_back({"nhl_fa32", b(s.fa32), false, kLeague});
  kv.push_back({"nhl_fd32", b(s.fd32), false, kLeague});
  kv.push_back({"nhl_draftclass_age", b(s.draft_age), false, kLeague});
  kv.push_back({"nhl_salary_cap", std::to_string(s.cap), false, kLeague});
  kv.push_back({"nhl_salary_floor", std::to_string(s.floor), false, kLeague});
  kv.push_back({"nhl_salary_min", std::to_string(s.min_salary), false, kLeague});
  kv.push_back({"nhl_menu_exit", b(s.menu_exit), false, kFix});
  kv.push_back({"nhl_sim_guard", b(s.sim_guard), false, kFix});
  kv.push_back({"nhl_sim_guard_live", b(s.sim_guard_live), false, kFix});
  kv.push_back({"nhl_settings_from_profile", b(s.settings_profile), false, kFix});
  return kv;
}

bool WriteLauncherToml(const std::wstring& path, const std::vector<Kv>& kv) {
  std::string text =
      "# NHL Legacy - настройки лаунчера (nhllegacy_launcher.exe). Файл пишет лаунчер при «Играть».\n"
      "# При запуске игры эти значения передаются ей аргументами --имя=значение и перекрывают\n"
      "# nhllegacy.toml (он не меняется). «Сбросить» в лаунчере = как в nhllegacy.toml.\n";
  const char* group = nullptr;
  for (const Kv& e : kv) {
    if (group == nullptr || std::strcmp(group, e.group) != 0) {
      group = e.group;
      text += "\n# ";
      text += group;
      text += "\n";
    }
    text += e.key + " = " + (e.quoted ? "\"" + e.value + "\"" : e.value) + "\n";
  }
  const std::wstring tmp = path + L".tmp";
  HANDLE f = CreateFileW(tmp.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
  if (f == INVALID_HANDLE_VALUE) return false;
  DWORD put = 0;
  BOOL ok = WriteFile(f, text.data(), static_cast<DWORD>(text.size()), &put, nullptr);
  CloseHandle(f);
  if (!ok || put != text.size()) {
    DeleteFileW(tmp.c_str());
    return false;
  }
  return MoveFileExW(tmp.c_str(), path.c_str(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) != 0;
}

std::wstring Widen(const std::string& s) {
  if (s.empty()) return {};
  int n = MultiByteToWideChar(CP_UTF8, 0, s.data(), static_cast<int>(s.size()), nullptr, 0);
  std::wstring w(n, L'\0');
  MultiByteToWideChar(CP_UTF8, 0, s.data(), static_cast<int>(s.size()), w.data(), n);
  return w;
}

// ─── Подсказки ─────────────────────────────────────────────────────────────────────────────

struct Hint {
  const wchar_t* title;
  const wchar_t* text;
};

enum HintId {
  kHintNone = -1,
  kHintRender,
  kHintScale,
  kHintPresent,
  kHintSharp,
  kHintAniso,
  kHintFullscreen,
  kHintVsync,
  kHintWindow,
  kHintMnk,
  kHintVibration,
  kHintSeason,
  kHintNhl32,
  kHintMenu32,
  kHintAhl32,
  kHintAigm32,
  kHintFa32,
  kHintFd32,
  kHintDraftAge,
  kHintMoney,
  kHintMenuExit,
  kHintSimGuard,
  kHintSimGuardLive,
  kHintSettingsProfile,
  kHintReset,
  kHintPlay,
  kHintCount
};

const Hint kHints[kHintCount] = {
    {L"Рендер",
     L"Как эмулируется видеочип Xbox 360. D3D12 — точный (ROV): проверенный вариант по умолчанию. "
     L"D3D12 — быстрый (RTV): меньше нагрузка на видеокарту. Vulkan — если D3D12 глючит; в первый запуск "
     L"собирает шейдеры, поэтому подтормаживает."},
    {L"Разрешение",
     L"Внутреннее разрешение 3D. ×1 — 1280×720, как на Xbox. ×2 — 2560×1440: заметно чётче, нагрузка на "
     L"видеокарту примерно в 4 раза больше. ×3 — 3840×2160 (4K): примерно в 9 раз больше, для замера; лучше с "
     L"рендером «D3D12 — быстрый (RTV)», на Vulkan экипировка может стать чёрной. Только целые кратные 720p: "
     L"540p или 1080p внутри игра не умеет. На Vulkan ×2 — экспериментально."},
    {L"Вывод кадра",
     L"Как кадр игры растягивается на экран. Обычный — билинейно (мягко). CAS — повышение резкости. "
     L"FSR 1 — апскейл AMD с резкостью: лучше всего при ×1 на мониторе 1080p и выше."},
    {L"Резкость", L"Сила резкости для CAS и FSR 1. Больше — чётче, но на краях могут появиться ореолы."},
    {L"Анизотропия",
     L"Чёткость льда, разметки и бортов под углом камеры. 16x почти ничего не стоит — оставьте."},
    {L"Полный экран",
     L"Окно без рамки на весь экран — меньше задержка. Без галочки — окно размера из строки «Окно», его можно "
     L"растянуть мышью."},
    {L"Без разрывов кадра (V-Sync)",
     L"Кадр выводится по обновлению монитора: без разрывов, но до 1 кадра задержки. С G-SYNC / FreeSync "
     L"не нужен. Скорость игры не меняется — она всегда 60 кадров/с, как на Xbox."},
    {L"Окно",
     L"Размер окна без полного экрана — для замеров. Игра узнаёт его как видеорежим приставки, поэтому 540p "
     L"может и рисовать меньше, а не только сжимать картинку — смотрите загрузку видеокарты. Внутреннее 3D задаёт "
     L"«Разрешение» (×1–×3). Обычное значение — 1280×720."},
    {L"Клавиатура как геймпад",
     L"Играть без геймпада: Enter — Start, Пробел — A, Backspace — B, L — X, P — Y, WASD — стик, "
     L"Shift+стрелки — крестовина, Q/E — LT/RT, 1/3 — LB/RB, Tab — Back."},
    {L"Вибрация", L"Вибрация геймпада."},
    {L"Сезон",
     L"Год текущего сезона: даты, возраст игроков, франшиза. 2015/16 — как на диске. Франшизу загружайте "
     L"с тем же сезоном, с которым она создана."},
    {L"НХЛ на 32 команды",
     L"Сиэтл и Вегас — клубы НХЛ во франшизе (нужна база на 32 команды из набора модов). Франшизу "
     L"загружайте с тем же числом команд, с которым она создана."},
    {L"Сиэтл и Вегас в выборе команды", L"Сиэтл и Вегас в списке команд новой франшизы «Стань GM»."},
    {L"АХЛ на 32",
     L"Фарм-клубы Сиэтла и Вегаса (Коачелла-Вэлли, Хендерсон), дивизионы АХЛ 8/8/8/8. Нужна база «АХЛ на "
     L"32». Только для новой франшизы: созданную на 30 клубов АХЛ загружайте без этой галочки."},
    {L"ИИ-менеджеры Сиэтла и Вегаса",
     L"Сиэтл и Вегас под управлением компьютера ведут межсезонье, как все: продления, обмены, свободные "
     L"агенты."},
    {L"Свободные агенты на 32",
     L"Записи свободных агентов при 32 командах без порчи (иначе сбивается интерес к Анахайму и "
     L"Виннипегу и сортировка списка)."},
    {L"Фэнтези-драфт на 32",
     L"Фэнтези-драфт на 32 команды: правильный порядок выбора, без падения на доске драфта."},
    {L"Класс драфта без переростков",
     L"В первом драфте новой франшизы — только игроки 18–20 лет; остальных игра сгенерирует сама."},
    {L"Финансы новой франшизы",
     L"Потолок зарплат, нижний порог и минимальная зарплата первого сезона, млн $. 0 — как на диске "
     L"(2015/16: 71,4 / 52,8 / 0,575). Дальше растут по правилам игры. На созданную франшизу не влияет."},
    {L"Пункт EXIT в главном меню",
     L"Пункт EXIT главного меню закрывает игру. С модом меню обязателен: без него пункт зависает."},
    {L"Страховка сима матча",
     L"Если в симе матча у команды не хватает игроков на льду, порт добавляет их из состава матча — без "
     L"зависаний и падений. Лучше не выключать."},
    {L"Страховка сима в «Стань профи»",
     L"Сим до следующей смены в «Стань профи» без падения после удаления. Лучше не выключать."},
    {L"Мои настройки — в новую карьеру",
     L"Новая франшиза и «Стань профи» начинаются с правил, слайдеров, звука и видео из главного меню, а не с "
     L"заводских. Уже начатые карьеры хранят свои настройки — их это не меняет."},
    {L"Сбросить", L"Вернуть все настройки как в nhllegacy.toml (как без лаунчера)."},
    {L"Играть",
     L"Сохранить настройки в nhllegacy_launcher.toml и запустить игру. nhllegacy.toml не меняется."},
};

const wchar_t* kDefaultHintTitle = L"Подсказка";
const wchar_t* kDefaultHintText =
    L"Наведите мышь на настройку — здесь появится, что она делает. Все настройки действуют со "
    L"следующего запуска игры.";

// ─── Окно ──────────────────────────────────────────────────────────────────────────────────

enum ControlId {
  kIdRender = 100,
  kIdScale,
  kIdPresent,
  kIdSharp,
  kIdSharpValue,
  kIdAniso,
  kIdFullscreen,
  kIdVsync,
  kIdWindow,
  kIdMnk,
  kIdVibration,
  kIdSeason,
  kIdNhl32,
  kIdMenu32,
  kIdAhl32,
  kIdAigm32,
  kIdFa32,
  kIdFd32,
  kIdDraftAge,
  kIdCap,
  kIdFloor,
  kIdMin,
  kIdMenuExit,
  kIdSimGuard,
  kIdSimGuardLive,
  kIdSettingsProfile,
  kIdReset,
  kIdPlay,
  kIdNote,
};

enum FontKind { kFontNormal, kFontGroup, kFontSmall, kFontCount };

struct Ctl {
  HWND hwnd;
  RECT r;  // в единицах 96 DPI
  FontKind font;
};

struct Zone {
  RECT r;  // в единицах 96 DPI, клиентская область
  int hint;
};

constexpr int kClientW = 880;
constexpr int kClientH = 652;
constexpr int kHeaderH = 64;
constexpr RECT kHintRect = {16, 524, 864, 588};

const COLORREF kColBg = RGB(255, 255, 255);
const COLORREF kColHeader = RGB(14, 27, 46);
const COLORREF kColHeaderText = RGB(255, 255, 255);
const COLORREF kColHeaderSub = RGB(160, 178, 202);
const COLORREF kColAccent = RGB(0, 103, 192);
const COLORREF kColAccentDown = RGB(0, 84, 160);
const COLORREF kColHintBg = RGB(243, 246, 250);
const COLORREF kColHintBorder = RGB(222, 228, 236);
const COLORREF kColGrayText = RGB(110, 110, 110);

struct App {
  HINSTANCE inst = nullptr;
  HWND wnd = nullptr;
  UINT dpi = 96;
  HFONT fonts[kFontCount] = {};
  HFONT font_title = nullptr, font_play = nullptr, font_hint_title = nullptr;
  HBRUSH br_bg = nullptr;
  std::vector<Ctl> ctls;
  std::vector<Zone> zones;
  std::map<HWND, int> hint_of;
  int hint = kHintNone;
  HWND last_focus = nullptr;
  std::wstring dir, exe, toml, launcher_toml, exe_info;
  bool exe_found = false;
  State state;
  bool shot = false;
} g;

int S(int v) { return MulDiv(v, static_cast<int>(g.dpi), 96); }

HWND Item(int id) { return GetDlgItem(g.wnd, id); }

HWND Add(const wchar_t* cls, const wchar_t* text, DWORD style, int x, int y, int w, int h, int id,
         FontKind font = kFontNormal, DWORD ex = 0) {
  HWND hwnd = CreateWindowExW(ex, cls, text, WS_CHILD | WS_VISIBLE | style, S(x), S(y), S(w), S(h), g.wnd,
                              reinterpret_cast<HMENU>(static_cast<INT_PTR>(id)), g.inst, nullptr);
  g.ctls.push_back({hwnd, {x, y, x + w, y + h}, font});
  return hwnd;
}

void AddZone(int x, int y, int w, int h, int hint) { g.zones.push_back({{x, y, x + w, y + h}, hint}); }

HWND Group(const wchar_t* text, int x, int y, int w, int h) {
  return Add(L"BUTTON", text, BS_GROUPBOX, x, y, w, h, -1, kFontGroup);
}

HWND Label(const wchar_t* text, int x, int y, int w, int h = 24) {
  return Add(L"STATIC", text, SS_LEFT | SS_CENTERIMAGE | SS_NOPREFIX, x, y, w, h, -1);
}

HWND Check(const wchar_t* text, int id, int x, int y, int w, int hint) {
  HWND h = Add(L"BUTTON", text, BS_AUTOCHECKBOX | WS_TABSTOP, x, y, w, 24, id);
  g.hint_of[h] = hint;
  AddZone(x, y, w, 24, hint);
  return h;
}

HWND Combo(int id, int x, int y, int w, std::initializer_list<const wchar_t*> items, int hint) {
  HWND h = Add(L"COMBOBOX", L"", CBS_DROPDOWNLIST | WS_VSCROLL | WS_TABSTOP, x, y, w, 320, id);
  for (const wchar_t* it : items) SendMessageW(h, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(it));
  g.hint_of[h] = hint;
  return h;
}

// Строка «подпись: выпадающий список» с общей зоной подсказки.
HWND ComboRow(const wchar_t* label, int id, int x, int y, int label_w, int combo_w,
              std::initializer_list<const wchar_t*> items, int hint) {
  Label(label, x, y, label_w);
  HWND h = Combo(id, x + label_w, y, combo_w, items, hint);
  AddZone(x, y, label_w + combo_w, 26, hint);
  return h;
}

HWND MoneyEdit(const wchar_t* label, int id, int x, int y, int label_w, int edit_w) {
  Label(label, x, y, label_w);
  HWND h = Add(L"EDIT", L"", ES_RIGHT | ES_AUTOHSCROLL | WS_TABSTOP, x + label_w, y, edit_w, 24, id, kFontNormal,
               WS_EX_CLIENTEDGE);
  SendMessageW(h, EM_SETLIMITTEXT, 8, 0);
  g.hint_of[h] = kHintMoney;
  return h;
}

void CreateFonts() {
  for (HFONT& f : g.fonts) {
    if (f) DeleteObject(f);
    f = nullptr;
  }
  for (HFONT* f : {&g.font_title, &g.font_play, &g.font_hint_title}) {
    if (*f) DeleteObject(*f);
    *f = nullptr;
  }
  NONCLIENTMETRICSW ncm{};
  ncm.cbSize = sizeof(ncm);
  SystemParametersInfoForDpi(SPI_GETNONCLIENTMETRICS, sizeof(ncm), &ncm, 0, g.dpi);
  LOGFONTW lf = ncm.lfMessageFont;
  g.fonts[kFontNormal] = CreateFontIndirectW(&lf);
  LOGFONTW bold = lf;
  bold.lfWeight = FW_SEMIBOLD;
  g.fonts[kFontGroup] = CreateFontIndirectW(&bold);
  g.font_hint_title = CreateFontIndirectW(&bold);
  LOGFONTW smallf = lf;
  smallf.lfHeight = MulDiv(lf.lfHeight, 11, 12);
  g.fonts[kFontSmall] = CreateFontIndirectW(&smallf);
  LOGFONTW title = lf;
  title.lfHeight = -S(24);
  title.lfWeight = FW_SEMIBOLD;
  g.font_title = CreateFontIndirectW(&title);
  LOGFONTW play = lf;
  play.lfHeight = -S(15);
  play.lfWeight = FW_SEMIBOLD;
  g.font_play = CreateFontIndirectW(&play);
}

void Layout() {
  for (const Ctl& c : g.ctls) {
    SetWindowPos(c.hwnd, nullptr, S(c.r.left), S(c.r.top), S(c.r.right - c.r.left), S(c.r.bottom - c.r.top),
                 SWP_NOZORDER | SWP_NOACTIVATE);
    SendMessageW(c.hwnd, WM_SETFONT, reinterpret_cast<WPARAM>(g.fonts[c.font]), FALSE);
  }
  InvalidateRect(g.wnd, nullptr, TRUE);
}

void CreateControls() {
  // Левая колонка: графика, экран, управление.
  const int lx = 16, lw = 424, ix = 32, lab = 116, cx = ix + lab, cw = lx + lw - 16 - cx;
  Group(L"Графика", lx, 76, lw, 194);
  ComboRow(L"Рендер", kIdRender, ix, 100, lab, cw,
           {L"D3D12 — точный (ROV)", L"D3D12 — быстрый (RTV)", L"Vulkan"}, kHintRender);
  ComboRow(L"Разрешение", kIdScale, ix, 132, lab, cw, {L"×1 — 1280×720, как на Xbox", L"×2 — 2560×1440", L"×3 — 3840×2160 (4K)"},
           kHintScale);
  ComboRow(L"Вывод кадра", kIdPresent, ix, 164, lab, cw,
           {L"Обычный (билинейный)", L"CAS — резкость", L"FSR 1 — апскейл и резкость"}, kHintPresent);
  Label(L"Резкость", ix, 196, lab, 26);
  HWND tb = Add(TRACKBAR_CLASSW, L"", TBS_HORZ | TBS_NOTICKS | TBS_BOTH | WS_TABSTOP, cx - 6, 197, cw - 44, 26,
                kIdSharp);
  SendMessageW(tb, TBM_SETRANGE, TRUE, MAKELPARAM(0, 100));
  SendMessageW(tb, TBM_SETPAGESIZE, 0, 10);
  g.hint_of[tb] = kHintSharp;
  Add(L"STATIC", L"", SS_RIGHT | SS_CENTERIMAGE, cx + cw - 50, 197, 50, 24, kIdSharpValue);
  AddZone(ix, 196, lab + cw, 28, kHintSharp);
  ComboRow(L"Анизотропия", kIdAniso, ix, 228, lab, cw, {L"Выкл.", L"2x", L"4x", L"8x", L"16x"}, kHintAniso);

  Group(L"Экран", lx, 282, lw, 106);
  Check(L"Полный экран", kIdFullscreen, ix, 304, lw - 32, kHintFullscreen);
  Check(L"Без разрывов кадра (V-Sync)", kIdVsync, ix, 330, lw - 32, kHintVsync);
  ComboRow(L"Окно", kIdWindow, ix, 356, lab, cw,
           {L"1280×720 — обычное", L"960×540", L"1920×1080", L"2560×1440", L"3840×2160 (4K)"}, kHintWindow);

  Group(L"Управление", lx, 400, lw, 118);
  Check(L"Клавиатура как геймпад", kIdMnk, ix, 424, lw - 32, kHintMnk);
  Check(L"Вибрация геймпада", kIdVibration, ix, 450, lw - 32, kHintVibration);

  // Правая колонка: наши изменения.
  const int rx = 456, rw = 408, jx = rx + 16, sub = jx + 20, rcw = rw - 32;
  Group(L"Сезон и лига", rx, 76, rw, 312);
  ComboRow(L"Сезон", kIdSeason, jx, 100, 64, 190, {}, kHintSeason);
  {
    HWND season = Item(kIdSeason);
    for (int y = 2015; y <= 2030; ++y) {
      wchar_t buf[48];
      if (y == 2015) {
        std::swprintf(buf, 48, L"%d/%02d — как на диске", y, (y + 1) % 100);
      } else {
        std::swprintf(buf, 48, L"%d/%02d", y, (y + 1) % 100);
      }
      int i = static_cast<int>(SendMessageW(season, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(buf)));
      SendMessageW(season, CB_SETITEMDATA, i, y);
    }
  }
  Check(L"НХЛ на 32 команды: Сиэтл и Вегас", kIdNhl32, jx, 134, rcw, kHintNhl32);
  Check(L"Сиэтл и Вегас в выборе команды «Стань GM»", kIdMenu32, sub, 160, rcw - 20, kHintMenu32);
  Check(L"АХЛ на 32: Коачелла-Вэлли и Хендерсон", kIdAhl32, sub, 186, rcw - 20, kHintAhl32);
  Check(L"ИИ-менеджеры Сиэтла и Вегаса", kIdAigm32, sub, 212, rcw - 20, kHintAigm32);
  Check(L"Свободные агенты на 32 команды", kIdFa32, sub, 238, rcw - 20, kHintFa32);
  Check(L"Фэнтези-драфт на 32 команды", kIdFd32, sub, 264, rcw - 20, kHintFd32);
  Check(L"Класс драфта без переростков (18–20 лет)", kIdDraftAge, jx, 292, rcw, kHintDraftAge);
  Label(L"Финансы новой франшизы, млн $ (0 — как на диске):", jx, 322, rcw, 22);
  MoneyEdit(L"Потолок", kIdCap, jx, 348, 58, 58);
  MoneyEdit(L"Порог", kIdFloor, jx + 128, 348, 46, 58);
  MoneyEdit(L"Минимум", kIdMin, jx + 244, 348, 64, 58);
  AddZone(jx, 322, rcw, 52, kHintMoney);

  Group(L"Исправления", rx, 400, rw, 118);
  Check(L"Пункт EXIT в главном меню", kIdMenuExit, jx, 420, rcw, kHintMenuExit);
  Check(L"Страховка сима матча (неполная пятёрка)", kIdSimGuard, jx, 442, rcw, kHintSimGuard);
  Check(L"Страховка сима в «Стань профи»", kIdSimGuardLive, jx, 464, rcw, kHintSimGuardLive);
  Check(L"Мои настройки — в новую карьеру", kIdSettingsProfile, jx, 486, rcw, kHintSettingsProfile);

  // Кнопки.
  HWND reset = Add(L"BUTTON", L"Сбросить", BS_PUSHBUTTON | WS_TABSTOP, 16, 602, 120, 34, kIdReset);
  g.hint_of[reset] = kHintReset;
  AddZone(16, 602, 120, 34, kHintReset);
  HWND play = Add(L"BUTTON", L"Играть", BS_OWNERDRAW | WS_TABSTOP, 704, 602, 160, 34, kIdPlay);
  g.hint_of[play] = kHintPlay;
  AddZone(704, 602, 160, 34, kHintPlay);
  EnableWindow(play, g.exe_found);
}

// ─── Состояние ⇄ элементы ──────────────────────────────────────────────────────────────────

void SetCheck(int id, bool v) { SendMessageW(Item(id), BM_SETCHECK, v ? BST_CHECKED : BST_UNCHECKED, 0); }
bool GetCheck(int id) { return SendMessageW(Item(id), BM_GETCHECK, 0, 0) == BST_CHECKED; }
int ComboSel(int id) { return static_cast<int>(SendMessageW(Item(id), CB_GETCURSEL, 0, 0)); }
void SetComboSel(int id, int i) { SendMessageW(Item(id), CB_SETCURSEL, i, 0); }

std::wstring MoneyText(long long dollars) {
  if (dollars == 0) return L"0";
  wchar_t buf[32];
  std::swprintf(buf, 32, L"%.3f", dollars / 1e6);
  std::wstring s = buf;
  while (!s.empty() && s.back() == L'0') s.pop_back();
  if (!s.empty() && s.back() == L'.') s.pop_back();
  for (wchar_t& ch : s) {
    if (ch == L'.') ch = L',';
  }
  return s;
}

bool ParseMoney(int id, double max_millions, long long& out) {
  wchar_t buf[32] = {};
  GetWindowTextW(Item(id), buf, 32);
  std::wstring s = buf;
  for (wchar_t& ch : s) {
    if (ch == L',') ch = L'.';
  }
  s.erase(std::remove(s.begin(), s.end(), L' '), s.end());
  if (s.empty()) {
    out = 0;
    return true;
  }
  wchar_t* end = nullptr;
  double v = std::wcstod(s.c_str(), &end);
  if (end == s.c_str() || *end != L'\0' || !(v >= 0.0) || v > max_millions) return false;
  out = std::llround(v * 1e6);
  return true;
}

int SharpOf(const State& s) { return s.present == 1 ? s.sharp_cas : s.sharp_fsr; }

void UpdateSharpLabel() {
  int v = static_cast<int>(SendMessageW(Item(kIdSharp), TBM_GETPOS, 0, 0));
  wchar_t buf[16];
  std::swprintf(buf, 16, L"%d %%", v);
  SetWindowTextW(Item(kIdSharpValue), buf);
}

void UpdateEnabled() {
  const bool nhl32 = GetCheck(kIdNhl32);
  for (int id : {kIdMenu32, kIdAhl32, kIdAigm32, kIdFa32, kIdFd32}) EnableWindow(Item(id), nhl32);
  EnableWindow(Item(kIdWindow), !GetCheck(kIdFullscreen));
  const bool sharp = ComboSel(kIdPresent) != 0;
  EnableWindow(Item(kIdSharp), sharp);
  EnableWindow(Item(kIdSharpValue), sharp);
}

void ToUi(const State& s) {
  SetComboSel(kIdRender, s.render);
  SetComboSel(kIdScale, s.scale - 1);
  SetComboSel(kIdPresent, s.present);
  SendMessageW(Item(kIdSharp), TBM_SETPOS, TRUE, SharpOf(s));
  UpdateSharpLabel();
  const int aniso_index[] = {0, 0, 1, 2, 3, 4};  // 0→Выкл., 2→2x, 3→4x, 4→8x, 5→16x
  SetComboSel(kIdAniso, aniso_index[std::clamp(s.aniso, 0, 5)]);
  SetCheck(kIdFullscreen, s.fullscreen);
  SetComboSel(kIdWindow, s.window);
  SetCheck(kIdVsync, s.vsync);
  SetCheck(kIdMnk, s.mnk);
  SetCheck(kIdVibration, s.vibration);
  HWND season = Item(kIdSeason);
  int count = static_cast<int>(SendMessageW(season, CB_GETCOUNT, 0, 0));
  int sel = -1;
  for (int i = 0; i < count; ++i) {
    if (static_cast<int>(SendMessageW(season, CB_GETITEMDATA, i, 0)) == s.season) sel = i;
  }
  if (sel < 0) {  // год вне списка (1990–2050 из nhllegacy.toml) — добавить строкой в конец
    wchar_t buf[32];
    std::swprintf(buf, 32, L"%d/%02d", s.season, (s.season + 1) % 100);
    sel = static_cast<int>(SendMessageW(season, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(buf)));
    SendMessageW(season, CB_SETITEMDATA, sel, s.season);
  }
  SetComboSel(kIdSeason, sel);
  SetCheck(kIdNhl32, s.nhl32);
  SetCheck(kIdMenu32, s.menu32);
  SetCheck(kIdAhl32, s.ahl32);
  SetCheck(kIdAigm32, s.aigm32);
  SetCheck(kIdFa32, s.fa32);
  SetCheck(kIdFd32, s.fd32);
  SetCheck(kIdDraftAge, s.draft_age);
  SetWindowTextW(Item(kIdCap), MoneyText(s.cap).c_str());
  SetWindowTextW(Item(kIdFloor), MoneyText(s.floor).c_str());
  SetWindowTextW(Item(kIdMin), MoneyText(s.min_salary).c_str());
  SetCheck(kIdMenuExit, s.menu_exit);
  SetCheck(kIdSimGuard, s.sim_guard);
  SetCheck(kIdSimGuardLive, s.sim_guard_live);
  SetCheck(kIdSettingsProfile, s.settings_profile);
  UpdateEnabled();
}

// Читает элементы в g.state; false — неверное число в финансах (фокус на нём).
bool FromUi() {
  State& s = g.state;
  s.render = std::max(0, ComboSel(kIdRender));
  s.scale = std::max(0, ComboSel(kIdScale)) + 1;
  s.present = std::max(0, ComboSel(kIdPresent));
  const int sharp = static_cast<int>(SendMessageW(Item(kIdSharp), TBM_GETPOS, 0, 0));
  if (s.present == 1) s.sharp_cas = sharp;
  if (s.present == 2) s.sharp_fsr = sharp;
  const int aniso_value[] = {0, 2, 3, 4, 5};
  s.aniso = aniso_value[std::clamp(ComboSel(kIdAniso), 0, 4)];
  s.fullscreen = GetCheck(kIdFullscreen);
  s.window = std::max(0, ComboSel(kIdWindow));
  s.vsync = GetCheck(kIdVsync);
  s.mnk = GetCheck(kIdMnk);
  s.vibration = GetCheck(kIdVibration);
  int sel = ComboSel(kIdSeason);
  if (sel >= 0) s.season = static_cast<int>(SendMessageW(Item(kIdSeason), CB_GETITEMDATA, sel, 0));
  s.nhl32 = GetCheck(kIdNhl32);
  s.menu32 = GetCheck(kIdMenu32);
  s.ahl32 = GetCheck(kIdAhl32);
  s.aigm32 = GetCheck(kIdAigm32);
  s.fa32 = GetCheck(kIdFa32);
  s.fd32 = GetCheck(kIdFd32);
  s.draft_age = GetCheck(kIdDraftAge);
  s.menu_exit = GetCheck(kIdMenuExit);
  s.sim_guard = GetCheck(kIdSimGuard);
  s.sim_guard_live = GetCheck(kIdSimGuardLive);
  s.settings_profile = GetCheck(kIdSettingsProfile);
  struct {
    int id;
    double max;
    long long* out;
  } money[] = {{kIdCap, 200.0, &s.cap}, {kIdFloor, 200.0, &s.floor}, {kIdMin, 10.0, &s.min_salary}};
  for (auto& m : money) {
    if (!ParseMoney(m.id, m.max, *m.out)) {
      SetFocus(Item(m.id));
      SendMessageW(Item(m.id), EM_SETSEL, 0, -1);
      return false;
    }
  }
  return true;
}

State BaseState() {
  Cvars c;
  ParseToml(g.toml, c);
  return FromCvars(c);
}

void LoadState() {
  Cvars c;
  ParseToml(g.toml, c);
  ParseToml(g.launcher_toml, c);  // свой файл поверх nhllegacy.toml
  g.state = FromCvars(c);
}

// ─── Запуск ───────────────────────────────────────────────────────────────────────────────

bool GameRunning() {
  HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
  if (snap == INVALID_HANDLE_VALUE) return false;
  PROCESSENTRY32W pe{};
  pe.dwSize = sizeof(pe);
  bool found = false;
  for (BOOL ok = Process32FirstW(snap, &pe); ok; ok = Process32NextW(snap, &pe)) {
    if (_wcsicmp(pe.szExeFile, L"nhllegacy.exe") == 0) {
      found = true;
      break;
    }
  }
  CloseHandle(snap);
  return found;
}

void ShowError(const wchar_t* text) { MessageBoxW(g.wnd, text, L"NHL Legacy", MB_OK | MB_ICONWARNING); }

bool SaveState() {
  if (!FromUi()) {
    ShowError(L"Финансы: введите число в миллионах долларов, например 104 или 76,9 (0 — как на диске).");
    return false;
  }
  if (!WriteLauncherToml(g.launcher_toml, ToCvars(g.state))) {
    ShowError(L"Не удалось записать nhllegacy_launcher.toml рядом с лаунчером.");
    return false;
  }
  return true;
}

void Play() {
  if (!g.exe_found) return;
  if (GameRunning()) {
    ShowError(L"Игра уже запущена. Закройте её и нажмите «Играть» ещё раз.");
    return;
  }
  if (!SaveState()) return;
  std::wstring cmd = L"\"" + g.exe + L"\"";
  for (const Kv& e : ToCvars(g.state)) cmd += L" --" + Widen(e.key) + L"=" + Widen(e.value);
  STARTUPINFOW si{};
  si.cb = sizeof(si);
  PROCESS_INFORMATION pi{};
  std::vector<wchar_t> buf(cmd.begin(), cmd.end());
  buf.push_back(L'\0');
  if (!CreateProcessW(g.exe.c_str(), buf.data(), nullptr, nullptr, FALSE, 0, nullptr, g.dir.c_str(), &si, &pi)) {
    ShowError(L"Не удалось запустить nhllegacy.exe.");
    return;
  }
  CloseHandle(pi.hThread);
  CloseHandle(pi.hProcess);
  DestroyWindow(g.wnd);
}

// ─── Рисование ────────────────────────────────────────────────────────────────────────────

RECT Scaled(const RECT& r) { return {S(r.left), S(r.top), S(r.right), S(r.bottom)}; }

void SetHint(int hint) {
  if (hint == g.hint) return;
  g.hint = hint;
  RECT r = Scaled(kHintRect);
  InvalidateRect(g.wnd, &r, FALSE);
}

void FillSolid(HDC dc, const RECT& r, COLORREF c) {
  SetDCBrushColor(dc, c);
  FillRect(dc, &r, static_cast<HBRUSH>(GetStockObject(DC_BRUSH)));
}

void Paint(HDC dc) {
  RECT client;
  GetClientRect(g.wnd, &client);
  // Шапка.
  RECT head = {0, 0, client.right, S(kHeaderH)};
  FillSolid(dc, head, kColHeader);
  RECT stripe = {0, S(kHeaderH) - S(3), client.right, S(kHeaderH)};
  FillSolid(dc, stripe, kColAccent);
  SetBkMode(dc, TRANSPARENT);
  HGDIOBJ old = SelectObject(dc, g.font_title);
  SetTextColor(dc, kColHeaderText);
  RECT t = {S(20), S(8), client.right - S(20), S(40)};
  DrawTextW(dc, L"NHL Legacy Remaster  v" NHL_VERSION, -1, &t, DT_LEFT | DT_SINGLELINE | DT_NOPREFIX);
  SelectObject(dc, g.fonts[kFontNormal]);
  SetTextColor(dc, kColHeaderSub);
  RECT st = {S(20), S(38), client.right - S(20), S(58)};
  DrawTextW(dc, L"Настройки перед запуском", -1, &st, DT_LEFT | DT_SINGLELINE | DT_NOPREFIX);
  RECT info = {S(300), S(38), client.right - S(20), S(58)};
  DrawTextW(dc, g.exe_info.c_str(), -1, &info, DT_RIGHT | DT_SINGLELINE | DT_NOPREFIX);

  // Подсказка.
  RECT hr = Scaled(kHintRect);
  FillSolid(dc, hr, kColHintBorder);
  RECT inner = {hr.left + 1, hr.top + 1, hr.right - 1, hr.bottom - 1};
  FillSolid(dc, inner, kColHintBg);
  RECT bar = {hr.left + 1, hr.top + 1, hr.left + S(4), hr.bottom - 1};
  FillSolid(dc, bar, kColAccent);
  const wchar_t* title = g.hint >= 0 ? kHints[g.hint].title : kDefaultHintTitle;
  const wchar_t* text = g.hint >= 0 ? kHints[g.hint].text : kDefaultHintText;
  SelectObject(dc, g.font_hint_title);
  SetTextColor(dc, RGB(30, 30, 30));
  RECT tr = {hr.left + S(16), hr.top + S(7), hr.right - S(12), hr.top + S(26)};
  DrawTextW(dc, title, -1, &tr, DT_LEFT | DT_SINGLELINE | DT_NOPREFIX | DT_END_ELLIPSIS);
  SelectObject(dc, g.fonts[kFontNormal]);
  SetTextColor(dc, RGB(60, 60, 60));
  RECT xr = {hr.left + S(16), hr.top + S(26), hr.right - S(12), hr.bottom - S(4)};
  DrawTextW(dc, text, -1, &xr, DT_LEFT | DT_WORDBREAK | DT_NOPREFIX | DT_END_ELLIPSIS);

  // Строка о файлах между кнопками.
  SelectObject(dc, g.fonts[kFontSmall]);
  SetTextColor(dc, kColGrayText);
  RECT fr = {S(150), S(602), S(690), S(636)};
  DrawTextW(dc, L"Сохраняется в nhllegacy_launcher.toml · nhllegacy.toml не меняется", -1, &fr,
            DT_CENTER | DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX);
  SelectObject(dc, old);
}

void DrawPlay(const DRAWITEMSTRUCT* di) {
  HDC dc = di->hDC;
  RECT r = di->rcItem;
  const bool disabled = (di->itemState & ODS_DISABLED) != 0;
  const bool down = (di->itemState & ODS_SELECTED) != 0;
  FillSolid(dc, r, kColBg);
  COLORREF fill = disabled ? RGB(200, 200, 200) : down ? kColAccentDown : kColAccent;
  HBRUSH br = CreateSolidBrush(fill);
  HPEN pen = CreatePen(PS_SOLID, 1, fill);
  HGDIOBJ ob = SelectObject(dc, br);
  HGDIOBJ op = SelectObject(dc, pen);
  RoundRect(dc, r.left, r.top, r.right, r.bottom, S(8), S(8));
  SelectObject(dc, ob);
  SelectObject(dc, op);
  DeleteObject(br);
  DeleteObject(pen);
  SetBkMode(dc, TRANSPARENT);
  SetTextColor(dc, RGB(255, 255, 255));
  HGDIOBJ of = SelectObject(dc, g.font_play);
  DrawTextW(dc, L"▶  Играть", -1, &r, DT_CENTER | DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX);
  SelectObject(dc, of);
  if ((di->itemState & ODS_FOCUS) && !(di->itemState & ODS_NOFOCUSRECT)) {
    RECT f = r;
    InflateRect(&f, -S(3), -S(3));
    DrawFocusRect(dc, &f);
  }
}

// ─── Оконная процедура ────────────────────────────────────────────────────────────────────

void UpdateHintFromCursor() {
  POINT pt;
  GetCursorPos(&pt);
  ScreenToClient(g.wnd, &pt);
  RECT client;
  GetClientRect(g.wnd, &client);
  if (!PtInRect(&client, pt)) return;
  for (const Zone& z : g.zones) {
    RECT r = Scaled(z.r);
    if (PtInRect(&r, pt)) {
      SetHint(z.hint);
      return;
    }
  }
}

LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
  switch (msg) {
    case WM_CREATE:
      g.wnd = hwnd;
      g.dpi = GetDpiForWindow(hwnd);
      CreateFonts();
      CreateControls();
      Layout();
      ToUi(g.state);
      return 0;
    case WM_DPICHANGED: {
      g.dpi = HIWORD(wp);
      CreateFonts();
      Layout();
      const RECT* r = reinterpret_cast<const RECT*>(lp);
      SetWindowPos(hwnd, nullptr, r->left, r->top, r->right - r->left, r->bottom - r->top,
                   SWP_NOZORDER | SWP_NOACTIVATE);
      return 0;
    }
    case WM_ERASEBKGND: {
      RECT r;
      GetClientRect(hwnd, &r);
      FillSolid(reinterpret_cast<HDC>(wp), r, kColBg);
      return 1;
    }
    case WM_PAINT: {
      PAINTSTRUCT ps;
      HDC dc = BeginPaint(hwnd, &ps);
      Paint(dc);
      EndPaint(hwnd, &ps);
      return 0;
    }
    case WM_CTLCOLORSTATIC:
    case WM_CTLCOLORBTN: {
      HDC dc = reinterpret_cast<HDC>(wp);
      HWND ctl = reinterpret_cast<HWND>(lp);
      SetBkColor(dc, kColBg);
      if (GetDlgCtrlID(ctl) == kIdNote) SetTextColor(dc, kColGrayText);
      return reinterpret_cast<LRESULT>(g.br_bg);
    }
    case WM_DRAWITEM: {
      const DRAWITEMSTRUCT* di = reinterpret_cast<const DRAWITEMSTRUCT*>(lp);
      if (di->CtlID == kIdPlay) {
        DrawPlay(di);
        return TRUE;
      }
      break;
    }
    case WM_MOUSEMOVE:
      UpdateHintFromCursor();
      return 0;
    case WM_HSCROLL:
      if (reinterpret_cast<HWND>(lp) == Item(kIdSharp)) {
        UpdateSharpLabel();
        SetHint(kHintSharp);
      }
      return 0;
    case WM_COMMAND: {
      const int id = LOWORD(wp);
      const int code = HIWORD(wp);
      if ((id == kIdNhl32 || id == kIdFullscreen) && code == BN_CLICKED) UpdateEnabled();
      if (id == kIdPresent && code == CBN_SELCHANGE) {
        // У CAS и FSR своя резкость: запомнить ползунок старого режима, показать нового.
        const int sharp = static_cast<int>(SendMessageW(Item(kIdSharp), TBM_GETPOS, 0, 0));
        if (g.state.present == 1) g.state.sharp_cas = sharp;
        if (g.state.present == 2) g.state.sharp_fsr = sharp;
        g.state.present = ComboSel(kIdPresent);
        SendMessageW(Item(kIdSharp), TBM_SETPOS, TRUE, SharpOf(g.state));
        UpdateSharpLabel();
        UpdateEnabled();
      }
      if (id == kIdReset && code == BN_CLICKED) {
        g.state = BaseState();
        ToUi(g.state);
      }
      if ((id == kIdPlay && code == BN_CLICKED) || id == IDOK) Play();
      if (id == IDCANCEL) PostMessageW(hwnd, WM_CLOSE, 0, 0);
      return 0;
    }
    case WM_CLOSE:
      if (!g.shot) {
        // Закрытие крестиком тоже сохраняет выбранное (неверные финансы — молча не сохранять).
        if (FromUi()) WriteLauncherToml(g.launcher_toml, ToCvars(g.state));
      }
      DestroyWindow(hwnd);
      return 0;
    case WM_DESTROY:
      PostQuitMessage(0);
      return 0;
  }
  return DefWindowProcW(hwnd, msg, wp, lp);
}

// ─── Снимок окна для макета (--shot) ──────────────────────────────────────────────────────

bool SavePng(HBITMAP bmp, const std::wstring& path) {
  IWICImagingFactory* factory = nullptr;
  if (FAILED(CoCreateInstance(CLSID_WICImagingFactory, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&factory)))) {
    return false;
  }
  bool ok = false;
  IWICBitmap* wb = nullptr;
  IWICStream* stream = nullptr;
  IWICBitmapEncoder* enc = nullptr;
  IWICBitmapFrameEncode* frame = nullptr;
  IPropertyBag2* props = nullptr;
  UINT w = 0, h = 0;
  WICPixelFormatGUID fmt = GUID_WICPixelFormat24bppBGR;
  if (SUCCEEDED(factory->CreateBitmapFromHBITMAP(bmp, nullptr, WICBitmapIgnoreAlpha, &wb)) &&
      SUCCEEDED(factory->CreateStream(&stream)) &&
      SUCCEEDED(stream->InitializeFromFilename(path.c_str(), GENERIC_WRITE)) &&
      SUCCEEDED(factory->CreateEncoder(GUID_ContainerFormatPng, nullptr, &enc)) &&
      SUCCEEDED(enc->Initialize(stream, WICBitmapEncoderNoCache)) &&
      SUCCEEDED(enc->CreateNewFrame(&frame, &props)) && SUCCEEDED(frame->Initialize(props)) &&
      SUCCEEDED(wb->GetSize(&w, &h)) && SUCCEEDED(frame->SetSize(w, h)) &&
      SUCCEEDED(frame->SetPixelFormat(&fmt)) && SUCCEEDED(frame->WriteSource(wb, nullptr)) &&
      SUCCEEDED(frame->Commit()) && SUCCEEDED(enc->Commit())) {
    ok = true;
  }
  if (props) props->Release();
  if (frame) frame->Release();
  if (enc) enc->Release();
  if (stream) stream->Release();
  if (wb) wb->Release();
  factory->Release();
  return ok;
}

int Shot(const std::wstring& path) {
  RECT wr;
  GetWindowRect(g.wnd, &wr);
  const int w = wr.right - wr.left, h = wr.bottom - wr.top;
  HDC screen = GetDC(nullptr);
  HDC mem = CreateCompatibleDC(screen);
  HBITMAP bmp = CreateCompatibleBitmap(screen, w, h);
  HGDIOBJ old = SelectObject(mem, bmp);
  PrintWindow(g.wnd, mem, PW_RENDERFULLCONTENT);
  SelectObject(mem, old);
  const bool ok = SavePng(bmp, path);
  DeleteObject(bmp);
  DeleteDC(mem);
  ReleaseDC(nullptr, screen);
  return ok ? 0 : 1;
}

void PumpFor(DWORD ms) {
  const DWORD end = GetTickCount() + ms;
  MSG msg;
  while (GetTickCount() < end) {
    while (PeekMessageW(&msg, nullptr, 0, 0, PM_REMOVE)) {
      TranslateMessage(&msg);
      DispatchMessageW(&msg);
    }
    Sleep(10);
  }
}

}  // namespace

int WINAPI wWinMain(HINSTANCE inst, HINSTANCE, PWSTR, int show) {
  SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
  CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
  INITCOMMONCONTROLSEX icc{sizeof(icc), ICC_STANDARD_CLASSES | ICC_BAR_CLASSES};
  InitCommonControlsEx(&icc);
  g.inst = inst;

  std::wstring shot_path;
  int shot_hint = kHintNone;
  int argc = 0;
  LPWSTR* argv = CommandLineToArgvW(GetCommandLineW(), &argc);
  for (int i = 1; argv && i < argc; ++i) {
    std::wstring a = argv[i];
    if (a.rfind(L"--shot=", 0) == 0) shot_path = a.substr(7);
    if (a.rfind(L"--shot-hint=", 0) == 0) shot_hint = _wtoi(a.c_str() + 12);
  }
  if (argv) LocalFree(argv);
  g.shot = !shot_path.empty();

  wchar_t module[MAX_PATH * 4];
  GetModuleFileNameW(nullptr, module, static_cast<DWORD>(std::size(module)));
  g.dir = module;
  g.dir.erase(g.dir.find_last_of(L"\\/"));
  g.exe = g.dir + L"\\nhllegacy.exe";
  g.toml = g.dir + L"\\nhllegacy.toml";
  g.launcher_toml = g.dir + L"\\nhllegacy_launcher.toml";
  WIN32_FILE_ATTRIBUTE_DATA fa{};
  g.exe_found = GetFileAttributesExW(g.exe.c_str(), GetFileExInfoStandard, &fa) != 0;
  if (g.exe_found) {
    FILETIME local;
    SYSTEMTIME st;
    FileTimeToLocalFileTime(&fa.ftLastWriteTime, &local);
    FileTimeToSystemTime(&local, &st);
    wchar_t buf[96];
    std::swprintf(buf, 96, L"nhllegacy.exe от %02u.%02u.%04u %02u:%02u", st.wDay, st.wMonth, st.wYear, st.wHour,
                  st.wMinute);
    g.exe_info = buf;
  } else {
    g.exe_info = L"nhllegacy.exe не найден — положите лаунчер рядом с ним";
  }
  LoadState();

  g.br_bg = CreateSolidBrush(kColBg);
  WNDCLASSEXW wc{sizeof(wc)};
  wc.lpfnWndProc = WndProc;
  wc.hInstance = inst;
  wc.hCursor = LoadCursorW(nullptr, IDC_ARROW);
  wc.hbrBackground = g.br_bg;
  wc.lpszClassName = L"NhlLegacyLauncher";
  // Иконка из ресурсов exe (id 1, tools/make_icon.py → launcher/icon/nhllegacy.ico, build.cmd); нет — стандартная.
  wc.hIcon = LoadIconW(inst, MAKEINTRESOURCEW(1));
  if (!wc.hIcon) wc.hIcon = LoadIconW(nullptr, IDI_APPLICATION);
  wc.hIconSm = static_cast<HICON>(LoadImageW(inst, MAKEINTRESOURCEW(1), IMAGE_ICON, GetSystemMetrics(SM_CXSMICON),
                                             GetSystemMetrics(SM_CYSMICON), LR_DEFAULTCOLOR));
  RegisterClassExW(&wc);

  const DWORD style = WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX | WS_CLIPCHILDREN;
  // Размер по DPI основного монитора; WM_DPICHANGED поправит, если окно окажется на другом.
  POINT origin = {0, 0};
  HMONITOR mon = MonitorFromPoint(origin, MONITOR_DEFAULTTOPRIMARY);
  UINT dpi_x = 96, dpi_y = 96;
  using GetDpiForMonitorFn = HRESULT(WINAPI*)(HMONITOR, int, UINT*, UINT*);
  if (HMODULE shcore = LoadLibraryW(L"shcore.dll")) {
    if (auto fn = reinterpret_cast<GetDpiForMonitorFn>(GetProcAddress(shcore, "GetDpiForMonitor"))) {
      fn(mon, 0, &dpi_x, &dpi_y);
    }
  }
  g.dpi = dpi_x;
  RECT wr = {0, 0, S(kClientW), S(kClientH)};
  AdjustWindowRectExForDpi(&wr, style, FALSE, 0, g.dpi);
  const int w = wr.right - wr.left, h = wr.bottom - wr.top;
  MONITORINFO mi{sizeof(mi)};
  GetMonitorInfoW(mon, &mi);
  int x = mi.rcWork.left + (mi.rcWork.right - mi.rcWork.left - w) / 2;
  int y = mi.rcWork.top + (mi.rcWork.bottom - mi.rcWork.top - h) / 2;
  if (g.shot) {  // за пределами экрана, без активации — окно пользователя не теряет фокус
    x = GetSystemMetrics(SM_XVIRTUALSCREEN) - w - 200;
    y = GetSystemMetrics(SM_YVIRTUALSCREEN);
  }
  HWND hwnd = CreateWindowExW(g.shot ? WS_EX_NOACTIVATE : 0, wc.lpszClassName, L"NHL Legacy Remaster v" NHL_VERSION L" — запуск", style, x, y,
                              w, h, nullptr, nullptr, inst, nullptr);
  if (!hwnd) return 1;

  if (g.shot) {
    if (shot_hint >= 0 && shot_hint < kHintCount) g.hint = shot_hint;
    ShowWindow(hwnd, SW_SHOWNOACTIVATE);
    UpdateWindow(hwnd);
    PumpFor(400);
    const int rc = Shot(shot_path);
    DestroyWindow(hwnd);
    PumpFor(50);
    return rc;
  }

  ShowWindow(hwnd, show);
  UpdateWindow(hwnd);
  MSG msg;
  while (GetMessageW(&msg, nullptr, 0, 0) > 0) {
    if (msg.message == WM_MOUSEMOVE && (msg.hwnd == g.wnd || IsChild(g.wnd, msg.hwnd))) UpdateHintFromCursor();
    if (IsDialogMessageW(g.wnd, &msg)) {
      HWND focus = GetFocus();
      if (focus != g.last_focus) {
        g.last_focus = focus;
        auto it = g.hint_of.find(focus);
        if (it != g.hint_of.end()) SetHint(it->second);
      }
      continue;
    }
    TranslateMessage(&msg);
    DispatchMessageW(&msg);
  }
  CoUninitialize();
  return 0;
}
