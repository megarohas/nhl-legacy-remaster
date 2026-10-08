"""Свободные агенты (`--fa`): реальные игроки без клуба НХЛ на 2026/27 → exhibitionfreeagents.

Кандидаты — все, кто играл в регулярном чемпионате НХЛ в 2024/25 или 2025/26 (stats REST `bios`
за оба сезона: в строке есть `currentTeamAbbrev` — нынешний клуб), а сейчас клуба нет и в составах
конвейера их нет. Проверка:
- карточка landing (`/v1/player/{id}/landing`): нет `currentTeamAbbrev` (клуб мог появиться после
  снимка bios); нет строк сезона 2026/27 в другой лиге (подписал контракт в КХЛ, Европе, АХЛ и уже
  играет — сезоны в Европе и КХЛ начались в сентябре; контракт АХЛ до первого матча 10.10 не виден);
  прошлый сезон — не только в Европе/КХЛ; `isActive` не годится: у всех без контракта НХЛ он false;
- Wikipedia: раздел «Last games» статей «2024–25 NHL season» и «2025–26 NHL season» (известные
  игроки, завершившие карьеру) и карточка игрока (`{{Infobox ice hockey player}}`): `career_end`
  заполнен — завершил карьеру, `team = Free agent` — подтверждение, другой клуб — подписан;
- не старше FA_MAX_AGE лет и не меньше FA_MIN_GP игр в НХЛ за два сезона.
Кэш: nhl/stats/{skater,goalie}-bios-20242025.json, nhl/fa/candidates.json, карточки — nhl/landing/,
wiki/season-2024-25.wikitext, wiki/season-2025-26.wikitext, wiki/players/<имя>.wikitext.

В базе свободный агент — как 183 свободных агента исходной базы: `team` 0, `proteam` 0, контракта нет
(`contractstatus` 0, сумма и срок 0), `yearufa` — нынешний год; связь — в exhibitionfreeagents, в
составах его нет. Строка — донор того же класса (write.py), рейтинг — по статистике (statsrating.py),
если EA/nhlratings.net его не знают.
"""
import os
import re
import urllib.parse

from .common import SEASON, SEASON_YEAR, TEAM_SLOT, norm, read_json, write_json

STATS = 'https://api.nhle.com/stats/rest/en'
NHL = 'https://api-web.nhle.com/v1'
FA_SEASONS = (SEASON - 20002, SEASON - 10001)      # 2024/25, 2025/26
FA_MIN_GP = 10
FA_MAX_AGE = 40
WIKI = 'https://en.wikipedia.org/wiki/{}?action=raw'          # robots.txt закрывает /w/, /wiki/ — открыт
SEASON_ARTICLES = ('2024–25', '2025–26')
ABROAD = {'KHL', 'SHL', 'Liiga', 'NL', 'DEL', 'Czechia', 'ICEHL', 'Slovakia', 'VHL', 'HockeyAllsvenskan', 'Mestis',
          'SL', 'DEL2', 'Norway', 'Denmark', 'Ligue Magnus', 'Belarus', 'Latvia', 'AlpsHL', 'EIHL', 'Kazakhstan'}


def _season_rel(season):
    return f"wiki/season-{season.replace('–', '-')}.wikitext"


def last_games(text):
    """Имена из раздела «Last games» (игроки, сыгравшие в этом сезоне последний матч в НХЛ)."""
    m = re.search(r'===\s*Last games\s*===(.*?)(?:\n==[^=]|\Z)', text or '', re.S)
    out = set()
    for line in (m.group(1) if m else '').split('\n'):
        line = line.strip()
        if line.startswith('|') and not line.startswith(('|-', '|}', '|+')):
            link = re.search(r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]', line)
            if link:
                out.add(norm(re.sub(r'\s*\(.*?\)$', '', link.group(2) or link.group(1))))
    return out


def _player_rel(title):
    return 'wiki/players/' + re.sub(r'[^\w().-]+', '_', title) + '.wikitext'


