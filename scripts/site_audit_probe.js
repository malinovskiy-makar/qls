/* ФАЗА 8. ОБХОД САЙТА ГЛАЗАМИ БРАУЗЕРА.
 *
 * Что собирается на каждом адресе × ширине × теме:
 *   · ошибки консоли и разбора скриптов (`pageerror` — их в console НЕТ);
 *   · упавшие запросы и ответы 4xx/5xx на СВОИ же адреса;
 *   · горизонтальное переполнение документа;
 *   · элементы, вылезшие за правый край окна;
 *   · внутренние ссылки, отвечающие 404 или 500 (собираются со всех страниц
 *     и проверяются один раз в конце — иначе один и тот же адрес
 *     проверялся бы десятки раз).
 *
 * ⚠️ POST-адреса и `/admin/` не открываются: GET по ним либо 405, либо
 * ведёт в чужой контур. Список — ниже, поимённо.
 *
 * Запуск: node scripts/site_audit_probe.js <порт> [файл.json]
 */
const { chromium } = require('playwright');
const fs = require('fs');

const PORT = process.argv[2] || '8901';
const OUT = process.argv[3] || 'reports/site_polish_20260904/audit.json';
const BASE = `http://127.0.0.1:${PORT}`;

const BOTS = {
  student: ['shot_bot', 'probebot-local-2026'],
  teacher: ['shot_bot_teacher', 'probebot-local-2026'],
};

/* Адрес → каким ролям он вообще открыт. Гость проверяется на публичных. */
const PAGES = [
  ['/', ['guest', 'student', 'teacher']],
  ['/catalog/', ['guest', 'student', 'teacher']],
  ['/catalog/map/', ['guest', 'student']],
  ['/textbook/', ['guest', 'student']],
  ['/olympiads/', ['guest', 'student']],
  ['/calc2/', ['guest', 'student']],
  ['/game/', ['guest', 'student']],
  ['/login/', ['guest']],
  ['/register/', ['guest']],
  ['/calendar/', ['student', 'teacher']],
  ['/profile/', ['student', 'teacher']],
  ['/profile/stats/', ['student']],
  ['/student/', ['student']],
  ['/teacher/groups/', ['teacher']],
  ['/teacher/groups/create/', ['teacher']],
  ['/teacher/problems/', ['teacher']],
  ['/teacher/work/', ['teacher']],
  ['/teacher/styleguide/', ['teacher']],
];

const WIDTHS = [1440, 1024, 380];
const THEMES = ['light', 'dark'];

const findings = [];
const linkPool = new Set();

function note(role, url, width, theme, kind, detail) {
  findings.push({ role, url, width, theme, kind, detail });
}

async function login(page, role) {
  const [user, pass] = BOTS[role];
  await page.goto(BASE + '/login/', { waitUntil: 'domcontentloaded' });
  await page.fill('input[name="username"]', user);
  await page.fill('input[name="password"]', pass);
  await page.click('button[type=submit], input[type=submit]');
  await page.waitForLoadState('domcontentloaded');
  if (page.url().includes('/login')) throw new Error('вход ролью ' + role);
}

