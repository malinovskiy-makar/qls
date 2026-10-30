// Визуальный прибор ночи 30.10: настоящие страницы сайта на 1280 и 390, светлая и тёмная тема.
// Основа — tools/check.mjs дизайнера (те же правила вылезания и наезда), плюс:
//   • кнопки, ссылки-кнопки и поля ниже 44 px на ширине 390;
//   • ошибки консоли браузера.
// Запуск: node screens_probe.mjs <этап> <имя>=<путь> [<имя>=<путь> ...] [--login=<user>:<pass>] [--js=<код до снимка>]
//   node screens_probe.mjs E2 vseros=/olympiads/vseros/ spbgu=/olympiads/spbgu/
// Снимки — shots/<этап>/<имя>.<ширина>.<тема>.png. Итог — «ИТОГО: ... проблем N» и код возврата.
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from '../../../node_modules/playwright/index.mjs';

const BASE = process.env.PROBE_BASE || 'http://127.0.0.1:8097';
const args = process.argv.slice(2);
const stage = args.shift();
const opts = Object.fromEntries(args.filter(a => a.startsWith('--')).map(a => { const [k, ...v] = a.slice(2).split('='); return [k, v.join('=')]; }));
const pages = args.filter(a => !a.startsWith('--')).map(a => { const i = a.indexOf('='); return [a.slice(0, i), a.slice(i + 1)]; });
const OUT = path.resolve(new URL('../shots/' + stage, import.meta.url).pathname);
fs.mkdirSync(OUT, { recursive: true });

const PROBE = (phone) => {
  const W = document.documentElement.clientWidth;
  const out = { overflow: [], outside: [], overlap: [], small: [] };
  const name = (el) => {
    const t = (el.innerText || el.textContent || el.value || '').trim().replace(/\s+/g, ' ').slice(0, 50);
    return `<${el.tagName.toLowerCase()}${el.className && typeof el.className === 'string' ? ' .' + el.className.trim().split(/\s+/).join('.') : ''}> «${t}»`;
  };
  // Содержимое закрытого <details> не нарисовано — его не меряем (кроме самой <summary>).
  const hidden = (el) => { for (let e = el; e; e = e.parentElement) { const cs = getComputedStyle(e); if (cs.display === 'none' || cs.visibility === 'hidden') return true; if (e.parentElement && e.parentElement.tagName === 'DETAILS' && !e.parentElement.open && e.tagName !== 'SUMMARY') return true; } return false; };
  const inScrollBox = (el) => { for (let e = el.parentElement; e && e !== document.body; e = e.parentElement) { const ox = getComputedStyle(e).overflowX; if (ox === 'auto' || ox === 'scroll') return true; } return false; };
  // Проверяется содержимое страницы раздела — шапка и подвал сайта общие и не наши.
  const scope = document.querySelector('.om') || document.body;
  for (const el of scope.querySelectorAll('*')) {
    if (el.closest('svg') && el.tagName.toLowerCase() !== 'svg') continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || hidden(el)) continue;
    if (el.classList.contains('sr-only')) continue;
    const scrolls = cs.overflowX === 'auto' || cs.overflowX === 'scroll';
    const ellipsis = cs.textOverflow === 'ellipsis' && cs.overflowX === 'hidden';
    if (cs.display !== 'inline' && el.clientWidth > 0) {
      if (el.scrollWidth > el.clientWidth + 1 && !scrolls && !ellipsis)
        out.overflow.push({ el: name(el), sw: el.scrollWidth, cw: el.clientWidth, kind: 'ширина' });
      if (scrolls && el.scrollWidth > el.clientWidth + 1 && !el.hasAttribute('data-scroll'))
        out.overflow.push({ el: name(el), sw: el.scrollWidth, cw: el.clientWidth, kind: 'прокрутка' });
    }
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.height > 0 && !inScrollBox(el) && (r.right > W + 0.5 || r.left < -0.5))
      out.outside.push({ el: name(el), left: Math.round(r.left), right: Math.round(r.right), W });
    if (phone && r.width > 0 && r.height > 0) {
      const tag = el.tagName.toLowerCase();
      const control = tag === 'button' || tag === 'select' || tag === 'textarea'
        || (tag === 'input' && !['hidden', 'file'].includes(el.type))
        || (tag === 'a' && (el.classList.contains('k-btn') || el.classList.contains('om-cell') || el.closest('.om-seg') || el.classList.contains('ph-link')))
        || tag === 'summary';
      if (control && r.height < 43.5) out.small.push({ el: name(el), h: Math.round(r.height) });
    }
  }
  if (document.documentElement.scrollWidth > W + 1) out.outside.push({ el: 'документ', left: 0, right: document.documentElement.scrollWidth, W });
  const labels = [...document.querySelectorAll('.om-bl, .om-today-l')].filter(el => !hidden(el));
  for (let i = 0; i < labels.length; i++) for (let j = i + 1; j < labels.length; j++) {
    const a = labels[i].getBoundingClientRect(), b = labels[j].getBoundingClientRect();
    if (a.left < b.right - 0.5 && b.left < a.right - 0.5 && a.top < b.bottom - 0.5 && b.top < a.bottom - 0.5)
      out.overlap.push({ a: name(labels[i]), b: name(labels[j]) });
  }
  return out;
};

