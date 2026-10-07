"""Декодер LZX — порт lzxd из libmspack на чистом Python.

    decompress(stream, out_size, window_bits)       # сплошной поток (XEX2, как в Xenia)
    xmem_decompress(payload, out_size, window_bits)  # кадры XMemCompress (EA chunklzx)

Поток делится на кадры по 0x8000 байт вывода; на границе кадра чтение выравнивается
на 16 бит. Блоки: 1 — verbatim, 2 — aligned, 3 — без сжатия. Слова потока —
little-endian, биты читаются от старшего.
"""

FRAME = 0x8000
NUM_CHARS = 256
NUM_SECONDARY = 249
SLOTS = {15: 30, 16: 32, 17: 34, 18: 36, 19: 38, 20: 42, 21: 50}

EXTRA_BITS, POSITION_BASE = [], []
_j = 0
for _i in range(0, 52, 2):
    EXTRA_BITS += [_j, _j]
    if _i and _j < 17:
        _j += 1
_j = 0
for _i in range(51):
    POSITION_BASE.append(_j)
    _j += 1 << EXTRA_BITS[_i]

class LzxError(ValueError):
    pass

def build_table(lengths, maybe_empty=False):
    """Каноническая таблица Хаффмана на 16 бит: запись = символ << 5 | длина."""
    table = [0] * 0x10000
    pos = 0
    for length, sym in sorted((l, s) for s, l in enumerate(lengths) if l):
        span = 1 << (16 - length)
        table[pos:pos + span] = [(sym << 5) | length] * span
        pos += span
    if pos == 0 and maybe_empty:
        return None
    if pos != 0x10000:
        raise LzxError('неполное дерево Хаффмана')
    return table

class Reader:
    def __init__(self, data):
        self.end = len(data)
        self.data = bytes(data) + bytes(64)
        self.pos = self.buf = self.n = 0

    def bits(self, k):
        if not k:
            return 0
        while self.n < k:
            self.buf = (self.buf << 16) | self.data[self.pos] | (self.data[self.pos + 1] << 8)
            self.pos += 2
            self.n += 16
        self.n -= k
        v = self.buf >> self.n
        self.buf &= (1 << self.n) - 1
        return v

    def sym(self, table):
        while self.n < 16:
            self.buf = (self.buf << 16) | self.data[self.pos] | (self.data[self.pos + 1] << 8)
            self.pos += 2
            self.n += 16
        e = table[self.buf >> (self.n - 16)]
        if not e:
            raise LzxError('неверный код Хаффмана')
        self.n -= e & 31
        self.buf &= (1 << self.n) - 1
        return e >> 5

