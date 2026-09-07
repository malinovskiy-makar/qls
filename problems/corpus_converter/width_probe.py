# -*- coding: utf-8 -*-
"""Реальная ширина формул: коды `OVER` и `OVER-M` из аудита.

Эти два кода — единственные, которые нельзя решить разбором текста.
«Формула шире карточки» — свойство отрендеренной страницы, а не строки:
одна и та же длина в символах даёт разную ширину у `\\frac` и у
`\\text{...}`. Аудит мерил именно так и назвал пороги: 800 px —
переполнение на десктопе, 600 px — риск на узком экране.

Измеряется тем же вендорным KaTeX 0.16.9, что стоит на боевом показе, и
в том же браузере, что уже поднят для проверки формул. Отдельной
песочницы нет намеренно: другая версия или другой шрифт превратили бы
замер в фикцию.
"""

#: Пороги аудита. Ширина карточки на боевом показе — около 800 px, узкий
#: экран — 600 px.
OVER_PX = 800
OVER_MOBILE_PX = 600

#: Скрипт вставляет HTML в страницу, рендерит каждую формулу в
#: неразрывный контейнер и меряет её естественную ширину. Именно
#: естественную: если мерить внутри карточки, перенос строки скроет
#: переполнение, и замер покажет «всё влезло».
MEASURE_WIDTHS_JS = r"""
window.__widths = function (html) {
  var box = document.getElementById('probe');
  if (!box) {
    box = document.createElement('div');
    box.id = 'probe';
    box.style.position = 'absolute';
    box.style.visibility = 'hidden';
    box.style.left = '-99999px';
    box.style.top = '0';
    box.style.whiteSpace = 'nowrap';
    box.style.display = 'inline-block';
    document.body.appendChild(box);
  }
  var host = document.createElement('div');
  host.innerHTML = html;
  var PAIRS = [['$$','$$'], ['\\[','\\]'], ['\\(','\\)'], ['$','$']];
  function findClose(s, from, close) {
    for (var i = from; i <= s.length - close.length; i++) {
      if (s.charAt(i) === '\\') { i++; continue; }
      if (s.substr(i, close.length) === close) return i;
    }
    return -1;
  }
  var widths = [];
  var walker = document.createTreeWalker(host, NodeFilter.SHOW_TEXT, null);
  var node, texts = [];
  while ((node = walker.nextNode())) texts.push(node.nodeValue);
  for (var t = 0; t < texts.length; t++) {
    var s = texts[t], i = 0;
    while (i < s.length) {
      var matched = null;
      for (var k = 0; k < PAIRS.length; k++) {
        var open = PAIRS[k][0], close = PAIRS[k][1];
        if (s.substr(i, open.length) !== open) continue;
        var end = findClose(s, i + open.length, close);
        if (end === -1) continue;
        matched = { body: s.slice(i + open.length, end),
                    display: open === '$$' || open === '\\[',
                    next: end + close.length };
        break;
      }
      if (!matched) { i++; continue; }
      i = matched.next;
      if (!matched.body.trim()) continue;
      // Короткая формула не может занять 600 px ни при каком шрифте, а
      // вставка в DOM и замер — самая дорогая часть прохода по корпусу.
      // Порог с запасом: 30 символов — это примерно 300 px.
      if (matched.body.length < 30) continue;
      try {
        box.innerHTML = katex.renderToString(matched.body, {
          displayMode: matched.display, throwOnError: false, trust: false
        });
        var w = box.getBoundingClientRect().width;
        if (w > 0) widths.push(Math.round(w * 10) / 10);
      } catch (e) { /* разбор — забота __preflight, здесь только ширина */ }
    }
  }
  box.innerHTML = '';
  return widths;
};
"""


def codes_for_widths(widths, over_px=OVER_PX, mobile_px=OVER_MOBILE_PX):
    """`[(код, подробность)]` по измеренным ширинам одного блока."""
    if not widths:
        return []
    widest = max(widths)
    if widest > over_px:
        return [('OVER', 'формула шириной %.0f px при карточке ~%d px'
                 % (widest, over_px))]
    if widest > mobile_px:
        return [('OVER-M', 'формула шириной %.0f px — узкий экран не вмещает'
                 % widest)]
    return []
