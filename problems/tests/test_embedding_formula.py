# -*- coding: utf-8 -*-
"""`problems/embedding_formula.py` — спецификация формулы отпечатка данными.

Главный тест файла — `V1ByteForByteTests`: спецификация `v1` обязана
воспроизводить `problem_to_text` СИМВОЛ В СИМВОЛ на реальных задачах банка.
Не «похоже» и не «эквивалентно». Это единственная гарантия, что сравнение
v1 против v2 честное, а не сравнение v2 с новой опечаткой.
"""
import re

from django.test import TestCase, tag

from problems.embedding_formula import (
    BLOCKS, CONCEPT_DROP_REASONS, PREFETCH, SPECS, build_text, clean_concepts,
)
from problems.management.commands.build_embeddings import problem_to_text
from problems.models import (
    EconConcept, Feature, Hint, OlympiadRef, Problem, ProblemFeature,
    ProblemPart, Skill, Tag, Topic,
)


class SpecsShapeTests(TestCase):

    def test_блоков_ровно_девятнадцать(self):
        self.assertEqual(len(BLOCKS), 19)

    def test_боевая_спецификация_v2_это_шестнадцать_блоков(self):
        self.assertEqual(len(SPECS['v2'].blocks), 16)
        for выпавший in ('blurb', 'plot', 'skills'):
            self.assertNotIn(выпавший, SPECS['v2'].blocks)

    def test_порядок_v2_зафиксирован_владельцем_07_09(self):
        self.assertEqual(SPECS['v2'].blocks, (
            'topics', 'tags', 'concepts', 'queries', 'find', 'given',
            'solution', 'statement', 'parts', 'hints', 'features', 'kind',
            'olympiad', 'difficulty_note', 'difficulty', 'title'))

    def test_ответ_не_входит_ни_в_один_вариант(self):
        """Медианная длина ответа в банке — 2 символа, то есть это число.
        «Ответ: 6» не помогает найти задачу ничем."""
        self.assertNotIn('answer', BLOCKS)

    def test_версии_уникальны(self):
        версии = [s.version for s in SPECS.values()]
        self.assertEqual(len(set(версии)), len(версии))

    def test_вариантов_семнадцать(self):
        self.assertEqual(len(SPECS), 17)

    def test_meta_first_отличается_от_v2_только_порядком(self):
        """Пара `v2` ↔ `v2_meta_first` — единственная проверка порядка: если
        состав или бюджеты разойдутся, разность между ними перестанет быть
        ценой порядка."""
        v2, mf = SPECS['v2'], SPECS['v2_meta_first']
        self.assertEqual(sorted(v2.blocks), sorted(mf.blocks))
        self.assertEqual(v2.budgets, mf.budgets)
        self.assertEqual(v2.options, mf.options)
        self.assertNotEqual(v2.blocks, mf.blocks)

    def test_focus_repeat_повторяет_ровно_пятёрку_упора(self):
        обычный, повтор = SPECS['v2_focus'].blocks, SPECS['v2_focus_repeat'].blocks
        self.assertEqual(повтор[:len(обычный)], обычный)
        self.assertEqual(повтор[len(обычный):],
                         ('topics', 'tags', 'concepts', 'find', 'given'))

    def test_неизвестный_блок_это_ошибка_а_не_молчаливый_пропуск(self):
        p = Problem.objects.create(statement='Задача.')
        плохая = SPECS['v2'].__class__(name='x', version=999,
                                       blocks=('нет-такого',), budgets={})
        with self.assertRaises(KeyError):
            build_text(p, плохая)


