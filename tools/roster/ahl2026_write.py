"""Запись составов АХЛ 2026/27 и пула свободных агентов на готовую базу (ahl2026.py): write.Writer, у которого
переписываются только составы клубов АХЛ (слоты игроков players.json вне НХЛ) и exhibitionfreeagents.

Отличия от write.Writer:
- донорами новых игроков служат только строки без клуба, прежнего пула свободных агентов и прежних игроков
  клубов АХЛ, которых нет в данных 2026/27 (строки игроков НХЛ, Европы и юниоров не трогаются);
- записи составов НХЛ, Европы, юниоров и особых команд остаются как были (у Writer составы НХЛ пересобираются);
- атрибуты строятся под OVR, который игра считает из атрибутов (legacy_model: ovrformula, формы NHL 27 по составам
  НХЛ базы), а не «среднее атрибутов + поправка группы» (11.10);
- проверки — по клубам АХЛ: 20 одетых, каждое место звеньев — одному, буквы, номера, 21–30 игроков (21 — у клубов,
  чьи составы в HockeyTech сами 22–24, а часть игроков в составах НХЛ на 08.10; координатор 10.10: настоящие
  составы, не добирать).
"""
import os
import shutil
from collections import Counter, defaultdict

from . import write as W
from .common import club_abbr, write_json
from .dbview import B, CLUBS, FLAGS, G, LINK_LIMIT, NATIONAL, NHL, POS_NAME, S, SPECIAL, T, View, fld

ROSTER_MIN, ROSTER_MAX = 21, 30          # 21: 20 одетых + запасной (до этапа в базе тоже были клубы АХЛ по 21)


