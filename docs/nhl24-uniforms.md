# Формы NHL 24 (PS4) и NHL Legacy: модели свитеров, воротники, текстуры, соответствие

Разбор 09.10.2026 по дампу пользователя `game/other/nhl24/Data` (NHL 24 v1.00, PS4, Frostbite «Gen4b») и
распакованным архивам NHL Legacy (`game/other/legacy/big/`). Ассеты NHL 24 — только для личного использования:
в git — только инструменты (`tools/fb/`) и этот текст, картинки и выгрузки — в `game/work/nhl24/` (gitignored).
В игры ничего не ставилось, Legacy не запускалась.

Инструменты (`tools/fb/`, venv — `game/work/nhl24/venv`):

| модуль | что делает |
|---|---|
| `scan.py`, `catalog.py`, `orphans.py` | проход по CAS без TOC, каталог ресурсов, привязка «бесхозных» чанков по sha1 |
| `extract.py` | текстуры по регулярке имени → PNG (детайлинг PS4, BCn) |
| `meshset.py` | сетки NHL 24 (позиции, UV, треугольники) — только для расчётов |
| `kit3d.py` | перенос текстуры через 3D (ближайшая точка поверхности) и офлайн-рендер (numpy, z-буфер) |
| `kit_hybrid.py` + `kit_rules.toml` | **гибрид**: основа свитера через 3D + нашивки декалями по правилам |
| `kit_models.py` | листы: модели обеих игр, свитер на всех вариантах сетки Legacy, комплекты NHL 24 по клубам |

## 1. NHL 24: модели свитеров

Сетки — `content/character/skater/player/jersey/<крой>/components/player_jersey_<крой>_<заправка>_<размер>_lod0…2_mesh`.

| крой | время | ворот | шнуровка (`player_jerseytie_<крой>`) |
|---|---|---|---|
| `adidas` | 2017+ (нынешние) | круглый, неглубокий (adidas) | две висячие завязки (252 вершины) |
| `rbk` | Reebok Edge 2007–2017 | V-вырез Edge | есть (не разобрана: другая раскладка буфера) |
| `nineties` | до 2007 (ретро) | классический V | есть (не разобрана) |

- **Все 24 сетки полевых — одна топология**: 3160 вершин, 5962 треугольника; рамка x ±0,51 м, y 0,93–1,72 м
  (метры, Y вверх, +Z — грудь, руки опущены).
- Внутри кроя заправка (`notuck`, `fulltuck`, `lefttuck`, `righttuck`) и размер (`large`, `small`) меняют
  только позиции (низ свитера, плечи ±1,5 см); **UV у всех вариантов кроя одинаковы**.
- Между кроями UV почти те же («крест»: спина сверху, рукава по бокам, грудь снизу, ворот в центре,
  шнуровка — угол 0,85…1 × 0,8…1); расхождение до 0,01 (rbk) и 0,02 (nineties).
  Форма отличается до 2–3 см — у ворота и низа.
- Вратари: `goalie_jersey_<крой>_notuck` (3348 вершин, шире: x ±0,54) и `goalie_jerseytie_<крой>`.
  Превью меню: `player_static_jersey`, `_nineties`.
- **Своих сеток воротника у клубов нет.** Вид ворота задают крой (через папку комплекта), текстура и, по флагу
  комплекта, сетка шнуровки. Где этот флаг лежит (EBX формы), не разбиралось: нужны типы EBX.

## 2. NHL 24: комплекты клубов

Путь: `content/character/skater/league/nhl/<клуб>/<крой>/<комплект>/`. Крой задаётся папкой.

- Всего **570 комплектов** в 39 папках: 32 клуба + All-Star (`atlantic`, `central`, `metropolitan`, `pacific`,
  `east`, `west`) + `legends`.
- По кроям: adidas — 246, rbk — 194, nineties — 130.
- Имена комплектов:
  - `home`, `away`, `three` — дом, выезд, третья;
  - `two`, `four`…`nine` — прошлые альтернативы и исторические;
  - `twentytwo`, `twentythree` — спецформы последних сезонов.

  Что есть что, видно на листе `game/work/nhl24/compare/nhl24_kits_adidas.png`: все adidas-комплекты 32 клубов
  на сетке NHL 24, вид спереди.

**Текстуры на комплект** (форматы — PS4 BCn, мипы полные):

