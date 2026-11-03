"""Стратегии клубов НХЛ (exhibitionteamstrategies) по спеке team_tactics.json: форчек, средняя зона, давление в атаке и
обороне, оборона, большинство, меньшинство, стиль звеньев и ползунки звеньев (заносить/вбрасывать, разыгрывать/бросать,
энергия, блоки, подключение защитников).

    python tools/legacy_data/team_tactics.py show [--clubs "FLA,CAR"] [--html ФАЙЛ.html] [--png ФАЙЛ.png] [--base БАЗА]
                                                  # сейчас → станет, без записи; таблица для просмотра
    python tools/legacy_data/team_tactics.py db БАЗА.db [БАЗА.db …] [--dry-run] [--clubs …]   # nhlng.db
    python tools/legacy_data/team_tactics.py save СЕЙВ [--write] [--clubs …]                    # сохранённый состав (ROSTER …)
    python tools/legacy_data/team_tactics.py check БАЗА.db|СЕЙВ [--clubs …]                     # всё ли как в спеке (код 1 — нет)
    … [--spec ФАЙЛ.json] [--nhl27 nhl_game.db]

Спека (tools/legacy_data/team_tactics.json) — открытые данные о системах игры клубов (ресёрч, API НХЛ); данных EA в
ней нет. Значение «nhl27» — взять из локальной базы NHL 27 (game/work/nhl27/db/nhl_game.db), только для полей с тем же
смыслом и порядком вариантов (средняя зона, оборона, давление, ловушка/форчек); нет базы NHL 27 — поле остаётся как
есть. Поля, которых в спеке нет, не меняются. Описание, словарь значений и как они найдены — docs/team-tactics.md.

Порядок вариантов — из таблиц exe (названия 83A2EDE0, подсказки и ползунки 8208FF40…82090790, разбор 03.11.2026) и
совпадает с меню NHL 27 (ChoiceValue по возрастанию). Ползунки звеньев в меню 0…10, ловушка/форчек 0…6; в спеке —
значения по звеньям (`lines`: 4 звена или 3 пары), ставятся как есть, поэтому повтор ничего не меняет. Скрытые в меню
поля (forwardN_bias2/6, defenseN_bias3–6, team_bias2–6) не трогаются.

Запись: только exhibitionteamstrategies, строки 0…31 (клубы НХЛ, по abbrname exhibitionteams). Число строк не меняется,
сейв не «damaged». Повтор ничего не меняет; после записи — проверка CRC (сейв — с копией в legacy-data/backup-saves).
Франшизы (DYNASTY, leagueteamstrategies) не трогаются: новая франшиза берёт стратегии из сейва состава при создании.
"""
import argparse
import html
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from tdb import SaveFile, Tdb, load_meta  # noqa: E402

SPEC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'team_tactics.json')
CACHE_DB = os.path.join(ROOT, 'nhl-legacy-port', 'userdata', 'cache', 'guest', 'db', 'nhlng.db')
CACHE_META = os.path.join(os.path.dirname(CACHE_DB), 'nhlng-meta.xml')
NHL27_DB = os.path.join(ROOT, 'game', 'work', 'nhl27', 'db', 'nhl_game.db')
T, S = 'exhibitionteams', 'exhibitionteamstrategies'

