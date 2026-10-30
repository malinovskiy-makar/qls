"""Заливка заданий пакета олимпиад в банк (`import_olympiads_tasks`).

Пакет — во временной папке из крошечных комплектов, как в
`test_import_kits.py`: комплекты заливаются той же командой
`import_olympiads_kits`, задания — проверяемой.
"""
import os
import subprocess
import sys
import textwrap

from django.conf import settings
from django.test import TestCase, override_settings
from django.core.management import call_command
from io import StringIO

from catalog.filters import base_queryset
from olympiads import bank_match as bm
from olympiads import tasks_import as ti
from olympiads.models import OlympiadVariantItem
from problems.models import Problem, ProblemFigure

from .test_import_kits import PackageMixin, make_kit_data

LONG = ('Спрос на товар задан функцией Qd = 100 - 2P, предложение — функцией '
        'Qs = 3P - 50. Найдите равновесную цену и объём продаж на рынке.')
TAIL = (' Известно также, что государство вводит потоварный налог в '
        'размере пяти рублей с каждой единицы, его уплачивает продавец.')
PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 32


def make_task(ref_key='k:1', statement=LONG, status='clean', **kwargs):
    task = {
        'ref_key': ref_key, 'olympiad': 'mosh', 'event_id': 'k',
        'number': ref_key.split(':', 1)[1], 'task_variant': '', 'title': '',
        'max_score': 10, 'statement_md': statement, 'section_md': '',
        'parts': [], 'tables': 0, 'test': None, 'answer': '',
        'solution_md': '', 'criteria_md': '', 'figures': [],
        'source_file': [], 'source_pages': [], 'solution_pages': [],
        'criteria_pages': [],
        'quality': {'status': status, 'reasons': [] if status == 'clean'
                    else ['тест без ключа'], 'has_solution': False},
        'bank': None,
    }
    task.update(kwargs)
    return task


