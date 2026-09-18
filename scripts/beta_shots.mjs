/* Снимки экранов беты для приёмки глазами (ночь 18.09.2026, A8.2).

   Что снимает: главная; каталог с поиском и плашкой «Нашли, что искали?»
   (обе стадии); каталог с плашкой «Всё ли нравится?»; профиль с новыми
   полями и карточкой Telegram; страница задачи с чипами двух файлов;
   Wecon Rush — старт и окно фильтров; окно обратной связи с середины
   каталога. Ширины 1440 и 390, темы light и dark.

   Вход — сессией, выписанной Django (`manage.py shell`): пароли демо-
   аккаунтов локально бывают погашены (`lockdown_dev_accounts`), а снимкам
   пароль не нужен. Правила показа плашек срабатывают через состояние
   localStorage/sessionStorage в `addInitScript` — отладочных параметров в
   боевом коде нет.

   Запуск (сервер уже поднят на порту):
     node scripts/beta_shots.mjs <префикс> [порт] [набор]
   Выход: reports/beta_20260918/shots/<префикс>_<имя>_<тема>_<ширина>.png

   Набор `stol` (дневная сессия «Стол», 18.09.2026) — экраны единого экрана
   каталога, выход в reports/stol_20260918/shots/; `stol:s1` — только сцены
   фазы S1 (префикс сцены до двоеточия).
   Для каждого экрана печатает, не шире ли документ окна, и ошибки консоли. */
import { chromium } from 'playwright';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const PREFIX = process.argv[2] || 'beta';
const PORT = process.argv[3] || '8611';
const SET = process.argv[4] || 'beta';
const BASE = 'http://127.0.0.1:' + PORT;
const OUT = SET.startsWith('stol') ? path.join('reports', 'stol_20260918', 'shots')
                                   : path.join('reports', 'beta_20260918', 'shots');
const PY = process.platform === 'win32' ? 'venv313/Scripts/python.exe' : 'venv313/bin/python';
const WIDTHS = [[1440, 900], [390, 844]];
const THEMES = ['light', 'dark'];
const PROBLEM_ID = 63315;

/* Сессия на пользователя — ключ куки `sessionid`. */
function sessionFor(username) {
  const code = [
    'from django.contrib.sessions.backends.db import SessionStore',
    'from django.contrib.auth import get_user_model, BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY',
    "u = get_user_model().objects.get(username='" + username + "')",
    's = SessionStore()',
    's[SESSION_KEY] = str(u.pk)',
    "s[BACKEND_SESSION_KEY] = 'django.contrib.auth.backends.ModelBackend'",
    's[HASH_SESSION_KEY] = u.get_session_auth_hash()',
    's.create()',
    "print('KEY=' + s.session_key)",
  ].join('\n');
  const out = execFileSync(PY, ['manage.py', 'shell', '-c', code], { encoding: 'utf8' });
  return out.match(/KEY=(\w+)/)[1];
}

/* Состояние, при котором плашка показывается сразу. */
const NOW = Date.now();
const STATE = {
  none: {},
  search: { local: { weco_sr: { n: 2, last: 0 } } },
  pulse: { local: { weco_pulse: { visits: 1, shown: [] } } },
};

function initScript(theme, state) {
  return `(() => {
    try {
      localStorage.setItem('theme', ${JSON.stringify(theme)});
      localStorage.setItem('weco_pulse', JSON.stringify({ visits: 0, shown: [${NOW}] }));
      const loc = ${JSON.stringify((state.local) || {})};
      Object.keys(loc).forEach(k => localStorage.setItem(k, JSON.stringify(loc[k])));
    } catch (e) {}
  })();`;
}

const shots = [];
async function snap(page, name, theme, width) {
  const file = path.join(OUT, `${PREFIX}_${name}_${theme}_${width}.png`);
  await page.screenshot({ path: file });
  const fits = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
  shots.push({ file, fits });
  console.log((fits ? 'ok  ' : 'ШИРЕ') + ' ' + file);
}

