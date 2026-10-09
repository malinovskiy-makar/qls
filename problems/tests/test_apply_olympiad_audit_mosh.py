"""`apply_olympiad_audit` и `olympiad_official_sources` для МОШ: параметр
олимпиады, вариант задания, этап по доказательству, перенумеровка по
вхождению, снятие строк с откатом.

Данные выдуманные, устроены как файлы сессии 1 аудита МОШ
(`weconomics-data/olympiads/audit_mosh_20261009/session1`). Банк МОШ
хранится в LaTeX, PDF — простым текстом: тексты банка нарочно с `$…$`.
"""
import csv
import json
import os
import tempfile

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from problems.models import OlympiadRef, Problem, Source
from problems.olympiad_audit import registry
from problems.tests.test_apply_olympiad_audit import APPROVE, snapshot, write_csv

MOSH = registry.get('mosh')

TEXT = {
    'A': ('Фирма-монополист продаёт товар на двух рынках с разной эластичностью '
          'спроса $Q_1 = 100 - P_1$ и $Q_2 = 60 - 2P_2$. Найдите цены на каждом '
          'рынке, прибыль фирмы и объясните, почему ценовая дискриминация выгодна '
          'фирме, а потребителям одного из рынков нет.'),
    'B': ('В стране Альфа производят только хлеб и вино, ресурсов хватает на 200 '
          'буханок или 50 бутылок. Постройте кривую производственных возможностей '
          'и найдите альтернативную стоимость одной бутылки вина в единицах хлеба '
          'при полной занятости ресурсов страны.'),
    'C': ('Центральный банк повысил ключевую ставку на два процентных пункта, с 7 '
          'до 9 процентов годовых. Опишите, как это повлияет на кредиты, инвестиции '
          'фирм, курс национальной валюты и инфляцию в краткосрочном и долгосрочном '
          'периодах.'),
    'D': ('Государство вводит потоварный налог 10 рублей на производителей сигарет. '
          'Спрос $Q_d = 120 - 2P$, предложение $Q_s = 3P - 30$. Покажите, как '
          'распределится налоговое бремя между продавцами и покупателями.'),
    'E1': ('Тест. Вариант 1. Если цена товара выросла на 10 процентов, а выручка '
           'не изменилась, то спрос на товар имеет единичную эластичность по цене. '
           'Верно ли это утверждение для линейного спроса на рынке яблок?'),
    'E2': ('Тест. Вариант 2. Если доход потребителя вырос на 20 процентов, а спрос '
           'на товар упал на 5 процентов, то товар является низшим благом для этого '
           'потребителя. Верно ли это утверждение для рынка картофеля зимой?'),
}
URL = {ev: f'https://mos.olimpiada.ru/upload/files/{ev}.pdf' for ev in (
    'mosh-2019-final-10-v1', 'mosh-2019-final-11-v1', 'mosh-2019-qualifying-9-v1',
    'mosh-2018-final-10-v1')}

# (event_id, номер, вариант задания, этап, класс, буква)
REFERENCE = [
    ('mosh-2019-final-10-v1', '1', '', 'final', '10', 'A'),
    ('mosh-2019-final-10-v1', '2', '', 'final', '10', 'B'),
    ('mosh-2019-final-10-v1', '3', '', 'final', '10', 'C'),
    ('mosh-2019-final-11-v1', '1', '', 'final', '11', 'D'),
    ('mosh-2019-qualifying-9-v1', '5', '1', 'qualifying', '9', 'E1'),
    ('mosh-2019-qualifying-9-v1', '5', '2', 'qualifying', '9', 'E2'),
    ('mosh-2018-final-10-v1', '1', '', 'final', '10', 'B'),
]


