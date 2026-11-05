// Папка content рядом с exe: наш контент по частям, склеенный в один cache: (nhl_content_root; docs/legacy-port.md,
// «Папка content»).
//
// Раскладка одобрена пользователем 05.11.2026 (game/work/status/layout-proposal.md): content\database, menus, photos,
// logos, uniforms, heads, equipment, arenas, music и my — в каждой части те же пути, что у игры (db\…, fe\…,
// rendering\…, audio\…); замена одной части = обновление частями. Раньше всё это лежало одной папкой
// userdata\cache\guest (2 ГБ, ~12 тыс. файлов) вперемешку с тем, что пишет сама игра.
//
// Игра ищет каждый файл сначала в cache:\<путь>, потом в архивах диска. Диск cache: здесь один, но смотрит в несколько
// папок по очереди, первая найденная главнее:
//   1. личное, что игра пишет в cache: — saves\highlights (highlights.sav);
//   2. cache\game — всё остальное, что пишет игра (809284.ver, admanager_cache_images…): запись идёт только сюда;
//   3. content\my — свои правки поверх всего;
//   4. остальные части content в порядке content\order.txt (по строке на часть), без него — по алфавиту.
// В content игра не пишет никогда: открытие файла части на запись идёт на чтение, перезапись создаёт копию в
// cache\game (копирование при записи), удаление прячет файл до конца сеанса. Один путь в двух частях — берётся первая,
// в журнал строка «content: … in A and B, using A» (до 20 строк и итог).
//
// Дерево всех частей строится один раз при запуске (как HostPathDevice строит своё), каталоги — свои узлы
// OverlayDir с детьми из всех частей, файлы — HostPathEntry со своим путём на диске. Поиск — только в памяти: индекс
// «путь → запись» и дерево для того, что игра создала сама. На диск поиск не ходит (05.11.2026: промах — файла нет в
// cache:, игра идёт в архив диска, — проверял все части на диске, до 11 обращений к ФС под общей блокировкой VFS; в
// матче это ~1 промах в секунду, при загрузке — сотни). Файл, положенный в content при запущенной игре, игра не увидит
// до перезапуска — как и прежде нельзя ставить моды поверх запущенной игры. Раз в 30 с — счётчики в журнале.

#include <algorithm>
#include <atomic>
#include <cctype>
#include <chrono>
#include <mutex>
#include <unordered_map>
#include <filesystem>
#include <fstream>
#include <map>
#include <memory>
#include <string>
#include <system_error>
#include <vector>

#include <rex/cvar.h>
#include <rex/filesystem.h>
#include <rex/filesystem/devices/host_path_device.h>
#include <rex/filesystem/devices/host_path_entry.h>
#include <rex/filesystem/file.h>
#include <rex/filesystem/vfs.h>
#include <rex/logging.h>
#include <rex/string.h>

REXCVAR_DEFINE_STRING(nhl_content_root, "content", "NHLLegacy",
                      "Folder with our content in parts (database, menus, photos, logos, uniforms, heads, equipment, "
                      "arenas, music, my), merged into cache:; relative to the exe folder. Missing folder or empty = "
                      "the old single folder <cache_root>/guest")
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

namespace {

namespace fs = std::filesystem;
using rex::filesystem::Entry;
using rex::filesystem::File;
using rex::filesystem::FileInfo;
using rex::filesystem::HostPathEntry;
using rex::X_STATUS;

std::string Lower(std::string s) {
  for (char& c : s) c = char(std::tolower(static_cast<unsigned char>(c)));
  return s;
}

struct Layer {
  std::string name;  // для журнала: highlights, game, my, database…
  fs::path root;
  bool writable = false;
  bool personal = false;  // только перечисленные имена (highlights.sav)
};

// Личное, что игра пишет в корень cache: — в saves (решение пользователя 05.11.2026).
const char* const kPersonal[] = {"highlights.sav"};

bool IsPersonal(const std::string& rel) {
  for (const char* p : kPersonal) {
    if (Lower(rel) == p) return true;
  }
  return false;
}

class OverlayDevice;

// Каталог cache: — объединение одноимённых каталогов всех частей.
class OverlayDir : public Entry {
 public:
  OverlayDir(OverlayDevice* device, Entry* parent, std::string_view path);
  X_STATUS Open(uint32_t desired_access, File** out_file) override;
  Entry* Add(std::unique_ptr<Entry> e) {
    children_.push_back(std::move(e));
    return children_.back().get();
  }