def infobox(text):
    """Поля карточки {{Infobox ice hockey player}}: {'team': …, 'career_end': …} или None."""
    m = re.search(r'\{\{\s*Infobox ice hockey (?:player|biography)(.*?)\n\}\}', text or '', re.S | re.I)
    if not m:
        return None
    out = {}
    for line in m.group(1).split('\n'):
        f = re.match(r'\s*\|\s*(\w+)\s*=\s*(.*)', line)
        if f:
            out[f.group(1).lower()] = re.sub(r'<!--.*?-->', '', f.group(2)).strip()
    return out


def _article(get, name):
    """Статья игрока: «Имя Фамилия» (с перенаправлением), иначе «… (ice hockey)»; текст или None.
    get(title) — wikitext страницы (сеть с кэшем или только кэш)."""
    for title in (name, f'{name} (ice hockey)'):
        text = None
        for _ in range(2):                                  # перенаправление — не больше одного
            text = get(title)
            red = re.match(r'\s*#REDIRECT\s*\[\[([^\]|#]+)', text or '', re.I)
            if not red:
                break
            title = red.group(1).strip()
        if text and infobox(text) is not None:
            return text
    return None


def wiki_player(h, name):
    return _article(lambda t: h.text(WIKI.format(urllib.parse.quote(t.replace(' ', '_'))), _player_rel(t)), name)


def _bios(h, kind, season):
    exp = urllib.parse.quote(f'gameTypeId=2 and seasonId={season}')
    url = f'{STATS}/{kind}/bios?isAggregate=false&isGame=false&start=0&limit=-1&cayenneExp={exp}'
    return (h.json(url, f'nhl/stats/{kind}-bios-{season}.json') or {}).get('data') or []


def candidates(h, roster_ids):
    """playerId → {'gp': игры НХЛ за два сезона, 'last': последний сезон} у тех, у кого в bios нет клуба."""
    out = {}
    for season in FA_SEASONS:
        for kind in ('skater', 'goalie'):
            for r in _bios(h, kind, season):
                pid = r['playerId']
                if pid in roster_ids:
                    continue
                c = out.setdefault(pid, {'gp': 0, 'last': season, 'team': r.get('currentTeamAbbrev')})
                c['gp'] += r.get('gamesPlayed') or 0
                c['last'] = max(c['last'], season)
                if season == FA_SEASONS[-1] or not c['team']:
                    c['team'] = r.get('currentTeamAbbrev')
    return {pid: c for pid, c in out.items() if not c['team']}


def fetch(h, roster_ids, log):
    """bios за 2024/25 (2025/26 уже есть), кандидаты, их карточки landing, статьи сезонов Wikipedia и
    статьи тех, кого карточка не отсеяла."""
    cand = candidates(h, roster_ids)
    write_json(h.path('nhl/fa/candidates.json'), {str(k): v for k, v in sorted(cand.items())})
    for pid in sorted(cand):
        h.json(f'{NHL}/player/{pid}/landing', f'nhl/landing/{pid}.json')
    for season in SEASON_ARTICLES:
        h.text(WIKI.format(urllib.parse.quote(f'{season}_NHL_season')), _season_rel(season))
    wiki = 0
    for pid in sorted(cand):
        land = h.json(f'{NHL}/player/{pid}/landing', f'nhl/landing/{pid}.json')
        if land and check_api(land, cand[pid]['gp']) is None:
            wiki += wiki_player(h, f"{land['firstName']['default']} {land['lastName']['default']}") is not None
    log(f'FA: кандидатов без клуба (играли в НХЛ в 2024/25–2025/26) {len(cand)}, статей Wikipedia {wiki}')


def check_api(land, gp):
    """Причина по карточке landing, по которой кандидат не свободный агент, или None."""
    if not land:
        return 'нет карточки'
    if land.get('currentTeamAbbrev'):
        return f"клуб {land['currentTeamAbbrev']}"
    rows = [s for s in land.get('seasonTotals') or [] if s.get('gameTypeId') == 2]
    now = [s for s in rows if s.get('season') == SEASON and s.get('leagueAbbrev') != 'NHL']
    if now:
        s = now[-1]
        return f"играет в 2026/27: {s.get('leagueAbbrev')} ({(s.get('teamName') or {}).get('default')})"
    last = [s for s in rows if s.get('season') == SEASON - 10001]
    if last and all(s.get('leagueAbbrev') in ABROAD for s in last):
        s = last[-1]
        return f"2025/26 играл в {s.get('leagueAbbrev')} ({(s.get('teamName') or {}).get('default')})"
    y = int(land['birthDate'][:4])
    if SEASON_YEAR - y > FA_MAX_AGE:
        return f'старше {FA_MAX_AGE} лет'
    if gp < FA_MIN_GP:
        return f'меньше {FA_MIN_GP} игр в НХЛ за два сезона'
    return None


