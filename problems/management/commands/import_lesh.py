# -*- coding: utf-8 -*-
r"""Боевой импорт ЛЭШ_2026_Гамма в банк (Фаза 2 брифа import-new-sources).

Расширение read-only `corpus_scaleup_lesh` до настоящего INSERT. Разбор
собственного макроса `\z[Название][баллы]{Текст}{\n Пункт;}[Источник]` —
`problems/corpus_converter/lesh.py`, здесь только запись в базу.

**Все 75 кандидатов импортируются, включая 40 без решения.** Решение
лежит в отдельных файлах-«решалках» и связывается с условием по ТОЧНОМУ
совпадению `\z[Название]` — по тексту условия совпадений нет вовсе, текст
решения переписан заново. Совпало 35 названий из 75. У остальных 40 поле
`solution` остаётся ПУСТЫМ: подбирать решение по смыслу в этой сессии
запрещено брифом, а «похожее» решение не у той задачи хуже, чем никакого.

**Шкалы сложности у источника нет.** Второй аргумент `\z` — это БАЛЛЫ за
задачу, а не сложность; он сохраняется в заметке привязки к источнику.
`difficulty` остаётся `NULL`.

**Пункты решения не теряются.** У блока-решения свои `\n`-пункты, и их
число не совпадает с числом пунктов условия (живой пример: «Классика» —
4 против 2). Разложить по частям их нельзя, поэтому они дописываются в
конец текста решения.

Исключения из корпуса — те же, что в read-only команде, и по той же
консервативной причине: `misc/` (служебные преамбулы, не задачи),
«Пример и шаблон/» и `качи.tex` (атлас пометил их как группу β/2023, не
подтверждённую часть среза Гамма-2026).

По умолчанию — сухой прогон. Запись — только с `--apply`.
"""
import glob
import hashlib
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from problems.corpus_converter.ingest import (
    convert_for_import, create_problem, get_or_create_source,
    imported_external_ids, require_dir, write_warnings,
)
from problems.corpus_converter.lesh import interpret_z_args, parse_z_blocks
from problems.models import Problem, ProblemPart, SourceReference

SOURCE_NAME = 'ЛЭШ 2026 — Гамма'
SOURCE_DEFAULTS = {
    'kind': 'авторские материалы',
    'year': 2026,
    'note': 'Летняя экономическая школа 2026, группа Гамма (.tex-архив составителей).',
}
EXCLUDED_DIR_PARTS = ('misc',)
EXCLUDED_PATH_SUBSTRINGS = ('Пример и шаблон', 'качи.tex')
#: Ключ дедупликации внутри корпуса — первые 200 символов условия (так же
#: считала read-only команда: 154 блока \z сворачиваются в 75 задач).
DEDUP_PREFIX = 200


def _lesh_dir(explicit):
    """В отличие от Школково и SolveHub этот источник лежит ВНУТРИ
    репозитория (`materials/` в .gitignore, но путь считается от
    BASE_DIR), а не в соседней `weconomics-data/`."""
    if explicit:
        return explicit
    return os.path.join(
        settings.BASE_DIR, 'materials', 'corpus_sources',
        'lesh_2026_gamma', 'ЛЭШ_2026__Гамма',
    )


def _iter_tex_files(root):
    for path in sorted(glob.glob(os.path.join(root, '**', '*.tex'), recursive=True)):
        rel = os.path.relpath(path, root)
        parts = rel.split(os.sep)
        if any(p in EXCLUDED_DIR_PARTS for p in parts):
            continue
        if any(sub in rel for sub in EXCLUDED_PATH_SUBSTRINGS):
            continue
        yield path, rel


def _is_reshalka(rel_path):
    return 'решалк' in rel_path.lower()


def external_key(statement):
    """Устойчивый внешний ключ задачи ЛЭШ.

    У источника нет ни числовых id, ни уникальных названий, а поле
    `SourceReference.problem_number` — 50 символов. Берём короткий хэш от
    того же префикса условия, по которому идёт дедупликация внутри
    корпуса: один и тот же текст даёт один и тот же ключ, поэтому
    повторный запуск не создаёт вторую копию. Человекочитаемое «файл ::
    название» лежит рядом, в заметке привязки."""
    return hashlib.md5(
        statement[:DEDUP_PREFIX].encode('utf-8'),
        usedforsecurity=False).hexdigest()[:16]


def solution_text(parsed):
    """Текст решения = условие блока-решения + его пункты списком."""
    if parsed is None:
        return ''
    body = [parsed['statement'].strip()]
    body += [item for item in parsed['subpoints'] if item.strip()]
    return '\n\n'.join(part for part in body if part)