# Варианты меню в порядке значений поля (exe: таблица названий 83A2EDE0, подсказки 82090590…82090790).
CHOICES = {
    'forecheck':    ('oz_forecheck', ['1-2-2 passive', '2-3', 'weak side lock', '1-2-2 aggressive']),
    'neutral_zone': ('nz_forecheck', ['1-3-1', '1-4', '1-2-2 red', '1-2-2 blue']),
    'opressure':    ('opressure', ['defend lead', 'conservative', 'standard', 'aggressive', 'full attack']),
    'dpressure':    ('dpressure', ['protect net', 'contain puck', 'normal', 'puck side attack', 'high pressure']),
    'defense':      ('defense', ['collapsing', 'staggered', 'tight point']),
    'pp':           ('pp', ['shooting', 'overload', 'umbrella']),
    'pk':           ('pk', ['passive box', 'large box', 'diamond']),
}
NUMBERS = {'trap_forecheck': ('trap_forecheck_bias', 0, 6)}
LINE_STYLE = ['overload', 'crash the net', 'behind the net']          # offense1…4
# Ползунки: поля звеньев (меню 0…10). Подписи — loc TXT_FORWARD_BIAS*/TXT_DEFENSE_BIAS*.
SLIDERS = {
    'carry_dump':  ([f'forward{i}_bias1' for i in range(1, 5)], 'заносить ↔ вбрасывать'),
    'cycle_shoot': ([f'forward{i}_bias3' for i in range(1, 5)], 'разыгрывать ↔ бросать'),
    'energy':      ([f'forward{i}_bias4' for i in range(1, 5)], 'экономия ↔ энергия'),
    'block':       ([f'forward{i}_bias5' for i in range(1, 5)], 'не блокировать ↔ блокировать'),
    'pinch':       ([f'defense{i}_bias1' for i in range(1, 4)], 'держать синюю ↔ подключаться'),
    'd_shoot':     ([f'defense{i}_bias2' for i in range(1, 4)], 'защитники: разыгрывать ↔ бросать'),
    'pp_carry_dump': (['team_bias1'], 'большинство: заносить ↔ вбрасывать'),
}
SLIDER_MAX = 10
# Поля NHL 27 с тем же смыслом и порядком вариантов: «nhl27» в спеке берёт их (с обрезкой по диапазону Legacy).
NHL27_SAME = {'neutral_zone', 'opressure', 'dpressure', 'defense', 'trap_forecheck'}
LABEL = {'forecheck': 'Форчек', 'neutral_zone': 'Средняя зона', 'trap_forecheck': 'Ловушка ↔ форчек (0–6)',
         'opressure': 'Давление в атаке', 'dpressure': 'Давление в обороне', 'defense': 'Оборона',
         'pp': 'Большинство', 'pk': 'Меньшинство'}


def norm(s):
    return ''.join(ch for ch in s.lower() if ch.isalnum())


def open_db(path, meta=None):
    if meta is None:
        mp = os.path.join(os.path.dirname(path), 'nhlng-meta.xml')
        meta = load_meta(mp if os.path.isfile(mp) else CACHE_META)
    return Tdb(open(path, 'rb').read(), meta)


class Nhl27:
    """Стратегии клубов из базы NHL 27: {название (norm): {поле: значение}}; нет базы — пусто."""

    def __init__(self, path=NHL27_DB):
        self.rows, self.path = {}, path
        if not os.path.isfile(path):
            return
        db = Tdb(open(path, 'rb').read(), load_meta(os.path.join(os.path.dirname(path), 'nhl_game-meta.xml')))
        srow = {db.get(S, 'index', r): r for r in db.live_rows(S)}
        for r in db.live_rows(T):
            name = norm(db.get_string(T, 'teamname', r))
            sr = srow.get(db.get(T, 'index', r))
            if sr is not None and name not in self.rows:
                self.rows[name] = {f: db.get(S, f, sr) for f in db.by_name[S]['fields']}

    def get(self, club_name, key):
        row = self.rows.get(norm(club_name))
        if row is None:
            return None
        field = CHOICES[key][0] if key in CHOICES else NUMBERS[key][0]
        return row.get(field)


