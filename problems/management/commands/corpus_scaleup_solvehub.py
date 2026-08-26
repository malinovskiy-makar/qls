# -*- coding: utf-8 -*-
"""Фаза 2 брифа corpus-converter-scaleup: путь INSERT на SolveHub.

READ-ONLY, как corpus_pilot_shkolkovo.py. Ничего не создаётся в базе —
только чтение с диска и генерация
reports/corpus_converter_scaleup/solvehub_report.md."""
import glob
import hashlib
import json
import os
import random
import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from problems.corpus_converter.core import convert_problem
from problems.corpus_converter.criteria import parse_solvehub_criteria
from problems.corpus_converter.report import render_entry, render_report
from problems.models import Problem, ProblemPart, Rubric, FileAsset

SAMPLE_SIZE = 40
#: Путь вне репозитория (как SHKOLKOVO_DIR в corpus_pilot_shkolkovo.py).
SOLVEHUB_DIR = os.path.join(
    os.path.dirname(settings.BASE_DIR), 'weconomics-data', 'solvehub',
)
EXCLUDED_SOURCE_NAME = 'Служебное: фикстуры рендерера (не публиковать)'
#: Кириллица внутри \text{} — атлас: ~250 задач SolveHub. Не текстовая
#: правка (шрифтовой фолбэк KaTeX — работа сайта/раздела 2б), только
#: подсчёт для отчёта, конвертер это не трогает.
_CYRILLIC_IN_TEXT_CMD_RE = re.compile(r'\\text\{[^}]*[а-яА-ЯёЁ][^}]*\}')


def _load_problems():
    problems_dir = os.path.join(SOLVEHUB_DIR, 'problems')
    for path in sorted(glob.glob(os.path.join(problems_dir, '*.json'))):
        with open(path, encoding='utf-8') as f:
            yield json.load(f)


def _classify_images(images, image_map, local_files):
    """Каждую картинку -> 'resolved' (скачана и лежит на диске) или
    'broken' (URL не в image_map — атлас: 293 из 837, или в image_map, но
    файла нет на диске — на живых данных не встречено, но не молчим)."""
    classified = []
    for img in images:
        ref = img['original_ref']
        if img['kind'] != 'markdown':
            classified.append({**img, 'status': 'не-markdown (includegraphics/url) — вне scope SolveHub'})
            continue
        local_name = image_map.get(ref)
        if local_name is None:
            classified.append({**img, 'status': 'битая ссылка — URL не в image_map (не скачано)'})
        elif local_name not in local_files:
            classified.append({**img, 'status': 'в image_map, но файла нет на диске'})
        else:
            classified.append({**img, 'status': f'resolved -> images/{local_name}'})
    return classified


