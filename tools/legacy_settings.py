"""Настройки игры в сейвах NHL Legacy: блок SETTINGS_MGR_CHUNK (номер 2, 656 байт) — разбор и сравнение.

    python tools/legacy_settings.py show FILE [--raw]       # все поля блока настроек сейва
    python tools/legacy_settings.py diff A B [C …]          # поля, где сейвы расходятся (A — как эталон)
    python tools/legacy_settings.py copy-sliders SRC DST [--sets 3,4] [--write]
                                                           # наборы слайдеров SRC → DST (без --write — прогон)

FILE — внутренний файл сейва Legacy из userdata порта: PROFILE (UserProfileFile), DYNASTY, BEAPRO, SEASON,
PLAYOFF, TOURNAMENT. show и diff только читают. Разбор — docs/legacy-port.md, «Настройки по умолчанию для новых
карьер».

Хвост сейва (после базы: 0x2C + u32@0x24) — цепочка блоков: u32 номер, u32 версия (1), u32 размер, u32 сумма,
данные (все поля big-endian). Сумма — CRC-32/BZIP2 по данным блока, так проверяет игра: 82BBA660 обходит блоки и
сравнивает сумму с 82BB6A90 / 826575C0 (CRC MSB-first, начало FFFFFFFF, в конце NOT); при неверной сумме сейв не
читается. Сверено на всех 880 блоках сейвов userdata порта. Блок 2 — копия настроек менеджера настроек игры (объект *(0x83BD3074), конструктор
829F4158): в профиле — общие настройки, в сейве карьеры — настройки этой карьеры. Раскладка 656 байт:

| Смещение | Что | ID настройки |
|---|---|---|
| 0x000…0x02D | 46 общих: камеры, визуальные, громкости (×10 %) | 105 + i |
| 0x02E…0x0B2 | правила: 7 копий по 19 байт (k = 0 правится и копируется во все) | 9 + j |
| 0x0B3…0x233 | слайдеры: 5 наборов по 77 байт; набор матча — GameStylePreset (правила, j = 15) | 28 + j |
| 0x234…0x28F | 7 байт, которые загрузка не трогает, и 20 float — не разбирались | — |

ID — номер настройки игры (таблица описаний меню 82050FB0: имя, тип, диапазон, значение по умолчанию). Имена
слайдеров — из таблицы меню и твиков `gTweakByGameStyle*` (829F8A20 берёт из них наборы 0…2), правил — из
«ruledefaults» (829FC060). Наборы слайдеров 0…2 — заводские Arcade / Hybrid / Simulation, 3 и 4 — свои.

copy-sliders: в блоке 2 сейва DST наборы слайдеров (по 77 байт) заменяются наборами из SRC. Общие и правила
остаются, сумма блока пересчитывается. Обёртку сейва пересобирает tools/tdb.py (SaveFile: суммы 0x10 / 0x28; у
ZlibV4 база не меняется, область и поток — как были). До записи проверяется:
- суммы DST сходятся, пересборка без правок даёт тот же файл;
- новый файл отличается от старого только суммой 0x10, суммой и наборами блока 2.
С --write:
- игра nhllegacy.exe не должна быть запущена;
- копия DST до правки — в game/work/legacy-data/backup-saves/ (`--backup-dir`);
- запись, затем повторный разбор: наборы = SRC, остальные поля как были, все суммы сходятся; иначе файл
  возвращается из копии.
"""
import argparse, datetime, os, shutil, struct, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tdb import SaveFile, crc32_bzip2

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKUP_DIR = os.path.join(REPO, 'game', 'work', 'legacy-data', 'backup-saves')

CHUNK_SETTINGS = 2
SIZE = 656
HEAD, RULES, SLIDERS, REST = 0x000, 0x02E, 0x0B3, 0x234
RULES_N, RULES_LEN = 7, 19
SETS_N, SET_LEN = 5, 77

