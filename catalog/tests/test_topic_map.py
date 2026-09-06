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

    def test_every_cross_link_carries_an_explanation(self):
        """У каждой из 82 связей есть пояснение, и оно осмысленной длины.

        ⚠️ ЭТО СТОРОЖ СМЫСЛА СВЯЗИ, а не придирка к полю. Без пояснения
        линия между двумя тегами не говорит человеку ничего: он видит, что
        связь есть, и не видит, в чём она. Нижняя граница в 5 символов
        отсекает заглушки вроде «—» и «ок», верхняя в 40 — фразу, которая
        не влезет ни в подпись посередине линии, ни в карточку панели.
        """
        cross = [ln for ln in self.links if ln['k'] == 'cross']
        self.assertEqual(len(cross), 82)
        for ln in cross:
            why = ln.get('w', '')
            self.assertTrue(
                why, 'связь без пояснения: %s ↔ %s' % (ln['s'], ln['t']))
            self.assertGreaterEqual(
                len(why), 5,
                'пояснение короче пяти символов: %s ↔ %s — %r'
                % (ln['s'], ln['t'], why))
            self.assertLessEqual(
                len(why), 40,
                'пояснение длиннее сорока символов: %s ↔ %s — %r'
                % (ln['s'], ln['t'], why))

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
        """У раздела есть имя и состав; цвет — есть, но не здесь.

        ⚠️ ЦВЕТА РАЗДЕЛОВ ВЕРНУЛИСЬ (ADR 0053), А ПОЛЯ `cl`/`cd` — НЕТ, и это
        не мелочь. Цвет раздела — оформление, его место в CSS
        (`--map-g-*` в topic_map.css), где его меняет дизайн и сторожит
        замер контраста. Данные карты остаются данными: положи цвет в JSON
        — и он разъедется с темой сайта, потому что тем две, а поле одно.
        """
        # Разделов ПЯТЬ с 04.09.2026 — те же блоки, что в фильтрах
        # каталога и на радаре статистики (ADR 0071).
        self.assertEqual(len(self.data['groups']), 5)
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

    #: Порог для надписи-ориентира — 4,5:1, а не 3:1. Это ТЕКСТ, а не
    #: кружок, и норма у него текстовая (WCAG 1.4.3).
    MIN_TEXT = 4.5

    def test_region_label_colour_is_readable_in_both_themes(self):
        """Надписи-ориентиры по разделам читаются на холсте.

        ⚠️ ЭТО СТОРОЖ ТРЕТЬЕГО ЦВЕТА КАРТЫ (ADR 0046). До него ориентиры
        писались тем же `--map-node`, что и узлы, и терялись среди них —
        это и увидел владелец на приёмке. Порог здесь текстовый, 4,5:1:
        ориентир — надпись, а не графический элемент. Замер на момент
        ввода: 5,05 в светлой теме и 9,32 в тёмной.

        Прозрачность в расчёт НЕ входит намеренно: под буквами лежит
        обводка цветом холста толщиной 3 px, и глаз сравнивает букву именно
        с ней, а не с тем, что под надписью оказалось.
        """
        for theme, css in self._themes().items():
            region = self._token(css, 'map-region')
            bg = self._token(css, 'bg')
            self.assertIsNotNone(
                region, '%s тема: нет токена --map-region' % theme)
            value = self._contrast(self._rgb(region), self._rgb(bg))
            self.assertGreaterEqual(
                value, self.MIN_TEXT,
                '%s тема, надпись раздела: контраст к холсту %s при норме %s'
                % (theme, value, self.MIN_TEXT))

    def test_region_colour_differs_from_node_and_accent(self):
        """Третий цвет — именно третий, а не переименованный первый.

        Написать ориентиры цветом узлов или акцентом — значит соврать про
        слой: серым они теряются среди узлов, малиновым притворяются
        подсветкой. Совпадение значений вернуло бы ровно тот дефект, ради
        которого цвет и заводился.
        """
        for theme, css in self._themes().items():
            region = self._token(css, 'map-region')
            self.assertNotEqual(
                self._rgb(region), self._rgb(self._token(css, 'map-node')),
                '%s тема: ориентир окрашен цветом узла' % theme)
            self.assertNotEqual(
                self._rgb(region), self._rgb(self._token(css, 'accent')),
                '%s тема: ориентир окрашен акцентом подсветки' % theme)

    def test_only_one_node_colour_is_declared(self):
        """Старых имён `--g-base` … `--g-tools` в токенах нет.

        ⚠️ СМЫСЛ ПРОВЕРКИ ПОМЕНЯЛСЯ ВМЕСТЕ С ADR 0053. Раньше она сторожила
        отказ от цветов разделов; теперь цвета вернулись, но под ИНЫМИ
        именами — `--map-g-*`, рядом с прочими ролями карты. Старая пара
        имён осталась бы вторым объявлением того же смысла, а два места
        объявления одной роли неизбежно расходятся: проверка стережёт
        именно это, а не сам факт цвета.
        """
        css = self.TOKENS.read_text(encoding='utf-8')
        for key, _label, _nums in GROUPS:
            self.assertIsNone(
                re.search(r'--g-%s:' % re.escape(key), css),
                'в токенах снова цвет раздела: --g-%s' % key)



