"""
Мелочи, найденные при проверке 16.08 (фаза 7).

7.1 Вес пункта пишется как везде на платформе: «1», «2», «0,5».
7.2 Задача без сложности — «сложность не указана», а не «0 из 5».
7.3 Отказ подбора объясняется ОДИН раз.
7.4 Экран называется одинаково везде.
7.5 В журнал уходит класс исключения и его сообщение, на экран — прежний
    мягкий текст.
"""
import os
from decimal import Decimal

from django.template.loader import render_to_string
from django.test import TestCase

from problems import scorefmt
from problems.models_platform import CustomProblem, CustomProblemPart
from problems.models import User


def read(*parts):
    with open(os.path.join(*parts), encoding='utf-8') as handle:
        return handle.read()


class PartWeightFormatTests(TestCase):
    """7.1 — «1,00» на экране быть не должно."""

    def setUp(self):
        self.tutor = User.objects.create_user('w_tutor', password='x',
                                              role='teacher')
        self.problem = CustomProblem.objects.create(
            owner=self.tutor, title='Своя', statement='Условие',
            kind=CustomProblem.Kind.OPEN)
        CustomProblemPart.objects.create(problem=self.problem, label='а',
                                         statement='Первый',
                                         points=Decimal('1.00'), order=0)
        CustomProblemPart.objects.create(problem=self.problem, label='б',
                                         statement='Второй',
                                         points=Decimal('2.50'),
                                         answer_tolerance=Decimal('0.001'),
                                         order=1)

    def test_editor_shows_the_same_record_as_the_rest_of_the_site(self):
        self.client.force_login(self.tutor)
        page = self.client.get('/teacher/problems/%d/edit/' % self.problem.pk)
        self.assertEqual(page.status_code, 200)
        body = page.content.decode()
        self.assertIn('value="1"', body)
        self.assertIn('value="2,5"', body)
        self.assertNotIn('value="1,00"', body)
        self.assertNotIn('value="2,50"', body)

    def test_tolerance_keeps_all_six_places(self):
        """⚠️ ДОПУСК НЕЛЬЗЯ ОКРУГЛЯТЬ ДО СОТЫХ.

        Значение лежит в поле формы: показать 0,001 как «0» значит стереть
        допуск при первом же сохранении. Поэтому у него своя запись —
        `scorefmt.exact`, без округления.
        """
        self.assertEqual(scorefmt.ball(Decimal('0.001')), '0')
        self.assertEqual(scorefmt.exact(Decimal('0.001')), '0,001')
        self.client.force_login(self.tutor)
        body = self.client.get(
            '/teacher/problems/%d/edit/' % self.problem.pk).content.decode()
        self.assertIn('value="0,001"', body)

    def test_exact_drops_trailing_zeros_without_rounding(self):
        self.assertEqual(scorefmt.exact(Decimal('0.000000')), '0')
        self.assertEqual(scorefmt.exact(Decimal('1.00')), '1')
        self.assertEqual(scorefmt.exact(Decimal('2.500000')), '2,5')
        self.assertEqual(scorefmt.exact(None), '')


class DifficultyWordsTests(TestCase):
    """7.2 — ноль по шкале 1–5 это не сложность, а её отсутствие."""

    def test_card_meta_says_it_in_words(self):
        from teacher.picker import card_meta

        self.assertIn('сложность не указана', card_meta([], 'Задача', 0))
        self.assertIn('сложность 3 из 5', card_meta([], 'Задача', 3))

    def test_builder_row_says_it_too(self):
        text = read('teacher', 'templates', 'teacher', 'assignment_build.html')
        self.assertIn("'сложность не указана'", text)
        self.assertNotIn("(row.difficulty || 0) + ' из 5'", text)

    def test_preview_window_does_not_show_five_empty_stars(self):
        script = read('teacher', 'templates', 'teacher', '_picker_js.html')
        self.assertIn('сложность не указана', script)


class OneWayOutTests(TestCase):
    """7.3 — выход из положения назван один раз."""

    def test_message_does_not_repeat_the_manual_path(self):
        from teacher.views_generate import AI_ERROR_TEXTS

        for kind, text in AI_ERROR_TEXTS.items():
            self.assertNotIn('вручную', text, kind)

    def test_the_link_below_still_offers_it(self):
        page = read('teacher', 'templates', 'teacher', 'generate.html')
        self.assertIn('Соберите работу вручную:', page)


class OneNameTests(TestCase):
    """7.4 — «конструктор подборки» во всех местах одинаково."""

    def test_button_and_screen_agree(self):
        page = read('teacher', 'templates', 'teacher', 'generate.html')
        build = read('teacher', 'templates', 'teacher',
                     'assignment_build.html')
        self.assertIn('конструктор подборки', page)
        self.assertNotIn('конструктор подборок', page)
        self.assertIn('Конструктор подборки', build)


class LoggingTests(TestCase):
    """7.5 — журнал знает больше экрана."""

    def test_provider_logs_the_real_cause(self):
        source = read('problems', 'ai', 'providers.py')
        self.assertIn('def log_cause', source)
        self.assertIn('type(error).__name__', source)
        self.assertIn('exc_info=True', source)
        # Ни одна ветка не собирает отказ мимо общей точки.
        self.assertNotIn('raise ProviderError(\n', source)

    def test_view_logs_class_and_message(self):
        source = read('teacher', 'views_generate.py')
        piece = source[source.index('Подбор по описанию не удался'):]
        piece = piece[:400]
        self.assertIn('type(error).__name__', piece)
        self.assertIn('exc_info=True', piece)

    def test_screen_text_stays_soft(self):
        from teacher.views_generate import AI_ERROR_TEXTS

        for text in AI_ERROR_TEXTS.values():
            self.assertNotRegex(text, r'\b\d{3}\b')      # кода ошибки нет
            self.assertNotIn('Error', text)

    def test_fake_provider_still_needs_no_key(self):
        """Подставной поставщик — то, чем проверяются экраны без ключа."""
        from problems.ai import providers

        self.assertTrue(hasattr(providers, 'FakeProvider'))
