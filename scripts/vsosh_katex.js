/**
 * ВсОШ v1: проверка формул эталона вендорным KaTeX в node (без браузера).
 *
 * Вход:  reference_problems_v1.jsonl (поля statement_md, solution_md,
 *        criteria_md, answer, parts[].text)
 * Выход: katex_v1.json — {fields, formulas, errors, red, by_key: {ключ: [ошибки]}}
 *
 * Разметка повторяет боевой конвейер catalog/base.html: `\$` маскируется,
 * разделители $$…$$, \[…\], \(…\), $…$ — $$ раньше $. Считаются ДВА вида
 * поломки (как в scripts/katex_damage.js): `errors` — формула не разобралась
 * (throwOnError), `red` — разобралась, но неизвестная команда покрашена
 * errorColor (сентинел-цвет, чтобы не спутать с авторским \color).
 * Отличие от katex_render_check.js — нет DOM: auto-render не нужен, сегменты
 * режутся тем же порядком разделителей. Ограничение записано в OLYMPIAD_AUDIT.md.
 *
 *   node scripts/vsosh_katex.js <reference_problems_v1.jsonl> <katex_v1.json>
 */
'use strict';

const fs = require('fs');
const path = require('path');
const katex = require(path.join(__dirname, '..', 'static', 'vendor', 'katex-0.16.9', 'katex.min.js'));

const SENTINEL = '#010203';
const DELIMS = [['$$', '$$', true], ['\\[', '\\]', true], ['\\(', '\\)', false], ['$', '$', false]];

function segments(text) {
  const masked = String(text || '').split('\\$').join('\uE000');
  const out = [];
  let i = 0;
  while (i < masked.length) {
    let hit = null;
    for (const [l, r, display] of DELIMS) {
      if (masked.startsWith(l, i)) {
        const j = masked.indexOf(r, i + l.length);
        if (j > -1) { hit = [masked.slice(i + l.length, j), display, j + r.length]; }
        break;
      }
    }
    if (hit) {
      out.push({ tex: hit[0].split('\uE000').join('\\$'), display: hit[1] });
      i = hit[2];
    } else {
      i += 1;
    }
  }
  return out;
}

function check(tex, display) {
  try {
    katex.renderToString(tex, { throwOnError: true, displayMode: display, strict: 'ignore' });
  } catch (e) {
    return 'error: ' + String(e.message || e).slice(0, 160);
  }
  const html = katex.renderToString(tex, { throwOnError: false, errorColor: SENTINEL, displayMode: display, strict: 'ignore' });
  if (html.indexOf(SENTINEL) > -1) return 'red: неизвестная команда';
  return '';
}

const [inp, out] = process.argv.slice(2);
const lines = fs.readFileSync(inp, 'utf8').split(/\r?\n/).filter(Boolean);
const res = { fields: 0, formulas: 0, errors: 0, red: 0, by_key: {}, examples: [] };
for (const line of lines) {
  const r = JSON.parse(line);
  const key = `${r.event_id}|${r.number}|${r.task_variant || ''}`;
  const texts = [r.statement_md, r.solution_md, r.criteria_md, r.answer]
    .concat((r.parts || []).map(p => p.text));
  const bad = [];
  for (const t of texts) {
    if (!t) continue;
    res.fields += 1;
    for (const s of segments(t)) {
      res.formulas += 1;
      const e = check(s.tex, s.display);
      if (e) {
        if (e.startsWith('error')) res.errors += 1; else res.red += 1;
        bad.push({ tex: s.tex.slice(0, 200), problem: e });
      }
    }
  }
  res.by_key[key] = bad;
  if (bad.length && res.examples.length < 40) res.examples.push({ key, bad: bad.slice(0, 3) });
}
fs.writeFileSync(out, JSON.stringify(res, null, 1), 'utf8');
console.log(`полей ${res.fields}, формул ${res.formulas}, ошибок ${res.errors}, красных ${res.red}`);
