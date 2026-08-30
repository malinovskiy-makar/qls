"""Справочник карты тем и тегов: инварианты дерева и целостность графа.

База данных здесь не участвует: карта строится по файлу
`catalog/data/taxonomy_tree.md`, а не по таблице `Tag` (новой таксономии
в базе ещё нет — см. `catalog/taxonomy_map.py`).
"""
import json
import pathlib
import re
import statistics

from django.test import SimpleTestCase

from catalog.taxonomy_map import (GROUPS, JSON_PATH, build_map, load_tree,
                                  parse_cross_links, parse_tree, read_map)


class TreeInvariantsTests(SimpleTestCase):
    """Числовые инварианты дерева — ровно те, что назвал владелец."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tree = load_tree()
        cls.tags = [t for th in cls.tree for t in th['tags']]

    def test_twenty_nine_themes(self):
        self.assertEqual(len(self.tree), 29)

    def test_theme_numbers_are_one_to_twenty_nine(self):
        self.assertEqual([th['n'] for th in self.tree], list(range(1, 30)))

    def test_three_hundred_forty_three_tags(self):
        self.assertEqual(len(self.tags), 343)

    def test_tags_per_theme_spread(self):
        sizes = [len(th['tags']) for th in self.tree]
        self.assertEqual(min(sizes), 5)
        self.assertEqual(max(sizes), 18)
        self.assertEqual(statistics.median(sizes), 11)

    def test_counter_present_on_one_hundred_eighty_tags(self):
        counted = [t for t in self.tags if t['count'] is not None]
        self.assertEqual(len(counted), 180)

    def test_sum_of_counters(self):
        """Сумма счётчиков — 37 264.

        ⚠️ В исходной спецификации стояло 31 780, и это число было получено
        парсером с двумя ошибками разбора скобки, а не из другого дерева:

          • «(3 153)» и «(1 792)» — пробел там разделяет РАЗРЯДЫ одного
            числа, а хвост « 153» отрезался как пояснение: крупнейший тег
            корпуса весил «3» задачи вместо 3 153;
          • «(110 / 197)» — слэш разделяет два паттерна, и второе число
            тоже уходило в «пояснение»: считалось 110 вместо 307.

        Разница ровно 5 484 = (3153−3) + (1792−1) + прирост четырёх пар со
        слэшем (543). Числа задач видны человеку на карте и задают размер
        узла, поэтому исправлены, а не подогнаны под прежний итог.
        """
        counted = [t['count'] for t in self.tags if t['count'] is not None]
        self.assertEqual(sum(counted), 37264)

    def test_thousands_separator_is_not_a_second_number(self):
        by_label = {t['label']: t['count'] for t in self.tags}
        self.assertEqual(by_label['Структура издержек: TC, VC, FC'], 3153)
        self.assertEqual(by_label['Средние и предельные издержки и их графики'], 1792)

    def test_slash_means_two_patterns_summed(self):
        by_label = {t['label']: t['count'] for t in self.tags}
        self.assertEqual(by_label['Абсолютные и сравнительные преимущества'], 307)
        self.assertEqual(by_label['Излишек потребителя и излишек производителя'], 489)

    def test_named_themes_keep_their_size(self):
        by_n = {th['n']: th for th in self.tree}
        self.assertEqual(by_n[8]['title'], 'Монополия и ценовая дискриминация')
        self.assertEqual(len(by_n[8]['tags']), 18)
        self.assertEqual(by_n[29]['title'], 'Другое')
        self.assertEqual(len(by_n[29]['tags']), 5)
        self.assertEqual(by_n[28]['title'], 'Математический аппарат')
        self.assertEqual(len(by_n[28]['tags']), 14)

    def test_every_theme_has_definition(self):
        for th in self.tree:
            self.assertTrue(th['desc'], 'у темы %d нет определения' % th['n'])

    def test_tag_numbers_are_consecutive_inside_theme(self):
        for th in self.tree:
            self.assertEqual([t['i'] for t in th['tags']],
                             list(range(1, len(th['tags']) + 1)),
                             'нумерация тегов темы %d с пропуском' % th['n'])

    def test_label_never_keeps_trailing_counter(self):
        """Счётчик вырезан из названия, а не оставлен в тексте подписи."""
        for t in self.tags:
            if t['count'] is not None:
                self.assertFalse(t['label'].rstrip().endswith(')') and
                                 t['label'].rstrip(')').rstrip().split()[-1].isdigit(),
                                 'в подписи остался счётчик: %r' % t['label'])

    def test_section_cut_does_not_stop_at_theme_five(self):
        """Раздел режется по началу строки, а не подстрокой «## 5.».

        Подстрока «## 5.» входит в «### 5. Теория потребителя и полезность»,
        и наивный поиск обрывал дерево на четвёртой теме — молча, без ошибки.
        """
        self.assertGreater(len(self.tree), 4)
        self.assertEqual(self.tree[4]['title'], 'Теория потребителя и полезность')


class GraphIntegrityTests(SimpleTestCase):
    """Целостность собранного графа."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.data = build_map()
        cls.nodes = cls.data['nodes']
        cls.links = cls.data['links']
        cls.by_id = {n['id']: n for n in cls.nodes}

    def test_node_and_link_counts(self):
        self.assertEqual(len(self.nodes), 372)          # 29 тем + 343 тега
        self.assertEqual(len(self.links), 425)          # 343 дерева + 82 кросса

    def test_node_ids_are_unique(self):
        self.assertEqual(len(self.by_id), len(self.nodes))

    def test_every_tag_has_exactly_one_parent_theme(self):
        parents = {}
        for ln in self.links:
            if ln['k'] != 'tree':
                continue
            self.assertNotIn(ln['t'], parents,
                             'у тега %s больше одного родителя' % ln['t'])
            parents[ln['t']] = ln['s']
        tags = [n for n in self.nodes if n['k'] == 'tag']
        self.assertEqual(len(parents), len(tags))
        for tag in tags:
            self.assertIn(tag['id'], parents, 'тег %s без темы' % tag['id'])
            parent = self.by_id[parents[tag['id']]]
            self.assertEqual(parent['k'], 'theme')
            self.assertEqual(parent['n'], tag['n'],
                             'тег %s подвешен к чужой теме' % tag['id'])

    def test_all_link_endpoints_exist(self):
        for ln in self.links:
            self.assertIn(ln['s'], self.by_id, 'ребро из ниоткуда: %s' % ln)
            self.assertIn(ln['t'], self.by_id, 'ребро в никуда: %s' % ln)

    def test_cross_links_join_different_themes(self):
        cross = [ln for ln in self.links if ln['k'] == 'cross']
        self.assertEqual(len(cross), 82)
        for ln in cross:
            a, b = self.by_id[ln['s']], self.by_id[ln['t']]
            self.assertEqual(a['k'], 'tag')
            self.assertEqual(b['k'], 'tag')
            self.assertNotEqual(a['n'], b['n'],
                                'перекрёстная связь внутри темы %d: %s ↔ %s'
                                % (a['n'], ln['s'], ln['t']))

    def test_cross_links_have_no_duplicates(self):
        pairs = [frozenset((ln['s'], ln['t']))
                 for ln in self.links if ln['k'] == 'cross']
        self.assertEqual(len(set(pairs)), len(pairs))

    def test_cross_link_list_parses_to_eighty_two_pairs(self):
        self.assertEqual(len(parse_cross_links()), 82)

    def test_every_theme_belongs_to_exactly_one_group(self):
        seen = {}
        for key, _label, nums in GROUPS:
            for n in nums:
                self.assertNotIn(n, seen, 'тема %d в двух разделах' % n)
                seen[n] = key
        self.assertEqual(sorted(seen), list(range(1, 30)))

    def test_group_of_tag_matches_group_of_its_theme(self):
        theme_group = {n['n']: n['g'] for n in self.nodes if n['k'] == 'theme'}
        for n in self.nodes:
            if n['k'] == 'tag':
                self.assertEqual(n['g'], theme_group[n['n']])

    def test_seven_groups_and_none_of_them_carries_a_colour(self):
        """Раздел остался структурным: имя и состав есть, цвета нет.

        ⚠️ ЭТО СТОРОЖ ОТКАЗА ОТ СЕМИ ЦВЕТОВ (ADR 0038), а не придирка к
        полям. Пока раздел носил свою пару цветов, их читал JavaScript
        карты; вернуть поля `cl`/`cd` — значит вернуть и разноцветные узлы,
        и никакой другой тест этого не заметит.
        """
        self.assertEqual(len(self.data['groups']), 7)
        for g in self.data['groups']:
            self.assertTrue(g['l'])
            self.assertTrue(g['themes'])
            self.assertNotIn('cl', g, 'у раздела снова появился цвет: %s' % g['k'])
            self.assertNotIn('cd', g, 'у раздела снова появился цвет: %s' % g['k'])


