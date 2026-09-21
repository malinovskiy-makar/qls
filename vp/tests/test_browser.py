"""Тренажёр ВП в настоящем браузере (Chromium через Playwright, `browser_take.mjs`).

Пять ручных сценариев владельца + состояния таймера, «время вышло», офлайн и
телефон — как обычный гость, без входа. После прогона проверяем и базу: то, что
браузер «сохранил», должно лежать в ней.

Нет node или Playwright — тест ПРОПУСКАЕТСЯ, а не падает.
"""
import json
import os
import shutil
import subprocess
from decimal import Decimal as D

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.db import connection
from django.test import tag
from django.utils import timezone

from vp.models import VPAttempt, VPVariant
from vp.tests import browser_fixture

RUNNER = os.path.join(os.path.dirname(__file__), 'browser_take.mjs')

# Каждая проверка раннера обязана отработать: пустой или обрезанный прогон — не «зелено».
EXPECTED = {
    # десктоп: вход, сценарии 1, 2, 3, 5
    'd.intro_five_blocks', 'd.intro_no_hscroll', 'd.intro_snake_paragraph_is_flowing_text',
    'd.take_hides_feedback_fab', 'd.intro.contrast_light', 'd.intro.contrast_dark',
    'd.start_goes_to_attempt', 'd.all_44_items', 'd.take_no_hscroll',
    'd.enter_walk_1_to_30', 'd.enter_after_last_goes_to_31', 'd.enter_never_submits',
    'd.counter_30', 'd.tiles_30',
    'd.reload_keeps_all_30', 'd.reload_keeps_last_typed', 'd.timer_continues', 'd.counter_30_after_reload',
    'd.counter_after_marks', 'd.dialog_opens', 'd.dialog_five_numbers_exact', 'd.dialog_text',
    'd.chip_closes_dialog', 'd.chip_returns_to_item17', 'd.item17_visible_below_header',
    'd.item17_marked_current', 'd.back_button_keeps_page',
    'd.theme_toggle_take', 'd.theme_toggle_back', 'd.take.contrast_light', 'd.take.contrast_dark',
    'd.submit_goes_to_result', 'd.result_score_present', 'd.result_has_five_blocks',
    'd.result_no_hscroll', 'd.result.contrast_light', 'd.result.contrast_dark', 'd.result_theme_toggle',
    'd.review_chain_30_rows', 'd.review_tests_14_cards', 'd.review_link_broken_named',
    'd.review_five_practice_buttons', 'd.review_share_button', 'd.comparison_shown',
    'd.comparison_marker_inside_scale', 'd.practice_form_opens', 'd.practice_wrong_gives_reference',
    'd.practice_reference_was_not_on_page', 'd.practice_right_says_right', 'd.practice_choice_is_checked',
    'd.practice_score_unchanged', 'd.practice_says_it_does_not_count',
    'd.take_after_submit_redirects', 'd.public_result_open', 'd.public_result_no_answers',
    'd.public_result_references_loaded', 'd.public_result_no_reference', 'd.public_result_no_review_blocks',
    'd.public_result_repeat_button', 'd.public_result_comparison', 'd.public.contrast_light',
    'd.public.contrast_dark',
    'd.foreign_take_404',
    # телефон: сценарий 4
    'm.intro_no_hscroll', 'm.take_no_hscroll', 'm.strip_visible_rail_hidden', 'm.inputs_16px',
    'm.options_44px', 'm.viewport_meta_no_zoom_lock', 'm.header_height_reasonable',
    'm.tap_cell_focus_not_under_header', 'm.tap_cell_focus_is_input', 'm.enter_next_not_under_header',
    'm.strip_follows_current', 'm.dialog_fits', 'm.take.contrast_light', 'm.take.contrast_dark',
    'm.result_no_hscroll',
    # автосохранение, таймер, офлайн, «время вышло»
    'i.twelve_saved_indicator',
    't.warn_state', 't.warn_banner_lists_missed', 't.warn_banner_updates_on_answer',
    't.warn_contrast_both_themes', 't.offline_indicator', 't.online_saved',
    't.danger_state', 't.danger_contrast_both_themes',
    't.timeup_redirects_to_result', 't.timeup_result_says_auto',
}


