"""Монеты NHL Legacy («P 2,500 · REDEEM COINS» на главном меню): блок PUCK_REWARD_CHUNK сейва профиля.

    python tools/legacy_coins.py show FILE [FILE …]                        # баланс, потолок, таблица начисления
    python tools/legacy_coins.py set FILE --max 2000000000 [--earned N] [--write]    # без --write — прогон

FILE — внутренний файл сейва PROFILE из userdata порта
(userdata/B13EBABEBABEBABE/454109EC/00000001/PROFILE <дата>/PROFILE <дата>). Разбор: docs/coins.md.

Почему счётчик стоит на 2500. EA копила монеты за матчи офлайн, чтобы потом перевести их на счёт Hockey Ultimate
Team на своём сервере и обнулить. Потолок — поле +4 этого блока (умолчание 2500 в образе, 0x820504A8; ключ сервера
EOGB_MATCH_BONUS_MAX_BONUS). Сервера нет, перевести нельзя, значит баланс упирается в потолок навсегда. Блок целиком
пишется в сейв и целиком читается обратно, поэтому у уже созданного профиля потолок живёт в сейве: поменять его
можно здесь, сборка exe для этого не нужна.

Блок 33, 1524 байта, big-endian (конструктор 82957730):

| Смещение | Что |
|---|---|
| +0x00 | u32 баланс (GetEarnedPuckRewards) |
| +0x04 | u32 потолок (HasUserEarnedMaximumPuckRewards; ActionScript его не вызывает) |
| +0x08 | 12 пар u32 (за единицу, предел статьи): 8 плюсов и 4 минуса, см. STATS |
| +0x68 | 4 float, множители сложности Rookie / Pro / All-Star / Superstar |
| +0x78 | u32 монеты за рекламу (GetEarnedAdPuckRewards) |
| +0x7C | 50 записей по 28 байт: рекламные награды 2013–2015 |

`show` печатает ещё счётчик доигранных матчей: блок 7, +0xE2C, 4 u32 по уровням сложности (82943768 прибавляет 1 в конце
матча, 829A7328, онлайн не считается). Потолка у него нет, это честное число матчей профиля.

Запись правит только поля +0 и +4, сумму блока (CRC-32/BZIP2) и обёртку сейва. До записи проверяется:
- суммы файла сходятся, пересборка без правок даёт тот же файл;
- новый файл отличается от старого только суммой 0x10, суммой блока и этими двумя полями.
С --write: игра nhllegacy.exe не должна быть запущена, копия файла до правки — в game/work/legacy-data/backup-saves/
(`--backup-dir`), после записи файл разбирается заново; при ошибке он возвращается из копии.
"""
import argparse, datetime, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from legacy_settings import BACKUP_DIR, bad_chunks, chunks, game_running, tail_start
from tdb import SaveFile, crc32_bzip2

CHUNK = 33            # номер блока: 8298FA48 в сборке группы сейва профиля 8298EC10
SIZE = 1524           # 0x7C + 50 × 28
EARNED, CAP, TABLE, MULT, AD, AWARDS = 0x00, 0x04, 0x08, 0x68, 0x78, 0x7C
MAX_FIELD = 0x7FFFFFFF  # игра сравнивает без знака, но ActionScript считает числа со знаком
# Порядок — ключи EOGB_MATCH_BONUS_POSITIVE_0…7 и NEGATIVE_0…3 (829FDBD0, 829FDCD8), смысл — разделы твиков
# FE/EndOfGameBonus/…. Счёт берётся по команде игрока, не по его хоккеисту (82F71838…82F71DC8).
STATS = ['+ матч сыгран', '+ голы', '+ броски в створ', '+ силовые', '+ вбрасывания', '+ время в атаке',
         '+ большинство %', '+ точность паса %', '− пропущенные', '− штрафные минуты', '− проброс', '− офсайд']
SKILL = ['Rookie', 'Pro', 'All-Star', 'Superstar']
CHUNK_PROFILE, GAMES = 7, 0xE2C  # блок 7: доигранные матчи по сложности


def block(path):
    """(байты файла, блок 33) или выход с понятной ошибкой."""
    if not os.path.isfile(path):
        sys.exit(f'{path}: файла нет')
    data = open(path, 'rb').read()
    if data[:16] != b'UserProfileFile\0':
        sys.exit(f'{path}: не сейв профиля (нужен внутренний файл PROFILE, не папка и не DYNASTY/ROSTER)')
    c = chunks(data)
    if CHUNK not in c or len(c[CHUNK][3]) != SIZE:
        sys.exit(f'{path}: блока {CHUNK} на {SIZE} байт нет — другой формат сейва?')
    return data, c[CHUNK][3]


def u32(b, o):
    return struct.unpack_from('>I', b, o)[0]


def show(path):
    data, b = block(path)
    print(path.replace('\\', '/').split('/')[-1])
    print(f'  баланс {u32(b, EARNED)}, потолок {u32(b, CAP)}, за рекламу {u32(b, AD)}')
    c = chunks(data)
    if CHUNK_PROFILE in c and len(c[CHUNK_PROFILE][3]) >= GAMES + 16:
        games = struct.unpack_from('>4I', c[CHUNK_PROFILE][3], GAMES)
        print(f'  доиграно матчей: {sum(games)} (' + ', '.join(f'{n} {g}' for n, g in zip(SKILL, games)) + ')')
    print('  статья               за единицу  предел')
    for i, name in enumerate(STATS):
        v, cap = struct.unpack_from('>II', b, TABLE + 8 * i)
        print(f'  {name:20} {v:10} {cap:7}')
    print('  сложность: ' + ', '.join(f'{n} ×{m:.1f}' for n, m in zip(SKILL, struct.unpack_from('>4f', b, MULT))))


