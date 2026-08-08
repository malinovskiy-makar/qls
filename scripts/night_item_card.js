/*
 * Сценарий карточки позиции (фаза 6): нажать «Подтвердить и включить
 * автопроверку» и убедиться, что состояние меняется СРАЗУ, без перезагрузки,
 * и нигде не остаётся надписи «не утверждено».
 *
 * ⚠️ Именно этот класс бага питон-тесты не видят: страница отдаёт 200,
 * разметка на месте, а расходятся два элемента уже в браузере.
 *
 * Запуск ИЗ КОРНЯ проекта:  node scripts/night_item_card.js [порт]
 */
const { chromium } = require('playwright');

const PORT = process.argv[2] || '8199';
const BASE = `http://127.0.0.1:${PORT}`;
const URL = '/teacher/groups/2/assignments/6/';

let failures = 0;
function check(name, ok, extra) {
  console.log(`${ok ? '  ok  ' : ' FAIL '} ${name}${extra ? ' — ' + extra : ''}`);
  if (!ok) failures += 1;
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });

  await page.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' });
  await page.fill('input[name=username]', 'tutor@test.local');
  await page.fill('input[name=password]', 'demo12345');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type=submit]'),
  ]);
  await page.goto(BASE + URL, { waitUntil: 'networkidle' });

  // 1. Бейдж-капслок должен исчезнуть со страницы целиком.
  //
  // ⚠️ Берём ВИДИМЫЙ текст (innerText), а не textContent: последний
  // возвращает и содержимое <script>, поэтому проверка «на странице нет
  // слов „не утверждено“» краснела на комментарии в нашем же скрипте.
  const visibleText = () => page.evaluate(() => document.body.innerText);
  const body = await visibleText();
  check('нет бейджа «уйдёт на ручную проверку»',
        !body.includes('уйдёт на ручную проверку'));
  check('нет надписи «не утверждено»', !body.includes('не утверждено'));
  check('нет капслока «ПРОВЕРЯЕТСЯ АВТОМАТИЧЕСКИ»',
        !body.includes('ПРОВЕРЯЕТСЯ АВТОМАТИЧЕСКИ'));

  // 2. Заголовки задач видны (раньше их на экране не было вовсе).
  const titles = await page.$$eval('.item-title', (n) => n.map((e) => e.textContent.trim()));
  check('у каждой позиции есть заголовок',
        titles.length === 7 && titles.every((t) => t.length > 0),
        `${titles.length} шт.`);

  // 3. Неутверждённая позиция: блок янтарный, раскрытый, КНОПКА ОДНА.
  const warn = await page.$('.check-state.is-warn');
  check('есть янтарное состояние', !!warn);
  if (warn) {
    const itemId = await warn.getAttribute('data-check');
    check('янтарный блок раскрыт',
          await warn.$eval('.check-fold', (d) => d.open));

    // ФАЗА 3.1 — кнопка ровно одна, надпись по состоянию.
    const buttons = await warn.$$eval('.ans-actions .k-btn',
      (n) => n.filter((b) => getComputedStyle(b).display !== 'none')
              .map((b) => b.textContent.trim()));
    check('кнопка в блоке ровно ОДНА', buttons.length === 1,
          buttons.join(' | '));
    check('надпись кнопки — «Включить автопроверку»',
          buttons[0] === 'Включить автопроверку', buttons[0]);

    // ФАЗА 3.3 — статус написан ОДИН раз, только в заголовке.
    const status = await warn.$eval('.ans-status', (e) => e.textContent.trim());
    check('подписи у кнопки нет', status === '', status);

    // ФАЗА 3.5 — правка полей ПЕРЕЖИВАЕТ переключение режима.
    const probe = 'проверка сохранения 12345';
    await warn.$eval('.ans-input', (e) => { e.value = ''; });
    await warn.$eval('.ans-input', (e, v) => { e.value = v; }, probe);

    // 4. Нажимаем кнопку — состояние обязано смениться на месте.
    await warn.$eval('.ans-toggle', (b) => b.click());
    await page.waitForFunction(
      (id) => {
        const box = document.querySelector('[data-check="' + id + '"]');
        return box && box.classList.contains('is-ok');
      }, itemId, { timeout: 5000 });

    const after = await page.$(`[data-check="${itemId}"]`);
    check('состояние стало зелёным',
          await after.evaluate((b) => b.classList.contains('is-ok')));
    check('заголовок стал «Проверяется само»',
          (await after.$eval('.check-title', (e) => e.textContent.trim()))
            === 'Проверяется само');
    check('значок стал галочкой',
          (await after.$eval('.check-icon', (e) => e.textContent.trim())) === '✓');
    check('блок свернулся',
          !(await after.$eval('.check-fold', (d) => d.open)));

    const shown = await after.$$eval('.ans-actions .k-btn',
      (n) => n.filter((b) => getComputedStyle(b).display !== 'none')
              .map((b) => b.textContent.trim()));
    check('кнопка по-прежнему ОДНА', shown.length === 1, shown.join(' | '));
    check('надпись сменилась на «Проверять вручную»',
          shown[0] === 'Проверять вручную', shown[0]);
    check('в свёрнутой строке эталон БЕЗ слова «эталон:»',
          !(await after.$eval('.check-gist', (e) => e.textContent.trim()))
            .startsWith('эталон:'));

    const bodyAfter = await visibleText();
    check('после нажатия нигде нет «не утверждено»',
          !bodyAfter.includes('не утверждено'));
    // ФАЗА 3.2 — слова «готово» в блоке нет ни в каком состоянии.
    check('слова «готово» на странице нет',
          !/\bготово\b/i.test(bodyAfter));

    // 5. Возврат к ручной проверке — обратно в янтарь, ПОЛЯ ЦЕЛЫ.
    await after.$eval('.ans-toggle', (b) => b.click());
    await page.waitForFunction(
      (id) => {
        const box = document.querySelector('[data-check="' + id + '"]');
        return box && box.classList.contains('is-warn');
      }, itemId, { timeout: 5000 });
    check('вернулось в янтарное состояние', true);
    const kept = await after.$eval('.ans-input', (e) => e.value);
    check('ФАЗА 3.5: введённое в поле НЕ стёрлось', kept === probe,
          `в поле «${kept}»`);

    // ФАЗА 3.7 — кликабельна вся строка заголовка.
    const cursor = await after.$eval('.check-head',
      (e) => getComputedStyle(e).cursor);
    check('курсор над заголовком — указатель', cursor === 'pointer', cursor);
    const openMark = await after.$('.check-open');
    check('значок раскрытия виден', !!openMark);
  }

  // 6. ФАЗА 4 — баллы заперты, потому что работу уже сдавали.
  //
  // ⚠️ Демо-домашка №3 сдана, значит поле балла в ней НЕ редактируется.
  // Проверяем оба состояния: здесь запертое, ниже — правку в работе, по
  // которой ещё никто не отвечал.
  check('в сданной работе поля балла нет',
        !(await page.$('.pts-input')));
  check('крупная цифра балла осталась видна',
        !!(await page.$('.k-score__value')));
  const lockedText = await visibleText();
  check('экран объясняет, почему заперто',
        lockedText.toLowerCase().includes('работу уже сдавали'));

  // 7. Правка максимального балла в НЕсданной работе сохраняется.
  await page.goto(`${BASE}/teacher/groups/2/assignments/12/`,
                  { waitUntil: 'networkidle' });
  const input = await page.$('.pts-input');
  check('в несданной работе поле балла есть', !!input);
  if (input) {
    const wasValue = await input.inputValue();
    await input.fill('7');
    await input.evaluate((e) => e.blur());
    await page.waitForFunction(
      () => {
        const s = document.querySelector('.pts-status');
        return s && s.textContent.trim() === 'сохранено';
      }, null, { timeout: 5000 }).catch(() => {});
    await page.reload({ waitUntil: 'networkidle' });
    const nowValue = await page.$eval('.pts-input', (e) => e.value);
    check('балл сохранился после перезагрузки', nowValue === '7',
          `было ${wasValue}, стало ${nowValue}`);
    // Возвращаем как было, чтобы сценарий можно было гонять повторно.
    const back = await page.$('.pts-input');
    await back.fill(wasValue);
    await back.evaluate((e) => e.blur());
    await page.waitForTimeout(600);
  }

  // 8. ФАЗА 7 — номер стоит у названия, а не над баллом.
  await page.goto(BASE + URL, { waitUntil: 'networkidle' });
  const numInTitle = await page.$('.item-title .item-num');
  check('номер позиции стоит у названия задачи', !!numInTitle);
  const numInRail = await page.$('.item-rail > .item-num');
  check('в рейке номера больше нет', !numInRail);

  check('ошибок в консоли нет', errors.length === 0, errors.slice(0, 3).join(' | '));

  await browser.close();
  console.log(failures ? `\nПРОВАЛЕНО: ${failures}` : '\nвсе проверки прошли');
  process.exit(failures ? 1 : 0);
})();
