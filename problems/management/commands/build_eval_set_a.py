# -*- coding: utf-8 -*-
"""Набор A измерителя (С14) — эталон для функции «Похожие задачи».

ТОЛЬКО ЧИТАЕТ БАЗУ. Результат — файл `problems/data/eval_set_a.json`.

⚠️ ПОЧЕМУ НЕ ИЗ ТАБЛИЦЫ `DuplicateCandidate`. `EMBEDDINGS.md` предлагает взять
эталон из подтверждённых пар как «размеченный людьми». В базе таких пар
10 731, и все они со статусом «подтверждён» — но `reviewed_by` и `reviewed_at`
пусты у каждой, все записи созданы за шесть секунд 08.06.2026, а статус
проставила команда `process_duplicates` автоматически по порогу косинуса
≥ 0,95. Человек не смотрел ни одной пары.

Взять их эталоном — замкнуть круг: пары отобраны близостью ТЕХ САМЫХ
векторов, которые измеритель и проверяет, поэтому recall вышел бы около
единицы и не значил бы ничего. Признак обязан быть независим от измеряемого,
поэтому пары строятся по совпадению нормализованного ТЕКСТА условия.

⚠️ ЧТО ЭТОТ НАБОР МЕРИТ И ЧЕГО НЕ МЕРИТ. Он мерит «задача → задача», то есть
блок «Похожие задачи», и служит сторожем регрессии: поменяли формулу
отпечатка — сразу видно, не развалился ли блок. Это НЕ поиск по описанию,
цифры отсюда с наборами B и C не сравниваются.

Запуск:
    manage.py build_eval_set_a
    manage.py build_eval_set_a --min-len 120 --limit 500
"""
from django.core.management.base import BaseCommand

from problems.eval_sets import (
    DATA_DIR,
    MIN_STATEMENT_LEN,
    group_duplicates_by_text,
    save_eval_set,
)
from problems.models import Problem
from problems.search_eval_metrics import EvalCase


class Command(BaseCommand):
    help = 'Собрать эталонный набор A (дубликаты по тексту) для search_eval.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--min-len', type=int, default=MIN_STATEMENT_LEN,
            help='Минимальная длина нормализованного условия (по умолчанию '
                 f'{MIN_STATEMENT_LEN}). Короткие тексты вроде «Найдите '
                 'равновесие» встречаются сотнями и одинаковой задачей не '
                 'делают.')
        parser.add_argument(
            '--limit', type=int, default=None,
            help='Взять не больше N групп (для быстрой проверки).')
        parser.add_argument(
            '--out', default=str(DATA_DIR / 'eval_set_a.json'),
            help='Куда записать набор.')

    def handle(self, *args, **options):
        min_len = options['min_len']

        # Только задачи с вектором: без него задача физически недостижима,
        # и включать её в эталон значит заранее записать себе провал.
        rows = list(
            Problem.objects
            .filter(embedding__isnull=False)
            .values_list('id', 'statement')
        )
        self.stdout.write(f'Задач с вектором: {len(rows)}')

        группы = group_duplicates_by_text(rows, min_len=min_len)
        if options['limit']:
            группы = группы[:options['limit']]

        случаи = []
        for группа in группы:
            представитель, *остальные = группа
            случаи.append(EvalCase(
                # Запрос — сама задача, а не её текст: режим 'problem'.
                query='',
                relevant_ids=остальные,
                meta={'query_problem_id': представитель,
                      'group_size': len(группа)},
            ))

        предупреждения = [
            'Пары построены по совпадению нормализованного текста условия, '
            'а НЕ из таблицы DuplicateCandidate: все 10 731 пары там '
            'проставлены автоматически по косинусу >= 0,95 (reviewed_by и '
            'reviewed_at пусты у всех), то есть тем же мерилом, которое '
            'проверяется. Это замкнутый круг, эталоном служить не может.',
            'Набор мерит функцию «Похожие задачи» (задача -> задача), а не '
            'поиск по описанию. С наборами B и C цифры не сравниваются.',
            'Тексты внутри группы совпадают дословно, поэтому задача для '
            'поиска лёгкая по построению. Это сторож регрессии, а не оценка '
            'сложности: он ловит поломку блока «Похожие», а не измеряет, '
            'насколько поиск умён.',
        ]

        путь = save_eval_set(
            options['out'], name='A',
            description='Дубликаты по совпадению нормализованного текста '
                        'условия. Эталон функции «Похожие задачи».',
            cases=случаи, warnings=предупреждения, mode='problem')

        всего_задач = sum(c.meta['group_size'] for c in случаи)
        self.stdout.write(self.style.SUCCESS(
            f'Готово: {len(случаи)} групп, {всего_задач} задач в них.\n'
            f'Записано: {путь}'))
