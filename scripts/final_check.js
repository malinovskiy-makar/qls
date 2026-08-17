/*
 * Сквозная браузерная проверка завершающей сессии ревью 17.08.2026.
 *
 * Питон-тесты не видят этого класса дефектов: они читают разметку, а здесь
 * меряются РЕАЛЬНЫЕ координаты и вычисленные стили на живой странице —
 * общая вертикаль правого края, высота повёрнутых подписей, зазор у черты.
 *
 * Запуск ИЗ КОРНЯ ПРОЕКТА (иначе не разрешится require('playwright')):
 *   node scripts/final_check.js 8501
 * Сервер поднимается на своей базе-снимке:
 *   cp db.sqlite3 db_check.sqlite3
 *   ./venv/bin/python manage.py runserver 8501 --settings=config.settings_check
 */
const { chromium } = require('playwright');

const PORT = process.argv[2] || '8501';
const BASE = 'http://127.0.0.1:' + PORT;
const SOLO_LESSON = 3;        // Мария Ким, индивидуальное
const SOLO_STUDENT = 13;      // она же
const GROUP = 2;              // Экономика 10–11, вторник
const GROUPED_STUDENT = 11;   // Сергей Дмитриев — только в группе

let ok = 0, bad = 0;
function check(name, cond, extra) {
  if (cond) { ok++; console.log('  ✓ ' + name); }
  else { bad++; console.log('  ✗ ' + name + (extra ? ' — ' + extra : '')); }
}

async function login(ctx, email) {
  const page = await ctx.newPage();
  await page.goto(BASE + '/login/');
  await page.fill('input[name=username]', email);
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([page.waitForNavigation(), page.click('button[type=submit]')]);
  return page;
}