# ID 105…150 — общие (голова блока). '?' — в таблице меню без имени.
GENERAL = {
    105: 'Camera', 106: 'ShootoutCamera', 107: 'GoalieCamera', 108: 'BapCamera', 109: 'BapEnergyMeter',
    110: 'AutoZoom', 111: '?111', 112: 'ControlIndicator', 113: '?113', 114: 'CameraPerspective',
    115: 'ScoreClockOverlay', 116: '?116', 117: '?117', 118: 'PuckSize', 119: 'PuckShadow', 120: '?120',
    121: '?121', 122: '?122', 123: '?123', 124: 'ArenaMusicVolume', 125: 'MenuMusicVolume', 126: 'SFXVolume',
    127: 'CrowdVolume', 128: 'CommentaryVolume', 129: 'RinkSpeechVolume', 130: 'GoalHornVolume', 131: '?131',
    132: 'ShotAimingTargets', 133: '?133 (яркость?)', 134: 'Brightness', 135: 'Contrast', 136: 'ScreenAngle',
    137: 'AutoSave', 138: '?138', 139: 'OnlinePlayerIndicators', 140: 'ControllerVisualization',
    141: 'PlayVisualization', 142: 'PositionalIndicators', 143: 'CustomCamera', 144: 'PuckTrails',
    145: 'GoalieMode', 146: 'FightingOverlays', 147: 'OnlineSkaterCamera', 148: 'OnlineGoalieCamera',
    149: 'OnlinePositionIndicator', 150: 'ForecheckVisualGuide',
}
VOLUMES = range(124, 131)

# ID 9…27 — правила (имена ruledefaults и таблицы меню).
RULES_NAMES = {
    9: 'SkillLevel', 10: 'Penalties', 11: 'Fighting', 12: 'Offsides', 13: 'Icing', 14: 'TwoLineOffside',
    15: 'Injuries', 16: 'RefereeType', 17: 'RinkType', 18: 'TieBreak', 19: 'MinorPenalty', 20: '?20',
    21: 'GoldenHelmet', 22: 'CreatedPlays', 23: 'BapBehaviour', 24: 'GameStylePreset', 25: 'TuningVersion',
    26: 'DynamicRatings', 27: 'PeriodLength',
}
GAME_STYLE_PRESET = 24

# ID 28…104 — слайдеры (CPU — половина пары «человек / CPU»).
SLIDERS_NAMES = {
    28: 'GameSpeed', 29: 'PuckControl', 30: 'FatigueEffect', 31: 'InjuryOccurrence', 32: '?32 (CPU)',
    33: 'FightDifficulty', 34: 'SpeedBurst', 35: 'FatigueRecovery', 36: 'PlayerAcceleration', 37: 'HittingPower',
    38: '?38 (CPU)', 39: 'HittingDifficulty', 40: 'HitStickEffect', 41: 'Aggression', 42: 'PokeEffect',
    43: 'WristShotAccuracy', 44: 'WristShotPower', 45: 'WristShotAccuracy CPU', 46: 'WristShotPower CPU',
    47: 'SlapShotAccuracy', 48: 'SlapShotPower', 49: 'PassAssist', 50: 'PassSpeed', 51: 'SaucerPassSpeed',
    52: 'PassInterception', 53: 'AIPassFrequency', 54: 'DumpSpeed', 55: 'SoftDumpHeight', 56: 'SoftDumpSpeed',
    57: 'DumpHeight', 58: 'AIDumpFrequency', 59: 'PuckFriction', 60: 'GlassBreak', 61: 'PuckElasticity',
    62: 'PuckGravity', 63: 'ShotBlocking', 64: 'HookEffect', 65: 'GoaliePassFrequency', 66: 'GoalieCoverPuck',
    67: 'PenaltyShotFrequency', 68: 'AILearning', 69: 'GoalieScreenEffect', 70: 'GoalieScreenEffect CPU',
    71: 'PuckControl CPU', 72: 'FatigueEffect CPU', 73: 'FatigueRecovery CPU', 74: 'Acceleration CPU',
    75: 'Aggression CPU', 76: 'PokeEffect CPU', 77: 'PassInterception CPU', 78: 'PassAccuracy',
    79: 'PassAccuracy CPU', 80: 'StickLift', 81: 'StickLift CPU', 82: 'ShotBlocking CPU',
    83: 'SlapShotPower CPU', 84: 'SlapShotAccuracy CPU', 85: 'OneTimerAccuracy', 86: 'OneTimerAccuracy CPU',
    87: 'CpuFaceoffDifficulty', 88: 'AttributeEffectAmplification', 89: 'PenaltyTimeScaling',
    90: 'OnBenchTimeScaling', 91: 'ManualPassing', 92: 'PostWhistleRules', 93: 'GoalieReaction',
    94: 'GoalieReaction CPU', 95: 'CPUDifficultyAdjustment', 96: 'GameStyle', 97: 'CpuPenalties',
    98: 'CpuTeammatePenalties', 99: 'StrategyAdjustments CPU', 100: 'StrategyAdjustments Human',
    101: 'StrategyAdjustments BAP', 102: 'BrokenStickFrequency', 103: 'PassReception', 104: '?104 (PassReception CPU)',
}
SET_NAMES = ['Arcade', 'Hybrid', 'Simulation', 'свой 3', 'свой 4']

