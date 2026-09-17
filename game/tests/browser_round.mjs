/* Wecon Rush: экран раунда (фаза P2, ADR 0109 и 0110).

   Раннер гоняет живую страницу игры в Chromium и печатает результат каждой
   проверки после ###RUSH-JSON###. Решение принимает
   `game/tests/test_browser_round.py::RoundBrowserTest`.

   Инварианты:
   - отсчёт 3-2-1: до его конца вопроса нет и таймер стоит; Enter — сразу;
   - на 1440×800 нет прокрутки: Блиц с пятью вариантами и Классика с условием в
     600 знаков; время на полосе — «m:ss»; шапка сайта скрыта;
   - у варианта три колонки, номер в первой, пятый вариант — на обе колонки;
   - неверный ответ: pause → через 3000 ± 100 мс resume и следующий вопрос; во
     время разбора цифра не отвечает; пробел — resume раньше трёх секунд;
   - ответ, нажатый сразу после разбора, уходит только после того, как
     вернулась подкачка следующего вопроса (одна очередь запросов забега);
   - чип рекорда есть у вошедшего с рекордом и отсутствует у гостя;
   - телефон 390×844 на разборе ошибки: ни прокрутки, ни кнопок меньше 44 px.

   Запуск руками:
     RUSH_BASE_URL=http://127.0.0.1:8000 RUSH_SESSION=значение_sessionid node game/tests/browser_round.mjs

   Коды возврата: 0 — прогон дошёл до конца, 3 — браузер не поднялся.     */
import { chromium } from 'playwright';

const BASE = process.env.RUSH_BASE_URL || 'http://127.0.0.1:8000';
const SESSION = process.env.RUSH_SESSION || '';

const out = { checks: {} };
const check = (name, ok, detail) => { out.checks[name] = { ok: !!ok, detail }; };

let browser;
try {
  browser = await chromium.launch();
} catch (e) {
  console.log('браузер не поднялся: ' + e.message);
  process.exit(3);
}
const host = new URL(BASE).hostname;

async function open(path, withSession) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 800 } });
  if (withSession && SESSION) {
    await context.addCookies([{ name: 'sessionid', value: SESSION, domain: host, path: '/' }]);
  }
  const page = await context.newPage();
  const log = [];
  const done = [];
  const name = (r) => {
    const u = r.url();
    return /\/game\/api\/(pause|resume|answer|question)\//.test(u) ? u.split('/game/api/')[1] : null;
  };
  page.on('request', (r) => { if (name(r)) log.push([name(r), Date.now()]); });
  page.on('requestfinished', (r) => { if (name(r)) done.push([name(r), Date.now()]); });
  await page.goto(BASE + path, { waitUntil: 'load', timeout: 30000 });
  await page.waitForSelector('#screen-start.active', { timeout: 15000 });
  return { context, page, log, done };
}

const fillFrac = (page) => page.$eval('#time-fill', (el) => {
  const m = /scaleX\(([-\d.e]+)\)/.exec(el.style.transform || '');
  return m ? parseFloat(m[1]) : NaN;
});
const questionText = (page) => page.$eval('#q-text', (el) => el.textContent.trim());
const noScroll = (page) => page.evaluate(() => ({
  sh: document.documentElement.scrollHeight, ih: window.innerHeight,
  sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth,
}));

