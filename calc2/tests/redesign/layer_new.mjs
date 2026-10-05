/* Слой «как найти орган и как прочитать ответ» для НОВОГО экрана calc2
   (редизайн 10.2026: шапка модели, «Условие», холст, «Ответ»).

   Сценарий и сверка общие (snapshot.mjs, compare.mjs). Слой знает три вещи:
   как войти в модель, как довести орган, заменённый по закрытому списку
   (fates.mjs), и как прочитать «Ответ». Пока «Ответ» собран из прежних
   блоков #info-* (до фазы 6), читается он так же, как на старом экране. */
import { fateOf } from './fates.mjs';

export const name = 'new';

export async function enter(page, key) {
  await page.evaluate((k) => { pickScene(k); }, key);
}

/* Раскрывать нечего: секции всегда открыты, колонки не сворачиваются.
   «Развернуть график» выключен, поля формул собраны. */
export async function expand(page) {
  await page.evaluate(() => {
    if (document.body.classList.contains('cv-focus') && typeof setFocusMode === 'function') setFocusMode(false);
    if (typeof flushMathfieldsSoon === 'function') flushMathfieldsSoon();
  });
}

export async function answer(page) {
  return page.evaluate(() => {
    const a = window.__RD.answerNew ? window.__RD.answerNew() : window.__RD.answerOld();
    a.tips = window.__RD.tipsOld();
    return a;
  });
}

/* Кнопок «Построить» нет: набор применяется сам (пункт (а)). */
export async function afterFormula() { return null; }

export async function closeTransient(page) {
  await page.keyboard.press('Escape');
  await page.evaluate(() => {
    document.body.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
    document.body.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  });
}

/* Прежний ключ органа → ключ на новом экране (там, где у замены свой id). */
const RENAME = {
  '#btn-scene-reset': '#btn-model-reset',
  '#btn-wrench': '#btn-view',
  '#tools-toggle': '#btn-focus',
  '#params-toggle': '#btn-focus',
};
export function mapKey(key) { return RENAME[key] || key; }

/* Действие над органом, которого больше нет (закрытый список). Возвращает
   описание действия или null — тогда орган ищется обычным путём. */
export async function actOverride(page, c) {
  const f = fateOf(c.key);
  if (f.fate !== 'заменён' && f.fate !== 'убран') return null;
  if (f.letter === 'а') return 'живое применение: кнопки нет, запись уже в модели';
  if (f.letter === 'д') return 'секция всегда раскрыта: сворачивать нечего';
  if (f.letter === 'г') return 'экран выбора одним экраном: проверяется обходом 44 ключей';
  if (f.letter === 'л' || f.letter === 'м') {
    /* (м) — сегмент из одной кнопки «Квота» в модели «Квоты». В монополии та
       же кнопка — настоящий выбор инструмента, и там она остаётся: если орган
       на экране, действуем как обычно. */
    const shown = await page.evaluate((k) => !!(window.__RD.findControl(k)), c.key);
    return shown ? null : 'убрано по закрытому списку';
  }
  return null;   // (в), (е), (ж), (и), (к): у замены свой орган — щёлкаем его
}
