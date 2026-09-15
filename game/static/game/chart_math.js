/* Разметка графика «Динамика раунда» (экран итогов Wecon Rush): чистые
   функции без DOM — чтобы инвариант проверялся арифметикой в node, а не на
   глаз по картинке (game/tests/test_chart_math.py).

   ⚠️ НАД ЛИНИЕЙ ОЧКОВ РЕЗЕРВИРУЕТСЯ ПОЛОСА ПОД ПОДПИСЬ. Последнее значение
   почти всегда максимум. Раньше его точка стояла на отступе P = 8, а подпись
   над ней — на 5 px выше, то есть за верхним краем viewBox: число обрезалось.
   Теперь шкала очков начинается на LABEL_PAD = 22 от верха, и подпись (на
   6 px выше точки) стоит не выше 16.
   Инвариант: подпись ≥ 12, все точки очков в [P, H − P].                  */
(function (root) {
  'use strict';

  var LABEL_PAD = 22;

  /* y точки очков: ноль — на нижней линии H − P, максимум — на LABEL_PAD. */
  function scoreY(value, maxScore, H, P) {
    return H - P - (value / maxScore) * (H - P - LABEL_PAD);
  }

  /* y подписи последнего значения — над его точкой. */
  function labelY(pointY) {
    return pointY - 6;
  }

  root.rushChartMath = { LABEL_PAD: LABEL_PAD, scoreY: scoreY, labelY: labelY };
})(typeof window !== 'undefined' ? window : globalThis);