async function run() {
  fs.mkdirSync(OUT, { recursive: true });
  const student = sessionFor('student1@test.local');
  const browser = await chromium.launch();
  const errors = [];

  for (const [width, height] of WIDTHS) {
    for (const theme of THEMES) {
      const open = async (state, cookie) => {
        const ctx = await browser.newContext({ viewport: { width, height } });
        if (cookie) {
          await ctx.addCookies([{ name: 'sessionid', value: cookie, url: BASE }]);
        }
        await ctx.addInitScript(initScript(theme, state));
        const page = await ctx.newPage();
        // Поиск на локальной базе идёт по словам ~15 с на запрос.
        page.setDefaultNavigationTimeout(120000);
        page.on('pageerror', e => errors.push(`[${theme} ${width}] pageerror ${e.message}`));
        page.on('console', m => { if (m.type() === 'error') errors.push(`[${theme} ${width}] ${m.text()}`); });
        return { ctx, page };
      };

      // Главная.
      let { ctx, page } = await open(STATE.none);
      await page.goto(BASE + '/', { waitUntil: 'load' });
      await snap(page, 'home', theme, width);
      await ctx.close();

      // Каталог с поиском: третий поиск → плашка через 15 с на выдаче.
      ({ ctx, page } = await open(STATE.search));
      await page.clock.install();
      await page.goto(BASE + '/catalog/?q=' + encodeURIComponent('монополист с двумя заводами'),
                      { waitUntil: 'load' });
      await page.clock.runFor(16000);
      await page.waitForSelector('#corner-stack .corner-card', { timeout: 5000 });
      await snap(page, 'search_rating_ask', theme, width);
      await page.click('#corner-stack [data-sr="no"]');
      await snap(page, 'search_rating_why', theme, width);
      await ctx.close();

      // «Всё ли нравится?»: второй визит, минута на сайте.
      ({ ctx, page } = await open(STATE.pulse));
      await page.clock.install();
      await page.goto(BASE + '/catalog/', { waitUntil: 'load' });
      await page.clock.runFor(61000);
      await page.waitForSelector('#corner-stack .corner-card', { timeout: 5000 });
      await snap(page, 'pulse_ask', theme, width);
      await page.click('#corner-stack [data-pulse="like"]');
      await snap(page, 'pulse_why', theme, width);
      await ctx.close();

      // Профиль ученика: новые поля и карточка Telegram.
      ({ ctx, page } = await open(STATE.none, student));
      await page.goto(BASE + '/profile/', { waitUntil: 'load' });
      await snap(page, 'profile_top', theme, width);
      await page.locator('.pf-beta-note').scrollIntoViewIfNeeded();
      await snap(page, 'profile_fields', theme, width);
      await page.locator('.pf-tg').scrollIntoViewIfNeeded();
      await snap(page, 'profile_telegram', theme, width);

      // Задача: два файла в чипах (подставлены в состояние чата страницы).
      await page.goto(BASE + '/catalog/problem/' + PROBLEM_ID + '/', { waitUntil: 'load' });
      const hasChat = await page.$('#ai-att');
      if (hasChat) {
        await page.evaluate(() => {
          const tpl = document.getElementById('ai-chip-tpl');
          const att = document.getElementById('ai-att');
          ['тетрадь-1.jpg', 'решение.pdf'].forEach(name => {
            const chip = tpl.content.firstElementChild.cloneNode(true);
            chip.querySelector('.ai-chip-name').textContent = name;
            att.appendChild(chip);
          });
          att.hidden = false;
          att.scrollIntoView({ block: 'center' });
        });
        await snap(page, 'problem_chips', theme, width);
      } else {
        console.log('нет чата на странице задачи (помощник выключен локально) — снимок чипов пропущен');
      }
      await ctx.close();

      // Wecon Rush: старт и окно фильтров с раскрытым разделом.
      ({ ctx, page } = await open(STATE.none));
      await page.goto(BASE + '/game/', { waitUntil: 'load' });
      await snap(page, 'game_start', theme, width);
      await page.click('#filter-open');
      await page.click('#topic-accs .fl-acc[data-group="micro"] [data-acc-toggle]');
      await page.waitForTimeout(400);
      await snap(page, 'game_filters', theme, width);
      await ctx.close();

      // Окно обратной связи с середины каталога.
      ({ ctx, page } = await open(STATE.none));
      await page.goto(BASE + '/catalog/', { waitUntil: 'load' });
      await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight / 2));
      if (await page.locator('.fb-btn').first().isVisible()) {
        await page.locator('.fb-btn').first().click();
        await page.waitForSelector('.fb-back', { timeout: 8000 });
        await page.waitForTimeout(300);
        await snap(page, 'feedback', theme, width);
      } else {
        console.log('кнопка обратной связи не видна на ' + width + ' — снимок окна пропущен');
      }
      await ctx.close();
    }
  }
  await browser.close();
  const wide = shots.filter(s => !s.fits && s.file.includes('_390'));
  console.log(`\nснимков ${shots.length}; шире окна на 390: ${wide.length}; ошибок консоли: ${errors.length}`);
  errors.forEach(e => console.log('  ' + e));
  process.exit(wide.length || errors.length ? 1 : 0);
}