LABELS = {
    105: ['Action', 'Ice', 'Classic', 'Overhead', 'Broadcast', 'TrueBroadcast', 'Custom1', 'Custom2', 'Custom3',
          'Custom4', 'Custom5'],
    9: ['Rookie', 'Pro', 'All-Star', 'Superstar'],
    12: ['Off', 'On', 'Delayed'],
    13: ['Off', 'On', 'No-touch', 'Hybrid'],
    18: ['Continuous OT', 'Shootout', '5 min + shootout', 'OT 4 on 4', 'OT 5 on 5', 'No OT'],
    24: SET_NAMES,
}


def chunks(data):
    """{номер: (смещение, версия, сумма, данные)} блоков хвоста сейва."""
    o = 0x2C + struct.unpack('>I', data[0x24:0x28])[0]
    out = {}
    while o + 16 <= len(data):
        cid, ver, size, h = struct.unpack('>IIII', data[o:o + 16])
        if size == 0 or o + 16 + size > len(data):
            break
        out[cid] = (o, ver, h, data[o + 16:o + 16 + size])
        o += 16 + size
    return out


def tail_start(data):
    return 0x2C + struct.unpack('>I', data[0x24:0x28])[0]


def bad_chunks(data):
    """Номера блоков хвоста, у которых сумма не сходится (CRC-32/BZIP2 по данным)."""
    return [cid for cid, (o, ver, h, d) in sorted(chunks(data).items()) if crc32_bzip2(d) != h]


def settings(path):
    c = chunks(open(path, 'rb').read())
    if CHUNK_SETTINGS not in c or len(c[CHUNK_SETTINGS][3]) != SIZE:
        sys.exit(f'{path}: нет блока настроек ({SIZE} байт)')
    return c[CHUNK_SETTINGS][3]


def s8(b):
    return b - 256 if b > 127 else b


def fmt(sid, v):
    if sid in VOLUMES:
        return f'{v} ({v * 10} %)'
    lab = LABELS.get(sid)
    return f'{v} ({lab[v]})' if lab and 0 <= v < len(lab) else str(v)


def fields(d):
    """[(группа, смещение, ID, имя, значение)] всех разобранных полей."""
    out = []
    for i in range(46):
        out.append(('общие', HEAD + i, 105 + i, GENERAL[105 + i], s8(d[HEAD + i])))
    for k in range(RULES_N):
        for j in range(RULES_LEN):
            o = RULES + k * RULES_LEN + j
            out.append((f'правила {k}', o, 9 + j, RULES_NAMES[9 + j], s8(d[o])))
    for k in range(SETS_N):
        for j in range(SET_LEN):
            o = SLIDERS + k * SET_LEN + j
            out.append((f'слайдеры {SET_NAMES[k]}', o, 28 + j, SLIDERS_NAMES[28 + j], s8(d[o])))
    return out