class NodeColourContrastTests(SimpleTestCase):
    """Один нейтральный цвет узла и акцент подсветки видны на холсте.

    ⚠️ ЭТО ЗАМЕНА СЕМИ ПРОВЕРОК СРАЗУ. До ADR 0038 карта разводила семь
    предметных цветов оттенком и светлотой, и контраст держала дотяжка
    внутри `topic_map.js`. Цветов больше нет — значит, нет и дотяжки, и
    порог теперь держат сами значения токенов. Проверяются ТРИ краски, из
    которых состоит вся карта: узел темы (в полную силу), узел тега (тот
    же цвет с прозрачностью 0,72) и акцент подсветки.

    Порог 3:1 — это норма для НЕтекстовой графики (WCAG 1.4.11): узел это
    кружок, а не буква.
    """

    TOKENS = pathlib.Path('templates/_tokens.html')
    MIN = 3.0
    TAG_ALPHA = 0.72          # то же число, что BASE_ALPHA_TAG в topic_map.js

    @staticmethod
    def _rgb(value):
        value = value.strip().lstrip('#')
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))

    @staticmethod
    def _over(top, bottom, alpha):
        """Полупрозрачная краска поверх непрозрачного фона."""
        return tuple(top[i] * alpha + bottom[i] * (1 - alpha) for i in range(3))

    @staticmethod
    def _luminance(rgb):
        def channel(part):
            part /= 255
            return (part / 12.92 if part <= 0.03928
                    else ((part + 0.055) / 1.055) ** 2.4)
        red, green, blue = (channel(p) for p in rgb)
        return 0.2126 * red + 0.7152 * green + 0.0722 * blue

    @classmethod
    def _contrast(cls, first, second):
        high, low = sorted((cls._luminance(first), cls._luminance(second)),
                           reverse=True)
        return round((high + 0.05) / (low + 0.05), 2)

    @classmethod
    def _themes(cls):
        css = cls.TOKENS.read_text(encoding='utf-8')
        cut = css.index('[data-theme="dark"]')
        return {'светлая': css[:cut], 'тёмная': css[cut:]}

    @staticmethod
    def _token(css, name):
        found = re.search(r'--%s:\s*([^;]+);' % re.escape(name), css)
        return found.group(1).strip() if found else None

    def _measure(self, css):
        """Три контраста к фону холста: тема, тег, акцент."""
        bg = self._token(css, 'bg')
        node = self._token(css, 'map-node')
        accent = self._token(css, 'accent')
        self.assertIsNotNone(bg, 'нет токена --bg')
        self.assertIsNotNone(node, 'нет токена --map-node')
        self.assertIsNotNone(accent, 'нет токена --accent')
        bg = self._rgb(bg)
        node = self._rgb(node)
        return {
            'узел темы': self._contrast(node, bg),
            'узел тега': self._contrast(self._over(node, bg, self.TAG_ALPHA), bg),
            'акцент': self._contrast(self._rgb(accent), bg),
        }

    def test_node_and_accent_stand_out_in_both_themes(self):
        for theme, css in self._themes().items():
            for what, value in self._measure(css).items():
                self.assertGreaterEqual(
                    value, self.MIN,
                    '%s тема, %s: контраст к холсту %s при норме %s'
                    % (theme, what, value, self.MIN))

    def test_only_one_node_colour_is_declared(self):
        """Семи цветов разделов в токенах больше нет.

        Без этой проверки токены `--g-base` … `--g-tools` можно вернуть, и
        покраснеет только глаз владельца.
        """
        css = self.TOKENS.read_text(encoding='utf-8')
        for key, _label, _nums in GROUPS:
            self.assertIsNone(
                re.search(r'--g-%s:' % re.escape(key), css),
                'в токенах снова цвет раздела: --g-%s' % key)


