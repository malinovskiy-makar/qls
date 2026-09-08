# -*- coding: utf-8 -*-
"""Замена боевого `title` кандидатом: правило корзин и инварианты записи.

Поле видит ученик, правка массовая и необратимая без снимка — поэтому здесь
проверяется не «команда отработала», а инварианты из задания: тексты не
тронуты, изменились ровно посчитанные задачи, имени поля в заголовке не
осталось, `--revert` возвращает побайтово, второй проход даёт ноль.

Критерий переписан в третий раз (решение владельца 07.09.2026 «Критерий
замены заголовков финальный»). Словарь экономических терминов из него убран
целиком, и тесты на него удалены вместе с кодом — оставленный «на всякий
случай» тест мёртвой проверки хуже, чем его отсутствие: он создаёт видимость,
что проверка работает.
"""
import json
import os
import tempfile

from django.core.management import call_command
from django.test import TestCase

from problems import title_replacement as tr
from problems.embedding_provenance import PROTECTED_FIELDS, protected_fingerprint
from problems.models import Problem

УСЛОВИЕ = ('Фирма-монополист производит два товара и максимизирует прибыль '
           'при линейном спросе. Найдите равновесную цену.')


def задача(**kwargs):
    kwargs.setdefault('statement', УСЛОВИЕ)
    return Problem.objects.create(**kwargs)


class NormalizedTests(TestCase):
    """Нормализация сверки. Она и есть починка детектора «эхо условия»."""

    def test_ё_и_е_считаются_одной_буквой(self):
        """Сторож починки: заголовок «трех» и условие «трёх» — совпадение.

        До починки детектор сравнивал буквально и на этой одной букве
        разваливался. Тест обязан краснеть на старой реализации.
        """
        self.assertEqual(tr.normalized('товары трёх групп'),
                         tr.normalized('товары трех групп'))
        self.assertTrue(tr.starts_statement(
            'Потребители покупают товары трех групп',
            'Потребители покупают товары трёх групп: хлеб, молоко и мясо.'))

    def test_пунктуация_снимается(self):
        self.assertEqual(tr.normalized('Спрос, предложение: равновесие!'),
                         'спрос предложение равновесие')

    def test_цифры_остаются(self):
        """Задание перечисляет цифры среди того, что НЕ снимается. Если их
        убрать, условие «2009 конкурентная фирма…» начнёт совпадать с любым
        заголовком «Конкурентная фирма…» — и критерий станет шире, чем решено."""
        self.assertEqual(tr.normalized('Задача 12 (2016)'), 'задача 12 2016')

    def test_пробелы_схлопываются_и_края_обрезаются(self):
        self.assertEqual(tr.normalized('  Спрос   и\n\tпредложение  '),
                         'спрос и предложение')

    def test_пустое_и_None(self):
        self.assertEqual(tr.normalized(None), '')
        self.assertEqual(tr.normalized('   '), '')


class CandidateUsableTests(TestCase):

    def test_годный_кандидат(self):
        self.assertTrue(tr.candidate_is_usable('Дуополия Курно'))

    def test_негодные_кандидаты(self):
        for плохой in ('', '   ', 'title_candidate', 'title_source',
                       'Задача 12', 'Цена $p$', r'Кривая \alpha',
                       'Очень длинный заголовок, который заведомо не влезает '
                       'в сорок символов'):
            with self.subTest(кандидат=плохой):
                self.assertFalse(tr.candidate_is_usable(плохой))


