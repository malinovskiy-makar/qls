/* Проба 1.13: не показывается ли «−1» у таймера в первые секунды забега.

   Владелец видел «−1» сразу при входе в Рапид, хотя сердце не отнималось.
   Здесь это воспроизводится честным путём: сыграть забег, получить дельту,
   выйти, войти снова — и посмотреть на плашку в первые 2 секунды.

   Запуск: node scripts/rush_delta_probe.js [порт]                          */
const { chromium } = require('playwright');

const PORT = process.argv[2] || '8611';
const BASE = 'http://127.0.0.1:' + PORT;

/* Что показывает плашка дельты прямо сейчас: текст, классы и ВИДИМАЯ
   непрозрачность (вычисленная, а не заявленная в стиле). */
async function delta(p) {
  return p.evaluate(() => {
    const c = document.getElementById('time-delta');
    const st = getComputedStyle(c);
    return { text: c.textContent.trim(), cls: c.className,
             opacity: st.opacity, anim: st.animationName };
  });
}

async function lives(p) {
  return p.evaluate(() => {
    const box = document.getElementById('hud-lives');
    return { всего: box.children.length,
             живых: [...box.children].filter(h => !h.classList.contains('lost')).length };
  });
}

async function startRun(p, mode) {
  await p.goto(BASE + '/game/', { waitUntil: 'load' });
  await p.waitForSelector('.mode-card[data-mode="' + mode + '"]', { timeout: 15000 });
  await p.click('.mode-card[data-mode="' + mode + '"]');
  await p.waitForFunction(() => {
    const t = document.getElementById('q-text');
    return t && t.textContent.trim().length > 0;
  }, null, { timeout: 15000 });
}

(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1440, height: 950 } });

  // ── Шаг 1. Чистый вход в Рапид на пустом localStorage.
  await startRun(p, 'rapid');
  await p.waitForTimeout(400);
  console.log('чистый вход в Рапид      :', JSON.stringify(await delta(p)),
              JSON.stringify(await lives(p)));

  // ── Шаг 2. Тот же экран, но ПОСЛЕ забега с потерянной жизнью.
  //    Отвечаем наугад, пока сердце не погаснет.
  await startRun(p, 'blitz');
  let lost = false;
  for (let i = 0; i < 25 && !lost; i++) {
    await p.keyboard.press('1');
    await p.waitForTimeout(1000);
    const l = await lives(p);
    if (l.живых < l.всего) lost = true;
    const fin = await p.evaluate(() =>
      document.getElementById('screen-final').classList.contains('active'));
    if (fin) break;
  }
  console.log('жизнь потеряна в Блице   :', lost);
  console.log('плашка сразу после потери:', JSON.stringify(await delta(p)));

  // ── Шаг 3. Выходим из забега и входим в Рапид — тот самый путь владельца.
  await p.click('#btn-quit');
  await p.waitForTimeout(200);
  await p.click('#quit-yes');
  await p.waitForTimeout(300);
  await p.click('.mode-card[data-mode="rapid"]');
  await p.waitForFunction(() => {
    const t = document.getElementById('q-text');
    return t && t.textContent.trim().length > 0;
  }, null, { timeout: 15000 });

  for (const ms of [100, 400, 900, 1500, 2000]) {
    await p.waitForTimeout(ms === 100 ? 100 : 300);
    const d = await delta(p);
    console.log('Рапид после Блица, ' + String(ms).padStart(4) + ' мс:',
                JSON.stringify(d), JSON.stringify(await lives(p)));
  }
  await p.screenshot({ path: 'reports/game/shots/phase1_bug113_rapid_hud.png' });

  await b.close();
})();
