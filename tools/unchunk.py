"""Разжимает на месте файлы EA chunkzip / chunklzx (после unpack_big.py).

    python unchunk.py DIR_OR_FILE...

Заголовок 0x20 байт: магия, версия 2, общий размер, размер куска, число кусков,
размер дескриптора. Данные каждого куска начинаются с адреса, кратного 16 (первый —
с 0x30), перед ними 8 байт: размер сжатых данных и метод (0 и 4 — без сжатия,
1 — deflate, 3 — LZX в кадрах XMemCompress с окном 2^17). Следующий кусок —
с align16(конец данных + 8).
"""
import os, struct, sys, zlib
from lzx import xmem_decompress

MAGICS = (b'chunkzip', b'chunklzx')

def unchunk(blob):
    version, total, chunk_size, count, desc_size = struct.unpack('>5I', blob[8:0x1C])
    if version != 2:
        raise ValueError(f'версия {version}')
    end, out = 0x28, bytearray()
    for _ in range(count):
        pos = (end + 8 + 15) & ~15
        comp, method = struct.unpack('>II', blob[pos - 8:pos])
        payload = blob[pos:pos + comp]
        end = pos + comp
        want = min(chunk_size, total - len(out))
        if method in (0, 4):  # 4 — тоже без сжатия: короткий последний кусок (NHL 12 crowd_29.cwd)
            chunk = payload
        elif method == 1:
            chunk = zlib.decompress(payload, wbits=-15)
        elif method == 3:
            chunk = xmem_decompress(payload, want, 17)
        else:
            raise ValueError(f'метод {method}')
        if len(chunk) != want:
            raise ValueError(f'кусок {len(chunk)} байт вместо {want}')
        out += chunk
    return bytes(out)

def main():
    files = []
    for arg in sys.argv[1:]:
        if os.path.isdir(arg):
            files += [os.path.join(dp, f) for dp, _, fs in os.walk(arg) for f in fs]
        else:
            files.append(arg)
    done = failed = 0
    for path in files:
        with open(path, 'rb') as f:
            if f.read(8) not in MAGICS:
                continue
            f.seek(0)
            blob = f.read()
        try:
            data = unchunk(blob)
        except Exception as e:
            print(f'ошибка: {path}: {e}')
            failed += 1
            continue
        with open(path, 'wb') as f:
            f.write(data)
        done += 1
    print(f'разжато: {done}, ошибок: {failed}')
    sys.exit(1 if failed else 0)

if __name__ == '__main__':
    main()
