"""Выбор плитками с картинкой для полей карточки игрока — как в Creation Zone / Edit Player игры.

Картинки — превью самой игры (fe/ion/artassets/createplayer/<папка>/<имя><N>.big, сцена Apt в левом верхнем углу
текстуры), где их нет — текстура ассета (лицо головы rendering/player/texlib_<headid>, рисунок маски
goaliehelmet_<тип>_<номер>_cm, обмотка sticktape_<N>_cm). Номер значения поля остаётся мелко рядом.

Соответствие «значение поля → картинка»:
- клюшка, краги, шлем, коньки, щитки, блин, ловушка, клюшка вратаря — номер N модели = N в имени превью
  (stick<N>, gloves<N>, helmet<N>, skate<N>, pads<N>, blocker<N>, trapper<N>, goaliestick<N>; docs/sticks.md, skates.md);
  названия — каталоги редактора игры (gamecat);
- голова: типовые 60000–60210 — превью head<headid>, сканы — текстура лица;
- тон кожи: лицо типовой головы с этим тоном (самой частой у игроков базы с этим тоном);
- цвет глаз: eyecolor<код + 1> (коды 0…7, превью 1…8);
- визор: 0 обычный → visor2, 1 «авиатор» → visor3, 2 нет → visor1 (docs/player-equipment.md: 0 обычный, 1 «авиатор»,
  2 нет визора; превью visor1 — знак «нет»);
- маска вратаря: превью из каталога масок игры ([превью, тип, номер], docs/goalie-masks.md), свои маски — 1000 + номер
  (nhllegacy_masks.txt), остальные — рисунок маски;
- обмотка: растр sticktape_<N>_cm в rendering/playerstick/texlib_999;
- цвет визора: превью в игре нет (оттенок задаёт шейдер) — образец цвета по названию из docs/player-equipment.md.

Поля без картинки, но с понятными значениями, — список с названиями (ENUMS): заправка свитера и гетр, длина шорт
(docs/player-equipment.md, docs/player-models.md).
"""
import re
import urllib.parse

CP = 'fe/ion/artassets/createplayer'
B, SE, GE = 'exhibitionplayerbiotable', 'exhibitionskaterequipment', 'exhibitiongoalieequipment'
EQUIP = {f'{SE}.stick': ('sticks', 'stick', 'stick'), f'{SE}.gloves': ('gloves', 'gloves', 'gloves'),
         f'{SE}.helmetbrand': ('helmet', 'helmet', 'helmetbrand'), f'{SE}.skatebrand': ('skates', 'skate', 'skatebrand'),
         f'{GE}.pads': ('pads', 'pads', 'goalie'), f'{GE}.blocker': ('blocker', 'blocker', 'goalie'),
         f'{GE}.trapper': ('trapper', 'trapper', 'goalie'), f'{GE}.stick': ('goaliestick', 'goaliestick', None)}
VISOR = {0: (2, 'обычный', 'standard'), 1: (3, '«авиатор»', 'aviator'), 2: (1, 'нет визора', 'no visor')}
EYES = range(8)              # коды 0…7 (превью eyecolor1…8)
# названий у игры нет (в Creation Zone — только картинка); подписи — по виду превью, для поиска (05.11.2026)
EYE_NAMES = {0: ('голубые', 'blue'), 1: ('серые', 'gray'), 2: ('тёмно-карие', 'dark brown'), 3: ('карие', 'brown'),
             4: ('зелёные', 'green'), 5: ('серо-зелёные', 'gray-green'), 6: ('ореховые', 'hazel'), 7: ('янтарные', 'amber')}
EYE_CROP = (0, 0, 138, 104)  # глаз — левый верхний угол текстуры 256×128, правее и ниже — растяжка (замер 05.11.2026)
# цвет визора (docs/player-equipment.md): название и примерный цвет образца (05.11.2026: в игре оттенок — параметр
# шейдера, своих картинок нет; цвета — на глаз по названию, 11–14 — названия из данных игры)
VISOR_COLORS = {0: ('прозрачный', 'clear', '#d8e2ea', .25), 1: ('тёмный', 'dark', '#2b2f36', .95),
                2: ('жёлтый', 'yellow', '#e6c62a', .8), 3: ('оранжевый', 'orange', '#ee7b22', .8),
                4: ('зелёный', 'green', '#3da64a', .8), 5: ('голубой', 'light blue', '#5bbfea', .8),
                6: ('синий', 'blue', '#2e5ccc', .8), 7: ('красный', 'red', '#d23838', .8),
                8: ('фиолетовый', 'purple', '#7b4bc0', .8), 9: ('розовый', 'pink', '#ee7fb3', .8),
                10: ('белый', 'white', '#f4f4f4', .9), 11: ('sky', 'sky', '#8ec8ff', .8),
                12: ('sunburst', 'sunburst', '#f5a524', .8), 13: ('aqua', 'aqua', '#2fcfc2', .8),
                14: ('haze', 'haze', '#b8b1a5', .8)}
