// Папка saves рядом с exe: всё личное отдельно от версии игры (nhl_saves_root; docs/legacy-port.md, «Папка saves»).
//
// Пользователь (05.11.2026): новую версию копирует поверх старой или рядом, сейвы при этом не трогаются; обновление
// частями — перетащить нужные папки, кроме saves. Раскладка одобрена им 05.11 (game/work/status/layout-proposal.md):
//   saves\profiles, rosters, franchises, be-a-pro, seasons, playoffs, tournaments, hockey-cards, … — по префиксу имени
//   сейва игры (PROFILE 20261105030242 → profiles); пакет сейва — saves\<папка>\<имя>\, заголовок — <имя>.header рядом;
//   saves\achievements, saves\xbox-profile, saves\settings (выбор в лаунчере), saves\highlights.
// Пути сейвов строит ContentManager в rexruntime.dll: раскладку делает патч SDK 0007 (cvar saved_game_root и
// saved_game_folders, scripts/sdk-patches/0007-saved-game-layout.patch), здесь их только ставим.
//
// Перенос со старого места (userdata\<xuid>\454109EC\00000001, заголовки — …\Headers\00000001) при каждом запуске:
// копируются сейвы, которых нет в saves ни в одной папке и которые ещё не переносились (список —
// saves\migrated-from-userdata.txt: удалённый в игре сейв не вернётся). Старые копии остаются на месте. Так же
// подхватывается папка userdata\B13EBABEBABEBABE от старой версии, положенная в новую.
// Стартовые сейвы релиза (start-saves\<папка>\…, make_dist.sh): копируются, только если в saves нет ни одного сейва
// этого вида (PROFILE, ROSTER). Поверх существующего в saves ничего никогда не пишется.

#include <algorithm>
#include <cctype>
#include <filesystem>
#include <fstream>
#include <map>
#include <set>
#include <string>
#include <system_error>
#include <vector>

#include <rex/cvar.h>
#include <rex/filesystem.h>
#include <rex/logging.h>

REXCVAR_DEFINE_STRING(nhl_saves_root, "saves", "NHLLegacy",
                      "Folder for everything personal: saves by kind, achievements, launcher settings, highlights; "
                      "relative to the exe folder. Empty = old layout userdata\\<xuid>\\454109EC\\00000001")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