class TruncationTests(TestCase):
    """Правило 2 — обрубок ДЛИННЕЕ 40 символов."""

    ДЛИННЫЙ = 'Фирма-монополист производит два товара и…'   # 41 символ

    def test_длинный_заголовок_дословно_начинает_условие(self):
        self.assertGreater(len(self.ДЛИННЫЙ), tr.TITLE_LIMIT)
        self.assertTrue(tr.is_truncation(self.ДЛИННЫЙ, УСЛОВИЕ))

    def test_порог_сорока_символов_обязателен(self):
        """Сторож ответа владельца на вопрос 3. Короткий заголовок, дословно
        начинающий условие, — это авторская кличка, продублированная шапкой
        («Национальное достояние», «ШтаКельНо»), а не обрубок. Замерено: таких
        коротких не-firstline заголовков 817 опубликованных.
        """
        кличка = 'Дуополия Курно'
        условие = 'Дуополия Курно. Две фирмы делят рынок и выбирают выпуск.'
        self.assertTrue(tr.starts_statement(кличка, условие))
        self.assertLessEqual(len(кличка), tr.TITLE_LIMIT)
        self.assertFalse(tr.is_truncation(кличка, условие))

    def test_ведущее_число_срезается_у_условия(self):
        """Сторож починки ложного отрицания: импорт оставляет в начале условия
        номер задачи или год, заголовок его не содержит. id 6308 и id 41249 —
        обе названы владельцем поимённо."""
        заголовок = 'Конкурентная фирма, максимизирующая прибыль, реализует'
        self.assertGreater(len(заголовок), tr.TITLE_LIMIT)
        условие = ('2009 Конкурентная фирма, максимизирующая прибыль, '
                   'реализует продукцию по 20 долл.')
        self.assertEqual(tr.compare_key(условие)[:12], 'конкурентная')
        self.assertTrue(tr.is_truncation(заголовок, условие))

    def test_свой_заголовок_условие_не_начинает(self):
        self.assertFalse(tr.is_truncation(
            'Совершенно осмысленное название задачи про дуополию', УСЛОВИЕ))

    def test_обрыв_на_чёрточке(self):
        for хвост in ('явля-', 'явля–', 'явля—', 'явля- '):
            with self.subTest(хвост=хвост):
                self.assertTrue(tr.ends_with_dash(
                    'Активами Центрального банка (ЦБ) ' + хвост))

    def test_кличка_с_чёрточкой_в_середине_не_обрубок(self):
        """«Подсолнух - 2» чёрточкой не заканчивается — это авторская кличка."""
        self.assertFalse(tr.ends_with_dash('Подсолнух - 2'))
        self.assertFalse(tr.ends_with_dash('Обзор мер регулирования -- 1'))

    def test_пустое_условие_обрубком_не_делает(self):
        self.assertFalse(tr.is_truncation(
            'Какой-то заголовок задачи подлиннее сорока символов', ''))

    def test_у_чёрточки_порога_длины_НЕТ(self):
        """Решение владельца 08.09 на замере: из 116 коротких не-firstline
        заголовков с чёрточкой на конце исключений нет ни одного. Собственный
        пример владельца — 38 символов, то есть под порогом не ловился бы."""
        короткий = 'Активами Центрального банка (ЦБ) явля-'
        self.assertLessEqual(len(короткий), tr.TITLE_LIMIT)
        self.assertTrue(tr.is_truncation(короткий, 'Активами ЦБ являются…'))
        self.assertTrue(tr.is_truncation('Рассмотрим инди-', 'что угодно'))

    def test_ведущее_число_срезается_с_ОБЕИХ_сторон(self):
        """Односторонний вариант ломался там, где номер есть и в заголовке."""
        заголовок = '[1] Страны А и Б производят клубничный смузи и десерт'
        условие = ('[1] Страны А и Б производят клубничный смузи и десерт, '
                   'используя клубнику.')
        self.assertGreater(len(заголовок), tr.TITLE_LIMIT)
        self.assertEqual(tr.compare_key(заголовок)[:6], 'страны')
        self.assertTrue(tr.is_truncation(заголовок, условие))


class TechnicalNumberTests(TestCase):
    """Корзина «технические номера» — регулярка не должна хватать лишнего."""

    def test_номер_вместо_названия(self):
        for заголовок in ('Тест 23', 'Задача 1 ОЧ-2016 (9 класс)',
                          'Задание 12. РЭ ПОШ – 2025 (9 класс)',
                          'Задача 5 (СПбГУ 2016)', 'Вопрос 3', '№ 7',
                          '№5', 'Задача №3', 'Упражнение 2', 'Пример 1',
                          'task 4', 'Problem 12', 'Тест-3'):
            with self.subTest(заголовок=заголовок):
                self.assertTrue(tr.is_technical_number(заголовок))

    def test_осмысленное_название_с_тем_же_словом_остаётся(self):
        """Главный риск регулярки — схватить «Задачу о двух заводах»."""
        for заголовок in ('Задача о двух заводах', 'Задача про номинальный доход',
                          'Тесты - макро', 'Тестирование рынка 5',
                          'Примерно 5 фирм на рынке', 'вопросик',
                          'Пример инструмента фискальной политики',
                          'Задача на построение КПВ'):
            with self.subTest(заголовок=заголовок):
                self.assertFalse(tr.is_technical_number(заголовок))

    def test_буква_между_словом_и_цифрой_запрещена(self):
        """Разделители — только пробелы, точки, чёрточки и «№». Если пустить
        туда буквы, «Тестирование рынка 5» станет техническим номером."""
        self.assertFalse(tr.is_technical_number('Тест по теме 3'))


