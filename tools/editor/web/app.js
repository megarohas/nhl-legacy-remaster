// Редактор NHL Legacy Remaster: дерево разделов, просмотр ассета, выгрузка и импорт (docs/editor.md).
'use strict';
const $ = (s, el = document) => el.querySelector(s);
const el = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') e.className = v; else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (k === 'html') e.innerHTML = v; else if (v !== null && v !== undefined && v !== false) e.setAttribute(k, v);
  }
  for (const c of kids.flat()) if (c !== null && c !== undefined && c !== false) e.append(c.nodeType ? c : document.createTextNode(c));
  return e;
};
const STATE = { info: null, current: null, running: false, stamp: Date.now() };

async function api(path, body) {
  const opt = body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
  const r = await fetch(path, opt);
  const j = await r.json().catch(() => ({ error: 'bad', message: r.statusText }));
  if (!r.ok || j.error) throw new Error(j.message || j.error || r.statusText);
  return j;
}
function toast(text, kind = 'ok', extra) {
  const d = el('div', { class: 'toast ' + kind }, el('div', {}, text), extra || null);
  $('#toasts').append(d);
  setTimeout(() => d.classList.add('gone'), kind === 'err' ? 12000 : 6000);
  setTimeout(() => d.remove(), kind === 'err' ? 12600 : 6600);
}
async function busy(label, fn) {
  $('#busytext').textContent = label || t('working');
  $('#busy').classList.remove('hidden');
  try { return await fn(); } catch (e) { toast(e.message, 'err'); return null; }
  finally { $('#busy').classList.add('hidden'); }
}
function srcBadge(f) {
  if (!f.exists) return el('span', { class: 'badge none' }, t('no_file'));
  if (f.source === 'my') return el('span', { class: 'badge my' }, t('src_my'));
  if (f.source === 'part') return el('span', { class: 'badge part' }, `${t('src_part')}: content\\${f.where}`);
  return el('span', { class: 'badge ea' }, `${t('src_ea')}: ${f.where || ''}`);
}

// ---------------------------------------------------------------- шапка, язык
function applyLang() {
  document.documentElement.lang = LANG;
  document.title = 'NHL Legacy Remaster Editor — ' + T('Редактор', 'Editor');
  $('#title').textContent = t('title');
  document.querySelectorAll('[data-t]').forEach(e => e.textContent = t(e.dataset.t));
  document.querySelectorAll('[data-tp]').forEach(e => e.placeholder = t(e.dataset.tp));
  document.querySelectorAll('[data-lang]').forEach(b => b.classList.toggle('on', b.dataset.lang === LANG));
  setGame(STATE.running);
}
function setGame(on) {
  STATE.running = on;
  const g = $('#game');
  g.textContent = on ? t('game_on') : t('game_off');
  g.className = 'chip ' + (on ? 'warn' : 'ok');
  document.body.classList.toggle('readonly', on);
}
document.querySelectorAll('[data-lang]').forEach(b => b.addEventListener('click', async () => {
  LANG = b.dataset.lang;
  await api('/api/lang', { lang: LANG }).catch(() => {});
  history.replaceState(null, '', '?lang=' + LANG);
  applyLang();
  $('#tree').innerHTML = '';
  await loadTree($('#tree'), 'root', 0);
  if (STATE.current) openNode(STATE.current); else welcome();
}));
setInterval(async () => {
  try { const j = await api('/api/ping'); if (j.running !== STATE.running) setGame(j.running); } catch (e) { /* сервер закрыт */ }
}, 3000);

