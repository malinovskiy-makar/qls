/* Wecon Rush: «Бесконечные тесты» (фаза P5, решение владельца 17.09.2026, ADR 0114).

   Раннер играет практику в Chromium и печатает результат каждой проверки после
   ###RUSH-JSON###. Решение принимает `game/tests/test_browser_practice.py`.

   Инварианты:
   - полоса: название, фильтр и четыре счётчика, без часов, сердец и очков;
   - неверный ответ на задачу банка — разбор с верным ответом и ссылкой в каталог;
     сгенерированный — с решением и без ссылки;
   - пропуск обратим: вернулись к пропущенному — варианты активны, ответ меняет
     квадратик и счётчики; отвеченный из истории — только просмотр;
   - кнопка справа: «Пропустить» / «Дальше» / «Вперёд»;
   - 30 вопросов: в ленте не больше, чем влезает, ранние свёрнуты в «ещё N»,
     «к пропущенным» ведёт к пропущенному;
   - наведение на вариант — только рамка;
   - Esc — «Закончить?», «Да, к итогу» — экран итога со списком и темами;
   - 1440×800: вопрос с пятью вариантами и разбором с решением без прокрутки;
   - телефон: листание прижато к низу, кнопки 50 px, без прокрутки вбок; итог тоже.

   Запуск руками:
     RUSH_BASE_URL=http://127.0.0.1:8000 node game/tests/browser_practice.mjs

   Коды возврата: 0 — прогон дошёл до конца, 3 — браузер не поднялся.     */
import { chromium } from 'playwright';

const BASE = process.env.RUSH_BASE_URL || 'http://127.0.0.1:8000';
const GEN_TOPIC = 'Теория потребителя и полезность';

const out = { checks: {} };
const check = (name, ok, detail) => { out.checks[name] = { ok: !!ok, detail }; };

let browser;
try {
  browser = await chromium.launch();
} catch (e) {
  console.log('браузер не поднялся: ' + e.message);
  process.exit(3);
}

/* Каждый сценарий — отдельно: сбой одного (дефект уронил ожидание) записывается
   в его проверки, а не обрывает весь прогон и не прячет имя проверки. */
const contexts = [];
async function block(names, fn) {
  try {
    await fn();
  } catch (e) {
    const detail = String((e && e.message) || e).slice(0, 400);
    names.forEach((name) => { if (!out.checks[name]) check(name, false, { error: detail }); });
  }
  while (contexts.length) await contexts.pop().close().catch(() => {});
}

async function start({ width = 1440, height = 800, path = '/game/' } = {}) {
  const context = await browser.newContext({ viewport: { width, height } });
  contexts.push(context);
  const page = await context.newPage();
  await page.goto(BASE + path, { waitUntil: 'load', timeout: 30000 });
  await page.waitForSelector('#practice-go:not([disabled])', { timeout: 15000 });
  await page.click('#practice-go');
  await page.waitForSelector('#screen-play.active #opts .opt', { timeout: 15000 });
  return { context, page };
}

const questionText = (page) => page.$eval('#q-text', (el) => el.textContent.trim());

/* Следующий вопрос появился (текст карточки сменился). */
async function waitNewQuestion(page, before) {
  await page.waitForFunction((t) => {
    const el = document.getElementById('q-text');
    return el && el.textContent.trim() !== t && document.querySelectorAll('#opts .opt').length > 1;
  }, before, { timeout: 8000 });
}

/* Неверный ответ: у тестовых вопросов верный — первый вариант. */
async function answerWrong(page) {
  await page.click('#opts .opt:nth-child(2)');
  await page.waitForSelector('#pr-fb:not([hidden])', { timeout: 8000 });
}

