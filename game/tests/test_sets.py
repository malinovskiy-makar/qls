"""
Тесты сущности «Набор» и конструктора учителя (Фаза 3).

Набор — забег с ЗАРАНЕЕ ЗАФИКСИРОВАННЫМ списком вопросов. Именно из этого
следуют все инварианты фазы:
- выдаются ровно те вопросы и ровно в том порядке (иначе сравнение
  результатов нечестно);
- добора из общего пула нет;
- исчезнувший из кэша вопрос молча пропускается (пул — кэш, его
  пересобирают);
- список кончился, а игрок жив → концовка set_done;
- вторая попытка авторизованного отбивается сервером.
"""
import datetime
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from game.models import GameQuestion, GameResult, GameSet, make_code, normalize_code
from problems.models import Problem

User = get_user_model()


def make_q(n=1, qtype='single'):
    out = []
    for i in range(n):
        p = Problem.objects.create(
            title='Т%d' % i, statement='Условие %d' % i,
            problem_type='тест: один ответ', answer='а',
            status=Problem.Status.PUBLISHED)
        out.append(GameQuestion.objects.create(
            problem=p, question_type=qtype, question='Вопрос %d?' % i,
            options=['а', 'б', 'в'], correct_index=0, difficulty=3,
            topics=['Спрос и предложение'], lang='ru', source_group='books'))
    return out


def make_set(questions, **kw):
    defaults = dict(mode='blitz', kind='custom', title='Набор',
                    question_ids=[q.id for q in questions],
                    filter_snapshot={}, attempts_allowed=1)
    defaults.update(kw)
    return GameSet.objects.create(**defaults)


class CodeTests(TestCase):
    def test_code_alphabet_has_no_confusing_letters(self):
        from game.models import CODE_ALPHABET
        for ch in 'ILOU':
            self.assertNotIn(ch, CODE_ALPHABET)

    def test_result_code_and_set_code_share_one_generator(self):
        """Копия генератора разъехалась бы с алфавитом — функция одна."""
        from game import models
        self.assertIs(models.make_result_code, models.make_code)

    def test_normalize_code_ignores_case_and_spaces(self):
        self.assertEqual(normalize_code(' ab 12 cd '), 'AB12CD')
        self.assertEqual(normalize_code(None), '')


class SetRunTests(TestCase):
    """Забег по набору: те же вопросы, тот же порядок, без добора."""

    def setUp(self):
        self.qs = make_q(4)
        self.extra = make_q(3)         # эти в набор НЕ входят
        self.gset = make_set(self.qs)
        self.url = reverse('game:session_start_set', args=[self.gset.code])

    def _play_all(self):
        d = self.client.get(self.url).json()
        served = [d['question']['id']]
        while True:
            r = self.client.get(reverse('game:question')).json()
            if 'question' not in r:
                break
            served.append(r['question']['id'])
        return served

    def test_serves_exactly_the_set_in_order(self):
        self.assertEqual(self._play_all(), self.gset.question_ids)

    def test_no_top_up_from_the_common_pool(self):
        served = self._play_all()
        self.assertEqual(len(served), 4)
        self.assertFalse(set(served) & {q.id for q in self.extra})

    def test_vanished_question_is_skipped_silently(self):
        """Пул пересобрали — вопрос исчез. Забег просто короче."""
        self.qs[1].delete()
        served = self._play_all()
        self.assertEqual(len(served), 3)

    def test_case_insensitive_code(self):
        url = reverse('game:session_start_set',
                      args=[self.gset.code.lower()])
        self.assertTrue(self.client.get(url).json()['ok'])

    def test_finishing_the_list_gives_set_done(self):
        d = self.client.get(self.url).json()
        qid = d['question']['id']
        while True:
            self.client.post(reverse('game:answer'),
                             json.dumps({'question_id': qid, 'choice': 0}),
                             content_type='application/json')
            r = self.client.get(reverse('game:question')).json()
            if 'question' not in r:
                break
            qid = r['question']['id']
        s = self.client.post(reverse('game:session_finish'),
                             json.dumps({'reason': 'done'}),
                             content_type='application/json').json()
        self.assertEqual(s['summary']['ended_reason'], 'set_done')

    def test_result_is_linked_to_the_set(self):
        d = self.client.get(self.url).json()
        self.client.post(reverse('game:answer'),
                         json.dumps({'question_id': d['question']['id'],
                                     'choice': 0}),
                         content_type='application/json')
        body = self.client.post(reverse('game:session_finish'),
                                json.dumps({'reason': 'done'}),
                                content_type='application/json').json()
        self.assertEqual(body['share']['set']['code'], self.gset.code)
        r = GameResult.objects.get(code=body['share']['code'])
        self.assertEqual(r.game_set_id, self.gset.id)
        self.assertEqual(len(r.question_outcomes), 1)


