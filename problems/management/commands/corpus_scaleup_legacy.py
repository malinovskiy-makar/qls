# -*- coding: utf-8 -*-
"""Фаза 1 брифа corpus-converter-scaleup: путь UPDATE на легаси-семейство
(Overleaf Archive 3, МатЭк, ЛШ Олмат 2025, Решалки Олмат) — общий конвейер
по атласу (CORPUS_FORMAT_ATLAS_20260825.md), один конвертер на все четыре.

READ-ONLY, как corpus_pilot_ile.py. Ни один Problem/ProblemPart не
изменяется — только чтение и генерация reports/corpus_converter_scaleup/
<slug>_report.md."""
import os
import random

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from problems.corpus_converter.core import convert_problem
from problems.corpus_converter.report import render_entry, render_report
from problems.models import Problem

SAMPLE_SIZE = 40
MIN_APPROVED = 20
MIN_WITH_STRUCTURE = 14

#: source_id -> (человекочитаемое имя для отчёта, слаг для имени файла).
#: Источники CLAUDE.md/Notion "Трек 2": легаси-семейство единого конвейера.
SOURCES = {
    'archive3': (14, 'Overleaf Archive 3 (ОШ/ЛШ Олмат)'),
    'matek': (13, 'МатЭк — Overleaf архивы (2021–2025)'),
    'lsh2025': (3, 'ЛШ Олмат 2025 (Overleaf)'),
    'reshalki': (16, 'Решалки Олмат (olmat41)'),
}
EXCLUDED_SOURCE_NAME = 'Служебное: фикстуры рендерера (не публиковать)'


class Command(BaseCommand):
    help = (
        'Фаза 1 (read-only): прогнать общий конвертер по всем задачам легаси-'
        'источника, собрать сэмпл на 40 в отчёт. --source из: ' + ', '.join(SOURCES)
    )

    def add_arguments(self, parser):
        parser.add_argument('--source', required=True, choices=list(SOURCES.keys()))

    def handle(self, *args, **options):
        slug = options['source']
        source_id, source_name = SOURCES[slug]

        count_before = Problem.objects.count()

        qs = (
            Problem.objects.filter(source_references__source_id=source_id)
            .exclude(source_references__source__name=EXCLUDED_SOURCE_NAME)
            .distinct()
            .prefetch_related('parts')
        )
        total = qs.count()
        self.stdout.write(f'{source_name}: {total} задач найдено.')

        processed = []
        warnings_total = []
        complex_table_ids = []
        images_ids = []
        existing_parts_by_id = {}

        for problem in qs.iterator(chunk_size=500):
            existing_parts = [(part.label, part.statement) for part in problem.parts.all()]
            existing_parts_by_id[problem.id] = existing_parts
            result = convert_problem(
                statement=problem.statement,
                answer=problem.answer,
                solution=problem.solution,
                # См. corpus_pilot_ile.py — НЕ "existing_parts or None":
                # пустой список — легитимный сигнал «частей нет», не «не
                # проверяли». Баг A финального ревью пилота, не повторяем.
                existing_parts=existing_parts,
            )
            processed.append((problem, result))
            warnings_total.extend(f'#{problem.id}: {w}' for w in result['warnings'])
            if result['complex_table']:
                complex_table_ids.append(problem.id)
            if result['images']:
                images_ids.append(problem.id)

        approved = [(p, r) for p, r in processed if p.human_review == Problem.HumanReview.APPROVED]
        with_structure = [
            (p, r) for p, r in processed
            if r['parts'] or r['images'] or r['complex_table']
        ]

        random.seed(20260826)
        sample = {}
        for item in (random.sample(approved, min(MIN_APPROVED, len(approved))) if approved else []):
            sample[item[0].id] = item
        remaining_structure = [item for item in with_structure if item[0].id not in sample]
        for item in (
            random.sample(remaining_structure, min(MIN_WITH_STRUCTURE, len(remaining_structure)))
            if remaining_structure else []
        ):
            sample[item[0].id] = item
        remaining_pool = [item for item in processed if item[0].id not in sample]
        if len(sample) < SAMPLE_SIZE and remaining_pool:
            for item in random.sample(remaining_pool, min(SAMPLE_SIZE - len(sample), len(remaining_pool))):
                sample[item[0].id] = item

        entries = []
        for problem, result in sorted(sample.values(), key=lambda item: item[0].id)[:SAMPLE_SIZE]:
            entries.append(render_entry(
                problem_id=problem.id,
                source_label=f'{source_name} (human_review={problem.human_review or "не смотрели"})',
                before={
                    'statement': problem.statement,
                    'parts': [
                        {'label': label, 'statement': part_statement}
                        for label, part_statement in existing_parts_by_id[problem.id]
                    ],
                    'answer': problem.answer,
                    'solution': problem.solution,
                },
                after={
                    'statement_md': result['statement_md'],
                    'parts': result['parts'],
                    'answer_md': result['answer_md'],
                    'solution_md': result['solution_md'],
                    'images': result['images'],
                    'warnings': result['warnings'],
                },
            ))

        warnings_summary = (
            f'Всего предупреждений: {len(warnings_total)}\n'
            f'Сложных таблиц (в ручную очередь): {len(complex_table_ids)} — id: {complex_table_ids[:80]}'
            + ('...' if len(complex_table_ids) > 80 else '') + '\n'
            f'Задач с найденными картинками: {len(images_ids)} — id: {images_ids[:80]}'
            + ('...' if len(images_ids) > 80 else '')
        )
        report = render_report(
            f'Масштабирование конвертера — UPDATE: {source_name}', entries, warnings_summary,
        )

        out_dir = os.path.join(settings.BASE_DIR, 'reports', 'corpus_converter_scaleup')
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f'{slug}_report.md')
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(report)

        count_after = Problem.objects.count()
        if count_before != count_after:
            raise CommandError(
                f'ИНВАРИАНТ НАРУШЕН: Problem.objects.count() было {count_before}, стало {count_after}'
            )

        self.stdout.write(self.style.SUCCESS(
            f'Готово ({source_name}). Обработано {len(processed)}, в отчёт {len(entries)}, '
            f'предупреждений {len(warnings_total)}, сложных таблиц {len(complex_table_ids)}, '
            f'с картинками {len(images_ids)}, инвариант count() сошёлся ({count_before}). '
            f'Отчёт: {out_path}'
        ))
