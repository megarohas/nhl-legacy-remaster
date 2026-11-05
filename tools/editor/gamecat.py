"""Названия для карточки игрока: страны и регионы (коды roster/codes.py), модели экипировки — из каталогов редактора
игры (в default.xex: клюшки, краги, шлемы, коньки, вратарская; tools/unlockables.py CATALOGS) с именами из
локализации (fe/loc/nhl_eng_us.db, tools/locdb.py).

Каталоги лежат в исполняемом файле, поэтому образ разжимается один раз (tools/xex.py, ~25 с на чистом Python) в
фоне, а результат — только номера и названия — кэшируется в cache\\editor\\catalogs.json (пересобирается, если
поменялись default.xex или строки). Номер записи каталога (первое слово) = значение поля игрока
(exhibitionskaterequipment.stick/gloves/helmetbrand/skatebrand), так у клюшек в docs/sticks.md.
"""
import json
import os
import struct
import threading

from roster import codes

# ISO-3 → (ru, en) для кодов стран базы (roster/codes.py COUNTRY)
COUNTRY_NAMES = {
    'CAN': ('Канада', 'Canada'), 'USA': ('США', 'USA'), 'DNK': ('Дания', 'Denmark'), 'FIN': ('Финляндия', 'Finland'),
    'NOR': ('Норвегия', 'Norway'), 'SWE': ('Швеция', 'Sweden'), 'BLR': ('Беларусь', 'Belarus'),
    'EST': ('Эстония', 'Estonia'), 'KAZ': ('Казахстан', 'Kazakhstan'), 'KGZ': ('Киргизия', 'Kyrgyzstan'),
    'LVA': ('Латвия', 'Latvia'), 'LTU': ('Литва', 'Lithuania'), 'RUS': ('Россия', 'Russia'), 'UKR': ('Украина', 'Ukraine'),
    'AUT': ('Австрия', 'Austria'), 'BEL': ('Бельгия', 'Belgium'), 'BGR': ('Болгария', 'Bulgaria'),
    'HRV': ('Хорватия', 'Croatia'), 'CZE': ('Чехия', 'Czechia'), 'GBR': ('Великобритания', 'Great Britain'),
    'FRA': ('Франция', 'France'), 'DEU': ('Германия', 'Germany'), 'HUN': ('Венгрия', 'Hungary'), 'ITA': ('Италия', 'Italy'),
    'MNE': ('Сербия и Черногория', 'Serbia and Montenegro'), 'NLD': ('Нидерланды', 'Netherlands'),
    'POL': ('Польша', 'Poland'), 'ROU': ('Румыния', 'Romania'), 'SVK': ('Словакия', 'Slovakia'),
    'SVN': ('Словения', 'Slovenia'), 'CHE': ('Швейцария', 'Switzerland'), 'AUS': ('Австралия', 'Australia'),
    'BHS': ('Багамы', 'Bahamas'), 'BRA': ('Бразилия', 'Brazil'), 'BRN': ('Бруней', 'Brunei'),
    'COL': ('Колумбия', 'Colombia'), 'COD': ('ДР Конго', 'DR Congo'), 'JPN': ('Япония', 'Japan'),
    'LBR': ('Либерия', 'Liberia'), 'NGA': ('Нигерия', 'Nigeria'), 'SGP': ('Сингапур', 'Singapore'),
    'ZAF': ('ЮАР', 'South Africa'), 'KOR': ('Южная Корея', 'South Korea'),
}
PROVINCE_FULL = {'AB': 'Alberta', 'BC': 'British Columbia', 'MB': 'Manitoba', 'NB': 'New Brunswick',
                 'NL': 'Newfoundland and Labrador', 'NT': 'Northwest Territories', 'NS': 'Nova Scotia',
                 'NU': 'Nunavut', 'ON': 'Ontario', 'PE': 'Prince Edward Island', 'QC': 'Quebec',
                 'SK': 'Saskatchewan', 'YT': 'Yukon'}
STATE_FULL = {v: k.title() for k, v in codes.STATE_NAMES.items() if ',' not in k and k != 'district of columbia'}
STATE_FULL['DC'] = 'District of Columbia'