class SectionColourTests(SimpleTestCase):
    """Семь цветов разделов: видны на холсте, различимы, не врут про слой.

    ⚠️ ЭТО ВОЗВРАТ ЦВЕТА, ОТМЕНЁННОГО В ADR 0038, и вернулся он не «как
    было». Прошлый отказ опирался на довод «легенду никто не помнит» —
    теперь легенда всегда на экране: заголовок раздела в правой панели
    написан своим цветом. См. ADR 0053.

    Значения живут в `templates/_tokens.html` рядом с `--map-node` и
    `--map-region`: это роли палитры, а не частность одного экрана.
    """

    TOKENS = pathlib.Path('templates/_tokens.html')
    JS = pathlib.Path('catalog/static/catalog/js/topic_map.js')
    PREVIEW_JS = pathlib.Path('catalog/static/catalog/js/topic_map_preview.js')

    #: Цвет здесь НЕСЁТ СМЫСЛ (в каком разделе узел), а не украшает, поэтому
    #: порог взят текстовый, 4,5:1, а не 3:1 как у нетекстовой графики.
    MIN_BG = 4.5
    #: Тег рисуется тем же цветом с прозрачностью 0,72 — то же число, что
    #: BASE_ALPHA_TAG в topic_map.js. Полупрозрачный кружок это уже графика,
    #: и порог у него 3:1.
    TAG_ALPHA = 0.72
    MIN_TAG = 3.0
    #: Насколько краски обязаны отличаться друг от друга и от чужих ролей.
    #: ΔE76 около 15 — это «видно, что цвета разные» на соседних пятнах;
    #: берём с запасом, замер даёт не меньше 23.
    MIN_APART = 15.0
    MIN_FROM_ROLE = 25.0

    # Считалки контраста берём у соседнего класса, а не переписываем: две
    # копии формулы WCAG неизбежно разойдутся. Обёртки нужны потому, что при
    # присваивании через класс статический метод теряет свою обёртку.
    _rgb = staticmethod(NodeColourContrastTests._rgb)
    _over = staticmethod(NodeColourContrastTests._over)
    _luminance = staticmethod(NodeColourContrastTests._luminance)
    _contrast = classmethod(NodeColourContrastTests._contrast.__func__)
    _token = staticmethod(NodeColourContrastTests._token)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        tokens = cls.TOKENS.read_text(encoding='utf-8')
        cut = tokens.index('[data-theme="dark"]')
        cls.tokens = {'светлая': tokens[:cut], 'тёмная': tokens[cut:]}
        # Цвета разделов лежат там же, где остальные роли карты.
        cls.blocks = cls.tokens

    def _colours(self, theme):
        """{ключ раздела: rgb} для одной темы."""
        out = {}
        for key, _label, _nums in GROUPS:
            found = re.search(r'--map-g-%s:\s*(#[0-9A-Fa-f]{6})' % re.escape(key),
                              self.blocks[theme])
            self.assertIsNotNone(
                found, '%s тема: нет цвета раздела --map-g-%s' % (theme, key))
            out[key] = self._rgb(found.group(1))
        return out

    @staticmethod
    def _lab(rgb):
        def inv(part):
            part /= 255
            return (part / 12.92 if part <= 0.04045
                    else ((part + 0.055) / 1.055) ** 2.4)
        red, green, blue = (inv(p) for p in rgb)
        x = (0.4124 * red + 0.3576 * green + 0.1805 * blue) / 0.95047
        y = 0.2126 * red + 0.7152 * green + 0.0722 * blue
        z = (0.0193 * red + 0.1192 * green + 0.9505 * blue) / 1.08883

        def f(t):
            return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
        fx, fy, fz = f(x), f(y), f(z)
        return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))

    @classmethod
    def _delta(cls, first, second):
        one, two = cls._lab(first), cls._lab(second)
        return round(sum((one[i] - two[i]) ** 2 for i in range(3)) ** 0.5, 1)

    def test_all_five_sections_have_a_colour_in_both_themes(self):
        for theme in ('светлая', 'тёмная'):
            self.assertEqual(len(self._colours(theme)), 5)

    def test_every_section_colour_is_visible_on_the_canvas(self):
        """Порог 4,5:1 к фону холста — цвет отвечает на вопрос «где я»."""
        for theme in ('светлая', 'тёмная'):
            bg = self._rgb(self._token(self.tokens[theme], 'bg'))
            for key, colour in self._colours(theme).items():
                value = self._contrast(colour, bg)
                self.assertGreaterEqual(
                    value, self.MIN_BG,
                    '%s тема, раздел %s: контраст к холсту %s при норме %s'
                    % (theme, key, value, self.MIN_BG))

    def test_tag_shade_of_every_section_still_stands_out(self):
        """Тег — тот же цвет вполсилы. Он не обязан быть текстом, но обязан
        быть видимым кружком: порог 3:1 (WCAG 1.4.11)."""
        for theme in ('светлая', 'тёмная'):
            bg = self._rgb(self._token(self.tokens[theme], 'bg'))
            for key, colour in self._colours(theme).items():
                mixed = self._over(colour, bg, self.TAG_ALPHA)
                value = self._contrast(mixed, bg)
                self.assertGreaterEqual(
                    value, self.MIN_TAG,
                    '%s тема, тег раздела %s: контраст к холсту %s при норме %s'
                    % (theme, key, value, self.MIN_TAG))

    def test_sections_do_not_blend_into_each_other(self):
        """Семь красок должны читаться как семь, а не как «примерно две».

        ⚠️ РАЗВЕДЕНЫ НЕ ТОЛЬКО ТОНОМ, НО И СВЕТЛОТОЙ. Пары с близким тоном
        (два зелёных, два фиолетовых) отличаются ещё и светлотой — иначе
        для того, кто путает красный с зелёным, они сливаются в одну.
        """
        for theme in ('светлая', 'тёмная'):
            colours = self._colours(theme)
            keys = list(colours)
            for i, first in enumerate(keys):
                for second in keys[i + 1:]:
                    value = self._delta(colours[first], colours[second])
                    self.assertGreaterEqual(
                        value, self.MIN_APART,
                        '%s тема: разделы %s и %s почти одного цвета (dE %s)'
                        % (theme, first, second, value))

    def test_sections_are_not_the_accent_and_not_the_region_label(self):
        """Цвет раздела не притворяется ни подсветкой, ни ориентиром.

        Акцент означает «вот то, что ты держишь», `--map-region` — «вот где
        ты на карте». Совпади с ними цвет раздела — и человек прочитает
        обычный узел как выделенный.
        """
        for theme in ('светлая', 'тёмная'):
            accent = self._rgb(self._token(self.tokens[theme], 'accent'))
            region = self._rgb(self._token(self.tokens[theme], 'map-region'))
            for key, colour in self._colours(theme).items():
                for name, other in (('акцентом', accent), ('ориентиром', region)):
                    value = self._delta(colour, other)
                    self.assertGreaterEqual(
                        value, self.MIN_FROM_ROLE,
                        '%s тема: раздел %s путается с %s (dE %s)'
                        % (theme, key, name, value))

    def test_both_map_modes_actually_read_the_section_colours(self):
        """Объявленный, но никем не читаемый цвет — не введённый цвет.

        ⚠️ ЭТО ПРЯМОЕ ПРИМЕНЕНИЕ ADR 0051: токен считается введённым только
        тогда, когда его кто-то читает. Полная карта и предпросмотр обязаны
        брать `--map-g-*`, иначе замеры выше сторожат красивые числа в файле
        и ничего на экране.
        """
        for name, path in (('полная карта', self.JS),
                           ('предпросмотр', self.PREVIEW_JS)):
            src = path.read_text(encoding='utf-8')
            self.assertIn("'--map-g-'", src,
                          '%s не читает цвета разделов' % name)


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
        # ⚠️ Записи разделяются «|», а не пробелом: пробел теперь отделяет
        # код связи от её пояснения.
        with self.assertRaises(ValueError) as box:
            self._build_with('1.1-2.1 | 2.1-1.1')
        self.assertIn('дважды', str(box.exception))

    def test_link_explanation_is_parsed_and_stored(self):
        data = self._build_with('1.1-2.2 общая тема')
        cross = [ln for ln in data['links'] if ln['k'] == 'cross']
        self.assertEqual(cross[0]['w'], 'общая тема')

    def test_link_without_explanation_still_parses(self):
        """Разбор пояснения не требует: обязательность — дело отдельного
        теста на боевом списке, а проверкам разбора важна только пара."""
        data = self._build_with('1.1-2.2')
        cross = [ln for ln in data['links'] if ln['k'] == 'cross']
        self.assertEqual(cross[0]['w'], '')

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







