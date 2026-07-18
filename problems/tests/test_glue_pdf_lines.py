# -*- coding: utf-8 -*-
"""Тесты склейки построчной PDF-нарезки
(problems.management.commands.glue_pdf_lines).

glue_field — чистая функция без обращений к базе, поэтому SimpleTestCase.
Отдельный класс с базой (GluePdfLinesCommandTests) проверяет, что dry-run
команды НЕ меняет базу, а границы источников соблюдаются.

Главный принцип, который фиксируют тесты: ошибка допустима только в
безопасную сторону (недоклеить), структурный текст не должен меняться
ни на символ.
"""
import os
import tempfile
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from problems.management.commands.glue_pdf_lines import (
    MAX_GLUES_PER_FIELD, classify_boundary, glue_field,
)
from problems.tests.factories import link_source, make_problem, make_source


def glued(text):
    """Утилита: вернуть склеенный текст (или исходный, если изменений нет)."""
    res = glue_field(text)
    return res.new_text if res.new_text is not None else text


class SimpleGlueTests(SimpleTestCase):
    """Основные случаи склейки — то, ради чего команда существует."""

    def test_mid_sentence_break_glued(self):
        # Реальный случай #6145 (Сборник тестов АА)
        text = ('Налог на продажи товаров первой необходимости\n'
                'является регрессивным.')
        self.assertEqual(
            glued(text),
            'Налог на продажи товаров первой необходимости является регрессивным.')

    def test_multiline_chain_glued_to_one_paragraph(self):
        # Реальный профиль #7225: строки по ~80 символов, обрыв посреди фразы
        text = ('В стране А наличных денег в три раза меньше,\n'
                'чем депозитов. Норма обязательных резервов равна 15%. Кроме того\n'
                'банки имеют избыточные резервы.')
        res = glue_field(text)
        self.assertEqual(res.glue_count, 2)
        self.assertNotIn('\n', res.new_text)

    def test_comma_continuation_after_inline_math(self):
        # Реальный случай #39596: строка кончается формулой, следующая
        # начинается с запятой («, где ...»)
        text = 'вид: $U_i = a_i \\cdot ln(C) + x_i$\n, где $C$ — залпы салюта.'
        self.assertEqual(
            glued(text),
            'вид: $U_i = a_i \\cdot ln(C) + x_i$ , где $C$ — залпы салюта.')

    def test_hanging_preposition_glues_even_before_uppercase(self):
        text = 'Цена выросла в\nМоскве на 10%.'
        self.assertEqual(glued(text), 'Цена выросла в Москве на 10%.')

    def test_digit_continuation_glued(self):
        # Реальный случай #50174: «...составляет» → «4800 млрд р.»
        text = 'Объем потенциального ВВП составляет\n4800 млрд р., как известно.'
        self.assertEqual(
            glued(text),
            'Объем потенциального ВВП составляет 4800 млрд р., как известно.')

    def test_operator_start_glued(self):
        # Реальный случай #50055: строка формулы без $ разорвана перед «=»
        text = 'Функция спроса на труд имеет вид Ld\n= 80 - w, где w — ставка.'
        self.assertEqual(
            glued(text),
            'Функция спроса на труд имеет вид Ld = 80 - w, где w — ставка.')

    def test_latin_text_glued(self):
        # AP Economics: латиница клеится по тем же правилам
        text = ('In an output table, the\n'
                'opportunity cost of producing 1 unit of good X is found by')
        self.assertEqual(
            glued(text),
            'In an output table, the opportunity cost of producing 1 unit '
            'of good X is found by')


