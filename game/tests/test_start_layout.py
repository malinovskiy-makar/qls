# -*- coding: utf-8 -*-
u"""Стартовый экран Wecon Rush — «стартовый экран аркады» (ADR 0108).

Решение владельца 17.09.2026, макеты `claude/mockups/wecon_rush_20260917/Main`,
`Student`, `Dark`, `Mobile`. Здесь разметка, данные сервера и код, на которых
держится экран; поведение в браузере (нет прокрутки на 1440×800, клавиши,
проверка кода, адреса ?mode= и ?duel=) меряет
`test_browser_layout.StartScreenBrowserTest`.
"""
import datetime
import re

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from game import config, daily
from game.models import GameQuestion, GameResult, GameSet
from game.tests.test_page_js import inline_js, page_source
from game.tests.test_sets import make_set
from problems.models import Problem, User

MAIN_MODES = ('bullet', 'blitz', 'rapid', 'classic')


def fill_pool(modes=MAIN_MODES, n=None):
    u"""По вопросу-другому на режим: вкладка есть только у режима с пулом."""
    n = n or config.MIN_PLAYABLE + 1
    for key in modes:
        qtype = config.MODES[key]['question_type']
        for i in range(n):
            problem = Problem.objects.create(
                title='', statement='Вопрос %s %d?' % (qtype, i), answer='',
                problem_type='тест: один ответ', status='published')
            GameQuestion.objects.create(
                problem=problem, question_type=qtype, question='Вопрос %s №%d?' % (qtype, i),
                options=['а', 'б', 'в', 'г'], correct_index=0, difficulty=2,
                topics=[], lang='ru')


def start_section(html):
    u"""Разметка одного стартового экрана — без окон, которые лежат ниже."""
    i = html.index('<section id="screen-start"')
    return html[i:html.index('<section id="screen-play"')]


class StartScreenMarkupTests(TestCase):
    def setUp(self):
        fill_pool()

    def page(self):
        return self.client.get(reverse('game:page')).content.decode('utf-8')

    def test_three_zones_for_a_guest(self):
        html = start_section(self.page())
        self.assertEqual(html.count('class="mtab"'), 4, 'вкладок режимов не четыре')
        self.assertIn('id="play-btn"', html)
        self.assertEqual(len(re.findall(r'role="tab" id="tab-(board|stats)"', html)), 2)
        self.assertIn('>Таблица</button>', html)
        self.assertIn('>Статистика</button>', html)
        self.assertEqual(html.count('class="st-card cell'), 4, 'ячеек полосы не четыре')

    def test_what_the_owner_removed_is_gone(self):
        html = start_section(self.page())
        for gone in ('rush-head', 'rush-sub', 'rush-count',        # большой логотип и лозунг
                     'Добавить фильтры',                            # кнопка и старый ряд чипов
                     'filter-chips',
                     'lb-modes', 'lb-tab',                          # ряд режимов в таблице
                     'entry-records', 'Мои рекорды</b>',            # плитка «Мои рекорды»
                     'Дуэль с другом', 'lb-login'):                 # ссылки-дубли и «Войти» в таблице
            self.assertNotIn(gone, html, gone)

    def test_mode_without_questions_has_no_tab(self):
        GameQuestion.objects.filter(question_type=config.MODES['rapid']['question_type']).delete()
        html = start_section(self.page())
        self.assertEqual(html.count('class="mtab"'), 3)
        self.assertNotIn('data-mode="rapid"', html)

    def test_tab_caption_is_duration_and_pool(self):
        html = start_section(self.page())
        n = config.MIN_PLAYABLE + 1
        self.assertIn('1 мин · <span class="mtab-n">%d</span> вопр.' % n, html)
        self.assertIn('10 мин · <span class="mtab-n">%d</span> вопр.' % n, html)

    def test_guest_sees_login_line_under_the_board_and_no_quota(self):
        html = start_section(self.page())
        self.assertIn('Играть можно без входа, но в таблицу попадают только вошедшие.', html)
        self.assertIn('<a href="/login/?next=/game/">Войти</a>', html)
        self.assertNotIn('id="quota"', html)
        self.assertIn('id="local-records"', html)
        self.assertNotIn('id="records-open"', html)

    def test_student_sees_quota_stats_and_records_button(self):
        user = User.objects.create_user(username='arcade_student', password='p12345')
        self.client.force_login(user)
        html = start_section(self.page())
        self.assertIn('id="quota"', html)
        self.assertIn('зачётных раундов сегодня', html)
        self.assertIn('id="records-open"', html)
        self.assertNotIn('Играть можно без входа, но в таблицу', html)

    def test_how_points_popover_takes_numbers_from_config(self):
        html = start_section(self.page())
        base = sorted(config.BASE_BY_DIFFICULTY.values())
        self.assertIn('от %d очков за вопрос на 1★ до %d за 5★' % (base[0], base[-1]), html)
        self.assertIn('получает ×%s;' % ('%g' % config.SCOPE_MULTIPLIER).replace('.', ','), html)
        self.assertIn('точность ниже %d %%' % round(config.ACCURACY_FULL_AT * 100), html)