class TasksMixin(PackageMixin):

    def import_tasks(self, *extra):
        out = StringIO()
        with override_settings(BASE_DIR=self.root):
            call_command('import_olympiads_tasks', self.root, *extra,
                         '--report-dir', self.root, stdout=out)
        return out.getvalue()

    def load(self, tasks, kit_id='mosh-2023-final-9-v1'):
        """Комплект в пакет и в базу, затем задания — с записью."""
        self.write_kit(make_kit_data(kit_id=kit_id, tasks=tasks))
        self.run_import('--apply')
        return self.import_tasks('--apply')

    def write_figure(self, rel, data=PNG):
        path = os.path.join(self.root, *rel.split('/'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as fh:
            fh.write(data)

    def bank_problem(self, statement=LONG, **kwargs):
        defaults = dict(status='published', answer='P = 30', solution='Старое.',
                        human_review='approved')
        defaults.update(kwargs)
        return Problem.objects.create(statement=statement, **defaults)


class MatchingTests(TasksMixin, TestCase):

    def test_matched_task_creates_no_problem(self):
        """1. Совпавшее с банком задание не заводит новую задачу."""
        old = self.bank_problem()
        before = Problem.objects.count()
        self.load([make_task('k:1', solution_md='Новое решение.')])
        self.assertEqual(Problem.objects.count(), before)
        self.assertEqual(OlympiadVariantItem.objects.get(ref_key='k:1').problem_id,
                         old.pk)

    def test_existing_problem_fields_untouched(self):
        """2. Поля задачи банка не переписываются ничем из пакета."""
        old = self.bank_problem()
        snapshot = Problem.objects.filter(pk=old.pk).values().get()
        self.load([make_task('k:1', answer='другой', solution_md='Новое.',
                             criteria_md='Критерии: 10 баллов за ответ.',
                             title='Новое имя')])
        self.assertEqual(Problem.objects.filter(pk=old.pk).values().get(), snapshot)

    def test_sign_only_difference_is_not_a_match(self):
        """Пара, отличающаяся только знаком, не связывается (норма слепа к знаку)."""
        self.bank_problem(statement=LONG.replace('100 - 2P', '100 + 2P'))
        self.load([make_task('k:1')])
        item = OlympiadVariantItem.objects.get(ref_key='k:1')
        self.assertEqual(item.problem.status, 'draft')

    def test_item_flags_follow_bank_problem_not_package(self):
        """У совпавшего задания признаки — по задаче банка, а не по пакету."""
        self.bank_problem(solution='', answer='')
        self.load([make_task('k:1', solution_md='Решение пакета.', answer='P = 30',
                             criteria_md='За ответ — 10 баллов.')])
        item = OlympiadVariantItem.objects.get(ref_key='k:1')
        self.assertFalse(item.has_solution)
        self.assertFalse(item.has_criteria)
        self.assertFalse(item.has_answer)

    def test_new_problem_flags_follow_written_solution(self):
        self.load([make_task('k:1', criteria_md='За ответ — 10 баллов.')])
        item = OlympiadVariantItem.objects.get(ref_key='k:1')
        self.assertFalse(item.has_solution)
        self.assertTrue(item.has_criteria)

    def test_number_replaced_is_not_a_match(self):
        self.bank_problem(statement=LONG.replace('100 - 2P', '90 - 2P'))
        self.load([make_task('k:1')])
        item = OlympiadVariantItem.objects.get(ref_key='k:1')
        self.assertEqual(item.problem.status, 'draft')


class NewProblemTests(TasksMixin, TestCase):

    def test_new_problem_is_draft_and_hidden_pending_review(self):
        """3. Новая задача — И draft, И hidden_pending_review."""
        self.load([make_task('k:1')])
        problem = OlympiadVariantItem.objects.get(ref_key='k:1').problem
        self.assertEqual(problem.status, Problem.Status.DRAFT)
        self.assertTrue(problem.hidden_pending_review)
        self.assertEqual(problem.content_format, Problem.ContentFormat.MARKDOWN)

    def test_catalog_does_not_see_new_problems(self):
        """4. Каталог и подбор репетитора новых задач не видят."""
        self.bank_problem(statement='Другая задача про эластичность спроса по '
                          'цене товара, которую видно в каталоге уже давно.',
                          hidden_pending_review=False)
        before = {g: base_queryset(g).count() for g in ('catalog', 'tutor')}
        self.load([make_task('k:1'), make_task('k:2', statement=LONG + ' Ещё.')])
        new_ids = set(OlympiadVariantItem.objects.values_list('problem_id', flat=True))
        for gate in ('catalog', 'tutor'):
            self.assertEqual(base_queryset(gate).count(), before[gate])
            self.assertFalse(base_queryset(gate).filter(id__in=new_ids).exists())

    def test_criteria_go_as_section_after_solution(self):
        """5. Критерии — разделом в конце решения."""
        self.load([make_task('k:1', solution_md='Решение: P = 30.',
                             criteria_md='За верный ответ — 10 баллов.')])
        problem = OlympiadVariantItem.objects.get(ref_key='k:1').problem
        self.assertEqual(problem.solution, 'Решение: P = 30.\n\n'
                         '## Критерии оценивания\n\nЗа верный ответ — 10 баллов.')

    def test_criteria_without_solution_give_only_section(self):
        """6. Критерии без решения — решение из одного раздела критериев."""
        self.load([make_task('k:1', criteria_md='**Критерии оценивания:**\n'
                             'За верный ответ — 10 баллов.')])
        problem = OlympiadVariantItem.objects.get(ref_key='k:1').problem
        self.assertEqual(problem.solution, '## Критерии оценивания\n\n'
                         'За верный ответ — 10 баллов.')

    def test_flagged_lives_on_item_not_on_problem(self):
        """8. «Под вопросом» — у позиции; у задачи флаг шлюза не ставится."""
        self.load([make_task('k:1', status='flagged')])
        item = OlympiadVariantItem.objects.get(ref_key='k:1')
        self.assertEqual(item.quality, 'flagged')
        self.assertEqual(item.quality_reasons, ['тест без ключа'])
        self.assertFalse(item.problem.needs_quality_review)
        self.assertEqual(item.problem.content_status, 'ok')

    def test_same_text_two_ref_keys_one_problem_two_items(self):
        """10. Разные ref_key, один текст — одна задача, две позиции."""
        before = Problem.objects.count()
        self.load([make_task('k:5:1'), make_task('k:5:2')])
        items = OlympiadVariantItem.objects.filter(ref_key__in=['k:5:1', 'k:5:2'])
        self.assertEqual(items.count(), 2)
        self.assertEqual(len({i.problem_id for i in items}), 1)
        self.assertEqual(Problem.objects.count(), before + 1)

    def test_sign_difference_is_two_problems(self):
        """Грубая нормализация «съела» бы знак: склеивать такие нельзя."""
        self.load([make_task('k:1'), make_task('k:2', statement=LONG.replace(
            '100 - 2P', '100 + 2P'))])
        self.assertEqual(len(set(OlympiadVariantItem.objects
                                 .values_list('problem_id', flat=True))), 2)

    def test_test_options_become_parts_with_marks(self):
        test = {'kind': 'multi', 'key': '1, 3', 'options': [
            {'label': '1', 'text': 'Банкноты', 'correct': True},
            {'label': '2', 'text': 'Векселя', 'correct': False},
            {'label': '3', 'text': 'Чеки', 'correct': True}]}
        self.load([make_task('k:1', test=test, answer='1, 3')])
        problem = OlympiadVariantItem.objects.get(ref_key='k:1').problem
        self.assertEqual(problem.problem_type, 'тест: все верные')
        self.assertEqual([(p.label, p.answer) for p in problem.parts.all()],
                         [('1', 'верно'), ('2', ''), ('3', 'верно')])

    def test_broken_test_is_plain_problem_with_key_in_answer(self):
        test = {'kind': 'broken', 'key': '4)', 'options': []}
        self.load([make_task('k:1', test=test, status='flagged')])
        problem = OlympiadVariantItem.objects.get(ref_key='k:1').problem
        self.assertEqual(problem.problem_type, '')
        self.assertEqual(problem.answer, '4)')

    def test_missing_section_phrase_is_appended(self):
        section = '**Выберите один ответ.**\n\n**Считайте, что налогов нет.**'
        self.load([make_task('k:1', statement='**Выберите один ответ.**\n\n' + LONG,
                             section_md=section)])
        statement = OlympiadVariantItem.objects.get(ref_key='k:1').problem.statement
        self.assertTrue(statement.endswith('**Считайте, что налогов нет.**'))
        self.assertEqual(statement.count('Выберите один ответ'), 1)

    def test_figure_without_file_flags_item(self):
        self.load([make_task('k:1', figures=[{'field': 'statement', 'path': None,
                                              'caption': 'график', 'page': 1,
                                              'flag': 'нет рамки', 'rejected': None}])])
        item = OlympiadVariantItem.objects.get(ref_key='k:1')
        self.assertEqual(item.quality, 'flagged')
        self.assertIn(ti.REASON_NO_FIGURE_FILE, item.quality_reasons)
        self.assertEqual(item.pages['figures'][0]['caption'], 'график')

    def test_fewer_options_than_parts_flags_item(self):
        test = {'kind': 'single', 'key': '1', 'options': [
            {'label': '1', 'text': 'да', 'correct': True}]}
        parts = [{'label': '1', 'text': 'да', 'points': None},
                 {'label': '2', 'text': 'нет', 'points': None}]
        self.load([make_task('k:1', test=test, parts=parts, answer='1')])
        item = OlympiadVariantItem.objects.get(ref_key='k:1')
        self.assertIn(ti.REASON_FEWER_OPTIONS, item.quality_reasons)

    def test_figure_lands_with_marker(self):
        rel = 'mosh/figures/k/k_1_1.png'
        self.write_figure(rel)
        self.load([make_task('k:1', figures=[{'field': 'statement', 'path': rel,
                                              'caption': '', 'page': 1, 'flag': '',
                                              'rejected': None}])])
        problem = OlympiadVariantItem.objects.get(ref_key='k:1').problem
        figure = ProblemFigure.objects.get(problem=problem)
        self.assertEqual(bytes(figure.image_data), PNG)
        self.assertIn('[[FIGURE:{}]]'.format(figure.tikz_hash), problem.statement)


class CriteriaCleaningTests(TestCase):
    """7. Продублированные критерии чистятся, одинарные не трогаются."""

    BLOCK = ('Схема проверки\n\nа) Найдена равновесная цена P = 30 — 2 балла.\n'
             'б) Найден объём продаж Q = 40 — 2 балла.\n')

    def test_exact_double_keeps_one_half(self):
        text, rule = ti.clean_criteria(self.BLOCK + '\n' + self.BLOCK)
        self.assertEqual(rule, 'exact')
        self.assertEqual(text, self.BLOCK.rstrip())

    def test_near_repeat_after_second_heading_is_dropped(self):
        second = self.BLOCK.replace('2 балла', '**2 балла**')
        text, rule = ti.clean_criteria('**' + self.BLOCK + '\n' + second)
        self.assertEqual(rule, 'headings')
        self.assertEqual(text, ('**' + self.BLOCK).rstrip())

    def test_single_and_distinct_sections_untouched(self):
        self.assertEqual(ti.clean_criteria(self.BLOCK), (self.BLOCK, None))
        other = ('Критерии оценивания\n\nЗа построение графика спроса и '
                 'предложения с подписанными осями — 4 балла.\n')
        both = self.BLOCK + '\n' + other
        self.assertEqual(ti.clean_criteria(both), (both, None))


class IdempotencyTests(TasksMixin, TestCase):

    def test_second_run_creates_and_changes_nothing(self):
        """9. Повторный прогон: 0 создано, 0 изменено."""
        self.load([make_task('k:1'), make_task('k:2', statement=LONG + ' Б.'),
                   make_task('k:3', status='flagged', statement=LONG + ' В.')])
        problems = list(Problem.objects.order_by('id').values())
        items = list(OlympiadVariantItem.objects.order_by('id').values())
        out = self.import_tasks('--apply')
        self.assertIn('новых задач будет создано', out)
        self.assertEqual(list(Problem.objects.order_by('id').values()), problems)
        self.assertEqual(list(OlympiadVariantItem.objects.order_by('id').values()), items)
        plan = ti.make_plan(self.root)
        self.assertEqual(ti.summarize(plan)['позиций будет создано'], 0)
        self.assertEqual(ti.summarize(plan)['новых задач будет создано'], 0)
        self.assertEqual(ti.summarize(plan)['позиций с изменившейся записью пакета'], 0)

    def test_human_review_is_never_overwritten(self):
        self.load([make_task('k:1')])
        problem = OlympiadVariantItem.objects.get(ref_key='k:1').problem
        Problem.objects.filter(pk=problem.pk).update(
            human_review='approved', statement='Поправлено человеком.')
        self.write_kit(make_kit_data(tasks=[make_task('k:1', answer='новый')]))
        self.import_tasks('--apply')
        problem.refresh_from_db()
        self.assertEqual(problem.statement, 'Поправлено человеком.')
        self.assertEqual(problem.answer, '')

    def test_dry_run_writes_nothing(self):
        self.write_kit(make_kit_data(tasks=[make_task('k:1')]))
        self.run_import('--apply')
        before = Problem.objects.count()
        self.import_tasks()
        self.assertEqual(Problem.objects.count(), before)
        self.assertEqual(OlympiadVariantItem.objects.count(), 0)


class OperatorSequenceTests(TestCase):

    def test_same_sign_in_any_spelling(self):
        self.assertEqual(bm.operator_sequence('Q = 100 − 2P, $a \\cdot b \\le c$'),
                         bm.operator_sequence('Q = 100 - 2P, $a·b ≤ c$'))

    def test_sign_change_differs(self):
        self.assertNotEqual(bm.operator_sequence('P = 100 - 2Q'),
                            bm.operator_sequence('P = 100 + 2Q'))

    def test_prose_dash_bullets_ranges_are_not_signs(self):
        self.assertEqual(bm.operator_sequence(
            'Спрос — функция.\n- пункт\nМОШ 22-23, задачи 5—8, кто-то'), [])


class DeterministicPickTests(TestCase):
    """Два равных кандидата → связь одна и та же, в любом процессе.

    Дефект разведки 30.10: при равных кандидатах решал порядок в множестве,
    а он зависит от случайного хеширования строк — от запуска к запуску
    задание связывалось с разными задачами банка.
    """

    def test_better_text_wins_over_number_among_equal_status(self):
        rows = [(10, 'Ломаная линейная кривая предложения, выходящая из начала '
                     'координат, имеет единичную ценовую эластичность в любой точке.',
                 'published', None, 'approved'),
                (20, 'Линейная кривая предложения, выходящая из начала '
                     'координат, имеет единичную ценовую эластичность в любой точке.',
                 'published', None, 'approved')]
        index = bm.BankIndex(rows, {})
        task = make_task('k:1', statement=rows[1][1] + ' Да или нет?')
        self.assertEqual(index.match(task)['problem_id'], 20)

    def test_same_link_in_every_process(self):
        script = textwrap.dedent('''
            import sys
            sys.path.insert(0, {base!r})
            from olympiads import bank_match as bm
            text = {text!r}
            # Подмены — только на БУКВАХ и вдали друг от друга и от краёв:
            # тогда у всех восьми кандидатов поровну общих фрагментов и
            # одинаковое сходство — ничья, которую раньше решал случай.
            letters = [i for i in range(40, len(text) - 40)
                       if text[i].isalpha() and text[i] != 'ж']
            positions = [letters[k * len(letters) // 8] for k in range(8)]
            rows = []
            for n, pos in enumerate(positions):
                cand = text[:pos] + 'ж' + text[pos + 1:]
                rows.append((108 - n, cand, 'published', None, 'approved'))
            task = {{'statement_md': text[:3] + 'щ' + text[4:], 'parts': []}}
            print(bm.BankIndex(rows, {{}}).match(task)['problem_id'])
        ''').format(base=str(settings.BASE_DIR), text=LONG + TAIL)
        seen = set()
        for seed in range(30):
            env = dict(os.environ, PYTHONHASHSEED=str(seed))
            out = subprocess.run([sys.executable, '-c', script], env=env,
                                 capture_output=True, text=True, check=True)
            seen.add(out.stdout.strip())
        self.assertEqual(seen, {'101'})