def check_wiki(cache, name, retired):
    """(причина или None, пометка): по разделам «Last games» и карточке игрока в Wikipedia."""
    if norm(name) in retired:
        return 'завершил карьеру (Wikipedia, «Last games» сезона)', None
    text = _article(lambda t: read_text(os.path.join(cache, *_player_rel(t).split('/'))), name)
    box = infobox(text)
    if box is None:
        return None, 'Wikipedia: статьи нет'
    if box.get('career_end'):
        return f"завершил карьеру (Wikipedia: career_end {box['career_end']})", None
    team = re.sub(r'\[\[(?:[^\]|]*\|)?([^\]]*)\]\]', r'\1', box.get('team') or box.get('current_team') or '').strip()
    if team and norm(team) != 'freeagent':
        return f'по Wikipedia — клуб {team}', None
    return None, 'Wikipedia: Free agent' if team else 'Wikipedia: клуб не указан'


def read_text(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        return f.read()


def players(cache, bios, base_record, entry_from_landing, landing, roster_ids, log=print, overrides=None):
    """Свободные агенты в формате players.json (team 'FA', slot None, поле fa) и отсев с причинами.
    overrides — ручные поправки (game/work/roster/fa-overrides.json): {"exclude": {nhl_id: причина},
    "include": {nhl_id: причина}} — include берёт кандидата, даже если проверка его отсеяла."""
    overrides = overrides or {}
    force_out = {str(k): v for k, v in (overrides.get('exclude') or {}).items()}
    force_in = {str(k): v for k, v in (overrides.get('include') or {}).items()}
    cand = read_json(os.path.join(cache, 'nhl', 'fa', 'candidates.json'))
    if cand is None:
        log('  FA: нет nhl/fa/candidates.json — сначала fetch --only fa')
        return [], []
    retired = set()
    for season in SEASON_ARTICLES:
        retired |= last_games(read_text(os.path.join(cache, *_season_rel(season).split('/'))))
    out, dropped = [], []
    for key, c in sorted(cand.items(), key=lambda kv: int(kv[0])):
        pid = int(key)
        if pid in roster_ids:
            continue
        land = landing(cache, pid)
        name = (f"{land['firstName']['default']} {land['lastName']['default']}" if land else key)
        why, note = check_api(land, c['gp']), None
        if why is None:
            why, note = check_wiki(cache, name, retired)
        if key in force_out:
            why = f'исключён вручную: {force_out[key] or "fa-overrides.json"}'
        elif key in force_in and land:
            why, note = None, f'включён вручную: {force_in[key] or "fa-overrides.json"}'
        if why:
            dropped.append({'nhl_id': pid, 'name': name, 'gp': c['gp'], 'why': why})
            continue
        if land.get('position') not in ('C', 'L', 'R', 'D', 'G'):
            dropped.append({'nhl_id': pid, 'name': name, 'gp': c['gp'], 'why': 'нет амплуа'})
            continue
        e = entry_from_landing(land)
        p = base_record('FA', e, land, bios.get(pid), slot=-1)
        p['slot'] = None
        p['fa'] = {'nhl_gp_2y': c['gp'], 'last_season': c['last'], 'wiki': note,
                   'last_team': next((s.get('teamName', {}).get('default') for s in reversed(land.get('seasonTotals') or [])
                                      if s.get('leagueAbbrev') == 'NHL'), None)}
        out.append(p)
    log(f'FA: свободных агентов {len(out)}, отсеяно {len(dropped)}')
    return out, dropped


assert all(t in TEAM_SLOT for t in ('ANA', 'VGK'))
