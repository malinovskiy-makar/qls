# -*- coding: utf-8 -*-
"""Собрать картинки из TikZ/PGFPlots-блоков в `ProblemFigure` (Фаза B).

Единственная команда этой сессии, которая ПИШЕТ в базу, и пишет она
только в новую таблицу `ProblemFigure`. Ни `content_format`, ни
`human_review`, ни `statement`/`answer`/`solution` она не трогает —
проверяется инвариантом по счётчикам и по контрольным суммам полей.

По умолчанию — сухой прогон (компилирует и показывает, что получилось,
но в базу не пишет). Запись — только с `--apply`, как требует
`problems/management/commands/CLAUDE.md`.

⚠️ Компиляция идёт в песочнице `problems/corpus_converter/tikz_render.py`:
офлайн (`-disable-installer`), без `\\write18` (`-no-shell-escape`), с
таймаутом 10 с и своим временным каталогом на каждый блок. Параметры
замерены в [ADR 0031](../../../docs/adr/0031-tikz-svg-blocked-by-sanitizer.md).

При ошибке или таймауте компиляции картинка НЕ создаётся, задача
остаётся без неё — и тогда шлюз `render_preflight_v2` заблокирует её
кодом `FIGURE-MISSING`. Сырой TikZ-код читателю не показывается никогда.
"""
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from problems.corpus_converter.preflight_gate import convert_problem_v2
from problems.corpus_converter.tikz_render import (
    TikzCompileError, compile_tikz_to_svg, toolchain_available,
)
from problems.models import Problem, ProblemFigure, ProblemPart

SOURCES = {
    'archive3': (14, 'Overleaf Archive 3 (ОШ/ЛШ Олмат)'),
    'matek': (13, 'МатЭк — Overleaf архивы (2021–2025)'),
    'lsh2025': (3, 'ЛШ Олмат 2025 (Overleaf)'),
    'reshalki': (16, 'Решалки Олмат (olmat41)'),
}
EXCLUDED_SOURCE_NAME = 'Служебное: фикстуры рендерера (не публиковать)'


class Command(BaseCommand):
    help = ('Скомпилировать TikZ-блоки в ProblemFigure. Без --apply — '
            'сухой прогон (компилирует, но в базу не пишет).')

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='реально записать ProblemFigure в базу')
        parser.add_argument('--ids', help='список id через запятую')
        parser.add_argument('--source', choices=list(SOURCES))
        parser.add_argument('--limit', type=int)

    def handle(self, *args, **options):
        if not toolchain_available():
            raise CommandError(
                'latex/dvisvgm не найдены — компиляция картинок невозможна. '
                'Установите MiKTeX или запускайте команду там, где он есть.')

        do_apply = options['apply']
        problems = self._select(options)
        self.stdout.write(f'Задач для разбора: {len(problems)}')

        # Инвариант: команда не имеет права тронуть тексты и флаги.
        before = self._fingerprint(problems)
        problems_before = Problem.objects.count()
        parts_before = ProblemPart.objects.count()

        compiled = failed = skipped = 0
        failures = []
        planned = []

        for problem in problems:
            raw_parts = [(p.label, p.statement) for p in problem.parts.all()]
            result = convert_problem_v2(
                statement=problem.statement, answer=problem.answer,
                solution=problem.solution, existing_parts=raw_parts)
            for figure in result.get('figures', []):
                if ProblemFigure.objects.filter(
                        problem=problem, tikz_hash=figure['hash']).exists():
                    skipped += 1
                    continue
                try:
                    svg = compile_tikz_to_svg(figure['source'])
                except TikzCompileError as exc:
                    failed += 1
                    failures.append((problem.id, figure['hash'][:12], str(exc)[:160]))
                    continue
                compiled += 1
                planned.append((problem, figure, svg))

        if do_apply:
            with transaction.atomic():
                for problem, figure, svg in planned:
                    part = None
                    if figure['part']:
                        part = problem.parts.filter(label=figure['part']).first()
                    ProblemFigure.objects.update_or_create(
                        problem=problem, tikz_hash=figure['hash'],
                        defaults={
                            'part': part,
                            'source_field': figure['field'],
                            'tikz_source': figure['source'],
                            'svg': svg,
                        })

        after = self._fingerprint(problems)
        if before != after:
            raise CommandError(
                'ИНВАРИАНТ НАРУШЕН: команда изменила тексты или флаги задач — '
                'она обязана писать только в ProblemFigure')
        if (Problem.objects.count(), ProblemPart.objects.count()) != (
                problems_before, parts_before):
            raise CommandError('ИНВАРИАНТ НАРУШЕН: изменилось число задач/подпунктов')

        self.stdout.write(
            f'Скомпилировано: {compiled}. Уже было: {skipped}. '
            f'Не удалось: {failed}.')
        for pid, digest, why in failures[:15]:
            self.stdout.write(f'  #{pid} {digest}: {why}')
        if failed > 15:
            self.stdout.write(f'  … и ещё {failed - 15}')

        if do_apply:
            self.stdout.write(self.style.SUCCESS(
                f'ЗАПИСАНО: {len(planned)} ProblemFigure. '
                f'Тексты задач и флаги не тронуты (инвариант сошёлся).'))
        else:
            self.stdout.write(self.style.WARNING(
                'Сухой прогон: в базу ничего не записано. Для записи — --apply.'))

    # ------------------------------------------------------------------
    def _select(self, options):
        if options['ids']:
            ids = [int(x) for x in options['ids'].split(',') if x.strip()]
            qs = Problem.objects.filter(id__in=ids)
        elif options['source']:
            source_id, _name = SOURCES[options['source']]
            qs = (Problem.objects.filter(source_references__source_id=source_id)
                  .exclude(source_references__source__name=EXCLUDED_SOURCE_NAME)
                  .distinct())
        else:
            source_ids = [sid for sid, _ in SOURCES.values()]
            qs = (Problem.objects.filter(source_references__source_id__in=source_ids)
                  .exclude(source_references__source__name=EXCLUDED_SOURCE_NAME)
                  .distinct())
        qs = qs.prefetch_related('parts')
        if options['limit']:
            qs = qs[:options['limit']]
        return list(qs)

    @staticmethod
    def _fingerprint(problems):
        """Слепок текстов и флагов — доказательство, что их не тронули."""
        return [
            (p.id, hash(p.statement), hash(p.answer), hash(p.solution),
             p.content_format, p.human_review)
            for p in Problem.objects.filter(
                id__in=[x.id for x in problems]).order_by('id')
        ]
