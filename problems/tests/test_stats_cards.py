"""
Карточки статистики после ревью 16.08 (фаза 5).

5.1 «Рост уровня» → «Динамика уровня».
5.2 Подписи шкалы радара уходят с вертикальной оси и садятся на подложку.
5.3 Кольцо «Ответы за период» убрано: оно повторяло карточку «Доля верных».
5.4 «Откуда задачи» → «Где решаешь», розовая пара вместо зелёного с красным.
5.5 Новая карточка «По сложности».
5.6 В блоке игры — тот же знак, что на её странице.
5.7 Кружок счётчика у вкладки «Задания» — красный. Контраст СЧИТАЕТСЯ, а
    не осматривается: та же проверка, что делали для янтаря.
"""
import os
import re
from datetime import timedelta

from django.template.loader import render_to_string
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from problems import stats
from problems.models import LearningEvent, Problem, StudentGroup, User

JS = os.path.join('problems', 'static', 'platform', 'stats.js')


def read(*parts):
    with open(os.path.join(*parts), encoding='utf-8') as handle:
        return handle.read()


def luminance(colour):
    colour = colour.lstrip('#')
    parts = [int(colour[i:i + 2], 16) / 255 for i in (0, 2, 4)]

    def channel(value):
        return (value / 12.92 if value <= 0.03928
                else ((value + 0.055) / 1.055) ** 2.4)

    red, green, blue = [channel(v) for v in parts]
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def ratio(first, second):
    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def make_student(username='cards_student'):
    user = User.objects.create_user(username=username, password='x12345678',
                                    email='%s@t.local' % username)
    user.role = 'student'
    user.save()
    return user


class DifficultyCardTests(TestCase):
    """5.5 — карта сложности на месте убранного кольца."""

    def setUp(self):
        self.user = make_student()
        self.now = timezone.now()

    def event(self, level, kind='solved'):
        # ⚠️ Событие БЕЗ ссылки на задачу в статистику не идёт вовсе
        # (`_problem_events`): служебные отметки «работа сдана» — не ответы.
        problem = Problem.objects.create(title='З%d' % level,
                                         statement='Условие',
                                         status=Problem.Status.PUBLISHED)
        row = LearningEvent.objects.create(user=self.user, event_type=kind,
                                           source='homework',
                                           catalog_problem=problem,
                                           difficulty=level)
        LearningEvent.objects.filter(pk=row.pk).update(
            created_at=self.now - timedelta(days=1))

    def test_five_levels_always(self):
        """Пустой уровень остаётся столбиком: провал в шкале — это тоже факт."""
        card = stats.difficulty_split(self.user, 'month', self.now)
        self.assertEqual([r['level'] for r in card['levels']], [1, 2, 3, 4, 5])

    def test_counts_and_accuracy(self):
        self.event(3)
        self.event(3)
        self.event(3, 'failed')
        card = stats.difficulty_split(self.user, 'month', self.now)
        third = card['levels'][2]
        self.assertEqual(third['attempted'], 3)
        self.assertEqual(third['solved'], 2)
        self.assertEqual(third['accuracy'], 67)

    def test_untouched_level_has_no_accuracy_not_zero(self):
        """⚠️ «0%» там, где не пробовали, читается как провал, которого нет."""
        self.event(2)
        card = stats.difficulty_split(self.user, 'month', self.now)
        self.assertIsNone(card['levels'][4]['accuracy'])

    def test_average_is_written_with_a_comma(self):
        self.event(1)
        self.event(4)
        card = stats.difficulty_split(self.user, 'month', self.now)
        self.assertEqual(card['average'], 2.5)
        self.assertIn('2,5', card['average_text'])
        self.assertNotIn('.', card['average_text'])

    def test_empty_state_says_so(self):
        card = stats.difficulty_split(self.user, 'month', self.now)
        self.assertEqual(card['total'], 0)
        self.assertEqual(card['average_text'], '')


class StatsPageCardsTests(TestCase):

    def setUp(self):
        # ⚠️ СВОДКА КЭШИРУЕТСЯ ПО (пользователь, период) НА ПЯТЬ МИНУТ, а в
        # прогоне номера пользователей переиспользуются между классами:
        # без чистки этот класс читал бы сводку чужого теста и краснел
        # ТОЛЬКО в полном прогоне. Та же ловушка, что с индексом поиска.
        cache.clear()
        self.user = make_student('cards_page')
        self.client.force_login(self.user)

    def page(self):
        return self.client.get('/profile/stats/').content.decode()

    def test_level_card_renamed(self):
        body = self.page()
        self.assertIn('Динамика уровня', body)
        self.assertNotIn('>Рост уровня<', body)

    def test_answers_ring_is_gone(self):
        body = self.page()
        self.assertNotIn('Ответы за период', body)
        self.assertNotIn('chart-ring', body)

    def test_sources_card_renamed(self):
        body = self.page()
        self.assertIn('Где решаешь', body)
        self.assertNotIn('Откуда задачи', body)

    def test_difficulty_card_is_there(self):
        body = self.page()
        self.assertIn('По сложности', body)
        self.assertIn('карта сложности', body)

    def test_game_block_carries_the_logo(self):
        """5.6 — знак тот же, что на странице игры: одна разметка."""
        body = self.page()
        self.assertIn('rush-logo', body)
        self.assertIn('>RUSH<', body)

    def test_logo_markup_lives_in_one_place(self):
        """⚠️ Копия знака разошлась бы с оригиналом при первой правке."""
        game = read('game', 'templates', 'game', 'game.html')
        self.assertIn('_rush_logo.html', game)
        self.assertNotIn('<span class="rush">RUSH</span>', game)


