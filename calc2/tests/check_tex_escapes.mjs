/* Обратные слэши LaTeX внутри строк JS обязаны быть УДВОЕНЫ.

   Класс ошибок, который не виден ни в одном обычном тесте: «$\pi$» в строке
   JavaScript превращается в «$pi$», «$MC_1 \ne MC_2$» — в «MC_1 » + перевод
   строки + «e MC_2», а «\beta» и вовсе несёт символ забоя (U+0008), на котором
   KaTeX рисует красную рамку. Формула при этом остаётся синтаксически
   правильной строкой, файл разбирается, тесты зелёные, а на экране написана
   ерунда или стоит ошибка рендера.

   Проверка идёт по исходникам: берём содержимое строковых литералов, ищем в них
   куски между долларами и смотрим, не остался ли там одиночный слэш перед
   буквой. Запуск: node calc2/tests/check_tex_escapes.mjs */
import { readFileSync, readdirSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const HERE = dirname(fileURLToPath(import.meta.url));
const DIR = join(HERE, '..', 'static', 'calc2');

const bad = [];
let scanned = 0;

for (const file of readdirSync(DIR).filter(f => f.endsWith('.js')).sort()) {
  const lines = readFileSync(join(DIR, file), 'utf8').split('\n');
  /* Комментарии пропускаем: там слэши живут в человеческом тексте и никуда не
     деваются. Блочные считаем по состоянию, построчно их не отличить. */
  let inBlock = false;
  lines.forEach((line, i) => {
    const wasBlock = inBlock;
    const opens = (line.match(/\/\*/g) || []).length;
    const closes = (line.match(/\*\//g) || []).length;
    if (opens > closes) inBlock = true;
    else if (closes > opens) inBlock = false;
    if (wasBlock || opens > 0) return;
    const code = line.replace(/\/\/.*$/, '');
    if (!code.includes('$')) return;
    scanned++;
    /* В ИСХОДНИКЕ правильная запись выглядит как «\\pi»: два символа слэша
       подряд. Одиночный слэш перед буквой внутри долларов означает, что при
       разборе строки он будет съеден. */
    const spans = code.match(/\$[^$]{0,200}\$/g) || [];
    for (const span of spans) {
      const m = span.match(/(^|[^\\])\\[a-zA-Z]/);
      if (m) bad.push(`${file}:${i + 1}  ${span.trim().slice(0, 70)}`);
    }
  });
}

console.log('Проверено строк с долларами: ' + scanned);
if (bad.length) {
  console.log('\nОдиночный слэш LaTeX внутри строки JS (будет съеден): ' + bad.length);
  bad.forEach(b => console.log('  ' + b));
  process.exit(1);
}
console.log('Одиночных слэшей LaTeX в строках нет.');
