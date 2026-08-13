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
let scannedLiterals = 0;

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
    /* Возврат каретки убираем ПЕРЕД срезом комментария. В регулярном
       выражении точка не совпадает с \r, поэтому на файле с CRLF «.*$» не
       доходило до конца строки и строчные комментарии не срезались вовсе:
       проверка молча читала человеческий текст как код. */
    const code = line.replace(/\r/g, '').replace(/\/\/.*$/, '');
    /* В ИСХОДНИКЕ правильная запись выглядит как «\\pi»: два символа слэша
       подряд. Одиночный слэш перед буквой внутри долларов означает, что при
       разборе строки он будет съеден. */
    if (code.includes('$')) {
      scanned++;
      const spans = code.match(/\$[^$]{0,200}\$/g) || [];
      for (const span of spans) {
        const m = span.match(/(^|[^\\])\\[a-zA-Z]/);
        if (m) bad.push(`${file}:${i + 1}  ${span.trim().slice(0, 70)}`);
      }
    }
    /* Команда LaTeX встречается и БЕЗ долларов вокруг: словари подстановок,
       куски преамбулы, тонкие пробелы. Именно так класс и вернулся: словарь
       греческих букв приехал в файл как «'\alpha'», то есть просто «alpha»,
       а «'\,'» — как запятая. Ловим одиночный слэш в любом строковом литерале
       перед буквой или перед запятой (тонкий пробел). */
    const literals = code.match(/'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"/g) || [];
    for (const lit of literals) {
      scannedLiterals++;
      /* Внутри литерала правильный слэш записан парой. Ищем нечётную серию.
         Команда может продолжаться подчёркиванием («\tau_1»), поэтому границу
         слова тут проверять нельзя: с ней проверка молча пропускала ровно
         такие записи. */
      const m = lit.match(/(^|[^\\])\\(?:[a-zA-Z]{2,}|,)/);
      if (!m) continue;
      // Известные однобуквенные escape-последовательности JS — не ошибка.
      bad.push(`${file}:${i + 1}  ${lit.trim().slice(0, 70)}`);
    }
  });
}

console.log('Проверено строк с долларами: ' + scanned + ', строковых литералов: ' + scannedLiterals);
if (bad.length) {
  console.log('\nОдиночный слэш LaTeX внутри строки JS (будет съеден): ' + bad.length);
  bad.forEach(b => console.log('  ' + b));
  process.exit(1);
}
console.log('Одиночных слэшей LaTeX в строках нет.');
