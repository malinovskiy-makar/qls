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
START_KINDS = ('entry_rows_even', 'mode_rows_even', 'record_line_reserved', 'lb_tabs_one_line',
               'lb_segments_even', 'lb_row_grid', 'no_hscroll')


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
    u"""Стартовый экран: карточки нижнего ряда и режимов ровными рядами (строка
    «рекорд» у одной карточки не двигает соседей), вкладки доски в одну строку,
    сегменты одной высоты, строка доски сеткой, подвал «Войти», нет дубля ссылок.
    """

    def setUp(self):
        # По вопросам на каждый тип: карточек режимов должно быть несколько,
        # иначе «ровный ряд» проверять не на чем.
        for qtype in sorted({m['question_type'] for m in config.MODES.values()}):
            for i in range(config.MIN_PLAYABLE + 2):
                problem = Problem.objects.create(
                    title='', statement='Вопрос %s %d?' % (qtype, i), answer='',
                    problem_type='тест: один ответ', status='published')
                GameQuestion.objects.create(
                    problem=problem, question_type=qtype,
                    question='Вопрос %s номер %d?' % (qtype, i),
                    options=['Фирмы', 'Страны', 'Планеты', 'Климат'],
                    correct_index=0, difficulty=2, topics=[], lang='ru')
        for i, score in enumerate((1250, 980, 640)):
            user = User.objects.create_user(username='start_player_%d' % i, password='p12345')
            GameResult.objects.create(user=user, mode=config.DEFAULT_MODE, score=score,
                                      correct_count=9, total_count=11, wrong_count=2,
                                      ranked=True, economy_version=config.ECONOMY_VERSION)

    def test_start_screen_rows_are_even(self):
        data = run_node(self, START_RUNNER, {'RUSH_BASE_URL': self.live_server_url,
                                             'RUSH_RECORD_MODE': config.DEFAULT_MODE}, 300)
        expected = {'start@%d:%s' % (width, kind) for width in START_WIDTHS for kind in START_KINDS}
        expected |= {'start@1280:login_button', 'start@1280:no_duplicate_links'}
        self.assertEqual(set(data['checks']), expected)
        failed = {k: v['detail'] for k, v in data['checks'].items() if not v['ok']}
        self.assertFalse(failed, 'стартовый экран игры:\n'
                         + json.dumps(failed, ensure_ascii=False, indent=1)[:6000])
