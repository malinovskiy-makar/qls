/**
 * Единая мера «сломанного рендера KaTeX». Общая для шлюза «не навреди»,
 * браузерных проверок и осмотра пакетов ревью. Ничего не пишет в базу.
 *
 * ЗАЧЕМ ОТДЕЛЬНЫЙ МОДУЛЬ. До 2026-08-08 все проверки считали узлы
 * `.katex-error` — и были слепы к целому классу видимых поломок. KaTeX 0.16.9
 * при `throwOnError: false` ведёт себя ДВУМЯ разными способами:
 *
 *   1. Формула не разобралась целиком (двойной индекс, неизвестное окружение,
 *      \begin{tikzpicture}) → один узел `.katex-error` с исходным текстом.
 *   2. Формула разобралась, но внутри встретилась НЕИЗВЕСТНАЯ КОМАНДА
 *      (`\tesxt` — опечатка, `\myarray` — самодельный макрос,
 *      `\includegraphics`) → `.katex-error` НЕ создаётся вообще, команда
 *      печатается цветом `errorColor`, а соседние куски формулы молча
 *      слипаются («31» + «8p» → «318p», ловушка #27420 из CLAUDE.md).
 *
 * Решение Notion 3b6b11c92bc181839c18ddaceb1e19f3: считать и второй режим.
 *
 * ⚠️ КАК ОТЛИЧИТЬ ОШИБКУ ОТ АВТОРСКОГО КРАСНОГО. Цвет ошибки по умолчанию —
 * `#cc0000`, и ровно его может написать автор задачи: `$\color{#cc0000} x+1$`
 * даёт rgb(204,0,0) без всякой ошибки. Поэтому меряем НЕ «красноту», а
 * СЛУЖЕБНЫЙ ЦВЕТ: в измерительной песочнице `errorColor` подменяется на
 * заведомо неиспользуемый #010203, и всё, что им покрашено, — гарантированно
 * работа KaTeX, а не автора. Проверено: `\textcolor{red}` даёт rgb(255,0,0),
 * `\color{#cc0000}` остаётся rgb(204,0,0), и ни один из них под сентинел
 * не попадает.
 *
 * Сентинел живёт ТОЛЬКО в измерителе. На боевых страницах ошибка обязана
 * оставаться красной — её видит ученик.
 *
 * ⚠️ ТРЕТИЙ ТИХИЙ РЕЖИМ, который здесь НЕ ловится. `$\frac{1}{2$` (непарный
 * доллар) — auto-render просто не находит пару разделителей, формула не
 * рендерится ВООБЩЕ: ни `.katex-error`, ни цвета, на экране сырой `$…$`.
 * Это ловит текстовый детектор `unpaired_dollar` (problems/diagnostics.py),
 * а не рендер: рендеру тут нечего показать.
 */
'use strict';

const fs = require('fs');
const path = require('path');

// Служебный цвет ошибки для песочницы. Любой элемент этого цвета — ошибка
// KaTeX, и никак иначе: автор задачи такой оттенок не напишет.
const SENTINEL = '#010203';
const SENTINEL_RGB = 'rgb(1, 2, 3)';

// Цвет ошибки KaTeX по умолчанию — им же красится боевая страница.
const DEFAULT_ERROR_RGB = 'rgb(204, 0, 0)';

const KATEX_DIR = path.join(process.cwd(), 'problems/review_bundle_assets/vendor/katex');

/**
 * Считалка в контексте страницы. Возвращает исходник функции, чтобы её можно
 * было и вшить в песочницу, и вызвать через page.evaluate на живой странице.
 *
 * Два правила против двойного счёта, оба выведены из реальной разметки KaTeX:
 *
 *   1. Пропускаем `.katex-mathml`. Каждую формулу KaTeX выводит ДВАЖДЫ:
 *      видимой вёрсткой в `.katex-html` и скрытой копией MathML в
 *      `.katex-mathml` (она для скринридеров). Обе несут `mathcolor`
 *      служебного цвета, и без этого правила каждая поломка считалась бы
 *      дважды. Та же ловушка уже подводила при подсчёте «сырого LaTeX на
 *      экране»: в MathML лежит `<annotation>` с ИСХОДНЫМ текстом формулы.
 *   2. Считаем САМЫЕ ВНЕШНИЕ элементы служебного цвета: внутри `.katex-html`
 *      KaTeX красит вложенную пару span'ов (`.mord text` → `.mord`).
 */
