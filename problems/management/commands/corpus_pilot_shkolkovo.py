# -*- coding: utf-8 -*-
"""Фаза 2 брифа corpus-converter-pilot: путь INSERT на Школково.

READ-ONLY. Ничего не создаётся в базе — только чтение с диска и генерация
reports/corpus_converter_pilot/shkolkovo_report.md."""
import glob
import hashlib
import json
import os
import random

from django.conf import settings
from django.core.management.base import BaseCommand

from problems.corpus_converter.core import convert_problem
from problems.corpus_converter.criteria import parse_shkolkovo_criteria
from problems.corpus_converter.report import render_entry, render_report
from problems.models import Problem, ProblemPart, Rubric, FileAsset

SAMPLE_SIZE = 30
#: Путь вне репозитория, найден в Фазе -1 (2026-08-26): соседняя папка
#: относительно корня qls, НЕ внутри репозитория — не трогать/не двигать.
SHKOLKOVO_DIR = os.path.join(
    os.path.dirname(settings.BASE_DIR), 'weconomics-data', 'shkolkovo',
)


def _load_problems():
    problems_dir = os.path.join(SHKOLKOVO_DIR, 'problems')
    for path in sorted(glob.glob(os.path.join(problems_dir, '*.json'))):
        with open(path, encoding='utf-8') as f:
            yield json.load(f)


class Command(BaseCommand):
    help = 'Фаза 2 (read-only): прогнать конвертер по Школково с диска, кандидаты в отчёт.'

    def handle(self, *args, **options):
        counts_before = {
            'Problem': Problem.objects.count(),
            'ProblemPart': ProblemPart.objects.count(),
            'Rubric': Rubric.objects.count(),
            'FileAsset': FileAsset.objects.count(),
        }

        existing_hashes = set(
            Problem.objects.exclude(content_hash='').values_list('content_hash', flat=True)
        )

        candidates = []
        dup_ids = []
        warnings_total = []
        complex_table_count = 0

        for raw in _load_problems():
            statement_tex = raw.get('statement_tex') or ''
            if not statement_tex:
                continue
            result = convert_problem(
                statement=statement_tex,
                answer=raw.get('answer_tex') or '',
                solution=raw.get('solution_tex') or '',
                existing_parts=None,
            )
            criteria_result = parse_shkolkovo_criteria(raw.get('criteria_tex') or '')

            content_hash = hashlib.md5(statement_tex.encode('utf-8')).hexdigest()
            is_dup = content_hash in existing_hashes
            if is_dup:
                dup_ids.append(raw['Id'])

            warnings_total.extend(f"{raw['Id']}: {w}" for w in result['warnings'])
            warnings_total.extend(f"{raw['Id']}: {w}" for w in criteria_result['warnings'])
            if result['complex_table']:
                complex_table_count += 1

            candidates.append((raw, result, criteria_result, is_dup))

        with_criteria = [c for c in candidates if c[2]['criteria']]
        with_images = [c for c in candidates if c[1]['images']]
        with_tables = [c for c in candidates if c[1]['complex_table']]
        rest = candidates

        random.seed(20260826)
        sample = []
        for bucket, n in ((with_criteria, 8), (with_images, 8), (with_tables, 6)):
            picks = random.sample(bucket, min(n, len(bucket))) if bucket else []
            for pick in picks:
                if pick not in sample:
                    sample.append(pick)
        remaining = [c for c in rest if c not in sample]
        if len(sample) < SAMPLE_SIZE and remaining:
            sample.extend(random.sample(remaining, min(SAMPLE_SIZE - len(sample), len(remaining))))

        entries = []
        for raw, result, criteria_result, is_dup in sample[:SAMPLE_SIZE]:
            entries.append(render_entry(
                problem_id=raw['Id'],
                source_label='Школково (кандидат, НЕ в базе)',
                before={
                    'statement_tex': raw.get('statement_tex', ''),
                    'answer_tex': raw.get('answer_tex', ''),
                    'solution_tex': raw.get('solution_tex', ''),
                    'criteria_tex': raw.get('criteria_tex', ''),
                },
                after={
                    'statement_md': result['statement_md'],
                    'parts': result['parts'],
                    'answer_md': result['answer_md'],
                    'solution_md': result['solution_md'],
                    'rubric_criteria': criteria_result['criteria'],
                    'images': result['images'],
                    'warnings': result['warnings'] + criteria_result['warnings'],
                },
                extra_note='ТОЧНОЕ совпадение content_hash с банком — вероятный дубль' if is_dup else '',
            ))

        warnings_summary = (
            f'Всего предупреждений: {len(warnings_total)}\n'
            f'Сложных таблиц (в ручную очередь): {complex_table_count}\n'
            f'Точных дублей по content_hash с банком (грубая проверка, полный дедуп — '
            f'работа следующей сессии): {len(dup_ids)} — id: {dup_ids[:50]}'
            + ('...' if len(dup_ids) > 50 else '')
        )
        report = render_report('Пилот конвертера — Фаза 2: Школково (INSERT)', entries, warnings_summary)

        out_dir = os.path.join(settings.BASE_DIR, 'reports', 'corpus_converter_pilot')
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, 'shkolkovo_report.md')
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(report)

        counts_after = {
            'Problem': Problem.objects.count(),
            'ProblemPart': ProblemPart.objects.count(),
            'Rubric': Rubric.objects.count(),
            'FileAsset': FileAsset.objects.count(),
        }
        assert counts_before == counts_after, (
            f'ИНВАРИАНТ НАРУШЕН: было {counts_before}, стало {counts_after}'
        )

        self.stdout.write(self.style.SUCCESS(
            f'Готово. Прочитано {len(candidates)} с диска, в отчёт {len(entries)}, '
            f'вероятных дублей {len(dup_ids)}, сложных таблиц {complex_table_count}, '
            f'инвариант счётчиков сошёлся. Отчёт: {out_path}'
        ))