class AhlWriter(W.Writer):
    def legacy_model(self):
        """Атрибуты — под OVR, который игра считает из атрибутов (Model.formula = ovrformula: точная формула игры,
        worth2.brk; OVR игры = цель у полевых и вратарей), а не «среднее атрибутов + поправка АХЛ». Форма нового
        игрока — как у конвейера (ratings.Model): медиана атрибутов игроков NHL 27 его амплуа и стиля; здесь — по игрокам
        составов НХЛ базы (их атрибуты писал конвейер 08.10), потому что в players.json этапа игроков с атрибутами NHL 27
        нет. У сопоставленного игрока форма — его атрибуты, стиль — прежний (Model.style)."""
        from . import ovrformula
        from .ratings import BASE, GK, SK, _median, cls
        m, v, db = self.model, self.v, self.db
        m.formula = ovrformula
        by_c, by_style = defaultdict(list), defaultdict(list)
        for r in range(v.nbio):
            if not v.ai(r) or v.created_slot(r) or not any(t in NHL for t in v.teams_of[r]):
                continue
            t, row = v.ai(r)
            c = cls(POS_NAME[v.g('position', r)])
            if (t == G) != (c == 'G'):
                continue
            a = {f: db.get(t, fld(f), row) + BASE for f in (GK if t == G else SK)}
            by_c[c].append(a)
            if t == S:
                by_style[(c, db.get(S, fld('p_style'), row))].append(a)
        for c, rows in by_c.items():
            m.shape[c] = {f: _median([a[f] for a in rows]) for f in rows[0]}
        m.shape_style = {k: {f: _median([a[f] for a in rows]) for f in SK} for k, rows in by_style.items()
                         if len(rows) >= 5}
        self.log('атрибуты — под OVR игры (точная формула, ovrformula); формы NHL 27 по игрокам '
                 'составов НХЛ: ' + ', '.join(f'{c} {len(x)}' for c, x in sorted(by_c.items()))
                 + f'; стилей {len(m.shape_style)}')

    def donor_candidates(self, taken):
        v = self.v
        out = {'G': [], 'S': []}
        for r in range(v.nbio):
            if r in taken or v.created_slot(r) or not v.ai(r):
                continue
            teams = v.teams_of[r]
            if any(t in SPECIAL for t in teams) or any(t in NHL for t in teams):
                continue
            if r in v.fa_rows:
                tier = 1
            elif not teams:
                tier = 2
            elif all(t in self.own_clubs for t in teams):
                tier = 4                          # игрок клуба АХЛ 2015 года, которого нет в данных 2026/27
            else:
                continue                          # клубы Европы и юниоров — не трогаем
            out['G' if v.is_goalie(r) else 'S'].append((False, v.birth(r)[0], tier, r))
        for k in out:
            out[k].sort()
        return out

    def rebuild_entries(self):
        v, db = self.v, self.db
        new_rows = set(self.p_of_row)
        donors = {self.row_of[i] for i in self.new}
        link_team = {e['playerindex']: e['team'] for e in v.entries}
        row_of_link = lambda l: v.row_of_gid.get(v.link_gid.get(l))
        kept, vacancies = [], []
        for e in v.entries:
            t, r = e['team'], row_of_link(e['playerindex'])
            if t in self.own_clubs:                   # клубы АХЛ — заново ниже
                continue
            if r in new_rows:
                if t in SPECIAL and r not in donors:
                    kept.append(dict(e))
                elif t in SPECIAL:
                    raise RuntimeError(f'донор {v.name(r)} в особой команде {t}')
                elif t in NHL:
                    raise RuntimeError(f'{v.name(r)} из состава НХЛ ({t}) попал в АХЛ/свободные агенты')
                else:
                    vacancies.append(dict(e))
            else:
                kept.append(dict(e))
        fa_keep = [l for l in v.fa if row_of_link(l) not in new_rows]
        used = {e['playerindex'] for e in kept} | set(fa_keep)
        if self.fa_only:
            self.fa_dropped = [v.name(row_of_link(l)) if row_of_link(l) is not None else f'связь {l}' for l in fa_keep]
            fa_keep = []
        free_index = (i for i in range(max(i for i in v.link_gid if i < LINK_LIMIT) + 1, LINK_LIMIT)
                      if i not in v.link_gid)

        def pick_link(r, team):
            gid = v.gid[r]
            cand = [l for l in v.links_of[gid] if l not in used and l not in v.link_created]
            cand.sort(key=lambda l: (link_team.get(l) != team, link_team.get(l) in SPECIAL, l))
            if cand:
                l = cand[0]
            else:
                l = next(free_index)
                self.new_links.append((l, gid))
            used.add(l)
            return l

        displaced = []
        for e in v.entries:
            r = row_of_link(e['playerindex'])
            if e['team'] in self.own_clubs and r not in new_rows and r not in displaced:
                displaced.append(r)
        self.displaced = list(displaced)
        refill = []
        orig_name = lambda r: f"{self.orig.get_string(B, 'firstname', r)} {self.orig.get_string(B, 'lastname', r)}"
        for e in sorted(vacancies, key=lambda e: (e['team'], e['playerindex'])):
            r_old = row_of_link(e['playerindex'])
            pos = self.orig.get(B, 'position', r_old)
            ne = self.free_vacancy(e, r_old, pos, kept, displaced, pick_link, orig_name)
            if ne is not None:
                refill.append(ne)
        for r in displaced:
            special = sorted(t for t in v.teams_of[r] if t in SPECIAL)
            nat = [t for t in special if t in NATIONAL]
            db.set(B, 'team', r, (nat or special)[0] + 1 if special else 0)
            for f in W.CONTRACT:
                db.set(B, f, r, 0)
        self.teamless = displaced
        own_entries = []
        by_team = defaultdict(list)
        for p in self.players:
            if p['slot'] is not None:
                by_team[p['slot']].append(p)
        self.lines_of, self.lines_info = {}, {}
        for team in sorted(by_team):
            tp = by_team[team]
            nums = self.numbers(tp)
            letters = self.letters(tp)
            keys, dressed = self.team_lines(team, tp)
            holder = defaultdict(set)
            for slot, k in keys.items():
                holder[k].add(slot)
            self.lines_of[team] = keys
            for p in tp:
                r = self.row_of[p['nhl_id']]
                e = {f: 0 for f in v.entry_fields}
                e.update({'team': team, 'playerindex': pick_link(r, team), 'jersey': nums[p['nhl_id']],
                          'playerstyle': p['_style'], 'rosterstatus': int(p['nhl_id'] in dressed),
                          'captain': letters.get(p['nhl_id'], 0)})
                for slot in holder[p['nhl_id']]:
                    e[slot] = 1
                db.set(B, 'jersey', r, nums[p['nhl_id']])
                own_entries.append(e)
                self.out[p['nhl_id']].update({'jersey': nums[p['nhl_id']], 'dressed': int(p['nhl_id'] in dressed),
                                              'letter': {1: 'C', 2: 'A'}.get(letters.get(p['nhl_id'], 0)),
                                              'slots': sorted(holder[p['nhl_id']])})
        self.fa_links = {}
        for p in self.fa_players:
            r = self.row_of[p['nhl_id']]
            self.fa_links[p['nhl_id']] = pick_link(r, None)
            self.out[p['nhl_id']].update({'jersey': v.g('jersey', r), 'dressed': 0, 'letter': None, 'slots': [],
                                          'fa_link': self.fa_links[p['nhl_id']]})
        fa_keep = sorted(fa_keep + list(self.fa_links.values()))
        entries = kept + refill + own_entries
        per_team = defaultdict(list)
        for e in entries:
            per_team[e['team']].append(e)
        final = []
        for team in sorted(per_team):
            es = sorted(per_team[team], key=lambda e: e['playerindex'])
            if len(es) > W.MAX_PER_TEAM:
                raise RuntimeError(f'в команде {team} {len(es)} игроков (больше {W.MAX_PER_TEAM})')
            for k, e in enumerate(es):
                e['key'] = team * W.MAX_PER_TEAM + k
                final.append(e)
        self.entries, self.fa_keep = final, fa_keep

    def verify(self):
        db = self.db
        v2 = View(db)
        bad = []
        es = v2.entries
        last = None
        cnt = Counter()
        for e in es:
            t = e['team']
            if e['key'] != t * W.MAX_PER_TEAM + cnt[t]:
                bad.append(f"key {e['key']} у команды {t} не по порядку")
            cnt[t] += 1
            if last is not None and e['key'] <= last:
                bad.append(f"key {e['key']} не по возрастанию")
            last = e['key']
        links = Counter(e['playerindex'] for e in es)
        bad += [f'связь {l} у {n} записей' for l, n in links.items() if n > 1]
        bad += [f"связи {e['playerindex']} нет в exhibitionplayers" for e in es if e['playerindex'] not in v2.link_gid]
        bad += [f'свободный агент {l} в составе' for l in v2.fa if l in links]
        club_of = defaultdict(list)
        for e in es:
            r = v2.row_of_gid.get(v2.link_gid.get(e['playerindex']))
            if r is None:
                bad.append(f"связь {e['playerindex']} → нет игрока")
                continue
            if e['team'] in NHL or e['team'] in CLUBS:
                club_of[r].append(e['team'])
            if v2.is_goalie(r) != (v2.ai(r)[0] == G):
                bad.append(f'{v2.name(r)}: амплуа и таблица атрибутов не совпадают')
        for r, ts in club_of.items():
            if len(ts) > 1:
                bad.append(f'{v2.name(r)} в двух клубах {ts}')
            if v2.g('team', r) != ts[0] + 1:
                bad.append(f"{v2.name(r)}: team {v2.g('team', r)} ≠ клуб {ts[0]} + 1")
        for team in sorted(self.own_clubs):
            te = [e for e in es if e['team'] == team]
            if not ROSTER_MIN <= len(te) <= ROSTER_MAX:
                bad.append(f'команда {team}: в составе {len(te)} (нужно {ROSTER_MIN}–{ROSTER_MAX})')
            for f in FLAGS:
                n = sum(e[f] for e in te)
                if n != 1:
                    bad.append(f'команда {team}: место {f} у {n} игроков')
            for f in FLAGS:
                for e in (e for e in te if e[f]):
                    r = v2.row_of_gid.get(v2.link_gid.get(e['playerindex']))
                    if r is None:
                        continue
                    pos = POS_NAME[v2.g('position', r)]
                    kind = W.lines_mod.slot_kind(f)
                    if (kind == 'G') != (pos == 'G'):
                        bad.append(f'команда {team}: на месте {f} {v2.name(r)} ({pos})')
            dressed = [e for e in te if any(e[f] for f in FLAGS)]
            if len(dressed) != 20 or any(e['rosterstatus'] != (e in dressed) for e in te):
                bad.append(f'команда {team}: одетых {len(dressed)}, rosterstatus не совпадает')
            caps = Counter(e['captain'] for e in te)
            if not ((caps[1] == 1 and caps[2] == 2) or (caps[1] == 0 and caps[2] == 3)):
                bad.append(f'команда {team}: буквы {dict(caps)}')
            nums = Counter(e['jersey'] for e in te)
            bad += [f'команда {team}: номер {n} у двоих' for n, c in nums.items() if c > 1]
        fa_set = set(v2.fa)
        for p in self.fa_players:
            r = self.row_of[p['nhl_id']]
            if club_of.get(r):
                bad.append(f'свободный агент {v2.name(r)} в составе {club_of[r]}')
            if self.fa_links.get(p['nhl_id']) not in fa_set:
                bad.append(f'свободного агента {v2.name(r)} нет в exhibitionfreeagents')
            if v2.g('team', r) != 0 or v2.g('contractstatus', r) != 0:
                bad.append(f"свободный агент {v2.name(r)}: team {v2.g('team', r)}, contractstatus "
                           f"{v2.g('contractstatus', r)}")
        want = {self.row_of[p['nhl_id']]: p['slot'] for p in self.players if p['slot'] is not None}
        for r, team in want.items():
            if club_of.get(r) != [team]:
                bad.append(f'{v2.name(r)}: в составах {club_of.get(r)}, нужен {team}')
        # составы НХЛ — байт в байт как были (записи тех же игроков с теми же звеньями)
        orig_v = View(self.orig)
        sig = lambda vv, e: (e['team'], vv.gid[vv.row_of_gid[vv.link_gid[e['playerindex']]]],
                             tuple(e[f] for f in FLAGS), e['jersey'], e['captain'], e['rosterstatus'])
        before = sorted(sig(orig_v, e) for e in orig_v.entries if e['team'] in NHL)
        after = sorted(sig(v2, e) for e in es if e['team'] in NHL)
        if before != after:
            bad.append(f'составы НХЛ изменились: было {len(before)} записей, стало {len(after)}')
        crc = db.verify()
        return bad, crc


