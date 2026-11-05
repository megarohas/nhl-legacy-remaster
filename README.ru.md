# NHL Legacy Remaster

[English](README.md) | **Русский**

Порт **NHL Legacy Edition** (Xbox 360, 2015) на Windows и моды к нему под сезон 2026/27. Эмулятора нет: код игры
перекомпилирован в x86-64 через [ReXGlue](https://github.com/rexglue/rexglue-sdk), по образцу
[nhl-legacy-recomp](https://github.com/puckhead73/nhl-legacy-recomp).

Что даёт:
- лигу на 32 клуба (Сиэтл, Вегас, Юта вместо Аризоны) и АХЛ на 32;
- составы, контракты и настоящий календарь 2026/27, рейтинги по точной формуле игры; сборные и составы Матча звёзд для
  «Играть сейчас»;
- нынешние формы всех 32 клубов НХЛ из NHL 27 (и клубов АХЛ, у которых форма сменилась с 2015 года), наклейки на шлемах,
  центры льда и арены, клюшки, коньки и экипировку NHL 27, свои вратарские маски;
- сканы лиц из NHL 24 и NHL 27, портреты, логотипы, шрифт и главное меню NHL 12;
- тактики клубов, историю Кубка Стэнли и наград;
- исправления франшизы, драфта и Be a Pro; заставку загрузки; курсор, скрытый над окном игры.

Проект начинался с порта NHL 13 (`nhl-13-port/`), сейчас тот порт заморожен.

## Что нужно

- **Своя копия NHL Legacy Edition для Xbox 360** (TitleID `454109EC`, диск или Games on Demand без обновлений):
  `default.xex` и архивы `*.big`, около 6 ГБ. Порт рассчитан на `default.xex` с SHA-256
  `d818eb15…c55624`. Как снять файлы с приставки — [docs/xbox-transfer.md](docs/xbox-transfer.md), как распаковать —
  [docs/game-files.md](docs/game-files.md).
- Windows 10/11 x64, видеокарта с DirectX 12 или Vulkan 1.3, геймпад XInput (можно и клавиатуру в роли геймпада).

## Быстрый старт: игроку

Готового exe в репозитории нет: в нём перекомпилированный код игры. Порт собирают из исходников (см. раздел ниже) или
получают готовую папку `NHL Legacy` из рук в руки.

1. **Папка порта.** В ней `nhllegacy.exe` и DLL. Свои файлы игры кладутся в `game\` рядом с exe
   ([docs/legacy-port.md](docs/legacy-port.md), раздел «Для друзей»).
2. **Лаунчер.** `nhllegacy_launcher.exe` открывает окно настроек перед запуском. Там выбираются рендер
   (D3D12 или Vulkan), разрешение, FSR 1 / CAS, сезон и финансы франшизы. НХЛ и АХЛ на 32 и исправления включены
   всегда ([docs/launcher.md](docs/launcher.md)). Без лаунчера `nhllegacy.exe` берёт настройки из `nhllegacy.toml`.
3. **Папки** (с 0.17.0, [docs/legacy-port.md](docs/legacy-port.md), разделы «Папка saves» и «Папка content»):

   ```
   NHL Legacy Remaster\
   ├─ nhllegacy_launcher.exe, nhllegacy.exe, DLL, nhllegacy.toml
   ├─ game\         свои файлы игры (default.xex, *.big)
   ├─ content\      моды-данные по темам: database, menus, photos, logos, uniforms, heads, equipment, arenas,
   │                music, my (свои правки, главнее всего)
   ├─ saves\        всё личное: сейвы по видам (profiles, rosters, franchises, be-a-pro…), повторы, ачивки,
   │                настройки лаунчера (saves\settings)
   ├─ start-saves\  стартовые профиль и ростер, копируются только в пустую saves\
   └─ cache\        кэш игры и шейдеров, можно удалить
   ```

   Внутри каждой `content\<часть>\` — пути самой игры (`db\…`, `fe\…`, `rendering\…`). Игра берёт эти файлы раньше
   архивов и в `content\` не пишет, поэтому мод убирается удалением файла, а любую часть можно заменить отдельно. Сборка
   и установка набора — [docs/legacy-data.md](docs/legacy-data.md).
4. **Обновление на новую версию:** скопировать новую папку поверх старой, кроме `saves\` (даже вместе с ней ничего не
   перезапишется). Новые составы приходят отдельным файлом: «Обновить ростеры» в лаунчере кладёт его в `saves\rosters`
   рядом со старыми. Сейвы версий до 0.17.0 (`userdata\B13EBABEBABEBABE\…`) игра при первом запуске копирует в `saves\`,
   старые остаются на месте.
5. Управление и известные ограничения описаны в
   [nhl-legacy-port/dist-template/README.txt](nhl-legacy-port/dist-template/README.txt).

## Быстрый старт: разработчику

- **Тулчейн:** VS 2022 Build Tools, LLVM/Clang, CMake, Ninja, Vulkan SDK ([docs/port.md](docs/port.md)). Пути к ним
  прописаны в `nhl-legacy-port/build.cmd`.
- **ReXGlue SDK:** ночная сборка 0.10.0.24 в `ref/rexglue-sdk-0.10.0.24/` или своя, с Vulkan и FSR 1 / CAS, в
  `ref/rexglue-sdk-custom/`. Свою собирает `nhl-legacy-port\scripts\sdk_build.cmd`: клонирует SDK, накладывает патчи из
  [nhl-legacy-port/scripts/sdk-patches/](nhl-legacy-port/scripts/sdk-patches/), собирает и устанавливает
  ([docs/sdk-build.md](docs/sdk-build.md)).
- **Игра для кодогена** — в `game/other/legacy/disc/` (`default.xex` и `*.big`).
- **Сборка порта:** `nhl-legacy-port\build.cmd` (Release, свой SDK) или `nhl-legacy-port\build.cmd win-amd64-relwithdebinfo`
  (ночной SDK, с символами). Первая сборка сама запускает кодоген ReXGlue (15–20 минут), потом идёт компиляция.
  Результат — `nhl-legacy-port/out/build/<пресет>/nhllegacy.exe` ([docs/legacy-port.md](docs/legacy-port.md), раздел
  «Сборка»).
- **Лаунчер:** `nhl-legacy-port\launcher\build.cmd` (результат — в `nhl-legacy-port/out/launcher/`). **Папка для игры:**
  `bash nhl-legacy-port/scripts/make_dist.sh [--mods]`; полная папка для другого своего ПК —
  `bash tools/device_release.sh [--no-saves] --check` ([docs/device-release.md](docs/device-release.md)).
- **Моды-данные:** `bash tools/legacy_data/build-all.sh [ЭТАП…] [--ahl32]` собирает набор в
  `game/work/legacy-data/out`, а `bash tools/legacy_data/install-legacy-data.sh` ставит его при закрытой игре. Этапы
  перечислены в [tools/README.md](tools/README.md), подробности — в [docs/legacy-data.md](docs/legacy-data.md).
  Нужную `content\<часть>` и сейвы установщики находят через `tools/legacy_paths.py` и `tools/legacy_saves.py` (обе
  раскладки, до 0.17.0 и после). Нужен Python 3; части этапов — ещё numpy и Pillow, Chrome без окна или ffmpeg.
- **Формы из новых NHL:** `tools/kitport` собирает, ставит и откатывает формы NHL 24 и NHL 27 на свитере Legacy
  ([docs/kitport.md](docs/kitport.md)).

## Карта папок

| Путь | Что |
|---|---|
| [nhl-legacy-port/](nhl-legacy-port/) | порт NHL Legacy: `src/` (врезки и исправления), `nhllegacy_*.toml` (манифест, функции, врезки), `scripts/` (кодоген, папка для игры, патчи SDK), `dist-template/`; сгенерированный код и сборка — вне git |
| [nhl-legacy-port/launcher/](nhl-legacy-port/launcher/) | лаунчер `nhllegacy_launcher.exe` (C++/Win32, один файл) |
| [tools/legacy_data/](tools/legacy_data/) | конвейер модов-данных Legacy: `build-all.sh`, установщик, этапы |
| [tools/roster/](tools/roster/) | составы 2026/27: API НХЛ, рейтинги, звенья, запись в базу |
| [tools/fb/](tools/fb/) | разбор Frostbite NHL 24 и NHL 27: формы, лица, портреты, лёд, наклейки на шлем (только для личного использования) |
| [tools/kitport/](tools/kitport/) | перенос форм из новых NHL: сборка, сравнение, установка, откат, листы проверки ([docs/kitport.md](docs/kitport.md)) |
| [tools/](tools/README.md) | остальные инструменты: форматы EA, формы, интерфейс, разведка кода — карта в [tools/README.md](tools/README.md) |
| [docs/](docs/README.md) | документация (на русском), оглавление по темам — [docs/README.md](docs/README.md) |
| [nhl-13-port/](nhl-13-port/) | порт NHL 13, с которого всё началось (заморожен) |
| `game/`, `ref/` | только локально, не в git: файлы игр и рабочие папки; чужие репозитории для справки |

## Версия

Номер версии — в [VERSION](VERSION), история изменений — в [CHANGELOG.md](CHANGELOG.md), у каждой версии есть метка
`vX.Y.Z`. Вторая цифра — номер сборки порта, третья — правки данных и инструментов без новой сборки.

## Правовая оговорка

Файлов игры здесь нет. В репозитории только свой код порта, инструменты и документация. Сгенерированный из игры код,
сборки, файлы игр, сейвы и базы EA, фото игроков, ассеты других игр (NHL 24) и музыка в него не попадают: они лежат в
`game/` и других папках из `.gitignore`. Для сборки нужна своя копия игры. NHL, EA SPORTS, названия и логотипы клубов —
товарные знаки их владельцев. Проект с ними не связан и ими не одобрен.
