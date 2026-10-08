"""Команда `apply_olympiad_audit` — девять проверок записи итогов аудита.

Задачи, эталон и файлы аудита выдуманные, но устроены как настоящие
файлы сессии 2 пилота ВП (docs/OLYMPIAD_AUDIT.md). Тексты разных
заданий нарочно непохожи друг на друга, а «близнец» — то же задание в
комплектах двух классов.
"""
import csv
import json
import os
import tempfile

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from problems.models import (
    OlympiadRef, Problem, ProblemFigure, ProblemPart, Source, SourceReference,
)
from problems.olympiad_official import OFFICIAL_SOURCE_NAME
from problems.text_dedup import normalize_for_compare

APPROVE = {'apply': True, 'yes_i_have_owner_approval': True}

TEXT = {
    'A': ('Фирма-монополист продаёт товар на двух рынках с разной эластичностью '
          'спроса. Найдите цены на каждом рынке и объясните, почему ценовая '
          'дискриминация выгодна фирме, а потребителям одного из рынков нет.'),
    'B': ('В стране Альфа производят только хлеб и вино. Постройте кривую '
          'производственных возможностей и найдите альтернативную стоимость '
          'производства одной бутылки вина в единицах хлеба при полной занятости.'),
    'C': ('Центральный банк повысил ключевую ставку на два процентных пункта. '
          'Опишите, как это повлияет на кредиты, инвестиции фирм, курс '
          'национальной валюты и инфляцию в краткосрочном периоде.'),
    'D': ('Государство вводит потоварный налог на производителей сигарет. '
          'Покажите на графике, как распределится налоговое бремя между '
          'продавцами и покупателями при неэластичном спросе на сигареты.'),
}
URL = {ev: f'https://olymp.hse.ru/data/{ev}.pdf' for ev in (
    'vp-2020-final-10-v1', 'vp-2020-final-11-v1', 'vp-2020-final-9-v1')}

# Эталон: A — близнец (есть и в 10, и в 11 классе), B — №2 десятого,
# C — №3 одиннадцатого, D — №2 девятого.
REFERENCE = [
    ('vp-2020-final-10-v1', '1', '10', 'A'),
    ('vp-2020-final-10-v1', '2', '10', 'B'),
    ('vp-2020-final-11-v1', '1', '11', 'A'),
    ('vp-2020-final-11-v1', '3', '11', 'C'),
    ('vp-2020-final-9-v1', '2', '9', 'D'),
]