// ---------------------------------------------------------------- дерево
async function loadTree(box, node, depth) {
  let items;
  try { items = await api('/api/tree?node=' + encodeURIComponent(node)); } catch (e) { toast(e.message, 'err'); return; }
  for (const it of items) box.append(treeItem(it, depth));
}
function treeItem(it, depth) {
  const label = LANG === 'ru' ? it.ru : it.en;
  const row = el('div', { class: 'node' + (it.leaf ? ' leaf' : ''), style: `padding-left:${8 + depth * 14}px`, 'data-id': it.id },
    el('span', { class: 'tw' }, it.leaf ? '' : '▸'), el('span', { class: 'lbl' }, label),
    it.count !== undefined ? el('span', { class: 'cnt' }, String(it.count)) : null,
    it.default ? el('span', { class: 'dot', title: t('default_kit') }, '●') : null);
  const kids = el('div', { class: 'kids hidden' });
  const wrap = el('div', { class: 'item' }, row, kids);
  row.addEventListener('click', async () => {
    document.querySelectorAll('.node.sel').forEach(n => n.classList.remove('sel'));
    row.classList.add('sel');
    if (it.leaf) { openNode(it.id); return; }
    const open = kids.classList.toggle('hidden') === false;
    row.querySelector('.tw').textContent = open ? '▾' : '▸';
    if (open && !kids.dataset.loaded) { kids.dataset.loaded = 1; await loadTree(kids, it.id, depth + 1); applyFilter(); }
    if (it.id === 'files' || it.id.startsWith('files:') || it.id === 'models' || it.id === 'music' || it.id === 'menus'
      || it.id === 'equipment' || it.id === 'arenas') { /* папки — без просмотра */ }
  });
  return wrap;
}
function applyFilter() {
  const q = $('#filter').value.trim().toLowerCase();
  document.querySelectorAll('#tree .item').forEach(w => {
    const n = w.firstChild; const leaf = n.classList.contains('leaf');
    if (!q) { w.style.display = ''; return; }
    if (leaf) w.style.display = n.textContent.toLowerCase().includes(q) ? '' : 'none';
  });
}
$('#filter').addEventListener('input', applyFilter);

