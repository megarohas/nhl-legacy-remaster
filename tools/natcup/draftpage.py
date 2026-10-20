"""Страница драфта сборной: game/work/natcup/draft-<год>-<страна>.html (локально). Пул — игроки страны из сейва
франшизы (natcup.franchise), состав — QUOTA; травмированные недоступны. «Сохранить» выгружает
natcup_draft.json в «Загрузки» — его читает `natcup roster`.

    python -m natcup.draftpage КОД_СТРАНЫ [СЕЙВ]
"""
import html
import json
import os
import sys

from .franchise import NATIONS, REPO, Franchise

QUOTA = {'C': 4, 'W': 8, 'D': 8, 'G': 3}      # 23 игрока
OUT = os.path.join(REPO, 'game', 'work', 'natcup')

PAGE = r"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Кубок наций — драфт</title>
<style>
:root { --bg:#14161b; --panel:#1d2027; --line:#2b2f38; --text:#e7e9ee; --dim:#9aa1ad; --acc:#4fa3ff; --ok:#3ecf8e;
        --warn:#f2b84b; --bad:#ef6461; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--text); font:14px/1.4 system-ui, "Segoe UI", sans-serif; }
header { padding:16px 20px; border-bottom:1px solid var(--line); display:flex; gap:16px; align-items:baseline; flex-wrap:wrap; }
h1 { margin:0; font-size:20px; } .sub { color:var(--dim); }
main { display:grid; grid-template-columns: 1fr 360px; gap:16px; padding:16px 20px; }
@media (max-width: 900px) { main { grid-template-columns:1fr; } }
.panel { background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:12px; }
.tabs { display:flex; gap:6px; margin-bottom:10px; flex-wrap:wrap; }
.tabs button, .btn { background:#262a33; color:var(--text); border:1px solid var(--line); border-radius:7px; padding:6px 12px;
       cursor:pointer; font:inherit; }
.tabs button.on { background:var(--acc); border-color:var(--acc); color:#06121f; font-weight:600; }
.btn.pri { background:var(--ok); border-color:var(--ok); color:#06150e; font-weight:600; }
table { width:100%; border-collapse:collapse; }
th, td { text-align:left; padding:5px 8px; border-bottom:1px solid var(--line); white-space:nowrap; }
th { color:var(--dim); font-weight:500; position:sticky; top:0; background:var(--panel); }
tr.pick td { color:var(--ok); } tr.inj td { color:var(--bad); opacity:.75; }
tbody tr:not(.inj) { cursor:pointer; } tbody tr:not(.inj):hover { background:#252934; }
.ovr { font-variant-numeric: tabular-nums; font-weight:600; }
.scroll { max-height: calc(100vh - 170px); overflow:auto; }
.q { display:flex; gap:10px; flex-wrap:wrap; margin:6px 0 10px; }
.q span { padding:3px 8px; border-radius:6px; background:#262a33; } .q span.full { background:#173a2a; color:var(--ok); }
.slot { display:flex; justify-content:space-between; padding:4px 6px; border-bottom:1px solid var(--line); cursor:pointer; }
.slot:hover { background:#252934; } .gh { color:var(--dim); margin-top:8px; font-size:12px; text-transform:uppercase; }
.row { display:flex; gap:8px; margin-top:12px; flex-wrap:wrap; } .avg { color:var(--warn); }
</style></head><body>
<header><h1>Кубок наций __YEAR__ — __NATION__</h1><span class="sub">пул: __N__ игроков страны во франшизе · травмированные недоступны</span></header>
<main>
<section class="panel"><div class="tabs" id="tabs"></div><div class="scroll"><table><thead><tr><th>Игрок</th><th>Поз.</th>
<th>OVR</th><th>Клуб</th><th>Возраст</th></tr></thead><tbody id="pool"></tbody></table></div></section>
<aside class="panel"><div><b>Состав</b> <span id="cnt"></span> · средний OVR <span class="avg" id="avg">—</span></div>
<div class="q" id="quota"></div><div id="roster"></div>
<div class="row"><button class="btn" id="auto">Автосостав</button><button class="btn" id="clear">Очистить</button>
<button class="btn pri" id="save">Сохранить</button></div></aside>
</main>
<script>
const DATA = __DATA__;
const QUOTA = __QUOTA__;
const NAMES = {C:"Центры", W:"Крайние", D:"Защитники", G:"Вратари"};
const grp = p => (p.p === "L" || p.p === "R") ? "W" : p.p;
let tab = "ALL"; const pick = new Set();
function count(g) { let n = 0; for (const i of pick) if (grp(DATA.byIdx[i]) === g) n++; return n; }
function toggle(p) {
  if (p.inj > 0) return;
  if (pick.has(p.i)) pick.delete(p.i);
  else { const g = grp(p); if (count(g) >= QUOTA[g]) return; pick.add(p.i); }
  draw();
}
function auto() {
  pick.clear();
  for (const g of Object.keys(QUOTA)) DATA.pool.filter(p => grp(p) === g && !(p.inj > 0)).slice(0, QUOTA[g]).forEach(p => pick.add(p.i));
  draw();
}
function draw() {
  const tabs = document.getElementById("tabs"); tabs.innerHTML = "";
  for (const t of ["ALL", "C", "W", "D", "G"]) {
    const b = document.createElement("button"); b.textContent = t === "ALL" ? "Все" : NAMES[t]; if (t === tab) b.className = "on";
    b.onclick = () => { tab = t; draw(); }; tabs.appendChild(b);
  }
  const tb = document.getElementById("pool"); tb.innerHTML = "";
  for (const p of DATA.pool) {
    if (tab !== "ALL" && grp(p) !== tab) continue;
    const tr = document.createElement("tr");
    if (pick.has(p.i)) tr.className = "pick"; if (p.inj > 0) tr.className = "inj";
    tr.innerHTML = `<td>${p.n}${p.inj > 0 ? " · травма " + p.inj + " дн." : ""}</td><td>${p.p}</td><td class="ovr">${p.o}</td><td>${p.t}</td><td>${p.a}</td>`;
    tr.onclick = () => toggle(p); tb.appendChild(tr);
  }
  const q = document.getElementById("quota"); q.innerHTML = "";
  let total = 0, sum = 0;
  for (const g of Object.keys(QUOTA)) { const n = count(g); total += n;
    const s = document.createElement("span"); s.textContent = `${NAMES[g]} ${n}/${QUOTA[g]}`; if (n === QUOTA[g]) s.className = "full"; q.appendChild(s); }
  const r = document.getElementById("roster"); r.innerHTML = "";
  for (const g of Object.keys(QUOTA)) {
    const h = document.createElement("div"); h.className = "gh"; h.textContent = NAMES[g]; r.appendChild(h);
    DATA.pool.filter(p => pick.has(p.i) && grp(p) === g).forEach(p => { sum += p.o;
      const d = document.createElement("div"); d.className = "slot"; d.innerHTML = `<span>${p.n} · ${p.p}</span><span class="ovr">${p.o}</span>`;
      d.onclick = () => toggle(p); r.appendChild(d); });
  }
  const need = Object.values(QUOTA).reduce((a, b) => a + b, 0);
  document.getElementById("cnt").textContent = `${total}/${need}`;
  document.getElementById("avg").textContent = total ? (sum / total).toFixed(1) : "—";
}
document.getElementById("auto").onclick = auto;
document.getElementById("clear").onclick = () => { pick.clear(); draw(); };
document.getElementById("save").onclick = () => {
  const need = Object.values(QUOTA).reduce((a, b) => a + b, 0);
  if (pick.size !== need) { alert(`Нужно ${need} игроков, выбрано ${pick.size}`); return; }
  const out = {year: DATA.year, country: DATA.country, nation: DATA.nation, save: DATA.save, players: [...pick]};
  const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([JSON.stringify(out, null, 1)], {type: "application/json"}));
  a.download = "natcup_draft.json"; a.click();
};
DATA.byIdx = Object.fromEntries(DATA.pool.map(p => [p.i, p]));
draw();
</script></body></html>
"""


def build(fr, country):
    tid, nation = NATIONS[country]
    year = fr.season_year()
    pool = []
    for p in fr.pool(country):
        by = p['born'][0]
        pool.append({'i': p['index'], 'n': f"{p['first']} {p['last']}", 'p': p['pos'], 'o': p['ovr'],
                     't': fr.team_abbr(p['team']), 'a': year - by, 'inj': p['injury_days']})
    data = {'year': year, 'country': country, 'nation': nation, 'save': os.path.basename(fr.path), 'pool': pool}
    page = (PAGE.replace('__DATA__', json.dumps(data, ensure_ascii=False)).replace('__QUOTA__', json.dumps(QUOTA))
            .replace('__YEAR__', str(year)).replace('__NATION__', html.escape(nation)).replace('__N__', str(len(pool))))
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f'draft-{year}-{nation.replace(" ", "_")}.html')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(page)
    return path


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    code = int(sys.argv[1])
    fr = Franchise.load(sys.argv[2]) if len(sys.argv) > 2 else Franchise.latest()
    print(build(fr, code))
