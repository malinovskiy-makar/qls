# -*- coding: utf-8 -*-
"""Фаза 2 брифа corpus-converter-scaleup: путь INSERT на ЛЭШ_2026_Гамма.

READ-ONLY. Ничего не создаётся в базе — только чтение с диска и генерация
reports/corpus_converter_scaleup/lesh_report.md.

Ловушка атласа ("Связь Подборки ↔ Решалки"): решения лежат в ОТДЕЛЬНЫХ
файлах и связываются с условием по названию \\z[Название], а не по имени
файла — сравнение по тексту условия даёт 0 совпадений, потому что текст
решения переписан заново."""
import glob
import hashlib
import os
import random

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from problems.corpus_converter.core import convert_problem
from problems.corpus_converter.lesh import parse_z_blocks, interpret_z_args
from problems.corpus_converter.report import render_entry, render_report
from problems.models import Problem, ProblemPart, Rubric, FileAsset

SAMPLE_SIZE = 40
#: В отличие от SolveHub/Школково этот источник лежит ВНУТРИ репозитория
#: (materials/corpus_sources/), не в соседней weconomics-data/.
LESH_DIR = os.path.join(
    settings.BASE_DIR, 'materials', 'corpus_sources',
    'lesh_2026_gamma', 'ЛЭШ_2026__Гамма',
)
EXCLUDED_SOURCE_NAME = 'Служебное: фикстуры рендерера (не публиковать)'
#: Исключены из корпуса Гамма-2026 сознательно, консервативно (атлас сам
#: оставляет это открытым вопросом): misc/ — служебные преамбулы, не
#: задачи; "Пример и шаблон/" и "качи.tex" — атлас пометил их как группу β
#: и датировку 2023 годом, не подтверждённые как часть среза Гамма-2026.
EXCLUDED_DIR_PARTS = ('misc',)
EXCLUDED_PATH_SUBSTRINGS = ('Пример и шаблон', 'качи.tex')


def _iter_tex_files():
    for path in glob.glob(os.path.join(LESH_DIR, '**', '*.tex'), recursive=True):
        rel = os.path.relpath(path, LESH_DIR)
        parts = rel.split(os.sep)
        if any(p in EXCLUDED_DIR_PARTS for p in parts):
            continue
        if any(sub in rel for sub in EXCLUDED_PATH_SUBSTRINGS):
            continue
        yield path, rel


def _is_reshalka_file(rel_path):
    return 'решалк' in rel_path.lower()


