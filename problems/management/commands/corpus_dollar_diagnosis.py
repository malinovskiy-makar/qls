# -*- coding: utf-8 -*-
"""Сессия 2026-08-27: диагностика разрыва `$$` МЕЖДУ полями (найдена
побочно при разборе #47127). READ-ONLY — только считает, ничего не
пишет в базу и не трогает `content_format`.

Полное описание диагноза и живые примеры — reports/corpus_converter_
scaleup/reshalki_dollar_diagnosis.md. Этот файл — тестируемый счётчик,
на числах которого держится отчёт (бриф сессии прямо требует тестов на
парсер, если он написан, а не только диагностику без кода).

Рендерер (`problems/rendering.py::render_markdown`) вызывается по
каждому полю (`statement`/`answer`/`solution`/`part.statement`/
`part.answer`) НЕЗАВИСИМО (см. `catalog/templates/catalog/
problem_detail.html`), поэтому непарный `$$` в конце одного поля и
непарный `$$` в начале следующего — не одна формула, разорванная на
две, а две отдельные поломки рендера, каждая в своём поле."""
from django.core.management.base import BaseCommand

from problems.models import Problem

SOURCES = {
    'archive3': (14, 'Overleaf Archive 3 (ОШ/ЛШ Олмат)'),
    'matek': (13, 'МатЭк — Overleaf архивы (2021–2025)'),
    'lsh2025': (3, 'ЛШ Олмат 2025 (Overleaf)'),
    'reshalki': (16, 'Решалки Олмат (olmat41)'),
}
EXCLUDED_SOURCE_NAME = 'Служебное: фикстуры рендерера (не публиковать)'

#: порядок полей ровно как их рендерит catalog/templates/catalog/
#: problem_detail.html — statement, затем части по порядку, затем
#: answer, затем solution.
TOP_FIELDS = ('statement', 'answer', 'solution')


def unescaped_dollar_dollar_positions(text):
    """Позиции НЕэкранированных вхождений `$$` в тексте одного поля.

    Посимвольно зеркалит пропуск `\\$` из problems.rendering.
    _protect_math_and_currency: экранированная валюта (`\\$100`) не
    разделитель формулы и не считается вовсе."""
    positions = []
    i, n = 0, len(text or '')
    while i < n:
        if text[i] == '\\' and i + 1 < n and text[i + 1] == '$':
            i += 2
            continue
        if text[i:i + 2] == '$$':
            positions.append(i)
            i += 2
            continue
        i += 1
    return positions


def field_dollar_info(text):
    """(число_$$_токенов, кончается_ли_поле_непарным_$$, начинается_ли_
    поле_непарным_$$).

    «Кончается/начинается» — после/до найденного токена в тексте
    остаются только пробелы: это позиционный признак «висящего на
    границе поля» токена, не любого `$$` где-то внутри."""
    if not text:
        return 0, False, False
    positions = unescaped_dollar_dollar_positions(text)
    if not positions:
        return 0, False, False
    ends = text[positions[-1] + 2:].strip() == ''
    starts = text[:positions[0]].strip() == ''
    return len(positions), ends, starts


def find_boundary_pairs(fields, order):
    """Пары полей (A, B), где A кончается непарным `$$`, B сразу следом
    в порядке `order` начинается непарным `$$`, и У ОБОИХ число
    `$$`-токенов нечётное.

    Требование нечётности с обеих сторон — не техническая мелочь: без
    него два САМОСТОЯТЕЛЬНО целых поля (у каждого чётное число `$$`,
    просто одно случайно кончается, а другое случайно начинается на
    `$$`) дали бы ложное совпадение. Нечётность — гарантия, что
    «висящий» токен ДЕЙСТВИТЕЛЬНО не имеет пары внутри своего же поля."""
    info = {name: field_dollar_info(text) for name, text in fields.items()}
    pairs = []
    names = [name for name in order if name in fields]
    for a in names:
        cnt_a, ends_a, _ = info[a]
        if not (cnt_a % 2 == 1 and ends_a):
            continue
        for b in names:
            if a == b:
                continue
            cnt_b, _, starts_b = info[b]
            if cnt_b % 2 == 1 and starts_b:
                pairs.append((a, b))
    return pairs


class Command(BaseCommand):
    help = (
        'READ-ONLY: точный счётчик разрыва $$ между полями по всем 4 '
        'легаси-источникам. Числа — основа reports/corpus_converter_'
        'scaleup/reshalki_dollar_diagnosis.md.'
    )

    def handle(self, *args, **options):
        for slug, (source_id, source_name) in SOURCES.items():
            qs = (
                Problem.objects.filter(source_references__source_id=source_id)
                .exclude(source_references__source__name=EXCLUDED_SOURCE_NAME)
                .distinct()
                .prefetch_related('parts')
            )
            total = qs.count()
            odd_problems = set()
            odd_fields_total = 0
            boundary_problem_ids = set()
            boundary_shapes = {}
            other_odd = 0

            for problem in qs.iterator(chunk_size=500):
                fields = {name: getattr(problem, name) or '' for name in TOP_FIELDS}
                for part in problem.parts.all():
                    fields[f'part[{part.label}].statement'] = part.statement or ''
                    fields[f'part[{part.label}].answer'] = part.answer or ''

                info = {name: field_dollar_info(text) for name, text in fields.items()}
                odd_names = {name for name, (cnt, _, _) in info.items() if cnt % 2 == 1}
                if odd_names:
                    odd_problems.add(problem.id)
                    odd_fields_total += len(odd_names)

                pairs = find_boundary_pairs(fields, order=list(fields.keys()))
                matched_names = {name for pair in pairs for name in pair}
                if pairs:
                    boundary_problem_ids.add(problem.id)
                    for a, b in pairs:
                        key = (a.split('[')[0], b.split('[')[0])
                        boundary_shapes[key] = boundary_shapes.get(key, 0) + 1
                other_odd += len(odd_names - matched_names)

            self.stdout.write(
                f'{source_name}: {total} задач | '
                f'нечётных задач {len(odd_problems)} | '
                f'нечётных полей {odd_fields_total} | '
                f'разрыв между полями {len(boundary_problem_ids)} | '
                f'прочих нечётных полей {other_odd} | '
                f'формы пар {boundary_shapes}'
            )

        problems_after = Problem.objects.count()
        self.stdout.write(self.style.SUCCESS(
            f'Готово. Read-only: Problem.objects.count() = {problems_after} '
            '(команда его не меняла — не сравнивается с "до", т.к. запрос '
            'не создавал/не удалял задачи по построению; никаких .save()/'
            '.create()/.delete() в этом файле нет).'
        ))