class AttemptLimitTests(TestCase):
    def setUp(self):
        self.qs = make_q(2)
        self.gset = make_set(self.qs)
        self.url = reverse('game:session_start_set', args=[self.gset.code])

    def _finish_a_run(self):
        d = self.client.get(self.url).json()
        self.client.post(reverse('game:answer'),
                         json.dumps({'question_id': d['question']['id'],
                                     'choice': 0}),
                         content_type='application/json')
        return self.client.post(reverse('game:session_finish'),
                                json.dumps({'reason': 'done'}),
                                content_type='application/json')

    def test_second_attempt_of_a_logged_in_player_is_refused(self):
        User.objects.create_user(username='u', password='pw12345')
        self.client.login(username='u', password='pw12345')
        self._finish_a_run()
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 409)

    def test_anonymous_second_attempt_is_refused_by_session(self):
        """Для анонима защита слабая (сессия + localStorage) — так решено
        сознательно: регистрация убила бы публичность игры."""
        self._finish_a_run()
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 409)

    def test_attempts_allowed_two_lets_the_second_run_through(self):
        self.gset.attempts_allowed = 2
        self.gset.save(update_fields=['attempts_allowed'])
        self._finish_a_run()
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_abandoned_run_does_not_spend_the_attempt(self):
        """Забег начали и бросили, не завершив, — попытка цела."""
        self.client.get(self.url)
        self.assertEqual(self.client.get(self.url).status_code, 200)


class SetPagesTests(TestCase):
    def setUp(self):
        self.qs = make_q(3)
        self.gset = make_set(self.qs)

    def test_set_page_does_not_leak_questions(self):
        """★ Требование безопасности: страница набора НЕ отдаёт вопросы.

        Иначе автор дуэли (Фаза 5) увидел бы задания до игры."""
        html = self.client.get(reverse('game:set_page',
                                       args=[self.gset.code])).content.decode()
        for q in self.qs:
            self.assertNotIn(q.question, html)
        self.assertIn(self.gset.code, html)

    def test_board_address_leads_to_the_set_page_with_its_board(self):
        u"""С 17.09.2026 (P6) доска живёт на странице набора: старый адрес — переход."""
        r = self.client.get(reverse('game:set_board', args=[self.gset.code]))
        self.assertRedirects(r, reverse('game:set_page', args=[self.gset.code]))
        self.assertContains(self.client.get(r['Location']), 'Кто прошёл')

    def test_unknown_code_is_404(self):
        r = self.client.get(reverse('game:set_page', args=['ZZZZZZZZ']))
        self.assertEqual(r.status_code, 404)


