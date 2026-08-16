/**
 * Сквозная проверка нового потока создания работы (ревью 17.08).
 *
 * ⚠️ ПРОВЕРКА ОБЯЗАНА СВЕРЯТЬ КОД ОТВЕТА. Первая версия соседнего сценария
 * открывала листок репетитора под учеником, получала 403 и «успешно»
 * мерила ширину страницы ошибки.
 *
 *   node scripts/work_flow_check.js [порт]
 *
 * Сервер поднимается с `config.settings_check` (своя `db_check.sqlite3`),
 * чтобы прогон не оставлял следов в витрине.
 */
const { chromium } = require('playwright');

const PORT = process.argv[2] || '8300';
const BASE = `http://127.0.0.1:${PORT}`;
const GROUP = 2;

let passed = 0;
const failures = [];

function ok(name, condition, detail) {
  if (condition) { passed += 1; return; }
  failures.push(`${name}${detail ? ' — ' + detail : ''}`);
}

async function login(page) {
  await page.goto(`${BASE}/login/`);
  await page.fill('[name=username]', 'tutor@test.local');
  await page.fill('[name=password]', 'demo12345');
  await page.click('button[type=submit]');
  await page.waitForLoadState('networkidle');
}

async function go(page, path) {
  const response = await page.goto(BASE + path);
  ok(`код ответа ${path}`, response.status() === 200, `${response.status()}`);
  await page.waitForLoadState('networkidle');
  return response;
}

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push(String(e)));

  await login(page);

  // ── Шаг 1: отбор ─────────────────────────────────────────────────────
  await go(page, `/teacher/work/?group=${GROUP}`);
  ok('крошка несёт занятие', await page.locator('.crumbs a').nth(1).count() === 1);
  ok('пять вкладок', await page.locator('.wk-tab').count() === 5,
     String(await page.locator('.wk-tab').count()));
  ok('корзина внизу', await page.locator('#wk-bar').count() === 1);
  ok('настроек тут нет', await page.locator('[name=deadline]').count() === 0);
  ok('«Дальше» заперта на пустой корзине',
     await page.locator('#wk-next.is-off').count() === 1);

  // Добавляем три задачи.
  const adds = page.locator('#pane-catalog .wk-add');
  const count = await adds.count();
  ok('карточки нашлись', count >= 3, `${count}`);
  for (let i = 0; i < 3; i += 1) { await adds.nth(i).click(); }
  await page.waitForTimeout(700);
  const tally = await page.locator('#wk-tally').textContent();
  ok('сводка собранного с сервера', /В работе: 3 задачи/.test(tally), tally);
  ok('добавленная карточка гаснет',
     await page.locator('.wk-card.is-added').count() === 3);
  ok('«Дальше» открылась', await page.locator('#wk-next.is-off').count() === 0);

  // «Целиком» — то же окно, что на шаге «Что нашлось».
  await page.locator('#pane-catalog .wk-more').first().click();
  await page.waitForTimeout(900);
  ok('задача раскрылась целиком',
     await page.locator('.wk-card .wk-full .wk-flags').first().isVisible());

  // Переключение вкладок не трогает корзину.
  await page.locator('.wk-tab[data-pane="pane-saved"]').click();
  await page.waitForTimeout(400);
  ok('вкладка сменилась', await page.locator('#pane-catalog').isHidden());
  const afterTab = await page.locator('#wk-tally').textContent();
  ok('корзина пережила вкладку', /3 задачи/.test(afterTab), afterTab);
  await page.locator('.wk-tab[data-pane="pane-catalog"]').click();

  // ── Смена вида работы посреди сбора ──────────────────────────────────
  await page.locator('.bh-kind__opt', { hasText: 'Контрольная' }).click();
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(700);
  ok('вид сменился на том же шаге', page.url().includes('/teacher/work/'), page.url());
  ok('занятие не потерялось', page.url().includes(`group=${GROUP}`), page.url());
  const afterKind = await page.locator('#wk-tally').textContent();
  ok('состав пережил смену вида', /3 задачи/.test(afterKind), afterKind);
  await page.locator('.bh-kind__opt', { hasText: 'Домашка' }).click();
  await page.waitForLoadState('networkidle');

  // ── Шаг 2 (состав) ───────────────────────────────────────────────────
  await page.locator('#wk-next').click();
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(900);
  ok('перешли в состав', page.url().includes('/teacher/work/compose/'), page.url());
  ok('занятие в адресе состава', page.url().includes(`group=${GROUP}`));
  const items = await page.locator('.wk-item').count();
  ok('позиции на месте', items === 3, `${items}`);
  ok('первая «выше» погашена',
     await page.locator('.wk-item .wk-up').first().isDisabled());
  ok('последняя «ниже» погашена',
     await page.locator('.wk-item .wk-down').last().isDisabled());

  // Балл по умолчанию — из сложности задачи (или 1 у теста).
  const points = await page.locator('.wk-pts input').evaluateAll(
    nodes => nodes.map(n => n.value));
  ok('баллы предложены', points.every(v => v && v !== '0'), points.join(','));
  ok('балл не десятка по умолчанию', points.some(v => v !== '10'), points.join(','));

  // Порядок кнопками.
  const before = await page.locator('.wk-title').evaluateAll(
    nodes => nodes.map(n => n.textContent.trim()));
  await page.locator('.wk-item .wk-down').first().click();
  await page.waitForTimeout(900);
  const after = await page.locator('.wk-title').evaluateAll(
    nodes => nodes.map(n => n.textContent.trim()));
  ok('порядок сменился кнопкой', before[0] !== after[0],
     `${before[0]} → ${after[0]}`);

  // Нулевая сумма запирает переход.
  const fields = page.locator('.wk-pts input');
  const n = await fields.count();
  for (let i = 0; i < n; i += 1) { await fields.nth(i).fill('0'); }
  await page.waitForTimeout(1200);
  ok('ноль баллов запирает «Дальше»',
     await page.locator('#wk-next.is-off').count() === 1);
  ok('сказано, чего не хватает',
     /Проставьте баллы/.test(await page.locator('#wk-why').textContent()));
  for (let i = 0; i < n; i += 1) { await fields.nth(i).fill(String(i + 2)); }
  await page.waitForTimeout(1200);
  ok('баллы вернули переход',
     await page.locator('#wk-next.is-off').count() === 0);

  // Дробный балл.
  await fields.first().fill('1,5');
  await page.waitForTimeout(1200);
  const sum = await page.locator('#wk-p').textContent();
  ok('дробный балл принят', sum.includes(','), sum);

  // Раскрытие позиции целиком.
  await page.locator('.wk-open').first().click();
  await page.waitForTimeout(500);
  ok('позиция раскрылась',
     await page.locator('.wk-item .wk-full').first().isVisible());

  // Глазами ученика.
  await page.locator('#wk-eyes-open').click();
  await page.waitForTimeout(500);
  ok('окно «глазами ученика» открылось',
     await page.locator('#wk-eyes.is-open').count() === 1);
  const eyesText = await page.locator('#wk-eyes-list').textContent();
  ok('ответов ученику не показываем', !/Ответ:/.test(eyesText));
  await page.keyboard.press('Escape');

  // ── Шаг 3 (выдача) ───────────────────────────────────────────────────
  await page.locator('#wk-next').click();
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(900);
  ok('перешли в выдачу', page.url().includes('/teacher/work/give/'), page.url());
  ok('занятие отмечено заранее',
     await page.locator(`[name=groups][value="${GROUP}"]`).isChecked());
  ok('без названия выдать нельзя',
     await page.locator('#wk-next.is-off').count() === 1);
  ok('сказано, чего не хватает',
     /впишите название/i.test(await page.locator('#wk-why').textContent()));

  await page.fill('[name=name]', 'Домашка из нового потока');
  await page.waitForTimeout(800);
  ok('название попало в предпросмотр',
     (await page.locator('#wk-paper-name').textContent())
       .includes('Домашка из нового потока'));
  ok('в предпросмотре есть задачи',
     await page.locator('.wk-paper__task').count() === 3);
  ok('выдать теперь можно',
     await page.locator('#wk-next.is-off').count() === 0);
  const giveTally = await page.locator('#wk-tally').textContent();
  ok('сводка считает учеников', /выдаётся/.test(giveTally), giveTally);

  // Кривая дата запирает выдачу.
  await page.locator('.k-date__text').first().fill('99.99.9999');
  await page.locator('.k-date__text').first().blur();
  await page.waitForTimeout(600);
  ok('кривая дата запирает выдачу',
     await page.locator('#wk-next.is-off').count() === 1);
  await page.locator('.k-date__text').first().fill('');
  await page.locator('.k-date__text').first().blur();
  await page.waitForTimeout(600);
  ok('без срока выдать можно',
     await page.locator('#wk-next.is-off').count() === 0);

  // ── Выдача ───────────────────────────────────────────────────────────
  await page.locator('#wk-next').click();
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(700);
  ok('после выдачи открылась сама работа',
     /\/teacher\/groups\/\d+\/assignments\/\d+\//.test(page.url()), page.url());
  const body = await page.locator('body').textContent();
  ok('состав работы на месте', body.includes('Домашка из нового потока'));

  // Корзина занятия очищена: возврат в поток даёт пустой отбор.
  await go(page, `/teacher/work/?group=${GROUP}`);
  await page.waitForTimeout(600);
  ok('корзина очищена после выдачи',
     /ничего нет/.test(await page.locator('#wk-tally').textContent()),
     await page.locator('#wk-tally').textContent());

  // ── Быстрый путь «Выдать сразу» (12.5) ───────────────────────────────
  await go(page, `/teacher/work/?group=${GROUP}`);
  ok('пустая корзина не предлагает выдать сразу',
     await page.locator('#wk-quick').isHidden());
  await page.locator('#pane-catalog .wk-add').first().click();
  await page.waitForTimeout(700);
  ok('«Выдать сразу» появилась', await page.locator('#wk-quick').isVisible());
  await page.locator('#wk-quick').click();
  await page.waitForLoadState('networkidle');
  ok('быстрый путь ведёт в выдачу', page.url().includes('/teacher/work/give/'),
     page.url());
  ok('занятие не потерялось', page.url().includes(`group=${GROUP}`));

  // ── Своя задача внутри потока (13.3) ─────────────────────────────────
  await go(page, `/teacher/work/?group=${GROUP}`);
  await page.locator('.wk-tab', { hasText: 'Написать свою' }).click();
  await page.waitForLoadState('networkidle');
  ok('редактор открылся с занятием', page.url().includes(`group=${GROUP}`),
     page.url());
  const mono = await page.evaluate(() => {
    const a = document.createElement('div');
    a.innerHTML = '<div class="part-row"><textarea></textarea></div>';
    document.body.appendChild(a);
    const font = getComputedStyle(a.querySelector('textarea')).fontFamily;
    a.remove();
    return font;
  });
  ok('поле пункта не моноширинное', !/mono/i.test(mono), mono);

  await page.fill('[name=title]', 'Задача из потока');
  await page.fill('[name=statement]', 'Условие своей задачи.');
  await page.click('#add-part-btn');
  await page.waitForTimeout(400);
  const chip = await page.locator('.part-chip input').first().inputValue();
  ok('буква пункта проставлена сама', chip === 'а', chip);
  ok('подпись «пункт N» на месте',
     /пункт 1/.test(await page.locator('.part-of').first().textContent()));
  await page.fill('[name=part_statement]', 'Найдите TC.');
  await page.fill('[name=part_answer]', '5000');
  await page.waitForTimeout(900);
  ok('превью показывает пункт живьём',
     /Найдите TC/.test(await page.locator('#preview-parts').textContent()));

  await page.click('button[type=submit]');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(900);
  ok('вернулись в поток', page.url().includes('/teacher/work/'), page.url());
  ok('занятие не потерялось после сохранения',
     page.url().includes(`group=${GROUP}`), page.url());
  const ownTally = await page.locator('#wk-tally').textContent();
  ok('своя задача легла в работу', /задач/.test(ownTally), ownTally);
  ok('открыта вкладка своих задач',
     await page.locator('#pane-own').isVisible());
  const ownCard = await page.locator('#pane-own .wk-card__title').first().textContent();
  ok('своя задача видна во вкладке', /Задача из потока/.test(ownCard), ownCard);
  ok('своя задача отмечена как выбранная',
     await page.locator('#pane-own .wk-card.is-added').count() >= 1);

  // ── Окно контрольной переживает переключение вида (12.2) ─────────────
  await go(page, `/teacher/work/give/?group=${GROUP}&kind=exam`);
  await page.locator('.k-date__text').first().fill('20.09.2026, 09:00');
  await page.locator('.k-date__text').first().blur();
  await page.waitForTimeout(500);
  await page.locator('.bh-kind__opt', { hasText: 'Домашка' }).click();
  await page.waitForLoadState('networkidle');
  await page.locator('.bh-kind__opt', { hasText: 'Контрольная' }).click();
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(700);
  const back = await page.locator('.k-date__text').first().inputValue();
  ok('окно контрольной вернулось', /20\.09\.2026/.test(back), back);

  // ── Тёмная тема и узкий экран ────────────────────────────────────────
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.setViewportSize({ width: 380, height: 900 });
  await go(page, `/teacher/work/compose/?group=${GROUP}`);
  const wide = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  ok('состав не уезжает вбок сверх шапки сайта', wide <= 560, `${wide}`);

  ok('консоль браузера чиста', errors.length === 0, errors.slice(0, 3).join(' | '));

  await browser.close();
  console.log(`\nПроверок пройдено: ${passed}`);
  if (failures.length) {
    console.log(`ПРОВАЛЕНО: ${failures.length}`);
    failures.forEach(f => console.log('  ✗ ' + f));
    process.exit(1);
  }
  console.log('Все проверки прошли.');
})();
