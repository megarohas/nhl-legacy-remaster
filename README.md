# NHL Legacy Remaster

**English** | [Русский](README.ru.md)

Native Windows ports of EA's Xbox 360 hockey games, modeled on
[nhl-legacy-recomp](https://github.com/puckhead73/nhl-legacy-recomp) (ReXGlue recompilation), plus
mods for them. The main one is **NHL Legacy Edition** (`legacy-port/`, TitleID `454109EC`): a 32-club league with
Seattle, Vegas and Utah, a 32-team AHL, 2026/27 rosters, ratings computed with the game's exact formula, fresh logos,
uniforms from NHL 24, and fixes for franchise mode, the draft and Be a Pro. Next to it is the NHL 13 port (`port/`,
TitleID `4541099B`), where it all started: editing the `nhlng.db` database, how leagues are structured, and the
current year.

Version: [VERSION](VERSION); history: [CHANGELOG.md](CHANGELOG.md) (in Russian).

**There are no game files here.** Only the port code (hooks and fixes), tools and documentation. Code generated
from the game, builds, game files, saves, EA databases, photos and assets from other games never go into the repo:
they live in `game/` and other folders listed in `.gitignore`. To build anything, you need your own copy of the
game. NHL, EA SPORTS and the club names are trademarks of their respective owners; this project is not affiliated
with them.

## Structure

The documentation in `docs/` is in Russian.

| Path | What |
|---|---|
| [docs/briefing.md](docs/briefing.md) | Intro: the goal, what's known about the database, the plan |
| [docs/xbox-transfer.md](docs/xbox-transfer.md) | How to get files off the console |
| [docs/game-files.md](docs/game-files.md) | What's inside the game, where the database is, how to unpack it; NHL 12, NHL 10 and NHL Legacy from the same console |
| [docs/year-and-date.md](docs/year-and-date.md) | Where the current year and dates live: saves, calendars, code |
| [docs/save-editing.md](docs/save-editing.md) | How a franchise save is structured and how to edit it |
| [docs/port.md](docs/port.md) | The port toolchain, ReXGlue code generation, what's next |
| [docs/research.md](docs/research.md) | Neighboring recomps (NHL 14, 3 on 3, Skate 3…) and what was borrowed from them |
| [docs/modding.md](docs/modding.md) | Database mods via cache: — players (nhlng.db) and names (localization) |
| [docs/music.md](docs/music.md) | Music: the audio/music bank (EALayer3), EA Trax, how the game picks a track, replacing the soundtrack |
| [docs/team-editor.md](docs/team-editor.md) | The built-in team editor: what filters out regular teams, what breaks saving, the "donor uniform" option |
| [docs/fe-fonts.md](docs/fe-fonts.md) | UI fonts (TrueType in fe/ion/fonts): which one is used for what, replacing them with your own; the NHL 12 menu font — installed in the game, install and rollback |
| [docs/fe-background.md](docs/fe-background.md) | Menu background (Apt animation): blue → any color, tools/febg.py |
| [docs/fe-menu.md](docs/fe-menu.md) | The NHL 12 main menu in NHL 13: arena background, list tiles and font, the Features panel, present-day players with their names; tools/menu12.py, menuplayers.py, feapt.py (ActionScript Apt) |
| [docs/player-models.md](docs/player-models.md) | Player 3D models: what a player is assembled from, LODs, the RW4 mesh format, socks (skatesocktuck) and the shin fix, stick tape all the way to the toe, an NHL 10-style back jersey hem |
| [docs/player-equipment.md](docs/player-equipment.md) | Player equipment from photos (NHL + Wikimedia Commons): stick tape, socks, jersey, visor — database fields and coverage |
| [docs/teams.md](docs/teams.md) | Teams, leagues, team references and calendars in the database; a 32-team NHL |
| [docs/graphics-settings.md](docs/graphics-settings.md) | Port graphics settings: runtime cvars, upscaling, RTV/ROV, input latency, the launcher |
| [docs/launcher.md](docs/launcher.md) | The NHL Legacy launcher (`legacy-port/launcher`): a pre-launch window for graphics settings and `nhl_*` toggles, its own settings file, passed to the game as arguments |
| [docs/performance.md](docs/performance.md) | Performance: in-game GPU/CPU measurements, the cost of FSI vs. host RTs, the render thread spin (fixed), pipeline-related hitches, an A/B plan |
| [docs/legacy-port-feasibility.md](docs/legacy-port-feasibility.md) | Carrying the work over to NHL Legacy (2015): what can be found automatically, how much work each piece takes, how friends can play Legacy on PC, the plan |
| [docs/legacy-port.md](docs/legacy-port.md) | Our own NHL Legacy port (`legacy-port/`): what works, building, running, the folder for friends, the year and 32 teams |
| [docs/legacy-data.md](docs/legacy-data.md) | NHL 13 data mods in NHL Legacy via cache: — 32 teams and a 32-team AHL, 2026/27 rosters, portraits, equipment, the NHL 12 font, music, 3D, SEA/VGK art: game profile, ZlibV4 saves, build, install, in-game verification |
| [docs/draft-pool.md](docs/draft-pool.md) | The franchise draft pool (NHL 13 and Legacy): how the game builds the class, why it contains 2012 CHL rosters and veterans, retirement, options (the `--retire-veterans` pipeline option, age filtering, fresh CHL rosters) |
| `port/` | The ReXGlue port project (generated code is not in git) |
| `legacy-port/` | The NHL Legacy port project (generated code, builds, saves and research are not in git) |
| [tools/svod.py](tools/svod.py) | Verifies and unpacks SVOD containers (disc installs, GoD) |
| [tools/stfs.py](tools/stfs.py) | Verifies and unpacks STFS packages (title updates, saves) |
| [tools/xex.py](tools/xex.py) | Decrypts and decompresses `default.xex` into a memory image |
| [tools/lzx.py](tools/lzx.py), [tools/aes.py](tools/aes.py) | LZX (a port of lzxd) and AES-128 in pure Python |
| [tools/unchunk.py](tools/unchunk.py) | Decompresses EA `chunklzx` / `chunkzip` inside `.big` |
| [tools/big.py](tools/big.py) | EA `.big` archives: BigEB v3 and BIG4 (NHL 10), RefPack and chunk compression, the whole disc folder by folder with a process pool |
| [tools/ppcdis.py](tools/ppcdis.py) | A mini PowerPC disassembler for exploring the image |
| [tools/genfn.py](tools/genfn.py) | Asm of game functions from the port's generated code (instruction comments and labels) |
| [tools/xmatch.py](tools/xmatch.py) | Matches code between two images in the series (NHL 13 → Legacy, NHL 12): functions and hook sites via masked signatures and the call graph |
| [tools/tdb_read.py](tools/tdb_read.py) | A reader for EA TDB v6 databases (read-only) |
| [tools/tdb.py](tools/tdb.py) | Writes TDB fields, recalculates the database and save-wrapper CRCs (NHL 13 and NHL Legacy's zlib-compressed saves — ZlibV4) |
| [tools/gameprofile.py](tools/gameprofile.py) | Game profile for the tools (`--game nhl13\|legacy`): archive and cache: paths, database schema, league and special-team strings, free art slots, rating fields; checks that the database belongs to that game |
| [tools/locdb.py](tools/locdb.py) | Localization strings (Huffman): export and editing |
| [tools/year_hooks.py](tools/year_hooks.py) | Finds year constants in the code and generates year-shift hooks for the port |
| [tools/nhl32.py](tools/nhl32.py) | A 32-team NHL: moving two teams, divisions, an 84-game schedule; `--game legacy` does the same for NHL Legacy (plus `--ahl32`) |
| [tools/febg.py](tools/febg.py) | Menu background: parsing the UI animation, recoloring, previews |
| [tools/fefont.py](tools/fefont.py) | UI font replacement: your own TTF/OTF fitted into the "skeleton" of a game font with the same names and metrics, or the font as-is (`--keep`, which is how the NHL 12 font was installed); glyph checks for strings and names, previews |
| [tools/music.py](tools/music.py) | Custom soundtrack: MP3/FLAC/WAV → the game's music bank, EA Trax titles and cover art (via ffmpeg) |
| [tools/rw4mesh.py](tools/rw4mesh.py) | RW4 player meshes ⇄ OBJ for Blender, the sock shin fix, gap checks, previews |
| [tools/jersey10.py](tools/jersey10.py) | An NHL 10-style back jersey hem: hem weights from NHL 10 on NHL 13 meshes (all variants and LODs), a fix for the hem clipping through the pants, checks in skating poses, a preview sheet |
| [tools/sticktape.py](tools/sticktape.py) | Stick tape all the way to the toe of the blade plus a rounded toe: skaters and goalies, both hands, `_2`/`_4`, checks, a preview sheet |
| [tools/perfwatch.ps1](tools/perfwatch.ps1), [tools/perf_ab.ps1](tools/perf_ab.ps1) | Passive per-thread GPU/CPU measurement during gameplay; launching A/B render variants via arguments |
| [tools/gameshot.ps1](tools/gameshot.ps1) | In-game checks without a gamepad: launches the build, captures the window (PrintWindow), sends keyboard input via `--mnk_mode` |
| [tools/stackpeek.py](tools/stackpeek.py) | What the game thread is busy with: its stack via ReadProcessMemory without stopping it, addresses → guest functions |
| `game/` | Local game files, not in git |
| `ref/` | Clones of puckhead73's repos for reference, not in git |

## Status

- [x] Xbox 360 found on the network, Aurora FTP responds
- [x] On the console: disc install, TU2 update, saves (including 4 franchises)
- [x] On the PC: install header, TU2, saves
- [x] On the PC: install data `Data0000`–`Data0037` (5.92 GB, sizes verified)
- [x] SVOD unpacking with hash verification: 20 files in `game/extracted/disc/` (`default.xex`, `.big`)
- [x] `nhlng.db` found (`cache.big` → `db/`), byte-for-byte identical to the anchor copy from nhl-modding-studio
- [x] TU2 update taken apart: `default.xexp` + `patch.big` (UI, scenarios; no database)
- [x] Starting year: not in the configs; the league year is in the save (`leaguestates`), but 2012 is hardcoded in ~88 functions
- [x] Age in franchise mode is computed from the league year (confirmed by the user on their own 2017 franchise)
- [x] Save editing: writing TDB with CRCs, STFS rehashing ([docs/save-editing.md](docs/save-editing.md))
- [x] Port toolchain: VS 2022 Build Tools, LLVM 23, CMake, Ninja, Vulkan SDK, ReXGlue SDK 0.10.0
- [x] Port: first ReXGlue code generation (679 files, 5 unresolved branches) — [docs/port.md](docs/port.md)
- [x] Port: builds and runs up to the title screen (VP6 video, audio, gamepad) — [docs/port.md](docs/port.md)
- [x] Port: first match — menus, 3D, audio, gamepad; 2.5 periods and a goal (2026-10-07)
- [x] Mods via cache: — `db/nhlng.db` (players) and `fe/loc/NHL_ENG_US.db` (team names) work in the port — [docs/modding.md](docs/modding.md)
- [ ] Port: performance (Release/PGO, vsync and lag in videos)
- [x] NHL Legacy: data mods via cache: (32 teams, 2026/27 rosters, portraits, equipment, NHL 12 font, music, 3D, SEA/VGK art) — verified in our own Legacy port (2026-10-08) — [docs/legacy-data.md](docs/legacy-data.md)
- [ ] A 32-team NHL (Tappara and TPS instead of the All-Star teams, an 84-game schedule) — in-game verification
- [x] Year: `season_year` shifts the game's "now" — age in "Play Now" and a new 2026/27 franchise
  verified in game (2026-10-07) — [docs/year-and-date.md](docs/year-and-date.md)
