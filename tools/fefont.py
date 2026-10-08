"""Шрифты интерфейса NHL 13 (Xbox 360): где лежат, разбор, замена своим шрифтом TTF/OTF.

    python fefont.py info [FONT…]                      # имена, метрики, набор символов, кернинг;
                                                       # без аргументов — шрифты игры
    python fefont.py styles FONT                       # оси и именованные стили вариативного шрифта
    python fefont.py extents [--check] [--out FILE]    # font_extents.txt по метрикам шрифтов (формула игры);
                                                       # --check — сверка с файлом игры построчно
    python fefont.py build OUTDIR --face KEY=SRC[#N][@СТИЛЬ] [--face …] [--fit cap|x|em] [--scale K]
                           [--width 1|auto|K] [--track N] [--no-kern] [--keep-marks] [--caps]
                           [--vmetrics game|source] [--preview DIR]
        # KEY — conbold, med, hv (интерфейс) или indicator (подписи игроков на льду);
        # SRC — TTF/OTF/TTC (#N — номер шрифта в TTC), @СТИЛЬ — именованный стиль вариативного шрифта
        # («SemiBold», «Bold Condensed») или оси («wght=600,wdth=80»).
        # --fit: под высоту прописных оригинала (cap, по умолчанию), строчных (x) или кегль в кегль (em);
        # --width auto — сжать/растянуть по ширине до средней ширины оригинала; --track — разрядка (ед. из 1000),
        # разная для разных KEY — отдельными запусками в один OUTDIR; --caps — строчные рисуются прописными;
        # ®, ™, ℠ вписываются в рамку маленьких надстрочных знаков EA (--keep-marks — оставить как в шрифте).
        # Результат — дерево как в cache: OUTDIR/fe/ion/fonts/EAHelveticaNeue…-Mod.ttf
        # (+ OUTDIR/fe/ion/fonts/font_extents.txt при --vmetrics source), отчёт — OUTDIR/fefont-build.json.
    python fefont.py preview OUTDIR PREVIEW_DIR [--shot PNG|WEBP] [--nhl12 JPG]
        # образцы «до/после» через Chrome/Edge без окна (+ сравнение с кусками снимка экрана
        # «Starting Lineups» 1651×982, если дан --shot; --nhl12 — главное меню NHL 12 1000×563 рядом
        # с теми же пунктами шрифтом «Hv» до и после)

Как устроено (подробности — docs/fe-fonts.md):
  * Интерфейс (Apt/ION) рисует текст шрифтами TrueType на лету (растеризатор Bitstream FontFusion
    в RenderWare/RNA, кэш глифов), атласов глифов нет. Игра читает fe/ion/fonts/fonts.txt — список
    файлов (arial.ttf, EAHelveticaNeueMed-Mod.ttf, …Hv-Mod.ttf, …ConBol-Mod.ttf; arial.ttf в архивах
    нет) и fe/ion/fonts/font_extents.txt — высоты строк. Ролики Apt ссылаются на шрифт по имени
    («EA HelveticaNeue Con Bold», «… Med», «… Hv») — оно берётся из таблицы name файла, поэтому
    сборка переносит name оригинала байт-в-байт.
  * «Con Bold» и «Med» в NHL 13 — один и тот же Helvetica Neue 65 Medium (отличается только знак ℠
    и классы веса/ширины в OS/2): это и есть шрифт большинства надписей. «Hv» — 85 Heavy.
    Настоящий узкий 77 Bold Condensed под именем «EA HelveticaNeue Con Bold» лежит отдельно —
    rendering/indicator/indicatorfont.ttf (подписи над игроками), и по нему посчитана таблица
    font_extents.txt для «Con Bold».
  * font_extents.txt: для каждого шрифта строки [ size A D ], size = 10…250,
    A = ceil(min(size, 127) · usWinAscent / unitsPerEm), D = ceil(min(size, 127) · usWinDescent / unitsPerEm)
    (сверено на всех 723 строках). Сборка по умолчанию сохраняет вертикальные метрики оригинала
    (--vmetrics game) — таблица остаётся верной, базовая линия не сдвигается.
  * Сборка: контуры исходного шрифта (TrueType как есть, CFF — кубические кривые в квадратичные,
    вариативный — в выбранном стиле, gvar/avar/HVAR) масштабируются под высоту прописных оригинала
    (--fit cap), составные глифы раскрываются, хинтинг не переносится. Набор символов — ровно как у
    оригинала; чего нет в исходном шрифте — заменяется похожим (пробел, дефис, Ё → Ë, ﬁ → f+i)
    или берётся глиф оригинала (список — в отчёте). Кернинг (GPOS/kern) — в таблицу kern.

Только стандартная библиотека (+ Chrome или Edge для preview). Каталог игры — NHL13_GAME или game/.
"""
import json, math, os, re, shutil, struct, subprocess, sys, tempfile, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import playerhead as ph  # noqa: E402  (game_dir, RefPack)

# ---------------------------------------------------------------- шрифты игры

FACES = {   # ключ: файл в cache:, (архив, путь в архиве), имя в Apt, что это
    'conbold': ('fe/ion/fonts/EAHelveticaNeueConBol-Mod.ttf', ('cache', 'fe/ion/fonts/eahelveticaneueconbol-mod.ttf'),
                'EA HelveticaNeue Con Bold', 'интерфейс: большинство надписей (Helvetica Neue 65 Medium)'),
    'med': ('fe/ion/fonts/EAHelveticaNeueMed-Mod.ttf', ('cache', 'fe/ion/fonts/eahelveticaneuemed-mod.ttf'),
            'EA HelveticaNeue Med', 'интерфейс: тот же 65 Medium под вторым именем'),
    'hv': ('fe/ion/fonts/EAHelveticaNeueHv-Mod.ttf', ('cache', 'fe/ion/fonts/eahelveticaneuehv-mod.ttf'),
           'EA HelveticaNeue Hv', 'интерфейс: цифры, пункты меню, заголовки таблиц (85 Heavy)'),
    'indicator': ('rendering/indicator/indicatorfont.ttf', ('cacherender', 'rendering/indicator/indicatorfont.ttf'),
                  'EA HelveticaNeue Con Bold', 'подписи игроков на льду (77 Bold Condensed)'),
}
EXTRA = {   # прочие шрифты в архивах (не заменяются сборкой)
    'rockwell': ('fe/ion/fonts/rockeb.ttf', ('cache', 'fe/ion/fonts/rockeb.ttf'), 'Rockwell Extra Bold',
                 'лежит в папке шрифтов, но нет в fonts.txt — игра его не открывает'),
    'debug': ('debug/consolasboldreduced.ttf', ('boot', 'debug/consolasboldreduced.ttf'), 'Consolas Bold',
              'отладочный шрифт'),
}
EXTENTS_FILE = 'fe/ion/fonts/font_extents.txt'
FONTS_LIST = 'fe/ion/fonts/fonts.txt'
EXTENTS_ORDER = ('conbold', 'hv', 'med')          # порядок блоков в font_extents.txt игры
EXTENTS_SIZES = range(10, 251)
EXTENTS_MAX_PX = 127                              # выше — те же значения (кэш глифов до 127 px)


def u16(b, o): return struct.unpack_from('>H', b, o)[0]
def s16(b, o): return struct.unpack_from('>h', b, o)[0]
def u32(b, o): return struct.unpack_from('>I', b, o)[0]
def s32(b, o): return struct.unpack_from('>i', b, o)[0]
def f2d14(b, o): return s16(b, o) / 16384.0
def fixed(b, o): return s32(b, o) / 65536.0


def bigeb_member(archive, member):
    """Запись из архива BigEB v3 (диск NHL 13) — сырые байты или None."""
    with open(archive, 'rb') as f:
        h = f.read(0x30)
        if h[:4] != b'EB\x00\x03':
            raise SystemExit(f'{archive}: не BigEB v3')
        count, names_off = u32(h, 4), u32(h, 0x0C)
        nstride, dstride, dcount = h[0x14], h[0x15], u16(h, 0x16)
        f.seek(0x30)
        ents = f.read(16 * count)
        f.seek(names_off)
        names = f.read(nstride * count)
        f.seek((names_off + nstride * count + 15) & ~15)
        dirs = f.read(dstride * dcount)
        dirs = [dirs[i * dstride:(i + 1) * dstride].split(b'\0')[0].decode('latin1') for i in range(dcount)]
        want = member.lower()
        for i in range(count):
            rec = names[i * nstride:(i + 1) * nstride]
            di, nm = u16(rec, 0), rec[2:].split(b'\0')[0].decode('latin1')
            d = dirs[di] if di < len(dirs) else ''
            path = f'{d}/{nm}' if d and d != '.' else nm
            if path.lower() != want:
                continue
            off, packed, size = u32(ents, 16 * i) * 16, u32(ents, 16 * i + 4), u32(ents, 16 * i + 8)
            f.seek(off)
            return f.read(packed or size)
    return None


def unwrap(blob):
    """Снять сжатие EA (chunklzx/chunkzip, RefPack), если есть."""
    if blob[:8] in (b'chunkzip', b'chunklzx'):
        import unchunk
        return unchunk.unchunk(blob)
    if len(blob) > 5 and blob[1] == 0xFB and blob[0] in (0x10, 0x11, 0x90, 0x91):
        return ph.refpack_decompress(blob)
    return blob


def game_file(archive, member, game=None):
    """Файл игры: распакованный (game/extracted/big/<архив>/…, game/work/fe-font/src/<архив>/…) или из .big."""
    g = game or ph.game_dir()
    for root in (os.path.join(g, 'extracted', 'big', archive), os.path.join(g, 'work', 'fe-font', 'src', archive)):
        p = os.path.join(root, *member.split('/'))
        if os.path.exists(p):
            return unwrap(open(p, 'rb').read())
    big = os.path.join(g, 'extracted', 'disc', archive + '.big')
    if os.path.exists(big):
        blob = bigeb_member(big, member)
        if blob is not None:
            return unwrap(blob)
    raise SystemExit(f'нет {archive}.big:{member} — распакуйте диск (docs/game-files.md)')


def game_font(key, game=None):
    rel, (arch, member), _, _ = {**FACES, **EXTRA}[key]
    return Font(game_file(arch, member, game), path=f'{arch}.big:{member}')


# ---------------------------------------------------------------- чтение шрифта

MAC_GLYPHS = (
    '.notdef .null nonmarkingreturn space exclam quotedbl numbersign dollar percent ampersand quotesingle '
    'parenleft parenright asterisk plus comma hyphen period slash zero one two three four five six seven eight '
    'nine colon semicolon less equal greater question at A B C D E F G H I J K L M N O P Q R S T U V W X Y Z '
    'bracketleft backslash bracketright asciicircum underscore grave a b c d e f g h i j k l m n o p q r s t u '
    'v w x y z braceleft bar braceright asciitilde Adieresis Aring Ccedilla Eacute Ntilde Odieresis Udieresis '
    'aacute agrave acircumflex adieresis atilde aring ccedilla eacute egrave ecircumflex edieresis iacute igrave '
    'icircumflex idieresis ntilde oacute ograve ocircumflex odieresis otilde uacute ugrave ucircumflex udieresis '
    'dagger degree cent sterling section bullet paragraph germandbls registered copyright trademark acute '
    'dieresis notequal AE Oslash infinity plusminus lessequal greaterequal yen mu partialdiff summation product '
    'pi integral ordfeminine ordmasculine Omega ae oslash questiondown exclamdown logicalnot radical florin '
    'approxequal Delta guillemotleft guillemotright ellipsis nonbreakingspace Agrave Atilde Otilde OE oe endash '
    'emdash quotedblleft quotedblright quoteleft quoteright divide lozenge ydieresis Ydieresis fraction currency '
    'guilsinglleft guilsinglright fi fl daggerdbl periodcentered quotesinglbase quotedblbase perthousand '
    'Acircumflex Ecircumflex Aacute Edieresis Egrave Iacute Icircumflex Idieresis Igrave Oacute Ocircumflex '
    'apple Ograve Uacute Ucircumflex Ugrave dotlessi circumflex tilde macron breve dotaccent ring cedilla '
    'hungarumlaut ogonek caron Lslash lslash Scaron scaron Zcaron zcaron brokenbar Eth eth Yacute yacute Thorn '
    'thorn minus multiply onesuperior twosuperior threesuperior onehalf onequarter threequarters franc Gbreve '
    'gbreve Idotaccent Scedilla scedilla Cacute cacute Ccaron ccaron dcroat').split()
