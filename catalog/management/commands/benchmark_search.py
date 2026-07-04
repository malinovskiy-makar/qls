"""
Команда benchmark_search — замер качества семантического поиска.

Прогоняет 5 фиксированных тестовых запросов через catalog.semantic.search()
и печатает топ-10 результатов с баллами. Дополнительно генерирует
reports/search_benchmark/benchmark_report.html с полными условиями и KaTeX.

Запуск:
    ./venv/bin/python manage.py benchmark_search
    ./venv/bin/python manage.py benchmark_search > reports/bge_benchmark/before_minilm.txt
"""

import html
import os
import time

from django.core.management.base import BaseCommand

QUERIES = [
    "Известно изменение цены и точечная эластичность спроса. Найти изменение количества.",
    "Несколько индивидуальных групп спроса с разным числом людей в каждой группе; "
    "в задаче меняется количество потребителей в каждой группе.",
    "Единственный продавец на рынке выбирает объём выпуска и цену для максимальной прибыли; "
    "даны функция спроса и функция издержек.",
    "На товар вводят налог. Найти, как налоговое бремя делится между покупателем и продавцом "
    "и чему равны потери общества.",
    "Две страны производят два товара с разной производительностью. Определить сравнительное "
    "преимущество и условия взаимовыгодной торговли.",
]

REPORT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)
    )))),
    "reports", "search_benchmark",
)

_KATEX_VERSION = "0.16.9"

_CSS = """\
  body { font-family: sans-serif; font-size: 13px; background: #f0f0f0; margin: 0; padding: 16px; }
  h1 { font-size: 20px; margin-bottom: 4px; }
  .toc { background: #fff; border: 1px solid #ddd; border-radius: 6px; padding: 12px 16px;
         margin-bottom: 24px; display: inline-block; min-width: 360px; }
  .toc h2 { font-size: 14px; margin: 0 0 8px; }
  .toc ol { margin: 0; padding-left: 20px; }
  .toc li { margin: 4px 0; }
  .toc a { color: #1d4ed8; text-decoration: none; }
  .toc a:hover { text-decoration: underline; }
  .section { margin-bottom: 40px; }
  .section-title { font-size: 16px; font-weight: bold; border-bottom: 2px solid #bbb;
                   padding-bottom: 6px; margin-bottom: 12px; }
  .section-stats { font-size: 12px; color: #555; margin-bottom: 10px; }
  .card { background: #fff; border: 1px solid #ddd; border-radius: 6px;
          margin: 10px 0; padding: 12px 14px; position: relative; }
  .card.relevant { border-left: 4px solid #16a34a; background: #f0fdf4; }
  .card.irrelevant { border-left: 4px solid #dc2626; background: #fef2f2; }
  .card-header { display: flex; align-items: flex-start; justify-content: space-between;
                 margin-bottom: 8px; gap: 8px; }
  .card-meta { flex: 1; }
  .rank { font-weight: bold; color: #555; margin-right: 6px; }
  .score { font-weight: bold; margin-right: 8px; }
  .score.high { color: #16a34a; }
  .score.mid  { color: #ca8a04; }
  .score.low  { color: #dc2626; }
  .prob-id a { color: #1d4ed8; font-size: 11px; text-decoration: none; }
  .prob-id a:hover { text-decoration: underline; }
  .prob-title { font-weight: bold; margin-top: 2px; }
  .toggle-btn { cursor: pointer; border: 1px solid #ccc; background: #f5f5f5;
                border-radius: 4px; padding: 3px 10px; font-size: 12px;
                white-space: nowrap; flex-shrink: 0; user-select: none; }
  .toggle-btn:hover { background: #e5e5e5; }
  .math-content { font-size: 13px; line-height: 1.7; overflow-wrap: break-word;
                  white-space: pre-wrap; margin-top: 6px; }
  .part-label { font-weight: bold; color: #555; margin-top: 8px; margin-bottom: 2px;
                font-size: 12px; }
  .total-bar { background: #fff; border: 1px solid #ccc; border-radius: 6px;
               padding: 12px 16px; margin-top: 32px; font-size: 14px; }
  .total-bar span { font-weight: bold; }"""

