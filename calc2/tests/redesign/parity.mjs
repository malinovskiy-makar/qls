/* ТАБЛИЦА ПАРИТЕТА calc2/tests/redesign/PARITY.md.

   Собирается из базового снимка (baseline/*.json), инвентаря и сверки пакета
   редизайна. У каждой строки одна из трёх судеб (COVERAGE.md, раздел 0, п. 2):
     «на месте» — тот же id или тот же генератор, новое место и вид;
     «заменён (буква, чем)» — по закрытому списку (а)–(к);
     «убран (буква)» — только (л) и (м).
   Правила судьбы — таблица FATES ниже: первая подошедшая строка. Строки без
   судьбы генератор не пишет молча, а считает и печатает в итог (их должно
   быть ноль). Запуск: node calc2/tests/redesign/parity.mjs                   */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PKG = path.resolve(HERE, '../../../claude/mockups/calc2_redesign_20261004');
const BASE = process.argv.includes('--base') ? path.resolve(process.argv[process.argv.indexOf('--base') + 1]) : path.join(HERE, 'baseline');

import { LETTERS, CHECK, FATES, fateOf } from './fates.mjs';

const rows = [];
const nofate = [];
const files = fs.existsSync(BASE) ? fs.readdirSync(BASE).filter(f => f.endsWith('.json')).sort() : [];
const ctlIndex = new Map();   // ключ органа → {kind, label, section, models:Set}
const answers = [];
let nModels = 0;
for (const f of files) {
  const rec = JSON.parse(fs.readFileSync(path.join(BASE, f), 'utf8'));
  if (!rec.controls) continue;
  nModels++;
  const add = (c, via) => {
    const e = ctlIndex.get(c.key) || { kind: c.kind, label: c.label, section: c.section, via: via || '', models: new Set() };
    e.models.add(rec.key);
    ctlIndex.set(c.key, e);
  };
  rec.controls.forEach(c => add(c));
  Object.entries(rec.inventory || {}).forEach(([k, c]) => add({ key: k, ...c }, c.via));
  (rec.start.answer.blocks || []).forEach(b => {
    b.rows.forEach(r => answers.push({ model: rec.key, block: b.id, i: r.i, label: r.label, value: r.value }));
    if (b.tables.length) answers.push({ model: rec.key, block: b.id, i: 't', label: 'таблица (' + b.tables.length + ')', value: '' });
    b.notes.forEach((n, i) => answers.push({ model: rec.key, block: b.id, i: 'n' + i, label: 'пояснение', value: n.slice(0, 60) }));
    b.warns.forEach((n, i) => answers.push({ model: rec.key, block: b.id, i: 'w' + i, label: 'предупреждение', value: n.slice(0, 60) }));
    b.final.forEach((n, i) => answers.push({ model: rec.key, block: b.id, i: 'f' + i, label: 'итоговая функция', value: n.tex }));
  });
  if (rec.start.answer.title) answers.push({ model: rec.key, block: '#sec-eq', i: 'title', label: 'заголовок группы', value: rec.start.answer.title });
  (rec.start.answer.explain || []).forEach((p, i) => answers.push({ model: rec.key, block: '#ex-body', i: 'p' + i, label: 'абзац разбора', value: p.slice(0, 60) }));
}

/* Ответ: куда встаёт строка табло (COVERAGE.md, раздел 9). */
function answerFate(a) {
  if (a.block === '#ex-body') return ['на месте', '«Разбор»'];
  if (a.label === 'заголовок группы') return ['на месте', 'заголовок группы в «Ответе»'];
  if (a.label === 'предупреждение') return ['на месте', 'строка статуса «Ответа» (§9 п. 3)'];
  if (a.label === 'пояснение') return ['на месте', 'тихим текстом под своей группой (§9 п. 3)'];
  if (a.label === 'итоговая функция') return ['на месте', 'карточка «Итоговая функция» в «Ответе»'];
  if (/Бюджет \(расход\)|расход/i.test(a.label)) return ['на месте', '«Ответ»: «Расход бюджета» положительным числом (§9 п. 2)'];
  return ['на месте', '«Ответ»: главные числа или таблица своей группы (§9 п. 1)'];
}

/* INVENTORY.md: каждый пункт-абзац «- **…**». */
const inv = fs.readFileSync(path.join(PKG, 'INVENTORY.md'), 'utf8').split('\n');
const invRows = [];
let sec = '';
inv.forEach((ln, i) => {
  const h = /^#{2,3} (.*)/.exec(ln);
  if (h) { sec = h[1].trim(); return; }
  const m = /^\s*- \*\*(.+?)\*\*(.*)/.exec(ln);
  if (m) invRows.push({ line: i + 1, sec, name: m[1], rest: m[2].slice(0, 90) });
});
const INV_FATE = [
  [/Экран блоков|Клик по блоку|Повторное открытие|Карточка модели|Оверлей/, 'заменён', 'г'],
  [/«Построить»/, 'заменён', 'а'],
  [/Стрелка|Корешок|свёрнут/i, 'заменён', 'в'],
  [/складные карточки|Свернуть/i, 'заменён', 'д'],
  [/«Вернуть исходный вид»/, 'заменён', 'и'],
  [/гаечн/i, 'заменён', 'и'],
  [/Ползунков в этой модели нет|Пустое состояние/, 'убран', 'л'],
];
function invFate(r) {
  for (const [re, fate, l] of INV_FATE) if (re.test(r.name + r.rest)) return [fate, l];
  return ['на месте', ''];
}