class MoshAuditTestBase(TestCase):
    olympiad = 'mosh'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.s1 = os.path.join(self.tmp.name, 'session1')
        self.out = os.path.join(self.tmp.name, 'session2')
        os.makedirs(self.s1)
        with open(os.path.join(self.s1, 'reference_problems_full.jsonl'), 'w',
                  encoding='utf-8') as handle:
            for event_id, number, variant, stage, grade, letter in REFERENCE:
                year = event_id.split('-')[1]
                handle.write(json.dumps({
                    'event_id': event_id, 'number': number, 'task_variant': variant,
                    'year': int(year), 'academic_year': f'{int(year) - 1}/{year[2:]}',
                    'grade': grade, 'stage': stage,
                    'raw_text': f'Задача {number}. (10 баллов)\n' + TEXT[letter].replace('$', ''),
                    'norm_text': '', 'source_url': URL[event_id]},
                    ensure_ascii=False) + '\n')

    def run_cmd(self, **kw):
        kw.setdefault('olympiad', self.olympiad)
        call_command('apply_olympiad_audit', out_dir=self.out, **kw)

    def problem(self, letter):
        return Problem.objects.create(statement=TEXT[letter], status='published')

    def aggregator_ref(self, problem, **kw):
        fields = dict(source_site='ile', olympiad_slug='mosh',
                      olympiad_name=MOSH.olympiad_name, year=2019, stage='',
                      grade='10', number='1', event_id='ile-mosh-2019-10-1',
                      record_id='x', official_url='https://iloveeconomics.ru/olimp/mosh/1',
                      match_method='url_exact', raw_meta={'title': 'с агрегатора'})
        fields.update(kw)
        return OlympiadRef.objects.create(problem=problem, **fields)

    def journals(self, suffix=''):
        return sorted(f for f in os.listdir(self.out)
                      if f.endswith(f'{suffix}.json') and f.startswith('apply_')
                      and (suffix or not f.endswith('_dryrun.json')))

    def auto_csv(self, rows):
        return write_csv(os.path.join(self.s1, 'candidates_auto.csv'), [
            {'problem_id': pid, 'event_id': ev, 'number': no, 'task_variant': tv,
             'match_score': '0.99', 'margin_vs_other_ref': '0.5'}
            for pid, ev, no, tv in rows])

    def update_csv(self, rows):
        base = {'ref_id': '', 'problem_id': '', 'action': '', 'coord_status': '',
                'current_event_id': '', 'official_event_id': '', 'proposed_stage': '',
                'proposed_grade': '', 'proposed_official_url': '',
                'proposed_number': '', 'proposed_slug': '', 'reason': ''}
        return write_csv(os.path.join(self.s1, 'proposed_updates_existing.csv'),
                         [{**base, **row} for row in rows])

    def review_md(self, high=(), high_eyeball=(), doubtful=()):
        lines = ['# Проверка', '', '## Высокий ярус: подтверждено', '',
                 'Расхождения — колонтитулы; спорные пары вынесены на глаза владельцу.', '',
                 '| problem_id | event_id | № | вариант | fuzzy | ratio |',
                 '|---|---|---|---|---|---|']
        lines += [f'| {pid} | {ev} | {no} | {tv} | 0.95 | 0.99 |' for pid, ev, no, tv in high]
        lines += ['', 'На глаза владельцу:', '',
                  '| problem_id | event_id | № | fuzzy | ratio |', '|---|---|---|---|---|']
        lines += [f'| {pid} | {ev} | {no} | 0.93 | 0.80 |' for pid, ev, no in high_eyeball]
        lines += ['', '## Перенумеровка: сомнительные', '']
        lines += [f'- {pid} {ev} {cur}→{new} текущий 0.1 предложенный 0.7 (url_exact)'
                  for pid, ev, cur, new in doubtful]
        path = os.path.join(self.s1, 'claude_review.md')
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write('\n'.join(lines) + '\n')
        return path


