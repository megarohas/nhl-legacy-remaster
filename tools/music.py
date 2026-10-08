"""Музыка NHL 13: банк audio/music (EA SBR + SBS, кодек EALayer3) и названия песен EA Trax.

    python music.py unpack                       # банк с диска → game/work/music/orig
    python music.py list    [--all]              # песни EA Trax (trax0…trax15) и все звуки банка
    python music.py export  WHAT… OUT_DIR [--wav]  # звук → .mp3 (без потерь) или .wav
    python music.py init    TRACKS_DIR           # tracks.txt по файлам папки (теги — ffprobe)
    python music.py build   TRACKS_DIR [OUT]     # песни + tracks.txt → OUT/audio/music/* (cache:)
    python music.py check   [DIR] [--deep] [--decode WHAT…]  # проверка собранного банка

WHAT — слот EA Trax `trax0`…`trax15`, id звука (`105`, `id105`) или категория (`HomeGoal`).
Исходный банк — game/work/music/orig (`--orig`), вывод — game/work/music/out в раскладке
cache: (`audio/music/` — три файла банка, `fe/ion/artassets/eatrax*/` — обложки); ставится
копированием в game/userdata/cache/guest. tracks.txt: «слот = файл | исполнитель | название |
альбом | обложка». build: `--no-alt` (не трогать вторые версии песен), `--copy` (MP3 44,1 кГц
стерео без перекодирования), `--quality N` (LAME -V, по умолчанию 2), `--bitrate K` (CBR),
`--volume дБ`, `--no-covers`.

Устройство (docs/music.md):
- `music_samples.sbr` — оглавление «SBKR»: 195 звуков, у каждого одно поле SNS1 — смещение
  потока в `.sbs`. `music_samples.sbs` — «SBKS» + 12 нулей, потоки подряд, каждый с границы 16.
- Поток — EA SPS: блок `H` (0x48, 12 байт: версия 1, кодек 5 = EALayer3 v1b, каналы,
  частота, тип 1 = поток, число сэмплов), блоки `D` (0x44: размер, сэмплов в блоке, кадры),
  блок `E` (0x45, 4–7 байт, выравнивает конец на 4).
- EALayer3 v1b — гранулы MPEG-1 Layer III без резервуара битов: на гранулу свой кадр
  [флаг 0x00/0xEE][2+2+2+2 бит заголовок][номер гранулы][scfsi у второй][по каналу 12+47 бит
  побочной информации][основные данные][добивка до байта]. У второго кадра первого блока флаг
  0xEE: после него 16 бит «отбросить» (0), 16 бит число PCM-сэмплов (47), 32 бита нулей и
  47 сэмплов PCM s16be — сначала левый канал, потом правый. Декодер выдаёт эти 47 сэмплов,
  отбрасывает первые 1152 сэмпла MP3 (задержка кодера LAME 576 + декодера 529 = 1105 = 1152 − 47)
  и дальше идёт по MP3. Значит, MP3 от LAME переупаковывается в EALayer3 без потерь.
- `music_musicboxdata.bin` — «MBX0»: по записи на звук (id, тип, теги «ключ=значение»):
  VolumeType (категория), у песен EA Trax ещё Index, Artist, Album, Title, AssetID, FirstBoot,
  loc_* (ключей eatrax13_* в nhl_eng_us.db нет — меню берёт простые строки).

MP3/FLAC/WAV читаются и MP3 кодируется через ffmpeg (есть в PATH: winget Gyan.FFmpeg).
"""
import argparse, os, re, shutil, struct, subprocess, sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
ORIG = os.path.join(ROOT, 'game', 'work', 'music', 'orig')
OUT = os.path.join(ROOT, 'game', 'work', 'music', 'out')
BANK = ('audio', 'music')
SBR, SBS, MBX = 'music_samples.sbr', 'music_samples.sbs', 'music_musicboxdata.bin'

SAMPLE_RATES = (44100, 48000, 32000)
BITRATES = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320)
GRANULE = 576
DELAY_PCM = 47            # сэмплов PCM в начале потока
DISCARD = 1152            # декодер отбрасывает столько сэмплов MP3
BLOCK_GRANULES = 16       # обычный блок D: 16 гранул = 9216 сэмплов
FIRST_GRANULES = 18       # первый блок: 18 гранул − 1152 + 47 = 9263 сэмпла
CODEC_EAL31B = 5

# ---------------------------------------------------------------- биты

class Bits:
    """Чтение битов от старшего: блок целиком — одно большое целое."""
    def __init__(self, data):
        self.n = int.from_bytes(data, 'big')
        self.size = len(data) * 8
        self.pos = 0

    def read(self, k):
        v = (self.n >> (self.size - self.pos - k)) & ((1 << k) - 1)
        self.pos += k
        return v

