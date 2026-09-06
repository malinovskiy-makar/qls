"""Фаза 7.3: экран теста — плитки, состояния, кнопки по правилу нуля."""
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from problems.models import Hint, ProblemPart
from problems.tests.factories import make_problem, make_topic, make_user


def _parts(problem, labels):
    for i, label in enumerate(labels, start=1):
        ProblemPart.objects.create(problem=problem, label=label,
                                   statement='Вариант %s про эластичность' % label, order=i)


class TestPageTests(TestCase):
    def setUp(self):
        self.topic = make_topic('Монополия и ценовая дискриминация')
        self.p = make_problem('Выберите верные утверждения о дискриминации.',
                              problem_type='тест: все верные', answer='аб', topic=self.topic,
                              solution='Первая степень: каждому своя цена, поэтому а и б верны.')
        _parts(self.p, 'абвг')
        self.url = reverse('catalog:problem_detail', args=[self.p.pk])

    def test_playable_test_has_tiles_rule_and_one_reveal_button(self):
        html = self.client.get(self.url).content.decode()
        main = html.split('<main')[1]
        self.assertIn('id="tq"', main)
        self.assertEqual(main.count('aria-pressed="false"'), 4)
        self.assertIn('data-l="г"', main)
        self.assertIn('верных может быть несколько: отметьте все', main)
        self.assertIn('<kbd>1</kbd>–<kbd>4</kbd>', main)
        self.assertIn('id="check-btn" disabled', main)
        self.assertEqual(main.count('Показать ответ'), 1)
        self.assertIn('Почему так', main)
        self.assertIn('каждому своя цена', main)
        for absent in ('id="sol-btn"', 'id="sv"', 'id="sv-text"', 'id="sol-confirm"',
                       '<ol class="parts">', 'id="chk-holder"', 'Ещё тест по этой теме',
                       'Спросить ИИ, почему так', 'решают верно'):
            self.assertNotIn(absent, main)
        self.assertIn('"multi": true', html)
        self.assertIn('"labels": ["а", "б", "в", "г"]', html)
        self.assertIn('"checkUrl": "/catalog/api/test-check/%d/"' % self.p.pk, html)

    def test_single_choice_rule_and_config(self):
        one = make_problem('Один верный.', problem_type='тест: один ответ', answer='б')
        _parts(one, 'абв')
        html = self.client.get(reverse('catalog:problem_detail', args=[one.pk])).content.decode()
        self.assertIn('выберите один', html)
        self.assertIn('"multi": false', html)
        self.assertIn('Попробуйте другой вариант.', html)

    def test_more_test_link_only_with_another_test_by_topic(self):
        other = make_problem('Второй тест.', problem_type='тест: один ответ', answer='а', topic=self.topic)
        _parts(other, 'аб')
        html = self.client.get(self.url).content.decode()
        self.assertIn('Ещё тест по этой теме', html)
        self.assertIn('/catalog/random/?type=test&amp;topic=%d&amp;exclude=%d' % (self.topic.pk, self.p.pk), html)

    def test_stat_line_only_with_game_stat(self):
        with patch('catalog.views._game_stat', return_value={'percent': 64, 'attempts': 40}):
            html = self.client.get(self.url).content.decode()
        self.assertIn('class="tq-stat"', html)
        self.assertIn('решают верно <b>64 %</b>', html)
        self.assertNotIn('class="pd-stat"', html)

    def test_ask_why_button_needs_model_and_login(self):
        with override_settings(AI_PROVIDER='fake'):
            self.assertNotIn('Спросить ИИ, почему так', self.client.get(self.url).content.decode())
            self.client.force_login(make_user('игрок'))
            html = self.client.get(self.url).content.decode()
        self.assertIn('id="ask-why" data-ask=""', html)

    def test_hint_button_lives_in_the_play_row(self):
        Hint.objects.create(problem=self.p, order=1, text='Вспомните определение.', reviewed=True)
        html = self.client.get(self.url).content.decode()
        row = html.split('id="row-play"')[1].split('id="row-done"')[0]
        self.assertIn('id="hint-btn"', row)
        self.assertIn('1 из 1', row)

    def test_test_without_game_is_an_ordinary_problem(self):
        numeric = make_problem('Сколько будет два плюс два?', problem_type='тест: числовой ответ',
                               answer='4', solution='Складываем.')
        html = self.client.get(reverse('catalog:problem_detail', args=[numeric.pk])).content.decode()
        main = html.split('<main')[1]
        for absent in ('id="tq"', 'Проверить', 'Показать ответ', 'aria-pressed', '"checkUrl"'):
            self.assertNotIn(absent, main)
        self.assertIn('id="sv"', main)
        self.assertIn('id="sol-btn"', main)
        outside = make_problem('Верные вне меток.', problem_type='тест: все верные', answer='бд')
        _parts(outside, 'абвг')
        html = self.client.get(reverse('catalog:problem_detail', args=[outside.pk])).content.decode()
        self.assertNotIn('id="tq"', html)
        self.assertIn('<ol class="parts">', html)