TUCK = {0: ('навыпуск', 'no tuck'), 1: ('заправлен слева', 'left tuck'), 2: ('заправлен справа', 'right tuck'),
        3: ('заправлен весь', 'full tuck')}
ENUMS = {
    f'{SE}.jerseytuck': TUCK, f'{GE}.jerseytuck': TUCK,
    # docs/player-equipment.md, «skatesocktuck»: 0 Full, 1 None, 2 Front, 3 Back
    f'{SE}.skatesocktuck': {0: ('в ботинке', 'full tuck'), 1: ('поверх ботинка', 'no tuck'),
                            2: ('спереди (язык поверх гетры)', 'front tuck'),
                            3: ('сзади (гетра закрывает язык)', 'back tuck')},
    # docs/player-models.md: сетка шорт pant_G_X_U_L, X = pantstypecode, 1 — длиннее
    f'{SE}.pantstypecode': {0: ('короткие', 'short'), 1: ('длинные', 'long')},
}


def swatch(color, alpha):
    """Образец цвета визора — SVG data: URL (визор на силуэте шлема)."""
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 128 99'><rect width='128' height='99' fill='#2b3038'/>"
           "<path d='M24 58 Q24 14 64 12 Q104 14 104 58 Z' fill='#e9ecef'/>"
           f"<path d='M16 54 Q64 34 112 54 L106 80 Q64 64 22 80 Z' fill='{color}' fill-opacity='{alpha}' "
           "stroke='#9aa3ad' stroke-width='1.5'/><path d='M30 58 Q64 46 98 58' stroke='#fff' stroke-opacity='.5' "
           "stroke-width='3' fill='none'/></svg>")
    return 'data:image/svg+xml,' + urllib.parse.quote(svg)


def thumb(rel, i=0, side=150, stage=True, crop=None):
    d = dict(rel=rel, i=i, side=side, stage=1 if stage else 0)
    if crop:
        d['crop'] = ','.join(map(str, crop))
    q = urllib.parse.urlencode(d)
    return f'/api/thumb?{q}'