class MapTextsTests(SimpleTestCase):
    """Тексты карты: легенда, описания тем, витрина страницы."""

    JS = pathlib.Path('catalog/static/catalog/js/topic_map.js')
    CSS = pathlib.Path('catalog/static/catalog/css/topic_map.css')

    #: Служебные пометки редактора, которым не место в тексте для человека.
    EDITORIAL = re.compile(
        r'НОВАЯ|НОВЫЙ|Переименован|Самый крупный|Целевая доля|'
        r'\d[\d\s]*задач|~\s*\d|в текущей теме|суммарно')

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.src = cls.JS.read_text(encoding='utf-8')
        cls.tree = load_tree()

    def test_legend_is_titled_as_a_legend(self):
        """Над легендой стоит «Как пользоваться», а не «Под курсором».

        ⚠️ БЛОК ОДИН, СОСТОЯНИЙ ДВА, И ЗАГОЛОВОК ОБЯЗАН ИДТИ ЗА
        СОДЕРЖИМЫМ. Пока ничего не наведено, в блоке объяснение знаков —
        а заголовок «Под курсором» над ним сообщал неправду: под курсором
        в этот момент ровно ничего.
        """
        html = self.client.get('/catalog/map/').content.decode('utf-8')
        self.assertIn('id="tmap-hover-head">Как пользоваться<', html)
        self.assertIn("setHoverHead('Как пользоваться')", self.src)
        self.assertIn("setHoverHead('Под курсором')", self.src)

    def test_legend_text_has_no_long_dashes(self):
        """Длинных тире в легенде нет: пять коротких фраз читаются быстрее
        одной длинной с оговорками."""
        howto = self.src[self.src.index('var HOWTO ='):]
        howto = howto[:howto.index("</ul>';")]
        self.assertNotIn('—', howto)

    def test_hover_block_hides_its_scrollbar(self):
        """У блока фиксированная высота, и системная полоса стояла в нём
        постоянно — даже когда прокручивать нечего."""
        css = self.CSS.read_text(encoding='utf-8')
        block = css[css.index('#tmap-hover-block {'):]
        block = block[:block.index('/* Прокручиваемая часть панели')]
        self.assertIn('scrollbar-width: none', block)
        self.assertIn('#tmap-hover-block:hover { scrollbar-width: thin; }', block)

    def test_theme_descriptions_carry_no_editorial_notes(self):
        """Описания тем — текст для человека, а не заметки редактора.

        ⚠️ «НОВАЯ ТЕМА», «Самый крупный блок корпуса», «2 525 задач
        упоминают монополию» — всё это про РАБОТУ НАД таксономией, а не про
        предмет. Человеку, открывшему карту, они не говорят ничего: он не
        знает, относительно чего тема новая и когда её переименовали.
        """
        for theme in self.tree:
            found = self.EDITORIAL.search(theme['desc'])
            self.assertIsNone(
                found,
                'тема %d: в описании служебная пометка «%s»'
                % (theme['n'], found.group(0) if found else ''))

    def test_theme_descriptions_are_short_and_uniform(self):
        """Единый шаблон: одна фраза о сути.

        Число задач в описании не повторяется НАРОЧНО: панель печатает его
        сама отдельной строкой, и второй источник того же числа разошёлся бы
        с первым при ближайшем пересчёте корпуса.
        """
        for theme in self.tree:
            self.assertTrue(theme['desc'], 'тема %d без описания' % theme['n'])
            self.assertLessEqual(
                len(theme['desc']), 110,
                'тема %d: описание в %d знаков, длиннее одной фразы'
                % (theme['n'], len(theme['desc'])))

    def test_page_says_what_it_is_not_what_to_do(self):
        """Витрина страницы отвечает «что это», а не «как этим пользоваться».

        Инструкция «наведитесь на тег и уходите от него по линиям» уместна в
        обучении, а не в шапке: человек читает её раньше, чем понял, зачем
        ему карта. Тому же учит теперь интерактивный тур.
        """
        html = self.client.get('/catalog/map/').content.decode('utf-8')
        self.assertIn('<h1>Интерактивная карта задач</h1>', html)
        self.assertNotIn('наведитесь на тег', html)


