# -*- coding: utf-8 -*-
"""Фаза 2 брифа corpus-converter-render: страница визуальной проверки для
владельца — reports/corpus_converter_scaleup/boevoi_render_review.html.

READ-ONLY: ничего не создаётся и не изменяется в базе, `content_format`
не пишется. Это МАТЕРИАЛ для решения владельца, не само решение —
`render_legacy_sources` (Фаза 3) ничего не читает из этого файла.

Показывает только PASS-кандидатов боевого рендера (Фаза 1): тех же
`_candidate_qs`/`FORCED_EXCLUDE_RESHALKI_DOLLAR_SPLIT`, что и
`render_legacy_sources.py` — какой список задач получил бы
`content_format='markdown'`, ровно те и показываются здесь через
настоящий `render_markdown` (та же KaTeX-цепочка, что на проде).

Выборка на источник: 50 случайных (seed 20260826, тот же сид, что у
остальных corpus_* команд) плюс ОБЯЗАТЕЛЬНО все PASS-кандидаты, где в
сыром тексте (условие/ответ/решение/подпункты) встречается
`\\begin{cases}` — самое чувствительное место (кусочные функции), по
находке владельца при ревью 2026-08-26 (см. report.md)."""
import os
import random

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from problems.corpus_converter.core import convert_problem, may_render_as_markdown
from problems.corpus_converter.reshalki_dollar_exclusions import (
    FORCED_EXCLUDE_RESHALKI_DOLLAR_SPLIT,
)
from problems.management.commands.corpus_review_html import (
    _HTML_HEAD, _HTML_FOOT_TEMPLATE, _esc, _render_sample_card,
)
from problems.management.commands.render_legacy_sources import (
    SOURCES, EXCLUDED_SOURCE_NAME, _candidate_qs,
)
from problems.models import Problem, ProblemPart
from problems.rendering import render_markdown

SAMPLE_SIZE = 50
RANDOM_SEED = 20260826
CASES_MARKER = '\\begin{cases}'

OUT_PATH = os.path.join(
    settings.BASE_DIR, 'reports', 'corpus_converter_scaleup', 'boevoi_render_review.html',
)


def _has_cases(problem, existing_parts):
    fields = [problem.statement, problem.answer, problem.solution]
    fields += [text for _label, text in existing_parts]
    return any(CASES_MARKER in (text or '') for text in fields)


def _build_sample(problem, result, existing_parts):
    raw_sections = [('Условие', problem.statement)]
    if existing_parts:
        raw_sections.append((
            'Части (было)',
            '\n'.join(f'{label}) {text}' for label, text in existing_parts),
        ))
    if problem.answer:
        raw_sections.append(('Ответ', problem.answer))
    if problem.solution:
        raw_sections.append(('Решение', problem.solution))

    converted_sections = [('Условие', result['statement_md'])]
    for part in result['parts']:
        converted_sections.append((f"Часть {part['label']}", part['statement_md']))
    if result['answer_md']:
        converted_sections.append(('Ответ', result['answer_md']))
    if result['solution_md']:
        converted_sections.append(('Решение', result['solution_md']))

    return {
        'source_id': str(problem.id),
        'label': f'human_review={problem.human_review or "не смотрели"}',
        'raw_sections': raw_sections,
        'converted_sections': converted_sections,
        'images': result['images'],
        'warnings': list(result['warnings']),
        'complex_table': result['complex_table'],
    }