try {
  // ── Полоса, разбор неверного ответа, листание и обратимый пропуск ──
  await block(['hud_filter_and_four_tallies', 'wrong_answer_feedback_with_catalog_link', 'hover_is_border_only',
               'history_is_read_only', 'next_label_by_situation', 'skip_is_reversible',
               'escape_asks_then_result_screen'], async () => {
    const { context, page } = await start();
    const hud = await page.evaluate(() => {
      const shown = (sel) => { const el = document.querySelector(sel); return !!el && el.checkVisibility(); };
      return { name: shown('.pr-name'), chip: document.getElementById('pr-filter').textContent,
               tallies: ['pr-answered', 'pr-correct', 'pr-wrong', 'pr-skipped'].filter((id) => shown('#' + id)).length,
               timer: shown('#hud-timer'), lives: shown('#hud-lives'), score: shown('#hud-score') };
    });
    check('hud_filter_and_four_tallies', hud.name && hud.chip === 'все вопросы' && hud.tallies === 4
          && !hud.timer && !hud.lives && !hud.score, hud);

    const firstLabel = await page.$eval('#pr-next-text', (el) => el.textContent);
    const q1 = await questionText(page);
    await page.keyboard.press(' ');                          // пропуск первого
    await waitNewQuestion(page, q1);
    const q2 = await questionText(page);
    await answerWrong(page);
    const fb = await page.evaluate(() => ({
      text: document.getElementById('pr-fb-v').textContent,
      href: document.getElementById('pr-open').getAttribute('href'),
      open: !document.getElementById('pr-open').hidden,
      panel: document.getElementById('pr-fb').textContent,
      afterLabel: document.getElementById('pr-next-text').textContent,
    }));
    check('wrong_answer_feedback_with_catalog_link', /Неверно\./.test(fb.text) && /Верный ответ – 1\./.test(fb.text)
          && fb.open && /^\/catalog\/problem\/\d+\/$/.test(fb.href) && !/Эластичность/.test(fb.panel), fb);

    await page.click('#pr-next');                           // «Дальше» — третий вопрос
    await waitNewQuestion(page, q2);
    const liveLabel = await page.$eval('#pr-next-text', (el) => el.textContent);
    // Наведение на вариант живого вопроса: только рамка, фон тот же.
    await page.mouse.move(5, 5);
    const before = await page.$eval('#opts .opt:nth-child(1)', (b) => getComputedStyle(b).backgroundColor);
    await page.hover('#opts .opt:nth-child(1)');
    await page.waitForTimeout(250);
    const hovered = await page.$eval('#opts .opt:nth-child(1)', (b) => ({
      bg: getComputedStyle(b).backgroundColor, border: getComputedStyle(b).borderTopColor, cls: b.className }));
    check('hover_is_border_only', hovered.bg === before && !/is-correct|show-right/.test(hovered.cls), { before, hovered });

    // Второй (отвеченный) из истории — только просмотр.
    await page.click('#pr-dots .pr-dot:nth-child(2)');
    await page.waitForFunction((t) => document.getElementById('q-text').textContent.trim() === t, q2, { timeout: 5000 });
    const history = await page.evaluate(() => ({
      chip: document.getElementById('pr-state').hidden ? '' : document.getElementById('pr-state').textContent,
      disabled: [...document.querySelectorAll('#opts .opt')].every((b) => b.disabled),
      label: document.getElementById('pr-next-text').textContent,
      fb: !document.getElementById('pr-fb').hidden,
    }));
    check('history_is_read_only', history.chip === 'уже отвечен · только просмотр' && history.disabled
          && history.fb && history.label === 'Вперёд', history);
    check('next_label_by_situation', firstLabel === 'Пропустить' && fb.afterLabel === 'Дальше'
          && liveLabel === 'Пропустить' && history.label === 'Вперёд', { firstLabel, fb, liveLabel, history });

    // Первый (пропущенный) — варианты активны, ответ меняет квадратик и счётчики.
    await page.click('#pr-dots .pr-dot:nth-child(1)');
    await page.waitForFunction((t) => document.getElementById('q-text').textContent.trim() === t, q1, { timeout: 5000 });
    const skipView = await page.evaluate(() => ({
      chip: document.getElementById('pr-state').hidden ? '' : document.getElementById('pr-state').textContent,
      enabled: [...document.querySelectorAll('#opts .opt')].every((b) => !b.disabled),
      label: document.getElementById('pr-next-text').textContent,
      skipped: document.getElementById('pr-skipped').textContent,
    }));
    await page.click('#opts .opt:nth-child(1)');
    // Без .catch сломанный обратимый пропуск ронял бы весь раннер, а не одну проверку.
    await page.waitForSelector('#pr-fb:not([hidden])', { timeout: 8000 }).catch(() => {});
    const afterAnswer = await page.evaluate(() => ({
      dot: document.querySelector('#pr-dots .pr-dot:nth-child(1)').className,
      skipped: document.getElementById('pr-skipped').textContent,
      answered: document.getElementById('pr-answered').textContent,
    }));
    check('skip_is_reversible', skipView.chip === 'пропущен · можно ответить сейчас' && skipView.enabled
          && skipView.label === 'Вперёд' && skipView.skipped === '1' && /\bok\b/.test(afterAnswer.dot)
          && afterAnswer.skipped === '0' && afterAnswer.answered === '2', { skipView, afterAnswer });

    // Esc → «Закончить?» → итог: одна ошибка, «1 из 2», темы с «Решать тему».
    await page.keyboard.press('Escape');
    await page.waitForSelector('#pr-end:not([hidden])', { timeout: 5000 });
    const ask = await page.$eval('#pr-end-title', (el) => el.textContent);
    await page.click('#pr-end-yes');
    await page.waitForSelector('#fin-practice:not([hidden])', { timeout: 8000 });
    await page.waitForTimeout(700);
    const result = await page.evaluate(() => ({
      rows: document.querySelectorAll('#prf-list .miss-item').length,
      bars: document.querySelectorAll('#prf-bars .prf-bar').length,
      solve: [...document.querySelectorAll('#prf-bars button')].map((b) => b.textContent),
      big: document.getElementById('prf-big').textContent,
      round: !document.getElementById('fin-round').hidden,
      screen: document.getElementById('screen-final').classList.contains('active'),
    }));
    check('escape_asks_then_result_screen', ask === 'Закончить?' && result.screen && !result.round
          && result.rows === 1 && result.big === '1 из 2' && result.bars >= 1
          && result.solve.includes('Решать тему'), { ask, result });
  });

  // ── 30 вопросов: лента сворачивает ранние, «к пропущенным» ведёт к пропуску ──
  await block(['many_questions_fold_and_jump'], async () => {
    const { context, page } = await start();
    for (let i = 0; i < 30; i += 1) {
      const t = await questionText(page);
      await page.keyboard.press(' ');
      await waitNewQuestion(page, t);
    }
    const tape = await page.evaluate(() => ({
      dots: document.querySelectorAll('#pr-dots .pr-dot').length,
      many: document.getElementById('pr-tape').classList.contains('is-many'),
      foldN: Number(document.getElementById('pr-fold-n').textContent),
      back: getComputedStyle(document.getElementById('pr-fold-back')).visibility,
      first: document.querySelector('#pr-dots .pr-dot').textContent,
      toSkip: !document.getElementById('pr-to-skip').hidden,
    }));
    await page.click('#pr-fold-back');
    const folded = await page.$eval('#pr-dots .pr-dot', (d) => d.textContent);
    await page.click('#pr-to-skip');
    await page.waitForTimeout(300);
    const jumped = await page.evaluate(() => ({
      chip: document.getElementById('pr-state').textContent,
      cur: document.querySelector('#pr-dots .pr-dot.cur') ? document.querySelector('#pr-dots .pr-dot.cur').className : '',
    }));
    check('many_questions_fold_and_jump', tape.many && tape.dots >= 20 && tape.dots < 31 && tape.foldN >= 1
          && tape.back === 'visible' && Number(folded) < Number(tape.first) && tape.toSkip
          && jumped.chip === 'пропущен · можно ответить сейчас' && /skip/.test(jumped.cur),
          { tape, folded, jumped });
  });

  // ── Сгенерированный вопрос: решение без ссылки; 1440×800 без прокрутки ──
  // Тема есть только у сгенерированных: потолок доли машинных отступает, и
  // первый же вопрос — сгенерированный.
  await block(['generated_solution_without_catalog_link', 'desktop_no_scroll_with_solution'], async () => {
    const { context, page } = await start({ path: '/game/?topics=' + encodeURIComponent(GEN_TOPIC) });
    const found = await page.$eval('#gen-note', (el) => !el.hidden);
    let gen = { found };
    if (found) {
      await answerWrong(page);
      await page.waitForTimeout(300);
      gen = await page.evaluate(() => ({
        found: true,
        sol: !document.getElementById('pr-fb-sol').hidden && document.getElementById('pr-fb-sol-text').textContent,
        open: !document.getElementById('pr-open').hidden,
        options: document.querySelectorAll('#opts .opt').length,
        sh: document.documentElement.scrollHeight, ih: innerHeight,
        foot: Math.round(document.querySelector('.pr-foot').getBoundingClientRect().bottom),
      }));
    }
    check('generated_solution_without_catalog_link', gen.found && !!gen.sol && !gen.open, gen);
    check('desktop_no_scroll_with_solution', gen.found && gen.options === 5 && gen.sh <= gen.ih && gen.foot <= gen.ih, gen);
  });

  // ── Телефон: листание внизу экрана, кнопки 50 px, без прокрутки вбок; итог ──
  await block(['mobile_bottom_bar_no_side_scroll', 'mobile_result_no_side_scroll'], async () => {
    const { context, page } = await start({ width: 390, height: 844 });
    await answerWrong(page);
    const m = await page.evaluate(() => {
      const foot = document.querySelector('.pr-foot').getBoundingClientRect();
      const btns = [...document.querySelectorAll('.pr-foot .pr-nb')].map((b) => Math.round(b.getBoundingClientRect().height));
      const fab = [...document.querySelectorAll('.fb-btn, .tg-fab')].filter((el) => el.checkVisibility()).length;
      return { footBottom: Math.round(foot.bottom), ih: innerHeight, btns, fab,
               sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth };
    });
    check('mobile_bottom_bar_no_side_scroll', m.footBottom === m.ih && m.btns.length === 2
          && m.btns.every((h) => h >= 50) && m.fab === 0 && m.sw <= m.cw, m);
    await page.click('#btn-quit');
    await page.waitForSelector('#pr-end:not([hidden])', { timeout: 5000 });
    await page.click('#pr-end-yes');
    await page.waitForSelector('#fin-practice:not([hidden])', { timeout: 8000 });
    await page.waitForTimeout(700);
    const r = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
    check('mobile_result_no_side_scroll', r.sw <= r.cw, r);
  });
} catch (e) {
  out.error = String((e && e.stack) || e);
}

console.log('###RUSH-JSON###');
console.log(JSON.stringify(out));
await browser.close();
process.exit(0);
