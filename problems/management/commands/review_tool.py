"""
review_tool.py — сессия H, этап 7. Интерактивный HTML для ручного отсмотра.

Генерирует reports/sessionH/review_200.html: N случайных ВИДИМЫХ задач
(published, без флага шлюза), стратифицированно по источникам (<= cap на
источник), самодостаточный HTML с KaTeX (CDN jsdelivr) и фронтовой чисткой
эскейпов \\$ \\_ \\& \\# (fix-v2 + DOMContentLoaded-страховка, как на сайте).

Интерактив:
  - кнопки «OK» / «Проблема» на каждой карточке (подсветка);
  - плавающая панель: «размечено X из N, проблемных Y», кнопка
    «Скопировать ID проблемных» + textarea с тем же списком;
  - прогресс в localStorage по ключу с seed и датой генерации (если
    localStorage недоступен на file:// — состояние живёт в памяти страницы).

Запуск:
    ./venv/bin/python manage.py review_tool                  # 200, seed 20260613
    ./venv/bin/python manage.py review_tool --count 100 --seed 7
    ./venv/bin/python manage.py review_tool --ids-file путь/к/ids.txt --output out.html
"""

import html
import os
import random
from collections import defaultdict

from django.core.management.base import BaseCommand

from problems.models import Problem

OUTPUT = 'reports/sessionH/review_200.html'
PER_SOURCE_CAP = 15

PAGE_HEAD = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Сессия H — ручной отсмотр {count} видимых задач</title>
<link rel="stylesheet"
  href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script defer
  src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<script defer
  src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"
  onload="maskEscapedDollars(document.body); renderMathInElement(document.body, {{delimiters: [
    {{left: '$$', right: '$$', display: true}},
    {{left: '$', right: '$', display: false}},
    {{left: '\\\\[', right: '\\\\]', display: true}},
    {{left: '\\\\(', right: '\\\\)', display: false}}
  ], throwOnError: false}}); fixCurrencyDollars(document.body);"></script>
