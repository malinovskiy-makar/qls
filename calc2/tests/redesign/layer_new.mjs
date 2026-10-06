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
  // «?» у метки: поле «Метка» получило свой id, ключ органа считается от него.
  '#export-modal>button.hint-btn': '#exp-label-field>button.hint-btn',
};
export function mapKey(key) {
  if (RENAME[key]) return RENAME[key];
  /* (ж) галочка видимости кривой → глаз на её карточке. Номер в старом ключе
     считал ВСЕ поля списка: на строку кривой их два (глаз и поле записи), и
     во всех 44 базовых снимках глаза идут через два — 0, 2, 4… Глаз k-й
     кривой — номер 2k, на новом экране это k-я кнопка .fc-eye. */
  const eye = /^#curve-list>input(?:\[(\d+)\])?$/.exec(key);
  if (eye) { const k = Math.ceil((+eye[1] || 0) / 2); return '#curve-list>button.fc-eye' + (k ? '[' + k + ']' : ''); }
  return key;
}

/* Орган, который на новом экране живёт в закрытом меню «…» карточки функции
   (крестик «Удалить функцию» / «Убрать с графика»): открыть меню его строки.
   Возвращает true, если меню открыто и орган можно искать снова. */
export async function reveal(page, key) {
  return page.evaluate((k) => {
    const el = window.__RD.findControlAny ? window.__RD.findControlAny(k) : null;
    /* Окно «Скачать»: поле «Метка» и его «?» видны у форматов с файлом TeX
       (у PNG метки нет, README макета, раздел 10) — выбрать TeX. */
    const lf = el && el.closest('#exp-label-field');
    if (lf && lf.hidden) {
      const tex = document.querySelector('#exp-fmt [data-fmt="tex"]');
      if (tex) tex.click();
      return !lf.hidden;
    }
    const menu = el && el.closest('.fc-menu');
    if (!menu) return false;
    const row = menu.closest('.fc-card');
    const gear = row && row.querySelector('.crow-gear');
    if (!gear) return false;
    if (!menu.classList.contains('open')) gear.click();
    return menu.classList.contains('open');
  }, key);
}

/* Действие над органом, которого больше нет (закрытый список). Возвращает
   описание действия или null — тогда орган ищется обычным путём. */
export async function actOverride(page, c) {
  const f = fateOf(c.key);
  if (f.fate !== 'заменён' && f.fate !== 'убран') return null;
  if (f.letter === 'а') return 'живое применение: кнопки нет, запись уже в модели';
  if (f.letter === 'д') return 'секция всегда раскрыта: сворачивать нечего';
  if (f.letter === 'г') return 'экран выбора одним экраном: проверяется обходом 44 ключей';
  if (f.letter === 'к') return 'выгрузка: формат сегментом и «Скачать» (#exp-go); проверяет export_audit.mjs';
  if (f.letter === 'е') {
    // Общая галочка излишков → две галочки CS и PS: то же действие — обе разом.
    const done = await page.evaluate(() => ['chk-cs', 'chk-ps'].filter(id => {
      const e = document.getElementById(id);
      if (!e || !window.__RD.visible(e)) return false;
      e.click(); return true;
    }));
    return done.length ? 'галочки ' + done.join(' и ') : 'галочек CS и PS в этой модели нет';
  }
  if (f.letter === 'л' || f.letter === 'м') {
    /* (м) — сегмент из одной кнопки «Квота» в модели «Квоты». В монополии та
       же кнопка — настоящий выбор инструмента, и там она остаётся: если орган
       на экране, действуем как обычно. */
    const shown = await page.evaluate((k) => !!(window.__RD.findControl(k)), c.key);
    return shown ? null : 'убрано по закрытому списку';
  }
  return null;   // (в), (е), (ж), (и), (к): у замены свой орган — щёлкаем его
}
