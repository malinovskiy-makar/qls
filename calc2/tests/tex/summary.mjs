/* Сводка аудита выгрузки .tex: node calc2/tests/tex/summary.mjs [ПАПКА] [--strict] [--fallback]

   ПАПКА — где лежит audit.jsonl (по умолчанию reports/calc2_tex/audit).
   Печатает: таблицу счётчиков по наборам (как RECON.md, раздел 2.1), инварианты
   «выгрузка ничего не трогает», время сборки, предупреждения описи, дефекты по
   моделям. --fallback — ещё и полный список кривых и областей, ушедших узлами
   (с причиной), для отчёта владельцу.

   Код возврата с --strict: 1, если есть сбой, дефект записи (без записи, не
   сошлась; кроме дефектов сцены из scene_defects.json), изменение состояния/холста/истории/хранилища, событие во время
   выгрузки, разный файл при повторе, расхождение двери и сборки, непрошедшая
   проверка текста. Без --strict — всегда 0 (сводка для журнала). */
import fs from 'node:fs';
import path from 'node:path';
import { OUT_ROOT } from './lib.mjs';

const args = process.argv.slice(2);
const DIR = args.find(a => !a.startsWith('--')) || path.join(OUT_ROOT, 'audit');
const STRICT = args.includes('--strict'), FALLBACK = args.includes('--fallback');
const rows = fs.readFileSync(path.join(DIR, 'audit.jsonl'), 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l));
// последняя строка по состоянию главнее (повторный прогон дописывает)
const byId = new Map(); rows.forEach(r => byId.set(r.id, r));
const all = [...byId.values()];
const ok = all.filter(r => r.stats), bad = all.filter(r => r.err), excl = all.filter(r => r.excluded);
const DEF = ['curvesNoRecPoly', 'curvesNoRecSampled', 'curvesMismatch', 'areasNoRecPoly', 'areasNoRecSampled', 'areasMismatch'];
const COLS = [['состояний', null], ['форм', 'curvesFormula'], ['числ', 'curvesNumeric'], ['(модели)', 'numericExact'], ['лом+', 'curvesPolyRec'],
  ['БЕЗ:лом', 'curvesNoRecPoly'], ['БЕЗ:отсч', 'curvesNoRecSampled'], ['НЕСОШ', 'curvesMismatch'],
  ['обл:гран', 'areasBounds'], ['обл:мн', 'areasPoly'], ['обл:БЕЗмн', 'areasNoRecPoly'], ['обл:числ', 'areasNumeric'], ['обл:БЕЗ', 'areasNoRecSampled'], ['обл:НЕСОШ', 'areasMismatch'], ['пар', 'pairs']];
/* Именной список дефектов сцены (scene_defects.json): там запись не сошлась
   потому, что неверно нарисовано на экране. Такие кривые вычитаются из
   «не сошлось» и печатаются отдельной строкой — поимённо, с причиной. */
