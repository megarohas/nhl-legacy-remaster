"""Сопоставление кода двух образов Xbox 360 одной серии (NHL 13 → NHL Legacy, NHL 12, NHL 14):
какие функции и места наших врезок находятся в другом образе автоматически.

    python xmatch.py A.bin B.bin --stats                         # сколько функций сошлось и как
    python xmatch.py A.bin B.bin --addr 82809330 828A8338        # где эти адреса A в образе B
    python xmatch.py A.bin B.bin --port DIR [--json OUT.json] [--md OUT.md]
                                                                 # все адреса порта NHL 13 из DIR

A и B — образы памяти из tools/xex.py (база 0x82000000). Границы функций — из .pdata образа.

Метод (без запуска игры):
1. Каждая функция переводится в поток «маскированных» слов: адресные части (lis с 0x82xx…0x84xx
   и младшие 16 бит инструкций, которые берут базу из такого регистра), смещения переходов `b`/`bl`
   за пределы функции и элементы таблиц переходов заменяются метками. Константы, смещения в
   структурах и регистры остаются — по ним и узнаётся функция.
2. Точное совпадение: одинаковый поток, единственный в обоих образах.
3. Распространение по графу вызовов: у пары с одинаковым потоком вызовы стоят на тех же местах —
   вызываемые функции тоже пара; у пары с отличиями вызовы сопоставляются выравниванием потоков
   (difflib), так же — пары по ссылкам на одни и те же строки (.rdata).
4. Для нужной функции без пары — кандидаты из контекста (вызывающие и вызываемые пары, строки),
   лучший по сходству потоков (ratio ≥ 0.5 и с запасом над вторым).
5. Место врезки переносится выравниванием: в совпавшем блоке — тот же номер инструкции; слово
   сверяется — тот же вид и то же число (регистры могут отличаться).

Категории места: exact (функция совпала целиком, слово то же), same (функция изменилась, слово
то же), same-imm (та же инструкция и то же число, регистры другие), moved (кусок вокруг изменён,
но такая инструкция в нём одна), aligned-diff / moved-diff (место нашлось, но число другое — смотреть
руками), lost (функция без пары или место в изменённом куске).
"""
import argparse, bisect, difflib, json, os, re, struct, sys
from collections import Counter, defaultdict

BASE = 0x82000000
MASK = 1 << 32           # метка «маскированное слово»
JT = 2 << 32             # метка «элемент таблицы переходов» (смещение от начала функции)
LIS_LO, LIS_HI = 0x8200, 0x8500
DFORM = set(range(32, 56)) | {14, 58, 62}   # addi, загрузки/записи (rA — база)
LOGIC31 = {24, 26, 28, 58, 60, 124, 284, 316, 412, 444, 476, 536, 792, 824, 922, 954}  # op 31 с результатом в rA


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def soft_token(t):
    """Маскированное слово без номеров регистров (непосредственные значения и смещения остаются)."""
    if t >= MASK:
        if t & MASK:
            op = (t >> 26) & 0x3F
            return t if op in (16, 18) else (t & 0xFC000000) | MASK
        return t                                              # элемент таблицы переходов
    op = t >> 26
    if op in (7, 8, 12, 13, 14, 15):                         # mulli subfic addic addi addis
        return (op << 26) | ((1 << 20) if (t >> 16) & 31 == 0 else 0) | (t & 0xFFFF)
    if op in (10, 11):                                        # cmpli / cmpi
        return (op << 26) | (t & 0x00200000) | (t & 0xFFFF)
    if op in (24, 25, 26, 27, 28, 29):                        # логические с imm
        return (op << 26) | (t & 0xFFFF)
    if 32 <= op <= 55 or op in (58, 62):                      # загрузки/записи: смещение, база r1 или нет
        return (op << 26) | ((1 << 21) if (t >> 16) & 31 == 1 else 0) | (t & 0xFFFF)
    if op in (16, 19):                                        # bc / bclr / bcctr: без номера cr
        return t & ~(0x7 << 18)
    if op in (20, 21):                                        # rlwimi / rlwinm: sh mb me
        return t & ~(0x3FF << 16)
    if op in (23, 30):
        return t & ~(0x7FFF << 11)
    if op == 31:
        xo = (t >> 1) & 0x3FF
        if xo in (339, 467, 371):                             # mfspr/mtspr/mftb: spr важен
            return t & ~(0x1F << 21)
        return t & ~(0x7FFF << 11)
    if op in (4, 5, 6, 59, 63):
        return t & ~(0x7FFF << 11)
    return t