// ---------------------------------------------------------------- просмотр
function welcome() {
  const i = STATE.info || {};
  const v = $('#view');
  v.innerHTML = '';
  v.append(el('div', { class: 'welcome' },
    el('h1', {}, t('welcome_h')), el('p', {}, t('welcome_p')),
    el('table', { class: 'facts' },
      el('tr', {}, el('td', {}, t('install')), el('td', {}, i.install || '')),
      el('tr', {}, el('td', {}, 'content'), el('td', {}, i.content || '—')),
      el('tr', {}, el('td', {}, i.names_from === 'roster' ? t('names_roster') : t('names_db')), el('td', {}, i.roster || i.db || '')),
      el('tr', {}, el('td', {}, t('ea_files')), el('td', {}, i.ea_files === null ? '…' : String(i.ea_files) + (i.ea_error ? ' (' + i.ea_error + ')' : ''))),
      el('tr', {}, el('td', {}, t('edits_count')), el('td', {}, String(i.my_count ?? ''))),
      el('tr', {}, el('td', {}, T('Версия', 'Version')), el('td', {}, i.version || '')))));
}
async function openNode(id) {
  STATE.current = id;
  if (id === 'my') return showMy();
  if (id === 'rosters') return window.Rosters ? Rosters.open($('#view')) : null;
  const v = $('#view');
  v.innerHTML = '';
  v.append(el('div', { class: 'loading' }, t('working')));
  let a;
  try { a = await api('/api/asset?id=' + encodeURIComponent(id)); } catch (e) { v.innerHTML = ''; toast(e.message, 'err'); return; }
  if (STATE.current !== id) return;
  renderAsset(a);
}
function anyMy(a) { return a.files.some(f => f.in_my); }
function renderAsset(a) {
  const v = $('#view');
  v.innerHTML = '';
  STATE.stamp = Date.now();
  const hasTex = a.files.some(f => f.textures && f.textures.length);
  const bar = el('div', { class: 'toolbar' },
    hasTex ? el('button', { class: 'w', onclick: () => doExportAll(a) }, t('export_all')) : null,
    hasTex ? el('button', { class: 'w', onclick: () => doImportFolder(a) }, t('import_folder')) : null,
    anyMy(a) ? el('button', { class: 'w danger', onclick: () => doRevert(a, a.files.filter(f => f.in_my).map(f => f.rel), t('confirm_revert_all')) }, t('revert_all')) : null);
  v.append(el('div', { class: 'ahead' }, el('h2', {}, a.title), a.note ? el('div', { class: 'note' }, a.note) : null, bar));
  for (const f of a.files) v.append(renderFile(a, f));
}
function renderFile(a, f) {
  const box = el('div', { class: 'file' + (f.exists ? '' : ' missing') });
  box.append(el('div', { class: 'fhead' },
    el('div', {}, el('b', {}, LANG === 'ru' ? f.ru : f.en), ' ', el('code', {}, f.rel)), srcBadge(f),
    el('span', { class: 'fbtn' },
      f.exists ? el('button', { class: 'ghost', onclick: () => doRaw('export_raw', f) }, t('export_file')) : null,
      el('button', { class: 'ghost w', onclick: () => doRaw('import_raw', f) }, t('import_file')),
      f.in_my ? el('button', { class: 'ghost w danger', onclick: () => doRevert(a, [f.rel], t('confirm_revert')) }, t('revert')) : null)));
  if (f.error) box.append(el('div', { class: 'note' }, f.error));
  if (f.mesh && window.renderMesh) box.append(window.renderMesh(a, f));
  if (f.audio && window.renderAudio) box.append(window.renderAudio(a, f));
  const grid = el('div', { class: 'grid' });
  for (const tx of f.textures || []) grid.append(texCard(a, f, tx));
  if (f.textures && f.textures.length) box.append(grid);
  return box;
}
function texCard(a, f, tx) {
  const src = `/api/tex?rel=${encodeURIComponent(f.rel)}&i=${tx.index}&side=384&s=${STATE.stamp}`;
  const img = el('img', { loading: 'lazy', src: tx.ok ? src : '', alt: '' });
  const card = el('div', { class: 'card' },
    el('div', { class: 'thumb check', title: T('Открыть крупно', 'Open large'), onclick: () => tx.ok && openViewer(a, f, tx) }, tx.ok ? img : el('span', { class: 'na' }, t('not_supported'))),
    el('div', { class: 'cap' }, el('b', {}, tx.label || tx.name), el('span', {}, `${tx.w}×${tx.h} ${tx.fmt}${tx.levels > 1 ? ' · ' + tx.levels + ' ' + T('уровней', 'mips') : ''}`)),
    el('div', { class: 'cbtn' },
      el('button', { disabled: !tx.ok, onclick: () => doExportOne(a, f, tx) }, t('export_png')),
      el('button', { class: 'w', disabled: !tx.ok, onclick: () => doImportOne(a, f, tx) }, t('import_img'))));
  card.addEventListener('dragover', e => { e.preventDefault(); card.classList.add('drop'); });
  card.addEventListener('dragleave', () => card.classList.remove('drop'));
  card.addEventListener('drop', async e => {
    e.preventDefault(); card.classList.remove('drop');
    const file = e.dataTransfer.files[0];
    if (!file || !tx.ok) return;
    const b64 = await new Promise(res => { const r = new FileReader(); r.onload = () => res(r.result.split(',')[1]); r.readAsDataURL(file); });
    const j = await busy(t('working'), () => api('/api/import', { rel: f.rel, i: tx.index, data: b64 }));
    if (j && !j.cancelled) done(j, a);
  });
  card.title = t('drop_hint');
  return card;
}
function done(j, a) {
  if (j.cancelled) return;
  const notes = (j.notes || []).length ? ' · ' + j.notes.join('; ') : '';
  const extra = [];
  if (j.skipped && j.skipped.length) extra.push(`${t('skipped')}: ${j.skipped.length}`);
  if (j.unknown && j.unknown.length) extra.push(`${t('unknown')}: ${j.unknown.join(', ')}`);
  toast(`${t('saved')}: ${j.written.map(r => r.split('/').pop()).join(', ')}${notes}${extra.length ? ' · ' + extra.join(' · ') : ''}`);
  refreshInfo();
  if (a) openNode(a.id);
}
async function doExportAll(a) {
  const j = await busy(t('working'), () => api('/api/export', { id: a.id }));
  if (j && !j.cancelled) toast(`${t('exported')}: ${j.written.length} PNG → ${j.folder}`, 'ok', el('button', { class: 'link', onclick: () => api('/api/open_folder', { path: j.folder }) }, t('open_folder')));
}
async function doExportOne(a, f, tx) {
  const j = await busy(t('working'), () => api('/api/export', { id: a.id, rel: f.rel, i: tx.index }));
  if (j && !j.cancelled) toast(`${t('exported')}: ${j.written[0]}`, 'ok', el('button', { class: 'link', onclick: () => api('/api/open_folder', { path: j.folder }) }, t('open_folder')));
}
async function doImportOne(a, f, tx) {
  const j = await busy(t('working'), () => api('/api/import', { rel: f.rel, i: tx.index }));
  if (j) done(j, a);
}
async function doImportFolder(a) {
  const j = await busy(t('working'), () => api('/api/import_folder', { id: a.id }));
  if (j) done(j, a);
}
async function doRaw(kind, f) {
  const j = await busy(t('working'), () => api('/api/' + kind, { rel: f.rel }));
  if (!j || j.cancelled) return;
  if (kind === 'export_raw') toast(`${t('exported')}: ${j.written[0]}`, 'ok', el('button', { class: 'link', onclick: () => api('/api/open_folder', { path: j.folder }) }, t('open_folder')));
  else done(j, { id: STATE.current });
}
async function doRevert(a, rels, q) {
  if (!confirm(q)) return;
  const j = await busy(t('working'), () => api('/api/revert', { rels }));
  if (j) { toast(`${t('reverted')}: ${j.reverted.map(r => r.split('/').pop()).join(', ')}`); refreshInfo(); openNode(a.id); }
}

