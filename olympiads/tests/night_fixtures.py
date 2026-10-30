"""Фикстуры ночи 30.10: маленькая «ВсОШ» с устройством настоящей базы.

Повторяет то, на чём ломаются экраны: туры «1» и «2», общий комплект
«10-11», комплект без классов, сезон без комплектов посреди диапазона,
повтор комплекта (`duplicate_of`), скрытая олимпиада и заглушка.
"""
from decimal import Decimal

from olympiads.models import (Olympiad, OlympiadStage, OlympiadVariant,
                              OlympiadVariantGrade, OlympiadVariantItem)
from problems.models import Problem

CRITERIA = (
    '## Критерии оценивания\n'
    'K1 Найден оптимум → 2 балла\n'
    'K2 Посчитан экспорт → 2 балла\n'
    'K3 Если выписан ответ без обоснования, то 0 баллов\n')


def olympiad(slug='vs', **extra):
    defaults = dict(name_full='Тестовая олимпиада', name_short=slug.upper(),
                    organizer='Никто', kind=Olympiad.Kind.VSOSH,
                    is_published=True, grade_min=9, grade_max=11,
                    manual_rank=100)
    defaults.update(extra)
    return Olympiad.objects.create(slug=slug, **defaults)


def stage(olymp, code='final', order=4, minutes=210, max_score=48):
    return OlympiadStage.objects.create(
        olympiad=olymp, code=code, name='Заключительный этап', order=order,
        duration_minutes=minutes, max_score=max_score)


_counter = {'n': 0}


def problem(statement='Условие', solution='Разбор', answer='', **extra):
    _counter['n'] += 1
    return Problem.objects.create(
        title='Задача %d' % _counter['n'],
        statement='%s %d' % (statement, _counter['n']),
        solution=solution, answer=answer, **extra)


def kit(olymp, stg, season, tour='1', grades=(11,), tasks=4, score=12,
        criteria=True, **extra):
    """Комплект с позициями. `score=None` — позиции без балла."""
    start = int(season.split('/')[0])
    variant = OlympiadVariant.objects.create(
        olympiad=olymp, stage=stg, season=season, year=start + 1, tour=tour,
        grade_raw='-'.join(str(g) for g in grades),
        kit_key='%s-%s-%s-%s-%s-%d' % (olymp.slug, stg.code, season, tour,
                                    '-'.join(map(str, grades)) or 'all',
                                    OlympiadVariant.objects.count()),
        **extra)
    for grade in grades:
        OlympiadVariantGrade.objects.create(variant=variant, grade=grade)
    for number in range(1, tasks + 1):
        prob = problem(solution='Разбор задачи.\n\n' + CRITERIA if criteria
                       else 'Разбор задачи.')
        OlympiadVariantItem.objects.create(
            variant=variant, problem=prob, number=str(number), order=number,
            ref_key='%s:%d' % (variant.kit_key, number),
            max_score=Decimal(score) if score is not None else None,
            has_solution=True, has_criteria=criteria)
    return variant


def mini_vsosh():
    """Олимпиада с заключительным этапом на 31 сезон 1995/96–2025/26."""
    olymp = olympiad('vs')
    final = stage(olymp)
    kits = {}
    for start in range(1995, 2026):
        season = '%d/%02d' % (start, (start + 1) % 100)
        if start == 2019:
            continue                      # сезон без комплектов
        if start == 2016:
            kits[season] = [kit(olymp, final, season, tour='1', grades=()),
                            kit(olymp, final, season, tour='2', grades=())]
        elif start in (2017, 2018):
            kits[season] = [kit(olymp, final, season, tour='1', grades=(9,)),
                            kit(olymp, final, season, tour='1',
                                grades=(10, 11))]
        else:
            kits[season] = [kit(olymp, final, season, tour=t, grades=(g,))
                            for g in (9, 10, 11) for t in ('1', '2')]
    return olymp, final, kits
