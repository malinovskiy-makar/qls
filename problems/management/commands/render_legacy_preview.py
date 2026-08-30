# -*- coding: utf-8 -*-
"""Страница визуальной проверки ПОСЛЕ боевого рендера (Фаза 2 брифа 29.08).

READ-ONLY. Чем отличается от `render_legacy_review_v2`: та страница
показывала пары «исходник → канонизированный текст» ДО записи. Эта
показывает то, что уже лежит в базе, ровно тем конвейером, каким его
покажет ученику `catalog/problem_detail.html`:

    problem.statement | render_markdown | render_figures

Тот же вызов, тот же санитайзер, тот же KaTeX 0.16.9 с той же
маскировкой `\\$` (`_HTML_HEAD`/`_HTML_FOOT_TEMPLATE` берутся из
`corpus_review_html`, а не пишутся заново — расхождение конвейеров
превратило бы проверку в фикцию).

Единственное намеренное отличие от боевой страницы: картинка
подставляется ВСТРОЕННЫМ `<svg>` из `ProblemFigure.svg`, а не ссылкой
`/problem-figure/<pk>.svg`. Иначе файл нельзя открыть без поднятого
сервера. Показывается тот же самый санитизированный SVG, что отдал бы
сайт.

Выборка честно случайная по всем задачам, которые изменила команда
`render_legacy_sources --apply` (список берётся из её журнала отката),
без стратификации по источникам: доля источника в выборке отражает его
реальную долю. Сид фиксирован и печатается.
"""
import base64
import json
import os
import random

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from problems.corpus_converter import render_codes as rc
from problems.corpus_converter.tikz_render import MARKER_RE
from problems.management.commands.corpus_review_html import (
    _HTML_FOOT_TEMPLATE, _esc, html_head,
)
from problems.models import Problem, ProblemFigure
from problems.rendering import render_markdown

DEFAULT_IDS = os.path.join(
    settings.BASE_DIR, 'reports', 'corpus_converter_scaleup',
    'render_legacy_sources_backup.json')
DEFAULT_OUT = os.path.join(
    settings.BASE_DIR, 'reports', 'corpus_converter_scaleup',
    'boevoi_render_applied_preview.html')


def _render_field(text, figures):
    """Боевой конвейер показа + встроенная картинка вместо ссылки.

    Отличие от сайта одно: там `<img src="/catalog/figure/N.svg">`, здесь
    содержимое вшито в файл — иначе страницу нельзя открыть без
    поднятого сервера. Показывается ровно то же, что отдал бы сайт.

    Два происхождения байтов, и оба надо вшить: собранные из TikZ лежат
    в `svg`, импортированные из архивов — в `image_data` (их 930, и без
    этой ветки на месте картинки был бы пустой абзац)."""
    html = render_markdown(text or '')
    if '[[FIGURE:' not in html:
        return html

    def repl(match):
        figure = figures.get(match.group(1))
        if figure is None:
            return ''
        if figure.svg:
            return f'<div class="problem-figure">{figure.svg}</div>'
        if figure.image_data:
            data = base64.b64encode(bytes(figure.image_data)).decode('ascii')
            return (f'<img class="problem-figure" alt="График к задаче" '
                    f'src="data:{figure.content_type};base64,{data}">')
        return ''

    return MARKER_RE.sub(repl, html)


def _card(problem, sources, figures):
    """Карточка задачи вместе с ЧЕСТНЫМ вердиктом о её читаемости.

    ⚠️ Раньше класс `no-warnings` стоял здесь строкой, безусловно. Аудит
    3 000 карточек отметил это первым пунктом глобальных дефектов: все
    3 000 были помечены «без замечаний», хотя 390 из них человек признал
    сломанными. Страница проверки, которая сама себе ставит зачёт,
    проверкой не является. Теперь коды считает
    `render_codes.analyze_problem` по ТОМУ ЖЕ HTML, что показан ниже."""
    blocks = [('Условие', problem.statement)]
    for part in problem.parts.all():
        blocks.append((f'Часть {part.label}', part.statement))
    if problem.answer:
        blocks.append(('Ответ', problem.answer))
    if problem.solution:
        blocks.append(('Решение', problem.solution))

    body = []
    htmls = []
    for name, text in blocks:
        html = _render_field(text, figures)
        htmls.append(html)
        body.append(
            f'<div class="block"><div class="block-name">{_esc(name)}</div>'
            f'<div class="math-content">{html}</div></div>'
        )

    found = rc.analyze_problem(
        [(name, '', text or '') for name, text in blocks], htmls,
        figure_svgs=[f.svg for f in figures.values() if f.svg])
    codes = sorted(found, key=lambda c: (rc.PRIORITY[c], c))
    worst = min((rc.PRIORITY[c] for c in codes), default='')
    state = 'has-warnings' if codes else 'no-warnings'
    chips = ''.join(
        f'<span class="badge warn" title="{_esc(rc.MEANING[c])}">'
        f'{_esc(c)}</span> ' for c in codes)

    return (
        f'<div class="sample-card {state}" data-id="{problem.id}" '
        f'data-has-warnings="{"true" if codes else "false"}" '
        f'data-priority="{worst}" data-codes="{_esc(",".join(codes))}" '
        f'data-reviewed="false">'
        f'<div class="sample-header">'
        f'<span class="sample-id">#{problem.id}</span> '
        f'<span class="sample-label">{_esc(sources)}</span> '
        f'<span class="badge">{_esc(problem.content_format)}</span> '
        f'{chips}'
        f'</div>{"".join(body)}</div>'
    )


