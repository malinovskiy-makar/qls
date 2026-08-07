/*
 * UX-аудит кабинета преподавателя — съёмка фактуры, ничего не чинит.
 *
 * Владелец прошёл кабинет руками, написал 25 замечаний по внешнему виду и
 * работе экранов. Этот скрипт снимает 21 экран в 3 ширинах (светлая тема) +
 * те же 21 экран в 1440 (тёмная тема), плюс два PDF версии для печати.
 * Решение о правках — за владельцем, скрипт только документирует.
 *
 * Запуск ИЗ КОРНЯ проекта (иначе require('playwright') не разрешится):
 *   node scripts/ux_audit_shots.js [порт] [файл-лога-сервера]
 *
 * Сервер должен быть уже поднят на этом порту, демо-данные залиты
 * (./venv/bin/python manage.py seed_platform_demo). Экраны 19–21 требуют
 * ANTHROPIC_API_KEY у сервера — без ключа страница честно скажет «функция
 * выключена», это не баг скрипта.
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const PORT = process.argv[2] || '8199';
const LOG_FILE = process.argv[3] || '/tmp/qls_runserver_8199.log';
const BASE = `http://127.0.0.1:${PORT}`;

const OUT_SHOTS = 'reports/ux_audit/shots';
const OUT_PDF = 'reports/ux_audit/pdf';
const META_PATH = 'reports/ux_audit/meta.json';
const ERROR_MD = 'reports/ux_audit/error-progress.md';

const TUTOR = { username: 'tutor@test.local', password: 'demo12345' };
const GEN_QUERY = 'Домашка на КПВ и КТВ из 5 задач. Первая задача — вывод ' +
  'функции КПВ, вторая и третья на сложение КПВ, 4 и 5 на построение КТВ';

// Известные id демо-данных (см. reconnaissance в начале сессии):
// группа 2, домашка 6, submission 16 (ответ есть) и 97 (сдано БЕЗ ответа,
// student2 по задаче-позиции 1), позиция 32 — единственная неутверждённая
// (order=6, catalog_problem_id=53708) — на ней демонстрируем Утвердить/До-После.
const GROUP = 2;
const ASSIGNMENT = 6;
const SUB_WITH_ANSWER = 16;
const SUB_NO_ANSWER = 97;
const UNAPPROVED_ITEM = 32;
const STUDENT_FOR_PROGRESS = 9; // student1@test.local

fs.mkdirSync(OUT_SHOTS, { recursive: true });
fs.mkdirSync(OUT_PDF, { recursive: true });

function fname(num, name, width, theme) {
  return `${num}-${name}__${width}__${theme}.png`;
}

async function login(page) {
  await page.goto(`${BASE}/login/`, { waitUntil: 'domcontentloaded' });
  await page.fill('input[name=username]', TUTOR.username);
  await page.fill('input[name=password]', TUTOR.password);
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle' }),
    page.click('button[type=submit]'),
  ]);
}

async function settle(page) {
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.waitForTimeout(250);
}

// Одна запись метаданных на экран: используется отчётом Фазы 5.
function makeEntry(num, name, title) {
  return { num, name, title, url: null, status: null, loadMs: null,
           consoleErrors: [], notes: [], files: [] };
}

async function widestOverflow(page) {
  return page.evaluate(() => {
    let worst = null;
    document.querySelectorAll('body *').forEach((el) => {
      const r = el.getBoundingClientRect();
      if (r.width === 0) return;
      if (!worst || r.right > worst.right) {
        worst = { right: Math.round(r.right), tag: el.tagName,
                  cls: (el.className || '').toString().slice(0, 60) };
      }
    });
    return {
      scrollW: document.documentElement.scrollWidth,
      clientW: document.documentElement.clientWidth,
      widest: worst,
    };
  });
}

/**
 * Снимает ОДИН прогон (одна ширина + одна тема) все 22 пункта списка.
 * Возвращает массив meta-записей.
 */
