"""Пустая прокрутка под «Столом» от формул в скроллерах панелей (13.10.2026).

Дефект: KaTeX ставит скрытой копии формулы `.katex-mathml` position: absolute.
Её предок для позиционирования — ближайший позиционированный, а у `.help-body`
и `.rail-list` (скроллеры с overflow: auto) position не было: предком
становилась sticky-колонка СНАРУЖИ скроллера. Overflow скроллера такие
элементы не обрезает, и длинная лента с формулами растягивала прокрутку
документа (58898 с раскрытым решением: +1 842 px пустоты на 1440).
Лечение — `position: relative` у обоих скроллеров (`stol.css`).

Раннер `catalog/tests/stol_scroll_leak_runner.mjs` (Playwright) меряет, здесь —
решение «зелёный/красный». Нет node или Playwright — тест ПРОПУСКАЕТСЯ.
"""
import json
import os
import shutil
import subprocess

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.cache import cache
from django.test import tag

from problems.tests.factories import make_problem, make_topic, make_user

RUNNER = os.path.join(os.path.dirname(__file__), 'stol_scroll_leak_runner.mjs')
STEP = ('Шаг %d: из условия $MR = 20 - 2Q$ и $MC = 2Q$ получаем '
        '$Q^* = \\frac{20}{4} = 5$, а излишек $\\sqrt{CS} = \\sqrt{25}$.')


# ⚠️ ПРИЧИНА МЕТКИ `serial`: класс поднимает живой сервер и гоняет по нему
# Chromium отдельным процессом node — внешние ресурсы, поделить их между
# воркерами шага A нельзя.
@tag('catalog', 'browser', 'serial')
class StolScrollLeakBrowserTest(StaticLiveServerTestCase):

    def setUp(self):
        cache.clear()
        topic = make_topic('Монополия и ценовая дискриминация', is_canonical=True)
        # Решение длиннее панели помощи: лента обязана переполниться.
        self.problem = make_problem('Монополист: спрос $P = 20 - Q$, $TC = Q^2$.', topic=topic,
                                    title='Монополист и излишек', difficulty=3,
                                    solution='\n\n'.join(STEP % i for i in range(1, 17)))
        # Строки выдачи без названия: превью условия с формулами (KaTeX в `.rail-list`).
        for i in range(24):
            make_problem('Фирма %d: $TC = Q^2 + %d$, $\\frac{dTC}{dQ} = 2Q$.' % (i, i),
                         topic=topic, difficulty=1 + i % 5)
        self.client.force_login(make_user('scroll_leak_student'))
        self.session = self.client.cookies['sessionid'].value

    def _run(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node не найден: замеры прокрутки не запускались')
        if not os.path.isdir(os.path.join(settings.BASE_DIR, 'node_modules', 'playwright')):
            self.skipTest('playwright не установлен в node_modules')
        env = dict(os.environ, LEAK_BASE_URL=self.live_server_url, LEAK_SESSION=self.session,
                   LEAK_PROBLEM=str(self.problem.pk))
        try:
            res = subprocess.run([node, RUNNER], env=env, cwd=str(settings.BASE_DIR),
                                 capture_output=True, text=True, encoding='utf-8',
                                 errors='replace', timeout=300)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.skipTest('раннер не запустился: %s' % exc)
        out = (res.stdout or '') + (res.stderr or '')
        if res.returncode == 3:
            self.skipTest('браузер не поднялся:\n' + out[-1500:])
        self.assertIn('###LEAK-JSON###', out, 'раннер не отдал результат:\n' + out[-2000:])
        data = json.loads(out.split('###LEAK-JSON###', 1)[1].strip().splitlines()[0])
        self.assertNotIn('error', data, data.get('error'))
        return data

    def test_no_empty_scroll_under_desk(self):
        data = self._run()
        problems = ['секция %s упала: %s' % (key[5:], msg) for key, msg in data.items()
                    if key.startswith('fail ')]
        for key in ('help 1781', 'help 1440', 'help 1280', 'rail'):
            box = data.get(key)
            if box is None:
                problems.append('%s: замера нет' % key)
                continue
            # Замер не пустой: формулы есть и скроллер действительно переполнен.
            if box['katex'] < 4 or box['over'] <= 0:
                problems.append('%s: нечего мерить (формул %s, переполнение %s px)'
                                % (key, box['katex'], box['over']))
            if box['doc'] > box['body'] + 1:
                problems.append('%s: документ длиннее body на %d px, пустая прокрутка под «Столом»'
                                % (key, box['doc'] - box['body']))
            if box['errors']:
                problems.append('%s: ошибки страницы %s' % (key, box['errors']))
        self.assertEqual(problems, [], '\n'.join(problems))