class PanelTreeTests(SimpleTestCase):
    """Правая панель — дерево разделы → темы → теги.

    Плоский список из 29 тем с бледными заголовками разделов заменён на
    дерево, свёрнутое по умолчанию. Заголовок раздела написан цветом
    раздела — он же легенда к цветам на карте (ADR 0053).
    """

    JS = pathlib.Path('catalog/static/catalog/js/topic_map.js')
    CSS = pathlib.Path('catalog/static/catalog/css/topic_map.css')

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.src = cls.JS.read_text(encoding='utf-8')
        cls.css = cls.CSS.read_text(encoding='utf-8')
        cls.html = None

    def _page(self):
        if self.html is None:
            type(self).html = self.client.get('/catalog/map/').content.decode('utf-8')
        return self.html

    def test_tree_carries_all_three_levels(self):
        """Пять разделов, 29 тем, 343 тега — весь справочник, а не выборка.

        Дерево печатается на сервере целиком: 372 строки это около 30 КБ
        разметки, а собирать их на клиенте значило бы держать вторую копию
        справочника ради того же результата.
        """
        html = self._page()
        self.assertEqual(html.count('class="tmap-sec-row"'), 5)
        self.assertEqual(html.count('class="tmap-theme-row"'), 29)
        self.assertEqual(html.count('class="tmap-tag-row"'), 343)

    def test_tree_starts_collapsed(self):
        """Свёрнуто по умолчанию: пять строк вместо двадцати девяти.

        Именно из-за этого в покое не нужна и полоса прокрутки.

        ⚠️ СЧИТАЕМ ВНУТРИ ДЕРЕВА, А НЕ ПО ВСЕЙ СТРАНИЦЕ. С 04.09.2026
        `aria-expanded` есть и у кнопки ☰ в шапке — она тоже «свёрнута», но к
        дереву разделов отношения не имеет.
        """
        tree = self._page().split('class="tmap-tree"', 1)[-1]
        self.assertEqual(tree.count('aria-expanded="false"'), 5 + 29)
        self.assertNotIn('aria-expanded="true"', tree)

    def test_section_headers_are_painted_with_their_colour(self):
        """Заголовок раздела — легенда, а не украшение.

        ⚠️ КЛЮЧ РАЗДЕЛА ВСТРЕЧАЕТСЯ СО СВОЕЙ КРАСКОЙ РОВНО В ОДНОМ МЕСТЕ —
        в этих пяти правилах. Разметка про цвета не знает и печатает только
        `data-sec`; разъедется — покраснеет здесь.
        """
        for key, _label, _nums in GROUPS:
            rule = '.tmap-tree-sec[data-sec="%s"]' % key
            self.assertIn(rule, self.css, 'у раздела %s нет цвета в дереве' % key)
            self.assertIn('--sec: var(--map-g-%s)' % key, self.css)
        self.assertIn('color: var(--sec', self.css)

    def test_clicking_a_tag_goes_to_the_tag_and_shows_where_it_belongs(self):
        """Клик по тегу ведёт камеру к ТЕГУ, а не к его теме.

        Дерево пользуется тем же исправлением, что и холст: выбирается и
        показывается ровно тот узел, по которому кликнули. Принадлежность
        показывается отдельно — импульсом по ребру к теме и мягкой вторичной
        подсветкой самой темы.
        """
        self.assertIn('function revealTag(', self.src)
        reveal = self.src[self.src.index('function revealTag('):]
        reveal = reveal[:reveal.index('\n}')]
        self.assertIn('flyTo(n, 2.1)', reveal)
        self.assertIn('pulse =', reveal)
        # тема попадает во ВТОРОЙ уровень подсветки, а не в первый
        self.assertIn('litNear[parent.id] = true;', self.src)
        self.assertNotIn('litSet[parent.id] = true;', self.src)

    def test_expanding_and_selecting_are_different_actions(self):
        """Клик по теме раскрывает, а не выбирает.

        Раньше одна кнопка делала два дела разом: наводила камеру и
        добавляла тему в выбранное. Человек, открывший список посмотреть
        состав, молча получал полтора десятка тегов в подборке.
        """
        panel = self.src[self.src.index("var themesBox = document.getElementById('tmap-themes');"):]
        # ⚠️ Сторожим ЛЮБОЙ вызов выбора из дерева, а не одну его запись:
        # узкая проверка на `selectNode(n)` пропустила бы `selectNode(byId[…])`.
        self.assertNotIn('selectNode(', panel)
        self.assertIn("e.target.closest('[data-open]')", panel)

    def test_pulse_stops_when_motion_is_switched_off(self):
        """Импульс — украшение поверх подсветки, и при отключённом движении
        его нет вовсе: подсветка сообщает то же самое и без него."""
        self.assertIn('if (pulse && !reduceMotion)', self.src)

    def test_scrollbar_is_hidden_until_the_panel_is_hovered(self):
        """Полосы прокрутки не видно, пока на панель не навелись.

        Прокрутка при этом работает всегда: убрана полоса, а не возможность.
        """
        block = self.css[self.css.index('.tmap-panel-scroll {'):]
        block = block[:block.index('.tmap-block {')]
        self.assertIn('scrollbar-width: none', block)
        self.assertIn('.tmap-panel-scroll:hover { scrollbar-width: thin; }', block)
        self.assertIn('overflow-y: auto', block)