_KATEX_JS = r"""
var DOLLAR_SENTINEL = '¤';

function maskEscapedDollars(root) {
  var walker = document.createTreeWalker(root || document.body, NodeFilter.SHOW_TEXT, null);
  var node;
  while ((node = walker.nextNode())) {
    var p = node.parentNode && node.parentNode.nodeName;
    if (p === 'SCRIPT' || p === 'STYLE' || p === 'TEXTAREA') continue;
    if (node.nodeValue.indexOf('\\$') !== -1) {
      node.nodeValue = node.nodeValue.split('\\$').join(DOLLAR_SENTINEL);
    }
  }
}

function fixCurrencyDollars(root) {
  var walker = document.createTreeWalker(root || document.body, NodeFilter.SHOW_TEXT, null);
  var node;
  while ((node = walker.nextNode())) {
    var p = node.parentNode && node.parentNode.nodeName;
    if (p === 'SCRIPT' || p === 'STYLE' || p === 'TEXTAREA') continue;
    var v = node.nodeValue;
    if (v.indexOf(DOLLAR_SENTINEL) !== -1 || v.indexOf('\\$') !== -1 ||
        v.indexOf('\\_') !== -1 || v.indexOf('\\&') !== -1 ||
        v.indexOf('\\#') !== -1) {
      node.nodeValue = v.split(DOLLAR_SENTINEL).join('$').split('\\$').join('$')
                        .split('\\_').join('_').split('\\&').join('&')
                        .split('\\#').join('#');
    }
  }
}

function initKaTeX() {
  maskEscapedDollars(document.body);
  renderMathInElement(document.body, {
    delimiters: [
      { left: '$$',  right: '$$',  display: true  },
      { left: '$',   right: '$',   display: false },
      { left: '\\[', right: '\\]', display: true  },
      { left: '\\(', right: '\\)', display: false }
    ],
    throwOnError: false,
    ignoredClasses: ['no-katex']
  });
  fixCurrencyDollars(document.body);
}

document.addEventListener('DOMContentLoaded', function () {
  fixCurrencyDollars(document.body);
});

// Переключатель галочек: — → ✓ в тему → ✗ не в тему → —
var STATES = ['neutral', 'relevant', 'irrelevant'];
var LABELS = { neutral: '—', relevant: '✓ в тему', irrelevant: '✗ не в тему' };

function cycleToggle(btn) {
  var card = btn.closest('.card');
  var sectionEl = btn.closest('.section');
  var cur = btn.dataset.state || 'neutral';
  var nextIdx = (STATES.indexOf(cur) + 1) % STATES.length;
  var next = STATES[nextIdx];
  btn.dataset.state = next;
  btn.textContent = LABELS[next];
  card.classList.remove('relevant', 'irrelevant');
  if (next !== 'neutral') card.classList.add(next);
  updateCounts(sectionEl);
  updateTotalCounts();
}

function countSection(sectionEl) {
  var cards = sectionEl.querySelectorAll('.card');
  var labeled = 0, relevant = 0;
  cards.forEach(function(c) {
    var btn = c.querySelector('.toggle-btn');
    if (!btn) return;
    var st = btn.dataset.state || 'neutral';
    if (st !== 'neutral') labeled++;
    if (st === 'relevant') relevant++;
  });
  return { total: cards.length, labeled: labeled, relevant: relevant };
}

function updateCounts(sectionEl) {
  var statsEl = sectionEl.querySelector('.section-stats');
  if (!statsEl) return;
  var c = countSection(sectionEl);
  statsEl.textContent = 'Размечено: ' + c.labeled + '/' + c.total + ', в тему: ' + c.relevant;
}

function updateTotalCounts() {
  var totalEl = document.getElementById('total-counts');
  if (!totalEl) return;
  var sections = document.querySelectorAll('.section');
  var labeled = 0, relevant = 0, total = 0;
  sections.forEach(function(s) {
    var c = countSection(s);
    labeled += c.labeled;
    relevant += c.relevant;
    total += c.total;
  });
  totalEl.innerHTML = 'Итого по всем запросам: размечено <span>' + labeled + '/' + total +
                      '</span>, в тему <span>' + relevant + '</span>';
}
"""


def _render_text(text: str) -> str:
    """Текст → HTML без разбивки на теги. white-space:pre-wrap сохраняет переносы."""
    if not text:
        return ""
    return html.escape(text)


def _score_class(score: float) -> str:
    if score >= 0.70:
        return "high"
    if score >= 0.50:
        return "mid"
    return "low"


def _card_html(rank: int, result: dict) -> str:
    p = result["problem"]
    score = result["score"]
    score_pct = score * 100
    pid = p.pk
    title = html.escape(p.title or f"Задача #{pid}")
    url = f"http://127.0.0.1:8000/catalog/problem/{pid}/"

    stmt_html = (
        f'<div class="math-content">{_render_text(p.statement or "")}</div>'
    )

    # Подпункты
    parts_html = ""
    parts = list(p.parts.order_by("label").all())
    for part in parts:
        parts_html += (
            f'<div class="part-label">Подпункт [{html.escape(part.label)}]</div>'
            f'<div class="math-content">{_render_text(part.statement or "")}</div>'
        )

    return (
        f'<div class="card" id="c{pid}-{rank}">'
        f'<div class="card-header">'
        f'<div class="card-meta">'
        f'<span class="rank">#{rank}</span>'
        f'<span class="score {_score_class(score)}">{score_pct:.1f}%</span>'
        f'<span class="prob-id"><a href="{url}" target="_blank">id={pid}</a></span>'
        f'<div class="prob-title">{title}</div>'
        f'</div>'
        f'<button class="toggle-btn" data-state="neutral" onclick="cycleToggle(this)">—</button>'
        f'</div>'
        f'{stmt_html}'
        f'{parts_html}'
        f'</div>'
    )


