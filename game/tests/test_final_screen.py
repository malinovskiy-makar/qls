# -*- coding: utf-8 -*-
u"""Экран итога раунда (фаза P3 редизайна 17.09.2026, ADR 0111): разметка и код.

Вердикт и действия сверху, одна карточка «Ход раунда» вместо девяти графиков,
ошибки и пропуски списком на странице, пустых карточек нет. Данные сервера —
`test_final.py`; в настоящем браузере (действия выше 800 px, дата в часовом
поясе зрителя, карточки анонима) — `test_browser_final.py`.
"""
import re

from django.test import TestCase

from game.tests.test_page_js import inline_js, page_source


class FinalScreenMarkupTests(TestCase):
    def setUp(self):
        self.src = page_source()
        self.js = inline_js(self.src)
        i = self.src.index('<section id="screen-final"')
        self.final = self.src[i:self.src.index('</section>\n\n  </div>\n</section>', i)]

    def body(self, name):
        m = re.search(r'function %s\([^)]*\) \{(.*?)\n  \}' % name, self.js, re.S)
        self.assertIsNotNone(m, '%s не найдена' % name)
        return m.group(1)

    def test_one_round_flow_card_instead_of_nine_charts(self):
        self.assertEqual(self.final.count('<h3>Ход раунда</h3>'), 1)
        for gone in ('chart-card', 'Лента ответов', 'Сколько думали', 'Время на ответ',
                     'Микро и макро', 'id="fin-share"', 'Разобрать все ошибки', 'det-body',
                     'Чисто! Ошибок нет'):
            self.assertNotIn(gone, self.src, gone)

    def test_actions_sit_in_the_verdict_card(self):
        verdict = self.final[:self.final.index('id="fin-flow"')]
        for button in ('id="btn-again"', 'id="btn-board"', 'id="btn-mistakes"',
                       'id="btn-review"', 'id="btn-share"', 'id="btn-catalog"'):
            self.assertIn(button, verdict, button)
        self.assertIn('<span>Сыграть ещё раз</span><kbd>Enter</kbd>', verdict)
        self.assertIn('ссылка на результат открывается у всех, без входа', verdict)

    def test_mistakes_are_a_list_on_the_page_not_behind_a_toggle(self):
        self.assertIn('<ul class="miss-list" id="miss-list"></ul>', self.final)
        self.assertIn("$('fin-misses').hidden = !misses.length;", self.body('paintMisses'))
        self.assertIn("scrollIntoView", self.js[self.js.index("$('btn-review').addEventListener"):])

    def test_empty_cards_are_hidden_instead_of_saying_nothing(self):
        self.assertIn("$('fin-points').hidden = !rows.length;", self.body('paintPoints'))
        self.assertIn("$('fin-topics').hidden = !rows.length;", self.body('paintTopics'))
        self.assertIn("$('fin-stars').hidden = !rows.length;", self.body('paintStars'))
        compare = self.body('paintCompare')
        self.assertIn("$('fin-login').hidden = authed;", compare)
        self.assertIn('runHistory.runs.length >= 2', compare)
        for empty in ('не набрано', 'не было', 'сравнивать пока не с чем'):
            self.assertNotIn(empty, self.final + self.body('paintFinal'), empty)

    def test_the_topic_layout_is_not_copied_a_second_time(self):
        u"""⚠️ ADR 0071: разделы — из `CFG.topic_groups`, не литералами."""
        body = self.body('paintGroups')
        self.assertIn('CFG.topic_groups', body)
        for literal in ('Микроэкономика', 'Макроэкономика', "'micro'", "'macro'", 'Эластичность'):
            self.assertNotIn(literal, body, literal)

    def test_charts_are_still_hand_drawn_svg_through_tokens(self):
        self.assertIn('var SVG_NS', self.js)
        for url in re.findall(r'<script[^>]*src="([^"]+)"', self.src):
            for lib in ('chart.js', 'd3', 'plotly', 'echarts', 'highcharts'):
                self.assertNotIn(lib, url.lower(), url)
        self.assertIn("'var(--rush-accent)'", self.body('chartCurve'))

    def test_local_storage_history_is_gone_entirely(self):
        for gone in ('econ_rush_history', 'saveRunToHistory', 'loadHistory', 'HISTORY_KEY'):
            self.assertNotIn(gone, self.src, gone)
        self.assertIn("api('/game/api/me/history/", self.js)


