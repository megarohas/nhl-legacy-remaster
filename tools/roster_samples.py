"""Образцы файлов ROSTER для проверки лаунчера и игры: хороший с меткой и испорченные на разные лады.

    python tools/roster_samples.py make  OUT ROSTER [--dynasty FILE] [--profile FILE] [--old FILE]
    python tools/roster_samples.py check OUT LAUNCHER.exe        # --check-roster по всем образцам: код против ожидаемого
    python tools/roster_samples.py plant SAMPLE USERDATA [--name ROSTER_ИМЯ]   # положить образец в сейвы мимо лаунчера

make пишет в OUT (папка проекта, не %TEMP%) файлы:
    good_marked       тот же ростер, у Crosby фамилия IMPORTED: видно в составе, что загружен именно он
    bad_random        случайные байты той же длины
    bad_truncated     первая половина файла
    bad_byte          испорчен байт сжатых данных, суммы файла старые
    bad_stream        испорчен байт сжатых данных, суммы файла пересчитаны (zlib или его сумма не сходятся)
    bad_db_sum        байт базы изменён, база упакована заново, суммы файла верны, сумма таблицы — нет
    bad_max_kits      у stockteamjerseys другое число мест, все суммы верны
    bad_max_swap      места двух таблиц изменены так, что размер файла прежний, все суммы верны
    bad_fields        у двух полей таблицы обменяны места, все суммы верны
    dynasty, profile, old   копии --dynasty, --profile, --old
Ожидаемые коды --check-roster — в EXPECT (nhl-legacy-port/launcher/roster_import.h, roster::Code).

plant нужен только для проверки реакции игры на файл, который лаунчер не пропустил бы: пишет папку и заголовок сейва с
именем новее всех. Работает лишь с копией: папку nhl-legacy-port/userdata не принимает. Подробности — docs/launcher.md.
"""
import argparse, datetime, os, random, re, shutil, struct, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gameprofile
from tdb import SaveFile, crc32_bzip2, crc32_ieee
from tdb_read import load_meta

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_USERDATA = os.path.normcase(os.path.join(REPO, 'nhl-legacy-port', 'userdata'))
REAL_SAVES = os.path.normcase(os.path.join(REPO, 'nhl-legacy-port', 'out', 'build', 'win-amd64-release', 'saves'))
XUID, TITLE = 'B13EBABEBABEBABE', '454109EC'
JERSEYS, VISORS = 'stockteamjerseys', 'stockplayervisorexempttable'
MARKED = 'Crosby'

EXPECT = {
    'good_marked': 0, 'bad_random': 3, 'bad_truncated': 5, 'bad_byte': 5, 'bad_stream': 5, 'bad_db_sum': 5,
    'bad_max_kits': 6, 'bad_max_swap': 6, 'bad_fields': 6, 'dynasty': 4, 'profile': 4, 'old': 6,
}


def rewrap(data):
    """Пересчитать обе суммы файла ZlibV4 (0x28 по области, 0x10 по [0x1C..конец])."""
    out = bytearray(data)
    region = struct.unpack('>I', out[0x24:0x28])[0]
    out[0x28:0x2C] = struct.pack('>I', crc32_bzip2(out[0x2C:0x2C + region]))
    out[0x10:0x14] = struct.pack('>I', crc32_ieee(out[0x1C:]))
    return bytes(out)


def set_room(sv, table, want):
    """Мест в таблице want, записи целы, [current, max) — 0xDB, как пишет игра (nhl24.py kit_room)."""
    maxr, cur = sv.counts(table)[:2]
    if want < cur:
        raise ValueError(f'{table}: {want} мест меньше {cur} записей')
    sv.resize(table, want)
    t = sv.by_name[table]
    sv.d[t['block'] + 0x14:t['block'] + 0x18] = struct.pack(sv.E + 'HH', want, cur)
    sv.d[t['records'] + t['reclen'] * cur:t['records'] + t['reclen'] * want] = b'\xDB' * (t['reclen'] * (want - cur))
    sv.__init__(bytes(sv.d), sv.meta)