class ChartColoursTests(TestCase):
    """5.4 — розовая пара вместо зелёного с красным."""

    def test_pink_pair_in_both_cards(self):
        source = read(JS)
        piece = source[source.index('var hit = colors.accent'):]
        self.assertIn("var miss = colors.accent", piece)
        for chart in ('chart-difficulty', 'chart-sources'):
            block = piece[piece.index("make('%s'" % chart):]
            block = block[:block.index('});')]
            self.assertIn('backgroundColor: hit', block, chart)
            self.assertIn('backgroundColor: miss', block, chart)
            self.assertNotIn('colors.green', block, chart)
            self.assertNotIn('colors.error', block, chart)

    def test_verdict_colours_are_free_for_verdicts(self):
        """Зелёный и красный остаются за вердиктом задачи, а не за долями."""
        source = read(JS)
        after = source[source.index('var hit = colors.accent'):]
        self.assertNotIn('colors.green', after)


class RadarTicksTests(TestCase):
    """5.2 — подписи шкалы уходят с вертикальной оси."""

    def test_builtin_ticks_are_off_and_we_draw_our_own(self):
        source = read(JS)
        radar = source[source.index("make('chart-radar'"):]
        radar = radar[:radar.index("make('chart-difficulty'")]
        # ⚠️ Пересчитано (ревью 17.08, п. 4.1): рядом с `display: false`
        # теперь стоит шаг сетки. Проверка про то, что ВСТРОЕННЫЕ подписи
        # выключены, а рисуем мы сами, — она и осталась.
        self.assertIn('display: false', radar)
        self.assertIn('stepSize: 20', radar)
        self.assertIn('plugins: [radarTicks]', radar)

    def test_five_rings_and_dots_on_vertices(self):
        """Пять делений вместо десяти и точка на каждой вершине."""
        source = read(JS)
        radar = source[source.index("make('chart-radar'"):]
        radar = radar[:radar.index("make('chart-difficulty'")]
        self.assertIn('stepSize: 20', radar)
        self.assertIn('pointRadius: 3.5', radar)

    def test_radar_box_is_tall(self):
        """Радиус 110 берётся из высоты контейнера, а не из настроек."""
        page = read('problems', 'templates', 'platform', 'stats.html')
        block = page[page.index('Разделы экономики'):]
        block = block[:block.index('</div>', block.index('chart-radar'))]
        self.assertIn('chart-box tall', block)

    def test_labels_sit_on_a_backdrop_of_the_card(self):
        source = read(JS)
        plugin = source[source.index('var radarTicks = {'):]
        plugin = plugin[:plugin.index("make('chart-radar'")]
        self.assertIn('fillRect', plugin)
        self.assertIn('opts.backdrop', plugin)
        self.assertIn('Math.PI / count', plugin)


class CounterIsRedTests(TestCase):
    """5.7 — кружок счётчика красный, и контраст СЧИТАЕТСЯ."""

    def test_counter_is_filled_with_error_colour(self):
        kit = read('templates', '_kit.html')
        rules = kit[kit.index('.k-count {'):]
        rules = rules[:rules.index('}')]
        self.assertIn('background: var(--error)', rules)
        self.assertIn('color: var(--on-error)', rules)
        self.assertNotIn('amber', rules)

    def test_ink_token_exists_in_both_themes(self):
        tokens = read('templates', '_tokens.html')
        light, dark = tokens.split('[data-theme="dark"]')
        for part in (light, dark):
            self.assertIn('--on-error:', part)

    def test_contrast_passes_aa_in_both_themes(self):
        """⚠️ Считаем прямо здесь: «проверено на глаз» не проверка.

        В тёмной теме `--error` СВЕТЛЫЙ, и белые чернила дали бы 2,78:1 —
        хуже нормы. Поэтому чернила меняются вместе с темой.
        """
        tokens = read('templates', '_tokens.html')
        light, dark = tokens.split('[data-theme="dark"]')
        for part, name in ((light, 'светлая'), (dark, 'тёмная')):
            red = re.search(r'--error:\s*(#[0-9a-fA-F]{6})', part).group(1)
            ink = re.search(r'--on-error:\s*(#[0-9a-fA-F]{6})',
                            part).group(1)
            self.assertGreaterEqual(round(ratio(ink, red), 2), 4.5, name)

    def test_counter_still_hides_at_zero(self):
        """Пустой кружок — не «ноль дел», а мусор на экране."""
        tutor = User.objects.create_user('cnt_tutor', password='x',
                                         role='teacher')
        group = StudentGroup.objects.create(name='Счётчик', teacher=tutor)
        self.client.force_login(tutor)
        body = self.client.get('/teacher/groups/%d/' % group.pk
                               ).content.decode()
        self.assertNotIn('class="k-count">0<', body)
