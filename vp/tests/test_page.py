"""Страница прохождения: что в разметке, что подставлено, чего на ней нет."""
import json
import re
from decimal import Decimal as D

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from vp import loader
from vp.models import VPAnswer, VPAttempt, VPItem
from vp.tests.helpers import make_published

SECRET_ANSWER = 'ЭТАЛОН-СЕКРЕТ-7'
SECRET_ACCEPTED = 'СИНОНИМ-СЕКРЕТ-8'
SECRET_SOLUTION = 'РЕШЕНИЕ-СЕКРЕТ-40'


class PageBase(TestCase):
    def setUp(self):
        self.variant = make_published()
        self.client = Client()
        # Стена регистрации (22.09.2026): попытку заводит только вошедший.
        self.client.force_login(
            get_user_model().objects.create_user('vp_page', password='p12345'))
        self.attempt = self.start()

    def start(self, **post):
        self.client.post(reverse('vp:start', args=['vp-t']), post)
        return VPAttempt.objects.order_by('-id').first()

    def html(self):
        response = self.client.get(reverse('vp:take', args=[self.attempt.public_code]))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def config(self, html):
        match = re.search(r'<script id="vp-config" type="application/json">(.*?)</script>',
                          html, re.S)
        return json.loads(match.group(1))

    def answer(self, number, raw):
        item = self.variant.items.get(number=number)
        VPAnswer.objects.create(attempt=self.attempt, item=item, raw=raw)


class LayoutTests(PageBase):
    def test_all_forty_four_items_are_in_the_markup_in_order(self):
        html = self.html()
        found = [int(n) for n in re.findall(r'<section class="vp-item" id="vp-item-(\d+)"', html)]
        self.assertEqual(found, list(range(1, 45)))

    def test_navigator_links_point_to_the_items(self):
        html = self.html()
        for number in (1, 17, 44):
            self.assertIn(f'href="#vp-item-{number}"', html)
        # Плитки есть и в колонке слева, и в полосе для телефона.
        self.assertEqual(len(re.findall(r'class="vp-cell[ "][^>]*data-n="12"', html)), 2)

    def test_block_headings_and_points(self):
        html = self.html()
        self.assertIn('Задания 1–30. Змейка', html)
        self.assertIn('· по 2 балла', html)
        self.assertIn('Задания 31–35. Пропущенные слова', html)
        self.assertIn('Задания 36–40. Все верные утверждения', html)
        self.assertIn('· по 3 балла · за лишние варианты балл уменьшается', html)
        self.assertIn('Задания 43–44. Расчётные, один ответ', html)
        self.assertIn('· от 4 до 5 баллов', html)         # 43 и 44 стоят по-разному

    def test_block_intro_is_the_first_items_intro_else_the_snake_default(self):
        first = self.variant.items.get(number=31)
        first.intro = 'Прочитайте текст о заводе Форда и выберите слово.'
        first.save()
        second = self.variant.items.get(number=32)
        second.intro = 'ЭТОТ ТЕКСТ НЕ ПЕРВОГО ЗАДАНИЯ'
        second.save()
        html = self.html()
        self.assertIn('Прочитайте текст о заводе Форда и выберите слово.', html)
        self.assertNotIn('ЭТОТ ТЕКСТ НЕ ПЕРВОГО ЗАДАНИЯ', html)
        self.assertIn('Каждый следующий ответ начинается со второй буквы предыдущего', html)

    def test_header_has_title_class_counter_and_submit(self):
        html = self.html()
        self.assertIn('Тестовый вариант', html)
        self.assertIn('9–10 классы', html)
        self.assertRegex(html, r'отвечено <b id="vp-answered">0</b> из 44')
        self.assertIn('id="vp-submit"', html)
        self.assertRegex(html, r'id="vp-timer"[^>]*data-seconds="\d+"')

    def test_untimed_attempt_shows_the_words_instead_of_a_clock(self):
        # Новый человек, а не «тот же браузер без печенек»: попытку заводит
        # только вошедший, а у прежнего по этому варианту уже есть живая.
        self.client.force_login(
            get_user_model().objects.create_user('vp_page2', password='p12345'))
        self.attempt = self.start(with_timer='0')
        html = self.html()
        self.assertNotIn('id="vp-timer"', html)
        self.assertIn('без таймера', html)

    def test_site_nav_is_hidden_and_config_is_json(self):
        html = self.html()
        self.assertIn('class="vp-focus"', html)
        config = self.config(html)
        self.assertEqual(config['numbers'], list(range(1, 45)))
        self.assertEqual(config['textNumbers'], list(range(1, 31)))
        self.assertTrue(config['timed'])
        self.assertLessEqual(config['seconds'], 1800)

    def test_page_is_not_indexed(self):
        self.assertIn('noindex', self.html())


