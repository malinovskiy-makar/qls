"""Проверки детекторов пропавшей картинки (``problems/missing_figures.py``).

Каждый тест ниже соответствует классу, который РЕАЛЬНО встретился в банке при
ручной выборке 93 кандидатов (сессия 2026-08-24). Ложные срабатывания
записаны с номерами задач, чтобы будущая правка паттернов не вернула их
молча.
"""

import os

from django.test import TestCase

from problems.missing_figures import (
    MISSING_FIGURE_TAG_SLUG,
    has_own_data, has_explicit_image_markup, method_a_hits, method_b_hits,
    references_missing_figure, scan_problems, unsolvable_ids,
)
from problems.models import Problem, ProblemPart, Source, SourceReference


class MethodATests(TestCase):
    """Метод А — явная разметка картинки."""

    def test_markdown_image(self):
        self.assertTrue(has_explicit_image_markup('текст ![подпись](a/b.png) хвост'))

    def test_includegraphics(self):
        self.assertTrue(has_explicit_image_markup(r'\includegraphics[width=5cm]{img1.png}'))

    def test_html_img(self):
        self.assertTrue(has_explicit_image_markup('<img src="x.png" alt="">'))

    def test_bare_image_url(self):
        # Реальный случай ILE, задача 3209.
        self.assertTrue(has_explicit_image_markup(
            'условие http://iloveeconomics.ru/sites/default/files/u80/pirat.gif далее'))

    def test_all_listed_extensions_are_caught(self):
        for ext in ('png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'):
            with self.subTest(ext=ext):
                self.assertTrue(has_explicit_image_markup(
                    f'см https://example.com/pic.{ext} тут'))

    def test_plain_link_is_not_an_image(self):
        self.assertFalse(has_explicit_image_markup(
            'источник https://example.com/task/1234 без картинки'))

    def test_markdown_link_without_bang_is_not_an_image(self):
        self.assertFalse(has_explicit_image_markup('[подпись](страница)'))

    def test_counts_are_reported_per_kind(self):
        hits = method_a_hits('![a](1.png) ![b](2.png) <img src="c">')
        self.assertEqual(hits['markdown'], 2)
        self.assertEqual(hits['html_img'], 1)


class MethodBTruePositiveTests(TestCase):
    """Метод Б — формулировки, которые ДОЛЖНЫ считаться отсылкой."""

    CASES = [
        ('см. рис.', 'предельные издержки убывают (см. рис.).'),
        ('см. рисунок 1', 'форму выпуклого четырехугольника (см. рисунок 1).'),
        ('на рисунке', 'Описанная ситуация изображена на рисунке.'),
        ('на графике ниже', 'На графике ниже представлена динамика Джини.'),
        ('на диаграмме ниже', 'На диаграмме ниже приведена динамика доходности.'),
        ('из нижеприведённых', 'Какой из нижеприведённых графиков показывает рост?'),
        ('на каком из приведённых ниже',
         'На каких из приведённых ниже графиков показано увеличение спроса?'),
        ('по представленному рисунку',
         'По представленному рисунку эластичности не сравнимы.'),
        ('на рисунке внизу', 'На рисунке внизу изображены графики дохода.'),
        ('the graph below', 'The graph below shows a binding price floor.'),
        ('the figure below', 'Consider the figure below.'),
        ('the chart above', 'the chart above shows his total utility'),
        ('based on the figure', 'Based on the figure, which expression equals the tax?'),
        ('shown in the graph', 'For the firm shown in the graph below.'),
        ('depicted in the graph', 'the profit-maximizing monopolist depicted in the graph'),
        ('the graph provided', 'curves are illustrated in the graph provided.'),
        ('Figure 1', 'Refer to Figure 1 for the market equilibrium.'),
    ]

    def test_true_positives(self):
        for label, text in self.CASES:
            with self.subTest(label):
                self.assertTrue(references_missing_figure(text),
                                f'не поймано: {text!r}')


