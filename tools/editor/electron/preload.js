// Окно приложения: файл, брошенный мимо карточки текстуры, не открывается в окне вместо редактора (карточки ловят
// drop сами — tools/editor/web/app.js texCard), страница знает, что она в приложении.
'use strict';
const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('nhlApp', { app: true });
window.addEventListener('dragover', e => e.preventDefault());
window.addEventListener('drop', e => e.preventDefault());
