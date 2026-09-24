"""Полировка «Стола» 24.09.2026 числами в настоящем браузере.

Раннер `catalog/tests/stol_polish_runner.mjs` (Playwright) меряет то, что
задание сессии называет числом: совет один раз, кнопка «свернуть» слева,
тонкие полосы прокрутки, «Теги» на месте, фокус с панелями поверх, ровные
колонки выдачи. Здесь — решение «зелёный/красный»; падения собираются списком.

Нет node или Playwright — тест ПРОПУСКАЕТСЯ, а не падает.
"""
import json
import os
import shutil
import subprocess

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.cache import cache
from django.test import override_settings, tag

from problems.models import AiUsageLog, Hint, ProblemPart
from problems.tests.factories import make_problem, make_topic, make_user

RUNNER = os.path.join(os.path.dirname(__file__), 'stol_polish_runner.mjs')
TIP = ('История чата в этой задаче сохраняется. Выделите фрагмент условия или ответа ИИ, '
       'чтобы обсудить именно его.')


# ⚠️ ПРИЧИНА МЕТКИ `serial`: класс поднимает живой сервер и гоняет по нему
# Chromium отдельным процессом node — внешние ресурсы, поделить их между
# воркерами шага A нельзя.
@tag('catalog', 'browser', 'serial')
@override_settings(CATALOG_CHAT_PROVIDER='fake', AI_PROVIDER='fake', AI_GENERATOR_DAILY_LIMIT=30,
                   AI_FAKE_REPLY=json.dumps({'reply': 'Начните с MR = MC.'}, ensure_ascii=False))
class StolPolishBrowserTest(StaticLiveServerTestCase):

    def setUp(self):
        cache.clear()
        self.topic = make_topic('Монополия и ценовая дискриминация', is_canonical=True)
        self.problem = make_problem('Монополист продаёт электроэнергию. Спрос $Q = 20 - P$.',
                                    topic=self.topic, title='Двухступенчатый тариф', difficulty=4,
                                    solution='Решение длиной больше тридцати знаков: $MR = MC$.')
        for i, label in enumerate(('а', 'б')):
            ProblemPart.objects.create(problem=self.problem, label=label, order=i,
                                       statement='Найдите цену %s.' % label)
        Hint.objects.create(problem=self.problem, text='Подсказка: начните с MR = MC.', order=0)
        self.other = make_problem('Фирма на конкурентном рынке. $TC = Q^2$.', topic=self.topic,
                                  title='Конкурентная фирма', difficulty=2)
        student = make_user('polish_browser_student')
        # Остаток ИИ 6 из 30: строка лимита скрыта, после одной реплики — видна.
        AiUsageLog.objects.bulk_create([AiUsageLog(user=student, kind='catalog_chat', model_name='fake', ok=True)
                                        for _ in range(24)])
        self.client.force_login(student)
        self.session = self.client.cookies['sessionid'].value

    def _run(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node не найден — замеры полировки не запускались')
        if not os.path.isdir(os.path.join(settings.BASE_DIR, 'node_modules', 'playwright')):
            self.skipTest('playwright не установлен в node_modules')
        env = dict(os.environ, POLISH_BASE_URL=self.live_server_url, POLISH_SESSION=self.session,
                   POLISH_PROBLEM=str(self.problem.pk), POLISH_PROBLEM2=str(self.other.pk))
        try:
            res = subprocess.run([node, RUNNER], env=env, cwd=str(settings.BASE_DIR),
                                 capture_output=True, text=True, encoding='utf-8',
                                 errors='replace', timeout=600)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.skipTest('раннер не запустился: %s' % exc)
        out = (res.stdout or '') + (res.stderr or '')
        if res.returncode == 3:
            self.skipTest('браузер не поднялся:\n' + out[-1500:])
        self.assertIn('###POLISH-JSON###', out, 'раннер не отдал результат:\n' + out[-2000:])
        data = json.loads(out.split('###POLISH-JSON###', 1)[1].strip().splitlines()[0])
        self.assertNotIn('error', data, data.get('error'))
        return data

    def test_polish_numbers(self):
        data = self._run()
        problems = []

        def check(ok, text):
            if not ok:
                problems.append(text)

        # Фаза 1: совет один раз, потом ⓘ (решение владельца 24.09.2026).
        tip = data['tip']
        check(tip['cleanCard'] is True and tip['cleanInfo'] is False,
              'совет: на чистом хранилище карточка должна быть видна, ⓘ скрыт (%s)' % tip)
        check(tip['afterOkCard'] is False and tip['afterOkInfo'] is True,
              'совет: после «Понятно» карточка скрыта, ⓘ виден (%s)' % tip)
        check(bool(tip['key']), 'совет: «Понятно» не записал weco_help_tip_seen')
        check(tip['reloadCard'] is False and tip['reloadInfo'] is True,
              'совет: после перезагрузки карточка вернулась или ⓘ пропал (%s)' % tip)
        check(tip['swapCard'] is False and tip['swapInfo'] is True,
              'совет: на другой задаче без перезагрузки карточка вернулась (%s)' % tip)
        check(tip['hoverPop'] is True, 'ⓘ: подсказка не открылась по наведению')
        check(tip['popText'] == TIP and tip['cardText'] == TIP,
              'ⓘ: текст подсказки не равен тексту совета (%r / %r)' % (tip['popText'], tip['cardText']))
        check(tip['popTop'] > tip['btnBottom'],
              'ⓘ: подсказка не под значком (верх %s, низ кнопки %s)' % (tip['popTop'], tip['btnBottom']))
        check(tip['expanded'] == 'true', 'ⓘ: aria-expanded не true при открытой подсказке')
        check(tip['escPop'] is False, 'ⓘ: Esc не закрыл подсказку')
        check(not tip['errors'], 'совет: ошибки страницы %s' % tip['errors'])

        # Фаза 2: строка лимита — число и видимость после ответа чата.
        lim = data['limit']
        check(lim['before'] == {'hidden': True, 'n': '6'}, 'лимит до реплики: %s' % lim['before'])
        check(lim['after']['hidden'] is False and lim['after']['n'] == '5',
              'лимит после ответа чата не обновился: %s' % lim['after'])
        check(lim['after']['text'] == 'Запросов к ИИ на сегодня: осталось 5',
              'лимит: подпись %r' % lim['after']['text'])
        check(not lim['errors'], 'лимит: ошибки страницы %s' % lim['errors'])

        self.assertEqual(problems, [], '\n'.join(problems))
