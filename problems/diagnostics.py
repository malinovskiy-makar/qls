# -*- coding: utf-8 -*-
"""Общий модуль диагностики отображения задач (только чтение).

Используется командами diagnostic_sample и full_defect_scan — детекторы
дефектов и HTML-рендер карточек живут здесь в одном месте, чтобы не
дублировать код между выборочной и полной диагностикой.

HTML-карточка воспроизводит реальный рендер страницы задачи
(catalog/templates/catalog/problem_detail.html): statement/part.statement
вставляются БЕЗ фильтров (только Django-автоэкранирование), в контейнер
.math-content без переопределения white-space (то есть браузер схлопывает
переносы строк — это фактическое поведение сайта сегодня). Правая колонка —
тот же экранированный текст, но в контейнере с white-space: pre-line.
KaTeX подключается через тот же CDN и с теми же разделителями/эскейпами
валюты (\\$ \\_ \\& \\#), что и в catalog/templates/catalog/base.html.
"""
import re

from django.utils.html import escape

SEED = 2026

FLAG_DEFS = [
    ('newline', 'Есть \\n'),
    ('bullet', 'Маркированный список'),
    ('numeric_list', 'Числовой список'),
    ('latex_junk', 'LaTeX/OCR-мусор'),
    ('truncated', 'Подозрение на обрыв'),
    ('long', 'Длина > 3000 симв.'),
]

CATEGORY_DEFS = [
    ('merged_lines', 'Слиплись строки/списки'),
    ('latex_junk', 'LaTeX/OCR-мусор'),
    ('numeric_list', 'Числовой список не разбит'),
    ('truncated', 'Обрыв текста'),
    ('missing_figure', 'Потерян рисунок'),
    ('multiple_problems', 'Несколько задач в одной'),
    ('broken_formulas', 'Формулы сломаны'),
    ('other', 'Другое'),
]


# ── Машинный пре-скан (дефекты статьи/подпунктов) ──────────────────────────

def strip_math_regions(text):
    """Вырезает области формул ($$..$$, $..$, \\[..\\], \\(..\\)), чтобы не
    путать корректный LaTeX внутри формул с мусором в обычном тексте."""
    text = re.sub(r'\$\$.*?\$\$', ' ', text, flags=re.S)
    text = re.sub(r'\$.*?\$', ' ', text, flags=re.S)
    text = re.sub(r'\\\[.*?\\\]', ' ', text, flags=re.S)
    text = re.sub(r'\\\(.*?\\\)', ' ', text, flags=re.S)
    return text


def detect_latex_junk(text):
    stripped = strip_math_regions(text)
    if '<<' in stripped or '>>' in stripped:
        return True
    if re.search(r'\\footnote\b', stripped):
        return True
    # строка-комментарий: % в начале строки (не проценты в тексте вроде "20%")
    if re.search(r'(?:^|\n)\s*%', stripped):
        return True
    # одиночные обрывки LaTeX-команд вне формул (\Big, \left и т.п.)
    if re.search(r'\\[A-Za-z]+', stripped):
        return True
    return False


def detect_truncated(text):
    t = text.rstrip()
    if not t:
        return False
    if t[-1] in ':,;':
        return True
    # обрыв на дефисе после буквы — похоже на недописанное слово
    if re.search(r'[a-zA-Zа-яА-ЯёЁ]-$', t):
        return True
    return False


def scan_flags(scan_text):
    return {
        'newline': '\n' in scan_text,
        'bullet': bool(re.search(r'(?:^|\n)\s*[•\-–—]\s+\S', scan_text)),
        'numeric_list': bool(re.search(r'(?:^|\n)\s*\d{1,2}[.)]\s+\S', scan_text)),
        'latex_junk': detect_latex_junk(scan_text),
        'truncated': detect_truncated(scan_text),
        'long': len(scan_text) > 3000,
    }


def build_scan_text(problem, parts):
    blocks = [problem.statement or '']
    for part in parts:
        if part.statement:
            blocks.append(part.statement)
    return '\n'.join(blocks)


# ── Статистика переносов строк (для классификации источников, Задача 2) ────

