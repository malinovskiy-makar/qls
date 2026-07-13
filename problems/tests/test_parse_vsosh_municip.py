# -*- coding: utf-8 -*-
"""
Тесты parse_vsosh_municip: по каждому профилю вёрстки (семейства A/B/C)
минимум по одному тесту каждого типа вопроса (single/numeric/open), плюс
юнит-тесты декода Symbol-PUA, схлопывания задвоенных глифов и таблицы
ответов. Синтетические Line-объекты — без PDF.
"""
import tempfile
import zipfile
from pathlib import Path

from django.test import SimpleTestCase

from problems.management.commands.parse_vsosh_municip import (
    BULLET, Line, PROFILES,
    cluster_radios, decode_symbol_pua, has_doubled_math,
    parse_answer_table, parse_docx_2019, parse_lines_a, _render_grid_spans,
)

BODY = 14.0


def sp(text, bold=False, font='TimesNewRomanPSMT', size=14.0, x=50.0, y=100.0):
    return {'text': text, 'font': font, 'size': size,
            'flags': 16 if bold else 0, 'origin': (x, y),
            'bbox': (x, y - 10, x + 8 * max(len(text), 1), y + 2)}


class LineFactory:
    """Строки с автоинкрементом y (важен порядок, не координаты)."""

    def __init__(self):
        self.y = 100.0

    def line(self, text=None, bold=False, spans=None, page=1, x=50.0,
             size=14.0):
        self.y += 20
        if spans is None:
            spans = [sp(text, bold=bold, x=x, y=self.y, size=size)]
        else:
            for s in spans:
                s['origin'] = (s['origin'][0], self.y)
                s['bbox'] = (s['bbox'][0], self.y - 10, s['bbox'][2],
                             self.y + 2)
        bbox = (min(s['bbox'][0] for s in spans),
                min(s['bbox'][1] for s in spans),
                max(s['bbox'][2] for s in spans),
                max(s['bbox'][3] for s in spans))
        return Line(spans, bbox, page)


class DecodeSymbolPuaTests(SimpleTestCase):

    def test_common_math_codes(self):
        self.assertEqual(decode_symbol_pua(''), '+=⋅')

    def test_brace_pieces_f8_block(self):
        self.assertEqual(decode_symbol_pua(''), '⎧⎨⎩')

    def test_unknown_pua_becomes_fffd(self):
        self.assertEqual(decode_symbol_pua(''), '�')

    def test_plain_text_untouched(self):
        self.assertEqual(decode_symbol_pua('спрос P=Q'), 'спрос P=Q')


class HasDoubledMathTests(SimpleTestCase):
    """Артефакт Word 2022: «TC(Q)» в текстовом слое = «TTTT(QQ)» — вторая
    буква пары потеряна, восстановить нельзя. Детектор ловит удвоенные
    латинские буквы только внутри $…$."""

    def test_doubled_in_math_detected(self):
        self.assertTrue(has_doubled_math('Пусть $TTTT(QQ) = QQ^{3}$ дано.'))

    def test_clean_math_ok(self):
        self.assertFalse(has_doubled_math('Пусть $TC(Q) = Q^{3}$ дано.'))

    def test_russian_double_letters_outside_math_ok(self):
        # «естественный», «аннуитет» — удвоения вне $…$ не считаются
        self.assertFalse(has_doubled_math('естественный уровень, аннуитет'))


class ParseAnswerTableTests(SimpleTestCase):

    def _lines(self, texts):
        f = LineFactory()
        return [f.line(t) for t in texts]

    def test_merged_rows(self):
        lines = self._lines(['', '№ 1 2 3 4 5', 'Ответ б в г г в'])
        self.assertEqual(parse_answer_table(lines, 0),
                         {1: 'б', 2: 'в', 3: 'г', 4: 'г', 5: 'в'})

    def test_cell_per_line(self):
        lines = self._lines(['№', '1', '2', 'Ответ', 'а', 'г'])
        self.assertEqual(parse_answer_table(lines, 0), {1: 'а', 2: 'г'})

    def test_incomplete_returns_none(self):
        lines = self._lines(['№ 1 2 3', 'Ответ б в'])
        self.assertIsNone(parse_answer_table(lines, 0))


