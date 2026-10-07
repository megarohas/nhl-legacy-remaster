"""AES-128, только расшифровка (ECB/CBC), на чистом Python — для XEX2.

Таблицы строятся при импорте из арифметики GF(2^8), раунды — как rijndaelDecrypt
в OpenSSL (aes_core.c). Самопроверка: python aes.py (вектор FIPS-197 C.1).
"""
import struct

def _xtime(a):
    return ((a << 1) ^ 0x11B) if a & 0x80 else a << 1

def _mul(a, b):
    r = 0
    while b:
        if b & 1:
            r ^= a
        a = _xtime(a)
        b >>= 1
    return r

_exp, _log = [0] * 255, [0] * 256
_x = 1
for _i in range(255):
    _exp[_i] = _x
    _log[_x] = _i
    _x ^= _xtime(_x)  # умножение на генератор 3

SBOX, INV = [0] * 256, [0] * 256
for _a in range(256):
    _b = _exp[(255 - _log[_a]) % 255] if _a else 0
    _s = _b
    for _k in range(1, 5):
        _s ^= ((_b << _k) | (_b >> (8 - _k))) & 0xFF
    SBOX[_a] = _s ^ 0x63
    INV[_s ^ 0x63] = _a

def _ror(w, n):
    return ((w >> n) | (w << (32 - n))) & 0xFFFFFFFF

TD0 = [(_mul(s, 14) << 24) | (_mul(s, 9) << 16) | (_mul(s, 13) << 8) | _mul(s, 11) for s in INV]
TD1 = [_ror(w, 8) for w in TD0]
TD2 = [_ror(w, 16) for w in TD0]
TD3 = [_ror(w, 24) for w in TD0]

def _expand(key):
    w = list(struct.unpack('>4I', key))
    rcon = 1
    for i in range(4, 44):
        t = w[-1]
        if i % 4 == 0:
            t = ((t << 8) | (t >> 24)) & 0xFFFFFFFF
            t = (SBOX[t >> 24] << 24) | (SBOX[(t >> 16) & 255] << 16) | (SBOX[(t >> 8) & 255] << 8) | SBOX[t & 255]
            t ^= rcon << 24
            rcon = _xtime(rcon) & 0xFF
        w.append(w[-4] ^ t)
    rounds = [w[4 * r:4 * r + 4] for r in range(10, -1, -1)]
    imc = lambda x: TD0[SBOX[x >> 24]] ^ TD1[SBOX[(x >> 16) & 255]] ^ TD2[SBOX[(x >> 8) & 255]] ^ TD3[SBOX[x & 255]]
    for r in range(1, 10):
        rounds[r] = [imc(x) for x in rounds[r]]
    return rounds

def _decrypt_block(rk, s0, s1, s2, s3):
    k = rk[0]
    s0 ^= k[0]; s1 ^= k[1]; s2 ^= k[2]; s3 ^= k[3]
    for r in range(1, 10):
        k = rk[r]
        t0 = TD0[s0 >> 24] ^ TD1[(s3 >> 16) & 255] ^ TD2[(s2 >> 8) & 255] ^ TD3[s1 & 255] ^ k[0]
        t1 = TD0[s1 >> 24] ^ TD1[(s0 >> 16) & 255] ^ TD2[(s3 >> 8) & 255] ^ TD3[s2 & 255] ^ k[1]
        t2 = TD0[s2 >> 24] ^ TD1[(s1 >> 16) & 255] ^ TD2[(s0 >> 8) & 255] ^ TD3[s3 & 255] ^ k[2]
        t3 = TD0[s3 >> 24] ^ TD1[(s2 >> 16) & 255] ^ TD2[(s1 >> 8) & 255] ^ TD3[s0 & 255] ^ k[3]
        s0, s1, s2, s3 = t0, t1, t2, t3
    k = rk[10]
    return ((INV[s0 >> 24] << 24 | INV[(s3 >> 16) & 255] << 16 | INV[(s2 >> 8) & 255] << 8 | INV[s1 & 255]) ^ k[0],
            (INV[s1 >> 24] << 24 | INV[(s0 >> 16) & 255] << 16 | INV[(s3 >> 8) & 255] << 8 | INV[s2 & 255]) ^ k[1],
            (INV[s2 >> 24] << 24 | INV[(s1 >> 16) & 255] << 16 | INV[(s0 >> 8) & 255] << 8 | INV[s3 & 255]) ^ k[2],
            (INV[s3 >> 24] << 24 | INV[(s2 >> 16) & 255] << 16 | INV[(s1 >> 8) & 255] << 8 | INV[s0 & 255]) ^ k[3])

def ecb_decrypt(key, data):
    rk = _expand(key)
    return b''.join(struct.pack('>4I', *_decrypt_block(rk, *w)) for w in struct.iter_unpack('>4I', data))

def cbc_decrypt(key, data, iv=bytes(16)):
    rk = _expand(key)
    out = bytearray(len(data))
    p0, p1, p2, p3 = struct.unpack('>4I', iv)
    pack = struct.Struct('>4I').pack_into
    for i, (c0, c1, c2, c3) in enumerate(struct.iter_unpack('>4I', data)):
        d0, d1, d2, d3 = _decrypt_block(rk, c0, c1, c2, c3)
        pack(out, i * 16, d0 ^ p0, d1 ^ p1, d2 ^ p2, d3 ^ p3)
        p0, p1, p2, p3 = c0, c1, c2, c3
    return bytes(out)

if __name__ == '__main__':
    got = ecb_decrypt(bytes(range(16)), bytes.fromhex('69c4e0d86a7b0430d8cdb78070b4c55a'))
    assert got == bytes.fromhex('00112233445566778899aabbccddeeff'), got.hex()
    print('FIPS-197 C.1: OK')
