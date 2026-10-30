"""Д3: «(4 балла)» в начале текста пункта — баллы уже показаны колонкой.

    manage.py strip_part_points            # сухой прогон, отчёт в reports/
    manage.py strip_part_points --apply    # снимок базы и запись

Пометка «(N балл…)» в начале текста пункта задачи S4 убирается, если у пункта
`points = N`; `points` пусто — ставится N, пометка убирается. N ≠ `points`
или пометка внутри разметки — «под вопросом», текст не трогаем. Правила —
`parts_fix.points_plan`.
"""
import collections
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from olympiads import bank_fix as bf
from olympiads import parts_fix as pf
from olympiads.management.commands.dedupe_problem_parts import load_parts


def build_plan(problem_ids):
    plan = {'edits': [], 'reasons': {}}
    for pid, parts in sorted(load_parts(problem_ids).items()):
        for part in parts:
            text, points, reason = pf.points_plan(part)
            if reason:
                plan['reasons'].setdefault(pid, [])
                if reason not in plan['reasons'][pid]:
                    plan['reasons'][pid].append(reason)
            elif text is not None:
                plan['edits'].append({'id': part['id'], 'problem': pid,
                                      'before': part['statement'], 'after': text,
                                      'points_before': part['points'],
                                      'points_after': points or part['points']})
    return plan


def marks_left(problem_ids):
    """Пунктов S4, чей текст начинается с «(N балл…)»."""
    return sum(1 for parts in load_parts(problem_ids).values()
               for p in parts if pf._LEAD_POINTS.match(p['statement'] or ''))


class Command(BaseCommand):
    help = 'Д3: убрать «(N балла)» из начала текста пунктов. Без --apply — сухой прогон.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Снимок и запись в базу.')
        parser.add_argument('--no-snapshot', action='store_true',
                            help='Не делать снимок (только для тестов).')
        parser.add_argument('--report-dir', default='', help='Куда класть отчёт.')

    def handle(self, *args, **options):
        from problems.models import ProblemPart
        apply = options['apply']
        editable = bf.editable_ids()
        plan = build_plan(editable)
        flags = bf.flag_edits(plan['reasons'])
        before = marks_left(editable)
        filled = sum(1 for e in plan['edits'] if e['points_before'] is None)
        snapshot = ''
        if apply and (plan['edits'] or flags):
            digest = bf.old_digest()
            if not options['no_snapshot']:
                snapshot = bf.snapshot_database('strip_points')
                self.stdout.write('Снимок базы: {}'.format(snapshot))
            now = timezone.now()
            with transaction.atomic():
                for e in plan['edits']:
                    ProblemPart.objects.filter(pk=e['id'], problem_id__in=editable).update(
                        statement=e['after'], points=Decimal(str(e['points_after'])))
                from problems.models import Problem
                Problem.objects.filter(pk__in={e['problem'] for e in plan['edits']}).update(
                    updated_at=now)
                bf.apply_flag_edits(flags, now)
                if bf.old_digest() != digest:
                    raise CommandError('ИНВАРИАНТ: изменилась прежняя задача банка; откат.')
            after = marks_left(editable)
        else:
            after = before - len(plan['edits'])
        out = self.stdout.write
        out(self.style.SUCCESS('ЗАПИСАНО' if apply else 'СУХОЙ ПРОГОН (в базе ничего не изменено)'))
        out('Пунктов S4 с «(N балла)» в начале текста: {} → {}'.format(before, after))
        out('Пометок убрано: {}; из них баллы заполнены из пометки: {}'.format(
            len(plan['edits']), filled))
        reasons = collections.Counter(r for rs in plan['reasons'].values() for r in rs)
        out('Задач «под вопросом»: {} ({})'.format(len(plan['reasons']), dict(reasons)))
        out('Позиций с новой пометкой: {}'.format(len(flags)))
        path = bf.write_report('olympiads_strip_points', {
            'applied': apply, 'snapshot': snapshot, 'marks_before': before,
            'marks_after': after, 'removed': len(plan['edits']), 'points_filled': filled,
            'flagged_problems': plan['reasons'], 'item_flags': flags,
            'edits': plan['edits'],
        }, options['report_dir'])
        out('Отчёт: {}'.format(path))