// ---------------------------------------------------------------- крупный просмотр
const VW = { scale: 1, x: 0, y: 0, fit: true, f: null, tx: null };
function openViewer(a, f, tx) {
  VW.f = f; VW.tx = tx; VW.fit = true;
  $('#vtitle').textContent = `${tx.label || tx.name} — ${f.rel} · ${tx.w}×${tx.h} ${tx.fmt}`;
  $('#vcmp').classList.toggle('hidden', !(f.in_my && f.sources && f.sources.length > 1));
  $('#vbelow').checked = false;
  loadViewerImg();
  $('#viewer').classList.remove('hidden');
}
function loadViewerImg() {
  const below = $('#vbelow').checked ? '&below=1' : '';
  const img = $('#vimg');
  img.onload = () => fitViewer();
  img.src = `/api/tex?rel=${encodeURIComponent(VW.f.rel)}&i=${VW.tx.index}${below}&s=${STATE.stamp}`;
}
function fitViewer() {
  const st = $('#vstage'), img = $('#vimg');
  if (VW.fit) {
    VW.scale = Math.min(st.clientWidth / img.naturalWidth, st.clientHeight / img.naturalHeight, 4);
    VW.x = (st.clientWidth - img.naturalWidth * VW.scale) / 2; VW.y = (st.clientHeight - img.naturalHeight * VW.scale) / 2;
  }
  img.style.transform = `translate(${VW.x}px,${VW.y}px) scale(${VW.scale})`;
}
$('#vbelow').addEventListener('change', loadViewerImg);
$('#vclose').addEventListener('click', () => $('#viewer').classList.add('hidden'));
$('#vfit').addEventListener('click', () => { VW.fit = true; fitViewer(); });
$('#v100').addEventListener('click', () => { VW.fit = false; VW.scale = 1; VW.x = 20; VW.y = 20; fitViewer(); });
document.querySelectorAll('[data-bg]').forEach(b => b.addEventListener('click', () => { $('#vstage').className = 'vstage ' + b.dataset.bg; }));
document.addEventListener('keydown', e => { if (e.key === 'Escape') $('#viewer').classList.add('hidden'); });
$('#vstage').addEventListener('wheel', e => {
  e.preventDefault(); VW.fit = false;
  const k = e.deltaY < 0 ? 1.15 : 1 / 1.15, r = $('#vstage').getBoundingClientRect();
  const mx = e.clientX - r.left, my = e.clientY - r.top;
  VW.x = mx - (mx - VW.x) * k; VW.y = my - (my - VW.y) * k; VW.scale *= k; fitViewer();
}, { passive: false });
(() => {
  let drag = null;
  $('#vstage').addEventListener('mousedown', e => { drag = [e.clientX - VW.x, e.clientY - VW.y]; VW.fit = false; });
  window.addEventListener('mousemove', e => { if (drag) { VW.x = e.clientX - drag[0]; VW.y = e.clientY - drag[1]; fitViewer(); } });
  window.addEventListener('mouseup', () => { drag = null; });
  window.addEventListener('resize', () => { if (!$('#viewer').classList.contains('hidden')) fitViewer(); });
})();

// ---------------------------------------------------------------- мои правки
async function showMy() {
  const v = $('#view');
  v.innerHTML = '';
  const j = await api('/api/my').catch(e => { toast(e.message, 'err'); return { files: [] }; });
  v.append(el('div', { class: 'ahead' }, el('h2', {}, t('my')), el('div', { class: 'note' }, t('edits_hint')),
    j.files.length ? el('div', { class: 'toolbar' }, el('button', { class: 'w danger', onclick: () => doRevert({ id: 'my' }, j.files.map(f => f.rel), t('confirm_revert_all')) }, t('revert_all'))) : null));
  if (!j.files.length) { v.append(el('p', { class: 'muted' }, t('no_edits'))); return; }
  const tb = el('table', { class: 'list' });
  for (const f of j.files) {
    tb.append(el('tr', {}, el('td', {}, el('code', {}, f.rel)), el('td', { class: 'muted' }, f.part),
      el('td', {}, el('button', { class: 'ghost', onclick: () => openNode('file:' + f.rel) }, T('Открыть', 'Open')),
        el('button', { class: 'ghost w danger', onclick: () => doRevert({ id: 'my' }, [f.rel], t('confirm_revert')) }, t('revert')))));
  }
  v.append(tb);
}
$('#btn-my').addEventListener('click', () => { document.querySelectorAll('.node.sel').forEach(n => n.classList.remove('sel')); openNode('my'); });

