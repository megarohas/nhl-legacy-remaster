"""Распаковка контейнера SVOD (установка с диска, GoD) Xbox 360.

    python svod.py info    HEADER
    python svod.py verify  HEADER            # всё дерево SHA-1: данные -> L0 -> L1 -> заголовок
    python svod.py list    HEADER
    python svod.py extract HEADER OUT_DIR

HEADER — файл-заголовок контейнера (CON/LIVE/PIRS), части лежат рядом в HEADER.data/Data0000…

Устройство каждой части (до 0xA290000 байт):
    [L1 0x1000][L0 0x1000][0x198 блоков по 0x800][L0][0x198 блоков]…
L0 — 0xCC хешей SHA-1, каждый на 0x1000 байт данных; L1 — хеши таблиц L0, а по
смещению 0xFDC — хеш L1 следующей части. SHA-1 таблицы L1 первой части — корневой
хеш в заголовке. Внутри — файловая система GDF (XDVDFS), секторы по 0x800.
Адресация блоков — как в Xenia (svod_container_device.cc).
"""
import argparse, hashlib, os, struct, sys

BLOCK = 0x800
HASH_BLOCK = 0x1000
BLOCKS_PER_L0 = 0x198
BLOCKS_PER_FILE = 0x14388
MAX_FILE_SIZE = 0xA290000
MEDIA_MAGIC = b'MICROSOFT*XBOX*MEDIA'

