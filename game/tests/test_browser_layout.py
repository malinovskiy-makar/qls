u"""Раскладка страниц Wecon Rush на 380 и 1280 px — в настоящем браузере.

Решение владельца 15.09.2026: экраны игры правятся по списку без макета,
приёмка по скринам. Здесь инварианты числами (`browser_layout.mjs`): у
страницы нет горизонтальной прокрутки, элементы управления не ниже 32 px,
текст кнопки не переносится на три строки. Страницы: вызов дня и его доска,
дуэль с итогом двоих, доска набора, страница итога, статистика пула.

⚠️ «Кликабельное ≥ 32 px» меряется у элементов управления: кнопок,
`role=button`, отправки формы и ссылок, оформленных кнопкой. Строчная ссылка
внутри абзаца — это текст, а не кнопка, и её высоту задаёт строка.

Нет node или Playwright — тест ПРОПУСКАЕТСЯ, а не падает.
"""
import json
import os
import shutil
import subprocess

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.cache import cache
from django.test import tag

from game import config
from game.models import GameQuestion, GameResult
from game.tests.test_sets import make_q, make_set
from problems.models import Problem, User

RUNNER = os.path.join(os.path.dirname(__file__), 'browser_layout.mjs')
START_RUNNER = os.path.join(os.path.dirname(__file__), 'browser_start.mjs')
WIDTHS = (380, 1280)
KINDS = ('no_hscroll', 'controls_32px', 'no_three_line_buttons')
START_WIDTHS = (1280, 700, 460, 380)
START_KINDS = ('guest_no_vscroll_1440x800', 'four_mode_tabs', 'four_band_cells',
               'three_medals_then_number', 'key1_selects_not_starts', 'board_follows_mode',
               'f_opens_filters', 'guest_stats_tab', 'wrong_code_stays',
               'wrong_code_message_clears_on_input', 'duel_code_goes_to_duel_page',
               'enter_starts_one_round', 'url_mode_selects_rapid',
               'url_duel_guest_sees_account_window', 'student_no_vscroll_1440x800',
               'url_duel_student_opens_create_window')


