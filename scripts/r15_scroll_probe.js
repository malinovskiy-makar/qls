/** Замер прокручиваемых блоков: полоса, растворение, клавиатура. */
const { chromium } = require('playwright');
const BASE = `http://127.0.0.1:${process.argv[2] || '8199'}`;
const BLOCKS = [
  ['/teacher/groups/2/', '.fade-box', 'теплокарта', 'x'],
  ['/teacher/student/11/progress/', '.fade-box', 'история работ ученика', 'x'],
  ['/teacher/assignment/create/?group=2', '.hw-sidebar', 'панель конструктора', 'y'],
];
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1100, height: 700 } });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/login/`);
  await page.fill('input[name=username]', 'tutor@test.local');
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([page.waitForNavigation(), page.click('button[type=submit]')]);
  for (const [url, sel, name, axis] of BLOCKS) {
    await page.goto(BASE + url, { waitUntil: 'networkidle' });
    const info = await page.evaluate(({ sel, axis }) => {
      const box = document.querySelector(sel);
      if (!box) return null;
      const sc = box.querySelector('[data-scroller]') || box.firstElementChild;
      const overflow = axis === 'y'
        ? sc.scrollHeight - sc.clientHeight : sc.scrollWidth - sc.clientWidth;
      const before = getComputedStyle(box, '::before');
      const after = getComputedStyle(box, '::after');
      return {
        переполнение: overflow,
        полосаСпрятана: getComputedStyle(sc).scrollbarWidth === 'none',
        вначале: box.classList.contains('is-start'),
        вконце: box.classList.contains('is-end'),
        левоеВидно: before.opacity !== '0',
        правоеВидно: after.opacity !== '0',
        табиндекс: sc.getAttribute('tabindex'),
        подпись: sc.getAttribute('aria-label'),
      };
    }, { sel, axis });
    console.log(`\n${name}: ${JSON.stringify(info, null, 1)}`);
    if (!info || info.переполнение <= 1) continue;
    // Прокручиваем с клавиатуры и смотрим, поехало ли.
    const moved = await page.evaluate(({ sel, axis }) => {
      const box = document.querySelector(sel);
      const sc = box.querySelector('[data-scroller]') || box.firstElementChild;
      sc.focus();
      const was = axis === 'y' ? sc.scrollTop : sc.scrollLeft;
      return { фокус: document.activeElement === sc, было: was };
    }, { sel, axis });
    await page.keyboard.press(axis === 'y' ? 'ArrowDown' : 'ArrowRight');
    await page.keyboard.press(axis === 'y' ? 'ArrowDown' : 'ArrowRight');
    await page.waitForTimeout(120);
    const after2 = await page.evaluate(({ sel, axis }) => {
      const box = document.querySelector(sel);
      const sc = box.querySelector('[data-scroller]') || box.firstElementChild;
      return { стало: axis === 'y' ? sc.scrollTop : sc.scrollLeft,
               левоеВидно: getComputedStyle(box, '::before').opacity !== '0',
               вначале: box.classList.contains('is-start') };
    }, { sel, axis });
    console.log(`  клавиатура: фокус=${moved.фокус}, было=${moved.было},`
      + ` стало=${after2.стало}, левое растворение=${after2.левоеВидно}`);
  }
  await browser.close();
})();