class ControlsTests(PageBase):
    def test_short_text_fields_have_labels_and_keyboard_attributes(self):
        html = self.html()
        self.assertIn('<label class="vp-sr" for="vp-in-5">Ответ на задание 5</label>', html)
        field = re.search(r'<input class="vp-input" id="vp-in-5"[^>]*>', html, re.S).group(0)
        for attribute in ('type="text"', 'autocomplete="off"', 'autocapitalize="off"',
                          'spellcheck="false"', 'name="item-5"'):
            self.assertIn(attribute, field)

    def test_prefix_and_suffix_are_separate_spans_next_to_the_field(self):
        item = self.variant.items.get(number=6)
        item.prefix = 'до'
        item.suffix = 'денег'
        item.statement = 'Число оборотов за год'
        item.save()
        html = self.html()
        block = re.search(r'<section class="vp-item" id="vp-item-6".*?</section>', html, re.S).group(0)
        self.assertIn('<span class="vp-affix">до</span>', block)
        self.assertIn('<span class="vp-affix">денег</span>', block)
        self.assertNotIn('денег', block.split('vp-answer')[0])     # не внутри условия

    def test_single_is_radio_and_multi_is_checkbox_inside_labels(self):
        html = self.html()
        single = re.search(r'<section class="vp-item" id="vp-item-31".*?</section>', html, re.S).group(0)
        multi = re.search(r'<section class="vp-item" id="vp-item-36".*?</section>', html, re.S).group(0)
        self.assertEqual(single.count('type="radio"'), 5)
        self.assertEqual(multi.count('type="checkbox"'), 5)
        self.assertRegex(single, r'<label class="vp-opt[^"]*"><input type="radio"')
        self.assertRegex(multi, r'<label class="vp-opt[^"]*"><input type="checkbox"')

    def test_multi_does_not_say_how_many_are_correct(self):
        html = self.html()
        multi = re.search(r'<section class="vp-item" id="vp-item-36".*?</section>', html, re.S).group(0)
        self.assertNotRegex(multi, r'(?i)(выберите|отметьте)\s+(два|три|\d)')
        self.assertNotIn('верных', multi)

    def test_short_options_become_pills_and_long_ones_do_not(self):
        short = self.variant.items.get(number=43)
        short.options = [{'n': 1, 'text': '390 000'}, {'n': 2, 'text': 'Нет верного ответа'}]
        short.save()
        long_ = self.variant.items.get(number=44)
        long_.options = [{'n': 1, 'text': 'Очень длинный вариант ответа, не помещающийся в таблетку'},
                         {'n': 2, 'text': 'Ещё один длинный вариант ответа для сравнения'}]
        long_.save()
        html = self.html()
        pills = re.search(r'<section class="vp-item" id="vp-item-43".*?</section>', html, re.S).group(0)
        column = re.search(r'<section class="vp-item" id="vp-item-44".*?</section>', html, re.S).group(0)
        self.assertIn('vp-opt--pill', pills)
        self.assertNotIn('vp-opt--pill', column)

    def test_gap_in_the_statement_is_drawn_as_a_blank(self):
        item = self.variant.items.get(number=31)
        item.statement = 'До предела ______, о котором писал Смит.'
        item.save()
        html = self.html()
        block = re.search(r'<section class="vp-item" id="vp-item-31".*?</section>', html, re.S).group(0)
        self.assertIn('<span class="vp-gap"', block)
        self.assertNotIn('______', block)

    def test_statement_is_escaped(self):
        item = self.variant.items.get(number=2)
        item.statement = '<script>alert(1)</script> и $Q^d = 100 - 2P$'
        item.save()
        html = self.html()
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', html)
        self.assertIn('$Q^d = 100 - 2P$', html)                     # TeX доедет до KaTeX как есть

    def test_table_is_output_as_is(self):
        item = self.variant.items.get(number=42)
        item.table_html = '<table><tr><th>Год</th></tr><tr><td colspan="2">2020</td></tr></table>'
        item.save()
        self.assertIn('<td colspan="2">2020</td>', self.html())

    def test_figure_is_drawn_with_caption_and_source(self):
        item = self.variant.items.get(number=41)
        item.figure = 'vp/figures/selftest/41.png'
        item.figure_caption = 'Кривая спроса'
        item.figure_source = 'Синтетика'
        item.save()
        block = re.search(r'<section class="vp-item" id="vp-item-41".*?</section>',
                          self.html(), re.S).group(0)
        self.assertRegex(block, r'<img src="[^"]*vp/figures/selftest/41\.png" alt="Кривая спроса"')
        self.assertIn('Источник: Синтетика', block)

    def test_missing_figure_does_not_break_the_page(self):
        """На боевом хранилище static() бросает ValueError для файла вне манифеста."""
        from unittest import mock
        item = self.variant.items.get(number=41)
        item.figure = 'vp/figures/net-takogo-faila.png'
        item.save()
        with mock.patch('vp.views.static', side_effect=ValueError('not in manifest')):
            html = self.html()
        block = re.search(r'<section class="vp-item" id="vp-item-41".*?</section>', html, re.S).group(0)
        self.assertNotIn('<img', block)
        self.assertIn('id="vp-item-44"', html)

    def test_match_item_renders_one_select_per_pair_without_the_answers(self):
        item = self.variant.items.get(number=44)
        item.kind = 'match'
        item.options = [{'n': 1, 'text': 'спрос'}, {'n': 2, 'text': 'предложение'}]
        item.correct = {'а': 2, 'б': 1}
        item.save()
        html = self.html()
        block = re.search(r'<section class="vp-item" id="vp-item-44".*?</section>', html, re.S).group(0)
        self.assertEqual(block.count('<select'), 2)
        self.assertIn('name="item-44.а"', block)
        self.assertIn('name="item-44.б"', block)
        self.assertNotIn(' selected', block)
        self.assertEqual(self.config(html)['numbers'][-1], 44)


