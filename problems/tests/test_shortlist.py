# -*- coding: utf-8 -*-
"""Лексический отбор шорт-листа словаря (Б1): problems/enrich/shortlist.py.

Три роли теста: детерминизм отбора, соблюдение жёстких правил про
обозначения (однобуквенные и неоднозначные не участвуют), и корректность
арифметики (документная частота, добор ядром, инварианты).
"""
import json
import os
import tempfile

from django.test import SimpleTestCase

from problems import econ_terms
from problems.enrich import shortlist


def _first_unambiguous_multiletter_notation():
    """Любое многобуквенное однозначное обозначение из реального словаря."""
    for symbol, slot in econ_terms.notation_index().items():
        if len(symbol) > 1 and slot.get('auto_normalize'):
            return symbol, slot['terms'][0]
    raise AssertionError('В словаре нет ни одного подходящего обозначения '
                         '— тест не может проверить правило')


def _first_ambiguous_multiletter_notation():
    for symbol, slot in econ_terms.notation_index().items():
        if len(symbol) > 1 and not slot.get('auto_normalize'):
            return symbol
    raise AssertionError('В словаре нет ни одного многобуквенного '
                         'неоднозначного обозначения — тест не может '
                         'проверить правило')


def _term_with_word_form():
    for term in econ_terms.terms():
        forms = term.get('word_forms') or {}
        for case, form in forms.items():
            if form and form.lower() != term['canonical'].lower():
                return term['canonical'], form
    raise AssertionError('В словаре нет термина со словоформой, отличной '
                         'от канонической формы')