class InteractiveTourTests(SimpleTestCase):
    """Обучение требует действий, а не досматривания.

    ⚠️ ПРЕЖНИЙ ТУР САМ ДВИГАЛ КАМЕРУ И САМ ДЕЛАЛ ПОКАЗАТЕЛЬНЫЙ ВЫБОР, а
    человек нажимал «дальше» пять раз. Руками он к карте так и не
    прикасался — и закрывал обучение, не научившись. Теперь каждый шаг ждёт
    настоящего действия и засчитывается слушателем этого действия.
    """

    JS = pathlib.Path('catalog/static/catalog/js/topic_map.js')
    CSS = pathlib.Path('catalog/static/catalog/css/topic_map.css')
    TPL = pathlib.Path('catalog/templates/catalog/topic_map.html')

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.src = cls.JS.read_text(encoding='utf-8')

    def test_tour_version_is_bumped_so_returning_people_see_it_once(self):
        """Логика шагов изменилась целиком — значит и ключ другой.

        Оставь прежний ключ, и тот, кто видел рассказ, не увидит практики
        никогда: флаг в localStorage у него уже стоит.
        """
        self.assertIn("var TOUR_KEY = 'weconomics.map.tour.v2';", self.src)

    def test_every_step_waits_for_a_real_action(self):
        """Пять шагов — пять условий `want`, и ни одного «показать самому».

        `go:` у шага означал «тур сам сделает это за человека» — ровно то, от
        чего уходим. Появится снова — шаг опять станет роликом.
        """
        tour = self.src[self.src.index('var TOUR = ['):]
        tour = tour[:tour.index('\n];')]
        self.assertEqual(tour.count('want: function'), 5)
        self.assertEqual(tour.count('    t: '), 5)
        self.assertNotIn('go: function', tour)

    def test_steps_are_counted_by_events_not_by_a_button(self):
        """Кнопки «Дальше» нет; шаг двигают сообщения из мест взаимодействия.

        Каждое `tourNotice` стоит в том обработчике, где действие реально
        происходит: перетаскивание, колесо, наведение, приход по линии, выбор.
        """
        html = self.client.get('/catalog/map/').content.decode('utf-8')
        self.assertNotIn('>Дальше<', html)
        self.assertIn('Пропустить шаг', html)
        for call in ("tourNotice('drag'", "tourNotice('zoom'", "tourNotice('pick'",
                     "tourNotice(viaRoute ? 'walk' : 'node'"):
            # ⚠️ Сообщение об ошибке короткое нарочно: подставь сюда весь
            # файл — и провал теста утонет в 150 КБ исходника.
            self.assertTrue(call in self.src,
                            'действие никто не засчитывает: %s' % call)

    def test_tour_overlay_does_not_swallow_the_cursor(self):
        """Слой тура не ловит курсор — иначе работать по карте нельзя.

        Пока тур только рассказывал, слой на всю страницу был безобиден.
        Теперь каждый шаг требует перетаскивания, колеса и наведения ПО
        ХОЛСТУ, и слой перехватывал бы их все.
        """
        css = self.CSS.read_text(encoding='utf-8')
        layer = css[css.index('.tmap-tour {'):]
        layer = layer[:layer.index('}')]
        self.assertIn('pointer-events: none', layer)
        self.assertIn('.tmap-tour-card { pointer-events: auto; }', css)

    def test_tour_card_stands_in_the_free_corner(self):
        """Карточка больше не закрывает нижний левый угол графа.

        Слева внизу кнопки масштаба, сверху шапка с поиском, справа за краем
        холста панель с результатом. Свободен правый нижний угол самого
        холста — от него и считаем.
        """
        place = self.src[self.src.index('function placeTourCard()'):]
        place = place[:place.index('\n}')]
        self.assertIn('box.right - cw', place)
        self.assertIn('box.bottom - ch', place)