def load_spec(path):
    spec = json.load(open(path, encoding='utf-8'))
    bad = []
    for ab, c in spec['clubs'].items():
        for k, v in c.get('team', {}).items():
            val = v['value']
            if k in CHOICES:
                if val != 'nhl27' and val not in CHOICES[k][1]:
                    bad.append(f'{ab}.{k}: «{val}» — нет такого варианта ({", ".join(CHOICES[k][1])})')
                if val == 'nhl27' and k not in NHL27_SAME:
                    bad.append(f'{ab}.{k}: «nhl27» нельзя — в NHL 27 у поля другие варианты')
            elif k in NUMBERS:
                lo, hi = NUMBERS[k][1:]
                if val != 'nhl27' and not (isinstance(val, int) and lo <= val <= hi):
                    bad.append(f'{ab}.{k}: {val} — нужно {lo}…{hi} или «nhl27»')
            else:
                bad.append(f'{ab}.team.{k}: неизвестная настройка')
        for st in (c.get('lines') or {}).get('style', []):
            if st is not None and st not in LINE_STYLE:
                bad.append(f'{ab}.lines: «{st}» — нет такого стиля ({", ".join(LINE_STYLE)})')
        for k, v in c.get('sliders', {}).items():
            if k not in SLIDERS:
                bad.append(f'{ab}.sliders.{k}: неизвестный ползунок')
            elif not (isinstance(v.get('lines'), list) and len(v['lines']) == len(SLIDERS[k][0])
                      and all(isinstance(x, int) and 0 <= x <= SLIDER_MAX for x in v['lines'])):
                bad.append(f'{ab}.sliders.{k}: нужно lines — {len(SLIDERS[k][0])} чисел 0…{SLIDER_MAX} (по звеньям)')
    if bad:
        raise SystemExit('ошибки в спеке:\n  ' + '\n  '.join(bad))
    return spec


def club_rows(db):
    """{abbrname: строка} клубов НХЛ (exhibitionteams 0…31, league 0)."""
    out = {}
    for r in range(min(32, db.by_name[T]['rows'])):
        if db.get(T, 'league', r) == 0:
            out[db.get_string(T, 'abbrname', r)] = r
    return out


def plan(db, spec, names, n27, base=None):
    """[(клуб, строка, поле, было, стало, почему)] по клубам names. base — база с exhibitionteams (у сейва — сам сейв)."""
    tdb = base or db
    rows = club_rows(tdb)
    out, warn = [], []
    for ab in names:
        c = spec['clubs'].get(ab)
        if c is None:
            raise SystemExit(f'{ab}: нет в спеке')
        r = rows.get(ab)
        if r is None:
            raise SystemExit(f'{ab}: нет среди клубов НХЛ базы')
        full = tdb.get_string(T, 'fullname', r)
        cur = {f: db.get(S, f, r) for f in db.by_name[S]['fields']}
        new = dict(cur)
        why = {}
        for k, v in c.get('team', {}).items():
            field = CHOICES[k][0] if k in CHOICES else NUMBERS[k][0]
            val = v['value']
            if val == 'nhl27':
                x = n27.get(full, k)
                if x is None:
                    warn.append(f'{ab}.{k}: нет в NHL 27 — как есть')
                    continue
                hi = len(CHOICES[k][1]) - 1 if k in CHOICES else NUMBERS[k][2]
                new[field] = max(0, min(hi, x))
                why[field] = 'как в NHL 27. ' + v.get('why', '')
            else:
                new[field] = CHOICES[k][1].index(val) if k in CHOICES else val
                why[field] = v.get('why', '')
        style = (c.get('lines') or {}).get('style', [])
        for i, st in enumerate(style[:4]):
            if st is not None:
                new[f'offense{i + 1}'] = LINE_STYLE.index(st)
                why[f'offense{i + 1}'] = c['lines'].get('why', '')
        for k, v in c.get('sliders', {}).items():
            for f, x in zip(SLIDERS[k][0], v['lines']):
                new[f] = x
                why[f] = v.get('why', '')
        for f in sorted(new):
            if f != 'index':
                out.append((ab, r, f, cur[f], new[f], why.get(f, '')))
    return out, warn


def apply(db, pl):
    n = 0
    for _ab, r, f, old, new, _w in pl:
        if old != new:
            db.set(S, f, r, new)
            n += 1
    return n


def name_of(field, v):
    for k, (f, ch) in CHOICES.items():
        if f == field:
            return ch[v] if 0 <= v < len(ch) else f'?{v}'
    if field.startswith('offense'):
        return LINE_STYLE[v] if 0 <= v < len(LINE_STYLE) else f'?{v}'
    return str(v)


def show_text(pl, log=print):
    last = None
    for ab, r, f, old, new, _w in pl:
        if old == new:
            continue
        if ab != last:
            log(f'  {ab}')
            last = ab
        log(f'     {f:22s} {name_of(f, old):>18s} → {name_of(f, new)}')