 private:
  std::unique_ptr<Entry> CreateEntryInternal(std::string_view name, uint32_t attributes) override;
  bool DeleteEntryInternal(Entry* entry) override;
};

// Файл части content: только чтение, перезапись — копией в cache\game.
class PackFileEntry : public HostPathEntry {
 public:
  PackFileEntry(OverlayDevice* device, Entry* parent, std::string_view path, const fs::path& host,
                const FileInfo& info);
  X_STATUS Open(uint32_t desired_access, File** out_file) override;
  bool Truncate() override { return false; }  // VFS тогда удаляет запись и создаёт новый файл в cache\game

 private:
  X_STATUS RenameEntryInternal(const std::vector<std::string_view>&) override { return X_STATUS_ACCESS_DENIED; }
};

class DirFile : public File {
 public:
  DirFile(uint32_t access, Entry* entry) : File(access, entry) {}
  void Destroy() override { delete this; }
  X_STATUS ReadSync(std::span<uint8_t>, size_t, size_t* out) override {
    if (out) *out = 0;
    return X_STATUS_NOT_IMPLEMENTED;
  }
  X_STATUS WriteSync(std::span<const uint8_t>, size_t, size_t* out) override {
    if (out) *out = 0;
    return X_STATUS_NOT_IMPLEMENTED;
  }
};

class OverlayDevice : public rex::filesystem::HostPathDevice {
 public:
  OverlayDevice(std::string_view mount, std::vector<Layer> layers, const fs::path& writable)
      : HostPathDevice(mount, writable, /*read_only=*/false, /*allow_share_delete=*/true),
        layers_(std::move(layers)),
        writable_(writable) {}

  bool Initialize() override {
    std::error_code ec;
    fs::create_directories(writable_, ec);
    root_ = std::make_unique<OverlayDir>(this, nullptr, "");
    for (size_t i = 0; i < layers_.size(); ++i) {
      if (fs::is_directory(layers_[i].root, ec)) {
        Populate(i, static_cast<OverlayDir*>(root_.get()), layers_[i].root, "");
      }
    }
    if (conflicts_ > kConflictLines) {
      REXLOG_WARN("[nhllegacy] content: {} paths in two parts in all, the first part wins", conflicts_);
    }
    return true;
  }

  Entry* ResolvePath(std::string_view path) override {
    Entry* e = nullptr;
    {
      std::lock_guard lock(index_mutex_);
      const auto it = index_.find(Key(path));
      if (it != index_.end()) e = it->second;
    }
    if (e) {
      ++hits_;
    } else if ((e = root_->ResolvePath(path)) != nullptr) {  // создано игрой после запуска (CreateEntry)
      ++walks_;
      std::lock_guard lock(index_mutex_);
      index_[Key(path)] = e;
    } else {
      ++misses_;
    }
    LogStats();
    return e;
  }

  void Forget(const Entry* e) {  // запись удалена из дерева (DeleteEntryInternal): она и всё под ней — из индекса
    const std::string k = Key(e->path());
    std::lock_guard lock(index_mutex_);
    for (auto it = index_.begin(); it != index_.end();) {
      const bool under = it->first == k || (it->first.size() > k.size() && it->first.compare(0, k.size(), k) == 0 &&
                                            it->first[k.size()] == '\\');
      it = under || it->second == e ? index_.erase(it) : std::next(it);
    }
  }

  void Dump(rex::string::StringBuffer* sb) override { root_->Dump(sb, 0); }