class MethodBFalsePositiveTests(TestCase):
    """Метод Б — формулировки, которые считать отсылкой НЕЛЬЗЯ.

    Все до одной найдены глазами в реальных задачах банка. Если тест
    покраснел — значит, правка паттернов вернула старую ловушку.
    """

    CASES = [
        # Главная ловушка: «график» как обычный экономический термин.
        ('термин', 'Постройте график спроса и предложения на этот товар.'),
        ('термин 2', 'На графике функции предложения найдите эластичность.'),
        ('термин 3', 'Изобразите графически кривую производственных возможностей.'),
        ('англ. задание', 'Draw a graph showing the market equilibrium.'),
        # Задача 33568: «схема» — порядок выплат, не чертёж.
        ('схема-порядок', 'Саша взял кредит по следующей схеме: банк начисляет проценты.'),
        # Задача 3519: «Схема 1»/«Схема 2» — варианты выплаты приза.
        ('схема с номером', 'Схема 1. Единовременно выплачивается 500 тыс. руб.'),
        # Задача 52561: «Рассмотрим график» содержит «смотрим график».
        ('рассмотрим', 'Рассмотрим график предложения S для линейной функции.'),
        ('рассмотрение', 'Рассмотрев график, экономист сделал вывод.'),
        # Задача 30335: ученик сам помечает на своём чертеже.
        ('укажите на', 'Во всех пунктах укажите на рисунках координаты точек.'),
        ('отметьте на', 'Отметьте на графике выручку от каждого этапа.'),
        # Задача 2490: график самого ученика из предыдущего пункта.
        ('свой график', 'Посмотрите на график, который вы построили в предыдущем пункте.'),
    ]

    def test_false_positives_are_filtered(self):
        for label, text in self.CASES:
            with self.subTest(label):
                self.assertFalse(
                    references_missing_figure(text),
                    f'ложное срабатывание: {text!r} → '
                    f'{method_b_hits(text)}')

    def test_exclusion_does_not_swallow_a_real_reference(self):
        """«Постройте график по данным рисунка 2» — задание И отсылка сразу.

        Вырезание задания не должно съедать отсылку, которая стоит рядом.
        """
        self.assertTrue(references_missing_figure(
            'Постройте график спроса по данным рисунка 2.'))


class HasOwnDataTests(TestCase):
    """Есть ли в условии данные, чтобы решить задачу без картинки."""

    def test_formula_counts_as_data(self):
        self.assertTrue(has_own_data('Функция спроса Qd = 100 - 2P, издержки нулевые.'))

    def test_several_numbers_count_as_data(self):
        self.assertTrue(has_own_data('Цена 20 руб., объём 15 шт., издержки 300 руб.'))

    def test_graph_labels_are_not_data(self):
        """Задачи 48310 и 48483: «Q1, P4» — подписи ПОТЕРЯННОГО графика.

        Считать их данными нельзя, иначе тестовый вопрос, который без
        картинки не решается вообще никак, попадёт в «решаемые».
        """
        self.assertFalse(has_own_data(
            'Output Q1, Price P4; Output Q2, Price P3; Output Q3, Price P2'))

    def test_year_is_not_data(self):
        self.assertFalse(has_own_data(
            'В 2015 году в стране произошли изменения на рынке труда.'))


class ScanProblemsTests(TestCase):
    """Сборка находок по базе: что попадает в выборку, а что нет."""

    def setUp(self):
        self.source = Source.objects.create(name='Тестовый источник')

    def _make(self, **kwargs):
        kwargs.setdefault('title', 'Задача')
        kwargs.setdefault('answer', '')
        kwargs.setdefault('solution', '')
        kwargs.setdefault('status', Problem.Status.PUBLISHED)
        problem = Problem.objects.create(**kwargs)
        SourceReference.objects.create(problem=problem, source=self.source)
        return problem

    def test_reference_in_statement_is_unsolvable(self):
        p = self._make(statement='На рисунке изображена кривая спроса.')
        found = scan_problems()
        self.assertIn(p.pk, found)
        self.assertIn(p.pk, unsolvable_ids(found))

    def test_reference_only_in_solution_is_not_unsolvable(self):
        """Потерянная иллюстрация к разбору — брак, но задача решаема."""
        p = self._make(statement='Найдите равновесие при Qd = 10 - P.',
                       solution='Как видно на графике ниже, равновесие в точке E.')
        found = scan_problems()
        self.assertIn(p.pk, found)
        self.assertNotIn(p.pk, unsolvable_ids(found))

    def test_reference_in_problem_part_is_found(self):
        p = self._make(statement='Фирма работает на рынке.')
        ProblemPart.objects.create(problem=p, label='а', answer='—',
                                   statement='По рисунку определите равновесие.')
        self.assertIn(p.pk, unsolvable_ids(scan_problems()))

    def test_clean_problem_is_not_found(self):
        p = self._make(statement='Постройте график спроса Qd = 100 - 2P.')
        self.assertNotIn(p.pk, scan_problems())

    def test_problem_with_attached_file_is_skipped(self):
        """Картинка на месте — ссылка не битая, прятать нечего."""
        from problems.models import FileAsset
        p = self._make(statement='На рисунке изображена кривая спроса.')
        p.files.add(FileAsset.objects.create(file='uploads/x.png'))
        self.assertNotIn(p.pk, scan_problems())

    def test_status_is_reported(self):
        p = self._make(statement='См. рисунок 2.', status=Problem.Status.DRAFT)
        self.assertEqual(scan_problems()[p.pk]['status'], Problem.Status.DRAFT)