def write_db(path, db, meta):
    db.fix()
    tmp = path + '.part'
    open(tmp, 'wb').write(bytes(db.d))
    if Tdb(open(tmp, 'rb').read(), meta).verify():
        os.remove(tmp)
        sys.exit(f'{path}: CRC не сходятся после записи — база не тронута')
    os.replace(tmp, path)


def cmd_db(a, spec, n27):
    for path in a.paths:
        db = open_db(path)
        if S not in db.by_name or T not in db.by_name:
            print(f'{path}: нет {S}/{T} — пропуск')
            continue
        pl, warn = plan(db, spec, a.names, n27)
        n = apply(db, pl)
        print(f'{path}: значений изменено {n} из {len(pl)} ({len(a.names)} клубов)')
        for w in warn:
            print('  !', w)
        show_text(pl)
        if n and not a.dry_run:
            write_db(path, db, db.meta)
            print('записано; CRC — OK')
        elif n:
            print('--dry-run: ничего не записано')


def cmd_save(a, spec, n27):
    meta = load_meta(CACHE_META)
    raw = open(a.paths[0], 'rb').read()
    sf = SaveFile(raw, meta)
    pl, warn = plan(sf.db, spec, a.names, n27)
    n = apply(sf.db, pl)
    print(f'{a.paths[0]}: значений изменено {n} из {len(pl)}')
    for w in warn:
        print('  !', w)
    show_text(pl)
    if not a.write or not n:
        print('без --write ничего не записано' if n else 'сейв уже совпадает со спекой')
        return
    out = sf.bytes(fix=True)
    assert len(out) == len(raw), 'размер сейва изменился'
    bdir = os.path.join(ROOT, 'game', 'work', 'legacy-data', 'backup-saves',
                        f'{os.path.basename(a.paths[0])}-tactics-{time.strftime("%Y%m%d-%H%M%S")}')
    os.makedirs(bdir, exist_ok=True)
    bak = os.path.join(bdir, os.path.basename(a.paths[0]) + '.bak')
    open(bak, 'wb').write(raw)
    open(a.paths[0], 'wb').write(out)
    bad = SaveFile(open(a.paths[0], 'rb').read(), meta).verify()
    if bad:
        open(a.paths[0], 'wb').write(raw)
        sys.exit(f'проверка не прошла, сейв возвращён: {bad}')
    print(f'записано; CRC и обёртка — OK; копия до правки — {bak}')


def cmd_check(a, spec, n27):
    path = a.paths[0]
    raw = open(path, 'rb').read()
    db = open_db(path) if raw[:2] == b'DB' else SaveFile(raw, load_meta(CACHE_META)).db
    pl, _ = plan(db, spec, a.names, n27)
    diff = [p for p in pl if p[3] != p[4]]
    print(f'{path}: как в спеке {len(pl) - len(diff)} из {len(pl)}')
    show_text(diff)
    sys.exit(1 if diff else 0)


def cmd_show(a, spec, n27):
    db = open_db(a.base)
    pl, warn = plan(db, spec, a.names, n27)
    for w in warn:
        print('  !', w)
    show_text(pl)
    n = sum(1 for p in pl if p[3] != p[4])
    print(f'изменится значений: {n} у {len({p[0] for p in pl if p[3] != p[4]})} клубов; база {a.base}')
    if a.html:
        write_html(a.html, db, spec, pl)
        print(a.html)
    if a.png:
        write_png(a.png, spec, pl)
        print(a.png)


TEAM_COLS = ['oz_forecheck', 'nz_forecheck', 'trap_forecheck_bias', 'opressure', 'dpressure', 'defense', 'pp', 'pk']
COL_TITLE = {'oz_forecheck': 'Форчек', 'nz_forecheck': 'Средняя зона', 'trap_forecheck_bias': 'Ловушка-ФЧ',
             'opressure': 'Давл. в атаке', 'dpressure': 'Давл. в обороне', 'defense': 'Оборона',
             'pp': 'Большинство', 'pk': 'Меньшинство'}