<script>
// fix-v3 как на сайте (H3): ДО KaTeX маскируем «\\$» приватным символом,
// иначе auto-render разрезает «\\$» по границе доллара и слэш остаётся виден.
var DOLLAR_SENTINEL = '\\uE000';
function maskEscapedDollars(root) {{
  var w = document.createTreeWalker(root || document.body, NodeFilter.SHOW_TEXT, null);
  var n;
  while ((n = w.nextNode())) {{
    var tag = n.parentNode && n.parentNode.nodeName;
    if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'TEXTAREA') continue;
    if (n.nodeValue.indexOf('\\\\$') !== -1) {{
      n.nodeValue = n.nodeValue.split('\\\\$').join(DOLLAR_SENTINEL);
    }}
  }}
}}
// после KaTeX возвращаем sentinel→$ и чистим прочие эскейпы \\_ \\& \\#
function fixCurrencyDollars(root) {{
  var w = document.createTreeWalker(root || document.body, NodeFilter.SHOW_TEXT, null);
  var n;
  while ((n = w.nextNode())) {{
    var tag = n.parentNode && n.parentNode.nodeName;
    if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'TEXTAREA') continue;
    var v = n.nodeValue;
    if (v.indexOf(DOLLAR_SENTINEL) !== -1 || v.indexOf('\\\\$') !== -1 ||
        v.indexOf('\\\\_') !== -1 || v.indexOf('\\\\&') !== -1 ||
        v.indexOf('\\\\#') !== -1) {{
      n.nodeValue = v.split(DOLLAR_SENTINEL).join('$').split('\\\\$').join('$')
                     .split('\\\\_').join('_').split('\\\\&').join('&')
                     .split('\\\\#').join('#');
    }}
  }}
}}
// страховка: без CDN KaTeX не запускался — фрагментации нет, чистим \\$ напрямую
document.addEventListener('DOMContentLoaded', function () {{
  fixCurrencyDollars(document.body);
}});
</script>
<style>
  body {{ font-family: -apple-system, 'Segoe UI', sans-serif; margin: 0;
         background: #f7f7f5; color: #1a1f2e; }}
  header {{ background: #1a1f2e; color: #fff; padding: 16px 28px; }}
  header h1 {{ margin: 0; font-size: 20px; }}
  header p {{ margin: 6px 0 0; font-size: 13px; color: #aab; }}
  main {{ max-width: 960px; margin: 0 auto; padding: 24px 24px 110px; }}
  h2.source {{ margin-top: 36px; border-bottom: 2px solid #4f7cff;
              padding-bottom: 6px; font-size: 18px; }}
  .problem {{ background: #fff; border: 1px solid #e8e8e4; border-radius: 10px;
             padding: 16px 20px; margin: 14px 0; transition: box-shadow .15s; }}
  .problem.ok {{ background: #f3faf4; border-color: #9fd6a8; }}
  .problem.bad {{ background: #fdf3f3; border-color: #e8a0a2; }}
  .problem .meta {{ font-size: 13px; color: #777; margin-bottom: 8px;
                   display: flex; align-items: center; gap: 10px; }}
  .problem .meta a {{ color: #4f7cff; text-decoration: none; }}
  .vote {{ margin-left: auto; display: flex; gap: 6px; }}
  .vote button {{ border: 1px solid #d8d8d4; background: #fff; border-radius: 7px;
                 padding: 4px 12px; font-size: 13px; cursor: pointer; }}
  .vote button.sel-ok {{ background: #2e9e44; border-color: #2e9e44; color: #fff; }}
  .vote button.sel-bad {{ background: #d04547; border-color: #d04547; color: #fff; }}
  .label {{ font-weight: 600; font-size: 13px; color: #4f7cff;
           margin: 10px 0 4px; text-transform: uppercase; }}
  .text {{ white-space: pre-wrap; line-height: 1.5; font-size: 15px; }}
  .part {{ border-left: 3px solid #e8e8e4; padding-left: 12px; margin: 8px 0; }}
  .part .plabel {{ font-weight: 600; }}
  .answer {{ background: #f0f6ff; border-radius: 6px; padding: 8px 12px; }}
  #panel {{ position: fixed; left: 0; right: 0; bottom: 0; background: #1a1f2e;
           color: #fff; padding: 10px 24px; display: flex; align-items: center;
           gap: 14px; font-size: 14px; z-index: 50; flex-wrap: wrap; }}
  #panel button {{ background: #4f7cff; color: #fff; border: none;
                  border-radius: 7px; padding: 7px 14px; cursor: pointer;
                  font-size: 13px; }}
  #panel textarea {{ flex: 1; min-width: 220px; height: 34px; border-radius: 6px;
                    border: none; padding: 6px 8px; font-size: 12px;
                    font-family: monospace; resize: vertical; }}
</style>
</head>
<body>
<header>
  <h1>Сессия H — ручной отсмотр {count} случайных видимых задач</h1>
  <p>seed {seed}, сгенерировано {gen_date}. Размечайте каждую карточку: OK или Проблема.
     Прогресс сохраняется в localStorage этого браузера.</p>
</header>
<main>
"""

PAGE_TAIL = """</main>
<div id="panel">
  <span id="progress">размечено 0 из {count}, проблемных 0</span>
  <button onclick="copyBad()">Скопировать ID проблемных</button>
  <textarea id="badlist" readonly
            placeholder="id проблемных появятся здесь"></textarea>
</div>
<script>
var TOTAL = {count};
var KEY = 'reviewH_{seed}_{gen_date}';
var state = {{}};
try {{
  state = JSON.parse(localStorage.getItem(KEY) || '{{}}');
}} catch (e) {{ state = {{}}; }}

function save() {{
  try {{ localStorage.setItem(KEY, JSON.stringify(state)); }} catch (e) {{}}
}}
function refresh() {{
  var marked = 0, bad = [];
  for (var id in state) {{
    marked++;
    if (state[id] === 'bad') bad.push(id);
  }}
  bad.sort(function (a, b) {{ return a - b; }});
  document.getElementById('progress').textContent =
    'размечено ' + marked + ' из ' + TOTAL + ', проблемных ' + bad.length;
  document.getElementById('badlist').value = bad.join(', ');
  document.querySelectorAll('.problem').forEach(function (card) {{
    var id = card.dataset.id;
    card.classList.toggle('ok', state[id] === 'ok');
    card.classList.toggle('bad', state[id] === 'bad');
    var bo = card.querySelector('.b-ok'), bb = card.querySelector('.b-bad');
    bo.classList.toggle('sel-ok', state[id] === 'ok');
    bb.classList.toggle('sel-bad', state[id] === 'bad');
  }});
}}
function vote(id, val) {{
  state[id] = (state[id] === val) ? undefined : val;
  if (state[id] === undefined) delete state[id];
  save();
  refresh();
}}
function copyBad() {{
  var t = document.getElementById('badlist');
  t.select();
  if (navigator.clipboard && navigator.clipboard.writeText) {{
    navigator.clipboard.writeText(t.value).catch(function () {{
      document.execCommand('copy');
    }});
  }} else {{
    document.execCommand('copy');
  }}
}}
document.addEventListener('DOMContentLoaded', refresh);
</script>
</body>
</html>
"""


def block(label, text, cls='text'):
    if not text:
        return ''
    return ('<div class="label">%s</div><div class="%s">%s</div>'
            % (label, cls, html.escape(text)))


class Command(BaseCommand):
    help = 'HTML для ручного отсмотра видимых задач с разметкой OK/Проблема'

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=200)
        parser.add_argument('--seed', type=int, default=20260613)
        parser.add_argument('--output', default=OUTPUT)
        parser.add_argument('--ids-file', default=None,
                            help='Файл со списком id задач (по одному на строку). '
                                 'Если задан — случайная выборка не делается, '
                                 'используются только эти id.')

    def handle(self, *args, **options):
        count = options['count']
        seed = options['seed']
        gen_date = '2026-06-13'
        os.makedirs(os.path.dirname(options['output']), exist_ok=True)

        # Режим явного списка id (--ids-file)
        if options['ids_file']:
            with open(options['ids_file']) as fh:
                explicit_ids = [int(s.strip()) for s in fh if s.strip().isdigit()]
            # группируем по источнику, сохраняя порядок из файла
            by_source = defaultdict(list)
            for pid, sid, sname in Problem.objects.filter(
                    id__in=explicit_ids).values_list(
                    'id', 'source_references__source__id',
                    'source_references__source__name'):
                by_source[(sid or 0, sname or 'Без источника')].append(pid)
            seen = set()
            picked = defaultdict(list)
            for key in by_source:
                for pid in by_source[key]:
                    if pid not in seen:
                        seen.add(pid)
                        picked[key].append(pid)
            order = sorted(picked.keys(), key=lambda k: k[0])
            total = sum(len(v) for v in picked.values())
        else:
            random.seed(seed)
            visible = Problem.objects.filter(status='published',
                                             needs_quality_review=False)
            by_source = defaultdict(list)
            for pid, sid, sname in visible.values_list(
                    'id', 'source_references__source__id',
                    'source_references__source__name'):
                by_source[(sid or 0, sname or 'Без источника')].append(pid)

            seen = set()
            for key in by_source:
                by_source[key] = [p for p in by_source[key]
                                  if not (p in seen or seen.add(p))]
            pools = {k: v for k, v in by_source.items() if v}
            for v in pools.values():
                random.shuffle(v)

            picked = defaultdict(list)
            order = sorted(pools.keys(), key=lambda k: k[0])
            total = 0
            while total < count:
                progress = False
                for key in order:
                    if total >= count:
                        break
                    if len(picked[key]) >= PER_SOURCE_CAP or not pools[key]:
                        continue
                    picked[key].append(pools[key].pop())
                    total += 1
                    progress = True
                if not progress:
                    break

        parts_html = [PAGE_HEAD.format(count=total, seed=seed, gen_date=gen_date)]
        for key in order:
            ids = picked.get(key)
            if not ids:
                continue
            sid, sname = key
            parts_html.append('<h2 class="source">#%s — %s (%d задач)</h2>'
                              % (sid or '—', html.escape(sname), len(ids)))
            for p in Problem.objects.filter(id__in=ids).prefetch_related('parts'):
                title = p.title or ('Задача #%d' % p.id)
                parts_html.append('<div class="problem" data-id="%d">' % p.id)
                parts_html.append(
                    '<div class="meta">#%d · %s · '
                    '<a href="http://127.0.0.1:8000/catalog/problem/%d/" '
                    'target="_blank">/catalog/problem/%d/</a>'
                    '<span class="vote">'
                    '<button class="b-ok" onclick="vote(\'%d\',\'ok\')">✅ ОК</button>'
                    '<button class="b-bad" onclick="vote(\'%d\',\'bad\')">❌ Проблема</button>'
                    '</span></div>'
                    % (p.id, html.escape(title[:80]), p.id, p.id, p.id, p.id))
                parts_html.append(block('Условие', p.statement))
                for part in p.parts.all().order_by('order', 'id'):
                    inner = ''
                    if part.statement:
                        inner += ('<div class="text">%s</div>'
                                  % html.escape(part.statement))
                    if part.answer:
                        inner += ('<div class="label">Ответ подпункта</div>'
                                  '<div class="text answer">%s</div>'
                                  % html.escape(part.answer))
                    plabel = (part.label or '?').rstrip(').．。 ') or '?'
                    parts_html.append(
                        '<div class="part"><span class="plabel">%s)</span> %s</div>'
                        % (html.escape(plabel), inner))
                parts_html.append(block('Ответ', p.answer, cls='text answer'))
                parts_html.append('</div>')
        parts_html.append(PAGE_TAIL.format(count=total, seed=seed,
                                           gen_date=gen_date))

        with open(options['output'], 'w') as fh:
            fh.write('\n'.join(parts_html))
        n_sources = sum(1 for k in picked if picked[k])
        self.stdout.write(self.style.SUCCESS(
            f'{options["output"]}: {total} задач из {n_sources} источников '
            f'(cap {PER_SOURCE_CAP}/источник, seed {seed})'))