MAC_INDEX = {n: i for i, n in enumerate(MAC_GLYPHS)}


def support_scalar(coords, peak, lower=None, upper=None):
    """Вес кортежа вариаций (как в OpenType: оси с нулевым пиком и неверными диапазонами не участвуют)."""
    s = 1.0
    for i, pk in enumerate(peak):
        if pk == 0:
            continue
        lo, hi = (min(0.0, pk), max(0.0, pk)) if lower is None else (lower[i], upper[i])
        if lo > pk or pk > hi or (lo < 0 < hi):
            continue
        v = coords[i] if i < len(coords) else 0.0
        if v == pk:
            continue
        if v <= lo or v >= hi:
            return 0.0
        s *= (v - lo) / (pk - lo) if v < pk else (v - hi) / (pk - hi)
    return s


class VarStore:
    """ItemVariationStore (HVAR, MVAR, GDEF — дельты GPOS)."""

    def __init__(self, b, off):
        rl = off + u32(b, off + 2)
        axes, nreg = u16(b, rl), u16(b, rl + 2)
        self.regions = []
        p = rl + 4
        for _ in range(nreg):
            st = [f2d14(b, p + 6 * a) for a in range(axes)]
            pk = [f2d14(b, p + 6 * a + 2) for a in range(axes)]
            en = [f2d14(b, p + 6 * a + 4) for a in range(axes)]
            self.regions.append((st, pk, en))
            p += 6 * axes
        self.data = []
        for k in range(u16(b, off + 6)):
            d = off + u32(b, off + 8 + 4 * k)
            items, wdc, nri = u16(b, d), u16(b, d + 2), u16(b, d + 4)
            ridx = [u16(b, d + 6 + 2 * i) for i in range(nri)]
            longw, words = wdc & 0x8000, wdc & 0x7FFF
            big, small = ('i', 'h') if longw else ('h', 'b')
            fmt = '>' + big * words + small * (nri - words)
            row = struct.calcsize(fmt)
            base = d + 6 + 2 * nri
            self.data.append((ridx, fmt, row, base, items))
        self.b = b

    def delta(self, outer, inner, coords):
        if outer >= len(self.data):
            return 0.0
        ridx, fmt, row, base, items = self.data[outer]
        if inner >= items:
            return 0.0
        vals = struct.unpack_from(fmt, self.b, base + row * inner)
        out = 0.0
        for r, v in zip(ridx, vals):
            if v:
                st, pk, en = self.regions[r]
                out += v * support_scalar(coords, pk, st, en)
        return out


def delta_set_map(b, off, gid):
    fmt, ef = b[off], b[off + 1]
    n = u16(b, off + 2) if fmt == 0 else u32(b, off + 2)
    p = off + (4 if fmt == 0 else 6)
    size = ((ef >> 4) & 3) + 1
    bits = (ef & 0xF) + 1
    i = min(gid, n - 1)
    e = int.from_bytes(b[p + i * size:p + (i + 1) * size], 'big')
    return e >> bits, e & ((1 << bits) - 1)


