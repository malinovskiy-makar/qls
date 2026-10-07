/* Проверка текста файла .tex без TeX (прибор tex_lint; его же зовёт тест CI).

   Что проверяет (SPEC.md, разделы 2.3, 7, 11):
     • запрещённые команды — ТЕМ ЖЕ выражением, что сервер (_TEX_FORBIDDEN,
       calc2/views.py): поиск без учёта регистра и без границы слова, то есть
       ловится НАЧАЛО команды (\includegraphics, \readline, \Input);
     • знаки: только ASCII, кириллица и « » — – №;
     • фигурные скобки сбалансированы (без \{ \} и комментариев);
     • окружения \begin{…}/\end{…} парны и вложены правильно;
     • доллары: в каждой строке их чётное число (одна строка — один предмет);
     • список настроек \begin{axis}[…] — одной строкой (пустая строка внутри
       роняет pgfplots, а браузер шлёт CRLF);
     • координаты (axis cs:…) и отрезки domain= не уходят дальше двух размахов
       окна панели: дальше pgfplots падает с «Dimension too large».

   node calc2/tests/tex/lint.mjs ПАПКА|ФАЙЛ …   код 1, если хоть один файл не прошёл */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// Слово в слово calc2/views.py:_TEX_FORBIDDEN (re.IGNORECASE).
export const TEX_FORBIDDEN = /\\(write18|input|include|openin|openout|read|catcode|csname|immediate|directlua|usepackage\s*\{\s*shellesc)/i;
const ALLOWED = /^[\x09\x0a\x0d\x20-\x7e\u0400-\u04ff«»—–№]$/u;

export function lintTex(text) {
  const problems = [];
  const add = (m) => { if (problems.length < 40) problems.push(m); };
  const m = TEX_FORBIDDEN.exec(text);
  if (m) add('запрещённая команда: ' + text.slice(m.index, m.index + 30).replace(/\n/g, ' '));
  for (const ch of text) if (!ALLOWED.test(ch)) { add('знак вне набора: U+' + ch.codePointAt(0).toString(16).toUpperCase().padStart(4, '0') + ' «' + ch + '»'); break; }
  const lines = text.split('\n');
  let depth = 0;
  const envs = [];
  lines.forEach((raw, i) => {
    // комментарий: % без обратного слэша перед ним
    let line = '';
    for (let k = 0; k < raw.length; k++) {
      if (raw[k] === '\\') { line += raw[k] + (raw[k + 1] || ''); k++; continue; }
      if (raw[k] === '%') break;
      line += raw[k];
    }
    const plain = line.replace(/\\[\\{}$%&#_]/g, '');
    for (const c of plain) { if (c === '{') depth++; else if (c === '}') { depth--; if (depth < 0) { add('строка ' + (i + 1) + ': лишняя }'); depth = 0; } } }
    const dollars = (plain.match(/\$/g) || []).length;
    if (dollars % 2) add('строка ' + (i + 1) + ': нечётное число $');
    const re = /\\(begin|end)\{([^}]*)\}/g; let e;
    while ((e = re.exec(line))) {
      if (e[1] === 'begin') envs.push(e[2]);
      else { const top = envs.pop(); if (top !== e[2]) add('строка ' + (i + 1) + ': \\end{' + e[2] + '} закрывает ' + (top ? '\\begin{' + top + '}' : 'ничего')); }
    }
    if (/\\begin\{axis\}\[/.test(line)) {
      let d = 0, closed = false;
      for (const c of line.slice(line.indexOf('\\begin{axis}[') + 12)) { if (c === '[') d++; else if (c === ']') { d--; if (d === 0) { closed = true; break; } } }
      if (!closed) add('строка ' + (i + 1) + ': настройки axis не уложились в одну строку');
    }
  });
  if (depth) add('фигурных скобок не хватает: ' + depth);
  if (envs.length) add('не закрыты окружения: ' + envs.join(', '));
  // Координаты относительно окна своей панели.
  let win = null;
  lines.forEach((line, i) => {
    if (/\\begin\{axis\}\[/.test(line)) {
      const g = (k) => { const r = new RegExp('\\b' + k + '=(-?[\\d.]+(?:e-?\\d+)?)').exec(line); return r ? +r[1] : null; };
      win = { x0: g('xmin'), x1: g('xmax'), y0: g('ymin'), y1: g('ymax') };
      if ([win.x0, win.x1, win.y0, win.y1].some(v => v == null || !isFinite(v))) { add('строка ' + (i + 1) + ': у axis нет окна'); win = null; }
      return;
    }
    if (/\\end\{axis\}/.test(line)) { win = null; return; }
    if (!win) return;
    const sx = Math.abs(win.x1 - win.x0) || 1, sy = Math.abs(win.y1 - win.y0) || 1;
    const inX = (v) => v >= Math.min(win.x0, win.x1) - 2 * sx && v <= Math.max(win.x0, win.x1) + 2 * sx;
    const inY = (v) => v >= Math.min(win.y0, win.y1) - 2 * sy && v <= Math.max(win.y0, win.y1) + 2 * sy;
    const re = /axis cs:(-?[\d.]+(?:e-?\d+)?),(-?[\d.]+(?:e-?\d+)?)/g; let c;
    while ((c = re.exec(line))) if (!inX(+c[1]) || !inY(+c[2])) { add('строка ' + (i + 1) + ': точка (' + c[1] + ', ' + c[2] + ') далеко за окном'); break; }
    const d = /domain=(-?[\d.]+(?:e-?\d+)?):(-?[\d.]+(?:e-?\d+)?)/.exec(line);
    if (d) {
      const vert = /variable=\\t/.test(line);
      const ok = vert ? (inY(+d[1]) && inY(+d[2])) : (inX(+d[1]) && inX(+d[2]));
      if (!ok) add('строка ' + (i + 1) + ': отрезок domain=' + d[1] + ':' + d[2] + ' далеко за окном');
    }
    const co = /coordinates \{([^}]*)\}/.exec(line);
    if (co) {
      const pr = /\((-?[\d.]+(?:e-?\d+)?),(-?[\d.]+(?:e-?\d+)?)\)/g; let q;
      while ((q = pr.exec(co[1]))) if (!inX(+q[1]) || !inY(+q[2])) { add('строка ' + (i + 1) + ': узел (' + q[1] + ', ' + q[2] + ') далеко за окном'); break; }
    }
  });
  if (!/\\begin\{document\}/.test(text) || !/\\end\{document\}/.test(text)) add('нет \\begin{document} или \\end{document}');
  return { ok: problems.length === 0, problems };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  if (!args.length) { console.log('node calc2/tests/tex/lint.mjs ПАПКА|ФАЙЛ …'); process.exit(2); }
  const files = [];
  args.forEach(a => {
    const st = fs.statSync(a);
    if (st.isDirectory()) fs.readdirSync(a).filter(f => f.endsWith('.tex')).sort().forEach(f => files.push(path.join(a, f)));
    else files.push(a);
  });
  let bad = 0;
  files.forEach(f => {
    const r = lintTex(fs.readFileSync(f, 'utf8'));
    if (!r.ok) { bad++; if (bad <= 30) console.log('НЕ ПРОШЁЛ', path.basename(f), '\n   ' + r.problems.slice(0, 5).join('\n   ')); }
  });
  console.log('проверено файлов', files.length, '| не прошли', bad);
  process.exit(bad ? 1 : 0);
}