class MatchedTermsTests(SimpleTestCase):
    """Что и как считается «встреченным термином» в тексте."""

    def test_каноническая_форма_находится(self):
        term = econ_terms.terms()[0]
        text = 'В условии упомянута %s без изменений.' % term['canonical']
        self.assertIn(term['canonical'], shortlist.matched_terms(text))

    def test_словоформа_находится(self):
        canonical, form = _term_with_word_form()
        text = 'Разговор про %s идёт весь абзац.' % form
        self.assertIn(canonical, shortlist.matched_terms(text))

    def test_подстрока_внутри_другого_слова_не_считается_совпадением(self):
        """Наивный `in` находил бы «рост» внутри «прирост» — здесь так нельзя."""
        found = shortlist.matched_terms('Экономический прирост измеряется в процентах.')
        self.assertNotIn('рост', found)

    def test_однобуквенное_обозначение_не_участвует_даже_если_однозначно(self):
        """`p`, `I`, `W`, `Π`... формально auto_normalize=True, но длина 1.

        Жёсткое правило Б1: однобуквенные не участвуют вообще, независимо
        от однозначности — без контекста абзаца это всё равно гадание.
        """
        single_letter_unambiguous = None
        for symbol, slot in econ_terms.notation_index().items():
            if len(symbol) == 1 and slot.get('auto_normalize'):
                single_letter_unambiguous = (symbol, slot['terms'][0])
                break
        if single_letter_unambiguous is None:
            self.skipTest('В текущем словаре нет однобуквенного '
                          'однозначного обозначения')
        symbol, canonical = single_letter_unambiguous
        text = 'Дано уравнение с переменной %s в правой части.' % symbol
        self.assertNotIn(canonical, shortlist.matched_terms(text))

    def test_многобуквенное_однозначное_обозначение_участвует(self):
        symbol, canonical = _first_unambiguous_multiletter_notation()
        text = 'Проверяем условие %s для найденной точки.' % symbol
        self.assertIn(canonical, shortlist.matched_terms(text))

    def test_многобуквенное_неоднозначное_обозначение_не_участвует(self):
        symbol = _first_ambiguous_multiletter_notation()
        mapped_terms = econ_terms.lookup_notation(symbol)['terms']
        text = 'В тексте встречается %s без пояснений.' % symbol
        found = shortlist.matched_terms(text)
        for canonical in mapped_terms:
            self.assertNotIn(canonical, found)

    # -----------------------------------------------------------------
    # Фаза A задания сессии 02.09: аппозитивный дефис («фирма-монополист»,
    # «страна-экспортёр») склеивает два самостоятельных слова в токенизаторе
    # в ОДИН токен (защита составных терминов вроде «Куна-Таккера») — и
    # словоформа внутри такого токена никогда не находится. Реальный случай
    # из боевого прогона: текст задачи #39 содержит «фирму-монополиста», а
    # matched_terms() термин «монополист» не находил вовсе.
    # -----------------------------------------------------------------

    def test_словоформа_после_аппозитивного_дефиса_находится(self):
        found = shortlist.matched_terms(
            'Рассмотрим фирму-монополиста Ф на рынке сахара.')
        self.assertIn('монополист', found)

    def test_составной_термин_словаря_с_дефисом_по_прежнему_находится(self):
        """Регрессия: защита «Куна-Таккера» не должна сломаться, пока мы
        чиним противоположный случай (два разных слова через дефис)."""
        found = shortlist.matched_terms(
            'Решение находится из условия Куна-Таккера для этой задачи.')
        self.assertIn('условие Куна-Таккера', found)

    def test_составной_термин_кобба_дугласа_находится(self):
        found = shortlist.matched_terms(
            'Дана производственная функция Кобба-Дугласа для двух ресурсов.')
        self.assertIn('производственная функция Кобба-Дугласа', found)

    def test_дефис_не_даёт_ложных_совпадений_из_обрезков(self):
        """Раскладка по дефису не должна путать бессмысленные обрезки
        («куна», «таккера» по отдельности) с настоящими терминами — здесь
        просто нечему найтись, кроме составного термина целиком."""
        found = shortlist.matched_terms('Куна-Таккера тут ни при чём.')
        # ни «куна», ни «таккера» сами по себе не термины словаря
        self.assertNotIn('куна', found)
        self.assertNotIn('таккера', found)

    # -----------------------------------------------------------------
    # Фаза A.3: STOP_TERMS («цена», «спрос», «функция»...) НЕ фильтруются
    # из буквального совпадения — они остаются самостоятельными
    # экономическими понятиями (рабочий пример A ядра вызова 1 прямо
    # просит найти «равновесие» и объявляет «спрос» законным
    # `econ_concepts` — см. `WorkedExamplesShortlistTests`). Проблемой была
    # не буквальная находка, а ДОБОР (`shortlist_for`), который вставлял
    # эти термины НАУГАД, когда их в тексте не было вовсе — фильтр стоит
    # только там, см. `test_добор_не_берёт_стоп_термины_даже_если_они_самые_частые`.
    # -----------------------------------------------------------------

    def test_буквальное_совпадение_стоп_термина_всё_ещё_находится(self):
        # именительный падеж — совпадает с канонической формой всегда,
        # винительный («цену») в словоформы термина «цена» не входит
        # (словарь покрывает род/дат/твор/предл, не все шесть падежей) —
        # это отдельный, ранее существовавший пробел, к этому тесту и к
        # аппозитивному дефису отношения не имеющий.
        found = shortlist.matched_terms(
            'Фирма-монополист устанавливает цена и объём выпуска на рынок.')
        self.assertIn('монополист', found)
        self.assertIn('фирма', found)
        self.assertIn('цена', found)
        self.assertIn('рынок', found)