def with_fields(data, earned, cap):
    """Новые байты сейва: поля блока 33, его сумма и обёртка пересчитаны."""
    o, ver, h, blk = chunks(data)[CHUNK]
    new = bytearray(blk)
    if earned is not None:
        struct.pack_into('>I', new, EARNED, earned)
    if cap is not None:
        struct.pack_into('>I', new, CAP, cap)
    ts = tail_start(data)
    tail = bytearray(data[ts:])
    rel = o - ts
    tail[rel + 12:rel + 16] = struct.pack('>I', crc32_bzip2(bytes(new)))
    tail[rel + 16:rel + 16 + SIZE] = new
    sf = SaveFile(data, {})
    if sf.zlib is not None:
        sf.zlib.tail = bytes(tail)
    sf.tail = bytes(tail)
    return sf.bytes()


def check(old, new, earned, cap):
    """Ошибки нового файла: суммы, поля, изменения вне полей и сумм."""
    err = SaveFile(new, {}).verify() + [f'блок {cid}: сумма не сходится' for cid in bad_chunks(new)]
    if len(new) != len(old):
        return err + [f'длина {len(new)} вместо {len(old)}']
    o = chunks(old)[CHUNK][0]
    c = chunks(new)
    if c[CHUNK][0] != o:
        return err + [f'блок {CHUNK} не на прежнем месте']
    b = c[CHUNK][3]
    if earned is not None and u32(b, EARNED) != earned:
        err.append('баланс не записался')
    if cap is not None and u32(b, CAP) != cap:
        err.append('потолок не записался')
    allowed = set(range(0x10, 0x14)) | set(range(o + 12, o + 16)) | set(range(o + 16, o + 24))
    outside = [i for i in range(len(new)) if new[i] != old[i] and i not in allowed]
    if outside:
        err.append(f'изменились байты вне полей и сумм: {[hex(i) for i in outside[:8]]}')
    return err


def set_fields(a):
    if a.max is None and a.earned is None:
        sys.exit('set: укажи --max и/или --earned')
    for name, v in (('--max', a.max), ('--earned', a.earned)):
        if v is not None and not 0 <= v <= MAX_FIELD:
            sys.exit(f'{name}: 0…{MAX_FIELD}')
    path = a.files[0]
    old, b = block(path)
    pre = SaveFile(old, {}).verify() + [f'блок {cid}: сумма не сходится' for cid in bad_chunks(old)]
    if pre:
        sys.exit(f'{path}: суммы не сходятся до правки — не трогаю:\n  ' + '\n  '.join(pre))
    if SaveFile(old, {}).bytes() != old:
        sys.exit(f'{path}: пересборка без правок не даёт исходный файл — не трогаю')
    new = with_fields(old, a.earned, a.max)
    err = check(old, new, a.earned, a.max)
    if err:
        sys.exit('проверка нового файла не прошла:\n  ' + '\n  '.join(err))
    nb = chunks(new)[CHUNK][3]
    print(f'баланс {u32(b, EARNED)} → {u32(nb, EARNED)}, потолок {u32(b, CAP)} → {u32(nb, CAP)}')
    print('проверка: все суммы сходятся, вне полей и сумм байты те же')
    if u32(nb, EARNED) > u32(nb, CAP):
        print('внимание: баланс больше потолка — первый же матч вернёт его к потолку (829F7368), подними и --max')
    if new == old:
        print('менять нечего')
        return
    if not a.write:
        print('прогон без --write: файл не записан')
        return
    if game_running():
        sys.exit('nhllegacy.exe запущен — не пишу (закрой игру: она перезапишет профиль при сохранении)')
    os.makedirs(a.backup_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = os.path.join(a.backup_dir, f'{os.path.basename(path)}.{stamp}')
    shutil.copy2(path, backup)
    if open(backup, 'rb').read() != old:
        sys.exit(f'копия {backup} не совпала с исходным — не пишу')
    print(f'копия до правки: {backup}')
    try:
        with open(path, 'wb') as f:
            f.write(new)
        back = open(path, 'rb').read()
        err = ([] if back == new else ['записанный файл не равен подготовленному']) + check(old, back, a.earned, a.max)
    except OSError as e:
        err = [f'запись: {e}']
    if err:
        shutil.copy2(backup, path)
        ok = open(path, 'rb').read() == old
        sys.exit('после записи проверка не прошла, файл возвращён из копии'
                 + ('' if ok else ' — НО НЕ СОВПАЛ С ИСХОДНЫМ, верни вручную') + ':\n  ' + '\n  '.join(err))
    print(f'записано: {path}')


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('cmd', choices=['show', 'set'])
    ap.add_argument('files', nargs='+')
    ap.add_argument('--max', type=int, help='set: новый потолок; 2000000000 — фактически без потолка')
    ap.add_argument('--earned', type=int, help='set: новый баланс')
    ap.add_argument('--write', action='store_true', help='set: записать (без него — только прогон)')
    ap.add_argument('--backup-dir', default=BACKUP_DIR, help='set: куда копия файла до правки')
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    if a.cmd == 'set':
        if len(a.files) != 1:
            ap.error('set: один файл')
        set_fields(a)
        return
    for f in a.files:
        show(f)


if __name__ == '__main__':
    main()
