"""Д4: «(отмечено)» в тексте теста — ключ, который видит ученик, — в ответ задачи.

    manage.py extract_marked_answers            # сухой прогон, отчёт в reports/
    manage.py extract_marked_answers --apply    # снимок базы и запись

Формат теста в банке (`problems/problem_types.py`, `answer_check`,
`catalog/testplay.py`): тип задачи из словаря тестов, варианты — пункты
задачи, верные метки — `Problem.answer` («а, в») и `ProblemPart.answer`
(«верно» / «неверно»). Команда пишет ключ из отметки «(отмечено)» в ПУСТЫЕ
поля этого формата и убирает отметку из текста; у позиций комплектов на
задачу ставится «есть эталон ответа». Непустой ответ, расходящийся с
отметкой, несколько отметок у теста на один ответ, варианты не пунктами,
«+» перед вариантом — «под вопросом», текст не трогаем. Правила —
`parts_fix.marks_plan`.
"""
import collections

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from olympiads import bank_fix as bf
from olympiads import parts_fix as pf
from olympiads.management.commands.dedupe_problem_parts import load_parts


def build_plan(problem_ids):
    from problems.models import Problem
    by_problem = load_parts(problem_ids)
    plan = {'edits': [], 'reasons': {}}
    rows = (Problem.objects.filter(pk__in=list(problem_ids))
            .values('id', 'statement', 'answer', 'problem_type'))
    for problem in sorted(rows, key=lambda r: r['id']):
        result = pf.marks_plan(problem, by_problem.get(problem['id'], []))
        if result is None:
            continue
        if 'reason' in result:
            plan['reasons'][problem['id']] = [result['reason']]
        else:
            plan['edits'].append(dict(result, id=problem['id'],
                                      statement_before=problem['statement']))
    return plan


def visible_marks(problem_ids):
    """Задач S4, где «(отмечено)» видно в условии или в тексте пункта."""
    from problems.models import Problem, ProblemPart
    ids = list(problem_ids)
    in_statement = set(Problem.objects.filter(pk__in=ids, statement__iregex=r'\(\s*отмечено\s*\)')
                       .values_list('pk', flat=True))
    in_parts = set(ProblemPart.objects.filter(problem_id__in=ids,
                                              statement__iregex=r'\(\s*отмечено\s*\)')
                   .values_list('problem_id', flat=True))
    return len(in_statement | in_parts)


class Command(BaseCommand):
    help = 'Д4: ключ теста из «(отмечено)» — в ответ задачи, отметку из текста. Без --apply — сухой прогон.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Снимок и запись в базу.')
        parser.add_argument('--no-snapshot', action='store_true',
                            help='Не делать снимок (только для тестов).')
        parser.add_argument('--report-dir', default='', help='Куда класть отчёт.')

    def handle(self, *args, **options):
        from problems.corpus_converter.ingest import content_hash_for
        from problems.models import Problem, ProblemPart
        from olympiads.models import OlympiadVariantItem as Item
        apply = options['apply']
        editable = bf.editable_ids()
        plan = build_plan(editable)
        flags = bf.flag_edits(plan['reasons'])
        before = visible_marks(editable)
        has_answer_before = Item.objects.filter(has_answer=True).count()
        answers_filled = sum(1 for e in plan['edits'] if e['answer_was_empty'])
        types_filled = collections.Counter(e['problem_type'] for e in plan['edits']
                                           if e['type_was_empty'])
        snapshot = ''
        if apply and (plan['edits'] or flags):
            digest = bf.old_digest()
            answers = dict(Problem.objects.filter(pk__in=[e['id'] for e in plan['edits']])
                           .values_list('pk', 'answer'))
            if not options['no_snapshot']:
                snapshot = bf.snapshot_database('marked_answers')
                self.stdout.write('Снимок базы: {}'.format(snapshot))
            now = timezone.now()
            with transaction.atomic():
                for e in plan['edits']:
                    fields = {'answer': e['answer'], 'problem_type': e['problem_type'],
                              'updated_at': now}
                    if e['statement'] != e['statement_before']:
                        fields['statement'] = e['statement']
                        fields['content_hash'] = content_hash_for(e['statement'])
                    Problem.objects.filter(pk=e['id'], pk__in=editable).update(**fields)
                    for pk, text in e['parts'].items():
                        ProblemPart.objects.filter(pk=pk, problem_id=e['id']).update(statement=text)
                    for pk, verdict in e['part_answers'].items():
                        ProblemPart.objects.filter(pk=pk, problem_id=e['id'], answer='').update(
                            answer=verdict)
                Item.objects.filter(problem_id__in=[e['id'] for e in plan['edits']]).update(
                    has_answer=True, updated_at=now)
                bf.apply_flag_edits(flags, now)
                # Ни один непустой ответ не перезаписан.
                overwritten = [pk for pk, old in answers.items() if old.strip() and
                               Problem.objects.get(pk=pk).answer != old]
                if overwritten:
                    raise CommandError('ИНВАРИАНТ: перезаписан ответ задач {}; откат.'
                                       .format(overwritten[:10]))
                if bf.old_digest() != digest:
                    raise CommandError('ИНВАРИАНТ: изменилась прежняя задача банка; откат.')
            after = visible_marks(editable)
        else:
            after = before - len(plan['edits'])
        has_answer_after = Item.objects.filter(has_answer=True).count()
        out = self.stdout.write
        out(self.style.SUCCESS('ЗАПИСАНО' if apply else 'СУХОЙ ПРОГОН (в базе ничего не изменено)'))
        out('Задач S4 с видимым «(отмечено)»: {} → {}'.format(before, after))
        out('Тестов с ключом из отметки: {}; ответов заполнено: {}; уже был и совпал: {}'.format(
            len(plan['edits']), answers_filled, len(plan['edits']) - answers_filled))
        out('Тип теста проставлен: {}'.format(dict(types_filled) or 0))
        reasons = collections.Counter(r for rs in plan['reasons'].values() for r in rs)
        out('Задач «под вопросом»: {} ({})'.format(len(plan['reasons']), dict(reasons)))
        out('Позиций с новой пометкой: {}'.format(len(flags)))
        out('Позиций «есть эталон ответа»: {} → {}'.format(
            has_answer_before, has_answer_after if apply else '…'))
        path = bf.write_report('olympiads_marked_answers', {
            'applied': apply, 'snapshot': snapshot, 'visible_before': before,
            'visible_after': after, 'answers_filled': answers_filled,
            'types_filled': types_filled, 'flagged_problems': plan['reasons'],
            'item_flags': flags, 'edits': plan['edits'],
        }, options['report_dir'])
        out('Отчёт: {}'.format(path))