class TeacherConstructorTests(TestCase):
    def setUp(self):
        self.qs = make_q(3)
        self.numeric = GameQuestion.objects.create(
            problem=make_q(1)[0].problem, question_type='numeric',
            question='Сколько?', options=[], correct_value='12',
            difficulty=3, topics=[], lang='ru', part=None)
        self.teacher = User.objects.create_user(
            username='t', password='pw12345', role='teacher')
        self.student = User.objects.create_user(
            username='s', password='pw12345', role='student')

    def test_student_cannot_open_the_constructor(self):
        self.client.login(username='s', password='pw12345')
        r = self.client.get(reverse('teacher:game_set_create'))
        self.assertIn(r.status_code, (302, 403))

    def test_teacher_sees_step_one_first(self):
        """★ Режим выбирается ПЕРВЫМ: набор для «Классики» может содержать
        только числовые вопросы. Дай собирать сначала — половина набора
        окажется несовместимой."""
        self.client.login(username='t', password='pw12345')
        r = self.client.get(reverse('teacher:game_set_create'))
        self.assertContains(r, 'Сначала режим')
        self.assertNotContains(r, 'Здесь только вопросы, пригодные для игры')

    def test_step_two_filters_the_pool_by_question_type(self):
        self.client.login(username='t', password='pw12345')
        r = self.client.get(reverse('teacher:game_set_create'),
                            {'mode': 'classic'})
        self.assertContains(r, 'Здесь только вопросы, пригодные для игры')
        self.assertContains(r, 'Сколько?')
        self.assertNotContains(r, 'Вопрос 0?')

    def test_teacher_sees_the_right_answer(self):
        """Учитель и так видит всё — собирать набор вслепую невозможно."""
        self.client.login(username='t', password='pw12345')
        r = self.client.get(reverse('teacher:game_set_create'),
                            {'mode': 'classic'})
        self.assertContains(r, 'ответ: 12')

    def test_saving_keeps_the_order(self):
        self.client.login(username='t', password='pw12345')
        ids = [self.qs[2].id, self.qs[0].id, self.qs[1].id]
        r = self.client.post(reverse('teacher:game_set_create'), {
            'mode': 'blitz', 'title': 'Мой набор',
            'question_ids': ','.join(str(i) for i in ids), 'attempts': '1'})
        gset = GameSet.objects.get(title='Мой набор')
        self.assertEqual(gset.question_ids, ids)
        self.assertEqual(gset.author, self.teacher)
        self.assertRedirects(r, reverse('teacher:game_set_detail',
                                        args=[gset.code]))

    def test_saving_drops_questions_of_a_foreign_type(self):
        self.client.login(username='t', password='pw12345')
        ids = [self.qs[0].id, self.numeric.id]
        self.client.post(reverse('teacher:game_set_create'), {
            'mode': 'blitz', 'title': 'Смесь',
            'question_ids': ','.join(str(i) for i in ids)})
        gset = GameSet.objects.get(title='Смесь')
        self.assertEqual(gset.question_ids, [self.qs[0].id])

    def test_foreign_set_is_not_editable(self):
        other = User.objects.create_user(username='o', password='pw12345',
                                         role='teacher')
        gset = make_set(self.qs, author=other, title='Чужой')
        self.client.login(username='t', password='pw12345')
        r = self.client.get(reverse('teacher:game_set_detail',
                                    args=[gset.code]))
        self.assertRedirects(r, reverse('teacher:game_sets'))

    def test_fill_api_returns_questions_of_the_right_type(self):
        self.client.login(username='t', password='pw12345')
        r = self.client.post(reverse('teacher:api_game_set_fill'),
                             json.dumps({'mode': 'blitz', 'n': 2,
                                         'exclude': []}),
                             content_type='application/json')
        got = r.json()['questions']
        self.assertLessEqual(len(got), 2)
        self.assertTrue(all(q['id'] != self.numeric.id for q in got))

    def test_sets_list_shows_only_mine(self):
        other = User.objects.create_user(username='o2', password='pw12345',
                                         role='teacher')
        make_set(self.qs, author=self.teacher, title='Мой')
        make_set(self.qs, author=other, title='Чужой')
        self.client.login(username='t', password='pw12345')
        r = self.client.get(reverse('teacher:game_sets'))
        self.assertContains(r, 'Мой')
        self.assertNotContains(r, 'Чужой')


class SetBoardStatsTests(TestCase):
    """Разбивка по вопросам НАБОРА — доля верных внутри набора."""

    def test_question_stats_are_counted_within_the_set(self):
        from game.views import set_question_stats
        qs = make_q(2)
        gset = make_set(qs)
        GameResult.objects.create(
            code=make_code(), mode='blitz', game_set=gset, score=100,
            question_outcomes=[
                {'question_id': qs[0].id, 'number': 1, 'outcome': 'correct'},
                {'question_id': qs[1].id, 'number': 2, 'outcome': 'wrong'}])
        GameResult.objects.create(
            code=make_code(), mode='blitz', game_set=gset, score=0,
            question_outcomes=[
                {'question_id': qs[0].id, 'number': 1, 'outcome': 'wrong'},
                {'question_id': qs[1].id, 'number': 2, 'outcome': 'skip'}])
        rows = set_question_stats(gset)
        self.assertEqual(rows[0]['percent'], 50)     # 1 из 2 попыток
        self.assertEqual(rows[1]['percent'], 0)      # пропуск в долю не идёт
        self.assertEqual(rows[1]['skip'], 1)


# ─── P6: страница набора ученика (решение владельца 17.09.2026, ADR 0115) ──

