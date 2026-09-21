"""Проверка присланных ответов: что попадает в `raw`, а что отвергается."""
from decimal import Decimal as D

from django.test import SimpleTestCase

from vp.answers import AnswerError, clean_answer
from vp.models import VPItem


def item(kind, **kw):
    options = [{'n': n, 'text': str(n)} for n in range(1, 6)]
    return VPItem(kind=kind, options=options, points=D('2'), **kw)


class CleanAnswerTests(SimpleTestCase):
    def test_short_text(self):
        short = item('short_text')
        self.assertEqual(clean_answer(short, '  картель '), 'картель')
        self.assertIsNone(clean_answer(short, '   '))
        self.assertIsNone(clean_answer(short, None))
        self.assertEqual(clean_answer(short, 'я' * 200), 'я' * 200)
        for bad in ('я' * 201, ['x'], 5, {'a': 1}):
            with self.assertRaises(AnswerError, msg=repr(bad)):
                clean_answer(short, bad)

    def test_single(self):
        single = item('single')
        self.assertEqual(clean_answer(single, 3), 3)
        self.assertEqual(clean_answer(single, '4'), 4)
        self.assertEqual(clean_answer(single, [2]), 2)
        for empty in (None, '', []):
            self.assertIsNone(clean_answer(single, empty))
        for bad in (9, 0, 'x', True, [1, 2], {'a': 1}):
            with self.assertRaises(AnswerError, msg=repr(bad)):
                clean_answer(single, bad)

    def test_multi(self):
        multi = item('multi')
        self.assertEqual(clean_answer(multi, [3, '1', 3]), [1, 3])
        for empty in (None, '', []):
            self.assertIsNone(clean_answer(multi, empty))
        for bad in (7, [1, 8], 'x', [True], [None]):
            with self.assertRaises(AnswerError, msg=repr(bad)):
                clean_answer(multi, bad)

    def test_match(self):
        pairs = item('match', correct={'а': 2, 'б': 1})
        self.assertEqual(clean_answer(pairs, {'а': 2, 'б': '1'}), {'а': 2, 'б': 1})
        self.assertEqual(clean_answer(pairs, {'а': 2, 'б': ''}), {'а': 2})
        for empty in (None, '', {}, []):
            self.assertIsNone(clean_answer(pairs, empty))
        self.assertIsNone(clean_answer(pairs, {'а': ''}))
        for bad in ({'в': 1}, {'а': 9}, {'а': True}, 'x', [1]):
            with self.assertRaises(AnswerError, msg=repr(bad)):
                clean_answer(pairs, bad)

    def test_unknown_kind(self):
        with self.assertRaises(AnswerError):
            clean_answer(item('nonsense'), 'x')
