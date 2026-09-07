# -*- coding: utf-8 -*-
"""Словарь терминов олимпиадной экономики (С6): целостность и лемматизация.

Словарь — не просто справочник: это закрытый список понятий для разметки
корпуса, нормализатор синонимов и аббревиатур для лексического поиска и
контрольный набор для проверки морфологии. Каждую из трёх ролей здесь
сторожит свой тест.
"""
import re
import unittest

from django.test import SimpleTestCase

from problems import econ_terms

try:
    import pymorphy3
except ImportError:  # pragma: no cover - зависит от окружения
    pymorphy3 = None

# Слова для морфологии: латиница и кириллица, без цифр и знаков формул.
RE_WORD = re.compile(r'[А-Яа-яЁёA-Za-z]+')

# Символы, у которых в словаре заведомо больше одного значения. Список не
# полный (их 56) — здесь те, что названы в самом словаре как опасные.
AMBIGUOUS_SYMBOLS = ('P', 'S', 'C', 'AC', 'AP', 'AR', 'π')


class DictionaryShapeTests(SimpleTestCase):
    """Форма словаря: числа, схема записи, разделы."""

    def test_числа_источника_сходятся_с_заявленными_в_нём(self):
        """Разобранный ИСТОЧНИК обязан совпасть с тем, что он пишет о себе
        сам — до ручных добавок (`econ_terms_manual.md`), у которых
        собственных заявленных чисел нет и быть не может.

        Молчаливо недоразобранный словарь выглядел бы как рабочий: поиск
        просто не находил бы часть терминов, и никто бы не понял почему.
        """
        meta = econ_terms.load()['meta']
        source = meta['source_counts']
        declared = meta['declared_counts']
        fixes = sum(len(v) for v in meta['known_fixes_applied'].values())
        self.assertEqual(source['terms'], declared['terms'])
        self.assertEqual(source['ru_aliases'], declared['ru_aliases'])
        self.assertEqual(source['english'], declared['english'])
        # Обозначений на наши починки больше — см. KNOWN_FIXES в команде сборки.
        self.assertEqual(source['notations'], declared['notations'] + fixes)

    def test_итоговые_числа_учитывают_ручные_добавки(self):
        """Ручная надстройка (задание владельца, 2026-09-03) сливается ПОСЛЕ
        сверки источника — итог обязан быть суммой источника и добавок,
        иначе слияние тихо теряет или задваивает записи."""
        meta = econ_terms.load()['meta']
        counts = meta['actual_counts']
        manual = meta['manual_additions']
        self.assertEqual(counts['terms'],
                         meta['source_counts']['terms'] + manual['new_terms'])
        self.assertEqual(counts['ru_aliases'],
                         meta['source_counts']['ru_aliases']
                         + manual['synonyms_added']
                         + manual['new_term_synonyms'])

    def test_разделов_на_один_больше_источника_из_за_ручной_надстройки(self):
        # 32 раздела у источника + 1 «Новые понятия» из econ_terms_manual.md.
        self.assertEqual(counts_sections(), 33)

    def test_у_каждого_термина_есть_раздел(self):
        without = [t['canonical'] for t in econ_terms.terms() if not t['section']]
        self.assertEqual(without, [], 'Термины без раздела: %s' % without[:10])

    def test_канонические_термины_уникальны(self):
        seen = {}
        duplicates = []
        for term in econ_terms.terms():
            name = term['canonical']
            if name in seen:
                duplicates.append(name)
            seen[name] = True
        self.assertEqual(duplicates, [], 'Дубли терминов: %s' % duplicates[:10])


def counts_sections():
    return len({t['section'] for t in econ_terms.terms()})


class NotationIndexTests(SimpleTestCase):
    """Обратный индекс обозначений и правило неоднозначности."""

    def test_неоднозначные_символы_не_нормализуются_автоматически(self):
        """⚠️ Правило контринтуитивно, поэтому и стоит тестом.

        Кажется, что чем больше сопоставлений «символ -> термин», тем лучше
        поиск. На самом деле однозначная замена без контекста УХУДШАЕТ
        качество: `P` — это цена, уровень цен и опцион пут одновременно.
        Предупреждение исходит от самого словаря.
        """
        for symbol in AMBIGUOUS_SYMBOLS:
            with self.subTest(symbol=symbol):
                slot = econ_terms.lookup_notation(symbol)
                self.assertIsNotNone(slot, 'Символ %r пропал из индекса' % symbol)
                self.assertGreater(
                    len(slot['terms']), 1,
                    '%r перестал быть неоднозначным — проверьте словарь' % symbol)
                self.assertFalse(
                    slot['auto_normalize'],
                    '%r помечен как автоматически нормализуемый, а за ним %d '
                    'разных термина: %s' % (symbol, len(slot['terms']),
                                            '; '.join(slot['terms'])))
                self.assertIsNone(econ_terms.normalizable_notation(symbol))

    def test_однозначный_символ_нормализуется(self):
        """Обратная сторона: MC ведёт ровно к одному термину."""
        self.assertEqual(econ_terms.normalizable_notation('MC'),
                         'предельные издержки')

    def test_флаг_автонормализации_согласован_с_числом_терминов(self):
        broken = [
            symbol for symbol, slot in econ_terms.notation_index().items()
            if slot['auto_normalize'] != (len(slot['terms']) == 1)
        ]
        self.assertEqual(broken, [], 'Флаг разошёлся с числом терминов: %s'
                         % broken[:10])