class Lzx:
    def __init__(self, window_bits):
        if window_bits not in SLOTS:
            raise LzxError(f'окно 2^{window_bits} не поддержано')
        self.wsize = 1 << window_bits
        self.window = bytearray(self.wsize)
        self.wpos = self.fpos = 0
        self.num_offsets = SLOTS[window_bits] << 3
        self.R = [1, 1, 1]
        self.header_read = False
        self.intel_filesize = 0
        self.intel_started = False
        self.block_type = self.block_length = self.block_remaining = 0
        self.main_len = [0] * (NUM_CHARS + self.num_offsets + 64)
        self.length_len = [0] * (NUM_SECONDARY + 64)
        self.main_table = self.length_table = self.aligned_table = None
        self.frame_no = 0
        self.offset = 0

    def read_lens(self, br, lens, first, last):
        pre = build_table([br.bits(4) for _ in range(20)])
        x = first
        while x < last:
            z = br.sym(pre)
            if z == 17:
                y = br.bits(4) + 4
                lens[x:x + y] = [0] * y
            elif z == 18:
                y = br.bits(5) + 20
                lens[x:x + y] = [0] * y
            elif z == 19:
                y = br.bits(1) + 4
                z = lens[x] - br.sym(pre)
                lens[x:x + y] = [z + 17 if z < 0 else z] * y
            else:
                z = lens[x] - z
                lens[x] = z + 17 if z < 0 else z
                y = 1
            x += y

    def read_block_header(self, br):
        if self.block_type == 3 and self.block_length & 1:
            br.pos += 1  # выравнивание после нечётного несжатого блока
        self.block_type = br.bits(3)
        self.block_length = self.block_remaining = (br.bits(16) << 8) | br.bits(8)
        if self.block_type == 2:
            self.aligned_table = build_table([br.bits(3) for _ in range(8)])
        if self.block_type in (1, 2):
            self.read_lens(br, self.main_len, 0, 256)
            self.read_lens(br, self.main_len, 256, NUM_CHARS + self.num_offsets)
            self.main_table = build_table(self.main_len[:NUM_CHARS + self.num_offsets])
            if self.main_len[0xE8]:
                self.intel_started = True
            self.read_lens(br, self.length_len, 0, NUM_SECONDARY)
            self.length_table = build_table(self.length_len[:NUM_SECONDARY], maybe_empty=True)
        elif self.block_type == 3:
            self.intel_started = True
            if br.n == 0:
                br.pos += 2
            br.n = br.buf = 0
            d = br.data
            self.R = [int.from_bytes(d[br.pos + i:br.pos + i + 4], 'little') for i in (0, 4, 8)]
            br.pos += 12
        else:
            raise LzxError(f'неверный тип блока {self.block_type}')

    def frame(self, br, frame_size):
        """Декодирует один кадр вывода (до 0x8000 байт)."""
        if not self.header_read:
            if br.bits(1):
                self.intel_filesize = (br.bits(16) << 16) | br.bits(16)
            self.header_read = True
        window, wsize = self.window, self.wsize
        fstart = self.fpos
        fend = fstart + frame_size
        R0, R1, R2 = self.R
        while self.wpos < fend:
            if self.block_remaining == 0:
                self.R = [R0, R1, R2]
                self.read_block_header(br)
                R0, R1, R2 = self.R
            wpos = self.wpos
            this_run = min(self.block_remaining, fend - wpos)
            self.block_remaining -= this_run
            btype = self.block_type
            if btype == 3:
                window[wpos:wpos + this_run] = br.data[br.pos:br.pos + this_run]
                br.pos += this_run
                self.wpos = wpos + this_run
                continue
            main, lengths, aligned = self.main_table, self.length_table, self.aligned_table
            sym, bits = br.sym, br.bits
            while this_run > 0:
                s = sym(main)
                if s < NUM_CHARS:
                    window[wpos] = s
                    wpos += 1
                    this_run -= 1
                    continue
                s -= NUM_CHARS
                mlen = s & 7
                if mlen == 7:
                    if lengths is None:
                        raise LzxError('пустое дерево длин')
                    mlen += sym(lengths)
                mlen += 2
                slot = s >> 3
                if slot == 0:
                    moff = R0
                elif slot == 1:
                    moff = R1
                    R1 = R0
                    R0 = moff
                elif slot == 2:
                    moff = R2
                    R2 = R0
                    R0 = moff
                elif slot == 3:
                    moff = 1
                    R2, R1, R0 = R1, R0, 1
                else:
                    extra = 17 if slot >= 36 else EXTRA_BITS[slot]
                    moff = POSITION_BASE[slot] - 2
                    if btype == 1:
                        moff += bits(extra)
                    elif extra > 3:
                        moff += bits(extra - 3) << 3
                        moff += sym(aligned)
                    elif extra == 3:
                        moff += sym(aligned)
                    elif extra > 0:
                        moff += bits(extra)
                    else:
                        moff = 1
                    R2, R1, R0 = R1, R0, moff
                if wpos + mlen > wsize:
                    raise LzxError('совпадение выходит за край окна')
                src = wpos - moff
                if src < 0:
                    for k in range(mlen):
                        window[wpos + k] = window[(src + k) % wsize]
                elif moff >= mlen:
                    window[wpos:wpos + mlen] = window[src:src + mlen]
                else:
                    chunk = window[src:wpos]
                    window[wpos:wpos + mlen] = (chunk * (mlen // moff + 1))[:mlen]
                wpos += mlen
                this_run -= mlen
            self.wpos = wpos
            if this_run < 0:
                if -this_run > self.block_remaining:
                    raise LzxError('совпадение выходит за конец блока')
                self.block_remaining += this_run
        self.R = [R0, R1, R2]
        # выравнивание потока на 16 бит в конце кадра
        if br.n & 15:
            br.bits(br.n & 15)
        out = bytearray(window[fstart:fend])
        if self.intel_started and self.intel_filesize and self.frame_no < 32768 and frame_size > 10:
            self.e8_translate(out)
        self.frame_no += 1
        self.offset += frame_size
        self.fpos = fend
        if self.fpos == wsize:
            self.fpos = 0
            self.wpos = 0
        if br.pos > br.end + 32:
            raise LzxError('поток закончился раньше времени')
        return out

    def e8_translate(self, data):
        curpos, filesize, i = self.offset, self.intel_filesize, 0
        while i < len(data) - 10:
            if data[i] != 0xE8:
                i += 1
                curpos += 1
                continue
            abs_off = int.from_bytes(data[i + 1:i + 5], 'little', signed=True)
            if -curpos <= abs_off < filesize:
                rel = abs_off - curpos if abs_off >= 0 else abs_off + filesize
                data[i + 1:i + 5] = (rel & 0xFFFFFFFF).to_bytes(4, 'little')
            i += 5
            curpos += 5

def decompress(stream, out_size, window_bits):
    d, br, out = Lzx(window_bits), Reader(stream), bytearray()
    while len(out) < out_size:
        out += d.frame(br, min(FRAME, out_size - len(out)))
    return bytes(out)

def xmem_decompress(payload, out_size, window_bits):
    d, out, p = Lzx(window_bits), bytearray(), 0
    while len(out) < out_size and p + 2 <= len(payload):
        if payload[p] == 0xFF:
            frame_size = int.from_bytes(payload[p + 1:p + 3], 'big')
            block_size = int.from_bytes(payload[p + 3:p + 5], 'big')
            p += 5
        else:
            frame_size = FRAME
            block_size = int.from_bytes(payload[p:p + 2], 'big')
            p += 2
        if not block_size:
            break
        out += d.frame(Reader(payload[p:p + block_size]), min(frame_size, out_size - len(out)))
        p += block_size
    if len(out) != out_size:
        raise LzxError(f'получено {len(out)} байт вместо {out_size}')
    return bytes(out)