class Command(BaseCommand):
    help = (
        'Read-only: страница визуальной проверки PASS-кандидатов боевого рендера '
        '(reports/corpus_converter_scaleup/boevoi_render_review.html).'
    )

    def handle(self, *args, **options):
        counts_before = {
            'Problem': Problem.objects.count(),
            'ProblemPart': ProblemPart.objects.count(),
        }

        sections_html = []
        summary_rows = []
        total_pass = total_shown = total_cases_forced = 0

        for slug, (source_id, name) in SOURCES.items():
            qs = _candidate_qs(slug, source_id)
            if slug == 'reshalki':
                qs = qs.exclude(id__in=FORCED_EXCLUDE_RESHALKI_DOLLAR_SPLIT)

            pass_items = []
            for problem in qs.prefetch_related('parts').iterator(chunk_size=500):
                existing_parts = [(p.label, p.statement) for p in problem.parts.all()]
                result = convert_problem(
                    statement=problem.statement, answer=problem.answer,
                    solution=problem.solution, existing_parts=existing_parts,
                )
                if not (may_render_as_markdown(result) and not result['warnings']):
                    continue
                pass_items.append((problem, result, existing_parts))

            total_pass += len(pass_items)

            cases_items = [item for item in pass_items if _has_cases(item[0], item[2])]
            random.seed(RANDOM_SEED)
            random_items = (
                random.sample(pass_items, min(SAMPLE_SIZE, len(pass_items)))
                if pass_items else []
            )

            chosen = {}
            for item in random_items:
                chosen[item[0].id] = item
            forced_added = 0
            for item in cases_items:
                if item[0].id not in chosen:
                    forced_added += 1
                chosen[item[0].id] = item
            total_cases_forced += forced_added
            total_shown += len(chosen)

            ordered = sorted(chosen.values(), key=lambda item: item[0].id)
            samples = []
            for problem, result, existing_parts in ordered:
                s = _build_sample(problem, result, existing_parts)
                if _has_cases(problem, existing_parts):
                    s['label'] += ' · содержит \\begin{cases}'
                samples.append(s)

            warn_in_sample = sum(1 for s in samples if s['warnings'])
            summary_rows.append(
                f'<tr><td>{_esc(name)}</td><td>{len(pass_items)}</td>'
                f'<td>{len(samples)}</td><td>{len(cases_items)}</td></tr>'
            )
            sections_html.append(
                f'<details class="source-section" open data-source="{slug}"><summary>'
                f'{_esc(name)} — PASS {len(pass_items)}, показано {len(samples)} '
                f'(из них с \\begin{{cases}}: {len(cases_items)}), warnings в выборке: {warn_in_sample}'
                f'</summary>'
            )
            for s in samples:
                pid = s['source_id']
                link = f'/catalog/problem/{pid}/'
                sections_html.append(
                    f'<div style="margin:4px 0 -8px;font-size:0.85rem;">'
                    f'<a href="{_esc(link)}" target="_blank" rel="noopener">{_esc(link)}</a></div>'
                )
                sections_html.append(_render_sample_card(s, reviewed=False))
            sections_html.append('</details>')

            self.stdout.write(
                f'{name}: PASS={len(pass_items)} показано={len(samples)} '
                f'(cases-принудительно={len(cases_items)})'
            )

        html_parts = [_HTML_HEAD]
        html_parts.append('<h1>Боевой рендер легаси-источников — визуальная проверка</h1>')
        html_parts.append(
            '<div class="subtitle">Только PASS-кандидаты (пройдут may_render_as_markdown() '
            'и получили бы content_format=markdown при --apply). Рендер — '
            'problems.rendering.render_markdown + KaTeX 0.16.9, как на проде. '
            'Это МАТЕРИАЛ для решения владельца об одобрении, не само решение.</div>'
        )
        summary_html = (
            '<table class="summary"><tr><th>Источник</th><th>PASS всего</th>'
            '<th>Показано</th><th>из них \\begin{cases}</th></tr>'
            + ''.join(summary_rows)
            + f'<tr class="total"><td>Итого</td><td>{total_pass}</td>'
            f'<td>{total_shown}</td><td>{total_cases_forced}</td></tr></table>'
        )
        html_parts.append(summary_html)
        html_parts.append(
            '<div id="filters">'
            '<button data-filter="all" class="active">Показать все</button>'
            '<button data-filter="warnings">Только с warnings</button>'
            '</div>'
        )
        html_parts.extend(sections_html)
        html_parts.append(_HTML_FOOT_TEMPLATE)

        os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
        with open(OUT_PATH, 'w', encoding='utf-8') as f:
            f.write(''.join(html_parts))

        counts_after = {
            'Problem': Problem.objects.count(),
            'ProblemPart': ProblemPart.objects.count(),
        }
        if counts_before != counts_after:
            raise CommandError(f'ИНВАРИАНТ НАРУШЕН: было {counts_before}, стало {counts_after}')

        self.stdout.write(self.style.SUCCESS(
            f'Готово. PASS всего: {total_pass}. Показано: {total_shown} '
            f'(из них принудительно по \\begin{{cases}}: {total_cases_forced}). '
            f'Инвариант счётчиков сошёлся. Файл: {OUT_PATH}'
        ))
