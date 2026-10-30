// Фаза 4: проверка досок замером.
// Каждая доска .dc.html превращается в обычную страницу (тема подставляется вместо {{theme}}),
// открывается в Chromium на ширине своей доски, в светлой и тёмной теме, и проверяется:
//   1) вылезание: у элемента содержимое шире (или выше) самого элемента — scrollWidth > clientWidth,
//      кроме намеренно обрезанных с многоточием и коробок с прокруткой (overflow: auto/scroll);
//   2) за краем доски: прямоугольник видимого элемента выходит за 0…ширина доски, документ шире доски;
//   3) наезд подписей: подписи календаря (.om-bl, .om-today-l) пересекаются друг с другом.
// Запуск: node check.mjs [папка project] [--shots]
// Шрифт — боевые файлы Montserrat из static/fonts репозитория (только чтение).
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from '/Users/makarmalinovskiy/Downloads/qls_platform/node_modules/playwright/index.mjs';

const ROOT = path.resolve(process.argv[2] || new URL('./canvas/project', import.meta.url).pathname);
const SHOTS = process.argv.includes('--shots');
const OUT = path.resolve(new URL('./out', import.meta.url).pathname);
const FONTS = '/Users/makarmalinovskiy/Downloads/qls_platform/static/fonts';
fs.mkdirSync(path.join(OUT, 'html'), { recursive: true });
fs.mkdirSync(path.join(OUT, 'shots'), { recursive: true });

const canvas = JSON.parse(fs.readFileSync(path.join(ROOT, 'canvas.json'), 'utf8'));
const faces = [['400', 'normal', '400'], ['400', 'italic', '400i'], ['500', 'normal', '500'], ['600', 'normal', '600'], ['700', 'normal', '700']]
  .map(([w, s, f]) => `@font-face{font-family:'Montserrat';font-weight:${w};font-style:${s};src:url('file://${FONTS}/montserrat-${f}.woff2') format('woff2');}`).join('\n');

function toStatic(src, theme) {
  const helmet = (src.match(/<helmet>([\s\S]*?)<\/helmet>/) || [, ''])[1]
    .replace(/<link[^>]+fonts\.googleapis[^>]*>/g, '');
  const body = src.match(/<x-dc>([\s\S]*?)<\/x-dc>/)[1].replace(/<helmet>[\s\S]*?<\/helmet>/, '');
  const filled = body
    .replace(/\s+on[A-Z][a-zA-Z]*="\{\{[^}]*\}\}"/g, '')
    .replace(/\{\{\s*theme\s*\}\}/g, theme)
    .replace(/\{\{\s*themeIcon\s*\}\}/g, theme === 'dark' ? '☀' : '☾');
  const left = filled.match(/\{\{[^}]*\}\}/g);
  if (left) throw new Error('незаполненные дыры: ' + left.join(' '));
  return `<!doctype html><html lang="ru"><head><meta charset="utf-8">
<link rel="stylesheet" href="file://${ROOT}/olymp.css"><style>${faces}</style>${helmet}</head><body>${filled}</body></html>`;
}

