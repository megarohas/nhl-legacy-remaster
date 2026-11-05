// NHL Legacy Remaster — Editor: окно приложения (Electron) поверх сервера редактора (Python, tools/editor/app.py
// --app-mode). Раскладка в папке игры (docs/editor.md, «Приложение»):
//   <игра>\editor\NHL Legacy Editor.exe            этот Electron (переименован, иконка и сведения — rcedit)
//   <игра>\editor\resources\app\                    package.json, main.js, preload.js, icon.ico
//   <игра>\editor\backend\nhllegacy_editor_server.exe   сервер (PyInstaller)
// Сервер запускается скрыто, на случайном порту и с ключом сессии; окно закрыто — сервер завершается (и сам следит за
// этим процессом: --parent-pid). Диалоги «Выгрузить/Импортировать» сервер просит у окна строкой «@@NHL {…}» в stdout,
// ответ — строкой в его stdin (winui.BRIDGE). Один экземпляр: второй запуск выводит вперёд уже открытое окно.
'use strict';
const { app, BrowserWindow, dialog, Menu, shell } = require('electron');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const { spawn } = require('child_process');

const APP_DIR = path.dirname(process.execPath);                          // <игра>\editor
const GAME_DIR = process.env.NHL_EDITOR_INSTALL || path.dirname(APP_DIR);  // <игра>
const TITLE = 'NHL Legacy Remaster — Editor';
const argLang = (process.argv.find(a => a.startsWith('--lang=')) || '').slice(7);

app.setPath('userData', path.join(GAME_DIR, 'cache', 'editor', 'app'));   // профиль Chromium — в папке игры
app.setName(TITLE);
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  start();
}

function settingsFile() {
  const s = path.join(GAME_DIR, 'saves', 'settings');
  return fs.existsSync(path.join(GAME_DIR, 'saves')) ? path.join(s, 'nhllegacy_editor_window.json')
    : path.join(app.getPath('userData'), 'window.json');
}
function loadBounds() {
  try { return JSON.parse(fs.readFileSync(settingsFile(), 'utf8')); } catch (e) { return null; }
}
// Размер и место запоминаются, только когда их меняет пользователь — после того как окно показано и улеглось.
// Если перезаписывать их при каждом закрытии, окно при дробном масштабе Windows (125 %) росло на 4–5 точек за запуск:
// размер, заданный при создании, Windows/Chromium округляют в большую сторону (проверено 05.11.2026).
let normal = null;                     // последнее положение и размер не развёрнутого окна
function trackBounds(win) {
  if (win.isMaximized() || win.isMinimized() || win.isFullScreen()) return;
  const b = win.getBounds(), c = win.getContentSize();
  normal = { x: b.x, y: b.y, width: c[0], height: c[1] };
}
function saveBounds(win) {
  try {
    const f = settingsFile();
    fs.mkdirSync(path.dirname(f), { recursive: true });
    if (!normal) trackBounds(win);     // первый запуск — записать как есть
    if (normal) fs.writeFileSync(f, JSON.stringify({ ...normal, maximized: win.isMaximized() }, null, 1));
  } catch (e) { /* не важно */ }
}

function backendCommand() {
  // NHL_EDITOR_BACKEND — для разработки: «путь\python.exe;путь\tools\editor» (сервер из репозитория)
  const dev = process.env.NHL_EDITOR_BACKEND;
  if (dev) { const [py, script] = dev.split(';'); return [py, [script]]; }
  return [path.join(APP_DIR, 'backend', 'nhllegacy_editor_server.exe'), []];
}

function page(title, text, extra) {
  const html = `<!DOCTYPE html><meta charset="utf-8"><title>${TITLE}</title><body style="margin:0;height:100vh;display:flex;
    align-items:center;justify-content:center;background:#14171c;color:#e6e9ee;font:15px 'Segoe UI',sans-serif">
    <div style="max-width:760px;padding:24px"><h2 style="margin:0 0 10px">${title}</h2><div style="white-space:pre-wrap;
    color:#c8cfd9">${text}</div>${extra || ''}</div></body>`;
  return 'data:text/html;charset=utf-8,' + encodeURIComponent(html);
}