try {
  // ── Блиц, гость: отсчёт, раскладка, разбор ────────────────────────────
  {
    const { context, page, log, done } = await open('/game/?mode=blitz', false);
    await page.keyboard.press('Enter');
    await page.waitForSelector('#screen-play.active', { timeout: 15000 });
    await page.waitForTimeout(900);
    const cd = await page.evaluate(() => ({
      shown: !document.getElementById('countdown').hidden,
      q: document.getElementById('q-text').textContent.trim(),
      n: document.getElementById('cd-n').textContent.trim(),
    }));
    const f0 = await fillFrac(page);
    await page.waitForTimeout(700);
    const f1 = await fillFrac(page);
    check('countdown_holds_question_and_clock', cd.shown && cd.q === '' && f0 === 1 && f1 === 1,
          { cd, f0, f1 });
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => document.getElementById('q-text').textContent.trim().length > 0,
                               null, { timeout: 5000 });
    const started = await page.evaluate(() => document.getElementById('countdown').hidden);
    check('enter_skips_countdown', started, { started });

    const m = await page.evaluate(() => {
      const nav = document.querySelector('nav.site-nav');
      const opts = Array.from(document.querySelectorAll('#opts .opt'));
      const o = opts[0];
      const cols = o ? getComputedStyle(o).gridTemplateColumns.split(' ').length : 0;
      const key = o && o.querySelector('.key').getBoundingClientRect();
      const last = opts[opts.length - 1];
      const grid = document.getElementById('opts').getBoundingClientRect();
      return {
        playing: document.body.classList.contains('rush-playing'),
        navHidden: !nav || getComputedStyle(nav).display === 'none',
        timer: document.getElementById('hud-timer').textContent.trim(),
        options: opts.length, cols,
        keyInFirstCol: !!(key && o && key.left - o.getBoundingClientRect().left < 20),
        lastWide: !!(last && Math.abs(last.getBoundingClientRect().width - grid.width) < 2),
        rec: !document.getElementById('hud-rec').hidden,
      };
    });
    const s1 = await noScroll(page);
    check('blitz_five_options_no_scroll', m.options === 5 && s1.sh <= s1.ih && s1.sw <= s1.cw, { m, s1 });
    check('timer_is_m_ss', /^\d+:\d{2}$/.test(m.timer), m.timer);
    check('site_header_hidden', m.playing && m.navHidden, m);
    check('option_grid_three_columns', m.cols === 3 && m.keyInFirstCol && m.lastWide, m);
    check('guest_has_no_record_chip', !m.rec, m);

    // Неверный ответ (верный у тестовых вопросов — первый): разбор 3 с.
    const before = log.length;
    const q1 = await questionText(page);
    await page.keyboard.press('2');
    await page.waitForSelector('#reveal:not([hidden])', { timeout: 5000 });
    await page.waitForTimeout(300);
    const answersBefore = log.filter((x) => x[0] === 'answer/').length;
    await page.keyboard.press('3');                       // цифра во время разбора
    await page.waitForTimeout(300);
    const answersAfter = log.filter((x) => x[0] === 'answer/').length;
    const paused = await page.evaluate(() => !document.getElementById('hud-paused').hidden);
    check('digits_do_not_answer_during_reveal', answersAfter === answersBefore && paused,
          { answersBefore, answersAfter, paused });
    await page.waitForFunction((q) => document.getElementById('q-text').textContent.trim() !== q
                               && document.getElementById('reveal').hidden, q1, { timeout: 6000 });
    const seq = log.slice(before);
    const p = seq.find((x) => x[0] === 'pause/');
    const r = seq.find((x) => x[0] === 'resume/');
    const gap = p && r ? r[1] - p[1] : null;
    check('reveal_pause_to_resume_3000ms', gap !== null && Math.abs(gap - 3000) <= 100, { gap });

    // Пробел во время разбора — дальше раньше трёх секунд.
    const before2 = log.length;
    const q2 = await questionText(page);
    await page.keyboard.press('2');
    await page.waitForSelector('#reveal:not([hidden])', { timeout: 5000 });
    await page.waitForTimeout(500);
    // Подкачку следующего вопроса сервер отдаёт с задержкой 400 мс: так ответ,
    // нажатый сразу после разбора, наверняка застаёт её в пути.
    await page.route('**/game/api/question/', async (route) => {
      await new Promise((r) => setTimeout(r, 400));
      await route.continue();
    });
    const doneBefore2 = done.length;
    await page.keyboard.press(' ');
    await page.waitForFunction((q) => document.getElementById('q-text').textContent.trim() !== q, q2,
                               { timeout: 4000 }).catch(() => {});
    const seq2 = log.slice(before2);
    const p2 = seq2.find((x) => x[0] === 'pause/');
    const r2 = seq2.find((x) => x[0] === 'resume/');
    const gap2 = p2 && r2 ? r2[1] - p2[1] : null;
    check('space_ends_reveal_early', gap2 !== null && gap2 < 2500, { gap2 });

    // Верный ответ (третья ошибка кончила бы раунд) сразу, пока подкачка в
    // пути: он обязан уйти ПОСЛЕ её возвращения, а не вместе с ней.
    const before3 = log.length;
    await page.keyboard.press('1');
    await page.waitForFunction(() => false, null, { timeout: 900 }).catch(() => {});
    const ans = log.slice(before3).find((x) => x[0] === 'answer/');
    const qDone = done.slice(doneBefore2).find((x) => x[0] === 'question/');
    check('answer_waits_for_prefetch', !!(ans && qDone && ans[1] >= qDone[1]),
          { answerAt: ans && ans[1], prefetchDone: qDone && qDone[1] });
    await context.close();
  }

  // ── Классика, длинное условие ─────────────────────────────────────────
  {
    const { context, page } = await open('/game/?mode=classic', false);
    await page.keyboard.press('Enter');
    await page.waitForSelector('#screen-play.active', { timeout: 15000 });
    await page.keyboard.press('Enter');                 // без отсчёта
    await page.waitForFunction(() => document.getElementById('q-text').textContent.trim().length > 500,
                               null, { timeout: 8000 }).catch(() => {});
    const len = (await questionText(page)).length;
    const s = await noScroll(page);
    const inputVisible = await page.evaluate(() => {
      const r = document.getElementById('num-input').getBoundingClientRect();
      return r.height > 0 && r.bottom <= window.innerHeight;
    });
    check('classic_600_chars_no_scroll', len >= 600 && s.sh <= s.ih && inputVisible, { len, s, inputVisible });
    await context.close();
  }

  // ── Телефон 390×844: разбор ошибки не даёт прокрутки вбок, цели от 44 px ──
  {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const page = await context.newPage();
    await page.goto(BASE + '/game/?mode=blitz', { waitUntil: 'load', timeout: 30000 });
    await page.waitForSelector('#screen-start.active', { timeout: 15000 });
    await page.click('#play-btn');
    await page.waitForSelector('#screen-play.active', { timeout: 15000 });
    await page.click('#countdown-card');
    await page.waitForFunction(() => document.querySelectorAll('#opts .opt').length > 1, null, { timeout: 8000 });
    await page.evaluate(() => document.querySelectorAll('#opts .opt')[1].click());
    await page.waitForSelector('#reveal:not([hidden])', { timeout: 5000 });
    await page.waitForTimeout(200);                       // «−1» у сердец ещё виден
    const mob = await page.evaluate(() => {
      const small = [];
      document.querySelectorAll('#screen-play button, #screen-play input').forEach((el) => {
        const r = el.getBoundingClientRect();
        if (r.width && r.height && (r.width < 44 || r.height < 44)) {
          small.push([el.id || el.className, Math.round(r.width), Math.round(r.height)]);
        }
      });
      return { sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth,
               sh: document.documentElement.scrollHeight, ih: window.innerHeight, small };
    });
    check('mobile_reveal_no_side_scroll_targets_44', mob.sw <= mob.cw && mob.sh <= mob.ih && mob.small.length === 0, mob);
    await context.close();
  }

  // ── Вошедший с рекордом: чип рекорда ──────────────────────────────────
  if (SESSION) {
    const { context, page } = await open('/game/?mode=blitz', true);
    await page.keyboard.press('Enter');
    await page.waitForSelector('#screen-play.active', { timeout: 15000 });
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => document.getElementById('q-text').textContent.trim().length > 0,
                               null, { timeout: 8000 }).catch(() => {});
    const rec = await page.evaluate(() => {
      const el = document.getElementById('hud-rec');
      return { shown: !el.hidden, text: el.textContent.trim() };
    });
    check('student_record_chip', rec.shown && /рекорд\s*1\s?260\s*·\s*ещё\s*1\s?260/.test(rec.text), rec);
    await context.close();
  }
} catch (e) {
  out.error = String((e && e.stack) || e);
}

console.log('###RUSH-JSON###');
console.log(JSON.stringify(out));
await browser.close();
process.exit(0);
