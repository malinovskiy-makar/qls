/* Проба фазы 2: тревога на экране.

   Снимки нужны для приёмки глазами, но глазами не проверить главное —
   что прозрачная сердцевина виньетки НАКРЫВАЕТ карточку вопроса и
   варианты. Это здесь считается числами.

   Время не подкручиваем: ждём по-настоящему, иначе проверялась бы
   заглушка, а не игра.

   Запуск: node scripts/rush_alarm_probe.js [порт]                        */
const { chromium } = require('playwright');
const path = require('path');

const PORT = process.argv[2] || '8611';
const BASE = 'http://127.0.0.1:' + PORT;
const OUT = path.join('reports', 'game', 'shots');

async function startRun(p, mode) {
  await p.goto(BASE + '/game/', { waitUntil: 'load' });
  await p.waitForSelector('.mode-card[data-mode="' + mode + '"]', { timeout: 15000 });
  await p.click('.mode-card[data-mode="' + mode + '"]');
  await p.waitForFunction(() => {
    const t = document.getElementById('q-text');
    return t && t.textContent.trim().length > 0;
  }, null, { timeout: 15000 });
}

/* Что сейчас на экране: тревога, размеры овала, покрытие карточки. */
async function state(p) {
  return p.evaluate(() => {
    const v = document.getElementById('vignette');
    const sc = document.querySelector('#screen-play .scene');
    const card = document.getElementById('q-card');
    const opts = document.getElementById('opts') || document.querySelector('.opts');
    const cs = getComputedStyle(v);
    const alarm = parseFloat(
      getComputedStyle(document.documentElement).getPropertyValue('--alarm') || '0');
    const rx = parseFloat(v.style.getPropertyValue('--al-rx')) || 0;
    const ry = parseFloat(v.style.getPropertyValue('--al-ry')) || 0;
    // Прозрачная зона градиента кончается на 55 % радиуса.
    const clearX = rx * 0.55, clearY = ry * 0.55;
    const cx = window.innerWidth / 2, cy = window.innerHeight / 2;
    function covered(el) {
      if (!el) return null;
      const r = el.getBoundingClientRect();
      if (!r.width) return null;
      // Самый дальний угол блока от центра экрана — по нему и судим.
      const dx = Math.max(Math.abs(r.left - cx), Math.abs(r.right - cx));
      const dy = Math.max(Math.abs(r.top - cy), Math.abs(r.bottom - cy));
      // Точка внутри эллипса, если (dx/a)^2 + (dy/b)^2 <= 1.
      const k = (dx / clearX) ** 2 + (dy / clearY) ** 2;
      return { dx: Math.round(dx), dy: Math.round(dy), k: +k.toFixed(3) };
    }
    return {
      alarm: +alarm.toFixed(3),
      alarmClass: v.classList.contains('alarm'),
      timer: document.getElementById('hud-timer').textContent,
      timerColor: getComputedStyle(document.getElementById('hud-timer')).color,
      barColor: getComputedStyle(document.getElementById('time-fill')).backgroundColor,
      lives: [...document.getElementById('hud-lives').children]
        .filter(h => !h.classList.contains('lost')).length,
      rx: Math.round(rx), ry: Math.round(ry),
      clearX: Math.round(clearX), clearY: Math.round(clearY),
      sceneW: sc ? Math.round(sc.getBoundingClientRect().width) : 0,
      cardCovered: covered(card),
      optsCovered: covered(opts),
      hasBeatListener: typeof window.rushSound === 'object',
      bpm: window.rushSound && window.rushSound.heartbeat
        ? window.rushSound.heartbeat.bpm() : null,
      hbOn: window.rushSound && window.rushSound.heartbeat
        ? window.rushSound.heartbeat.isOn() : null,
      vignetteBg: cs.backgroundImage.slice(0, 60),
    };
  });
}

/* Дождаться, пока на таймере станет не больше `sec` секунд. */
async function waitUntil(p, sec) {
  await p.waitForFunction((s) => {
    const t = document.getElementById('hud-timer').textContent
      .replace(',', '.').replace(/[^\d.]/g, '');
    return parseFloat(t) <= s;
  }, sec, { timeout: 200000, polling: 250 });
}

(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1440, height: 950 } });
  const errs = [];
  p.on('pageerror', e => errs.push('[pageerror] ' + e.message));

  // Считаем удары сердца, пришедшие в страницу.
  await p.addInitScript(() => {
    window.__beats = 0;
    window.addEventListener('rush:beat', () => { window.__beats++; });
  });

  // ── 1. Блиц, спокойное состояние.
  await startRun(p, 'blitz');
  await p.waitForTimeout(500);
  console.log('спокойно   :', JSON.stringify(await state(p)));

  // ── 2. Блиц при 8 с (тревога уже идёт: окно 10 % от 120 = 12 с).
  await waitUntil(p, 8);
  const at8 = await state(p);
  console.log('при 8 с    :', JSON.stringify(at8));
  await p.screenshot({ path: path.join(OUT, 'phase2_blitz_8s.png') });

  // ── 3. Блиц при 2 с.
  await waitUntil(p, 2.2);
  const at2 = await state(p);
  console.log('при 2 с    :', JSON.stringify(at2));
  await p.screenshot({ path: path.join(OUT, 'phase2_blitz_2s.png') });
  console.log('ударов сердца пришло:', await p.evaluate(() => window.__beats));

  // ── 4. Последняя жизнь при полном запасе времени.
  await startRun(p, 'blitz');
  for (let i = 0; i < 30; i++) {
    const l = await p.evaluate(() =>
      [...document.getElementById('hud-lives').children]
        .filter(h => !h.classList.contains('lost')).length);
    if (l <= 1) break;
    const fin = await p.evaluate(() =>
      document.getElementById('screen-final').classList.contains('active'));
    if (fin) { await startRun(p, 'blitz'); continue; }
    await p.keyboard.press('1');
    await p.waitForTimeout(1100);
  }
  const last = await state(p);
  console.log('последняя жизнь:', JSON.stringify(last));
  await p.screenshot({ path: path.join(OUT, 'phase2_last_life.png') });

  // ── Приговор по числам.
  const checks = [];
  const ok = (c, what) => checks.push((c ? 'ОК   ' : 'ПЛОХО') + '  ' + what);
  ok(at8.alarmClass && at8.alarm > 0 && at8.alarm < 1, 'при 8 с тревога идёт и не в максимуме');
  ok(at2.alarm > at8.alarm, 'к 2 с тревога выросла');
  ok(at8.cardCovered && at8.cardCovered.k <= 1,
     'карточка вопроса внутри прозрачной зоны (k=' + (at8.cardCovered || {}).k + ')');
  ok(at8.optsCovered && at8.optsCovered.k <= 1,
     'варианты внутри прозрачной зоны (k=' + (at8.optsCovered || {}).k + ')');
  ok(last.alarm > 0 && last.lives === 1, 'последняя жизнь поднимает тревогу');
  ok(Math.abs(last.bpm - 70) <= 1, 'на последней жизни темп 70 (получено ' + last.bpm + ')');
  ok(at8.timerColor !== last.timerColor || at8.timerColor.length > 0, 'цвет таймера считается');
  console.log('\n' + checks.join('\n'));

  await b.close();
  if (errs.length) {
    console.log('ОШИБКИ СТРАНИЦЫ:', [...new Set(errs)].slice(0, 5).join(' | '));
    process.exitCode = 1;
  }
  if (checks.some(c => c.startsWith('ПЛОХО'))) process.exitCode = 1;
})();
