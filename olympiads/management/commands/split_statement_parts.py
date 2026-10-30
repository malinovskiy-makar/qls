"""Д2: текст пунктов лежит ещё и в условии — условие = общая часть до пунктов.

    manage.py split_statement_parts            # сухой прогон, отчёт в reports/
    manage.py split_statement_parts --apply    # снимок базы и запись

В банке принято: условие — общая часть, пункты — отдельно. У задач S4 текст
пунктов почти всегда лежит и в хвосте условия, и ученик видит каждый пункт
дважды. Если хвост условия от метки первого пункта — ровно тексты пунктов по
порядку (без учёта пробелов, разметки меток и «(N балла)»), условие
укорачивается до первого пункта. Иначе — «под вопросом: пункты в условии не
совпали с пунктами задачи», условие не трогаем. Правила — `parts_fix.split_plan`.

⚠️ Каждое укорочение сверяется второй, независимой проверкой
(`parts_fix.tail_is_parts`): вырезанный хвост без меток и пометок баллов =
склеенные тексты пунктов. Не сошлось — задача уходит в «под вопросом», а не
в запись. Прежние задачи (их 664 с пунктами в условии) не трогаются — только
число в отчёт.
"""
import collections

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from olympiads import bank_fix as bf
from olympiads import parts_fix as pf
from olympiads.management.commands.dedupe_problem_parts import load_parts

REASON_CHECK = 'вырезанный хвост условия не сошёлся с текстами пунктов'


def build_plan(problem_ids):
    from problems.models import Problem
    by_problem = load_parts(problem_ids)
    statements = dict(Problem.objects.filter(pk__in=list(by_problem))
                      .values_list('pk', 'statement'))
    plan = {'cut': [], 'reasons': {}}
    for pid, parts in sorted(by_problem.items()):
        before = statements[pid]
        # Пункты бывают записаны в условии дважды подряд: вторая копия
        # видна только после первого укорочения. Режем до неподвижной точки,
        # каждое укорочение — со своей сверкой хвоста.
        after, reason, copies = before, None, 0
        while True:
            shorter, why = pf.split_plan(after, parts)
            if shorter is not None and not pf.tail_is_parts(after[len(shorter):], parts):
                shorter, why = None, REASON_CHECK
            if shorter is None:
                # Укоротили, а текст пункта в условии остался (в середине) —
                # та же причина, что без укорочения: повторный прогон её не
                # допишет второй раз.
                reason = why
                break
            after, copies = shorter, copies + 1
        if reason:
            plan['reasons'][pid] = [reason]
        if after != before:
            plan['cut'].append({'id': pid, 'before': before, 'after': after,
                                'tail': before[len(after):], 'copies': copies})
    return plan


def parts_inside(problem_ids):
    """Сколько задач несут текст хотя бы одного пункта в условии (мерка фазы −1)."""
    from problems.models import Problem
    by_problem = load_parts(problem_ids)
    statements = dict(Problem.objects.filter(pk__in=list(by_problem))
                      .values_list('pk', 'statement'))
    return sum(1 for pid, parts in by_problem.items()
               if any(pf.squeeze(p['statement'])[:60] in pf.squeeze(statements[pid])
                      for p in parts if pf.squeeze(p['statement'])))


def _tail_ok(entry):
    """Сверка на всех укороченных: хвост = пункты, записанные один или больше раз."""
    parts = load_parts([entry['id']])[entry['id']]
    return pf.tail_is_parts(entry['tail'], parts * entry['copies'])


class Command(BaseCommand):
    help = 'Д2: убрать из условия текст пунктов, записанный и пунктами. Без --apply — сухой прогон.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Снимок и запись в базу.')
        parser.add_argument('--no-snapshot', action='store_true',
                            help='Не делать снимок (только для тестов).')
        parser.add_argument('--report-dir', default='', help='Куда класть отчёт.')

    def handle(self, *args, **options):
        from problems.corpus_converter.ingest import content_hash_for
        from problems.models import Problem, ProblemPart
        apply = options['apply']
        editable = bf.editable_ids()
        plan = build_plan(editable)
        flags = bf.flag_edits(plan['reasons'])
        inside_before = parts_inside(editable)
        legacy_ids = set(ProblemPart.objects.filter(problem_id__lt=bf.S4_FIRST)
                         .values_list('problem_id', flat=True))
        legacy_inside = parts_inside(legacy_ids)
        snapshot = ''
        if apply and (plan['cut'] or flags):
            digest = bf.old_digest()
            if not options['no_snapshot']:
                snapshot = bf.snapshot_database('split_parts')
                self.stdout.write('Снимок базы: {}'.format(snapshot))
            now = timezone.now()
            with transaction.atomic():
                for e in plan['cut']:
                    Problem.objects.filter(pk=e['id'], pk__in=editable).update(
                        statement=e['after'], updated_at=now,
                        content_hash=content_hash_for(e['after']))
                bf.apply_flag_edits(flags, now)
                if bf.old_digest() != digest:
                    raise CommandError('ИНВАРИАНТ: изменилась прежняя задача банка; откат.')
            inside_after = parts_inside(editable)
        else:
            inside_after = inside_before - len(plan['cut'])

        out = self.stdout.write
        out(self.style.SUCCESS('ЗАПИСАНО' if apply else 'СУХОЙ ПРОГОН (в базе ничего не изменено)'))
        out('Задач S4 в проверке: {}'.format(len(editable)))
        out('Задач S4 с текстом пунктов в условии: {} → {}'.format(inside_before, inside_after))
        out('Условий укорочено: {}'.format(len(plan['cut'])))
        reasons = collections.Counter(r for rs in plan['reasons'].values() for r in rs)
        out('Задач «под вопросом»: {} ({})'.format(len(plan['reasons']), dict(reasons)))
        out('Позиций с новой пометкой: {}'.format(len(flags)))
        out('Прежних задач с текстом пунктов в условии (не тронуты): {}'.format(legacy_inside))
        checked = sum(1 for e in plan['cut'] if _tail_ok(e))
        out('Сверка «вырезанный хвост = тексты пунктов»: {} из {}'.format(
            checked, len(plan['cut'])))
        path = bf.write_report('olympiads_split_parts', {
            'applied': apply, 'snapshot': snapshot, 'editable': len(editable),
            'inside_before': inside_before, 'inside_after': inside_after,
            'legacy_inside': legacy_inside, 'cut': plan['cut'],
            'flagged_problems': plan['reasons'], 'item_flags': flags,
        }, options['report_dir'])
        out('Отчёт: {}'.format(path))