def run_node(test, runner, env, timeout):
    u"""Запустить раннер и вернуть разобранный JSON; нет node/браузера — пропуск."""
    node = shutil.which('node')
    if not node:
        test.skipTest('node не найден — браузерная проверка раскладки не запускалась')
    if not os.path.isdir(os.path.join(settings.BASE_DIR, 'node_modules', 'playwright')):
        test.skipTest('playwright не установлен в node_modules')
    try:
        res = subprocess.run([node, runner], env=dict(os.environ, **env), cwd=str(settings.BASE_DIR),
                             capture_output=True, text=True, encoding='utf-8',
                             errors='replace', timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        test.skipTest('раннер не запустился: %s' % exc)
    out = (res.stdout or '') + (res.stderr or '')
    if res.returncode == 3:
        test.skipTest('браузер не поднялся:\n' + out[-1500:])
    test.assertIn('###RUSH-JSON###', out, 'раннер не отдал результат:\n' + out[-2000:])
    data = json.loads(out.split('###RUSH-JSON###', 1)[1].strip().splitlines()[0])
    test.assertNotIn('error', data, data.get('error'))
    return data


# ⚠️ ПРИЧИНА МЕТКИ `serial`: класс поднимает живой сервер и гоняет по нему
# Chromium — внешние ресурсы, поделить их между воркерами шага A нельзя.
@tag('game', 'browser', 'serial')
class GamePagesLayoutBrowserTest(StaticLiveServerTestCase):

    def setUp(self):
        questions = make_q(15)
        self.staff = User.objects.create_user(username='layout_staff', password='p12345',
                                              is_staff=True, is_superuser=True)
        rival = User.objects.create_user(username='layout_rival', password='p12345')
        custom = make_set(questions[:5], title='Контрольная по спросу')
        GameResult.objects.create(game_set=custom, user=rival, mode='blitz', score=640,
                                  correct_count=6, total_count=8, wrong_count=2)
        duel = make_set(questions[:5], kind='duel', title='Дуэль · Блиц', author=self.staff)
        for user, score in ((self.staff, 1250), (rival, 980)):
            GameResult.objects.create(game_set=duel, user=user, mode='blitz', score=score,
                                      correct_count=9, total_count=11, wrong_count=2,
                                      skip_count=1, max_combo=1.5, avg_correct_ms=2100,
                                      wall_ms=121000)
        result = GameResult.objects.create(mode='blitz', score=870, correct_count=7,
                                           total_count=9, wrong_count=2)
        self.pages = ['/game/daily/', '/game/daily/blitz/', '/game/d/%s/' % duel.code,
                      '/game/s/%s/board/' % custom.code, '/game/r/%s/' % result.code,
                      '/game/stats/']

    def test_pages_fit_380_and_1280(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node не найден — браузерная проверка раскладки не запускалась')
        if not os.path.isdir(os.path.join(settings.BASE_DIR, 'node_modules', 'playwright')):
            self.skipTest('playwright не установлен в node_modules')
        self.client.force_login(self.staff)
        env = dict(os.environ, RUSH_BASE_URL=self.live_server_url,
                   RUSH_PAGES=','.join(self.pages),
                   RUSH_SESSION=self.client.cookies[settings.SESSION_COOKIE_NAME].value)
        try:
            res = subprocess.run([node, RUNNER], env=env, cwd=str(settings.BASE_DIR),
                                 capture_output=True, text=True, encoding='utf-8',
                                 errors='replace', timeout=300)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.skipTest('раннер не запустился: %s' % exc)
        out = (res.stdout or '') + (res.stderr or '')
        if res.returncode == 3:
            self.skipTest('браузер не поднялся:\n' + out[-1500:])
        self.assertIn('###RUSH-JSON###', out, 'раннер не отдал результат:\n' + out[-2000:])
        data = json.loads(out.split('###RUSH-JSON###', 1)[1].strip().splitlines()[0])
        self.assertNotIn('error', data, data.get('error'))
        # Пустой прогон — не «зелено»: каждая страница на каждой ширине обязана
        # пройти все три проверки, а не выпасть на загрузке.
        expected = {'%s@%d:%s' % (page, width, kind)
                    for page in self.pages for width in WIDTHS for kind in KINDS}
        self.assertEqual(set(data['checks']), expected)
        failed = {k: v['detail'] for k, v in data['checks'].items() if not v['ok']}
        # Красные проверки — целиком в сообщении: по ним чинят раскладку.
        self.assertFalse(failed, 'раскладка страниц игры на 380/1280 px:\n'
                         + json.dumps(failed, ensure_ascii=False, indent=1)[:6000])


# ⚠️ ПРИЧИНА МЕТКИ `serial`: класс поднимает живой сервер и гоняет по нему
# Chromium — внешние ресурсы, поделить их между воркерами шага A нельзя.
@tag('game', 'browser', 'serial')
class StartScreenBrowserTest(StaticLiveServerTestCase):
    u"""Стартовый экран «аркады» (ADR 0108): без прокрутки на 1440×800 у гостя и
    у вошедшего, четыре вкладки, три медали, клавиши 1 / Enter / F, проверка
    кода без ухода со страницы, адреса ?mode= и ?duel=, статистика гостя.
    """

    MAIN_MODES = ('bullet', 'blitz', 'rapid', 'classic')

    def setUp(self):
        # ⚠️ Доска кэшируется на минуту (`leaderboard.top`), а база между
        # браузерными тестами чистится, кэш — нет. В полном шаге B 15.09.2026
        # предыдущий тест открыл `/game/` за полминуты до этого, оставил в кэше
        # пустую доску — и строк на экране не было ни на одной ширине.
        cache.clear()
        # Вопросы только четырёх основных режимов: вкладок ровно четыре и при
        # включённом «Графике» (его вкладка появляется только с вопросами).
        for key in self.MAIN_MODES:
            qtype = config.MODES[key]['question_type']
            for i in range(config.MIN_PLAYABLE + 2):
                problem = Problem.objects.create(
                    title='', statement='Вопрос %s %d?' % (qtype, i), answer='',
                    problem_type='тест: один ответ', status='published')
                GameQuestion.objects.create(
                    problem=problem, question_type=qtype,
                    question='Вопрос %s номер %d?' % (qtype, i),
                    options=['Фирмы', 'Страны', 'Планеты', 'Климат'],
                    correct_index=0, difficulty=2, topics=[], lang='ru')
        # Четыре строки таблицы: три медали и число у четвёртой.
        for i, score in enumerate((1250, 980, 640, 410)):
            user = User.objects.create_user(username='start_player_%d' % i, password='p12345')
            GameResult.objects.create(user=user, mode=config.DEFAULT_MODE, score=score,
                                      correct_count=9, total_count=11, wrong_count=2,
                                      ranked=True, economy_version=config.ECONOMY_VERSION)
        self.student = User.objects.create_user(username='start_student', password='p12345')
        duel = make_set(GameQuestion.objects.filter(question_type='single')[:5],
                        kind='duel', title='Дуэль · Блиц', author=self.student)
        self.duel_code = duel.code

    def test_start_screen_arcade(self):
        self.client.force_login(self.student)
        data = run_node(self, START_RUNNER, {
            'RUSH_BASE_URL': self.live_server_url,
            'RUSH_DUEL_CODE': self.duel_code,
            'RUSH_SESSION': self.client.cookies[settings.SESSION_COOKIE_NAME].value,
        }, 300)
        expected = set(START_KINDS) | {'no_hscroll@%d' % w for w in START_WIDTHS}
        self.assertEqual(set(data['checks']), expected)
        failed = {k: v['detail'] for k, v in data['checks'].items() if not v['ok']}
        self.assertFalse(failed, 'стартовый экран игры:\n'
                         + json.dumps(failed, ensure_ascii=False, indent=1)[:6000])