const SD = JSON.parse(fs.readFileSync(path.join(path.dirname(new URL(import.meta.url).pathname), 'scene_defects.json'), 'utf8'));
const known = [];
all.filter(r => r.stats && SD[r.id]).forEach(r => (r.fallback || []).forEach(x => {
  const why = x.kind === 'не сошлась' && SD[r.id][x.name || ''];
  if (!why) return;
  const k = x.what === 'область' ? 'areasMismatch' : 'curvesMismatch';
  r.stats = Object.assign({}, r.stats, { [k]: r.stats[k] - 1 });
  known.push(r.id + ' | ' + (x.name || '(без имени)') + ' — ' + why);
}));
const sum = (list) => { const t = {}; list.forEach(r => Object.entries(r.stats).forEach(([k, v]) => { t[k] = (t[k] || 0) + v; })); return t; };
// Состояния рецептов делятся по файлам рецептов (states.json, поле file).
let stFile = {};
try { JSON.parse(fs.readFileSync(path.join(path.dirname(new URL(import.meta.url).pathname), 'states.json'), 'utf8')).forEach(s => { stFile[s.id] = s.file || s.src; }); } catch (e) {}
const groups = {};
ok.forEach(r => { const g = r.src === 'recipe' ? (stFile[r.id] || 'recipe') : r.src; (groups[g] = groups[g] || []).push(r); });
console.log('Набор'.padEnd(20) + COLS.map(c => c[0].padStart(10)).join(''));
const line = (name, list) => { const t = sum(list); console.log(name.padEnd(20) + COLS.map(([n, k]) => String(k ? (t[k] || 0) : list.length).padStart(10)).join('')); };
Object.keys(groups).sort().forEach(g => line(g, groups[g]));
line('ВСЕГО', ok);
const T = sum(ok);
console.log('\nсостояний', all.length, '| файл построен', ok.length, '| сбоев', bad.length, '| исключено (именной список)', excl.length);
bad.slice(0, 15).forEach(r => console.log('   СБОЙ', r.id, String(r.err).slice(0, 200)));
excl.forEach(r => console.log('   ИСКЛЮЧЕНО', r.id, '—', r.excluded));
const cnt = (f) => ok.filter(f);
const changed = cnt(r => r.stateDiff && r.stateDiff.length), domBad = cnt(r => r.dom && !r.dom.same);
const histBad = cnt(r => r.hist && (r.hist.undo[0] !== r.hist.undo[1] || r.hist.redo[0] !== r.hist.redo[1]));
const lsBad = cnt(r => r.hist && !r.hist.lsSame);
const evBad = cnt(r => r.events && (r.events['calc2:changing'] || r.events['calc2:history']));
const repBad = cnt(r => !r.repeatSame), doorBad = cnt(r => !r.doorSame), lintBad = cnt(r => r.lint);
const pageErr = cnt(r => r.pageErrors);
/* Предметов на листе столько же, сколько в файле (подписи, отрезки, точки,
   строки легенды, линии осей и сетки). Подписи делений, имена осей и «0»
   стоят в файле настройками оси, засечки делений рисует pgfplots сам —
   поэтому они прибавляются к своим строкам файла. */
const itemsDiff = (r) => {
  const s = r.stats, v = r.seen;
  if (!v || s.tickLabels == null) return null;
  const d = [];
  const cmp = (n, a, b) => { if (a !== b) d.push(n + ' ' + a + '≠' + b); };
  cmp('подписей', v.texts, s.texts + s.tickLabels + s.zeroLabels + s.axisNames);
  cmp('отрезков', v.lines, s.segs + s.tickMarks);
  cmp('точек', v.dots, s.dots);
  cmp('легенды', v.legendRows, s.legendRows);
  cmp('осей', v.axisLines, s.axisLines);
  cmp('сетки', v.gridLines, s.gridLines);
  return d.length ? d.join(', ') : null;
};
const itemsBad = cnt(r => itemsDiff(r));
const selfLeak = cnt(r => r.seen && r.seen.selfLeak);
console.log('после выгрузки: состояние изменилось', changed.length, '| узлы холста другие', domBad.length,
  '| стек «Отменить» другой', histBad.length, '| localStorage другой', lsBad.length, '| событий «изменено» было', evBad.length);
console.log('предметов на листе (холст) и в файле не поровну:', itemsBad.length, 'состояний', ok.some(r => r.stats.tickLabels == null) ? '(у прототипа нет счётчиков настроек оси — сравнение не идёт)' : '');
itemsBad.slice(0, 8).forEach(r => console.log('   ПРЕДМЕТЫ', r.id, itemsDiff(r)));
console.log('«Сначала сам»: подписей с числом в разметке, которого нет на холсте:', selfLeak.reduce((a, r) => a + r.seen.selfLeak, 0), 'в', selfLeak.length, 'состояниях');
selfLeak.slice(0, 6).forEach(r => console.log('   ЧИСЛО ОТВЕТА', r.id, r.seen.selfLeak));
console.log('повторная сборка дала другой файл', repBad.length, '| дверь buildTex ≠ сборка', doorBad.length, '| проверка текста не прошла', lintBad.length, '| ошибок страницы', pageErr.length);
[['СОСТОЯНИЕ', changed, r => r.stateDiff.slice(0, 3).join('; ')], ['ХОЛСТ', domBad, r => r.dom.why], ['ИСТОРИЯ', histBad, r => JSON.stringify(r.hist)],
 ['ХРАНИЛИЩЕ', lsBad, () => ''], ['СОБЫТИЯ', evBad, r => JSON.stringify(r.events)], ['ПОВТОР', repBad, () => ''], ['ДВЕРЬ', doorBad, () => ''],
 ['ТЕКСТ', lintBad, r => r.lint.join('; ')], ['СТРАНИЦА', pageErr, r => r.pageErrors.join('; ')]].forEach(([n, list, f]) => list.slice(0, 6).forEach(r => console.log('   ' + n, r.id, String(f(r)).slice(0, 220))));
