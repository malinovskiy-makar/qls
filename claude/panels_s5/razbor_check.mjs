/* Проверка «Разбора» по правке А4 (тихие панели, сессия 5; README пакета 6, 10): перенесённые из «Условия» и
   «Ответа» абзацы (.ex-from-cond, .ex-from-answer) — только экономика и математика.
   По всем 42 моделям, в перенесённых абзацах:
     · нет слов из закрытого списка интерфейса (INTERFACE ниже);
     · нет слов капсом длиннее 3 букв, кроме сокращений (ABBR);
     · нет «_» в видимом тексте, нет моноширинного шрифта;
     · нет пары «перенесённая фраза ↔ фраза вопроса или ответа «Разбора» (или другая перенесённая)» с совпадением
       ≥ 80 % (слова по основе: доля слов одной фразы в другой или общая доля);
     · между соседними перенесёнными абзацами отступ ≥ 8 px.
   node claude/panels_s5/razbor_check.mjs [выгрузка.json]   — без аргумента снимает выгрузку сам (сервер 8099,
   BASE=…; razbor_dump.mjs). Код 0 — всё чисто. */
import fs from 'fs';
import { execFileSync } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';
const HERE = path.dirname(fileURLToPath(import.meta.url));
let file = process.argv[2];
if (!file) {
  file = path.join(HERE, 'tmp', 'razbor_check_now.json');
  fs.mkdirSync(path.dirname(file), { recursive: true });
  execFileSync('node', [path.join(HERE, 'razbor_dump.mjs'), file], { stdio: 'inherit' });
}
const D = JSON.parse(fs.readFileSync(file, 'utf8'));
// Закрытый список слов интерфейса (README 6: «тянуть мышью», переключатели, «можно писать», «поле», «ползунок»,
// «роль D», «буква становится ползунком», «пустое поле значит», как устроен поиск внутри).
export const INTERFACE = [/тянуть/i, /тяните/i, /перетаскива/i, /мыш(ью|кой)/i, /переключат/i, /переключите/i, /можно писать/i,
  /пишите/i, /(^|[^а-яё])пол(е|я|ем)([^а-яё]|$)/i, /ползун/i, /\(роль|роль [DSM]/i, /пуст(ое|ым) пол/i, /щёлкн|щелкн/i, /нажм/i, /кнопк/i,
  /галочк/i, /включите/i, /задайте/i, /двигайте/i, /двигая/i, /введите/i, /вводятся/i, /способ[ау]? ввода/i,
  /тройн(ой|ым) поиск/i, /ищется численно/i, /движок/i, /калькулятор/i, /строка принимает/i, /в карточке/i, /в «Функциях»/i,
  /в «Параметрах»/i];
const ABBR = new Set(['МРОТ', 'MRPL', 'MRTS', 'LRAS', 'SRAS', 'P90', 'P10']);
const stem = (w) => w.slice(0, 5);
const words = (s) => (s.toLowerCase().replace(/ё/g, 'е').match(/[a-zа-я0-9]{2,}/g) || []).map(stem);
const sentences = (t) => t.split(/(?<=[.!?])\s+/).map(x => x.trim()).filter(Boolean);
function sim(a, b) {
  const A = new Set(words(a)), B = new Set(words(b));
  if (A.size < 5 || B.size < 3) return 0;
  let n = 0; A.forEach(w => { if (B.has(w)) n++; });
  return n / A.size;                       // доля слов перенесённой фразы, которые есть в другой
}
const bad = [];
let nPar = 0, nSent = 0;
for (const [key, m] of Object.entries(D)) {
  const qa = [...m.qs, ...m.as].flatMap(sentences);
  m.tr.forEach((p, i) => {
    nPar++;
    const where = key + ' [' + p.from + ' ' + (i + 1) + ']';
    INTERFACE.forEach(re => { if (re.test(p.text)) bad.push(where + ': интерфейс ' + re + ' «' + p.text.slice(0, 70) + '»'); });
    (p.text.match(/[A-ZА-ЯЁ]{4,}/g) || []).filter(w => !ABBR.has(w) && !/[a-zа-яё]/.test(w)).forEach(w => bad.push(where + ': капс «' + w + '»'));
    if (p.text.includes('_')) bad.push(where + ': «_» в тексте «' + p.text.slice(0, 60) + '»');
    if (p.mono) bad.push(where + ': моноширинный шрифт');
    sentences(p.text).forEach(s => {
      nSent++;
      const hit = qa.find(q => sim(s, q) >= 0.8);
      if (hit) bad.push(where + ': повтор вопроса/ответа «' + s.slice(0, 60) + '» ↔ «' + hit.slice(0, 60) + '»');
      m.tr.forEach((o, j) => { if (j !== i) sentences(o.text).forEach(t => { if (j > i && sim(s, t) >= 0.8 && sim(t, s) >= 0.8) bad.push(where + ': повтор перенесённой фразы «' + s.slice(0, 60) + '»'); }); });
    });
    const next = m.tr[i + 1];
    if (next && next.top - p.bottom < 8) bad.push(where + ': отступ до следующего абзаца ' + Math.round(next.top - p.bottom) + ' px');
  });
}
bad.forEach(x => console.log('  ✗ ' + x));
console.log((bad.length ? 'РАЗБОР НЕ ЧИСТ' : 'РАЗБОР ЧИСТ') + ': моделей ' + Object.keys(D).length + ', перенесённых абзацев ' + nPar + ', фраз ' + nSent + ', замечаний ' + bad.length);
process.exit(bad.length ? 1 : 0);