def by_club(pl):
    out = {}
    for ab, r, f, old, new, w in pl:
        out.setdefault(ab, {})[f] = (old, new, w)
    return out


def write_html(path, db, spec, pl):
    bc = by_club(pl)
    esc = html.escape
    rows = []
    for ab, c in spec['clubs'].items():
        if ab not in bc:
            continue
        v = bc[ab]
        cells = []
        for f in TEAM_COLS:
            old, new, w = v[f]
            ch = old != new
            cells.append(f'<td class="{"ch" if ch else ""}" title="{esc(w)}">'
                         + (f'<s>{esc(name_of(f, old))}</s><br>' if ch else '') + f'<b>{esc(name_of(f, new))}</b></td>')
        lines = []
        for i in range(1, 5):
            old, new, w = v[f'offense{i}']
            lines.append(f'<span class="{"ch" if old != new else ""}" title="{esc(w)}">{i}: {esc(name_of("offense", new))}'
                         + (f' <s>{esc(name_of("offense", old))}</s>' if old != new else '') + '</span>')
        sl = []
        for k, (fields, label) in SLIDERS.items():
            o = [v[f][0] for f in fields]
            nn = [v[f][1] for f in fields]
            if o != nn:
                sl.append(f'<span class="ch" title="{esc(v[fields[0]][2])}">{esc(label)}: {"/".join(map(str, o))} → '
                          f'<b>{"/".join(map(str, nn))}</b></span>')
        why = ''.join(f'<li><b>{esc(LABEL.get(k, k))}</b>: {esc(x.get("why", ""))}</li>'
                      for k, x in c.get('team', {}).items())
        if c.get('lines', {}).get('why'):
            why += f'<li><b>Звенья</b>: {esc(c["lines"]["why"])}</li>'
        why += ''.join(f'<li><b>{esc(SLIDERS[k][1])}</b>: {esc(x.get("why", ""))}</li>' for k, x in c.get('sliders', {}).items())
        src = ' '.join(f'<a href="{esc(u)}">[{i + 1}]</a>' for i, u in enumerate(c.get('sources', [])))
        rows.append(f'<tr><td class="club"><b>{esc(ab)}</b><br><small>{esc(c.get("coach", ""))}</small></td>'
                    + ''.join(cells) + f'<td class="lines">{"<br>".join(lines)}</td><td class="sl">{"<br>".join(sl)}</td></tr>'
                    f'<tr class="why"><td></td><td colspan="10"><details><summary>почему и источники {src}</summary>'
                    f'<ul>{why}</ul></details></td></tr>')
    doc = f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Стратегии клубов НХЛ</title><style>
