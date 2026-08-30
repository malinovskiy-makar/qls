# -*- coding: utf-8 -*-
"""Фаза 1: диагностика читаемости по 19 кодам аудита на всём корпусе.

Аудит владельца прошёл по выборке 3 000 карточек и нашёл 390 дефектных
(13,0 %). Здесь те же коды считает машина — и по ВСЕМ применённым
задачам, а не по выборке.

Команда ТОЛЬКО ЧИТАЕТ. Она ничего не чинит и ничего не прячет: её дело
— назвать числа и выдать список id по каждому коду. Скрытие непочиненного
— отдельный шаг (`quality_gate`), и он должен опираться на этот список,
а не на собственную вторую реализацию тех же проверок.

Замер идёт по тому, что видит ученик: `render_markdown` + подстановка
картинок `render_figures`, то есть дословно боевой конвейер показа.
Ширина формул (`OVER`, `OVER-M`) требует настоящего браузера и включается
флагом `--widths`: разбором строки ширину не узнать.
"""
import collections
import json
import os

from django.conf import settings
from django.core.management.base import BaseCommand

from problems.corpus_converter import render_codes as rc
from problems.figures import render_figures
from problems.models import Problem, SourceReference
from problems.rendering import render_markdown

LEGACY = {14: 'archive3', 13: 'matek', 3: 'lsh2025', 16: 'reshalki'}
OUT_DIR = os.path.join(settings.BASE_DIR, 'reports', 'corpus_render_codes')


class Command(BaseCommand):
    help = ('Диагностика 19 кодов читаемости по корпусу. Ничего не пишет '
            'в базу.')

    def add_arguments(self, parser):
        parser.add_argument('--all-formats', action='store_true',
                            help='включая plain (по умолчанию только markdown, '
                                 'потому что показывается именно он)')
        parser.add_argument('--limit', type=int, default=0)
        parser.add_argument('--widths', action='store_true',
                            help='мерить ширину формул настоящим браузером '
                                 '(коды OVER и OVER-M)')
        parser.add_argument('--report-dir', default=OUT_DIR)

    def handle(self, *args, **options):
        ids = set(SourceReference.objects
                  .filter(source_id__in=LEGACY)
                  .values_list('problem_id', flat=True))
        qs = Problem.objects.filter(pk__in=ids)
        if not options['all_formats']:
            qs = qs.filter(content_format='markdown')
        qs = qs.order_by('id').prefetch_related('parts', 'figures')
        if options['limit']:
            qs = qs[:options['limit']]

        source_of = {}
        for pid, sid in SourceReference.objects.filter(
                source_id__in=LEGACY).values_list('problem_id', 'source_id'):
            source_of.setdefault(pid, LEGACY[sid])

        by_code = collections.defaultdict(list)
        by_priority = collections.Counter()
        by_source_bad = collections.Counter()
        by_source_total = collections.Counter()
        details = {}
        total = clean = 0

        probe = self._open_probe() if options['widths'] else None
        try:
            for problem in qs.iterator(chunk_size=200):
                total += 1
                slug = source_of.get(problem.pk, '?')
                by_source_total[slug] += 1
                blocks, htmls = self._render(problem)
                svgs = [f.svg for f in problem.figures.all() if f.svg]
                found = rc.analyze_problem(blocks, htmls, figure_svgs=svgs)
                if probe is not None:
                    found.update(self._widths(probe, htmls))
                if not found:
                    clean += 1
                    continue
                by_source_bad[slug] += 1
                worst = min((rc.PRIORITY[c] for c in found), default='P2')
                by_priority[worst] += 1
                details[problem.pk] = sorted(found)
                for code in found:
                    by_code[code].append(problem.pk)
        finally:
            if probe is not None:
                probe.__exit__(None, None, None)

        report_dir = options['report_dir']
        os.makedirs(report_dir, exist_ok=True)
        with open(os.path.join(report_dir, 'codes.json'), 'w',
                  encoding='utf-8') as fh:
            json.dump({'by_code': {k: sorted(v) for k, v in by_code.items()},
                       'by_problem': {str(k): v for k, v in details.items()}},
                      fh, ensure_ascii=False)

        self.stdout.write('проверено задач: %d' % total)
        self.stdout.write('без единого кода: %d (%.1f %%)'
                          % (clean, 100.0 * clean / max(1, total)))
        self.stdout.write('с дефектом: %d (%.1f %%)'
                          % (total - clean,
                             100.0 * (total - clean) / max(1, total)))
        self.stdout.write('')
        self.stdout.write('по худшему приоритету карточки:')
        for prio in ('P0', 'P1', 'P2'):
            self.stdout.write('  %s  %6d' % (prio, by_priority[prio]))
        self.stdout.write('')
        self.stdout.write('%-12s %4s %7s   %s' % ('код', 'при', 'задач',
                                                  'что видит человек'))
        for code, lst in sorted(by_code.items(),
                                key=lambda kv: (rc.PRIORITY[kv[0]],
                                                -len(kv[1]))):
            self.stdout.write('%-12s %4s %7d   %s'
                              % (code, rc.PRIORITY[code], len(lst),
                                 rc.MEANING[code]))
        self.stdout.write('')
        self.stdout.write('%-10s %8s %8s %8s' % ('источник', 'задач',
                                                 'с деф.', 'доля'))
        for slug in sorted(by_source_total):
            n = by_source_total[slug]
            bad = by_source_bad[slug]
            self.stdout.write('%-10s %8d %8d %7.1f %%'
                              % (slug, n, bad, 100.0 * bad / max(1, n)))
        self.stdout.write('')
        self.stdout.write('отчёт: %s'
                          % os.path.join(report_dir, 'codes.json'))
        if probe is None:
            self.stdout.write('⚠ ширина формул НЕ мерилась: коды OVER и '
                              'OVER-M в числах отсутствуют (нужен --widths).')

    # ------------------------------------------------------------------

    @staticmethod
    def _render(problem):
        """Блоки и их HTML — дословно как на боевом показе."""
        blocks = [('Условие', '', problem.statement or '')]
        for part in problem.parts.all():
            blocks.append(('Часть %s' % part.label, '', part.statement or ''))
        if problem.answer:
            blocks.append(('Ответ', '', problem.answer))
        if problem.solution:
            blocks.append(('Решение', '', problem.solution))
        htmls = [render_figures(render_markdown(c or ''), problem)
                 for _n, _r, c in blocks]
        return blocks, htmls

    @staticmethod
    def _open_probe():
        # Синхронный playwright поднимает event loop, после чего Django
        # запрещает ORM. Здесь доступ к базе только на чтение и в один
        # поток — ровно случай, для которого флаг и предназначен.
        os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', '1')
        from problems.corpus_converter.katex_preflight import KatexPreflight
        return KatexPreflight().__enter__()

    @staticmethod
    def _widths(probe, htmls):
        from problems.corpus_converter.width_probe import codes_for_widths
        found = {}
        for widths in probe.widths_many(htmls):
            for code, detail in codes_for_widths(widths):
                found.setdefault(code, detail)
        return found
