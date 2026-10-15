# NHL Legacy Remaster

**English** | [Русский](README.ru.md)

A Windows port of **NHL Legacy Edition** (Xbox 360, 2015) plus mods that bring it up to the 2026/27 season. There is
no emulator: the game code is recompiled to x86-64 with [ReXGlue](https://github.com/rexglue/rexglue-sdk),
following the approach of [nhl-legacy-recomp](https://github.com/puckhead73/nhl-legacy-recomp).

What you get:
- a 32-club league (Seattle, Vegas, and Utah in place of Arizona) and a 32-club AHL;
- 2026/27 rosters and contracts, with ratings computed by the game's own formula;
- current logos, uniforms, portraits and face scans from NHL 24, plus the NHL 12 font and main menu;
- fixes for franchise mode, the draft and Be a Pro.

The project started as an NHL 13 port (`nhl-13-port/`). That port is now frozen.

## What you need

- **Your own copy of NHL Legacy Edition for Xbox 360** (TitleID `454109EC`, disc or Games on Demand, no title
  updates): `default.xex` and the `*.big` archives, about 6 GB. The port targets the `default.xex` with SHA-256
  `d818eb15…c55624`. Getting the files off the console: [docs/xbox-transfer.md](docs/xbox-transfer.md); unpacking:
  [docs/game-files.md](docs/game-files.md).
- Windows 10/11 x64, a GPU with DirectX 12 or Vulkan 1.3, and an XInput gamepad (the keyboard can stand in for one).

## Quick start: players

The repository has no prebuilt exe, because it contains recompiled game code. You build the port from source (next
section) or get a ready-made `NHL Legacy` folder from someone in person.

1. **Port folder.** It holds `nhllegacy.exe` and its DLLs. Put your game files into `game\` next to the exe
   ([docs/legacy-port.md](docs/legacy-port.md), section «Для друзей»).
2. **Launcher.** `nhllegacy_launcher.exe` opens a settings window before the game starts. You pick the renderer
   (D3D12 or Vulkan), resolution, FSR 1 / CAS, season, 32-club NHL and AHL, and fixes there
   ([docs/launcher.md](docs/launcher.md)). Started without the launcher, `nhllegacy.exe` reads `nhllegacy.toml`.
3. **Data mods** (rosters, uniforms, logos, font, music, menus) are files in `userdata\cache\guest`. The game reads
   them before its own archives, so deleting a file removes that mod. Building and installing the set:
   [docs/legacy-data.md](docs/legacy-data.md).
4. Saves, controls and known limitations are covered in
   [nhl-legacy-port/dist-template/README.txt](nhl-legacy-port/dist-template/README.txt) (in Russian).

## Quick start: developers

- **Toolchain:** VS 2022 Build Tools, LLVM/Clang, CMake, Ninja, Vulkan SDK ([docs/port.md](docs/port.md)). Their
  paths are set in `nhl-legacy-port/build.cmd`.
- **ReXGlue SDK:** the 0.10.0.24 nightly in `ref/rexglue-sdk-0.10.0.24/`, or our own build with Vulkan and FSR 1 / CAS
  in `ref/rexglue-sdk-custom/`. `nhl-legacy-port\scripts\sdk_build.cmd` produces our own build: it clones the SDK, applies
  the patches from [nhl-legacy-port/scripts/sdk-patches/](nhl-legacy-port/scripts/sdk-patches/), builds and installs it
  ([docs/sdk-build.md](docs/sdk-build.md)).
- **Game files for codegen** go in `game/other/legacy/disc/` (`default.xex` and `*.big`).
- **Building the port:** `nhl-legacy-port\build.cmd` (Release, our SDK) or `nhl-legacy-port\build.cmd win-amd64-relwithdebinfo`
  (nightly SDK, with symbols). The first build runs ReXGlue codegen by itself (15–20 minutes), then compiles. Output:
  `nhl-legacy-port/out/build/<preset>/nhllegacy.exe` ([docs/legacy-port.md](docs/legacy-port.md), section «Сборка»).
- **Launcher:** `nhl-legacy-port\launcher\build.cmd` (output in `nhl-legacy-port/out/launcher/`). **Player folder:**
  `bash nhl-legacy-port/scripts/make_dist.sh [--mods]`.
- **Data mods:** `bash tools/legacy_data/build-all.sh [STAGE…] [--ahl32]` builds the set into
  `game/work/legacy-data/out`, and `bash tools/legacy_data/install-legacy-data.sh` installs it while the game is closed.
  The stages are listed in [tools/README.md](tools/README.md), details are in [docs/legacy-data.md](docs/legacy-data.md).
  You need Python 3; some stages also need numpy and Pillow, headless Chrome or ffmpeg.

## Repository map

| Path | What |
|---|---|
| [nhl-legacy-port/](nhl-legacy-port/) | the NHL Legacy port: `src/` (hooks and fixes), `nhllegacy_*.toml` (manifest, functions, hooks), `scripts/` (codegen, player folder, SDK patches), `dist-template/`; generated code and builds stay out of git |
| [nhl-legacy-port/launcher/](nhl-legacy-port/launcher/) | the `nhllegacy_launcher.exe` launcher (C++/Win32, a single file) |
| [tools/legacy_data/](tools/legacy_data/) | the Legacy data-mod pipeline: `build-all.sh`, installer, stages |
| [tools/roster/](tools/roster/) | 2026/27 rosters: NHL API, ratings, lines, writing the database |
| [tools/fb/](tools/fb/) | Frostbite (NHL 24) readers: uniforms, faces, portraits (personal use only) |
| [tools/](tools/README.md) | everything else: EA file formats, uniforms, UI, code research; map in [tools/README.md](tools/README.md) |
| [docs/](docs/README.md) | documentation (in Russian), table of contents by topic in [docs/README.md](docs/README.md) |
| [nhl-13-port/](nhl-13-port/) | the NHL 13 port where it all started (frozen) |
| `game/`, `ref/` | local only, not in git: game files and work folders; other people's repos for reference |

## Version

The version number is in [VERSION](VERSION), the change history in [CHANGELOG.md](CHANGELOG.md) (in Russian), and each
version has a `vX.Y.Z` tag. The second number is the port build; the third covers data and tool changes without a new
build.

## Legal

There are no game files here. The repository holds only our own port code, tools and documentation. Code generated
from the game, builds, game files, EA saves and databases, player photos, assets from other games (NHL 24) and music
never go in: they live in `game/` and other folders listed in `.gitignore`. You need your own copy of the game to
build anything. NHL, EA SPORTS, and club names and logos are trademarks of their respective owners. This project is
not affiliated with or endorsed by them.