class OlympiadParamTests(MoshAuditTestBase):
    def test_1_refused_without_olympiad(self):
        """Без --olympiad обе команды отказывают и ничего не пишут."""
        p = self.problem('B')
        auto = self.auto_csv([(p.pk, 'mosh-2019-final-10-v1', '2', '')])
        before = snapshot()
        with self.assertRaises(CommandError):
            call_command('apply_olympiad_audit', new_refs=auto, tier='auto',
                         out_dir=self.out, **APPROVE)
        with self.assertRaises(CommandError):
            call_command('olympiad_official_sources', apply=True)
        self.assertEqual(snapshot(), before)
        self.assertFalse(Source.objects.filter(name=MOSH.official_source_name).exists())

    def test_2_mosh_name_source_stage_from_registry(self):
        """МОШ: Source из реестра (ВП не заводится, повтор — ничего), новая
        строка — слаг, название и этап из реестра и эталона."""
        call_command('olympiad_official_sources', olympiad='mosh', apply=True)
        call_command('olympiad_official_sources', olympiad='mosh', apply=True)
        self.assertEqual(Source.objects.filter(name=MOSH.official_source_name).count(), 1)
        self.assertFalse(Source.objects.filter(
            name=registry.get('vp').official_source_name).exists())
        p = self.problem('B')
        self.run_cmd(new_refs=self.auto_csv([(p.pk, 'mosh-2019-final-10-v1', '2', '')]),
                     tier='auto', **APPROVE)
        ref = OlympiadRef.objects.get(problem=p)
        self.assertEqual(
            (ref.olympiad_slug, ref.olympiad_name, ref.source_site, ref.stage,
             ref.grade, ref.academic_year, ref.raw_meta['session']),
            ('mosh', MOSH.olympiad_name, 'official', 'final', '10', '2018/19', 'mosh2'))
        self.assertTrue(self.journals())   # журнал лёг в session2 (--out-dir)

    def test_3_task_variant_kept(self):
        """Вариант задания: строка берёт текст и ссылку своего варианта,
        вариант — в raw_meta и record_id; без варианта задание не находится."""
        p, q = self.problem('E2'), self.problem('E1')
        self.run_cmd(new_refs=self.auto_csv([
            (p.pk, 'mosh-2019-qualifying-9-v1', '5', '2'),
            (q.pk, 'mosh-2019-qualifying-9-v1', '5', '')]), tier='auto', **APPROVE)
        ref = OlympiadRef.objects.get(problem=p)
        self.assertEqual((ref.raw_meta['task_variant'], ref.stage, ref.record_id),
                         ('2', 'qualifying', 'official:mosh-2019-qualifying-9-v1:5:2'))
        self.assertFalse(OlympiadRef.objects.filter(problem=q).exists())

    def test_4_high_tier_eyeball_not_written(self):
        """Высокий ярус: подтверждённая пара пишется с reviewed_by МОШ, пара
        из таблицы «на глаза» того же раздела — нет."""
        yes, eye = self.problem('B'), self.problem('C')
        queue = write_csv(os.path.join(self.s1, 'candidates_review.csv'), [
            {'problem_id': pid, 'ref_event_id': 'mosh-2019-final-10-v1',
             'ref_number': no, 'task_variant': '', 'fuzzy': '0.95', 'margin': '0.4',
             'is_test': 'False', 'review_tier': 'высокий (текст ≥0,90)'}
            for pid, no in ((yes.pk, '2'), (eye.pk, '3'))])
        md = self.review_md(high=[(yes.pk, 'mosh-2019-final-10-v1', '2', '')],
                            high_eyeball=[(eye.pk, 'mosh-2019-final-10-v1', '3')])
        self.run_cmd(new_refs=queue, tier='high', confirmed_by=md, **APPROVE)
        ref = OlympiadRef.objects.get(problem=yes)
        self.assertEqual((ref.match_method, ref.reviewed_by_human, ref.raw_meta['reviewed_by']),
                         ('manual', True, 'claude-chat-20261009'))
        self.assertFalse(OlympiadRef.objects.filter(problem=eye).exists())