class RestoreTests(PageBase):
    def test_saved_answers_are_rendered_into_fields_and_marks(self):
        self.answer(1, 'мой ответ')
        self.answer(31, 3)
        self.answer(36, [1, 4])
        html = self.html()
        self.assertIn('value="мой ответ"', html)
        self.assertRegex(html, r'name="item-31" value="3" checked')
        self.assertRegex(html, r'name="item-36" value="1" checked')
        self.assertRegex(html, r'name="item-36" value="4" checked')
        self.assertNotRegex(html, r'name="item-36" value="2" checked')
        self.assertRegex(html, r'отвечено <b id="vp-answered">3</b> из 44')

    def test_answered_tiles_are_marked_and_blank_ones_are_not(self):
        self.answer(1, 'мой ответ')
        self.answer(2, '   ')                  # пробелы — не ответ
        self.answer(3, None)
        self.answer(36, [])
        html = self.html()
        self.assertEqual(len(re.findall(r'class="vp-cell is-answered" href="#vp-item-1"', html)), 2)
        self.assertNotIn('is-answered" href="#vp-item-2"', html)
        self.assertNotIn('is-answered" href="#vp-item-3"', html)
        self.assertNotIn('is-answered" href="#vp-item-36"', html)
        self.assertRegex(html, r'отвечено <b id="vp-answered">1</b> из 44')

    def test_saved_match_answer_is_selected(self):
        item = self.variant.items.get(number=44)
        item.kind = 'match'
        item.options = [{'n': 1, 'text': 'спрос'}, {'n': 2, 'text': 'предложение'}]
        item.correct = {'а': 2, 'б': 1}
        item.save()
        self.answer(44, {'а': 1})
        html = self.html()
        block = re.search(r'<section class="vp-item" id="vp-item-44".*?</section>', html, re.S).group(0)
        self.assertEqual(block.count(' selected'), 1)
        self.assertRegex(block, r'<option value="1" selected>спрос</option>')


class SecrecyTests(PageBase):
    def setUp(self):
        super().setUp()
        item = self.variant.items.get(number=7)
        item.answer = SECRET_ANSWER
        item.accepted = [SECRET_ACCEPTED]
        item.chain_first, item.chain_second = loader.chain_letters(item.chain_word())
        item.save()
        multi = self.variant.items.get(number=40)
        multi.solution = SECRET_SOLUTION
        multi.save()

    def test_take_hides_answers(self):
        html = self.html()
        for secret in (SECRET_ANSWER, SECRET_ACCEPTED, SECRET_SOLUTION):
            self.assertNotIn(secret, html)
        for leak in ('chain_first', 'chain_second', 'data-chain', 'data-answer',
                     'data-correct', '"correct"', 'accepted'):
            self.assertNotIn(leak, html)
        self.assertNotIn(' checked', html)            # верные варианты заранее не отмечены

    def test_take_hides_answers_from_a_page_with_saved_state_too(self):
        self.answer(7, 'мой')
        html = self.html()
        self.assertNotIn(SECRET_ANSWER, html)
        self.assertNotIn(SECRET_SOLUTION, html)

    def test_rows_carry_no_model_instances(self):
        from vp import views
        row = views._row(self.variant.items.get(number=7), None)
        self.assertFalse(any(isinstance(value, VPItem) for value in row.values()))
        for forbidden in ('answer', 'correct', 'accepted', 'solution', 'chain_first',
                          'chain_second', 'wrong_penalty', 'penalty'):
            self.assertNotIn(forbidden, row)
        self.assertEqual(row['points'], D('2'))
