"""Дерево разделов редактора и ассеты: какие файлы игры составляют «форму клуба», «логотипы», «фото игрока» …

Узел дерева: {id, ru, en, leaf, count}. Ассет (лист): {id, ru, en, files: [{rel, role_ru, role_en}]}; содержимое
файлов (текстуры, сетка, звук) редактор показывает по rel. Имена — из базы и ROSTER (gamedb), пути — как у игры
(docs/uniforms.md, docs/logos-arenas.md, docs/player-photos.md, docs/arenas.md, docs/music.md).
"""
import re

import gamedb

SECTIONS = [
    ('uniforms', 'Формы', 'Uniforms'),
    ('logos', 'Логотипы', 'Logos'),
    ('photos', 'Фото игроков', 'Player photos'),
    ('heads', 'Лица и головы', 'Faces and heads'),
    ('equipment', 'Экипировка', 'Equipment'),
    ('arenas', 'Арены и лёд', 'Arenas and ice'),
    ('menus', 'Меню и шрифты', 'Menus and fonts'),
    ('music', 'Музыка', 'Music'),
    ('models', 'Модели (сетки)', 'Models (meshes)'),
    ('rosters', 'Составы', 'Rosters'),
    ('my', 'Мои правки', 'My edits'),
    ('files', 'Все файлы игры', 'All game files'),
]

KIT_FILES = [
    ('rendering/jersey/texlib_{s}_{a}_{v}.rx2', 'Свитер и шрифт номеров', 'Jersey and number font'),
    ('rendering/jersey/name_{s}_{a}_{v}_cm.rx2', 'Карта мест номера и фамилии', 'Number/name placement map'),
    ('rendering/pant/texlib_{s}_{a}_{v}.rx2', 'Шорты', 'Pants'),
    ('rendering/sock/sock_{s}_{a}_{v}_cm.rx2', 'Гетры', 'Socks'),
    ('fe/ion/artassets/jerseys/jersey_{s}_{a}_{f}.big', 'Превью в меню', 'Menu preview'),
]
HELMET_LOGO = ('rendering/logo/texlib_{a}_{s}_{v}.rx2', 'Наклейка на шлем', 'Helmet decal')
UI_LOGOS = [
    ('fe/ion/artassets/teamlogos/t{n}.big', 'Логотип (меню)', 'Logo (menus)'),
    ('fe/ion/artassets/teamlogossmall/s{n}.big', 'Таблетка (табло)', 'Small (scoreboard)'),
    ('fe/ion/artassets/teamlogosdynasty/d{n}.big', 'Франшиза', 'Franchise'),
    ('fe/ion/artassets/teamlogoscalendar/c{n}.big', 'Календарь', 'Calendar'),
    ('fe/ion/artassets/teamlogoswide/w{n}.big', 'Крупный план', 'Wide'),
    ('fe/ion/artassets/teamlogosreflection/r{n}.big', 'С отражением', 'Reflection'),
    ('fe/ion/artassets/twittericonsteam/t{n}.big', 'Иконка', 'Icon'),
]
LOGOS_3D = [
    ('rendering/icesurface/centerlogo_{n}_cm.rx2', 'Центр льда', 'Center ice'),
    ('rendering/puck/puck_{n}_cm.rx2', 'Шайба', 'Puck'),
    ('rendering/banner/banner_{n}_cm.rx2', 'Баннер арены', 'Arena banner'),
]

# подписи растров по имени (jersey_1_23_0_cm.Raster → «Свитер — цвет»)
RASTER_LABELS = [
    (r'^jersey_.*_0_nm', 'Свитер — рельеф (нормали)', 'Jersey — relief (normals)'),
    (r'^jersey_.*_cm', 'Свитер — цвет', 'Jersey — color'),
    (r'^jersey_.*_sm', 'Свитер — блеск', 'Jersey — gloss'),
    (r'^font_.*_cm', 'Шрифт номеров и фамилии', 'Number and name font'),
    (r'^font_.*_nm', 'Шрифт — рельеф', 'Font — relief'),
    (r'^font_.*_sm', 'Шрифт — блеск', 'Font — gloss'),
    (r'^name_.*_cm', 'Карта мест номера и фамилии', 'Number/name placement map'),
    (r'^pant_.*_cm', 'Шорты — цвет', 'Pants — color'),
    (r'^pant_.*_nm', 'Шорты — рельеф', 'Pants — relief'),
    (r'^pant_.*_sm', 'Шорты — блеск', 'Pants — gloss'),
    (r'^sock_.*_cm', 'Гетры — цвет', 'Socks — color'),
    (r'^logo_.*_0$', 'Наклейка на шлем', 'Helmet decal'),
    (r'^head_.*_cm', 'Лицо', 'Face'),
    (r'^hair_.*_cm', 'Волосы', 'Hair'),
    (r'^centerlogo_', 'Центр льда', 'Center ice'),
    (r'^puck_', 'Шайба', 'Puck'),
    (r'^banner_', 'Баннер', 'Banner'),
    (r'^goaliehelmet_', 'Маска вратаря', 'Goalie mask'),
]


