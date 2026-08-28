# -*- coding: utf-8 -*-
"""Боевой импорт Школково в банк (Фаза 0 брифа import-new-sources).

Первый источник, который действительно ВСТАВЛЯЕТСЯ в базу: до сих пор
`corpus_pilot_shkolkovo` только читал с диска и писал отчёт.

Что кладётся в базу, поле за полем:

| Поле банка | Откуда | Замечание |
|---|---|---|
| `title` | `Name` | у всех 3414 непусто |
| `statement` | `statement_tex` | через `ingest.convert_for_import` |
| подпункты | а)/б)/в) внутри `statement_tex` | 269 задач |
| `answer` | `answer_tex`, иначе `Answer.text` | 51 / 2322 задачи |
| `solution` | `solution_tex` | 3406 задач |
| рубрика | `criteria_tex` | 836 задач, парсер `parse_shkolkovo_criteria` |
| `difficulty` | **нечему маппиться** | см. ниже |
| `SourceReference` | `Id`, `_source_url`, `source_name` | обязателен у каждой |

⚠️ **Шкала сложности у Школково отсутствует.** Единственное поле
`DifficultyId` равно `0` у ВСЕХ 3414 записей — это не «уровень 0», а
«поле не заполнено на стороне источника». Придумывать шкалу из тем или
длины текста запрещено (это было бы выдуманное, не импортированное
знание), поэтому `difficulty` остаётся `NULL`, а `difficulty_native` —
пустым. Таблица маппинга для этого источника состоит из одной строки и
приведена в отчёте.

Источник не проверен человеком: `status='draft'`,
`hidden_pending_review=True`, `content_format='plain'`. Разметку markdown
ставит только шлюз `render_preflight_v2` (отдельная команда), и только
прошедшим его.

По умолчанию — сухой прогон. Запись — только с `--apply`.
"""
import glob
import json
import os

from django.core.management.base import BaseCommand, CommandError

from problems.corpus_converter.criteria import parse_shkolkovo_criteria
from problems.corpus_converter.ingest import (
    convert_for_import, create_problem, data_root, get_or_create_source,
    imported_external_ids, require_dir, write_warnings,
)
from problems.models import Problem, ProblemPart, Rubric, SourceReference

SOURCE_NAME = 'Школково — банк задач по экономике'
SOURCE_DEFAULTS = {
    'kind': 'онлайн-банк задач',
    'note': 'Выгрузка 3.shkolkovo.online (LaTeX от latex-service), август 2026.',
}
#: Единственная строка «маппинга» шкалы сложности — см. docstring модуля.
DIFFICULTY_MAP = {0: (None, '')}


def _problems_dir(explicit):
    """`--data-dir` может указывать и на корень выгрузки, и прямо на папку
    с json (так удобнее фикстурам в тестах)."""
    base = explicit or os.path.join(data_root(), 'shkolkovo')
    nested = os.path.join(base, 'problems')
    return nested if os.path.isdir(nested) else base


def _load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _answer_text(raw):
    """`answer_tex` есть у 51 задачи, у остальных краткий ответ лежит в
    `Answer.text` — берём то, что есть, приоритет у развёрнутого."""
    if raw.get('answer_tex'):
        return raw['answer_tex']
    return ((raw.get('Answer') or {}).get('text') or '')


