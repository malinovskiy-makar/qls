"""
Блок «Активность на сайте» — один вместо трёх (ревью 16.08, фаза 4).

⚠️ ЧТО БЫЛО. «Календарь занятий», «По дням недели» и «По часам» — три
карточки об одном и том же в разных концах страницы. Календарь ВСЕГДА
показывал год: человек выбирал наверху «Неделю», а видел двенадцать
месяцев, и переключатель периода стоял рядом зря. Цвет клетки считался
долей от ЛИЧНОГО пика, поэтому легенда честно не могла сказать, сколько
это минут: у одного человека тёмная клетка — сорок задач, у другого одна.

Главная проверка файла — согласие чисел: сетка, подпись под ней и
карточка «Минут на сайте» обязаны говорить ОДНО И ТО ЖЕ.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from problems import stats
from problems.models import LearningEvent, User


def make_student(username='act_student'):
    user = User.objects.create_user(username=username, password='x12345678',
                                    email='%s@t.local' % username)
    user.role = 'student'
    user.save()
    return user


class ActivityGridTests(TestCase):

    def setUp(self):
        self.user = make_student()
        self.now = timezone.now()

    def event(self, when, kind='solved', source='homework'):
        row = LearningEvent.objects.create(user=self.user, event_type=kind,
                                           source=source)
        LearningEvent.objects.filter(pk=row.pk).update(created_at=when)
        return row

    def busy_day(self, days_ago, count=6, step_minutes=4):
        """Несколько событий подряд — то есть настоящие минуты на сайте."""
        base = self.now - timedelta(days=days_ago)
        for index in range(count):
            self.event(base + timedelta(minutes=index * step_minutes))

    def test_grid_covers_the_chosen_period(self):
        """⚠️ ГЛАВНОЕ: сетка подчиняется переключателю периода."""
        sizes = {}
        for period in ('day', 'week', 'month'):
            grid = stats.activity_grid(self.user, period, self.now)
            sizes[period] = len([c for c in grid['cells'] if c['inside']])
        self.assertLess(sizes['day'], sizes['week'])
        self.assertLess(sizes['week'], sizes['month'])

    def test_all_time_is_a_compressed_year(self):
        grid = stats.activity_grid(self.user, 'all', self.now)
        self.assertEqual(grid['mode'], 'year')
        self.assertGreater(len(grid['cells']), 360)

    def test_grid_starts_on_monday(self):
        grid = stats.activity_grid(self.user, 'month', self.now)
        self.assertEqual(grid['cells'][0]['date'].weekday(), 0)

    def test_days_outside_the_period_are_marked(self):
        grid = stats.activity_grid(self.user, 'week', self.now)
        self.assertTrue(any(not c['inside'] for c in grid['cells']))
        for cell in grid['cells']:
            if not cell['inside']:
                self.assertEqual(cell['minutes'], 0)

    def test_today_is_marked(self):
        grid = stats.activity_grid(self.user, 'week', self.now)
        today = timezone.localtime(self.now).date()
        marked = [c for c in grid['cells'] if c['is_today']]
        self.assertEqual(len(marked), 1)
        self.assertEqual(marked[0]['date'], today)

    def test_level_is_minutes_not_a_share_of_personal_peak(self):
        """⚠️ Границы общие для всех, иначе легенда ничего не мерит."""
        self.assertEqual(stats.minutes_level(0), 0)
        self.assertEqual(stats.minutes_level(1), 1)
        self.assertEqual(stats.minutes_level(15), 1)
        self.assertEqual(stats.minutes_level(16), 2)
        self.assertEqual(stats.minutes_level(40), 2)
        self.assertEqual(stats.minutes_level(90), 3)
        self.assertEqual(stats.minutes_level(200), 4)

    def test_legend_names_the_same_edges(self):
        grid = stats.activity_grid(self.user, 'month', self.now)
        self.assertEqual(grid['legend'],
                         ['0', 'до 15', 'до 40', 'до 90', 'больше'])
        for edge in stats.MINUTE_STEPS:
            self.assertTrue(any(str(edge) in name for name in grid['legend']))

    def test_total_matches_the_minutes_card(self):
        """⚠️ ГЛАВНАЯ ПРОВЕРКА: два числа об одном не имеют права разойтись.

        Клетка округляется до минуты сама по себе, час на графике — сам по
        себе, и суммы трёх разложений одного времени расходятся на единицы.
        Итог печатается ОДИН и берётся у карточки.
        """
        self.busy_day(2)
        self.busy_day(5)
        grid = stats.activity_grid(self.user, 'month', self.now)
        card = stats.minutes_on_site(self.user, 'month', self.now)
        self.assertEqual(grid['facts'][1]['minutes'], card)

    def test_hint_speaks_the_same_total(self):
        self.busy_day(1)
        data = stats.full_stats(self.user, 'month', self.now,
                                use_cache=False)
        self.assertIn(str(data['activity']['facts'][1]['minutes']),
                      data['time_hint'])

    def test_facts_count_working_days_not_all_days(self):
        """«В средний рабочий день» делится на дни С ЗАНЯТИЯМИ."""
        self.busy_day(1, count=10)
        grid = stats.activity_grid(self.user, 'month', self.now)
        worked = [c for c in grid['cells'] if c['inside'] and c['minutes']]
        self.assertEqual(len(worked), 1)
        average = grid['facts'][2]['value']
        self.assertEqual(average, '%d мин' % grid['facts'][1]['minutes'])

    def test_empty_history_shows_a_dash_not_zero(self):
        """Ноль рабочих дней — прочерк: делить не на что."""
        grid = stats.activity_grid(self.user, 'month', self.now)
        self.assertEqual(grid['facts'][2]['value'], '—')

    def test_best_streak(self):
        for days_ago in (2, 3, 4, 8):
            self.busy_day(days_ago)
        grid = stats.activity_grid(self.user, 'month', self.now)
        self.assertEqual(grid['facts'][3]['value'], '3 дня')

    def test_solved_count_excludes_the_game(self):
        """Игра даёт минуты, но не «решено» — как в карточках наверху."""
        when = self.now - timedelta(days=1)
        self.event(when, 'solved', 'game')
        self.event(when + timedelta(minutes=2), 'solved', 'homework')
        grid = stats.activity_grid(self.user, 'week', self.now)
        day = timezone.localtime(when).date()
        cell = [c for c in grid['cells'] if c['date'] == day][0]
        self.assertEqual(cell['solved'], 1)
        self.assertGreater(cell['minutes'], 0)


class HintTests(TestCase):
    """Подпись под блоком говорит о том же, о чём блок, — о минутах."""

    def rows(self, pairs):
        return [{'hour': h, 'value': pairs.get(h, 0),
                 'text': stats.minutes_text(pairs.get(h, 0))}
                for h in range(24)]

    def test_hint_is_about_minutes(self):
        text = stats.busy_time_hint(self.rows({19: 100, 20: 60, 21: 37}),
                                    'month')
        self.assertIn('минут', text)
        self.assertIn('за месяц', text)
        self.assertNotIn('верных', text)
        self.assertNotIn('попыт', text)

    def test_hint_names_the_window(self):
        text = stats.busy_time_hint(self.rows({19: 100, 20: 60}), 'month')
        self.assertIn('19:00', text)
        self.assertIn('вечером', text)

    def test_empty_history_says_so_without_numbers(self):
        text = stats.busy_time_hint(self.rows({}), 'week')
        self.assertNotIn('0 минут', text)
        self.assertIn('Пока', text)


class ActivityPageTests(TestCase):
    """Разметка: три блока свелись в один, и его рисует сервер."""

    def setUp(self):
        self.user = make_student('act_page')
        self.client.force_login(self.user)

    def test_page_shows_one_block(self):
        page = self.client.get('/profile/stats/')
        self.assertEqual(page.status_code, 200)
        body = page.content.decode()
        self.assertIn('Активность на сайте', body)
        self.assertNotIn('Календарь занятий', body)
        self.assertNotIn('Когда занимаешься', body)

    def test_cells_carry_a_day_number_and_a_hint(self):
        body = self.client.get('/profile/stats/').content.decode()
        self.assertIn('class="act-grid', body)
        self.assertIn('data-hint=', body)
        self.assertIn('минут в день:', body)

    def test_period_switch_gets_ready_markup_from_the_server(self):
        """⚠️ Вторую раскладку тех же дней на клиенте не заводим."""
        answer = self.client.get('/profile/stats/data/?period=week',
                                 HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(answer.status_code, 200)
        self.assertIn('act-grid', answer.json()['activityHtml'])

    def test_old_year_heatmap_is_gone_from_this_page(self):
        """⚠️ Ищем РАЗМЕТКУ, а не имя класса: стили вклеены в страницу.

        Правило проекта, нарушенное здесь при первом же написании теста:
        `.heat-scroll` живёт в общей таблице стилей и приезжает на страницу
        вместе с ней — теплокарта за год осталась у репетитора и родителя.
        """
        body = self.client.get('/profile/stats/').content.decode()
        self.assertNotIn('class="heat-scroll"', body)
        self.assertNotIn('<svg width=', body.split('act-grid')[0])

    def test_teacher_and_parent_screens_keep_their_calendar(self):
        """Календарь за год живёт дальше там, где он и был."""
        self.assertTrue(callable(stats.activity_calendar))
