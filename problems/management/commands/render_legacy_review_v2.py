# -*- coding: utf-8 -*-
"""Страница визуальной проверки по НОВОМУ шлюзу — вторая половина Фазы 8.

READ-ONLY. Отличия от прежней `render_legacy_review_html`:

* PASS определяет `render_preflight_v2` (настоящий KaTeX), а не
  `may_render_as_markdown()`;
* показывается КАНОНИЗИРОВАННЫЙ текст (Фазы 4/5/1) — ровно то, что
  увидел бы ученик после `--apply`, а не выход стадии 1;
* отдельным блоком идут ЗАБЛОКИРОВАННЫЕ карточки с машинными кодами
  причин: владельцу нужно видеть не только «что пройдёт», но и «что
  отсеялось и почему».

Прежний файл `boevoi_render_review.html` не перезаписывается — он нужен
для сравнения «до/после» с аудитом. Новый: `boevoi_render_review_v2.html`.
"""
import os
import random

os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', '1')

from django.conf import settings  # noqa: E402
from django.core.management.base import BaseCommand, CommandError  # noqa: E402

from problems.corpus_converter.katex_preflight import KatexPreflight  # noqa: E402
from problems.corpus_converter.preflight_gate import (  # noqa: E402
    build_blocks, convert_problem_v2, render_preflight_v2,
)
from problems.management.commands.corpus_render_gate import (  # noqa: E402
    SOURCES, _candidate_qs,
)
from problems.management.commands.corpus_review_html import (  # noqa: E402
    _HTML_FOOT_TEMPLATE, _esc, _render_sample_card, html_head,
)
from problems.models import Problem, ProblemPart  # noqa: E402

SAMPLE_SIZE = 50
BLOCKED_SHOWN = 25
RANDOM_SEED = 20260826
CASES_MARKER = '\\begin{cases}'
OUT_PATH = os.path.join(settings.BASE_DIR, 'reports', 'corpus_converter_scaleup',
                        'boevoi_render_review_v2.html')


def _has_cases(problem, raw_parts):
    fields = [problem.statement, problem.answer, problem.solution]
    fields += [t for _l, t in raw_parts]
    return any(CASES_MARKER in (t or '') for t in fields)


def _sample(problem, result, raw_parts, verdict):
    raw_sections = [('Условие', problem.statement)]
    if raw_parts:
        raw_sections.append(('Части (было)', '\n'.join(
            f'{label}) {text}' for label, text in raw_parts)))
    if problem.answer:
        raw_sections.append(('Ответ', problem.answer))
    if problem.solution:
        raw_sections.append(('Решение', problem.solution))

    converted = [('Условие', result['statement_md'])]
    for part in result['parts']:
        converted.append((f"Часть {part['label']}", part['statement_md']))
    if result['answer_md']:
        converted.append(('Ответ', result['answer_md']))
    if result['solution_md']:
        converted.append(('Решение', result['solution_md']))

    label = f'human_review={problem.human_review or "не смотрели"}'
    if _has_cases(problem, raw_parts):
        label += ' · \\begin{cases}'
    return {
        'source_id': str(problem.id), 'label': label,
        'raw_sections': raw_sections, 'converted_sections': converted,
        'images': result['images'],
        'warnings': verdict.details if not verdict.ok else [],
        'complex_table': not verdict.ok,
    }