class Image:
    def __init__(self, path):
        self.path = path
        self.img = open(path, 'rb').read()
        img = self.img
        e = struct.unpack('<I', img[0x3C:0x40])[0]
        nsec, optsz = struct.unpack('<H', img[e + 6:e + 8])[0], struct.unpack('<H', img[e + 20:e + 22])[0]
        opt = e + 24
        self.base = struct.unpack('<I', img[opt + 28:opt + 32])[0]
        if self.base != BASE:
            raise ValueError(f'{path}: база {self.base:08X}, ожидалась {BASE:08X}')
        prva, psz = struct.unpack('<II', img[opt + 96 + 8 * 3:opt + 104 + 8 * 3])
        self.sections = {}
        for i in range(nsec):
            s = img[opt + optsz + 40 * i:opt + optsz + 40 * i + 40]
            name = s[:8].rstrip(b'\0').decode('latin1')
            vsz, va = struct.unpack('<II', s[8:16])
            self.sections[name] = (BASE + va, BASE + va + vsz)
        funcs = {}
        for i in range(psz // 8):
            start, info = struct.unpack('>II', img[prva + 8 * i:prva + 8 * i + 8])
            n = (info >> 8) & 0x3FFFFF
            if start and n:
                funcs[start] = max(funcs.get(start, 0), start + 4 * n)
        self.pdata_count = len(funcs)
        self._gap_functions(funcs)
        self.starts = sorted(funcs)
        self.ends = [funcs[s] for s in self.starts]
        self._tok = {}
        self._soft = {}
        self._calls = {}
        self._refs = {}
        self.callers = None

    def _gap_functions(self, funcs):
        """Функции без записи в .pdata (мелкие листовые): режем промежутки .text по blr/bctr/b,
        если внутренние переходы не уходят дальше."""
        t0, t1 = self.sections['.text']
        starts = sorted(funcs)
        gaps, prev = [], t0
        for st in starts:
            if st > prev:
                gaps.append((prev, st))
            prev = max(prev, funcs[st])
        if prev < t1:
            gaps.append((prev, t1))
        img = self.img
        for g0, g1 in gaps:
            a = g0
            while a < g1:
                while a < g1 and self.word(a) == 0:
                    a += 4
                if a >= g1:
                    break
                start, reach, p = a, a, a
                while p < g1:
                    w = self.word(p)
                    op = w >> 26
                    if op == 16:
                        t = (p + s16(w & 0xFFFC)) & 0xFFFFFFFF
                        if start <= t < g1:
                            reach = max(reach, t)
                    elif op == 18 and not w & 3:
                        li = w & 0x03FFFFFC
                        if li & 0x02000000:
                            li -= 0x04000000
                        t = (p + li) & 0xFFFFFFFF
                        if start <= t < g1 and t > p:
                            reach = max(reach, t)
                        elif p >= reach:
                            break                       # хвостовой переход наружу
                    elif w in (0x4E800020, 0x4E800420) and p >= reach:
                        break
                    p += 4
                end = min(p + 4, g1)
                if end - start >= 8:
                    funcs[start] = end
                a = end

    def word(self, a):
        o = a - BASE
        return struct.unpack('>I', self.img[o:o + 4])[0]

    def func_at(self, a):
        i = bisect.bisect_right(self.starts, a) - 1
        if i >= 0 and self.starts[i] <= a < self.ends[i]:
            return self.starts[i]
        return None

    def end_of(self, f):
        return self.ends[bisect.bisect_left(self.starts, f)]

    def cstring(self, a, lo=4):
        """ASCII-строка по адресу в .rdata (≥ lo символов, с нулём в конце), иначе None."""
        r = self.sections.get('.rdata')
        if not r or not r[0] <= a < r[1]:
            return None
        o = a - BASE
        end = self.img.find(b'\0', o, o + 256)
        if end < 0 or end - o < lo:
            return None
        s = self.img[o:end]
        if all(32 <= c < 127 for c in s):
            return s.decode('ascii')
        return None

    def analyze(self, f):
        """Поток маскированных слов (по слову на инструкцию); заодно вызовы наружу [(номер, цель)]
        и ссылки на данные [(номер, адрес)]."""
        if f in self._tok:
            return self._tok[f]
        end = self.end_of(f)
        n = (end - f) // 4
        o = f - BASE
        words = struct.unpack(f'>{n}I', self.img[o:o + 4 * n])
        toks, calls, refs = [], [], []
        hi = {}            # регистр → старшая половина адреса (после lis)
        for i, w in enumerate(words):
            a = f + 4 * i
            op = w >> 26
            rd, ra = (w >> 21) & 31, (w >> 16) & 31
            if f <= w < end and w & 3 == 0 and i > 0:
                toks.append(JT | (w - f))                 # таблица переходов внутри функции
                continue
            if op == 18:                                  # b / bl
                li = w & 0x03FFFFFC
                if li & 0x02000000:
                    li -= 0x04000000
                t = (li if w & 2 else a + li) & 0xFFFFFFFF
                if f <= t < end:
                    toks.append(w)
                else:
                    toks.append((w & 0xFC000003) | MASK)
                    calls.append((i, t))
                if w & 1:
                    for r in (0, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12):
                        hi.pop(r, None)
                continue
            if op == 16:                                  # bc
                bd = s16(w & 0xFFFC)
                t = (bd if w & 2 else a + bd) & 0xFFFFFFFF
                toks.append(w if f <= t < end else (w & 0xFFFF0003) | MASK)
                continue
            if op == 15 and ra == 0 and LIS_LO <= (w & 0xFFFF) < LIS_HI:   # lis адрес
                toks.append((w & 0xFFFF0000) | MASK)
                hi[rd] = (w & 0xFFFF) << 16
                continue
            if op in DFORM and ra in hi:                  # addi/lwz/stw… от адреса
                toks.append((w & 0xFFFF0000) | MASK)
                lo = s16(w & 0xFFFC) if op in (58, 62) else s16(w & 0xFFFF)
                refs.append((i, (hi[ra] + lo) & 0xFFFFFFFF))
                if op in (33, 35, 37, 39, 41, 43, 45, 49, 51, 53, 55):   # с обновлением базы
                    hi.pop(ra, None)
                if op == 14 or 32 <= op <= 35 or 40 <= op <= 43 or op in (46, 58):
                    hi.pop(rd, None)                      # rD теперь полный адрес или данные
                continue
            if op == 24 and rd in hi:                     # ori rA, rS(адрес), lo
                toks.append((w & 0xFFFF0000) | MASK)
                refs.append((i, (hi[rd] | (w & 0xFFFF)) & 0xFFFFFFFF))
                hi.pop(ra, None)
                continue
            toks.append(w)
            # кто перезаписан (грубо: rA у логических и сдвигов, rD у остальных)
            if op in (20, 21, 23, 24, 25, 26, 27, 28, 29):
                hi.pop(ra, None)
            elif op == 31:
                xo = (w >> 1) & 0x3FF
                hi.pop(ra if xo in LOGIC31 else rd, None)
            elif op not in (10, 11, 16, 18, 19, 36, 37, 38, 39, 44, 45, 47, 52, 53, 54, 55, 62):
                hi.pop(rd, None)
        self._tok[f] = toks
        self._calls[f] = calls
        self._refs[f] = refs
        return toks

    def soft(self, f):
        """Тот же поток без номеров регистров (для сходства и выравнивания: у новой версии
        игры распределение регистров часто другое при той же логике)."""
        if f not in self._soft:
            self._soft[f] = [soft_token(t) for t in self.analyze(f)]
        return self._soft[f]

    def calls(self, f):
        self.analyze(f)
        return self._calls[f]

    def refs(self, f):
        self.analyze(f)
        return self._refs[f]

    def strings(self, f):
        return tuple(sorted({s for _, a in self.refs(f) for s in [self.cstring(a)] if s}))

    def build_callers(self):
        if self.callers is None:
            self.callers = defaultdict(list)
            for f in self.starts:
                for i, t in self.calls(f):
                    g = self.func_at(t)
                    if g is not None:
                        self.callers[g].append((f, i))
        return self.callers


def fhash(toks):
    return hash(tuple(toks))


class Matcher:
    def __init__(self, A, B, log=None):
        self.A, self.B = A, B
        self.ab, self.ba = {}, {}
        self.how = {}
        self.log = log or (lambda *a: None)

    def pair(self, fa, fb, how):
        if fa in self.ab or fb in self.ba:
            return False
        self.ab[fa], self.ba[fb] = fb, fa
        self.how[fa] = how
        return True

    def exact(self):
        A, B = self.A, self.B
        ha, hb = defaultdict(list), defaultdict(list)
        for f in A.starts:
            ha[fhash(A.analyze(f))].append(f)
        for f in B.starts:
            hb[fhash(B.analyze(f))].append(f)
        self.ha, self.hb = ha, hb
        n = 0
        for h, fs in ha.items():
            gs = hb.get(h)
            if gs and len(fs) == 1 and len(gs) == 1 and len(A.analyze(fs[0])) >= 4:
                n += self.pair(fs[0], gs[0], 'exact')
        self.log(f'точных уникальных пар: {n}')
        sa, sb = defaultdict(list), defaultdict(list)
        for f in A.starts:
            if f not in self.ab:
                sa[fhash(A.soft(f))].append(f)
        for f in B.starts:
            if f not in self.ba:
                sb[fhash(B.soft(f))].append(f)
        m = 0
        for h, fs in sa.items():
            gs = sb.get(h)
            if gs and len(fs) == 1 and len(gs) == 1 and len(A.soft(fs[0])) >= 8:
                m += self.pair(fs[0], gs[0], 'soft')
        self.log(f'совпадений без учёта регистров: {m}')

    def aligned_calls(self, fa, fb):
        """Пары вызываемых функций по выравниванию потоков fa и fb."""
        A, B = self.A, self.B
        ta, tb = A.analyze(fa), B.analyze(fb)
        ca, cb = dict(A.calls(fa)), dict(B.calls(fb))
        out = []
        if ta == tb:
            for i, t in ca.items():
                if i in cb:
                    out.append((t, cb[i]))
            return out
        if len(ta) * len(tb) > 4e7:
            return out
        for tag, i1, i2, j1, j2 in self.opcodes(fa, fb):
            if tag == 'equal' or (tag == 'replace' and i2 - i1 == j2 - j1):
                for k in range(i2 - i1):
                    if i1 + k in ca and j1 + k in cb:
                        out.append((ca[i1 + k], cb[j1 + k]))
        return out

    def opcodes(self, fa, fb):
        """Выравнивание потоков без регистров (кэшируется)."""
        key = (fa, fb)
        if not hasattr(self, '_ops'):
            self._ops = {}
        if key not in self._ops:
            sm = difflib.SequenceMatcher(None, self.A.soft(fa), self.B.soft(fb), autojunk=False)
            self._ops[key] = sm.get_opcodes()
        return self._ops[key]

    def propagate(self, rounds=20):
        A, B = self.A, self.B
        todo = list(self.ab.items())
        seen = set()
        total = 0
        while todo:
            nxt = []
            for fa, fb in todo:
                if (fa, fb) in seen:
                    continue
                seen.add((fa, fb))
                exact_body = A.analyze(fa) == B.analyze(fb)
                for ta, tb in self.aligned_calls(fa, fb):
                    ga, gb = A.func_at(ta), B.func_at(tb)
                    if ga is None or gb is None or ga != ta or gb != tb:
                        continue
                    if ga in self.ab or gb in self.ba:
                        continue
                    same = A.analyze(ga) == B.analyze(gb)
                    if not same and not exact_body:
                        r = self.ratio(ga, gb)
                        if r < 0.5:
                            continue
                    if self.pair(ga, gb, 'call' if same else 'call~'):
                        nxt.append((ga, gb))
                        total += 1
            todo = nxt
        self.log(f'распространение по вызовам: +{total}')
        return total

    def by_strings(self):
        A, B = self.A, self.B
        sa, sb = defaultdict(list), defaultdict(list)
        for f in A.starts:
            s = A.strings(f)
            if s:
                sa[s].append(f)
        for f in B.starts:
            s = B.strings(f)
            if s:
                sb[s].append(f)
        n = 0
        for s, fs in sa.items():
            gs = sb.get(s)
            if gs and len(fs) == 1 and len(gs) == 1:
                if self.ratio(fs[0], gs[0]) >= 0.3:
                    n += self.pair(fs[0], gs[0], 'strings')
        self.log(f'пары по строкам: {n}')
        return n

    def ratio(self, fa, fb):
        if self.A.analyze(fa) == self.B.analyze(fb):
            return 1.0
        ta, tb = self.A.soft(fa), self.B.soft(fb)
        if not ta or not tb:
            return 0.0
        if len(ta) * len(tb) > 4e7:
            # грубо: по мультимножеству слов
            ca, cb = Counter(ta), Counter(tb)
            return 2 * sum((ca & cb).values()) / (len(ta) + len(tb))
        sm = difflib.SequenceMatcher(None, ta, tb, autojunk=False)
        if sm.real_quick_ratio() < 0.3 or sm.quick_ratio() < 0.3:
            return sm.quick_ratio() * 0.5
        return sm.ratio()

    def candidates(self, fa):
        """Кандидаты в B для функции fa по контексту (вызывающие/вызываемые пары, строки)."""
        A, B = self.A, self.B
        A.build_callers(); B.build_callers()
        cands = Counter()
        for ca, i in A.callers.get(fa, []):
            cb = self.ab.get(ca)
            if cb is None:
                continue
            for ta, tb in self.aligned_calls(ca, cb):
                if ta == fa:
                    g = B.func_at(tb)
                    if g == tb:
                        cands[g] += 3
        for i, t in A.calls(fa):
            g = A.func_at(t)
            gb = self.ab.get(g) if g == t else None
            if gb is None:
                continue
            users = B.callers.get(gb, [])
            if len(users) > 30:
                continue                  # общие функции (выделение памяти и т. п.) ничего не говорят
            for cb in {c for c, j in users}:
                cands[cb] += 1
        # соседи по адресу: линковщик обычно сохраняет порядок функций внутри модуля
        k = bisect.bisect_left(A.starts, fa)
        for d in (-2, -1, 1, 2):
            if 0 <= k + d < len(A.starts):
                nb = self.ab.get(A.starts[k + d])
                if nb is not None:
                    j = bisect.bisect_left(B.starts, nb) - d
                    if 0 <= j < len(B.starts):
                        cands[B.starts[j]] += 2 if abs(d) == 1 else 1
        rare = self._rare_b()
        votes = Counter()
        for t in set(A.soft(fa)):
            fs = rare.get(t)
            if fs:
                for g in fs:
                    votes[g] += 1
        for g, v in votes.most_common(8):
            if v >= 2:
                cands[g] += 1 + min(v, 6) // 2
        s = A.strings(fa)
        if s:
            for f in self._string_index_b().get(s, []):
                cands[f] += 2
            for one in s:
                for f in self._string_any_b().get(one, [])[:50]:
                    cands[f] += 1
        return cands

    def _rare_b(self, limit=12):
        """Редкие слова (без регистров) образа B → функции, где они есть (не больше limit)."""
        if not hasattr(self, '_rare'):
            idx = {}
            for f in self.B.starts:
                for t in set(self.B.soft(f)):
                    st = idx.get(t)
                    if st is None:
                        idx[t] = {f}
                    elif len(st) <= limit:
                        st.add(f)
            self._rare = {t: fs for t, fs in idx.items() if len(fs) <= limit}
        return self._rare

    def _string_index_b(self):
        if not hasattr(self, '_sib'):
            self._sib = defaultdict(list)
            for f in self.B.starts:
                s = self.B.strings(f)
                if s:
                    self._sib[s].append(f)
        return self._sib

    def _string_any_b(self):
        if not hasattr(self, '_sab'):
            self._sab = defaultdict(list)
            for f in self.B.starts:
                for one in self.B.strings(f):
                    self._sab[one].append(f)
        return self._sab

    def resolve(self, fa, depth=2):
        """Пара для функции fa: уже известная или лучшая по контексту."""
        if fa in self.ab:
            return self.ab[fa]
        cands = self.candidates(fa)
        if not cands and depth > 0:
            # поднять контекст: сначала найти пары для вызывающих
            for ca, i in self.A.build_callers().get(fa, [])[:6]:
                self.resolve(ca, depth - 1)
            cands = self.candidates(fa)
        scored = []
        la = len(self.A.analyze(fa))
        for g, w in cands.most_common(16):
            if g in self.ba:
                continue
            lb = len(self.B.analyze(g))
            if not 0.4 <= lb / max(la, 1) <= 2.5:
                continue
            scored.append((self.ratio(fa, g), w, g))
        scored.sort(reverse=True)
        if not scored:
            return None
        best = scored[0]
        second = scored[1][0] if len(scored) > 1 else 0.0
        if len(scored) > 1 and best[0] == second and best[0] >= 0.9 and best[1] > scored[1][1]:
            second = 0.0      # одинаковые тела (дубликаты) — решает контекст
        if best[0] >= 0.5 and best[0] - second >= 0.05:
            how = 'context' if best[0] < 1.0 else 'context='
            self.pair(fa, best[2], how)
            self.how[fa] = f'{how} {best[0]:.2f}'
            self.propagate_one(fa, best[2])
            return best[2]
        return None

    def propagate_one(self, fa, fb):
        saved = list(self.ab.items())
        todo = [(fa, fb)]
        while todo:
            x, y = todo.pop()
            for ta, tb in self.aligned_calls(x, y):
                ga, gb = self.A.func_at(ta), self.B.func_at(tb)
                if ga != ta or gb != tb or ga in self.ab or gb in self.ba:
                    continue
                if self.A.analyze(ga) == self.B.analyze(gb) and self.pair(ga, gb, 'call'):
                    todo.append((ga, gb))

    def map_data(self, x, limit=8):
        """Адрес данных A → B по ссылкам из сопоставленных функций (lis/addi на тех же местах)."""
        A, B = self.A, self.B
        if not hasattr(self, '_refidx'):
            self._refidx = defaultdict(list)
            for f in A.starts:
                for i, t in A.refs(f):
                    self._refidx[t].append((f, i))
        votes = Counter()
        users = self._refidx.get(x, [])
        for f, i in users[:limit * 4]:
            fb = self.resolve(f, depth=1)
            if fb is None:
                continue
            j = self.map_index(f, fb, i)
            if j is None:
                continue
            rb = dict(B.refs(fb)).get(j)
            if rb is not None:
                votes[rb] += 1
            if sum(votes.values()) >= limit:
                break
        if not users:
            return None, 'data-noref', 'на адрес нет ссылок lis/addi в коде'
        if not votes:
            return None, 'data-lost', f'ссылок {len(users)}, ни одна не перенеслась'
        (b, n), *rest = votes.most_common()
        if rest and rest[0][1] * 2 > n:
            return b, 'data-?', f'голоса {dict(votes.most_common(3))}'
        return b, 'data', f'{n} ссылок из {len(users)}'

    def map_index(self, fa, fb, i):
        ta, tb = self.A.analyze(fa), self.B.analyze(fb)
        if ta == tb:
            return i
        for tag, i1, i2, j1, j2 in self.opcodes(fa, fb):
            if i1 <= i < i2:
                if tag == 'equal' or (tag == 'replace' and i2 - i1 == j2 - j1):
                    return j1 + (i - i1)
                return None
        return None

    def map_addr(self, a):
        """Адрес A → (адрес B или None, категория, пояснение)."""
        A, B = self.A, self.B
        fa = A.func_at(a)
        if fa is None:
            return None, 'nofunc', 'адрес вне функций .pdata'
        fb = self.resolve(fa)
        if fb is None:
            return None, 'lost', f'нет пары для функции {fa:08X}'
        i = (a - fa) // 4
        ta, tb = A.analyze(fa), B.analyze(fb)
        how = self.how.get(fa, '')
        if ta == tb:
            j = i
        else:
            j = None
            moved = None
            sa, sb = A.soft(fa), B.soft(fb)
            for tag, i1, i2, j1, j2 in self.opcodes(fa, fb):
                if i1 <= i < i2:
                    if tag == 'equal' or (tag == 'replace' and i2 - i1 == j2 - j1):
                        j = j1 + (i - i1)
                    else:
                        # кусок изменён: та же инструкция (вид и число, регистры любые) рядом —
                        # если она одна, берём её (категория moved — проверить глазами)
                        lo, hi = max(0, j1 - 2), min(len(sb), j2 + 2)
                        same = [k for k in range(lo, hi) if sb[k] == sa[i]]
                        if len(same) == 1:
                            moved = same[0]
                        else:
                            kind = [k for k in range(lo, hi) if (sb[k] >> 26) == (sa[i] >> 26)
                                    and (sb[k] & ~0xFFFF) == (sa[i] & ~0xFFFF)]
                            if len(kind) == 1 and len(same) == 0:
                                moved = kind[0]
                    break
            if j is None and moved is not None:
                b = fb + 4 * moved
                wa, wb = A.word(a), B.word(b)
                cat = 'moved' if soft_token(wa) == soft_token(wb) else 'moved-diff'
                return b, cat, f'{how}; в изменённом куске, найдено по виду инструкции ({wa:08X} → {wb:08X})'
            if j is None:
                return None, 'lost', f'функция {fa:08X}→{fb:08X} ({how}), место в изменённом куске'
        b = fb + 4 * j
        wa, wb = A.word(a), B.word(b)
        if a == fa:
            return b, 'func', how
        if wa == wb:
            return b, 'exact' if ta == tb else 'same', how
        if soft_token(wa) == soft_token(wb):
            return b, 'same-imm', how     # та же инструкция и то же число, другие регистры
        return b, 'aligned-diff', f'{how}; было {wa:08X}, стало {wb:08X}'


# ---------- адреса порта NHL 13 ----------

def port_addresses(port_dir):
    """Все адреса, на которые опирается порт: [(адрес, вид, источник)]."""
    out = []
    for name in sorted(os.listdir(port_dir)):
        p = os.path.join(port_dir, name)
        if name.endswith('.toml') and os.path.isfile(p):
            txt = open(p, encoding='utf-8').read()
            for m in re.finditer(r'^address\s*=\s*0x([0-9A-Fa-f]{8})', txt, re.M):
                out.append((int(m.group(1), 16), 'midasm', name))
            if 'functions' in name:
                for m in re.finditer(r'^0x([0-9A-Fa-f]{8})\s*=', txt, re.M):
                    out.append((int(m.group(1), 16), 'function-decl', name))
            for m in re.finditer(r'^(setjmp|longjmp)_address\s*=\s*0x([0-9A-Fa-f]{8})', txt, re.M):
                out.append((int(m.group(2), 16), 'crt', name))
    src = os.path.join(port_dir, 'src')
    for name in sorted(os.listdir(src)):
        if not name.endswith(('.cpp', '.h')):
            continue
        txt = open(os.path.join(src, name), encoding='utf-8', errors='replace').read()
        for m in re.finditer(r'__imp__sub_([0-9A-F]{8})', txt):
            out.append((int(m.group(1), 16), 'override', name))
        for m in re.finditer(r'(?<![_0-9A-Za-z])sub_([0-9A-F]{8})', txt):
            out.append((int(m.group(1), 16), 'call', name))
        for m in re.finditer(r'0x(8[23][0-9A-Fa-f]{6})', txt):
            out.append((int(m.group(1), 16), 'const', name))
    seen = {}
    for a, kind, src_ in out:
        k = (a, kind)
        seen.setdefault(k, set()).add(src_)
    return [(a, kind, ', '.join(sorted(s))) for (a, kind), s in sorted(seen.items())]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('a')
    ap.add_argument('b')
    ap.add_argument('--addr', nargs='*', default=[])
    ap.add_argument('--port', help='папка порта NHL 13 (port/): все адреса toml и src')
    ap.add_argument('--sites', nargs='*', default=[], help='списки мест (docs/team32_sites.json …)')
    ap.add_argument('--json', help='куда записать сопоставление')
    ap.add_argument('--stats', action='store_true')
    args = ap.parse_args()
    for st in (sys.stdout, sys.stderr):
        st.reconfigure(encoding='utf-8')
    log = lambda *m: print(*m, file=sys.stderr)
    A, B = Image(args.a), Image(args.b)
    log(f'A: {len(A.starts)} функций, B: {len(B.starts)}')
    M = Matcher(A, B, log)
    M.exact()
    M.propagate()
    M.by_strings()
    M.propagate()
    if args.stats:
        c = Counter(h.split()[0] for h in M.how.values())
        log(f'пар всего: {len(M.ab)} из {len(A.starts)} ({100 * len(M.ab) / len(A.starts):.1f} %): {dict(c)}')
    items = [(int(x, 16), 'addr', 'cli') for x in args.addr]
    if args.port:
        items += port_addresses(args.port)
    for path in args.sites:
        d = json.load(open(path, encoding='utf-8'))
        for s in d.get('sites', []):
            items.append((int(s['addr'], 16), 'site:' + s.get('class', ''), os.path.basename(path)))
    res = []
    for a, kind, src in items:
        if kind == 'const' and A.func_at(a) is None:
            b, cat, note = M.map_data(a)
            res.append(dict(a=f'{a:08X}', kind=kind, src=src, b=f'{b:08X}' if b else None, cat=cat, note=note))
            continue
        b, cat, note = M.map_addr(a)
        res.append(dict(a=f'{a:08X}', kind=kind, src=src, b=f'{b:08X}' if b else None, cat=cat, note=note))
    if res:
        order = ['func', 'exact', 'same', 'same-imm', 'moved', 'aligned-diff', 'moved-diff', 'lost', 'nofunc', 'data', 'data-?', 'data-lost', 'data-noref']
        by = defaultdict(Counter)
        for r in res:
            by[(r['src'], r['kind'].split(':')[0])][r['cat']] += 1
        log(f'{"источник":34s} {"вид":14s} ' + ' '.join(f'{c:>12s}' for c in order))
        for (src, kind), cnt in sorted(by.items()):
            log(f'{src[:34]:34s} {kind:14s} ' + ' '.join(f'{cnt.get(c, 0):12d}' for c in order))
    if args.json:
        json.dump(dict(a=args.a, b=args.b, pairs=len(M.ab), items=res), open(args.json, 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)
    elif res and not args.port and not args.sites:
        for r in res:
            print(r['a'], '→', r['b'], r['cat'], r['note'])


if __name__ == '__main__':
    main()
