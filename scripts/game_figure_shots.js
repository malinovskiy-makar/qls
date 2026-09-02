/*
 * Снимки режима «График» при GAME_FIGURE_ENABLED=1: стартовый экран и один
 * вопрос. Нужны приёмке — решение о включении режима на проде за владельцем.
 *
 * Сервер поднимается конфигурацией `dev-figure` (порт 8011,
 * --settings=config.settings_figure).
 *
 * Запуск ИЗ КОРНЯ ПРОЕКТА:  node scripts/game_figure_shots.js 8011
 *
 * ⚠️ СВЕРЯЕМ КОД ОТВЕТА И СОДЕРЖИМОЕ. Съёмка, снявшая страницу 403 или
 * пустой экран и отчитавшаяся об успехе, уже случалась в этом проекте.
 */
const fs = require('fs');
const { chromium } = require('playwright');

const PORT = process.argv[2] || '8011';
const BASE = 'http://127.0.0.1:' + PORT;
const OUT = 'reports/game/shots';

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  const resp = await page.goto(BASE + '/game/', { waitUntil: 'networkidle' });
  if (!resp || resp.status() !== 200) {
    console.error('стартовый экран отдал ' + (resp && resp.status()));
    await browser.close();
    process.exit(1);
  }

  // Карточка режима «График» обязана быть на экране: без неё флаг не сработал.
  const card = page.locator('.mode-card', { hasText: 'График' }).first();
  if (!(await card.count())) {
    console.error('карточки режима «График» на старте нет — флаг выключен?');
    await browser.close();
    process.exit(1);
  }
  await page.screenshot({ path: OUT + '/figure_start.png', fullPage: false });
  console.log('✓ figure_start.png');

  await card.click();
  await page.waitForTimeout(2500);

  // На экране вопроса обязан быть чертёж (svg) и подпись про первый шаг.
  const text = await page.locator('body').innerText();
  if (text.indexOf('неверный шаг') === -1) {
    console.error('вопрос аудита не открылся: на экране нет «неверный шаг»');
    await browser.close();
    process.exit(1);
  }
  const svgs = await page.locator('#screen-play svg').count();
  if (!svgs) {
    console.error('чертежа на экране вопроса нет');
    await browser.close();
    process.exit(1);
  }
  await page.screenshot({ path: OUT + '/figure_question.png' });
  console.log('✓ figure_question.png (чертежей на экране: ' + svgs + ')');

  await browser.close();
}

main().catch(function (e) { console.error(e); process.exit(1); });