def raster_label(name, lang='ru'):
    base = name.split('.')[0]
    for rx, ru, en in RASTER_LABELS:
        if re.search(rx, base):
            return ru if lang == 'ru' else en
    return base


class Catalog:
    def __init__(self, fs, db):
        self.fs, self.db = fs, db

    # ------------------------------------------------------------ дерево
    def children(self, node, lang='ru'):
        """Дети узла дерева: [{id, ru, en, leaf, count?}]."""
        self.db.load()
        db = self.db
        if node in ('', 'root'):
            return [dict(id=s, ru=ru, en=en, leaf=s in ('rosters', 'my')) for s, ru, en in SECTIONS]
        parts = node.split(':')
        sec = parts[0]
        if sec in ('uniforms', 'logos', 'photos', 'heads') and len(parts) == 1:
            out = []
            for code, teams in db.leagues():
                name = 'Матч звёзд' if code == 99 else db.league_name(code, 'ru')
                name_en = 'All-Star' if code == 99 else db.league_name(code, 'en')
                out.append(dict(id=f'{sec}:L{code}', ru=name, en=name_en, leaf=False, count=len(teams)))
            if sec in ('photos', 'heads'):
                out.append(dict(id=f'{sec}:FA', ru='Без клуба', en='Free agents', leaf=False))
            return out
        if sec in ('uniforms', 'logos', 'photos', 'heads') and len(parts) == 2 and parts[1].startswith('L'):
            code = int(parts[1][1:])
            teams = dict(db.leagues()).get(code, [])
            if sec in ('photos', 'heads'):
                return [dict(id=f'{sec}:T{t["index"]}', ru=t['name'], en=t['name'], leaf=False,
                             count=len(db.members.get(t['index'], []))) for t in teams]
            if sec == 'uniforms':
                return [dict(id=f'{sec}:T{t["index"]}', ru=t['name'], en=t['name'], leaf=False,
                             count=len(db.kits.get(t['index'], []))) for t in teams]
            return [dict(id=f'logos:T{t["index"]}', ru=t['name'], en=t['name'], leaf=False) for t in teams]
        if sec == 'uniforms' and len(parts) == 2 and parts[1].startswith('T'):
            ti = int(parts[1][1:])
            out = []
            for k in db.kits.get(ti, []):
                kid = f'{k["s"]}_{k["a"]}_{k["v"]}_{k["f"]}'
                out.append(dict(id=f'kit:{ti}:{kid}', ru=db.kit_label(k, 'ru'), en=db.kit_label(k, 'en'), leaf=True,
                                default=bool(k['default'])))
            return out
        if sec == 'logos' and len(parts) == 2 and parts[1].startswith('T'):
            ti = int(parts[1][1:])
            return [dict(id=f'logoui:{ti}', ru='Логотипы меню и табло', en='Menu and scoreboard logos', leaf=True),
                    dict(id=f'logo3d:{ti}', ru='Лёд, шайба, баннер', en='Ice, puck, banner', leaf=True)]
        if sec in ('photos', 'heads') and len(parts) == 2:
            if parts[1] == 'FA':
                ids = {g for gs in db.members.values() for g in gs}
                pl = [p for g, p in db.players.items() if g not in ids and p['first']]
            else:
                pl = db.roster(int(parts[1][1:]))
            pl = sorted(pl, key=lambda p: (p['last'], p['first']))
            kind = 'photo' if sec == 'photos' else 'head'
            return [dict(id=f'{kind}:{p["gid"]}', ru=f'{p["last"]} {p["first"]} · {p["pos"]} #{p["jersey"]}',
                         en=f'{p["last"]} {p["first"]} · {p["pos"]} #{p["jersey"]}', leaf=True) for p in pl]
        if sec == 'files':
            return self.files_children(node[len('files'):].lstrip(':'))
        return []

    def files_children(self, folder):
        """«Все файлы игры»: папки и файлы под folder (content и архивы EA вместе)."""
        fs = self.fs
        names = fs.list_dir(folder) if folder else None
        out, dirs = [], {}
        if names is None:
            tops = set()
            for _, root in fs.layers():
                import os
                if os.path.isdir(root):
                    tops |= {d.lower() for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))}
            fs.ea.ready.wait()
            tops |= {k.split('/')[0] for k in fs.ea.index if '/' in k}
            return [dict(id=f'files:{t}', ru=t, en=t, leaf=False) for t in sorted(tops)]
        base = folder.rstrip('/') + '/'
        for rel in names:
            rest = rel[len(base):]
            if '/' in rest:
                d = rest.split('/')[0]
                dirs.setdefault(d.lower(), d)
            else:
                out.append(dict(id=f'file:{rel}', ru=rest, en=rest, leaf=True))
        return ([dict(id=f'files:{base}{d}', ru=d, en=d, leaf=False) for d in sorted(dirs.values(), key=str.lower)]
                + sorted(out, key=lambda x: x['ru'].lower()))

    def path(self, aid):
        """Узлы дерева от корня до ассета (чтобы открыть ссылку #open=…)."""
        self.db.load()
        kind, _, rest = aid.partition(':')
        sec = {'kit': 'uniforms', 'logoui': 'logos', 'logo3d': 'logos', 'photo': 'photos', 'head': 'heads'}.get(kind)
        if sec is None:
            return []
        if kind in ('photo', 'head'):
            gid = int(rest)
            team = next((t for t, gs in self.db.members.items() if gid in gs and t in self.db.teams), None)
            if team is None:
                return [sec, f'{sec}:FA']
        else:
            team = int(rest.split(':')[0])
        code = next((c for c, ts in self.db.leagues() if any(t['index'] == team for t in ts)), None)
        return [sec, f'{sec}:L{code}', f'{sec}:T{team}']

    # ------------------------------------------------------------ ассеты
    def asset(self, aid, lang='ru'):
        self.db.load()
        db = self.db
        kind, _, rest = aid.partition(':')
        if kind == 'kit':
            ti, kid = rest.split(':')
            s, a, v, f = (int(x) for x in kid.split('_'))
            t = db.team(int(ti)) or {}
            k = next((k for k in db.kits.get(int(ti), []) if (k['s'], k['a'], k['v'], k['f']) == (s, a, v, f)), None)
            files = [dict(rel=p.format(s=s, a=a, v=v, f=f), ru=ru, en=en) for p, ru, en in KIT_FILES]
            if k is None or k.get('helmetlogo'):
                p, ru, en = HELMET_LOGO
                files.append(dict(rel=p.format(s=s, a=a, v=v), ru=ru, en=en))
            title = f'{t.get("name", ti)} — {db.kit_label(k, lang) if k else kid}'
            return dict(id=aid, title=title, files=files, export_name=f'{t.get("abbr", ti)} {kid}')
        if kind in ('logoui', 'logo3d'):
            t = db.team(int(rest)) or {}
            n = t.get('artid', rest)
            spec = UI_LOGOS if kind == 'logoui' else LOGOS_3D
            files = [dict(rel=p.format(n=n), ru=ru, en=en) for p, ru, en in spec]
            sub = ('логотипы меню' if lang == 'ru' else 'menu logos') if kind == 'logoui' else \
                ('лёд, шайба, баннер' if lang == 'ru' else 'ice, puck, banner')
            return dict(id=aid, title=f'{t.get("name", rest)} — {sub} (art {n})', files=files,
                        export_name=f'{t.get("abbr", rest)} logos{"" if kind == "logoui" else " 3d"}')
        if kind == 'photo':
            p = db.players.get(int(rest)) or {}
            n = p.get('artid', 0)
            folder = 'p0_4000' if n <= 4000 else 'p4001_8000' if n <= 8000 else 'p8001_12000' if n <= 12000 else \
                'silhouettes'
            files = [dict(rel=f'fe/ion/artassets/playerheads/{folder}/p{n}.big', ru='Портрет', en='Portrait'),
                     dict(rel=f'fe/ion/artassets/playerheadssmall/{folder}/p{n}.big', ru='Малый портрет',
                          en='Small portrait')]
            note = None if p.get('portrait') else ('У игрока в базе hasportrait = 0 — в игре силуэт' if lang == 'ru'
                                                   else 'hasportrait = 0 in the roster — the game shows a silhouette')
            return dict(id=aid, title=f'{db.player_name(int(rest))} — фото (art {n})', files=files, note=note,
                        export_name=f'{p.get("last", rest)} {p.get("first", "")} photo')
        if kind == 'head':
            p = db.players.get(int(rest)) or {}
            h = p.get('headid', 0)
            files = [dict(rel=f'rendering/player/texlib_{h}.rx2', ru='Текстуры головы', en='Head textures'),
                     dict(rel=f'rendering/player/player_{h}.rx2', ru='Сетка головы', en='Head mesh')]
            note = ('Типовая голова: её носят и другие игроки' if lang == 'ru' else
                    'Generic head: other players use it too') if 60000 <= h <= 60210 else None
            return dict(id=aid, title=f'{db.player_name(int(rest))} — голова {h}', files=files, note=note,
                        export_name=f'head {h}')
        if kind == 'file':
            return dict(id=aid, title=rest, files=[dict(rel=rest, ru='Файл', en='File')],
                        export_name=rest.split('/')[-1].rsplit('.', 1)[0])
        return None
