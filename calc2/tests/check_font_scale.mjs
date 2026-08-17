/* Запрет писать размер шрифта числом (решение штаба от 13.08, пункт А4).

   Было 84 места, где кегль вбит числом, и этих чисел двенадцать: 9, 9.5, 10,
   10.5, 11, 11.5, 12, 12.5, 13, 13.5, 14, 15. Это не шкала, а осадок десятка
   сессий; разницу в полпункта глаз читает как неряшливость.

   Теперь шкала одна: FS.small / FS.base / FS.large / FS.title (и FS_PT — та же
   шкала в пунктах для бумаги). Проверка идёт по коду ОТРИСОВКИ: числовой
   font-size в нём означает, что кто-то снова завёл свой размер мимо шкалы.

   Запуск: node calc2/tests/check_font_scale.mjs */
import { readFileSync, readdirSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const HERE = dirname(fileURLToPath(import.meta.url));
const DIR = join(HERE, '..', 'static', 'calc2');

const bad = [];
let scanned = 0;

for (const file of readdirSync(DIR).filter(f => f.endsWith('.js')).sort()) {
  const lines = readFileSync(join(DIR, file), 'utf8').replace(/\r/g, '').split('\n');
  let inBlock = false;
  lines.forEach((line, i) => {
    const wasBlock = inBlock;
    const opens = (line.match(/\/\*/g) || []).length;
    const closes = (line.match(/\*\//g) || []).length;
    if (opens > closes) inBlock = true;
    else if (closes > opens) inBlock = false;
    if (wasBlock || opens > 0) return;
    const code = line.replace(/\/\/.*$/, '');
    scanned++;
    // Числовой размер шрифта в коде отрисовки: .attr('font-size', 12) и
    // строковые «font-size: 12px» внутри разметки, которую собирает JS.
    if (/\.attr\(\s*['"]font-size['"]\s*,\s*[0-9.]+\s*\)/.test(code)
        || /font-size:\s*[0-9.]+px/.test(code)) {
      bad.push(`${file}:${i + 1}  ${code.trim().slice(0, 90)}`);
    }
  });
}

console.log('Проверено строк кода: ' + scanned);
if (bad.length) {
  console.log('\nРазмер шрифта задан числом мимо шкалы FS: ' + bad.length);
  bad.forEach(b => console.log('  ' + b));
  console.log('\nИспользуйте FS.small / FS.base / FS.large / FS.title.');
  process.exit(1);
}
console.log('Числовых кеглей в коде отрисовки нет: вся шкала через FS.');