TERMINAL_PUNCT = ('.', '?', '!', ';')
# Хвостовые закрывающие символы — не мешают засчитать пунктуацию перед ними
# (например, строка кончается на «...функции.)» — это нормальное окончание).
LINE_CLOSERS = ')]"\'»”'
LIST_LINE_RE = re.compile(r'^\s*(?:[•\-–—]\s+\S|\d{1,2}[.)]\s+\S)')


def line_ends_badly(line):
    """True, если строка обрывается НЕ на завершающую пунктуацию (и не
    похожа на элемент списка — это проверяется отдельно вызывающим кодом)."""
    t = line.rstrip()
    while t and t[-1] in LINE_CLOSERS:
        t = t[:-1]
    if not t:
        return False
    return t[-1] not in TERMINAL_PUNCT


def collect_line_stats(text, stats):
    """Обновляет накопительный словарь stats метриками по строкам statement.

    stats — dict с ключами 'line_lengths' (list), 'non_list_lines' (int),
    'bad_ending_lines' (int). Строки-элементы списка не участвуют в оценке
    «оборванности» (список естественно не кончается точкой на каждой строке).
    """
    for raw_line in text.split('\n'):
        line = raw_line.strip()
        if not line:
            continue
        stats['line_lengths'].append(len(line))
        if LIST_LINE_RE.match(raw_line):
            continue
        stats['non_list_lines'] += 1
        if line_ends_badly(line):
            stats['bad_ending_lines'] += 1


# ── HTML-рендер карточки задачи ─────────────────────────────────────────

CARD_TEMPLATE = """
<section class="card" data-id="{pid}">
  <header class="card-head">
    <div class="card-head-top">
      <span class="card-id">#{pid}</span>
      <span class="card-source">{source_label}</span>
      <a class="card-link" href="{url}" target="_blank" rel="noopener">{url}</a>
    </div>
    <h2 class="card-title">{title}</h2>
    <div class="card-flags">{flag_badges}</div>
  </header>

  <div class="card-cols">
    <div class="col">
      <div class="col-label">Как сейчас на сайте</div>
      <div class="problem-statement">
        <div class="math-content ws-normal">{statement_html}</div>
      </div>
      {parts_left}
    </div>
    <div class="col">
      <div class="col-label">С исправленными переносами (white-space: pre-line)</div>
      <div class="problem-statement">
        <div class="math-content ws-preline">{statement_html}</div>
      </div>
      {parts_right}
    </div>
  </div>

  <div class="markup-panel" data-id="{pid}">
    <div class="markup-row">
      <label><input type="radio" name="verdict-{pid}" value="ok"> Нормально</label>
      <label><input type="radio" name="verdict-{pid}" value="bad"> Плохо</label>
    </div>
    <div class="markup-categories" hidden>
      {category_checkboxes}
      <label class="comment-label">Комментарий:
        <input type="text" class="comment-input" data-id="{pid}" placeholder="комментарий (необязательно)">
      </label>
    </div>
    <div class="markup-row">
      <label><input type="checkbox" class="preline-better" data-id="{pid}"> Правая колонка (pre-line) выглядит лучше левой</label>
    </div>
  </div>
</section>
"""


def _flag_badges_html(flags):
    badges = []
    for key, label in FLAG_DEFS:
        if flags.get(key):
            badges.append('<span class="badge badge-{0}">{1}</span>'.format(key, escape(label)))
    if not badges:
        badges.append('<span class="badge badge-clean">чисто</span>')
    return ''.join(badges)


def _part_block_html(parts, ws_class):
    if not parts:
        return ''
    rows = []
    for part in parts:
        if not part.statement:
            continue
        rows.append(
            '<div class="part-item"><div class="part-header">'
            '<span class="part-label">{label})</span>'
            '<div class="part-statement math-content {ws}">{stmt}</div>'
            '</div></div>'.format(
                label=escape(part.label),
                ws=ws_class,
                stmt=escape(part.statement),
            )
        )
    if not rows:
        return ''
    return '<div class="parts-intro">Подпункты</div><div class="parts-list">' + ''.join(rows) + '</div>'


