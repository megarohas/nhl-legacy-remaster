"""Экипировка игроков из NHL 27 → NHL Legacy: клюшка, коньки, шлем, краги, шорты, визор, обмотка крюка, заправка свитера
и гетр. Базы сборки (out, out-ahl32) и сохранения пользователя (состав ROSTER, франшиза DYNASTY).

Просьба пользователя 23.10.2026: всем игрокам базы взять из NHL 27 всё, что там есть об экипировке, — и в сохранённый
состав, и во франшизу (Миннесота). Правки самого пользователя в редакторе игры можно перезаписать.

    python tools/legacy_data/equipment27.py                          # проба по out и out-ahl32: что изменится, отчёт
    python tools/legacy_data/equipment27.py out --write              # запись (копия базы — legacy-data/equipment27/backup/)
    python tools/legacy_data/equipment27.py save "…/ROSTER 2026…"    # проба по сейву (ROSTER или DYNASTY)
    python tools/legacy_data/equipment27.py save СЕЙВ --out КОПИЯ    # результат — в копию, исходник не трогается
    python tools/legacy_data/equipment27.py save СЕЙВ --write        # на месте; копия до правки — legacy-data/backup-saves/
    python tools/legacy_data/equipment27.py table [stick|skate|helmet|glove]   # модели NHL 27 → номера Legacy
    python tools/legacy_data/equipment27.py mappings                 # перечитать таблицы моделей из дампа NHL 27

Общие опции: --fields stick,gloves,… (только эти поля), --generic (брать и шаблон EA, см. ниже), --db27 nhl_game.db,
--show N (N примеров на поле), --who Фамилия (что у этих игроков станет).

Откуда (разбор 23.10.2026, docs/equipment27.md).
- База NHL 27 (tools/roster/nhl27.py): exhibitionskaterequipment / exhibitiongoalieequipment по game_id. Номера моделей
  клюшки (stick), коньков (skatebrand), шлема (helmetbrand) и краг (gloves) — ключи таблиц content/common/configs/mappings/
  player_{stick,skate,helmet,glove}_mapping дампа (ebx: массив u32 число, записи по 16 байт: u64 смещение имени от поля,
  u32 номер, u32 0; разобраны 23.10). Номера у EA сквозные с NHL 14: 105 у обеих — bauer_vapor_1x, 82 у краг — тоже, 23 у
  шлема — CCM Fitlite. Кэш — game/work/equipment27/mappings27.json (команда mappings).
- Игрок Legacy ↔ NHL 27 — по имени, фамилии и дате рождения (без диакритики, roster.common.norm), иначе по фамилии и дате
  рождения при той же первой букве имени (Alex / Alexander), иначе по имени, фамилии и году, если в дате NHL 27 переставлены
  день и месяц или неверно одно из них (у EA такие ошибки: Cuylle, Zellweger, Weegar); только однозначные пары с обеих
  сторон, полевой к полевому, вратарь к вратарю.
- Шаблон EA: у 5050 из 7432 полевых NHL 27 (почти все юниоры, европейцы, часть АХЛ) экипировка — заготовка генератора:
  лента крюка цвета 0xDFDDD7 (у настоящих — 0xE7E7E7 белая или 0x202020 чёрная), Vapor FlyLite, Re-Akt 3D, обмотка
  smalltoe, гетры 0. Поле такого игрока, равное значению шаблона, не берётся (это не его экипировка; в Legacy остаётся
  прежнее); отличное от шаблона — берётся. --generic — брать и шаблон.

Поля (полевые; Legacy ← NHL 27):
- stick ← stick: модель → слот каталога Legacy по плану tools/fb/stick_slots.toml (from = "nhl27:<модель>"); модели не
  из плана — слот той же линейки (STICK_LINES), иначе марки; спецклюшки (casual_graphic_*, special_*) — не берутся;
- skatebrand ← skatebrand: так же по tools/fb/skate_slots.toml и SKATE_LINES;
- helmetbrand ← helmetbrand: моделей NHL 27 в Legacy нет — шлем Legacy той же марки и вида (HELMET_LINES; Re-Akt → 21,
  Fitlite → 23, Tacks → 20, Warrior → 25); JOFA — 7 только без визора (у ретро-шлема 7 нет сетки визора), иначе 1;
  generic_default — не берётся;
- gloves ← gloves: номер NHL 27, если такие краги есть в Legacy (LEGACY_GLOVES, ids общие), иначе — по линейке
  (GLOVE_LINES; Vapor → 82, Supreme → 80, Nexus → 83, Jetspeed → 53, Tacks → 68, Covert → 66, Alpha → 58);
- pantsbrand ← pantsbrand (как есть: сверено на 1077 игроках, бывших и в базе EA 2015, — значения совпадают);
- pantstypecode ← pantstypecode: looseshort 0 / tightshort 2 → 0 (короткие), looselong 1 / tightlong 3 → 1;
- jerseytuck, skatesocktuck ← те же поля (перечисления совпадают: player_jersey_tuck_mapping, player_sock_tuck_mapping);
- visortype ← faceprotectortype (player_visor_type_mapping): −1 нет → 2; straight 0 → 0; curved 1, aviator 3 → 1
  («авиатор»); large, tilted, hightilted, full и решётки 7–10 → 0 (обычный: решёток у полевых Legacy нет);
- visorcolor ← visorcolor (0 прозрачный, 1 тёмный…, как есть до 14);
- sticktapecolor ← stickbladetapecolor (цвет RGB) и stickbladetapestyle (вид обмотки крюка): чёрная — 0 (частичных
  чёрных у Legacy нет); белая — по виду: smalltoe, notoe, rezztek → 1 (вся), largetoe → 4 (носок голый), half → 3
  (середина), halfnotoe → 6 (пятка голая) — по развёртке масок player_sticktape_blade_common_<вид>_alpha (доля длины
  крюка от пятки: largetoe 0–0,70, smalltoe 0–0,89, notoe 0–1, half 0,31–0,89, halfnotoe 0,31–1; варианты Legacy —
  tools/tapestyles.py); синяя, зелёная, голубая — 2, 5, 7. Игроки tools/legacy_data/tape_players.json — код оттуда
  (решение пользователя главнее).
Вратари: jerseytuck и sticktapecolor (0 чёрная, 1 белая). Щитки, блин, ловушка, клюшка и маска вратаря — командные
(legacy_data/goalie_gear.py, решение пользователя 12.10), здесь не трогаются.
Не переносятся: shoulderpads, skaterocker, stickcurve, stickflex — в NHL 27 у всех одно значение (0, 1, 2, 1), сведений
об игроке нет; у NHL 27 есть, а у Legacy нет полей: лента рукояти (stickshafttape*), шнурки и рама конька, защита
коньков, капа, шея, уши, цвета краг и шлема.

Запись.
- Базы (out/db/nhlng.db, out-ahl32/db/nhlng.db): копия до записи — game/work/legacy-data/equipment27/backup/<набор>-
  <время>/; после записи — CRC, повторный план пуст, вне полей экипировки всё байт в байт; draft_roster.db рядом —
  заново (legacy_data/draft_roster.py). Этап build-all «equip27» — после useredits, tape и players.
- Сейв: ROSTER (exhibition*, по game_id) или DYNASTY (leagueplayerbiotable / leagueskaterequipment /
  leaguegoalieequipment по index) — то, что есть в файле. Без --out/--write — проба. --out — результат в другой файл;
  --write — на месте, копия — game/work/legacy-data/backup-saves/<сейв>-<время>/; при запущенной игре на месте не пишет.
  После записи — CRC базы и обёртки ZlibV4, размер файла тот же, повторный план пуст, прочие таблицы и поля — как были;
  при ошибке исходник возвращается. Схема сейва — nhl-legacy-port/userdata/cache/guest/db/nhlng-meta.xml (--meta).
Отчёт — game/work/legacy-data/equipment27/<набор или сейв>.json. Повтор ничего не меняет.
"""
import argparse
import colorsys
import glob
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
import tomllib
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
REPO = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
os.environ.setdefault('NHL_GAME', 'legacy')
from roster.common import set_game  # noqa: E402
set_game('legacy')
from roster import nhl27  # noqa: E402
from roster.common import norm  # noqa: E402
from tdb import SaveFile, Tdb, load_meta  # noqa: E402

