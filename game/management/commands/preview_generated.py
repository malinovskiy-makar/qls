"""
preview_generated — HTML-превью сгенерированных вопросов для проверки глазами.

По каждому архетипу генерирует --per примеров КАЖДОГО типа (numeric, single,
boolean) и складывает в reports/generators/preview.html: условие (KaTeX),
варианты с пометкой правильного, ответ, пошаговое решение, сложность,
обёртка, generator_key. Оглавление по блокам. В базу ничего не пишется.

Запуск: ./venv/bin/python manage.py preview_generated --per 10 [--seed S]
"""
import html
import os
import random

from django.core.management.base import BaseCommand

from game.generators.base import generate_batch
from game.generators.registry import ARCHETYPES

OUT_PATH = 'reports/generators/preview.html'
QUESTION_TYPES = ('numeric', 'single', 'boolean')
TYPE_TITLES = {'numeric': u'Числовой (Классика)',
               'single': u'Один из вариантов (Блиц)',
               'boolean': u'Данетка (Пуля)'}

PAGE_HEAD = u"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Превью генераторов Econ Rush</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"
        onload="renderMathInElement(document.body,
        {delimiters: [{left: '$$', right: '$$', display: true},
                      {left: '$', right: '$', display: false}]});"></script>
<style>
 body { font-family: -apple-system, 'Segoe UI', sans-serif; margin: 24px;
        max-width: 980px; color: #1a1a1a; }
 h1 { font-size: 22px; }
 h2 { font-size: 18px; margin-top: 40px; border-bottom: 2px solid #BE185D;
      padding-bottom: 4px; }
 h3 { font-size: 15px; margin-top: 24px; color: #444; }
 .toc { background: #f6f6f8; padding: 12px 18px; border-radius: 8px; }
 .toc a { color: #BE185D; text-decoration: none; }
 .card { border: 1px solid #ddd; border-radius: 8px; padding: 12px 16px;
         margin: 10px 0; }
 .meta { font-size: 11px; color: #777; margin-bottom: 6px; }
 .meta code { background: #f2f2f4; padding: 1px 5px; border-radius: 4px; }
 .stmt { font-size: 14.5px; line-height: 1.5; }
 .opts { margin: 8px 0 0 0; padding-left: 20px; font-size: 13.5px; }
 .opts li.ok { color: #1d7e45; font-weight: 600; }
 .opts li.ok::after { content: ' ✓'; }
 .ans { margin-top: 6px; font-size: 13px; }
 .ans b { color: #1d7e45; }
 .sol { margin-top: 8px; padding: 8px 12px; background: #f9f6f7;
        border-left: 3px solid #BE185D; font-size: 13px;
        white-space: pre-line; }
 .sol-label { font-size: 11px; color: #999; text-transform: uppercase;
              letter-spacing: .05em; }
 .diff { color: #b26b00; }
</style>
</head>
<body>
"""


class Command(BaseCommand):
    help = 'Строит HTML-превью сгенерированных вопросов (без записи в базу).'

    def add_arguments(self, parser):
        parser.add_argument('--per', type=int, default=10,
                            help='Примеров каждого типа на архетип')
        parser.add_argument('--seed', type=int, default=20260715,
                            help='Зерно генератора')

    def handle(self, *args, **options):
        per = options['per']
        rng = random.Random(options['seed'])

        # Архетипы группируются по блокам в порядке реестра.
        blocks = []
        for key, arch in ARCHETYPES.items():
            if not blocks or blocks[-1][0] != arch.block:
                blocks.append((arch.block, []))
            blocks[-1][1].append(arch)

        parts = [PAGE_HEAD]
        parts.append(u'<h1>Превью генераторов Econ Rush</h1>')
        parts.append(u'<p>По {} примеров каждого типа на архетип; правильный '
                     u'вариант отмечен ✓. В базу ничего не записано — превью '
                     u'генерирует свежие вопросы (seed {}).</p>'.format(
                         per, options['seed']))

        parts.append(u'<div class="toc"><b>Оглавление</b><ul>')
        for block, archs in blocks:
            parts.append(u'<li>{}<ul>'.format(html.escape(block)))
            for arch in archs:
                parts.append(u'<li><a href="#{}">{} — {}</a></li>'.format(
                    arch.key, arch.key, html.escape(arch.title)))
            parts.append(u'</ul></li>')
        parts.append(u'</ul></div>')

        total = 0
        for block, archs in blocks:
            parts.append(u'<h2>{}</h2>'.format(html.escape(block)))
            for arch in archs:
                parts.append(u'<h2 id="{}">{} — {}</h2>'.format(
                    arch.key, arch.key, html.escape(arch.title)))
                parts.append(u'<p class="meta">Темы: {}</p>'.format(
                    html.escape(', '.join(arch.topics))))
                for qtype in QUESTION_TYPES:
                    parts.append(u'<h3>{}</h3>'.format(TYPE_TITLES[qtype]))
                    for q in generate_batch(arch, rng, qtype, per):
                        total += 1
                        parts.append(self._card(q))

        parts.append(u'<p class="meta">Всего примеров: {}</p>'.format(total))
        parts.append(u'</body></html>')

        os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
        with open(OUT_PATH, 'w') as f:
            f.write('\n'.join(parts))
        self.stdout.write(self.style.SUCCESS(
            'Превью: {} ({} примеров)'.format(OUT_PATH, total)))

    def _card(self, q):
        rows = [u'<div class="card">']
        rows.append(
            u'<div class="meta"><code>{}</code> · сложность '
            u'<span class="diff">{}</span> · обёртка <code>{}</code> · '
            u'вопрос о <code>{}</code></div>'.format(
                q['generator_key'], q['difficulty'],
                q['params'].get('_wrapper', ''),
                q['params'].get('_asked', '')))
        rows.append(u'<div class="stmt">{}</div>'.format(
            html.escape(q['statement'])))
        if q['options']:
            rows.append(u'<ol class="opts">')
            for i, o in enumerate(q['options']):
                cls = ' class="ok"' if i == q['correct_index'] else ''
                rows.append(u'<li{}>{}</li>'.format(cls, html.escape(o)))
            rows.append(u'</ol>')
        if q['question_type'] == 'numeric':
            unit = u' {}'.format(q['unit']) if q['unit'] else ''
            rows.append(u'<div class="ans">Ответ: <b>{}</b>{}</div>'.format(
                html.escape(q['correct_value']), html.escape(unit)))
        rows.append(u'<div class="sol"><span class="sol-label">Решение'
                    u'</span><br>{}</div>'.format(
                        html.escape(q['solution_text'])))
        rows.append(u'</div>')
        return '\n'.join(rows)