def game_running():
    if os.name != 'nt':
        return False
    out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq nhllegacy.exe', '/NH'], capture_output=True)
    return b'nhllegacy.exe' in out.stdout.lower()


def set_offsets(sets):
    """Смещения в блоке 2 всех байтов наборов sets."""
    return {SLIDERS + k * SET_LEN + j for k in sets for j in range(SET_LEN)}


def with_sliders(dst, src_block, sets):
    """(новые байты сейва dst, смещение блока 2): наборы sets — из src_block, сумма блока и обёртка пересчитаны."""
    o, ver, h, block = chunks(dst)[CHUNK_SETTINGS]
    new = bytearray(block)
    for i in set_offsets(sets):
        new[i] = src_block[i]
    ts = tail_start(dst)
    tail = bytearray(dst[ts:])
    rel = o - ts
    tail[rel + 12:rel + 16] = struct.pack('>I', crc32_bzip2(bytes(new)))
    tail[rel + 16:rel + 16 + SIZE] = new
    sf = SaveFile(dst, {})
    if sf.zlib is not None:
        sf.zlib.tail = bytes(tail)
    sf.tail = bytes(tail)
    return sf.bytes(), o


def check(old, new, src_block, sets, o):
    """Ошибки нового файла: суммы, наборы ≠ источник, изменения вне наборов и сумм."""
    err = SaveFile(new, {}).verify() + [f'блок {cid}: сумма не сходится' for cid in bad_chunks(new)]
    if len(new) != len(old):
        return err + [f'длина {len(new)} вместо {len(old)}']
    c = chunks(new)
    if CHUNK_SETTINGS not in c or c[CHUNK_SETTINGS][0] != o:
        return err + ['блок 2 не на прежнем месте']
    nb, ob = c[CHUNK_SETTINGS][3], chunks(old)[CHUNK_SETTINGS][3]
    in_sets = set_offsets(sets)
    differ = sorted(i for i in in_sets if nb[i] != src_block[i])
    if differ:
        err.append(f'наборы расходятся с источником: {len(differ)} байт (первый 0x{differ[0]:03X})')
    other = [i for i in range(SIZE) if i not in in_sets and nb[i] != ob[i]]
    if other:
        err.append(f'блок 2: изменились байты вне наборов: {[hex(i) for i in other[:8]]}')
    allowed = set(range(0x10, 0x14)) | set(range(o + 12, o + 16)) | {o + 16 + i for i in in_sets}
    outside = [i for i in range(len(new)) if new[i] != old[i] and i not in allowed]
    if outside:
        err.append(f'файл: изменились байты вне сумм и наборов: {[hex(i) for i in outside[:8]]}')
    return err