(async () => {
  const browser = await chromium.launch();

  for (const role of ['guest', 'student', 'teacher']) {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await page.setViewportSize({ width: 1440, height: 900 });
    if (role !== 'guest') await login(page, role);

    for (const [url, roles] of PAGES) {
      if (!roles.includes(role)) continue;
      for (const theme of THEMES) {
        for (const width of WIDTHS) {
          const consoleErrors = [];
          const failed = [];
          const onConsole = m => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 180)); };
          const onPageError = e => consoleErrors.push('pageerror: ' + String(e).slice(0, 180));
          const onFailed = r => failed.push(r.url().slice(0, 140));
          const onResponse = r => {
            if (r.status() >= 400 && r.url().startsWith(BASE)) {
              failed.push(r.status() + ' ' + r.url().slice(BASE.length, BASE.length + 120));
            }
          };
          page.on('console', onConsole);
          page.on('pageerror', onPageError);
          page.on('requestfailed', onFailed);
          page.on('response', onResponse);

          await page.setViewportSize({ width, height: 800 });
          await page.goto(BASE + url, { waitUntil: 'load' });
          await page.evaluate(t => {
            try { localStorage.setItem('theme', t); } catch (e) {}
            if (t === 'dark') document.documentElement.setAttribute('data-theme', 'dark');
            else document.documentElement.removeAttribute('data-theme');
          }, theme);
          await page.waitForTimeout(700);

          const box = await page.evaluate(() => {
            const doc = document.documentElement;
            /* Элементы, вылезшие за правый край. Скрытые и заведомо
               «уезжающие» контейнеры с прокруткой не в счёт. */
            const out = [];
            const limit = doc.clientWidth + 2;
            document.querySelectorAll('body *').forEach(el => {
              const style = getComputedStyle(el);
              if (style.display === 'none' || style.visibility === 'hidden') return;
              if (style.position === 'fixed') return;
              const r = el.getBoundingClientRect();
              if (r.width === 0 || r.height === 0) return;
              if (r.right > limit) {
                /* Внутри блока со своей прокруткой — не находка. */
                let p = el.parentElement, scrolls = false;
                while (p && p !== document.body) {
                  const ps = getComputedStyle(p);
                  if (['auto', 'scroll', 'hidden'].includes(ps.overflowX)) { scrolls = true; break; }
                  p = p.parentElement;
                }
                if (!scrolls) out.push((el.tagName + '.' + String(el.className)).slice(0, 60)
                                       + ' → ' + Math.round(r.right));
              }
            });
            return {
              scroll: doc.scrollWidth, client: doc.clientWidth,
              overflowing: [...new Set(out)].slice(0, 4),
              links: [...document.querySelectorAll('a[href^="/"]')]
                .map(a => a.getAttribute('href')).slice(0, 60),
            };
          });

          page.off('console', onConsole);
          page.off('pageerror', onPageError);
          page.off('requestfailed', onFailed);
          page.off('response', onResponse);

          box.links.forEach(h => linkPool.add(h.split('#')[0]));
          if (consoleErrors.length) note(role, url, width, theme, 'консоль', consoleErrors.slice(0, 3));
          if (failed.length) note(role, url, width, theme, 'запрос', [...new Set(failed)].slice(0, 3));
          if (box.scroll > box.client + 1) {
            note(role, url, width, theme, 'едет вбок', box.scroll + ' > ' + box.client);
          }
          if (box.overflowing.length) {
            note(role, url, width, theme, 'за краем', box.overflowing);
          }
        }
      }
    }
    await ctx.close();
  }

  /* ── Внутренние ссылки: каждая проверяется ОДИН раз ──────────────── */
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await login(page, 'teacher');
  const badLinks = [];
  const links = [...linkPool].filter(
    h => h && h.startsWith('/') && !h.startsWith('//') && !h.startsWith('/admin/')
         && !h.startsWith('/logout') && !h.startsWith('/media/'));
  for (const href of links) {
    /* ⚠️ РЕДИРЕКТЫ СЛЕДУЕМ, А НЕ СЧИТАЕМ ОШИБКОЙ. С `redirect: 'manual'`
       fetch отдаёт непрозрачный ответ со статусом 0, и живые адреса вроде
       `/catalog/random/` попадали в «битые» — первая версия пробы так и
       доложила пять несуществующих поломок. */
    const status = await page.evaluate(async (u) => {
      try {
        const r = await fetch(u, { method: 'GET', credentials: 'same-origin' });
        return r.status;
      } catch (e) { return -1; }
    }, href);
    /* 403 у чужого кабинета — это работающая граница, а не битая ссылка:
       обход идёт под учителем, а `/student/…` закрыт от него намеренно. */
    const foreignCabinet = status === 403 && href.startsWith('/student/');
    if ((status >= 400 || status < 0) && !foreignCabinet) {
      badLinks.push(href + ' → ' + status);
    }
  }
  await ctx.close();
  await browser.close();

  const report = { findings, links: { checked: links.length, bad: badLinks } };
  fs.mkdirSync('reports/site_polish_20260904', { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(report, null, 2), 'utf8');

  const byKind = {};
  findings.forEach(f => { byKind[f.kind] = (byKind[f.kind] || 0) + 1; });
  console.log('НАХОДОК:', findings.length, JSON.stringify(byKind));
  findings.slice(0, 25).forEach(f =>
    console.log(`  ${f.kind.padEnd(10)} ${f.role.padEnd(8)} ${String(f.width).padStart(4)}px ${f.theme.padEnd(5)} ${f.url} :: ${JSON.stringify(f.detail).slice(0, 150)}`));
  console.log(`ССЫЛОК проверено ${links.length}, битых ${badLinks.length}`);
  badLinks.slice(0, 15).forEach(l => console.log('  ' + l));
})();