class Command(BaseCommand):
    help = ('Read-only: страница визуальной проверки по новому шлюзу '
            '(reports/corpus_converter_scaleup/boevoi_render_review_v2.html).')

    def handle(self, *args, **options):
        before = (Problem.objects.count(), ProblemPart.objects.count())
        sections, summary_rows = [], []
        totals = {'pass': 0, 'fail': 0, 'shown': 0, 'cases': 0}

        with KatexPreflight() as checker:
            for slug, (source_id, name) in SOURCES.items():
                passed, blocked = [], []
                for problem in _candidate_qs(slug, source_id).prefetch_related(
                        'parts').iterator(chunk_size=200):
                    raw_parts = [(p.label, p.statement) for p in problem.parts.all()]
                    result = convert_problem_v2(
                        statement=problem.statement, answer=problem.answer,
                        solution=problem.solution, existing_parts=raw_parts)
                    blocks = build_blocks(problem.statement, raw_parts,
                                          problem.answer, problem.solution, result)
                    verdict = render_preflight_v2(
                        blocks, checker, raw_statement=problem.statement)
                    (passed if verdict.ok else blocked).append(
                        (problem, result, raw_parts, verdict))

                totals['pass'] += len(passed)
                totals['fail'] += len(blocked)
                cases_items = [it for it in passed if _has_cases(it[0], it[2])]
                random.seed(RANDOM_SEED)
                chosen = {}
                for it in (random.sample(passed, min(SAMPLE_SIZE, len(passed)))
                           if passed else []):
                    chosen[it[0].id] = it
                for it in cases_items:
                    chosen[it[0].id] = it
                totals['shown'] += len(chosen)
                totals['cases'] += len(cases_items)

                summary_rows.append(
                    f'<tr><td>{_esc(name)}</td><td>{len(passed)}</td>'
                    f'<td>{len(blocked)}</td><td>{len(chosen)}</td>'
                    f'<td>{len(cases_items)}</td></tr>')

                sections.append(
                    f'<details class="source-section" open><summary>{_esc(name)} — '
                    f'PASS {len(passed)}, заблокировано {len(blocked)}, '
                    f'показано {len(chosen)} (с \\begin{{cases}}: {len(cases_items)})'
                    f'</summary>')
                for item in sorted(chosen.values(), key=lambda x: x[0].id):
                    link = f'/catalog/problem/{item[0].id}/'
                    sections.append(
                        f'<div style="margin:4px 0 -8px;font-size:.85rem;">'
                        f'<a href="{_esc(link)}" target="_blank" rel="noopener">'
                        f'{_esc(link)}</a></div>')
                    sections.append(_render_sample_card(_sample(*item), reviewed=False))
                sections.append('</details>')

                if blocked:
                    sections.append(
                        f'<details class="source-section"><summary>⛔ {_esc(name)} — '
                        f'ЗАБЛОКИРОВАНО шлюзом: {len(blocked)} '
                        f'(показаны первые {min(BLOCKED_SHOWN, len(blocked))})</summary>')
                    for item in blocked[:BLOCKED_SHOWN]:
                        sections.append(_render_sample_card(_sample(*item), reviewed=True))
                    sections.append('</details>')

                self.stdout.write(f'  {name}: PASS {len(passed)}, блок {len(blocked)}')

        html = [html_head(),
                '<h1>Боевой рендер — визуальная проверка по НОВОМУ шлюзу (v2)</h1>',
                '<div class="subtitle">PASS определяет render_preflight_v2 — '
                'настоящий KaTeX 0.16.9 (throwOnError=true, trust=false), а не '
                'текстовые признаки. Показан КАНОНИЗИРОВАННЫЙ текст: ровно то, '
                'что увидит ученик после --apply. Отдельным блоком — что шлюз '
                'отсеял и почему.</div>',
                '<table class="summary"><tr><th>Источник</th><th>PASS</th>'
                '<th>Заблокировано</th><th>Показано</th><th>с cases</th></tr>'
                + ''.join(summary_rows)
                + f'<tr class="total"><td>Итого</td><td>{totals["pass"]}</td>'
                f'<td>{totals["fail"]}</td><td>{totals["shown"]}</td>'
                f'<td>{totals["cases"]}</td></tr></table>',
                '<div id="filters"><button data-filter="all" class="active">'
                'Показать все</button><button data-filter="warnings">'
                'Только с причинами блокировки</button></div>']
        html += sections
        html.append(_HTML_FOOT_TEMPLATE)

        os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
        with open(OUT_PATH, 'w', encoding='utf-8') as f:
            f.write(''.join(html))

        if (Problem.objects.count(), ProblemPart.objects.count()) != before:
            raise CommandError('ИНВАРИАНТ НАРУШЕН: счётчики изменились')
        self.stdout.write(self.style.SUCCESS(
            f'Готово. PASS {totals["pass"]}, заблокировано {totals["fail"]}, '
            f'показано {totals["shown"]}. Файл: {OUT_PATH}'))