  // Где на диске писать новый файл или каталог rel (путь внутри cache:).
  fs::path WritablePath(const std::string& rel) const {
    if (IsPersonal(rel)) {
      for (const auto& l : layers_) {
        if (l.personal) return l.root / rex::to_path(rel);
      }
    }
    return writable_ / rex::to_path(rex::string::utf8_fix_path_separators(rel));
  }

  bool IsWritableHost(const fs::path& host) const {
    for (const auto& l : layers_) {
      if (!l.writable) continue;
      const auto r = Lower(rex::path_to_utf8(l.root)), h = Lower(rex::path_to_utf8(host));
      if (h.size() > r.size() && h.compare(0, r.size(), r) == 0) return true;
    }
    return false;
  }

  Entry* MakeEntry(size_t layer, OverlayDir* parent, const fs::path& host, const FileInfo& info) {
    const std::string path = rex::string::utf8_join_guest_paths(parent->path(), rex::path_to_utf8(info.name));
    Entry* e;
    if (info.type == FileInfo::Type::kDirectory) {
      e = parent->Add(std::make_unique<OverlayDir>(this, parent, path));
    } else if (layers_[layer].writable) {
      e = parent->Add(std::unique_ptr<Entry>(HostPathEntry::Create(this, parent, host, info)));
    } else {
      e = parent->Add(std::make_unique<PackFileEntry>(this, parent, path, host, info));
    }
    std::lock_guard lock(index_mutex_);
    index_[Key(path)] = e;
    return e;
  }

 private:
  static constexpr int kConflictLines = 20;

  // Личный слой виден только для своих имён в корне.
  bool Visible(size_t layer, const std::string& rel) const { return !layers_[layer].personal || IsPersonal(rel); }

  void Populate(size_t layer, OverlayDir* dir, const fs::path& host_dir, const std::string& rel_dir) {
    for (const auto& info : rex::filesystem::ListFiles(host_dir)) {
      const std::string name = rex::path_to_utf8(info.name);
      const std::string rel = rel_dir.empty() ? name : rel_dir + "\\" + name;
      if (!Visible(layer, rel)) continue;
      if (layer_of_.count(Lower(rel)) == 0 || info.type == FileInfo::Type::kDirectory) {
        Entry* existing = dir->GetChild(name);
        if (info.type == FileInfo::Type::kDirectory) {
          if (!existing) {
            existing = MakeEntry(layer, dir, host_dir / info.name, info);
          }
          if (existing->attributes() & rex::filesystem::kFileAttributeDirectory) {
            Populate(layer, static_cast<OverlayDir*>(existing), host_dir / info.name, rel);
          }
          continue;
        }
        if (!existing) {
          MakeEntry(layer, dir, host_dir / info.name, info);
          layer_of_[Lower(rel)] = layer;
          continue;
        }
      }
      // Тот же путь уже дала часть выше по очереди.
      const auto it = layer_of_.find(Lower(rel));
      const size_t first = it == layer_of_.end() ? layer : it->second;
      if (!layers_[first].writable && !layers_[first].personal && !layers_[layer].writable) {
        if (++conflicts_ <= kConflictLines) {
          REXLOG_WARN("[nhllegacy] content: {} in {} and {}, using {}", rel, layers_[first].name, layers_[layer].name,
                      layers_[first].name);
        }
      }
    }
  }

  // Ключ индекса: путь в нижнем регистре ASCII, разделитель «\\», без ведущих и повторных разделителей.
  static std::string Key(std::string_view path) {
    std::string k;
    k.reserve(path.size());
    for (char c : path) {
      if (c == '/' || c == '\\') {
        if (!k.empty() && k.back() != '\\') k.push_back('\\');
        continue;
      }
      k.push_back(char(std::tolower(static_cast<unsigned char>(c))));
    }
    while (!k.empty() && k.back() == '\\') k.pop_back();
    return k;
  }

  void LogStats() {
    const auto now = std::chrono::steady_clock::now();
    std::lock_guard lock(stats_mutex_);
    if (now - last_log_ < std::chrono::seconds(30)) return;
    if (last_log_.time_since_epoch().count() != 0) {
      REXLOG_INFO("[nhllegacy] content: lookups in 30 s — {} found by index, {} in the tree, {} not in cache: (no disk "
                  "access)", hits_.exchange(0), walks_.exchange(0), misses_.exchange(0));
    }
    last_log_ = now;
  }