class ShortlistForTests(SimpleTestCase):
    """shortlist_for(): сортировка, добор, детерминизм."""

    def test_детерминирован(self):
        text = 'Монополист выбирает цену и объём выпуска на рынке.'
        df = {}
        first = shortlist.shortlist_for(text, df=df)
        second = shortlist.shortlist_for(text, df=df)
        self.assertEqual(first, second)

    def test_редкие_термины_идут_первыми(self):
        found_a = econ_terms.terms()[100]['canonical']
        found_b = econ_terms.terms()[200]['canonical']
        text = '%s встречается рядом с %s в одном абзаце.' % (found_a, found_b)
        df = {found_a: 500, found_b: 5}
        result = shortlist.shortlist_for(text, df=df)
        self.assertLess(result.index(found_b), result.index(found_a))

    def test_шорт_лист_не_длиннее_k(self):
        many_terms = ' '.join(t['canonical'] for t in econ_terms.terms()[:60])
        result = shortlist.shortlist_for(many_terms, k=40, df={})
        self.assertLessEqual(len(result), 40)

    def test_меньше_пятнадцати_добирается_ядром_до_пятнадцати(self):
        result = shortlist.shortlist_for('текст без единого термина словаря', df={})
        self.assertEqual(len(result), shortlist.MIN_SHORTLIST)
        core = {t['canonical'] for t in econ_terms.terms()
                if t.get('priority') == shortlist.OLYMPIC_CORE_PRIORITY}
        self.assertTrue(set(result).issubset(core))

    def test_добор_не_дублирует_уже_найденные_термины(self):
        found = econ_terms.terms()[0]['canonical']
        text = 'В задаче встречается %s и больше ничего по словарю.' % found
        result = shortlist.shortlist_for(text, df={})
        self.assertEqual(len(result), len(set(result)))
        self.assertEqual(len(result), shortlist.MIN_SHORTLIST)

    def test_добор_берёт_самые_частые_термины_ядра(self):
        # STOP_TERMS не участвуют в доборе (Фаза A.3) — исключаем их и
        # здесь, иначе тест требовал бы от кода того самого поведения,
        # которое мы чиним.
        core_terms = [t['canonical'] for t in econ_terms.terms()
                      if t.get('priority') == shortlist.OLYMPIC_CORE_PRIORITY
                      and t['canonical'] not in shortlist.STOP_TERMS]
        df = {name: (i + 1) for i, name in enumerate(sorted(core_terms))}
        result = shortlist.shortlist_for('пусто', df=df)
        expected_top = sorted(core_terms, key=lambda n: (-df[n], n))[:15]
        self.assertEqual(result, expected_top)

    def test_добор_не_берёт_стоп_термины_даже_если_они_самые_частые(self):
        """Главная зубастость Фазы A: раньше добор сортировал ядро по
        УБЫВАНИЮ частоты — а самые частые термины ядра ровно и есть стоп-
        термины («цена», «спрос», «функция»...). Без фильтра тест краснеет."""
        result = shortlist.shortlist_for('текст без единого термина словаря', df={})
        self.assertFalse(set(result) & shortlist.STOP_TERMS,
                         'В доборе оказались стоп-термины: %s'
                         % (set(result) & shortlist.STOP_TERMS))

    def test_достаточно_найденного_добор_не_срабатывает(self):
        terms = econ_terms.terms()[:20]
        text = ' '.join(t['canonical'] for t in terms)
        df = {t['canonical']: 1 for t in terms}
        result = shortlist.shortlist_for(text, k=40, df=df)
        core = {t['canonical'] for t in econ_terms.terms()
                if t.get('priority') == shortlist.OLYMPIC_CORE_PRIORITY}
        found_names = {t['canonical'] for t in terms}
        extra = set(result) - found_names
        self.assertEqual(extra & core, extra)  # добор если и есть — только ядром
        self.assertGreaterEqual(len(result), 15)


class DocumentFrequencyTests(SimpleTestCase):
    """compute_document_frequencies(): счёт по документам, не по вхождениям."""

    def test_повтор_в_одном_документе_считается_один_раз(self):
        term = econ_terms.terms()[0]['canonical']
        text = '%s. И снова %s в этом же тексте.' % (term, term)
        expected_found = len(shortlist.matched_terms(text))
        df, counts = shortlist.compute_document_frequencies([text])
        self.assertEqual(df[term], 1)
        self.assertEqual(counts, [expected_found])

    def test_частота_растёт_с_числом_документов(self):
        term = econ_terms.terms()[0]['canonical']
        expected_found = len(shortlist.matched_terms(term))
        texts = [term, term, 'текст без терминов вообще']
        df, counts = shortlist.compute_document_frequencies(texts)
        self.assertEqual(df[term], 2)
        self.assertEqual(counts, [expected_found, expected_found, 0])

    def test_пустой_корпус_даёт_пустые_результаты(self):
        df, counts = shortlist.compute_document_frequencies([])
        self.assertEqual(df, {})
        self.assertEqual(counts, [])


