"""Этап 2 редизайна каталога: множественный выбор, пять блоков, правило нуля.

Промпт владельца 04.09.2026, фазы 2.1–2.2: темы, сложности, источники и
особенности — списки (ИЛИ внутри группы, И между группами); старые одиночные
адреса читаются как список из одного; вариант с нулём в корпусе не
рендерится, ноль под текущими фильтрами остаётся с флагом `zero`; темы
лежат в пяти блоках владельца; группы «Характер» и «Особенности» включаются
сами, когда у задач появляются данные.
"""
from django.http import QueryDict
from django.test import SimpleTestCase, TestCase

from catalog import filters
from problems.tests.factories import (
    link_source, make_problem, make_source, make_topic,
)

CATALOG_URL = '/catalog/'


class ParseTests(SimpleTestCase):
    def test_lists_come_from_repeated_params(self):
        active = filters.parse(QueryDict(
            'topic=1&topic=2&topic=1&difficulty=4&difficulty=5&difficulty=9'
            '&source=7&feature=graph&feature=nope&tag=3&type=test'
            '&test_type=тест: один ответ&character=quant&has_solution=1'))
        self.assertEqual(active['topics'], ['1', '2'])
        self.assertEqual(active['difficulties'], ['4', '5'])
        self.assertEqual(active['sources'], ['7'])
        self.assertEqual(active['features'], ['graph'])
        self.assertEqual(active['tags'], ['3'])
        # Старый адрес нёс точную строку `problem_type`; разбор переводит
        # её в ВИД теста — одна точка правды `problems.problem_types`.
        self.assertEqual((active['kind'], active['test_type']),
                         ('test', 'single'))
        self.assertEqual(active['character'], 'quant')
        self.assertTrue(active['has_solution'])

    def test_legacy_single_address_and_plain_dict(self):
        self.assertEqual(filters.parse(QueryDict('topic=843'))['topics'], ['843'])
        active = filters.parse({'topic': '843', 'difficulty': '4',
                                'feature': ['graph', 'table'], 'character': 'x'})
        self.assertEqual(active['topics'], ['843'])
        self.assertEqual(active['difficulties'], ['4'])
        self.assertEqual(active['features'], ['graph', 'table'])
        self.assertEqual(active['character'], '')

    def test_query_round_trip(self):
        active = filters.parse(QueryDict(
            'topic=1&topic=2&tag=3&difficulty=4&difficulty=5&type=test'
            '&test_type=тест: все верные&source=7&feature=graph&has_solution=1&q=спрос'))
        url = filters.query({'view': 'gallery'}, active)
        again = filters.parse(QueryDict(url[1:]))
        self.assertEqual(again, active)
        self.assertIn('view=gallery', url)
        self.assertEqual(url.count('topic='), 2)
        hidden = dict(filters._hidden_fields({}, active))
        self.assertNotIn('q', hidden)
        self.assertEqual([v for k, v in filters._hidden_fields({}, active) if k == 'topic'],
                         ['1', '2'])

    def test_selected_count_and_emptiness(self):
        active = filters.parse(QueryDict('topic=1&topic=2&difficulty=4&difficulty=5'
                                         '&type=test&test_type=тест: один ответ'
                                         '&has_solution=1&source=7'))
        self.assertEqual(filters.selected_count(active), 7)
        self.assertFalse(filters.is_empty(active))
        self.assertTrue(filters.is_empty(filters.parse(QueryDict('q=спрос'))))

    def test_scope_and_relief_labels_for_several_values(self):
        self.assertEqual(filters.scope_label('topic', ['Монополия']), 'по теме «Монополия»')
        self.assertEqual(filters.scope_label('topic', ['А', 'Б']), 'по темам «А», «Б»')
        self.assertEqual(filters.scope_label('topic', ['А', 'Б', 'В', 'Г']), 'по 4 темам')
        self.assertEqual(filters.scope_label('difficulty', ['5', '4']), 'на сложностях 4–5')
        self.assertEqual(filters.relief_label('topic', 1), 'тема')
        self.assertEqual(filters.relief_label('topic', 2), '2 темы')
        self.assertEqual(filters.relief_label('source', 5), '5 источников')


class MultiSelectQueryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.mon = make_topic('Монополия и ценовая дискриминация')
        cls.el = make_topic('Эластичность')
        cls.gdp = make_topic('ВВП и национальные счета')
        cls.src_a = make_source('Сборник А')
        cls.src_b = make_source('Сборник Б')
        cls.p_a1 = make_problem('Монополист один.', topic=cls.mon, difficulty=4)
        cls.p_a2 = make_problem('Монополист два.', topic=cls.mon, difficulty=5)
        cls.p_b = make_problem('Эластичность спроса.', topic=cls.el, difficulty=5)
        cls.p_c = make_problem('ВВП по расходам.', topic=cls.gdp, difficulty=2)
        cls.p_ab = make_problem('Монополист и эластичность.', topic=cls.mon,
                                difficulty=3, solution='Решение.')
        cls.p_ab.topics.add(cls.el)
        link_source(cls.p_a1, cls.src_a)
        link_source(cls.p_b, cls.src_b)

    def _ids(self, params):
        resp = self.client.get(CATALOG_URL, params)
        self.assertEqual(resp.status_code, 200)
        return {c['problem'].pk for c in resp.context['cards']}

    def test_two_topics_are_a_union(self):
        both = {'topic': [self.mon.pk, self.el.pk]}
        self.assertEqual(self._ids(both),
                         {self.p_a1.pk, self.p_a2.pk, self.p_b.pk, self.p_ab.pk})
        self.assertEqual(self.client.get(CATALOG_URL, both).context['total'], 4)

    def test_two_difficulties_add_up_and_groups_intersect(self):
        self.assertEqual(self._ids({'difficulty': [4, 5]}),
                         {self.p_a1.pk, self.p_a2.pk, self.p_b.pk})
        self.assertEqual(self._ids({'difficulty': [4, 5], 'topic': self.el.pk}),
                         {self.p_b.pk})
        self.assertEqual(self._ids({'source': [self.src_a.pk, self.src_b.pk]}),
                         {self.p_a1.pk, self.p_b.pk})

    def test_scope_names_several_topics(self):
        resp = self.client.get(CATALOG_URL, {'topic': [self.mon.pk, self.el.pk]})
        # Порядок подписей — порядок владельца (блок, место в блоке), не адреса.
        self.assertEqual(resp.context['scope'],
                         'по темам «Эластичность», «Монополия и ценовая дискриминация»')

    def _build(self, params):
        active = filters.parse(QueryDict(params))
        return filters.build(filters.base_queryset('catalog'), active)[1]

    def test_zero_in_corpus_is_not_an_option_zero_under_filters_stays(self):
        ctx = self._build('')
        by_key = {g['key']: g for g in ctx['groups']}
        self.assertEqual([o['value'] for o in by_key['difficulty']['options']],
                         ['2', '3', '4', '5'])
        ctx = self._build('topic=%d' % self.gdp.pk)
        by_key = {g['key']: g for g in ctx['groups']}
        counts = {o['value']: (o['count'], o['zero']) for o in by_key['difficulty']['options']}
        self.assertEqual(counts, {'2': (1, False), '3': (0, True),
                                  '4': (0, True), '5': (0, True)})

    def test_kind_and_test_types_follow_the_corpus(self):
        by_key = {g['key']: g for g in self._build('')['groups']}
        self.assertEqual([o['value'] for o in by_key['kind']['options']], ['open'])
        self.assertEqual(by_key['kind']['test_types'], [])
        make_problem('Тестовый вопрос.', problem_type='тест: один ответ')
        by_key = {g['key']: g for g in self._build('')['groups']}
        self.assertEqual([o['value'] for o in by_key['kind']['options']], ['open', 'test'])
        self.assertEqual([o['value'] for o in by_key['kind']['test_types']],
                         ['single'])

    def test_topics_sit_in_owner_blocks_in_owner_order(self):
        by_key = {g['key']: g for g in self._build('')['groups']}
        blocks = by_key['topic']['groups']
        self.assertEqual([b['key'] for b in blocks], ['micro', 'macro'])
        self.assertEqual([o['label'] for o in blocks[0]['options']],
                         ['Эластичность', 'Монополия и ценовая дискриминация'])
        self.assertEqual(blocks[0]['options'][1]['section'], 'micro')
        self.assertEqual(blocks[1]['label'], 'Макро')
        self.assertEqual(blocks[1]['count'], 1)
        selected = {g['key']: g for g in self._build('topic=%d' % self.gdp.pk)['groups']}
        self.assertEqual([b['selected'] for b in selected['topic']['groups']], [0, 1])
        self.assertEqual([b['open'] for b in selected['topic']['groups']], [False, True])

    def test_unknown_topic_names_are_not_filter_options(self):
        junk = make_topic('Иванов И. И.')
        self.p_c.topics.add(junk)
        labels = [o['label'] for g in self._build('')['groups'] if g['key'] == 'topic'
                  for b in g['groups'] for o in b['options']]
        self.assertNotIn('Иванов И. И.', labels)

    def test_modal_layout_is_the_owners(self):
        self.assertEqual(filters.MODAL_LEFT, ('topic', 'character', 'kind', 'has_solution'))
        self.assertEqual(filters.MODAL_RIGHT, ('tag', 'difficulty', 'feature', 'source'))
        self.assertEqual(filters.CHARACTERS, (('qual', 'Качественная'),
                                              ('quant', 'Количественная')))


class CharacterAndFeaturesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.topic = make_topic('Эластичность')
        cls.p1 = make_problem('С графиком.', topic=cls.topic, difficulty=3)
        cls.p2 = make_problem('С таблицей.', topic=cls.topic, difficulty=3)
        cls.p3 = make_problem('Без всего.', topic=cls.topic, difficulty=3)

    def _keys(self):
        active = filters.parse(QueryDict(''))
        return filters.field_keys(filters.build(filters.base_queryset('catalog'), active)[1])

    def test_groups_appear_only_with_data(self):
        self.assertNotIn('character', self._keys())
        self.assertNotIn('feature', self._keys())
        self.p1.character = 'quant'
        self.p1.features = ['graph', 'table']
        self.p1.save(update_fields=['character', 'features'])
        self.p2.features = ['table']
        self.p2.save(update_fields=['features'])
        self.assertIn('character', self._keys())
        self.assertIn('feature', self._keys())
        active = filters.parse(QueryDict(''))
        by_key = {g['key']: g for g in filters.build(filters.base_queryset('catalog'), active)[1]['groups']}
        self.assertEqual([(o['value'], o['count']) for o in by_key['character']['options']],
                         [('quant', 1)])
        self.assertEqual([(o['value'], o['count']) for o in by_key['feature']['options']],
                         [('graph', 1), ('table', 2)])

    def test_filtering_by_character_and_features(self):
        self.p1.character = 'quant'
        self.p1.features = ['graph']
        self.p1.save(update_fields=['character', 'features'])
        self.p2.features = ['table', 'proof']
        self.p2.save(update_fields=['features'])
        ids = lambda params: {c['problem'].pk for c in
                              self.client.get(CATALOG_URL, params).context['cards']}
        self.assertEqual(ids({'character': 'quant'}), {self.p1.pk})
        self.assertEqual(ids({'feature': 'graph'}), {self.p1.pk})
        self.assertEqual(ids({'feature': ['graph', 'proof']}), {self.p1.pk, self.p2.pk})
        self.assertEqual(ids({'feature': 'graph', 'character': 'quant'}), {self.p1.pk})
        html = self.client.get(CATALOG_URL, {'feature': ['graph', 'proof'],
                                             'character': 'quant'}).content.decode()
        self.assertIn('data-chip="character">Количественная<a', html)
        self.assertIn('data-chip="feature">Есть график<a', html)
        self.assertIn('data-chip="feature">Требует доказательства<a', html)
