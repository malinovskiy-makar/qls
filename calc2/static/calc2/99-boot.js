// Инициализация: запуск калькулятора после загрузки страницы.
/* ---------------------------------------------------------------------
   ИНИЦИАЛИЗАЦИЯ
   --------------------------------------------------------------------- */
/* Числовое поле — просто поле ввода числа (П16).
   Крутилки спрятаны стилями, но Chrome всё равно листает значение колесом на
   сфокусированном поле и стрелками вверх-вниз. Слушателя колеса в коде не было
   совсем, поэтому и «пролистывание» никуда не девалось. Ловим оба пути одним
   делегированным обработчиком на всю рабочую область: он переживает любую
   перерисовку списков, в отличие от навески на каждое поле по отдельности.
   Колесо на поле при этом должно прокручивать ПАНЕЛЬ, а не менять число, —
   поэтому просто снимаем фокус и пропускаем событие дальше, без preventDefault. */
function lockNumberFields() {
  const app = document.querySelector('.app') || document;
  const isNum = (el) => el && el.tagName === 'INPUT' && el.type === 'number';
  app.addEventListener('wheel', (e) => {
    const el = e.target;
    if (isNum(el) && document.activeElement === el) el.blur();
  }, { passive: true, capture: true });
  app.addEventListener('keydown', (e) => {
    if ((e.key === 'ArrowUp' || e.key === 'ArrowDown') && isNum(e.target)) e.preventDefault();
  }, true);
}

function init() {
  // Проверяем, что библиотеки загрузились (в консоли браузера видно версии).
  if (typeof d3 === 'undefined' || typeof math === 'undefined') {
    console.error('Не загрузились библиотеки D3 или Math.js (проверьте интернет).');
    return;
  }
  console.log('calc2: D3', d3.version, '| Math.js загружен');
  lockNumberFields();   // числовое поле — только набор с клавиатуры (П16)
  refreshColors();   // наполнить карту цветов до первого рисования/добавления кривой
  relocateForScene();   // перенести блоки результатов в панель аналитики
  cardifySections();    // панель ввода — список закрытых карточек
  foldPickerGroups();   // окно сценариев — десять закрытых блоков
  wireControls();
  wireScene();          // полоса иконок, панели, меню плоскости, тема
  // Н50, Н73: пары сегментных кнопок показываем настоящим тумблером. Идёт после
  // wireControls: к самим кнопкам к этому моменту уже привязаны обработчики.
  segToToggle('ac-mode', 'ac-curve', 'ac-poly', 'Под кривой', 'Между точками');
  segToToggle('mm-mode', 'mm-min', 'mm-max', 'Наименьшую', 'Наибольшую');
  initSceneColorPickers();
  renderCurveList();
  redrawAll();
  syncViewFields();
  openPicker();   // при входе показываем окно выбора сценария (рабочее место — под ним)
  // Размер холста стерегёт ResizeObserver (см. wireScene): он ловит и окно,
  // и сворачивание панелей. Отдельный слушатель resize больше не нужен.
}

document.addEventListener('DOMContentLoaded', init);