class Command(BaseCommand):
    help = 'Фаза 2 (read-only): прогнать конвертер по SolveHub с диска, кандидаты в отчёт.'

    def handle(self, *args, **options):
        counts_before = {
            'Problem': Problem.objects.count(),
            'ProblemPart': ProblemPart.objects.count(),
            'Rubric': Rubric.objects.count(),
            'FileAsset': FileAsset.objects.count(),
        }

        with open(os.path.join(SOLVEHUB_DIR, 'image_map.json'), encoding='utf-8') as f:
            image_map = json.load(f)
        local_files = set(os.listdir(os.path.join(SOLVEHUB_DIR, 'images')))

        existing_hashes = set(
            Problem.objects
            .exclude(content_hash='')
            .exclude(source_references__source__name=EXCLUDED_SOURCE_NAME)
            .values_list('content_hash', flat=True)
        )

        candidates = []
        dup_ids = []
        warnings_total = []
        complex_table_count = 0
        broken_image_count = 0
        cyrillic_in_text_count = 0

        for raw in _load_problems():
            statement_md = raw.get('md') or ''
            if not statement_md:
                continue
            answer_md_raw = raw.get('answer_md') or ''
            result = convert_problem(
                statement=statement_md,
                answer='',
                solution=answer_md_raw,
                existing_parts=None,
            )
            criteria_result = parse_solvehub_criteria(answer_md_raw)
            images = _classify_images(result['images'], image_map, local_files)
            broken_here = [img for img in images if 'битая ссылка' in img['status']]
            if broken_here:
                broken_image_count += 1

            if _CYRILLIC_IN_TEXT_CMD_RE.search(statement_md) or _CYRILLIC_IN_TEXT_CMD_RE.search(answer_md_raw):
                cyrillic_in_text_count += 1

            content_hash = hashlib.md5(statement_md.encode('utf-8'), usedforsecurity=False).hexdigest()
            is_dup = content_hash in existing_hashes
            if is_dup:
                dup_ids.append(raw['id'])

            warnings_total.extend(f"{raw['id']}: {w}" for w in result['warnings'])
            warnings_total.extend(f"{raw['id']}: {w}" for w in criteria_result['warnings'])
            if result['complex_table']:
                complex_table_count += 1

            candidates.append((raw, result, criteria_result, images, is_dup))

        with_criteria = [c for c in candidates if c[2]['criteria']]
        with_broken_images = [c for c in candidates if any('битая ссылка' in i['status'] for i in c[3])]
        with_tables = [c for c in candidates if c[1]['complex_table']]
        rest = candidates

        random.seed(20260826)
        sample = []
        for bucket, n in ((with_criteria, 10), (with_broken_images, 10), (with_tables, 8)):
            picks = random.sample(bucket, min(n, len(bucket))) if bucket else []
            for pick in picks:
                if pick not in sample:
                    sample.append(pick)
        remaining = [c for c in rest if c not in sample]
        if len(sample) < SAMPLE_SIZE and remaining:
            sample.extend(random.sample(remaining, min(SAMPLE_SIZE - len(sample), len(remaining))))

        entries = []
        for raw, result, criteria_result, images, is_dup in sample[:SAMPLE_SIZE]:
            entries.append(render_entry(
                problem_id=raw['id'],
                source_label='SolveHub (кандидат, НЕ в базе)',
                before={
                    'title': raw.get('title', ''),
                    'md': raw.get('md', ''),
                    'answer_md': raw.get('answer_md', ''),
                },
                after={
                    'statement_md': result['statement_md'],
                    'parts': result['parts'],
                    'solution_md': result['solution_md'],
                    'rubric_criteria': criteria_result['criteria'],
                    'images': images,
                    'warnings': result['warnings'] + criteria_result['warnings'],
                },
                extra_note='ТОЧНОЕ совпадение content_hash с банком — вероятный дубль' if is_dup else '',
            ))

        warnings_summary = (
            f'Всего предупреждений: {len(warnings_total)}\n'
            f'Сложных таблиц (в ручную очередь): {complex_table_count}\n'
            f'Задач хотя бы с одной битой ссылкой на картинку: {broken_image_count}\n'
            f'Задач с кириллицей внутри \\text{{}} (только подсчёт для отчёта, шрифтовой '
            f'фолбэк — работа сайта, не конвертера): {cyrillic_in_text_count}\n'
            f'Точных дублей по content_hash с банком (грубая проверка, полный дедуп — '
            f'работа следующей сессии): {len(dup_ids)} — id: {dup_ids[:50]}'
            + ('...' if len(dup_ids) > 50 else '')
        )
        report = render_report('Масштабирование конвертера — INSERT: SolveHub', entries, warnings_summary)

        out_dir = os.path.join(settings.BASE_DIR, 'reports', 'corpus_converter_scaleup')
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, 'solvehub_report.md')
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
            f'Готово. Прочитано {len(candidates)} с диска, в отчёт {len(entries)}, '
            f'вероятных дублей {len(dup_ids)}, сложных таблиц {complex_table_count}, '
            f'с битыми картинками {broken_image_count}, инвариант счётчиков сошёлся. '
            f'Отчёт: {out_path}'
        ))
