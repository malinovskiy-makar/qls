# -*- coding: utf-8 -*-
"""Реальный KaTeX-preflight: НАСТОЯЩИЙ рендер, а не текстовые эвристики.

Зачем модуль. Прежний шлюз `may_render_as_markdown()` решал «можно ли
показывать задачу через markdown» по текстовым признакам конвертера
(`complex_table`, `warnings`). Независимый аудит владельца
(`weconomics_converter_render_audit.md`, 2026-08-27) прогнал по тем же
846 карточкам НАСТОЯЩИЙ KaTeX 0.16.9 и нашёл, что **368 из 846 (43,5%)**
карточек имеют реальный дефект отображения, а старый шлюз пропускал их
как чистые (`data-has-warnings=false` у всех). Причина ровно та, о
которой предупреждает `problems/management/commands/CLAUDE.md`:
«Считать поле сломанным по текстовым признакам нельзя — сломанная
формула это то, что решил KaTeX».

Ключевой дефект архитектуры, который ловит только настоящий рендер
(раздел «Ключевой дефект архитектуры» аудита): markdown СНАЧАЛА ставит
`<br>`/`<p>`, и лишь ПОТОМ auto-render ищет разделители формул отдельно
в каждом текстовом узле. Если `\\begin{cases}` и `\\end{cases}` оказались
по разные стороны `<br>`, формулу уже не собрать — на экране сырой TeX.
Ни один текстовый предфильтр этого не видит: в исходной строке
окружение целое.

Поэтому здесь воспроизводится ВЕСЬ боевой конвейер по шагам:
1. `problems.rendering.render_markdown()` — тот же код, что на проде;
2. полученный HTML грузится в браузер;
3. обход текстовых узлов и поиск разделителей — дословная копия
   `templates/_katex_dollars.html` + `catalog/base.html` (маскировка
   `\\$`, те же четыре пары, `$$` раньше `$`);
4. каждый найденный фрагмент — через `katex.renderToString` с
   `throwOnError: true`, `strict` (обработчик), `trust: false`.

Отличие от боевой страницы ровно одно и оно намеренное: на проде стоит
`throwOnError: false`, и это НЕ чинит формулу, а лишь подменяет
исключение узлом `.katex-error`, внутри которого ученик видит сырой TeX
(раздел 2 аудита). Решение о миграции обязано приниматься по строгому
preflight, а показ ученику — оставаться терпимым.

KaTeX берётся вендорный (`problems/review_bundle_assets/vendor/katex`,
версия 0.16.9 — сверено `window.katex.version`), не с CDN: та же версия,
что на проде, и проверка не зависит от сети.

⚠️ Требует `playwright` (есть в venv313) и установленный chromium.
Node-скрипты рядом (`scripts/katex_render_check.js`) для этого не
годятся: `node_modules/` в репозитории пуст, `require('playwright')`
там не разрешается.

⚠️ `DJANGO_ALLOW_ASYNC_UNSAFE`. Синхронный API playwright поднимает
event loop, и Django после этого запрещает обращения к ORM
(`SynchronousOnlyOperation`). Вызывающая сторона обязана выставить
`DJANGO_ALLOW_ASYNC_UNSAFE=1` — здесь это безопасно и ровно для того
и предназначено: доступ к базе ТОЛЬКО на чтение, один поток, никаких
async-драйверов. Ставится не здесь, а в вызывающей команде, явно и
с комментарием — чтобы модуль не трогал глобальное состояние молча.
"""
from __future__ import annotations

import json
import os
import re

from django.conf import settings

from problems.corpus_converter.macros import find_unresolved_macros

KATEX_DIR = os.path.join(
    settings.BASE_DIR, 'problems', 'review_bundle_assets', 'vendor', 'katex',
)

#: Команды, присутствие которых в ВИДИМОМ тексте (после рендера) означает
#: сырой LaTeX на экране — Шаг 5 аудита, «нет текста, совпадающего с
#: \begin{, \end{, \addplot, \draw, \node, $$, \[, \]».
RAW_TEX_MARKERS = (
    '\\begin{', '\\end{', '\\addplot', '\\draw', '\\node', '\\filldraw',
    '\\addlegendentry', '\\multicolumn', '\\multirow', '\\hline',
    '\\toprule', '\\midrule', '\\bottomrule', '\\includegraphics',
    '\\section', '\\caption', '\\label', '\\item', '\\diagbox',
    '$$', '\\[', '\\]', '\\(', '\\)',
)

#: Любая последовательность `\команда` в видимом тексте. Экранированные
#: `\$`, `\%`, `\&`, `\_`, `\#` сюда не попадают: у них нет букв после
#: слеша, а боевой `fixCurrencyDollars` превращает их в обычные символы.
_LEFTOVER_TEX_CMD_RE = re.compile(r'\\[A-Za-z]{2,}')

