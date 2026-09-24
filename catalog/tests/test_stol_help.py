"""Панель помощи «Стола» и тест (README §4, §5).

Лестница «берите столько помощи, сколько нужно» — ступени только при данных;
после первого действия — лента по времени, которая переживает перезагрузку:
открытые подсказки и решение рисует сервер из прогресса ученика. Без ключа
чата нет ни разговора, ни поля — подсказки и решение остаются. «Почему так»
у теста — без повтора верного варианта и без разбалловки жюри.
"""
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from catalog.preview import strip_correct_repeat, strip_score_tails
from problems.models import Hint, ProblemPart
from problems.models_platform import ProblemProgress
from problems.tests.factories import make_problem, make_topic, make_user

#: Живое «Почему так» теста 63243 (аудит S3, 18.09.2026) — как лежит в банке.
EXPLAIN_63243 = ('(b) Центральный банк Российской Федерации.  Пояснение: Ключевую ставку '
                 'в РФ устанавливает ЦБ РФ.  ( $4$ балла)')
OPTIONS_63243 = ('Правительство Российской Федерации', 'Центральный банк Российской Федерации',
                 'Министерство финансов Российской Федерации', 'Администрация Президента Российской Федерации')


def _help(html):
    start = html.index('<aside class="help-panel"')
    return html[start:html.index('</aside>', start)]


@override_settings(CATALOG_CHAT_PROVIDER='fake', AI_PROVIDER='fake')
class HelpPanelTests(TestCase):

    def setUp(self):
        cache.clear()
        topic = make_topic('Монополия и ценовая дискриминация', is_canonical=True)
        self.problem = make_problem('Монополист продаёт электроэнергию.', topic=topic,
                                    title='Двухступенчатый тариф монополиста',
                                    solution='Полное решение задачи длиннее тридцати знаков: $MR = MC$.')
        for i in range(3):
            Hint.objects.create(problem=self.problem, text='Подсказка номер %d.' % (i + 1), order=i)
        self.student = make_user('help_student')
        self.client.force_login(self.student)

    def _page(self, problem=None):
        return self.client.get(reverse('catalog:problem_detail', args=[(problem or self.problem).pk])).content.decode()

    def test_empty_state_is_the_ladder_with_steps_only_from_data(self):
        panel = _help(self._page())
        # Вводной фразы нет: вместо неё совет один раз (решение владельца 24.09.2026),
        # сервер рисует его скрытым — открывает скрипт по ключу в браузере.
        self.assertNotIn('ladder-lead', panel)
        self.assertIn('<div class="help-tipcard" id="help-tipcard" hidden>', panel)
        self.assertNotIn('Берите столько помощи', panel)
        self.assertIn('<div class="help-ladder" id="help-ladder">', panel)
        self.assertIn('<b>Подсказка 1 из 3</b>', panel)
        self.assertIn('data-step="ai"', panel)
        self.assertIn('data-step="sol"', panel)
        # Ответов по пунктам нет — ступени нет (решение владельца 17.09).
        self.assertNotIn('data-step="part"', panel)
        self.assertIn('Пока ничем не пользовались', panel)
        # Постоянной подсказки внизу панели больше нет (24.09.2026).
        self.assertNotIn('Выделите фрагмент условия, чтобы обсудить его с ИИ', panel)

    def test_start_block_hides_once_a_chat_exists_and_for_guests(self):
        """24.09.2026: стартовые фразы — только пока лента пуста и только вошедшему."""
        from problems.models_platform import ChatTurn
        ChatTurn.objects.create(user=self.student, problem=self.problem, user_text='Вопрос',
                                reply='Ответ помощника')
        panel = _help(self._page())
        self.assertIn('id="help-ladder" hidden', panel)
        self.assertNotIn('Выделите фрагмент условия, чтобы обсудить его с ИИ', panel)
        self.client.logout()
        guest = _help(self._page())
        self.assertNotIn('help-tipcard', guest)
        self.assertNotIn('Выделите фрагмент условия', guest)

    def test_part_answer_step_appears_with_data(self):
        ProblemPart.objects.create(problem=self.problem, label='а', order=0,
                                   statement='Найдите цену.', answer='$p = 10$')
        html = self._page()
        self.assertIn('data-step="part"', _help(html))
        # Сам ответ — запросом (24.09.2026, ADR 0129), в разметке только выбор пункта.
        self.assertIn('<template id="help-parts-tpl">', html)
        self.assertNotIn('$p = 10$', html)

    def test_reload_restores_opened_hints_and_the_solution(self):
        ProblemProgress.objects.create(user=self.student, problem=self.problem, status='opened',
                                       hints_opened=2, solution_viewed=True)
        panel = _help(self._page())
        self.assertEqual(panel.count('class="feed-card feed-hint"'), 2)
        self.assertIn('Подсказка номер 2.', panel)
        self.assertNotIn('Подсказка номер 3.', panel)
        self.assertIn('id="help-ladder" hidden', panel)
        self.assertIn('Подсказок 2 из 3 · решение', panel)
        self.assertIn('<span class="n" id="hint-n">3 из 3</span>', panel)
        self.assertIn('class="feed-card feed-sol sol is-on"', panel)
        self.assertIn('id="sol-btn" data-step="sol" hidden', panel)

    def test_hint_answer_and_reload_share_one_shape(self):
        data = self.client.get(reverse('catalog:api_hint', args=[self.problem.pk, 1])).json()
        self.assertEqual(set(data), {'n', 'total', 'text', 'ai', 'reviewed', 'part'})
        self.assertEqual(ProblemProgress.objects.get(user=self.student, problem=self.problem).hints_opened, 1)

    def test_confirmation_text_is_the_readme_one(self):
        html = self._page()
        self.assertIn('Открыть эталонное решение? В статистике задача будет отмечена как «посмотрел решение».', html)
        self.assertNotIn('до отправки', html)

    def test_no_chat_key_means_no_conversation_but_hints_and_solution_stay(self):
        with self.settings(CATALOG_CHAT_PROVIDER='anthropic', AI_PROVIDER='anthropic', ANTHROPIC_API_KEY=''):
            panel = _help(self._page())
        self.assertNotIn('id="ai-text"', panel)
        self.assertNotIn('data-step="ai"', panel)
        self.assertNotIn('Выделите фрагмент условия', panel)
        self.assertIn('<b>Подсказка 1 из 3</b>', panel)
        self.assertIn('data-step="sol"', panel)
        self.assertIn('id="hint-btn"', panel)

    def test_nothing_in_the_bank_draws_no_note(self):
        """24.09.2026: фразы «нет ни подсказок, ни решения» нет — остаётся ступень ИИ."""
        bare = make_problem('Задача без подсказок и решения.')
        panel = _help(self._page(bare))
        self.assertNotIn('ladder-none', panel)
        self.assertNotIn('остаётся ИИ', panel)
        self.assertIn('data-step="ai"', panel)

    def test_part_ask_button_only_with_the_chat(self):
        ProblemPart.objects.create(problem=self.problem, label='а', order=0, statement='Найдите цену.')
        self.assertIn('data-ask-part aria-label="Спросить ИИ про пункт а)"', self._page())
        with self.settings(CATALOG_CHAT_PROVIDER='anthropic', ANTHROPIC_API_KEY=''):
            self.assertNotIn('data-ask-part', self._page())

    def test_attempt_card_is_gone_from_the_centre(self):
        html = self._page()
        centre = html[html.index('id="stol-center"'):html.index('id="stol-help"')]
        self.assertNotIn('id="sv"', centre)
        self.assertNotIn('id="sv-text"', html)
        self.assertIn('data-mode="check"', _help(html))