def run_write(paths, log=print):
    w = AhlWriter(paths, log, real_lines=False)
    w.legacy_model()
    bad, crc, removed = w.run()
    if crc:
        raise SystemExit(f'CRC не сходятся: {crc[:3]}')
    os.makedirs(os.path.dirname(paths.db_out), exist_ok=True)
    tmp = paths.db_out + '.part'
    with open(tmp, 'wb') as f:
        f.write(w.db.d)
    os.replace(tmp, paths.db_out)
    if w.meta_path and os.path.dirname(os.path.abspath(w.meta_path)) != os.path.dirname(os.path.abspath(paths.db_out)):
        shutil.copyfile(w.meta_path, os.path.join(os.path.dirname(paths.db_out), 'nhlng-meta.xml'))
    write_json(paths.registry, dict(sorted(w.registry.items(), key=lambda kv: int(kv[0]))))
    sizes = Counter(e['team'] for e in w.entries if e['team'] in w.own_clubs)
    summary = {
        'db_in': paths.db_in, 'db_out': paths.db_out, 'players': list(w.out.values()),
        'no_room': [{'nhl_id': p['nhl_id'], 'name': f"{p['first']} {p['last']}", 'team': p['team'], 'pos': p['pos']}
                    for p in w.no_room],
        'events': w.events, 'teamless': [{'row': r, 'name': w.v.name(r), 'birth': list(w.v.birth(r))}
                                         for r in w.teamless],
        'new_links': w.new_links, 'stats_removed': removed, 'problems': bad, 'fa_dropped': w.fa_dropped,
        'lines': {club_abbr(t): k for t, k in w.lines_of.items()}, 'sizes': {str(t): n for t, n in sorted(sizes.items())},
        'vacancy_actions': dict(w.vacancy_actions),
        'rows': {'roster': w.db.by_name[W.R]['rows'], 'free_agents': w.db.by_name[W.F]['rows'],
                 'links': w.db.by_name[W.P]['rows']},
    }
    write_json(paths.written, summary)
    log(f'write: {len(w.out)} игроков ({len(w.out) - len(w.new)} сопоставлено, {len(w.new)} в строках доноров, '
        f'без места {len(w.no_room)}); клубов АХЛ {len(sizes)} ({min(sizes.values())}–{max(sizes.values())} игроков); '
        f'свободных агентов {w.db.by_name[W.F]["rows"]}; без клуба (АХЛ 2015) {len(w.teamless)} -> {paths.db_out}')
    log('  проверки: OK' if not bad else f'  проверки: {len(bad)} проблем, первые: {bad[:6]}')
    return summary, bad