class HyphenTests(SimpleTestCase):
    """Дефисные разрывы: в v1 не клеятся вовсе (AUTO_HYPHEN_JOIN=False),
    все случаи — в лог; уверенные кандидаты помечаются «[склеил бы]»."""

    def test_confident_hyphen_break_logged_not_joined(self):
        # Политика v1 (итог адверсариального ревью): даже уверенный кандидат
        # не клеится — без словаря «предло-жение» неотличимо от
        # «денежно-кредитную», разорванного по собственному дефису
        text = 'Функция предло-\nжения растёт с ценой.'
        res = glue_field(text)
        self.assertIsNone(res.new_text)
        self.assertEqual(len(res.doubtful), 1)
        self.assertIn('[склеил бы: предложения]', res.doubtful[0])

    def test_auto_join_mechanics_work_when_enabled(self):
        # Механика склейки сохранена за константой — проверяем её отдельно
        with mock.patch(
                'problems.management.commands.glue_pdf_lines.AUTO_HYPHEN_JOIN',
                True):
            res = glue_field('Функция предло-\nжения растёт с ценой.')
            self.assertEqual(res.new_text, 'Функция предложения растёт с ценой.')
            self.assertEqual(res.hyphen_count, 1)

    def test_compound_word_never_corrupted(self):
        # Находка ревью: «денежно-\nкредитную» склеивалась бы в порчу
        # «денежнокредитную» — политика v1 исключает это классом
        text = 'Центральный банк проводит денежно-\nкредитную политику.'
        res = glue_field(text)
        self.assertIsNone(res.new_text)

    def test_doubtful_prefix_left_untouched_and_logged(self):
        # «во-первых» — осмысленное дефисное слово, склейка испортила бы его
        text = 'Он сделал это во-\nпервых, потому что так надо.'
        res = glue_field(text)
        self.assertIsNone(res.new_text)
        self.assertEqual(len(res.doubtful), 1)
        self.assertIn('во-первых', res.doubtful[0])

    def test_doubtful_particle_left_untouched_and_logged(self):
        # «что-либо»: правая половинка — частица из RIGHT_DOUBT
        text = 'Если появится что-\nлибо новое, сообщите.'
        res = glue_field(text)
        self.assertIsNone(res.new_text)
        self.assertEqual(len(res.doubtful), 1)

    def test_abbreviation_kol_vo_is_doubtful(self):
        # Реальный случай #42377: «кол-\nву» — сокращение «кол-во» с настоящим
        # дефисом; склейка дала бы порчу «колву»
        text = 'Определите изменение кол-\nву проданных товаров.'
        res = glue_field(text)
        self.assertIsNone(res.new_text)
        self.assertEqual(len(res.doubtful), 1)

    def test_latin_hyphen_break_is_doubtful(self):
        # По ТЗ дефис убираем только у кириллических половинок
        text = 'The firm maximizes its consump-\ntion every period.'
        res = glue_field(text)
        self.assertIsNone(res.new_text)
        self.assertEqual(len(res.doubtful), 1)


