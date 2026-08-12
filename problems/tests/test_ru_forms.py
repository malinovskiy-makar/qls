"""
Русская грамматика в шаблонах — фильтры `problems/templatetags/ru.py`.

⚠️ ПОЧЕМУ ФИЛЬТР ПРИШЛОСЬ ЗАВОДИТЬ. Встроенный `pluralize` умеет ДВЕ формы,
а в русском их три. В шаблонах кабинета стояло `{{ n|pluralize:",а,ов" }}` —
и это не «почти работает»: с тремя формами `pluralize` возвращает пустую
строку при любом числе. На экране стояло «3 ученик», «11 задани».
Первый тест здесь и фиксирует эту ловушку, чтобы её не завели заново.
"""
from django.template import Context, Template
from django.template.defaultfilters import pluralize
from django.test import SimpleTestCase

from problems.templatetags.ru import count_ru, pick, plural_ru, prep_o


class BuiltinPluralizeTrapTests(SimpleTestCase):
    def test_builtin_pluralize_is_useless_for_russian(self):
        """Ловушка: три формы → пустая строка, а не «почти правильно»."""
        for number in (1, 2, 5, 11, 21):
            self.assertEqual(pluralize(number, ',а,ов'), '')


class PickTests(SimpleTestCase):
    FORMS = ('ученик', 'ученика', 'учеников')

    def test_one(self):
        for number in (1, 21, 101, 131):
            self.assertEqual(pick(number, *self.FORMS), 'ученик', number)

    def test_few(self):
        for number in (2, 3, 4, 22, 33, 104):
            self.assertEqual(pick(number, *self.FORMS), 'ученика', number)

    def test_many(self):
        for number in (0, 5, 9, 10, 20, 25, 100):
            self.assertEqual(pick(number, *self.FORMS), 'учеников', number)

    def test_teens_are_the_exception(self):
        """11–14 берут форму «многих», хотя кончаются на 1–4."""
        for number in (11, 12, 13, 14, 111, 112, 113, 114):
            self.assertEqual(pick(number, *self.FORMS), 'учеников', number)

    def test_garbage_does_not_crash(self):
        self.assertEqual(pick(None, *self.FORMS), 'учеников')
        self.assertEqual(pick('много', *self.FORMS), 'учеников')


class FilterTests(SimpleTestCase):
    def test_plural_ru_returns_word_only(self):
        self.assertEqual(plural_ru(3, 'работа,работы,работ'), 'работы')

    def test_count_ru_returns_number_and_word(self):
        self.assertEqual(count_ru(1, 'ученик,ученика,учеников'), '1 ученик')
        self.assertEqual(count_ru(3, 'ученик,ученика,учеников'), '3 ученика')
        self.assertEqual(count_ru(11, 'ученик,ученика,учеников'), '11 учеников')

    def test_short_form_list_does_not_crash(self):
        """Забыли форму — берём последнюю, а не роняем страницу."""
        self.assertEqual(count_ru(5, 'работа'), '5 работа')

    def test_works_from_a_template(self):
        out = Template(
            '{% load ru %}{{ n|count_ru:"задание,задания,заданий" }}'
        ).render(Context({'n': 11}))
        self.assertEqual(out, '11 заданий')


class PrepositionTests(SimpleTestCase):
    def test_ob_before_open_vowels(self):
        for name in ('Иван', 'Анна', 'Ольга', 'Ульяна', 'Эдуард'):
            self.assertEqual(prep_o(name), 'об', name)

    def test_o_before_consonants(self):
        for name in ('Пётр', 'Мария', 'Николай', 'Тимур'):
            self.assertEqual(prep_o(name), 'о', name)

    def test_o_before_iotated_vowels(self):
        """«Елена», «Юля», «Яна» начинаются с согласного звука «й»."""
        for name in ('Елена', 'Юля', 'Яна', 'Ёжик'):
            self.assertEqual(prep_o(name), 'о', name)

    def test_empty_is_o(self):
        self.assertEqual(prep_o(''), 'о')
        self.assertEqual(prep_o(None), 'о')

    def test_works_from_a_template(self):
        out = Template(
            '{% load ru %}Полезная информация {{ name|prep_o }} {{ name }}'
        ).render(Context({'name': 'Иване Петрове'}))
        self.assertEqual(out, 'Полезная информация об Иване Петрове')


class NoBrokenPluralizeLeftTests(SimpleTestCase):
    """Ни в одном шаблоне не должно остаться `pluralize` с тремя формами."""

    def test_no_three_form_pluralize_in_templates(self):
        import os
        import re

        from django.conf import settings

        pattern = re.compile(r'pluralize:"[^"]*,[^"]*,')
        found = []
        for root, dirs, files in os.walk(settings.BASE_DIR):
            dirs[:] = [d for d in dirs
                       if d not in ('venv', 'node_modules', '.git', 'reports')]
            for name in files:
                if not name.endswith('.html'):
                    continue
                path = os.path.join(root, name)
                with open(path, encoding='utf-8') as handle:
                    if pattern.search(handle.read()):
                        found.append(os.path.relpath(path, settings.BASE_DIR))
        self.assertEqual(found, [], 'pluralize с тремя формами возвращает пустоту')
