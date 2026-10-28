/**
 * Контур качества (Q1, 29.10.2026): формулы текстов задач тем же разбором,
 * что на сайте, и vendored KaTeX в node.
 *
 *   node scripts/olympiad_contour_katex.js <in.json> <out.json>
 *
 * Вход — JSON-массив строк. Выход — массив того же размера:
 *   {errors: [{tex, problem}], currency: [...], text_in_math: [...], unpaired: N}
 *
 * Разбор повторяет страницу: сначала `maskOutsideMath` из
 * `templates/_katex_dollars.html` (литеральный «\$» вне формул прячется), затем
 * `splitAtDelimiters` авторендера KaTeX 0.16 (порядок разделителей —
 * `catalog/base.html`: $$, $, \[, \(). Текст, где разделитель не закрылся,
 * остаётся текстом — его «$» ученик видит буквально (`unpaired`).
 *
 * `currency` — «формула», которая на деле валюта: между двумя «$» русский текст,
 * а к «$» примыкает цифра («5$ за штуку, а 10$»). `text_in_math` — русские слова
 * в формуле без \text{}: KaTeX съедает пробелы, слова слипаются.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const katex = require(path.join(__dirname, '..', 'static', 'vendor', 'katex-0.16.9', 'katex.min.js'));

const SENTINEL = '';
const DELIMS = [
  { left: '$$', right: '$$', display: true },
  { left: '$', right: '$', display: false },
  { left: '\\[', right: '\\]', display: true },
  { left: '\\(', right: '\\)', display: false },
];

// ── templates/_katex_dollars.html ──────────────────────────────────────
function findClose(s, from, close) {
  let i = from;
  while (i < s.length) {
    if (s.charAt(i) === '\\' && (s.charAt(i + 1) === '$' || s.charAt(i + 1) === '\\')) { i += 2; continue; }
    if (s.substr(i, close.length) === close) return i;
    i++;
  }
  return -1;
}
function mathSpanEnd(s, i) {
  const pairs = [['$$', '$$'], ['\\[', '\\]'], ['\\(', '\\)'], ['$', '$']];
  for (const [open, close] of pairs) {
    if (s.substr(i, open.length) !== open) continue;
    const end = findClose(s, i + open.length, close);
    if (end === -1) continue;
    return end + close.length;
  }
  return i;
}
function maskOutsideMath(s) {
  if (s.indexOf('\\$') === -1) return s;
  let out = '', i = 0;
  while (i < s.length) {
    if (s.charAt(i) === '\\' && s.charAt(i + 1) === '$') { out += SENTINEL; i += 2; continue; }
    const end = mathSpanEnd(s, i);
    if (end > i) { out += s.slice(i, end); i = end; continue; }
    out += s.charAt(i); i++;
  }
  return out;
}

// ── KaTeX 0.16 contrib/auto-render: splitAtDelimiters ───────────────────
function findEndOfMath(delimiter, text, startIndex) {
  let index = startIndex, braceLevel = 0;
  while (index < text.length) {
    const ch = text[index];
    if (braceLevel <= 0 && text.slice(index, index + delimiter.length) === delimiter) return index;
    else if (ch === '\\') index++;
    else if (ch === '{') braceLevel++;
    else if (ch === '}') braceLevel--;
    index++;
  }
  return -1;
}
const escapeRegex = (s) => s.replace(/[-/\\^$*+?.()|[\]{}]/g, '\\$&');
const amsRegex = /^\\begin{/;
function splitAtDelimiters(text, delimiters) {
  const data = [];
  const regexLeft = new RegExp('(' + delimiters.map((x) => escapeRegex(x.left)).join('|') + ')');
  let consumed = 0;
  while (true) {
    let index = text.search(regexLeft);
    if (index === -1) break;
    if (index > 0) { data.push({ type: 'text', data: text.slice(0, index) }); text = text.slice(index); consumed += index; }
    const i = delimiters.findIndex((d) => text.startsWith(d.left));
    index = findEndOfMath(delimiters[i].right, text, delimiters[i].left.length);
    if (index === -1) break;
    const rawData = text.slice(0, index + delimiters[i].right.length);
    const math = amsRegex.test(rawData) ? rawData : text.slice(delimiters[i].left.length, index);
    data.push({ type: 'math', data: math, rawData, display: delimiters[i].display, at: consumed });
    text = text.slice(index + delimiters[i].right.length);
    consumed += rawData.length;
  }
  if (text !== '') data.push({ type: 'text', data: text });
  return data;
}

// ── Классы поломок ──────────────────────────────────────────────────────
function bareWords(tex) {
  let s = tex.replace(/\\(?:text|mathrm|textbf|textit|mbox|operatorname|mathbf|mathit)\s*\{[^{}]*\}/g, ' ');
  let prev = null;
  while (prev !== s) { prev = s; s = s.replace(/\{[^{}]*\}/g, ' '); }
  s = s.replace(/\\[A-Za-z]+/g, ' ');
  return s.match(/[А-Яа-яЁё]{2,}/g) || [];
}

function check(text) {
  const res = { errors: [], currency: [], text_in_math: [], unpaired: 0 };
  const masked = maskOutsideMath(String(text || ''));
  for (const seg of splitAtDelimiters(masked, DELIMS)) {
    if (seg.type === 'text') {
      const bare = seg.data.split('\\$').join('');
      res.unpaired += (bare.match(/\$/g) || []).length;
      continue;
    }
    const tex = seg.data;
    try {
      katex.renderToString(tex, { throwOnError: true, displayMode: seg.display, strict: 'ignore' });
    } catch (e) {
      res.errors.push({ tex: tex.slice(0, 200), problem: String(e.message || e).slice(0, 200) });
      continue;
    }
    if (!seg.display && bareWords(tex).length >= 2) {
      const before = masked.charAt(seg.at - 1);
      const after = masked.charAt(seg.at + seg.rawData.length);
      if (/\d/.test(before) || /\d/.test(after)) res.currency.push(seg.rawData.slice(0, 120));
      else res.text_in_math.push(seg.rawData.slice(0, 120));
    }
  }
  return res;
}

const [inp, out] = process.argv.slice(2);
const items = JSON.parse(fs.readFileSync(inp, 'utf8'));
fs.writeFileSync(out, JSON.stringify(items.map(check)), 'utf8');