const PROBE = () => {
  const W = document.documentElement.clientWidth;
  const out = { overflow: [], outside: [], overlap: [], docW: document.documentElement.scrollWidth, docH: document.documentElement.scrollHeight };
  const name = (el) => {
    const t = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 60);
    return `<${el.tagName.toLowerCase()}${el.className && typeof el.className === 'string' ? ' .' + el.className.trim().split(/\s+/).join('.') : ''}> «${t}»`;
  };
  const hidden = (el) => { for (let e = el; e; e = e.parentElement) { const cs = getComputedStyle(e); if (cs.display === 'none' || cs.visibility === 'hidden') return true; } return false; };
  const inScrollBox = (el) => { for (let e = el.parentElement; e && e !== document.body; e = e.parentElement) { const ox = getComputedStyle(e).overflowX; if (ox === 'auto' || ox === 'scroll') return true; } return false; };
  for (const el of document.body.querySelectorAll('*')) {
    if (el.closest('svg') && el.tagName.toLowerCase() !== 'svg') continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || hidden(el)) continue;
    // подпись только для экранного диктора сжата до 1 px намеренно
    if (el.classList.contains('sr-only')) continue;
    const scrolls = cs.overflowX === 'auto' || cs.overflowX === 'scroll';
    const ellipsis = cs.textOverflow === 'ellipsis' && cs.overflowX === 'hidden';
    if (cs.display !== 'inline' && el.clientWidth > 0) {
      if (el.scrollWidth > el.clientWidth + 1 && !scrolls && !ellipsis)
        out.overflow.push({ el: name(el), sw: el.scrollWidth, cw: el.clientWidth, kind: 'ширина' });
      // прокрутка законна только там, где её задумали: элемент помечен data-scroll
      if (scrolls && el.scrollWidth > el.clientWidth + 1 && !el.hasAttribute('data-scroll'))
        out.overflow.push({ el: name(el), sw: el.scrollWidth, cw: el.clientWidth, kind: 'прокрутка' });
      const clipsY = cs.overflowY === 'hidden' || cs.overflowY === 'clip';
      if (clipsY && el.scrollHeight > el.clientHeight + 1)
        out.overflow.push({ el: name(el), sw: el.scrollHeight, cw: el.clientHeight, kind: 'высота' });
    }
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.height > 0 && !inScrollBox(el) && (r.right > W + 0.5 || r.left < -0.5))
      out.outside.push({ el: name(el), left: Math.round(r.left), right: Math.round(r.right), W });
  }
  // разрыв числа: «2 658» с обычным пробелом не должно ломаться между строками
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let node; (node = walker.nextNode());) {
    for (const m of node.data.matchAll(/\d[  ]\d{3}(?!\d)/g)) {
      const range = document.createRange();
      range.setStart(node, m.index); range.setEnd(node, m.index + m[0].length);
      const tops = new Set([...range.getClientRects()].filter(r => r.width > 0).map(r => Math.round(r.top)));
      if (tops.size > 1) out.overflow.push({ el: name(node.parentElement), sw: tops.size, cw: 1, kind: `разрыв числа «${m[0]}»` });
    }
  }
  // подписи календаря: попарно внутри одной полосы и подпись «сегодня» против всех
  const labels = [...document.querySelectorAll('.om-bl, .om-today-l')];
  const rect = (el) => { const rs = [...el.getClientRects()]; return rs.length ? el.getBoundingClientRect() : null; };
  for (let i = 0; i < labels.length; i++) for (let j = i + 1; j < labels.length; j++) {
    const a = rect(labels[i]), b = rect(labels[j]);
    if (!a || !b) continue;
    if (a.left < b.right - 0.5 && b.left < a.right - 0.5 && a.top < b.bottom - 0.5 && b.top < a.bottom - 0.5)
      out.overlap.push({ a: name(labels[i]), b: name(labels[j]) });
  }
  return out;
};

const browser = await chromium.launch();
const summary = [];
let total = 0;
for (const file of canvas.order) {
  const board = canvas.boards[file];
  if (!fs.existsSync(path.join(ROOT, file))) { console.log(`нет файла: ${file}`); total++; continue; }
  const src = fs.readFileSync(path.join(ROOT, file), 'utf8');
  for (const theme of ['light', 'dark']) {
    const html = toStatic(src, theme);
    const htmlPath = path.join(OUT, 'html', `${file.replace('.dc.html', '')}.${theme}.html`);
    fs.writeFileSync(htmlPath, html);
    // низкое окно: тогда высота документа — это высота содержимого, по ней ставится рамка доски
    const page = await browser.newPage({ viewport: { width: board.w, height: 200 } });
    await page.goto('file://' + htmlPath);
    await page.evaluate(() => document.fonts.ready);
    const res = await page.evaluate(PROBE);
    if (res.docW > board.w) res.outside.push({ el: 'документ', left: 0, right: res.docW, W: board.w });
    const n = res.overflow.length + res.outside.length + res.overlap.length;
    total += n;
    summary.push({ board: file, theme, w: board.w, h: res.docH, problems: n, ...res });
    if (SHOTS) await page.screenshot({ path: path.join(OUT, 'shots', `${file.replace('.dc.html', '')}.${theme}.png`), fullPage: true });
    await page.close();
  }
}
await browser.close();
fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify(summary, null, 1));
for (const s of summary) {
  console.log(`${s.problems === 0 ? 'ок ' : 'ПЛОХО'} ${s.board.padEnd(24)} ${s.theme.padEnd(5)} ${s.w}×${s.h}  вылезаний ${s.overflow.length}, за краем ${s.outside.length}, наездов ${s.overlap.length}`);
  for (const o of s.overflow) console.log(`      вылезание (${o.kind}) ${o.sw} > ${o.cw}: ${o.el}`);
  for (const o of s.outside) console.log(`      за краем ${o.left}…${o.right} при ширине ${o.W}: ${o.el}`);
  for (const o of s.overlap) console.log(`      наезд: ${o.a}  ×  ${o.b}`);
}
console.log(`ИТОГО: досок ${canvas.order.length}, прогонов ${summary.length}, проблем ${total}`);
process.exitCode = total ? 1 : 0;