W_DIR = os.path.abspath(os.environ.get('LEGACY_DATA_WORK') or os.path.join(REPO, 'game', 'work', 'legacy-data'))
WORK = os.path.join(W_DIR, 'equipment27')                        # отчёты, копии баз
MAP_CACHE = os.path.join(REPO, 'game', 'work', 'equipment27', 'mappings27.json')
CACHE_META = os.path.join(REPO, 'nhl-legacy-port', 'userdata', 'cache', 'guest', 'db', 'nhlng-meta.xml')
STICK_PLAN = os.path.join(TOOLS, 'fb', 'stick_slots.toml')
SKATE_PLAN = os.path.join(TOOLS, 'fb', 'skate_slots.toml')
TAPE_SPEC = os.path.join(HERE, 'tape_players.json')
MAPPINGS = {'stick': 'player_stick_mapping', 'skate': 'player_skate_mapping', 'helmet': 'player_helmet_mapping',
            'glove': 'player_glove_mapping', 'tape': 'player_stick_tape_blade_mapping',
            'visor': 'player_visor_type_mapping', 'cage': 'player_cage_type_mapping',
            'jersey_tuck': 'player_jersey_tuck_mapping', 'sock_tuck': 'player_sock_tuck_mapping',
            'pant_type': 'player_pant_type_mapping'}
MAP_DIR = 'content/common/configs/mappings/'

E27S, E27G, B27 = 'exhibitionskaterequipment', 'exhibitiongoalieequipment', 'exhibitionplayerbiotable'
GENERIC_TAPE = 0xDFDDD7          # лента крюка заготовки EA (5050 полевых NHL 27); у настоящих — 0xE7E7E7 / 0x202020
SPECIAL = ('casual_', 'special_', 'xbox_', 'ps3_', 'generic_', 'null', 'nhl_', 'intl_')   # спецмодели, пустышки