# ⚠️ ПРИЧИНА МЕТКИ `serial`: класс поднимает живой сервер и гоняет по нему Chromium
# отдельным процессом node — внешние ресурсы (порт и браузер), поделить их между
# воркерами шага A нельзя. Прогон около двух минут: часть проверок ждёт настоящих
# секунд (таймер, «время вышло», возврат связи).
@tag('vp', 'browser', 'serial')
class TakeInBrowserTest(StaticLiveServerTestCase):
    def setUp(self):
        # Живой сервер и тест делят одно соединение SQLite в памяти: параллельные запросы
        # страницы (автосохранение, sendBeacon на перезагрузке, опрос времени) дают на нём
        # ложные 500 `InterfaceError`. На боевой PostgreSQL этого нет — там тест идёт по-настоящему.
        if connection.vendor == 'sqlite':
            self.skipTest('SQLite в памяти: живой сервер делит с тестом одно соединение и '
                          'ловит ложные 500 — тест идёт на PostgreSQL (config.settings_test_pg)')
        for slug, title, duration in (
                ('vp-ui', 'Пробный вариант 1 тура «Высшей пробы»', 1800),
                ('vp-warn', 'Вариант на пять минут', 299),
                ('vp-danger', 'Вариант на минуту', 55),
                ('vp-fast', 'Вариант на десять секунд', 10)):
            browser_fixture.write(browser_fixture.rich_data(slug=slug, duration=duration, title=title))
        # Девятнадцать «других людей» у варианта vp-ui: с гостем, который пройдёт его в браузере,
        # получается ровно двадцать — граница, с которой на экране появляется сравнение.
        now = timezone.now()
        variant = VPVariant.objects.get(slug='vp-ui')
        for i in range(19):
            VPAttempt.objects.create(
                variant=variant, public_code='fake-%02d' % i, session_key='fake-%02d' % i, score=D(i),
                max_score=D('100'), submitted_at=now, expires_at=now)

    def run_runner(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node не найден — браузерная проверка ВП не запускалась')
        if not os.path.isdir(os.path.join(settings.BASE_DIR, 'node_modules', 'playwright')):
            self.skipTest('playwright не установлен в node_modules')
        env = dict(os.environ, VP_BASE_URL=self.live_server_url)
        try:
            res = subprocess.run([node, RUNNER], env=env, cwd=str(settings.BASE_DIR),
                                 capture_output=True, text=True, encoding='utf-8',
                                 errors='replace', timeout=420)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.skipTest('раннер не запустился: %s' % exc)
        out = (res.stdout or '') + (res.stderr or '')
        if res.returncode == 3:
            self.skipTest('браузер не поднялся:\n' + out[-1500:])
        self.assertIn('###VP-JSON###', out, 'раннер не отдал результат:\n' + out[-2000:])
        return json.loads(out.split('###VP-JSON###', 1)[1].strip().splitlines()[0])

    def test_owner_scenarios_timer_states_and_phone(self):
        data = self.run_runner()
        self.assertNotIn('error', data, data.get('error'))
        self.assertEqual(set(data['checks']), EXPECTED)
        failed = {k: v['detail'] for k, v in data['checks'].items() if not v['ok']}
        self.assertFalse(failed, 'браузерные проверки ВП:\n'
                         + json.dumps(failed, ensure_ascii=False, indent=1)[:6000])
        self.check_database(data['attempts'])

    def check_database(self, codes):
        def attempt(name):
            return VPAttempt.objects.get(public_code=codes[name])

        # Сценарии 1–3: гость дошёл до сдачи.
        desktop = attempt('desktop')
        self.assertIsNone(desktop.user)
        self.assertIsNotNone(desktop.submitted_at)
        self.assertFalse(desktop.is_auto_submitted)
        rows = {a.item.number: a for a in desktop.answers.select_related('item')}
        self.assertEqual(len(rows), 44)
        self.assertEqual(rows[30].raw, 'ПОСЛЕДНЕЕ')                 # набрано за миг до перезагрузки
        self.assertEqual([rows[n].raw for n in (1, 2, 29)], ['слово1', 'слово2', 'слово29'])
        empty = sorted(n for n, a in rows.items() if a.raw is None)
        self.assertEqual(empty, [17, 35, 40, 42, 44])                # ровно пять пустых, как в окне
        self.assertTrue(all(rows[n].is_correct is None and rows[n].score == D('0.00') for n in empty))
        self.assertEqual(desktop.score, sum((a.score for a in rows.values()), D('0.00')))

        # Числовой инвариант автосохранения: 12 полей → ровно 12 строк, raw есть, баллов нет.
        invariant = attempt('invariant')
        self.assertIsNone(invariant.submitted_at)
        rows = invariant.answers.all()
        self.assertEqual(rows.count(), 12)
        self.assertEqual(rows.exclude(raw__isnull=True).count(), 12)
        self.assertEqual(rows.filter(score__isnull=True).count(), 12)

        # Офлайн: набранное без связи доехало после её возвращения.
        warn = attempt('warn')
        raws = {a.item.number: a.raw for a in warn.answers.select_related('item')}
        self.assertEqual(raws.get(2), 'офлайн')
        self.assertEqual(raws.get(1), 'абум')

        # «Время вышло»: сдалось само, введённое засчитано.
        fast = attempt('fast')
        self.assertTrue(fast.is_auto_submitted)
        self.assertEqual(fast.submitted_at, fast.expires_at)
        self.assertEqual(fast.answers.get(item__number=1).raw, 'абум')
        self.assertEqual(fast.score, D('2.00'))

        # Телефон: сдал с телефона.
        phone = attempt('phone')
        self.assertIsNotNone(phone.submitted_at)
        self.assertEqual(phone.answers.get(item__number=12).raw, 'слово12')
