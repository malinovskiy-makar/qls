# -*- coding: utf-8 -*-
"""Код MISS: «ученик рисует сам» — это не пропавшая картинка.

Живые примеры владельца — #43780 («покажите его на графике») и #43791
(«Покажите излишки всех агентов на графике»). В оригинале картинки не
было ни в условии, ни в решении: рисовать велено ученику.

Правило сознательно НЕсимметрично: сомнение трактуется в пользу дефекта.
Показать битое хуже, чем задержать хорошее.
"""
from django.test import SimpleTestCase

from problems.corpus_converter.render_codes import analyze_problem
from problems.rendering import render_markdown

BS = chr(92)


def codes(*texts, htmls=None):
    """Коды задачи, собранной из блоков.

    HTML считается настоящим `render_markdown` — анализ смотрит именно на
    видимый текст страницы, а не на исходник. Картинок в нём нет, если не
    передать `htmls` явно."""
    blocks = [('Условие' if i == 0 else 'Часть %d' % i, t, t)
              for i, t in enumerate(texts)]
    return analyze_problem(blocks, htmls or [render_markdown(t) for t in texts])


class DrawsItHimselfTests(SimpleTestCase):
    """Повелительное «покажите … на графике» — не пропажа."""

    def test_owner_example_43780(self):
        c = codes('Екатерине исполнилось 18 лет, родители подарили 18 тыс.',
                  'Найдите уравнение межвременного бюджетного ограничения '
                  'Кати и покажите его на графике ($C_1, C_2$)')
        self.assertNotIn('MISS', c)

    def test_owner_example_43791(self):
        c = codes('В мегаполисе функционирует метрополитен-монополист. '
                  'Спрос задается уравнением $Q=300-2P$.',
                  'Найдите общественное благосостояние в равновесии. '
                  'Покажите излишки всех агентов на графике')
        self.assertNotIn('MISS', c)

    def test_build_the_graph_yourself(self):
        self.assertNotIn('MISS', codes(
            'Функция спроса задана. Постройте график спроса и найдите излишек.'))

    def test_draw_yourself(self):
        self.assertNotIn('MISS', codes(
            'Нарисуйте на графике кривую предложения фирмы.'))

    def test_illustrate_yourself(self):
        self.assertNotIn('MISS', codes(
            'Проиллюстрируйте изменение равновесия на графике спроса.'))


class RealMissStillCaughtTests(SimpleTestCase):
    """Твёрдый признак пропажи сильнее поблажки — MISS остаётся."""

    def test_reference_to_numbered_figure(self):
        self.assertIn('MISS', codes(
            'На рис. 2 изображена кривая. Покажите на графике излишек.'))

    def test_see_figure_reference(self):
        self.assertIn('MISS', codes(
            'См. рис. Постройте на графике новую кривую.'))

    def test_figure_below(self):
        self.assertIn('MISS', codes(
            'На рисунке ниже дан график. Покажите на графике равновесие.'))

    def test_surviving_includegraphics_beats_the_exemption(self):
        self.assertIn('MISS', codes(
            'Постройте на графике КПВ. ' + BS + 'includegraphics{kpv.png}'))

    def test_plain_reference_without_imperative_is_still_miss(self):
        self.assertIn('MISS', codes(
            'На графике изображена кривая спроса. Найдите равновесие.'))

    def test_passive_voice_is_not_an_imperative(self):
        """«изображён» — не «изобразите»: картинка БЫЛА."""
        self.assertIn('MISS', codes(
            'На диаграмме изображено распределение доходов. Найдите Джини.'))


class MissUnaffectedWhenObjectPresentTests(SimpleTestCase):
    """Если картинка на экране есть — кода нет в любом случае."""

    def test_image_present_means_no_miss(self):
        blocks = [('Условие', 'На графике дана кривая спроса.',
                   'На графике дана кривая спроса.')]
        self.assertNotIn('MISS', analyze_problem(blocks, ['<img src="/x.png">']))