class LayoutLabelsAndFontTests(SimpleTestCase):
    """Раскладка просторнее, ориентиры живут с поворотом, шрифт общий с сайтом."""

    JS = pathlib.Path('catalog/static/catalog/js/topic_map.js')
    TOKENS = pathlib.Path('templates/_tokens.html')

    _rgb = staticmethod(NodeColourContrastTests._rgb)
    _luminance = staticmethod(NodeColourContrastTests._luminance)
    _contrast = classmethod(NodeColourContrastTests._contrast.__func__)
    _token = staticmethod(NodeColourContrastTests._token)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.src = cls.JS.read_text(encoding='utf-8')
        tokens = cls.TOKENS.read_text(encoding='utf-8')
        cut = tokens.index('[data-theme="dark"]')
        cls.tokens = {'светлая': tokens[:cut], 'тёмная': tokens[cut:]}

    def test_tag_crown_stays_roomy(self):
        """Венец тегов — главный рычаг тесноты, и он замерен.

        Венец это длина связи тема→тег. Поднять вместо него отталкивание
        бесполезно: обзор вписывает облако в холст, и равномерно раздутая
        раскладка возвращается на экран того же размера — замер показал ровно
        ноль изменений. А венец +20 % убрал треть тесноты: узлов, у которых
        сосед ближе 6 px, стало 32 из 372 вместо 46.
        """
        found = re.search(r'return ([\d.]+) \+ ([\d.]+) \* count;', self.src)
        self.assertIsNotNone(found, 'формула венца тегов пропала')
        base, per_tag = float(found.group(1)), float(found.group(2))
        self.assertGreaterEqual(base, 55, 'венец ужался обратно: %s' % base)
        self.assertGreaterEqual(per_tag, 6.6, 'венец ужался обратно: %s' % per_tag)

    def test_region_labels_depend_on_the_current_turn(self):
        """Набор надписей-ориентиров пересчитывается по глубине скопления.

        ⚠️ РАНЬШЕ ВСЕ СЕМЬ ГОРЕЛИ ОДИНАКОВО И ВСЕГДА. Сцена поворачивается,
        скопления меняются местами, а подписи стояли как вкопанные; надпись
        уехавшего за граф раздела проецировалась в середину экрана поверх
        чужих узлов. Теперь вес надписи считается от глубины её скопления в
        ТЕКУЩЕЙ ориентации, а ушедшее за спину не рисуется вовсе.
        """
        self.assertIn('GROUP_DEPTH_FLOOR', self.src)
        self.assertIn('GROUP_DEPTH_DROP', self.src)
        # доля считается от размаха кадра, а не от абсолютной глубины
        self.assertIn('(zMax - a.pz) / span', self.src)

    def test_canvas_labels_use_the_site_font(self):
        """Подписи на холсте пишутся тем же шрифтом, что весь сайт.

        ⚠️ ЭТО ЛОВИТСЯ ГЛАЗОМ ПЛОХО. Системный гротеск похож на Montserrat
        ровно настолько, чтобы разницу списали на сглаживание холста, —
        поэтому семейство обязано браться из токена, а не быть зашитым.
        """
        self.assertIn("cs.getPropertyValue('--font-ui')", self.src)
        font_call = self.src[self.src.index('function setLabelFont('):]
        font_call = font_call[:font_call.index('\n}')]
        self.assertIn('PAL.font', font_call)
        self.assertNotIn('-apple-system', font_call)

    def test_region_label_reads_as_one_colour_in_both_themes(self):
        """Ориентир в двух темах — один цвет, а не два похожих.

        ⚠️ ПРОВЕРЯЕТСЯ ТОН И НАСЫЩЕННОСТЬ, А НЕ КОНТРАСТ. Контраст обе версии
        проходили и раньше: тёмная давала 8,76 при пороге 4,5 — то есть вдвое
        громче нужного, и рядом со светлой читалась как другая краска
        (светлота 72 % против 42 %, насыщенность 57 % против 42 %). Порог
        сторожит соседний тест; этот сторожит УЗНАВАЕМОСТЬ.
        """
        import colorsys
        hues, sats = {}, {}
        for theme in ('светлая', 'тёмная'):
            red, green, blue = self._rgb(self._token(self.tokens[theme], 'map-region'))
            hue, light, sat = colorsys.rgb_to_hls(red / 255, green / 255, blue / 255)
            hues[theme] = hue * 360
            sats[theme] = sat * 100
        self.assertLess(
            abs(hues['светлая'] - hues['тёмная']), 8,
            'тон ориентира разошёлся: %.0f и %.0f' % (hues['светлая'], hues['тёмная']))
        self.assertLess(
            abs(sats['светлая'] - sats['тёмная']), 10,
            'насыщенность ориентира разошлась: %.0f%% и %.0f%%'
            % (sats['светлая'], sats['тёмная']))