async function runScreens(browser, { width, theme, doPdf }) {
  const consoleBucket = [];
  const context = await browser.newContext({
    viewport: { width, height: 900 },
    deviceScaleFactor: 1,
  });
  if (theme === 'dark') {
    // Тот же способ, что и переключатель в _nav.html: анти-мигание читает
    // localStorage ДО первой отрисовки, поэтому достаточно проставить ключ
    // заранее — кликать переключатель на каждой странице не нужно.
    await context.addInitScript(() => {
      try { localStorage.setItem('theme', 'dark'); } catch (e) { /* noop */ }
    });
  }
  const page = await context.newPage();
  page.on('console', (m) => {
    const t = m.type();
    if (t === 'error' || t === 'warning') consoleBucket.push(`[${t}] ${m.text()}`);
  });
  page.on('pageerror', (e) => consoleBucket.push(`[pageerror] ${e.message}`));

  const meta = [];

  async function goto(entry, url) {
    entry.url = url;
    consoleBucket.length = 0;
    const t0 = Date.now();
    try {
      const resp = await page.goto(BASE + url, { waitUntil: 'networkidle', timeout: 30000 });
      entry.status = resp ? resp.status() : null;
    } catch (e) {
      entry.notes.push('НАВИГАЦИЯ ОШИБКА: ' + e.message);
    }
    await page.waitForTimeout(250);
    entry.loadMs = Date.now() - t0;
    entry.consoleErrors = consoleBucket.slice();
    if (width === 380) {
      entry.overflow = await widestOverflow(page).catch(() => null);
    }
  }

  async function shootFull(entry) {
    const file = fname(entry.num, entry.name, width, theme);
    await page.screenshot({ path: path.join(OUT_SHOTS, file), fullPage: true });
    entry.files.push(file);
  }

  async function shootLocator(entry, locator, suffix) {
    const shortName = suffix ? `${entry.name}-${suffix}` : entry.name;
    const file = fname(entry.num, shortName, width, theme);
    try {
      await locator.scrollIntoViewIfNeeded();
      await locator.screenshot({ path: path.join(OUT_SHOTS, file) });
      entry.files.push(file);
    } catch (e) {
      entry.notes.push(`Не удалось снять элемент (${suffix || 'элемент'}): ${e.message}`);
    }
  }

  async function shootClip(entry, clip, suffix) {
    const shortName = suffix ? `${entry.name}-${suffix}` : entry.name;
    const file = fname(entry.num, shortName, width, theme);
    try {
      await page.screenshot({ path: path.join(OUT_SHOTS, file), clip });
      entry.files.push(file);
    } catch (e) {
      entry.notes.push(`Не удалось снять область (${suffix || 'область'}): ${e.message}`);
    }
  }

  await login(page);

  // ---- 01: страница домашки целиком -----------------------------------
  {
    const e = makeEntry('01', 'assignment-overview', 'Домашка у преподавателя целиком');
    await goto(e, `/teacher/groups/${GROUP}/assignments/${ASSIGNMENT}/`);
    await shootFull(e);
    meta.push(e);
  }

  // ---- 02 / 03: карточка ДО / ПОСЛЕ «Утвердить» (без перезагрузки) -----
  {
    const e2 = makeEntry('02', 'approve-before', 'Карточка каталожной задачи ДО «Утвердить»');
    const e3 = makeEntry('03', 'approve-after', 'Она же ПОСЛЕ «Утвердить»');
    // Уже на странице 01 (goto не нужен — состояние должно быть общим).
    e2.url = e3.url = `/teacher/groups/${GROUP}/assignments/${ASSIGNMENT}/#item-${UNAPPROVED_ITEM}`;
    const card = page.locator(`#item-${UNAPPROVED_ITEM}`);
    const exists = await card.count();
    if (!exists) {
      const msg = `Позиция item-${UNAPPROVED_ITEM} не найдена на странице`;
      e2.notes.push(msg); e3.notes.push(msg);
    } else {
      let details = page.locator(`.ans-block[data-item="${UNAPPROVED_ITEM}"]`);
      let saveBtn = details.locator('.ans-save');
      let clearBtn = details.locator('.ans-clear');
      const isAnswersApiResponse = (resp) =>
        resp.url().includes('/teacher/api/item/answers/') && resp.request().method() === 'POST';

      // Ждём не перекраску DOM, а САМ сетевой ответ — источник истины.
      async function clickAndWait(locator, wantApproved) {
        const [resp] = await Promise.all([
          page.waitForResponse(isAnswersApiResponse, { timeout: 15000 }),
          locator.click(),
        ]);
        const body = await resp.json().catch(() => null);
        await page.waitForTimeout(150);
        return body && body.approved === wantApproved;
      }

      if (await details.count()) {
        await details.evaluate((el) => { el.open = true; });
        await page.waitForTimeout(150);
        // Прогон мог быть повторным — позиция уже утверждена с прошлого
        // раза (состояние живёт в базе, не в браузере, между запусками
        // скрипта). Сбрасываем, чтобы «ДО/ПОСЛЕ» снимался из одного и
        // того же стартового состояния при каждом запуске.
        const badgeOn = await page.locator(`[data-badge="${UNAPPROVED_ITEM}"].ap-on`).count();
        if (badgeOn && await clearBtn.count()) {
          const ok = await clickAndWait(clearBtn, false)
            .catch((err) => { e2.notes.push('Не удалось сбросить утверждение перед съёмкой: ' + err.message); return false; });
          if (!ok) e2.notes.push('Ответ сервера на сброс не подтвердил approved=false');
          // ⚠️ «Снять утверждение» чистит .ans-input ПРЯМО В БРАУЗЕРЕ
          // (assignment_detail.html: input.value = '' в обработчике клика) —
          // это настоящее поведение кнопки, не баг съёмки. Если после этого
          // сразу нажать «Утвердить» в той же вкладке, отправятся пустые
          // значения. Перезагружаем страницу, чтобы получить свежие подставленные
          // из каталога значения — как увидел бы их человек, открыв страницу заново.
          await page.reload({ waitUntil: 'networkidle' });
          await page.waitForTimeout(200);
          details = page.locator(`.ans-block[data-item="${UNAPPROVED_ITEM}"]`);
          saveBtn = details.locator('.ans-save');
          clearBtn = details.locator('.ans-clear');
          if (await details.count()) {
            await details.evaluate((el) => { el.open = true; });
            await page.waitForTimeout(150);
          }
        }
      }
      await card.scrollIntoViewIfNeeded();
      await shootLocator(e2, card);
      if (await saveBtn.count()) {
        const ok = await clickAndWait(saveBtn, true)
          .catch((err) => { e3.notes.push('Клик «Утвердить» не дождался ответа сервера: ' + err.message); return false; });
        if (!ok) {
          e3.notes.push('Сервер не подтвердил approved=true в ответе — снимок может показывать состояние ДО утверждения.');
        }
        await shootLocator(e3, card);
      } else {
        e3.notes.push('Кнопка «Утвердить» не найдена — возможно, позиция уже утверждена в этом прогоне');
      }
    }
    meta.push(e2, e3);
  }

  // ---- 04: карточка задачи, сданной БЕЗ ответа --------------------------
  {
    const e = makeEntry('04', 'submission-no-answer', 'Карточка задачи, сданной без ответа');
    await goto(e, `/teacher/groups/${GROUP}/submissions/${SUB_NO_ANSWER}/`);
    const block = page.locator('.answer-block').first();
    if (await block.count()) {
      await shootLocator(e, block);
      e.notes.push('Существующее демо-состояние (student2, позиция 1) — создавать не пришлось.');
    } else {
      e.notes.push('.answer-block не найден на странице');
      await shootFull(e);
    }
    meta.push(e);
  }

  // ---- 05: кнопки Утвердить/Снять + отправка/видимость комментариев ----
  {
    const e = makeEntry('05', 'approve-and-comments', 'Утвердить/Снять + отправка и видимость комментариев');
    await goto(e, `/teacher/groups/${GROUP}/assignments/${ASSIGNMENT}/#item-1`);
    // Позиция 1 — единственная (кроме 32, занятой сценарием 02/03) с
    // непустым .ans-block на текущих демо-данных (см. reconnaissance).
    const details1 = page.locator('.ans-block[data-item="1"]');
    if (await details1.count()) {
      await details1.evaluate((el) => { el.open = true; });
    }
    const actions = page.locator('.ans-block[data-item="1"] .ans-actions');
    const comments = page.locator('#item-1 .comments');
    if (await actions.count() && await comments.count()) {
      const box = await page.evaluate(() => {
        const a = document.querySelector('.ans-block[data-item="1"] .ans-actions');
        const c = document.querySelector('#item-1 .comments');
        const ra = a.getBoundingClientRect();
        const rc = c.getBoundingClientRect();
        return {
          x: Math.min(ra.left, rc.left),
          y: Math.min(ra.top, rc.top),
          right: Math.max(ra.right, rc.right),
          bottom: Math.max(ra.bottom, rc.bottom),
        };
      });
      await shootClip(e, {
        x: Math.max(0, box.x - 8), y: Math.max(0, box.y - 8),
        width: Math.min(width, box.right - box.x + 16),
        height: box.bottom - box.y + 16,
      });
    } else {
      e.notes.push('.ans-actions или .comments не найдены на позиции 26');
      await shootFull(e);
    }
    meta.push(e);
  }

  // ---- 06 / 07: версия для печати (ученикам / с ответами) --------------
  for (const [num, forParam, shortName, pdfName, title] of [
    ['06', 'student', 'print-student', 'listok-uchenikam.pdf', 'Листок «ученикам»'],
    ['07', 'teacher', 'print-teacher', 'listok-s-otvetami.pdf', 'Листок «с ответами»'],
  ]) {
    const e = makeEntry(num, shortName, title);
    await goto(e, `/teacher/groups/${GROUP}/assignments/${ASSIGNMENT}/print/?for=${forParam}`);
    await shootFull(e);
    if (doPdf) {
      try {
        await page.emulateMedia({ media: 'print' });
        await page.pdf({ path: path.join(OUT_PDF, pdfName), format: 'A4', printBackground: true });
        await page.emulateMedia({ media: 'screen' });
        e.notes.push(`PDF: reports/ux_audit/pdf/${pdfName}`);
      } catch (err) {
        e.notes.push('Не удалось собрать PDF: ' + err.message);
      }
    }
    meta.push(e);
  }

  // ---- 08: таблица решений по заданию -----------------------------------
  {
    const e = makeEntry('08', 'submissions-table', 'Таблица решений по заданию');
    await goto(e, `/teacher/groups/${GROUP}/assignments/${ASSIGNMENT}/submissions/`);
    await shootFull(e);
    meta.push(e);
  }

  // ---- 09: кнопка «Открыть разбор всей работы глазами ученика» ---------
  {
    const e = makeEntry('09', 'open-as-student-button', 'Кнопка «Открыть разбор всей работы глазами ученика»');
    e.url = `/teacher/groups/${GROUP}/submissions/${SUB_WITH_ANSWER}/`;
    // Страница уже посещается пунктом 10 — но нам важен именно этот
    // элемент, поэтому заходим отдельно, чтобы не зависеть от порядка.
    consoleBucket.length = 0;
    const t0 = Date.now();
    try {
      const resp = await page.goto(BASE + e.url, { waitUntil: 'networkidle', timeout: 30000 });
      e.status = resp ? resp.status() : null;
    } catch (err) { e.notes.push('НАВИГАЦИЯ ОШИБКА: ' + err.message); }
    await page.waitForTimeout(250);
    e.loadMs = Date.now() - t0;
    e.consoleErrors = consoleBucket.slice();
    const link = page.locator('a:has-text("Открыть разбор всей работы")').first();
    if (await link.count()) {
      const wrapper = link.locator('xpath=..');
      await shootLocator(e, wrapper);
      e.notes.push('Известная жалоба владельца: текст вылезает за границы кнопки (класс .btn-back с white-space:nowrap переиспользован для длинной надписи).');
    } else {
      e.notes.push('Кнопка «Открыть разбор всей работы...» не найдена — возможно, work_review_url не построился для этого submission.');
      await shootFull(e);
    }
    meta.push(e);
  }

  // ---- 10: форма проверки решения ----------------------------------------
  {
    const e = makeEntry('10', 'submission-review', 'Форма проверки решения');
    await goto(e, `/teacher/groups/${GROUP}/submissions/${SUB_WITH_ANSWER}/`);
    await shootFull(e);
    meta.push(e);
  }

  // ---- 11-13: вкладки группы ---------------------------------------------
  for (const [num, tab, title] of [
    ['11', 'students', 'Группа — вкладка «Ученики»'],
    ['12', 'assignments', 'Группа — вкладка «Задания»'],
    ['13', 'materials', 'Группа — вкладка «Материалы»'],
  ]) {
    const e = makeEntry(num, `group-${tab}`, title);
    await goto(e, `/teacher/groups/${GROUP}/?tab=${tab}`);
    await shootFull(e);
    meta.push(e);
  }

  // ---- 14: вкладка «Статистика» (отдельная страница, не таб) -----------
  {
    const e = makeEntry('14', 'group-stats', 'Группа — «Статистика» (без верхних вкладок — известная жалоба)');
    await goto(e, `/teacher/groups/${GROUP}/stats/`);
    await page.evaluate(() => window.scrollTo(0, 0));
    e.notes.push('Верхняя навигация со вкладками Ученики/Задания/Материалы/Статистика на ЭТОЙ странице отсутствует в разметке — «Статистика» ссылка ведёт на отдельный шаблон teacher/groups/stats.html, а не на detail.html с табами (teacher/templates/teacher/groups/detail.html:21 против stats.html).');
    await shootFull(e);
    meta.push(e);
  }

  // ---- 15: прогресс ученика — известная ошибка ---------------------------
  {
    const e = makeEntry('15', 'student-progress-error', 'Прогресс ученика — ошибка 500');
    await goto(e, `/teacher/student/${STUDENT_FOR_PROGRESS}/progress/`);
    await shootFull(e);
    if (e.status === 500) {
      const area = page.locator('#traceback_area');
      if (await area.count()) {
        const text = await area.inputValue().catch(() => null)
          || await area.textContent().catch(() => null);
        if (text) {
          fs.writeFileSync(ERROR_MD,
            '# Ошибка на «Прогресс ученика» — /teacher/student/'
            + `${STUDENT_FOR_PROGRESS}/progress/\n\n`
            + '## Диагноз простыми словами\n\n'
            + 'Страница пытается прочитать поле `problem` у сданной работы '
            + '(`Submission.problem.problem_type`), но у части сданных работ '
            + 'это поле теперь пустое — ответ на задачу хранится через новую '
            + 'позицию задания (`problem_item`), а старое поле `problem` '
            + 'заполняется только у части записей. Код на этом экране не '
            + 'обновили под новую модель, и он падает на первой же работе '
            + 'без старого поля.\n\n'
            + '## Где именно (файл и строка)\n\n'
            + '`teacher/views.py:424` — `student_progress()`:\n\n'
            + '```python\n'
            + "open_s = [s for s in subs if not (s.problem.problem_type or '').startswith('тест')]\n"
            + '```\n\n'
            + '## Полный traceback (из отладочной страницы Django)\n\n'
            + '```\n' + text.trim() + '\n```\n');
          e.notes.push(`Traceback сохранён целиком в ${ERROR_MD}`);
        } else {
          e.notes.push('Не удалось прочитать #traceback_area — traceback не сохранён автоматически, смотрите скриншот.');
        }
      } else {
        e.notes.push('#traceback_area не найден на странице ошибки (DEBUG=False?) — traceback не сохранён.');
      }
    } else {
      e.notes.push(`Ожидалась ошибка 500, получен статус ${e.status} — экран мог быть починен, обновите заметку в findings.`);
    }
    meta.push(e);
  }

  // ---- 16: создание домашки ----------------------------------------------
  {
    const e = makeEntry('16', 'assignment-create', 'Создание домашки');
    await goto(e, '/teacher/assignment/create/');
    await shootFull(e);
    meta.push(e);
  }

  // ---- 17: создание контрольной ------------------------------------------
  {
    const e = makeEntry('17', 'exam-create', 'Создание контрольной (адрес: teacher:exam_create, /teacher/groups/<pk>/exams/new/)');
    await goto(e, `/teacher/groups/${GROUP}/exams/new/`);
    await shootFull(e);
    meta.push(e);
  }

  // ---- 18: подбор домашки — пустая форма ---------------------------------
  {
    const e = makeEntry('18', 'generate-empty', 'Подбор домашки по описанию — пустая форма');
    await goto(e, '/teacher/assignment/generate/');
    await shootFull(e);
    meta.push(e);
  }

  // ---- 19: та же форма, заполненная запросом (до отправки) --------------
  let plannedOk = false;
  {
    const e = makeEntry('19', 'generate-filled', 'Форма подбора, заполненная запросом (до отправки)');
    e.url = '/teacher/assignment/generate/';
    const textarea = page.locator('textarea[name=text]');
    if (await textarea.count()) {
      await textarea.fill(GEN_QUERY);
      await page.waitForTimeout(150);
      await shootFull(e);
    } else {
      e.notes.push('Поле запроса не найдено — функция подбора выключена (нет ANTHROPIC_API_KEY?)');
      await shootFull(e);
    }
    meta.push(e);

    // ---- 20: шаг «Что нашлось» ------------------------------------------
    const e20 = makeEntry('20', 'generate-found', 'Шаг «Что нашлось»');
    if (await textarea.count()) {
      const submitBtn = page.locator('button[type=submit]:has-text("Разобрать запрос")');
      const t0 = Date.now();
      try {
        await Promise.all([
          page.waitForNavigation({ waitUntil: 'networkidle', timeout: 60000 }),
          submitBtn.click(),
        ]);
        e20.status = 200;
        plannedOk = true;
      } catch (err) {
        e20.notes.push('Отправка запроса модели не удалась: ' + err.message);
      }
      e20.loadMs = Date.now() - t0;
      e20.url = '/teacher/assignment/generate/ (POST action=parse)';
      await settle(page);
      await shootFull(e20);
      if (plannedOk) {
        const firstRow = page.locator('.plan-row').first();
        if (await firstRow.count()) {
          const box = await page.evaluate(() => {
            const diff = document.querySelector('input[name=row_difficulty]');
            const count = document.querySelector('input[name=row_count]');
            if (!diff || !count) return null;
            const rd = diff.getBoundingClientRect();
            const rc = count.getBoundingClientRect();
            return { x: Math.min(rd.left, rc.left), y: Math.min(rd.top, rc.top),
                     right: Math.max(rd.right, rc.right), bottom: Math.max(rd.bottom, rc.bottom) };
          });
          if (box) {
            await shootClip(e20, {
              x: Math.max(0, box.x - 16), y: Math.max(0, box.y - 16),
              width: Math.min(width, box.right - box.x + 32),
              height: box.bottom - box.y + 32,
            }, 'numbers');
          } else {
            e20.notes.push('Не нашёл row_difficulty/row_count для крупного снимка');
          }
        }
      }
    } else {
      e20.notes.push('Пропущено — функция подбора выключена на шаге 19');
    }
    meta.push(e20);

    // ---- 21: итоговый экран подбора ---------------------------------------
    const e21 = makeEntry('21', 'generate-result', 'Итоговый экран подбора');
    if (plannedOk) {
      const searchBtn = page.locator('button[type=submit]:has-text("Подобрать задачи")');
      if (await searchBtn.count()) {
        const t0 = Date.now();
        try {
          await Promise.all([
            page.waitForNavigation({ waitUntil: 'networkidle', timeout: 30000 }),
            searchBtn.click(),
          ]);
          e21.status = 200;
        } catch (err) {
          e21.notes.push('Отправка «Подобрать задачи» не удалась: ' + err.message);
        }
        e21.loadMs = Date.now() - t0;
        e21.url = '/teacher/assignment/generate/ (POST action=search)';
        await settle(page);
        await shootFull(e21);
      } else {
        e21.notes.push('Кнопка «Подобрать задачи» не найдена на шаге «Что нашлось»');
      }
    } else {
      e21.notes.push('Пропущено — шаг «Что нашлось» не был получен');
    }
    meta.push(e21);
  }

  // ---- 22: плашка «Требует внимания» -------------------------------------
  {
    const e = makeEntry('22', 'needs-attention', 'Плашка «Требуют внимания» (группа × статистика)');
    await goto(e, `/teacher/groups/${GROUP}/stats/`);
    const panel = page.locator('.panel').filter({ hasText: 'Требуют внимания' }).first();
    if (await panel.count()) {
      await shootLocator(e, panel);
      e.notes.push('Состояние получено на существующих демо-данных (не пришлось вызывать искусственно).');
    } else {
      e.notes.push('Панель «Требуют внимания» не появилась — в демо-данных сейчас никто не подходит под условия.');
      await shootFull(e);
    }
    meta.push(e);
  }

  await context.close();
  return meta;
}