| текстура | размер, формат | что |
|---|---|---|
| `jersey_*_color` | 2048² BC1 sRGB | готовый свитер: цвет, полосы, все нашивки |
| `jersey_*_normal`, `_coeff` | 2048² (BC5 / BC1) | рельеф и параметры материала |
| `pant_*_color/normal/coeff` | 2048² | шорты |
| `sock_*_color` | 1024² | гетры |
| `font_*_color/normal/coeff` | 1024² | атлас номеров и букв — **та же раскладка, что у EA в Legacy (512²), ×2** |
| `helmetlogo_*_N_color` | 1024×512 | наклейка на шлем (у SEA — Amazon) |
| у 122 комплектов adidas (с 2022–23): `jersey/pant/sock_*_base_*` | как выше | основа без нашивок |
| `branding_jersey_*_N_color/normal/coeff` (+ `_array`) | 512² BC3 sRGB | нашивки слоями: герб, плечи, щит NHL, спонсор, … |

EBX рядом: `stamp_jersey_*` (раскладка слоёв), `*_hq_asp`, `*_doublesided_asp`.
Номера и фамилии на свитер не запечены — как и в Legacy: атлас шрифта плюс раскладка.

**Таблица комплектов** (звёздочка — чанк текстуры свитера не найден без TOC, см. §7):

| клуб | adidas | rbk | nineties |
|---|---|---|---|
| anaheim | home, away, three, two, four, twentytwo, twentythree | home, away, three, two, four, five | home, away, three, two |
| arizona | home, away, three, two, four, twentytwo, twentythree | home, away*, three, four, five | home, away, three, four* |
| boston | home, away, three, two, four, five, twentytwo, twentythree | home, away, three, two, four | home, away, three, two |
| buffalo | home, away, three, two, four, five, six, seven, twentytwo, twentythree | home, away*, three, two, four | home, away, three*, two |
| calgary | home, away*, three*, two, twentytwo, twentythree | home, away, three, two | home, away, three, four*, five |
| carolina | home, away, three, two, four, five, twentytwo, twentythree | home, away, three, two, four | home, away*, three, four* |
| chicago | home, away, three, two, twentytwo, twentythree | home, away, three, four, five, six, seven | home*, away*, three, two, four |
| colorado | home, away*, three, two, twentytwo, twentythree | home, away, three, two, four | home, away*, three, two, four* |
| columbus | home, away*, two, twentytwo, twentythree | home, away, two | home, away*, two |
| dallas | home, away, three, two, twentytwo, twentythree | home, three, two, four | home, away*, three, four*, five*, six, seven, eight, nine |
| detroit | home, away, two, twentytwo, twentythree | home, away, three, two, four, five | home, away*, three |
| edmonton | home*, away*, three, two, four, five*, twentytwo*, twentythree | three*, two, four | home, away*, three, two, four* |
| florida | home, away, twentytwo, twentythree | home, away*, three, four, five, six | home, away*, two |
| losangeles | home, away, three*, two, four, five, twentytwo, twentythree | home, two, four, five, six, seven | home, away, three, two, four*, five, six |
| minnesota | home, away, two, twentytwo, twentythree | home, away, three, two, four | home, away*, two |
| montreal | home, away, three, two, twentytwo, twentythree | home, away, two | home, away, three, two |
| nashville | home, away, three, two, twentytwo, twentythree | home, away, three, two, four, five | home, away, two |
| newjersey | home, away, three, two, twentytwo, twentythree | home, away*, three, two | home, away*, three, four, five, six |
| nyi | home, away, two, twentytwo, twentythree | home, away*, three, two, five, six | home, away*, three, two, four* |
| nyr | home, away, three, two, twentytwo, twentythree | home, away, three, two, four | home, away, three, two, four* |
| ottawa | home, away*, three, two, four*, twentytwo, twentythree | home, away, three, four | home, away, three, two |
| philadelphia | home, away*, three, two, six, seven, twentytwo, twentythree | home, three, four, five*, six, seven | home, away*, two |
| pittsburgh | home, away, three, two, four, five, twentytwo, twentythree | home, away*, two, four, five, six, seven, eight | home, away*, three, four*, five, six |
| sanjose | home, away, three, two, four, five*, twentytwo, twentythree | home, away*, three, two, four, five | home, away*, two |
| seattle | home, away, twentythree | — | — |
| stlouis | home, away, three*, two, four, twentytwo, twentythree | home, away*, three, two, four, five | home, away*, three, four |
| tampabay | home, away, three, two, twentytwo, twentythree | home, away*, three, four, five | home, away* |
| toronto | home, away, three, two, four, five, six, seven, twentytwo, twentythree | home, away*, three, four, five, six, seven, eight*, nine | home, away*, three, two, four, five |
| vancouver | home, away, three, two, four, five*, six, twentytwo, twentythree | home, away, three, two, four | home, away*, three, two, four*, five*, six |
| vegas | home, away, three, two, twentytwo, twentythree | — | — |
| washington | home, away, three, two, four, five, twentytwo, twentythree | home, away*, three, four*, five | home, away |
| winnipeg | home, away, three, two, twentytwo, twentythree | three, four*, five | three, four* |

All-Star и `legends` — в сводке `game/work/nhl24/catalog/kits_table.md`.