class Svod:
    def __init__(self, header_path):
        h = open(header_path, 'rb').read(0xB000)
        self.magic = h[:4]
        if self.magic not in (b'CON ', b'LIVE', b'PIRS'):
            raise ValueError(f'не контейнер Xbox 360: {self.magic!r}')
        self.content_type, = struct.unpack('>I', h[0x344:0x348])
        self.title_id, = struct.unpack('>I', h[0x360:0x364])
        self.name = h[0x411:0x491].decode('utf-16-be').split('\0')[0]
        vd = h[0x379:0x379 + 0x24]
        if struct.unpack('>I', h[0x3A9:0x3AD])[0] != 1:
            raise ValueError('это STFS, а не SVOD')
        self.root_hash = vd[4:0x18]
        self.egdf = bool(vd[0x18] & 0x40)
        self.start_block = int.from_bytes(vd[0x1C:0x1F], 'little')
        self.file_count, = struct.unpack('>I', h[0x39D:0x3A1])
        data_dir = header_path + '.data'
        self.files = [open(os.path.join(data_dir, f'Data{i:04d}'), 'rb') for i in range(self.file_count)]
        if not self.egdf:
            raise NotImplementedError('поддержана только раскладка EGDF')
        root = self.read_raw(0, 0x2000, 0x20)
        if root[:20] != MEDIA_MAGIC:
            raise ValueError('нет сигнатуры GDF по смещению 0x2000')
        self.root_sector, self.root_size = struct.unpack('<II', root[20:28])

    def locate(self, block):
        """Сектор GDF -> (номер части, смещение в ней)."""
        true_block = block - self.start_block * 2 + 2  # EGDF: сдвиг на 0x1000
        file_index, file_block = divmod(true_block, BLOCKS_PER_FILE)
        l0_count = file_block // BLOCKS_PER_L0 + 1
        offset = file_block * BLOCK + (l0_count + 1) * HASH_BLOCK
        if offset >= MAX_FILE_SIZE:
            file_index += 1
            offset = offset % MAX_FILE_SIZE + 0x2000
        return file_index, offset

    def read_raw(self, file_index, offset, size):
        f = self.files[file_index]
        f.seek(offset)
        return f.read(size)

    def spans(self, sector, size):
        """Непрерывные куски (часть, смещение, длина) для size байт с сектора sector."""
        run = None
        for i in range((size + BLOCK - 1) // BLOCK):
            fi, off = self.locate(sector + i)
            n = min(BLOCK, size - i * BLOCK)
            if run and run[0] == fi and run[1] + run[2] == off:
                run[2] += n
            else:
                if run:
                    yield tuple(run)
                run = [fi, off, n]
        if run:
            yield tuple(run)

    def read(self, sector, size):
        return b''.join(self.read_raw(*s) for s in self.spans(sector, size))

    def walk(self, sector=None, size=None, prefix=''):
        """Обход дерева GDF: (путь, сектор, размер, это_папка)."""
        if sector is None:
            sector, size = self.root_sector, self.root_size
        if not size:
            return
        table = self.read(sector, size)
        stack = [0]
        while stack:
            o = stack.pop()
            left, right, start, length, attr, nlen = struct.unpack('<HHIIBB', table[o:o + 14])
            if left == 0xFFFF:  # пустая папка заполнена 0xFF
                continue
            name = table[o + 14:o + 14 + nlen].decode('latin-1')
            path = prefix + name
            is_dir = bool(attr & 0x10)
            yield path, start, length, is_dir
            if is_dir:
                yield from self.walk(start, length, path + '/')
            for child in (right, left):
                if child:
                    stack.append(child * 4)

    def verify(self, progress=None):
        """Проверяет всё дерево хешей; возвращает (ошибки, проверено блоков по 0x1000)."""
        errors, checked = [], 0
        expected_l1 = self.root_hash
        for fi, f in enumerate(self.files):
            f.seek(0, 2)
            fsize = f.tell()
            f.seek(0)
            l1 = f.read(HASH_BLOCK)
            if hashlib.sha1(l1).digest() != expected_l1:
                errors.append(f'Data{fi:04d}: L1 не сходится с цепочкой')
            expected_l1 = l1[0xFDC:0xFF0]
            pos, group = HASH_BLOCK, 0
            while pos < fsize:
                l0 = f.read(HASH_BLOCK)
                if hashlib.sha1(l0).digest() != l1[group * 20:group * 20 + 20]:
                    errors.append(f'Data{fi:04d}: L0 #{group} не сходится')
                pos += HASH_BLOCK
                data = f.read(min(BLOCKS_PER_L0 * BLOCK, fsize - pos))
                for j in range(0, len(data), HASH_BLOCK):
                    if hashlib.sha1(data[j:j + HASH_BLOCK]).digest() != l0[j // HASH_BLOCK * 20:j // HASH_BLOCK * 20 + 20]:
                        errors.append(f'Data{fi:04d}: блок 0x{pos + j:X} не сходится')
                checked += len(data) // HASH_BLOCK
                pos += len(data)
                group += 1
            if progress:
                progress(fi + 1, self.file_count)
        return errors, checked

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('cmd', choices=['info', 'verify', 'list', 'extract'])
    ap.add_argument('header')
    ap.add_argument('out', nargs='?')
    a = ap.parse_args()
    s = Svod(a.header)
    if a.cmd == 'info':
        print(f'{s.magic.decode()} «{s.name}» title {s.title_id:08X}, тип {s.content_type:08X}, '
              f'частей {s.file_count}, EGDF {s.egdf}, start_block {s.start_block}, '
              f'корень GDF: сектор {s.root_sector}, {s.root_size} байт')
    elif a.cmd == 'verify':
        errors, checked = s.verify(lambda i, n: print(f'  {i}/{n}', end='\r', flush=True))
        print()
        print(f'проверено блоков данных: {checked} ({checked * HASH_BLOCK / 2**30:.2f} ГБ)')
        print('\n'.join(errors[:50]) if errors else 'OK: все хеши сходятся')
        sys.exit(1 if errors else 0)
    elif a.cmd == 'list':
        for path, start, length, is_dir in s.walk():
            print(f'{"<dir>" if is_dir else length:>12}  {path}')
    else:
        if not a.out:
            ap.error('нужна папка OUT_DIR')
        files = total = 0
        for path, start, length, is_dir in s.walk():
            dst = os.path.join(a.out, *path.split('/'))
            if is_dir:
                os.makedirs(dst, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, 'wb') as out:
                for span in s.spans(start, length):
                    out.write(s.read_raw(*span))
            files += 1
            total += length
        print(f'распаковано файлов: {files}, {total / 2**30:.2f} ГБ -> {a.out}')

if __name__ == '__main__':
    main()