namespace {

namespace fs = std::filesystem;

// Префикс имени сейва → папка (решение пользователя 05.11.2026: английские имена). Префиксы — таблица групп сейвов
// игры (0x8208BBA4…: PROFILE, DYNASTY, ROSTER, ONLINEROSTER, TOURNAMENT, BEAPRO, VIDEO, SCREENSHOT, HOCKEYCARD,
// PLAYOFF, SEASON, BUILDYOURAI, SCENARIOFILE, DYNAMICRATINGS, RIVALRYGAME). Порядок важен: перечисление идёт по нему.
constexpr const char* kFolders =
    "PROFILE=profiles;ROSTER=rosters;DYNASTY=franchises;BEAPRO=be-a-pro;SEASON=seasons;PLAYOFF=playoffs;"
    "TOURNAMENT=tournaments;HOCKEYCARD=hockey-cards;BUILDYOURAI=build-your-ai;SCENARIOFILE=scenarios;"
    "DYNAMICRATINGS=dynamic-ratings;RIVALRYGAME=rivalry-games;ONLINEROSTER=online-rosters;VIDEO=videos;"
    "SCREENSHOT=screenshots;*=other";
constexpr const char* kTitle = "454109EC";
constexpr const char* kSavedGames = "00000001";
constexpr const char* kMigratedList = "migrated-from-userdata.txt";

fs::path g_root;                 // пусто — старая раскладка
std::vector<std::string> g_log;  // журнал ещё не поднят, пока идёт OnConfigurePaths

std::string Upper(std::string s) {
  for (char& c : s) c = char(std::toupper(static_cast<unsigned char>(c)));
  return s;
}

struct Layout {
  std::vector<std::pair<std::string, std::string>> map;  // PREFIX → папка
  std::string fallback = "other";
  std::vector<std::string> all;
};

Layout ParseLayout(const std::string& spec) {
  Layout l;
  size_t pos = 0;
  while (pos <= spec.size()) {
    size_t end = spec.find(';', pos);
    if (end == std::string::npos) end = spec.size();
    const std::string item = spec.substr(pos, end - pos);
    const size_t eq = item.find('=');
    if (eq != std::string::npos && eq + 1 < item.size()) {
      const std::string key = Upper(item.substr(0, eq)), dir = item.substr(eq + 1);
      if (key == "*") {
        l.fallback = dir;
      } else {
        l.map.emplace_back(key, dir);
      }
    }
    pos = end + 1;
  }
  for (const auto& [k, d] : l.map) {
    if (std::find(l.all.begin(), l.all.end(), d) == l.all.end()) l.all.push_back(d);
  }
  if (std::find(l.all.begin(), l.all.end(), l.fallback) == l.all.end()) l.all.push_back(l.fallback);
  return l;
}

// Как в патче 0007 (FolderForSave): ведущие буквы имени.
std::string Prefix(const std::string& name) {
  size_t n = 0;
  while (n < name.size() && (std::isalpha(static_cast<unsigned char>(name[n])) || name[n] == '_')) ++n;
  return Upper(name.substr(0, n));
}

const std::string& FolderFor(const Layout& l, const std::string& name) {
  const std::string p = Prefix(name);
  for (const auto& [k, d] : l.map) {
    if (k == p) return d;
  }
  return l.fallback;
}

bool IsXuid(const std::string& s) {
  return s.size() == 16 && std::all_of(s.begin(), s.end(), [](char c) { return std::isxdigit(static_cast<unsigned char>(c)); });
}

bool InSaves(const Layout& l, const std::string& name) {
  std::error_code ec;
  for (const auto& d : l.all) {
    if (fs::is_directory(g_root / d / rex::to_path(name), ec)) return true;
  }
  return false;
}

// Копия папки через временное имя рядом: игра не увидит половину сейва (временная папка — не в папках сейвов).
bool CopyDir(const fs::path& from, const fs::path& to, std::string& err) {
  std::error_code ec;
  const fs::path tmp = g_root / ".copy.tmp";
  fs::remove_all(tmp, ec);
  fs::create_directories(tmp, ec);
  const fs::path staged = tmp / to.filename();
  fs::copy(from, staged, fs::copy_options::recursive, ec);
  if (ec) {
    err = ec.message();
    fs::remove_all(tmp, ec);
    return false;
  }
  fs::create_directories(to.parent_path(), ec);
  fs::rename(staged, to, ec);
  if (ec) {
    err = ec.message();
    fs::remove_all(tmp, ec);
    return false;
  }
  fs::remove_all(tmp, ec);
  return true;
}

std::set<std::string> ReadMigrated() {
  std::set<std::string> out;
  std::ifstream f(g_root / kMigratedList);
  std::string line;
  while (std::getline(f, line)) {
    if (!line.empty() && line.back() == '\r') line.pop_back();
    if (line.empty() || line[0] == '#') continue;
    out.insert(Upper(line));
  }
  return out;
}

void AddMigrated(const std::vector<std::string>& names) {
  if (names.empty()) return;
  std::error_code ec;
  const fs::path p = g_root / kMigratedList;
  const bool fresh = !fs::exists(p, ec);
  std::ofstream f(p, std::ios::app);
  if (fresh) {
    f << "# Saves copied from the old place userdata\\<xuid>\\454109EC\\00000001 into saves\\ (nhllegacy.exe).\n"
         "# A listed name is never copied again, so a save deleted in the game does not come back.\n";
  }
  for (const auto& n : names) f << n << "\n";
}

// userdata\<xuid>\454109EC\00000001\<имя> → saves\<папка>\<имя> (+ заголовок).
void MigrateOldSaves(const Layout& l, const fs::path& user_data_root) {
  std::error_code ec;
  if (!fs::is_directory(user_data_root, ec)) return;
  std::set<std::string> migrated = ReadMigrated();
  std::vector<std::string> added;
  std::map<std::string, int> per_folder;
  int failed = 0, already = 0;
  for (const auto& xuid : fs::directory_iterator(user_data_root, ec)) {
    const std::string xuid_name = rex::path_to_utf8(xuid.path().filename());
    if (!xuid.is_directory(ec) || !IsXuid(xuid_name)) continue;
    const fs::path saves = xuid.path() / kTitle / kSavedGames;
    const fs::path headers = xuid.path() / kTitle / "Headers" / kSavedGames;
    if (!fs::is_directory(saves, ec)) continue;
    for (const auto& save : fs::directory_iterator(saves, ec)) {
      if (!save.is_directory(ec)) continue;
      const std::string name = rex::path_to_utf8(save.path().filename());
      if (migrated.count(Upper(name))) continue;
      if (InSaves(l, name)) {
        ++already;
        migrated.insert(Upper(name));
        added.push_back(name);
        continue;
      }
      const std::string& folder = FolderFor(l, name);
      const fs::path to = g_root / folder / rex::to_path(name);
      std::string err;
      if (!CopyDir(save.path(), to, err)) {
        ++failed;
        g_log.push_back("saves: could not copy " + rex::path_to_utf8(save.path()) + ": " + err);
        continue;
      }
      const fs::path header = headers / rex::to_path(name + ".header");
      const fs::path header_to = g_root / folder / rex::to_path(name + ".header");
      if (fs::is_regular_file(header, ec) && !fs::exists(header_to, ec)) {
        fs::copy_file(header, header_to, ec);
      }
      migrated.insert(Upper(name));
      added.push_back(name);
      ++per_folder[folder];
    }
  }
  AddMigrated(added);
  int copied = 0;
  std::string list;
  for (const auto& [folder, n] : per_folder) {
    copied += n;
    list += (list.empty() ? "" : ", ") + folder + " " + std::to_string(n);
  }
  if (copied || failed) {
    g_log.push_back("saves: copied " + std::to_string(copied) + " old save(s) from " +
                    rex::path_to_utf8(user_data_root) + "\\<xuid>\\454109EC\\00000001 to " + rex::path_to_utf8(g_root) +
                    (list.empty() ? "" : " (" + list + ")") + "; the old copies stay where they were" +
                    (failed ? ", " + std::to_string(failed) + " failed" : ""));
  }
  if (already) {
    g_log.push_back("saves: " + std::to_string(already) + " old save(s) already in saves, not copied");
  }
}

// Файл или папка со старого места, если на новом ещё нет (ачивки, настройки профиля Xbox).
void MigrateOne(const fs::path& from, const fs::path& to, const char* what) {
  std::error_code ec;
  if (!fs::exists(from, ec) || fs::exists(to, ec)) return;
  fs::create_directories(to.parent_path(), ec);
  fs::copy(from, to, fs::copy_options::recursive, ec);
  g_log.push_back(std::string("saves: ") + what + " copied from " + rex::path_to_utf8(from) +
                  (ec ? " FAILED: " + ec.message() : " (old copy left in place)"));
}

bool HasSaveOfKind(const Layout& l, const std::string& prefix) {
  std::error_code ec;
  for (const auto& d : l.all) {
    const fs::path dir = g_root / d;
    if (!fs::is_directory(dir, ec)) continue;
    for (const auto& e : fs::directory_iterator(dir, ec)) {
      if (e.is_directory(ec) && Prefix(rex::path_to_utf8(e.path().filename())) == prefix) return true;
    }
  }
  return false;
}

// start-saves\<папка>\<имя>[.header] → saves, только если такого вида сейвов в saves нет совсем.
void StartSaves(const Layout& l, const fs::path& start) {
  std::error_code ec;
  if (!fs::is_directory(start, ec)) return;
  std::map<std::string, bool> has;  // префикс → в saves уже есть (проверяется до копирования)
  int copied = 0;
  for (const auto& folder : fs::directory_iterator(start, ec)) {
    if (!folder.is_directory(ec)) continue;
    for (const auto& save : fs::directory_iterator(folder.path(), ec)) {
      if (!save.is_directory(ec)) continue;
      const std::string name = rex::path_to_utf8(save.path().filename());
      const std::string prefix = Prefix(name);
      if (!has.count(prefix)) has[prefix] = HasSaveOfKind(l, prefix);
      if (has[prefix] || InSaves(l, name)) continue;
      const std::string& dest = FolderFor(l, name);
      std::string err;
      if (!CopyDir(save.path(), g_root / dest / rex::to_path(name), err)) {
        g_log.push_back("saves: start save " + name + " not copied: " + err);
        continue;
      }
      const fs::path header = folder.path() / rex::to_path(name + ".header");
      const fs::path header_to = g_root / dest / rex::to_path(name + ".header");
      if (fs::is_regular_file(header, ec) && !fs::exists(header_to, ec)) fs::copy_file(header, header_to, ec);
      ++copied;
    }
  }
  if (copied) {
    g_log.push_back("saves: " + std::to_string(copied) + " start save(s) copied from " + rex::path_to_utf8(start) +
                    " (saves had none of that kind)");
  }
}

}  // namespace