class Font:
    """Шрифт OpenType (TrueType или CFF), в т. ч. вариативный: контуры (квадратичные), метрики, кернинг."""

    def __init__(self, data, index=0, path=''):
        self.path = path
        base = 0
        if data[:4] == b'ttcf':
            n = u32(data, 8)
            if not 0 <= index < n:
                raise SystemExit(f'{path}: в коллекции {n} шрифтов, номер {index} вне диапазона')
            base = u32(data, 12 + 4 * index)
        self.flavor = data[base:base + 4]
        if self.flavor in (b'wOFF', b'wOF2'):
            raise SystemExit(f'{path}: WOFF/WOFF2 не поддерживается — нужен TTF/OTF')
        if self.flavor not in (b'\0\1\0\0', b'OTTO', b'true'):
            raise SystemExit(f'{path}: не шрифт TrueType/OpenType')
        self.t = {}
        for i in range(u16(data, base + 4)):
            tag, _, off, ln = struct.unpack_from('>4sIII', data, base + 12 + 16 * i)
            self.t[tag.decode('latin1')] = data[off:off + ln]
        for need in ('head', 'hhea', 'hmtx', 'maxp', 'cmap'):
            if need not in self.t:
                raise SystemExit(f'{path}: нет таблицы {need}')
        h = self.t['head']
        self.upem = u16(h, 18)
        self.bbox = struct.unpack_from('>4h', h, 36)
        self.mac_style = u16(h, 44)
        self.ng = u16(self.t['maxp'], 4)
        hh = self.t['hhea']
        self.ascender, self.descender, self.line_gap = struct.unpack_from('>3h', hh, 4)
        nhm = u16(hh, 34)
        hm = self.t['hmtx']
        self.adv, self.lsb = [], []
        for i in range(self.ng):
            if i < nhm:
                a, l = struct.unpack_from('>Hh', hm, 4 * i)
            else:
                a = self.adv[nhm - 1]
                l = s16(hm, 4 * nhm + 2 * (i - nhm)) if 4 * nhm + 2 * (i - nhm) + 2 <= len(hm) else 0
            self.adv.append(a)
            self.lsb.append(l)
        self.os2 = self._os2()
        self.names = self._names()
        self.cmap = self._cmap()
        self.cff = None
        if 'glyf' in self.t:
            ilf = s16(h, 50)
            lo = self.t['loca']
            if ilf == 0:
                self.loca = [2 * v for v in struct.unpack_from('>%dH' % (self.ng + 1), lo)]
            else:
                self.loca = list(struct.unpack_from('>%dI' % (self.ng + 1), lo))
        elif 'CFF ' in self.t:
            self.cff = Cff(self.t['CFF '], self.ng)
        elif 'CFF2' in self.t:
            raise SystemExit(f'{path}: CFF2 (вариативный OTF) не поддерживается')
        else:
            raise SystemExit(f'{path}: нет контуров (glyf/CFF)')
        self.axes, self.instances = self._fvar()
        self.coords = []                          # нормализованные координаты вариаций; [] — стиль по умолчанию
        self._cache = {}

    # -- метаданные
    def _os2(self):
        b = self.t.get('OS/2')
        if not b:
            return {}
        o = {'version': u16(b, 0), 'xavg': s16(b, 2), 'weight': u16(b, 4), 'width': u16(b, 6), 'fstype': u16(b, 8),
             'fsselection': u16(b, 62), 'first': u16(b, 64), 'last': u16(b, 66),
             'typo': struct.unpack_from('>3h', b, 68), 'win': struct.unpack_from('>2H', b, 74)}
        if o['version'] >= 2 and len(b) >= 90:
            o['xheight'], o['capheight'] = struct.unpack_from('>2h', b, 86)
        return o

    def _names(self):
        b = self.t.get('name')
        out = {}
        if not b:
            return out
        n, so = u16(b, 2), u16(b, 4)
        for i in range(n):
            pl, en, la, nid, ln, off = struct.unpack_from('>6H', b, 6 + 12 * i)
            raw = b[so + off:so + off + ln]
            if pl in (0, 3):
                s = raw.decode('utf-16-be', 'replace')
            elif pl == 1 and en == 0:
                s = raw.decode('mac_roman', 'replace')
            else:
                continue
            out[(pl, en, la, nid)] = s
        return out

    def name(self, nid):
        for key in sorted(self.names, key=lambda k: (k[0] != 3, k[2] != 0x409, k[0] != 1, k)):
            if key[3] == nid:
                return self.names[key]
        return None

    def _cmap(self):
        b = self.t['cmap']
        subs = []
        for i in range(u16(b, 2)):
            pl, en, off = struct.unpack_from('>HHI', b, 4 + 8 * i)
            subs.append((pl, en, off, u16(b, off)))
        def rank(s):                                       # одна лучшая подтаблица: Юникод > символьная > Mac
            pl, en, _, fmt = s
            if pl in (0, 3) and fmt == 12:
                return 0
            if (pl == 3 and en == 1) or (pl == 0 and fmt in (4, 6)):
                return 1
            if pl == 3 and en == 0:
                return 2
            if pl == 1 and en == 0:
                return 3
            return 9
        out = {}
        for pl, en, off, fmt in sorted(subs, key=rank):
            if rank((pl, en, off, fmt)) == 9:
                continue
            m = self._cmap_sub(b, off, fmt)
            if not m:
                continue
            if pl == 1 and en == 0:
                m = {ord(bytes([c]).decode('mac_roman')): g for c, g in m.items() if c < 256}
            elif pl == 3 and en == 0:                          # символьный: F020… → ASCII
                m = {**m, **{c - 0xF000: g for c, g in m.items() if 0xF000 <= c <= 0xF0FF}}
            out = m
            break
        return {c: g for c, g in out.items() if 0 < g < self.ng}

    @staticmethod
    def _cmap_sub(b, o, fmt):
        m = {}
        if fmt == 0:
            for c in range(256):
                m[c] = b[o + 6 + c]
        elif fmt == 4:
            n = u16(b, o + 6) // 2
            ends = struct.unpack_from('>%dH' % n, b, o + 14)
            starts = struct.unpack_from('>%dH' % n, b, o + 16 + 2 * n)
            deltas = struct.unpack_from('>%dh' % n, b, o + 16 + 4 * n)
            ro = o + 16 + 6 * n
            ranges = struct.unpack_from('>%dH' % n, b, ro)
            for s in range(n):
                for c in range(starts[s], ends[s] + 1):
                    if c == 0xFFFF:
                        continue
                    if ranges[s] == 0:
                        g = (c + deltas[s]) & 0xFFFF
                    else:
                        gp = ro + 2 * s + ranges[s] + 2 * (c - starts[s])
                        if gp + 2 > len(b):
                            continue
                        g = u16(b, gp)
                        if g:
                            g = (g + deltas[s]) & 0xFFFF
                    if g:
                        m[c] = g
        elif fmt == 6:
            first, cnt = u16(b, o + 6), u16(b, o + 8)
            for i in range(cnt):
                m[first + i] = u16(b, o + 10 + 2 * i)
        elif fmt == 12:
            for i in range(u32(b, o + 12)):
                sc, ec, sg = struct.unpack_from('>3I', b, o + 16 + 12 * i)
                for c in range(sc, ec + 1):
                    m[c] = sg + c - sc
        else:
            return None
        return m

    def glyph_names(self):
        p = self.t.get('post')
        if p and u32(p, 0) == 0x20000:
            n = u16(p, 32)
            idx = struct.unpack_from('>%dH' % n, p, 34)
            pos, extra = 34 + 2 * n, []
            while pos < len(p):
                ln = p[pos]
                extra.append(p[pos + 1:pos + 1 + ln].decode('latin1'))
                pos += 1 + ln
            return [MAC_GLYPHS[i] if i < 258 else (extra[i - 258] if i - 258 < len(extra) else f'g{k}')
                    for k, i in enumerate(idx)]
        return None

    # -- вариации
    def _fvar(self):
        b = self.t.get('fvar')
        if not b:
            return [], []
        ao, na, asz, ni, isz = u16(b, 4), u16(b, 8), u16(b, 10), u16(b, 12), u16(b, 14)
        axes = []
        for i in range(na):
            p = ao + asz * i
            axes.append((b[p:p + 4].decode('latin1'), fixed(b, p + 4), fixed(b, p + 8), fixed(b, p + 12), u16(b, p + 18)))
        insts = []
        for i in range(ni):
            p = ao + asz * na + isz * i
            sub = self.name(u16(b, p)) or f'#{i}'
            insts.append((sub, {axes[a][0]: fixed(b, p + 4 + 4 * a) for a in range(na)}))
        return axes, insts

    def set_style(self, style):
        """Стиль вариативного шрифта: имя («SemiBold») или оси («wght=600,wdth=80»)."""
        if not style:
            return
        if not self.axes:
            raise SystemExit(f'{self.path}: шрифт не вариативный — стиль «{style}» задать нельзя')
        user = None
        if '=' in style:
            user = {}
            for part in style.split(','):
                k, v = part.split('=')
                user[k.strip()] = float(v)
            unknown = set(user) - {a[0] for a in self.axes}
            if unknown:
                raise SystemExit(f'{self.path}: нет осей {", ".join(sorted(unknown))}')
        else:
            norm = lambda s: re.sub(r'\s+', ' ', s.strip().lower())
            for sub, c in self.instances:
                if norm(sub) == norm(style):
                    user = c
            if user is None:
                raise SystemExit(f'{self.path}: нет стиля «{style}»; есть: ' + ', '.join(s for s, _ in self.instances))
        self.user_coords = user
        self.coords = self._normalize(user)
        self._cache = {}

    def _normalize(self, user):
        coords = []
        maps = self._avar()
        for i, (tag, mn, df, mx, _) in enumerate(self.axes):
            v = min(max(user.get(tag, df), mn), mx)
            n = (v - df) / (df - mn) if v < df else (v - df) / (mx - df) if v > df else 0.0
            if i < len(maps) and maps[i]:
                seg = maps[i]
                for k in range(1, len(seg)):
                    (a0, b0), (a1, b1) = seg[k - 1], seg[k]
                    if a0 <= n <= a1:
                        n = b0 + (b1 - b0) * (n - a0) / (a1 - a0) if a1 != a0 else b0
                        break
            coords.append(round(n * 16384) / 16384)
        return coords

    def _avar(self):
        b = self.t.get('avar')
        if not b:
            return []
        out, p = [], 8
        for _ in range(u16(b, 6)):
            n = u16(b, p)
            out.append([(f2d14(b, p + 2 + 4 * k), f2d14(b, p + 4 + 4 * k)) for k in range(n)])
            p += 2 + 4 * n
        return out

    def _gvar_data(self, gid):
        b = self.t.get('gvar')
        if not b or not self.coords:
            return None
        if not hasattr(self, '_gv'):
            axes, nshared, so = u16(b, 4), u16(b, 6), u32(b, 8)
            gc, flags, do = u16(b, 12), u16(b, 14), u32(b, 16)
            if flags & 1:
                offs = struct.unpack_from('>%dI' % (gc + 1), b, 20)
            else:
                offs = [2 * v for v in struct.unpack_from('>%dH' % (gc + 1), b, 20)]
            shared = [[f2d14(b, so + 2 * (axes * t + a)) for a in range(axes)] for t in range(nshared)]
            self._gv = (axes, shared, do, offs, gc)
        axes, shared, do, offs, gc = self._gv
        if gid >= gc or offs[gid] == offs[gid + 1]:
            return None
        return b[do + offs[gid]:do + offs[gid + 1]], axes, shared

    def _gvar_deltas(self, gid, pts, ends, interpolate):
        """Сдвиги точек глифа (pts — с 4 фантомными в конце) в текущем стиле."""
        n = len(pts)
        dx, dy = [0.0] * n, [0.0] * n
        got = self._gvar_data(gid)
        if not got:
            return dx, dy
        data, axes, shared = got
        tvc, doff = u16(data, 0), u16(data, 2)
        hdrs, p = [], 4
        for _ in range(tvc & 0x0FFF):
            size, ti = u16(data, p), u16(data, p + 2)
            p += 4
            if ti & 0x8000:
                peak = [f2d14(data, p + 2 * a) for a in range(axes)]
                p += 2 * axes
            else:
                peak = shared[ti & 0x0FFF]
            lo = hi = None
            if ti & 0x4000:
                lo = [f2d14(data, p + 2 * a) for a in range(axes)]
                hi = [f2d14(data, p + 2 * axes + 2 * a) for a in range(axes)]
                p += 4 * axes
            hdrs.append((size, ti, peak, lo, hi))
        q = doff
        shared_pts = None
        if tvc & 0x8000:
            shared_pts, q = _packed_points(data, q)
        for size, ti, peak, lo, hi in hdrs:
            end = q + size
            sc = support_scalar(self.coords, peak, lo, hi)
            if sc:
                r = q
                if ti & 0x2000:
                    which, r = _packed_points(data, r)
                else:
                    which = shared_pts
                cnt = n if which is None else len(which)
                xd, r = _packed_deltas(data, r, cnt)
                yd, r = _packed_deltas(data, r, cnt)
                if which is None:
                    for i in range(n):
                        dx[i] += sc * xd[i]
                        dy[i] += sc * yd[i]
                else:
                    tx, ty = [None] * n, [None] * n
                    for k, i in enumerate(which):
                        if i < n:
                            tx[i], ty[i] = xd[k], yd[k]
                    if interpolate:
                        _iup(tx, ty, pts, ends)
                    for i in range(n):
                        if tx[i] is not None:
                            dx[i] += sc * tx[i]
                            dy[i] += sc * ty[i]
            q = end
        return dx, dy

    def _hvar_adv(self, gid):
        b = self.t.get('HVAR')
        if not b or not self.coords:
            return None
        if not hasattr(self, '_hv'):
            self._hv = VarStore(b, u32(b, 4)), u32(b, 8)
        vs, amap = self._hv
        outer, inner = delta_set_map(b, amap, gid) if amap else (0, gid)
        return vs.delta(outer, inner, self.coords)

    # -- контуры
    def outline(self, gid):
        """Глиф → (контуры [[(x, y, on)…]…] — квадратичные, как в TrueType; ширина)."""
        if gid in self._cache:
            return self._cache[gid]
        if self.cff:
            cs = self.cff.outline(gid)
            res = ([_reverse(c) for c in cs], float(self.adv[gid]))
        else:
            res = self._tt_outline(gid, 0)
        self._cache[gid] = res
        return res

    def _tt_outline(self, gid, depth):
        if depth > 16:
            raise SystemExit(f'{self.path}: слишком глубокие составные глифы ({gid})')
        g = self.t['glyf'][self.loca[gid]:self.loca[gid + 1]] if gid < self.ng else b''
        adv, lsb = self.adv[gid], self.lsb[gid]
        xmin = s16(g, 2) if len(g) >= 10 else 0
        phantom = [(xmin - lsb, 0), (xmin - lsb + adv, 0), (0, 0), (0, 0)]
        if len(g) < 10 or s16(g, 0) == 0:
            pts, ends, comps = [], [], None
        elif s16(g, 0) > 0:
            ends, pts = _simple_glyph(g)
            comps = None
        else:
            comps = _composite_glyph(g)
            pts, ends = [], []
        if comps is None:
            allp = [(x, y) for x, y, _ in pts] + phantom
            if self.coords:
                dx, dy = self._gvar_deltas(gid, allp, ends, True)
                allp = [(allp[i][0] + dx[i], allp[i][1] + dy[i]) for i in range(len(allp))]
            ox, aw = allp[-4][0], allp[-3][0] - allp[-4][0]
            contours, s = [], 0
            for e in ends:
                contours.append([(allp[i][0] - ox, allp[i][1], pts[i][2]) for i in range(s, e + 1)])
                s = e + 1
        else:
            offs = [(c['args'][0], c['args'][1]) if c['xy'] else (0, 0) for c in comps] + phantom
            if self.coords:
                dx, dy = self._gvar_deltas(gid, offs, [], False)
                offs = [(offs[i][0] + dx[i], offs[i][1] + dy[i]) for i in range(len(offs))]
            ox, aw = offs[-4][0], offs[-3][0] - offs[-4][0]
            contours = []
            for k, c in enumerate(comps):
                sub, sub_adv = self._tt_outline(c['gid'], depth + 1)
                a, b, cc, d = c['m']
                tr = [[(a * x + cc * y, b * x + d * y, on) for x, y, on in ct] for ct in sub]
                if c['xy']:
                    ex, ey = offs[k]
                    if c['flags'] & 0x800:                 # SCALED_COMPONENT_OFFSET
                        ex, ey = a * ex + cc * ey, b * ex + d * ey
                else:                                      # совмещение точек
                    flat_parent = [p for ct in contours for p in ct]
                    flat_child = [p for ct in tr for p in ct]
                    i1, i2 = c['args']
                    if i1 < len(flat_parent) and i2 < len(flat_child):
                        ex, ey = flat_parent[i1][0] - flat_child[i2][0], flat_parent[i1][1] - flat_child[i2][1]
                    else:
                        ex = ey = 0
                contours += [[(x + ex, y + ey, on) for x, y, on in ct] for ct in tr]
                if c['flags'] & 0x200:                     # USE_MY_METRICS
                    aw = sub_adv
            contours = [[(x - ox, y, on) for x, y, on in ct] for ct in contours]
        if self.coords:
            hv = self._hvar_adv(gid)
            if hv is not None:
                aw = adv + hv
        return contours, float(aw)

    def cap_height(self):
        return self._measure('HIEZT', 'capheight', 0.7)

    def x_height(self):
        return self._measure('xzvw', 'xheight', 0.5)

    def _measure(self, chars, key, frac):
        for ch in chars:
            g = self.cmap.get(ord(ch))
            if g:
                cs, _ = self.outline(g)
                ys = [y for c in cs for _, y, on in c if on]
                if ys:
                    return max(ys)
        return self.os2.get(key) or frac * self.upem

    # -- кернинг
    def kerning(self, gids):
        """Пары {(левый, правый): сдвиг} среди gids: GPOS (признак kern, с вариациями) или старая kern."""
        gset = set(gids)
        pairs = self._gpos_kern(gset) if 'GPOS' in self.t else {}
        if not pairs and 'kern' in self.t:
            pairs = self._kern_table(gset)
        return {k: v for k, v in pairs.items() if v}

    def _kern_table(self, gset):
        b = self.t['kern']
        out = {}
        if u16(b, 0) != 0:
            return out
        p = 4
        for _ in range(u16(b, 2)):
            ln, cov = u16(b, p + 2), u16(b, p + 4)
            if cov >> 8 == 0 and cov & 1 and not cov & 6:
                n = u16(b, p + 6)
                for k in range(n):
                    l, r, v = struct.unpack_from('>HHh', b, p + 14 + 6 * k)
                    if l in gset and r in gset:
                        out[(l, r)] = out.get((l, r), 0) + v
            p += ln
        return out

    def _gpos_kern(self, gset):
        g = self.t['GPOS']
        fl, ll = u16(g, 6), u16(g, 8)
        lookups = set()
        for i in range(u16(g, fl)):
            if g[fl + 2 + 6 * i:fl + 6 + 6 * i] == b'kern':
                ft = fl + u16(g, fl + 6 + 6 * i)
                lookups.update(u16(g, ft + 4 + 2 * k) for k in range(u16(g, ft + 2)))
        vs = None
        if self.coords and 'GDEF' in self.t:
            gd = self.t['GDEF']
            if u16(gd, 2) >= 3 and len(gd) >= 18 and u32(gd, 14):
                vs = VarStore(gd, u32(gd, 14))
        total = {}
        for li in sorted(lookups):
            lo = ll + u16(g, ll + 2 + 2 * li)
            lt, ns = u16(g, lo), u16(g, lo + 4)
            decided = {}
            for k in range(ns):
                so = lo + u16(g, lo + 6 + 2 * k)
                t = lt
                if t == 9:
                    t, so = u16(g, so + 2), so + u32(g, so + 4)
                if t == 2:
                    self._pairpos(g, so, gset, decided, vs)
            for key, v in decided.items():
                if v:
                    total[key] = total.get(key, 0) + v
        return total

    def _pairpos(self, g, so, gset, decided, vs):
        fmt, cov = u16(g, so), _coverage(g, so + u16(g, so + 2))
        vf1, vf2 = u16(g, so + 4), u16(g, so + 6)
        s1, s2 = 2 * bin(vf1 & 0xFF).count('1'), 2 * bin(vf2 & 0xFF).count('1')
        if fmt == 1:
            for ci, g1 in enumerate(cov):
                if g1 not in gset:
                    continue
                ps = so + u16(g, so + 10 + 2 * ci)
                rec = 2 + s1 + s2
                for k in range(u16(g, ps)):
                    r = ps + 2 + rec * k
                    g2 = u16(g, r)
                    if g2 in gset and (g1, g2) not in decided:
                        decided[(g1, g2)] = self._xadv(g, r + 2, vf1, so, vs)
        elif fmt == 2:
            cd1, cd2 = _classdef(g, so + u16(g, so + 8)), _classdef(g, so + u16(g, so + 10))
            n1, n2 = u16(g, so + 12), u16(g, so + 14)
            rec = s1 + s2
            cls2 = {g2: cd2.get(g2, 0) for g2 in gset}
            memo = {}
            for g1 in cov:
                if g1 not in gset:
                    continue
                c1 = cd1.get(g1, 0)
                if c1 >= n1:
                    continue
                for g2, c2 in cls2.items():
                    if c2 >= n2 or (g1, g2) in decided:
                        continue
                    key = (c1, c2)
                    if key not in memo:
                        memo[key] = self._xadv(g, so + 16 + rec * (c1 * n2 + c2), vf1, so, vs)
                    decided[(g1, g2)] = memo[key]

    def _xadv(self, g, p, vf, base, vs):
        v = 0.0
        for bit in (1, 2, 4, 8, 0x10, 0x20, 0x40, 0x80):
            if vf & bit:
                if bit == 4:
                    v += s16(g, p)
                elif bit == 0x40 and vs and u16(g, p):
                    d = base + u16(g, p)
                    if u16(g, d + 4) == 0x8000:
                        v += vs.delta(u16(g, d), u16(g, d + 2), self.coords)
                p += 2
        return v


