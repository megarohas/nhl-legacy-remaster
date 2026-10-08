"""Архивы EA .big: BigEB v3 (NHL 11 и новее) и BIG4/BIGF (NHL 10 и старше) — список и распаковка.

    python big.py list    ARCHIVE [--pattern RE]
    python big.py extract ARCHIVE OUT_DIR [--pattern RE] [--jobs N] [--raw]
    python big.py disc    DISC_DIR OUT_ROOT [--only RE] [--exclude RE] [--pattern RE] [--jobs N] [--state FILE]

`disc` раскладывает все .big/.viv из DISC_DIR (рекурсивно) по папкам OUT_ROOT/<путь архива без
расширения>/…, `--only`/`--exclude` — по пути архива, `--pattern` — по пути файла внутри.
Сжатые записи разжимаются пулом процессов (`--jobs`, по умолчанию число ядер − 4), `--raw` — без
разжатия. Запись, которую разжать не удалось, сохраняется как есть (с пометкой в выводе).

BigEB v3 (big-endian): 0x04 число записей, 0x0C смещение таблицы имён, 0x14 шаг имени, 0x15 шаг
папки, 0x16 число папок, 0x1C размер архива; с 0x30 записи по 16 байт — смещение в блоках по 16,
сжатый размер (0 — не сжат), полный размер, контрольная сумма (не CRC32 данных); имя — u16 номер
папки + строка; таблица папок — с align16 после имён. Сжатые записи — chunkzip/chunklzx.
BIG4/BIGF: 0x04 размер архива (little-endian), 0x08 число записей и 0x0C размер индекса
(big-endian), записи «смещение, размер (BE), имя\\0»; после индекса метка вроде `L286`.

Сжатие внутри записей:
- EA chunkzip/chunklzx (tools/unchunk.py): куски deflate (1), LZX в кадрах XMemCompress (3),
  без сжатия (0 и 4 — метод 4 встречается в последнем коротком куске, NHL 12 crowd_29.cwd);
- RefPack (QFS): `10 FB` + 3 байта полного размера (у NHL 10 так сжата каждая запись BIG4),
  флаг 0x01 — есть поле сжатого размера, 0x80 — размеры по 4 байта.
"""
import argparse, concurrent.futures as cf, os, re, struct, sys, time, zlib
from pathlib import PurePosixPath

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lzx import xmem_decompress

COPY = 8 << 20
CHUNK_MAGICS = (b'chunkzip', b'chunklzx')

# --- форматы архивов -------------------------------------------------------------------------

class Entry:
    __slots__ = ('path', 'offset', 'stored', 'size')

    def __init__(self, path, offset, stored, size):
        self.path, self.offset, self.stored, self.size = path, offset, stored, size

def cstr(b):
    return b.split(b'\0', 1)[0].decode('latin-1')

def parse(path):
    """-> (формат, [Entry]); size — полный размер, если архив его знает (иначе None)."""
    with open(path, 'rb') as f:
        h = f.read(0x30)
        if h[:4] == b'EB\x00\x03':
            count, = struct.unpack_from('>I', h, 4)
            names_at, = struct.unpack_from('>I', h, 0x0C)
            name_stride, dir_stride = h[0x14], h[0x15]
            dir_count, = struct.unpack_from('>H', h, 0x16)
            f.seek(0x30)
            raw = f.read(count * 16)
            f.seek(names_at)
            names = f.read(count * name_stride)
            f.seek((names_at + count * name_stride + 15) & ~15)
            dirs = f.read(dir_count * dir_stride)
            dirs = [cstr(dirs[i * dir_stride:(i + 1) * dir_stride]) for i in range(dir_count)]
            out = []
            for i in range(count):
                blocks, packed, size, _ = struct.unpack_from('>4I', raw, i * 16)
                rec = names[i * name_stride:(i + 1) * name_stride]
                d = struct.unpack_from('>H', rec)[0]
                name = cstr(rec[2:])
                d = dirs[d] if d < len(dirs) else ''
                out.append(Entry(f'{d}/{name}' if d and d != '.' else name, blocks * 16, packed or size, size))
            return 'BigEB v3', out
        if h[:4] in (b'BIG4', b'BIGF', b'BIG '):
            count, index_size = struct.unpack_from('>II', h, 8)
            f.seek(16)
            idx = f.read(index_size - 16)
            out, p = [], 0
            for _ in range(count):
                off, size = struct.unpack_from('>II', idx, p)
                e = idx.index(b'\0', p + 8)
                out.append(Entry(idx[p + 8:e].decode('latin-1'), off, size, None))
                p = e + 1
            return h[:4].decode().strip(), out
        if h[:2] == b'EB':
            raise ValueError(f'BigEB версии {h[2]}.{h[3]} не поддержан')
        raise ValueError(f'неизвестный формат: {h[:16].hex(" ")}')