class StructuralKeepTests(SimpleTestCase):
    """Структурные переносы не склеиваются — ни один из перечисленных."""

    def test_list_markers_kept(self):
        # Реальный случай #36343: варианты ответа а) б) в)
        text = ('Расходы потребителей составили:\n'
                'а) 2\n'
                'б) $2\\sqrt{2}$\n'
                '(в) 16\n'
                '1. первый пункт\n'
                '2) второй пункт\n'
                '• маркер\n'
                '— тире-пункт')
        self.assertEqual(glued(text), text)

    def test_service_labels_kept(self):
        for label in ('Решение: приравняем', 'Ответ: 42', 'Дано: функция',
                      'Найти: цену', 'Примечание: без учёта'):
            text = 'Определите равновесие рынка\n' + label
            self.assertEqual(glued(text), text, label)

    def test_colon_intro_kept(self):
        text = 'Функция задана следующим образом:\nспрос убывает по цене.'
        self.assertEqual(glued(text), text)

    def test_display_math_boundaries_kept(self):
        # Реальный случай #39596: display-формула на своей строке
        text = ('Количество залпов зависит от собранных денег\n'
                '\\[C = \\sum_{i = 1}^{n}s_i\\]\n'
                'и растёт с каждым взносом.')
        self.assertEqual(glued(text), text)

    def test_newline_inside_math_untouched(self):
        # \n живёт ВНУТРИ $$...$$ — содержимое формул не трогаем никогда
        text = 'Дано уравнение $$x + y =\n2z$$ для всех переменных.'
        self.assertEqual(glued(text), text)

    def test_table_rows_kept(self):
        # Реальный случай #49867: markdown-таблица, размазанная по строкам
        text = ('| | $\\omega_d$ | $\\omega_m$ |\n'
                '|---|---|---|\n'
                '| $S_1$ | $S_0$ | $S_0$ |')
        self.assertEqual(glued(text), text)

    def test_latex_table_rows_kept(self):
        text = 'Строка & со & значениями\nвторая & строка & таблицы'
        self.assertEqual(glued(text), text)

    def test_paragraph_breaks_kept(self):
        # Абзацный \n\n — не техническая нарезка; клеится только внутри абзацев
        text = ('Первый абзац оборван посреди\nфразы про экономику.\n'
                '\n'
                'Второй абзац тоже оборван на\nполуслове предложения.')
        res = glue_field(text)
        self.assertEqual(
            res.new_text,
            'Первый абзац оборван посреди фразы про экономику.\n'
            '\n'
            'Второй абзац тоже оборван на полуслове предложения.')

    def test_numeric_axis_column_kept(self):
        # Реальный случай #49925: столбик значений оси графика
        text = 'Спрос на врачей\n700\n600\n500\n1980 1985 1990 1995'
        self.assertEqual(glued(text), text)

    def test_label_number_rows_kept(self):
        # Реальный случай #50095: показатели национальных счетов
        text = 'расходы фирм на оборудование: 350\nстроительство за счёт бюджета: 200'
        self.assertEqual(glued(text), text)

    def test_roman_numeral_markers_kept(self):
        # Находка ревью: (ii)/(iii) склеивались через paren_continuation
        text = ('Which of the following are true?\n'
                '(i) demand increases when price falls\n'
                '(ii) supply increases when price rises\n'
                '(iii) the equilibrium is unique')
        self.assertEqual(glued(text), text)

    def test_list_marker_without_space_kept(self):
        # Находка ревью: PDF-извлечение теряет пробел после скобки — «а)12»
        text = 'Выберите верный ответ\nа)12\nб)24\nв)36'
        self.assertEqual(glued(text), text)

    def test_data_rows_without_colon_kept(self):
        # Находка ревью: столбик показателей без двоеточия
        text = 'Дано:\nинфляция 5%\nбезработица 6%\nнорма резервирования 20%'
        self.assertEqual(glued(text), text)

    def test_year_rows_kept(self):
        # Находка ревью: годовой ряд «2019 г. — 500 млрд»
        text = ('Динамика ВВП страны\n2019 г. — 500 млрд\n'
                '2020 г. — 550 млрд\n2021 г. — 600 млрд')
        self.assertEqual(glued(text), text)

    def test_uppercase_after_weak_ending_kept(self):
        # Реальный случай #50174: недоклеить безопаснее, чем склеить лишнее
        text = 'Определите фактический\nВВП прошлого года.'
        self.assertEqual(glued(text), text)

    def test_math_start_next_line_kept(self):
        # Реальный случай #49732: перечень формул построчно — не склеивать
        text = '$u_1(T, L) = x$,\n$u_1(B, L) = 1$.'
        self.assertEqual(glued(text), text)

    def test_ile_like_structural_text_unchanged(self):
        # Профиль ILE: длинные строки-абзацы с завершающей пунктуацией,
        # список с маркерами. Не должен измениться ни на символ.
        text = ('Полное условие задачи записано одним длинным абзацем, который '
                'заканчивается точкой и не требует никакой склейки строк.\n'
                'Далее идёт перечисление условий взаимодействия сторон:\n'
                '• Первым делом, фирмы независимо выбирают расположение.\n'
                '• Затем каждый житель принимает решение о покупке.\n'
                '\n'
                'Если магазины расположены в одном месте, потребители '
                'разделяются поровну.')
        res = glue_field(text)
        self.assertIsNone(res.new_text)
        self.assertEqual(res.glue_count, 0)
        self.assertEqual(res.hyphen_count, 0)


class IdempotencyAndGuardTests(SimpleTestCase):
    def test_idempotent_on_all_glue_kinds(self):
        battery = [
            'Налог на продажи товаров\nявляется регрессивным.',
            'Кривая предложения фирмы в краткосрочном периоде\nимеет положительный наклон.',
            'Цена выросла в\nМоскве на 10%.',
            'вид: $U = ln(C)$\n, где $C$ — потребление.',
            'ВВП составляет\n4800 млрд р., как известно.',
            'Первый абзац про\nэкономику.\n\nВторой абзац про\nфинансы тоже.',
        ]
        for text in battery:
            first = glue_field(text)
            self.assertIsNotNone(first.new_text, text)
            second = glue_field(first.new_text)
            self.assertIsNone(second.new_text,
                              'повторный прогон изменил текст: %r' % text)

    def test_guard_skips_field_with_too_many_glues(self):
        # MAX_GLUES_PER_FIELD + 20 склеиваемых границ — аномалия, поле
        # помечается пограничным (но new_text строится для предпросмотра)
        n = MAX_GLUES_PER_FIELD + 20
        text = '\n'.join(['строка номер %d без знака' % i for i in range(n + 1)])
        res = glue_field(text)
        self.assertIsNotNone(res.borderline)
        self.assertIn('too_many_glues', res.borderline)
        self.assertIsNotNone(res.new_text)  # предпросмотру нужно «что было бы»

    def test_guard_skips_giant_glued_paragraph(self):
        # три строки по ~900 символов без пунктуации → абзац > 2500 символов
        chunk = 'слово ' * 150
        text = (chunk + '\n' + chunk + '\n' + chunk + 'конец').strip()
        res = glue_field(text)
        self.assertIsNotNone(res.borderline)
        self.assertIn('giant_paragraph', res.borderline)

    def test_text_without_newlines_untouched(self):
        text = 'Одна строка без переносов. $MC = 2Q$.'
        res = glue_field(text)
        self.assertIsNone(res.new_text)


