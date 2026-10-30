"""Д1: пункты задачи записаны дважды («а б в а б в») — оставить по одному.

    manage.py dedupe_problem_parts            # сухой прогон, отчёт в reports/
    manage.py dedupe_problem_parts --apply    # снимок базы и запись

Пункты задачи S4 с одной меткой, одним текстом (без учёта пробелов), одними
баллами, ответом и решением — один пункт; остаётся первый по порядку. Все
ссылки на удаляемые пункты (каждый внешний ключ на `ProblemPart`: рисунки,
подсказки, черновики, ответы, игра, тренировка) переносятся на оставленный —
иначе каскад унёс бы их вместе с копией. Метка одна, а текст или баллы
различаются — «под вопросом» на позициях комплектов, пункты не трогаем.
Правила — `olympiads/parts_fix.py`; общее устройство — `olympiads/bank_fix.py`.
"""
import collections

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from olympiads import bank_fix as bf
from olympiads import parts_fix as pf


def part_links():
    """(модель, поле) каждого внешнего ключа на `ProblemPart`."""
    from problems.models import ProblemPart
    return [(rel.related_model, rel.field.name)
            for rel in ProblemPart._meta.related_objects
            if rel.field.many_to_one]


def load_parts(problem_ids):
    from problems.models import ProblemPart
    by_problem = collections.defaultdict(list)
    rows = (ProblemPart.objects.filter(problem_id__in=list(problem_ids))
            .order_by('problem_id', 'order', 'id')
            .values('id', 'problem_id', 'label', 'statement', 'points',
                    'answer', 'solution', 'order'))
    for row in rows.iterator(chunk_size=5000):
        by_problem[row['problem_id']].append(row)
    return by_problem


def build_plan(problem_ids):
    by_problem = load_parts(problem_ids)
    plan = {'remove': {}, 'reasons': {}, 'problems': [],
            'repeated_before': 0, 'repeated_after': 0}
    for pid, parts in sorted(by_problem.items()):
        remove, reasons = pf.dedupe_plan(parts)
        plan['repeated_before'] += pf.has_repeated_text(parts)
        plan['repeated_after'] += pf.has_repeated_text(
            [p for p in parts if p['id'] not in remove])
        if reasons:
            plan['reasons'][pid] = reasons
        if remove:
            plan['remove'].update(remove)
            plan['problems'].append({
                'id': pid,
                'labels_before': [p['label'] for p in parts],
                'labels_after': [p['label'] for p in parts if p['id'] not in remove],
                'removed': sorted(remove),
            })
    return plan


class Command(BaseCommand):
    help = 'Д1: схлопнуть пункты задач пакета олимпиад, записанные дважды. Без --apply — сухой прогон.'

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
        links = part_links()
        moved = {'{}.{}'.format(m.__name__, f): m.objects.filter(
            **{f + '__in': list(plan['remove'])}).count() for m, f in links}
        parts_before = ProblemPart.objects.count()
        snapshot = ''
        if apply and (plan['remove'] or flags):
            digest = bf.old_digest()
            if not options['no_snapshot']:
                snapshot = bf.snapshot_database('dedupe_parts')
                self.stdout.write('Снимок базы: {}'.format(snapshot))
            now = timezone.now()
            with transaction.atomic():
                by_kept = collections.defaultdict(list)
                for copy, kept in plan['remove'].items():
                    by_kept[kept].append(copy)
                for model, field in links:
                    for kept, copies in by_kept.items():
                        model.objects.filter(**{field + '__in': copies}).update(**{field: kept})
                ids = list(plan['remove'])
                for start in range(0, len(ids), 500):
                    ProblemPart.objects.filter(
                        pk__in=ids[start:start + 500],
                        problem_id__in=editable).delete()
                bf.apply_flag_edits(flags, now)
                parts_after = ProblemPart.objects.count()
                if parts_before - parts_after != len(plan['remove']):
                    raise CommandError('ИНВАРИАНТ: пунктов стало меньше на {}, а копий {}; откат.'
                                       .format(parts_before - parts_after, len(plan['remove'])))
                if bf.old_digest() != digest:
                    raise CommandError('ИНВАРИАНТ: изменилась прежняя задача банка; откат.')
        parts_after = ProblemPart.objects.count() if apply else parts_before - len(plan['remove'])

        out = self.stdout.write
        out(self.style.SUCCESS('ЗАПИСАНО' if apply else 'СУХОЙ ПРОГОН (в базе ничего не изменено)'))
        out('Задач S4 в проверке: {}'.format(len(editable)))
        out('Задач с повторённым текстом пункта (мерка карточки): {} → {}'.format(
            plan['repeated_before'], plan['repeated_after']))
        out('Задач, где схлопнуты копии: {}; копий удалено: {}'.format(
            len(plan['problems']), len(plan['remove'])))
        out('Пунктов в банке: {} → {}'.format(parts_before, parts_after))
        out('Ссылок перенесено на оставленный пункт: {}'.format(
            {k: v for k, v in moved.items() if v} or 0))
        reasons = collections.Counter(r for rs in plan['reasons'].values() for r in rs)
        out('Задач «под вопросом»: {} ({})'.format(len(plan['reasons']), dict(reasons)))
        out('Позиций с новой пометкой: {}'.format(len(flags)))
        path = bf.write_report('olympiads_dedupe_parts', {
            'applied': apply, 'snapshot': snapshot,
            'editable': len(editable),
            'repeated_before': plan['repeated_before'],
            'repeated_after': plan['repeated_after'],
            'removed': len(plan['remove']), 'parts_before': parts_before,
            'parts_after': parts_after, 'links_moved': moved,
            'flagged_problems': plan['reasons'], 'item_flags': flags,
            'problems': plan['problems'],
        }, options['report_dir'])
        out('Отчёт: {}'.format(path))
