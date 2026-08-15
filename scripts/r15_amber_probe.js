/** Замер контраста янтарных элементов НА ЖИВОЙ СТРАНИЦЕ, а не в токенах. */
const { chromium } = require('playwright');
const BASE = `http://127.0.0.1:${process.argv[2] || '8199'}`;
const TARGETS = [
  ['/teacher/groups/2/assignments/6/students/9/', '.k-flag--partial', 'чип «частично»'],
  ['/teacher/groups/2/?tab=assignments', '.k-count', 'кружок счётчика'],
  ['/teacher/groups/', '.gc-wait', 'чип «N работ ждут проверки»'],
  ['/teacher/groups/2/', '.k-level--mid', 'процент в таблице учеников'],
  ['/teacher/groups/2/', '.matrix-mid', 'клетка теплокарты'],
];
function lum(rgb) {
  const [r, g, b] = rgb;
  const f = [r, g, b].map((v) => { v /= 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
  return 0.2126 * f[0] + 0.7152 * f[1] + 0.0722 * f[2];
}
function ratio(a, b) {
  const [x, y] = [lum(a), lum(b)];
  return Math.round(((Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05)) * 100) / 100;
}
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/login/`);
  await page.fill('input[name=username]', 'tutor@test.local');
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([page.waitForNavigation(), page.click('button[type=submit]')]);
  let bad = 0;
  for (const theme of ['light', 'dark']) {
    console.log(`\n=== тема: ${theme} ===`);
    await page.evaluate((t) => localStorage.setItem('theme', t), theme);
    for (const [url, sel, name] of TARGETS) {
      await page.goto(BASE + url, { waitUntil: 'networkidle' });
      const found = await page.evaluate((sel) => {
        const el = document.querySelector(sel);
        if (!el) return null;
        // Настоящий фон под элементом: поднимаемся, пока фон прозрачный.
        const solid = (node) => {
          while (node) {
            const bg = getComputedStyle(node).backgroundColor;
            const m = bg.match(/rgba?\(([\d.]+), ([\d.]+), ([\d.]+)(?:, ([\d.]+))?\)/);
            if (m && (m[4] === undefined || Number(m[4]) === 1)) {
              return [+m[1], +m[2], +m[3]];
            }
            node = node.parentElement;
          }
          return [255, 255, 255];
        };
        const mix = (fg, alpha, bg) =>
          fg.map((c, i) => Math.round(c * alpha + bg[i] * (1 - alpha)));
        const cs = getComputedStyle(el);
        const own = cs.backgroundColor.match(
          /rgba?\(([\d.]+), ([\d.]+), ([\d.]+)(?:, ([\d.]+))?\)/);
        const under = solid(el.parentElement);
        const bg = own
          ? mix([+own[1], +own[2], +own[3]],
                own[4] === undefined ? 1 : Number(own[4]), under)
          : under;
        const fg = cs.color.match(/rgba?\(([\d.]+), ([\d.]+), ([\d.]+)/);
        return { текст: [+fg[1], +fg[2], +fg[3]], фон: bg,
                 надпись: el.textContent.trim().slice(0, 14) };
      }, sel);
      if (!found) { console.log(`  ? ${name}: элемента нет на ${url}`); continue; }
      const r = ratio(found.текст, found.фон);
      const ok = r >= 4.5;
      if (!ok) bad += 1;
      console.log(`  ${ok ? '+' : '-'} ${name}: ${r}:1  («${found.надпись}»)`);
    }
  }
  console.log(bad ? `\nНИЖЕ НОРМЫ: ${bad}` : '\nВсе янтарные надписи проходят AA');
  await browser.close();
  process.exit(bad ? 1 : 0);
})();
