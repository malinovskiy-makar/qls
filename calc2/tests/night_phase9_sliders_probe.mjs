/* Ночная сессия. ФАЗА 9 — ползунки сдвига: подпись, центр, выравнивание.
     node calc2/tests/night_phase9_sliders_probe.mjs */
import { chromium } from 'playwright';
const BASE = process.env.CALC2_BASE_URL || 'http://127.0.0.1:8099';
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
const errs = []; page.on('pageerror', e => errs.push(e.message));
await page.goto(`${BASE}/login/`, { waitUntil: 'networkidle' });
await page.fill('#id_username', process.env.CALC2_USER || 'admin');
await page.fill('#id_password', process.env.CALC2_PASS || 'admin12345');
await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle' }), page.click('button[type=submit]')]);
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);
let ok = true;
const rep = (n, pass, d) => { console.log((pass ? 'OK  ' : 'FAIL') + ' ' + n + (d ? '  -> ' + d : '')); if (!pass) ok = false; };

const r = await page.evaluate(async () => {
  const wait = ms => new Promise(res => setTimeout(res, ms));
  const out = {};
  resetSceneMemory(); pickScene('sd'); await wait(500);
  const chips = () => [...document.querySelectorAll('#params-curves .pchip')];
  const eqText = () => chips().map(c => (c.querySelector('.reg-eq') || {}).textContent || '');
  out.labels = eqText();
  out.hasKatex = chips().map(c => !!(c.querySelector('.reg-eq .katex')));
  out.sliders = chips().map(c => {
    const s = c.querySelector('input[type=range]');
    return { min: +s.min, max: +s.max, value: +s.value,
             centered: Math.abs((+s.value - (+s.min + +s.max) / 2)) < 1e-6 };
  });
  out.bStart = STATE.curves.map(c => c.linear && c.linear.b);
  // Протяжка ползунка спроса на +20 обязана сдвинуть кривую, а не задать b=20.
  const sl = chips()[0].querySelector('input[type=range]');
  sl.value = 20; sl.dispatchEvent(new Event('input', { bubbles: true }));
  await wait(350);
  out.afterDrag = { b: STATE.curves[0].linear.b, label: (chips()[0].querySelector('.reg-eq') || {}).textContent };
  sl.value = 0; sl.dispatchEvent(new Event('input', { bubbles: true }));
  await wait(300);
  out.backToZero = STATE.curves[0].linear.b;

  // Выравнивание: левый край дорожки у ВСЕХ ползунков панели (кривые + буквы + регуляторы)
  const measure = () => {
    /* Только ВИДИМЫЕ дорожки. В правой панели с недавних пор живёт и блок
       вмешательства государства, а в нём спрятано поле неактивного
       инструмента: у скрытого элемента рамка нулевая, и он портил бы замер. */
    const rows = [...document.querySelectorAll('#params-panel .param-track')]
      .filter(t => t.offsetParent !== null && t.getBoundingClientRect().width > 0);
    return rows.map(t => {
      const s = t.querySelector('input[type=range]');
      return { left: Math.round(s.getBoundingClientRect().left * 100) / 100,
               bound: (t.querySelector('.param-bound') || {}).textContent };
    });
  };
  /* Богатая панель: сдвиги кривых (−50…50), регулятор ставки (0…100) и буква
     из формулы (−10…10). Разрядность границ у них РАЗНАЯ — ради этого случая
     правка и делалась. Сцена «Пол и потолок цены»: два сдвига кривых и
     регулируемая цена, границы «−50», «50», «0», «100». */
  resetSceneMemory(); pickScene('ceil'); await wait(600);
  out.tracksPlain = measure();
  const inp = document.querySelector('#curve-list .curve-expr-inp');
  inp.value = '100 - a*Q'; inp.dispatchEvent(new Event('input', { bubbles: true }));
  await wait(700);
  redrawAll(); await wait(500);
  out.tracks = measure();
  return out;
});
console.log(JSON.stringify(r, null, 1));
rep('подпись называет сдвиг, а не значение кривой',
    r.labels.length >= 2 && r.labels.every(t => /Сдвиг/.test(t)), JSON.stringify(r.labels));
rep('буква кривой набрана формулой (KaTeX)', r.hasKatex.every(Boolean), JSON.stringify(r.hasKatex));
rep('ползунок стартует в середине своего диапазона',
    r.sliders.length >= 2 && r.sliders.every(s => s.centered), JSON.stringify(r.sliders));
rep('на старте сдвиг равен нулю', r.labels.every(t => /=\s*0$/.test(t.replace(/\s+/g, ' ').trim())),
    JSON.stringify(r.labels));
rep('сдвиг +20 двигает кривую, а не задаёт b=20',
    Math.abs(r.afterDrag.b - (r.bStart[0] + 20)) < 1e-6,
    'b было ' + r.bStart[0] + ', стало ' + r.afterDrag.b + ', подпись «' + r.afterDrag.label + '»');
rep('возврат ползунка в центр возвращает кривую', Math.abs(r.backToZero - r.bStart[0]) < 1e-6,
    'b=' + r.backToZero);
[['без буквы', r.tracksPlain], ['с буквой в формуле', r.tracks]].forEach(([what, tr]) => {
  const lefts = tr.map(t => t.left);
  const uniq = [...new Set(lefts)];
  rep('левый край дорожки совпадает у всех ползунков панели (' + what + ')',
      tr.length >= 2 && uniq.length === 1,
      'дорожек ' + lefts.length + ', разных координат ' + uniq.length + ': ' + uniq.join(', ')
        + ' | границы: ' + tr.map(t => t.bound).join(', '));
});
if (errs.length) rep('без ошибок страницы', false, errs.slice(0, 3).join(' | '));
await browser.close();
console.log('\nИТОГ: ' + (ok ? 'ползунки подписаны честно, стоят по центру и выровнены' : 'ЕСТЬ ПРОБЛЕМА'));
process.exit(ok ? 0 : 1);