def _coverage(g, o):
    fmt = u16(g, o)
    if fmt == 1:
        return list(struct.unpack_from('>%dH' % u16(g, o + 2), g, o + 4))
    out = []
    for i in range(u16(g, o + 2)):
        s, e, _ = struct.unpack_from('>3H', g, o + 4 + 6 * i)
        out.extend(range(s, e + 1))
    return out


def _classdef(g, o):
    fmt, out = u16(g, o), {}
    if fmt == 1:
        st, n = u16(g, o + 2), u16(g, o + 4)
        for i in range(n):
            out[st + i] = u16(g, o + 6 + 2 * i)
    elif fmt == 2:
        for i in range(u16(g, o + 2)):
            s, e, c = struct.unpack_from('>3H', g, o + 4 + 6 * i)
            for k in range(s, e + 1):
                out[k] = c
    return out


def _packed_points(b, p):
    c = b[p]
    p += 1
    if c & 0x80:
        c = ((c & 0x7F) << 8) | b[p]
        p += 1
    if c == 0:
        return None, p
    pts, last = [], 0
    while len(pts) < c:
        ctl = b[p]
        p += 1
        for _ in range((ctl & 0x7F) + 1):
            if ctl & 0x80:
                v = u16(b, p)
                p += 2
            else:
                v = b[p]
                p += 1
            last += v
            pts.append(last)
    return pts[:c], p


def _packed_deltas(b, p, count):
    out = []
    while len(out) < count:
        ctl = b[p]
        p += 1
        run = (ctl & 0x3F) + 1
        if ctl & 0x80:
            out.extend([0] * run)
        elif ctl & 0x40:
            out.extend(struct.unpack_from('>%dh' % run, b, p))
            p += 2 * run
        else:
            out.extend(struct.unpack_from('>%db' % run, b, p))
            p += run
    return out[:count], p


def _iup(tx, ty, pts, ends):
    """Достроить сдвиги нетронутых точек контуров (IUP, как в OpenType gvar)."""
    s = 0
    for e in ends:
        idx = list(range(s, e + 1))
        s = e + 1
        touched = [i for i in idx if tx[i] is not None]
        if not touched:
            continue
        if len(touched) == len(idx):
            continue
        if len(touched) == 1:
            t = touched[0]
            for i in idx:
                if tx[i] is None:
                    tx[i], ty[i] = tx[t], ty[t]
            continue
        n = len(idx)
        pos = {i: k for k, i in enumerate(idx)}
        for k, t in enumerate(touched):
            t2 = touched[(k + 1) % len(touched)]
            a, b = pos[t], pos[t2]
            run = []
            j = (a + 1) % n
            while j != b:
                run.append(idx[j])
                j = (j + 1) % n
            if not run:
                continue
            for arr, axis in ((tx, 0), (ty, 1)):
                c1, c2 = pts[t][axis], pts[t2][axis]
                d1, d2 = arr[t], arr[t2]
                if c1 == c2:
                    for i in run:
                        arr[i] = d1 if d1 == d2 else 0.0
                    continue
                if c1 > c2:
                    c1, c2, d1, d2 = c2, c1, d2, d1
                for i in run:
                    c = pts[i][axis]
                    arr[i] = d1 if c <= c1 else d2 if c >= c2 else d1 + (c - c1) * (d2 - d1) / (c2 - c1)


def _simple_glyph(g):
    nc = s16(g, 0)
    ends = struct.unpack_from('>%dH' % nc, g, 10)
    n = ends[-1] + 1
    p = 10 + 2 * nc
    p += 2 + u16(g, p)
    flags = []
    while len(flags) < n:
        f = g[p]
        p += 1
        flags.append(f)
        if f & 8:
            flags.extend([f] * g[p])
            p += 1
    flags = flags[:n]
    coords = []
    for short, same in ((2, 0x10), (4, 0x20)):
        v, out = 0, []
        for f in flags:
            if f & short:
                v += g[p] if f & same else -g[p]
                p += 1
            elif not f & same:
                v += s16(g, p)
                p += 2
            out.append(v)
        coords.append(out)
    return list(ends), [(coords[0][i], coords[1][i], bool(flags[i] & 1)) for i in range(n)]


def _composite_glyph(g):
    p, comps = 10, []
    while True:
        fl, gi = struct.unpack_from('>HH', g, p)
        p += 4
        if fl & 1:
            a1, a2 = struct.unpack_from('>hh' if fl & 2 else '>HH', g, p)
            p += 4
        else:
            a1, a2 = struct.unpack_from('>bb' if fl & 2 else '>BB', g, p)
            p += 2
        m = (1.0, 0.0, 0.0, 1.0)
        if fl & 8:
            sc = f2d14(g, p)
            m = (sc, 0.0, 0.0, sc)
            p += 2
        elif fl & 0x40:
            m = (f2d14(g, p), 0.0, 0.0, f2d14(g, p + 2))
            p += 4
        elif fl & 0x80:
            m = (f2d14(g, p), f2d14(g, p + 2), f2d14(g, p + 4), f2d14(g, p + 6))
            p += 8
        comps.append({'flags': fl, 'gid': gi, 'args': (a1, a2), 'xy': bool(fl & 2), 'm': m})
        if not fl & 0x20:
            return comps


def _reverse(contour):
    """Обратный обход (контуры CFF идут против часовой, в TrueType внешний — по часовой)."""
    return [contour[0]] + contour[:0:-1] if contour else contour


# ---------------------------------------------------------------- CFF (OTF) → квадратичные контуры

def _cff_index(b, p):
    n = u16(b, p)
    if n == 0:
        return [], p + 2
    osz = b[p + 2]
    offs = [int.from_bytes(b[p + 3 + osz * i:p + 3 + osz * (i + 1)], 'big') for i in range(n + 1)]
    base = p + 2 + osz * (n + 1)
    return [b[base + offs[i]:base + offs[i + 1]] for i in range(n)], base + offs[n]


def _cff_dict(d):
    out, ops, p = {}, [], 0
    while p < len(d):
        b0 = d[p]
        if b0 <= 21:
            if b0 == 12:
                key = 1200 + d[p + 1]
                p += 2
            else:
                key = b0
                p += 1
            out[key], ops = ops, []
        elif b0 == 28:
            ops.append(s16(d, p + 1))
            p += 3
        elif b0 == 29:
            ops.append(s32(d, p + 1))
            p += 5
        elif b0 == 30:
            s, p = '', p + 1
            while True:
                byte = d[p]
                p += 1
                done = False
                for nib in (byte >> 4, byte & 15):
                    if nib == 15:
                        done = True
                        break
                    s += '0123456789.EE?-'[nib] + ('-' if nib == 12 else '')
                if done:
                    break
            ops.append(float(s.replace('E-', 'e-').replace('E', 'e') or 0))
        elif 32 <= b0 <= 246:
            ops.append(b0 - 139)
            p += 1
        elif 247 <= b0 <= 250:
            ops.append((b0 - 247) * 256 + d[p + 1] + 108)
            p += 2
        elif 251 <= b0 <= 254:
            ops.append(-(b0 - 251) * 256 - d[p + 1] - 108)
            p += 2
        else:
            p += 1
    return out


def _bias(subrs):
    n = len(subrs)
    return 107 if n < 1240 else 1131 if n < 33900 else 32768


class Cff:
    def __init__(self, b, ng):
        p = b[2]
        _, p = _cff_index(b, p)
        tops, p = _cff_index(b, p)
        _, p = _cff_index(b, p)
        self.gsubrs, p = _cff_index(b, p)
        top = _cff_dict(tops[0])
        self.charstrings, _ = _cff_index(b, top[17][0])
        fm = top.get(1207)
        self.scale = fm[0] * 1000 if fm and fm[0] else 1.0
        self.fd_of = None
        if 1236 in top:                                    # CID: FDArray + FDSelect
            fds, _ = _cff_index(b, top[1236][0])
            self.privates = [self._private(b, _cff_dict(fd)) for fd in fds]
            o = top[1237][0]
            fmt = b[o]
            if fmt == 0:
                self.fd_of = list(b[o + 1:o + 1 + len(self.charstrings)])
            else:
                nr = u16(b, o + 1)
                self.fd_of = [0] * len(self.charstrings)
                for i in range(nr):
                    first, fd = u16(b, o + 3 + 3 * i), b[o + 5 + 3 * i]
                    last = u16(b, o + 3 + 3 * (i + 1))
                    for gid in range(first, min(last, len(self.fd_of))):
                        self.fd_of[gid] = fd
        else:
            self.privates = [self._private(b, top)]

    @staticmethod
    def _private(b, d):
        if 18 not in d:
            return []
        size, off = d[18]
        pd = _cff_dict(b[off:off + size])
        if 19 in pd:
            subrs, _ = _cff_index(b, off + pd[19][0])
            return subrs
        return []

    def outline(self, gid):
        lsubrs = self.privates[self.fd_of[gid] if self.fd_of else 0] if self.privates else []
        cubic = _t2_run(self.charstrings[gid], self.gsubrs, lsubrs)
        k = self.scale
        out = []
        for c in cubic:
            pts = [(c[0][0] * k, c[0][1] * k, True)]
            for seg in c[1:]:
                if len(seg) == 1:
                    pts.append((seg[0][0] * k, seg[0][1] * k, True))
                else:
                    p0 = (pts[-1][0], pts[-1][1])
                    (x1, y1), (x2, y2), (x3, y3) = seg
                    for q, e in _cu2qu(p0, (x1 * k, y1 * k), (x2 * k, y2 * k), (x3 * k, y3 * k), 1.0):
                        pts.append((q[0], q[1], False))
                        pts.append((e[0], e[1], True))
            if len(pts) > 1 and pts[-1][:2] == pts[0][:2]:
                pts.pop()
            if len(pts) >= 2:
                out.append(pts)
        return out


