# -*- coding: utf-8 -*-
"""Документная частота терминов словаря по всему корпусу (Б1).

Один проход по каждой задаче (условие + подпункты), находит термины по
правилам `problems/enrich/shortlist.py` и кладёт результат в
`data/econ_terms_df.json` — читает его дальше `shortlist_for()` на каждом
вызове пилота обогащения, чтобы не считать это заново на каждой задаче.

Печатает три инварианта, которые владелец смотрит перед прогоном: медиану
числа найденных терминов на задачу и доли задач, где нашлось меньше 15 или
больше 40 — это первый сигнал, если правила отбора ведут себя не так, как
задумано (например, слишком жадно матчат короткие слова).

Запуск:
    venv313\\Scripts\\python.exe manage.py build_econ_terms_df
"""
from django.core.management.base import BaseCommand

from problems.enrich.shortlist import (
    compute_document_frequencies, corpus_invariants, save_df_cache,
)
from problems.enrich.text import problem_full_text
from problems.models import Problem


class Command(BaseCommand):
    help = 'Документная частота терминов словаря по всему корпусу (Б1).'

    def handle(self, *args, **options):
        qs = Problem.objects.all().prefetch_related('parts').order_by('id')
        texts = (problem_full_text(p.statement, p.parts.all())
                 for p in qs.iterator(chunk_size=300))
        df, found_counts = compute_document_frequencies(texts)
        save_df_cache(df)

        stats = corpus_invariants(found_counts)
        self.stdout.write('Задач обработано: {:,}'.format(len(found_counts)))
        self.stdout.write(
            'Медиана найденных терминов на задачу: {}'.format(stats['median']))
        self.stdout.write(
            'Доля задач с находками < 15: {:.1%}'.format(stats['share_below_15']))
        self.stdout.write(
            'Доля задач с находками > 40: {:.1%}'.format(stats['share_above_40']))
        self.stdout.write(
            'Кэш записан: data/{} ({} терминов)'.format(
                'econ_terms_df.json', len(df)))