const ms = ok.map(r => r.ms.door).sort((a, b) => a - b), ms2 = ok.map(r => r.ms.paper + (r.ms.capture || 0) + r.ms.emit).sort((a, b) => a - b);
if (ms.length) console.log('время двери buildTex, мс: медиана', ms[ms.length >> 1], '| 95 %', ms[Math.floor(ms.length * 0.95)], '| наибольшее', ms[ms.length - 1],
  '  (бумажный прогон + сборка: медиана', ms2[ms2.length >> 1], ', наибольшее', ms2[ms2.length - 1] + ')');
console.log('разных файлов', new Set(ok.map(r => r.sha)).size, '| в режиме «Сначала сам»', ok.filter(r => r.self).length,
  '| панелей', T.panels, '| линий осей', T.axisLines, '| линий сетки', T.gridLines, '| делений', T.ticks,
  '| отрезков', T.segs, '| точек', T.dots, '| подписей', T.texts, '| прямоугольников', T.rects, '| строк легенды', T.legendRows);
const warn = {}; ok.forEach(r => new Set(r.warn || []).forEach(w => { (warn[w] = warn[w] || []).push(r.id); }));
Object.entries(warn).forEach(([w, ids]) => console.log('   предупреждение описи (' + ids.length + '): ' + w + ' — ' + ids.slice(0, 6).join(', ')));
const axes = ok.filter(r => r.stats.axisLines !== 2 * r.stats.panels);
console.log('у панели не две оси (ноль за кадром или оси выключены): состояний', axes.length);
const by = {};
ok.forEach(r => { const c = by[r.key] = by[r.key] || {}; DEF.forEach(k => { c[k] = Math.max(c[k] || 0, r.stats[k] || 0); }); });
const defModels = Object.keys(by).filter(k => DEF.some(d => by[k][d])).sort();
console.log('дефекты записи: моделей', defModels.length, '— наибольшее на одно состояние (ломаная без записи / отсчёты без записи / область без записи / не сошлось):');
defModels.forEach(k => { const c = by[k]; console.log('   ' + k.padEnd(14) + [c.curvesNoRecPoly, c.curvesNoRecSampled, (c.areasNoRecSampled || 0) + (c.areasNoRecPoly || 0), c.curvesMismatch + c.areasMismatch].map(v => String(v).padStart(3)).join(' /')); });
const defStates = ok.filter(r => DEF.some(d => r.stats[d]));
console.log('состояний с дефектом записи', defStates.length, 'из', ok.length, '| суммы:', DEF.map(d => d + ' ' + (T[d] || 0)).join(', '));
console.log('известные дефекты сцены (именной список scene_defects.json, в «не сошлось» не входят):', known.length);
known.forEach(k => console.log('   СЦЕНА', k.slice(0, 260)));
if (FALLBACK) {
  const fb = {};
  ok.forEach(r => (r.fallback || []).forEach(x => { const k = [r.key, x.what, x.name || '(без имени)', x.kind, x.why].join(' | '); (fb[k] = fb[k] || []).push(r.id); }));
  console.log('\nУшли узлами или ломаной (модель | что | имя | как | причина — состояний):');
  Object.keys(fb).sort().forEach(k => console.log('   ' + k + ' — ' + fb[k].length + ' (' + fb[k].slice(0, 3).join(', ') + ')'));
}
const failed = selfLeak.length + itemsBad.length + bad.length + DEF.reduce((s, d) => s + (T[d] || 0), 0) + changed.length + domBad.length + histBad.length + lsBad.length + evBad.length + repBad.length + doorBad.length + lintBad.length;
if (STRICT) process.exit(failed ? 1 : 0);