def _t2_run(code, gsubrs, lsubrs):
    """Type 2 charstring → контуры [[старт, (точка,) | (c1, c2, точка)…]…]."""
    contours, st = [], {'x': 0.0, 'y': 0.0, 'stems': 0, 'width': False, 'stack': [], 'cur': None, 'done': False}
    gb, lb = _bias(gsubrs), _bias(lsubrs)

    def pt(dx, dy):
        st['x'] += dx
        st['y'] += dy
        return (st['x'], st['y'])

    def moveto(dx, dy):
        p = pt(dx, dy)
        st['cur'] = [p]
        contours.append(st['cur'])

    def line(dx, dy):
        st['cur'].append((pt(dx, dy),))

    def curve(a, b, c, d, e, f):
        p1 = pt(a, b)
        p2 = pt(c, d)
        p3 = pt(e, f)
        st['cur'].append((p1, p2, p3))

    def take_width(nargs_even):
        s = st['stack']
        if not st['width']:
            st['width'] = True
            if nargs_even(len(s)):
                del s[0]

    def run(cs, depth):
        if depth > 10:
            return
        s = st['stack']
        i = 0
        while i < len(cs) and not st['done']:
            b0 = cs[i]
            i += 1
            if b0 >= 32 or b0 == 28:
                if b0 == 28:
                    s.append(s16(cs, i))
                    i += 2
                elif b0 <= 246:
                    s.append(b0 - 139)
                elif b0 <= 250:
                    s.append((b0 - 247) * 256 + cs[i] + 108)
                    i += 1
                elif b0 <= 254:
                    s.append(-(b0 - 251) * 256 - cs[i] - 108)
                    i += 1
                else:
                    s.append(s32(cs, i) / 65536.0)
                    i += 4
                continue
            if b0 in (1, 3, 18, 23):                       # hstem vstem hstemhm vstemhm
                take_width(lambda n: n % 2 == 1)
                st['stems'] += len(s) // 2
                s.clear()
            elif b0 in (19, 20):                           # hintmask cntrmask
                take_width(lambda n: n % 2 == 1)
                st['stems'] += len(s) // 2
                s.clear()
                i += (st['stems'] + 7) // 8
            elif b0 == 21:                                 # rmoveto
                take_width(lambda n: n > 2)
                moveto(s[-2], s[-1])
                s.clear()
            elif b0 == 22:                                 # hmoveto
                take_width(lambda n: n > 1)
                moveto(s[-1], 0)
                s.clear()
            elif b0 == 4:                                  # vmoveto
                take_width(lambda n: n > 1)
                moveto(0, s[-1])
                s.clear()
            elif b0 == 5:                                  # rlineto
                for k in range(0, len(s) - 1, 2):
                    line(s[k], s[k + 1])
                s.clear()
            elif b0 in (6, 7):                             # hlineto vlineto
                horiz = b0 == 6
                for v in s:
                    line(v, 0) if horiz else line(0, v)
                    horiz = not horiz
                s.clear()
            elif b0 == 8:                                  # rrcurveto
                for k in range(0, len(s) - 5, 6):
                    curve(*s[k:k + 6])
                s.clear()
            elif b0 == 24:                                 # rcurveline
                k = 0
                while k + 6 <= len(s) - 2:
                    curve(*s[k:k + 6])
                    k += 6
                line(s[k], s[k + 1])
                s.clear()
            elif b0 == 25:                                 # rlinecurve
                k = 0
                while k + 2 <= len(s) - 6:
                    line(s[k], s[k + 1])
                    k += 2
                curve(*s[k:k + 6])
                s.clear()
            elif b0 == 26:                                 # vvcurveto
                k, dx1 = 0, 0
                if len(s) % 2:
                    dx1, k = s[0], 1
                while k + 4 <= len(s):
                    curve(dx1, s[k], s[k + 1], s[k + 2], 0, s[k + 3])
                    dx1 = 0
                    k += 4
                s.clear()
            elif b0 == 27:                                 # hhcurveto
                k, dy1 = 0, 0
                if len(s) % 2:
                    dy1, k = s[0], 1
                while k + 4 <= len(s):
                    curve(s[k], dy1, s[k + 1], s[k + 2], s[k + 3], 0)
                    dy1 = 0
                    k += 4
                s.clear()
            elif b0 in (30, 31):                           # vhcurveto hvcurveto
                horiz = b0 == 31
                k = 0
                while k + 4 <= len(s):
                    last = len(s) - k == 5
                    a, b, c, d = s[k:k + 4]
                    e = s[k + 4] if last else 0
                    if horiz:
                        curve(a, 0, b, c, e, d)
                    else:
                        curve(0, a, b, c, d, e)
                    horiz = not horiz
                    k += 5 if last else 4
                s.clear()
            elif b0 == 10:                                 # callsubr
                n = int(s.pop()) + lb
                if 0 <= n < len(lsubrs):
                    run(lsubrs[n], depth + 1)
            elif b0 == 29:                                 # callgsubr
                n = int(s.pop()) + gb
                if 0 <= n < len(gsubrs):
                    run(gsubrs[n], depth + 1)
            elif b0 == 11:                                 # return
                return
            elif b0 == 14:                                 # endchar
                take_width(lambda n: n in (1, 5))
                st['done'] = True
                s.clear()
                return
            elif b0 == 12:
                b1 = cs[i]
                i += 1
                if b1 == 35:                               # flex
                    curve(*s[0:6])
                    curve(*s[6:12])
                elif b1 == 34:                             # hflex
                    dx1, dx2, dy2, dx3, dx4, dx5, dx6 = s[:7]
                    curve(dx1, 0, dx2, dy2, dx3, 0)
                    curve(dx4, 0, dx5, -dy2, dx6, 0)
                elif b1 == 36:                             # hflex1
                    dx1, dy1, dx2, dy2, dx3, dx4, dx5, dy5, dx6 = s[:9]
                    curve(dx1, dy1, dx2, dy2, dx3, 0)
                    curve(dx4, 0, dx5, dy5, dx6, -(dy1 + dy2 + dy5))
                elif b1 == 37:                             # flex1
                    d = s[:11]
                    sx, sy = sum(d[0:10:2]), sum(d[1:10:2])
                    curve(*d[0:6])
                    if abs(sx) > abs(sy):
                        curve(d[6], d[7], d[8], d[9], d[10], -sy)
                    else:
                        curve(d[6], d[7], d[8], d[9], -sx, d[10])
                elif b1 == 9:
                    s.append(abs(s.pop()))
                elif b1 == 10:
                    b_, a_ = s.pop(), s.pop()
                    s.append(a_ + b_)
                elif b1 == 11:
                    b_, a_ = s.pop(), s.pop()
                    s.append(a_ - b_)
                elif b1 == 12:
                    b_, a_ = s.pop(), s.pop()
                    s.append(a_ / b_ if b_ else 0)
                elif b1 == 14:
                    s.append(-s.pop())
                elif b1 == 18:
                    s.pop()
                elif b1 == 24:
                    b_, a_ = s.pop(), s.pop()
                    s.append(a_ * b_)
                elif b1 == 27:
                    s.append(s[-1])
                elif b1 == 28:
                    s[-1], s[-2] = s[-2], s[-1]
                if b1 in (34, 35, 36, 37):
                    s.clear()
            else:
                s.clear()

    run(code, 0)
    return contours


def _cu2qu(p0, p1, p2, p3, tol):
    """Кубическая кривая → квадратичные [(контрольная, конец)…] с ошибкой не больше tol."""
    def split(a, b, c, d, t):
        ab = ((1 - t) * a[0] + t * b[0], (1 - t) * a[1] + t * b[1])
        bc = ((1 - t) * b[0] + t * c[0], (1 - t) * b[1] + t * c[1])
        cd = ((1 - t) * c[0] + t * d[0], (1 - t) * c[1] + t * d[1])
        abc = ((1 - t) * ab[0] + t * bc[0], (1 - t) * ab[1] + t * bc[1])
        bcd = ((1 - t) * bc[0] + t * cd[0], (1 - t) * bc[1] + t * cd[1])
        m = ((1 - t) * abc[0] + t * bcd[0], (1 - t) * abc[1] + t * bcd[1])
        return (a, ab, abc, m), (m, bcd, cd, d)

    for n in range(1, 17):
        pieces, rest = [], (p0, p1, p2, p3)
        for k in range(n, 1, -1):
            first, rest = split(*rest, 1.0 / k)
            pieces.append(first)
        pieces.append(rest)
        out, ok = [], True
        for a, b, c, d in pieces:
            # ошибка приближения средней точкой: |a − 3b + 3c − d| · √3 / 36
            ex, ey = a[0] - 3 * b[0] + 3 * c[0] - d[0], a[1] - 3 * b[1] + 3 * c[1] - d[1]
            if math.hypot(ex, ey) * math.sqrt(3) / 36 > tol and n < 16:
                ok = False
                break
            out.append((((3 * (b[0] + c[0]) - a[0] - d[0]) / 4, (3 * (b[1] + c[1]) - a[1] - d[1]) / 4), d))
        if ok:
            return out
    return out


# ---------------------------------------------------------------- запись TrueType