class Command(BaseCommand):
    help = ('Страница визуальной проверки боевого рендера: случайная выборка '
            'из уже применённых задач, показанных боевым конвейером.')

    def add_arguments(self, parser):
        parser.add_argument('--ids-file', default=DEFAULT_IDS,
                            help='журнал отката render_legacy_sources')
        parser.add_argument('--sample', type=int, default=3000)
        parser.add_argument('--seed', type=int, default=20260829)
        parser.add_argument('--out', default=DEFAULT_OUT)

    def handle(self, *args, **options):
        ids_file = options['ids_file']
        if not os.path.exists(ids_file):
            raise CommandError(
                f'Нет файла со списком применённых задач: {ids_file}. '
                f'Сначала render_legacy_sources --apply.')
        with open(ids_file, encoding='utf-8') as f:
            applied = [row['problem_id'] for row in json.load(f)['problems']]

        rng = random.Random(options['seed'])
        size = min(options['sample'], len(applied))
        chosen = sorted(rng.sample(applied, size))

        problems = (Problem.objects.filter(id__in=chosen)
                    .prefetch_related('parts', 'source_references__source')
                    .order_by('id'))
        figures_by_problem = {}
        for figure in ProblemFigure.objects.filter(problem_id__in=chosen):
            figures_by_problem.setdefault(figure.problem_id, {})[
                figure.tikz_hash] = figure

        per_source = {}
        cards = []
        for problem in problems:
            names = sorted({ref.source.name
                            for ref in problem.source_references.all()})
            for name in names:
                per_source[name] = per_source.get(name, 0) + 1
            cards.append(_card(problem, '; '.join(names),
                               figures_by_problem.get(problem.id, {})))

        summary = ''.join(
            f'<li>{_esc(name)}: <b>{count}</b></li>'
            for name, count in sorted(per_source.items(),
                                      key=lambda kv: -kv[1]))
        head = (
            f'<h1>Боевой рендер легаси: что теперь лежит в базе</h1>'
            f'<p>Случайная выборка <b>{len(cards)}</b> задач из '
            f'<b>{len(applied)}</b> применённых. Сид <b>{options["seed"]}</b> '
            f'— выборка воспроизводима. Стратификации по источникам нет: '
            f'доля источника отражает его реальную долю.</p>'
            f'<p>Показано боевым конвейером '
            f'<code>render_markdown</code> + подстановка картинок, тем же '
            f'KaTeX 0.16.9, что и на сайте. Картинки встроены как '
            f'<code>&lt;svg&gt;</code>, чтобы файл открывался без сервера.</p>'
            f'<ul>{summary}</ul>'
            # Кнопки фильтра: JS подвала ищет `#filters button[data-filter]`,
            # но рисовать их было некому — аудит отметил это восьмым пунктом
            # («контроль качества фактически недоступен»).
            f'<div id="filters">'
            f'<button data-filter="all">все ({len(cards)})</button>'
            f'<button data-filter="warnings">только с кодами '
            f'({sum(1 for c in cards if "has-warnings" in c)})</button>'
            f'</div>'
        )

        os.makedirs(os.path.dirname(options['out']), exist_ok=True)
        with open(options['out'], 'w', encoding='utf-8') as f:
            f.write(html_head())
            f.write(head)
            f.write(''.join(cards))
            f.write(_HTML_FOOT_TEMPLATE)

        size_mb = os.path.getsize(options['out']) / (1024 * 1024)
        self.stdout.write(self.style.SUCCESS(
            f'Готово: {options["out"]} ({len(cards)} карточек, '
            f'{size_mb:.1f} МБ, сид {options["seed"]}).'))
        for name, count in sorted(per_source.items(), key=lambda kv: -kv[1]):
            self.stdout.write(f'  {name}: {count}')
