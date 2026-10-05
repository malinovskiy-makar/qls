/* Слой «как найти орган и как прочитать ответ» для СТАРОГО экрана calc2
   (коммит 6b79758: левая панель «Ввод функций», правая «Аналитика»).

   Сценарий и сравнение у старого и нового экрана общие (snapshot.mjs);
   слой знает только раскладку. На новом экране его заменит layer_new.mjs. */

export const name = 'old';

/* Двенадцать кнопок «Построить»: поле под ними применяется только щелчком
   (CODE_NOTES, раздел 6). В базовом снимке такое поле сравнивается ПОСЛЕ
   применения: набрали и нажали. */
export const APPLY_IDS = ['btn-d3-apply', 'btn-kink-apply', 'btn-costs-apply', 'btn-cparts-apply',
  'btn-pl-apply', 'btn-prod-apply', 'btn-ppf-apply', 'btn-ppfsum-apply', 'btn-ppft-apply',
  'btn-tb-apply', 'ineq-incomes-apply', 'ineq-formula-apply'];

/* Войти в модель так, как это делает щелчок по карточке окна выбора. */
export async function enter(page, key) {
  await page.evaluate((k) => { pickScene(k); }, key);
}

/* Раскрыть всё, что раскрывается без действия человека над моделью: обе
   панели и все карточки (приём canon_checks.mjs:53-73). */
export async function expand(page) {
  await page.evaluate(() => {
    if (typeof setToolsOpen === 'function') setToolsOpen(true);
    if (typeof setParamsOpen === 'function') setParamsOpen(true);
    document.querySelectorAll('.fold-btn[aria-controls]').forEach(btn => {
      const body = document.getElementById(btn.getAttribute('aria-controls'));
      if (!body) return;
      body.classList.add('open');
      btn.setAttribute('aria-expanded', 'true');
      const card = btn.closest('.section, .side-part');
      if (card) card.classList.add('open-card');
    });
    if (typeof flushMathfieldsSoon === 'function') flushMathfieldsSoon();
  });
}

/* Ответ: табло, заголовок группы, «Объяснение модели», подсказки. */
export async function answer(page) {
  return page.evaluate(() => {
    const a = window.__RD.answerOld();
    a.tips = window.__RD.tipsOld();
    return a;
  });
}

/* После набора в поле под кнопкой «Построить» — нажать её. Кнопку ищем у
   ближайшего предка поля, где она видна. Возвращает id нажатой кнопки. */
export async function afterFormula(page, ctrlKey) {
  return page.evaluate(([key, ids]) => {
    const el = window.__RD.findControl(key) || document.activeElement;
    if (!el) return null;
    for (let n = el.parentElement; n && n !== document.body; n = n.parentElement) {
      const b = ids.map(id => document.getElementById(id)).find(x => x && n.contains(x) && window.__RD.visible(x));
      if (b) { b.click(); return b.id; }
    }
    return null;
  }, [ctrlKey, APPLY_IDS]);
}

/* Закрыть всё временное: окна, меню, клавиатуру, подсказку. */
export async function closeTransient(page) {
  await page.keyboard.press('Escape');
  // «Щелчок мимо» без щелчка по экрану: любой реальный щелчок мог бы попасть
  // в орган. Меню calc2 слушают pointerdown на документе в фазе погружения.
  await page.evaluate(() => {
    document.body.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
    document.body.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  });
}

/* Слой нового экрана повторяет действие над тем же органом. На старом
   экране ключ органа и есть способ его найти. */
export function mapKey(key) { return key; }