class SelectionAndViewTests(SimpleTestCase):
    """Пять точечных правок карты: выбор, счётчик, сброс вида, толщина дороги.

    ⚠️ ПРОВЕРКИ ПО ТЕКСТУ ФАЙЛА — своего прогона JavaScript в проекте нет.
    Поведение снималось в браузере через `window.TMAP`; здесь сторожится то,
    потерю чего текстом заметить МОЖНО: единственная точка выбора, отсутствие
    захвата пары, «неизвестно» вместо нуля, возврат поворота и толщина
    главной дороги.
    """

    JS = pathlib.Path('catalog/static/catalog/js/topic_map.js')

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.src = cls.JS.read_text(encoding='utf-8')

    def test_lower_bound_note_is_gone_from_the_screen(self):
        """Строки «Оценка снизу: счётчик задан у N тегов из M» нет нигде.

        Это была служебная бухгалтерия, которую человек читает всегда, а
        относится она к случаю, который может его и не касаться. Неполнота
        теперь проговаривается в самом счётчике и только когда она есть.
        """
        html = self.client.get('/catalog/map/').content.decode('utf-8')
        self.assertNotIn('Оценка снизу', html)
        self.assertNotIn('tmap-note', html)

    def test_selection_has_exactly_one_entry_point(self):
        """Выбор идёт через `selectNode`, и второго пути нет.

        ⚠️ ЭТО НЕ ПРИДИРКА К ИМЕНИ. Каждый обход общей функции заново решает,
        что значит «выбрать тег», и решает по-своему — ровно так и появился
        дефект «кликнул тег, выбралась вся тема».
        """
        self.assertIn('function selectNode(', self.src)
        self.assertNotIn('togglePick', self.src)

    def test_click_never_takes_both_ends_of_a_line(self):
        """Клик выбирает РОВНО ОДИН узел.

        Прежний код на клике по линии писал в `picked` оба её конца, и у тега
        в выбранное молча уезжала его тема. Сторожим сам приём: двух присвоений
        подряд быть не должно.
        """
        self.assertNotIn('picked[r2.a.id] = true', self.src)
        self.assertNotIn('picked[r2.b.id] = true', self.src)

    def test_click_aims_at_a_node_not_at_a_line(self):
        """У клика свой прицел, шире чем у наведения.

        Кружок тега 3–5 px: пока клик разбирался тем же pick(), что и
        хождение, промах на шесть пикселей отдавал его линии. Клик обязан
        сначала спросить hitTest с его допуском в 10 px.
        """
        after = self.src[self.src.index("addEventListener('pointerup'"):]
        head = after[:after.index('touchActivity()')]
        self.assertIn('hitTest(', head)
        self.assertLess(head.index('hitTest('), head.index('selectNode('))

    def test_missing_counter_is_called_unknown_not_zero(self):
        """«Примерно 0 задач» читается как «ничего не нашлось».

        А означает противоположное: у тега счётчика ещё нет. Суммируются
        только теги с заданным счётчиком; если таких среди выбранных нет —
        так и пишем.
        """
        self.assertIn('число задач пока неизвестно', self.src)
        self.assertNotIn('sum += byId[id].c || 0', self.src)

    def test_reset_returns_the_whole_view_including_the_turn(self):
        """«Вернуть обзор» возвращает и поворот.

        Карта тихо вращается сама; сброс без yaw возвращал не тот вид, с
        которого человек начал. Двойной клик по пустому месту делает то же
        самое — привычный жест «покажи всё целиком».
        """
        reset = self.src[self.src.index('function resetView()'):]
        reset = reset[:reset.index('\n}')]
        self.assertIn('cam.yaw = START_YAW', reset)
        self.assertIn('cam.pitch = START_PITCH', reset)
        self.assertIn('cam.zoomTarget = 1', reset)

        dbl = self.src[self.src.index("addEventListener('dblclick'"):]
        dbl = dbl[:dbl.index('});')]
        self.assertIn('else resetView();', dbl)

    def test_home_road_is_visibly_thicker_than_the_others(self):
        """Дорога тега к СВОЕЙ теме толще прочих подсвеченных связей.

        Она отвечает на вопрос «откуда этот тег» и среди десятка подсвеченных
        линий обязана читаться первой; одной с ними толщиной терялась.
        Разница должна быть заметной, а не десятой долей пикселя.
        """
        found = re.search(r'var ROAD_HOME_WIDTH = ([\d.]+);', self.src)
        self.assertIsNotNone(found, 'толщина главной дороги больше не названа')
        home = float(found.group(1))
        self.assertGreaterEqual(
            home, 3.0,
            'главная дорога %s px — на глаз не отличается от обычных 2,2' % home)