class BucketTests(TestCase):

    def test_обрубок_первой_строки(self):
        p = задача(title='Фирма-монополист производит два товара и…',
                   title_candidate='Дуополия Курно',
                   title_source='model-firstline')
        self.assertEqual(tr.bucket(p), 'обрубки')

    def test_правило_1_метка_происхождения_без_других_правил(self):
        """Самая новая часть критерия: короткий осколок, который не ловят ни
        правило 2 (длиннее 40), ни правило 3 (номер). Ловит только метка."""
        for осколок in ('a', 'b, c, d', 'КПВ', 'Банк', '[рисунок]'):
            with self.subTest(заголовок=осколок):
                p = задача(title=осколок, title_candidate='Дуополия Курно',
                           title_source='model-firstline')
                self.assertFalse(tr.is_truncation(p.title, p.statement))
                self.assertFalse(tr.is_technical_number(p.title))
                self.assertEqual(tr.bucket(p), 'первая строка')

    def test_такой_же_осколок_но_не_firstline_остаётся(self):
        """Зеркало предыдущего: без метки происхождения тот же заголовок —
        авторская кличка, и её владелец велел беречь."""
        p = задача(title='Банк', title_candidate='Дуополия Курно',
                   title_source='kept')
        self.assertEqual(tr.bucket(p), 'не трогаем')

    def test_обрубок_среди_kept(self):
        p = задача(title='Фирма-монополист производит два товара и…',
                   title_candidate='Дуополия Курно', title_source='kept')
        self.assertGreater(len(p.title), tr.TITLE_LIMIT)
        self.assertEqual(tr.bucket(p), 'обрубки')

    def test_технический_номер(self):
        p = задача(title='Тест 23', title_candidate='Повышение акциза',
                   title_source='kept')
        self.assertEqual(tr.bucket(p), 'технические номера')

    def test_авторская_кличка_остаётся(self):
        for кличка in ('Подсолнух - 2', "It's a life", 'Измерение С-37',
                       'Заминка'):
            with self.subTest(кличка=кличка):
                p = задача(title=кличка, title_candidate='Опцион и погода',
                           title_source='kept')
                self.assertEqual(tr.bucket(p), 'не трогаем')

    def test_осмысленный_длинный_заголовок_остаётся(self):
        """Прямое решение владельца 07.09: длина сама по себе не порок."""
        p = задача(title='Закон Оукена при равенстве фрикционной и '
                         'структурной безработицы',
                   title_candidate='Закон Оукена', title_source='kept')
        self.assertGreater(len(p.title), tr.TITLE_LIMIT)
        self.assertEqual(tr.bucket(p), 'не трогаем')

    def test_длина_на_корзину_не_влияет(self):
        """Два осмысленных заголовка разной длины — одна корзина."""
        короткий = задача(title='Кривая Лаффера', title_candidate='Налог',
                          title_source='kept')
        длинный = задача(title='Потоварный налог, кривая Лаффера и '
                               'максимизация сборов',
                         title_candidate='Налог', title_source='kept')
        self.assertGreater(len(длинный.title), tr.TITLE_LIMIT)
        self.assertEqual(tr.bucket(короткий), tr.bucket(длинный))
        self.assertEqual(tr.bucket(длинный), 'не трогаем')

    def test_словарь_терминов_в_критерии_не_участвует(self):
        """Сторож снятой проверки. «Монополия» — термин словаря, и по прежнему
        критерию заголовок бы уцелел; теперь решает только обрубочность."""
        self.assertFalse(hasattr(tr, 'has_econ_term'))
        p = задача(title='Фирма-монополист производит два товара и…',
                   title_candidate='Дуополия Курно', title_source='kept')
        self.assertEqual(tr.bucket(p), 'обрубки')

    def test_уже_равен_кандидату(self):
        p = задача(title='Дуополия Курно', title_candidate='Дуополия Курно',
                   title_source='model-empty')
        self.assertEqual(tr.bucket(p), 'уже равен кандидату')

    def test_баговый_кандидат(self):
        p = задача(title='Монополия', title_candidate='title_candidate',
                   title_source='title_source')
        self.assertEqual(tr.bucket(p), 'кандидат негоден')

    def test_корзины_отчёта_не_меняют_состав_замены(self):
        """Порядок правил в `bucket()` влияет только на то, в какой корзине
        задача покажется в отчёте. Замена — объединение трёх правил."""
        p = задача(title='Тест 23', title_candidate='Повышение акциза',
                   title_source='model-firstline')
        self.assertIn(tr.bucket(p), tr.REPLACED)

    def test_обрубок_проверяется_раньше_номера(self):
        """«Задача 5. Фирма-монополист производит…» — и номер, и обрубок.
        Порядок записан: обрубочность проверена по условию, номер — по виду
        заголовка, поэтому в отчёте задача обязана быть обрубком."""
        p = задача(title='Задача 5. Фирма-монополист производит два товара и…',
                   statement='Задача 5. Фирма-монополист производит два '
                             'товара и максимизирует прибыль.',
                   title_candidate='Дуополия Курно', title_source='kept')
        self.assertTrue(tr.is_technical_number(p.title))
        self.assertEqual(tr.bucket(p), 'обрубки')


