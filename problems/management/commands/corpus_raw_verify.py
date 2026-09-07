# -*- coding: utf-8 -*-
"""Проверка карты «задача → фрагмент `.tex`» человеческими глазами.

Карта из `corpus_raw_index` — основание для всей дальнейшей работы:
по ней будут восстанавливаться потерянные рисунки и недостающие куски
условия. Ошибка здесь тиражируется на тысячи задач, поэтому карта не
принимается на веру, а показывается парами «что в базе / что в
исходнике» на случайной выборке с явным сидом.

Команда ТОЛЬКО ЧИТАЕТ. Кроме показа она считает объективную меру —
долю слов задачи, найденных во фрагменте: глаз проверяет смысл,
число ловит систематический сдвиг на масштабе.
"""
import json
import os
import random

from django.core.management.base import BaseCommand, CommandError

from problems.corpus_converter import raw_sources as rs
from problems.models import Problem, SourceReference

RAW = os.path.join('C:', os.sep, 'Users', 'shipu', 'weconomics-data', '_raw2026')
LEGACY = {14: 'archive3', 13: 'matek', 3: 'lsh2025', 16: 'reshalki'}
#: Запас вокруг найденного фрагмента: границы задачи чуть шире, чем
#: совпавшая проза (заголовок, `\item`, картинка сразу за текстом).
PAD = 400


class Command(BaseCommand):
    help = 'Показать пары «задача в базе / фрагмент исходника» для проверки.'

    def add_arguments(self, parser):
        parser.add_argument('--raw', default=RAW)
        parser.add_argument('--sample', type=int, default=40)
        parser.add_argument('--seed', type=int, default=20260830)
        parser.add_argument('--chars', type=int, default=340,
                            help='Сколько символов показывать с каждой стороны')
        parser.add_argument('--ids', default='',
                            help='Явные id через запятую вместо выборки')
        parser.add_argument('--measure-all', action='store_true',
                            help='Только числа: покрытие по всей карте')

    def handle(self, *args, **options):
        raw = options['raw']
        path = os.path.join(raw, 'index', 'mapping.json')
        if not os.path.exists(path):
            raise CommandError('Нет %s — сначала corpus_raw_index.' % path)
        mapping = json.load(open(path, encoding='utf-8'))

        src_of = {}
        for pid, sid in SourceReference.objects.values_list('problem_id',
                                                            'source_id'):
            if sid in LEGACY:
                src_of[pid] = LEGACY[sid]

        if options['measure_all']:
            return self._measure(raw, mapping, src_of)

        if options['ids']:
            ids = [int(x) for x in options['ids'].split(',') if x.strip()]
        else:
            pool = sorted(int(k) for k in mapping if int(k) in src_of)
            rnd = random.Random(options['seed'])
            ids = rnd.sample(pool, min(options['sample'], len(pool)))
            ids.sort()

        cut = options['chars']
        good = 0
        for pid in ids:
            rec = mapping[str(pid)][0]
            problem = Problem.objects.filter(pk=pid).first()
            if problem is None:
                continue
            cover = self._coverage(problem, self._fragment(raw, rec))
            good += cover >= 0.5
            self.stdout.write('=' * 78)
            self.stdout.write(
                '#%d  %s  %s/%s  окон=%d  покрытие=%.0f %%'
                % (pid, src_of.get(pid, '?'), rec['slot'], rec['rel'],
                   rec['hits'], 100 * cover))
            self.stdout.write('--- БАЗА ---')
            self.stdout.write(self._flat(problem.statement)[:cut])
            self.stdout.write('--- ИСХОДНИК ---')
            # Показ идёт РОВНО с начала совпадения. С левым запасом первые
            # экраны занял бы сам запас, и сравнить было бы нечего —
            # именно так первая проверка и выглядела «совпадающей на 100 %»
            # при визуально несовпадающих кусках.
            self.stdout.write(self._flat(self._fragment(raw, rec, left=0))[:cut])
        self.stdout.write('')
        self.stdout.write('показано: %d, покрытие >= 50 %%: %d (%.0f %%)'
                          % (len(ids), good, 100.0 * good / max(1, len(ids))))

    # ----------------------------------------------------------------

    def _fragment(self, raw, rec, left=PAD, right=PAD):
        full = os.path.join(raw, rec['slot'], rec['rel'].replace('/', os.sep))
        try:
            text = rs.read_text(full)
        except OSError:
            return ''
        a = max(0, rec['start'] - left)
        b = min(len(text), rec['end'] + right)
        return text[a:b]

    @staticmethod
    def _flat(text):
        return ' '.join((text or '').split())

    @staticmethod
    def _coverage(problem, fragment):
        """Доля значимых слов УСЛОВИЯ задачи, найденных во фрагменте."""
        want = rs.plain_words(problem.statement or '')
        if not want:
            return 0.0
        have = set(rs.plain_words(fragment, tex=True, mask=False))
        return sum(1 for w in want if w in have) / len(want)

    def _measure(self, raw, mapping, src_of):
        """Покрытие по всей карте — систематический сдвиг виден только так."""
        buckets = {}
        cache = {}
        qs = Problem.objects.filter(pk__in=[int(k) for k in mapping
                                            if int(k) in src_of])
        for problem in qs.iterator(chunk_size=500):
            rec = mapping[str(problem.pk)][0]
            key = (rec['slot'], rec['rel'])
            if key not in cache:
                full = os.path.join(raw, rec['slot'],
                                    rec['rel'].replace('/', os.sep))
                try:
                    cache[key] = rs.read_text(full)
                except OSError:
                    cache[key] = ''
                if len(cache) > 40:
                    cache.pop(next(iter(cache)))
            text = cache[key]
            a = max(0, rec['start'] - PAD)
            b = min(len(text), rec['end'] + PAD)
            cover = self._coverage(problem, text[a:b])
            slug = src_of[problem.pk]
            row = buckets.setdefault(slug, [0, 0, 0, 0])
            row[0] += 1
            row[1] += cover
            row[2] += cover >= 0.5
            row[3] += cover >= 0.9
        self.stdout.write('%-10s %7s %9s %9s %9s'
                          % ('источник', 'задач', 'среднее', '>=50 %', '>=90 %'))
        for slug, (n, s, c50, c90) in sorted(buckets.items()):
            self.stdout.write('%-10s %7d %8.0f %% %8.0f %% %8.0f %%'
                              % (slug, n, 100 * s / n, 100 * c50 / n,
                                 100 * c90 / n))