function start() {
  let win = null, child = null, quitting = false, stderr = '';
  const token = crypto.randomBytes(16).toString('hex');
  const ru = (argLang || 'ru') === 'ru';

  app.on('second-instance', () => {
    if (!win) return;
    if (win.isMinimized()) win.restore();
    win.show();
    win.focus();
  });

  app.whenReady().then(() => {
    Menu.setApplicationMenu(null);
    const b = loadBounds();
    win = new BrowserWindow({
      title: TITLE, useContentSize: true, width: (b && b.width) || 1500, height: (b && b.height) || 900,
      x: b ? b.x : undefined, y: b ? b.y : undefined,
      minWidth: 1000, minHeight: 640, backgroundColor: '#14171c', show: false, autoHideMenuBar: true,
      icon: path.join(__dirname, 'icon.ico'),
      webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false, sandbox: true },
    });
    if (b && b.maximized) win.maximize();
    win.on('page-title-updated', e => e.preventDefault());
    win.once('ready-to-show', () => win.show());
    win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    win.webContents.on('will-navigate', (e, url) => { if (!url.startsWith('http://127.0.0.1:')) e.preventDefault(); });
    if (b) normal = { x: b.x, y: b.y, width: b.width, height: b.height };
    let settled = false;
    win.once('show', () => setTimeout(() => { settled = true; }, 1500));
    win.on('resize', () => { if (settled) trackBounds(win); });
    win.on('move', () => { if (settled) trackBounds(win); });
    win.on('close', () => saveBounds(win));
    win.on('closed', () => { win = null; app.quit(); });
    win.loadURL(page(ru ? 'Запуск редактора…' : 'Starting the editor…', ru ? 'Сервер редактора готовит разделы и имена.' : 'The editor server is preparing sections and names.'));

    const [exe, pre] = backendCommand();
    const args = [...pre, '--app-mode', '--install', GAME_DIR, '--token', token, '--parent-pid', String(process.pid)];
    if (argLang) args.push('--lang', argLang);
    try {
      child = spawn(exe, args, { windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'], cwd: GAME_DIR,
        env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUNBUFFERED: '1' } });
    } catch (e) {
      win.loadURL(page(ru ? 'Сервер редактора не запустился' : 'The editor server did not start', String(e)));
      return;
    }
    let buf = '';
    child.stdout.setEncoding('utf8');
    child.stdout.on('data', d => {
      buf += d;
      let i;
      while ((i = buf.indexOf('\n')) >= 0) {
        const line = buf.slice(0, i).replace(/\r$/, '');
        buf = buf.slice(i + 1);
        onLine(line);
      }
    });
    child.stderr.setEncoding('utf8');
    child.stderr.on('data', d => { stderr = (stderr + d).slice(-4000); });
    child.on('exit', code => {
      child = null;
      if (quitting || !win) return;
      const log = path.join(GAME_DIR, 'cache', 'editor', 'editor.log');
      win.loadURL(page(ru ? 'Сервер редактора остановился' : 'The editor server stopped',
        (ru ? `Код выхода ${code}. Журнал: ${log}\n\n` : `Exit code ${code}. Log: ${log}\n\n`) + stderr.replace(/</g, '&lt;'),
        `<p><a href="#" onclick="location.href='nhl://restart';return false" style="color:#8fc0ff">${ru ? 'Перезапустить' : 'Restart'}</a></p>`));
    });
    win.webContents.on('will-navigate', (e, url) => {
      if (url === 'nhl://restart') { e.preventDefault(); app.relaunch(); app.exit(0); }
    });

    function onLine(line) {
      const m = line.match(/^READY (\d+)/);
      if (m) {
        const lang = argLang || '';
        win.loadURL(`http://127.0.0.1:${m[1]}/?token=${token}${lang ? '&lang=' + lang : ''}`);
        return;
      }
      if (line.startsWith('@@NHL ')) {
        let req;
        try { req = JSON.parse(line.slice(6)); } catch (e) { return; }
        answer(req).then(p => {        // ответ — ASCII (\uXXXX): путь с кириллицей доходит при любой кодировке канала
          const js = JSON.stringify({ id: req.id, path: p || null }).replace(/[\u0080-￿]/g, c => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'));
          if (child) child.stdin.write(js + '\n');
        });
      }
    }

    async function answer(req) {
      const d = req.dialog || {};
      const opt = { title: d.title || TITLE };
      if (d.start) opt.defaultPath = d.name ? path.join(d.start, d.name) : d.start;
      else if (d.name) opt.defaultPath = d.name;
      if (d.filters && d.filters.length) opt.filters = d.filters;
      if (d.kind === 'folder') {
        const r = await dialog.showOpenDialog(win, { ...opt, properties: ['openDirectory', 'createDirectory'] });
        return r.canceled ? null : r.filePaths[0];
      }
      if (d.kind === 'open') {
        const r = await dialog.showOpenDialog(win, { ...opt, properties: ['openFile'] });
        return r.canceled ? null : r.filePaths[0];
      }
      if (d.kind === 'save') {
        const r = await dialog.showSaveDialog(win, opt);
        return r.canceled ? null : r.filePath;
      }
      if (d.kind === 'message') {
        await dialog.showMessageBox(win, { type: d.error ? 'error' : 'info', title: d.title || TITLE, message: d.text || '' });
        return null;
      }
      if (d.kind === 'open_path' && d.path) { shell.openPath(d.path); return null; }
      return null;
    }
  });

  app.on('before-quit', () => { quitting = true; });
  app.on('will-quit', () => { if (child) { try { child.kill(); } catch (e) { /* */ } } });
  app.on('window-all-closed', () => app.quit());
}