# --- сжатие ----------------------------------------------------------------------------------

def is_refpack(b):
    return len(b) >= 5 and b[1] == 0xFB and (b[0] & 0x3E) == 0x10

def refpack(src):
    """RefPack (QFS) -> bytes."""
    flags = src[0]
    n = 4 if flags & 0x80 else 3
    p = 2 + (n if flags & 0x01 else 0)
    size = int.from_bytes(src[p:p + n], 'big')
    p += n
    out = bytearray(size)
    o = 0
    end = len(src)
    while p < end:
        c0 = src[p]
        if c0 < 0x80:
            c1 = src[p + 1]
            p += 2
            lit = c0 & 3
            length = ((c0 & 0x1C) >> 2) + 3
            dist = ((c0 & 0x60) << 3) + c1 + 1
        elif c0 < 0xC0:
            c1 = src[p + 1]
            c2 = src[p + 2]
            p += 3
            lit = c1 >> 6
            length = (c0 & 0x3F) + 4
            dist = ((c1 & 0x3F) << 8) + c2 + 1
        elif c0 < 0xE0:
            c1 = src[p + 1]
            c2 = src[p + 2]
            c3 = src[p + 3]
            p += 4
            lit = c0 & 3
            length = ((c0 & 0x0C) << 6) + c3 + 5
            dist = ((c0 & 0x10) << 12) + (c1 << 8) + c2 + 1
        else:
            p += 1
            lit = ((c0 & 0x1F) << 2) + 4 if c0 < 0xFC else c0 & 3
            out[o:o + lit] = src[p:p + lit]
            p += lit
            o += lit
            if c0 >= 0xFC:
                break
            continue
        if lit:
            out[o:o + lit] = src[p:p + lit]
            p += lit
            o += lit
        s = o - dist
        if s < 0:
            raise ValueError(f'RefPack: ссылка назад за начало (вывод {o}, расстояние {dist})')
        if dist >= length:
            out[o:o + length] = out[s:s + length]
        else:
            out[o:o + length] = (out[s:o] * (length // dist + 1))[:length]
        o += length
    if o != size or len(out) != size:
        raise ValueError(f'RefPack: вышло {o} байт вместо {size}')
    return bytes(out)

def unchunk(blob):
    """EA chunkzip/chunklzx версии 2 -> bytes (как tools/unchunk.py, плюс метод 4)."""
    version, total, chunk_size, count, _ = struct.unpack('>5I', blob[8:0x1C])
    if version != 2:
        raise ValueError(f'chunk: версия {version}')
    end, out = 0x28, bytearray()
    for _ in range(count):
        pos = (end + 8 + 15) & ~15
        comp, method = struct.unpack('>II', blob[pos - 8:pos])
        payload = blob[pos:pos + comp]
        end = pos + comp
        want = min(chunk_size, total - len(out))
        if method in (0, 4):
            chunk = payload
        elif method == 1:
            chunk = zlib.decompress(payload, wbits=-15)
        elif method == 3:
            chunk = xmem_decompress(payload, want, 17)
        else:
            raise ValueError(f'chunk: метод {method}')
        if len(chunk) != want:
            raise ValueError(f'chunk: кусок {len(chunk)} байт вместо {want}')
        out += chunk
    return bytes(out)

def kind(head):
    if head[:8] in CHUNK_MAGICS:
        return head[:8].decode()
    if is_refpack(head):
        return 'refpack'
    return ''

def decode(data):
    """Снимает сжатие (возможно, вложенное) -> (данные, 'вид+вид')."""
    kinds = []
    for _ in range(4):
        k = kind(data[:8])
        if not k:
            break
        data = unchunk(data) if k.startswith('chunk') else refpack(data)
        kinds.append(k)
    return data, '+'.join(kinds)

# --- распаковка ------------------------------------------------------------------------------

def safe_path(root, name):
    name = name.replace('\\', '/')
    if re.match(r'[A-Za-z]:/', name):
        # абсолютный путь со сборочной машины (options.viv: C:\polaris\…\options.txt) — только имя файла
        name = name.rsplit('/', 1)[-1]
    parts = PurePosixPath(name).parts
    if not parts or any(x in ('..', '') or ':' in x for x in parts) or name.startswith(('/', '\\')):
        raise ValueError(f'опасный путь в архиве: {name!r}')
    return os.path.join(root, *parts)

_files = {}

def _job(args):
    """В процессе пула: прочитать запись, разжать, записать. -> (путь, вид, ошибка)."""
    archive, offset, stored, size, dst = args
    f = _files.get(archive)
    if f is None:
        f = _files[archive] = open(archive, 'rb')
    f.seek(offset)
    raw = f.read(stored)
    try:
        data, k = decode(raw)
        if size is not None and k and len(data) != size:
            raise ValueError(f'после разжатия {len(data)} байт, в архиве {size}')
        err = None
    except Exception as e:
        data, k, err = raw, '', str(e)
    try:
        with open(dst, 'wb') as out:
            out.write(data)
    except OSError as e:
        return dst, '', f'не записан: {e}'
    return dst, k, err

def extract(archive, out_dir, pattern=None, jobs=None, raw=False, log=print, pool=None):
    fmt, entries = parse(archive)
    if pattern:
        rx = re.compile(pattern, re.I)
        entries = [e for e in entries if rx.search(e.path)]
    t0 = time.time()
    log(f'{archive}: {fmt}, записей {len(entries)}')
    seen, dup = set(), 0
    queue, errors = [], []
    copied = 0
    with open(archive, 'rb') as f:
        for e in entries:
            try:
                dst = safe_path(out_dir, e.path)
                key = dst.lower()
                if key in seen:
                    dup += 1
                    log(f'  повтор имени (перезапись): {e.path}')
                seen.add(key)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                f.seek(e.offset)
                head = f.read(min(e.stored, 16))
                if not raw and kind(head):
                    # полный размер сверяется только у записей, которые архив сам пометил сжатыми
                    full = e.size if e.size is not None and e.size != e.stored else None
                    queue.append((os.path.abspath(archive), e.offset, e.stored, full, dst))
                    continue
                with open(dst, 'wb') as out:
                    out.write(head)
                    left = e.stored - len(head)
                    while left:
                        b = f.read(min(COPY, left))
                        if not b:
                            raise EOFError('архив обрезан')
                        out.write(b)
                        left -= len(b)
                copied += 1
            except (OSError, ValueError) as x:
                errors.append(f'{e.path}: {x}')
                log(f'  пропущен: {e.path}: {x}')
    stats = {}
    if queue:
        own = pool is None
        if own:
            pool = cf.ProcessPoolExecutor(jobs or max(1, (os.cpu_count() or 4) - 4))
        try:
            step = max(1, len(queue) // 10)
            for i, (dst, k, err) in enumerate(pool.map(_job, queue, chunksize=8), 1):
                if err:
                    errors.append(f'{os.path.relpath(dst, out_dir)}: {err}')
                    log(f'  не разжал (сохранён как есть): {os.path.relpath(dst, out_dir)}: {err}')
                else:
                    stats[k] = stats.get(k, 0) + 1
                if i % step == 0:
                    log(f'  разжато {i}/{len(queue)} ({time.time() - t0:.0f} с)')
        finally:
            if own:
                pool.shutdown()
    kinds = ', '.join(f'{k} {v}' for k, v in sorted(stats.items()))
    log(f'{archive}: готово за {time.time() - t0:.0f} с — файлов {copied + len(queue)}, '
        f'без сжатия {copied}, разжато: {kinds or "—"}, ошибок {len(errors)}, повторов имён {dup}')
    return len(entries), errors

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('list')
    p.add_argument('archive')
    p.add_argument('--pattern')
    p = sub.add_parser('extract')
    p.add_argument('archive')
    p.add_argument('out')
    p.add_argument('--pattern')
    p.add_argument('--jobs', type=int)
    p.add_argument('--raw', action='store_true')
    p = sub.add_parser('disc')
    p.add_argument('disc')
    p.add_argument('out')
    p.add_argument('--only')
    p.add_argument('--exclude')
    p.add_argument('--pattern')
    p.add_argument('--jobs', type=int)
    p.add_argument('--raw', action='store_true')
    p.add_argument('--state', help='файл со списком уже распакованных архивов (дописывается)')
    a = ap.parse_args()
    log = lambda s: print(time.strftime('%H:%M:%S'), s, flush=True)
    if a.cmd == 'list':
        fmt, entries = parse(a.archive)
        rx = re.compile(a.pattern, re.I) if a.pattern else None
        with open(a.archive, 'rb') as f:
            for e in entries:
                if rx and not rx.search(e.path):
                    continue
                f.seek(e.offset)
                k = kind(f.read(16))
                size = '' if e.size is None or e.size == e.stored else f' -> {e.size}'
                print(f'{e.offset:#012x} {e.stored:>11}{size} {k or "-":9} {e.path}')
        print(f'{fmt}: записей {len(entries)}', file=sys.stderr)
        return
    if a.cmd == 'extract':
        _, errors = extract(a.archive, a.out, a.pattern, a.jobs, a.raw, log)
        sys.exit(1 if errors else 0)
    done = set()
    if a.state and os.path.exists(a.state):
        done = set(open(a.state, encoding='utf-8').read().split('\n')) - {''}
    archives = []
    for dp, dn, fn in os.walk(a.disc):
        dn.sort()
        for n in sorted(fn):
            if n.lower().endswith(('.big', '.viv')):
                archives.append(os.path.relpath(os.path.join(dp, n), a.disc).replace('\\', '/'))
    failed = 0
    with cf.ProcessPoolExecutor(a.jobs or max(1, (os.cpu_count() or 4) - 4)) as pool:
        for rel in archives:
            if a.only and not re.search(a.only, rel, re.I) or a.exclude and re.search(a.exclude, rel, re.I):
                continue
            if rel in done:
                log(f'{rel}: уже распакован, пропуск')
                continue
            dst = os.path.join(a.out, *os.path.splitext(rel)[0].split('/'))
            try:
                _, errors = extract(os.path.join(a.disc, rel), dst, a.pattern, None, a.raw, log, pool)
            except Exception as e:
                log(f'{rel}: не распакован: {e}')
                failed += 1
                continue
            failed += bool(errors)
            if a.state and not errors and not a.pattern:
                with open(a.state, 'a', encoding='utf-8') as s:
                    s.write(rel + '\n')
    log(f'архивов с ошибками: {failed}')
    sys.exit(1 if failed else 0)

if __name__ == '__main__':
    main()
