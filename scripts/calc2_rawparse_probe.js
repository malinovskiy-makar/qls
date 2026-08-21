/* ПРЯМОЙ ПУТЬ РАЗБОРА — сырые строки, без поля ввода.

   ⚠️ Зачем нужен отдельно от «живого пути». Прибор, который печатает формулу в
   поле, меряет не разбор, а СВЯЗКУ «MathLive + поле + разбор»: математическое
   поле кладёт в скрытый input уже переведённую запись, и до разбора сырой
   LaTeX не доезжает вовсе. Такой прибор зеленеет при мёртвом разборе. Здесь
   строки подаются в parsePpfEquation и compilePpf КАК ЕСТЬ.

   Запуск: node scripts/calc2_rawparse_probe.js <порт> <файл.json> */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const PORT = process.argv[2] || '8720';
const OUT  = process.argv[3] || 'reports/calc2_22aug/rawparse.json';
const BASE = `http://127.0.0.1:${PORT}`;

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto(BASE + '/login/', { waitUntil: 'domcontentloaded' });
  if (page.url().includes('login')) {
    await page.fill('input[name="username"]', 'student1');
    await page.fill('input[name="password"]', 'student12345');
    await page.click('button[type=submit], input[type=submit]');
    await page.waitForLoadState('domcontentloaded');
  }
  // Свежий адрес: Django отдаёт скрипты с кэширующими заголовками.
  await page.goto(BASE + '/calc2/?v=' + Date.now(), { waitUntil: 'load' });
  await page.waitForFunction(() => typeof pickScene === 'function', null, { timeout: 20000 });
  const known = await page.evaluate(() => Object.keys(SCENE_ROUTE || {}));
  if (!known.includes('ppf')) { console.error('НЕТ КЛЮЧА СЦЕНЫ ppf'); process.exit(2); }
  await page.evaluate(() => pickScene('ppf'));
  await page.waitForTimeout(900);

  const rows = await page.evaluate(() => {
    const B = String.fromCharCode(92);
    const CASES = ['y=100-ax', 'y=100-a' + B + 'cdot x', 'y=100-a*x', B + 'frac{100}{x}',
                   '100-ax', '100-a' + B + 'cdot x'];
    // Буква обязана иметь значение: без ползунка расчёт честно не может считать.
    // Меряем ОБА случая порознь, иначе «не посчиталось» смешается с «не разобралось».
    const num = v => (typeof v === 'number' && isFinite(v)) ? +v.toFixed(4) : String(v);
    return CASES.map(src => {
      const r = { src };
      try { r.prep = prepExpr(src); } catch (e) { r.prep = 'THROW ' + e.message; }
      try { const c = compilePpf(src); r.compile = c.error || 'ok'; } catch (e) { r.compile = 'THROW ' + e.message; }
      try {
        const p = parsePpfEquation(src);
        r.kind = p.error ? ('ERR ' + p.error) : p.kind;
        if (!p.error && typeof p.f === 'function') {
          // без ползунка
          delete STATE.params.a;
          r.f5_noParam = num(p.f(5));
          // с ползунком a = 1
          STATE.params.a = { value: 1, min: -10, max: 10, step: 0.1 };
          r.f5_a1 = num(p.f(5));
          STATE.params.a.value = 10;
          r.f5_a10 = num(p.f(5));
          delete STATE.params.a;
        }
      } catch (e) { r.kind = 'THROW ' + e.message; }
      return r;
    });
  });

  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(rows, null, 2), 'utf8');
  rows.forEach(r => console.log(
    r.src.padEnd(18), '| prep:', String(r.prep).padEnd(14),
    '| compilePpf:', String(r.compile).slice(0, 26).padEnd(26),
    '| kind:', String(r.kind).slice(0, 26).padEnd(26),
    '| f(5) без ползунка:', String(r.f5_noParam).padEnd(8),
    'a=1:', String(r.f5_a1).padEnd(8), 'a=10:', String(r.f5_a10)));
  await browser.close();
})();