def copy_sliders(a):
    sets = sorted({int(x) for x in a.sets.split(',')})
    if not sets or any(not 0 <= k < SETS_N for k in sets):
        sys.exit(f'--sets: номера наборов 0…{SETS_N - 1}')
    src, dst = a.files
    src_block = settings(src)
    settings(dst)
    old = open(dst, 'rb').read()
    pre = SaveFile(old, {}).verify() + [f'блок {cid}: сумма не сходится' for cid in bad_chunks(old)]
    if pre:
        sys.exit(f'{dst}: суммы не сходятся до правки — не трогаю:\n  ' + '\n  '.join(pre))
    if SaveFile(old, {}).bytes() != old:
        sys.exit(f'{dst}: пересборка без правок не даёт исходный файл — не трогаю')
    new, o = with_sliders(old, src_block, sets)
    before, after = fields(chunks(old)[CHUNK_SETTINGS][3]), fields(chunks(new)[CHUNK_SETTINGS][3])
    changed = [(b, c[4]) for b, c in zip(before, after) if b[4] != c[4]]
    names = [x.replace('\\', '/').split('/')[-1] for x in (src, dst)]
    print(f'{names[1]} ← {names[0]}: наборы {", ".join(SET_NAMES[k] for k in sets)}; меняется значений: {len(changed)}')
    for (grp, off, sid, name, v0), v1 in changed:
        print(f'  {grp:20} 0x{off:03X} id {sid:3} {name:26} {v0} → {v1}')
    err = check(old, new, src_block, sets, o)
    if err:
        sys.exit('проверка нового файла не прошла:\n  ' + '\n  '.join(err))
    print(f'проверка: все суммы сходятся, вне сумм и наборов байты те же (блок 2 @0x{o:X})')
    if not changed:
        print('менять нечего')
        return
    if not a.write:
        print('прогон без --write: файл не записан')
        return
    if game_running():
        sys.exit('nhllegacy.exe запущен — не пишу (закрой игру)')
    os.makedirs(a.backup_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = os.path.join(a.backup_dir, f'{os.path.basename(dst)}.{stamp}')
    shutil.copy2(dst, backup)
    if open(backup, 'rb').read() != old:
        sys.exit(f'копия {backup} не совпала с исходным — не пишу')
    print(f'копия до правки: {backup}')
    try:
        with open(dst, 'wb') as f:
            f.write(new)
        back = open(dst, 'rb').read()
        err = ([] if back == new else ['записанный файл не равен подготовленному']) + \
            check(old, back, src_block, sets, o)
    except OSError as e:
        err = [f'запись: {e}']
    if err:
        shutil.copy2(backup, dst)
        ok = open(dst, 'rb').read() == old
        sys.exit('после записи проверка не прошла, файл возвращён из копии'
                 + ('' if ok else ' — НО НЕ СОВПАЛ С ИСХОДНЫМ, верни вручную') + ':\n  ' + '\n  '.join(err))
    print(f'записано: {dst}\nповторный разбор: наборы = источник, остальное как было, все суммы сходятся')


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('cmd', choices=['show', 'diff', 'copy-sliders'])
    ap.add_argument('files', nargs='+')
    ap.add_argument('--raw', action='store_true', help='show: ещё и неразобранный остаток блока')
    ap.add_argument('--sets', default='3,4', help='copy-sliders: номера наборов через запятую (3,4 — свои)')
    ap.add_argument('--write', action='store_true', help='copy-sliders: записать (без него — только прогон)')
    ap.add_argument('--backup-dir', default=BACKUP_DIR, help='copy-sliders: куда копия DST до правки')
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    if a.cmd == 'copy-sliders':
        if len(a.files) != 2:
            ap.error('copy-sliders: нужно SRC DST')
        copy_sliders(a)
        return
    data = [settings(f) for f in a.files]
    if a.cmd == 'show':
        d = data[0]
        rows = fields(d)
        preset = d[RULES + 15]
        print(f'GameStylePreset (правила 0) = {preset} → слайдеры набора «{SET_NAMES[preset] if preset < 5 else preset}»')
        for grp, o, sid, name, v in rows:
            print(f'{grp:20} 0x{o:03X}  id {sid:3}  {name:30} {fmt(sid, v)}')
        if a.raw:
            print('остаток 0x234…:', d[REST:].hex())
        return
    if len(data) < 2:
        ap.error('diff: нужно два файла и больше')
    names = [f.replace('\\', '/').split('/')[-1] for f in a.files]
    print('поле'.ljust(64) + ' | '.join(n[:24] for n in names))
    per = [fields(d) for d in data]
    for idx, (grp, o, sid, name, v) in enumerate(per[0]):
        vals = [p[idx][4] for p in per]
        if len(set(vals)) > 1:
            print(f'{grp:20} 0x{o:03X} id {sid:3} {name:24}'.ljust(64) + ' | '.join(fmt(sid, x) for x in vals))
    rest = [d[REST:] for d in data]
    if len(set(rest)) > 1:
        print('остаток 0x234…0x28F различается (не разбирался)')


if __name__ == '__main__':
    main()