class TestExplanationTests(TestCase):

    def setUp(self):
        cache.clear()
        self.test = make_problem('Кто устанавливает ключевую ставку в России?',
                                 problem_type='тест: один ответ', answer='b', solution=EXPLAIN_63243)
        for i, (label, text) in enumerate(zip('abcd', OPTIONS_63243)):
            ProblemPart.objects.create(problem=self.test, label=label, order=i, statement=text)

    def test_why_has_no_repeat_and_no_score_on_the_live_example(self):
        # «Почему так» — решение теста: только вошедшему (ADR 0129).
        self.client.force_login(make_user('why_reader'))
        html = self.client.get(reverse('catalog:problem_detail', args=[self.test.pk])).content.decode()
        why = html[html.index('id="expl"'):]
        why = why[:why.index('</section>')]
        self.assertIn('Ключевую ставку в РФ устанавливает ЦБ РФ.', why)
        self.assertNotIn('Центральный банк Российской Федерации', why)
        self.assertNotIn('Пояснение', why)
        self.assertNotIn('балла', why)

    def test_test_ladder_offers_the_answer_not_the_solution(self):
        panel = _help(self.client.get(reverse('catalog:problem_detail', args=[self.test.pk])).content.decode())
        self.assertIn('data-step="reveal"', panel)
        self.assertNotIn('data-step="sol"', panel)


class StripCorrectRepeatTests(SimpleTestCase):
    GAME = {'correct': {'b'}, 'options': [{'label': 'a', 'text': 'Правительство'},
                                          {'label': 'b', 'text': 'Центральный банк'}]}

    def test_cuts_only_a_correct_label(self):
        self.assertEqual(strip_correct_repeat('(b) Центральный банк. Пояснение: Так устроено.', self.GAME),
                         'Так устроено.')
        self.assertEqual(strip_correct_repeat('(a) Правительство. Пояснение: Нет.', self.GAME),
                         '(a) Правительство. Пояснение: Нет.')

    def test_repeat_without_the_word_explanation(self):
        self.assertEqual(strip_correct_repeat('(b) Центральный банк.\nСтавку задаёт ЦБ.', self.GAME),
                         'Ставку задаёт ЦБ.')

    def test_plain_explanation_is_left_alone(self):
        self.assertEqual(strip_correct_repeat('Ставку задаёт ЦБ.', self.GAME), 'Ставку задаёт ЦБ.')

    def test_score_tail_with_a_formula_number(self):
        self.assertEqual(strip_score_tails('Ответ верный.  ( $4$ балла)'), 'Ответ верный.')