class CorpusInvariantsTests(SimpleTestCase):

    def test_медиана_нечётного_набора(self):
        stats = shortlist.corpus_invariants([1, 5, 3])
        self.assertEqual(stats['median'], 3)

    def test_медиана_чётного_набора(self):
        stats = shortlist.corpus_invariants([1, 2, 3, 4])
        self.assertEqual(stats['median'], 2.5)

    def test_доли_ниже_15_и_выше_40(self):
        counts = [5, 10, 20, 41, 50]
        stats = shortlist.corpus_invariants(counts)
        self.assertAlmostEqual(stats['share_below_15'], 2 / 5)
        self.assertAlmostEqual(stats['share_above_40'], 2 / 5)

    def test_пустой_список_не_падает(self):
        stats = shortlist.corpus_invariants([])
        self.assertEqual(stats['median'], 0)


class DfCacheTests(SimpleTestCase):

    def test_запись_и_чтение_кэша_даёт_то_же_самое(self):
        df = {'абсолютная величина': 12, 'налог': 500}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'df.json')
            shortlist.save_df_cache(df, path=path)
            loaded = shortlist.load_df_cache(path=path)
        self.assertEqual(loaded, df)

    def test_кэш_на_диске_читаемый_json(self):
        df = {'налог': 1}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'df.json')
            shortlist.save_df_cache(df, path=path)
            with open(path, encoding='utf-8') as fh:
                raw = json.load(fh)
        self.assertEqual(raw, df)


class ManualDictionaryAdditionsTests(SimpleTestCase):
    """Ручные добавки словаря (задание владельца, 2026-09-03): зубастость.

    Черновик-предложение (`reports/enrich_pilot/dict_candidates.md`) регулярно
    склеивал разные понятия, иногда противоположные (например,
    «совершенные дополнения» -> «совершенные субституты» — это антонимы).
    Каждый тест здесь красит в красный ровно ту ошибку, которую владелец
    указал явно, а не абстрактную «работает ли словарь вообще».
    """

    def test_условие_закрытия_фирмы_находит_точку_закрытия_фирмы(self):
        found = shortlist.matched_terms(
            'Условие закрытия фирмы в коротком периоде выполняется, когда '
            'цена ниже средних переменных издержек.')
        self.assertIn('точка закрытия фирмы', found)

    def test_совершенные_дополнения_не_путаются_с_субститутами(self):
        """Черновик предлагал «совершенные дополнения» синонимом «совершенных
        субститутов» — противоположные понятия в теории потребления."""
        found = shortlist.matched_terms(
            'У потребителя совершенные дополнения: левый и правый ботинок.')
        self.assertNotIn('совершенные субституты', found)

    def test_новое_понятие_находится_в_косвенном_падеже(self):
        found = shortlist.matched_terms(
            'В многозаводской фирме выпуск распределяется между заводами '
            'так, чтобы предельные издержки совпадали.')
        self.assertIn('многозаводская фирма', found)

    def test_новое_понятие_находится_в_косвенном_падеже_аккордный_налог(self):
        found = shortlist.matched_terms(
            'При аккордном налоге сумма выплаты не зависит от объёма '
            'производства фирмы.')
        self.assertIn('аккордный налог', found)

    def test_добавленный_синоним_ведёт_к_правильному_канону(self):
        found = shortlist.matched_terms(
            'Специализация работников повышает выпуск в расчёте на час труда.')
        self.assertIn('разделение труда', found)
        self.assertNotIn('специализация', found)  # это не отдельный термин


