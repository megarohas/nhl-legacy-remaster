"""Чтение пакетов STFS Xbox 360: апдейты (LIVE), сейвы и профили (CON), DLC (PIRS).

    python stfs.py info    PACKAGE
    python stfs.py verify  PACKAGE           # SHA-1 блоков файлов, таблиц L0 и верхней таблицы
    python stfs.py list    PACKAGE
    python stfs.py extract PACKAGE OUT_DIR

Блоки по 0x1000 сразу после заголовка. На каждые 0xAA блоков данных — таблица L0
(0xAA записей по 0x18: SHA-1, статус, следующий блок), на каждые 0xAA таблиц L0 —
таблица L1. В пакетах с парными таблицами (бит 0 block separation = 0, обычно CON)
у каждой таблицы есть копия, активную выбирает бит 0x40 статуса уровнем выше.
Формулы адресации — как в Velocity (StfsPackage.cpp). Пакеты больше 0x70E4 блоков
(верхний уровень L2) не поддержаны.
"""
import argparse, hashlib, os, struct, sys

BLOCK = 0x1000
PER_TABLE = 0xAA

def u32(b, o):
    return struct.unpack('>I', b[o:o + 4])[0]

class Stfs:
    def __init__(self, path):
        self.f = open(path, 'rb')
        h = self.f.read(0xC000)
        self.magic = h[:4]
        if self.magic not in (b'CON ', b'LIVE', b'PIRS'):
            raise ValueError(f'не пакет Xbox 360: {self.magic!r}')
        if u32(h, 0x3A9) != 0:
            raise ValueError('это SVOD, а не STFS (см. svod.py)')
        self.header_size = u32(h, 0x340)
        self.base = (self.header_size + 0xFFF) & ~0xFFF
        self.header = h[:self.base]
        self.content_type = u32(h, 0x344)
        self.title_id = u32(h, 0x360)
        self.version = u32(h, 0x358)
        self.media_id = u32(h, 0x354)
        self.name = h[0x411:0x491].decode('utf-16-be').split('\0')[0]
        vd = h[0x379:0x379 + 0x24]
        self.block_sep = vd[2]
        self.pairs = (~self.block_sep) & 1  # 1 — у таблиц есть резервные копии
        self.ft_blocks = int.from_bytes(vd[3:5], 'little')
        self.ft_start = int.from_bytes(vd[5:8], 'little')
        self.top_hash = vd[8:0x1C]
        self.alloc = u32(vd, 0x1C)
        self.step0 = 0xAC if self.pairs else 0xAB
        l0_tables = -(-self.alloc // PER_TABLE)
        if l0_tables > PER_TABLE:
            raise NotImplementedError('пакет с таблицей L2 не поддержан')
        self.top_level = 0 if l0_tables <= 1 else 1
        self.top_addr = self.addr(self.l1_block() if self.top_level else 0)
        if self.pairs:
            self.top_addr += (self.block_sep & 2) << 11
        self.top_table = self.read_at(self.top_addr, BLOCK)

    def read_at(self, offset, size):
        self.f.seek(offset)
        return self.f.read(size)

    def addr(self, backing_block):
        return self.base + (backing_block << 12)

    def backing(self, n):
        """Номер блока данных -> номер блока в файле (с учётом хеш-таблиц)."""
        r = (((n + PER_TABLE) // PER_TABLE) << self.pairs) + n
        if n < PER_TABLE:
            return r
        return r + (((n + 0x70E4) // 0x70E4) << self.pairs)

    def l0_block(self, n):
        if n < PER_TABLE:
            return 0
        return (n // PER_TABLE) * self.step0 + (1 << self.pairs)

    def l1_block(self):
        return self.step0

    def l0_active_offset(self, n):
        if not self.pairs:
            return 0
        if self.top_level == 0:
            return (self.block_sep & 2) << 11
        return (self.top_table[(n // PER_TABLE) * 0x18 + 0x14] & 0x40) << 6

    def hash_entry(self, n):
        """(sha1, статус, следующий блок) для блока данных n."""
        e = self.read_at(self.addr(self.l0_block(n)) + self.l0_active_offset(n) + (n % PER_TABLE) * 0x18, 0x18)
        return e[:20], e[20], int.from_bytes(e[21:24], 'big')

    def block(self, n):
        return self.read_at(self.addr(self.backing(n)), BLOCK)

    def chain(self, start, count, consecutive):
        n = start
        for _ in range(count):
            yield n
            n = n + 1 if consecutive else self.hash_entry(n)[2]

    def entries(self):
        """Записи таблицы файлов: dict(path, is_dir, start, blocks, size, consecutive)."""
        raw = []
        for n in self.chain(self.ft_start, self.ft_blocks, False):
            b = self.block(n)
            for o in range(0, BLOCK, 0x40):
                e = b[o:o + 0x40]
                flags = e[0x28]
                if not flags & 0x3F:
                    continue
                raw.append(dict(
                    name=e[:flags & 0x3F].decode('latin-1'),
                    is_dir=bool(flags & 0x80),
                    consecutive=bool(flags & 0x40),
                    blocks=int.from_bytes(e[0x29:0x2C], 'little'),
                    start=int.from_bytes(e[0x2F:0x32], 'little'),
                    parent=struct.unpack('>h', e[0x32:0x34])[0],
                    size=u32(e, 0x34),
                ))
        for e in raw:
            parts, p = [e['name']], e['parent']
            while p >= 0:
                parts.append(raw[p]['name'])
                p = raw[p]['parent']
            e['path'] = '/'.join(reversed(parts))
        return raw

    def file_blocks(self, e):
        return self.chain(e['start'], e['blocks'], e['consecutive'])

    def read_file(self, e):
        data = b''.join(self.block(n) for n in self.file_blocks(e))
        return data[:e['size']]

    def verify(self):
        """Возвращает (ошибки, проверено блоков данных)."""
        errors, checked = [], 0
        if hashlib.sha1(self.header[0x344:self.base]).digest() != self.header[0x32C:0x340]:
            errors.append('заголовок: хеш 0x32C не сходится')
        if hashlib.sha1(self.top_table).digest() != self.top_hash:
            errors.append('верхняя таблица не сходится с хешем в заголовке')
        if self.top_level == 1:
            for i in range(-(-self.alloc // PER_TABLE)):
                n = i * PER_TABLE
                table = self.read_at(self.addr(self.l0_block(n)) + self.l0_active_offset(n), BLOCK)
                if hashlib.sha1(table).digest() != self.top_table[i * 0x18:i * 0x18 + 20]:
                    errors.append(f'таблица L0 #{i} не сходится')
        blocks = list(self.chain(self.ft_start, self.ft_blocks, False))
        for e in self.entries():
            if not e['is_dir']:
                blocks.extend(self.file_blocks(e))
        for n in blocks:
            if hashlib.sha1(self.block(n)).digest() != self.hash_entry(n)[0]:
                errors.append(f'блок {n} не сходится')
            checked += 1
        return errors, checked

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('cmd', choices=['info', 'verify', 'list', 'extract'])
    ap.add_argument('package')
    ap.add_argument('out', nargs='?')
    a = ap.parse_args()
    s = Stfs(a.package)
    if a.cmd == 'info':
        v = s.version
        print(f'{s.magic.decode()} «{s.name}» title {s.title_id:08X}, тип {s.content_type:08X}, '
              f'версия {v >> 28}.{(v >> 24) & 0xF}.{(v >> 8) & 0xFFFF}.{v & 0xFF}, media {s.media_id:08X}, '
              f'блоков {s.alloc}, таблицы {"парные" if s.pairs else "одиночные"}, верхний уровень L{s.top_level}')
    elif a.cmd == 'verify':
        errors, checked = s.verify()
        print(f'проверено блоков данных: {checked}')
        print('\n'.join(errors[:50]) if errors else 'OK: все хеши сходятся')
        sys.exit(1 if errors else 0)
    elif a.cmd == 'list':
        for e in s.entries():
            print(f'{"<dir>" if e["is_dir"] else e["size"]:>12}  {e["path"]}')
    else:
        if not a.out:
            ap.error('нужна папка OUT_DIR')
        n = 0
        for e in s.entries():
            dst = os.path.join(a.out, *e['path'].split('/'))
            if e['is_dir']:
                os.makedirs(dst, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, 'wb') as out:
                out.write(s.read_file(e))
            n += 1
        print(f'распаковано файлов: {n} -> {a.out}')

if __name__ == '__main__':
    main()