class CleanConceptsTests(TestCase):
    """Чистка понятий (раздел 3.1.1). Одинаковая для обоих источников:
    контринтуитивно, но общие слова сидят не в offlist, а в словарных
    понятиях — «цена» стоит у 18,5 % банка и не различает ничего."""

    def test_короткие_и_только_знаки_выбрасываются(self):
        stats = {}
        self.assertEqual(clean_concepts(['ВВП', 'ЦБ', '—', '...'], stats), ['ВВП'])
        self.assertEqual(sorted(stats[CONCEPT_DROP_REASONS[0]]),
                         sorted(['ЦБ', '—', '...']))

    def test_однобуквенное_обозначение_ловится_правилом_длины(self):
        """`P` без контекста — цена, уровень цен и put-опцион разом. Ловится
        первым же правилом (короче 3 символов), до правила обозначений."""
        stats = {}
        self.assertEqual(clean_concepts(['P', 'π', 'спрос на деньги'], stats),
                         ['спрос на деньги'])
        self.assertEqual(sorted(stats[CONCEPT_DROP_REASONS[0]]), sorted(['P', 'π']))

    def test_многобуквенное_обозначение_выбрасывается(self):
        """Правило 2 работает там, где правило длины бессильно: `AVC`, `MC`,
        `NPV` — обозначения, а не слова."""
        stats = {}
        оставлено = clean_concepts(['AVC', 'MC', 'NPV', 'спрос на деньги'], stats)
        self.assertEqual(оставлено, ['спрос на деньги'])
        self.assertEqual(sorted(stats[CONCEPT_DROP_REASONS[1]]), ['AVC', 'NPV'])
        # 'MC' короче трёх символов — его ловит правило длины, не это.
        self.assertEqual(stats[CONCEPT_DROP_REASONS[0]], ['MC'])

    def test_кириллическая_аббревиатура_остаётся(self):
        """«ВВП» и «ППС» — слова русского языка, а не обозначения."""
        self.assertEqual(clean_concepts(['ВВП', 'ППС']), ['ВВП', 'ППС'])

    def test_стоп_лист_выбрасывает_общие_слова(self):
        stats = {}
        self.assertEqual(clean_concepts(['выбор', 'Оценка', 'кривая Лоренца'], stats),
                         ['кривая Лоренца'])
        self.assertEqual(len(stats[CONCEPT_DROP_REASONS[2]]), 2)

    def test_термин_с_цифрой_внутри_остаётся(self):
        """Их всего 15 и все законные."""
        термины = ['денежный агрегат М1', 'правило 70',
                   'выбросы CO2 на душу населения']
        self.assertEqual(clean_concepts(термины), sorted(термины))

    def test_дубли_снимаются_и_порядок_детерминирован(self):
        self.assertEqual(clean_concepts(['спрос', 'предложение', 'спрос']),
                         ['предложение', 'спрос'])


def _make_problem(**kwargs):
    поля = dict(statement='Фирма выпускает товар на конкурентном рынке.',
                title='', ai_blurb='')
    поля.update(kwargs)
    return Problem.objects.create(**поля)


class V1ByteForByteTests(TestCase):
    """⚠️ Главный тест модуля. Выборка синтетическая, но покрывает ровно те
    случаи, на которых склейка v1 расходится незаметно: задачи с
    подпунктами, без темы, без blurb, с пустым `title`, с пустым условием
    (в v1 условие добавляется ДАЖЕ ПУСТЫМ и даёт двойной пробел).

    Прогон по 2 000+ реальных задач банка — отдельной командой
    `embeddings_export_texts --self-check`: в тестовой базе задач банка нет.
    """

    @classmethod
    def setUpTestData(cls):
        # ⚠️ `Topic.slug` — unique и blank=True: две темы с пустым слагом
        # роняют создание по UNIQUE. Слаги задаём явно.
        тема = Topic.objects.create(name='Микроэкономика', slug='micro',
                                    is_canonical=True)
        тест = Topic.objects.create(name='Тест', slug='test-topic',
                                    is_canonical=True)
        листок = Topic.objects.create(name='Best of тачки', slug='listok',
                                      is_canonical=False)
        навык = Skill.objects.create(name='Оптимизация')
        канон = sorted(__import__(
            'problems.embedding_config', fromlist=['x']).CANONICAL_TAG_NAMES)
        # `Tag.slug` — та же ловушка unique+blank, что у `Topic.slug`.
        стар1 = Tag.objects.create(name=канон[0], slug='t1', kind='canonical')
        стар2 = Tag.objects.create(name=канон[1], slug='t2', kind='canonical')
        новый = Tag.objects.create(name='тег-которого-нет-в-старом-списке',
                                   slug='t3', kind='canonical')
        мусор = Tag.objects.create(name='Homework', slug='t4', kind='legacy')

        cls.случаи = []

        обычная = _make_problem(title='Пекарня Ивана',
                                ai_blurb='Фирма максимизирует прибыль.')
        обычная.topics.add(тема, тест, листок)
        обычная.skills.add(навык)
        обычная.tags.add(стар1, стар2, новый, мусор)
        cls.случаи.append(обычная)

        с_подпунктами = _make_problem(title='Две фирмы')
        for i in range(4):
            ProblemPart.objects.create(problem=с_подпунктами, order=i,
                                       label='%d)' % i,
                                       statement='Подпункт %d. ' % i + 'т' * 200)
        с_подпунктами.topics.add(тема, листок)
        cls.случаи.append(с_подпунктами)

        cls.случаи.append(_make_problem(title='', ai_blurb=''))
        cls.случаи.append(_make_problem(title='Без темы и без тегов',
                                        ai_blurb='Суть.' * 200))
        cls.случаи.append(_make_problem(statement=''))
        cls.случаи.append(_make_problem(statement='у' * 2000, title='Длинное'))

        только_новые = _make_problem(title='Только новая таксономия')
        только_новые.tags.add(новый, мусор)
        cls.случаи.append(только_новые)

    def test_v1_совпадает_с_problem_to_text_символ_в_символ(self):
        for задача in self.случаи:
            задача.refresh_from_db()
            with self.subTest(problem=задача.pk):
                self.assertEqual(build_text(задача, SPECS['v1']),
                                 problem_to_text(задача))

    def test_v2_берёт_только_канонические_темы(self):
        """Тем в банке 865, канонических 29; остальные — импортные названия
        листков («Best of тачки»), которые искать по ним никто не будет."""
        обычная = self.случаи[0]
        self.assertIn('Best of тачки', build_text(обычная, SPECS['v1']))
        self.assertNotIn('Best of тачки', build_text(обычная, SPECS['v2']))
        self.assertIn('Темы: Микроэкономика.', build_text(обычная, SPECS['v2']))

    def test_блок_тегов_v1_действительно_мёртв_на_новой_таксономии(self):
        """Замер, ради которого v2 берёт теги по `Tag.kind`: старый список —
        222 имени времён Батча 1, а в банке 344 канонических тега с другими
        названиями. Блок «Теги» v1 срабатывает у 108 задач из 41 307."""
        только_новые = self.случаи[-1]
        self.assertNotIn('Теги:', build_text(только_новые, SPECS['v1']))
        self.assertIn('Теги: тег-которого-нет-в-старом-списке.',
                      build_text(только_новые, SPECS['v2']))


