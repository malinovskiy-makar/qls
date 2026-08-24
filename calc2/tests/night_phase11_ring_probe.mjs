/* Ночная сессия. ФАЗА 11 — рамка (кольцо фокуса) на первой карточке.
   Сначала ВОСПРОИЗВЕДЕНИЕ, потом уже решение: чинить или доложить замер.
     node calc2/tests/night_phase11_ring_probe.mjs */
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

const ring = () => page.evaluate(() => {
  const p = document.getElementById('scene-picker');
  const first = p.querySelector('.bcard') || p.querySelector('.scard:not([disabled])');
  const act = document.activeElement;
  const cs = first ? getComputedStyle(first) : null;
  const acs = act ? getComputedStyle(act) : null;
  const has = (el, s) => el && s && s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0;
  return {
    firstCls: first ? first.className : null,
    firstFocused: act === first,
    focusVisible: first ? first.matches(':focus-visible') : null,
    firstRing: has(first, cs), firstOutline: cs ? cs.outlineStyle + ' ' + cs.outlineWidth : null,
    active: act ? (act.tagName + '.' + (act.className || '').split(' ')[0]) : null,
    activeRing: has(act, acs), activeCls: act ? act.className : null,
  };
});

let ok = true;
const rep = (n, pass, d) => { console.log((pass ? 'OK  ' : 'FAIL') + ' ' + n + (d ? '  -> ' + d : '')); if (!pass) ok = false; };

console.log('══ 1. Первый экран сразу после загрузки ═══════════════════════');
await page.goto(`${BASE}/calc2/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);
const s0 = await ring(); console.log(JSON.stringify(s0));
rep('сразу после загрузки кольца на первой карточке нет', !s0.firstRing, s0.firstOutline);

console.log('\n══ 2. Щелчок по пустому месту страницы ════════════════════════');
await page.mouse.click(720, 880);          // низ экрана, мимо карточек
await page.waitForTimeout(350);
const s1 = await ring(); console.log(JSON.stringify(s1));
rep('после щелчка по пустому месту кольца на карточке нет', !s1.firstRing, s1.firstOutline);
rep('после щелчка фокус с карточки ушёл', !s1.firstFocused, 'фокус на ' + s1.active);

console.log('\n══ 3. Возврат к выбору внутри блока (открывается .scard) ══════');
await page.evaluate(() => { resetSceneMemory(); pickScene('sd'); });
await page.waitForTimeout(500);
await page.evaluate(() => openPicker());
await page.waitForTimeout(500);
const s2 = await page.evaluate(() => {
  const p = document.getElementById('scene-picker');
  const g = p.querySelector('.picker-group.open');
  const first = g ? g.querySelector('.scard:not([disabled])') : null;
  const cs = first ? getComputedStyle(first) : null;
  return {
    cls: first ? first.className : null,
    focused: document.activeElement === first,
    focusVisible: first ? first.matches(':focus-visible') : null,
    outline: cs ? cs.outlineStyle + ' ' + cs.outlineWidth : null,
    ring: !!(cs && cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0),
  };
});
console.log(JSON.stringify(s2));
rep('у первой карточки внутри блока кольца тоже нет', !s2.ring,
    'класс «' + s2.cls + '», обводка ' + s2.outline + ', :focus-visible ' + s2.focusVisible);

console.log('\n══ 4. Клавиатура кольцо возвращает ═══════════════════════════');
/* Кольцо на карточке гасится только ДО первого действия человека. Ставим
   фокус на карточку из-под клавиатуры (Tab внутри окна выбора) и смотрим,
   что браузер снова решает сам. */
await page.evaluate(() => {
  /* Именно ВИДИМУЮ карточку: когда блок раскрыт, плитки блоков спрятаны, и
     focus() на спрятанной кнопке молча не срабатывает — фокус остаётся на
     body, и проба мерила бы не то. */
  const p = document.getElementById('scene-picker');
  const c = [...p.querySelectorAll('.bcard, .scard:not([disabled])')].find(x => x.offsetParent);
  if (c) c.focus();
});
await page.keyboard.press('Tab');
await page.waitForTimeout(250);
const s3 = await page.evaluate(() => {
  const a = document.activeElement, cs = a ? getComputedStyle(a) : null;
  return { active: a ? a.tagName + '.' + (a.className || '').split(' ')[0] : null,
           focusVisible: a && a.matches ? a.matches(':focus-visible') : null,
           outline: cs ? cs.outlineStyle + ' ' + cs.outlineWidth : null,
           ring: !!(cs && cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0) };
});
console.log(JSON.stringify(s3));
rep('по Tab кольцо появляется — доступность не сломана', s3.ring, JSON.stringify(s3));
if (errs.length) rep('без ошибок страницы', false, errs.slice(0, 3).join(' | '));
await browser.close();
console.log('\nИТОГ: ' + (ok ? 'кольцо появляется только от клавиатуры — гипотеза Фазы 11 НЕ подтвердилась'
                             : 'ЕСТЬ ПРОБЛЕМА'));
process.exit(ok ? 0 : 1);