## 3. NHL Legacy: модели свитеров

Подробности — в `docs/uniforms.md` и `docs/player-models.md`.

Сетки — `rendering/jersey/jersey_<вратарь>_<стиль>_<2|рука ловушки>_<заправка>_<наплечники>_<LOD>.rx2`, архив
`nocacherender`. Шнуровка — `jerseytie_<вратарь>_<стиль>_<LOD>`, флаг `stockteamjerseys.hastie`. Нижняя
рубашка — `shirt_*`.

| сетка (LOD _2) | вершин | ворот | где используется |
|---|---|---|---|
| `jersey_0_1_2_T_P_2` — стиль 1, Reebok Edge | 2055 | V Edge с короткой вставкой | все комплекты `style 1`: клубы НХЛ, SEA/VGK (наши) |
| `jersey_0_0_2_T_P_2` — стиль 0, «ретро» | 1896 | глубокий V, мешковатый крой | `style 0`: ретро- и винтажные формы, сборные; **для переноса не берём** |
| `jersey_1_1_H_0_0_2` — вратарь, стиль 1 | 1947 | как у полевого стиля 1 | вратари |
| `jerseytie_0_1_2`, `jerseytie_1_1_2` — шнуровка | 208 | бантик со шнурками | комплекты с `hastie 1` |

- **У кроя Reebok (стиль 1) одна сетка ворота на все клубы.** Варианты сетки — только заправка T 0…3 и
  наплечники P 0/1.
- UV у всех вариантов стиля 1 общие (у P 0 — сдвиг до 0,012), у вратарского — до 0,006.
- «Длинный тонкий вырез» (как у нынешней SEA из czkit), «клин» (как у «Питтсбурга» EA) и прочие вырезы —
  **рисунок V-вставки в `jersey_cm`, геометрии у них нет**. Шнуровка — отдельная сетка поверх ворота.
- Развёртка шнуровки у обеих игр лежит в углу той же текстуры свитера (0,82…0,95 × 0,79…0,95). Поэтому при
  переносе её цвет берётся из шнуровки NHL 24.

**Текстуры комплекта Legacy:**
- `rendering/jersey/texlib_S_A_V.rx2`:
  - `jersey_*_cm` — 1024² DXT1;
  - `_sm` — 1024² DXT1;
  - `_0_nm` — 1024² DXN;
  - шрифт: `font_cm` 512² DXT5, `_nm`, `_sm`.
- `name_*_cm` — 256², карта мест номеров и фамилии.
- Шорты: `pant_*` 512².
- Гетры: `sock_*_cm` 1024×512.
- Наклейка на шлем: `logo_*` 256×128.

Подробно — `docs/uniforms.md`. Сборка в игру — `tools/kitpaint.py pack`: PNG ровно размера слоя шаблона.

## 4. Сравнение сеток и соответствие

Ближайшая точка поверхности (вершины Legacy → свитер NHL 24 той же стороны) и расхождение UV в соответствующих
точках:

| Legacy | NHL 24 adidas | NHL 24 rbk | NHL 24 nineties |
|---|---|---|---|
| стиль 1 (P 1) | 1,0 см (95 % — 4,1); UV 0,024 / 90 % 0,069 | 1,0 см; UV 0,025 / 0,071 | 0,9 см; UV 0,024 / 0,068 |
| стиль 1 (P 0) | 1,1 см (95 % — 4,2); UV 0,024 / 0,070 | 1,1 см; UV 0,025 / 0,072 | 1,0 см; UV 0,024 / 0,069 |
| стиль 0 (P 1) | 2,1 см (95 % — 5,3); UV 0,046 / 0,139 | 2,2 см; UV 0,047 / 0,328 | 2,1 см; UV 0,046 / 0,137 |

Выводы:
- UV похожи, но копировать текстуру «как есть» нельзя: 25–70 пикселей сдвига на 1024². Нужен перенос через 3D.
- **Стиль 1 Legacy ближе всего ко всем трём кроям NHL 24.**

| NHL 24 | → Legacy | ворот | что решить |
|---|---|---|---|
| adidas (все клубы, 2017+) | стиль 1 | круглый ворот → V Edge: в V Legacy ложится тёмная внутренняя сторона ворота NHL 24 | оставить так (выглядит как внутренняя сторона) или красить V-вставку правилом |
| adidas с завязками | стиль 1 + `jerseytie`, `hastie 1` | завязки → бантик Legacy | профиль `laces`: щит NHL на 9 см ниже |
| rbk (Edge-ретро) | стиль 1 | V ↔ V Edge — совпадение по эпохе | — |
| nineties (ретро 90-х) | стиль 1 | классический V ↔ V Edge | по смыслу ближе стиль 0, но он мешковатый — пользователь просил не брать |