def cmd_make(a):
    os.makedirs(a.out, exist_ok=True)
    meta = load_meta(gameprofile.get('legacy').meta)
    src = open(a.roster, 'rb').read()
    put = lambda name, data: open(os.path.join(a.out, name), 'wb').write(data)      # noqa: E731
    fresh = lambda: SaveFile(src, meta)                                              # noqa: E731
    rng = random.Random(13)

    sv = fresh()
    bio = 'exhibitionplayerbiotable'
    row = next((r for r in sv.db.live_rows(bio) if sv.db.get_string(bio, 'lastname', r) == MARKED), None)
    if row is None:
        sys.exit(f'в ростере нет игрока {MARKED}')
    sv.db.set_string(bio, 'lastname', row, 'IMPORTED')
    put('good_marked', sv.bytes())

    put('bad_random', rng.randbytes(len(src)))
    put('bad_truncated', src[:len(src) // 2])

    bad = bytearray(src)
    bad[0x30 + 5000] ^= 0x40
    put('bad_byte', bytes(bad))
    put('bad_stream', rewrap(bad))

    sv = fresh()
    t = sv.db.by_name['exhibitionteams']
    sv.db.fix()
    sv.db.d[t['records'] + 40] ^= 1                    # после пересчёта сумм базы: они больше не сходятся
    put('bad_db_sum', sv.bytes(fix=False))

    sv = fresh()
    set_room(sv.db, JERSEYS, sv.db.counts(JERSEYS)[0] + 100)
    put('bad_max_kits', sv.bytes())

    sv = fresh()                                       # 8 байт на запись формы, 4 — на запись визора
    set_room(sv.db, JERSEYS, sv.db.counts(JERSEYS)[0] + 8)
    set_room(sv.db, VISORS, sv.db.counts(VISORS)[0] - 16)
    data = sv.bytes()
    if len(data) != len(src):
        sys.exit('bad_max_swap: размер файла изменился')
    put('bad_max_swap', data)

    sv = fresh()
    t = sv.db.by_name['stockteamjerseys']
    fields = sv.db.d[t['block'] + 0x28:t['records']]
    pairs = [fields[i:i + 16] for i in range(0, len(fields), 16)]
    a_i, b_i = next((i, j) for i in range(len(pairs)) for j in range(i + 1, len(pairs))
                    if pairs[i][12:] == pairs[j][12:] and pairs[i][4:8] != pairs[j][4:8])
    one, two = bytearray(pairs[a_i]), bytearray(pairs[b_i])
    one[4:8], two[4:8] = pairs[b_i][4:8], pairs[a_i][4:8]
    at = t['block'] + 0x28
    sv.db.d[at + 16 * a_i:at + 16 * a_i + 16] = one
    sv.db.d[at + 16 * b_i:at + 16 * b_i + 16] = two
    put('bad_fields', sv.bytes())

    for name, path in (('dynasty', a.dynasty), ('profile', a.profile), ('old', a.old)):
        if path:
            shutil.copyfile(path, os.path.join(a.out, name))
    print('готово:', a.out)


def cmd_check(a):
    bad = 0
    for name in sorted(os.listdir(a.out)):
        if name not in EXPECT:
            continue
        p = subprocess.run([os.path.abspath(a.launcher), '--check-roster', os.path.join(a.out, name)],
                           capture_output=True, timeout=60)
        text = p.stdout.decode('utf-8', 'replace').strip()
        ok = p.returncode == EXPECT[name]
        bad += not ok
        print(f"{'ок ' if ok else 'НЕ ТО'} {name:15s} код {p.returncode} (ждали {EXPECT[name]}): {text[:110]}")
    sys.exit(1 if bad else 0)


def header(folder):
    h = bytearray(0x148)
    h[0:8] = struct.pack('>II', 1, 1)
    name = 'ROSTER1'.encode('utf-16-be')
    h[8:8 + len(name)] = name
    raw = folder.encode('ascii')
    h[0x108:0x108 + len(raw)] = raw
    h[0x138:0x140] = bytes.fromhex(XUID)
    h[0x140:0x144] = bytes.fromhex(TITLE)
    return bytes(h)


def cmd_plant(a):
    ud = os.path.abspath(a.userdata)
    if os.path.normcase(ud) == REAL_USERDATA:
        sys.exit('это настоящие сейвы пользователя: образцы — только в копию')
    from legacy_saves import Saves
    place = Saves.of_userdata(ud)
    if place.saves_root and os.path.normcase(os.path.abspath(place.saves_root)) == REAL_SAVES:
        sys.exit('это настоящие сейвы пользователя: образцы — только в копию')
    names = [r.name for r in place.list('ROSTER') if re.fullmatch(r'ROSTER \d{14}A?', r.name)]
    if a.name:
        folder = a.name
    else:
        newest = max((n[7:21] for n in names), default='20000101000000')
        t = datetime.datetime.strptime(newest, '%Y%m%d%H%M%S') + datetime.timedelta(seconds=1)
        folder = 'ROSTER ' + t.strftime('%Y%m%d%H%M%S')
    if not os.path.isfile(a.sample):
        sys.exit(f'нет файла {a.sample}')
    save_dir, header_path = place.place_for(folder)   # saves\\rosters (0.17.0+) или userdata\\<xuid>\\…\\00000001
    os.makedirs(save_dir)
    shutil.copyfile(a.sample, os.path.join(save_dir, folder))
    os.makedirs(os.path.dirname(header_path), exist_ok=True)
    open(header_path, 'wb').write(header(folder))
    print(folder)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest='cmd', required=True)
    m = s.add_parser('make')
    m.add_argument('out')
    m.add_argument('roster')
    m.add_argument('--dynasty')
    m.add_argument('--profile')
    m.add_argument('--old')
    m.set_defaults(fn=cmd_make)
    c = s.add_parser('check')
    c.add_argument('out')
    c.add_argument('launcher')
    c.set_defaults(fn=cmd_check)
    q = s.add_parser('plant')
    q.add_argument('sample')
    q.add_argument('userdata')
    q.add_argument('--name')
    q.set_defaults(fn=cmd_plant)
    a = p.parse_args()
    a.fn(a)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main()
