"""Объединение классов у привязок к олимпиадам — `problems/olympiad_grades.py`.

Проверяется ADR 0058: расхождение только по `grade` при совпадающем туре —
это диапазон, а не конфликт. Разбор строк базы не требует, поэтому
`SimpleTestCase`; строки `OlympiadRef` подставляются несохранёнными
объектами — модель нужна только как носитель четырёх полей.
"""
from django.test import SimpleTestCase

from problems.models import OlympiadRef
from problems.olympiad_grades import (
    classify_refs,
    event_key,
    format_grades,
    merge_grades_by_event,
    parse_grades,
)


def ref(slug='vseros', year=2021, stage='final', grade='9'):
    """Несохранённая строка привязки — носитель четырёх интересных полей."""
    return OlympiadRef(olympiad_slug=slug, year=year, stage=stage, grade=grade)


class ParseGradesTests(SimpleTestCase):

    def test_одиночный_класс(self):
        self.assertEqual(parse_grades('9'), {9})

    def test_диапазон_раскрывается_целиком(self):
        """SolveHub кладёт готовый диапазон одной строкой."""
        self.assertEqual(parse_grades('7-11'), {7, 8, 9, 10, 11})

    def test_пустое_значение_даёт_пустое_множество(self):
        for value in ('', '   ', None):
            self.assertEqual(parse_grades(value), set())

    def test_непонятное_значение_не_роняет_прогон(self):
        """Класс — справочное поле; незнакомый формат не повод падать."""
        self.assertEqual(parse_grades('старшая школа'), set())

    def test_перевёрнутый_диапазон_читается(self):
        self.assertEqual(parse_grades('11-9'), {9, 10, 11})


class FormatGradesTests(SimpleTestCase):

    def test_подряд_идущие_схлопываются_в_диапазон(self):
        self.assertEqual(format_grades({9, 10, 11}), '9-11')

    def test_два_подряд_тоже_диапазон(self):
        """«10-11», а не «10, 11» — так пишут сами олимпиады."""
        self.assertEqual(format_grades({10, 11}), '10-11')

    def test_разрыв_разделяется_запятой(self):
        self.assertEqual(format_grades({9, 11}), '9, 11')

    def test_пробеги_и_разрывы_вместе(self):
        """Случай из фактических данных: 7-8, 10-11 (одна задача банка).

        Плоского «списка через запятую» здесь не хватило бы.
        """
        self.assertEqual(format_grades({7, 8, 10, 11}), '7-8, 10-11')

    def test_один_класс_остаётся_числом(self):
        self.assertEqual(format_grades({9}), '9')

    def test_пусто_остаётся_пустым(self):
        self.assertEqual(format_grades(set()), '')


class ClassifyRefsTests(SimpleTestCase):
    """Главное правило ADR 0058: класс — не конфликт, тур — конфликт."""

    def test_одна_строка_сравнивать_не_с_чем(self):
        self.assertEqual(classify_refs([ref()]), 'single')

    def test_совпало_всё_кроме_учётной_мелочи(self):
        self.assertEqual(classify_refs([ref(), ref()]), 'agree')

    def test_разные_классы_при_одном_туре_НЕ_конфликт(self):
        """Случай ILE z/2438: «Пробу» 2011 писали и 10-е, и 11-е классы."""
        self.assertEqual(
            classify_refs([ref(grade='10'), ref(grade='11')]),
            'grade_only',
        )

    def test_разная_олимпиада_это_конфликт(self):
        self.assertEqual(
            classify_refs([ref(slug='mosh'), ref(slug='vseros')]),
            'conflict',
        )

    def test_разный_год_это_конфликт(self):
        self.assertEqual(
            classify_refs([ref(year=2019), ref(year=2020)]),
            'conflict',
        )

    def test_разный_этап_это_конфликт(self):
        self.assertEqual(
            classify_refs([ref(stage='final'), ref(stage='municipal')]),
            'conflict',
        )

    def test_разный_класс_поверх_разной_олимпиады_остаётся_конфликтом(self):
        """Класс не может «починить» расхождение по туру."""
        self.assertEqual(
            classify_refs([ref(slug='mosh', grade='10'),
                           ref(slug='vseros', grade='11')]),
            'conflict',
        )


class MergeGradesByEventTests(SimpleTestCase):

    def test_класс_не_входит_в_ключ_группировки(self):
        """Иначе строки с разными классами не встретились бы в одной группе."""
        self.assertEqual(event_key(ref(grade='10')), event_key(ref(grade='11')))

    def test_строки_одного_тура_сливаются_в_диапазон(self):
        merged = merge_grades_by_event([ref(grade='11'), ref(grade='9-10')])
        self.assertEqual(merged, {('vseros', 2021, 'final'): '9-11'})

    def test_разные_туры_остаются_разными_группами(self):
        """Случай #1733: две олимпиады, классы сливаются внутри каждой.

        Конфликт остаётся конфликтом, но класс всё равно объединяется —
        поэтому отчёт может показать оба тура с их диапазонами.
        """
        merged = merge_grades_by_event([
            ref(slug='nes', stage='', grade='9'),
            ref(slug='nes', stage='', grade='10'),
            ref(slug='vseros', grade='9'),
            ref(slug='vseros', grade='10'),
        ])
        self.assertEqual(merged, {
            ('nes', 2021, ''): '9-10',
            ('vseros', 2021, 'final'): '9-10',
        })