def render_card(problem, parts, flags, source_label):
    url = 'http://127.0.0.1:8000/catalog/{0}/'.format(problem.pk)
    title = escape(problem.title) if problem.title else 'Задача #{0}'.format(problem.pk)
    statement_html = escape(problem.statement or '')

    category_checkboxes = ''.join(
        '<label><input type="checkbox" class="cat-box" data-cat="{key}" data-id="{pid}"> {label}</label>'.format(
            key=key, label=escape(label), pid=problem.pk,
        )
        for key, label in CATEGORY_DEFS
    )

    return CARD_TEMPLATE.format(
        pid=problem.pk,
        source_label=escape(source_label),
        url=url,
        title=title,
        flag_badges=_flag_badges_html(flags),
        statement_html=statement_html,
        parts_left=_part_block_html(parts, 'ws-normal'),
        parts_right=_part_block_html(parts, 'ws-preline'),
        category_checkboxes=category_checkboxes,
    )


def render_group_header(title, description=''):
    """Заголовок-разделитель группы карточек (флаг или источник) внутри
    общего потока cards_html."""
    desc_html = '<div class="group-desc">{0}</div>'.format(escape(description)) if description else ''
    return '<div class="group-header"><h2>{0}</h2>{1}</div>'.format(escape(title), desc_html)


