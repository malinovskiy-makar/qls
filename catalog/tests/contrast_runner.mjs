/* Контраст текста каталога по WCAG в обеих темах (решение владельца 17.09.2026).

   Раннер обходит страницы в Chromium, в светлой и тёмной теме, и для каждого
   видимого текстового элемента считает контраст между цветом текста и
   фактическим фоном — ближайшим предком с непрозрачным фоном. Норма: 4,5 для
   обычного текста, 3 для крупного (от 24 px или от 18,66 px жирным).
   Решение «зелёный/красный» принимает `catalog/tests/test_contrast.py`.

   Не меряется: скрытое (нулевой прямоугольник, visibility), текст внутри SVG,
   выключенные элементы (WCAG их не требует), текст поверх фоновой картинки
   или градиента между ним и его фоном — там фон не один цвет, и число было бы
   выдумкой; такие считаются отдельно и печатаются числом.

   Запуск руками:
     CONTRAST_BASE_URL=http://127.0.0.1:8000 CONTRAST_PROBLEM=/catalog/problem/4/ node catalog/tests/contrast_runner.mjs

   Коды возврата: 0 — прогон дошёл до конца, 3 — браузер не поднялся.        */
import { chromium } from 'playwright';

const BASE = process.env.CONTRAST_BASE_URL || 'http://127.0.0.1:8000';
const PROBLEM = process.env.CONTRAST_PROBLEM || '/catalog/';
const PAGES = [
  { name: 'каталог', path: '/catalog/', root: 'body' },
  { name: 'страница задачи', path: PROBLEM, root: 'body' },
  { name: 'окно фильтров', path: '/catalog/', root: '#ct-all', open: '#ct-all-open' },
  { name: 'вход', path: '/login/', root: 'body' },
];
const THEMES = ['light', 'dark'];

let browser;
try {
  browser = await chromium.launch();
} catch (e) {
  console.log('браузер не поднялся: ' + e.message);
  process.exit(3);
}

/* Замер внутри страницы — одна функция, передаётся в page.evaluate. */
function measure(rootSelector) {
  const parse = (c) => {
    const m = /rgba?\(([^)]+)\)/.exec(c || '');
    if (!m) { return null; }
    const p = m[1].split(/[\s,/]+/).filter(Boolean).map(Number);
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  };
  const channel = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const lum = (c) => 0.2126 * channel(c.r) + 0.7152 * channel(c.g) + 0.0722 * channel(c.b);
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const over = (fg, alpha, bg) => ({ r: fg.r * alpha + bg.r * (1 - alpha), g: fg.g * alpha + bg.g * (1 - alpha), b: fg.b * alpha + bg.b * (1 - alpha) });
  const selector = (el) => {
    const parts = [];
    for (let e = el; e && e.nodeType === 1 && parts.length < 4; e = e.parentElement) {
      let s = e.tagName.toLowerCase();
      if (e.id) { parts.unshift(s + '#' + e.id); break; }
      if (e.classList.length) { s += '.' + [...e.classList].slice(0, 2).join('.'); }
      parts.unshift(s);
    }
    return parts.join(' > ');
  };

  const root = document.querySelector(rootSelector);
  const out = { theme: document.documentElement.getAttribute('data-theme') || 'light',
                checked: 0, skipped_image_bg: 0, violations: [] };
  if (!root) { out.error = 'нет корня ' + rootSelector; return out; }
  const seen = new Set();
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const el = node.parentElement;
    if (!el || seen.has(el) || !node.textContent.trim()) { continue; }
    seen.add(el);
    if (el.closest('svg, script, style, noscript, [disabled], [aria-disabled="true"]')) { continue; }
    const cs = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    if (rect.width < 2 || rect.height < 2 || cs.visibility !== 'visible') { continue; }

    let opacity = 1, bg = null, imageBetween = false;
    for (let e = el; e; e = e.parentElement) {
      const s = getComputedStyle(e);
      opacity *= parseFloat(s.opacity);
      if (bg) { continue; }
      const color = parse(s.backgroundColor);
      if (color && color.a >= 1) { bg = color; continue; }
      if (s.backgroundImage && s.backgroundImage !== 'none') { imageBetween = true; }
    }
    if (imageBetween) { out.skipped_image_bg += 1; continue; }
    bg = bg || { r: 255, g: 255, b: 255, a: 1 };
    const fg = parse(cs.color);
    if (!fg) { continue; }
    const seenColor = over(over(fg, fg.a, bg), opacity, bg);
    const value = ratio(seenColor, bg);
    const size = parseFloat(cs.fontSize);
    const weight = parseInt(cs.fontWeight, 10) || 400;
    /* Графика с подписью (`role="img"`, например звёзды сложности) — не текст:
       норма 3:1, WCAG 1.4.11. */
    const graphic = !!el.closest('[role="img"]');
    const need = graphic || size >= 24 || (size >= 18.66 && weight >= 700) ? 3 : 4.5;
    out.checked += 1;
    if (value < need) {
      out.violations.push({ sel: selector(el), text: node.textContent.trim().slice(0, 40),
                            ratio: Math.round(value * 100) / 100, need,
                            color: cs.color, bg: 'rgb(' + [bg.r, bg.g, bg.b].join(', ') + ')',
                            opacity: Math.round(opacity * 100) / 100 });
    }
  }
  return out;
}

const result = {};
for (const theme of THEMES) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, reducedMotion: 'reduce' });
  await context.addInitScript((t) => { try { localStorage.setItem('theme', t); } catch (e) { /* нет хранилища */ } }, theme);
  const page = await context.newPage();
  for (const target of PAGES) {
    const key = target.name + ' · ' + theme;
    try {
      await page.goto(BASE + target.path, { waitUntil: 'networkidle' });
      // Переходы цвета мерились бы на середине: выключаем их до замера.
      await page.addStyleTag({ content: '*,*::before,*::after{transition:none!important;animation:none!important}' });
      if (target.open) {
        await page.click(target.open);
        await page.waitForSelector(target.root + '[open]', { timeout: 5000 });
      }
      await page.waitForTimeout(300);
      result[key] = await page.evaluate(measure, target.root);
    } catch (e) {
      result[key] = { error: e.message };
    }
  }
  await context.close();
}
await browser.close();
console.log('###CONTRAST-JSON###');
console.log(JSON.stringify(result));