  std::vector<Layer> layers_;
  fs::path writable_;
  std::unique_ptr<Entry> root_;
  std::mutex index_mutex_;
  std::unordered_map<std::string, Entry*> index_;
  std::atomic<uint64_t> hits_{0}, walks_{0}, misses_{0};
  std::mutex stats_mutex_;
  std::chrono::steady_clock::time_point last_log_{};
  std::map<std::string, size_t> layer_of_;  // путь файла (нижний регистр) → часть, откуда он взят
  int conflicts_ = 0;
};

OverlayDir::OverlayDir(OverlayDevice* device, Entry* parent, std::string_view path) : Entry(device, parent, path) {
  attributes_ = rex::filesystem::kFileAttributeDirectory;
}

X_STATUS OverlayDir::Open(uint32_t desired_access, File** out_file) {
  *out_file = new DirFile(desired_access, this);
  return X_STATUS_SUCCESS;
}

std::unique_ptr<Entry> OverlayDir::CreateEntryInternal(std::string_view name, uint32_t attributes) {
  auto* dev = static_cast<OverlayDevice*>(device_);
  const std::string rel = rex::string::utf8_join_guest_paths(path_, name);
  const fs::path host = dev->WritablePath(rel);
  std::error_code ec;
  fs::create_directories(host.parent_path(), ec);
  if (attributes & rex::filesystem::kFileAttributeDirectory) {
    fs::create_directories(host, ec);
    if (ec) return nullptr;
    return std::make_unique<OverlayDir>(dev, this, rel);
  }
  if (!rex::filesystem::CreateEmptyFile(host)) {
    return nullptr;
  }
  FileInfo info;
  if (!rex::filesystem::GetInfo(host, &info)) {
    return nullptr;
  }
  return std::unique_ptr<Entry>(HostPathEntry::Create(dev, this, host, info));
}

bool OverlayDir::DeleteEntryInternal(Entry* entry) {
  auto* dev = static_cast<OverlayDevice*>(device_);
  dev->Forget(entry);
  if (entry->attributes() & rex::filesystem::kFileAttributeDirectory) {
    std::error_code ec;
    fs::remove(dev->WritablePath(entry->path()), ec);  // только пустой каталог cache\game; части не трогаются
    return true;
  }
  if (auto* host = dynamic_cast<HostPathEntry*>(entry); host && dev->IsWritableHost(host->host_path())) {
    std::error_code ec;
    fs::remove(host->host_path(), ec);
    return !ec;
  }
  return true;  // файл части: прячется до конца сеанса, на диске остаётся
}

PackFileEntry::PackFileEntry(OverlayDevice* device, Entry* parent, std::string_view path, const fs::path& host,
                             const FileInfo& info)
    : HostPathEntry(device, parent, path, host) {
  create_timestamp_ = info.create_timestamp;
  access_timestamp_ = info.access_timestamp;
  write_timestamp_ = info.write_timestamp;
  attributes_ = rex::filesystem::kFileAttributeNormal | rex::filesystem::kFileAttributeReadOnly;
  size_ = info.total_size;
  allocation_size_ = (info.total_size + 0x1FF) & ~size_t(0x1FF);
}

X_STATUS PackFileEntry::Open(uint32_t desired_access, File** out_file) {
  constexpr uint32_t kWrite = rex::filesystem::FileAccess::kFileWriteData | rex::filesystem::FileAccess::kFileAppendData |
                              rex::filesystem::FileAccess::kGenericWrite | rex::filesystem::FileAccess::kGenericAll;
  if (desired_access & kWrite) {
    static bool once = false;
    if (!once) {
      once = true;
      REXLOG_WARN("[nhllegacy] content: {} opened for write, read only (content parts are never written)", path());
    }
    desired_access = (desired_access & ~kWrite) | rex::filesystem::FileAccess::kFileReadData;
  }
  return HostPathEntry::Open(desired_access, out_file);
}

fs::path g_content;               // корень content (пусто — старая раскладка)
std::vector<std::string> g_order;  // части по очереди (без my)

std::vector<std::string> PackOrder(const fs::path& content) {
  std::vector<std::string> order;
  std::error_code ec;
  std::ifstream f(content / "order.txt");
  std::string line;
  while (std::getline(f, line)) {
    if (!line.empty() && line.back() == '\r') line.pop_back();
    while (!line.empty() && std::isspace(static_cast<unsigned char>(line.back()))) line.pop_back();
    if (line.empty() || line[0] == '#' || Lower(line) == "my") continue;
    if (fs::is_directory(content / rex::to_path(line), ec)) order.push_back(line);
  }
  std::vector<std::string> rest;
  for (const auto& e : fs::directory_iterator(content, ec)) {
    if (!e.is_directory(ec)) continue;
    const std::string n = rex::path_to_utf8(e.path().filename());
    if (Lower(n) == "my" || n.empty() || n[0] == '.') continue;
    if (std::none_of(order.begin(), order.end(), [&](const std::string& o) { return Lower(o) == Lower(n); })) {
      rest.push_back(n);
    }
  }
  std::sort(rest.begin(), rest.end(), [](const std::string& a, const std::string& b) { return Lower(a) < Lower(b); });
  order.insert(order.end(), rest.begin(), rest.end());
  return order;
}

}  // namespace

