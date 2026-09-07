# -*- coding: utf-8 -*-
"""Слияние ручной надстройки словаря (`econ_terms_manual.md`) с источником.

`Command._merge_manual()` — единственное место, где ручные добавки владельца
(задание сессии 2026-09-03) сходятся с аудируемым `econ_terms_source.md`.
Тесты бьют по механизму синтетическими данными, а не по сегодняшнему
содержимому `econ_terms_manual.md` — оно будет расти, а правило «коллизия
останавливает запись целиком» обязано работать всегда.
"""
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from problems.management.commands.build_econ_terms import Command


def _term(canonical, synonyms=(), word_forms=None):
    return {
        'canonical': canonical,
        'section': 'тест',
        'synonyms': list(synonyms),
        'english': [],
        'notations': [],
        'word_forms': dict(word_forms or {}),
        'sources': [],
        'priority': '',
        'sources_approximate': [],
    }


class MergeManualExistingTermTests(SimpleTestCase):

    def test_синоним_дописывается_к_существующему_термину(self):
        terms = [_term('точка закрытия фирмы')]
        manual = [_term('точка закрытия фирмы', synonyms=['условие закрытия фирмы'])]
        stats = Command()._merge_manual(terms, manual)
        self.assertEqual(terms[0]['synonyms'], ['условие закрытия фирмы'])
        self.assertEqual(stats, {'existing_extended': 1, 'synonyms_added': 1,
                                 'new_terms': 0, 'new_term_synonyms': 0})

    def test_повторный_синоним_не_дублируется(self):
        terms = [_term('трансферт', synonyms=['трансферты'])]
        manual = [_term('трансферт', synonyms=['трансферты'])]
        Command()._merge_manual(terms, manual)
        self.assertEqual(terms[0]['synonyms'], ['трансферты'])


class MergeManualNewTermTests(SimpleTestCase):

    def test_неизвестный_канон_со_словоформами_становится_новым_термином(self):
        terms = [_term('квота')]
        manual = [_term('многозаводская фирма',
                        word_forms={'род': 'многозаводской фирмы'})]
        stats = Command()._merge_manual(terms, manual)
        self.assertEqual(len(terms), 2)
        self.assertEqual(terms[1]['canonical'], 'многозаводская фирма')
        self.assertEqual(stats['new_terms'], 1)


class MergeManualGuardTests(SimpleTestCase):
    """Правило Фазы 4 задания: опечатка в цели или коллизия синонима не
    должны молча испортить словарь — команда обязана упасть явно."""

    def test_неизвестный_канон_без_словоформ_считается_опечаткой_в_цели(self):
        """Запись без словоформ — это по конвенции добавка синонима к
        СУЩЕСТВУЮЩЕМУ термину. Если такого термина нет — это опечатка в
        целевом имени, а не новый термин («не выдумывай замену»)."""
        terms = [_term('точка закрытия фирмы')]
        manual = [_term('точка закрытии фирмы', synonyms=['условие закрытия фирмы'])]
        with self.assertRaises(CommandError):
            Command()._merge_manual(terms, manual)

    def test_коллизия_синонима_роняет_слияние_целиком(self):
        """Синоним, уже принадлежащий ДРУГОМУ термину, не должен уйти в
        JSON ни туда, ни сюда — весь `--check`/боевой прогон обязан упасть,
        а не смолчать про недетерминированный отбор в будущем."""
        terms = [
            _term('совершенные субституты'),
            _term('совершенные дополнения', synonyms=['совершенные субституты']),
        ]
        # т.е. кто-то по ошибке предложил тот же синоним ещё и другому термину
        manual = [_term('заменители', synonyms=['совершенные субституты'])]
        with self.assertRaises(CommandError):
            Command()._merge_manual(terms, manual)
        # исходные термины не тронуты частично — заменители синоним не получил
        self.assertNotIn('совершенные субституты',
                         [s for t in terms for s in t['synonyms']
                          if t['canonical'] == 'заменители'])

    def test_словарь_не_падает_целиком_если_надстройки_нет(self):
        """`econ_terms_manual.md` — необязательный файл: сборка без него
        (или до его появления) обязана продолжать работать по одному
        источнику, а не требовать надстройку как обязательную часть."""
        terms = [_term('квота')]
        stats = Command()._merge_manual(terms, [])
        self.assertEqual(terms, [_term('квота')])
        self.assertEqual(stats, {'existing_extended': 0, 'synonyms_added': 0,
                                 'new_terms': 0, 'new_term_synonyms': 0})