class Command(BaseCommand):
    help = ('Импорт Школково в банк (INSERT). Без --apply — сухой прогон.')

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='реально записать в базу (по умолчанию сухой прогон)')
        parser.add_argument('--limit', type=int,
                            help='импортировать только первые N (усечение называется в выводе)')
        parser.add_argument('--data-dir',
                            help='папка выгрузки Школково (по умолчанию weconomics-data/shkolkovo)')

    def handle(self, *args, **options):
        do_apply = options['apply']
        limit = options['limit']
        problems_dir = require_dir(
            _problems_dir(options.get('data_dir')), 'Школково')

        before = {
            'Problem': Problem.objects.count(),
            'ProblemPart': ProblemPart.objects.count(),
            'Rubric': Rubric.objects.count(),
        }

        source = None
        already = set()
        if do_apply:
            source = get_or_create_source(SOURCE_NAME, **SOURCE_DEFAULTS)
            already = imported_external_ids(source)
        else:
            existing = SourceReference.objects.filter(source__name=SOURCE_NAME)
            already = set(existing.exclude(problem_number='')
                          .values_list('problem_number', flat=True))

        paths = sorted(glob.glob(os.path.join(problems_dir, '*.json')))
        if not paths:
            raise CommandError(f'Школково: в {problems_dir} нет ни одного *.json')

        created = skipped_existing = skipped_empty = converted = 0
        with_parts = with_answer = with_solution = with_rubric = 0
        with_images = 0
        warnings = []

        for path in paths:
            if limit is not None and created + skipped_existing >= limit:
                break
            raw = _load(path)
            external_id = str(raw.get('Id') or '')
            statement_tex = raw.get('statement_tex') or ''
            if not external_id or not statement_tex:
                skipped_empty += 1
                continue
            seen_before = external_id in already
            if seen_before and do_apply:
                # Боевой прогон уже импортированную задачу не трогает и не
                # тратит на неё конвертер. Сухой — наоборот, гонит её через
                # конвертер ради предупреждений: иначе повторный сухой прогон
                # по уже импортированному источнику отчитался бы
                # «предупреждений 0», что читается как «всё чисто».
                skipped_existing += 1
                continue

            result = convert_for_import(
                statement=statement_tex,
                answer=_answer_text(raw),
                solution=raw.get('solution_tex') or '',
                existing_parts=None,
            )
            converted += 1
            criteria = parse_shkolkovo_criteria(raw.get('criteria_tex') or '')
            warnings.extend(f'{external_id}: {w}' for w in result['warnings'])
            warnings.extend(f'{external_id}: {w}' for w in criteria['warnings'])

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
                raw.get('DifficultyId'), (None, ''))

            if do_apply:
                source_names = raw.get('source_names') or []
                note = raw.get('source_name') or (
                    '; '.join(str(n) for n in source_names) if source_names else '')
                create_problem(
                    source=source,
                    external_id=external_id,
                    title=raw.get('Name') or '',
                    statement_md=result['statement_md'],
                    answer_md=result['answer_md'],
                    solution_md=result['solution_md'],
                    parts=result['parts'],
                    difficulty=difficulty,
                    difficulty_native=native,
                    reference_note=note,
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

        self._report(problems_dir, paths, created, skipped_existing, converted,
                     skipped_empty, with_parts, with_answer, with_solution,
                     with_rubric, with_images, warnings, before, after,
                     do_apply, limit)

    def _report(self, problems_dir, paths, created, skipped_existing, converted,
                skipped_empty, with_parts, with_answer, with_solution,
                with_rubric, with_images, warnings, before, after,
                do_apply, limit):
        mode = 'ЗАПИСЬ (--apply)' if do_apply else 'СУХОЙ ПРОГОН (без --apply)'
        lines = [
            f'Школково — {mode}',
            f'  папка: {problems_dir}',
            f'  файлов на диске: {len(paths)}',
            f'  импортировано: {created}',
            f'  уже импортировано: {skipped_existing}',
            f'  пропущено (нет Id или пустое условие): {skipped_empty}',
            f'  с подпунктами: {with_parts}',
            f'  с ответом: {with_answer}',
            f'  с решением: {with_solution}',
            f'  с рубрикой (criteria_tex разобран): {with_rubric}',
            f'  с картинками в тексте: {with_images}',
            f'  прогнано через конвертер: {converted}',
            f'  предупреждений конвертера: {len(warnings)}',
            '  сложность: DifficultyId=0 у всех записей источника — '
            'difficulty=NULL, difficulty_native=пусто (маппить нечего)',
            f'  счётчики: было {before}, стало {after}',
        ]
        if limit is not None:
            lines.append(f'  ⚠️ ОХВАТ УСЕЧЁН: --limit {limit} — '
                         f'обработана только часть корпуса')
        lines.append('  ' + write_warnings(
            'shkolkovo_warnings.txt', warnings, converted))
        self.stdout.write(self.style.SUCCESS('\n'.join(lines)))
