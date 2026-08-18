/* Проверка 19 канона (фаза 9), вынесенная вперёд: на странице нет сырого
   шаблонного синтаксиса. Именно такой дефект прошёл мимо всех проверок
   и был виден пользователю на каждой странице /calc2/.
   Запуск: node scripts/calc2_raw_template_probe.js <порт> */
const { chromium } = require('playwright');
const PORT = process.argv[2] || '8601';
const BASE = `http://127.0.0.1:${PORT}`;
const PAGES = ['/calc2/', '/teacher/groups/', '/student/', '/catalog/'];

const scan = () => {
  const bad = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const p = n.parentElement;
    if (!p || p.closest('script, style')) continue;   /* внутри кода это данные */
    const t = n.nodeValue || '';
    for (const mark of ['{#', '#}', '{%', '{{']) {
      if (t.includes(mark)) {
        bad.push({ mark, len: t.length, where: p.tagName,
                   text: t.trim().slice(0, 70) });
        break;
      }
    }
  }
  return bad;
};

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
  let total = 0;
  for (const path of PAGES) {
    const resp = await page.goto(BASE + path, { waitUntil: 'domcontentloaded' });
    const code = resp ? resp.status() : 0;
    const bad = await page.evaluate(scan);
    total += bad.length;
    console.log(`${path}  [${code}]  сырых узлов: ${bad.length}`);
    bad.forEach(b => console.log(`    ${b.mark} в <${b.where}> (${b.len} знаков): ${b.text}`));
  }
  console.log(total === 0 ? '\nЧИСТО: сырого шаблонного синтаксиса нет.'
                          : `\nНАЙДЕНО ${total}`);
  await browser.close();
  process.exit(total === 0 ? 0 : 1);
})();