def parse(lines, profile, grades=(9,), group='9'):
    return parse_lines_a(lines, BODY, list(grades), group, profile, 'test.pdf')


class FamilyA2017Tests(SimpleTestCase):
    """2017: сквозная нумерация, номер отдельной строкой, полужирный вариант
    + сверка с таблицей ответов."""

    def _doc(self, bold_letter='б', table_letter='б'):
        f = LineFactory()
        table_letters = {'а': 'а', 'б': 'б', 'в': 'в', 'г': 'г'}[table_letter]
        return [
            f.line('Тестовые задания', bold=True),
            f.line('1.', bold=True, size=16.0),
            f.line('Сколько будет два плюс два в рыночной экономике?'),
            f.line('а) три', bold=(bold_letter == 'а')),
            f.line('б) четыре', bold=(bold_letter == 'б')),
            f.line('в) пять', bold=(bold_letter == 'в')),
            f.line('г) не определено', bold=(bold_letter == 'г')),
            f.line('Таблица ответов на тестовые задания', bold=True),
            f.line('№ 1'),
            f.line(f'Ответ {table_letters}'),
            f.line('Задания с кратким ответом', bold=True),
            f.line('2.', bold=True, size=16.0),
            f.line('Найдите равновесную цену, если спрос и предложение'),
            f.line('линейны и пересекаются в целой точке.'),
            f.line('Ответ: 45 руб. (6 баллов).'),
            f.line('Решение:'),
            f.line('Приравняем спрос и предложение.'),
            f.line('Задания с развёрнутым ответом (решением)', bold=True),
            f.line('3.', bold=True, size=16.0),
            f.line('Опишите последствия введения потолка цены.'),
            f.line('Решение:'),
            f.line('Возникает дефицит, чёрный рынок и очереди.'),
        ]

    def test_single_bold_and_table_agree(self):
        qs, unp = parse(self._doc(), PROFILES[2017])
        self.assertEqual(unp, [])
        single = [q for q in qs if q['qtype'] == 'single'][0]
        self.assertEqual(single['correct'], 1)
        self.assertEqual(single['options'][1], 'четыре')

    def test_single_bold_table_mismatch_unparsed(self):
        qs, unp = parse(self._doc(bold_letter='в', table_letter='б'),
                        PROFILES[2017])
        self.assertEqual([q for q in qs if q['qtype'] == 'single'], [])
        self.assertTrue(any('расхождение' in u['reason'] for u in unp))

    def test_numeric_answer_with_unit(self):
        qs, _ = parse(self._doc(), PROFILES[2017])
        num = [q for q in qs if q['qtype'] == 'numeric'][0]
        self.assertEqual(num['correct'], '45')
        self.assertEqual(num['unit'], 'руб')
        self.assertIn('Приравняем', num['solution'])

    def test_open_with_solution(self):
        qs, _ = parse(self._doc(), PROFILES[2017])
        op = [q for q in qs if q['qtype'] == 'open'][0]
        self.assertIn('дефицит', op['solution'])
        self.assertEqual(op['options'], [])

    def test_two_column_option_order(self):
        # порядок чтения «а в б г» (две колонки) — собирается по буквам
        f = LineFactory()
        lines = [
            f.line('Тестовые задания', bold=True),
            f.line('1.', bold=True, size=16.0),
            f.line('Сколько золота добыли гномы?'),
            f.line('а) 969 т'),
            f.line('в) 931 т', bold=True),
            f.line('б) 969,4 т'),
            f.line('г) 931,4 т'),
            f.line('Таблица ответов на тестовые задания', bold=True),
            f.line('№ 1'),
            f.line('Ответ в'),
        ]
        qs, unp = parse(lines, PROFILES[2017])
        self.assertEqual(unp, [])
        self.assertEqual(qs[0]['options'],
                         ['969 т', '969,4 т', '931 т', '931,4 т'])
        self.assertEqual(qs[0]['correct'], 2)


