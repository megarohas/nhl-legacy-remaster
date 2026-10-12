"""Настройки игры в сейвах NHL Legacy: блок SETTINGS_MGR_CHUNK (номер 2, 656 байт) — разбор и сравнение.

    python tools/legacy_settings.py show FILE [--raw]       # все поля блока настроек сейва
    python tools/legacy_settings.py diff A B [C …]          # поля, где сейвы расходятся (A — как эталон)

FILE — внутренний файл сейва Legacy из userdata порта: PROFILE (UserProfileFile), DYNASTY, BEAPRO, SEASON,
PLAYOFF, TOURNAMENT. Только чтение. Разбор — docs/legacy-port.md, «Настройки по умолчанию для новых карьер».

Хвост сейва (после базы: 0x2C + u32@0x24) — цепочка блоков: u32 номер, u32 версия (1), u32 размер, u32 сумма,
данные (все поля big-endian). Блок 2 — копия настроек менеджера настроек игры (объект *(0x83BD3074), конструктор
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
"""
import argparse, struct, sys

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


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('cmd', choices=['show', 'diff'])
    ap.add_argument('files', nargs='+')
    ap.add_argument('--raw', action='store_true', help='show: ещё и неразобранный остаток блока')
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
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
