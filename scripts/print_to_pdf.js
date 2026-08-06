/*
 * Печать страницы задания в PDF настоящим браузером.
 *
 * Запускать из корня проекта: node scripts/print_to_pdf.js <in.html> <out.pdf>
 *
 * ⚠️ ЭТО ЗАГОТОВКА, А НЕ ВКЛЮЧЁННАЯ ФУНКЦИЯ. Кнопка «Скачать PDF» стоит за
 * выключенным по умолчанию флагом `ASSIGNMENT_PDF_ENABLED`. Причина —
 * память: на бесплатном Render всему приложению отведено 512 МБ, а
 * headless Chromium на ОДИН документ берёт 200–400 МБ. Два учителя,
 * нажавшие кнопку одновременно, кладут сайт целиком. Включать после
 * переезда на тариф, где память есть.
 *
 * Печатаем ту же страницу, что открывается по «Версия для печати»:
 * второй вёрстки для PDF не заводим — она разошлась бы с экранной, и
 * пришлось бы чинить оба листка на каждую правку.
 */
const { chromium } = require('playwright');
const path = require('path');

async function main() {
  const [input, output] = process.argv.slice(2);
  if (!input || !output) {
    console.error('нужно: node scripts/print_to_pdf.js <in.html> <out.pdf>');
    process.exit(2);
  }

  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    // Формулы рисует KaTeX с CDN — ждём, пока сеть успокоится, иначе в
    // PDF уедет сырой текст «$TC = 2Q$» вместо формулы.
    await page.goto('file://' + path.resolve(input),
                    { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(300);
    await page.pdf({
      path: output,
      format: 'A4',
      printBackground: false,
      margin: { top: '16mm', bottom: '16mm', left: '14mm', right: '14mm' },
    });
  } finally {
    await browser.close();
  }
}

main().catch(function (error) {
  console.error(String(error && error.message ? error.message : error));
  process.exit(1);
});
