"""Двигатель импорта эталона, ночь 28→29.10.2026 (сессия P1): разметка пар
(`--decisions`), чужой слаг (`--as-slug`), строки `needs_eyes`, видимость v6,
тестовые вопросы, одинаковые задания двух вариантов, адреса файлов.

Данные выдуманные; кандидаты подкладываются файлом, KaTeX не запускается.
"""
import json
import os
import shutil
import tempfile

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from catalog.filters import base_queryset
from problems.models import OlympiadRef, Problem, ProblemPart, Source, SourceReference
from problems.olympiad_audit import reference_import as ri
from problems.olympiad_audit import registry

ENTR = 'mosh-entrepreneurship'
EV = 'mosh-entrepreneurship-2010-final-8-11-v1'
PDF = 'raw/pdf/mos.olimpiada.ru__upload__files__entr__tasks-2010.pdf'
LONG = ('Предприниматель открывает кофейню: аренда 120 000 рублей в месяц, зарплата '
        'бариста 45 000, закупка зёрен 38 500, средний чек 350 рублей. Сколько чашек '
        'в день нужно продавать, чтобы выйти на безубыточность за 30 дней работы?')
DEVNULL = os.devnull


def _r(number, statement, **extra):
    row = {'event_id': EV, 'number': str(number), 'task_variant': '', 'title': f'Задача {number}',
           'year': 2010, 'academic_year': '2009/2010', 'stage': 'final', 'grade': '8-11',
           'statement_md': statement, 'parts': [], 'figures': [], 'solution_figures': [],
           'solution_md': 'Решение.', 'answer': '42', 'criteria_md': '', 'max_score': 10,
           'source_file': [PDF], 'source_pages': [PDF + '#p1'], 'solution_pages': [],
           'official': True, 'source': 'official', 'needs_eyes': False, 'numbers_ok': True}
    row.update(extra)
    return row


def _quiet():
    return open(DEVNULL, 'w', encoding='utf-8')