class SameTourTests(MoshAuditTestBase):
    def test_9_two_classless_rows_each_get_own_pair(self):
        """Две строки агрегатора без класса (комплекты `…-10-…` и `…-11-…`) и
        две пары высокого яруса 10 и 11 класса: каждая пара дописывает
        «свою» строку, новых строк нет, одну строку две пары не трогают."""
        p = Problem.objects.create(statement=TEXT['D'])
        r10 = self.aggregator_ref(p, grade='', event_id='ile-mosh-2019-10-1')
        r11 = self.aggregator_ref(p, grade='', event_id='ile-mosh-2019-11-1')
        queue = write_csv(os.path.join(self.s1, 'candidates_review.csv'), [
            {'problem_id': p.pk, 'ref_event_id': ev, 'ref_number': no,
             'task_variant': '', 'fuzzy': '0.95', 'margin': '0.4', 'is_test': 'False',
             'review_tier': 'высокий (текст ≥0,90)'}
            for ev, no in (('mosh-2019-final-11-v1', '1'), ('mosh-2019-final-10-v1', '3'))])
        md = self.review_md(high=[(p.pk, 'mosh-2019-final-11-v1', '1', ''),
                                  (p.pk, 'mosh-2019-final-10-v1', '3', '')])
        self.run_cmd(new_refs=queue, tier='high', confirmed_by=md, **APPROVE)
        r10.refresh_from_db()
        r11.refresh_from_db()
        self.assertEqual(OlympiadRef.objects.filter(problem=p).count(), 2)
        self.assertEqual((r10.raw_meta['official_event_id'], r10.number),
                         ('mosh-2019-final-10-v1', '3'))
        self.assertEqual((r11.raw_meta['official_event_id'], r11.number),
                         ('mosh-2019-final-11-v1', '1'))


class MoshUpdateTests(MoshAuditTestBase):
    def stage_csv(self):
        return write_csv(os.path.join(self.s1, 'catalog_vs_official.csv'), [
            {'catalog_event_id': 'ile-mosh-2019-10-1', 'stage_established': 'final'},
            {'catalog_event_id': 'ile-mosh-2019-11-1', 'stage_established': 'final?'}])

    def test_5_stage_only_with_evidence(self):
        """Пустой этап: ставится только у комплекта с доказанным этапом
        (`final`, в том числе у размноженного id `…__propagated…`), `final?`
        и запуск без --stage-from этап не трогают."""
        p1, p2, p3 = self.problem('B'), self.problem('D'), self.problem('C')
        proven = self.aggregator_ref(p1, number='2')
        guess = self.aggregator_ref(p2, grade='11', event_id='ile-mosh-2019-11-1')
        spread = self.aggregator_ref(
            p3, number='3', event_id='ile-mosh-2019-10-1__propagated_text_sha1__from1')
        rows = [{'ref_id': r.pk, 'problem_id': r.problem_id,
                 'action': 'set_stage+set_official_url', 'coord_status': 'coords_ok',
                 'official_event_id': ev, 'proposed_stage': 'final',
                 'proposed_official_url': URL[ev]}
                for r, ev in ((proven, 'mosh-2019-final-10-v1'),
                              (guess, 'mosh-2019-final-11-v1'),
                              (spread, 'mosh-2019-final-10-v1'))]
        upd, md = self.update_csv(rows), self.review_md()
        self.run_cmd(update_existing=upd, confirmed_by=md, **APPROVE)
        self.assertEqual([r.stage for r in OlympiadRef.objects.order_by('id')], ['', '', ''])
        self.run_cmd(update_existing=upd, confirmed_by=md, stage_from=self.stage_csv(),
                     **APPROVE)
        for ref in (proven, guess, spread):
            ref.refresh_from_db()
        self.assertEqual((proven.stage, guess.stage, spread.stage), ('final', '', 'final'))
        self.assertEqual(guess.official_url, URL['mosh-2019-final-11-v1'])

    def test_6_renumber_doubtful_by_containment(self):
        """Сомнительная перенумеровка: только с флагом и только если текст
        банка входит в задание под новым номером и не входит под текущим.
        Подтверждённая — без флага."""
        sure, doubt_ok, doubt_bad = self.problem('C'), self.problem('B'), self.problem('A')
        r_sure = self.aggregator_ref(sure, source_site='solvehub', number='1')
        r_ok = self.aggregator_ref(doubt_ok, source_site='solvehub', number='3')
        r_bad = self.aggregator_ref(doubt_bad, source_site='solvehub', number='1')
        row = {'action': 'renumber+check+set_official_url',
               'coord_status': 'number_shifted_same_event',
               'official_event_id': 'mosh-2019-final-10-v1'}
        upd = self.update_csv([
            {**row, 'ref_id': r_sure.pk, 'problem_id': sure.pk, 'proposed_number': '3'},
            {**row, 'ref_id': r_ok.pk, 'problem_id': doubt_ok.pk, 'proposed_number': '2'},
            {**row, 'ref_id': r_bad.pk, 'problem_id': doubt_bad.pk, 'proposed_number': '2'}])
        md = self.review_md(doubtful=[(doubt_ok.pk, 'mosh-2019-final-10-v1', '3', '2'),
                                      (doubt_bad.pk, 'mosh-2019-final-10-v1', '1', '2')])
        self.run_cmd(update_existing=upd, confirmed_by=md, **APPROVE)
        numbers = lambda: [OlympiadRef.objects.get(pk=r.pk).number  # noqa: E731
                           for r in (r_sure, r_ok, r_bad)]
        self.assertEqual(numbers(), ['3', '3', '1'])
        self.run_cmd(update_existing=upd, confirmed_by=md, renumber_by_containment=True,
                     **APPROVE)
        self.assertEqual(numbers(), ['3', '2', '1'])
        r_ok.refresh_from_db()
        self.assertEqual(r_ok.raw_meta['aggregator_number'], '3')

    def test_7_twin_without_own_event_untouched(self):
        """Близнец МОШ: найденный комплект — из файла сверки; если комплекта
        класса строки нет в эталоне (финал 2017/18 11 кл.), класс не
        исправляется и строка не трогается."""
        p = self.problem('B')
        ref = self.aggregator_ref(p, year=2018, grade='11', event_id='ile-mosh-2018-11-2')
        upd = self.update_csv([{
            'ref_id': ref.pk, 'problem_id': p.pk, 'coord_status': 'other_event',
            'action': 'other_event+check+set_official_url',
            'official_event_id': 'mosh-2018-final-10-v1',
            'proposed_official_url': URL['mosh-2018-final-10-v1']}])
        write_csv(os.path.join(self.s1, 'existing_refs_text_check.csv'), [{
            'ref_id': ref.pk, 'best_any_event': 'mosh-2018-final-10-v1',
            'best_any_number': '1', 'best_any_variant': ''}])
        before = snapshot()
        self.run_cmd(update_existing=upd, confirmed_by=self.review_md(),
                     twin_pdf_to_pdf=True, **APPROVE)
        self.assertEqual(snapshot(), before)