class FamilyA2018TableTests(SimpleTestCase):
    """2018/2020: варианты не выделены, ответ ТОЛЬКО из таблицы."""

    def test_single_from_table_only(self):
        f = LineFactory()
        lines = [
            f.line('Тестовые задания', bold=True),
            f.line(spans=[sp('1. ', bold=True), sp('Что из перечисленного '
                                                   'приведёт к росту цены?', x=80)]),
            f.line('а) налог на покупателей'),
            f.line('б) субсидия продавцам'),
            f.line('в) рост доходов потребителей'),
            f.line('г) удешевление сырья'),
            f.line('Таблица ответов на тестовые задания', bold=True),
            f.line('№ 1'),
            f.line('Ответ в'),
            f.line('По 4 балла за каждый правильный ответ.', bold=True),
        ]
        qs, unp = parse(lines, PROFILES[2018])
        self.assertEqual(unp, [])
        self.assertEqual(qs[0]['correct'], 2)
        # бейдж «По 4 балла…» не прилип к последнему варианту
        self.assertEqual(qs[0]['options'][3], 'удешевление сырья')

    def test_missing_table_sends_test_to_unparsed(self):
        f = LineFactory()
        lines = [
            f.line('Тестовые задания', bold=True),
            f.line(spans=[sp('1. ', bold=True), sp('Вопрос без ключа?', x=80)]),
            f.line('а) один'), f.line('б) два'),
            f.line('в) три'), f.line('г) четыре'),
        ]
        qs, unp = parse(lines, PROFILES[2018])
        self.assertEqual(qs, [])
        self.assertTrue(any('таблица ответов' in u['reason'] for u in unp))

    def test_long_subanswers_go_to_solution(self):
        # 2020: «Ответ на вопрос 1: 33.» — разбор жюри, уходит в решение
        f = LineFactory()
        lines = [
            f.line('Задания с развёрнутым ответом', bold=True),
            f.line(spans=[sp('12. ', bold=True),
                          sp('Монополист работает на рынке.', x=80)]),
            f.line('Вопрос 1 (7 баллов). Какую цену назначит монополист?'),
            f.line('Ответ на вопрос 1: 33.'),
            f.line('Ответ на вопрос 2: 14.'),
        ]
        qs, unp = parse(lines, PROFILES[2020])
        self.assertEqual(unp, [])
        self.assertEqual(qs[0]['qtype'], 'open')
        self.assertIn('Ответ на вопрос 1: 33.', qs[0]['solution'])


class FamilyA2022Tests(SimpleTestCase):
    """2022: нумерация с 1 в каждой секции, правильный вариант полужирный."""

    def _doc(self):
        f = LineFactory()
        return [
            f.line('Тестовые задания', bold=True),
            f.line(spans=[sp('1. ', bold=True),
                          sp('Понижение ключевой ставки — это:', x=80)]),
            f.line('а) стимулирующая мера'),
            f.line(spans=[sp('б)', bold=True, x=50),
                          sp(' сдерживающая мера', bold=True, x=70)]),
            f.line('в) нейтральная мера'),
            f.line('г) не мера вовсе'),
            f.line('Максимум за тестовые задания – 20 баллов.', bold=True),
            f.line('Задания с кратким ответом', bold=True),
            f.line(spans=[sp('1. ', bold=True),
                          sp('Найдите TC(6), если TC линейна.', x=80)]),
            f.line('Ответ: 87.'),
            f.line('Решение: подставим и посчитаем.'),
        ]

    def test_single_bold_option(self):
        qs, unp = parse(self._doc(), PROFILES[2022])
        self.assertEqual(unp, [])
        single = [q for q in qs if q['qtype'] == 'single'][0]
        self.assertEqual(single['correct'], 1)

    def test_per_section_numbering_restarts(self):
        qs, unp = parse(self._doc(), PROFILES[2022])
        nums = sorted((q['section'], q['number']) for q in qs)
        self.assertEqual(nums, [('short', '1'), ('test', '1')])

    def test_numeric_in_short_section(self):
        qs, _ = parse(self._doc(), PROFILES[2022])
        num = [q for q in qs if q['qtype'] == 'numeric'][0]
        self.assertEqual(num['correct'], '87')
        self.assertIn('подставим', num['solution'])