class _EngineBase(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.dig = os.path.join(self.tmp, 'entr', 'digitized')
        os.makedirs(self.dig)
        self.source = Source.objects.create(name=registry.get(ENTR).official_source_name)
        self.bank = Problem.objects.create(statement='Совсем другой текст про налоги и бюджет 2010.',
                                           status='published', content_format='markdown')
        self.out = os.path.join(self.tmp, 'out')
        os.makedirs(self.out)

    def run_cmd(self, rows, *extra, decisions=None, cands=None):
        queue = os.path.join(self.dig, 'reference_problems_v2.jsonl')
        with open(queue, 'w', encoding='utf-8') as h:
            for r in rows:
                h.write(json.dumps(r, ensure_ascii=False) + '\n')
        with open(os.path.join(self.out, 'bank_candidates.json'), 'w', encoding='utf-8') as h:
            json.dump({'meta': {}, 'candidates': cands or {}}, h)
        args = ['--olympiad', ENTR, '--queue', queue, '--digitized', self.dig, '--out-dir', self.out,
                '--no-katex', '--bundle-date', '20261028', *extra]
        if decisions is not None:
            path = os.path.join(self.tmp, 'decisions.json')
            with open(path, 'w', encoding='utf-8') as h:
                json.dump({'rows': decisions}, h, ensure_ascii=False)
            args += ['--decisions', path]
        call_command('import_olympiad_reference', *args, stdout=_quiet())
        journals = sorted(f for f in os.listdir(self.out) if f.startswith('import_')
                          and not f.endswith('_dryrun.json'))
        return os.path.join(self.out, journals[-1]) if journals else None

    def apply(self, rows, **kw):
        return self.run_cmd(rows, '--apply', '--yes-i-have-owner-approval', '--as-slug',
                            'mosh-fingram', **kw)

    def rollback(self, journal):
        call_command('import_olympiad_reference', '--olympiad', ENTR, '--rollback', journal,
                     '--apply', '--yes-i-have-owner-approval', stdout=_quiet())


class EngineNight2810Tests(_EngineBase):
    def test_as_slug_writes_under_fingram_and_keeps_original(self):
        self.apply([_r(1, LONG)])
        ref = OlympiadRef.objects.get(event_id=EV)
        self.assertEqual(ref.olympiad_slug, 'mosh-fingram')
        self.assertEqual(ref.raw_meta['original_olympiad']['slug'], ENTR)
        sref = SourceReference.objects.get(problem=ref.problem)
        self.assertEqual(sref.source, self.source)
        self.assertTrue(sref.note.startswith(registry.get(ENTR).olympiad_name))

    def test_needs_eyes_not_written(self):
        self.apply([_r(1, LONG, needs_eyes=True)])
        self.assertFalse(OlympiadRef.objects.filter(event_id=EV).exists())

    def test_v6_visibility_from_reference_fields(self):
        self.apply([_r(1, LONG), _r(2, LONG.replace('кофейню', 'пекарню') + ' 777',
                                    numbers_ok=False)])
        refs = {r.number: r.problem for r in OlympiadRef.objects.filter(event_id=EV)}
        self.assertTrue(base_queryset('catalog').filter(pk=refs['1'].pk).exists())
        self.assertFalse(base_queryset('catalog').filter(pk=refs['2'].pk).exists())
        self.assertFalse(ri.auto_publish_of({'statement_md': 'x', 'numbers_ok': False})[0])
        self.assertEqual(ri.auto_publish_of({'auto_publish_ok': True}), (True, []))

    def test_decision_link_overrides_engine_and_new_creates(self):
        rows = [_r(1, LONG), _r(2, LONG.replace('кофейню', 'булочную'))]
        dec = [{'key': f'{EV}:1', 'decision': 'link', 'bank_id': self.bank.id, 'decided_by': 'owner'},
               {'key': f'{EV}:2', 'decision': 'new', 'bank_id': self.bank.id, 'decided_by': 'owner'}]
        before = Problem.objects.count()
        self.apply(rows, decisions=dec, cands={f'{EV}:1': [self.bank.id], f'{EV}:2': [self.bank.id]})
        self.assertTrue(OlympiadRef.objects.filter(problem=self.bank, event_id=EV, number='1').exists())
        self.assertEqual(Problem.objects.count(), before + 1)

    def test_decision_unsure_stays_with_engine(self):
        dec = [{'key': f'{EV}:1', 'decision': 'unsure', 'bank_id': self.bank.id}]
        self.apply([_r(1, LONG)], decisions=dec)
        self.assertFalse(OlympiadRef.objects.filter(problem=self.bank).exists())

    def test_decision_link_to_problem_already_in_this_round_goes_to_kit(self):
        OlympiadRef.objects.create(problem=self.bank, source_site='official', olympiad_slug='mosh-fingram',
                                   event_id=EV, record_id='x', number='3', match_method='m',
                                   match_score=1.0, raw_meta={'origin': 'old'})
        dec = [{'key': f'{EV}:5', 'decision': 'link', 'bank_id': self.bank.id, 'decided_by': 'owner'}]
        journal = self.apply([_r(5, LONG)], decisions=dec)
        ref = OlympiadRef.objects.get(problem=self.bank, event_id=EV)
        self.assertEqual(ref.raw_meta['kit_numbers'], ['5'])
        self.rollback(journal)
        ref.refresh_from_db()
        self.assertEqual(ref.raw_meta, {'origin': 'old'})

    def test_two_decision_links_same_round_one_ref_and_kit(self):
        """Судья: задания 2 и 3 одного тура — пункты одной задачи банка. Одна новая
        OlympiadRef, второй номер — в её kit_numbers; инвариант плана не срабатывает."""
        dec = [{'key': f'{EV}:2', 'decision': 'link', 'bank_id': self.bank.id, 'decided_by': 'claude:x'},
               {'key': f'{EV}:3', 'decision': 'link', 'bank_id': self.bank.id, 'decided_by': 'claude:x'}]
        journal = self.apply([_r(2, LONG), _r(3, LONG + ' Пункт б.')], decisions=dec)
        ref = OlympiadRef.objects.get(problem=self.bank, event_id=EV)
        self.assertEqual(ref.number, '2')
        self.assertEqual(ref.raw_meta['kit_numbers'], ['3'])
        self.rollback(journal)
        self.assertFalse(OlympiadRef.objects.filter(problem=self.bank, event_id=EV).exists())

    def test_missing_figure_file_hidden_not_crash(self):
        fig = {'path': 'figures_v2/нет_такого.png', 'caption': '', 'flag': '', 'page': 1}
        self.apply([_r(1, LONG, figures=[fig])])
        problem = OlympiadRef.objects.get(event_id=EV).problem
        self.assertFalse(base_queryset('catalog').filter(pk=problem.pk).exists())
        self.assertFalse(problem.figures.exists())

    def test_same_task_in_two_variants_is_one_problem(self):
        rows = [_r(1, LONG, task_variant='1'), _r(1, LONG, task_variant='2')]
        journal = self.apply(rows)
        refs = OlympiadRef.objects.filter(event_id=EV)
        self.assertEqual(refs.count(), 1)
        self.assertEqual(refs[0].raw_meta['also_variants'][0]['variant'], '2')
        n = Problem.objects.count()
        self.apply(rows)                                    # повтор — ноль
        self.assertEqual(Problem.objects.count(), n)
        self.rollback(journal)
        self.assertFalse(OlympiadRef.objects.filter(event_id=EV).exists())

    def test_different_numbers_in_variants_are_two_problems(self):
        rows = [_r(1, LONG, task_variant='1'),
                _r(1, LONG.replace('120 000', '150 000'), task_variant='2')]
        self.apply(rows)
        refs = OlympiadRef.objects.filter(event_id=EV)
        self.assertEqual(refs.count(), 2)                   # по строке у каждой задачи
        self.assertEqual(len({r.problem_id for r in refs}), 2)
        self.assertEqual(SourceReference.objects.filter(source=self.source).count(), 2)
        self.assertEqual(Problem.objects.filter(source_references__source=self.source).distinct().count(), 2)

    def test_test_question_types_and_options(self):
        rows = [
            _r('тест-1.1', '**1. Частное лицо может быть участником только одного товарищества.**\n\n'
                           '1) верно\n2) неверно', answer='1) верно', title='Тест № 1.'),
            _r('тест-2', 'Экономическая теория изучает:\n1) только рынок\n2) все системы\n3) ничего',
               answer='2'),
            _r('тест-3', 'Выберите все верные:\n1) спрос\n2) предложение\n3) налог', answer='1, 2'),
            _r('тест-4', 'Сколько будет дважды два?', answer='4'),
        ]
        self.apply(rows)
        by = {r.number: r.problem for r in OlympiadRef.objects.filter(event_id=EV)}
        self.assertEqual(by['тест-1.1'].problem_type, 'верно_неверно')
        self.assertEqual(list(by['тест-1.1'].parts.order_by('order').values_list('label', 'answer')),
                         [('а', 'верно'), ('б', '')])
        self.assertEqual(by['тест-2'].problem_type, 'единственный_выбор')
        self.assertEqual(by['тест-2'].answer, '2')
        self.assertNotIn('1) только рынок', by['тест-2'].statement)
        self.assertEqual(ProblemPart.objects.filter(problem=by['тест-2'], answer='верно').count(), 1)
        self.assertEqual(by['тест-3'].problem_type, 'множественный_выбор')
        self.assertEqual(by['тест-4'].problem_type, 'тест: короткий ответ')
        self.assertTrue(by['тест-1.1'].title.startswith('МОШ по основам предпринимательства'))


class UpdateFromNewVersionTests(_EngineBase):
    """2.2: своя задача обновляется из новой версии эталона только в изменённых полях."""

    def test_changed_field_updated_with_version_conflict_and_rollback(self):
        from problems.models import ProblemVersion
        old_rows = [_r(1, LONG), _r(2, LONG.replace('кофейню', 'пекарню'))]
        journal = self.apply(old_rows)
        old_path = os.path.join(self.tmp, 'v6.jsonl')
        new_path = os.path.join(self.tmp, 'v7.jsonl')
        new_rows = [_r(1, LONG + ' Учтите налог 6 %.'), _r(2, LONG.replace('кофейню', 'пекарню'))]
        for path, rows in ((old_path, old_rows), (new_path, new_rows)):
            with open(path, 'w', encoding='utf-8') as h:
                for r in rows:
                    h.write(json.dumps(r, ensure_ascii=False) + '\n')
        p1 = OlympiadRef.objects.get(event_id=EV, number='1').problem
        p2 = OlympiadRef.objects.get(event_id=EV, number='2').problem

        def upd(*extra):
            call_command('update_olympiad_reference', '--olympiad', ENTR, '--journal', journal,
                         '--old', old_path, '--new', new_path, '--old-digitized', self.dig,
                         '--new-digitized', self.dig, '--out-dir', self.tmp, *extra, stdout=_quiet())
            return sorted(f for f in os.listdir(self.tmp) if f.startswith('update_') and 'dryrun' not in f)

        done = upd('--apply', '--yes-i-have-owner-approval')
        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertTrue(p1.statement.endswith('Учтите налог 6 %.'))
        self.assertEqual(ProblemVersion.objects.filter(problem=p1).count(), 1)
        self.assertFalse(ProblemVersion.objects.filter(problem=p2).exists())
        done2 = upd('--apply', '--yes-i-have-owner-approval')          # повтор — ноль
        with open(os.path.join(self.tmp, [f for f in done2 if f not in done][0]), encoding='utf-8') as h:
            self.assertEqual(json.load(h)['changes'], [])
        call_command('update_olympiad_reference', '--olympiad', ENTR, '--rollback',
                     os.path.join(self.tmp, done[0]), '--apply', '--yes-i-have-owner-approval', stdout=_quiet())
        p1.refresh_from_db()
        self.assertFalse(p1.statement.endswith('Учтите налог 6 %.'))
        Problem.objects.filter(pk=p1.pk).update(statement='Правка человека.')
        upd('--apply', '--yes-i-have-owner-approval')                  # конфликт — не трогаем
        p1.refresh_from_db()
        self.assertEqual(p1.statement, 'Правка человека.')


class ImportTitlesCommandTests(TestCase):
    """Заглушка → title_candidate только у задач журнала; повтор — ноль; откат."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.stub = Problem.objects.create(statement='Инвестор выбирает облигацию.', title='Задание 4',
                                           title_candidate='Выбор облигации')
        self.real = Problem.objects.create(statement='У Александра 300 000 руб.',
                                           title='Как не потерять деньги?', title_candidate='Риск')
        self.alien = Problem.objects.create(statement='Чужая задача.', title='Задача 1',
                                            title_candidate='Чужой кандидат')
        self.journal = os.path.join(self.tmp, 'import_x.json')
        with open(self.journal, 'w', encoding='utf-8') as h:
            json.dump({'command': 'import_olympiad_reference', 'applied': True,
                       'created_problem_ids': [self.stub.id, self.real.id]}, h)

    def run_titles(self, *extra):
        call_command('import_reference_titles', '--journal', self.journal, *extra, stdout=_quiet())
        return sorted(f for f in os.listdir(self.tmp) if f.startswith('titles_') and 'dryrun' not in f)

    def test_stub_replaced_real_and_alien_untouched_repeat_zero_rollback(self):
        done = self.run_titles('--apply', '--yes-i-have-owner-approval')
        for p in (self.stub, self.real, self.alien):
            p.refresh_from_db()
        self.assertEqual((self.stub.title, self.stub.title_source), ('Выбор облигации', 'model-empty'))
        self.assertEqual(self.real.title, 'Как не потерять деньги?')
        self.assertEqual(self.alien.title, 'Задача 1')
        done2 = self.run_titles('--apply', '--yes-i-have-owner-approval')
        with open(os.path.join(self.tmp, [f for f in done2 if f not in done][0]), encoding='utf-8') as h:
            self.assertEqual(json.load(h)['changes'], [])
        call_command('import_reference_titles', '--rollback', os.path.join(self.tmp, done[0]),
                     '--apply', '--yes-i-have-owner-approval', stdout=_quiet())
        self.stub.refresh_from_db()
        self.assertEqual(self.stub.title, 'Задание 4')


class UrlMapTests(SimpleTestCase):
    def test_address_from_file_name_and_official_host(self):
        m = ri.UrlMap({}, ('olimpiada.ru',))
        self.assertEqual(m.get('mos.olimpiada.ru__upload__files__a.pdf'),
                         ('https://mos.olimpiada.ru/upload/files/a.pdf', True))
        self.assertEqual(m.get('api.solvehub.app__uploads__x.pdf'),
                         ('https://api.solvehub.app/uploads/x.pdf', False))
        self.assertIsNone(m.get('2014_tasks_10.pdf'))
