// Составы: ростер → клуб → игрок; карточка, перевод, новый игрок, запись новым ростером (docs/editor.md «Составы»).
'use strict';
const Rosters = (() => {
  let root = null, team = null, gid = null, data = null, card = null, edits = {};
  let LAST_PLAYERS = [];
  const L = (ru, en) => T(ru, en);
  async function open(v) {
    root = v; v.innerHTML = '';
    const h = new URLSearchParams(location.hash.replace(/^#open=rosters&?/, ''));   // #open=rosters&team=30&gid=4166
    if (h.get('team') && team === null) { team = h.get('team'); if (h.get('gid')) gid = Number(h.get('gid')); }
    v.append(el('div', { class: 'loading' }, t('working')));
    try { data = await api('/api/x/rosters/teams'); } catch (e) { v.innerHTML = ''; v.append(el('div', { class: 'note' }, e.message)); return; }
    render();
  }
  async function listRosters() { return api('/api/x/rosters/list'); }
  function render() {
    root.innerHTML = '';
    const head = el('div', { class: 'ahead' },
      el('h2', {}, L('Составы', 'Rosters')),
      data.is_db
        ? el('div', { class: 'note' }, L('Правите БАЗУ игры (content\\…\\db\\nhlng.db): её берут новая франшиза, новый профиль и SET DEFAULT ROSTERS. Сохранённые ростеры — то, что игра грузит при запуске, — не меняются: чтобы правка была в игре сразу, правьте ростер. Запись — в content\\my\\db (прежняя — копией в cache\\editor\\backup), затем новейший ростер сверяется с новой базой.',
          'You are editing the game DATABASE (content\\…\\db\\nhlng.db): new franchises, new profiles and SET DEFAULT ROSTERS take it. Saved rosters — what the game loads on start — do not change: edit the roster to see the edit right away. Written to content\\my\\db (the previous one is copied to cache\\editor\\backup), then the newest roster is checked against the new database.'))
        : el('div', { class: 'muted' }, L('Правите РОСТЕР — его игра грузит при запуске поверх базы. Правки копятся здесь и пишутся новым ростером — прежние остаются. Основа для новых франшиз и профилей — база (последний пункт списка).',
          'You are editing a ROSTER — the game loads it on start over the database. Edits pile up here and are written as a new roster — older ones stay. The base for new franchises and profiles is the database (last item in the list).')));
    const sel = el('select', { id: 'rsel' });
    const bar = el('div', { class: 'toolbar' }, el('span', { class: 'muted' }, L('Что правим:', 'Editing:')), sel,
      el('button', { class: 'ghost', onclick: () => doExport() }, data.is_db ? L('Выгрузить базу', 'Export database') : L('Выгрузить файл ростера', 'Export roster file')),
      el('button', { class: 'ghost w', onclick: () => doImport() }, L('Загрузить файл ростера…', 'Add roster file…')),
      el('span', { style: 'flex:1' }),
      el('button', { class: 'w', id: 'rsave', disabled: !data.dirty, onclick: () => doSave() }, data.is_db ? L('Сохранить базу', 'Save database') : L('Сохранить новым ростером', 'Save as new roster')),
      el('button', { class: 'ghost', id: 'rdiscard', disabled: !data.dirty, onclick: () => doDiscard() }, L('Отменить правки', 'Discard edits')));
    head.append(bar);
    const ch = el('div', { id: 'rchanges', class: 'muted' }, changesText(data.changes));
    head.append(ch);
    root.append(head);
    listRosters().then(j => {
      for (const r of j.rosters) sel.append(el('option', { value: r.name, selected: r.name === data.roster }, r.name === '@db' ? r.display : `${L('Ростер', 'Roster')} ${r.display || r.name}  ·  ${r.name.slice(7)}`));
    });
    sel.addEventListener('change', async () => {
      if (data.dirty && !confirm(L('Несохранённые правки пропадут. Открыть другой ростер?', 'Unsaved edits will be lost. Open another roster?'))) { sel.value = data.roster; return; }
      await busy(t('working'), () => api('/api/x/rosters/open', { name: sel.value, discard: true }));
      open(root);
    });
    const tsel = el('select', { id: 'tsel' });
    for (const lg of data.leagues) {
      const og = el('optgroup', { label: lg.name });
      for (const tm of lg.teams) og.append(el('option', { value: tm.index, selected: String(tm.index) === String(team) }, `${tm.name} (${tm.count})`));
      tsel.append(og);
    }
    tsel.append(el('optgroup', { label: L('Без клуба', 'No club') }, el('option', { value: 'FA', selected: team === 'FA' }, L('Свободные агенты', 'Free agents'))));
    const cols = el('div', { class: 'rcols' },
      el('div', { class: 'rleft' }, el('div', { class: 'toolbar' }, tsel,
        el('button', { class: 'w', onclick: () => newPlayer() }, L('Новый игрок', 'New player')),
        el('button', { class: 'w ghost', title: L('4 тройки, 3 пары, спецбригады и 2 вратаря заново по рейтингу', '4 lines, 3 pairs, special teams and 2 goalies rebuilt by rating'), onclick: async () => {
          if (team === 'FA') return;
          const j = await busy(t('working'), () => api('/api/x/rosters/lines', { team }));
          if (j) { toast(L('Звенья собраны по рейтингу', 'Lines rebuilt by rating')); refreshHead(); loadPlayers(); } } }, L('Звенья по рейтингу', 'Lines by rating')),
        el('button', { class: 'w ghost', title: L('Свой клуб на свободном слоте Custom Team (как CREATE TEAM в игре)', 'Your own club on a free Custom Team slot (like CREATE TEAM in the game)'), onclick: async () => {
          const name = prompt(L('Название клуба (латиницей)', 'Club name'), ''); if (!name) return;
          const abbr = prompt(L('Сокращение, до 4 букв', 'Abbreviation, up to 4 letters'), name.slice(0, 3).toUpperCase()); if (!abbr) return;
          const j = await busy(t('working'), () => api('/api/x/rosters/new_club', { name, abbr }));
          if (j) { toast(L(`Клуб ${name} создан (слот ${j.team}). Переведите в него игроков (нужно 2 вратаря и 18 полевых) и нажмите «Звенья по рейтингу»`, `Club ${name} created (slot ${j.team}). Move players into it (2 goalies and 18 skaters) and press «Lines by rating»`)); team = String(j.team); open(root); } } }, L('Новый клуб…', 'New club…'))),
        el('div', { id: 'plist' })),
      el('div', { class: 'rright', id: 'pcard' }, el('p', { class: 'muted' }, L('Выберите игрока', 'Pick a player'))));
    root.append(cols);
    tsel.addEventListener('change', () => { team = tsel.value; gid = null; loadPlayers(); });
    if (team === null) team = tsel.value;
    loadPlayers();
    if (gid !== null) loadCard(gid);
  }
  function changesText(ch) {
    if (!ch || !ch.length) return L('Правок нет', 'No edits');
    return L('Несохранённые правки: ', 'Unsaved edits: ') + ch.slice(-6).join(' · ') + (ch.length > 6 ? ` (+${ch.length - 6})` : '');
  }
  async function refreshHead() {
    data = await api('/api/x/rosters/teams');
    $('#rchanges').textContent = changesText(data.changes);
    $('#rsave').disabled = !data.dirty; $('#rdiscard').disabled = !data.dirty;
  }
  async function loadPlayers() {
    const box = $('#plist'); box.innerHTML = '';
    const j = await api('/api/x/rosters/players?team=' + encodeURIComponent(team)).catch(e => { toast(e.message, 'err'); return { players: [] }; });
    const order = { C: 0, LW: 1, RW: 2, D: 3, G: 4 };
    j.players.sort((a, b) => (order[a.pos] - order[b.pos]) || (b.ovr - a.ovr));
    LAST_PLAYERS = j.players;
    const tb = el('table', { class: 'list plist' }, el('tr', {}, ...['#', L('Игрок', 'Player'), L('Амп.', 'Pos'), 'OVR', L('Возр.', 'Age'), ''].map(h => el('th', {}, h))));
    for (const p of j.players) {
      const tr = el('tr', { class: p.gid === gid ? 'sel' : '', onclick: () => { gid = p.gid; box.querySelectorAll('tr.sel').forEach(x => x.classList.remove('sel')); tr.classList.add('sel'); loadCard(p.gid); } },
        el('td', {}, String(p.jersey)), el('td', {}, p.last + ', ' + p.first + (p.letter ? ` (${p.letter})` : '')),
        el('td', {}, p.pos), el('td', {}, p.ovr === null ? '' : String(p.ovr)), el('td', {}, String(p.age)),
        el('td', { class: 'muted' }, p.dressed ? L('в составе', 'dressed') : (p.fa ? 'FA' : L('запас', 'spare'))));
      tb.append(tr);
    }
    box.append(tb);
  }
  async function loadCard(g) {
    const box = $('#pcard'); box.innerHTML = '';
    try { card = await api(`/api/x/rosters/card?gid=${g}&team=${encodeURIComponent(team)}`); } catch (e) { toast(e.message, 'err'); return; }
    edits = {};
    renderCard();
  }
  function renderCard() {
    const box = $('#pcard'); box.innerHTML = '';
    const p = card.player;
    const ovr = el('span', { class: 'ovr' }, p.ovr === null ? '' : `OVR ${p.ovr}`);
    box.append(el('div', { class: 'phead' }, el('h3', {}, `${p.first} ${p.last}`), el('span', { class: 'muted' }, `${p.pos} · #${p.jersey} · ${p.age} ${L('лет', 'y.o.')}`), ovr,
      p.clubs.length > 1 ? el('div', { class: 'muted' }, L('Ещё в составах: ', 'Also on: ') + p.clubs.map(c => c.name).join(', ')) : null));
    const mv = el('select', { id: 'mvsel' }, el('option', { value: '' }, L('— клуб —', '— club —')));
    for (const lg of data.leagues) {
      const og = el('optgroup', { label: lg.name });
      for (const tm of lg.teams) if (tm.club) og.append(el('option', { value: tm.index }, tm.name));
      mv.append(og);
    }
    mv.append(el('option', { value: 'FA' }, L('Свободные агенты', 'Free agents')));
    box.append(el('div', { class: 'toolbar' },
      el('button', { class: 'w', id: 'apply', disabled: true, onclick: () => applyEdits() }, L('Применить', 'Apply')),
      el('span', { class: 'muted' }, L('Перевести в', 'Move to')), mv,
      el('button', { class: 'w ghost', onclick: () => mv.value && doMove(mv.value) }, L('Перевести', 'Move'))));
    if (team !== 'FA' && LAST_PLAYERS.length) {
      const sw = el('select', { id: 'swsel' }, el('option', { value: '' }, L('— игрок клуба —', '— teammate —')));
      for (const q of LAST_PLAYERS) if (q.gid !== p.gid) sw.append(el('option', { value: q.gid }, `${q.pos} #${q.jersey} ${q.last}, ${q.first}${q.dressed ? ' · ' + L('в составе', 'dressed') : ''}`));
      box.append(el('div', { class: 'toolbar' }, el('span', { class: 'muted' }, L('Поменять местами в звеньях с', 'Swap line spots with')), sw,
        el('button', { class: 'w ghost', onclick: () => sw.value && doSwap(Number(sw.value)) }, L('Поменять', 'Swap'))));
    }
    for (const s of card.sections) {
      const fs = el('div', { class: 'fgrid' });
      for (const f of s.fields) fs.append(fieldInput(f));
      const sec = el('details', { class: 'psec', open: !s.advanced }, el('summary', {}, s.title), fs);
      box.append(sec);
    }
  }
  function fieldInput(f) {
    let inp;
    const mark = () => { $('#apply').disabled = !Object.keys(edits).length; };
    if (f.kind === 'enum') {
      inp = el('select', {});
      for (const [k, v] of f.options) inp.append(el('option', { value: k, selected: k === f.value }, v));
      inp.addEventListener('change', () => { edits[f.key] = Number(inp.value); mark(); });
    } else if (f.kind === 'bool') {
      inp = el('input', { type: 'checkbox' }); inp.checked = !!f.value;
      inp.addEventListener('change', () => { edits[f.key] = inp.checked ? 1 : 0; mark(); });
    } else if (f.kind === 'str') {
      inp = el('input', { type: 'text', value: f.value, maxlength: f.maxlen });
      inp.addEventListener('input', () => { edits[f.key] = inp.value; mark(); });
    } else {
      inp = el('input', { type: 'number', value: f.value, min: f.min, max: f.max, step: f.step || 1 });
      inp.addEventListener('input', () => { edits[f.key] = Number(inp.value); mark(); });
      if (f.kind === 'rating') {
        const bar = el('input', { type: 'range', min: f.min, max: f.max, value: f.value, class: 'rbar' });
        bar.addEventListener('input', () => { inp.value = bar.value; edits[f.key] = Number(bar.value); mark(); });
        inp.addEventListener('input', () => { bar.value = inp.value; });
        if (f.readonly) { inp.disabled = true; bar.disabled = true; }
        return el('label', { class: 'fld rating' }, el('span', {}, f.label), bar, inp);
      }
    }
    if (f.readonly) inp.disabled = true;
    return el('label', { class: 'fld' }, el('span', {}, f.label), inp);
  }
  async function applyEdits() {
    const j = await busy(t('working'), () => api('/api/x/rosters/update', { gid: card.player.gid, team, values: edits }));
    if (!j) return;
    card = j; edits = {}; renderCard();
    (j.notes || []).forEach(n => toast(n));
    toast(L('Правка в памяти — запишется кнопкой «Сохранить новым ростером»', 'Edit kept in memory — «Save as new roster» writes it'));
    refreshHead(); loadPlayers();
  }
  async function doSwap(other) {
    const j = await busy(t('working'), () => api('/api/x/rosters/swap', { a: card.player.gid, b: other, team }));
    if (!j) return;
    toast(L('Поменяны местами в звеньях', 'Line spots swapped') + (j.notes.length ? ': ' + j.notes.join('; ') : ''));
    refreshHead(); loadPlayers();
  }
  async function doMove(dst) {
    const j = await busy(t('working'), () => api('/api/x/rosters/move', { gid: card.player.gid, src: team, dst }));
    if (!j) return;
    toast(L('Переведён', 'Moved') + (j.notes.length ? ': ' + j.notes.join('; ') : ''));
    refreshHead(); loadPlayers(); $('#pcard').innerHTML = ''; gid = null;
  }
  async function newPlayer() {
    const box = $('#pcard'); box.innerHTML = '';
    const first = el('input', { type: 'text', maxlength: 24 }), last = el('input', { type: 'text', maxlength: 24 });
    const pos = el('select', {}, ...[[0, 'C'], [1, 'LW'], [2, 'RW'], [3, 'D'], [4, 'G']].map(([k, v]) => el('option', { value: k }, v)));
    const ovr = el('input', { type: 'number', value: 70, min: 40, max: 99 });
    box.append(el('h3', {}, L('Новый игрок', 'New player')),
      el('p', { class: 'muted' }, L('Игрок займёт пустой слот создаваемых игроков (как CREATE PLAYER в игре) и попадёт в запас выбранного клуба. Атрибуты — ровные под OVR, потом поправьте в карточке.',
        'The player takes a free created-player slot (like CREATE PLAYER in the game) and goes to the spares of the picked club. Attributes are even for the OVR; fine-tune them in the card.')),
      el('div', { class: 'fgrid' }, el('label', { class: 'fld' }, el('span', {}, L('Имя', 'First name')), first),
        el('label', { class: 'fld' }, el('span', {}, L('Фамилия', 'Last name')), last),
        el('label', { class: 'fld' }, el('span', {}, L('Амплуа', 'Position')), pos),
        el('label', { class: 'fld' }, el('span', {}, 'OVR'), ovr)),
      el('div', { class: 'toolbar' }, el('button', { class: 'w', onclick: async () => {
        const j = await busy(t('working'), () => api('/api/x/rosters/create', { team, pos: Number(pos.value), first: first.value, last: last.value, ovr: Number(ovr.value) }));
        if (!j) return;
        (j.notes || []).forEach(n => toast(n));
        gid = j.gid; refreshHead(); loadPlayers(); loadCard(j.gid);
      } }, L('Создать', 'Create'))));
  }
  async function doSave() {
    const j = await busy(L('Пишу…', 'Writing…'), () => api('/api/x/rosters/save', {}));
    if (!j) return;
    if (j.db) { toast(L(`База записана в ${j.display}; новейший ростер с ней сверен (лаунчер, код ${j.launcher ?? '—'})`, `Database saved to ${j.display}; the newest roster checked against it (launcher code ${j.launcher ?? '—'})`)); open(root); return; }
    toast(L(`Записан ${j.display} (${j.name}) — игра загрузит его при следующем запуске`, `Saved ${j.display} (${j.name}) — the game loads it on the next start`));
    open(root);
  }
  async function doDiscard() {
    if (!confirm(L('Отменить все несохранённые правки составов?', 'Discard all unsaved roster edits?'))) return;
    await busy(t('working'), () => api('/api/x/rosters/discard', {}));
    gid = null; open(root);
  }
  async function doExport() {
    const j = await busy(t('working'), () => api('/api/x/rosters/export', {}));
    if (j && !j.cancelled) toast(`${t('exported')}: ${j.written[0]}`, 'ok', el('button', { class: 'link', onclick: () => api('/api/open_folder', { path: j.folder }) }, t('open_folder')));
  }
  async function doImport() {
    const j = await busy(t('working'), () => api('/api/x/rosters/import', {}));
    if (j && !j.cancelled) { toast(j.message || 'OK'); open(root); }
  }
  return { open };
})();
window.Rosters = Rosters;