// Из OnConfigurePaths, после чтения nhllegacy.toml и до создания рантайма.
void NhlLegacyConfigureSaves(const fs::path& exe_dir, const fs::path& user_data_root) {
  const std::string v = REXCVAR_GET(nhl_saves_root);
  if (v.empty()) {
    g_log.push_back("saves: nhl_saves_root is empty, saves stay in " + rex::path_to_utf8(user_data_root));
    return;
  }
  fs::path root = rex::to_path(v);
  if (root.is_relative()) root = exe_dir / root;
  std::error_code ec;
  root = fs::weakly_canonical(root, ec);
  if (ec) root = fs::absolute(rex::to_path(v), ec);
  if (rex::cvar::GetFlagInfo("saved_game_root") == nullptr) {
    g_log.push_back("saves: rexruntime.dll has no saved_game_root (SDK patch 0007 missing), saves stay in " +
                    rex::path_to_utf8(user_data_root));
    return;
  }
  fs::create_directories(root, ec);
  if (ec) {
    g_log.push_back("saves: cannot create " + rex::path_to_utf8(root) + ": " + ec.message() + ", saves stay in " +
                    rex::path_to_utf8(user_data_root));
    return;
  }
  if (rex::cvar::GetFlagByName("saved_game_folders").empty()) {
    rex::cvar::SetFlagByName("saved_game_folders", kFolders);
  }
  rex::cvar::SetFlagByName("saved_game_root", rex::path_to_utf8(root));
  g_root = root;
  const Layout l = ParseLayout(rex::cvar::GetFlagByName("saved_game_folders"));
  MigrateOldSaves(l, user_data_root);
  MigrateOne(user_data_root / "achievements" / (std::string(kTitle) + ".toml"),
             g_root / "achievements" / (std::string(kTitle) + ".toml"), "achievements");
  MigrateOne(user_data_root / kTitle / "profile", g_root / "xbox-profile", "Xbox profile settings");
  StartSaves(l, exe_dir / "start-saves");
}

// Из OnPostSetup: журнал уже поднят.
void NhlLegacyLogSaves() {
  if (!g_root.empty()) {
    REXLOG_INFO("[nhllegacy] saves: {} (by kind: {})", rex::path_to_utf8(g_root),
                rex::cvar::GetFlagByName("saved_game_folders"));
  }
  for (const auto& line : g_log) {
    REXLOG_INFO("[nhllegacy] {}", line);
  }
  g_log.clear();
}

// Корень saves (пусто — старая раскладка): highlights.sav и прочее личное, что игра пишет в cache:.
const fs::path& NhlLegacySavesRoot() {
  return g_root;
}
