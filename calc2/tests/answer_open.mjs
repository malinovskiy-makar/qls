/* «Ответ» для приборов (тихие панели, 14.10.2026; решение владельца Notion …81de…, ADR 0150).

   От 1240 px «Ответ» на первом заходе ЗАКРЫТ (полоска 44 px). Прибор, который читает или меряет открытый
   «Ответ», открывает его так, как он выглядит у человека, однажды открывшего «Ответ»: ключ памяти
   calc2.v1.answerHidden = '0' до каждой загрузки страницы.

   ⚠️ Прибор, который смотрит только видимое, при закрытой колонке ЗЕЛЕНЕЕТ ВХОЛОСТУЮ (пустой список
   проходит). Поэтому первая проверка такого прибора — answerShown(page): «#params-panel > .side-inner
   видна» (на ширине меньше 1240 колонки нет — там проверка честно истинна).

     import { keepAnswerOpen, answerShown } from './answer_open.mjs';   // из redesign/ — '../answer_open.mjs'
     const browser = keepAnswerOpen(await chromium.launch());
     ...
     ok('предусловие: «Ответ» открыт', await answerShown(page));
*/
const KEY = 'calc2.v1.answerHidden';

/* Скрипт до загрузки страницы. Свои скрипты приборов (localStorage.clear()) регистрируются
   позже и выполняются после этого: clear() перехвачен и ключ возвращает. */
export const ANSWER_OPEN_SCRIPT = () => {
  try {
    const k = 'calc2.v1.answerHidden';
    localStorage.setItem(k, '0');
    const clear = Storage.prototype.clear;
    Storage.prototype.clear = function () { clear.call(this); try { if (this === window.localStorage) this.setItem(k, '0'); } catch (e) {} };
  } catch (e) {}
};

/* Каждый новый контекст и страница этого браузера открывают «Ответ». */
export function keepAnswerOpen(browser) {
  const nc = browser.newContext.bind(browser);
  browser.newContext = async (...a) => { const ctx = await nc(...a); await ctx.addInitScript(ANSWER_OPEN_SCRIPT); return ctx; };
  const np = browser.newPage.bind(browser);
  browser.newPage = async (...a) => { const p = await np(...a); await p.context().addInitScript(ANSWER_OPEN_SCRIPT); await p.evaluate(ANSWER_OPEN_SCRIPT).catch(() => {}); return p; };
  return browser;
}

/* Колонка «Ответ» открыта (или её на этой ширине нет вовсе — до 1240 она выезжает). */
export function answerShown(page) {
  return page.evaluate(() => {
    if (window.innerWidth < 1240) return true;
    const e = document.querySelector('#params-panel > .side-inner');
    return !!(e && e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden');
  });
}

export { KEY as ANSWER_HIDDEN_KEY };