// Из OnConfigurePaths: есть ли папка content (тогда cache: — её части, а кэш игры — cache рядом с exe).
bool NhlLegacyContentConfigure(const fs::path& exe_dir) {
  const std::string v = REXCVAR_GET(nhl_content_root);
  if (v.empty()) return false;
  fs::path root = rex::to_path(v);
  if (root.is_relative()) root = exe_dir / root;
  std::error_code ec;
  if (!fs::is_directory(root, ec)) return false;
  g_content = fs::weakly_canonical(root, ec);
  if (ec) g_content = root;
  return true;
}

bool NhlLegacyContentOn() {
  return !g_content.empty();
}

// Из OnPostSetup: смонтировать cache: из частей. game_cache — cache_root\game, highlights — saves\highlights (пусто —
// highlights.sav тоже в game_cache). Возвращает папку, где искать nhllegacy_masks.txt.
fs::path NhlLegacyMountContent(rex::filesystem::VirtualFileSystem* vfs, const fs::path& game_cache,
                               const fs::path& highlights) {
  std::vector<Layer> layers;
  std::error_code ec;
  if (!highlights.empty()) {
    fs::create_directories(highlights, ec);
    layers.push_back({"highlights", highlights, /*writable=*/true, /*personal=*/true});
  }
  layers.push_back({"game", game_cache, /*writable=*/true, /*personal=*/false});
  layers.push_back({"my", g_content / "my", false, false});
  g_order = PackOrder(g_content);
  for (const auto& p : g_order) {
    layers.push_back({p, g_content / rex::to_path(p), false, false});
  }
  fs::path masks = g_content / "equipment";
  for (const auto& l : layers) {
    if (!l.personal && fs::is_regular_file(l.root / "nhllegacy_masks.txt", ec)) {
      masks = l.root;
      break;
    }
  }
  std::string order = "my";
  for (const auto& p : g_order) order += ", " + p;
  auto device = std::make_unique<OverlayDevice>("\\CACHE", std::move(layers), game_cache);
  if (device->Initialize() && vfs->RegisterDevice(std::move(device))) {
    vfs->RegisterSymbolicLink("cache:", "\\CACHE");
    REXLOG_INFO("[nhllegacy] cache: -> content {} ({}), game writes to {}{}", rex::path_to_utf8(g_content), order,
                rex::path_to_utf8(game_cache),
                highlights.empty() ? std::string() : ", highlights.sav to " + rex::path_to_utf8(highlights));
  } else {
    REXLOG_ERROR("[nhllegacy] failed to mount cache: from content {}", rex::path_to_utf8(g_content));
  }
  return masks;
}