class FamilyA2023BulletTests(SimpleTestCase):
    """2023: варианты — буллеты без букв, правильный = полужирный текст."""

    def _bullet_line(self, f, text, bold=False):
        return f.line(spans=[sp(BULLET, font='Symbol', x=50),
                             sp(text, bold=bold, x=70)])

    def _doc(self):
        f = LineFactory()
        return [
            f.line('Тестовые задания', bold=True),
            f.line('За правильный ответ начисляется 4 балла.'),
            f.line(spans=[sp('1. ', bold=True),
                          sp('Чему равна эластичность?', x=80)]),
            self._bullet_line(f, '0,5'),
            self._bullet_line(f, '–0,5'),
            self._bullet_line(f, '2', bold=True),
            self._bullet_line(f, '–2'),
            f.line('Комментарий:'),
            f.line('Эластичность считается по формуле.'),
            f.line('Задания с кратким ответом', bold=True),
            f.line('За правильный ответ начисляется 8 баллов.'),
            f.line(spans=[sp('1. ', bold=True),
                          sp('Определите совокупный доход Маши.', x=80)]),
            f.line('Ответ: 4200'),
            f.line('Решение: купонный доход за 5 лет.'),
        ]

    def test_single_bold_bullet(self):
        qs, unp = parse(self._doc(), PROFILES[2023])
        self.assertEqual(unp, [])
        single = [q for q in qs if q['qtype'] == 'single'][0]
        self.assertEqual(single['correct'], 2)
        self.assertEqual(single['options'], ['0,5', '–0,5', '2', '–2'])
        self.assertIn('по формуле', single['solution'])

    def test_numeric(self):
        qs, _ = parse(self._doc(), PROFILES[2023])
        num = [q for q in qs if q['qtype'] == 'numeric'][0]
        self.assertEqual(num['correct'], '4200')
        self.assertEqual(num['points'], 8)  # из преамбулы своей секции

    def test_points_from_preamble(self):
        qs, _ = parse(self._doc(), PROFILES[2023])
        single = [q for q in qs if q['qtype'] == 'single'][0]
        self.assertEqual(single['points'], 4)


class NumericFallbackTests(SimpleTestCase):

    def test_multi_part_answer_becomes_open(self):
        # «Ответ: а) 6; б) 12» — не число: честный фолбэк в open
        f = LineFactory()
        lines = [
            f.line('Задания с кратким ответом', bold=True),
            f.line(spans=[sp('6. ', bold=True),
                          sp('Найдите оба значения.', x=80)]),
            f.line('Ответ: а) 6 (2 балла); б) 12 (4 балла).'),
        ]
        qs, unp = parse(lines, PROFILES[2017])
        self.assertEqual(unp, [])
        self.assertEqual(qs[0]['qtype'], 'open')
        self.assertIn('а) 6', qs[0]['answer_text'])
        self.assertIn('не в игру', qs[0]['notes'])


class Grid2021Tests(SimpleTestCase):
    """2021: сетка онлайн-платформы — кластеризация радиокнопок и STIX."""

    def test_cluster_radios_by_gap(self):
        radios = [(100, 114, False), (150, 164, True), (200, 214, False),
                  (250, 264, False),
                  (500, 514, True), (550, 564, False), (600, 614, False),
                  (650, 664, False)]
        clusters = cluster_radios(radios)
        self.assertEqual([len(c) for c in clusters], [4, 4])
        self.assertEqual([k for k, c in enumerate(clusters[0]) if c[2]], [1])

    def test_render_grid_spans_stix_math(self):
        # математические алфавитно-цифровые (STIX) → $…$
        spans = [sp('Функция ', font='Roboto-Regular', size=7.9, x=10),
                 sp('\U0001d447\U0001d436', font='STIXGeneral-Italic',
                    size=9.6, x=80),
                 sp(' возрастает', font='Roboto-Regular', size=7.9, x=120)]
        text = _render_grid_spans(spans)
        self.assertIn('$TC$', text.replace(' ', ''))
        self.assertTrue(text.startswith('Функция'))