class ApplyTests(TestCase):

    def setUp(self):
        self.снимок = os.path.join(tempfile.mkdtemp(), 'titles.json')
        self.меняем = задача(title='Фирма-монополист производит два товара и…',
                             title_candidate='Дуополия Курно',
                             title_source='model-firstline')
        self.не_трогаем = задача(title='Монополия',
                                 title_candidate='title_candidate',
                                 title_source='title_source')

    def _apply(self, *args):
        call_command('apply_title_candidates', '--snapshot', self.снимок, *args)

    def test_без_apply_ничего_не_пишется(self):
        self._apply()
        self.меняем.refresh_from_db()
        self.assertEqual(self.меняем.title,
                         'Фирма-монополист производит два товара и…')
        self.assertFalse(os.path.exists(self.снимок))

    def test_пишется_только_title(self):
        до = protected_fingerprint(Problem.objects.all(), PROTECTED_FIELDS)
        кандидат_до = self.меняем.title_candidate
        self._apply('--apply')
        self.меняем.refresh_from_db()
        self.assertEqual(self.меняем.title, 'Дуополия Курно')
        self.assertEqual(self.меняем.title_candidate, кандидат_до)
        self.assertEqual(
            protected_fingerprint(Problem.objects.all(), PROTECTED_FIELDS), до)

    def test_задача_вне_корзин_не_меняется(self):
        self._apply('--apply')
        self.не_трогаем.refresh_from_db()
        self.assertEqual(self.не_трогаем.title, 'Монополия')

    def test_после_замены_нет_имён_полей_и_нет_длинных(self):
        self._apply('--apply')
        self.assertFalse(Problem.objects.filter(
            title__in=sorted(tr.FIELD_NAME_MARKERS)).exists())
        for заголовок in Problem.objects.filter(
                id=self.меняем.id).values_list('title', flat=True):
            self.assertLessEqual(len(заголовок), tr.TITLE_LIMIT)

    def test_снимок_содержит_ровно_изменённые(self):
        self._apply('--apply')
        with open(self.снимок, encoding='utf-8') as fh:
            снимок = json.load(fh)
        self.assertEqual(list(снимок), [str(self.меняем.id)])
        self.assertEqual(снимок[str(self.меняем.id)],
                         'Фирма-монополист производит два товара и…')

    def test_revert_возвращает_побайтово(self):
        было = self.меняем.title
        self._apply('--apply')
        self._apply('--revert', '--apply')
        self.меняем.refresh_from_db()
        self.assertEqual(self.меняем.title, было)

    def test_повторный_прогон_после_замены_даёт_ноль(self):
        """Идемпотентность: после замены `title` равен кандидату, значит
        задача уходит в «уже равен кандидату» и второй раз не переписывается."""
        self._apply('--apply')
        self.меняем.refresh_from_db()
        self.assertEqual(tr.bucket(self.меняем), 'уже равен кандидату')

    def test_отчёт_рисуется_и_не_пишет_в_базу(self):
        путь = os.path.join(os.path.dirname(self.снимок), 'review.html')
        self._apply('--report', '--report-path', путь)
        self.assertTrue(os.path.exists(путь))
        with open(путь, encoding='utf-8') as fh:
            html = fh.read()
        self.assertIn('Дуополия Курно', html)
        self.меняем.refresh_from_db()
        self.assertNotEqual(self.меняем.title, 'Дуополия Курно')

    def test_отчёт_не_упоминает_словарь_терминов(self):
        """Задание: убрать термин «и из кода, и из описаний отчёта», чтобы
        через неделю никто не гадал, работает эта проверка или нет."""
        путь = os.path.join(os.path.dirname(self.снимок), 'review.html')
        self._apply('--report', '--report-path', путь)
        with open(путь, encoding='utf-8') as fh:
            html = fh.read().lower()
        self.assertNotIn('термин', html)
        self.assertNotIn('словар', html)