(async () => {
  const browser = await chromium.launch();
  const RUNS = [
    { width: 1440, theme: 'light', doPdf: true },
    { width: 768, theme: 'light', doPdf: false },
    { width: 380, theme: 'light', doPdf: false },
    { width: 1440, theme: 'dark', doPdf: false },
  ];

  const allMeta = [];
  for (const run of RUNS) {
    console.log(`--- Прогон: ${run.width}px, ${run.theme} ---`);
    try {
      const meta = await runScreens(browser, run);
      for (const e of meta) {
        e.width = run.width; e.theme = run.theme;
        const flag = e.notes.length ? ' ⚠ ' + e.notes.join(' | ') : '';
        console.log(`  ${e.num} ${e.name} [${run.width}/${run.theme}] status=${e.status} files=${e.files.length}${flag}`);
      }
      allMeta.push(...meta);
    } catch (err) {
      console.error(`ЭКРАН-ПРОГОН ${run.width}/${run.theme} НЕДОСТУПЕН: ${err.message}`);
      allMeta.push({ num: '??', name: `run-failed-${run.width}-${run.theme}`,
                     width: run.width, theme: run.theme, notes: [String(err.stack || err)] });
    }
  }

  await browser.close();
  fs.writeFileSync(META_PATH, JSON.stringify(allMeta, null, 2));
  console.log('\nМетаданные записаны в', META_PATH);
})();