class HideCommandTests(TestCase):
    """Команда ``hide_missing_figures``: обратимость и неприкосновенность текста."""

    def setUp(self):
        import tempfile
        self.source = Source.objects.create(name='Тестовый источник')
        # ⚠️ Журнал ОБЯЗАН быть временным. Прогон с боевым путём оставлял в
        # reports/ журнал с id тестовой базы, и следующий --revert применил
        # бы их к настоящим задачам.
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.journal = os.path.join(self.tmp.name, 'hide_journal.json')

    def _make(self, statement, status=Problem.Status.PUBLISHED):
        problem = Problem.objects.create(
            title='Задача', statement=statement, answer='',
            solution='', status=status)
        SourceReference.objects.create(problem=problem, source=self.source)
        return problem

    def _run(self, *args):
        from io import StringIO

        from django.core.management import call_command
        out = StringIO()
        call_command('hide_missing_figures', *args,
                     journal=self.journal, stdout=out)
        return out.getvalue()

    def test_dry_run_changes_nothing(self):
        p = self._make('На рисунке изображена кривая спроса.')
        self._run()
        p.refresh_from_db()
        self.assertEqual(p.status, Problem.Status.PUBLISHED)
        self.assertEqual(p.tags.count(), 0)

    def test_apply_hides_and_tags(self):
        p = self._make('На рисунке изображена кривая спроса.')
        clean = self._make('Постройте график спроса Qd = 100 - 2P.')
        self._run('--apply')
        p.refresh_from_db()
        clean.refresh_from_db()
        self.assertEqual(p.status, Problem.Status.HIDDEN)
        self.assertEqual(
            list(p.tags.values_list('slug', flat=True)),
            [MISSING_FIGURE_TAG_SLUG])
        self.assertEqual(clean.status, Problem.Status.PUBLISHED)

    def test_apply_does_not_touch_text(self):
        text = 'На рисунке изображена кривая спроса.'
        p = self._make(text)
        ProblemPart.objects.create(problem=p, label='а', answer='42',
                                   statement='подпункт', solution='реш')
        self._run('--apply')
        p.refresh_from_db()
        part = p.parts.get()
        self.assertEqual(p.statement, text)
        self.assertEqual(p.answer, '')
        self.assertEqual(p.solution, '')
        self.assertEqual(part.statement, 'подпункт')
        self.assertEqual(part.answer, '42')

    def test_duplicate_keeps_its_status_but_gets_the_tag(self):
        """У дубликата свой смысл — затирать его скрытием нельзя."""
        p = self._make('На рисунке изображена кривая спроса.',
                       status=Problem.Status.DUPLICATE)
        self._run('--apply')
        p.refresh_from_db()
        self.assertEqual(p.status, Problem.Status.DUPLICATE)
        self.assertEqual(p.tags.count(), 1)

    def test_revert_restores_status_and_removes_tag(self):
        p = self._make('На рисунке изображена кривая спроса.')
        self._run('--apply')
        self._run('--revert', '--apply')
        p.refresh_from_db()
        self.assertEqual(p.status, Problem.Status.PUBLISHED)
        self.assertEqual(p.tags.count(), 0)

    def test_apply_is_idempotent(self):
        self._make('На рисунке изображена кривая спроса.')
        self._run('--apply')
        first = Problem.objects.filter(status=Problem.Status.HIDDEN).count()
        self._run('--apply')
        second = Problem.objects.filter(status=Problem.Status.HIDDEN).count()
        self.assertEqual(first, second)

    def test_tag_finds_exactly_the_hidden_set(self):
        """Фаза «сопоставить картинки» обязана находить их одним запросом."""
        p = self._make('См. рисунок 2.')
        self._make('Обычная задача без картинок.')
        self._run('--apply')
        self.assertEqual(
            list(Problem.objects.filter(
                tags__slug=MISSING_FIGURE_TAG_SLUG
            ).values_list('id', flat=True)),
            [p.pk])

    def test_journal_never_written_to_the_real_reports_dir(self):
        """Тест не имеет права оставлять журнал с id тестовой базы.

        Именно так и случилось при первом применении команды: в
        reports/missing_figures/ появился журнал с id=1 из тестовой базы,
        и --revert применил бы его к боевой задаче номер 1.
        """
        real = os.path.join('reports', 'missing_figures', 'hide_journal.json')
        existed = os.path.exists(real)
        before = os.path.getmtime(real) if existed else None
        self._make('На рисунке изображена кривая спроса.')
        self._run('--apply')
        self.assertTrue(os.path.exists(self.journal))
        if existed:
            self.assertEqual(os.path.getmtime(real), before)
        else:
            self.assertFalse(os.path.exists(real))
