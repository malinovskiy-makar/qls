# -*- coding: utf-8 -*-
"""Лексическая нога поиска: лемматизация pymorphy3 + BM25 (bm25s).

Решение от 19.08.2026: лексика живёт в Python, а не в PostgreSQL, и
слияние с плотным поиском идёт подобранным весом. Этот модуль — только
нога; к каталогу он не подключён, его гоняет офлайн-замер.

⚠️ `catalog/hybrid.py` НЕ ТРОГАЕТСЯ: на нём висит аварийная деградация
каталога, когда смысловой поиск лежит. Новая нога живёт рядом.

Что здесь стережётся:
  - словоформа находит задачу: «налоги» обязаны найти «налог». Без
    лемматизации BM25 на русском вырождается в поиск по точной форме, и
    вся нога теряет смысл;
  - «ё» и регистр не разводят одно слово на два;
  - в отпечаток входят тема, теги и понятия задачи, а не только условие:
    именно по ним работает разбор запроса моделью;
  - индекс переживает запись на диск и чтение обратно — прогон на 129
    запросах не должен пересобирать его каждый раз.
"""
from django.test import SimpleTestCase

from catalog import lexical_bm25 as lex


class LemmaTests(SimpleTestCase):
    def test_словоформа_сводится_к_начальной(self):
        self.assertEqual(lex.lemmatize('налоги'), lex.lemmatize('налог'))

    def test_падеж_не_разводит_слово(self):
        self.assertEqual(lex.lemmatize('кривой предложения'),
                         lex.lemmatize('кривая предложение'))

    def test_ё_и_регистр_не_разводят_слово(self):
        self.assertEqual(lex.lemmatize('Твёрдый'), lex.lemmatize('твердый'))

    def test_пунктуация_выбрасывается(self):
        self.assertEqual(lex.lemmatize('спрос, предложение!'),
                         lex.lemmatize('спрос предложение'))

    def test_числа_остаются(self):
        # «М1», «CO2», номера годов — часть смысла задачи, не мусор.
        self.assertIn('2020', lex.lemmatize('в 2020 году'))

    def test_однобуквенные_предлоги_не_попадают_в_отпечаток(self):
        self.assertNotIn('в', lex.lemmatize('в 2020 году'))

    def test_пустая_строка_даёт_пустой_список(self):
        self.assertEqual(lex.lemmatize(''), [])


class IndexTextTests(SimpleTestCase):
    def test_в_отпечаток_входят_все_шесть_частей(self):
        text = lex.index_text({
            'title': 'Налог на дуополию',
            'statement': 'Найдите равновесие',
            'parts': ['подпункт а', 'подпункт б'],
            'find': 'равновесную цену',
            'given': 'спрос P = 100 - Q',
            'topics': ['Теория отраслевых рынков'],
            'tags': ['дуополия'],
            'concepts': ['равновесие по Курно'],
        })
        for piece in ('Налог на дуополию', 'Найдите равновесие', 'подпункт а',
                      'подпункт б', 'равновесную цену', 'P = 100 - Q',
                      'Теория отраслевых рынков', 'дуополия',
                      'равновесие по Курно'):
            self.assertIn(piece, text)

    def test_пустые_поля_не_ломают_склейку(self):
        self.assertEqual(lex.index_text({'statement': 'только условие'}).strip(),
                         'только условие')


class SearchTests(SimpleTestCase):
    DOCS = {
        11: 'Введение потоварного налога на рынке дуополии Курно',
        12: 'Кривая Лоренца и коэффициент Джини по доходам населения',
        13: 'Банковский мультипликатор, норма резервирования, депозиты',
    }

    def index(self):
        ids = list(self.DOCS)
        return lex.build_index(ids, [self.DOCS[i] for i in ids])

    def test_словоформа_находит_задачу(self):
        # «налоги» в запросе, «налога» в тексте — без лемматизации ноль.
        hits = lex.search(self.index(), 'налоги дуополия', top_k=3)
        self.assertEqual(hits[0][0], 11)

    def test_выдача_не_длиннее_запрошенного(self):
        self.assertLessEqual(len(lex.search(self.index(), 'налог', top_k=2)), 2)

    def test_выдача_упорядочена_по_убыванию_веса(self):
        hits = lex.search(self.index(), 'депозиты резервирование', top_k=3)
        scores = [score for _, score in hits]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_запрос_без_общих_слов_не_выдаёт_ничего(self):
        self.assertEqual(lex.search(self.index(), 'фотосинтез хлорофилл',
                                    top_k=3), [])

    def test_индекс_переживает_запись_на_диск(self):
        import tempfile
        import os

        path = os.path.join(tempfile.mkdtemp(), 'idx')
        lex.save_index(self.index(), path)
        loaded = lex.load_index(path)
        self.assertEqual(lex.search(loaded, 'налоги дуополия', top_k=1)[0][0],
                         11)
