"""
Команда benchmark_search — замер качества семантического поиска.

Прогоняет 5 фиксированных тестовых запросов через catalog.semantic.search()
и печатает топ-10 результатов с баллами. Используется для сравнения «до» и «после»
апгрейда модели эмбеддингов.

Запуск:
    ./venv/bin/python manage.py benchmark_search
    ./venv/bin/python manage.py benchmark_search > reports/bge_benchmark/before_minilm.txt
"""

import os
import sys
import time
from django.core.management.base import BaseCommand

QUERIES = [
    "Известно изменение цены и точечная эластичность спроса. Найти изменение количества.",
    "Несколько индивидуальных групп спроса с разным числом людей в каждой группе; "
    "в задаче меняется количество потребителей в каждой группе.",
    "Единственный продавец на рынке выбирает объём выпуска и цену для максимальной прибыли; "
    "даны функция спроса и функция издержек.",
    "На товар вводят налог. Найти, как налоговое бремя делится между покупателем и продавцом "
    "и чему равны потери общества.",
    "Две страны производят два товара с разной производительностью. Определить сравнительное "
    "преимущество и условия взаимовыгодной торговли.",
]


class Command(BaseCommand):
    help = 'Замер качества семантического поиска (5 тестовых запросов, топ-10)'

    def handle(self, *args, **options):
        from catalog.semantic import search

        self.stdout.write('=' * 80)
        self.stdout.write('ЗАМЕР СЕМАНТИЧЕСКОГО ПОИСКА — топ-10 по каждому запросу')
        self.stdout.write('=' * 80)
        self.stdout.write('')

        summary_lines = []

        for q_idx, query in enumerate(QUERIES, start=1):
            self.stdout.write(f'── Запрос {q_idx}/5 ──────────────────────────────────────────────────────────')
            self.stdout.write(f'  {query}')
            self.stdout.write('')

            t0 = time.time()
            results = search(query, content_kind='all', limit=10)
            elapsed = time.time() - t0

            if not results:
                self.stdout.write('  [Нет результатов]')
                self.stdout.write('')
                summary_lines.append(f'Q{q_idx}: нет результатов')
                continue

            for rank, r in enumerate(results, start=1):
                p = r['problem']
                score_pct = r['score'] * 100
                title = (p.title or '')[:70]
                stmt = (p.statement or '')[:80].replace('\n', ' ')
                self.stdout.write(
                    f'  #{rank:2d}  {score_pct:5.1f}%  id={p.pk:<6}  '
                    f'title={title!r}'
                )
                self.stdout.write(
                    f'           stmt: {stmt!r}'
                )

            self.stdout.write('')

            top1_score = results[0]['score'] * 100
            top5_scores = [r['score'] * 100 for r in results[:5]]
            avg_top5 = sum(top5_scores) / len(top5_scores)

            summary_line = (
                f'Q{q_idx}: топ-1={top1_score:.1f}%  '
                f'топ-5 avg={avg_top5:.1f}%  '
                f'[{", ".join(f"{s:.1f}" for s in top5_scores)}]  '
                f'({elapsed:.2f}с)'
            )
            self.stdout.write(f'  Итог: {summary_line}')
            self.stdout.write('')
            summary_lines.append(summary_line)

        self.stdout.write('=' * 80)
        self.stdout.write('СВОДКА')
        self.stdout.write('=' * 80)
        for line in summary_lines:
            self.stdout.write(f'  {line}')
        self.stdout.write('')