class BuiltJsonTests(SimpleTestCase):
    """Записанный в репозиторий JSON — валиден и совпадает со сборкой."""

    def test_json_file_exists_and_parses(self):
        self.assertTrue(JSON_PATH.exists(), 'нет %s' % JSON_PATH)
        data = json.loads(JSON_PATH.read_text(encoding='utf-8'))
        self.assertEqual(set(data), {'groups', 'nodes', 'links'})

    def test_json_matches_a_fresh_build(self):
        """Если разошлись — дерево правили, а команду не гоняли."""
        self.assertEqual(read_map(), build_map(),
                         'topic_map.json отстал от дерева: '
                         'manage.py build_topic_map')

    def test_json_stays_small_enough_to_ship(self):
        size = JSON_PATH.stat().st_size
        self.assertLess(size, 120 * 1024, 'карта разрослась: %d байт' % size)


class ParserUnitTests(SimpleTestCase):
    """Разбор отдельных строк — без чтения файла."""

    def test_counter_forms(self):
        md = ('### 1. Проверочная тема\n'
              '*Определение темы.*\n'
              '1. Тег без счётчика\n'
              '2. Тег с числом (42)\n'
              '3. Тег с разрядами (3 153)\n'
              '4. Тег с двумя паттернами (110 / 197)\n'
              '5. Тег с пояснением (338 суммарно по экстерналиям)\n'
              '6. Тег с пояснением и слэшем (142 по паттерну технологий/ИИ)\n')
        tags = parse_tree(md)[0]['tags']
        self.assertEqual([t['count'] for t in tags],
                         [None, 42, 3153, 307, 338, 142])
        self.assertEqual(tags[3]['label'], 'Тег с двумя паттернами')
        self.assertEqual(tags[4]['label'], 'Тег с пояснением')