const browser = await chromium.launch();
let total = 0;
const report = [];
for (const [width, height] of [[1280, 900], [390, 844]]) {
  for (const theme of ['light', 'dark']) {
    const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1 });
    // Окно cookie закрыто выбором «только необходимые» — иначе полоса ложится на снимок.
    await context.addCookies([{ name: 'weco_consent', value: 'necessary', url: BASE }]);
    await context.addInitScript((t) => { try { localStorage.setItem('theme', t); } catch (e) {} }, theme);
    const page = await context.newPage();
    const errors = [];
    page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
    page.on('pageerror', e => errors.push(String(e)));
    // --login-file=<файл «логин:пароль»> — пароль не попадает в командную строку.
    const login = opts['login-file'] ? fs.readFileSync(opts['login-file'], 'utf8').trim() : opts.login;
    if (login) {
      const [user, pass] = login.split(':');
      await page.goto(BASE + '/login/');
      await page.fill('input[name="username"]', user);
      await page.fill('input[name="password"]', pass);
      await Promise.all([page.waitForLoadState('networkidle'), page.click('form [type="submit"]')]);
    }
    for (const [nameKey, url] of pages) {
      errors.length = 0;
      const response = await page.goto(BASE + url, { waitUntil: 'networkidle' });
      await page.evaluate(() => document.fonts.ready);
      if (opts.js) await page.evaluate(opts.js);
      const res = await page.evaluate(PROBE, width < 500);
      const status = response ? response.status() : 0;
      const bad = (status >= 400 ? 1 : 0);
      const n = res.overflow.length + res.outside.length + res.overlap.length + res.small.length + errors.length + bad;
      total += n;
      report.push({ name: nameKey, url, width, theme, status, problems: n, ...res, errors: [...errors] });
      await page.screenshot({ path: path.join(OUT, `${nameKey}.${width}.${theme}.png`), fullPage: true });
    }
    await context.close();
  }
}
await browser.close();
fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify(report, null, 1));
for (const r of report) {
  console.log(`${r.problems === 0 ? 'ок ' : 'ПЛОХО'} ${r.name.padEnd(16)} ${String(r.width).padEnd(4)} ${r.theme.padEnd(5)} ${r.status} вылезаний ${r.overflow.length}, за краем ${r.outside.length}, наездов ${r.overlap.length}, мелких ${r.small.length}, ошибок консоли ${r.errors.length}`);
  for (const o of r.overflow) console.log(`      вылезание (${o.kind}) ${o.sw} > ${o.cw}: ${o.el}`);
  for (const o of r.outside.slice(0, 8)) console.log(`      за краем ${o.left}…${o.right} при ширине ${o.W}: ${o.el}`);
  for (const o of r.overlap) console.log(`      наезд: ${o.a} × ${o.b}`);
  for (const o of r.small.slice(0, 8)) console.log(`      ниже 44 px (${o.h}): ${o.el}`);
  for (const e of r.errors) console.log(`      консоль: ${e}`);
}
console.log(`ИТОГО: страниц ${pages.length}, прогонов ${report.length}, проблем ${total}`);
process.exitCode = total ? 1 : 0;