:root{{--bg:#16181d;--fg:#e8e8ea;--mut:#9aa0a8;--line:#2c3038;--ch:#3a2f12;--chb:#f0b429}}
body{{background:var(--bg);color:var(--fg);font:14px/1.35 "Segoe UI",system-ui,sans-serif;margin:16px}}
table{{border-collapse:collapse;width:100%}} th,td{{border-bottom:1px solid var(--line);padding:4px 6px;vertical-align:top;text-align:left}}
th{{position:sticky;top:0;background:#20232a;font-weight:600}} td.ch,span.ch{{background:var(--ch)}} td.ch b,span.ch b{{color:var(--chb)}}
s{{color:var(--mut)}} small{{color:var(--mut)}} tr.why td{{border-bottom:2px solid var(--line);padding-top:0}} details{{color:var(--mut)}}
a{{color:#7fb3ff}} .lines,.sl{{font-size:12px;white-space:nowrap}}
</style></head><body><h2>Стратегии 32 клубов НХЛ — сейчас → станет</h2>
<p>Жёлтым — что меняется (зачёркнуто — сейчас). Наведите на ячейку — почему. Спека: tools/legacy_data/team_tactics.json,
описание — docs/team-tactics.md.</p><table><tr><th>Клуб</th>{"".join(f"<th>{COL_TITLE[f]}</th>" for f in TEAM_COLS)}
<th>Стиль звеньев</th><th>Ползунки звеньев (1/2/3/4)</th></tr>{"".join(rows)}</table></body></html>'''
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    open(path, 'w', encoding='utf-8').write(doc)


def write_png(path, spec, pl):
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 14)
        bold = ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf', 14)
    except OSError:
        font = bold = ImageFont.load_default()
    bc = by_club(pl)
    clubs = [ab for ab in spec['clubs'] if ab in bc]
    cols = [('Клуб', 150)] + [(COL_TITLE[f], 128) for f in TEAM_COLS] + [('Стиль звеньев 1 · 2 · 3 · 4', 420)]
    H, top = 40, 34
    im = Image.new('RGB', (sum(w for _, w in cols) + 20, top + H * len(clubs) + 30), (22, 24, 29))
    d = ImageDraw.Draw(im)
    x = 10
    for t, w in cols:
        d.text((x + 4, 10), t, fill=(200, 200, 205), font=bold)
        x += w
    short = {'overload': 'перегруз', 'crash the net': 'на пятак', 'behind the net': 'из-за ворот'}
    for i, ab in enumerate(clubs):
        y = top + i * H
        v = bc[ab]
        d.line([(10, y), (im.width - 10, y)], fill=(44, 48, 56))
        d.text((14, y + 4), ab, fill=(240, 240, 240), font=bold)
        d.text((14, y + 21), spec['clubs'][ab].get('coach', '')[:20], fill=(150, 155, 165), font=font)
        x = 10 + cols[0][1]
        for f in TEAM_COLS:
            old, new, _ = v[f]
            ch = old != new
            if ch:
                d.rectangle([x, y + 1, x + 126, y + H - 1], fill=(58, 47, 18))
                d.text((x + 4, y + 21), name_of(f, old), fill=(130, 130, 135), font=font)
            d.text((x + 4, y + 4), name_of(f, new), fill=(240, 180, 41) if ch else (225, 225, 228), font=font)
            x += 128
        ln = []
        for k in range(1, 5):
            old, new, _ = v[f'offense{k}']
            ln.append((short[name_of('offense', new)], old != new))
        xx = x + 4
        for j, (t, ch) in enumerate(ln):
            if ch:
                d.rectangle([xx - 3, y + 1, xx + 100, y + H - 1], fill=(58, 47, 18))
            d.text((xx, y + 12), t, fill=(240, 180, 41) if ch else (225, 225, 228), font=font)
            xx += 105
    d.text((10, im.height - 22), 'жёлтым — меняется (снизу серым — сейчас); ползунки звеньев и «почему» — в HTML',
           fill=(150, 155, 165), font=font)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    im.save(path)


def main(argv):
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=['show', 'db', 'save', 'check'])
    ap.add_argument('paths', nargs='*')
    ap.add_argument('--spec', default=SPEC)
    ap.add_argument('--nhl27', default=NHL27_DB, help='база NHL 27 для значений «nhl27»')
    ap.add_argument('--clubs', help='только эти клубы (abbrname через запятую)')
    ap.add_argument('--dry-run', action='store_true', help='db: показать, не записывать')
    ap.add_argument('--write', action='store_true', help='save: записать (без него — только подсчёт)')
    ap.add_argument('--base', default=CACHE_DB, help='show: база, от которой считать «сейчас»')
    ap.add_argument('--html')
    ap.add_argument('--png')
    a = ap.parse_args(argv)
    spec = load_spec(a.spec)
    a.names = [c.strip() for c in a.clubs.split(',')] if a.clubs else list(spec['clubs'])
    if a.cmd in ('db', 'save', 'check') and not a.paths:
        ap.error(f'{a.cmd}: укажите файл')
    n27 = Nhl27(a.nhl27)
    if not n27.rows:
        print(f'! нет базы NHL 27 ({a.nhl27}): значения «nhl27» остаются как есть')
    {'show': cmd_show, 'db': cmd_db, 'save': cmd_save, 'check': cmd_check}[a.cmd](a, spec, n27)


if __name__ == '__main__':
    main(sys.argv[1:])