class Docx2019Tests(SimpleTestCase):
    """2019 DOCX: варианты word-списком + таблица ответов; OLE → unparsed."""

    W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

    def _p(self, text, bold=False, numid=None, italic=False, ole=False):
        rpr = ''
        if bold:
            rpr = '<w:rPr><w:b/></w:rPr>'
        elif italic:
            rpr = '<w:rPr><w:i/></w:rPr>'
        npr = (f'<w:pPr><w:numPr><w:ilvl w:val="0"/>'
               f'<w:numId w:val="{numid}"/></w:numPr></w:pPr>'
               if numid else '')
        obj = '<w:r><w:object/></w:r>' if ole else ''
        return (f'<w:p>{npr}<w:r>{rpr}<w:t xml:space="preserve">{text}'
                f'</w:t></w:r>{obj}</w:p>')

    def _tbl(self, rows):
        out = ['<w:tbl>']
        for row in rows:
            out.append('<w:tr>')
            for cell in row:
                out.append(f'<w:tc><w:p><w:r><w:t>{cell}</w:t></w:r>'
                           '</w:p></w:tc>')
            out.append('</w:tr>')
        out.append('</w:tbl>')
        return ''.join(out)

    def _make_docx(self, body_xml):
        doc = (f'<?xml version="1.0"?><w:document xmlns:w="{self.W}">'
               f'<w:body>{body_xml}</w:body></w:document>')
        numbering = (f'<?xml version="1.0"?><w:numbering xmlns:w="{self.W}">'
                     '<w:abstractNum w:abstractNumId="0">'
                     '<w:lvl w:ilvl="0"><w:numFmt w:val="russianLower"/>'
                     '</w:lvl></w:abstractNum>'
                     '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
                     '</w:numbering>')
        tmp = tempfile.NamedTemporaryFile(suffix='.docx', delete=False)
        with zipfile.ZipFile(tmp, 'w') as z:
            z.writestr('word/document.xml', doc)
            z.writestr('word/numbering.xml', numbering)
        tmp.close()
        return Path(tmp.name)

    def _standard_doc(self):
        return self._make_docx(''.join([
            self._p('Тестовые задания', bold=True),
            self._p('1.\xa0Отличительной чертой рыночной экономики является:',
                    bold=True),
            self._p('ограниченное вмешательство государства', numid='1'),
            self._p('большая доля ручного труда', numid='1'),
            self._p('государственная собственность', numid='1'),
            self._p('высокие тарифы', numid='1'),
            self._p('Таблица ответов на тестовые задания', bold=True),
            self._tbl([['№', '1'], ['Ответ', 'а']]),
            self._p('Задания с кратким ответом', bold=True),
            self._p('2.\xa0Насколько упадёт выручка?', bold=True),
            self._p('Ответ: 21 (6 баллов)'),
            self._p('Решение: посчитаем эластичность.'),
            self._p('Задания с развёрнутым ответом (решением)', bold=True),
            self._p('3.\xa0Найдите цену золота в ливро.', bold=True),
            self._p('Ответ: 216 ливро.'),
            self._p('Решение: арбитраж выравнивает цены.'),
            self._p('4.\xa0Задача с формулой-объектом.', bold=True, ole=True),
            self._p('Ответ: 17 200.'),
        ]))

    def test_single_letter_from_table(self):
        qs, unp = parse_docx_2019(self._standard_doc(), (9,), '9', 'x.docx')
        single = [q for q in qs if q['qtype'] == 'single'][0]
        self.assertEqual(single['correct'], 0)
        self.assertEqual(len(single['options']), 4)

    def test_numeric(self):
        qs, _ = parse_docx_2019(self._standard_doc(), (9,), '9', 'x.docx')
        num = [q for q in qs if q['qtype'] == 'numeric'][0]
        self.assertEqual(num['correct'], '21')
        self.assertIn('эластичность', num['solution'])

    def test_open(self):
        qs, _ = parse_docx_2019(self._standard_doc(), (9,), '9', 'x.docx')
        op = [q for q in qs if q['qtype'] == 'open'][0]
        self.assertEqual(op['answer_text'], '216 ливро.')
        self.assertIn('арбитраж', op['solution'])

    def test_ole_in_statement_unparsed(self):
        _, unp = parse_docx_2019(self._standard_doc(), (9,), '9', 'x.docx')
        self.assertTrue(any(u['number'] == '4' and 'OLE' in u['reason']
                            for u in unp))