class SetInvitationPageTests(TestCase):
    u"""`/game/s/<код>/` — отдельная страница: приглашение и доска набора."""

    def setUp(self):
        self.qs = make_q(5)
        self.teacher = User.objects.create_user(username='uchitel', password='pw12345')
        self.gset = make_set(self.qs, title='Контрольная по спросу', author=self.teacher)
        self.url = reverse('game:set_page', args=[self.gset.code])

    def page(self, url=None, status=200):
        r = self.client.get(url or self.url)
        self.assertEqual(r.status_code, status)
        return r.content.decode()

    def result(self, user=None, score=100, **kw):
        return GameResult.objects.create(code=make_code(), mode='blitz', game_set=self.gset, user=user,
                                         score=score, correct_count=4, total_count=5, **kw)

    def test_separate_page_with_invitation_and_both_board_parts(self):
        html = self.page()
        self.assertNotIn('id="mode-grid"', html)
        self.assertNotIn('id="screen-start"', html)
        self.assertIn('Контрольная по спросу', html)
        self.assertIn('автор uchitel', html)
        self.assertIn('Блиц · один верный ответ', html)
        self.assertIn('<b>5</b> вопросов', html)
        self.assertIn('href="%s?auto=1"' % self.url, html)
        self.assertIn('Кто прошёл · 0', html)
        self.assertIn('Где ошиблись', html)
        self.assertNotIn('открыт до', html)

    def test_guest_is_warned_and_offered_to_log_in(self):
        html = self.page()
        self.assertIn('учитель вас не узнает', html)
        self.assertIn('/login/?next=%s' % self.url, html)

    def test_no_play_button_when_attempts_are_spent(self):
        student = User.objects.create_user(username='uchenik', password='pw12345')
        self.result(student, score=186)
        self.client.force_login(student)
        html = self.page()
        self.assertNotIn('?auto=1', html)
        self.assertIn('попытки закончились', html)
        self.assertIn('Ваш результат', html)
        self.assertIn('Страница результата', html)

    def test_closed_set_says_so_and_deadline_chip_only_with_closes_at(self):
        self.gset.closes_at = timezone.now() - datetime.timedelta(days=1)
        self.gset.save(update_fields=['closes_at'])
        html = self.page()
        self.assertIn('Набор закрыт', html)
        self.assertIn('открыт до', html)
        self.assertNotIn('?auto=1', html)

    def test_question_texts_for_the_player_and_author_only(self):
        text = self.qs[0].question
        student = User.objects.create_user(username='sygral', password='pw12345')
        self.result(student, question_outcomes=[{'question_id': self.qs[0].id, 'outcome': 'wrong'}])
        self.assertNotIn(text, self.page())
        self.assertIn('текст откроется после вашей попытки', self.page())
        self.client.force_login(student)
        self.assertIn(text, self.page())
        self.client.force_login(self.teacher)
        self.assertIn(text, self.page())

    def test_anonymous_rounds_are_on_the_board_as_anonymous(self):
        self.result(None, score=160)
        self.result(User.objects.create_user(username='katya', password='pw12345'), score=214)
        html = self.page()
        self.assertIn('Кто прошёл · 2', html)
        self.assertIn('class="who anon">аноним</td>', html)

    def test_board_address_redirects_and_daily_without_auto_goes_to_daily(self):
        r = self.client.get(reverse('game:set_board', args=[self.gset.code]))
        self.assertRedirects(r, self.url)
        from game import daily as daily_mod
        daily = daily_mod.get_daily_set('blitz')
        r = self.client.get(reverse('game:set_page', args=[daily.code]))
        self.assertRedirects(r, reverse('game:daily'))
        r = self.client.get(reverse('game:set_page', args=[daily.code]) + '?auto=1')
        self.assertEqual(r.status_code, 200)

    def test_autostart_plays_on_the_game_page(self):
        html = self.page(self.url + '?auto=1')
        self.assertIn('id="screen-start"', html)
        self.assertIn('autostarting', html)

    def test_wrong_code_is_a_game_page_with_status_404(self):
        for url in (reverse('game:set_page', args=['QQQQ1111']), reverse('game:set_board', args=['QQQQ1111'])):
            html = self.page(url, status=404)
            self.assertIn('Набора с кодом', html)
            self.assertIn('QQQQ1111', html)
            self.assertIn('/game/api/set_check/', html)
            self.assertNotIn('занятие или работа', html)

    def test_finish_of_a_teacher_set_leads_back_to_its_page(self):
        student = User.objects.create_user(username='finish', password='pw12345')
        self.client.force_login(student)
        d = self.client.get(reverse('game:session_start_set', args=[self.gset.code])).json()
        self.client.post(reverse('game:answer'), json.dumps({'question_id': d['question']['id'], 'choice': 0}),
                         content_type='application/json')
        data = self.client.post(reverse('game:session_finish'), json.dumps({'reason': 'done'}),
                                content_type='application/json').json()
        self.assertTrue(data['share']['set']['board_url'].endswith(self.url))
