"""Измерительная страница KaTeX — та же мера поломки, что у шлюза «не навреди».

⚠️ ЗАЧЕМ ВТОРАЯ РЕАЛИЗАЦИЯ И ЧЕМ ОНА ПРИВЯЗАНА К ПЕРВОЙ.
Мера поломки живёт в `scripts/katex_damage.js` и запускается через Playwright.
На машине без Node.js (а это ровно машина, куда проект переезжает) Playwright
недоступен, и признаки «в»/«г» нечем измерить вовсе. Поэтому здесь собирается
ТА ЖЕ страница на питоне: её можно открыть любым браузером.

Расхождение двух реализаций — известная болезнь проекта (два генератора
превью, два рисователя чертежей). Поэтому совпадение существенных констант
(служебный цвет, разделители формул, маска экранированного доллара)
проверяется тестом `problems/tests/test_katex_sandbox.py`: он читает
`katex_damage.js` и сверяет их с этим файлом. Меняете одно — тест краснеет.

ЧТО МЕРЯЕТСЯ (два разных режима, см. докстринг katex_damage.js):
    errors — формула не разобралась целиком, виден узел `.katex-error`;
    red    — формула разобралась, но внутри НЕИЗВЕСТНАЯ команда: узла ошибки
             нет, команда молча выброшена, соседние куски слипаются.
"""

import json
import os

# Служебный цвет ошибки. Любой элемент этого цвета — работа KaTeX, а не
# автора задачи: такой оттенок никто не напишет руками.
SENTINEL = '#010203'
SENTINEL_RGB = 'rgb(1, 2, 3)'

# Приватный символ, которым боевой конвейер маскирует экранированный «\$».
DOLLAR_SENTINEL = '\\uE000'

# Разделители — дословно как в catalog/templates/catalog/base.html:
# «$$» обязано проверяться РАНЬШЕ «$», иначе двойной разделитель разберётся
# как два пустых одинарных.
DELIMITERS = [
    ('$$', '$$', True),
    ('$', '$', False),
    ('\\\\[', '\\\\]', True),
    ('\\\\(', '\\\\)', False),
]

KATEX_DIR = os.path.join('problems', 'review_bundle_assets', 'vendor', 'katex')

# Считалка «сколько элементов покрашено служебным цветом». Два правила против
# двойного счёта: пропускаем скрытую копию MathML и берём только САМЫЕ
# ВНЕШНИЕ покрашенные элементы (KaTeX красит вложенную пару span'ов).
COUNT_FN = """function (root, rgb) {
  var hits = 0;
  var all = root.querySelectorAll('*');
  for (var i = 0; i < all.length; i++) {
    var el = all[i];
    if (el.closest && el.closest('.katex-mathml')) continue;
    if (getComputedStyle(el).color !== rgb) continue;
    var p = el.parentElement;
    if (p && p !== root && getComputedStyle(p).color === rgb) continue;
    hits++;
  }
  return hits;
}"""


def _asset(name):
    with open(os.path.join(KATEX_DIR, name), encoding='utf-8') as fh:
        return fh.read()


def _delims_js():
    rows = []
    for left, right, display in DELIMITERS:
        rows.append('{ left: "%s", right: "%s", display: %s }'
                    % (left, right, 'true' if display else 'false'))
    return '[' + ', '.join(rows) + ']'


def build_measure_page(queue):
    """HTML, который сам прогонит очередь и положит итог в window.__RESULT.

    queue — список словарей {pid, field, text}. Страница считает поломки и
    ищет числа, появившиеся ТОЛЬКО после рендера (слипание).
    """
    return """<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Замер рендера</title>
<style>%(css)s</style>
<script>%(js)s</script>
<script>%(auto)s</script>
</head><body>
<div id="box"></div>
<pre id="log">готовлюсь…</pre>
<script>
var QUEUE = %(queue)s;
var SENTINEL_RGB = %(rgb)s;
var countColored = %(count_fn)s;
var DOLLAR_SENTINEL = '%(dollar)s';

function maskEscapedDollars(root) {
  var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null), node;
  while ((node = walker.nextNode())) {
    if (node.nodeValue.indexOf('\\\\$') !== -1) {
      node.nodeValue = node.nodeValue.split('\\\\$').join(DOLLAR_SENTINEL);
    }
  }
}

function measure(text) {
  var box = document.getElementById('box');
  box.textContent = text;
  maskEscapedDollars(box);
  renderMathInElement(box, {
    delimiters: %(delims)s,
    throwOnError: false,
    errorColor: %(sentinel)s
  });
  var errors = box.querySelectorAll('.katex-error').length;
  var colored = countColored(box, SENTINEL_RGB);
  // Узлы .katex-error тоже покрашены служебным цветом — вычитаем, чтобы одна
  // поломка не считалась дважды.
  return { errors: errors, red: Math.max(0, colored - errors) };
}

function visibleText() {
  var box = document.getElementById('box').cloneNode(true);
  var mm = box.querySelectorAll('.katex-mathml');
  for (var i = 0; i < mm.length; i++) { mm[i].remove(); }
  return box.textContent || '';
}

function numbers(s) { return String(s).match(/\\d+/g) || []; }

// Числа, появившиеся ТОЛЬКО после рендера: «31» + «8» -> «318».
function glued(source, rendered) {
  var was = {}, i;
  var a = numbers(source);
  for (i = 0; i < a.length; i++) { was[a[i]] = 1; }
  var out = [], b = numbers(rendered);
  for (i = 0; i < b.length; i++) {
    if (!was[b[i]] && b[i].length >= 3 && out.indexOf(b[i]) === -1) out.push(b[i]);
  }
  return out;
}

var results = [], idx = 0, errFields = 0, redFields = 0;

function step() {
  var end = Math.min(idx + 50, QUEUE.length);
  for (; idx < end; idx++) {
    var item = QUEUE[idx];
    var m = measure(item.text || '');
    if (m.errors) errFields++;
    if (!m.errors && m.red) redFields++;
    if (m.errors || m.red) {
      var row = { pid: item.pid, field: item.field, errors: m.errors, red: m.red };
      if (!m.errors && m.red) row.glued = glued(item.text || '', visibleText());
      results.push(row);
    }
  }
  document.getElementById('log').textContent =
    'прогнано ' + idx + ' / ' + QUEUE.length;
  if (idx < QUEUE.length) { setTimeout(step, 0); return; }
  window.__RESULT = results;
  window.__DONE = true;
  document.getElementById('log').textContent =
    'ГОТОВО. полей ' + QUEUE.length + '; с ошибкой ' + errFields +
    '; с выброшенной командой ' + redFields;
}
setTimeout(step, 0);
</script></body></html>""" % {
        'css': _asset('katex.min.css'),
        'js': _asset('katex.min.js'),
        'auto': _asset(os.path.join('contrib', 'auto-render.min.js')),
        'queue': json.dumps(queue, ensure_ascii=False),
        'rgb': json.dumps(SENTINEL_RGB),
        'sentinel': json.dumps(SENTINEL),
        'count_fn': COUNT_FN,
        'delims': _delims_js(),
        'dollar': DOLLAR_SENTINEL,
    }