class ClassifyBoundaryTests(SimpleTestCase):
    """Точечные проверки классификатора границ (тень = сама строка,
    когда математики нет)."""

    def _cls(self, a, b):
        return classify_boundary(a, b, a, b)

    def test_terminated_line_keeps(self):
        self.assertEqual(self._cls('Фраза закончилась.', 'и продолжение'),
                         ('keep', 'terminated'))

    def test_closers_do_not_hide_terminal_punct(self):
        self.assertEqual(self._cls('Фраза (в скобках.)', 'и продолжение'),
                         ('keep', 'terminated'))

    def test_lowercase_continuation_glues(self):
        self.assertEqual(self._cls('Строка оборвана посреди', 'фразы без пунктуации'),
                         ('glue', 'lowercase'))

    def test_escaped_dollar_currency_glues(self):
        # AP Economics #49551: «...the output price is» → «\$10, which...»
        action = self._cls('If the output price is', '\\$10, which is true?')
        self.assertEqual(action, ('glue', 'currency'))

    def test_latex_command_start_keeps(self):
        self.assertEqual(self._cls('Величина спроса задана', '\\frac{a}{b} + c'),
                         ('keep', 'latex_command_start'))


class GluePdfLinesCommandTests(TestCase):
    """Команда: dry-run не пишет в базу, границы источников соблюдаются."""

    def setUp(self):
        self.source = make_source(name='PDF-источник (тест)')
        self.sliced = make_problem(
            statement='Налог на продажи товаров\nявляется регрессивным.')
        link_source(self.sliced, self.source)
        self.other_source = make_source(name='Чужой источник (тест)')
        self.other = make_problem(
            statement='Другая задача оборвана посреди\nфразы про экономику.')
        link_source(self.other, self.other_source)

    def _call(self, *args):
        # Отчёты команды уводим во временную папку: тестовый прогон не должен
        # перезаписывать боевые reports/glue_lines/*.
        out = StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch(
                    'problems.management.commands.glue_pdf_lines.REPORT_DIR',
                    os.path.join(tmpdir, 'glue_lines')):
                call_command('glue_pdf_lines', *args, stdout=out)
        return out.getvalue()

    def test_dry_run_does_not_touch_db(self):
        before = self.sliced.statement
        out = self._call('--source-id', str(self.source.id))
        self.sliced.refresh_from_db()
        self.assertEqual(self.sliced.statement, before)
        self.assertIn('база НЕ изменена', out)

    def test_dry_run_counts_only_requested_source(self):
        out = self._call('--source-id', str(self.source.id))
        self.assertIn('PDF-источник (тест)', out)
        self.assertNotIn('Чужой источник (тест)', out)

    def test_confirm_with_duplicate_part_labels_keeps_texts_apart(self):
        # Регресс адверсариального ревью: метки подпунктов НЕ уникальны
        # (в базе есть задачи с двумя «а») — запись по label затирала оба
        # подпункта одним текстом. Применение обязано адресовать по pk.
        from problems.models import ProblemPart
        p1 = ProblemPart.objects.create(
            problem=self.sliced, label='а', order=1,
            statement='Первый подпункт оборван посреди\nфразы про спрос.')
        p2 = ProblemPart.objects.create(
            problem=self.sliced, label='а', order=2,
            statement='Второй подпункт оборван посреди\nфразы про предложение.')
        self._call('--source-id', str(self.source.id), '--confirm')
        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.statement,
                         'Первый подпункт оборван посреди фразы про спрос.')
        self.assertEqual(p2.statement,
                         'Второй подпункт оборван посреди фразы про предложение.')

    def test_confirm_applies_and_writes_changed_ids(self):
        # --confirm в этой сессии не запускается на боевой базе — но сама
        # ветка записи обязана работать (тестовая БД, tearDown её удалит)
        self._call('--source-id', str(self.source.id), '--confirm')
        self.sliced.refresh_from_db()
        self.assertEqual(self.sliced.statement,
                         'Налог на продажи товаров является регрессивным.')
        self.other.refresh_from_db()
        self.assertIn('\n', self.other.statement)  # чужой источник не тронут