# ---------------------------------------------------------------- соответствия моделей (23.10.2026)
# Клюшки и коньки: сначала план слотов (fb/stick_slots.toml, fb/skate_slots.toml: модель NHL 27 → её слот), иначе
# самый длинный подходящий префикс ниже (линейка, потом марка). Слот — номер каталога Legacy (буква редактора — в плане).
STICK_LINES = {
    'bauer_nexus': 108, 'bauer_supreme': 111, 'bauer_one': 111, 'nikebauer_one': 111,      # One95 / TotalOne — Supreme
    'bauer_vapor': 105, 'bauer_original_vaporflylite': 105, 'bauer_twitch': 70,
    'bauer_proto': 105, 'bauer_pulse': 105, 'bauer_agent': 105, 'bauer_pastrnak': 105, 'bauer_': 105,
    'ccm_jetspeed_ft8': 102, 'ccm_jetspeed_ft9': 102, 'ccm_jetspeed': 86,                  # FT8 и новее — E, прочие — F (FT7)
    'ccm_rbz': 86, 'ccm_uplus': 86,                                                         # предшественники Jetspeed
    'ccm_ftghost': 72, 'ccm_xfghost': 72,
    'ccm_ribcor_trigger10': 112, 'ccm_ribcor': 103, 'ccm_one_ribcor': 103, 'reebok_ribcor': 103, 'reebok_': 103,
    'ccm_tacks': 87, 'ccm_supertacks': 99, 'ccm_ultratacks': 99, 'ccm_vizion': 106, 'ccm_': 86,
    'true_hzrdus': 104, 'true_catalyst': 85, 'true_projectx': 82, 'true_': 85, 'easton_': 74,
    'sherwood_rekker': 109, 'sherwood_m90rekker': 109, 'sherwood_wooden': 36, 'sherwood_': 95, 'swd': 95,
    'stx_stallion': 110, 'stx_surgeon': 107, 'stx_': 107,
    'warrior_covert': 84, 'warrior_alpha': 98, 'warrior_dynasty': 98,                      # слот T был Dynasty HD1
    'warrior_novium_super': 93, 'warrior_novium': 100, 'warrior_': 84,
    'titan_': 35,
}
SKATE_LINES = {
    'bauer_vapor': 47, 'bauer_supreme_shadow': 70, 'bauer_supreme': 48, 'bauer_nexus': 48, 'bauer_one': 48, 'bauer_': 47,
    'ccm_jetspeed_ft8': 43, 'ccm_jetspeed_ft9': 43, 'ccm_vizion': 43, 'ccm_jetspeed': 41, 'ccm_rbz': 41,
    'ccm_upluscl': 41, 'ccm_supertacks': 72, 'ccm_tacks': 39, 'ccm_ribcor': 44, 'ccm_': 41, 'reebok_': 44,
    'true_catalyst': 45, 'true_hzrdus': 46, 'true_tfpro': 74, 'true_custom': 74, 'true_': 45,
    'easton_': 45, 'graf_': 46,                                                             # слоты G и H были Easton и Graf
}
# Шлемы Legacy (ref/nhl-modding-studio/defs/enums/helmet-model.toml; сетки и визоры — cacherender/rendering/helmet):
# 1 Bauer 4500, 6 CCM V10, 7 JOFA (ретро, без визора), 18 Bauer IMS, 19 Bauer 5100, 20 CCM (Resistance; у NHL 27 номер 20 —
# ccm_tacks_710), 21 Bauer Re-Akt, 23 CCM Fitlite, 24 Easton Synergy, 25 Warrior Krown PX3. У EA при переносе в Legacy
# Fitlite 3DS (26) → 23 у всех 54, Re-Akt 3D (38) → 21 у всех 327 (сверка с базой EA 2015).
HELMET_LINES = {
    'bauer_reakt': 21, 'bauer_vapor': 21, 'bauer_ims': 18, 'bauer_4500': 1, 'bauer_': 21,
    'ccm_fitlite': 23, 'ccm_tacks': 20, 'ccm_v10': 6, 'ccm_': 20, 'reebok_': 23,
    'warrior_': 25, 'true_': 24, 'easton_': 24, 'jofa_': 7,
}
JOFA, JOFA_VISOR = 7, 1          # у шлема 7 нет сетки визора: с визором — Bauer 4500 (классический)
# Краги Legacy, у которых есть модели (cacherender/rendering/glove/glove_<N>_*), кроме промо EA (70–77, 100, 101: у NHL 27
# под этими номерами другие краги). Номер NHL 27 из этого списка берётся как есть (номера общие).
LEGACY_GLOVES = {15, 18, 20, 21, 23, 24, 25, 27, 28, 29, 30, 33, 38, 39, 40, 41, 42, 43, 44, 45, 46, 48, 49, 51, 52, 53,
                 54, 55, 56, 57, 58, 59, 61, 62, 65, 66, 67, 68, 69, 80, 81, 82, 83}
GLOVE_LINES = {
    'bauer_vapor': 82, 'bauer_supreme': 80, 'bauer_nexus': 83, 'nexus_': 54, 'bauer_one': 42, 'bauer_4roll': 24,
    'bauer_apx': 61, 'bauer_x60': 38, 'bauer_': 82,
    'ccm_jetspeed': 53, 'ccm_quicklite': 53, 'ccm_cl': 53, 'ccm_4roll': 29, 'ccm_tacks': 68, 'ccm_supertacks': 68,
    'ccm_ultratacks': 68, 'ccm_ribcor': 69, 'ccm_': 53,
    'warrior_covert': 66, 'warrior_alpha': 58, 'warrior_dynasty': 58, 'warrior_': 66,
    'true_4roll': 29, 'true_': 81, 'easton_': 81,                                           # TRUE — на место Easton, как клюшки K–M
    'sherwood_': 62, 'newsherwood_': 33, 'stx_stallion': 65, 'stx_surgeon': 67, 'stx_': 67,
    'eagle_': 27, 'graf_': 51, 'winnwell_': 56, 'reebok_': 59, 'rbk_': 59, 'tps_': 23, 'torspo_': 30,
}
# Простые поля
PANT_LENGTH = {0: 0, 1: 1, 2: 0, 3: 1}                     # looseshort, looselong, tightshort, tightlong → 0 короткие, 1 длинные
VISOR = {-1: 2, 0: 0, 1: 1, 3: 1, 2: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0, 10: 0}
# Обмотка: вид NHL 27 → код Legacy у белой ленты (tools/tapestyles.py STYLES). Доли длины крюка от пятки — по маскам NHL 27.
TAPE_WHITE = {0: 4, 1: 1, 2: 1, 3: 3, 4: 6, 5: 1}           # largetoe, smalltoe, notoe, half, halfnotoe, rezztek
TAPE_COLORS = {2: 225, 5: 120, 7: 200}                       # синяя, зелёная, голубая (EA): тон, °

# Перечисления NHL 27, на которых стоят правила выше (таблицы mappings дампа): изменятся в новой игре — инструмент остановится
ENUMS = {'jersey_tuck': {0: 'notuck', 1: 'lefttuck', 2: 'righttuck', 3: 'fulltuck'},          # = jerseytuck Legacy
         'sock_tuck': {0: 'fulltuck', 1: 'notuck', 2: 'fronttuck', 3: 'backtuck'},            # = skatesocktuck Legacy
         'pant_type': {0: 'looseshort', 1: 'looselong', 2: 'tightshort', 3: 'tightlong'},       # PANT_LENGTH
         'tape': {0: 'largetoe', 1: 'smalltoe', 2: 'notoe', 3: 'half', 4: 'halfnotoe', 5: 'rezztek'},   # TAPE_WHITE
         'visor': {0: 'straight', 1: 'curved', 2: 'full', 3: 'aviator', 4: 'large', 5: 'tilted', 6: 'hightilted',
                   9: 'fullshield', 10: 'hybrid'},                                         # VISOR
         'cage': {7: 'full', 8: 'half', 9: 'fullshield', 10: 'hybrid'}}

SKATER_FIELDS = ('stick', 'skatebrand', 'helmetbrand', 'gloves', 'pantsbrand', 'pantstypecode', 'jerseytuck',
                 'skatesocktuck', 'visortype', 'visorcolor', 'sticktapecolor')