class BitWriter:
    def __init__(self):
        self.v = 0
        self.n = 0

    def put(self, value, k):
        if k:
            self.v = (self.v << k) | (value & ((1 << k) - 1))
            self.n += k

    def align(self):
        self.put(0, -self.n % 8)

    def bytes(self):
        self.align()
        return self.v.to_bytes(self.n // 8, 'big')

# ---------------------------------------------------------------- гранулы MP3

class Granule:
    """Гранула MPEG-1 Layer III вместе со своими основными данными."""
    __slots__ = ('sri', 'mode', 'modeext', 'gi', 'scfsi', 'side', 'data')

    def __init__(self, sri, mode, modeext, gi, scfsi, side, data):
        self.sri, self.mode, self.modeext, self.gi = sri, mode, modeext, gi
        self.scfsi = scfsi      # у гранулы 1: по 4 бита на канал
        self.side = side        # по каналу: (part2_3_length, остальные 47 бит)
        self.data = data        # по каналу: основные данные как целое (part2_3_length бит)

    @property
    def nch(self):
        return 1 if self.mode == 3 else 2


def _skip_id3(mp3):
    if mp3[:3] == b'ID3':
        size = 0
        for b in mp3[6:10]:
            size = (size << 7) | (b & 0x7F)
        return 10 + size + (10 if mp3[5] & 0x10 else 0)
    return 0


def lame_padding(mp3):
    """Сэмплов добивки в конце по тегу LAME после заголовка Xing/Info первого кадра, иначе 0."""
    pos = _skip_id3(mp3)
    i = max(mp3.find(b'Xing', pos, pos + 64), mp3.find(b'Info', pos, pos + 64))
    if i < 0:
        return 0
    flags = int.from_bytes(mp3[i + 4:i + 8], 'big')
    j = i + 8 + 4 * bool(flags & 1) + 4 * bool(flags & 2) + 100 * bool(flags & 4) + 4 * bool(flags & 8)
    d = mp3[j + 21:j + 24]                   # строка кодера 9 байт, … задержка 12 бит, добивка 12 бит
    return ((d[1] & 0x0F) << 8) | d[2] if len(d) == 3 else 0


def mp3_granules(mp3):
    """Кадры MP3 (MPEG-1 Layer III) → гранулы, резервуар битов раскрыт."""
    pos = _skip_id3(mp3)
    res = bytearray()           # основные данные всех кадров подряд
    out = []
    first = True
    while pos + 4 <= len(mp3):
        h = int.from_bytes(mp3[pos:pos + 4], 'big')
        if h >> 21 != 0x7FF:
            if mp3[pos:pos + 3] == b'TAG' or not any(mp3[pos:]):
                break
            raise ValueError(f'MP3: нет синхронизации на 0x{pos:x}')
        ver, layer, noprot = (h >> 19) & 3, (h >> 17) & 3, (h >> 16) & 1
        bri, sri, pad = (h >> 12) & 15, (h >> 10) & 3, (h >> 9) & 1
        mode, modeext = (h >> 6) & 3, (h >> 4) & 3
        if ver != 3 or layer != 1:
            raise ValueError('MP3: нужен MPEG-1 Layer III (частота 32/44,1/48 кГц)')
        if bri in (0, 15) or sri == 3:
            raise ValueError(f'MP3: битрейт {bri}/частота {sri} не поддерживаются')
        size = 144000 * BITRATES[bri] // SAMPLE_RATES[sri] + pad
        nch = 1 if mode == 3 else 2
        silen = 17 if nch == 1 else 32
        p = pos + 4 + (0 if noprot else 2)
        frame_end = pos + size
        if frame_end > len(mp3):
            break                                   # обрезанный хвост
        slot = mp3[p + silen:frame_end]
        if first and (slot[:4] in (b'Xing', b'Info') or mp3[pos + 36:pos + 40] == b'VBRI'):
            pos = frame_end                         # служебный кадр (LAME/Fraunhofer) без звука
            first = False
            continue
        first = False
        b = Bits(mp3[p:p + silen])
        mdb = b.read(9)
        b.read(5 if nch == 1 else 3)
        scfsi = [b.read(4) for _ in range(nch)]
        side = [[(b.read(12), b.read(47)) for _ in range(nch)] for _ in range(2)]
        start = len(res) - mdb
        if start < 0:
            raise ValueError('MP3: резервуар ссылается до начала потока')
        res += slot
        total = sum(p23 for gr in side for p23, _ in gr)
        md = Bits(bytes(res[start:start + (total + 7) // 8]))
        for gi in range(2):
            data = [md.read(p23) for p23, _ in side[gi]]
            out.append(Granule(sri, mode, modeext, gi, scfsi if gi else None, side[gi], data))
        if len(res) > 1 << 16:                     # резервуар не длиннее 511 байт
            del res[:len(res) - 4096]
        pos = frame_end
    return out

# ---------------------------------------------------------------- EALayer3 v1b

def eal3_frame(g, pcm=None):
    """Гранула → кадр EALayer3 v1b; pcm — (сэмплов, байты s16be по каналам подряд)."""
    w = BitWriter()
    w.put(0xEE if pcm else 0x00, 8)
    w.put(3, 2); w.put(g.sri, 2); w.put(g.mode, 2); w.put(g.modeext, 2)
    w.put(g.gi, 1)
    if g.gi:
        for s in g.scfsi:
            w.put(s, 4)
    for p23, rest in g.side:
        w.put(p23, 12); w.put(rest, 47)
    for (p23, _), d in zip(g.side, g.data):
        w.put(d, p23)
    w.align()
    if pcm:
        n, raw = pcm
        w.put(0, 16); w.put(n, 16); w.put(0, 32)
        return w.bytes() + raw
    return w.bytes()


def eal3_parse(payload):
    """Данные блока D → гранулы и PCM (список (сэмплов, байты) у кадров 0xEE)."""
    b = Bits(payload)
    grans, pcms = [], []
    while b.pos < b.size:
        start = b.pos
        flag = b.read(8)
        if flag not in (0x00, 0xEE):
            raise ValueError(f'EALayer3: флаг 0x{flag:02x} на байте {start // 8}')
        vi, sri, mode, modeext, gi = b.read(2), b.read(2), b.read(2), b.read(2), b.read(1)
        if vi != 3:
            raise ValueError('EALayer3: поддерживается только MPEG-1')
        nch = 1 if mode == 3 else 2
        scfsi = [b.read(4) for _ in range(nch)] if gi else None
        side = [(b.read(12), b.read(47)) for _ in range(nch)]
        data = [b.read(p23) for p23, _ in side]
        b.pos += -(b.pos - start - 8) % 8
        grans.append(Granule(sri, mode, modeext, gi, scfsi, side, data))
        if flag == 0xEE:
            b.read(16)                               # отбросить (у v1b — 0)
            n = b.read(16)
            b.read(32)
            byte = b.pos // 8
            pcms.append((n, payload[byte:byte + 2 * n * nch]))
            b.pos += 16 * n * nch
    if b.pos != b.size:
        raise ValueError('EALayer3: кадры не сходятся с размером блока')
    return grans, pcms


def granules_to_mp3(grans):
    """Гранулы → MP3 320 кбит/с с резервуаром (для прослушивания и проверки через ffmpeg).

    Слоты основных данных всех кадров — одна лента; данные кадра k кладутся как можно
    раньше: с конца данных кадра k−1, но не дальше 511 байт до начала своего слота."""
    if len(grans) % 2:
        grans = grans[:-1]
    if not grans:
        return b''
    sri, nch = grans[0].sri, grans[0].nch
    cap = 144000 * 320 // SAMPLE_RATES[sri] - 4 - (17 if nch == 1 else 32)
    nframes = len(grans) // 2
    tape = bytearray(cap * nframes)
    heads = []
    end = 0                                          # конец данных предыдущего кадра
    for k in range(nframes):
        g0, g1 = grans[2 * k], grans[2 * k + 1]
        if g0.gi != 0 or g1.gi != 1:
            raise ValueError('EALayer3: гранулы не парами')
        md = BitWriter()
        for g in (g0, g1):
            for (p23, _), d in zip(g.side, g.data):
                md.put(d, p23)
        md = md.bytes()
        slot = k * cap
        start = max(end, slot - 511)
        if start + len(md) > slot + cap:
            raise ValueError('EALayer3: гранулы не влезают в кадр 320 кбит/с')
        tape[start:start + len(md)] = md
        end = start + len(md)
        si = BitWriter()
        si.put(slot - start, 9); si.put(0, 5 if nch == 1 else 3)
        for s in g1.scfsi:
            si.put(s, 4)
        for g in (g0, g1):
            for p23, rest in g.side:
                si.put(p23, 12); si.put(rest, 47)
        hdr = (0x7FF << 21) | (3 << 19) | (1 << 17) | (1 << 16) | (14 << 12) | (sri << 10) \
            | (g0.mode << 6) | (g0.modeext << 4) | (1 << 2)
        heads.append(hdr.to_bytes(4, 'big') + si.bytes())
    return b''.join(h + tape[k * cap:(k + 1) * cap] for k, h in enumerate(heads))

# ---------------------------------------------------------------- поток SPS

def sps_header(raw):
    """Блок H → (кодек, каналы, частота, сэмплов, длина заголовка)."""
    if raw[0] != 0x48:
        raise ValueError(f'SPS: нет блока H (0x{raw[0]:02x})')
    size = int.from_bytes(raw[1:4], 'big')
    h1, h2 = struct.unpack_from('>II', raw, 4)
    if h1 >> 28 != 1 or (h2 >> 30) & 3 != 1:
        raise ValueError('SPS: ожидалась версия 1 и тип «поток»')
    return (h1 >> 24) & 15, ((h1 >> 18) & 63) + 1, h1 & 0x3FFFF, h2 & 0x1FFFFFFF, size


def sps_blocks(raw):
    """Поток целиком → список блоков D (сэмплов, данные); проверяет блок E."""
    pos = sps_header(raw)[4]
    blocks = []
    while True:
        bid, size = raw[pos], int.from_bytes(raw[pos + 1:pos + 4], 'big')
        if bid == 0x45:
            return blocks
        if bid != 0x44 or size < 8:
            raise ValueError(f'SPS: блок 0x{bid:02x} на 0x{pos:x}')
        blocks.append((int.from_bytes(raw[pos + 4:pos + 8], 'big'), raw[pos + 8:pos + size]))
        pos += size


def sps_read(f, off):
    """Поток из открытого .sbs по смещению → байты потока (до конца блока E)."""
    f.seek(off)
    head = f.read(16)
    size = sps_header(head)[4]
    pos, parts = off + size, [head[:size]]
    while True:
        f.seek(pos)
        b = f.read(4)
        bsz = int.from_bytes(b[1:4], 'big')
        if len(b) < 4 or b[0] not in (0x44, 0x45) or bsz < 4:
            raise ValueError(f'SPS: битый блок на 0x{pos:x}')
        f.seek(pos)
        parts.append(f.read(bsz))
        pos += bsz
        if b[0] == 0x45:
            return b''.join(parts)


def stream_decode_parts(raw):
    """Поток EALayer3 → (гранулы, PCM-начала, сэмплов по заголовку, каналы, частота)."""
    codec, ch, rate, ns, _ = sps_header(raw)
    if codec != CODEC_EAL31B:
        raise ValueError(f'кодек {codec} не поддерживается (ожидался 5 — EALayer3 v1b)')
    grans, pcms = [], []
    for _, payload in sps_blocks(raw):
        g, p = eal3_parse(payload)
        grans += g
        pcms += p
    return grans, pcms, ns, ch, rate


def sps_build(grans, pcm47, nsamples, channels, rate, max_block=9600):
    """Гранулы MP3 + 47 сэмплов PCM (planar s16be) → поток SPS как у EA.

    Первый блок — 18 гранул (минус 1152 на задержку, плюс 47 PCM), дальше по 16
    (крупный блок дробится до 8 гранул, чтобы не превышать max_block байт — у EA
    самый большой 9671); хвост короче 8 гранул присоединяется к последнему блоку."""
    need = -(-(nsamples - DELAY_PCM + DISCARD) // GRANULE)
    need += need % 2
    if len(grans) < need:
        need = len(grans) // 2 * 2
        nsamples = need * GRANULE - DISCARD + DELAY_PCM
    grans = grans[:need]
    if need < FIRST_GRANULES + 2:
        raise ValueError('звук слишком короткий')
    frames = [eal3_frame(g, (DELAY_PCM, pcm47) if i == 1 else None) for i, g in enumerate(grans)]
    sizes, i = [FIRST_GRANULES], FIRST_GRANULES
    while i < need:
        left = need - i
        n = min(BLOCK_GRANULES, left)
        if 0 < left - n < 8:
            n = left
        while n > 8 and sum(len(x) for x in frames[i:i + n]) + 8 > max_block:
            n -= 2
        sizes.append(n)
        i += n
    out = bytearray(b'\x48\x00\x00\x0c')
    out += struct.pack('>II', (1 << 28) | (CODEC_EAL31B << 24) | ((channels - 1) << 18) | rate,
                       (1 << 30) | nsamples)
    i, left = 0, nsamples
    for k, n in enumerate(sizes):
        samples = n * GRANULE - (DISCARD - DELAY_PCM if k == 0 else 0)
        samples = left if k == len(sizes) - 1 else min(samples, left)
        payload = b''.join(frames[i:i + n])
        out += struct.pack('>II', (0x44 << 24) | (len(payload) + 8), samples) + payload
        left -= samples
        i += n
    pad = -(len(out) + 4) % 4
    out += struct.pack('>I', (0x45 << 24) | (4 + pad)) + bytes(pad)
    return bytes(out)

# ---------------------------------------------------------------- ffmpeg

def ffmpeg(args, data=None):
    exe = shutil.which('ffmpeg')
    if not exe:
        raise SystemExit('нужен ffmpeg в PATH (у пользователя стоит winget Gyan.FFmpeg)')
    r = subprocess.run([exe, '-hide_banner', '-v', 'error', '-nostdin'] + args,
                       input=data, capture_output=True)
    if r.returncode:
        raise RuntimeError('ffmpeg: ' + r.stderr.decode('utf-8', 'replace').strip()[-800:])
    return r.stdout


def ffprobe_tags(path):
    exe = shutil.which('ffprobe')
    if not exe:
        return {}
    r = subprocess.run([exe, '-v', 'error', '-show_entries', 'format_tags=artist,title,album',
                        '-of', 'default=noprint_wrappers=1', path], capture_output=True)
    tags = {}
    for line in r.stdout.decode('utf-8', 'replace').splitlines():
        if '=' in line:
            k, v = line.split('=', 1)
            tags[k.split(':')[-1].lower()] = v.strip()
    return tags


def decode_pcm(path, volume=None):
    """Любой звук → PCM s16le, 44100 Гц, стерео (volume — усиление в дБ)."""
    af = ['-af', f'volume={volume}dB'] if volume else []
    return ffmpeg(['-i', path, '-map', '0:a:0', '-vn'] + af +
                  ['-ac', '2', '-ar', '44100', '-f', 's16le', '-acodec', 'pcm_s16le', 'pipe:1'])


def encode_mp3(pcm, quality=2, bitrate=None):
    """PCM s16le 44100 стерео → MP3 (LAME: VBR -V quality или CBR bitrate кбит/с)."""
    mode = ['-b:a', f'{bitrate}k'] if bitrate else ['-q:a', str(quality)]
    return ffmpeg(['-f', 's16le', '-ar', '44100', '-ac', '2', '-i', 'pipe:0',
                   '-c:a', 'libmp3lame'] + mode +
                  ['-write_xing', '0', '-id3v2_version', '0', '-f', 'mp3', 'pipe:1'], pcm)


def mp3_raw_decode(mp3):
    """MP3 без тега LAME → PCM s16le как есть (вместе с задержкой декодера)."""
    return ffmpeg(['-f', 'mp3', '-i', 'pipe:0', '-f', 's16le', '-acodec', 'pcm_s16le', 'pipe:1'], mp3)


def pcm_head(grans):
    """47 сэмплов, которые декодер выдал бы на местах 1105…1151, — planar s16be.

    Берутся из декодированного начала самих гранул: PCM-начало и MP3 после отброса
    1152 сэмплов стыкуются без шва при любой задержке кодера."""
    raw = mp3_raw_decode(granules_to_mp3(grans[:8]))
    nch = grans[0].nch
    start = (DISCARD - DELAY_PCM) * 2 * nch
    vals = struct.unpack('<%dh' % (DELAY_PCM * nch), raw[start:start + DELAY_PCM * 2 * nch])
    return b''.join(struct.pack('>%dh' % DELAY_PCM, *vals[c::nch]) for c in range(nch))


def encode_track(path, quality=2, bitrate=None, copy=False, volume=None):
    """Файл пользователя → (поток SPS EALayer3, как кодировали).

    copy — MP3 (MPEG-1, 44,1 кГц, стерео) переупаковать без перекодирования."""
    if copy and path.lower().endswith('.mp3') and not volume:
        data = open(path, 'rb').read()
        try:
            grans = mp3_granules(data)
            ok = len(grans) > 40 and all(g.sri == 0 and g.nch == 2 for g in grans)
        except ValueError:
            ok = False
        if ok:
            ns = len(grans) * GRANULE - (DISCARD - DELAY_PCM)
            ns -= min(max(0, lame_padding(data) - 529), ns // 2)   # добивка LAME включает 529 декодера
            return sps_build(grans, pcm_head(grans), ns, 2, 44100), 'MP3 без перекодирования'
    pcm = decode_pcm(path, volume)
    ns = len(pcm) // 4
    if ns < 44100:
        raise ValueError('звук короче секунды')
    grans = mp3_granules(encode_mp3(pcm, quality, bitrate))
    how = f'LAME {bitrate} кбит/с' if bitrate else f'LAME -V{quality}'
    return sps_build(grans, pcm_head(grans), ns, 2, 44100), how


def stream_to_pcm(raw):
    """Поток банка → PCM s16le так, как его выдаёт игра: 47 PCM + MP3 после 1152."""
    grans, pcms, ns, ch, rate = stream_decode_parts(raw)
    dec = mp3_raw_decode(granules_to_mp3(grans))
    head = b''
    if pcms:
        n, planar = pcms[0]
        vals = [struct.unpack('>%dh' % n, planar[c * 2 * n:(c + 1) * 2 * n]) for c in range(ch)]
        head = b''.join(struct.pack('<%dh' % ch, *(v[i] for v in vals)) for i in range(n))
    return (head + dec[DISCARD * 2 * ch:])[:ns * 2 * ch], ch, rate


def wav_bytes(pcm, ch, rate):
    return (b'RIFF' + struct.pack('<I', 36 + len(pcm)) + b'WAVEfmt ' +
            struct.pack('<IHHIIHH', 16, 1, ch, rate, rate * 2 * ch, 2 * ch, 16) +
            b'data' + struct.pack('<I', len(pcm)) + pcm)

# ---------------------------------------------------------------- архивы и chunklzx

def u32(d, o):
    return struct.unpack_from('>I', d, o)[0]


def cstr(d, o):
    return d[o:d.index(b'\0', o)].decode('utf-8')


def unchunked(data):
    """Снять EA chunklzx/chunkzip, если он есть (tools/unchunk.py)."""
    if data[:8] in (b'chunklzx', b'chunkzip'):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from unchunk import unchunk
        return unchunk(data)
    return data


def big_extract(archive, wanted, outdir):
    """Достать файлы из BigEB v3 диска по путям в архиве (как unpack_big.py) → список путей."""
    got = []
    with open(archive, 'rb') as f:
        h = f.read(0x30)
        if h[:4] != b'EB\x00\x03':
            raise ValueError(f'{archive}: не BigEB v3')
        count, noff = u32(h, 4), u32(h, 0xC)
        nstride, dstride, ndirs = h[0x14], h[0x15], struct.unpack_from('>H', h, 0x16)[0]
        f.seek(0x30)
        ents = f.read(count * 16)
        f.seek(noff)
        names = f.read(count * nstride)
        f.seek((noff + count * nstride + 15) & ~15)
        dirs = f.read(ndirs * dstride)
        dirs = [dirs[i * dstride:(i + 1) * dstride].split(b'\0')[0].decode('latin1') for i in range(ndirs)]
        for i in range(count):
            off, packed, size, _ = struct.unpack_from('>4I', ents, 16 * i)
            rec = names[i * nstride:(i + 1) * nstride]
            di = struct.unpack_from('>H', rec)[0]
            name = rec[2:].split(b'\0')[0].decode('latin1')
            path = f'{dirs[di]}/{name}' if di < len(dirs) and dirs[di] not in ('', '.') else name
            if path.lower() not in wanted:
                continue
            if packed:
                raise ValueError(f'{path}: упакован chunkzip в оглавлении — не ожидалось')
            dst = os.path.join(outdir, *path.split('/'))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            f.seek(off * 16)
            with open(dst, 'wb') as o:
                left = size
                head = f.read(min(left, 1 << 20))
                if head[:8] in (b'chunklzx', b'chunkzip'):
                    o.write(unchunked(head + f.read(left - len(head))))
                else:
                    o.write(head)
                    left -= len(head)
                    while left:
                        part = f.read(min(left, 8 << 20))
                        o.write(part)
                        left -= len(part)
            got.append(dst)
    return got

# ---------------------------------------------------------------- music_musicboxdata.bin

class MusicBox:
    """MBX0: шапка (событие trigger_MusicEvent) + по записи на звук с тегами «ключ=значение»."""
    def __init__(self, data):
        if data[:4] != b'MBX0':
            raise ValueError('не MBX0')
        n, tab = u32(data, 0x8C), u32(data, 0x90)
        self.prefix = data[:tab]
        self.records = []
        for i in range(n):
            r = list(struct.unpack_from('>9I', data, tab + 36 * i))
            sid, misc, typ, npairs, off = r[0], r[1:6], r[6], r[7], r[8]
            ptrs = struct.unpack_from('>%dI' % (2 * npairs), data, off)
            tags = [[cstr(data, ptrs[2 * j]), cstr(data, ptrs[2 * j + 1])] for j in range(npairs)]
            self.records.append([sid, misc, typ, tags])
        self.by_id = {r[0]: r for r in self.records}

    def tags(self, sid):
        return dict(self.by_id[sid][3]) if sid in self.by_id else {}

    def set_tag(self, sid, key, value):
        tags = self.by_id[sid][3]
        for kv in tags:
            if kv[0] == key:
                kv[1] = value
                return
        tags.append([key, value])

    def bytes(self):
        tab = len(self.prefix)
        pos = tab + 36 * len(self.records)
        table, body = bytearray(), bytearray()
        for sid, misc, typ, tags in self.records:
            off = pos + len(body)
            strs, ptrs = bytearray(), []
            base = off + 8 * len(tags)
            for kv in tags:
                for s in kv:
                    ptrs.append(base + len(strs))
                    strs += s.encode('utf-8') + b'\0'
                    strs += bytes(-len(strs) % 4)
            body += struct.pack('>%dI' % len(ptrs), *ptrs) + strs
            table += struct.pack('>9I', sid, *misc, typ, len(tags), off)
        return bytes(self.prefix) + bytes(table) + bytes(body)

    def trax(self):
        """Песни EA Trax: {номер слота (Index): id звука}."""
        out = {}
        for sid, _, _, tags in self.records:
            t = dict(tags)
            if t.get('VolumeType') == 'MenuTunes' and 'Index' in t:
                out[int(t['Index'])] = sid
        return dict(sorted(out.items()))

# ---------------------------------------------------------------- банк

# вторые версии песен EA Trax (тег MenuTunes без названия): сверено по огибающей громкости
# (корреляция 0,85–0,97 против < 0,65 у ближайшей чужой песни) и по длительности
ALTERNATES = {104: 77, 113: 78, 114: 79, 116: 80, 117: 82, 212: 83, 105: 208, 112: 209,
              211: 217, 111: 218, 110: 219, 109: 220, 106: 221, 107: 222}


class Bank:
    """Банк в папке DIR/audio/music: оглавление .sbr, потоки .sbs, теги .bin."""
    def __init__(self, root):
        self.root = root
        d = os.path.join(root, *BANK)
        for name in (SBR, SBS, MBX):
            if not os.path.exists(os.path.join(d, name)):
                raise SystemExit(f'нет {os.path.join(d, name)} — сначала: python music.py unpack')
        self.sbs_path = os.path.join(d, SBS)
        self.sbr = bytearray(unchunked(open(os.path.join(d, SBR), 'rb').read()))
        self.mbx = MusicBox(unchunked(open(os.path.join(d, MBX), 'rb').read()))
        s = self.sbr
        if s[:4] != b'SBKR' or s[u32(s, 0x28):u32(s, 0x28) + 4] != b'SNS1':
            raise ValueError('music_samples.sbr: не SBKR/SNS1')
        n, tab = u32(s, 0x1C), u32(s, 0x24)
        self.slots = {}            # id → место в .sbr, где лежит смещение потока
        for i in range(n):
            sid, cnt, doff = struct.unpack_from('>IHI', s, tab + 10 * i)
            field, voff = struct.unpack_from('>HI', s, doff)
            if cnt != 1 or field != 0:
                raise ValueError(f'звук {sid}: неожиданное поле {cnt}/{field}')
            self.slots[sid] = voff
        with open(self.sbs_path, 'rb') as f:
            if f.read(4) != b'SBKS':
                raise ValueError('music_samples.sbs: не SBKS')

    def offset(self, sid):
        return u32(self.sbr, self.slots[sid])

    def ids(self):
        return sorted(self.slots)

    def read(self, sid):
        with open(self.sbs_path, 'rb') as f:
            return sps_read(f, self.offset(sid))

    def info(self, sid):
        with open(self.sbs_path, 'rb') as f:
            f.seek(self.offset(sid))
            codec, ch, rate, ns, _ = sps_header(f.read(16))
        return dict(codec=codec, ch=ch, rate=rate, samples=ns, sec=ns / rate)

    def save(self, out_root, streams):
        """Записать банк в out_root/audio/music: потоки streams {id: байты} вместо исходных."""
        d = os.path.join(out_root, *BANK)
        os.makedirs(d, exist_ok=True)
        sbs_out = os.path.join(d, SBS)
        if os.path.abspath(sbs_out) == os.path.abspath(self.sbs_path):
            raise SystemExit('папка вывода совпадает с исходной')
        order = sorted(self.slots, key=self.offset)        # порядок потоков как у EA
        sbr = bytearray(self.sbr)
        tmp = sbs_out + '.tmp'
        with open(self.sbs_path, 'rb') as src, open(tmp, 'wb') as o:
            o.write(b'SBKS' + bytes(12))
            pos = 16
            for sid in order:                            # каждый поток с границы 16, хвост без добивки
                raw = streams[sid] if sid in streams else sps_read(src, self.offset(sid))
                pad = -pos % 16
                o.write(bytes(pad))
                pos += pad
                struct.pack_into('>I', sbr, self.slots[sid], pos)
                o.write(raw)
                pos += len(raw)
        os.replace(tmp, sbs_out)
        open(os.path.join(d, SBR), 'wb').write(sbr)
        open(os.path.join(d, MBX), 'wb').write(self.mbx.bytes())
        return d

# ---------------------------------------------------------------- обложки EA Trax

# fe/ion/artassets/eatrax/e<AssetID>.big (сцена Apt 275×271, текстура 512×512 DXT5) и
# eatrax_thumbs/e<AssetID>_thumb.big (61×60 в 64×64) — те же BIGF+Apt+XPR2, что у фото
# игроков, поэтому собираются tools/playerhead.py по оригиналу как шаблону.
COVERS = (('eatrax', 'e{}.big'), ('eatrax_thumbs', 'e{}_thumb.big'))
IMAGE_EXT = ('.png', '.jpg', '.jpeg', '.webp', '.bmp')


def cover_source(folder, fn, explicit):
    """Картинка для обложки: поле 5 tracks.txt, иначе файл с тем же именем, иначе встроенная."""
    if explicit:
        p = os.path.join(folder, explicit)
        if not os.path.exists(p):
            raise SystemExit(f'нет обложки {p}')
        return p
    if fn:
        stem = os.path.splitext(os.path.join(folder, fn))[0]
        for ext in IMAGE_EXT:
            if os.path.exists(stem + ext):
                return stem + ext
        return os.path.join(folder, fn)          # попробовать картинку внутри MP3/FLAC
    return None


def cover_rgba(src, w, h):
    """Картинка (или обложка внутри звукового файла) → RGBA w×h через ffmpeg; None — нет картинки."""
    try:
        data = ffmpeg(['-i', src, '-map', '0:v:0', '-frames:v', '1',
                       '-vf', f'scale={w}:{h}:flags=lanczos,format=rgba',
                       '-f', 'rawvideo', '-pix_fmt', 'rgba', 'pipe:1'])
    except RuntimeError:
        return None
    return data if len(data) == w * h * 4 else None


def cover_template(sub, name):
    rel = ('fe', 'ion', 'artassets', sub, name)
    p = os.path.join(ROOT, 'game', 'extracted', 'big', 'cache', *rel)
    if os.path.exists(p):
        return p
    p = os.path.join(ORIG, *rel)
    if not os.path.exists(p):
        big_extract(os.path.join(ROOT, 'game', 'extracted', 'disc', 'cache.big'), {'/'.join(rel)}, ORIG)
    return p


def build_cover(asset, src, out_root):
    """Обложка и миниатюра для слота AssetID → OUT/fe/ion/artassets/…; False — картинки нет."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import playerhead
    made = []
    for sub, pattern in COVERS:
        name = pattern.format(asset)
        head = playerhead.PlayerHead.load(cover_template(sub, name))
        sw, sh = head.stage
        rgba = cover_rgba(src, sw, sh)
        if rgba is None:
            return False
        t = head.tex
        blocks = playerhead.dxt5_encode(playerhead.place(rgba, sw, sh, t.width, t.height), t.width, t.height)
        dst = os.path.join(out_root, 'fe', 'ion', 'artassets', sub, name)
        made.append((dst, head.with_blocks(blocks)))
    for dst, data in made:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, 'wb').write(data)
    return True

# ---------------------------------------------------------------- команды

AUDIO_EXT = ('.mp3', '.flac', '.wav', '.ogg', '.oga', '.opus', '.m4a', '.aac', '.wma', '.aiff', '.aif')
TRACKS = 'tracks.txt'
TRACKS_HEAD = """\
# NHL 13 — свой саундтрек (python tools/music.py build ПАПКА).
# Строка: слот = файл | исполнитель | название | альбом | обложка
#   trax0 … trax15 — песни EA Trax (меню; список: python tools/music.py list);
#   число или id105 — любой звук банка (list --all), названия у них не показываются;
#   категория (HomeGoal, AwayGoal, TeamIntroduction, OffPlayGeneric …) — все её звуки одним файлом.
# Файл — путь от этой папки; пусто — звук остаётся прежним (меняются только названия).
# Пустые поля названий — берутся теги файла, без тегов — имя файла.
# Обложка (только trax) — картинка; пусто — файл с тем же именем (.jpg/.png) или картинка
# внутри MP3/FLAC; нет ни того ни другого — остаётся старая обложка.
"""


def resolve(bank, target):
    """trax3 / id105 / 105 / HomeGoal → (список id, слот EA Trax или None)."""
    t = target.strip()
    m = re.fullmatch(r'(?i)trax(\d+)', t)
    if m:
        trax = bank.mbx.trax()
        k = int(m.group(1))
        if k not in trax:
            raise SystemExit(f'{t}: слота нет, есть trax0…trax{max(trax)}')
        return [trax[k]], k
    m = re.fullmatch(r'(?i)(?:id)?(\d+)', t)
    if m:
        sid = int(m.group(1))
        if sid not in bank.slots:
            raise SystemExit(f'{t}: такого звука в банке нет')
        return [sid], None
    ids = [r[0] for r in bank.mbx.records if dict(r[3]).get('VolumeType', '').lower() == t.lower()]
    if not ids:
        raise SystemExit(f'{t}: не слот, не id и не категория')
    return ids, None


def read_tracks(path):
    rows = []
    for n, line in enumerate(open(path, encoding='utf-8-sig'), 1):
        line = line.strip()
        if not line or line.startswith('#'):            # комментарии — только целой строкой
            continue
        if '=' not in line:
            raise SystemExit(f'{path}:{n}: нет «=»')
        target, rest = line.split('=', 1)
        f = [x.strip() for x in rest.split('|')] + [''] * 5
        rows.append((n, target.strip(), f[0], f[1], f[2], f[3], f[4]))
    return rows


def describe(bank, sid):
    t = bank.mbx.tags(sid)
    return t.get('VolumeType', '?'), t


def cmd_unpack(a):
    disc = a.disc or os.path.join(ROOT, 'game', 'extracted', 'disc')
    names = ['music_eventdef.csi', SBR, 'music_moduledef.xml', 'music_eventsubscr.bin',
             'music_graffitidata.bin', MBX, 'music_repetitionpools.bin']
    got = big_extract(os.path.join(disc, 'audioboot.big'), {'audio/music/' + x for x in names}, a.orig)
    print(f'audioboot.big: {len(got)} файлов')
    got = big_extract(os.path.join(disc, 'nocache.big'), {'audio/music/' + SBS}, a.orig)
    print(f'nocache.big: {SBS} ({os.path.getsize(got[0]):,} байт)' if got else 'nocache.big: потока нет!')
    print('→', os.path.join(a.orig, *BANK))


def cmd_list(a):
    bank = Bank(a.orig)
    trax = bank.mbx.trax()
    alt_of = {v: k for k, v in ALTERNATES.items()}
    print('EA Trax — песни меню (слот = Index; FirstBoot — по названию, песни первого запуска):')
    for k, sid in trax.items():
        t = bank.mbx.tags(sid)
        alt = f'  вторая версия: {ALTERNATES[sid]}' if sid in ALTERNATES else ''
        first = '  FirstBoot' if t.get('FirstBoot') == 'Yes' else ''
        print(f'  trax{k:<3} id {sid:<4} {bank.info(sid)["sec"]:6.1f} с  {t.get("Artist")} — '
              f'{t.get("Title")} ({t.get("Album")}){first}{alt}')
    if not a.all:
        print('Все звуки банка: list --all')
        return
    print('\nВсе звуки (id, категория VolumeType, длительность):')
    for sid in bank.ids():
        cat, t = describe(bank, sid)
        note = f'  = вторая версия id {alt_of[sid]}' if sid in alt_of else ''
        if 'Index' in t:
            note = f'  = trax{t["Index"]}'
        print(f'  {sid:<4} {cat:<24} {bank.info(sid)["sec"]:6.1f} с{note}')
    cats = {}
    for sid in bank.ids():
        cats.setdefault(describe(bank, sid)[0], []).append(sid)
    print('\nКатегории:', ', '.join(f'{c} ({len(v)})' for c, v in cats.items()))


def safe_name(s):
    return re.sub(r'[\\/:*?"<>|]+', '_', s).strip() or 'track'


def cmd_export(a):
    bank = Bank(a.orig)
    os.makedirs(a.out_dir, exist_ok=True)
    for what in a.what:
        ids, slot = resolve(bank, what)
        for sid in ids:
            t = bank.mbx.tags(sid)
            name = f'{sid}'
            if 'Index' in t:
                name = f'trax{t["Index"]}_{sid} {t.get("Artist", "")} - {t.get("Title", "")}'
            elif 'VolumeType' in t:
                name = f'{sid}_{t["VolumeType"]}'
            raw = bank.read(sid)
            if a.wav:
                pcm, ch, rate = stream_to_pcm(raw)
                path = os.path.join(a.out_dir, safe_name(name) + '.wav')
                open(path, 'wb').write(wav_bytes(pcm, ch, rate))
            else:
                path = os.path.join(a.out_dir, safe_name(name) + '.mp3')
                open(path, 'wb').write(granules_to_mp3(stream_decode_parts(raw)[0]))
            print(path)


def scan_audio(folder):
    return sorted(f for f in os.listdir(folder)
                  if f.lower().endswith(AUDIO_EXT) and os.path.isfile(os.path.join(folder, f)))


def names_from_file(path):
    """(исполнитель, название, альбом): теги файла, иначе имя «[01 - ]Исполнитель - Название»."""
    tags = ffprobe_tags(path)
    artist, title = tags.get('artist', ''), tags.get('title', '')
    if not title:
        stem = re.sub(r'^\d{1,3}\s*[-._)]\s*', '', os.path.splitext(os.path.basename(path))[0])
        a2, _, t2 = stem.partition(' - ')
        artist, title = (artist or a2.strip(), t2.strip()) if t2 else (artist, stem)
    return artist, title, tags.get('album', '')


def make_tracks(folder, bank):
    files = scan_audio(folder)
    trax = bank.mbx.trax()
    lines = [TRACKS_HEAD]
    if len(files) > len(trax):
        lines.append(f'# файлов {len(files)}, слотов {len(trax)}: лишние ниже закомментированы\n')
    for i, fn in enumerate(files):
        artist, title, album = names_from_file(os.path.join(folder, fn))
        row = f'trax{i} = {fn} | {artist} | {title} | {album}'
        lines.append(row if i < len(trax) else '# ' + row)
    lines.append('')
    for k, sid in trax.items():
        if k >= len(files):
            t = bank.mbx.tags(sid)
            lines.append(f'# trax{k} = | {t.get("Artist")} | {t.get("Title")} | {t.get("Album")}   (оригинал)')
    return '\n'.join(lines) + '\n', len(files)


def cmd_init(a):
    bank = Bank(a.orig)
    path = os.path.join(a.tracks_dir, TRACKS)
    if os.path.exists(path) and not a.force:
        raise SystemExit(f'{path} уже есть (--force — перезаписать)')
    text, n = make_tracks(a.tracks_dir, bank)
    open(path, 'w', encoding='utf-8', newline='\n').write(text)
    print(f'{path}: {n} файлов; поправьте слоты/названия и запустите build')


def cmd_build(a):
    bank = Bank(a.orig)
    tracks = os.path.join(a.tracks_dir, TRACKS)
    if not os.path.exists(tracks):
        text, n = make_tracks(a.tracks_dir, bank)
        if not n:
            raise SystemExit(f'в {a.tracks_dir} нет звуковых файлов')
        open(tracks, 'w', encoding='utf-8', newline='\n').write(text)
        print(f'{tracks}: создан по файлам папки ({n})')
    for sub, pattern in COVERS:                      # старые обложки прошлой сборки
        d = os.path.join(a.out, 'fe', 'ion', 'artassets', sub)
        if os.path.isdir(d):
            for name in os.listdir(d):
                if re.fullmatch(pattern.format(r'\d+').replace('.', r'\.'), name):
                    os.remove(os.path.join(d, name))
    streams, cache, report, covers = {}, {}, [], 0
    for n, target, fn, artist, title, album, cover in read_tracks(tracks):
        ids, slot = resolve(bank, target)
        if fn:
            src = os.path.join(a.tracks_dir, fn)
            if not os.path.exists(src):
                raise SystemExit(f'{tracks}:{n}: нет файла {src}')
            if src not in cache:
                raw, how = encode_track(src, a.quality, a.bitrate, a.copy, a.volume)
                sec = sps_header(raw)[3] / 44100
                cache[src] = raw
                print(f'  {fn}: {sec:.1f} с, {len(raw) / 1048576:.1f} МБ ({how})')
            targets = list(ids)
            if slot is not None and not a.no_alt and ids[0] in ALTERNATES:
                targets.append(ALTERNATES[ids[0]])
            for sid in targets:
                streams[sid] = cache[src]
        if slot is not None:
            sid = ids[0]
            if fn:      # новая песня: пустое поле — из тегов/имени файла, нет и там — пусто
                fa, ft, fal = names_from_file(os.path.join(a.tracks_dir, fn))
                new = {'Artist': artist or fa, 'Title': title or ft, 'Album': album or fal}
            else:       # только переименование: пустое поле — прежнее значение
                new = {k: v for k, v in (('Artist', artist), ('Title', title), ('Album', album)) if v}
            for key, val in new.items():
                if any(ord(c) > 0x7E for c in val):
                    print(f'  внимание: trax{slot} {key} «{val}» — не латиница, шрифт меню может не показать')
                bank.mbx.set_tag(sid, key, val)
            t = bank.mbx.tags(sid)
            if t.get('Title') in ('Grace', 'Turn Your Back'):
                print(f'  внимание: у названия «{t["Title"]}» игра подменяет исполнителя (зашито в код)')
            line = f'trax{slot} (id {sid}): {t.get("Artist")} — {t.get("Title")}' + ('' if fn else ' [звук прежний]')
            if not a.no_covers and (fn or cover):
                src_img = cover_source(a.tracks_dir, fn, cover)
                if src_img and build_cover(t.get('AssetID', str(slot)), src_img, a.out):
                    covers += 1
                    line += f' + обложка ({os.path.basename(src_img)})'
                else:
                    line += ' [обложка старая: картинки нет]'
            report.append(line)
        elif artist or title or album or cover:
            print(f'  {tracks}:{n}: у {target} названий и обложек нет — поля пропущены')
        if slot is None and fn:
            report.append(f'{target}: id {", ".join(map(str, ids))}')
    d = bank.save(a.out, streams)
    print('\n'.join(report))
    print(f'заменено потоков: {len(streams)}, обложек: {covers}; банк → {d}')
    print(f'поставить (игра закрыта): содержимое {a.out} (audio\\music, fe\\ion\\artassets\\eatrax*) '
          '→ game\\userdata\\cache\\guest; убрать — удалить эти файлы оттуда')


def cmd_check(a):
    bank = Bank(a.dir)
    d = os.path.join(a.dir, *BANK)
    mbx_raw = unchunked(open(os.path.join(d, MBX), 'rb').read())
    print('MBX: пересборка без правок совпадает' if bank.mbx.bytes() == mbx_raw else
          'MBX: пересборка ОТЛИЧАЕТСЯ — формат понят не до конца')
    bad, total, size = 0, 0, os.path.getsize(bank.sbs_path)
    ends = []
    with open(bank.sbs_path, 'rb') as f:
        for sid in bank.ids():
            off = bank.offset(sid)
            try:
                raw = sps_read(f, off)
                codec, ch, rate, ns, _ = sps_header(raw)
                blocks = sps_blocks(raw)
                if sum(s for s, _ in blocks) != ns:
                    raise ValueError(f'сумма сэмплов блоков {sum(s for s, _ in blocks)} ≠ {ns}')
                if a.deep:
                    for samples, payload in blocks:
                        g, _ = eal3_parse(payload)
                        if samples > len(g) * GRANULE:
                            raise ValueError('в блоке меньше гранул, чем сэмплов')
                ends.append((off, off + len(raw)))
            except Exception as e:
                bad += 1
                print(f'  {sid}: {e}')
            total += 1
    ends.sort()
    overlap = sum(1 for (a0, a1), (b0, b1) in zip(ends, ends[1:]) if b0 < a1)
    print(f'звуков {total}, битых {bad}, пересечений {overlap}, .sbs {size:,} байт'
          + (' (кадры EALayer3 разобраны)' if a.deep else ''))
    for what in a.decode or []:
        for sid in resolve(bank, what)[0]:
            pcm, ch, rate = stream_to_pcm(bank.read(sid))
            n = len(pcm) // (2 * ch)
            vals = struct.unpack('<%dh' % (len(pcm) // 2), pcm)
            rms = (sum(v * v for v in vals[::97]) / max(1, len(vals[::97]))) ** 0.5
            print(f'  {sid}: ffmpeg декодировал {n} сэмплов ({n / rate:.1f} с), RMS {rms:.0f}')
    sys.exit(1 if bad or overlap else 0)


def main():
    p = argparse.ArgumentParser(description='Музыка NHL 13: банк audio/music и песни EA Trax')
    sub = p.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('unpack', help='достать банк из архивов диска')
    s.add_argument('--disc', help='папка с audioboot.big и nocache.big (game/extracted/disc)')
    s.add_argument('--orig', default=ORIG)
    s.set_defaults(fn=cmd_unpack)
    s = sub.add_parser('list', help='песни EA Trax и звуки банка')
    s.add_argument('--orig', default=ORIG)
    s.add_argument('--all', action='store_true')
    s.set_defaults(fn=cmd_list)
    s = sub.add_parser('export', help='звук → .mp3 (без потерь) или .wav')
    s.add_argument('what', nargs='+')
    s.add_argument('out_dir')
    s.add_argument('--orig', default=ORIG)
    s.add_argument('--wav', action='store_true')
    s.set_defaults(fn=cmd_export)
    s = sub.add_parser('init', help='tracks.txt для папки с песнями')
    s.add_argument('tracks_dir')
    s.add_argument('--orig', default=ORIG)
    s.add_argument('--force', action='store_true')
    s.set_defaults(fn=cmd_init)
    s = sub.add_parser('build', help='собрать банк со своими песнями')
    s.add_argument('tracks_dir')
    s.add_argument('out', nargs='?', default=OUT)
    s.add_argument('--orig', default=ORIG)
    s.add_argument('--no-alt', action='store_true', help='не трогать вторые версии песен EA Trax')
    s.add_argument('--copy', action='store_true', help='MP3 44,1 кГц стерео — без перекодирования')
    s.add_argument('--quality', type=int, default=2, help='LAME VBR -V (0 лучше … 9), по умолчанию 2')
    s.add_argument('--bitrate', type=int, help='LAME CBR, кбит/с (вместо VBR)')
    s.add_argument('--volume', type=float, help='усиление, дБ (например -3)')
    s.add_argument('--no-covers', action='store_true', help='не делать обложки EA Trax')
    s.set_defaults(fn=cmd_build)
    s = sub.add_parser('check', help='проверить банк в папке (раскладка cache:)')
    s.add_argument('dir', nargs='?', default=OUT)
    s.add_argument('--deep', action='store_true', help='разобрать все кадры EALayer3')
    s.add_argument('--decode', nargs='*', help='декодировать звуки через ffmpeg')
    s.set_defaults(fn=cmd_check)
    a = p.parse_args()
    a.fn(a)


if __name__ == '__main__':
    main()
