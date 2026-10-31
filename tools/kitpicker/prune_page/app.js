// Чистка форм: снятая галочка — форма уйдёт. С сервером prune.py выбор пишется в selection.json при каждом клике;
// открыта как файл — живёт в браузере (localStorage) и выгружается кнопкой «Сохранить файл».
(function () {
  const KEY = 'kitprune.v1';
  const { teams, groups } = window.KITS;
  const served = location.protocol.startsWith('http');
  const titles = Object.fromEntries(groups.map(g => [g.id, g.title]));
  const all = teams.flatMap(t => t.kits.map(k => ({ ...k, code: t.code, team: t })));
  const free = new Set(all.filter(k => !k.locked).map(k => k.id));
  let removed = new Set();
  let timer = null;

  const $ = id => document.getElementById(id);
  const state = msg => { $('state').textContent = msg; };

  function result() {
    return { saved: new Date().toISOString(), remove: [...removed].sort() };
  }

  async function push() {
    try { localStorage.setItem(KEY, JSON.stringify([...removed])); } catch (e) { /* без хранилища — только сервер */ }
    if (!served) { state('сохранено в браузере'); return; }
    const res = await fetch('selection', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(result()),
    }).catch(() => null);
    state(res && res.ok ? 'сохранено ' + new Date().toLocaleTimeString() : 'не сохранилось: сервер не отвечает');
  }

  function changed() {
    refresh();
    clearTimeout(timer);
    timer = setTimeout(push, 250);
  }

  function refresh() {
    document.querySelectorAll('.card').forEach(el => {
      const off = removed.has(el.dataset.id);
      el.classList.toggle('off', off);
      el.querySelector('input').checked = !off;
    });
    for (const t of teams) {
      const gone = t.kits.filter(k => removed.has(k.id)).length;
      $('n_' + t.code).textContent = gone
        ? `остаётся ${t.kits.length - gone} из ${t.kits.length}` : `${t.kits.length} форм`;
      $('s_' + t.code).classList.toggle('has', gone > 0);
      $('a_' + t.code).classList.toggle('has', gone > 0);
    }
    for (const g of groups) {
      const mine = all.filter(k => k.group === g.id);
      const gone = mine.filter(k => removed.has(k.id)).length;
      const chip = $('g_' + g.id);
      chip.classList.toggle('part', gone > 0 && gone < mine.length);
      chip.classList.toggle('none', gone === mine.length);
      chip.querySelector('span').textContent = gone ? `${mine.length - gone} из ${mine.length}` : mine.length;
    }
    $('total').innerHTML = `остаётся <b>${all.length - removed.size}</b> · уйдёт <b class="n-drop">${removed.size}</b> из ${all.length}`;
  }

  function card(k) {
    return `<label class="card g-${k.group}${k.locked ? ' locked' : ''}" data-id="${k.id}">
      <input type="checkbox" checked${k.locked ? ' disabled' : ''} aria-label="Оставить ${k.label}, ${k.id}">
      <div class="pic"><img src="${k.img}" alt="" loading="lazy"></div>
      <div class="txt"><div class="lab">${k.label}</div><div class="tag">${titles[k.group]}</div></div>
      <button type="button" class="big" title="Крупнее" aria-label="Показать крупнее">⤢</button>
    </label>`;
  }

  function render() {
    $('nav').innerHTML = teams.map(t => `<a id="a_${t.code}" href="#${t.code}">${t.code}</a>`).join('');
    $('chips').innerHTML = groups.map(g => {
      const locked = all.some(k => k.group === g.id && k.locked);
      return `<button class="chip" id="g_${g.id}" data-g="${g.id}"${locked ? ' disabled' : ''}>${g.title} <span></span></button>`;
    }).join('');
    $('teams').innerHTML = teams.map(t => `<section id="s_${t.code}">
        <a id="${t.code}"></a>
        <h2>${t.code} · ${t.name} <span id="n_${t.code}"></span></h2>
        <div class="grid">${t.kits.map(card).join('')}</div>
      </section>`).join('');
  }

  document.addEventListener('change', e => {
    if (e.target.id === 'only') { document.body.classList.toggle('only-off', e.target.checked); return; }
    const el = e.target.closest('.card');
    if (!el) return;
    if (e.target.checked) removed.delete(el.dataset.id); else removed.add(el.dataset.id);
    changed();
  });

  document.addEventListener('click', e => {
    const big = e.target.closest('.big');
    if (big) {
      e.preventDefault();
      const el = big.closest('.card');
      const k = all.find(x => x.id === el.dataset.id);
      const zoom = $('zoom');
      zoom.querySelector('img').src = k.img;
      $('zoomcap').textContent = `${k.code} · ${k.label} · ${titles[k.group]}`;
      zoom.showModal();
      return;
    }
    if (e.target.id === 'zoom' || e.target.closest('#zoom')) { $('zoom').close(); return; }
    const chip = e.target.closest('.chip');
    if (chip) {
      const mine = all.filter(k => k.group === chip.dataset.g && !k.locked);
      const anyKept = mine.some(k => !removed.has(k.id));
      mine.forEach(k => (anyKept ? removed.add(k.id) : removed.delete(k.id)));
      changed();
    }
  });

  $('save').onclick = () => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(result(), null, 1)], { type: 'application/json' }));
    a.download = 'selection.json';
    a.click();
  };

  async function load() {
    let saved = null;
    if (served) {
      const res = await fetch('selection.json').catch(() => null);
      if (res && res.ok) saved = (await res.json().catch(() => ({}))).remove;
    }
    if (!saved) {
      try { saved = JSON.parse(localStorage.getItem(KEY)); } catch (e) { saved = null; }
    }
    removed = new Set((saved || []).filter(id => free.has(id)));
  }

  render();
  load().then(() => {
    refresh();
    $('save').hidden = served;
    state(served ? 'выбор сохраняется сам' : 'выбор живёт в браузере');
  });
})();