GOALIE_FIELDS = ('jerseytuck', 'sticktapecolor')
SOURCE = {'stick': ('stick',), 'skatebrand': ('skatebrand',), 'helmetbrand': ('helmetbrand',), 'gloves': ('gloves',),
          'pantsbrand': ('pantsbrand',), 'pantstypecode': ('pantstypecode',), 'jerseytuck': ('jerseytuck',),
          'skatesocktuck': ('skatesocktuck',), 'visortype': ('faceprotectortype',), 'visorcolor': ('visorcolor',),
          'sticktapecolor': ('stickbladetapecolor', 'stickbladetapestyle')}


def say(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------- таблицы моделей NHL 27 (ebx mappings)

def parse_mapping(d):
    """ebx content/common/configs/mappings/* NHL 27 → {номер: имя}. Массив с 0x84: u32 число записей, записи по 16 байт
    (u64 смещение C-строки имени от начала поля, u32 номер, u32 0) — одинаково у всех 24 таблиц (23.10.2026)."""
    n = struct.unpack_from('<I', d, 0x84)[0]
    out = {}
    for i in range(n):
        o = 0x88 + 16 * i
        rel, key, zero = struct.unpack_from('<QII', d, o)
        if zero or not 0 < o + rel < len(d):
            raise ValueError(f'запись {i}: не тот формат (смещение {rel}, хвост {zero})')
        e = d.index(b'\0', o + rel)
        out[key] = d[o + rel:e].decode('latin1')
    return out


def extract_mappings():
    """Таблицы MAPPINGS из дампа NHL 27 (catalog/scan прохода fb.scan, fb.cas; numpy не нужен) → кэш MAP_CACHE."""
    os.environ['FB_GAME'] = 'nhl27'
    from fb import cas, source
    want = {MAP_DIR + v: k for k, v in MAPPINGS.items()}
    scan = os.path.join(source.CATALOG, 'scan')
    if not os.path.isdir(scan):
        sys.exit(f'нет прохода fb.scan дампа NHL 27 ({scan}): python tools/eaimport.py prepare --game nhl27')
    found = {}
    for fn in sorted(os.listdir(scan)):
        with open(os.path.join(scan, fn), encoding='utf-8') as f:
            for line in f:
                if MAP_DIR in line and '"k": "ebx"' in line:
                    r = json.loads(line)
                    if r['name'] in want and r['name'] not in found:
                        found[r['name']] = r
    miss = sorted(set(want) - set(found))
    if miss:
        sys.exit(f'в дампе нет: {miss}')
    out = {}
    for name, r in found.items():
        ip, c = r['cas'].split('/')[-2:]
        root = source.LAYOUT if not r['cas'].startswith('patch/') else os.path.join(source.PATCH, source.PLATFORM,
                                                                                     'superbundlelayout')
        with open(os.path.join(root, source.PACKAGE + ip[2:], c + '.cas'), 'rb') as f:
            d, _ = cas.read_entry(f, r['ofs'], r['size'])
        out[want[name]] = {str(k): v for k, v in sorted(parse_mapping(bytes(d)).items())}
    os.makedirs(os.path.dirname(MAP_CACHE), exist_ok=True)
    json.dump({'note': 'NHL 27 content/common/configs/mappings: номер → модель (tools/legacy_data/equipment27.py '
                       'mappings); только для личного использования', 'mappings': out},
              open(MAP_CACHE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return {k: {int(a): b for a, b in v.items()} for k, v in out.items()}


def load_mappings():
    if not os.path.isfile(MAP_CACHE):
        say(f'нет {os.path.relpath(MAP_CACHE, REPO)} — читаю таблицы моделей из дампа NHL 27')
        return extract_mappings()
    m = json.load(open(MAP_CACHE, encoding='utf-8'))['mappings']
    return {k: {int(a): b for a, b in v.items()} for k, v in m.items()}


# ---------------------------------------------------------------- модель NHL 27 → номер Legacy

def model_key(name):
    """Имя модели без хвоста _base (у текстур плана: ccm_jetspeed_ft8_base, в таблице моделей — ccm_jetspeed_ft8)."""
    return name[:-5] if name.endswith('_base') else name


def plan_slots(path):
    """{модель NHL 27: слот Legacy} и все слоты плана fb/*_slots.toml."""
    plan = tomllib.load(open(path, 'rb'))['slot']
    by_model = {}
    for n, s in plan.items():
        src = s.get('from', '')
        if src.startswith('nhl27:'):
            by_model[model_key(src[6:])] = int(n)
    return by_model, {int(n) for n in plan}


def by_prefix(name, table):
    best = None
    for p, v in table.items():
        if name.startswith(p) and (best is None or len(p) > len(best)):
            best = p
    return (table[best], f'линейка {best.rstrip("_")}') if best else (None, None)


class Mapper:
    def __init__(self, maps):
        self.maps = maps
        for k, want in ENUMS.items():
            if maps.get(k) != want:
                sys.exit(f'перечисление {MAPPINGS[k]} в дампе другое ({maps.get(k)}), правила рассчитаны на {want}: '
                         'проверьте и поправьте ENUMS и правила полей')
        self.stick_plan, stick_slots = plan_slots(STICK_PLAN)
        self.skate_plan, skate_slots = plan_slots(SKATE_PLAN)
        for table, slots, what in ((STICK_LINES, stick_slots, 'клюшек'), (SKATE_LINES, skate_slots, 'коньков')):
            bad = sorted({v for v in table.values() if v not in slots})
            if bad:
                sys.exit(f'слоты {bad} не из плана {what} — поправьте STICK_LINES/SKATE_LINES')

    def model(self, kind, v):
        """(номер Legacy | None, как) для модели kind ('stick', 'skate', 'helmet', 'glove') с номером NHL 27 v."""
        name = self.maps[kind].get(v)
        if name is None:
            return None, f'номера {v} нет в таблице моделей NHL 27'
        if name.startswith(SPECIAL):
            return None, f'спецмодель {name}'
        key = model_key(name)
        if kind == 'stick' and key in self.stick_plan:
            return self.stick_plan[key], 'план'
        if kind == 'skate' and key in self.skate_plan:
            return self.skate_plan[key], 'план'
        if kind == 'glove' and v in LEGACY_GLOVES:
            return v, 'тот же номер'
        table = {'stick': STICK_LINES, 'skate': SKATE_LINES, 'helmet': HELMET_LINES, 'glove': GLOVE_LINES}[kind]
        x, how = by_prefix(key, table)
        return (x, how) if x is not None else (None, f'нет пары для {name}')

    def name(self, kind, v):
        return self.maps[kind].get(v, f'#{v}')


def tape_code(rgb, style):
    """Цвет ленты крюка NHL 27 (0xRRGGBB) и вид обмотки → код sticktapecolor Legacy."""
    r, g, b = rgb >> 16 & 255, rgb >> 8 & 255, rgb & 255
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    if s > 0.35 and v > 0.25:                                     # цветная: синяя, зелёная, голубая — как у EA
        def gap(c):
            d = abs(h * 360 - TAPE_COLORS[c])
            return min(d, 360 - d)
        code = min(TAPE_COLORS, key=gap)
        if gap(code) <= 30:
            return code, 'цветная'
    if 0.299 * r + 0.587 * g + 0.114 * b < 128:                  # прочие цвета (красная…) — по яркости
        return 0, 'чёрная'
    return TAPE_WHITE.get(style, 1), f'белая, вид {style}'


# ---------------------------------------------------------------- игроки

def people(db, bio, key):
    """({(имя, фамилия, год, месяц, день): [ключ]}, {(фамилия, дата): [(ключ, имя)]}, {ключ: «Имя Фамилия»})."""
    full, last, who = defaultdict(list), defaultdict(list), {}
    for r in db.live_rows(bio):
        ln = db.get_string(bio, 'lastname', r)
        if not ln.strip():
            continue
        fn = db.get_string(bio, 'firstname', r)
        d = (db.value(bio, 'year', r), db.value(bio, 'month', r), db.value(bio, 'day', r))
        k = db.value(bio, key, r)
        full[(norm(fn), norm(ln)) + d].append(k)
        last[(norm(ln),) + d].append((k, norm(fn)))
        who[k] = f'{fn} {ln}'.strip()
    return full, last, who


def pairs(L, bio, key, N):
    """{ключ Legacy: (game_id NHL 27, как)} — однозначные пары (имя + дата, иначе фамилия + дата при той же букве имени)."""
    lf, ll, who = people(L, bio, key)
    nf, nl, _ = people(N, B27, 'game_id')
    out, used = {}, set()
    for k, ks in lf.items():
        if len(ks) == 1 and len(nf.get(k, [])) == 1:
            out[ks[0]] = (nf[k][0], 'имя')
            used.add(nf[k][0])
    for k, ks in ll.items():
        if len(ks) != 1 or ks[0][0] in out or len(nl.get(k, [])) != 1:
            continue
        g, fn27 = nl[k][0]
        if g in used or not ks[0][1] or not fn27 or ks[0][1][0] != fn27[0]:
            continue
        out[ks[0][0]] = (g, 'фамилия')
        used.add(g)
    # у части игроков NHL 27 дата рождения с ошибкой: день и месяц переставлены (Cuylle, Zellweger, Eklund) или одно из
    # них другое (Weegar, Soucy, Perreault, Dvorsky — 23.10.2026) → то же имя и фамилия (одни на всю базу с обеих сторон),
    # тот же год, совпадает день или месяц либо они переставлены
    ln, nn = by_name(lf), by_name(nf)
    for k, (key_l, d) in ln.items():
        if key_l in out or k not in nn:
            continue
        g, e = nn[k]
        if g in used or d[0] != e[0] or not (d[1] == e[1] or d[2] == e[2] or (d[1], d[2]) == (e[2], e[1])):
            continue
        out[key_l] = (g, 'имя и год')
        used.add(g)
    return out, who


def by_name(full):
    """{(имя, фамилия): (ключ, дата)} — у кого имя и фамилия одни на всю базу."""
    out, seen = {}, Counter()
    for k, ks in full.items():
        seen[k[:2]] += len(ks)
        out[k[:2]] = (ks[0], k[2:])
    return {k: v for k, v in out.items() if seen[k] == 1}


def tape_players(L, bio, key):
    """{ключ Legacy: код} — решения пользователя из tape_players.json (фамилия + дата рождения, одна строка)."""
    spec = json.load(open(TAPE_SPEC, encoding='utf-8'))['players']
    rows = defaultdict(list)
    for r in L.live_rows(bio):
        rows[(L.get_string(bio, 'lastname', r).lower(), L.get(bio, 'year', r) + 1900, L.get(bio, 'month', r) + 1,
              L.get(bio, 'day', r) + 1)].append(L.value(bio, key, r))
    out = {}
    for p in spec:
        ks = rows.get((p['last'].lower(), *p['birth']), [])
        if len(ks) == 1:
            out[ks[0]] = p['sticktapecolor']
    return out


def user_edits():
    """{(таблица, game_id, поле): значение} — правки пользователя в редакторе игры (legacy-data/equipment-user/*правки.json,
    legacy_data/user_equipment.py; поздний файл главнее): только для отчёта — какие из них перезапишет NHL 27."""
    out = {}
    for f in sorted(glob.glob(os.path.join(W_DIR, 'equipment-user', '*правки.json'))):
        for e in json.load(open(f, encoding='utf-8')).get('edits', []):
            out[(e['table'], e['game_id'], e['field'])] = e['new']
    return out


def layout(db):
    """Таблицы игрока в файле: (био, ключ, экипировка полевых, экипировка вратарей). Состав и базы — exhibition*,
    франшиза — league* (ключ index)."""
    t = db.by_name
    if 'exhibitionplayerbiotable' in t and 'exhibitionskaterequipment' in t \
            and len(db.live_rows('exhibitionskaterequipment')):
        return 'exhibitionplayerbiotable', 'game_id', 'exhibitionskaterequipment', 'exhibitiongoalieequipment'
    if 'leagueplayerbiotable' in t and 'leagueskaterequipment' in t:
        return 'leagueplayerbiotable', 'index', 'leagueskaterequipment', 'leaguegoalieequipment'
    sys.exit('в файле нет таблиц игроков и экипировки (exhibition* или league*)')


class Source:
    """Экипировка NHL 27: значения по game_id, шаблон EA (самое частое значение поля у заготовок)."""
    def __init__(self, N):
        self.N = N
        self.sk = {N.value(E27S, 'game_id', r): r for r in N.live_rows(E27S)}
        self.gk = {N.value(E27G, 'game_id', r): r for r in N.live_rows(E27G)}
        gen = [r for r in self.sk.values() if N.value(E27S, 'stickbladetapecolor', r) == GENERIC_TAPE]
        fields = {f for fs in SOURCE.values() for f in fs}
        self.generic_rows = len(gen)
        self.default = {f: Counter(N.value(E27S, f, r) for r in gen).most_common(1)[0][0] for f in fields} if gen else {}

    def skater(self, gid):
        r = self.sk.get(gid)
        if r is None:
            return None
        return {f: self.N.value(E27S, f, r) for fs in SOURCE.values() for f in fs}

    def goalie(self, gid):
        r = self.gk.get(gid)
        return None if r is None else {f: self.N.value(E27G, f, r) for f in GOALIE_FIELDS}

    def is_generic(self, v):
        return v.get('stickbladetapecolor') == GENERIC_TAPE


def convert(field, v, M):
    """Значение поля Legacy из значений NHL 27 v → (значение | None, как)."""
    if field == 'stick':
        return M.model('stick', v['stick'])
    if field == 'skatebrand':
        return M.model('skate', v['skatebrand'])
    if field == 'gloves':
        return M.model('glove', v['gloves'])
    if field == 'helmetbrand':
        x, how = M.model('helmet', v['helmetbrand'])
        if x == JOFA and VISOR.get(v['faceprotectortype'], 0) != 2:
            return JOFA_VISOR, how + ', с визором — 1'
        return x, how
    if field == 'pantsbrand':
        return (v[field], 'как есть') if 0 <= v[field] <= 7 else (None, f'значение {v[field]}')
    if field == 'pantstypecode':
        x = PANT_LENGTH.get(v[field])
        return (x, 'длина') if x is not None else (None, f'значение {v[field]}')
    if field in ('jerseytuck', 'skatesocktuck'):
        return (v[field], 'как есть') if 0 <= v[field] <= 3 else (None, f'значение {v[field]}')
    if field == 'visortype':
        x = VISOR.get(v['faceprotectortype'])
        return (x, 'вид визора') if x is not None else (None, f'faceprotectortype {v["faceprotectortype"]}')
    if field == 'visorcolor':
        return (v[field], 'как есть') if 0 <= v[field] <= 14 else (None, f'значение {v[field]}')
    if field == 'sticktapecolor':
        return tape_code(v['stickbladetapecolor'], v['stickbladetapestyle'])
    raise KeyError(field)


def plan(L, N, src, M, args):
    """Что поменять: [(таблица, строка, поле, было, станет, кто)], сводка по полям и игрокам."""
    bio, key, ts, tg = layout(L)
    pr, who = pairs(L, bio, key, N)
    tp = tape_players(L, bio, key)
    want = set(args.fields) if args.fields else None
    rows_s = {L.value(ts, key, r): r for r in L.live_rows(ts)}
    rows_g = {L.value(tg, key, r): r for r in L.live_rows(tg)} if tg in L.by_name else {}
    stat = defaultdict(Counter)
    models = defaultdict(Counter)
    changes = []
    match = Counter(how for _, how in pr.values())
    kinds = Counter()

    def put(table, row, field, new, k, how):
        if want and field not in want:
            return
        lo = L.by_name[table]['lows'].get(field, 0)
        old = L.value(table, field, row)
        w = L.by_name[table]['fields'][field][1]
        if not 0 <= new - lo < 1 << w:
            stat[field][f'не влезает в {w} бит'] += 1
            return
        if old == new:
            stat[field]['уже так'] += 1
        else:
            stat[field]['меняется'] += 1
            changes.append((table, row, field, old, new, who.get(k, k), how))

    for k, (g, _) in sorted(pr.items()):
        if k in rows_s:
            v = src.skater(g)
            if v is None:
                kinds['полевой в Legacy, в NHL 27 — вратарь'] += 1
                continue
            kinds['полевой'] += 1
            generic = src.is_generic(v)
            if generic:
                kinds['полевой с шаблоном EA'] += 1
            for f in SKATER_FIELDS:
                if f not in L.by_name[ts]['fields']:
                    continue
                if f == 'sticktapecolor' and k in tp:
                    put(ts, rows_s[k], f, tp[k], k, 'tape_players.json')
                    continue
                if generic and not args.generic and all(v[s] == src.default.get(s) for s in SOURCE[f]):
                    if not want or f in want:
                        stat[f]['шаблон EA — не берётся'] += 1
                    continue
                x, how = convert(f, v, M)
                if f in ('stick', 'skatebrand', 'helmetbrand', 'gloves'):
                    kind = {'stick': 'stick', 'skatebrand': 'skate', 'helmetbrand': 'helmet', 'gloves': 'glove'}[f]
                    models[f][(M.name(kind, v[SOURCE[f][0]]), x, how)] += 1
                if x is None:
                    if not want or f in want:
                        stat[f][how if how.startswith('спец') or how.startswith('номера') else 'нет пары'] += 1
                    continue
                put(ts, rows_s[k], f, x, k, how)
        elif k in rows_g:
            v = src.goalie(g)
            if v is None:
                kinds['вратарь в Legacy, в NHL 27 — полевой'] += 1
                continue
            kinds['вратарь'] += 1
            for f in GOALIE_FIELDS:
                if f in L.by_name[tg]['fields'] and v[f] in ((0, 1) if f == 'sticktapecolor' else (0, 1, 2, 3)):
                    put(tg, rows_g[k], f, v[f], k, 'как есть')
    for k, code in tp.items():                                  # решения пользователя — и у тех, кого нет в NHL 27
        if k not in pr and k in rows_s and (not want or 'sticktapecolor' in want):
            put(ts, rows_s[k], 'sticktapecolor', code, k, 'tape_players.json')
    edits = user_edits() if key == 'game_id' else {}
    overridden = [{'who': c[5], 'field': c[2], 'user': edits[(c[0], L.value(c[0], key, c[1]), c[2])], 'new': c[4]}
                  for c in changes if (c[0], L.value(c[0], key, c[1]), c[2]) in edits
                  and edits[(c[0], L.value(c[0], key, c[1]), c[2])] == c[3]]
    summary = {'tables': [bio, ts, tg], 'players_legacy': len(rows_s) + len(rows_g), 'skaters_legacy': len(rows_s),
               'user_edits_overwritten': overridden,
               'goalies_legacy': len(rows_g), 'pairs': len(pr), 'pairs_by': dict(match), 'kinds': dict(kinds),
               'fields': {f: dict(c) for f, c in stat.items()},
               'models': {f: [{'nhl27': a, 'legacy': b, 'how': h, 'players': n} for (a, b, h), n in c.most_common()]
                          for f, c in models.items()}}
    return changes, summary


def apply(L, changes):
    for t, row, f, old, new, *_ in changes:
        L.set(t, f, row, new - L.by_name[t]['lows'].get(f, 0))


def check_same(before, after, changes):
    """Вне записанных полей — как было: все таблицы, кроме экипировки, байт в байт; в экипировке — только эти поля."""
    touched = defaultdict(set)
    for t, row, f, *_ in changes:
        touched[t].add((row, f))
    bad = []
    for t, info in before.by_name.items():
        if t not in touched:
            if [before.record(t, r) for r in before.live_rows(t)] != [after.record(t, r) for r in after.live_rows(t)]:
                bad.append(f'{t}: записи изменились')
            continue
        for r in before.live_rows(t):
            for f in info['fields']:
                if (r, f) not in touched[t] and before.get(t, f, r) != after.get(t, f, r):
                    bad.append(f'{t} строка {r} поле {f}')
                    break
    return bad[:10]


# ---------------------------------------------------------------- вывод

def report(name, changes, s, args):
    say(f"{name}: игроков Legacy {s['players_legacy']} (полевых {s['skaters_legacy']}, вратарей {s['goalies_legacy']}), "
        f"пар с NHL 27 {s['pairs']} ({', '.join(f'{k} {v}' for k, v in s['pairs_by'].items())})")
    say('  ' + ', '.join(f'{k} {v}' for k, v in s['kinds'].items()))
    if s['user_edits_overwritten']:
        say(f"  правок пользователя (equipment-user) перезапишется {len(s['user_edits_overwritten'])}: "
            + ', '.join(f"{k} {v}" for k, v in Counter(x['field'] for x in s['user_edits_overwritten']).items()))
    by_field = defaultdict(list)
    for c in changes:
        by_field[c[2]].append(c)
    for f in sorted(s['fields'], key=lambda f: (SKATER_FIELDS + GOALIE_FIELDS).index(f)):
        c = s['fields'][f]
        tables = Counter(x[0] for x in by_field[f])
        say(f"  {f:15} меняется {c.get('меняется', 0):5}, уже так {c.get('уже так', 0):5}"
            + ''.join(f', {k} {v}' for k, v in c.items() if k not in ('меняется', 'уже так'))
            + (f"  ({', '.join(f'{t} {n}' for t, n in tables.items())})" if len(tables) > 1 else ''))
        for t, row, _, old, new, who, how in by_field[f][:args.show]:
            say(f'      {who}: {old} → {new} ({how})')
    if args.who:
        names = [w.lower() for w in args.who]
        for t, row, f, old, new, who, how in changes:
            if any(n in str(who).lower() for n in names):
                say(f'   {who}: {t}.{f} {old} → {new} ({how})')


def save_report(name, changes, s, extra=None):
    os.makedirs(WORK, exist_ok=True)
    out = dict(s, changes=len(changes), **(extra or {}))
    out['examples'] = [{'who': w, 'table': t, 'field': f, 'old': o, 'new': n, 'how': h}
                       for t, _, f, o, n, w, h in changes[:3000]]
    p = os.path.join(WORK, re.sub(r'[^\w.-]+', '_', name) + '.json')
    json.dump(out, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return p


# ---------------------------------------------------------------- команды

def meta_beside(path):
    m = os.path.join(os.path.dirname(path), 'nhlng-meta.xml')
    return m if os.path.isfile(m) else None


def cmd_db(args, N, src, M):
    paths = []
    for s in args.targets or ['out', 'out-ahl32']:
        p = os.path.join(W_DIR, s, 'db', 'nhlng.db') if s in ('out', 'out-ahl32') else os.path.abspath(s)
        if not os.path.isfile(p):
            if s in ('out', 'out-ahl32') and not args.targets:
                continue
            sys.exit(f'нет базы {p}')
        paths.append((s if s in ('out', 'out-ahl32') else os.path.basename(os.path.dirname(os.path.dirname(p)))
                      or os.path.basename(p), p))
    if not paths:
        sys.exit('нет баз out/db и out-ahl32/db (сначала build-all.sh)')
    for name, path in paths:
        meta = meta_beside(path) or args.meta
        if not meta:
            sys.exit(f'{path}: рядом нет nhlng-meta.xml (--meta)')
        data = open(path, 'rb').read()
        L = Tdb(data, load_meta(meta))
        changes, s = plan(L, N, src, M, args)
        report(name, changes, s, args)
        extra = {'db': path}
        if args.write and changes:
            stamp = time.strftime('%Y%m%d-%H%M%S')
            bk = os.path.join(WORK, 'backup', f'{name}-{stamp}')
            os.makedirs(bk, exist_ok=True)
            for f in ('nhlng.db', 'draft_roster.db'):
                if os.path.isfile(os.path.join(os.path.dirname(path), f)):
                    shutil.copy2(os.path.join(os.path.dirname(path), f), os.path.join(bk, f))
            apply(L, changes)
            L.fix()
            A = Tdb(bytes(L.d), load_meta(meta))
            bad = [f'CRC {x}' for x in A.verify()] + check_same(Tdb(data, load_meta(meta)), A, changes)
            again, _ = plan(A, N, src, M, args)
            if again:
                bad.append(f'повторный план не пуст: {len(again)}')
            if bad:
                sys.exit(f'{path}: проверка не прошла, база не тронута: {bad}')
            open(path + '.part', 'wb').write(L.d)
            os.replace(path + '.part', path)
            extra.update(written=True, backup=bk)
            say(f'  записано; копия до записи — {bk}')
            dr = os.path.join(os.path.dirname(path), 'draft_roster.db')
            if os.path.isfile(dr):
                subprocess.run([sys.executable, os.path.join(HERE, 'draft_roster.py'), path, dr], check=True)
        elif args.write:
            say('  база уже такая')
        say(f'  отчёт — {save_report(name, changes, s, extra)}')
    if not args.write:
        say('проба: ничего не записано (--write — записать)')


def game_running():
    try:
        out = subprocess.run(['tasklist'], capture_output=True, text=True, errors='replace').stdout
    except OSError:
        return False
    return any('nhl' in line.lower().split(' ')[0] for line in out.splitlines() if line.strip())


def cmd_save(args, N, src, M):
    save = os.path.abspath(args.targets[0]) if args.targets else None
    if not save or not os.path.isfile(save):
        sys.exit(f'нет файла сейва {save} (нужен файл внутри папки сейва: …/ROSTER <время>/ROSTER <время>)')
    if args.write and args.out:
        sys.exit('или --out (в другой файл), или --write (на месте)')
    if args.out and os.path.abspath(args.out) == save:
        sys.exit('--out совпадает с исходным сейвом — для записи на месте --write')
    meta = load_meta(args.meta or CACHE_META)
    raw = open(save, 'rb').read()
    sf = SaveFile(raw, meta)
    bad0 = sf.verify()
    if bad0:
        sys.exit(f'{save}: сейв не проходит проверку ещё до правки: {bad0}')
    before = Tdb(bytes(sf.db.d), meta)
    changes, s = plan(sf.db, N, src, M, args)
    name = os.path.basename(save)
    report(name, changes, s, args)
    extra = {'save': save}
    if args.out or args.write:
        if not changes:
            say('  сейв уже такой — не пишу')
        else:
            if args.write and game_running():
                sys.exit('запущена игра (tasklist: nhl…) — сейв на месте не пишу; закройте игру')
            apply(sf.db, changes)
            out = sf.bytes(fix=True)
            if len(out) != len(raw):
                sys.exit(f'размер сейва изменился ({len(raw)} → {len(out)}) — не пишу')
            chk = SaveFile(out, meta)
            bad = chk.verify() + check_same(before, chk.db, changes)
            again, _ = plan(chk.db, N, src, M, args)
            if again:
                bad.append(f'повторный план не пуст: {len(again)}')
            if bad:
                sys.exit(f'проверка не прошла, ничего не записано: {bad}')
            dst = os.path.abspath(args.out) if args.out else save
            if args.write:
                bdir = os.path.join(W_DIR, 'backup-saves', f'{name}-{time.strftime("%Y%m%d-%H%M%S")}')
                os.makedirs(bdir, exist_ok=True)
                bak = os.path.join(bdir, name + '.bak')
                open(bak, 'wb').write(raw)
                extra['backup'] = bak
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            open(dst, 'wb').write(out)
            bad = SaveFile(open(dst, 'rb').read(), meta).verify()
            if bad:
                if args.write:
                    open(save, 'wb').write(raw)
                sys.exit(f'после записи проверка не прошла{", сейв возвращён" if args.write else ""}: {bad}')
            extra['written'] = dst
            say(f'  записано: {dst}; CRC базы и обёртки — OK, размер тот же'
                + (f"; копия до правки — {extra['backup']}" if args.write else ''))
    else:
        say('проба: ничего не записано (--out КОПИЯ или --write)')
    say(f'  отчёт — {save_report(name, changes, s, extra)}')


def cmd_table(args, M):
    kinds = args.targets or ['stick', 'skate', 'helmet', 'glove']
    for kind in kinds:
        if kind not in ('stick', 'skate', 'helmet', 'glove'):
            sys.exit(f'table: stick, skate, helmet, glove — не {kind}')
        say(f'== {kind}: номер NHL 27, модель → номер Legacy (как)')
        for v, name in sorted(M.maps[kind].items()):
            if name.startswith(SPECIAL) and not args.all:
                continue
            x, how = M.model(kind, v)
            say(f'  {v:5} {name:36} → {x if x is not None else "—":>4}  {how}')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    doc = __doc__.split('\n\n')
    ap = argparse.ArgumentParser(description=doc[0], formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog='\n\n'.join(doc[1:]))
    ap.add_argument('args', nargs='*', metavar='[db|save|table|mappings] …',
                    help='db (по умолчанию): out, out-ahl32 или путь к nhlng.db; save СЕЙВ; table [вид]; mappings')
    ap.add_argument('--write', action='store_true', help='записать (базы; сейв — на месте, с копией)')
    ap.add_argument('--out', help='save: записать результат в этот файл (исходный сейв не трогается)')
    ap.add_argument('--fields', type=lambda s: [x.strip() for x in s.split(',') if x.strip()],
                    help='только эти поля: ' + ', '.join(SKATER_FIELDS))
    ap.add_argument('--generic', action='store_true', help='брать и значения шаблона EA (заготовки генератора NHL 27)')
    ap.add_argument('--db27', help='база NHL 27 (по умолчанию NHL27_DB или game/work/nhl27/db/nhl_game.db)')
    ap.add_argument('--meta', help=f'схема сейва (по умолчанию {os.path.relpath(CACHE_META, REPO)})')
    ap.add_argument('--show', type=int, default=0, help='показать N изменений на поле')
    ap.add_argument('--who', action='append', help='показать изменения у игроков с этим именем (можно несколько)')
    ap.add_argument('--all', action='store_true', help='table: и спецмодели')
    a = ap.parse_args()
    cmd = a.args[0] if a.args and a.args[0] in ('db', 'save', 'table', 'mappings') else 'db'
    a.targets = a.args[1:] if a.args and a.args[0] == cmd else a.args
    if a.fields:
        bad = [f for f in a.fields if f not in SKATER_FIELDS]
        if bad:
            ap.error(f'--fields: нет полей {bad}; есть {", ".join(SKATER_FIELDS)}')
    if cmd == 'mappings':
        m = extract_mappings()
        say(f'{os.path.relpath(MAP_CACHE, REPO)}: ' + ', '.join(f'{k} {len(v)}' for k, v in m.items()))
        return
    M = Mapper(load_mappings())
    if cmd == 'table':
        cmd_table(a, M)
        return
    N = nhl27.open_db(a.db27)
    src = Source(N)
    if cmd == 'save':
        cmd_save(a, N, src, M)
    else:
        if a.out:
            ap.error('--out — только для save')
        cmd_db(a, N, src, M)


if __name__ == '__main__':
    main()
