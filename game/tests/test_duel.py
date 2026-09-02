"""
Тесты асинхронной дуэли (Фаза 5).

★ Главное требование безопасности фичи: набор дуэли собирается СЛУЧАЙНО
под выбранные фильтры, и автор вызова НЕ ВИДИТ вопросы до игры — он играет
их вслепую первым, наравне с соперником. Ни одна вьюха не имеет права
отдать список вопросов до того, как игрок их сыграл.
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from game import config
from game.models import GameQuestion, GameResult, GameSet, make_code
from problems.models import Problem

User = get_user_model()


def make_q(n, topic='Спрос и предложение', group='books'):
    out = []
    for i in range(n):
        p = Problem.objects.create(
            title='Т%d' % i, statement='Условие %d' % i,
            problem_type='тест: один ответ', answer='а',
            status=Problem.Status.PUBLISHED)
        out.append(GameQuestion.objects.create(
            problem=p, question_type='single',
            question='СЕКРЕТНЫЙ вопрос дуэли %d?' % i,
            options=['а', 'б', 'в'], correct_index=0, difficulty=3,
            topics=[topic], lang='ru', source_group=group))
    return out


class DuelCreationTests(TestCase):
    def setUp(self):
        self.qs = make_q(30)
        # ⚠️ Дуэль теперь только для вошедших: она сравнивает двоих ПО
        # ИМЕНИ, а у анонима имени нет и на доске он был бы «кто-то».
        from problems.models import User
        self.me = User.objects.create_user(username='duelist', password='p12345')
        self.client.force_login(self.me)

    def test_new_duel_creates_a_set_and_sends_to_play(self):
        r = self.client.get(reverse('game:duel_new'), {'mode': 'blitz'})
        gset = GameSet.objects.get(kind='duel')
        self.assertEqual(gset.size, config.DUEL_SIZE)
        self.assertRedirects(
            r, reverse('game:set_page', args=[gset.code]) + '?auto=1',
            fetch_redirect_response=False)

    def test_duel_respects_the_filter(self):
        make_q(5, topic='Рынок труда')
        self.client.get(reverse('game:duel_new'),
                        {'mode': 'blitz', 'topics': 'Рынок труда'})
        gset = GameSet.objects.get(kind='duel')
        chosen = GameQuestion.objects.filter(id__in=gset.question_ids)
        self.assertTrue(all('Рынок труда' in q.topics for q in chosen))
        self.assertEqual(gset.filter_snapshot['topics'], ['Рынок труда'])

    def test_empty_filter_does_not_create_an_empty_duel(self):
        """Пустая дуэль = ссылка в никуда. Лучше честно сказать."""
        r = self.client.get(reverse('game:duel_new'),
                            {'mode': 'blitz', 'topics': 'Эконометрика и анализ данных'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Дуэль не собралась')
        self.assertFalse(GameSet.objects.filter(kind='duel').exists())

    def test_author_is_recorded_when_logged_in(self):
        u = User.objects.create_user(username='u', password='pw12345')
        self.client.login(username='u', password='pw12345')
        self.client.get(reverse('game:duel_new'), {'mode': 'blitz'})
        self.assertEqual(GameSet.objects.get(kind='duel').author, u)


class DuelSecrecyTests(TestCase):
    """★ Вопросы дуэли не утекают ни одной вьюхой до игры."""

    def setUp(self):
        self.qs = make_q(20)
        from problems.models import User
        self.client.force_login(
            User.objects.create_user(username='duelist', password='p12345'))
        self.client.get(reverse('game:duel_new'), {'mode': 'blitz'})
        self.gset = GameSet.objects.get(kind='duel')

    def _assert_no_questions(self, resp):
        html = resp.content.decode('utf-8')
        for q in GameQuestion.objects.filter(id__in=self.gset.question_ids):
            self.assertNotIn(q.question, html)
        # и текст «СЕКРЕТНЫЙ» на всякий случай целиком
        self.assertNotIn('СЕКРЕТНЫЙ вопрос дуэли', html)

    def test_duel_page_does_not_leak(self):
        self._assert_no_questions(
            self.client.get(reverse('game:duel', args=[self.gset.code])))

    def test_set_page_does_not_leak(self):
        self._assert_no_questions(
            self.client.get(reverse('game:set_page', args=[self.gset.code])))

    def test_set_board_does_not_leak_before_anyone_played(self):
        self._assert_no_questions(
            self.client.get(reverse('game:set_board', args=[self.gset.code])))

    def test_start_payload_gives_one_question_at_a_time(self):
        d = self.client.get(reverse('game:session_start_set',
                                    args=[self.gset.code])).json()
        self.assertIn('question', d)
        self.assertNotIn('question_ids', json.dumps(d))
        self.assertNotIn('questions', d)


class DuelFlowTests(TestCase):
    def setUp(self):
        self.qs = make_q(20)
        from problems.models import User
        self.me = User.objects.create_user(username='duelist', password='p12345')
        self.client.force_login(self.me)

    def _play(self, client, code, wrong=0):
        """Сыграть дуэль до конца. wrong — сколько ответов сделать неверными."""
        d = client.get(reverse('game:session_start_set', args=[code])).json()
        qid = d['question']['id']
        i = 0
        while True:
            choice = 1 if i < wrong else 0
            r = client.post(reverse('game:answer'),
                            json.dumps({'question_id': qid, 'choice': choice}),
                            content_type='application/json').json()
            i += 1
            if r.get('game_over'):
                break
            nxt = client.get(reverse('game:question')).json()
            if 'question' not in nxt:
                break
            qid = nxt['question']['id']
        return client.post(reverse('game:session_finish'),
                           json.dumps({'reason': 'done'}),
                           content_type='application/json').json()

    def test_second_attempt_of_the_same_player_is_refused(self):
        self.client.get(reverse('game:duel_new'), {'mode': 'blitz'})
        gset = GameSet.objects.get(kind='duel')
        self._play(self.client, gset.code)
        r = self.client.get(reverse('game:session_start_set',
                                    args=[gset.code]))
        self.assertEqual(r.status_code, 409)

    def _logged(self, name):
        """Отдельный вошедший клиент: дуэль сравнивает людей по имени."""
        from django.test import Client
        from problems.models import User
        c = Client()
        c.force_login(User.objects.create_user(username=name, password='p12345'))
        return c

    def test_comparison_is_computed_for_two_players(self):
        author = self._logged('avtor')
        author.get(reverse('game:duel_new'), {'mode': 'blitz'})
        gset = GameSet.objects.get(kind='duel')
        self._play(author, gset.code)              # автор — без ошибок

        rival = self._logged('sopernik')
        self._play(rival, gset.code, wrong=1)      # соперник ошибается

        page = rival.get(reverse('game:duel', args=[gset.code]))
        self.assertEqual(page.status_code, 200)
        cmp_ = page.context['compare']
        self.assertIsNotNone(cmp_)
        self.assertEqual(len(cmp_['strip']), gset.size)
        self.assertIn('Побеждает', cmp_['verdict'])
        self.assertGreater(cmp_['a']['score'], cmp_['b']['score'])

    def test_third_player_appears_on_the_board(self):
        a = self._logged('igrok_a')
        b = self._logged('igrok_b')
        c = self._logged('igrok_v')
        a.get(reverse('game:duel_new'), {'mode': 'blitz'})
        gset = GameSet.objects.get(kind='duel')
        for cl in (a, b, c):
            self._play(cl, gset.code)
        page = c.get(reverse('game:duel', args=[gset.code]))
        self.assertEqual(len(page.context['rows']), 3)
        self.assertEqual(sum(1 for r in page.context['rows'] if r['is_author']), 1)

    def test_challenge_again_makes_a_new_set_with_the_same_filter(self):
        self.client.get(reverse('game:duel_new'),
                        {'mode': 'blitz', 'topics': 'Спрос и предложение'})
        first = GameSet.objects.get(kind='duel')
        page = self.client.get(reverse('game:duel', args=[first.code]))
        again = page.context['again_url']
        self.assertIn('topics=', again)
        self.client.get(again)
        sets = list(GameSet.objects.filter(kind='duel').order_by('id'))
        self.assertEqual(len(sets), 2)
        self.assertNotEqual(sets[0].code, sets[1].code)
        self.assertEqual(sets[1].filter_snapshot['topics'],
                         ['Спрос и предложение'])

    def test_result_links_back_to_the_duel_page(self):
        self.client.get(reverse('game:duel_new'), {'mode': 'blitz'})
        gset = GameSet.objects.get(kind='duel')
        body = self._play(self.client, gset.code)
        self.assertIn('/game/d/%s/' % gset.code, body['share']['set']['board_url'])


class DuelPageTests(TestCase):
    def test_only_duel_sets_are_served_here(self):
        make_q(5)
        gset = GameSet.objects.create(
            code=make_code(), mode='blitz', kind='custom',
            question_ids=[], filter_snapshot={})
        r = self.client.get(reverse('game:duel', args=[gset.code]))
        self.assertEqual(r.status_code, 404)

    def test_filter_text_is_human_readable(self):
        from game.views import _filter_text
        text = _filter_text({'topics': ['Эластичность'], 'sources': ['vsosh'],
                             'stars': [2, 3, 4]})
        self.assertIn('Эластичность', text)
        self.assertIn('ВсОШ', text)
        self.assertIn('2★', text)
        text2 = _filter_text({'topics': [], 'sources': [], 'stars': []})
        self.assertIn('все темы', text2)
        self.assertIn('любая сложность', text2)

    def test_filter_text_survives_an_old_snapshot(self):
        """⚠️ В базе лежат дуэли и наборы, созданные ДО множества звёзд —
        со снимком `dmin`/`dmax`. Упасть на чужой старой дуэли нельзя."""
        from game.views import _filter_text
        text = _filter_text({'topics': ['Эластичность'], 'sources': [],
                             'dmin': 2, 'dmax': 4})
        self.assertIn('Эластичность', text)
        self.assertIn('2★', text)


class DuelLoginBoundaryTests(TestCase):
    u"""Дуэль — только для вошедших (решение владельца, фаза 7).

    Отрицательные тесты: аноним не создаёт вызов и не принимает его.
    Страница дуэли при этом ОТКРЫТА всем — по ссылке приходит соперник, и
    первое, что он должен увидеть, это во что его зовут.
    """

    def setUp(self):
        from problems.models import User
        self.qs = make_q(20)
        self.author = User.objects.create_user(username='avtor',
                                               password='p12345')
        self.client.force_login(self.author)
        self.client.get(reverse('game:duel_new'), {'mode': 'blitz'})
        self.gset = GameSet.objects.get(kind='duel')
        self.client.logout()

    def test_anonymous_cannot_create_a_duel(self):
        r = self.client.get(reverse('game:duel_new'), {'mode': 'blitz'})
        self.assertIn(r.status_code, (302, 403), r.status_code)
        self.assertEqual(GameSet.objects.filter(kind='duel').count(), 1)

    def test_anonymous_cannot_accept_a_duel(self):
        r = self.client.get(reverse('game:session_start_set',
                                    args=[self.gset.code]))
        self.assertEqual(r.status_code, 409)
        self.assertIn('вошедшие', r.json()['error'])

    def test_anonymous_still_sees_the_invitation_page(self):
        u"""Страницу закрывать нельзя: соперник должен понять условие ДО
        того, как потратит время на вход."""
        r = self.client.get(reverse('game:duel', args=[self.gset.code]))
        self.assertEqual(r.status_code, 200)
        html = r.content.decode('utf-8')
        self.assertIn('только вошедшие', html)
        self.assertIn('Скопировать ссылку-приглашение', html)

    def test_logged_in_player_can_accept(self):
        from problems.models import User
        rival = User.objects.create_user(username='sopernik', password='p12345')
        self.client.force_login(rival)
        d = self.client.get(reverse('game:session_start_set',
                                    args=[self.gset.code])).json()
        self.assertTrue(d.get('ok'), d)

    def test_duel_run_is_unranked_but_lands_in_personal_stats(self):
        u"""У дуэли своя доска; в общую таблицу её забег не идёт, но в
        личной статистике игрока он есть — это его забег."""
        from problems.models import User
        from game.models import GameResult
        rival = User.objects.create_user(username='sopernik2', password='p12345')
        self.client.force_login(rival)
        d = self.client.get(reverse('game:session_start_set',
                                    args=[self.gset.code])).json()
        qid = d['question']['id']
        gq = GameQuestion.objects.get(id=qid)
        self.client.post(reverse('game:answer'),
                         json.dumps({'question_id': qid,
                                     'choice': gq.correct_index}),
                         content_type='application/json')
        self.client.post(reverse('game:session_finish'),
                         json.dumps({'reason': 'done'}),
                         content_type='application/json')
        r = GameResult.objects.filter(user=rival).first()
        self.assertIsNotNone(r)
        self.assertFalse(r.ranked)
        self.assertEqual(r.unranked_reason, 'set_run')
        self.assertEqual(r.user, rival)
