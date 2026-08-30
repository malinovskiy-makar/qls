# -*- coding: utf-8 -*-
"""Разбор карточек-заглушек: мусор прячем, настоящие задачи — нет.

Опасность здесь односторонняя. Спрятать настоящую задачу хуже, чем
оставить видимой помету: помету человек прочитает и пожмёт плечами, а
спрятанную задачу никто не найдёт. Поэтому больше половины тестов —
про то, что НЕ должно попасть в мусор.
"""
import io

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from problems.management.commands.classify_stub_problems import Command
from problems.models import Problem
from problems.tests.factories import link_source, make_problem, make_source

BS = chr(92)


def group_of(text):
    """В какую группу попадёт карточка с таким текстом.

    Зовёт БОЕВОЕ решающее правило, а не повторяет его здесь. Первая
    версия этих тестов условие дублировала — и осталась зелёной, когда
    правило в команде сломали нарочно. Проверка, которую нельзя сломать,
    ничего и не проверяет."""
    return Command.group_for(text)[0]


class JunkFamilyTests(SimpleTestCase):
    """Живые карточки, проверенные глазами: это не задачи."""

    def test_latex_scaffolding(self):
        self.assertEqual(group_of(BS + 'end {document}'), 'junk')

    def test_solution_template(self):
        self.assertEqual(
            group_of('задача\n\n' + BS + 'solution\n{ответ или решение}'), 'junk')

    def test_grading_note(self):
        self.assertEqual(
            group_of('0.5 за два пункта, 1 задача в файле (1 задача)'), 'junk')

    def test_form_header(self):
        self.assertEqual(
            group_of('Имя и фамилия:\n\n\n\nВыберите единственный верный ответ:'),
            'junk')

    def test_author_stub(self):
        self.assertEqual(group_of('Привет я задача А я пунтк а я второй пункт'),
                         'junk')

    def test_bare_answer_label(self):
        self.assertEqual(group_of('(множественный выбор)'), 'junk')

    def test_section_heading(self):
        self.assertEqual(
            group_of('Задачи на самостоятельное решение, листок — 2'), 'junk')

    def test_author_aside(self):
        self.assertEqual(
            group_of('Как хотите так и принимайте, задание творческое)))'), 'junk')


class RealProblemsMustSurviveTests(SimpleTestCase):
    """ГЛАВНОЕ: помета на настоящей задаче не делает её мусором."""

    def test_long_problem_titled_yet_another_task(self):
        """#35374: «Ещё задача» — заголовок живой задачи на 974 символа."""
        text = ('Ещё задача\n\nТётя Оля хочет поехать летом на море и может '
                'по-разному спланировать этот отпуск. ' + 'Подробности. ' * 12)
        self.assertEqual(group_of(text), 'real')

    def test_real_problem_under_a_form_header(self):
        """#4425: шапка бланка стоит над настоящим листочком."""
        text = ('Имя и фамилия:\n\nНа рынке монополист продает круассаны, '
                'спрос на которые задан функцией $Q=120-P$. Найдите цену.')
        self.assertEqual(group_of(text), 'real')

    def test_true_false_assertion_is_a_problem(self):
        """Формат SolveHub: утверждение, ученик отвечает «верно/неверно»."""
        self.assertEqual(group_of('Алюминий добывают в шахтах.'), 'real')

    def test_another_true_false_assertion(self):
        self.assertEqual(
            group_of('Рецессия не может сопровождаться инфляцией.'), 'real')

    def test_short_task_with_math(self):
        self.assertEqual(
            group_of('Найдите хотя бы $1$ корень уравнения $x^{x^x}=8x$'), 'real')

    def test_multiple_choice_with_options(self):
        self.assertEqual(
            group_of('Налог на продажи является:\n\nВарианты ответа:\n\n'
                     '1. регрессивным\n2. прямым'), 'real')

    def test_grading_words_inside_a_real_problem(self):
        """«1,7 за один год» — это условие, а не заметка о баллах."""
        text = ('Изменение дефлятора ВВП с 1,5 до 1,7 за один год возможно '
                'в условиях: 1) дефляции; 2) дезинфляции; 3) инфляции.')
        self.assertEqual(group_of(text), 'real')


class BorderlineTests(SimpleTestCase):
    """Незаконченный обрывок — сомнительный, но НЕ мусор: не гадаем."""

    def test_bare_title_is_borderline(self):
        self.assertEqual(
            group_of('Никак не решусь, куда же сделать первый шаг'), 'borderline')

    def test_heading_without_period_is_borderline(self):
        self.assertEqual(group_of('Крутая задача\n\nЧетвертая\n\n Про олигополию'),
                         'borderline')

    def test_figure_only_card_is_borderline(self):
        self.assertEqual(group_of('[[FIGURE:%s]]' % ('a' * 64)), 'borderline')


class ApplyTests(TestCase):
    """`--apply` прячет мусор статусом и умеет откатываться."""

    def setUp(self):
        import shutil, tempfile
        self.src = make_source('Источник')
        self.other = make_source('Чужой')
        # ⚠️ свой --report-dir: иначе прогон набора затирает боевой журнал
        self.reports = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.reports, ignore_errors=True)

    def _card(self, text, source=None):
        p = make_problem(text, status=Problem.Status.PUBLISHED,
                         hidden_pending_review=True)
        link_source(p, source or self.src)
        return p

    def run_cmd(self, **kw):
        out = io.StringIO()
        kw.setdefault('sources', str(self.src.id))
        kw.setdefault('report_dir', self.reports)
        call_command('classify_stub_problems', stdout=out, **kw)
        return out.getvalue()

    def test_junk_becomes_hidden(self):
        junk = self._card('(множественный выбор)')
        self.run_cmd(apply=True)
        junk.refresh_from_db()
        self.assertEqual(junk.status, Problem.Status.HIDDEN)

    def test_real_problem_is_untouched(self):
        good = self._card('Алюминий добывают в шахтах.')
        self.run_cmd(apply=True)
        good.refresh_from_db()
        self.assertEqual(good.status, Problem.Status.PUBLISHED)

    def test_foreign_source_is_untouched(self):
        junk = self._card('(множественный выбор)', source=self.other)
        self.run_cmd(apply=True)
        junk.refresh_from_db()
        self.assertEqual(junk.status, Problem.Status.PUBLISHED)

    def test_dry_run_changes_nothing(self):
        junk = self._card('(множественный выбор)')
        out = self.run_cmd()
        junk.refresh_from_db()
        self.assertEqual(junk.status, Problem.Status.PUBLISHED)
        self.assertIn('СУХОЙ ПРОГОН', out)

    def test_revert_restores_status(self):
        junk = self._card('(множественный выбор)')
        self.run_cmd(apply=True)
        self.run_cmd(revert=True)
        junk.refresh_from_db()
        self.assertEqual(junk.status, Problem.Status.PUBLISHED)

    def test_problem_count_never_changes(self):
        self._card('(множественный выбор)')
        self._card('Алюминий добывают в шахтах.')
        before = Problem.objects.count()
        self.run_cmd(apply=True)
        self.assertEqual(Problem.objects.count(), before)
