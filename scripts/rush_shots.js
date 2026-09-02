/* Снимки экранов Wecon Rush для приёмки владельцем.

   Смотреть глазами всё равно придётся — лист только избавляет от ручного
   хождения по режимам и показывает, что именно изменилось за фазу.

   Запуск: node scripts/rush_shots.js <префикс> [порт]
   Пример: node scripts/rush_shots.js phase0 8611                          */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const PREFIX = process.argv[2] || 'shot';
const PORT = process.argv[3] || '8611';
const BASE = 'http://127.0.0.1:' + PORT;
const OUT = path.join('reports', 'game', 'shots');

/* Одна карточка режима на стартовом экране: кликаем её и ждём, пока
   появится первый вопрос. Без ожидания снимок ловит пустой экран. */
async function startRun(p, mode) {
  await p.goto(BASE + '/game/', { waitUntil: 'load' });
  await p.waitForSelector('.mode-card[data-mode="' + mode + '"]', { timeout: 15000 });
  await p.click('.mode-card[data-mode="' + mode + '"]');
  await p.waitForFunction(
    () => {
      const t = document.getElementById('q-text');
      return t && t.textContent.trim().length > 0;
    }, null, { timeout: 15000 });
  await p.waitForTimeout(350);
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1440, height: 950 } });
  const errs = [];
  p.on('pageerror', e => errs.push('[pageerror] ' + e.message));
  p.on('console', m => { if (m.type() === 'error') errs.push('[console] ' + m.text()); });

  const shots = [];
  const shot = async (name) => {
    const f = path.join(OUT, PREFIX + '_' + name + '.png');
    await p.screenshot({ path: f });
    shots.push(f);
  };

  // 1. Стартовый экран.
  await p.goto(BASE + '/game/', { waitUntil: 'load' });
  await p.waitForSelector('.mode-card', { timeout: 15000 });
  await p.waitForTimeout(400);
  const cards = await p.$$eval('.mode-card', els => els.map(e => e.dataset.mode));
  await shot('start');

  // 2. Забег в каждом режиме — по кадру.
  for (const mode of cards) {
    await startRun(p, mode);
    await shot('run_' + mode);
  }

  // 3. Экран результатов: доигрываем блиц до конца пропусками.
  await startRun(p, 'blitz');
  for (let i = 0; i < 80; i++) {
    const state = await p.evaluate(() => {
      const fin = document.getElementById('screen-final');
      const t = document.getElementById('q-text');
      return { done: !!(fin && fin.classList.contains('active')),
               text: t ? t.textContent.trim() : '' };
    });
    if (state.done) break;
    // ⚠️ Ждём СМЕНЫ вопроса, а не «немножко». Пропуск на уже смененном
    // вопросе сервер честно отбивает 404 («Этот вопрос не выдавался») —
    // это анти-чит, а не ошибка, но лог засоряет и снимок врёт.
    await p.keyboard.press('Space');
    await p.waitForFunction(
      (prev) => {
        const fin = document.getElementById('screen-final');
        if (fin && fin.classList.contains('active')) return true;
        const t = document.getElementById('q-text');
        return t && t.textContent.trim() !== prev;
      }, state.text, { timeout: 8000 }).catch(() => {});
  }
  await p.waitForTimeout(700);
  await shot('final');

  await b.close();
  console.log('снимков: ' + shots.length);
  shots.forEach(s => console.log('  ' + s));
  console.log('карточек режимов на старте: ' + cards.length + ' [' + cards.join(', ') + ']');
  if (errs.length) {
    console.log('ОШИБКИ В КОНСОЛИ БРАУЗЕРА (' + errs.length + '):');
    [...new Set(errs)].slice(0, 10).forEach(e => console.log('  ' + e));
    process.exitCode = 1;
  } else {
    console.log('ошибок в консоли браузера нет');
  }
})();