class DeleteRefsTests(MoshAuditTestBase):
    def test_8_delete_refs_journal_and_rollback(self):
        """--delete-refs: сухой прогон ничего не меняет; запись снимает строки,
        журнал хранит полные копии; откат возвращает их с теми же id и
        полями. Строку чужой олимпиады снять нельзя."""
        p = self.problem('A')
        r1 = self.aggregator_ref(p, source_site='solvehub', year=2020, grade='10',
                                 number='3', raw_meta={'title': 'ВП, а не МОШ'})
        r2 = self.aggregator_ref(p, source_site='solvehub', year=2020, grade='11',
                                 number='3', event_id='solvehub-mosh-2020-11')
        vp = self.aggregator_ref(p, olympiad_slug='vp', event_id='solvehub-vp-2019-9')
        before = snapshot()
        with self.assertRaises(CommandError):
            self.run_cmd(delete_refs=f'{vp.pk}', **APPROVE)
        self.run_cmd(delete_refs=f'{r1.pk},{r2.pk}')
        self.assertEqual(snapshot(), before)
        self.run_cmd(delete_refs=f'{r1.pk},{r2.pk}', **APPROVE)
        self.assertEqual(list(OlympiadRef.objects.filter(problem=p).values_list('pk', flat=True)),
                         [vp.pk])
        journal_path = os.path.join(self.out, self.journals()[-1])
        with open(journal_path, encoding='utf-8') as handle:
            journal = json.load(handle)
        copy = {c['id']: c for c in journal['deleted_refs']}[r1.pk]
        self.assertEqual((copy['raw_meta'], copy['number'], copy['event_id']),
                         ({'title': 'ВП, а не МОШ'}, '3', 'ile-mosh-2019-10-1'))
        self.run_cmd(rollback=journal_path, **APPROVE)
        self.assertEqual(snapshot(), before)