def write_csv(path, rows):
    with open(path, 'w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def snapshot():
    """Всё, что команда могла бы изменить, — до значения."""
    refs = [tuple(getattr(r, f.attname) for f in OlympiadRef._meta.fields
                  if f.attname != 'created_at')
            for r in OlympiadRef.objects.order_by('id')]
    return (refs, Problem.objects.count(), ProblemPart.objects.count(),
            SourceReference.objects.count(), ProblemFigure.objects.count())


class AuditTestBase(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.s2 = os.path.join(self.tmp.name, 'session2')
        self.out = os.path.join(self.tmp.name, 'session3')
        os.makedirs(self.s2)
        with open(os.path.join(self.s2, 'reference_problems_full.jsonl'), 'w',
                  encoding='utf-8') as handle:
            for event_id, number, grade, letter in REFERENCE:
                handle.write(json.dumps({
                    'event_id': event_id, 'number': number, 'year': '2020',
                    'academic_year': '2019/2020', 'grade': grade,
                    'stage': 'final', 'raw_text': TEXT[letter],
                    'norm_text': normalize_for_compare(TEXT[letter]),
                    'source_url': URL[event_id]}, ensure_ascii=False) + '\n')

    def problem(self, letter):
        return Problem.objects.create(statement=TEXT[letter], status='published')

    def aggregator_ref(self, problem, **kw):
        fields = dict(source_site='solvehub', olympiad_slug='vp',
                      olympiad_name='Олимпиада школьников «Высшая проба» по экономике',
                      year=2020, stage='', grade='10', number='1',
                      event_id=f'solvehub-vp-{problem.pk}', record_id='x',
                      official_url='https://solvehub.app/econ/1',
                      match_method='url_exact', raw_meta={'title': 'с агрегатора'})
        fields.update(kw)
        return OlympiadRef.objects.create(problem=problem, **fields)

    def run_cmd(self, **kw):
        call_command('apply_olympiad_audit', out_dir=self.out, **kw)

    def journals(self, suffix=''):
        return sorted(f for f in os.listdir(self.out)
                      if f.endswith(f'{suffix}.json') and f.startswith('apply_')
                      and (suffix or not f.endswith('_dryrun.json')))

    def auto_csv(self, rows):
        return write_csv(os.path.join(self.s2, 'proposed_new_refs.csv'), [
            {'problem_id': pid, 'event_id': ev, 'number': no, 'match_score': '0.99',
             'margin_vs_other_ref': '0.5'} for pid, ev, no in rows])

    def review_md(self, high=(), eyeball=()):
        lines = ['# Проверка', '', '## Высокий ярус: все подтверждены', '',
                 '| problem_id | event_id | № | fuzzy | ratio |', '|---|---|---|---|---|']
        lines += [f'| {pid} | {ev} | {no} | 0.95 | 0.99 |' for pid, ev, no in high]
        lines += ['', '## Перенумеровка: на глаза', '',
                  '| problem_id | event_id | текущий № | предложенный № | a | b |',
                  '|---|---|---|---|---|---|']
        lines += [f'| {pid} | {ev} | {cur} | {new} | 0.1 | 0.85 |'
                  for pid, ev, cur, new in eyeball]
        path = os.path.join(self.s2, 'claude_review.md')
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write('\n'.join(lines) + '\n')
        return path

    def update_csv(self, rows):
        base = {'ref_id': '', 'problem_id': '', 'action': '', 'coord_status': '',
                'official_event_id': '', 'proposed_stage': '', 'proposed_grade': '',
                'proposed_official_url': '', 'proposed_number': '',
                'proposed_slug': '', 'reason': ''}
        return write_csv(os.path.join(self.s2, 'proposed_updates_existing.csv'),
                         [{**base, **row} for row in rows])


class DryRunAndApprovalTests(AuditTestBase):
    def test_1_dry_run_changes_nothing(self):
        """Сухой прогон всех трёх видов не меняет ни строки, ни числа."""
        p_new, p_old = self.problem('B'), self.problem('C')
        ref = self.aggregator_ref(p_old, grade='11', number='1')
        auto = self.auto_csv([(p_new.pk, 'vp-2020-final-10-v1', '2')])
        upd = self.update_csv([{
            'ref_id': ref.pk, 'problem_id': p_old.pk, 'action': 'renumber+check',
            'coord_status': 'number_shifted_same_event',
            'official_event_id': 'vp-2020-final-11-v1', 'proposed_number': '3'}])
        before = snapshot()
        self.run_cmd(new_refs=auto, tier='auto')
        self.run_cmd(update_existing=upd, confirmed_by=self.review_md())
        self.assertEqual(snapshot(), before)
        self.assertEqual(len(self.journals('_dryrun')), 2)

    def test_2_apply_without_phrase_refused(self):
        """--apply без фразы владельца — отказ и ни одной записи."""
        p = self.problem('B')
        auto = self.auto_csv([(p.pk, 'vp-2020-final-10-v1', '2')])
        before = snapshot()
        with self.assertRaises(CommandError):
            self.run_cmd(new_refs=auto, tier='auto', apply=True)
        self.assertEqual(snapshot(), before)


class NewRefTests(AuditTestBase):
    def test_3_official_row_and_no_duplicate_pair(self):
        """Новая строка — official и официальный event_id; дубль пары не заводится."""
        p = self.problem('B')
        auto = self.auto_csv([(p.pk, 'vp-2020-final-10-v1', '2')])
        self.run_cmd(new_refs=auto, tier='auto', **APPROVE)
        ref = OlympiadRef.objects.get(problem=p)
        self.assertEqual(
            (ref.source_site, ref.event_id, ref.number, ref.grade, ref.stage,
             ref.academic_year, ref.match_method, ref.reviewed_by_human),
            ('official', 'vp-2020-final-10-v1', '2', '10', 'final', '2019/20',
             'text_fuzzy_numeric', False))
        self.assertEqual(ref.official_url, URL['vp-2020-final-10-v1'])
        self.run_cmd(new_refs=auto, tier='auto', **APPROVE)
        self.assertEqual(OlympiadRef.objects.filter(problem=p).count(), 1)

    def test_4_existing_vp_row_same_tour_is_updated(self):
        """Строка ВП того же года и класса уже есть — она дописывается, второй нет."""
        p = self.problem('B')
        old = self.aggregator_ref(p, grade='10', number='5')
        auto = self.auto_csv([(p.pk, 'vp-2020-final-10-v1', '2')])
        self.run_cmd(new_refs=auto, tier='auto', **APPROVE)
        self.assertEqual(OlympiadRef.objects.filter(problem=p).count(), 1)
        old.refresh_from_db()
        self.assertEqual((old.number, old.official_url, old.source_site),
                         ('2', URL['vp-2020-final-10-v1'], 'solvehub'))
        self.assertEqual(old.raw_meta['aggregator_number'], '5')

    def test_6_high_tier_only_when_confirmed(self):
        """Высокий ярус пишется только для пар из таблицы подтверждений."""
        yes, no = self.problem('B'), self.problem('C')
        queue = write_csv(os.path.join(self.s2, 'review_queue.csv'), [
            {'problem_id': yes.pk, 'ref_event_id': 'vp-2020-final-10-v1',
             'ref_number': '2', 'fuzzy': '0.95', 'margin': '0.4',
             'review_tier': 'высокий (текст ≥0,90)'},
            {'problem_id': no.pk, 'ref_event_id': 'vp-2020-final-11-v1',
             'ref_number': '3', 'fuzzy': '0.95', 'margin': '0.4',
             'review_tier': 'высокий (текст ≥0,90)'},
        ])
        md = self.review_md(high=[(yes.pk, 'vp-2020-final-10-v1', '2')])
        self.run_cmd(new_refs=queue, tier='high', confirmed_by=md, **APPROVE)
        ref = OlympiadRef.objects.get(problem=yes)
        self.assertEqual((ref.match_method, ref.reviewed_by_human,
                          ref.raw_meta['reviewed_by']),
                         ('manual', True, 'claude-chat-20261008'))
        self.assertFalse(OlympiadRef.objects.filter(problem=no).exists())


class UpdateTests(AuditTestBase):
    def renumber_row(self, ref, problem):
        return {'ref_id': ref.pk, 'problem_id': problem.pk,
                'action': 'renumber+check',
                'coord_status': 'number_shifted_same_event',
                'official_event_id': 'vp-2020-final-11-v1', 'proposed_number': '3'}

    def test_5_renumber_keeps_old_number_and_eyeball_waits(self):
        """Перенумерация: старый номер в raw_meta; «на глаза» — только с флагом."""
        p1, p2 = self.problem('C'), Problem.objects.create(statement=TEXT['C'] + ' ')
        r1 = self.aggregator_ref(p1, grade='11', number='1')
        r2 = self.aggregator_ref(p2, grade='11', number='1')
        upd = self.update_csv([self.renumber_row(r1, p1), self.renumber_row(r2, p2)])
        md = self.review_md(eyeball=[(p2.pk, 'vp-2020-final-11-v1', '1', '3')])
        self.run_cmd(update_existing=upd, confirmed_by=md, **APPROVE)
        r1.refresh_from_db()
        r2.refresh_from_db()
        self.assertEqual((r1.number, r1.raw_meta['aggregator_number']), ('3', '1'))
        self.assertEqual(r1.raw_meta['aggregator_url'], 'https://solvehub.app/econ/1')
        self.assertEqual((r2.number, r2.raw_meta), ('1', {'title': 'с агрегатора'}))
        self.run_cmd(update_existing=upd, confirmed_by=md, include_eyeball=True, **APPROVE)
        r2.refresh_from_db()
        self.assertEqual(r2.number, '3')

    def test_8_twin_stays_on_own_grade(self):
        """Близнец: текст совпал с 11 классом, но то же задание есть в 10-м —
        строка остаётся на 10 классе и получает номер и PDF десятого. Без
        близнеца в своём классе — класс исправляется."""
        twin, lone = self.problem('A'), self.problem('C')
        r_twin = self.aggregator_ref(twin, grade='10', number='4')
        r_lone = self.aggregator_ref(lone, grade='10', number='4')
        reason = ('текст совпал с vp-2020-final-11-v1 №{found} (0.99), а координаты '
                  'строки ведут в vp-2020-final-10-v1 №4')
        upd = self.update_csv([
            {'ref_id': r_twin.pk, 'problem_id': twin.pk, 'action': 'check',
             'coord_status': 'other_event', 'reason': reason.format(found=1)},
            {'ref_id': r_lone.pk, 'problem_id': lone.pk, 'action': 'check',
             'coord_status': 'other_event', 'reason': reason.format(found=3)},
        ])
        self.run_cmd(update_existing=upd, confirmed_by=self.review_md(), **APPROVE)
        r_twin.refresh_from_db()
        r_lone.refresh_from_db()
        self.assertEqual((r_twin.grade, r_twin.number, r_twin.official_url),
                         ('10', '1', URL['vp-2020-final-10-v1']))
        self.assertEqual((r_lone.grade, r_lone.number, r_lone.official_url),
                         ('11', '3', URL['vp-2020-final-11-v1']))
        self.assertEqual(r_lone.raw_meta['aggregator_grade'], '10')


class ImportAndRollbackTests(AuditTestBase):
    def setUp(self):
        super().setUp()
        call_command('olympiad_official_sources', apply=True)
        self.queue = os.path.join(self.s2, 'import_queue_vp.jsonl')
        with open(self.queue, 'w', encoding='utf-8') as handle:
            handle.write(json.dumps({
                'event_id': 'vp-2020-final-9-v1', 'number': '4', 'year': '2020',
                'academic_year': '2019/2020', 'grade': '9', 'max_score': '25.0',
                'raw_text': 'Задание 4. «Налоги» (25 баллов)\n' + TEXT['D'],
                'solution_text': 'Решение\nБремя ляжет на покупателей.',
                'has_figure': False, 'source_url': URL['vp-2020-final-9-v1'],
                'tasks_pdf': 't.pdf', 'solutions_pdf': 's.pdf',
                'parts': [{'label': 'а', 'statement': 'Найдите бремя.', 'answer': '3/4'}],
            }, ensure_ascii=False) + '\n')

    def test_9_import_creates_everything_once(self):
        """Импорт: Problem + ProblemPart + SourceReference + OlympiadRef(official);
        повторный импорт ничего не создаёт."""
        before = snapshot()
        self.run_cmd(import_queue=self.queue, **APPROVE)
        problem = Problem.objects.get(source_references__source__name=OFFICIAL_SOURCE_NAME)
        self.assertEqual(problem.title, 'Налоги')
        self.assertTrue(problem.hidden_pending_review)
        self.assertEqual(problem.status, 'draft')
        self.assertEqual(list(problem.parts.values_list('label', 'answer')), [('а', '3/4')])
        sref = problem.source_references.get()
        self.assertEqual((sref.url, sref.grade, sref.year),
                         (URL['vp-2020-final-9-v1'], '9', 2020))
        ref = problem.olympiad_refs.get()
        self.assertEqual((ref.source_site, ref.event_id, ref.number),
                         ('official', 'vp-2020-final-9-v1', '4'))
        after = snapshot()
        self.assertEqual(after[1:], (before[1] + 1, before[2] + 1, before[3] + 1, before[4]))
        self.run_cmd(import_queue=self.queue, **APPROVE)
        self.assertEqual(snapshot()[1:], after[1:])

    def test_7_rollback_restores_exactly(self):
        """Откат по журналу возвращает базу до единицы — и привязки, и импорт."""
        p_new, p_old = self.problem('B'), self.problem('C')
        ref = self.aggregator_ref(p_old, grade='', number='1')
        before = snapshot()
        self.run_cmd(new_refs=self.auto_csv([(p_new.pk, 'vp-2020-final-10-v1', '2')]),
                     tier='auto', **APPROVE)
        upd = self.update_csv([{
            'ref_id': ref.pk, 'problem_id': p_old.pk, 'action': 'renumber+check',
            'coord_status': 'number_shifted_same_event',
            'official_event_id': 'vp-2020-final-11-v1', 'proposed_number': '3'}])
        self.run_cmd(update_existing=upd, confirmed_by=self.review_md(), **APPROVE)
        self.run_cmd(import_queue=self.queue, **APPROVE)
        self.assertNotEqual(snapshot(), before)
        for name in reversed(self.journals()):
            self.run_cmd(rollback=os.path.join(self.out, name), **APPROVE)
        self.assertEqual(snapshot(), before)
        self.assertTrue(Source.objects.filter(name=OFFICIAL_SOURCE_NAME).exists())