async function openPath(id) {
  // ссылка #open=<id ассета>: раскрыть дерево до него и открыть
  const path = await api('/api/path?id=' + encodeURIComponent(id)).catch(() => []);
  for (const nid of path) {
    const row = document.querySelector(`.node[data-id="${CSS.escape(nid)}"]`);
    if (!row) break;
    const kids = row.parentElement.querySelector('.kids');
    if (kids && kids.classList.contains('hidden')) { row.click(); await new Promise(r => setTimeout(r, 50)); for (let i = 0; i < 50 && !kids.dataset.loaded; i++) await new Promise(r => setTimeout(r, 50)); await new Promise(r => setTimeout(r, 300)); }
  }
  const leaf = document.querySelector(`.node[data-id="${CSS.escape(id)}"]`);
  if (leaf) { leaf.classList.add('sel'); leaf.scrollIntoView({ block: 'center' }); }
  await openNode(id);
}
window.renderMesh = (a, f) => {
  const m = f.mesh;
  const box = el('div', { class: 'mesh' });
  const info = m.error ? `${t('mesh')}: ${m.error}` : `${t('mesh')}: ${m.subs > 1 ? m.subs + ' × ' : ''}${m.vertices} ${t('vertices')}, ${m.triangles} ${t('triangles')}`;
  const holder = el('div', {});
  const bar = el('div', { class: 'meshbar' }, el('span', { class: 'muted' }, info),
    m.error ? null : el('button', { class: 'ghost', onclick: () => show3d() }, t('view3d')),
    m.error ? null : el('button', { class: 'ghost', onclick: () => showUv() }, t('uv')),
    m.error ? null : el('button', { onclick: () => meshAct('export', f) }, t('export_obj')),
    m.error ? null : el('button', { class: 'w', onclick: () => meshAct('import', f) }, t('import_obj')));
  box.append(bar, holder);
  let geom = null;
  async function g() { if (!geom) geom = await busy(t('working'), () => api('/api/x/meshes/geom?rel=' + encodeURIComponent(f.rel))); return geom; }
  async function show3d() { const gg = await g(); if (!gg) return; holder.innerHTML = ''; const c = el('canvas', { class: 'v3d' }); holder.append(c); View3D.mount(c, gg); }
  async function showUv() {
    const gg = await g(); if (!gg) return; holder.innerHTML = '';
    const tx = a.files.find(x => x.textures && x.textures.length && x.textures[0].ok);
    const c = el('canvas', { class: 'uvc', style: 'width:512px;height:512px;border-radius:6px' }); holder.append(c);
    View3D.uvLayout(c, gg, tx ? `/api/tex?rel=${encodeURIComponent(tx.rel)}&i=${tx.textures[0].index}&side=512` : null);
  }
  if (!m.error && m.vertices < 60000) setTimeout(show3d, 30);
  return box;
};
async function meshAct(kind, f) {
  const j = await busy(t('working'), () => api('/api/x/meshes/' + kind, { rel: f.rel }));
  if (!j || j.cancelled) return;
  if (kind === 'export') toast(`${t('exported')}: ${j.written.join(', ')}`, 'ok', el('button', { class: 'link', onclick: () => api('/api/open_folder', { path: j.folder }) }, t('open_folder')));
  else done(j, { id: STATE.current });
}
async function refreshInfo() {
  try { STATE.info = await api('/api/info'); setGame(STATE.info.running); } catch (e) { /* */ }
}
(async function init() {
  applyLang();
  await refreshInfo();
  if (STATE.info && STATE.info.lang && !new URLSearchParams(location.search).get('lang')) { LANG = STATE.info.lang; applyLang(); }
  await loadTree($('#tree'), 'root', 0);
  welcome();
  const m = location.hash.match(/^#open=(.+)$/);
  if (m) await openPath(decodeURIComponent(m[1]));
  if (STATE.info && STATE.info.ea_files === null) setTimeout(async () => { await refreshInfo(); if (!STATE.current) welcome(); }, 2500);
})();
