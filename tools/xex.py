"""Распаковка XEX2 Xbox 360: расшифровка, разжатие, проверка хешей.

    python xex.py info    FILE.xex
    python xex.py extract FILE.xex OUT.bin    # образ в памяти, с адреса загрузки
    python xex.py cab     FILE.xex OUT.cab    # поток LZX в CAB для сверки с expand.exe

Ключ файла (security info +0x150) расшифровывается розничным ключом XEX2 (как в
Xenia), им — данные после заголовка (AES-128-CBC, IV = 0). Сжатие «normal»: цепочка
блоков, каждый начинается с размера и SHA-1 следующего (проверяется), внутри куски
с 16-битной длиной — по куску на кадр LZX в 32 КБ. Их поток — обычный LZX, как в
CAB, поэтому сверить разжатие можно эталоном Windows:
    %SystemRoot%\\System32\\expand.exe OUT.cab -F:* ПАПКА
(файл в ПАПКЕ получит имя самого CAB; для NHL 13 вывод lzx.py совпал с expand.exe
байт в байт). Хеши страниц из security info пока не сверяются: формула не выяснена
(нулевые страницы дают SHA-1(страница + следующий дескриптор), остальные — нет).
"""
import argparse, hashlib, struct, sys
import aes, lzx

RETAIL_KEY = bytes.fromhex('20B185A59D28FDC340583FBB0896BF91')
DEVKIT_KEY = bytes(16)
OPT_FILE_FORMAT = 0x000003FF
OPT_ENTRY_POINT = 0x00010100
OPT_EXECUTION_INFO = 0x00040006

def u32(b, o):
    return struct.unpack('>I', b[o:o + 4])[0]

