"""Перепись задач, ссылающихся на картинку, которой у нас нет. ТОЛЬКО ЧИТАЕТ.

Два детектора (см. ``problems/missing_figures.py``):

* **метод А** — явная разметка (`![]()`, `\\includegraphics`, `<img>`, голый
  URL на файл картинки);
* **метод Б** — словесная отсылка («см. рисунок», «на графике ниже»,
  «The graph below»), нужная для источников, перебитых из PDF руками.

    manage.py figure_census                # таблица по всем источникам
    manage.py figure_census --samples 20   # + примеры совпадений

Команда ничего не пишет в базу. Скрытие — отдельная команда
``hide_missing_figures``.
"""

import random

from django.core.management.base import BaseCommand

from problems.models import Problem
from problems.missing_figures import scan_problems, unsolvable_ids


class Command(BaseCommand):
    help = ('Считает задачи, ссылающиеся на недоступную картинку, '
            'по каждому источнику. Ничего не меняет.')

    def add_arguments(self, parser):
        parser.add_argument('--samples', type=int, default=0,
                            help='показать N случайных совпадений')
        parser.add_argument('--source', default='',
                            help='ограничить одним источником (подстрока)')

    def handle(self, *args, **opts):
        say = self.stdout.write
        found = scan_problems()
        if opts['source']:
            needle = opts['source'].lower()
            found = {k: v for k, v in found.items()
                     if needle in v['source'].lower()}
        unsolvable = unsolvable_ids(found)

        # ── раскладка по источникам ────────────────────────────────────
        rows = {}
        for pid, hit in found.items():
            row = rows.setdefault(hit['source'], {
                'a': 0, 'b_stmt': 0, 'b_sol': 0, 'no_data': 0,
                'published': 0, 'hidden': 0})
            if hit['method_a']:
                row['a'] += 1
            if hit['method_b_statement']:
                row['b_stmt'] += 1
            elif not hit['method_a']:
                row['b_sol'] += 1
            if pid in unsolvable:
                if not hit['has_data']:
                    row['no_data'] += 1
                if hit['status'] == Problem.Status.PUBLISHED:
                    row['published'] += 1
                if hit['status'] == Problem.Status.HIDDEN:
                    row['hidden'] += 1

        head = (f'{"Источник":<36}{"А":>5}{"Б.усл":>7}{"Б.реш":>7}'
                f'{"без данных":>12}{"published":>11}{"уже hidden":>12}')
        say(head)
        say('-' * len(head))
        total = {k: 0 for k in ('a', 'b_stmt', 'b_sol', 'no_data',
                                'published', 'hidden')}
        for src in sorted(rows, key=lambda s: -(rows[s]['a'] + rows[s]['b_stmt'])):
            r = rows[src]
            for k in total:
                total[k] += r[k]
            say(f'{src[:35]:<36}{r["a"]:>5}{r["b_stmt"]:>7}{r["b_sol"]:>7}'
                f'{r["no_data"]:>12}{r["published"]:>11}{r["hidden"]:>12}')
        say('-' * len(head))
        say(f'{"ИТОГО":<36}{total["a"]:>5}{total["b_stmt"]:>7}'
            f'{total["b_sol"]:>7}{total["no_data"]:>12}'
            f'{total["published"]:>11}{total["hidden"]:>12}')
        say('')
        say(f'Задач с недоступной картинкой всего: {len(found)}')
        say(f'Из них НЕ РЕШАЮТСЯ без картинки (метод А где угодно либо '
            f'метод Б в условии): {len(unsolvable)}')
        say(f'Только иллюстрация к разбору (метод Б лишь в решении): '
            f'{len(found) - len(unsolvable)} — эти НЕ прячем')

        if opts['samples']:
            say('')
            say('=== примеры ===')
            random.seed(20260824)
            for pid in random.sample(sorted(unsolvable),
                                     min(opts['samples'], len(unsolvable))):
                hit = found[pid]
                frags = [m for v in hit['method_b_statement'].values()
                         for m in v][:3]
                say(f'  id={pid} [{hit["source"][:28]}] {hit["status"]} '
                    f'A={list(hit["method_a"])} Б={frags}')