class V2BlocksTests(TestCase):

    def setUp(self):
        self.p = _make_problem(
            title='Старый обрубок из первой строки условия',
            title_candidate='Пекарня Ивана',
            given='Функция спроса линейная, издержки постоянные',
            find='Равновесную цену и объём',
            solution='Приравниваем предельную выручку к предельным издержкам, '
                     'получаем 12 единиц.',
            plot='Монополист на двух рынках.',
            ai_blurb='Краткая суть.',
            difficulty=3,
            difficulty_note='Требуется два шага и проверка условия закрытия.',
            problem_type='несколько_подвопросов',
            task_nature='расчётная',
            search_queries=['равновесие монополиста', 'предельная выручка'],
            concepts_offlist=['условие закрытия фирмы', 'P', 'выбор'],
        )
        EconConcept.objects.create(canonical='предельные издержки')
        self.p.econ_concepts.add(EconConcept.objects.get(canonical='предельные издержки'))
        модельная = Feature.objects.create(key='параметры', label='Параметры',
                                           counted_by='model', order=1)
        кодовая = Feature.objects.create(key='многопунктовая',
                                         label='Многопунктовая',
                                         counted_by='code', order=2)
        ProblemFeature.objects.create(problem=self.p, feature=модельная, source='model')
        ProblemFeature.objects.create(problem=self.p, feature=кодовая, source='code')
        Hint.objects.create(problem=self.p, order=1, text='Начните со спроса.')
        Hint.objects.create(problem=self.p, order=2, text='Сравните с ценой.')
        OlympiadRef.objects.create(
            problem=self.p, source_site='solvehub', olympiad_slug='vsosh',
            olympiad_name='Всероссийская олимпиада школьников', stage='региональный',
            year=2025, event_id='e1', record_id='r1',
            official_url='https://solvehub.example/задача/1')

    def текст(self, имя='v2'):
        return build_text(Problem.objects.get(pk=self.p.pk), SPECS[имя])

    def test_заголовок_берёт_кандидата_а_не_обрубок(self):
        текст = self.текст()
        self.assertIn('Заголовок: Пекарня Ивана.', текст)
        self.assertNotIn('Старый обрубок', текст)

    def test_сложность_пишется_словом_а_не_цифрой(self):
        """Голая цифра модели ничего не говорит и рискует смешаться с
        числами условия."""
        self.assertIn('Сложность: средняя.', self.текст())

    def test_пустая_сложность_не_даёт_блока(self):
        Problem.objects.filter(pk=self.p.pk).update(difficulty=None)
        self.assertNotIn('Сложность:', self.текст())

    def test_понятия_склеивают_словарь_и_offlist_и_чистятся(self):
        текст = self.текст()
        self.assertIn('Понятия: предельные издержки, условие закрытия фирмы.',
                      текст)
        self.assertNotIn(', P,', текст)     # голое обозначение
        self.assertNotIn('выбор', текст)    # стоп-лист

    def test_no_offlist_оставляет_только_словарные(self):
        self.assertIn('Понятия: предельные издержки.', self.текст('v2_no_offlist'))

    def test_особенности_по_label_а_не_по_key(self):
        текст = self.текст()
        self.assertIn('Особенности: Многопунктовая, Параметры.', текст)
        self.assertNotIn('многопунктовая', текст)

    def test_model_features_only_убирает_кодовые(self):
        self.assertIn('Особенности: Параметры.', self.текст('v2_no_code_features'))

    def test_олимпиада_без_ссылки_на_агрегатора(self):
        текст = self.текст()
        self.assertIn('Олимпиада: Всероссийская олимпиада школьников, '
                      'региональный, 2025.', текст)
        self.assertNotIn('solvehub', текст)
        self.assertNotIn('http', текст)

    def test_решение_входит_в_v2_и_выпадает_в_v2_no_solution(self):
        self.assertIn('Решение: Приравниваем', self.текст())
        self.assertNotIn('Решение:', self.текст('v2_no_solution'))

    def test_сюжет_и_blurb_в_v2_не_входят(self):
        текст = self.текст()
        self.assertNotIn('Сюжет:', текст)
        self.assertNotIn('Краткая суть', текст)

    def test_v2_plus_blurb_возвращает_blurb_четвёртым(self):
        self.assertIn('Краткая суть.', self.текст('v2_plus_blurb'))

    def test_обезличивание_чисел_только_в_отпечатке(self):
        текст = self.текст('v2_masked_numbers')
        self.assertIn('получаем # единиц', текст)
        self.assertEqual(Problem.objects.get(pk=self.p.pk).solution,
                         self.p.solution)

    def test_обезличивание_не_трогает_метаданные(self):
        """Год олимпиады и сложность — не числа условия; маска их не касается,
        иначе вариант мерил бы не то, что заявляет."""
        текст = self.текст('v2_masked_numbers')
        self.assertIn('2025', текст)
        self.assertIn('Сложность: средняя.', текст)

    def test_запросы_склеиваются_через_точку_с_запятой(self):
        self.assertIn('Запросы: равновесие монополиста; предельная выручка.',
                      self.текст())

    def test_focus_режет_число_запросов(self):
        Problem.objects.filter(pk=self.p.pk).update(
            search_queries=['раз', 'два', 'три', 'четыре', 'пять', 'шесть'])
        текст = self.текст('v2_focus')
        self.assertIn('Запросы: раз; два; три; четыре.', текст)
        self.assertNotIn('пять', текст)

    def test_no_queries_убирает_блок_целиком(self):
        self.assertNotIn('Запросы:', self.текст('v2_no_queries'))

    def test_пустые_блоки_не_добавляются(self):
        пустая = _make_problem(statement='Короткое условие.')
        текст = build_text(пустая, SPECS['v2'])
        for метка in ('Темы:', 'Теги:', 'Понятия:', 'Запросы:', 'Найти:',
                      'Дано:', 'Решение:', 'Подпункты:', 'Подсказки:',
                      'Особенности:', 'Олимпиада:', 'Сложность:'):
            self.assertNotIn(метка, текст)
        self.assertNotIn('  ', текст)

    def test_бюджет_подпунктов_в_v2_на_каждый_а_в_v1_суммарный(self):
        for i in range(3):
            ProblemPart.objects.create(problem=self.p, order=i, label='%d)' % i,
                                       statement='п' * 2000)
        v1 = build_text(Problem.objects.get(pk=self.p.pk), SPECS['v1'])
        v2 = build_text(Problem.objects.get(pk=self.p.pk), SPECS['v2'])
        самый_длинный = re.compile(r'п{2,}')
        self.assertEqual(sum(len(m.group()) for m in самый_длинный.finditer(v1)), 500)
        self.assertEqual(sum(len(m.group()) for m in самый_длинный.finditer(v2)),
                         3 * 1500)


class PrefetchTests(TestCase):

    def test_состав_prefetch_покрывает_все_связи_формулы(self):
        """Без этого — N+1 на 41 тысяче задач, и сборка текстов станет
        дольше самого кодирования."""
        self.assertEqual(set(PREFETCH), {
            'parts', 'topics', 'skills', 'tags', 'econ_concepts',
            'features_rel', 'hints', 'olympiad_refs'})

    def test_сборка_v2_не_делает_лишних_запросов(self):
        p = _make_problem()
        задача = (Problem.objects.filter(pk=p.pk)
                  .prefetch_related(*PREFETCH))[0]
        with self.assertNumQueries(0):
            build_text(задача, SPECS['v2'])