Клубов «без пары» нет: у всех 32 есть adidas-комплекты, и все они садятся на стиль 1. Решения нужны общие, а не по
клубам:
- что делать с V-вставкой: тёмная от NHL 24 или цвет клуба по правилу;
- какие комплекты NHL 24 со шнуровкой — флаг в EBX формы, пока не прочитан;
- что делать с ретро-комплектами `nineties`.

## 5. Метод переноса — гибрид (`tools/fb/kit_hybrid.py`)

1. **Основа** — `jersey_*_base_color` (2048², без нашивок) переносится на развёртку Legacy через 3D:
   - сначала соответствие считается в вершинах Legacy — ближайшая точка свитера NHL 24 с нормалью той же стороны;
   - внутри треугольников оно кусочно-линейное, поэтому края полос не «дрожат»;
   - треугольники на швах UV NHL 24 считаются по текселям (у SEA их 524 из 3894);
   - сверхвыборка 2×2, растекание цвета за края островов.
2. **Нашивки** — связные участки «готовый `jersey_*_color` минус основа» (у SEA их 7: герб, Muckleshoot,
   2 якоря, щит NHL, adidas сзади, бирка).
   - Центр и касательная рамка (якобиан UV→3D треугольника) берутся на свитере NHL 24.
   - Дальше — сдвиг, масштаб и поворот по правилам, затем посадка на ближайшую точку свитера Legacy.
   - Рисунок проецируется на поверхность Legacy по текселям — плоская декаль в касательной плоскости. Поэтому
     локальный масштаб и поворот учтены, на швах развёртки разрывов нет.
   - На шнуровку декали не ложатся.
3. **Правила** — `tools/fb/kit_rules.toml`:
   - нашивка опознаётся по центру на развёртке NHL 24;
   - ключи: `offset_cm` [x, y, z] — мировые оси, `scale`, `rotate_deg`, `enabled`;
   - порядок применения: `[patch.*]` ← `[profile.<имя>.*]` (`--profile laces`) ← `[club.<КОД>.<форма>.*]`.
   - Сейчас:
     - щит NHL у горловины — −4 см: у Legacy там вставка воротника, без сдвига щит уходит под воротник;
     - со шнуровкой — −9 см, под шнурками.

Проверено на SEA home (листы в `game/work/nhl24/compare/`):

| лист | что |
|---|---|
| `sea_home_best.png` | NHL 24 / наш нынешний / вариант Б (всё через 3D) / гибрид — спереди, сзади, горловина крупно |
| `sea_home_render.png` | 2×4 — спереди и сзади |
| `sea_home_uv.png` | развёртки 1024² |
| `sea_home_collars.png` | гибрид на всех вариантах сетки стиля 1: заправка 0–3, наплечники 0/1, вратарь, шнуровка |
| `sea_home_laces_rule.png` | шнуровка: щит −4 см и −9 см |
| `jersey_models.png` | модели обеих игр, спереди и ворот крупно, клетка и SEA |
| `nhl24_kits_adidas.png` | все adidas-комплекты 32 клубов |

Итоговая развёртка SEA home — `sea_home_best_jersey_cm.png` (1024²). Её можно отдать в `kitpaint.py pack` как
`jersey_cm`. `sm`/`nm` и остальные слои пока свои, Legacy.

Сетки NHL 24 нужны только для расчёта. В игру ставятся одни текстуры в развёртке Legacy.

## 6. Что осталось по формам

- **Шорты, гетры, наклейка на шлем, шрифт** — тем же методом:
  - шорты и гетры — через 3D;
  - шрифт — уменьшить 1024 → 512, раскладка та же;
  - наклейка — 1024×512 → 256×128.
- Остальные карты свитера: `sm` и `nm` Legacy — свои, от шаблона, со швами и рельефом старых нашивок. Для нового
  свитера стереть рельеф нашивок EA (как в `kitpaint`) или перенести `normal` NHL 24 через 3D — тот же перенос,
  но в касательном базисе.
- Флаг шнуровки и раскладка нашивок (`stamp_jersey_*`) в EBX — нужны типы EBX (в дампе их нет, они в exe).
  Пока нашивки находятся сравнением «готовый минус основа». У 124 комплектов adidas без `base` основу можно
  получить, замаскировав нашивки на готовом свитере (участки, отличные от соседей; на всех adidas-комплектах
  они лежат в одних местах развёртки).

## 7. Пробелы дампа

После удаления 09.10 не вернулись 9 оглавлений (`*.toc`, ≈37 МБ). Список для повторного снятия с PS4 —
`game/work/nhl24/need_from_ps4.txt`.

Без них места чанков ищутся по sha1 манифеста — это sha1 сжатого потока в CAS вместе с заголовками блоков:
- найдено 21 835 из 29 809 чанков без места;
- из 570 свитеров клубов не найдены 103 (звёздочки в §2).

С TOC найдутся все.
