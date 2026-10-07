"""Коды мест в exhibitionplayerbiotable: `state` (7 бит) и `intlcountry` (7 бит).

Одна шкала, восстановлена по местам рождения игроков исходной базы (python tools/roster
codes — таблица «код → частые места»):
- 0 — Канада, 1–13 — провинции и территории по алфавиту (1 Alberta … 9 Ontario … 13 Yukon);
- 14 — США, 15–65 — штаты по алфавиту полных названий, с округом Колумбия (DC — 22, перед
  Delaware — 23: Уилмингтон в базе — 23);
- 66 и дальше — страны: 66–69 Скандинавия, 70–77 бывший СССР, 78–97 Европа, 98 и дальше —
  остальной мир, всё по алфавиту внутри группы; 127 — нет/неизвестно.
`state` — провинция или штат для Северной Америки, страна рождения для остальных;
`intlcountry` — гражданство (сборная), только коды стран.
Коды, которых нет в базе, выведены из алфавитного порядка групп и помечены (?) —
для игроков НХЛ 2026/27 они почти не встречаются.
"""

PROVINCES = ['AB', 'BC', 'MB', 'NB', 'NL', 'NT', 'NS', 'NU', 'ON', 'PE', 'QC', 'SK', 'YT']   # 1..13
PROVINCE_NAMES = {'alberta': 'AB', 'british columbia': 'BC', 'manitoba': 'MB', 'new brunswick': 'NB',
                  'newfoundland': 'NL', 'newfoundland and labrador': 'NL', 'northwest territories': 'NT',
                  'nova scotia': 'NS', 'nunavut': 'NU', 'ontario': 'ON', 'prince edward island': 'PE',
                  'quebec': 'QC', 'québec': 'QC', 'saskatchewan': 'SK', 'yukon': 'YT', 'yukon territory': 'YT',
                  'nf': 'NL', 'pq': 'QC', 'pei': 'PE', 'yk': 'YT'}
STATES = ['AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DC', 'DE', 'FL', 'GA', 'HI', 'ID', 'IL', 'IN', 'IA', 'KS',
          'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM', 'NY', 'NC',
          'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY']  # 15..65
STATE_NAMES = {
    'alabama': 'AL', 'alaska': 'AK', 'arizona': 'AZ', 'arkansas': 'AR', 'california': 'CA', 'colorado': 'CO',
    'connecticut': 'CT', 'delaware': 'DE', 'district of columbia': 'DC', 'washington, d.c.': 'DC', 'florida': 'FL',
    'georgia': 'GA', 'hawaii': 'HI', 'idaho': 'ID', 'illinois': 'IL', 'indiana': 'IN', 'iowa': 'IA',
    'kansas': 'KS', 'kentucky': 'KY', 'louisiana': 'LA', 'maine': 'ME', 'maryland': 'MD', 'massachusetts': 'MA',
    'michigan': 'MI', 'minnesota': 'MN', 'mississippi': 'MS', 'missouri': 'MO', 'montana': 'MT', 'nebraska': 'NE',
    'nevada': 'NV', 'new hampshire': 'NH', 'new jersey': 'NJ', 'new mexico': 'NM', 'new york': 'NY',
    'north carolina': 'NC', 'north dakota': 'ND', 'ohio': 'OH', 'oklahoma': 'OK', 'oregon': 'OR',
    'pennsylvania': 'PA', 'rhode island': 'RI', 'south carolina': 'SC', 'south dakota': 'SD', 'tennessee': 'TN',
    'texas': 'TX', 'utah': 'UT', 'vermont': 'VT', 'virginia': 'VA', 'washington': 'WA', 'west virginia': 'WV',
    'wisconsin': 'WI', 'wyoming': 'WY'}
CANADA, USA, NONE = 0, 14, 127
# ISO-3 (как в API НХЛ) → код страны. Без пометки — встречается в базе с местами рождения этой страны.
COUNTRY = {
    'CAN': 0, 'USA': 14,
    'DNK': 66, 'FIN': 67, 'NOR': 68, 'SWE': 69,
    'BLR': 70, 'EST': 71, 'KAZ': 72, 'KGZ': 73,  # 73 (?)
    'LVA': 74, 'LTU': 75, 'RUS': 76, 'UKR': 77,
    'AUT': 78, 'BEL': 79, 'BGR': 80,             # 80 (?)
    'HRV': 81, 'CZE': 82, 'GBR': 83, 'FRA': 84, 'DEU': 85, 'HUN': 86, 'ITA': 87,
    'MNE': 88, 'SRB': 88, 'YUG': 88,             # Подгорица; 88 — Югославия/Сербия и Черногория (?)
    'NLD': 89, 'POL': 91, 'ROU': 92, 'SVK': 95, 'SVN': 96, 'CHE': 97,
    'AUS': 98,                                   # 98 (?) по алфавиту первая в «остальном мире»
    'BHS': 99, 'BRA': 100, 'BRN': 101, 'COL': 104, 'COD': 105, 'JPN': 109, 'LBR': 110, 'NGA': 112,
    'SGP': 116, 'ZAF': 117, 'KOR': 118,
}
# прочие написания стран (stats REST, nhlratings.net, EA)
COUNTRY_ALIAS = {'GER': 'DEU', 'SUI': 'CHE', 'DEN': 'DNK', 'LAT': 'LVA', 'SLO': 'SVN', 'NED': 'NLD',
                 'CRO': 'HRV', 'BUL': 'BGR', 'ENG': 'GBR', 'SCO': 'GBR', 'WAL': 'GBR', 'NIR': 'GBR',
                 'SCG': 'MNE', 'RSA': 'ZAF', 'CZECHIA': 'CZE', 'CANADA': 'CAN', 'UNITED STATES': 'USA'}


def country_code(iso3):
    """Код страны (intlcountry/state) по ISO-3; None — неизвестная страна."""
    k = (iso3 or '').strip().upper()
    k = COUNTRY_ALIAS.get(k, k)
    return COUNTRY.get(k)


def state_code(country_iso3, province):
    """`state` для места рождения: провинция/штат в Канаде и США, иначе код страны (127 — нет)."""
    c = country_code(country_iso3)
    p = (province or '').strip()
    if c == CANADA:
        k = PROVINCE_NAMES.get(p.lower(), p.upper())
        return 1 + PROVINCES.index(k) if k in PROVINCES else CANADA
    if c == USA:
        k = STATE_NAMES.get(p.lower(), p.upper())
        return 15 + STATES.index(k) if k in STATES else USA
    return NONE if c is None else c


def table(db, table_name='exhibitionplayerbiotable'):
    """Код → (число игроков, частые места рождения) — проверка шкалы по базе."""
    from collections import Counter, defaultdict
    places = defaultdict(Counter)
    for r in range(db.by_name[table_name]['rows']):
        places[db.get(table_name, 'state', r)][db.get_string(table_name, 'birthplace', r)] += 1
    return {s: (sum(c.values()), [p for p, _ in c.most_common(5)]) for s, c in sorted(places.items())}


assert len(PROVINCES) == 13 and len(STATES) == 51
assert state_code('CAN', 'Nova Scotia') == 7 and state_code('CAN', 'ON') == 9 and state_code('USA', 'WI') == 64
assert state_code('USA', 'Minnesota') == 38 and state_code('USA', 'Massachusetts') == 36 and state_code('SWE', '') == 69