class Pickers:
    def __init__(self, ed):
        self.ed = ed
        self._skin = None
        self._masks = None

    def has(self, rel):
        return self.ed.fs.exists(rel)

    def cp(self, folder, prefix, n):
        rel = f'{CP}/{folder}/{prefix}{n}.big'
        return thumb(rel) if self.has(rel) else None

    # ------------------------------------------------------------ по полям
    def apply(self, session, sections, lang, gid=None):
        ru = lang == 'ru'
        self._gid = gid
        for s in sections:
            for f in s['fields']:
                try:
                    opts = self.for_field(session, f, ru)
                except Exception:                      # noqa: BLE001  (картинки нет — останется список/число)
                    opts = None
                if opts:
                    f['base_kind'] = f['kind']
                    f['kind'] = 'tiles'
                    f['tiles'] = opts
                elif f['key'] in ENUMS and f['kind'] != 'enum':
                    names = ENUMS[f['key']]
                    opts = [[n, f'{w[0] if ru else w[1]} ({n})'] for n, w in names.items()]
                    if f.get('value') not in names:
                        opts.insert(0, [f.get('value'), str(f.get('value'))])
                    f['base_kind'] = f['kind']
                    f['kind'] = 'enum'
                    f['options'] = opts

    def for_field(self, session, f, ru):
        k, v = f['key'], f.get('value')
        if k in EQUIP:
            folder, prefix, cat = EQUIP[k]
            names = {}
            c = getattr(self.ed, 'catalogs', None)
            d = c.get() if c else None
            if d and cat:
                names = d.get(cat) or {}
            nums = sorted({int(x) for x in names} | {int(v)}) if names else sorted(
                {int(m.group(1)) for r in self.ed.fs.list_dir(f'{CP}/{folder}')
                 for m in [re.search(rf'{prefix}(\d+)\.big$', r)] if m} | {int(v)})
            return [[n, names.get(str(n), ''), self.cp(folder, prefix, n)] for n in nums]
        if k == f'{SE}.visortype':
            return [[n, w[1] if ru else w[2], self.cp('visor', 'visor', w[0])] for n, w in VISOR.items()]
        if k == f'{B}.eyecolorcode':
            nums = sorted(set(EYES) | {int(v)})
            return [[n, EYE_NAMES.get(n, ('', ''))[0 if ru else 1], thumb(f'{CP}/eyecolor/eyecolor{n + 1}.big', stage=False, crop=EYE_CROP)
                     if self.has(f'{CP}/eyecolor/eyecolor{n + 1}.big') else None] for n in nums]
        if k == f'{B}.headid':
            return self.heads(session, int(v))
        if k == f'{B}.skincolor':
            return self.skins(session, int(v), ru)
        if k == f'{GE}.maskid':
            return self.masks(session, f, int(v))
        if k == f'{SE}.visorcolor':
            nums = sorted(set(VISOR_COLORS) | {int(v)})
            return [[n, (VISOR_COLORS[n][0] if ru else VISOR_COLORS[n][1]) if n in VISOR_COLORS else '',
                     swatch(*VISOR_COLORS[n][2:]) if n in VISOR_COLORS else None] for n in nums]
        if k == f'{SE}.sticktapecolor':
            return self.tapes(int(v), ru)
        return None

    def head_img(self, h):
        p = self.cp('head', 'head', h)
        if p:
            return p
        rel = f'rendering/player/texlib_{h}.rx2'
        c = self.ed.container(rel) if self.has(rel) else None
        if c is None:
            return None
        i = next((r.index for r in c.rasters if r.name.startswith('head_')), 0)
        return thumb(rel, i, 128, stage=False)

    def heads(self, session, v):
        generic = list(range(60000, 60211))
        nums = generic + ([v] if v not in generic else [])
        return [[h, ('типовая' if h >= 60000 else 'скан') if True else '', self.head_img(h)] for h in nums]

    def skins(self, session, v, ru):
        """Тон кожи: лицо самой частой у игроков с этим тоном типовой головы."""
        if self._skin is None:
            from collections import Counter
            db = session.db
            by = {}
            for r in db.live_rows(B):
                h = db.get(B, 'headid', r)
                if 60000 <= h <= 60210:
                    by.setdefault(db.get(B, 'skincolor', r), Counter())[h] += 1
            self._skin = {s: c.most_common(1)[0][0] for s, c in by.items()}
        nums = sorted(set(self._skin) | {v})
        return [[s, ('тон ' if ru else 'tone ') + str(s), self.head_img(self._skin[s]) if s in self._skin else None]
                for s in nums]

    def masks(self, session, f, v):
        """Маска вратаря при текущем типе маски: превью каталога игры и своих масок, иначе рисунок маски."""
        mt = 0
        et, er = session.eq.get(getattr(self, '_gid', None), (None, None))
        if et == GE:
            mt = session.db.get(GE, 'masktype', er)
        if self._masks is None:
            prev = {}
            c = getattr(self.ed, 'catalogs', None)
            d = c.get() if c else None
            for p, t, i in (d or {}).get('masks', []):
                prev.setdefault((t, i), p)
            data = self.ed.fs.read('nhllegacy_masks.txt')
            for line in (data or b'').decode('utf-8', 'replace').splitlines():
                w = line.split('#')[0].split()
                if len(w) >= 2 and w[0].isdigit() and w[1].isdigit():
                    t, i = int(w[0]), int(w[1])
                    prev[(t, i)] = int(w[2]) if len(w) > 2 and w[2].isdigit() else 1000 + i
            files = {}
            for rel in self.ed.fs.list_dir('rendering/goaliehelmet', r'goaliehelmet_\d+_\d+_cm\.rx2$'):
                m = re.search(r'goaliehelmet_(\d+)_(\d+)_cm\.rx2$', rel)
                files[(int(m.group(1)), int(m.group(2)))] = rel
            if d is None:                      # каталоги ещё собираются в фоне — без кэша, следующая карточка возьмёт их
                return self._mask_tiles(prev, files, mt, v)
            self._masks = (prev, files)
        prev, files = self._masks
        return self._mask_tiles(prev, files, mt, v)

    def _mask_tiles(self, prev, files, mt, v):
        owners = self.ed.cat.mask_owners() if hasattr(self.ed, 'cat') else {}
        nums = sorted({i for (t, i) in list(prev) + list(files) if t == mt} | {v})
        out = []
        for i in nums:
            img = self.cp('mask', 'mask', prev[(mt, i)]) if (mt, i) in prev else None
            if img is None and (mt, i) in files:
                img = thumb(files[(mt, i)], 0, 128, stage=False)
            out.append([i, ', '.join(owners.get(i, [])[:3]), img])
        return out

    def tapes(self, v, ru):
        rel = 'rendering/playerstick/texlib_999.rx2'
        c = self.ed.container(rel) if self.has(rel) else None
        if c is None:
            return None
        by = {}
        for r in c.rasters:
            m = re.fullmatch(r'sticktape_(\d+)_cm\.Raster', r.name)
            if m:
                by[int(m.group(1))] = r.index
        if not by:
            return None
        nums = sorted(set(by) | {v})
        return [[n, ('обмотка ' if ru else 'tape ') + str(n), thumb(rel, by[n], 128, stage=False) if n in by else None]
                for n in nums]
