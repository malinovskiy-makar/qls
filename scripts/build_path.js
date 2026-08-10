/**
 * Путь создания работы ЦЕЛИКОМ — проверка связки фаз 2–4 (п. 12.1–12.3).
 *
 * Вход репетитором → «Создание работы» → описать словами → «Разобрать
 * запрос» → раскрыть карточки, отсмотреть условие, выбрать галочками,
 * «Показать ещё 5» (счётчик обращений НЕ растёт) → «Отправить в конструктор
 * подборок» → убрать задачу, поменять балл, название, срок, группа →
 * «Создать работу» → работа создана и открылась.
 *
 * ⚠️ Сценарий жмёт сохраняющие кнопки, поэтому работает по ОТДЕЛЬНОЙ базе
 * (`config.settings_check` → db_check.sqlite3). Витрина не портится.
 * ⚠️ Каждый шаг сверяет КОД ОТВЕТА: страница ошибки тоже отдаёт разметку,
 * и без этой сверки проверка молча меряет не то.
 *
 * Запускать ИЗ КОРНЯ проекта: node scripts/build_path.js [порт] [exam]
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const PORT = process.argv[2] || '8199';
const IS_EXAM = process.argv[3] === 'exam';
const BASE = `http://127.0.0.1:${PORT}`;
const SHOTS = path.join('reports', 'review');

let ok = 0, bad = 0;
function check(name, condition, extra) {
  if (condition) { ok += 1; console.log('  ✓', name); }
  else { bad += 1; console.log('  ✗', name, extra === undefined ? '' : extra); }
}

async function shot(page, name) {
  fs.mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SHOTS, name), fullPage: true });
}

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await ctx.newPage();
  const codes = {};
  page.on('response', (r) => { codes[r.url()] = r.status(); });

  await page.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' });
  await page.fill('input[name=username]', 'tutor@test.local');
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type=submit]'),
  ]);

  const kind = IS_EXAM ? 'exam' : 'homework';
  const genUrl = `${BASE}/teacher/assignment/generate/?kind=${kind}&group=2`;
  let resp = await page.goto(genUrl, { waitUntil: 'networkidle' });
  check('экран подбора открылся (200)', resp.status() === 200, resp.status());

  // ── Шаг 1: описать словами ────────────────────────────────────────────
  await page.fill('#gen-text',
    'домашка по международной торговле: большая открытая экономика, ' +
    'малая открытая экономика, последняя задача с параметром');
  await page.fill('#id_open', '4');
  await page.fill('#id_test', '1');
  const usedBefore = await page.textContent('.gen-used');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle' }),
    page.click('button.k-btn--main'),
  ]);

  // ── Шаг 2: что нашлось ────────────────────────────────────────────────
  const blocks = await page.$$('.plan-block');
  check('карточки запросов появились', blocks.length > 0, blocks.length);
  check('серой строки «Ваша строка» больше нет',
        !(await page.content()).includes('Ваша строка'));

  // раскрыть все карточки (первая уже раскрыта — её не трогаем, иначе
  // клик её ЗАКРОЕТ)
  for (const head of await page.$$('.plan-block:not(.is-open) .q-head')) {
    await head.click();
  }
  const openCount = await page.$$eval('.plan-block.is-open', (n) => n.length);
  check('все карточки раскрываются на месте', openCount === blocks.length,
        `${openCount}/${blocks.length}`);
  await shot(page, `ф02-что-нашлось${IS_EXAM ? '-контрольная' : ''}.png`);

  // кандидатов вдвое, но не меньше пяти
  const sizes = await page.$$eval('.plan-block', (rows) => rows.map((row) => ({
    need: parseInt(row.querySelector('[name=row_count]').value, 10),
    cands: row.querySelectorAll('.cand').length,
  })));
  check('кандидатов вдвое, но не меньше пяти',
        sizes.every((s) => s.cands >= Math.max(5, 2 * s.need) || s.cands === 0),
        JSON.stringify(sizes));

  // отсмотреть условие
  await page.click('.plan-block.is-open .cand-name');
  const shown = await page.$$eval('.cand.is-shown .cand-body',
    (n) => n.map((e) => e.textContent.trim().length));
  check('условие раскрывается прямо в строке',
        shown.length === 1 && shown[0] > 20, JSON.stringify(shown));
  await shot(page, `ф02-условие-раскрыто${IS_EXAM ? '-контрольная' : ''}.png`);

  // «Показать ещё 5» — без обращения к модели
  const firstCount = await page.$$eval('.plan-block .cand', (n) => n.length);
  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/generate/more/')),
    page.click('.plan-block .q-more-btn:not([disabled])'),
  ]);
  await page.waitForTimeout(800);
  const afterCount = await page.$$eval('.plan-block .cand', (n) => n.length);
  check('«Показать ещё 5» добавил кандидатов', afterCount > firstCount,
        `${firstCount} → ${afterCount}`);

  // счётчик обращений не вырос — читаем его со свежего экрана подбора
  // ⚠️ Вкладка ИЗ ТОГО ЖЕ контекста: у новой нет наших кук, и вместо
  // экрана подбора она получила бы страницу входа.
  const probe = await ctx.newPage();
  await probe.goto(genUrl, { waitUntil: 'networkidle' });
  const usedAfter = await probe.textContent('.gen-used');
  await probe.close();
  check('счётчик обращений не вырос', usedBefore.trim() === usedAfter.trim(),
        `${usedBefore.trim()} → ${usedAfter.trim()}`);

  // повтор в другой строке помечен
  const taken = await page.$$eval('.cand.is-taken', (n) => n.length);
  console.log('    повторов, помеченных «уже выбрана»:', taken);
  if (taken) { await shot(page, 'ф02-повтор-помечен.png'); }

  // недобранная строка: снимаем галочку — плашка желтеет
  await page.$eval('.plan-block.is-open .cand-pick:checked', (box) => {
    box.checked = false;
    box.dispatchEvent(new Event('change', { bubbles: true }));
  });
  const short = await page.$$eval('.q-tally.is-short', (n) => n.length);
  check('недобранная строка помечена жёлтым', short > 0, short);
  await shot(page, 'ф02-недобранная-строка.png');

  // вернуть галочку
  await page.$eval('.plan-block.is-open .cand-pick:not(:disabled)', (box) => {
    box.checked = true;
    box.dispatchEvent(new Event('change', { bubbles: true }));
  });

  const picked = await page.$$eval('.cand-pick:checked', (n) => n.length);
  check('что-то выбрано', picked > 0, picked);

  // ── Шаг 3: конструктор подборки ───────────────────────────────────────
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle' }),
    page.click('#to-cart'),
  ]);
  check('конструктор подборки открылся',
        page.url().includes('/assignment/build/'), page.url());
  await page.waitForTimeout(1200);
  const items = await page.$$eval('.bd-item', (n) => n.length);
  check('позиции приехали из корзины', items === picked, `${items} из ${picked}`);
  const sections = await page.$$eval('.bd-sep', (n) => n.map((e) => e.textContent));
  console.log('    подписи частей:', JSON.stringify(sections));

  // убрать одну задачу и поменять балл другой
  await page.click('.bd-item .bd-drop');
  await page.waitForTimeout(300);
  const afterDrop = await page.$$eval('.bd-item', (n) => n.length);
  check('крестик убирает позицию', afterDrop === items - 1,
        `${items} → ${afterDrop}`);
  await page.$eval('.bd-item .bd-points', (f) => {
    f.value = '7';
    f.dispatchEvent(new Event('input', { bubbles: true }));
  });
  const total = await page.textContent('#bd-points');
  check('итог баллов пересчитался', Boolean(total), total);

  const name = 'Проверка связки ' + (IS_EXAM ? 'контрольная' : 'домашка');
  await page.fill('[name=name]', name);
  if (IS_EXAM) {
    // ⚠️ `datetime-local` — МЕСТНОЕ время, а `toISOString()` даёт UTC.
    // Разница в три часа делала окно «в прошлом», и форма законно
    // отказывалась создавать контрольную. Считаем со сдвигом пояса.
    const local = (hours) => {
      const d = new Date(Date.now() + hours * 3600 * 1000);
      d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
      return d.toISOString().slice(0, 16);
    };
    const iso = (h) => local(h);
    check('у контрольной спрашивают окно',
          Boolean(await page.$('[name=starts_at]')));
    await page.fill('[name=starts_at]', iso(24));
    await page.fill('[name=ends_at]', iso(27));
  } else {
    check('у домашки спрашивают срок', Boolean(await page.$('[name=deadline]')));
    await page.fill('[name=deadline]', '2026-12-01T20:00');
  }
  await page.$eval('[name=groups]', (b) => {
    b.checked = true;
    b.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await page.waitForTimeout(200);
  await shot(page, `ф03-конструктор${IS_EXAM ? '-контрольная' : ''}.png`);
  const disabled = await page.$eval('#submit-btn', (b) => b.disabled);
  check('кнопка создания разблокировалась', disabled === false);

  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle' }),
    page.click('#submit-btn'),
  ]);
  const code = codes[page.url()];
  check('после создания открылась страница задания (200)',
        page.url().includes('/assignments/') && code === 200,
        `${page.url()} → ${code}`);
  const banner = await page.textContent('body');
  check('сверху сказано, что работа создана и кому выдана',
        banner.includes('создана и выдана группе'));
  await shot(page, `ф04-после-создания${IS_EXAM ? '-контрольная' : ''}.png`);
  check('на странице есть печать',
        banner.includes('печат') || banner.includes('Печат'));

  console.log(`\nитого: ${ok} успешно, ${bad} неудачно`);
  await browser.close();
  process.exit(bad ? 1 : 0);
})();