class AdAsGapTests(SimpleTestCase):
    """Закрытый пропуск словаря: AD–AS через ен-тире.

    ⚠️ ЧТО ИМЕННО БЫЛО ПРОПУЩЕНО. Термин «модель AD–AS» в словаре есть, и в
    его обозначениях стоит `AD-AS` через ОБЫЧНЫЙ ДЕФИС. Вариант через
    ЕН-ТИРЕ `AD–AS` встречался только в заголовке раздела и в English-поле,
    то есть в обратный индекс не попадал. Сам словарь отмечает это в разделе
    контроля качества как `MISSING: AD–AS`.

    Почему это важно: в условиях задач встречаются ОБА начертания — авторы
    набирают то дефис, то тире, а Word меняет одно на другое автозаменой.
    Нормализация видела бы половину случаев и молчала бы про вторую.
    """

    EN_DASH = 'AD–AS'   # U+2013
    HYPHEN = 'AD-AS'    # U+002D

    def test_оба_начертания_ведут_к_одному_термину(self):
        self.assertNotEqual(self.EN_DASH, self.HYPHEN,
                            'Тест потерял смысл: начертания стали одинаковыми')
        for symbol in (self.EN_DASH, self.HYPHEN):
            with self.subTest(symbol=symbol):
                slot = econ_terms.lookup_notation(symbol)
                self.assertIsNotNone(
                    slot,
                    'Обозначение %r пропало из индекса. Это тот самый пропуск '
                    'MISSING: AD–AS — чинится в KNOWN_FIXES команды '
                    'build_econ_terms, а не правкой источника.' % symbol)
                self.assertEqual(slot['terms'], ['модель AD–AS'])

    def test_термин_модель_ad_as_существует(self):
        self.assertIsNotNone(econ_terms.get('модель AD–AS'))


@unittest.skipIf(pymorphy3 is None,
                 'pymorphy3 не установлен (requirements/dev.in)')
class LemmatizationControlSetTests(SimpleTestCase):
    """Словоформы словаря как контрольный набор для морфологии.

    Словарь даёт формы в четырёх падежах — это готовый эталон: правильный
    разбор обязан свести словоформу и канонический термин к одним и тем же
    леммам. Если морфология сломается (сменится версия pymorphy3, поедут
    словари), тест покраснеет здесь, а не в виде «поиск стал хуже».
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Разбор тяжёлый на старте (~секунда) — один анализатор на класс.
        cls.morph = pymorphy3.MorphAnalyzer()

    def lemma_options(self, word):
        """ВСЕ варианты нормальной формы слова, а не только первый."""
        return {p.normal_form for p in self.morph.parse(word)}

    def matches(self, canonical, form):
        """Совпадают ли термин и словоформа хотя бы по одному разбору."""
        words_canonical = RE_WORD.findall(canonical)
        words_form = RE_WORD.findall(form)
        if len(words_canonical) != len(words_form):
            return False
        return all(self.lemma_options(a) & self.lemma_options(b)
                   for a, b in zip(words_canonical, words_form))

    def test_каждая_словоформа_сводится_к_своему_термину(self):
        failures = []
        total = 0
        for canonical, case, form in econ_terms.word_form_pairs():
            total += 1
            if not self.matches(canonical, form):
                failures.append('%s | %s | %s' % (canonical, case, form))

        self.assertGreater(total, 7000,
                           'Словоформ стало подозрительно мало: %d' % total)
        self.assertEqual(
            failures, [],
            'Морфология не свела %d из %d словоформ к их каноническому '
            'термину. Это значит, что запрос в косвенном падеже не найдёт '
            'задачу, где термин стоит в именительном. Первые случаи:\n%s'
            % (len(failures), total, '\n'.join(failures[:15])))

    def test_наивный_разбор_по_первому_варианту_недостаточен(self):
        """⚠️ ЗАЩИТА ОТ «УПРОЩЕНИЯ», КОТОРОЕ ВЫГЛЯДИТ БЕЗОБИДНО.

        Напрашивается взять `parse(word)[0].normal_form` — самый вероятный
        разбор — и не возиться с множествами. Замер по этому же словарю
        22.08.2026: наивный способ не сводит 184 словоформы из 7 057, это
        2,61 % МОЛЧАЛИВЫХ промахов поиска. Ломается на омонимии: «среднее»
        разбирается и как прилагательное, и как существительное, «график»
        спорит с «графикой», «корень» — с «корном».

        Тест намеренно утверждает, что наивный способ ПЛОХ: если однажды он
        станет достаточным, тест покраснеет и заставит перечитать это место,
        а не тихо разрешит упрощение.
        """
        naive_failures = 0
        total = 0
        for canonical, _case, form in econ_terms.word_form_pairs():
            total += 1
            naive_canonical = tuple(self.morph.parse(w)[0].normal_form
                                    for w in RE_WORD.findall(canonical))
            naive_form = tuple(self.morph.parse(w)[0].normal_form
                               for w in RE_WORD.findall(form))
            if naive_canonical != naive_form:
                naive_failures += 1

        self.assertGreater(
            naive_failures, 0,
            'Наивный разбор по первому варианту вдруг стал безошибочным на '
            '%d словоформах. Возможно, обновились словари pymorphy3. Тогда '
            'проверьте руками и перепишите это место — но НЕ упрощайте '
            'matches() до parse()[0], пока не убедились на свежем замере.'
            % total)