def country_options(lang='ru', countries_only=False):
    """[(код, подпись)] для intlcountry (только страны) и state (страны + провинции Канады и штаты США)."""
    k = 0 if lang == 'ru' else 1
    by_code = {}
    for iso, c in codes.COUNTRY.items():
        if c not in by_code and iso in COUNTRY_NAMES:
            by_code[c] = COUNTRY_NAMES[iso][k]
    out = [(c, n) for c, n in sorted(by_code.items(), key=lambda x: x[1])]
    if not countries_only:
        out += [(1 + i, f'{COUNTRY_NAMES["CAN"][k]}: {PROVINCE_FULL[p]}') for i, p in enumerate(codes.PROVINCES)]
        out += [(15 + i, f'{COUNTRY_NAMES["USA"][k]}: {STATE_FULL.get(s, s)}') for i, s in enumerate(codes.STATES)]
    out.append((codes.NONE, 'нет / неизвестно' if lang == 'ru' else 'none / unknown'))
    return out


# каталоги редактора игры: (имя в карточке, номера каталогов из tools/unlockables.CATALOGS)
EQUIP_CATALOGS = {'stick': ('клюшки',), 'gloves': ('перчатки',), 'helmetbrand': ('шлемы',), 'skatebrand': ('коньки',),
                  'goalie': ('категория 4', 'категория 5', 'категория 6', 'категория 7')}


class Catalogs:
    def __init__(self, ed):
        self.ed = ed
        self.data = None
        self.state = 'idle'
        self.error = None
        self._lock = threading.Lock()

    def _paths(self):
        fs = self.ed.fs
        xex = os.path.join(fs.game_root, 'default.xex')
        return xex, os.path.join(fs.work, 'catalogs.json')

    def get(self):
        """Готовые каталоги или None (тогда сборка идёт в фоне)."""
        if self.data is not None:
            return self.data
        with self._lock:
            if self.state == 'idle':
                xex, cache = self._paths()
                sig = self._signature(xex)
                try:
                    d = json.load(open(cache, encoding='utf-8'))
                    if d.get('sig') == sig:
                        self.data = d
                        self.state = 'ready'
                        return d
                except (OSError, ValueError):
                    pass
                self.state = 'building'
                threading.Thread(target=self._build, args=(xex, cache, sig), daemon=True).start()
        return self.data

    def _signature(self, xex):
        try:
            st = os.stat(xex)
            hit = self.ed.fs.find('fe/loc/nhl_eng_us.db')
            loc = os.path.getmtime(hit[2]) if hit and hit[2] else 0
            return f'{st.st_size}:{int(st.st_mtime)}:{int(loc)}'
        except OSError:
            return None

    def _build(self, xex, cache, sig):
        try:
            import xex as xexmod
            import unlockables as U
            img = xexmod.Xex(xex).image(log=lambda *a: None)
            im = U.Img.__new__(U.Img)
            im.d = img
            loc = self.loc_names()
            out = {'sig': sig}
            cats = {t: (n, base, uo, size) for t, n, base, uo, size in U.CATALOGS}
            for field, titles in EQUIP_CATALOGS.items():
                names = {}
                for t in titles:
                    n, base, uo, size = cats[t]
                    for i in range(n):
                        rec = base + size * i
                        num = struct.unpack_from('>i', img, rec - U.BASE)[0]
                        key = im.key_in(rec, size)
                        if key and str(num) not in names:
                            names[str(num)] = (loc.get(key.lower()) or key).strip()
                out[field] = names
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            json.dump(out, open(cache, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
            self.data = out
            self.state = 'ready'
        except Exception as e:                           # noqa: BLE001
            self.error = str(e)
            self.state = 'error'

    def loc_names(self):
        """Ключ строки (нижний регистр) → текст из fe/loc/nhl_eng_us.db (то, что возьмёт игра)."""
        from locdb import LocDb
        from tdb_read import load_meta
        fs = self.ed.fs
        db = fs.read('fe/loc/nhl_eng_us.db')
        meta_hit = fs.find('fe/loc/nhl_eng_us-meta.xml')
        if db is None or meta_hit is None:
            return {}
        if meta_hit[2]:
            meta = load_meta(meta_hit[2])
        else:
            p = os.path.join(fs.work, 'loc-meta.xml')
            os.makedirs(fs.work, exist_ok=True)
            open(p, 'wb').write(fs.read('fe/loc/nhl_eng_us-meta.xml'))
            meta = load_meta(p)
        loc = LocDb(db, meta)
        return {sid.lower(): loc.text(off) for _, sid, off in loc.rows()}

    def options(self, field, value, lang='ru'):
        d = self.get()
        if not d:
            return None
        names = d.get(field) or {}
        opts = sorted(((int(k), f'{v} ({k})') for k, v in names.items()), key=lambda x: x[1].lower())
        if str(value) not in names:
            opts.insert(0, (value, f'{value} — ' + ('нет в каталоге' if lang == 'ru' else 'not in the catalog')))
        return opts
