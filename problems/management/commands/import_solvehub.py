# -*- coding: utf-8 -*-
"""Боевой импорт SolveHub в банк (Фаза 1 брифа import-new-sources).

Расширение read-only `corpus_scaleup_solvehub` до настоящего INSERT: не
на выборке в 40 задач, а на всех 6119 записях с диска (файлов 6121, у
двух пустое поле `md`).

| Поле банка | Откуда | Замечание |
|---|---|---|
| `title` | `title` | непусто у 3698 |
| `statement` | `md` + варианты ответа | см. `solvehub.options_block` |
| `answer` | `correct_answer` + `check_options` | см. `solvehub.format_answer` |
| `solution` | `answer_md` | непусто у 2248 |
| рубрика | `answer_md` прозой | `parse_solvehub_criteria` |
| `difficulty` | `difficulty` | `level1..5` -> `1..5`, `none` -> NULL |
| `SourceReference` | `hash`, `_source_url`, `source` | обязателен у каждой |

**Известные ограничения, перенесённые как есть (решение владельца).**

- **Дедупликация не применяется.** 366 задач совпадают с банком по
  точному `content_hash`; расследование прошлой сессии показало, что это
  короткие типовые формулировки тестовых вопросов (средняя длина 98
  символов), а не реальное пересечение корпусов. Импорт их НЕ отбрасывает
  и НЕ помечает — `find_duplicates` отработает позже обычной логикой.
- **Картинки остаются ссылками в тексте.** `FileAsset` во всём банке
  пуст, показ картинок не подключён (санитайзер `problems/rendering.py`
  режет `<img>`). Выкидывать ссылку из условия значило бы терять
  материал, поэтому она остаётся как есть. Докачка файлов — отдельный
  шаг, `scripts/solvehub/fetch_images.py`.

По умолчанию — сухой прогон. Запись — только с `--apply`.
"""
import glob
import json
import os

from django.core.management.base import BaseCommand, CommandError

from problems.corpus_converter.criteria import parse_solvehub_criteria
from problems.corpus_converter.ingest import (
    convert_for_import, create_problem, data_root, get_or_create_source,
    imported_external_ids, require_dir, write_warnings,
)
from problems.corpus_converter.solvehub import (
    DIFFICULTY_MAP, format_answer, options_block, parse_options,
)
from problems.models import Problem, ProblemPart, Rubric, SourceReference

SOURCE_NAME = 'SolveHub — банк задач по экономике'
SOURCE_DEFAULTS = {
    'kind': 'онлайн-банк задач',
    'note': 'Выгрузка solvehub.app/econ, август 2026.',
}


def _problems_dir(explicit):
    base = explicit or os.path.join(data_root(), 'solvehub')
    nested = os.path.join(base, 'problems')
    return nested if os.path.isdir(nested) else base


def _load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _statement_with_options(md, check_type, options):
    """Условие плюс варианты ответа — до конвертера, чтобы список прошёл
    ту же нормализацию, что и остальной текст."""
    block = options_block(check_type, options)
    return f'{md}\n\n{block}' if block else md