# ── HTML-страница целиком ───────────────────────────────────────────────

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>{page_title}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js" onload="initKaTeX()"></script>
<style>
:root {{
  --bg: #f4f4f6; --surface: #fff; --border: #ddd; --text: #1a1a1a; --text2: #666;
  --accent: #BE185D; --chip-bg: #f0f0f2; --chip-text: #444;
  --amber: #b26b00; --green: #1d7e45; --red: #c0392b;
}}
* {{ box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 24px; }}
h1 {{ font-size: 20px; margin-bottom: 4px; }}
.meta {{ color: var(--text2); font-size: 13px; margin-bottom: 20px; }}
.summary {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px 20px; margin-bottom: 20px; }}
.summary table {{ border-collapse: collapse; font-size: 13px; }}
.summary td {{ padding: 3px 12px 3px 0; }}
.toolbar {{ margin-bottom: 24px; display: flex; align-items: center; gap: 12px; }}
.toolbar button {{ background: var(--accent); color: #fff; border: none; border-radius: 8px; padding: 10px 18px; font-size: 14px; cursor: pointer; }}
.toolbar button:hover {{ opacity: .9; }}
#copy-status {{ font-size: 13px; color: var(--green); }}
.group-header {{ margin: 32px 0 14px; padding-bottom: 6px; border-bottom: 2px solid var(--accent); }}
.group-header h2 {{ font-size: 17px; margin: 0 0 4px; }}
.group-header .group-desc {{ font-size: 12px; color: var(--text2); }}
.card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 18px 20px; margin-bottom: 20px; }}
.card-head-top {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap; font-size: 12px; color: var(--text2); margin-bottom: 6px; }}
.card-id {{ font-weight: 700; color: var(--text); }}
.card-source {{ background: var(--chip-bg); color: var(--chip-text); border-radius: 20px; padding: 2px 9px; }}
.card-link {{ color: var(--accent); text-decoration: none; }}
.card-title {{ font-size: 16px; margin: 0 0 8px; }}
.card-flags {{ margin-bottom: 12px; }}
.badge {{ display: inline-block; font-size: 11px; padding: 2px 8px; border-radius: 20px; margin: 0 5px 5px 0; background: var(--chip-bg); color: var(--chip-text); }}
.badge-clean {{ background: #e5f4ec; color: var(--green); }}
.badge-latex_junk, .badge-truncated {{ background: #fbe8e6; color: var(--red); }}
.badge-long, .badge-numeric_list, .badge-bullet {{ background: #fdf1de; color: var(--amber); }}
.card-cols {{ display: flex; gap: 16px; }}
.col {{ flex: 1; min-width: 0; }}
.col-label {{ font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .5px; color: var(--text2); margin-bottom: 6px; }}
.problem-statement {{ background: #fafafa; border: 1px solid var(--border); border-radius: 8px; padding: 14px 16px; margin-bottom: 10px; }}
.math-content {{ font-size: 14px; line-height: 1.7; word-wrap: break-word; }}
.ws-normal {{ white-space: normal; }}
.ws-preline {{ white-space: pre-line; }}
.parts-intro {{ font-size: 11px; font-weight: 600; text-transform: uppercase; color: var(--text2); margin: 4px 0 8px; }}
.parts-list {{ display: flex; flex-direction: column; gap: 8px; }}
.part-item {{ border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; background: #fdf2f6; }}
.part-header {{ display: flex; gap: 8px; align-items: baseline; }}
.part-label {{ font-weight: 700; color: var(--accent); font-size: 13px; }}
.markup-panel {{ border-top: 1px solid var(--border); margin-top: 14px; padding-top: 12px; font-size: 13px; }}
.markup-row {{ display: flex; gap: 18px; flex-wrap: wrap; margin-bottom: 8px; align-items: center; }}
.markup-categories {{ display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 8px; padding: 8px 10px; background: #fafafa; border-radius: 8px; }}
.comment-label {{ display: flex; align-items: center; gap: 6px; flex: 1; min-width: 220px; }}
.comment-input {{ flex: 1; padding: 4px 8px; border: 1px solid var(--border); border-radius: 6px; }}
@media (max-width: 900px) {{ .card-cols {{ flex-direction: column; }} }}
</style>
</head>
<body>
<h1>{page_title}</h1>
<div class="meta">{meta_line}</div>

<div class="summary">
  <strong>Сводка машинного пре-скана</strong>
  <table>{summary_rows}</table>
</div>

<div class="toolbar">
  <button id="copy-btn">Скопировать итог</button>
  <span id="copy-status"></span>
</div>

{cards_html}

<script>
var DOLLAR_SENTINEL = '\\uE000';
function maskEscapedDollars(root) {{
  var walker = document.createTreeWalker(root || document.body, NodeFilter.SHOW_TEXT, null);
  var node;
  while ((node = walker.nextNode())) {{
    var p = node.parentNode && node.parentNode.nodeName;
    if (p === 'SCRIPT' || p === 'STYLE' || p === 'TEXTAREA') continue;
    if (node.nodeValue.indexOf('\\\\$') !== -1) {{
      node.nodeValue = node.nodeValue.split('\\\\$').join(DOLLAR_SENTINEL);
    }}
  }}
}}
function fixCurrencyDollars(root) {{
  var walker = document.createTreeWalker(root || document.body, NodeFilter.SHOW_TEXT, null);
  var node;
  while ((node = walker.nextNode())) {{
    var p = node.parentNode && node.parentNode.nodeName;
    if (p === 'SCRIPT' || p === 'STYLE' || p === 'TEXTAREA') continue;
    var v = node.nodeValue;
    if (v.indexOf(DOLLAR_SENTINEL) !== -1 || v.indexOf('\\\\$') !== -1 ||
        v.indexOf('\\\\_') !== -1 || v.indexOf('\\\\&') !== -1 ||
        v.indexOf('\\\\#') !== -1) {{
      node.nodeValue = v.split(DOLLAR_SENTINEL).join('$').split('\\\\$').join('$')
                        .split('\\\\_').join('_').split('\\\\&').join('&')
                        .split('\\\\#').join('#');
    }}
  }}
}}
function initKaTeX() {{
  maskEscapedDollars(document.body);
  renderMathInElement(document.body, {{
    delimiters: [
      {{ left: '$$',   right: '$$',   display: true  }},
      {{ left: '$',    right: '$',    display: false }},
      {{ left: '\\\\[',  right: '\\\\]',  display: true  }},
      {{ left: '\\\\(',  right: '\\\\)',  display: false }}
    ],
    throwOnError: false
  }});
  fixCurrencyDollars(document.body);
}}
document.addEventListener('DOMContentLoaded', function () {{
  fixCurrencyDollars(document.body);
}});

// ── Панель разметки: хранение в localStorage, сборка итога ──────────────
var STORAGE_KEY = 'diagnostic_sample_markup_v1';

function loadState() {{
  try {{ return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {{}}; }}
  catch (e) {{ return {{}}; }}
}}
function saveState(state) {{
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}}
function getEntry(state, id) {{
  if (!state[id]) state[id] = {{ verdict: '', categories: [], comment: '', prelineBetter: false }};
  return state[id];
}}

var state = loadState();

// Восстановить состояние из localStorage на странице.
document.querySelectorAll('.markup-panel').forEach(function (panel) {{
  var id = panel.getAttribute('data-id');
  var entry = getEntry(state, id);
  var radios = panel.querySelectorAll('input[type=radio]');
  radios.forEach(function (r) {{
    if (r.value === entry.verdict) r.checked = true;
    r.addEventListener('change', function () {{
      entry.verdict = r.value;
      panel.querySelector('.markup-categories').hidden = (r.value !== 'bad');
      saveState(state);
    }});
  }});
  panel.querySelector('.markup-categories').hidden = (entry.verdict !== 'bad');

  panel.querySelectorAll('.cat-box').forEach(function (box) {{
    var cat = box.getAttribute('data-cat');
    box.checked = entry.categories.indexOf(cat) !== -1;
    box.addEventListener('change', function () {{
      var idx = entry.categories.indexOf(cat);
      if (box.checked && idx === -1) entry.categories.push(cat);
      if (!box.checked && idx !== -1) entry.categories.splice(idx, 1);
      saveState(state);
    }});
  }});

  var commentInput = panel.querySelector('.comment-input');
  commentInput.value = entry.comment || '';
  commentInput.addEventListener('input', function () {{
    entry.comment = commentInput.value;
    saveState(state);
  }});

  var prelineBox = panel.querySelector('.preline-better');
  prelineBox.checked = !!entry.prelineBetter;
  prelineBox.addEventListener('change', function () {{
    entry.prelineBetter = prelineBox.checked;
    saveState(state);
  }});
}});

document.getElementById('copy-btn').addEventListener('click', function () {{
  var lines = [];
  var okCount = 0, badCount = 0, prelineBetterCount = 0;
  var catCounts = {{}};
  Object.keys(state).sort(function (a, b) {{ return Number(a) - Number(b); }}).forEach(function (id) {{
    var e = state[id];
    if (!e.verdict) return;
    if (e.verdict === 'ok') okCount++;
    if (e.verdict === 'bad') badCount++;
    if (e.prelineBetter) prelineBetterCount++;
    e.categories.forEach(function (c) {{ catCounts[c] = (catCounts[c] || 0) + 1; }});
    var line = '#' + id + ' -> ' + e.verdict;
    if (e.categories.length) line += ' [' + e.categories.join(', ') + ']';
    if (e.prelineBetter) line += ' (preline лучше)';
    if (e.comment) line += ' — ' + e.comment;
    lines.push(line);
  }});
  var summary = 'Итог: нормально=' + okCount + ', плохо=' + badCount + ', preline-лучше=' + prelineBetterCount;
  var catSummary = Object.keys(catCounts).sort().map(function (k) {{ return k + '=' + catCounts[k]; }}).join(', ');
  var text = summary + (catSummary ? ('\\nКатегории: ' + catSummary) : '') + '\\n\\n' + lines.join('\\n');
  var statusEl = document.getElementById('copy-status');
  function done() {{ statusEl.textContent = 'Скопировано (' + lines.length + ' размечено)'; }}
  if (navigator.clipboard && navigator.clipboard.writeText) {{
    navigator.clipboard.writeText(text).then(done, function () {{ statusEl.textContent = 'Не удалось скопировать'; }});
  }} else {{
    var ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    done();
  }}
}});
</script>
</body>
</html>
"""


def render_page(page_title, meta_line, summary_rows_html, cards_html):
    return PAGE_TEMPLATE.format(
        page_title=escape(page_title),
        meta_line=meta_line,  # уже готовый HTML (может содержать ссылки) — не экранируем
        summary_rows=summary_rows_html,
        cards_html=cards_html,
    )