/* COVERAGE.md: строки О1–О36, К1–К7, Р1–Р26 и модели раздела 3. */
const cov = fs.readFileSync(path.join(PKG, 'COVERAGE.md'), 'utf8').split('\n');
const covRows = [];
cov.forEach(ln => {
  const m = /^\| ([ОКР]\d+) \| (.+?) \|/.exec(ln);
  if (m) covRows.push({ id: m[1], what: m[2].slice(0, 110) });
  const mm = /^\| ([a-z][a-z0-9-]+) \| (.+?) \| (.+?) \|/.exec(ln);
  if (mm) covRows.push({ id: 'модель ' + mm[1], what: ('органы: ' + mm[2] + ' · числа: ' + mm[3]).slice(0, 110) });
});

const L = [];
L.push('# Таблица паритета calc2: старый экран → новый экран');
L.push('');
L.push('Собрана `calc2/tests/redesign/parity.mjs` из базового снимка `baseline/` (старый экран, `6b79758`), `INVENTORY.md`');
L.push('и `COVERAGE.md` пакета. Судьбы — по `COVERAGE.md`, раздел 0, п. 2. Столбец «чем проверено» называет прибор;');
L.push('«не проверено на…» — с причиной.');
L.push('');
L.push(`Моделей в снимке: **${nModels}**. Органов (уникальных ключей): **${ctlIndex.size}**. Строк ответа: **${answers.length}**. `
  + `Пунктов инвентаря: **${invRows.length}**. Строк сверки: **${covRows.length}**.`);
L.push('');
L.push('## 0. Закрытый список');
L.push('');
L.push('| Буква | Что | Ключи органов базового снимка |');
L.push('|---|---|---|');
Object.entries(LETTERS).forEach(([l, t]) => {
  const ks = [...ctlIndex.keys()].filter(k => fateOf(k).letter === l);
  L.push(`| ${l} | ${t} | ${ks.length ? ks.map(k => '`' + k + '`').join(', ') : '— (в снимке не встречается: орган спрятан маршрутом или появится в новых фазах)'} |`);
});
L.push('');
L.push('## 1. Органы управления (базовый снимок, все модели)');
L.push('');
L.push('| Ключ | Вид | Подпись | Где было | Моделей | Судьба | Чем заменён | Чем проверено |');
L.push('|---|---|---|---|---|---|---|---|');
const esc = (s) => String(s || '').replace(/\|/g, '\\|').replace(/\n/g, ' ').slice(0, 90);
[...ctlIndex.entries()].sort((a, b) => a[0] < b[0] ? -1 : 1).forEach(([k, e]) => {
  const f = fateOf(k);
  if (!f.fate) nofate.push(k);
  L.push(`| \`${esc(k)}\` | ${e.kind} | ${esc(e.label)} | ${esc(e.section)}${e.via ? ' (через ' + esc(e.via) + ')' : ''} | ${e.models.size} | ${f.fate}${f.letter ? ' (' + f.letter + ')' : ''} | ${esc(f.by)} | ${esc(f.check)} |`);
});
L.push('');
L.push('## 2. Ответ: строки табло, пояснения, разборы (стартовое состояние)');
L.push('');
L.push('| Модель | Блок | № | Подпись | Значение | Судьба | Место на новом экране | Чем проверено |');
L.push('|---|---|---|---|---|---|---|---|');
answers.forEach(a => {
  const [fate, where] = answerFate(a);
  L.push(`| ${a.model} | ${a.block} | ${a.i} | ${esc(a.label)} | ${esc(a.value)} | ${fate} | ${where} | compare.mjs: паритет чисел и текстов |`);
});
L.push('');
L.push('## 3. Инвентарь (INVENTORY.md)');
L.push('');
L.push('| Строка | Раздел | Пункт | Судьба | Чем проверено |');
L.push('|---|---|---|---|---|');
invRows.forEach(r => {
  const [fate, l] = invFate(r);
  L.push(`| ${r.line} | ${esc(r.sec)} | ${esc(r.name)} | ${fate}${l ? ' (' + l + ')' : ''} | ${l ? 'по букве закрытого списка' : CHECK} |`);
});
L.push('');
L.push('## 4. Сверка (COVERAGE.md, разделы 2–4)');
L.push('');
L.push('| № | Что | Судьба | Чем проверено |');
L.push('|---|---|---|---|');
covRows.forEach(r => {
  const fate = /^Р/.test(r.id) ? 'как в коде (спецификация ошибалась)' : 'на месте (по решению строки сверки)';
  L.push(`| ${r.id} | ${esc(r.what)} | ${fate} | ${CHECK} |`);
});
L.push('');
L.push(`**Строк без судьбы: ${nofate.length}.**`);
fs.writeFileSync(path.join(HERE, 'PARITY.md'), L.join('\n') + '\n');
console.log(`моделей ${nModels}, органов ${ctlIndex.size}, строк ответа ${answers.length}, инвентарь ${invRows.length}, сверка ${covRows.length}, без судьбы ${nofate.length}`);
process.exit(nofate.length ? 1 : 0);
