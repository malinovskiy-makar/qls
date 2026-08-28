# -*- coding: utf-8 -*-
"""Страница визуальной проверки картинок (Фаза B).

READ-ONLY. Собирает `reports/corpus_converter_scaleup/figures_preview.html`
из задач, у которых есть `ProblemFigure`: слева исходный TikZ, справа —
результат ТОЙ ЖЕ цепочки показа, что на боевой странице задачи:

    render_markdown(...)  ->  render_figures(..., problem)

⚠️ Почему нельзя просто открыть страницу задачи. Маркер `[[FIGURE:...]]`
живёт в КАНОНИЗИРОВАННОМ тексте, который появится в базе только после
`--apply`. Сейчас в `Problem.statement` лежит сырой TikZ, поэтому
предпросмотр строится по выходу `convert_problem_v2` — ровно по тому
тексту, который туда и будет записан.

SVG вставляется в файл как `data:`-URI, чтобы страницу можно было
открыть без запущенного сервера. На боевой странице `src` ведёт на
`/catalog/figure/<pk>.svg` — путь один и тот же, отличается только
способ доставки байтов для офлайнового просмотра.
"""
import base64
import html as html_module
import os
import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from problems.corpus_converter.preflight_gate import convert_problem_v2
from problems.figures import render_figures
from problems.models import Problem, ProblemFigure
from problems.rendering import render_markdown

OUT_PATH = os.path.join(settings.BASE_DIR, 'reports', 'corpus_converter_scaleup',
                        'figures_preview.html')
_SRC_RE = re.compile(r'src="(/catalog/figure/(\d+)\.svg)"')


def _esc(text):
    return html_module.escape(text or '', quote=False)


class Command(BaseCommand):
    help = 'Read-only: страница визуальной проверки сгенерированных картинок.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=40)

    def handle(self, *args, **options):
        problem_ids = list(
            ProblemFigure.objects.values_list('problem_id', flat=True).distinct()
        )[:options['limit']]
        if not problem_ids:
            raise CommandError('Нет ни одной ProblemFigure — сначала '
                               'corpus_build_figures --apply')

        svg_by_pk = {f.pk: f.svg for f in
                     ProblemFigure.objects.filter(problem_id__in=problem_ids)}

        def inline(match):
            """`/catalog/figure/<pk>.svg` -> data:-URI для офлайн-просмотра."""
            svg = svg_by_pk.get(int(match.group(2)), '')
            encoded = base64.b64encode(svg.encode('utf-8')).decode('ascii')
            return 'src="data:image/svg+xml;base64,' + encoded + '"'

        cards, total_imgs = [], 0
        for problem in (Problem.objects.filter(id__in=problem_ids)
                        .prefetch_related('parts', 'figures')):
            raw_parts = [(p.label, p.statement) for p in problem.parts.all()]
            result = convert_problem_v2(
                statement=problem.statement, answer=problem.answer,
                solution=problem.solution, existing_parts=raw_parts)

            sections = []
            for title, text in (('Условие', result['statement_md']),
                                ('Ответ', result['answer_md']),
                                ('Решение', result['solution_md'])):
                if not text:
                    continue
                # ТА ЖЕ цепочка, что в шаблоне задачи.
                shown = render_figures(render_markdown(text), problem)
                total_imgs += len(re.findall(r'<img', shown))
                sections.append(f'<h4>{_esc(title)}</h4>'
                                + _SRC_RE.sub(inline, shown))

            sources = ''.join(
                f'<pre>{_esc(f.tikz_source[:600])}</pre>'
                for f in problem.figures.all())
            cards.append(
                f'<div class="card"><div class="hd">#{problem.id} — '
                f'картинок: {problem.figures.count()}</div>'
                f'<div class="body"><div class="col"><h4>Исходный TikZ</h4>'
                f'{sources}</div><div class="col">{"".join(sections)}</div>'
                f'</div></div>')

        page = (
            '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            '<title>Картинки TikZ — визуальная проверка</title><style>'
            'body{font-family:Segoe UI,Arial,sans-serif;background:#f7f7f5;'
            'margin:0;padding:20px;color:#1a1a1a}'
            '.card{background:#fff;border:1px solid #ddd;border-radius:6px;'
            'margin-bottom:14px;padding:10px 14px}'
            '.hd{font-weight:700;margin-bottom:6px}'
            '.body{display:grid;grid-template-columns:1fr 1fr;gap:14px}'
            'pre{white-space:pre-wrap;word-break:break-word;font-size:.78rem;'
            'background:#fafafa;border:1px solid #eee;padding:8px;max-height:320px;'
            'overflow:auto}'
            'h4{margin:6px 0 4px;font-size:.8rem;text-transform:uppercase;color:#888}'
            'img.problem-figure{max-width:100%;height:auto;background:#fff;'
            'border:1px solid #eee;padding:4px}'
            '</style></head><body>'
            '<h1>Картинки TikZ — визуальная проверка</h1>'
            f'<p>Задач: {len(cards)}. Тегов &lt;img&gt; на странице: {total_imgs}. '
            'Справа — результат боевой цепочки '
            '<code>render_markdown → render_figures</code>.</p>'
            + ''.join(cards) + '</body></html>')

        os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
        with open(OUT_PATH, 'w', encoding='utf-8') as f:
            f.write(page)
        self.stdout.write(self.style.SUCCESS(
            f'Готово. Задач: {len(cards)}, тегов <img>: {total_imgs}. '
            f'Файл: {OUT_PATH}'))
