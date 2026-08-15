const { chromium } = require('playwright');
const BASE = `http://127.0.0.1:${process.argv[3] || '8199'}`;
const PAGES = [
  ['/teacher/groups/2/', 'обзор занятия'],
  ['/teacher/groups/2/assignments/6/', 'задание целиком'],
  ['/teacher/groups/2/assignments/6/submissions/', 'сводка решений'],
  ['/teacher/groups/2/assignments/6/students/9/', 'разбор глазами ученика'],
  ['/teacher/groups/2/students/', 'ученики группы'],
  ['/teacher/assignment/create/?group=3', 'конструктор домашки'],
  ['/teacher/assignment/generate/?group=2', 'подбор по описанию'],
  ['/teacher/assignment/build/?group=2', 'конструктор подборки'],
  ['/teacher/problems/new/', 'своя задача'],
  ['/teacher/problems/', 'мои задачи'],
  ['/teacher/student/11/progress/', 'карточка ученика'],
  ['/teacher/groups/new/', 'новая группа'],
  ['/teacher/groups/2/exams/new/', 'конструктор контрольной'],
];
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/login/`);
  await page.fill('input[name=username]', 'tutor@test.local');
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([page.waitForNavigation(), page.click('button[type=submit]')]);
  const theme = process.argv[2] || 'light';
  await page.evaluate((t) => localStorage.setItem('theme', t), theme);
  for (const [url, name] of PAGES) {
    const r = await page.goto(BASE + url, { waitUntil: 'domcontentloaded' });
    const info = await page.evaluate(() => {
      const box = document.querySelector('.crumbs');
      if (!box) return { есть: false, backLink: !!document.querySelector('.back-link, a[href^="javascript"]') };
      const cs = getComputedStyle(box);
      const arrows = [...box.children].map((el) => {
        const b = getComputedStyle(el, '::before');
        return { тег: el.tagName, стрелка: b.content, цвет: b.color };
      });
      const links = [...box.querySelectorAll('a')].map((a) => {
        const s = getComputedStyle(a);
        return { текст: a.textContent.trim(), цвет: s.color, подчёркивание: s.textDecorationLine, вес: s.fontWeight };
      });
      // Есть ли ХОТЬ ОДНО правило с селектором .crumbs в таблицах стилей
      let rules = 0;
      for (const sheet of document.styleSheets) {
        let list; try { list = sheet.cssRules; } catch (e) { continue; }
        for (const rule of list) {
          if (rule.selectorText && rule.selectorText.includes('.crumbs')) rules += 1;
        }
      }
      return {
        есть: true, правил: rules,
        контейнер: { цвет: cs.color, кегль: cs.fontSize, отступ: cs.marginBottom },
        ссылки: links, звенья: arrows,
        текст: box.textContent.replace(/\s+/g, ' ').trim().slice(0, 90),
      };
    });
    console.log(`\n${name} [${r.status()}] ${url}`);
    console.log(JSON.stringify(info, null, 1));
  }
  await browser.close();
})();
