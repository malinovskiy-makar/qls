/* Статическая перепись мест рисования (прибор tex_sites).

   Каждое место, где код калькулятора создаёт путь (`append('path')`), обязано
   иметь судьбу в sites.json (SPEC.md, разделы 3.1 и 12):
     record  — есть запись (вид: expr, area, numeric, poly, curve, helper);
     todo    — будет запись (вид), пока нет: это долг, а не судьба навсегда;
     none    — в файл не идёт (причина: служебный узел, defs, функция нигде
               не вызывается…).
   Место узнаётся по файлу, функции и порядковому номеру внутри неё, а не по
   строке: строки сдвигаются от любой правки выше.

   У судьбы record прибор проверяет и сам текст места: в операторе с
   append('path') (и шести строках за ним — путь бывает сохранён в переменную
   и помечен ниже) обязан стоять вызов записи своего вида.

   node calc2/tests/tex/sites.mjs            сверить; код 1 — есть место без судьбы, судьба без места
                                             или запись, которой нет в тексте
   node calc2/tests/tex/sites.mjs --final    то же, и ещё код 1, если осталась судьба todo
   node calc2/tests/tex/sites.mjs --list     печать всех мест с судьбами */
import fs from 'node:fs';
import path from 'node:path';
import { HERE, ROOT } from './lib.mjs';

const DIR = path.join(ROOT, 'calc2/static/calc2');
const KIND_RE = {
  expr: /markExpr\(|data-expr/, area: /markArea\(/, numeric: /markNumeric\(|data-numeric/, poly: /markPoly\(|data-poly/,
  curve: /data-curve/, skip: /data-skip-export|data-service/,
};

export function scan() {
  const out = [];
  for (const f of fs.readdirSync(DIR).filter(x => x.endsWith('.js')).sort()) {
    const src = fs.readFileSync(path.join(DIR, f), 'utf8');
    const lines = src.split('\n');
    const count = {};
    let fn = '(верх файла)';
    lines.forEach((line, i) => {
      const m = /^(?:async\s+)?function\s+([\w$]+)/.exec(line) || /^(?:const|let|var)\s+([\w$]+)\s*=/.exec(line);
      if (m) fn = m[1];
      const re = /\.append\(\s*['"]path['"]\s*\)/g; let a;
      while ((a = re.exec(line))) {
        const n = count[fn] = (count[fn] || 0) + 1;
        // оператор: от начала строки до точки с запятой на нулевой глубине скобок
        const start = src.split('\n').slice(0, i).join('\n').length + (i ? 1 : 0);
        let depth = 0, j = start, q = null;
        for (; j < src.length; j++) {
          const c = src[j];
          if (q) { if (c === '\\') { j++; continue; } if (c === q) q = null; continue; }
          if (c === '"' || c === "'" || c === '`') { q = c; continue; }
          if (c === '(' || c === '[' || c === '{') depth++;
          else if (c === ')' || c === ']' || c === '}') { depth--; if (depth < 0) break; }
          else if (c === ';' && depth <= 0) break;
        }
        const endLine = src.slice(0, j).split('\n').length;
        const text = lines.slice(i, Math.min(lines.length, endLine + 6)).join('\n');
        out.push({ file: f, fn, n, line: i + 1, head: line.trim().slice(0, 140), text });
      }
    });
  }
  return out;
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === path.resolve(HERE, 'sites.mjs');
if (isMain) {
  const sites = scan();
  const fatesFile = path.join(HERE, 'sites.json');
  const fates = JSON.parse(fs.readFileSync(fatesFile, 'utf8')).sites;
  const key = (s) => s.file + ' | ' + s.fn + ' | ' + s.n;
  const byKey = new Map(fates.map(x => [key(x), x]));
  const seen = new Set();
  const bad = [];
  const tally = { record: 0, todo: 0, none: 0 };
  sites.forEach(s => {
    const k = key(s); const fate = byKey.get(k);
    if (!fate) { bad.push('МЕСТО БЕЗ СУДЬБЫ ' + s.file + ':' + s.line + ' ' + s.fn + ' №' + s.n + ' — ' + s.head); return; }
    seen.add(k);
    tally[fate.fate] = (tally[fate.fate] || 0) + 1;
    if (fate.fate === 'record') {
      const re = fate.check ? new RegExp(fate.check) : KIND_RE[fate.kind];
      if (!re) bad.push('НЕЗНАКОМЫЙ ВИД ЗАПИСИ ' + k + ': ' + fate.kind);
      else if (!re.test(s.text)) bad.push('ЗАПИСИ НЕТ В ТЕКСТЕ ' + s.file + ':' + s.line + ' ' + s.fn + ' №' + s.n + ' (ждали ' + (fate.check || fate.kind) + ')');
    } else if (fate.fate === 'none') {
      if (!fate.why) bad.push('НЕТ ПРИЧИНЫ «В ФАЙЛ НЕ ИДЁТ» ' + k);
    } else if (fate.fate !== 'todo') bad.push('НЕЗНАКОМАЯ СУДЬБА ' + k + ': ' + fate.fate);
    if (process.argv.includes('--list')) console.log((s.file + ':' + s.line).padEnd(26), s.fn.padEnd(26), '№' + s.n, fate.fate.padEnd(7), (fate.kind || '').padEnd(8), fate.why || '');
  });
  fates.forEach(x => { if (!seen.has(key(x))) bad.push('СУДЬБА БЕЗ МЕСТА ' + key(x) + ' (место исчезло или сдвинулось в другую функцию)'); });
  bad.forEach(b => console.log(b));
  console.log('мест, где создаётся path:', sites.length, '| есть запись', tally.record, '| будет запись', tally.todo || 0, '| в файл не идёт', tally.none, '| нарушений', bad.length);
  const fail = bad.length || (process.argv.includes('--final') && tally.todo);
  process.exit(fail ? 1 : 0);
}