class FinalScreenLogicTests(TestCase):
    def setUp(self):
        self.js = inline_js(page_source())

    def body(self, name):
        m = re.search(r'function %s\([^)]*\) \{(.*?)\n  \}' % name, self.js, re.S)
        self.assertIsNotNone(m, '%s не найдена' % name)
        return m.group(1)

    def test_record_badge_comes_from_the_server_rule(self):
        notes = self.body('paintNotes')
        self.assertIn('badge.hidden = !(rec && rec.is_record);', notes)
        self.assertIn("'личный рекорд · было ' + rec.prev_best", notes)
        self.assertNotIn('localStorage', notes)

    def test_first_action_by_kind_of_round(self):
        actions = self.body('paintActions')
        daily = actions.split("setRun.kind === 'daily'", 1)[1].split("setRun.kind === 'duel'", 1)[0]
        self.assertIn('again.hidden = true;', daily)
        self.assertIn("'Доска дня'", daily)
        self.assertIn("'Следующий вызов: ' + nx.title", daily)
        duel = actions.split("setRun.kind === 'duel'", 1)[1].split('} else if (setRun) {', 1)[0]
        self.assertIn("'Итог дуэли'", duel)
        self.assertIn("$('btn-rematch').hidden = !(s.duel && s.duel.rival_done);", duel)
        teacher = actions.split('} else if (setRun) {', 1)[1]
        self.assertIn("'К набору и доске'", teacher)
        self.assertIn('again.hidden = !(s.attempts_left > 0);', teacher)
        self.assertIn("b.classList.toggle('fin-primary', b === primary);", actions)

    def test_enter_presses_the_primary_action(self):
        m = re.search(r"if \(state === 'finished'\) \{(.*?)\n    \}", self.js, re.S)
        self.assertIsNotNone(m)
        self.assertIn("document.querySelector('#fin-actions .fin-primary')", m.group(1))
        self.assertNotIn('startRun()', m.group(1))

    def test_score_counter_always_lands_on_the_total(self):
        u"""На бою 17.09 итог показал «6» при 52: кадры в фоне не идут."""
        self.assertIn('setTimeout(function () { scoreEl.textContent = total; }, 850);',
                      self.body('paintScore'))

    def test_date_is_the_saved_moment_in_the_viewers_time_zone(self):
        fmt = self.body('formatDate')
        self.assertIn("toLocaleString('ru-RU'", fmt)
        self.assertNotIn('timeZone', fmt)
        self.assertIn("$('fin-date').textContent = formatDate(s.played_at);", self.body('paintFinal'))

    def test_misses_collect_wrong_answers_and_skips(self):
        self.assertIn("misses.push(missEntry(q, d, 'wrong', given));", self.body('registerWrong'))
        self.assertIn("misses.push(missEntry(q, d, 'skip', ''));", self.body('skip'))
        self.assertIn("'пропуск → верный '", self.body('paintMisses'))

    def test_every_helper_the_final_screen_calls_is_defined(self):
        u"""Сборка итога однажды удалила `plural` вместе с соседней функцией:
        тесты разметки зеленели, а экран падал ReferenceError."""
        code = ''.join(self.body(n) for n in (
            'paintFinal', 'paintNotes', 'paintActions', 'paintFlow', 'paintGroups',
            'paintStars', 'paintPoints', 'paintHistory', 'paintUsual', 'paintMisses',
            'paintMissSolution', 'chartCurve'))
        defined = set(re.findall(r'\bfunction (\w+)\(', self.js))
        called = set(re.findall(r'(?<![.\w])([a-z]\w*)\(', code))
        # Глобали браузера, рисователь чертежей из static/game/figure.js,
        # локальные функции-выражения кривой и `var(` внутри строк цветов.
        browser = {'function', 'if', 'return', 'parseInt', 'setTimeout', 'String',
                   'requestAnimationFrame', 'encodeURIComponent', 'drawFigure',
                   'up', 'x', 'yScore', 'var'}
        self.assertEqual(sorted(called - defined - browser), [])

    def test_quit_round_has_its_own_title(self):
        self.assertIn("if (s.ended_reason === 'quit') return 'Вы вышли из раунда';",
                      self.body('titleText'))

    def test_accuracy_note_takes_the_threshold_from_config(self):
        notes = self.body('paintNotes')
        self.assertIn('CFG.accuracy_full_at', notes)
        self.assertNotIn('85', notes)