class Command(BaseCommand):
    help = 'Импорт SolveHub в банк (INSERT). Без --apply — сухой прогон.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='реально записать в базу (по умолчанию сухой прогон)')
        parser.add_argument('--limit', type=int,
                            help='импортировать только первые N (усечение называется в выводе)')
        parser.add_argument('--data-dir',
                            help='папка выгрузки SolveHub (по умолчанию weconomics-data/solvehub)')
        parser.add_argument('--report-dir',
                            help='куда класть отчёт; тесты обязаны давать временную папку — иначе затирают боевой')

    def handle(self, *args, **options):
        do_apply = options['apply']
        limit = options['limit']
        problems_dir = require_dir(
            _problems_dir(options.get('data_dir')), 'SolveHub')

        before = {
            'Problem': Problem.objects.count(),
            'ProblemPart': ProblemPart.objects.count(),
            'Rubric': Rubric.objects.count(),
        }

        source = None
        if do_apply:
            source = get_or_create_source(SOURCE_NAME, **SOURCE_DEFAULTS)
            already = imported_external_ids(source)
        else:
            already = set(
                SourceReference.objects.filter(source__name=SOURCE_NAME)
                .exclude(problem_number='')
                .values_list('problem_number', flat=True))

        paths = sorted(glob.glob(os.path.join(problems_dir, '*.json')))
        if not paths:
            raise CommandError(f'SolveHub: в {problems_dir} нет ни одного *.json')

        created = skipped_existing = skipped_empty = converted = 0
        with_answer = with_solution = with_rubric = with_images = 0
        with_options = with_parts = 0
        by_difficulty = {}
        warnings = []

        for path in paths:
            if limit is not None and created + skipped_existing >= limit:
                break
            raw = _load(path)
            external_id = str(raw.get('hash') or '')
            md = raw.get('md') or ''
            if not external_id or not md:
                skipped_empty += 1
                continue
            seen_before = external_id in already
            if seen_before and do_apply:
                skipped_existing += 1
                continue

            check_type = raw.get('check_type')
            opts = parse_options(raw.get('check_options'))
            local_warnings = []
            answer_text = format_answer(
                raw.get('correct_answer'), opts, local_warnings)
            statement_src = _statement_with_options(md, check_type, opts)
            if statement_src is not md:
                with_options += 1

            result = convert_for_import(
                statement=statement_src,
                answer=answer_text,
                solution=raw.get('answer_md') or '',
                existing_parts=None,
            )
            converted += 1
            criteria = parse_solvehub_criteria(raw.get('answer_md') or '')
            for text in (local_warnings + result['warnings'] + criteria['warnings']):
                warnings.append(f'{external_id} (#{raw.get("id")}): {text}')

            if result['parts']:
                with_parts += 1
            if result['answer_md']:
                with_answer += 1
            if result['solution_md']:
                with_solution += 1
            if criteria['criteria']:
                with_rubric += 1
            if result['images']:
                with_images += 1

            difficulty, native = DIFFICULTY_MAP.get(
                raw.get('difficulty'), (None, ''))
            by_difficulty[native or 'нет'] = by_difficulty.get(native or 'нет', 0) + 1

            if do_apply:
                create_problem(
                    source=source,
                    external_id=external_id,
                    title=raw.get('title') or '',
                    statement_md=result['statement_md'],
                    answer_md=result['answer_md'],
                    solution_md=result['solution_md'],
                    parts=result['parts'],
                    difficulty=difficulty,
                    difficulty_native=native,
                    reference_note=(raw.get('source') or '')[:300],
                    reference_url=raw.get('_source_url') or '',
                    rubric_criteria=criteria['criteria'],
                )
            if seen_before:
                skipped_existing += 1
            else:
                created += 1
                already.add(external_id)

        after = {
            'Problem': Problem.objects.count(),
            'ProblemPart': ProblemPart.objects.count(),
            'Rubric': Rubric.objects.count(),
        }
        if not do_apply and before != after:
            raise CommandError(
                f'СУХОЙ ПРОГОН НЕ ДОЛЖЕН ПИСАТЬ: было {before}, стало {after}')
        if do_apply and after['Problem'] - before['Problem'] != created:
            raise CommandError(
                f'ИНВАРИАНТ НАРУШЕН: создано {created}, а Problem вырос на '
                f'{after["Problem"] - before["Problem"]}')

        mode = 'ЗАПИСЬ (--apply)' if do_apply else 'СУХОЙ ПРОГОН (без --apply)'
        lines = [
            f'SolveHub — {mode}',
            f'  папка: {problems_dir}',
            f'  файлов на диске: {len(paths)}',
            f'  импортировано: {created}',
            f'  уже импортировано: {skipped_existing}',
            f'  пропущено (нет hash или пустое md): {skipped_empty}',
            f'  прогнано через конвертер: {converted}',
            f'  с вариантами ответа, дописанными в условие: {with_options}',
            f'  с подпунктами: {with_parts}',
            f'  с ответом: {with_answer}',
            f'  с решением: {with_solution}',
            f'  с рубрикой (критерии из прозы): {with_rubric}',
            f'  с картинками в тексте: {with_images}',
            f'  сложность: {by_difficulty}',
            f'  предупреждений: {len(warnings)}',
            '  дедупликация НЕ применялась (решение владельца): 366 совпадений '
            'content_hash с банком признаны вероятно ложными, разбор — за find_duplicates',
            f'  счётчики: было {before}, стало {after}',
        ]
        if limit is not None:
            lines.append(f'  ⚠️ ОХВАТ УСЕЧЁН: --limit {limit} — '
                         f'обработана только часть корпуса')
        lines.append('  ' + write_warnings(
            'solvehub_warnings.txt', warnings, converted, options.get('report_dir')))
        self.stdout.write(self.style.SUCCESS('\n'.join(lines)))
