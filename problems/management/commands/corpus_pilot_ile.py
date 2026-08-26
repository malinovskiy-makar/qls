# -*- coding: utf-8 -*-
"""Фаза 1 брифа corpus-converter-pilot: путь UPDATE на ILE.

READ-ONLY. Ни один Problem/ProblemPart не изменяется — только чтение и
генерация reports/corpus_converter_pilot/ile_report.md."""
import os
import random

from django.conf import settings
from django.core.management.base import BaseCommand

from problems.corpus_converter.core import convert_problem
from problems.corpus_converter.report import render_entry, render_report
from problems.models import Problem

SAMPLE_SIZE = 30
MIN_APPROVED = 15
MIN_WITH_STRUCTURE = 10


class Command(BaseCommand):
    help = 'Фаза 1 (read-only): прогнать конвертер по всем ILE-задачам, собрать сэмпл на 30 в отчёт.'

    def handle(self, *args, **options):
        count_before = Problem.objects.count()

        qs = (
            Problem.objects.filter(source_references__source__name='ILE / iloveeconomics.ru')
            .exclude(source_references__source__name='Служебное: фикстуры рендерера (не публиковать)')
            .distinct()
            .prefetch_related('parts')
        )
        total = qs.count()
        self.stdout.write(f'ILE: {total} задач найдено.')

        processed = []
        warnings_total = []
        complex_table_ids = []

        for problem in qs.iterator(chunk_size=300):
            existing_parts = [(part.label, part.statement) for part in problem.parts.all()]
            result = convert_problem(
                statement=problem.statement,
                answer=problem.answer,
                solution=problem.solution,
                existing_parts=existing_parts or None,
            )
            processed.append((problem, result))
            warnings_total.extend(f'#{problem.id}: {w}' for w in result['warnings'])
            if result['complex_table']:
                complex_table_ids.append(problem.id)

        approved = [(p, r) for p, r in processed if p.human_review == Problem.HumanReview.APPROVED]
        with_structure = [
            (p, r) for p, r in processed
            if r['parts'] or r['images'] or r['complex_table']
        ]

        # dict, не set: result — обычный dict (незахешируемый), поэтому
        # дедуп идёт по problem.id, а не по хешу пары (problem, result).
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
                source_label=f'ILE (human_review={problem.human_review or "не смотрели"})',
                before={
                    'statement': problem.statement,
                    'answer': problem.answer,
                    'solution': problem.solution,
                },
                after={
                    'statement_md': result['statement_md'],
                    'parts': result['parts'],
                    'answer_md': result['answer_md'],
                    'solution_md': result['solution_md'],
                    'warnings': result['warnings'],
                },
            ))

        warnings_summary = (
            f'Всего предупреждений: {len(warnings_total)}\n'
            f'Сложных таблиц (в ручную очередь): {len(complex_table_ids)} — id: {complex_table_ids}\n'
        )
        report = render_report('Пилот конвертера — Фаза 1: ILE (UPDATE)', entries, warnings_summary)

        out_dir = os.path.join(settings.BASE_DIR, 'reports', 'corpus_converter_pilot')
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, 'ile_report.md')
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(report)

        count_after = Problem.objects.count()
        assert count_before == count_after, (
            f'ИНВАРИАНТ НАРУШЕН: Problem.objects.count() было {count_before}, стало {count_after}'
        )

        self.stdout.write(self.style.SUCCESS(
            f'Готово. Обработано {len(processed)}, в отчёт {len(entries)}, '
            f'сложных таблиц {len(complex_table_ids)}, инвариант count() сошёлся ({count_before}). '
            f'Отчёт: {out_path}'
        ))