def _checksum(b):
    b = b + b'\0' * (-len(b) % 4)
    return sum(struct.unpack('>%dI' % (len(b) // 4), b)) & 0xFFFFFFFF


def encode_glyph(contours):
    """Простой глиф TrueType (без инструкций) → (байты, bbox, точек, контуров)."""
    contours = [[(int(round(x)), int(round(y)), on) for x, y, on in c] for c in contours]
    contours = [c for c in contours if len(c) >= 3 and len({(x, y) for x, y, _ in c}) >= 2]
    if not contours:
        return b'', None, 0, 0
    pts = [p for c in contours for p in c]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    bbox = (min(xs), min(ys), max(xs), max(ys))
    ends, n = [], 0
    for c in contours:
        n += len(c)
        ends.append(n - 1)
    flags, xb, yb = [], bytearray(), bytearray()
    px = py = 0
    for x, y, on in pts:
        f = 1 if on else 0
        dx, dy = x - px, y - py
        px, py = x, y
        if dx == 0:
            f |= 0x10
        elif -255 <= dx <= 255:
            f |= 0x02 | (0x10 if dx > 0 else 0)
            xb.append(abs(dx))
        else:
            xb += struct.pack('>h', dx)
        if dy == 0:
            f |= 0x20
        elif -255 <= dy <= 255:
            f |= 0x04 | (0x20 if dy > 0 else 0)
            yb.append(abs(dy))
        else:
            yb += struct.pack('>h', dy)
        flags.append(f)
    fb, i = bytearray(), 0
    while i < len(flags):
        f, r = flags[i], 0
        while i + 1 + r < len(flags) and flags[i + 1 + r] == f and r < 255:
            r += 1
        if r:
            fb += bytes([f | 8, r])
        else:
            fb.append(f)
        i += 1 + r
    out = struct.pack('>h4h', len(contours), *bbox) + struct.pack('>%dH' % len(ends), *ends) + b'\0\0' + fb + xb + yb
    return out + b'\0' * (-len(out) % 4), bbox, len(pts), len(contours)


def build_cmap(cmap):
    """(0,3) и (3,1) — формат 4, (1,0) — формат 6 (Mac Roman), как у шрифтов игры."""
    codes = sorted(c for c in cmap if c <= 0xFFFF)
    segs, i = [], 0
    while i < len(codes):
        j = i
        while j + 1 < len(codes) and codes[j + 1] == codes[j] + 1:
            j += 1
        segs.append((codes[i], codes[j]))
        i = j + 1
    starts, ends, deltas, ranges, garr = [], [], [], [], []
    for s, e in segs:
        gl = [cmap[c] for c in range(s, e + 1)]
        starts.append(s)
        ends.append(e)
        if all(gl[k] - gl[0] == k for k in range(len(gl))):
            deltas.append((gl[0] - s) & 0xFFFF)
            ranges.append(None)
        else:
            deltas.append(0)
            ranges.append(len(garr))
            garr += gl
    starts.append(0xFFFF)
    ends.append(0xFFFF)
    deltas.append(1)
    ranges.append(None)
    n = len(starts)
    ro = []
    for k, r in enumerate(ranges):
        ro.append(0 if r is None else 2 * (n - k) + 2 * r)
    es = int(math.log2(n))
    sr = 2 * (1 << es)
    body = struct.pack('>4H', 2 * n, sr, es, 2 * n - sr)
    body += struct.pack('>%dH' % n, *ends) + b'\0\0' + struct.pack('>%dH' % n, *starts)
    body += struct.pack('>%dH' % n, *deltas) + struct.pack('>%dH' % n, *ro) + struct.pack('>%dH' % len(garr), *garr)
    f4 = struct.pack('>HHH', 4, 6 + len(body), 0) + body
    mac = {}
    for c in range(256):
        u = ord(bytes([c]).decode('mac_roman'))
        if u in cmap:
            mac[c] = cmap[u]
    if mac:
        first, last = min(mac), max(mac)
        ids = [mac.get(c, 0) for c in range(first, last + 1)]
        f6 = struct.pack('>5H', 6, 10 + 2 * len(ids), 0, first, len(ids)) + struct.pack('>%dH' % len(ids), *ids)
    else:
        f6 = None
    subs = [(0, 3, f4), (1, 0, f6), (3, 1, f4)] if f6 else [(0, 3, f4), (3, 1, f4)]
    head = struct.pack('>HH', 0, len(subs))
    off = 4 + 8 * len(subs)
    data, where = b'', {}
    for pl, en, blob in subs:
        if id(blob) not in where:
            where[id(blob)] = off + len(data)
            data += blob + b'\0' * (-len(blob) % 4)
        head += struct.pack('>HHI', pl, en, where[id(blob)])
    return head + data


def build_kern(pairs):
    items = sorted(pairs.items())
    if len(items) > 10920:                                # предел подтаблицы формата 0
        keep = set(k for k, _ in sorted(items, key=lambda kv: -abs(kv[1]))[:10920])
        items = [kv for kv in items if kv[0] in keep]
    n = len(items)
    es = int(math.log2(n)) if n else 0
    sr = 6 * (1 << es) if n else 0
    sub = struct.pack('>HHH', 0, 14 + 6 * n, 0x0001) + struct.pack('>4H', n, sr, es, 6 * n - sr)
    sub += b''.join(struct.pack('>HHh', l, r, v) for (l, r), v in items)
    return struct.pack('>HH', 0, 1) + sub


def build_post(names, base):
    idx, extra = [], []
    for n in names:
        if n in MAC_INDEX:
            idx.append(MAC_INDEX[n])
        else:
            idx.append(258 + len(extra))
            extra.append(n)
    out = struct.pack('>I', 0x20000) + base[4:32] + struct.pack('>H', len(names)) + struct.pack('>%dH' % len(idx), *idx)
    for n in extra:
        e = n.encode('latin1', 'replace')[:63]
        out += bytes([len(e)]) + e
    return out


def pack_sfnt(tables):
    tags = sorted(tables)
    n = len(tags)
    es = int(math.log2(n))
    sr = 16 * (1 << es)
    head = struct.pack('>IHHHH', 0x00010000, n, sr, es, 16 * n - sr)
    order = [t for t in ('head', 'hhea', 'maxp', 'OS/2', 'hmtx', 'cmap', 'loca', 'glyf', 'kern', 'name', 'post')
             if t in tables] + [t for t in tags if t not in ('head', 'hhea', 'maxp', 'OS/2', 'hmtx', 'cmap', 'loca',
                                                              'glyf', 'kern', 'name', 'post')]
    off = 12 + 16 * n
    body, pos = b'', {}
    for t in order:
        pos[t] = off + len(body)
        body += tables[t] + b'\0' * (-len(tables[t]) % 4)
    for t in tags:
        head += struct.pack('>4sIII', t.encode('latin1'), _checksum(tables[t]), pos[t], len(tables[t]))
    font = bytearray(head + body)
    adj = (0xB1B0AFBA - _checksum(bytes(font))) & 0xFFFFFFFF
    struct.pack_into('>I', font, pos['head'] + 8, adj)
    return bytes(font)


# ---------------------------------------------------------------- пересадка контуров в шрифт игры

ALIAS = {   # чего нет в исходном шрифте → похожие символы (по порядку)
    0x0009: [0x0020], 0x00A0: [0x0020], 0x2007: [0x0020], 0x202F: [0x0020],
    0x00AD: [0x002D, 0x2010], 0x2010: [0x002D], 0x2011: [0x2010, 0x002D], 0x2012: [0x2013],
    0x0401: [0x00CB], 0x0451: [0x00EB], 0x2126: [0x03A9], 0x2206: [0x0394], 0x00B5: [0x03BC],
    0x2215: [0x2044, 0x002F], 0x2044: [0x2215, 0x002F], 0x2219: [0x00B7, 0x2022], 0x00B7: [0x2219],
    0x2212: [0x2013], 0x2113: [0x006C], 0x2116: [], 0x2120: [], 0x212E: [0x0065],
}
LIGATURES = {0xFB01: 'fi', 0xFB02: 'fl'}
WIDTH_SAMPLE = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
MARKS = (0x00AE, 0x2122, 0x2120)   # ®, ™, ℠: у EA маленькие надстрочные («Wild®») — вписываются в рамку оригинала


def _bbox(contours):
    pts = [(x, y) for c in contours for x, y, _ in c]
    if not pts:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def transplant(target, source, fit='cap', scale=1.0, width='1', track=0.0, kern=True, vmetrics='game',
               marks=True, caps=False, max_size=None, log=print):
    """Контуры source в «скелет» target (имена, классы, вертикальные метрики, набор символов).
    max_size — предел размера файла (по умолчанию в build — размер оригинала): лишнее — за счёт кернинга."""
    charset = sorted(target.cmap)
    if fit == 'cap':
        s = target.cap_height() / source.cap_height()
    elif fit == 'x':
        s = target.x_height() / source.x_height()
    else:
        s = target.upem / source.upem
    s *= scale
    both = [c for c in map(ord, WIDTH_SAMPLE) if c in target.cmap and c in source.cmap]
    t_mean = sum(target.adv[target.cmap[c]] for c in both) / max(1, len(both))
    s_mean = sum(source.outline(source.cmap[c])[1] for c in both) / max(1, len(both)) * s
    natural = s_mean / t_mean if t_mean else 1.0
    kx = (t_mean / s_mean if s_mean else 1.0) if width == 'auto' else float(width)
    kx = min(max(kx, 0.5), 1.6)

    picks, fallback, notes = {}, [], []
    for c in charset:
        if c in source.cmap:
            picks[c] = ('mark', source.cmap[c], c) if marks and c in MARKS else ('s', source.cmap[c])
            continue
        alt = next((a for a in ALIAS.get(c, []) if a in source.cmap), None)
        if alt is not None:
            picks[c] = ('s', source.cmap[alt])
            notes.append(f'U+{c:04X} ← U+{alt:04X}')
            continue
        if c in LIGATURES and all(ord(ch) in source.cmap for ch in LIGATURES[c]):
            picks[c] = ('lig', LIGATURES[c])
            notes.append(f'U+{c:04X} ← {LIGATURES[c]}')
            continue
        picks[c] = ('t', target.cmap[c])
        fallback.append(c)
    if caps:                                              # строчные → глифы прописных (шрифт «только прописные»)
        for c in charset:
            up = chr(c).upper()
            if up != chr(c) and len(up) == 1 and ord(up) in picks:
                picks[c] = picks[ord(up)]
        fallback = [c for c in fallback if picks[c][0] == 't']

    tnames = target.glyph_names() or []
    out = [('s', 0)]                                      # 0 — .notdef исходного шрифта
    index = {('s', 0): 0}
    cmap = {}
    for c in charset:
        k = picks[c]
        if k not in index:
            index[k] = len(out)
            out.append(k)
        cmap[c] = index[k]

    glyphs, names = [], []
    for k in out:
        if k[0] in ('s', 'mark'):
            cs, aw = source.outline(k[1])
            cs = [[(x * s * kx, y * s, on) for x, y, on in ct] for ct in cs]
            aw = aw * s * kx
            if k[0] == 'mark':
                tcs, taw = target.outline(target.cmap[k[2]])
                tb, sb = _bbox(tcs), _bbox(cs)
                if tb and sb and sb[3] > sb[1] and (tb[3] - tb[1]) < 0.75 * (sb[3] - sb[1]):
                    kk = (tb[3] - tb[1]) / (sb[3] - sb[1])
                    cs = [[((x - sb[0]) * kk + tb[0], (y - sb[1]) * kk + tb[1], on) for x, y, on in ct] for ct in cs]
                    aw = taw
                    notes.append(f'U+{k[2]:04X} {chr(k[2])} — уменьшен до размера оригинала (×{kk:.2f})')
            elif aw > 0 and track:
                cs = [[(x + track / 2, y, on) for x, y, on in ct] for ct in cs]
                aw += track
        elif k[0] == 'lig':
            cs, aw = [], 0.0
            for ch in k[1]:
                sub, sa = source.outline(source.cmap[ord(ch)])
                cs += [[((x + aw) * s * kx, y * s, on) for x, y, on in ct] for ct in sub]
                aw += sa
            aw = aw * s * kx + track
        else:
            cs, aw = target.outline(k[1])
        glyphs.append((cs, max(0, int(round(aw)))))
    seen = set()
    rev = {}
    for c in charset:
        rev.setdefault(cmap[c], c)
    for i in range(len(out)):
        if i == 0:
            nm = '.notdef'
        else:
            c = rev[i]
            tg = target.cmap.get(c)
            nm = tnames[tg] if tg is not None and tg < len(tnames) else f'uni{c:04X}'
        while nm in seen:
            nm += '.alt'
        seen.add(nm)
        names.append(nm)

    pairs, cut = {}, 0
    if kern:
        src_ids = {k[1]: i for k, i in index.items() if k[0] == 's'}
        for (l, r), v in source.kerning(src_ids).items():
            v = int(round(v * s * kx))
            if v:
                pairs[(src_ids[l], src_ids[r])] = v
        if len(pairs) > 10920:                            # предел одной подтаблицы kern формата 0
            cut = len(pairs) - 10920
            pairs = dict(sorted(pairs.items(), key=lambda kv: -abs(kv[1]))[:10920])

    # таблицы
    glyf, loca = bytearray(), []
    hm = bytearray()
    bb = [32767, 32767, -32768, -32768]
    maxpts = maxct = 0
    adv_max, min_l, min_r, max_ext = 0, 32767, 32767, -32768
    total_adv = cnt_adv = 0
    for cs, aw in glyphs:
        data, box, npts, nct = encode_glyph(cs)
        loca.append(len(glyf))
        glyf += data
        lsb = box[0] if box else 0
        hm += struct.pack('>Hh', aw, lsb)
        adv_max = max(adv_max, aw)
        if aw:
            total_adv += aw
            cnt_adv += 1
        if box:
            bb = [min(bb[0], box[0]), min(bb[1], box[1]), max(bb[2], box[2]), max(bb[3], box[3])]
            min_l = min(min_l, box[0])
            min_r = min(min_r, aw - box[2])
            max_ext = max(max_ext, box[2])
            maxpts, maxct = max(maxpts, npts), max(maxct, nct)
    loca.append(len(glyf))
    if bb[0] > bb[2]:
        bb = [0, 0, 0, 0]
    short = len(glyf) < 0x20000
    loca_b = struct.pack('>%dH' % len(loca), *[v // 2 for v in loca]) if short else struct.pack('>%dI' % len(loca), *loca)
    ng = len(glyphs)

    head = bytearray(target.t['head'])
    struct.pack_into('>I', head, 8, 0)
    struct.pack_into('>H', head, 16, u16(head, 16) & ~0x14)   # инструкций нет: снять биты 2 и 4
    struct.pack_into('>q', head, 28, int(time.time()) + 2082844800)
    struct.pack_into('>4h', head, 36, *bb)
    struct.pack_into('>h', head, 50, 0 if short else 1)

    vm = None
    if vmetrics == 'source':
        so2 = source.os2
        win = so2.get('win') or (max(source.ascender, source.bbox[3]), max(-source.descender, -source.bbox[1]))
        typo = so2.get('typo') or (source.ascender, source.descender, source.line_gap)
        vm = {'hhea': [int(round(v * s)) for v in (source.ascender, source.descender, source.line_gap)],
              'typo': [int(round(v * s)) for v in typo], 'win': [int(round(v * s)) for v in win]}
    hhea = bytearray(target.t['hhea'])
    if vm:
        struct.pack_into('>3h', hhea, 4, *vm['hhea'])
    struct.pack_into('>Hhhh', hhea, 10, adv_max, min_l if min_l < 32767 else 0, min_r if min_r < 32767 else 0,
                     max_ext if max_ext > -32768 else 0)
    struct.pack_into('>H', hhea, 34, ng)
    maxp = struct.pack('>IHHHHHHHHHHHHHH', 0x00010000, ng, maxpts, maxct, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0)

    os2 = bytearray(target.t['OS/2'])
    struct.pack_into('>h', os2, 2, int(round(total_adv / max(1, cnt_adv))))
    codes = [c for c in cmap if c <= 0xFFFF]
    struct.pack_into('>HH', os2, 64, min(codes), max(codes))
    if vm:
        struct.pack_into('>3h', os2, 68, *vm['typo'])
        struct.pack_into('>2H', os2, 74, *vm['win'])
    new_cap = new_x = None
    for ch, attr in (('H', 'cap'), ('x', 'x')):
        g = cmap.get(ord(ch))
        if g is not None:
            ys = [y for ct in glyphs[g][0] for _, y, on in ct if on]
            if ys:
                if attr == 'cap':
                    new_cap = int(round(max(ys)))
                else:
                    new_x = int(round(max(ys)))
    if u16(os2, 0) >= 2 and len(os2) >= 90:
        struct.pack_into('>2h', os2, 86, new_x or s16(os2, 86), new_cap or s16(os2, 88))

    tables = {'head': bytes(head), 'hhea': bytes(hhea), 'maxp': maxp, 'OS/2': bytes(os2), 'hmtx': bytes(hm),
              'cmap': build_cmap(cmap), 'loca': loca_b, 'glyf': bytes(glyf), 'name': target.t['name'],
              'post': build_post(names, target.t['post'])}
    if pairs:
        tables['kern'] = build_kern(pairs)
    font = pack_sfnt(tables)
    dropped = 0
    if max_size and len(font) > max_size and pairs:     # не больше оригинала: убрать самые слабые пары кернинга
        keep = max(0, len(pairs) - math.ceil((len(font) - max_size) / 6))
        strong = sorted(pairs.items(), key=lambda kv: -abs(kv[1]))[:keep]
        dropped = len(pairs) - len(strong)
        pairs = dict(strong)
        if pairs:
            tables['kern'] = build_kern(pairs)
        else:
            tables.pop('kern', None)
        font = pack_sfnt(tables)
    if max_size and len(font) > max_size:
        log(f'  внимание: файл больше оригинала ({len(font)} > {max_size} байт) — буфер шрифтов игры может быть '
            f'рассчитан на оригинал')
    win = vm['win'] if vm else list(target.os2['win'])
    report = {
        'scale': round(s, 5), 'width_factor': round(kx, 4), 'natural_width': round(natural, 4),
        'track': track, 'glyphs': ng, 'chars': len(charset), 'kern_pairs': len(pairs),
        'cap_height': new_cap, 'x_height': new_x, 'target_cap_height': int(round(target.cap_height())),
        'target_x_height': int(round(target.x_height())), 'win': win, 'upem': target.upem,
        'from_original': [f'U+{c:04X} {chr(c)}' for c in fallback], 'substituted': notes,
        'size': len(font)}
    log(f'  масштаб {s:.4f} (по {"высоте прописных" if fit == "cap" else "высоте строчных" if fit == "x" else "кеглю"}), '
        f'ширина ×{kx:.3f} (своя ширина шрифта к оригиналу: {natural:.3f}), кернинг: {len(pairs)} пар'
        + (f' (ещё {cut} слабых — сверх предела таблицы kern)' if cut else '')
        + (f' (ещё {dropped} слабых убрано, чтобы файл не был больше оригинала)' if dropped else '')
        + f', глифов {ng}, символов {len(charset)}')
    if fallback:
        log(f'  из оригинала ({len(fallback)}): ' + ' '.join(chr(c) if c > 0x20 and c != 0x7F else f'U+{c:04X}'
                                                         for c in fallback))
    if natural > 1.08 and kx == 1.0:
        log(f'  внимание: шрифт шире оригинала на {100 * (natural - 1):.0f}% — длинные надписи могут не влезть '
            f'(--width auto или --width 0.9)')
    over = [chr(c) for c in charset if picks[c][0] != 't' and (lambda b: b and (b[3] > win[0] + 0.5 or b[1] < -win[1] - 0.5))(
        _bbox(glyphs[cmap[c]][0]))]
    if over:
        report['beyond_win'] = ''.join(over)
        log(f'  выходят за usWinAscent/Descent ({win[0]}/{win[1]}): {"".join(over)} — в игре края могут обрезаться')
    return font, report


# ---------------------------------------------------------------- font_extents.txt

def extents_rows(font):
    wa, wd = font.os2['win']
    return [(sz, math.ceil(min(sz, EXTENTS_MAX_PX) * wa / font.upem - 1e-9),
             math.ceil(min(sz, EXTENTS_MAX_PX) * wd / font.upem - 1e-9)) for sz in EXTENTS_SIZES]


def parse_extents(text):
    return {name: [tuple(map(int, r.split())) for r in re.findall(r'\[([^\]]*)\]', body)]
            for name, body in re.findall(r'"([^"]+)"\s*((?:\[[^\]]*\]\s*)+)', text)}


def format_extents(blocks):
    out = ''
    for name, rows in blocks:
        out += '{\r\n\t"' + name + '"\r\n' + ''.join(f'\t[ {a} {b} {c} ]\r\n' for a, b, c in rows) + '}\r\n'
    return out + '\r\n\r\n'


# ---------------------------------------------------------------- превью (Chrome/Edge без окна)

def render_page(html, out_png, w, h, transparent=False):
    import teamart
    tmp = tempfile.mkdtemp(prefix='fefont_')
    try:
        page = os.path.join(tmp, 'page.html')
        open(page, 'w', encoding='utf-8').write(html)
        out_abs = os.path.abspath(out_png)
        os.makedirs(os.path.dirname(out_abs), exist_ok=True)
        if os.path.exists(out_abs):
            os.remove(out_abs)
        cmd = [teamart.browser(), '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run',
               '--no-default-browser-check', '--force-device-scale-factor=1', '--allow-file-access-from-files',
               f'--user-data-dir={os.path.join(tmp, "profile")}', f'--window-size={w},{h}',
               '--virtual-time-budget=3000', f'--screenshot={out_abs}', 'file:///' + page.replace('\\', '/')]
        if transparent:
            cmd.insert(-2, '--default-background-color=00000000')
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180, check=False)
        if not os.path.exists(out_abs):
            raise SystemExit(f'браузер не сохранил {out_abs}')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def file_url(p):
    return 'file:///' + os.path.abspath(p).replace('\\', '/')


PREVIEW_LINES = [
    ('Starting Lineups', 36), ('Minnesota VS Chicago', 24), ('B. COLEMAN  J. ERIKSSON EK  M. BOLDY', 24),
    ('LW  C  RW  D  G', 24), ('Press START', 24), ('Wild®  Blackhawks®  Penguins®', 32),
    ('0123456789  20  14  91  88', 40), ('PLAY NOW  ·  HOCKEY ULTIMATE TEAM  ·  BE A PRO', 21),
    ('The quick brown fox jumps over the lazy dog — 2026/27', 20),
]


def preview(outdir, prevdir, shot=None, game=None, nhl12=None):
    rep_path = os.path.join(outdir, 'fefont-build.json')
    report = json.load(open(rep_path, encoding='utf-8')) if os.path.exists(rep_path) else {}
    faces = [k for k in FACES if os.path.exists(os.path.join(outdir, *FACES[k][0].split('/')))]
    if not faces:
        raise SystemExit(f'{outdir}: нет собранных шрифтов')
    os.makedirs(prevdir, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix='fefont_src_')
    try:
        css = ''
        for k in FACES:                                    # o_* — оригинал, n_* — сборка (или оригинал, если не менялся)
            if k == 'indicator' and k not in faces:
                continue
            orig = os.path.join(tmp, f'orig_{k}.ttf')
            open(orig, 'wb').write(game_file(*FACES[k][1], game))
            new = os.path.join(outdir, *FACES[k][0].split('/')) if k in faces else orig
            css += (f"@font-face{{font-family:'o_{k}';src:url('{file_url(orig)}')}}"
                    f"@font-face{{font-family:'n_{k}';src:url('{file_url(new)}')}}\n")
        base_css = ('body{margin:0;background:#0b1626;color:#e8edf3;font-family:sans-serif}'
                    '.lab{font:12px/1.2 Segoe UI,sans-serif;color:#8fa3bd;margin:10px 0 2px}'
                    '.ln{white-space:nowrap;line-height:1.15}.pair{display:flex;gap:28px;padding:10px 18px;'
                    'border-bottom:1px solid #22344d}.col{flex:1;overflow:hidden}.h{font:600 14px Segoe UI,sans-serif;'
                    'color:#ffd27a;margin-bottom:4px}.fb{color:#ff6b6b}')
        for k in faces:
            info = report.get(k, {})
            src = info.get('source', '?')
            body = (f'<div class="pair"><div class="col"><div class="h">ДО — {FACES[k][2]} (оригинал NHL 13)</div>'
                    f'</div><div class="col"><div class="h">ПОСЛЕ — {os.path.basename(src)} {info.get("style") or ""}'
                    f' → «{FACES[k][2]}»</div></div></div>')
            for text, px in PREVIEW_LINES:
                body += (f'<div class="pair"><div class="col"><div class="ln" style="font-family:o_{k};font-size:{px}px">'
                         f'{text}</div></div><div class="col"><div class="ln" style="font-family:n_{k};font-size:{px}px">'
                         f'{text}</div></div></div>')
            fb = set(x.split()[0] for x in info.get('from_original', []))
            chars = sorted(Font(game_file(*FACES[k][1], game)).cmap)
            grid = ''.join(f'<span class="{"fb" if f"U+{c:04X}" in fb else ""}">{chr(c) if c > 0x20 and c != 0x7F else "·"}'
                           f'</span>' for c in chars)
            body += (f'<div class="pair"><div class="col"><div class="lab">все символы оригинала</div><div style="font-family:o_{k};'
                     f'font-size:22px;word-break:break-all;letter-spacing:3px">{grid}</div></div><div class="col">'
                     f'<div class="lab">после (красным — взяты из оригинала)</div><div style="font-family:n_{k};font-size:22px;'
                     f'word-break:break-all;letter-spacing:3px">{grid}</div></div></div>')
            html = f'<!doctype html><html><head><meta charset="utf-8"><style>{css}{base_css}</style></head><body>{body}</body></html>'
            out = os.path.join(prevdir, f'{k}_before_after.png')
            render_page(html, out, 1400, 1040)
            print(f'  {out}')
        if shot:
            _preview_shot(shot, faces, css, base_css, prevdir)
        if nhl12:
            _preview_nhl12(nhl12, outdir, css, prevdir, game)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


SHOT_CROPS = [   # снимок экрана «Starting Lineups» 1651×982 (игра в окне 1600×900): x, y, w, h, текст, кегль, шрифт
    (660, 175, 345, 50, 'Starting Lineups', 36, 'conbold'), (690, 224, 290, 34, 'Minnesota VS Chicago', 24, 'conbold'),
    (335, 432, 150, 30, 'B. COLEMAN', 24, 'conbold'), (765, 850, 150, 36, 'Press START', 24, 'conbold'),
    (540, 770, 100, 40, 'Wild®', 32, 'conbold'), (985, 770, 200, 40, 'Blackhawks®', 32, 'conbold'),
    (375, 388, 75, 50, '20', 44, 'hv'),
]


def _preview_shot(shot, faces, css, base_css, prevdir):
    """Кусочки кадра из игры рядом с тем же текстом: оригинальный шрифт (Chrome) и новый."""
    img = file_url(shot)
    rows = ('<div class="pair"><div class="col h">кадр из игры</div><div class="col h">оригинальный шрифт '
            '(Chrome)</div><div class="col h">новый шрифт</div></div>')
    for x, y, w, h, text, px, k in SHOT_CROPS:
        rows += (f'<div class="pair" style="align-items:center"><div class="col"><div style="width:{w * 2}px;'
                 f'height:{h * 2}px;background:url({img}) -{x * 2}px -{y * 2}px / {1651 * 2}px {982 * 2}px"></div></div>'
                 f'<div class="col ln" style="font-family:o_{k};font-size:{px * 2}px;color:#f2f2f2">{text}</div>'
                 f'<div class="col ln" style="font-family:n_{k};font-size:{px * 2}px;color:#f2f2f2">{text}</div></div>')
    html = (f'<!doctype html><html><head><meta charset="utf-8"><style>{css}{base_css}body{{background:#000}}'
            f'</style></head><body>{rows}</body></html>')
    out = os.path.join(prevdir, 'shot_compare.png')
    render_page(html, out, 2200, 1000)
    print(f'  {out}')


NHL12_MENU = [   # снимок главного меню NHL 12 1000×563: текст, верх прописных (y), высота прописных, px
    ('ИГРАТЬ', 240, 10.5), ('HOCKEY ULTIMATE TEAM', 262, 15.6), ('WINTER CLASSIC', 290, 10.5),
    ('EA SPORTS™ HOCKEY LEAGUE', 310, 10.5), ('РЕЖИМ «ПРОФИ»', 330, 10.5), ('«ЛЕГЕНДА»', 350, 10.5),
    ('РЕЖИМЫ ИГРЫ', 370, 10.5), ('XBOX LIVE', 390, 10.5), ('СВОЯ ИГРА NHL™ 12', 410, 10.5),
    ('ВЫПОЛНИТЕ ВХОД', 430, 10.5)]


def _preview_nhl12(shot, outdir, css, prevdir, game=None):
    """Меню NHL 12 (кусок снимка) рядом с теми же пунктами шрифтом пунктов меню NHL 13 («Hv»): до и после."""
    K = 3
    img = file_url(shot)
    orig = Font(game_file(*FACES['hv'][1], game))
    newp = os.path.join(outdir, *FACES['hv'][0].split('/'))
    new = Font(open(newp, 'rb').read()) if os.path.exists(newp) else orig
    x0, y0, w, h = 140, 230, 390, 220

    def panel(fam, font):
        cap_u = font.cap_height() / font.upem
        out = (f'<svg width="{w * K}" height="{h * K}" viewBox="0 0 {w * K} {h * K}" style="background:#101216">'
               f'<rect x="{(145 - x0) * K}" y="{(255 - y0) * K}" width="{370 * K}" height="{28 * K}" fill="#c9cdd2"/>')
        for text, top, cap in NHL12_MENU:
            fs = cap * K / cap_u
            col = '#1b1d20' if cap > 12 else '#c6c8cb'
            out += (f'<text x="{(153 - x0) * K}" y="{(top + cap - y0) * K:.1f}" fill="{col}" '
                    f'style="font-family:{fam};font-size:{fs:.2f}px">{text}</text>')
        return out + '</svg>'

    crop = (f'<div style="width:{w * K}px;height:{h * K}px;background:url({img}) -{x0 * K}px -{y0 * K}px / '
            f'{1000 * K}px {563 * K}px"></div>')
    head = ('<div class="pair"><div class="col h">NHL 12 (снимок)</div><div class="col h">NHL 13 сейчас: «EA HelveticaNeue '
            'Hv» (85 Heavy)</div><div class="col h">новый «Hv»</div></div>')
    body = (head + f'<div class="pair"><div class="col">{crop}</div><div class="col">{panel("o_hv", orig)}</div>'
            f'<div class="col">{panel("n_hv", new)}</div></div>'
            '<div class="lab" style="padding:6px 18px">Высота прописных — как на снимке NHL 12; в NHL 13 кегль пунктов задаёт '
            'разметка меню (буквы те же, размер может отличаться). Прописными пункты делает код меню (toUpperCase), '
            'не шрифт.</div>')
    html = (f'<!doctype html><html><head><meta charset="utf-8"><style>{css}'
            'body{margin:0;background:#0b1626;color:#e8edf3}.pair{display:flex;gap:16px;padding:8px 18px}'
            '.col{flex:none}.h{font:600 16px Segoe UI,sans-serif;color:#ffd27a;width:' + str(w * K) + 'px}'
            '.lab{font:13px Segoe UI,sans-serif;color:#8fa3bd}</style></head><body>' + body + '</body></html>')
    out = os.path.join(prevdir, 'nhl12_menu_compare.png')
    render_page(html, out, 3 * w * K + 2 * 16 + 36, h * K + 110)
    print(f'  {out}')


# ---------------------------------------------------------------- команды

def load_source(spec):
    """SRC[#N][@СТИЛЬ] → Font."""
    style = None
    if '@' in spec:
        spec, style = spec.split('@', 1)
    index = 0
    m = re.match(r'^(.*)#(\d+)$', spec)
    if m:
        spec, index = m.group(1), int(m.group(2))
    if not os.path.exists(spec):
        raise SystemExit(f'нет файла {spec}')
    f = Font(open(spec, 'rb').read(), index, spec)
    f.set_style(style)
    return f, spec, style


def cmd_info(paths):
    items = [(k, game_font(k)) for k in list(FACES) + list(EXTRA)] if not paths else \
        [(p, load_source(p)[0]) for p in paths]
    for key, f in items:
        role = ''
        if key in FACES or key in EXTRA:
            rel, (arch, member), apt, role = {**FACES, **EXTRA}[key]
            print(f'== {key}: cache:\\{rel.replace("/", chr(92))}  ({arch}.big)  — {role}')
        else:
            print(f'== {key}')
        o = f.os2
        print(f'   имя: {f.name(1)!r} / {f.name(2)!r}, полное {f.name(4)!r}, типогр. {f.name(16)!r}')
        print(f'   {"CFF" if f.cff else "TrueType"}, {f.ng} глифов, {len(f.cmap)} символов, unitsPerEm {f.upem}, '
              f'вес {o.get("weight")}, ширина {o.get("width")}' + (f', оси: ' + ', '.join(
                  f'{a[0]} {a[1]:g}…{a[3]:g} ({a[2]:g})' for a in f.axes) if f.axes else ''))
        print(f'   вертикаль: hhea {f.ascender}/{f.descender}/{f.line_gap}, typo {o.get("typo")}, win {o.get("win")}; '
              f'прописные {f.cap_height():.0f}, строчные {f.x_height():.0f}')
        hint = 'fpgm' in f.t or 'prep' in f.t
        kp = f.kerning(range(f.ng)) if f.ng < 3000 else {}
        print(f'   хинтинг: {"есть" if hint else "нет"}, кернинг: {len(kp)} пар'
              f' ({"GPOS" if "GPOS" in f.t else "kern" if "kern" in f.t else "нет"})')
        rs, cs = [], sorted(f.cmap)
        for c in cs:
            if rs and c == rs[-1][1] + 1:
                rs[-1][1] = c
            else:
                rs.append([c, c])
        print('   символы: ' + ' '.join(f'{a:04X}-{b:04X}' if a != b else f'{a:04X}' for a, b in rs))


def cmd_styles(path):
    f = load_source(path)[0]
    if not f.axes:
        print(f'{path}: шрифт не вариативный')
        return
    for tag, mn, df, mx, _ in f.axes:
        print(f'ось {tag}: {mn:g} … {mx:g}, по умолчанию {df:g}')
    for sub, c in f.instances:
        print(f'  «{sub}»: ' + ', '.join(f'{k}={v:g}' for k, v in c.items()))


def cmd_extents(args):
    check = '--check' in args
    out = args[args.index('--out') + 1] if '--out' in args else None
    blocks = [(FACES[k][2], extents_rows(game_font(k))) for k in EXTENTS_ORDER]
    text = format_extents(blocks)
    if out:
        open(out, 'wb').write(text.encode('ascii'))
        print(f'записано {out}')
    if check or not out:
        game = parse_extents(game_file('cache', EXTENTS_FILE).decode('latin1'))
        ind = extents_rows(game_font('indicator'))
        for name, rows in blocks:
            g = game.get(name, [])
            bad = sum(1 for a, b in zip(rows, g) if a != b) + abs(len(rows) - len(g))
            print(f'{name}: строк {len(g)}, расхождений с формулой по файлу шрифта: {bad}')
            if bad and name == FACES['indicator'][2]:
                bad2 = sum(1 for a, b in zip(ind, g) if a != b)
                print(f'   по метрикам indicatorfont.ttf (77 Bold Condensed): расхождений {bad2}')


def cmd_build(args):
    if not args or args[0].startswith('--'):
        raise SystemExit('нужен OUTDIR')
    outdir, args = args[0], args[1:]
    opts = {'fit': 'cap', 'scale': '1', 'width': '1', 'track': '0', 'vmetrics': 'game', 'preview': None}
    faces, kern, marks, caps = [], True, True, False
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--face':
            key, spec = args[i + 1].split('=', 1)
            if key not in FACES:
                raise SystemExit(f'неизвестный KEY {key}; есть: {", ".join(FACES)}')
            faces.append((key, spec))
            i += 2
        elif a == '--no-kern':
            kern = False
            i += 1
        elif a == '--keep-marks':
            marks = False
            i += 1
        elif a == '--caps':
            caps = True
            i += 1
        elif a[2:] in opts:
            opts[a[2:]] = args[i + 1]
            i += 2
        else:
            raise SystemExit(f'непонятный параметр {a}')
    if not faces:
        raise SystemExit('нужен хотя бы один --face KEY=SRC')
    report = {}
    new_win = {}
    for key, spec in faces:
        src, path, style = load_source(spec)
        orig = game_file(*FACES[key][1])
        target = Font(orig, path=f'{FACES[key][1][0]}.big:{FACES[key][1][1]}')
        print(f'{key} ← {path}' + (f' @{style}' if style else '') + f'  ({FACES[key][2]})')
        font, rep = transplant(target, src, fit=opts['fit'], scale=float(opts['scale']), width=opts['width'],
                               track=float(opts['track']), kern=kern, vmetrics=opts['vmetrics'], marks=marks,
                               caps=caps, max_size=len(orig))
        check = Font(font, path='сборка')                # самопроверка: файл читается, набор символов тот же
        assert set(check.cmap) == set(target.cmap), 'набор символов не совпал'
        dst = os.path.join(outdir, *FACES[key][0].split('/'))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, 'wb').write(font)
        rep.update({'source': os.path.abspath(path), 'style': style, 'file': FACES[key][0], 'apt_name': FACES[key][2]})
        report[key] = rep
        new_win[key] = check
        print(f'  → {dst} ({len(font)} байт)')
    if opts['vmetrics'] == 'source':
        blocks = []
        game_rows = parse_extents(game_file('cache', EXTENTS_FILE).decode('latin1'))
        for k in EXTENTS_ORDER:
            blocks.append((FACES[k][2], extents_rows(new_win[k]) if k in new_win else game_rows[FACES[k][2]]))
        dst = os.path.join(outdir, *EXTENTS_FILE.split('/'))
        text = format_extents(blocks).encode('ascii')
        if text == game_file('cache', EXTENTS_FILE):
            print('  font_extents.txt совпадает с игровым — не нужен')
            if os.path.exists(dst):
                os.remove(dst)
        else:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            open(dst, 'wb').write(text)
            print(f'  → {dst} (высоты строк по новым метрикам)')
    rp = os.path.join(outdir, 'fefont-build.json')
    old = json.load(open(rp, encoding='utf-8')) if os.path.exists(rp) else {}
    old.update(report)
    json.dump(old, open(rp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    if opts['preview']:
        preview(outdir, opts['preview'])


def main():
    a = sys.argv[1:]
    if not a or a[0] in ('-h', '--help'):
        print(__doc__)
        return
    cmd, rest = a[0], a[1:]
    if cmd == 'info':
        cmd_info(rest)
    elif cmd == 'styles':
        cmd_styles(rest[0])
    elif cmd == 'extents':
        cmd_extents(rest)
    elif cmd == 'build':
        cmd_build(rest)
    elif cmd == 'preview':
        shot = rest[rest.index('--shot') + 1] if '--shot' in rest else None
        nhl12 = rest[rest.index('--nhl12') + 1] if '--nhl12' in rest else None
        preview(rest[0], rest[1], shot, nhl12=nhl12)
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main()
