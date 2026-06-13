"""
Генерирует автономную HTML-страницу предпросмотра задач, изменённых в сессии
чистки текстов: по 10 случайных задач с каждого затронутого источника
(id берутся из reports/formula_cleanup/changed_ids.txt).

KaTeX подключается с CDN (jsdelivr), формулы рендерятся в браузере.
Для каждой задачи: id, источник, ссылка на /catalog/problem/<id>/,
statement / answer / solution / подпункты.

Запуск:
    ./venv/bin/python manage.py export_cleanup_preview
Результат: reports/formula_cleanup/preview.html
"""

import html
import os
import random

from django.core.management.base import BaseCommand

from problems.models import Problem

CHANGED_IDS_FILE = 'reports/formula_cleanup/changed_ids.txt'
OUTPUT_FILE = 'reports/formula_cleanup/preview.html'
PER_SOURCE = 10

PAGE_HEAD = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Превью чистки текстов задач</title>
<link rel="stylesheet"
  href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script defer
  src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<script defer
  src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"
  onload="renderMathInElement(document.body, {delimiters: [
    {left: '$$', right: '$$', display: true},
    {left: '$', right: '$', display: false},
    {left: '\\\\[', right: '\\\\]', display: true},
    {left: '\\\\(', right: '\\\\)', display: false}
  ], throwOnError: false});"></script>
<style>
  body { font-family: -apple-system, 'Segoe UI', sans-serif; margin: 0;
         background: #f7f7f5; color: #1a1f2e; }
  header { background: #1a1f2e; color: #fff; padding: 16px 28px; }
  header h1 { margin: 0; font-size: 20px; }
  main { max-width: 960px; margin: 0 auto; padding: 24px; }
  h2.source { margin-top: 36px; border-bottom: 2px solid #4f7cff;
              padding-bottom: 6px; font-size: 18px; }
  .problem { background: #fff; border: 1px solid #e8e8e4; border-radius: 10px;
             padding: 16px 20px; margin: 14px 0; }
  .problem .meta { font-size: 13px; color: #777; margin-bottom: 8px; }
  .problem .meta a { color: #4f7cff; text-decoration: none; }
  .label { font-weight: 600; font-size: 13px; color: #4f7cff;
           margin: 10px 0 4px; text-transform: uppercase; }
  .text { white-space: pre-wrap; line-height: 1.5; font-size: 15px; }
  .part { border-left: 3px solid #e8e8e4; padding-left: 12px; margin: 8px 0; }
  .part .plabel { font-weight: 600; }
</style>
</head>
<body>
<header><h1>Превью чистки текстов — изменённые задачи по источникам</h1></header>
<main>
"""


def block(label, text):
    if not text:
        return ''
    return (f'<div class="label">{label}</div>'
            f'<div class="text">{html.escape(text)}</div>')


class Command(BaseCommand):
    help = 'HTML-превью (KaTeX) изменённых в сессии чистки задач'

    def add_arguments(self, parser):
        parser.add_argument('--ids-file', default=CHANGED_IDS_FILE,
                            help='Файл со списком id изменённых задач')
        parser.add_argument('--out', default=OUTPUT_FILE,
                            help='Куда писать HTML')
        parser.add_argument('--per-source', default='',
                            help='Особые квоты вида "2:20,15:15" (sid:количество)')
        parser.add_argument('--must-ids', default='',
                            help='id задач, которые включить обязательно (через запятую)')

    def handle(self, *args, **options):
        ids_file = options['ids_file']
        out_file = options['out']
        quotas = {}
        if options['per_source']:
            for pair in options['per_source'].split(','):
                sid, n = pair.split(':')
                quotas[int(sid)] = int(n)

        if not os.path.exists(ids_file):
            self.stderr.write(f'Нет файла {ids_file}')
            return
        with open(ids_file, encoding='utf-8') as f:
            ids = [int(ln) for ln in f if ln.strip()]

        # группируем изменённые задачи по источникам
        by_source = {}
        problems = (Problem.objects.filter(id__in=ids)
                    .prefetch_related('parts', 'source_references__source'))
        for p in problems:
            refs = list(p.source_references.all())
            sname = refs[0].source.name if refs else 'Без источника'
            sid = refs[0].source.id if refs else 0
            by_source.setdefault((sid, sname), []).append(p)

        rng = random.Random(42)
        parts_html = [PAGE_HEAD]
        total = 0
        must_ids = {int(x) for x in options['must_ids'].split(',') if x.strip()}
        for (sid, sname), probs in sorted(by_source.items()):
            quota = quotas.get(sid, PER_SOURCE)
            forced = [p for p in probs if p.id in must_ids]
            rest = [p for p in probs if p.id not in must_ids]
            n_rest = max(0, quota - len(forced))
            sample = forced + (rng.sample(rest, n_rest)
                               if len(rest) > n_rest else rest)
            parts_html.append(
                f'<h2 class="source">#{sid} — {html.escape(sname)} '
                f'(изменено задач: {len(probs)}, показано: {len(sample)})</h2>')
            for p in sorted(sample, key=lambda x: x.id):
                total += 1
                title = html.escape(p.title or f'Задача #{p.id}')
                parts_html.append('<div class="problem">')
                parts_html.append(
                    f'<div class="meta">Задача <b>#{p.id}</b> — {title} — '
                    f'<a href="http://127.0.0.1:8000/catalog/problem/{p.id}/">'
                    f'открыть в каталоге</a></div>')
                parts_html.append(block('Условие', p.statement))
                pparts = list(p.parts.all())
                if pparts:
                    parts_html.append('<div class="label">Подпункты</div>')
                    for part in pparts:
                        parts_html.append('<div class="part">')
                        parts_html.append(
                            f'<span class="plabel">{html.escape(part.label)})</span>'
                            f'<div class="text">{html.escape(part.statement or "")}</div>')
                        if part.answer:
                            parts_html.append(
                                f'<div class="text"><i>Ответ:</i> '
                                f'{html.escape(part.answer)}</div>')
                        parts_html.append('</div>')
                parts_html.append(block('Ответ', p.answer))
                parts_html.append(block('Решение', p.solution))
                parts_html.append('</div>')

        parts_html.append('</main></body></html>')
        with open(out_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(parts_html))

        self.stdout.write(self.style.SUCCESS(
            f'Готово: {out_file} — {total} задач из {len(by_source)} источников.'))
