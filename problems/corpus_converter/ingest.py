# -*- coding: utf-8 -*-
r"""Общая часть боевого INSERT новых источников (Школково, SolveHub, ЛЭШ).

Три команды импорта делают одно и то же и различаются только разбором
своего формата с диска. Всё, что у них общее, живёт здесь: путь к данным,
канонизация текста, хэш, создание `Problem`/`ProblemPart`/`Rubric`/
`SourceReference` одной транзакцией.

**Почему свой конвейер, а не `convert_problem_v2`.** `convert_problem_v2`
дополнительно ВЫРЕЗАЕТ TikZ из текста и подменяет его маркером
`[[FIGURE:<hex>]]`. Для легаси это безопасно: там в базе лежит исходный
текст, а конвертер запускается на лету. Здесь в базу ложится результат
конвертера — и маркер вместо TikZ означал бы, что исходный код картинки
потерян навсегда: `corpus_build_figures` ищет TikZ в СОХРАНЁННОМ тексте
(`problem.statement`), а маркера ему мало. Плюс pdflatex в этой среде не
установлен, собрать картинку прямо сейчас нечем, и маркер без строки
`ProblemFigure` на экране просто исчезает (`problems/figures.py`) —
график пропал бы молча. Поэтому TikZ остаётся в тексте как есть: он
виден, шлюз `render_preflight_v2` честно забракует такую задачу кодом
`PLOT`, а собрать картинки можно будет позже, ничего не переимпортируя.

Остальные стадии — ровно те же и в том же порядке, что у легаси
(`preflight_gate.polish_field`): стадия 1 `core.convert_problem`, затем
Фазы 4 (текстовые окружения) → 5 (опечатки макросов) → 1 (канонизация
математики).
"""
from __future__ import annotations

import hashlib
import os

from django.conf import settings
from django.core.management.base import CommandError
from django.db import transaction

from problems.corpus_converter.core import convert_problem
from problems.corpus_converter.macros import apply_macro_fixes
from problems.corpus_converter.math_canon import canonicalize
from problems.corpus_converter.text_env import convert_text_environments
from problems.models import (
    Problem, ProblemPart, Rubric, RubricCriterion, Source, SourceReference,
)

#: Данные трёх источников лежат ВНЕ репозитория, в соседней папке
#: `weconomics-data/`. Путь берётся от родителя BASE_DIR — и это ловушка:
#: в git worktree BASE_DIR другой, и родитель указывает в пустоту.
#: Переменная окружения перекрывает путь; отсутствие папки — громкая
#: ошибка, а не «прочитано 0 задач» (ровно так `corpus_pilot_shkolkovo`
#: молча прочитал ноль записей при первом запуске в worktree).
ENV_DATA_ROOT = 'WECONOMICS_DATA_DIR'


def data_root():
    override = os.environ.get(ENV_DATA_ROOT)
    if override:
        return override
    return os.path.join(os.path.dirname(settings.BASE_DIR), 'weconomics-data')


def require_dir(path, what):
    """Папка обязана существовать и быть непустой — иначе CommandError."""
    if not os.path.isdir(path):
        raise CommandError(
            f'{what}: папки нет — {path}\n'
            f'Данные источников лежат вне репозитория. Задайте {ENV_DATA_ROOT} '
            f'или --data-dir, если корпус лежит в другом месте.'
        )
    if not os.listdir(path):
        raise CommandError(f'{what}: папка пуста — {path}')
    return path


def polish(text_md):
    """Фазы 4 → 5 → 1 поверх выхода стадии 1 — дословно тот же порядок и
    те же функции, что `preflight_gate.polish_field` применяет к легаси."""
    text = convert_text_environments(text_md or '')
    text = apply_macro_fixes(text)
    return canonicalize(text)


def convert_for_import(statement, answer='', solution='', existing_parts=None):
    """Стадия 1 + Фазы 4/5/1, БЕЗ вырезания TikZ (см. модульный docstring)."""
    result = convert_problem(
        statement=statement, answer=answer, solution=solution,
        existing_parts=existing_parts,
    )
    result['statement_md'] = polish(result['statement_md'])
    for part in result['parts']:
        part['statement_md'] = polish(part['statement_md'])
    result['answer_md'] = polish(result['answer_md'])
    result['solution_md'] = polish(result['solution_md'])
    return result


def content_hash_for(statement_md):
    """MD5 того, что реально ложится в `Problem.statement`.

    Нормализация ДО хэша — правило `problems/management/commands/CLAUDE.md`:
    иначе один и тот же текст с разными пробелами даёт разные хэши и
    `find_duplicates` сравнивает разные тексты."""
    return hashlib.md5(
        (statement_md or '').encode('utf-8'), usedforsecurity=False).hexdigest()


def get_or_create_source(name, **defaults):
    source, _created = Source.objects.get_or_create(name=name, defaults=defaults)
    return source


def imported_external_ids(source):
    """Внешние id, уже импортированные из этого источника.

    Ключ дедупликации импорта — `SourceReference.problem_number` («Номер
    задачи в источнике»), а НЕ `content_hash`: повторный запуск не должен
    создавать вторую копию, но и не должен отбрасывать задачу только за
    то, что её условие совпало с чужим (у SolveHub 366 таких совпадений,
    и они признаны вероятно ложными — короткие типовые формулировки)."""
    return set(
        SourceReference.objects.filter(source=source)
        .exclude(problem_number='')
        .values_list('problem_number', flat=True)
    )


def create_problem(*, source, external_id, title, statement_md, answer_md,
                   solution_md, parts, difficulty=None, difficulty_native='',
                   reference_note='', reference_url='', reference_year=None,
                   rubric_criteria=None):
    """Создать одну задачу целиком. Возвращает `Problem`.

    Каждый вызов — в собственном `transaction.atomic()`: на SQLite
    `IntegrityError` внутри общей транзакции отравляет родительский
    savepoint (ловушка из `problems/management/commands/CLAUDE.md`)."""
    with transaction.atomic():
        problem = Problem.objects.create(
            title=(title or '')[:300],
            statement=statement_md,
            answer=answer_md or '',
            solution=solution_md or '',
            difficulty=difficulty,
            difficulty_native=(difficulty_native or '')[:20],
            status=Problem.Status.DRAFT,
            content_format=Problem.ContentFormat.PLAIN,
            human_review=Problem.HumanReview.NONE,
            # Человек эти задачи ещё не видел — это НЕ оценка качества,
            # а третий, отдельный признак (CLAUDE.md, «Ручное ревью»).
            hidden_pending_review=True,
            content_hash=content_hash_for(statement_md),
        )
        for order, part in enumerate(parts or []):
            ProblemPart.objects.create(
                problem=problem,
                label=(part['label'] or '')[:10],
                statement=part['statement_md'],
                answer=part.get('answer', '') or '',
                solution=part.get('solution', '') or '',
                order=order,
            )
        SourceReference.objects.create(
            problem=problem,
            source=source,
            problem_number=str(external_id)[:50],
            note=(reference_note or '')[:300],
            url=reference_url or '',
            year=reference_year,
        )
        if rubric_criteria:
            rubric = Rubric.objects.create(
                problem=problem, name='Критерии оценивания')
            for order, criterion in enumerate(rubric_criteria):
                RubricCriterion.objects.create(
                    rubric=rubric,
                    name=(criterion['name'] or '')[:300],
                    max_points=criterion.get('max_points') or 0,
                    description=criterion.get('description', '') or '',
                    order=order,
                )
    return problem