/* ── Набор «Стол» ─────────────────────────────────────────────────────
   Сцена — { phase, name, who, widths, go(page) }. Поиск на локальной базе
   идёт по словам 12–15 с — таймауты с запасом. */
const QUERY = 'монополист с двумя заводами и налогом';
/* Облако фона стартует лениво (простой браузера, данные, раскладка) — для
   кадра дожидаемся данных и досчитываем раскладку вручную (pump). */
async function settleBg(p) {
  await p.waitForFunction(() => {
    const el = document.getElementById('stol-bg');
    return !el || (el.__tmapPreview && el.__tmapPreview.stats().nodes > 0);
  }, null, { timeout: 60000 });
  await p.evaluate(() => { const el = document.getElementById('stol-bg'); if (el) el.__tmapPreview.pump(150); });
}
const STOL_SCENES = [
  { phase: 's1', name: 'entry_empty', go: async p => {
      await p.goto(BASE + '/catalog/', { waitUntil: 'load' }); await p.waitForTimeout(1500); } },
  { phase: 's1', name: 'entry_search', go: async p => {
      await p.goto(BASE + '/catalog/?q=' + encodeURIComponent(QUERY), { waitUntil: 'load' });
      await p.waitForTimeout(1500); } },
  { phase: 's1', name: 'entry_topic_dd', go: async p => {
      await p.goto(BASE + '/catalog/', { waitUntil: 'load' }); await p.waitForTimeout(800);
      await p.click('[data-dd="topic"]'); await p.waitForTimeout(400); } },
  { phase: 's1', name: 'entry_filters', go: async p => {
      await p.goto(BASE + '/catalog/?topic=843&topic=99&tag=652', { waitUntil: 'load' });
      await p.waitForTimeout(1800); } },
  { phase: 's1', name: 'entry_continue', who: 'student', go: async p => {
      await p.goto(BASE + '/catalog/', { waitUntil: 'load' }); await p.waitForTimeout(1500); } },
];

async function runStol() {
  fs.mkdirSync(OUT, { recursive: true });
  const phase = SET.includes(':') ? SET.split(':')[1] : '';
  const scenes = STOL_SCENES.filter(sc => !phase || sc.phase === phase);
  const sessions = { student: sessionFor('student1@test.local') };
  const browser = await chromium.launch();
  const errors = [];
  for (const sc of scenes) {
    for (const [width, height] of (sc.widths || [[1440, 900], [1280, 800]])) {
      for (const theme of THEMES) {
        const ctx = await browser.newContext({ viewport: { width, height } });
        if (sc.who) await ctx.addCookies([{ name: 'sessionid', value: sessions[sc.who], url: BASE }]);
        await ctx.addInitScript(initScript(theme, STATE.none));
        const page = await ctx.newPage();
        page.setDefaultNavigationTimeout(120000);
        page.setDefaultTimeout(60000);
        page.on('pageerror', e => errors.push(`[${sc.name} ${theme} ${width}] pageerror ${e.message}`));
        page.on('console', m => { if (m.type() === 'error') errors.push(`[${sc.name} ${theme} ${width}] ${m.text()}`); });
        await sc.go(page);
        await settleBg(page);
        await snap(page, sc.name, theme, width);
        await ctx.close();
      }
    }
  }
  await browser.close();
  console.log(`
снимков ${shots.length}; ошибок консоли: ${errors.length}`);
  errors.forEach(e => console.log('  ' + e));
  process.exit(errors.length ? 1 : 0);
}

if (SET.startsWith('stol')) runStol(); else run();