class BuildGuardsTests(SimpleTestCase):
    """Сборка обязана ОТВЕРГАТЬ битые данные, а не собирать битый граф.

    ⚠️ Эти проверки появились после разбора зубастости остальных.
    Тесты `GraphIntegrityTests` смотрят на результат `build_map()`, а он
    никогда не бывает плохим, пока защиты внутри сборки целы: испорченная
    связь роняет сборку исключением, и до проверок дело не доходит. То
    есть сами защиты оставались без сторожа — их можно было удалить, и ни
    один тест бы не покраснел (проверено: при снятой защите дефект ловят
    уже `GraphIntegrityTests`, но пропажу самой защиты — никто).
    """

    def _tree(self):
        """Крошечное дерево из двух тем — чтобы не зависеть от файла."""
        md = ('### 1. Первая тема\n'
              '*Определение.*\n'
              '1. Альфа\n'
              '2. Бета\n'
              '\n'
              '### 2. Вторая тема\n'
              '*Определение.*\n'
              '1. Гамма\n'
              '2. Дельта\n')
        return parse_tree(md)

    def _build_with(self, raw):
        from unittest import mock
        with mock.patch('catalog.taxonomy_map.CROSS_LINKS_RAW', raw):
            return build_map(self._tree())

    def test_rejects_link_to_missing_tag(self):
        with self.assertRaises(ValueError) as box:
            self._build_with('1.1-2.99')
        self.assertIn('несуществующий', str(box.exception))

    def test_rejects_link_inside_one_theme(self):
        with self.assertRaises(ValueError) as box:
            self._build_with('1.1-1.2')
        self.assertIn('внутри одной темы', str(box.exception))

    def test_rejects_duplicate_link(self):
        with self.assertRaises(ValueError) as box:
            self._build_with('1.1-2.1  2.1-1.1')
        self.assertIn('дважды', str(box.exception))

    def test_rejects_theme_outside_groups(self):
        """Тема, не попавшая ни в один раздел корпуса, не должна пройти молча:
        без цвета раздела она станет невидимой на карте."""
        md = ('### 41. Тема из ниоткуда\n'
              '*Определение.*\n'
              '1. Альфа\n')
        with self.assertRaises(ValueError) as box:
            build_map(parse_tree(md))
        self.assertIn('вне разделов', str(box.exception))

    def test_accepts_valid_pair(self):
        data = self._build_with('1.1-2.2')
        cross = [ln for ln in data['links'] if ln['k'] == 'cross']
        self.assertEqual(len(cross), 1)