#: Строго документированный allowlist для `unicodeTextInMathMode`.
#: ПУСТ намеренно. Аудит (раздел 3) показал: русский текст в math mode —
#: это 397 формул в 183 карточках, где `если T≤300` визуально слипается
#: в курсивную кашу. Правильный ответ — `\text{…}` (Фаза 1 канонизации),
#: а не разрешение. Заводить сюда символы можно только с обоснованием,
#: почему конкретно ЭТОТ символ читается верно без `\text{}`.
UNICODE_TEXT_ALLOWLIST: frozenset[str] = frozenset()


def _read_asset(*parts):
    with open(os.path.join(KATEX_DIR, *parts), encoding='utf-8') as f:
        return f.read()


#: Функция-измеритель в контексте страницы. Дословно повторяет боевой
#: конвейер разделителей: сначала маскировка `\$` (валюта) приватным
#: символом, затем поиск пар в порядке `$$`, `\[`, `\(`, `$` — как в
#: `mathSpanEnd` боевого шаблона. Порядок обязателен: `$` последним,
#: иначе `$$` открывалось бы как две пустые inline-формулы.
_MEASURE_JS = r"""
window.__preflight = function (html) {
  var box = document.getElementById('box');
  box.innerHTML = html;

  var DOLLAR_SENTINEL = '';
  function findClose(s, from, close) {
    var i = from;
    while (i < s.length) {
      if (s.charAt(i) === '\\' && s.charAt(i + 1) === '$') { i += 2; continue; }
      if (s.substr(i, close.length) === close) return i;
      i++;
    }
    return -1;
  }
  var PAIRS = [['$$', '$$'], ['\\[', '\\]'], ['\\(', '\\)'], ['$', '$']];
  function mathSpanEnd(s, i) {
    for (var k = 0; k < PAIRS.length; k++) {
      var open = PAIRS[k][0], close = PAIRS[k][1];
      if (s.substr(i, open.length) !== open) continue;
      var end = findClose(s, i + open.length, close);
      if (end === -1) continue;
      return { end: end + close.length, open: open, close: close,
               body: s.slice(i + open.length, end), display: open === '$$' || open === '\\[' };
    }
    return null;
  }
  // Маскировка \$ — валюта не должна открывать формулу (боевой
  // maskOutsideMath из templates/_katex_dollars.html).
  function maskOutsideMath(s) {
    if (s.indexOf('\\$') === -1) return s;
    var out = '', i = 0, n = s.length;
    while (i < n) {
      if (s.charAt(i) === '\\' && s.charAt(i + 1) === '$') { out += DOLLAR_SENTINEL; i += 2; continue; }
      var span = mathSpanEnd(s, i);
      if (span) { out += s.slice(i, span.end); i = span.end; continue; }
      out += s.charAt(i); i++;
    }
    return out;
  }

  var fragments = [];
  var leftoverText = [];
  var walker = document.createTreeWalker(box, NodeFilter.SHOW_TEXT, null);
  var node;
  while ((node = walker.nextNode())) {
    var p = node.parentNode && node.parentNode.nodeName;
    if (p === 'SCRIPT' || p === 'STYLE' || p === 'TEXTAREA') continue;
    var s = maskOutsideMath(node.nodeValue);
    var i = 0, plain = '';
    while (i < s.length) {
      var span = mathSpanEnd(s, i);
      if (span) {
        fragments.push({ tex: span.body, display: span.display });
        i = span.end;
        continue;
      }
      plain += s.charAt(i);
      i++;
    }
    if (plain.trim()) leftoverText.push(plain);
  }

  // Каждый фрагмент — строгим рендером. throwOnError:true даёт настоящую
  // ошибку разбора; strict-обработчик копит предупреждения отдельно,
  // чтобы отличить «формула не разобралась» от «разобралась, но текст
  // попал в math mode» (в режиме strict:'error' это слилось бы в одно).
  var errors = [], strictHits = [];
  for (var f = 0; f < fragments.length; f++) {
    var codes = [];
    try {
      katex.renderToString(fragments[f].tex, {
        displayMode: fragments[f].display,
        throwOnError: true,
        trust: false,
        strict: function (code, msg) { codes.push(code); return 'ignore'; }
      });
    } catch (e) {
      errors.push({ tex: fragments[f].tex.slice(0, 160), message: String(e.message).slice(0, 220) });
    }
    for (var c = 0; c < codes.length; c++) {
      strictHits.push({ code: codes[c], tex: fragments[f].tex.slice(0, 120) });
    }
  }

  return {
    fragmentCount: fragments.length,
    errors: errors,
    strictHits: strictHits,
    visibleText: leftoverText.join('\n')
  };
};
"""


def build_sandbox_html():
    """HTML песочницы: вендорный KaTeX 0.16.9 + измеритель."""
    css = _read_asset('katex.min.css')
    js = _read_asset('katex.min.js')
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        f'<style>{css}</style><script>{js}</script>'
        f'<script>{_MEASURE_JS}</script>'
        '</head><body><div id="box"></div></body></html>'
    )