class Xex:
    def __init__(self, path):
        d = self.d = open(path, 'rb').read()
        if d[:4] != b'XEX2':
            raise ValueError('не XEX2')
        self.module_flags, self.pe_offset, _, self.sec_offset, n = struct.unpack('>5I', d[4:0x18])
        self.opt = dict(struct.unpack('>II', d[0x18 + 8 * i:0x20 + 8 * i]) for i in range(n))
        s = self.sec_offset
        self.image_size = u32(d, s + 4)
        self.image_flags = u32(d, s + 0x10C)
        self.load_address = u32(d, s + 0x110)
        self.file_key = d[s + 0x150:s + 0x160]
        count = u32(d, s + 0x180)
        self.pages = [(u32(d, s + 0x184 + 0x18 * i), d[s + 0x188 + 0x18 * i:s + 0x19C + 0x18 * i]) for i in range(count)]
        ff = self.opt[OPT_FILE_FORMAT]
        self.enc_type, self.comp_type = struct.unpack('>HH', d[ff + 4:ff + 8])
        if self.comp_type == 1:
            n_blocks = (u32(d, ff) - 8) // 8
            self.basic_blocks = [struct.unpack('>II', d[ff + 8 + 8 * i:ff + 16 + 8 * i]) for i in range(n_blocks)]
        elif self.comp_type == 2:
            self.window = u32(d, ff + 8)
            self.first_block = u32(d, ff + 0xC)
            self.first_hash = d[ff + 0x10:ff + 0x24]
        elif self.comp_type != 0:
            raise NotImplementedError(f'сжатие {self.comp_type} (дельта-патч .xexp) не поддержано')

    def entry_point(self):
        return self.opt.get(OPT_ENTRY_POINT)

    def execution_info(self):
        o = self.opt.get(OPT_EXECUTION_INFO)
        if o is None:
            return None
        media, ver, base, title = struct.unpack('>4I', self.d[o:o + 16])
        return dict(media_id=media, version=ver, base_version=base, title_id=title)

    def decrypt(self):
        data = self.d[self.pe_offset:]
        if self.enc_type == 0:
            return data, 'нет'
        for name, key in (('розничный', RETAIL_KEY), ('devkit', DEVKIT_KEY)):
            session = aes.ecb_decrypt(key, self.file_key)
            if self.comp_type == 2:
                head = aes.cbc_decrypt(session, data[:(self.first_block + 15) & ~15])[:self.first_block]
                if hashlib.sha1(head).digest() != self.first_hash:
                    continue
            plain = aes.cbc_decrypt(session, data[:len(data) & ~15])
            if self.comp_type != 2 and plain[:2] != b'MZ':
                continue
            return plain, name
        raise ValueError('ни один ключ не подошёл')

    def image(self, log=print):
        data, key = self.decrypt()
        log(f'расшифровано ключом: {key}')
        if self.comp_type == 0:
            return data[:self.image_size]
        if self.comp_type == 1:
            out, p = bytearray(), 0
            for size, zeros in self.basic_blocks:
                out += data[p:p + size] + bytes(zeros)
                p += size
            return bytes(out[:self.image_size])
        chunks = self.lzx_chunks(data, log)
        return lzx.decompress(b''.join(chunks), self.image_size, self.window.bit_length() - 1)

    def lzx_chunks(self, data, log=print):
        """Куски потока LZX из цепочки блоков (с проверкой SHA-1 каждого блока)."""
        chunks, p, size, digest, blocks = [], 0, self.first_block, self.first_hash, 0
        while size:
            block = data[p:p + size]
            if hashlib.sha1(block).digest() != digest:
                raise ValueError(f'блок {blocks} @0x{p:X}: SHA-1 не сходится')
            next_size, next_digest = u32(block, 0), block[4:24]
            q = 24
            while True:
                n = struct.unpack('>H', block[q:q + 2])[0]
                q += 2
                if not n:
                    break
                chunks.append(block[q:q + n])
                q += n
            p += size
            size, digest = next_size, next_digest
            blocks += 1
        log(f'сжатых блоков: {blocks} (SHA-1 сходится), кусков LZX {len(chunks)}, '
            f'{sum(map(len, chunks)):,} байт, окно 0x{self.window:X}')
        return chunks

    def cab(self, name='image.bin'):
        """CAB с одной папкой LZX: по блоку CFDATA на кусок, 32 КБ вывода на блок."""
        if self.comp_type != 2:
            raise ValueError('в CAB имеет смысл выгружать только сжатие LZX')
        data, _ = self.decrypt()
        chunks = self.lzx_chunks(data, log=lambda s: None)
        name = name.encode() + b'\0'
        data_off = 36 + 8 + 16 + len(name)
        blocks = b''.join(struct.pack('<IHH', 0, len(c), min(lzx.FRAME, self.image_size - i * lzx.FRAME)) + c
                          for i, c in enumerate(chunks))
        window_bits = self.window.bit_length() - 1
        return (struct.pack('<4sIIIIIBBHHHHH', b'MSCF', 0, data_off + len(blocks), 0, 44, 0, 3, 1, 1, 1, 0, 0, 0)
                + struct.pack('<IHH', data_off, len(chunks), (window_bits << 8) | 3)
                + struct.pack('<IIHHHH', self.image_size, 0, 0, 0x5A21, 0, 0x20) + name + blocks)

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('cmd', choices=['info', 'extract', 'cab'])
    ap.add_argument('xex')
    ap.add_argument('out', nargs='?')
    a = ap.parse_args()
    x = Xex(a.xex)
    comp = {0: 'нет', 1: 'basic', 2: 'LZX'}[x.comp_type]
    print(f'образ 0x{x.image_size:X} байт @0x{x.load_address:08X}, точка входа 0x{x.entry_point():08X}, '
          f'шифрование {x.enc_type}, сжатие {comp}, дескрипторов страниц {len(x.pages)}')
    ei = x.execution_info()
    if ei:
        print('execution info: ' + ', '.join(f'{k} {v:08X}' for k, v in ei.items()))
    if a.cmd in ('extract', 'cab') and not a.out:
        ap.error('нужен путь для результата')
    if a.cmd == 'extract':
        img = x.image()
        if img[:2] != b'MZ':
            print('предупреждение: образ не начинается с MZ')
        open(a.out, 'wb').write(img)
        print(f'записано {len(img):,} байт -> {a.out}')
    elif a.cmd == 'cab':
        cab = x.cab()
        open(a.out, 'wb').write(cab)
        print(f'записано {len(cab):,} байт -> {a.out}')

if __name__ == '__main__':
    main()