class PreviewModeTests(SimpleTestCase):
    """Встраиваемый режим карты: маленькое окно для чужого экрана.

    ⚠️ ЭТО ПРОВЕРКИ ПО ТЕКСТУ ФАЙЛА, И ЭТО ОСОЗНАННО. Своего прогона
    JavaScript в проекте нет, поведение снимается глазами и через
    `TopicMapPreview.all()[0].stats()` в браузере. Здесь сторожатся ровно те
    свойства, потерю которых текстом заметить МОЖНО: подписей нет, курсор не
    слушается, цикл кадров снимается вне экрана и при отключённом движении,
    точка подключения на месте, вес не разросся до полного движка.

    Требования — решение владельца от 01.09.2026 «Предпросмотр карты тем:
    сейчас готовим только место и архитектуру»
    (https://app.notion.com/p/3ceb11c92bc18146a098f0e93526c347).
    """

    JS = pathlib.Path('catalog/static/catalog/js/topic_map_preview.js')
    CSS = pathlib.Path('catalog/static/catalog/css/topic_map_preview.css')
    FULL_JS = pathlib.Path('catalog/static/catalog/js/topic_map.js')

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.src = cls.JS.read_text(encoding='utf-8')

    def test_preview_draws_no_labels_at_all(self):
        """Ни одной подписи: только узлы и связи.

        Подпись на холсте рисуется единственным способом — `fillText` или
        `strokeText`. Нет их в файле — нет и подписей, и никакая правка не
        протащит их незаметно.
        """
        for call in ('fillText', 'strokeText', 'measureText'):
            self.assertNotIn(
                call, self.src,
                'в предпросмотре появился вывод текста: %s' % call)

    def test_preview_listens_to_no_pointer_events(self):
        """Курсор на карту не влияет — и это держится устройством.

        У холста `pointer-events: none`, а обработчиков указателя в модуле
        нет вовсе. Появится хоть один — вернётся и остановка вращения при
        наведении, ради отсутствия которой режим и заводился.
        """
        self.assertIn("canvas.style.pointerEvents = 'none'", self.src)
        for event in ('pointerdown', 'pointermove', 'pointerup', 'wheel',
                      'mouseover', 'mousemove', 'dblclick'):
            self.assertNotIn(
                "'%s'" % event, self.src,
                'предпросмотр начал слушать курсор: %s' % event)

    def test_preview_stops_off_screen_and_without_motion(self):
        """Вне экрана и при prefers-reduced-motion кадры не просто одинаковые,
        а не запрашиваются вовсе: заявка на кадр снимается."""
        self.assertIn('IntersectionObserver', self.src)
        self.assertIn('cancelAnimationFrame', self.src)
        self.assertIn('prefers-reduced-motion', self.src)

    def test_preview_waits_for_the_host_screen(self):
        """Данные тянутся после отрисовки экрана-хозяина, а не вместе с ним."""
        self.assertIn('requestIdleCallback', self.src)
        self.assertIn("'load'", self.src)

    def test_preview_exposes_the_mount_point(self):
        """Точка подключения — то, ради чего режим и делался.

        Другая сессия монтирует предпросмотр в свой блок, не заглядывая
        внутрь движка: либо атрибутом `data-tmap-preview`, либо вызовом
        `TopicMapPreview.mount(el, opts)`.
        """
        self.assertIn('window.TopicMapPreview', self.src)
        self.assertIn('data-tmap-preview', self.src)
        for name in ('mount:', 'scan:', 'version:'):
            self.assertIn(name, self.src)

    def test_preview_stays_far_lighter_than_the_full_engine(self):
        """Вес — весь смысл отдельного файла.

        Полный движок около 150 КБ, и тянуть его на каждое открытие каталога
        ради вращающегося окошка дорого (это и есть причина решения). Если
        предпросмотр однажды дорастёт до четверти движка, значит в него
        переехало то, чего он не показывает.
        """
        small = len(self.src.encode('utf-8'))
        big = len(self.FULL_JS.read_text(encoding='utf-8').encode('utf-8'))
        self.assertLess(
            small, big / 4,
            'предпросмотр разросся: %d байт против %d у полной карты'
            % (small, big))

    def test_preview_styles_live_in_their_own_file(self):
        """Стили предпросмотра отдельно от стилей полной карты: экрану-хозяину
        не нужны шапка, панель, тур и нижняя полоса."""
        css = self.CSS.read_text(encoding='utf-8')
        self.assertIn('.tmap-preview', css)
        self.assertIn('pointer-events: none', css)

    def test_demo_page_shows_two_preview_blocks(self):
        """Стенд приёмки: один блок виден сразу, второй лежит ниже экрана.

        Второй нужен именно для проверки ленивости: пока до него не
        доскроллили, данные не запрашиваются вовсе.
        """
        response = self.client.get('/catalog/map/preview-demo/')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        self.assertEqual(html.count('class="tmap-preview"'), 2)
        self.assertEqual(len(re.findall(r'data-tmap-preview(?![-\w])', html)), 2)
        self.assertIn('topic_map_preview.js', html)
        self.assertIn('topic_map_preview.css', html)

    def test_demo_blocks_lead_to_the_full_map(self):
        """Клик по блоку ведёт на полную карту — адрес берётся из маршрута,
        а не переписан строкой."""
        html = self.client.get('/catalog/map/preview-demo/').content.decode('utf-8')
        self.assertIn('href="/catalog/map/"', html)