(async () => {
  const browser = await chromium.launch();
  // ⚠️ Роли — РАЗНЫЕ контексты: вкладки делят куки, и вход учеником выбил бы
  // сессию репетитора (ловушка сессии 9).
  const tutorCtx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const p = await login(tutorCtx, 'tutor@test.local');

  console.log('\n== ФАЗА 1: занятие и карточка слились ==');
  let r = await p.goto(BASE + '/teacher/groups/' + SOLO_LESSON + '/');
  check('экран индивидуального занятия открыт', r.status() === 200, 'код ' + r.status());
  let html = await p.content();
  let body = html.replace(/<style[\s\S]*?<\/style>/g, '');
  check('кнопки «Карточка ученика» нет', !body.includes('Карточка ученика'));
  check('заметки об ученике в обзоре', body.includes('Заметки об ученике'));
  check('плейсхолдер в предложном падеже', body.includes('Полезная информация о Марии Ким'));
  check('заметки идут ПОСЛЕ истории работ',
        body.indexOf('Заметки об ученике') > body.indexOf('История работ'));

  r = await p.goto(BASE + '/teacher/student/' + SOLO_STUDENT + '/progress/');
  check('карточка индивидуального уводит на занятие',
        p.url().endsWith('/teacher/groups/' + SOLO_LESSON + '/'), p.url());

  r = await p.goto(BASE + '/teacher/student/' + GROUPED_STUDENT + '/progress/');
  check('карточка ученика группы работает как раньше',
        r.status() === 200 && p.url().includes('/progress/'), p.url());
  body = (await p.content()).replace(/<style[\s\S]*?<\/style>/g, '');
  check('на карточке ученика группы заметки на месте', body.includes('Заметки об ученике'));

  console.log('\n== ФАЗА 1: заметка сохраняется с обоих экранов ==');
  await p.goto(BASE + '/teacher/groups/' + SOLO_LESSON + '/');
  await p.fill('.note-form textarea', 'проверка заметки с занятия');
  await p.click('.note-form button[type=submit]');
  await p.waitForTimeout(1000);
  const said = await p.textContent('.note-said');
  check('пометка «сохранено» появилась', (said || '').includes('сохранен'), said);
  await p.reload();
  check('заметка вернулась в поле',
        (await p.inputValue('.note-form textarea')) === 'проверка заметки с занятия');
  check('остались НА ЗАНЯТИИ, а не уехали на карточку',
        p.url().includes('/teacher/groups/' + SOLO_LESSON + '/'), p.url());

  console.log('\n== ФАЗА 2 ==');
  await p.goto(BASE + '/teacher/groups/');
  body = (await p.content()).replace(/<style[\s\S]*?<\/style>/g, '');
  check('кнопки «Мои задачи» на «Учениках» нет', !body.includes('Мои задачи'));
  check('«+ Группа» и «+ Ученик» на месте',
        body.includes('+ Группа') && body.includes('+ Ученик'));
  check('фраза «Всё вовремя» убрана', !body.includes('Всё вовремя'));
  check('«Работ на проверке нет» осталась', body.includes('Работ на проверке нет'));
  r = await p.goto(BASE + '/teacher/problems/');
  check('адрес «Мои задачи» жив', r.status() === 200, 'код ' + r.status());

  await p.goto(BASE + '/teacher/groups/' + GROUP + '/?tab=overview');
  const labels = await p.$$eval('.matrix-head', els => els.map(e => e.textContent.trim()));
  const heights = await p.$$eval('.matrix-head',
                                 els => els.map(e => e.getBoundingClientRect().height));
  check('подписи матрицы длиннее прежних 14 символов',
        Math.max(...labels.map(l => l.length)) > 14,
        'самая длинная ' + Math.max(...labels.map(l => l.length)));
  check('ни одна подпись не срезана потолком', Math.max(...heights) <= 171,
        'макс. высота ' + Math.max(...heights).toFixed(0));
  const theories = labels.filter(l => l.startsWith('Теория'));
  check('две «Теории» различимы', new Set(theories).size === theories.length,
        JSON.stringify(theories));

  const studentPage = await (await browser.newContext(
    { viewport: { width: 1440, height: 1000 } })).newPage();
  await studentPage.goto(BASE + '/login/');
  await studentPage.fill('input[name=username]', 'student1@test.local');
  await studentPage.fill('input[name=password]', 'demo12345');
  await Promise.all([studentPage.waitForNavigation(),
                     studentPage.click('button[type=submit]')]);
  await studentPage.goto(BASE + '/profile/stats/');
  const aligns = await studentPage.$$eval('.hero-cell',
                                          els => els.map(e => getComputedStyle(e).textAlign));
  check('верхний блок статистики выровнен влево',
        aligns.length > 0 && aligns.every(a => a === 'left'), JSON.stringify(aligns));
  const missLinks = await studentPage.$$eval('.miss-go a', els => els.map(e => e.getAttribute('href')));
  check('ссылка промахов ведёт в каталог по теме',
        missLinks.length > 0 && missLinks.every(h => h.includes('/catalog/?topic=')),
        JSON.stringify(missLinks));
  check('ссылки «в игру целиком» больше нет',
        !missLinks.some(h => h === '/game/'), JSON.stringify(missLinks));
  await studentPage.screenshot({ path: 'reports/review/final-stats-hero.png' });

  console.log('\n== ФАЗА 3 ==');
  await p.goto(BASE + '/teacher/groups/' + GROUP + '/?tab=assignments');
  const sides = await p.$$eval('.ass-side',
                               els => els.map(e => Math.round(e.getBoundingClientRect().right)));
  check('правый край карточек на одной вертикали', new Set(sides).size === 1,
        JSON.stringify(sides));
  // ⚠️ Меряем ПЕРЕСЕЧЕНИЕ по вертикали, а не равенство координат: кнопка и
  // пилюля разной высоты, и при выравнивании по центру их верхние края
  // законно отличаются на пиксель.
  const headBoxes = await p.$eval('.ass-head', e => [...e.children].map(k => {
    const r = k.getBoundingClientRect();
    return { top: r.top, bottom: r.bottom, left: r.left };
  }));
  check('кнопка и счётчик на одной горизонтали',
        headBoxes.length === 2
        && headBoxes[0].top < headBoxes[1].bottom
        && headBoxes[1].top < headBoxes[0].bottom,
        JSON.stringify(headBoxes));
  check('кнопка слева, счётчик справа',
        headBoxes.length === 2 && headBoxes[0].left < headBoxes[1].left,
        JSON.stringify(headBoxes.map(b => Math.round(b.left))));

  await p.goto(BASE + '/teacher/groups/' + SOLO_LESSON + '/?tab=overview');
  const gap = await p.$eval('.k-pair', e => getComputedStyle(e).columnGap);
  check('зазор у черты не меньше 6px', parseFloat(gap) >= 6, gap);
  const folds = await p.$$eval('.tp-rest-fold summary', els => els.map(e => e.textContent.trim()));
  check('пустые темы свёрнуты под одну строку',
        folds.length === 1 && /без ответов за период/.test(folds[0]), JSON.stringify(folds));
  // ⚠️ `offsetParent` тут НЕ ГОДИТСЯ: Chromium прячет содержимое закрытого
  // `<details>` через `content-visibility`, бокс у строк остаётся, и первая
  // версия проверки насчитала все 25 строк на свёрнутом блоке. Меряем то,
  // ради чего правка делалась, — ВЫСОТУ блока до и после раскрытия.
  const foldedHeight = await p.$eval('.tp-rest-fold', e => e.getBoundingClientRect().height);
  const rowsInside = await p.$$eval('.tp-rest-fold .tp-row', els => els.length);
  await p.click('.tp-rest-fold summary');
  await p.waitForTimeout(200);
  const openHeight = await p.$eval('.tp-rest-fold', e => e.getBoundingClientRect().height);
  check('свёрнутые темы не занимают экран',
        rowsInside > 5 && openHeight > foldedHeight * 3,
        'строк внутри ' + rowsInside + ', высота ' + foldedHeight.toFixed(0)
        + ' → ' + openHeight.toFixed(0));
  const hintText = await p.textContent('.panel-hint');
  check('дробная доля объяснена на виду', /весом/.test(await p.innerText('body')), hintText);

  console.log('\n== ФАЗА 3.1: контраст органов управления ==');
  await p.goto(BASE + '/teacher/work/compose/');
  const grip = await p.$eval('.wk-grip, #wk-item-tpl',
                             () => null).catch(() => null);
  const gripColor = await p.evaluate(() => {
    const tpl = document.getElementById('wk-item-tpl');
    if (!tpl) { return null; }
    const node = tpl.content.cloneNode(true);
    document.body.appendChild(node);
    const g = document.body.querySelector('.wk-grip');
    const b = document.body.querySelector('.wk-move button');
    return { grip: getComputedStyle(g).color,
             btn: getComputedStyle(b).color,
             border: getComputedStyle(b).borderTopColor };
  });
  check('ручка перетаскивания перекрашена', gripColor && gripColor.grip === 'rgb(91, 100, 114)',
        JSON.stringify(gripColor));
  check('рамка стрелок плотнее границы',
        gripColor && gripColor.border === 'rgba(22, 26, 38, 0.34)', JSON.stringify(gripColor));

  console.log('\n== ФАЗА 4: вкладка «Материалы» ==');
  for (const [id, label] of [[GROUP, 'группа'], [SOLO_LESSON, 'индивидуальное']]) {
    r = await p.goto(BASE + '/teacher/groups/' + id + '/?tab=materials');
    check('«Материалы» открываются (' + label + ')', r.status() === 200, 'код ' + r.status());
    const text = (await p.innerText('body')).replace(/\s+/g, ' ');
    const after = text.split('Материалы').slice(-1)[0].slice(0, 300);
    console.log('    [' + label + '] ' + after);
    await p.screenshot({ path: 'reports/review/final-materials-' + label + '.png',
                         fullPage: true });
  }

  console.log('\nИТОГО: ✓ ' + ok + '   ✗ ' + bad);
  await browser.close();
  process.exit(bad ? 1 : 0);
})();