class Command(BaseCommand):
    help = 'Фаза 2 (read-only): прогнать конвертер по ЛЭШ Гамма с диска, кандидаты в отчёт.'

    def handle(self, *args, **options):
        counts_before = {
            'Problem': Problem.objects.count(),
            'ProblemPart': ProblemPart.objects.count(),
            'Rubric': Rubric.objects.count(),
            'FileAsset': FileAsset.objects.count(),
        }

        existing_hashes = set(
            Problem.objects
            .exclude(content_hash='')
            .exclude(source_references__source__name=EXCLUDED_SOURCE_NAME)
            .values_list('content_hash', flat=True)
        )

        condition_blocks = []  # (rel_path, parsed)
        solutions_by_name = {}  # name -> (rel_path, parsed)
        parse_warnings = []
        files_read = 0

        for path, rel in _iter_tex_files():
            files_read += 1
            with open(path, encoding='utf-8', errors='replace') as f:
                text = f.read()
            blocks, warnings = parse_z_blocks(text)
            parse_warnings.extend(f'{rel}: {w}' for w in warnings)
            is_reshalka = _is_reshalka_file(rel)
            for block in blocks:
                parsed = interpret_z_args(block)
                if is_reshalka:
                    if parsed['name']:
                        solutions_by_name.setdefault(parsed['name'], (rel, parsed))
                else:
                    condition_blocks.append((rel, parsed))

        # Дедуп ВНУТРИ корпуса — атлас: "по первым 200 символам условия,
        # 113 уникальных из 152". Первое вхождение выигрывает.
        seen_prefixes = set()
        unique_conditions = []
        internal_dup_count = 0
        for rel, parsed in condition_blocks:
            prefix = parsed['statement'][:200]
            if not prefix:
                continue
            if prefix in seen_prefixes:
                internal_dup_count += 1
                continue
            seen_prefixes.add(prefix)
            unique_conditions.append((rel, parsed))

        candidates = []
        dup_ids = []  # против банка (content_hash)
        warnings_total = list(parse_warnings)
        matched_solution_count = 0
        with_images_count = 0
        with_footnote_or_table_count = 0

        for idx, (rel, parsed) in enumerate(unique_conditions):
            statement = parsed['statement']
            if not statement:
                continue
            solution_text = ''
            if parsed['name'] and parsed['name'] in solutions_by_name:
                sol_rel, sol_parsed = solutions_by_name[parsed['name']]
                solution_text = sol_parsed['statement']
                matched_solution_count += 1
            else:
                warnings_total.append(f'{rel} [{parsed["name"]}]: решение не найдено по названию')

            existing_parts = [
                (str(i + 1), subpoint) for i, subpoint in enumerate(parsed['subpoints'])
            ]
            result = convert_problem(
                statement=statement,
                answer='',
                solution=solution_text,
                existing_parts=existing_parts or [],
            )
            warnings_total.extend(f'{rel} [{parsed["name"]}]: {w}' for w in result['warnings'])
            if result['images']:
                with_images_count += 1
            if '\\includegraphics' in statement or '\\includegraphics' in solution_text:
                with_footnote_or_table_count += 1  # tikzpicture/includegraphics — визуальные случаи

            content_hash = hashlib.md5(statement.encode('utf-8'), usedforsecurity=False).hexdigest()
            is_dup = content_hash in existing_hashes
            if is_dup:
                dup_ids.append(f'{rel}[{parsed["name"]}]')

            candidates.append((rel, parsed, result, solution_text, is_dup))

        with_images = [c for c in candidates if c[2]['images']]
        with_solution = [c for c in candidates if c[3]]
        rest = candidates

        random.seed(20260826)
        sample = []
        for bucket, n in ((with_images, 10), (with_solution, 15)):
            picks = random.sample(bucket, min(n, len(bucket))) if bucket else []
            for pick in picks:
                if pick not in sample:
                    sample.append(pick)
        remaining = [c for c in rest if c not in sample]
        if len(sample) < SAMPLE_SIZE and remaining:
            sample.extend(random.sample(remaining, min(SAMPLE_SIZE - len(sample), len(remaining))))

        entries = []
        for rel, parsed, result, solution_text, is_dup in sample[:SAMPLE_SIZE]:
            entries.append(render_entry(
                problem_id=f'{rel} :: {parsed["name"] or "(без названия)"}',
                source_label='ЛЭШ_2026_Гамма (кандидат, НЕ в базе)',
                before={
                    'name': parsed['name'] or '',
                    'statement_raw': parsed['statement'],
                    'subpoints_raw': parsed['subpoints'],
                    'solution_raw (найдено по названию в Решалках)': solution_text,
                },
                after={
                    'statement_md': result['statement_md'],
                    'parts': result['parts'],
                    'solution_md': result['solution_md'],
                    'images': result['images'],
                    'warnings': result['warnings'],
                },
                extra_note='ТОЧНОЕ совпадение content_hash с банком — вероятный дубль' if is_dup else '',
            ))

        warnings_summary = (
            f'Файлов .tex прочитано: {files_read} (исключены misc/, "Пример и шаблон/", "качи.tex")\n'
            f'Блоков \\z найдено: {len(condition_blocks)} в Подборках, {len(solutions_by_name)}'
            f' уникальных названий в Решалках\n'
            f'Дублей внутри корпуса (по первым 200 симв. условия): {internal_dup_count}\n'
            f'Уникальных задач-кандидатов: {len(unique_conditions)}\n'
            f'Решение найдено по названию: {matched_solution_count} из {len(candidates)}\n'
            f'Задач с картинками (\\includegraphics): {with_images_count}\n'
            f'Всего предупреждений: {len(warnings_total)}\n'
            f'Точных дублей по content_hash с банком (грубая проверка): {len(dup_ids)} — {dup_ids[:50]}'
            + ('...' if len(dup_ids) > 50 else '')
        )
        report = render_report('Масштабирование конвертера — INSERT: ЛЭШ_2026_Гамма', entries, warnings_summary)

        out_dir = os.path.join(settings.BASE_DIR, 'reports', 'corpus_converter_scaleup')
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, 'lesh_report.md')
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(report)

        counts_after = {
            'Problem': Problem.objects.count(),
            'ProblemPart': ProblemPart.objects.count(),
            'Rubric': Rubric.objects.count(),
            'FileAsset': FileAsset.objects.count(),
        }
        if counts_before != counts_after:
            raise CommandError(f'ИНВАРИАНТ НАРУШЕН: было {counts_before}, стало {counts_after}')

        self.stdout.write(self.style.SUCCESS(
            f'Готово. Файлов {files_read}, уникальных задач {len(unique_conditions)}, '
            f'в отчёт {len(entries)}, решение найдено {matched_solution_count}, '
            f'вероятных дублей {len(dup_ids)}, инвариант счётчиков сошёлся. Отчёт: {out_path}'
        ))