class KatexPreflight:
    """Браузер поднимается ОДИН раз на всю проверку корпуса.

    Использование::

        with KatexPreflight() as pf:
            report = pf.check(html)

    `check()` принимает УЖЕ отрендеренный markdown-HTML (результат
    `problems.rendering.render_markdown`), а не сырой текст: разрывы
    `<br>`/`<p>`, которые и ломают окружения, появляются именно там.
    """

    def __init__(self):
        self._pw = None
        self._browser = None
        self._page = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        self._page = self._browser.new_page()
        self._page.set_content(build_sandbox_html(), wait_until='load')
        version = self._page.evaluate('window.katex.version')
        if version != '0.16.9':
            raise RuntimeError(
                f'Вендорный KaTeX версии {version}, ожидалась 0.16.9 — '
                f'проверка боевого рендера должна идти той же версией, что прод.'
            )
        return self

    def __exit__(self, *exc):
        if self._browser is not None:
            self._browser.close()
        if self._pw is not None:
            self._pw.stop()
        return False

    def check(self, html):
        """Один HTML-фрагмент → отчёт preflight (см. `summarize`)."""
        return self._page.evaluate('(h) => window.__preflight(h)', html)

    def check_many(self, htmls):
        """Список HTML → список отчётов, одним заходом в браузер.

        Батч заметно быстрее поштучных вызовов: на корпусе в 16 804
        задачи (по 3–6 полей у каждой) round-trip в браузер на каждое
        поле стоил бы десятки минут."""
        return self._page.evaluate(
            '(items) => items.map(h => window.__preflight(h))', htmls,
        )


def summarize(report):
    """Отчёт браузера → машинные коды дефектов (коды реестра аудита).

    Возвращает `(ok, codes, details)`: `ok=False` означает «нельзя
    ставить content_format=markdown»."""
    codes = []
    details = []

    if report['errors']:
        messages = [e['message'] for e in report['errors']]
        # Неизвестный макрос отделяется от прочих ошибок разбора: его
        # причина другая (нет преамбулы исходного проекта) и маршрут
        # другой — ручной разбор человеком, а не правка конвертера.
        # Решает сам KaTeX, а не список в macros.py: список собран по
        # 846 карточкам из 16 804 и неполон по построению.
        unresolved = find_unresolved_macros(messages)
        if unresolved:
            codes.append('MACRO')
            details.append('неизвестные макросы: ' + ', '.join(unresolved[:8]))
        other = [m for m in messages if 'Undefined control sequence' not in m]
        if other:
            codes.append('K-ERR')
            details.append(
                f'KaTeX parse error в {len(other)} формул(ах): '
                + '; '.join(other[:3])
            )

    unicode_hits = [
        h for h in report['strictHits']
        if h['code'] == 'unicodeTextInMathMode'
        and not _all_allowed(h['tex'])
    ]
    if unicode_hits:
        codes.append('K-TEXT')
        details.append(
            f'текст/Unicode в math mode: {len(unicode_hits)} случ. '
            f'(пример: {unicode_hits[0]["tex"][:80]})'
        )

    other_strict = sorted({
        h['code'] for h in report['strictHits'] if h['code'] != 'unicodeTextInMathMode'
    })
    if other_strict:
        codes.append('K-STRICT')
        details.append('strict-предупреждения KaTeX: ' + ', '.join(other_strict))

    visible = report['visibleText']

    # Любая уцелевшая TeX-команда в ВИДИМОМ тексте — сырой LaTeX на
    # экране, даже если её нет в списке маркеров. Найдено проверкой
    # готовой страницы v2: у #4073/#35255 непарный `$$` съедался
    # сканером как пустая пара (`$`+`$`), поэтому в visibleText не
    # попадал, а соседний `\sqrt{2}` в список маркеров не входил — и
    # шлюз пропускал карточку, на которой ученик видит сырой TeX.
    # Критерий аудита сформулирован именно широко: «нет текста,
    # совпадающего с … document-LaTeX командами».
    leftover_commands = sorted(set(_LEFTOVER_TEX_CMD_RE.findall(visible)))
    if leftover_commands:
        codes.append('R-CMD')
        details.append('уцелевшие TeX-команды в видимом тексте: '
                       + ', '.join(leftover_commands[:8]))

    raw_found = sorted({m for m in RAW_TEX_MARKERS if m in visible})
    if raw_found:
        code = 'PLOT' if any(
            m in raw_found for m in ('\\addplot', '\\draw', '\\node', '\\filldraw', '\\addlegendentry')
        ) else 'R-ENV' if any(m in raw_found for m in ('\\begin{', '\\end{')) else 'R-CMD'
        codes.append(code)
        details.append('сырой LaTeX в видимом тексте: ' + ', '.join(raw_found[:8]))

    return (not codes), codes, details


def _all_allowed(tex):
    """Все не-ASCII символы фрагмента входят в allowlist? (сейчас пуст —
    значит всегда False на любом не-ASCII, что и требуется)."""
    if not UNICODE_TEXT_ALLOWLIST:
        return False
    return all(ch in UNICODE_TEXT_ALLOWLIST for ch in tex if ord(ch) > 127)


def dump_report(report):
    """Компактный JSON отчёта — для файлов очереди ручного разбора."""
    return json.dumps(report, ensure_ascii=False)
