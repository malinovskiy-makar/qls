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

from problems.enrich import features as enrich_features
from problems.models import (AiUsageLog, Feature, Hint, ProblemFeature, ProblemPart, Source,
                             SourceReference, Tag)
from problems.models_platform import SavedProblem
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
        # Худшая строка свойств: все показываемые особенности, длинный источник, теги.
        self.long = make_problem('Фирма выбирает цену и выпуск. $TC = Q^2$.', topic=self.topic,
                                 title='Длинная строка свойств', difficulty=3, character='quant')
        for order, (key, label, by) in enumerate(enrich_features.CATALOG_FEATURES):
            feature = Feature.objects.get_or_create(key=key, defaults={
                'label': label, 'counted_by': by, 'order': order})[0]
            ProblemFeature.objects.create(problem=self.long, feature=feature, source='code')
        SourceReference.objects.create(problem=self.long, url='https://example.org/task/1',
                                       source=Source.objects.create(name='Школково – банк задач по экономике'))
        for name in ('монополия', 'эластичность', 'налоги'):
            self.long.tags.add(Tag.objects.create(name=name, slug=name, kind='canonical'))
        # Выдача не короче 12 строк: темы, сложности, решения, тест (фаза 6).
        other_topic = make_topic('Совершенная конкуренция', is_canonical=True)
        for i in range(12):
            make_problem('Фирма %d выбирает выпуск: $TC = Q^2 + %d$.' % (i, i),
                         topic=other_topic if i % 3 else self.topic,
                         title='Фирма %d' % i + (' с очень длинным названием про издержки и выпуск' if i == 4 else ''),
                         difficulty=1 + i % 5,
                         solution=('Решение длиной больше тридцати знаков: MC = P.' if i % 2 else ''))
        # Без темы, но со сложностью: соседние колонки не должны съехать.
        make_problem('Задача без темы: $TC = 2Q$.', title='Без темы', difficulty=3)
        test = make_problem('Кто устанавливает ключевую ставку?', topic=self.topic, title='Ставка',
                            problem_type='тест: один ответ', answer='b', difficulty=2,
                            solution='(b) Центральный банк устанавливает ключевую ставку.')
        for i, label in enumerate('abcd'):
            ProblemPart.objects.create(problem=test, label=label, order=i, statement='Вариант %s' % label)
        student = make_user('polish_browser_student')
        SavedProblem.objects.create(owner=student, catalog_problem=self.other)
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
                   POLISH_PROBLEM=str(self.problem.pk), POLISH_PROBLEM2=str(self.other.pk),
                   POLISH_LONG=str(self.long.pk))
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

        # Упавшие секции раннера — каждая своей строкой; остальные меряются дальше.
        for key, message in data.items():
            if key.startswith('fail '):
                check(False, 'секция %s упала: %s' % (key[5:], message))

        # Фаза 1: совет один раз, потом ⓘ (решение владельца 24.09.2026).
        # Секция пишет свои числа по ходу: упала посередине — недостающее будет None.
        tip = dict.fromkeys(('popTop', 'btnBottom'), 0)
        tip.update(data.get('tip') or {})
        tip = dict({'errors': []}, **tip)
        check(tip.get('cleanCard') is True and tip.get('cleanInfo') is False,
              'совет: на чистом хранилище карточка должна быть видна, ⓘ скрыт (%s)' % tip)
        check(tip.get('afterOkCard') is False and tip.get('afterOkInfo') is True,
              'совет: после «Понятно» карточка скрыта, ⓘ виден (%s)' % tip)
        check(bool(tip.get('key')), 'совет: «Понятно» не записал weco_help_tip_seen')
        check(tip.get('reloadCard') is False and tip.get('reloadInfo') is True,
              'совет: после перезагрузки карточка вернулась или ⓘ пропал (%s)' % tip)
        check(tip.get('swapCard') is False and tip.get('swapInfo') is True,
              'совет: на другой задаче без перезагрузки карточка вернулась (%s)' % tip)
        check(tip.get('hoverPop') is True, 'ⓘ: подсказка не открылась по наведению')
        check(tip.get('popText') == TIP and tip.get('cardText') == TIP,
              'ⓘ: текст подсказки не равен тексту совета (%r / %r)' % (tip.get('popText'), tip.get('cardText')))
        check(tip.get('popTop') > tip.get('btnBottom'),
              'ⓘ: подсказка не под значком (верх %s, низ кнопки %s)' % (tip.get('popTop'), tip.get('btnBottom')))
        check(tip.get('expanded') == 'true', 'ⓘ: aria-expanded не true при открытой подсказке')
        check(tip.get('escPop') is False, 'ⓘ: Esc не закрыл подсказку')
        check(not tip.get('errors'), 'совет: ошибки страницы %s' % tip.get('errors'))

        # Фаза 2: строка лимита — число и видимость после ответа чата.
        lim = data['limit']
        check(lim['before'] == {'hidden': True, 'n': '6'}, 'лимит до реплики: %s' % lim['before'])
        check(lim['after']['hidden'] is False and lim['after']['n'] == '5',
              'лимит после ответа чата не обновился: %s' % lim['after'])
        check(lim['after']['text'] == 'Запросов к ИИ на сегодня: осталось 5',
              'лимит: подпись %r' % lim['after']['text'])
        check(not lim['errors'], 'лимит: ошибки страницы %s' % lim['errors'])

        # Фаза 3: «свернуть» у левого края, тонкие полосы, искра пункта без кружка.
        for theme in ('light', 'dark'):
            box = data['p3 ' + theme]
            check(box['collapseFirst'] and box['collapseGap'] <= 16,
                  '%s: «свернуть» не у левого края шапки (отступ %s)' % (theme, box['collapseGap']))
            check(box['resetLeft'] is not None and box['resetLeft'] > box['titleRight'],
                  '%s: «Решить заново» не правее «Помощь» (%s)' % (theme, box))
            for sel, bar in box['bars'].items():
                check(bar['over'] and bar['gutter'] == 5,
                      '%s: полоса прокрутки %s шириной %s, нужно 5 (%s)' % (theme, sel, bar['gutter'], bar))
            ask = box['ask']
            check(ask['bg'] in ('rgba(0, 0, 0, 0)', 'transparent'), '%s: у значка пункта фон %s' % (theme, ask['bg']))
            check(ask['border'] == '0px', '%s: у значка пункта рамка %s' % (theme, ask['border']))
            check(round(ask['svgW']) == 19, '%s: искра %s px, нужно 19' % (theme, ask['svgW']))
            check(round(ask['w']) == 32 and round(ask['h']) == 32,
                  '%s: зона нажатия %sx%s, нужно 32x32' % (theme, ask['w'], ask['h']))
            check(ask['color'] == ask['accentInk'],
                  '%s: цвет значка %s, а --accent-ink %s' % (theme, ask['color'], ask['accentInk']))
            check(not box['errors'], '%s: ошибки страницы %s' % (theme, box['errors']))

        # Фаза 4: «Теги · N» стоит на месте, список раскрывается строкой ниже.
        tags = data['tags']
        for key in ('open', 'closed'):
            check(abs(tags[key]['left'] - tags['before']['left']) <= 1
                  and abs(tags[key]['top'] - tags['before']['top']) <= 1,
                  'теги: кнопка сдвинулась (%s: %s → %s)' % (key, tags['before'], tags[key]))
        check(tags['expanded'] == 'true' and tags['listShown'] is True,
              'теги: после клика список не раскрылся (%s)' % tags)
        check(tags['listTop'] > tags['subBottom'],
              'теги: список не ниже строки свойств (%s ≤ %s)' % (tags['listTop'], tags['subBottom']))
        check(tags['expandedAfter'] == 'false' and tags['listShownAfter'] is False,
              'теги: повторный клик не свернул список (%s)' % tags)
        check(not tags['errors'], 'теги: ошибки страницы %s' % tags['errors'])
        # Длинная строка свойств при любых панелях и ширинах окна.
        for key, row in data['propRow'].items():
            check(row['btnRight'] is not None and abs(row['btnRight'] - row['colRight']) <= 1,
                  '%s: «Теги» не у правого края колонки (%s vs %s)' % (key, row['btnRight'], row['colRight']))
            check(row['wordsRight'] <= row['colRight'] + 0.5,
                  '%s: слова вылезли за колонку (%s > %s)' % (key, row['wordsRight'], row['colRight']))
            check(row['scrollWidth'] <= row['clientWidth'],
                  '%s: у колонки горизонтальная прокрутка (%s > %s)' % (key, row['scrollWidth'], row['clientWidth']))
            check(abs(row['btnTop'] - row['subTop']) <= 1,
                  '%s: «Теги» не в первой строке (%s vs %s)' % (key, row['btnTop'], row['subTop']))
            check(not row['errors'], '%s: ошибки страницы %s' % (key, row['errors']))

        # Фаза 5: в «Фокусе» «Помощь» и «Лента» открываются поверх, Esc в два шага.
        foc = data['focus']
        for panel, width_key, width in (('help', 'helpW', 392), ('rail', 'railW', 316)):
            run = foc[panel]
            check(run['inFocus']['focus'] and not run['inFocus']['nav'], '%s: F не включил фокус (%s)' % (panel, run['inFocus']))
            opened = run['opened']
            check(opened['focus'] and not opened['nav'] and opened[panel],
                  '%s: пилюля вывела из фокуса или панель не видна (%s)' % (panel, opened))
            check(abs(opened[width_key] - width) <= 1, '%s: ширина панели %s, нужно %d' % (panel, opened[width_key], width))
            check(abs(opened['colX'] - run['inFocus']['colX']) <= 1,
                  '%s: колонка условия сдвинулась (%s → %s)' % (panel, run['inFocus']['colX'], opened['colX']))
            check(run['esc1']['focus'] and not run['esc1'][panel],
                  '%s: первый Esc должен закрыть панель и оставить фокус (%s)' % (panel, run['esc1']))
            check(not run['esc2']['focus'], '%s: второй Esc не вышел из фокуса (%s)' % (panel, run['esc2']))
        check(foc['keyOpen']['focus'] and foc['keyOpen']['help'], '] в фокусе: %s' % foc['keyOpen'])
        check(foc['clickAway']['focus'] and not foc['clickAway']['help'], 'клик мимо: %s' % foc['clickAway'])
        check(foc['askPop']['focus'] and foc['askPop']['help'], '«Обсудить с ИИ» в фокусе: %s' % foc['askPop'])
        check(foc['storeBefore'] == foc['storeAfter'],
              'weco_stol изменился: %s → %s' % (foc['storeBefore'], foc['storeAfter']))
        check(foc['normalAfter']['dataHelp'] == foc['normalBefore']['dataHelp']
              and foc['normalAfter']['dataRail'] == foc['normalBefore']['dataRail'],
              'обычные панели после фокуса не те же: %s → %s' % (foc['normalBefore'], foc['normalAfter']))
        check(not foc['errors'], 'фокус: ошибки страницы %s' % foc['errors'])

        # Фаза 6: метки у названия, ровные колонки, без чередования, без прокрутки.
        for theme in ('light', 'dark'):
            box = data['rows ' + theme]
            rows = box['rows']
            check(box['n'] >= 12, '%s: в выдаче %d строк, нужно не меньше 12' % (theme, box['n']))
            lefts = [r['topicLeft'] for r in rows if r['topicLeft'] is not None]
            widths = [r['topicW'] for r in rows if r['topicW'] is not None]
            stars = [r['starsRight'] for r in rows if r['starsRight'] is not None]
            check(lefts and max(lefts) - min(lefts) <= 1, '%s: левый край чипа темы гуляет %s' % (theme, sorted(set(lefts))))
            check(widths and max(widths) - min(widths) <= 1, '%s: ширина чипа темы гуляет %s' % (theme, sorted(set(widths))))
            check(stars and max(stars) - min(stars) <= 1, '%s: правый край звёзд гуляет %s' % (theme, sorted(set(stars))))
            marked = [r for r in rows if r['markLeft'] is not None]
            check(len(marked) >= 3, '%s: строк с метками %d' % (theme, len(marked)))
            for r in marked:
                check(r['markLeft'] > r['titleRight'] - 1 and (r['topicLeft'] is None or r['markLeft'] < r['topicLeft']),
                      '%s: метка не у названия (%s)' % (theme, r))
            check(sum(r['metaMarks'] for r in rows) == 0, '%s: метки остались в rail-meta' % theme)
            bgs = [r['bg'] for r in rows]
            check(all(a == b for a, b in zip(bgs, bgs[1:])), '%s: цвет строк чередуется %s' % (theme, sorted(set(bgs))))
            check(box['docW'] <= box['winW'], '%s 1440: документ шире окна (%s > %s)' % (theme, box['docW'], box['winW']))
            check(not box['errors'], '%s: ошибки страницы %s' % (theme, box['errors']))
        for width in (1024, 390):
            doc = data['rows doc %d' % width]
            check(doc['docW'] <= doc['winW'], '%d: документ шире окна (%s > %s)' % (width, doc['docW'], doc['winW']))
        narrow = data['narrow']
        check(abs(narrow['railW'] - 316) <= 1, 'узкая лента шириной %s, нужно 316' % narrow['railW'])
        check(narrow['n'] >= 12 and narrow['withMarks'] >= 3, 'узкая лента: строк %s, с метками %s' % (narrow['n'], narrow['withMarks']))
        check(narrow['overlaps'] == 0, 'узкая лента: метки наезжают на название в %s строках' % narrow['overlaps'])
        check(narrow['docW'] <= narrow['winW'], 'узкая лента: документ шире окна')
        check(not narrow['errors'], 'узкая лента: ошибки страницы %s' % narrow['errors'])

        self.assertEqual(problems, [], '\n'.join(problems))