const COUNT_FN = `function (root, rgb) {
  var hits = 0;
  var all = root.querySelectorAll('*');
  for (var i = 0; i < all.length; i++) {
    var el = all[i];
    if (el.closest && el.closest('.katex-mathml')) continue;   // скрытая копия
    if (getComputedStyle(el).color !== rgb) continue;
    var p = el.parentElement;
    if (p && p !== root && getComputedStyle(p).color === rgb) continue;  // вложенный
    hits++;
  }
  return hits;
}`;

/** HTML песочницы: вендорный KaTeX + боевой конвейер + window.measure(). */
function buildSandbox() {
  const css = fs.readFileSync(path.join(KATEX_DIR, 'katex.min.css'), 'utf8');
  const js = fs.readFileSync(path.join(KATEX_DIR, 'katex.min.js'), 'utf8');
  const auto = fs.readFileSync(path.join(KATEX_DIR, 'contrib/auto-render.min.js'), 'utf8');
  return `<!DOCTYPE html><html><head><meta charset="utf-8">
<style>${css}</style>
<script>${js}</script>
<script>${auto}</script>
</head><body><div id="box"></div>
<script>
var SENTINEL_RGB = ${JSON.stringify(SENTINEL_RGB)};
var countColored = ${COUNT_FN};
// Конвейер повторяет боевой из catalog/templates/catalog/base.html дословно:
// маскировка \\$ приватным символом, те же разделители, $$ раньше $.
var DOLLAR_SENTINEL = '\\uE000';
function maskEscapedDollars(root) {
  var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null), node;
  while ((node = walker.nextNode())) {
    if (node.nodeValue.indexOf('\\\\$') !== -1) {
      node.nodeValue = node.nodeValue.split('\\\\$').join(DOLLAR_SENTINEL);
    }
  }
}
window.measure = function (text) {
  var box = document.getElementById('box');
  box.textContent = text;
  maskEscapedDollars(box);
  renderMathInElement(box, {
    delimiters: [
      { left: '$$',  right: '$$',  display: true  },
      { left: '$',   right: '$',   display: false },
      { left: '\\\\[', right: '\\\\]', display: true  },
      { left: '\\\\(', right: '\\\\)', display: false }
    ],
    throwOnError: false,
    errorColor: ${JSON.stringify(SENTINEL)}
  });
  var errors = box.querySelectorAll('.katex-error').length;
  // .katex-error тоже покрашен служебным цветом — вычитаем, чтобы одна
  // поломка не считалась дважды.
  var colored = countColored(box, SENTINEL_RGB);
  return { errors: errors, red: Math.max(0, colored - errors), total: colored };
};
</script></body></html>`;
}

/** Счёт «красноты» на УЖЕ отрисованной боевой странице (сентинела там нет).
 *
 * ⚠️ Приблизительно, по двум причинам:
 *   1. На боевой странице цвет ошибки — тот же #cc0000, который может
 *      написать и автор задачи через \color{#cc0000}. Поэтому результат —
 *      КАНДИДАТЫ; подтверждать их надо прогоном текста через песочницу
 *      (buildSandbox + window.measure), где сентинел снимает двусмысленность.
 *   2. `redCandidates` включает и сами узлы `.katex-error` — они тоже
 *      покрашены цветом ошибки, а вычесть их, как в песочнице, здесь нельзя:
 *      неизвестно, где ошибка целой формулы, а где отдельной команды.
 *      Поэтому `errors` и `redCandidates` тут ПЕРЕСЕКАЮТСЯ, и складывать их
 *      нельзя; для разделения нужен прогон через песочницу.
 */
function livePageCounterSource() {
  return `(function () {
    var countColored = ${COUNT_FN};
    return {
      errors: document.querySelectorAll('.katex-error').length,
      redCandidates: countColored(document.body, ${JSON.stringify(DEFAULT_ERROR_RGB)})
    };
  })()`;
}

module.exports = {
  SENTINEL, SENTINEL_RGB, DEFAULT_ERROR_RGB,
  buildSandbox, livePageCounterSource, COUNT_FN,
};
