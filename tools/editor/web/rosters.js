// Составы: ростер → клуб → игрок; карточка, перевод, новый игрок, запись новым ростером (docs/editor.md «Составы»).
'use strict';
const Rosters = (() => {
  let root = null, team = null, gid = null, data = null, card = null, edits = {};
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
      el('div', { class: 'muted' }, L('Игра грузит новейший ростер поверх базы. Правки копятся здесь и пишутся новым ростером — прежние остаются.',
        'The game loads the newest roster over the database. Edits pile up here and are written as a new roster — older ones stay.')));
    const sel = el('select', { id: 'rsel' });
    const bar = el('div', { class: 'toolbar' }, el('span', { class: 'muted' }, L('Ростер:', 'Roster:')), sel,
      el('button', { class: 'ghost', onclick: () => doExport() }, L('Выгрузить файл ростера', 'Export roster file')),
      el('button', { class: 'ghost w', onclick: () => doImport() }, L('Загрузить файл ростера…', 'Add roster file…')),
      el('span', { style: 'flex:1' }),
      el('button', { class: 'w', id: 'rsave', disabled: !data.dirty, onclick: () => doSave() }, L('Сохранить новым ростером', 'Save as new roster')),
      el('button', { class: 'ghost', id: 'rdiscard', disabled: !data.dirty, onclick: () => doDiscard() }, L('Отменить правки', 'Discard edits')));
    head.append(bar);
    const ch = el('div', { id: 'rchanges', class: 'muted' }, changesText(data.changes));
    head.append(ch);
    root.append(head);
    listRosters().then(j => {
      for (const r of j.rosters) sel.append(el('option', { value: r.name, selected: r.name === data.roster }, `${r.display || r.name}  ·  ${r.name.slice(7)}`));
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
        el('button', { class: 'w', onclick: () => newPlayer() }, L('Новый игрок', 'New player'))), el('div', { id: 'plist' })),
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
    const j = await busy(L('Пишу ростер…', 'Writing roster…'), () => api('/api/x/rosters/save', {}));
    if (!j) return;
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