class DashNormalizationTests(SimpleTestCase):
    """Фаза 0 задания сессии 03.09.2026: тире всех видов — один знак.

    Токенизатор понимал дефис `-` и короткое тире `–`, но не длинное `—`.
    Длинное тире стоит в именах моделей и теорем (Манделла—Флеминга,
    Столпера—Сэмюэльсона, Хекшера—Олина, Блэка—Шоулза), и у 13 из 15
    таких терминов словаря дефисного варианта НЕТ вовсе — значит, найтись
    в тексте они не могли никогда, каким бы знаком автор задачи их ни
    записал.

    Сломать нормализацию (убрать знак из `_DASH_TRANSLATION` или перестать
    строить ключи фраз через токенизатор) — и оба направления краснеют.
    """

    def test_термин_с_длинным_тире_находится_в_тексте_с_дефисом(self):
        found = shortlist.matched_terms(
            'В открытой экономике работает модель Манделла-Флеминга.')
        self.assertIn('модель Манделла—Флеминга', found)

    def test_термин_с_длинным_тире_находится_в_тексте_с_длинным_тире(self):
        # именительный падеж: винительный («теорему») в словоформы словаря
        # не входит — он не покрыт ни у одного термина, это отдельный
        # известный пробел, к тире отношения не имеющий.
        found = shortlist.matched_terms(
            'Здесь работает теорема Хекшера—Олина для двух стран.')
        self.assertIn('теорема Хекшера—Олина', found)

    def test_термин_с_дефисом_находится_в_тексте_с_длинным_тире(self):
        """Обратное направление: словарь пишет через дефис, автор задачи —
        через длинное тире."""
        found = shortlist.matched_terms(
            'Решение находится из условия Куна—Таккера для этой задачи.')
        self.assertIn('условие Куна-Таккера', found)

    def test_кобба_дугласа_находится_через_длинное_тире(self):
        found = shortlist.matched_terms(
            'Дана производственная функция Кобба—Дугласа для двух ресурсов.')
        self.assertIn('производственная функция Кобба-Дугласа', found)

    def test_короткое_тире_тоже_нормализуется(self):
        found = shortlist.matched_terms(
            'Оценим концентрацию через индекс Херфиндаля–Хиршмана.')
        self.assertIn('индекс Херфиндаля—Хиршмана', found)

    def test_термин_в_кавычках_с_тире_находится(self):
        """«цена—прибыль» в словаре записан с кавычками-ёлочками: ключ,
        построенный дословно, не совпал бы с текстом никогда — кавычки
        токенизатор выбрасывает."""
        found = shortlist.matched_terms(
            'Коэффициент цена-прибыль равен 12 для этой компании.')
        self.assertIn('коэффициент «цена—прибыль»', found)

    # -----------------------------------------------------------------
    # Нормализация НЕ склеивает разные термины: она меняет только знак,
    # а не границы слов. Требование задания — проверить отдельно.
    # -----------------------------------------------------------------

    def test_нормализация_не_склеивает_разные_термины(self):
        """«Куна-Таккера» остаётся одним составным термином, а обрезки
        «куна»/«таккера» терминами не становятся."""
        found = shortlist.matched_terms('Куна—Таккера тут ни при чём.')
        self.assertNotIn('куна', found)
        self.assertNotIn('таккера', found)

    def test_нормализация_не_путает_соседние_составные_термины(self):
        """Два РАЗНЫХ составных термина в одном тексте остаются разными:
        нормализация тире не должна дать совпадение «поперёк» границы."""
        found = shortlist.matched_terms(
            'Сравним товары-заменители и дополняющие товары на рынке.')
        self.assertIn('взаимозаменяемые товары', found)   # синоним «товары-заменители»
        self.assertNotIn('модель Манделла—Флеминга', found)

    def test_аппозитивный_дефис_через_длинное_тире_тоже_разрезается(self):
        """Регрессия на `split_hyphens`: «фирму—монополиста» через длинное
        тире обязана вести к «монополисту» так же, как через дефис."""
        found = shortlist.matched_terms(
            'Рассмотрим фирму—монополиста Ф на рынке сахара.')
        self.assertIn('монополист', found)

    def test_пунктуационное_тире_не_создаёт_ложных_совпадений(self):
        """Длинное тире между пробелами — обычная русская пунктуация, а не
        часть слова: склеивать соседние слова в один токен оно не должно."""
        found = shortlist.matched_terms(
            'Цена — это денежное выражение стоимости товара.')
        self.assertIn('цена', found)
        self.assertIn('товар', found)
