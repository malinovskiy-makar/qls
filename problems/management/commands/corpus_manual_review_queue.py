# -*- coding: utf-8 -*-
"""Фаза 2 сессии 2026-08-27: собрать ФИНАЛЬНЫЙ список задач, которые
конвертер разобрать не смог и которые пойдут на ручной разбор — всё, у
чего `complex_table=True` (multicolumn/multirow, сломанный
`\\begin{cases}`, голые `&`-строки без обёртки).

READ-ONLY, как остальные corpus_*-команды: ни один Problem/ProblemPart
не изменяется, инвариант count() проверяется кодом. Автоматической
правки здесь нет и не должно быть — смысл файла ровно в том, что эти
задачи чинит человек."""
import os
import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from problems.corpus_converter.core import convert_problem
from problems.models import Problem, ProblemPart

#: те же четыре легаси-источника, что у corpus_scaleup_legacy.
SOURCES = {
    'archive3': (14, 'Overleaf Archive 3 (ОШ/ЛШ Олмат)'),
    'matek': (13, 'МатЭк — Overleaf архивы (2021–2025)'),
    'lsh2025': (3, 'ЛШ Олмат 2025 (Overleaf)'),
    'reshalki': (16, 'Решалки Олмат (olmat41)'),
}
EXCLUDED_SOURCE_NAME = 'Служебное: фикстуры рендерера (не публиковать)'

#: что показать в файле как «сырой фрагмент» — кусок вокруг первого
#: проблемного места, чтобы ревьюер сразу видел, о чём речь.
_TRIGGERS = (
    ('\\begin{cases}', 'сломанный \\begin{cases}'),
    ('\\multicolumn', 'multicolumn'),
    ('\\multirow', 'multirow'),
    ('\\begin{tabular}', 'таблица'),
)
FRAGMENT_CHARS = 320


def _fragment(problem):
    """Короткий кусок сырого текста вокруг первого подозрительного места."""
    fields = [('условие', problem.statement), ('ответ', problem.answer),
              ('решение', problem.solution)]
    fields += [(f'подпункт «{p.label}»', p.statement) for p in problem.parts.all()]
    for field_name, text in fields:
        if not text:
            continue
        for marker, _ in _TRIGGERS:
            pos = text.find(marker)
            if pos >= 0:
                start = max(0, pos - 60)
                return field_name, text[start:start + FRAGMENT_CHARS]
    # ни одного маркера — показываем начало условия, чтобы строка не была пустой
    return 'условие', (problem.statement or '')[:FRAGMENT_CHARS]


def _reasons(warnings):
    """Свернуть предупреждения задачи в короткий список причин без
    повторов — у задачи с четырьмя сломанными cases причина одна."""
    seen = []
    for warning in warnings:
        short = warning.split(' — в очередь')[0].strip()
        if short not in seen:
            seen.append(short)
    return seen


class Command(BaseCommand):
    help = (
        'Фаза 2 (read-only): собрать очередь ручного разбора — все задачи '
        'четырёх легаси-источников с complex_table=True — в '
        'reports/corpus_converter_scaleup/manual_review_queue.md'
    )

    def handle(self, *args, **options):
        problems_before = Problem.objects.count()
        parts_before = ProblemPart.objects.count()

        rows = []
        totals = {}
        for slug, (source_id, source_name) in SOURCES.items():
            qs = (
                Problem.objects.filter(source_references__source_id=source_id)
                .exclude(source_references__source__name=EXCLUDED_SOURCE_NAME)
                .distinct()
                .prefetch_related('parts')
            )
            seen = flagged = 0
            for problem in qs.iterator(chunk_size=500):
                seen += 1
                result = convert_problem(
                    statement=problem.statement,
                    answer=problem.answer,
                    solution=problem.solution,
                    existing_parts=[(p.label, p.statement) for p in problem.parts.all()],
                )
                if not result['complex_table']:
                    continue
                flagged += 1
                field_name, fragment = _fragment(problem)
                rows.append({
                    'id': problem.id,
                    'source': source_name,
                    'field': field_name,
                    'fragment': fragment,
                    'reasons': _reasons(result['warnings']),
                })
            totals[source_name] = (seen, flagged)
            self.stdout.write(f'{source_name}: {flagged} из {seen}')

        out_dir = os.path.join(settings.BASE_DIR, 'reports', 'corpus_converter_scaleup')
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, 'manual_review_queue.md')
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(_render(rows, totals))

        problems_after = Problem.objects.count()
        parts_after = ProblemPart.objects.count()
        if (problems_before, parts_before) != (problems_after, parts_after):
            raise CommandError(
                'ИНВАРИАНТ НАРУШЕН: было '
                f'Problem={problems_before}/ProblemPart={parts_before}, стало '
                f'Problem={problems_after}/ProblemPart={parts_after}'
            )

        self.stdout.write(self.style.SUCCESS(
            f'Готово. В очереди {len(rows)} задач, инвариант count() сошёлся '
            f'(Problem={problems_before}, ProblemPart={parts_before}). Файл: {out_path}'
        ))


def _render(rows, totals):
    """Собрать markdown-файл очереди."""
    lines = [
        '# Очередь ручного разбора — задачи, которые конвертер разобрать не смог',
        '',
        'Собрано командой `corpus_manual_review_queue` (только чтение).',
        'Сюда попадает всё, у чего `complex_table=True`: сложные таблицы',
        '(`\\multicolumn`/`\\multirow`), сломанные `\\begin{cases}`, голые',
        '`&`-строки без обёртки. **Автоматической правки по этому списку нет',
        'и быть не должно** — эти задачи чинит человек.',
        '',
        'Боевой рендер такие задачи пропустить не сможет: решение принимает',
        '`problems.corpus_converter.core.may_render_as_markdown()` — одна точка,',
        'покрытая тестом, а не проверка флага руками в команде рендера.',
        '',
        '## Сводка',
        '',
        '| Источник | Задач в источнике | В очередь |',
        '|---|---:|---:|',
    ]
    for source_name, (seen, flagged) in totals.items():
        lines.append(f'| {source_name} | {seen} | {flagged} |')
    lines += [
        f'| **Итого** | **{sum(s for s, _ in totals.values())}** '
        f'| **{sum(f for _, f in totals.values())}** |',
        '',
        '## Задачи',
        '',
    ]
    for row in sorted(rows, key=lambda r: r['id']):
        lines += [
            f'### #{row["id"]} — {row["source"]}',
            '',
            'Причина: ' + ('; '.join(row['reasons']) or 'сложная таблица'),
            '',
            f'Сырой фрагмент ({row["field"]}):',
            '',
            '```latex',
            row['fragment'],
            '```',
            '',
        ]
    return '\n'.join(lines) + '\n'