def _section_html(q_idx: int, query: str, results: list) -> str:
    anchor = f"q{q_idx}"
    cards = "\n".join(_card_html(rank, r) for rank, r in enumerate(results, start=1))
    return (
        f'<div class="section" id="{anchor}">'
        f'<div class="section-title">Запрос {q_idx}: {html.escape(query)}</div>'
        f'<div class="section-stats">Размечено: 0/{len(results)}, в тему: 0</div>'
        f'{cards}'
        f'</div>'
    )


def _build_html(all_sections: list) -> str:
    v = _KATEX_VERSION
    cdn = f"https://cdn.jsdelivr.net/npm/katex@{v}/dist"

    toc_items = "\n".join(
        f'<li><a href="#q{i}">{html.escape(q[:80])}</a></li>'
        for i, q in enumerate(QUERIES, start=1)
    )
    toc = (
        f'<div class="toc">'
        f'<h2>Оглавление</h2>'
        f'<ol>{toc_items}</ol>'
        f'</div>'
    )

    sections_html = "\n\n".join(all_sections)

    total_bar = (
        '<div class="total-bar" id="total-counts">'
        'Итого по всем запросам: размечено <span>0/0</span>, в тему <span>0</span>'
        '</div>'
    )

    return "\n".join([
        "<!DOCTYPE html>",
        '<html lang="ru">',
        "<head>",
        '<meta charset="utf-8">',
        "<title>Benchmark семантического поиска</title>",
        f'<link rel="stylesheet" href="{cdn}/katex.min.css">',
        f'<script defer src="{cdn}/katex.min.js"></script>',
        f'<script defer src="{cdn}/contrib/auto-render.min.js"',
        '        onload="initKaTeX()"></script>',
        "<style>",
        _CSS,
        "</style>",
        "</head>",
        "<body>",
        "<h1>Benchmark семантического поиска</h1>",
        toc,
        sections_html,
        total_bar,
        "<script>",
        _KATEX_JS,
        "</script>",
        "</body>",
        "</html>",
    ])


class Command(BaseCommand):
    help = 'Замер качества семантического поиска (5 тестовых запросов, топ-10)'

    def handle(self, *args, **options):
        from catalog.semantic import search

        self.stdout.write('=' * 80)
        self.stdout.write('ЗАМЕР СЕМАНТИЧЕСКОГО ПОИСКА — топ-10 по каждому запросу')
        self.stdout.write('=' * 80)
        self.stdout.write('')

        summary_lines = []
        all_sections = []

        for q_idx, query in enumerate(QUERIES, start=1):
            self.stdout.write(f'── Запрос {q_idx}/5 ──────────────────────────────────────────────────────────')
            self.stdout.write(f'  {query}')
            self.stdout.write('')

            t0 = time.time()
            results = search(query, content_kind='all', limit=10)
            elapsed = time.time() - t0

            if not results:
                self.stdout.write('  [Нет результатов]')
                self.stdout.write('')
                summary_lines.append(f'Q{q_idx}: нет результатов')
                all_sections.append(_section_html(q_idx, query, []))
                continue

            # Prefetch подпунктов для HTML-отчёта
            from django.db.models import prefetch_related_objects
            problems = [r["problem"] for r in results]
            prefetch_related_objects(problems, "parts")

            for rank, r in enumerate(results, start=1):
                p = r['problem']
                score_pct = r['score'] * 100
                title = (p.title or '')[:70]
                stmt = (p.statement or '')[:80].replace('\n', ' ')
                self.stdout.write(
                    f'  #{rank:2d}  {score_pct:5.1f}%  id={p.pk:<6}  '
                    f'title={title!r}'
                )
                self.stdout.write(
                    f'           stmt: {stmt!r}'
                )

            self.stdout.write('')

            top1_score = results[0]['score'] * 100
            top5_scores = [r['score'] * 100 for r in results[:5]]
            avg_top5 = sum(top5_scores) / len(top5_scores)

            summary_line = (
                f'Q{q_idx}: топ-1={top1_score:.1f}%  '
                f'топ-5 avg={avg_top5:.1f}%  '
                f'[{", ".join(f"{s:.1f}" for s in top5_scores)}]  '
                f'({elapsed:.2f}с)'
            )
            self.stdout.write(f'  Итог: {summary_line}')
            self.stdout.write('')
            summary_lines.append(summary_line)

            all_sections.append(_section_html(q_idx, query, results))

        self.stdout.write('=' * 80)
        self.stdout.write('СВОДКА')
        self.stdout.write('=' * 80)
        for line in summary_lines:
            self.stdout.write(f'  {line}')
        self.stdout.write('')

        # HTML-отчёт
        os.makedirs(REPORT_DIR, exist_ok=True)
        report_path = os.path.join(REPORT_DIR, "benchmark_report.html")
        html_content = _build_html(all_sections)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        self.stdout.write(f'HTML-отчёт: {report_path}')