class DailyCellTests(TestCase):
    u"""Живая ячейка «Вызов дня»: анониму — сколько вызовов, вошедшему — сыграно N из 4."""

    def setUp(self):
        fill_pool()

    def cell(self):
        html = self.client.get(reverse('game:page')).content.decode('utf-8')
        i = html.index('id="daily-line"')
        return html[i:html.index('</p>', i)]

    def test_guest_line_has_no_streak_and_no_played(self):
        line = self.cell()
        self.assertIn('4 вызова на сегодня', line)
        self.assertNotIn('серия', line)
        self.assertNotIn('сыграно', line)

    def test_student_with_one_played_daily_today(self):
        user = User.objects.create_user(username='daily_one', password='p12345')
        gset = daily.get_daily_set('blitz')
        GameResult.objects.create(user=user, game_set=gset, mode='blitz', score=10)
        self.client.force_login(user)
        line = self.cell()
        self.assertIn('сыграно <b>1</b> из 4', line)
        self.assertIn('серия <b>1</b> день', line)

    def test_reset_moment_comes_from_the_server(self):
        html = self.client.get(reverse('game:page')).content.decode('utf-8')
        self.assertIn('data-reset-at="%s"' % daily.next_reset().isoformat(timespec='seconds'), html)


class SetCheckApiTests(TestCase):
    u"""`GET /game/api/set_check/?code=` — неверный код не уводит на 404 сайта."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        questions = [GameQuestion.objects.create(
            problem=Problem.objects.create(title='', statement='x', answer='',
                                           status='published'),
            question_type='single', question='В?', options=['а', 'б'],
            correct_index=0, difficulty=2, topics=[], lang='ru') for _ in range(3)]
        self.custom = make_set(questions, title='Контрольная')
        self.duel = make_set(questions, kind='duel', title='Дуэль')

    def get(self, code):
        return self.client.get(reverse('game:set_check'), {'code': code})

    def test_unknown_code(self):
        r = self.get('NOPE2345')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {'exists': False, 'url': ''})

    def test_set_code_leads_to_the_set_page_case_and_spaces_ignored(self):
        messy = ' '.join(self.custom.code.lower())
        d = self.get(messy).json()
        self.assertEqual(d, {'exists': True, 'url': '/game/s/%s/' % self.custom.code})

    def test_duel_code_leads_to_the_duel_page(self):
        d = self.get(self.duel.code).json()
        self.assertEqual(d, {'exists': True, 'url': '/game/d/%s/' % self.duel.code})

    def test_many_misses_from_one_address_are_slowed_down(self):
        from problems import ratelimit
        from game.views import SET_CHECK_SCOPE
        threshold = ratelimit.LADDER[0][0] * ratelimit.IP_MULTIPLIER
        for i in range(threshold):
            self.assertEqual(self.get('MISS%04d' % i).status_code, 200)
        r = self.get(self.custom.code)
        self.assertEqual(r.status_code, 429, 'лестница задержек не сработала')
        self.assertFalse(r.json()['exists'])
        self.assertTrue(ratelimit.failures(SET_CHECK_SCOPE + ':ip', '127.0.0.1') >= threshold)

    def test_empty_code_is_not_a_miss(self):
        from problems import ratelimit
        from game.views import SET_CHECK_SCOPE
        self.assertFalse(self.get('   ').json()['exists'])
        self.assertEqual(ratelimit.failures(SET_CHECK_SCOPE + ':ip', '127.0.0.1'), 0)


class StartScreenServerDataTests(TestCase):
    u"""Данные экрана: рекорды вошедшего по режимам и квота по режимам."""

    def setUp(self):
        fill_pool()

    def test_best_scores_per_mode_for_the_student(self):
        from game import leaderboard as lb
        user = User.objects.create_user(username='best_one', password='p12345')
        for mode, score in (('blitz', 300), ('blitz', 450), ('bullet', 90)):
            GameResult.objects.create(user=user, mode=mode, score=score,
                                      economy_version=config.ECONOMY_VERSION)
        GameResult.objects.create(user=user, mode='rapid', score=999,
                                  economy_version=config.ECONOMY_VERSION - 1)
        self.assertEqual(lb.best_scores(user), {'blitz': 450, 'bullet': 90})

    def test_page_config_carries_best_and_quota_only_for_the_student(self):
        html = self.client.get(reverse('game:page')).content.decode('utf-8')
        self.assertIn('"my_best": {}', html)
        self.assertIn('"ranked_quota": null', html)
        user = User.objects.create_user(username='cfg_student', password='p12345')
        GameResult.objects.create(user=user, mode='classic', score=77,
                                  economy_version=config.ECONOMY_VERSION)
        self.client.force_login(user)
        html = self.client.get(reverse('game:page')).content.decode('utf-8')
        self.assertIn('"my_best": {"classic": 77}', html)
        self.assertIn('"ranked_quota": {"used": {', html)


class StartScreenClientTests(TestCase):
    u"""Код стартового экрана: что сторожится текстом скрипта."""

    def setUp(self):
        self.src = page_source()
        self.js = inline_js(self.src)

    def start_keys(self):
        m = re.search(r"if \(state === 'start'\) \{(.*?)\n      return;\n    \}", self.js, re.S)
        self.assertIsNotNone(m, 'ветка клавиш стартового экрана не найдена')
        return m.group(1)

    def test_digits_select_a_mode_and_do_not_start(self):
        u"""1–4 выбирают режим (решение 17.09.2026); стартует только Enter."""
        keys = self.start_keys()
        digits = keys[keys.index("if (e.key >= '1' && e.key <= '5')"):]
        digits = digits[:digits.index('\n      }\n')]
        self.assertIn('selectMode(shown[idx])', digits)
        self.assertNotIn('startRun', digits)
        enter = keys[keys.index("if (e.key === 'Enter' && CFG.pool_counts[mode])"):]
        enter = enter[:enter.index('\n      }\n')]
        self.assertIn('startRun()', enter)

    def test_f_opens_the_filter_window_and_modifiers_are_left_to_the_browser(self):
        keys = self.start_keys()
        self.assertIn("e.code === 'KeyF'", keys)
        self.assertIn("openFilters(true, $('filter-open'))", keys)
        self.assertIn('if (e.metaKey || e.ctrlKey || e.altKey) return;', keys)

    def test_tab_click_only_selects(self):
        m = re.search(r"\$\('mode-grid'\)\.addEventListener\('click', function \(e\) \{(.*?)\n  \}\);",
                      self.js, re.S)
        self.assertIsNotNone(m)
        self.assertIn('selectMode(tab.dataset.mode)', m.group(1))
        self.assertNotIn('startRun', m.group(1))

    def test_medals_for_places_one_to_three(self):
        m = re.search(r'function lbRowNode\(r, pinned\) \{(.*?)\n  \}', self.js, re.S)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn('if (r.place >= 1 && r.place <= 3) {', body)
        self.assertIn('pl.innerHTML = MEDAL_SVG;', body)
        self.assertIn('pl.textContent = r.place;', body)
        self.assertIn('class="medal"', self.js)
        for place in ('--medal-gold', '--medal-silver', '--medal-bronze'):
            self.assertIn(place, self.src)

    def test_board_follows_the_selected_mode(self):
        m = re.search(r'function renderModeTabs\(\) \{(.*?)\n  \}', self.js, re.S)
        self.assertIsNotNone(m)
        self.assertIn('if (LB && LB.mode !== mode) {', m.group(1))
        self.assertIn("api('/game/api/leaderboard/?mode=' + encodeURIComponent(LB.mode)", self.js)

    def test_code_is_checked_without_leaving_the_page(self):
        m = re.search(r'\(function codeForm\(\) \{(.*?)\n  \}\)\(\);', self.js, re.S)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("api('/game/api/set_check/?code=' + encodeURIComponent(code))", body)
        self.assertIn("'Набора с таким кодом нет. Проверьте код.'", body)
        self.assertIn('location.href = d.url', body)
        self.assertNotIn("'/game/s/'", body)

    def test_mode_and_duel_from_the_address(self):
        m = re.search(r'\(function modeFromUrl\(\) \{(.*?)\n  \}\)\(\);', self.js, re.S)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn('selectMode(want)', body)
        self.assertIn('history.replaceState', body)
        self.assertIn('openDuelWindow(true)', body)

    def test_tokens_exist_in_both_themes(self):
        tokens = open('templates/_tokens.html', encoding='utf-8').read()
        dark = tokens[tokens.index('[data-theme="dark"] {'):]
        for name in ('--on-accent:', '--medal-gold:', '--accent-ring:', '--accent-tint:'):
            self.assertIn(name, tokens[:tokens.index('[data-theme="dark"] {')], name)
        for name in ('--on-accent:', '--accent-ring:', '--accent-tint:'):
            self.assertIn(name, dark, name)

    def test_no_hex_colours_in_the_start_markup(self):
        start = open('game/templates/game/_start.html', encoding='utf-8').read()
        self.assertIsNone(re.search(r'#[0-9a-fA-F]{3,8}\b', start))

    def test_time_left_to_moscow_midnight_is_drawn_not_computed(self):
        m = re.search(r'\(function dailyCountdown\(\) \{(.*?)\n  \}\)\(\);', self.js, re.S)
        self.assertIsNotNone(m)
        self.assertIn("getAttribute('data-reset-at')", m.group(1))
        self.assertNotIn('getTimezoneOffset', m.group(1))


class StreakTests(TestCase):
    u"""Серия дней вызова дня (фаза P4.1 сделана в P1: её ждала ячейка на главной)."""

    def setUp(self):
        fill_pool(('blitz', 'bullet'))
        self.user = User.objects.create_user(username='streaker', password='p12345')
        self.today = daily.today()

    def play(self, day, mode='blitz', saved_at=None):
        gset = GameSet.objects.filter(kind='daily', mode=mode, day=day).first()
        if gset is None:
            gset = GameSet.objects.create(code='D%s%s' % (day.strftime('%m%d'), mode[:3].upper()),
                                          mode=mode, kind='daily', day=day, question_ids=[])
        r = GameResult.objects.create(user=self.user, game_set=gset, mode=mode, score=1)
        if saved_at:
            GameResult.objects.filter(pk=r.pk).update(created_at=saved_at)

    def days_ago(self, n):
        return self.today - datetime.timedelta(days=n)

    def test_nothing_played(self):
        s = daily.streak_for(self.user)
        self.assertEqual((s['current'], s['best']), (0, 0))
        self.assertEqual(len(s['week']), 7)

    def test_chain_up_to_yesterday_is_kept_until_midnight(self):
        for n in (3, 2, 1):
            self.play(self.days_ago(n))
        self.assertEqual(daily.streak_for(self.user)['current'], 3)
        self.play(self.today)
        s = daily.streak_for(self.user)
        self.assertEqual((s['current'], s['best'], s['played_today']), (4, 4, True))

    def test_a_gap_of_one_day_resets(self):
        self.play(self.days_ago(3))
        self.play(self.days_ago(1))
        self.assertEqual(daily.streak_for(self.user)['current'], 1)
        self.play(self.days_ago(5))
        self.play(self.days_ago(6))
        s = daily.streak_for(self.user)
        self.assertEqual(s['best'], 2)
        self.assertGreaterEqual(s['best'], s['current'])

    def test_two_challenges_on_one_day_are_one_day(self):
        self.play(self.today, 'blitz')
        self.play(self.today, 'bullet')
        self.assertEqual(daily.streak_for(self.user)['current'], 1)
        cell = daily.daily_cell(self.user)
        self.assertEqual((cell['played'], cell['streak']), (2, 1))

    def test_round_saved_after_midnight_counts_for_its_set_day(self):
        yesterday = self.days_ago(1)
        after_midnight = timezone.now().replace(hour=0, minute=1)
        self.play(yesterday, saved_at=after_midnight)
        s = daily.streak_for(self.user)
        self.assertEqual(s['current'], 1)
        self.assertFalse(s['played_today'])

    def test_week_is_monday_to_sunday_with_today_marked(self):
        s = daily.streak_for(self.user)
        self.assertEqual([d['label'] for d in s['week']], list(daily.WEEKDAY_LABELS))
        self.assertEqual(datetime.date.fromisoformat(s['week'][0]['day']).weekday(), 0)
        self.assertEqual(sum(1 for d in s['week'] if d['is_today']), 1)
        self.assertTrue(s['week'][self.today.weekday()]['is_today'])
        self.play(self.today)
        self.assertTrue(daily.streak_for(self.user)['week'][self.today.weekday()]['hit'])

    def test_anonymous_has_no_streak_and_no_errors(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertEqual(daily.played_days(AnonymousUser()), set())
        cell = daily.daily_cell(AnonymousUser())
        self.assertFalse(cell['is_authenticated'])
        self.assertNotIn('streak', cell)

    def test_one_query_per_user(self):
        for n in range(10):
            self.play(self.days_ago(n))
        with self.assertNumQueries(1):
            daily.streak_for(self.user)