class Command(BaseCommand):
    help = 'Импорт ЛЭШ 2026 Гамма в банк (INSERT). Без --apply — сухой прогон.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='реально записать в базу (по умолчанию сухой прогон)')
        parser.add_argument('--limit', type=int,
                            help='импортировать только первые N (усечение называется в выводе)')
        parser.add_argument('--data-dir',
                            help='корень архива ЛЭШ (по умолчанию materials/corpus_sources/...)')
        parser.add_argument('--report-dir',
                            help='куда класть отчёт; тесты обязаны давать временную папку — иначе затирают боевой')

    def handle(self, *args, **options):
        do_apply = options['apply']
        limit = options['limit']
        root = require_dir(_lesh_dir(options.get('data_dir')), 'ЛЭШ 2026 Гамма')

        before = {
            'Problem': Problem.objects.count(),
            'ProblemPart': ProblemPart.objects.count(),
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

        warnings = []
        conditions = []          # (rel, parsed)
        solutions_by_name = {}   # название -> parsed
        files_read = 0

        for path, rel in _iter_tex_files(root):
            files_read += 1
            with open(path, encoding='utf-8', errors='replace') as f:
                text = f.read()
            blocks, parse_warnings = parse_z_blocks(text)
            warnings.extend(f'{rel}: {w}' for w in parse_warnings)
            for block in blocks:
                parsed = interpret_z_args(block)
                if _is_reshalka(rel):
                    if parsed['name']:
                        solutions_by_name.setdefault(parsed['name'], parsed)
                else:
                    conditions.append((rel, parsed))

        if not conditions:
            raise CommandError(
                f'ЛЭШ: в {root} не найдено ни одного блока \\z в подборках')

        seen_prefixes = set()
        unique = []
        internal_dups = 0
        for rel, parsed in conditions:
            statement = parsed['statement']
            if not statement:
                continue
            prefix = statement[:DEDUP_PREFIX]
            if prefix in seen_prefixes:
                internal_dups += 1
                continue
            seen_prefixes.add(prefix)
            unique.append((rel, parsed))

        created = skipped_existing = converted = 0
        matched = unmatched = with_parts = with_images = 0

        for rel, parsed in unique:
            if limit is not None and created + skipped_existing >= limit:
                break
            statement = parsed['statement']
            key = external_key(statement)
            seen_before = key in already
            if seen_before and do_apply:
                skipped_existing += 1
                continue

            name = parsed['name'] or ''
            sol_parsed = solutions_by_name.get(name) if name else None
            if sol_parsed is not None:
                matched += 1
            else:
                unmatched += 1
                warnings.append(
                    f'{rel} [{name}]: решение по названию не найдено — '
                    f'поле solution остаётся пустым (подбор по смыслу запрещён)')

            existing_parts = [
                (str(i + 1), subpoint)
                for i, subpoint in enumerate(parsed['subpoints'])
            ]
            result = convert_for_import(
                statement=statement,
                answer='',
                solution=solution_text(sol_parsed),
                existing_parts=existing_parts,
            )
            converted += 1
            warnings.extend(f'{rel} [{name}]: {w}' for w in result['warnings'])
            if result['parts']:
                with_parts += 1
            if result['images']:
                with_images += 1

            if do_apply:
                note_bits = [f'{rel} :: {name or "(без названия)"}']
                if parsed['points']:
                    note_bits.append(f'баллы: {parsed["points"]}')
                if parsed['source']:
                    note_bits.append(f'источник: {parsed["source"]}')
                create_problem(
                    source=source,
                    external_id=key,
                    title=name,
                    statement_md=result['statement_md'],
                    answer_md='',
                    solution_md=result['solution_md'],
                    parts=result['parts'],
                    difficulty=None,
                    difficulty_native='',
                    reference_note=' | '.join(note_bits),
                    reference_year=2026,
                )
            if seen_before:
                skipped_existing += 1
            else:
                created += 1
                already.add(key)

        after = {
            'Problem': Problem.objects.count(),
            'ProblemPart': ProblemPart.objects.count(),
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
            f'ЛЭШ 2026 Гамма — {mode}',
            f'  корень: {root}',
            f'  файлов .tex прочитано: {files_read} '
            f'(исключены misc/, «Пример и шаблон/», качи.tex)',
            f'  блоков \\z в подборках: {len(conditions)}, '
            f'названий в решалках: {len(solutions_by_name)}',
            f'  дублей внутри корпуса (первые {DEDUP_PREFIX} симв. условия): {internal_dups}',
            f'  уникальных задач-кандидатов: {len(unique)}',
            f'  импортировано: {created}',
            f'  уже импортировано: {skipped_existing}',
            f'  прогнано через конвертер: {converted}',
            f'  решение найдено по названию: {matched}',
            f'  без решения: {unmatched} — поле solution пустое, '
            f'подбор по смыслу НЕ выполнялся',
            f'  с подпунктами: {with_parts}',
            f'  с картинками: {with_images}',
            '  сложность: у макроса \\z второй аргумент — баллы, а не сложность; '
            'difficulty=NULL, баллы сохранены в заметке привязки',
            f'  счётчики: было {before}, стало {after}',
        ]
        if limit is not None:
            lines.append(f'  ⚠️ ОХВАТ УСЕЧЁН: --limit {limit} — '
                         f'обработана только часть корпуса')
        lines.append('  ' + write_warnings(
            'lesh_warnings.txt', warnings, converted, options.get('report_dir')))
        self.stdout.write(self.style.SUCCESS('\n'.join(lines)))
