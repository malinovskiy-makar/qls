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

    def test_new_duel_answers_json_and_does_not_redirect(self):
        u"""⚠️ ВЬЮХА БОЛЬШЕ НЕ УВОДИТ АВТОРА В ИГРУ (08.09.2026).

        Раньше она возвращала редирект на `/game/s/<код>/?auto=1`, и забег
        начинался немедленно: автор не видел ни лобби, ни ссылки, соперник
        приходил позже, и в одном забеге они практически никогда не
        пересекались. Живого табло из-за этого не видел никто.
        """
        r = self.client.get(reverse('game:duel_new'), {'mode': 'blitz'})
        self.assertEqual(r.status_code, 200)
        d = json.loads(r.content.decode('utf-8'))
        gset = GameSet.objects.get(kind='duel')
        self.assertTrue(d['ok'])
        self.assertEqual(d['code'], gset.code)
        self.assertIn('/game/d/', d['duel_url'])
        self.assertEqual(d['play_url'],
                         reverse('game:set_page', args=[gset.code]))
        # ⚠️ Ни следа автостарта в адресе, куда уходит автор.
        self.assertNotIn('auto=1', d['play_url'])

    def test_the_queue_is_a_reserve_not_a_round_length(self):
        u"""Числовой инвариант фазы: min(сколько есть, DUEL_QUEUE_LIMIT).

        Проверяется на двух пулах — заведомо меньше запаса и заведомо
        больше. Один случай доказывал бы только половину правила.
        """
        # 30 вопросов из setUp — меньше запаса: берём все.
        self.client.get(reverse('game:duel_new'), {'mode': 'blitz'})
        small = GameSet.objects.get(kind='duel')
        self.assertEqual(small.size, 30)
        self.assertLess(small.size, config.DUEL_QUEUE_LIMIT)

        # Добираем пул выше запаса: обрезаем ровно по нему.
        make_q(config.DUEL_QUEUE_LIMIT + 20 - 30)
        small.delete()
        self.client.get(reverse('game:duel_new'), {'mode': 'blitz'})
        big = GameSet.objects.get(kind='duel')
        self.assertEqual(big.size, config.DUEL_QUEUE_LIMIT)

    def test_both_players_walk_the_same_queue(self):
        u"""Суть дуэли: очередь перемешивается ОДИН раз при создании набора.

        Оба игрока идут по `GameSet.question_ids`; добор из общего пула в
        наборе запрещён. Разные очереди означали бы разные игры.
        """
        self.client.get(reverse('game:duel_new'), {'mode': 'blitz'})
        gset = GameSet.objects.get(kind='duel')

        rival = User.objects.create_user(username='rival', password='p12345')
        order = list(gset.question_ids)
        seen = []
        for user in (self.me, rival):
            client = self.client_class()
            client.force_login(user)
            r = client.get(reverse('game:session_start_set', args=[gset.code]))
            self.assertEqual(r.status_code, 200)
            from django.core.cache import cache
            from game import state as run_state
            run_id = client.session.get(run_state.RUN_ID_KEY)
            self.assertIsNotNone(run_id)
            run = cache.get(run_state.cache_key(run_id))
            self.assertIsNotNone(run, 'состояние забега не найдено')
            # ⚠️ Сравниваем ОЧЕРЕДЬ ПЛЮС ВЫДАННЫЙ ВОПРОС: старт сразу
            # снимает с очереди первый, и голая очередь у двоих отличалась
            # бы на один элемент, хотя порядок один и тот же.
            queue = list(run['queue'])
            self.assertEqual(queue, order[len(order) - len(queue):],
                             'очередь — не хвост общего списка')
            seen.append(queue)
        self.assertEqual(seen[0], seen[1])
        self.assertEqual(len(seen[0]), len(order) - 1)

    def test_duel_respects_the_filter(self):
        make_q(5, topic='Рынок труда')
        self.client.get(reverse('game:duel_new'),
                        {'mode': 'blitz', 'topics': 'Рынок труда'})
        gset = GameSet.objects.get(kind='duel')
        chosen = GameQuestion.objects.filter(id__in=gset.question_ids)
        self.assertTrue(all('Рынок труда' in q.topics for q in chosen))
        self.assertEqual(gset.filter_snapshot['topics'], ['Рынок труда'])

    def test_empty_filter_does_not_create_an_empty_duel(self):
        """Пустая дуэль = ссылка в никуда. Лучше честно сказать.

        ⚠️ Ответ разный, и это не дубль: окну вызова (fetch) нужна строка
        ошибки, а человеку, набравшему адрес руками, — страница. Получатели
        разные. Набор не создаётся ни в том, ни в другом случае.
        """
        args = {'mode': 'blitz', 'topics': 'Эконометрика и анализ данных'}

        r = self.client.get(reverse('game:duel_new'), args)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Дуэль не собралась')

        r = self.client.get(reverse('game:duel_new'), args,
                            HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r.status_code, 200)
        d = json.loads(r.content.decode('utf-8'))
        self.assertFalse(d['ok'])
        self.assertTrue(d['error'])

        self.assertFalse(GameSet.objects.filter(kind='duel').exists())

    def test_the_duel_set_page_does_not_start_the_run_by_itself(self):
        u"""⚠️ ЗАПРЕТ, А НЕ УМОЛЧАНИЕ.

        Условие стоит в `set_page`, а не только в `duel_new`: иначе адрес с
        `?auto=1`, набранный руками или оставшийся в чьей-то закладке,
        вернул бы прежнее поведение — забег автора начинался бы сразу, и
        лобби со ссылкой он снова не увидел бы.
        """
        self.client.get(reverse('game:duel_new'), {'mode': 'blitz'})
        gset = GameSet.objects.get(kind='duel')
        url = reverse('game:set_page', args=[gset.code])
        for suffix in ('', '?auto=1'):
            r = self.client.get(url + suffix)
            self.assertEqual(r.status_code, 200, suffix)
            self.assertFalse(r.context['auto_set']['autostart'], suffix)

    def test_the_queue_reserve_never_shows_up_on_screen(self):
        u"""Число 150 — внутренний запас. Игрок его не видит и не должен."""
        self.client.get(reverse('game:duel_new'), {'mode': 'blitz'})
        gset = GameSet.objects.get(kind='duel')
        html = self.client.get(
            reverse('game:set_page', args=[gset.code])).content.decode('utf-8')

        # ⚠️ Смотрим на ВИДИМУЮ разметку, без стилей и скриптов: в CSS
        # страницы «150» встречается размером колонки, и проверка по всему
        # файлу краснела бы на ровном месте, ничего не доказывая.
        import re as _re
        visible = _re.sub(r'<style.*?</style>', ' ', html, flags=_re.S)
        visible = _re.sub(r'<script.*?</script>', ' ', visible, flags=_re.S)
        self.assertNotIn(str(config.DUEL_QUEUE_LIMIT), visible)

        # Вместо числа — слова. Подпись собирает клиент, в шаблоне лежит
        # ветка «дуэль → без лимита».
        self.assertIn('без лимита вопросов', html)
        self.assertIn("AUTO_SET.kind === 'duel'", html)

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


class ScoreboardIsOneMarkupTests(TestCase):
    u"""Табло `.vs` — одно и то же на дуэли и на обычном забеге.

    Решение владельца 08.09.2026: второго вида табло не заводим. Проверяется
    по РАЗМЕТКЕ обеих страниц: если когда-нибудь заведут вторую, страницы
    разойдутся, и этот тест это увидит.
    """

    def setUp(self):
        make_q(20)
        self.me = User.objects.create_user(username='vs_user', password='p12345')
        self.client.force_login(self.me)

    def _vs_block(self, html):
        self.assertIn('<div class="vs" id="vs"', html)
        return html.split('<div class="vs" id="vs"', 1)[1].split(
            '<div class="duel-emoji"', 1)[0]

    def test_the_same_block_serves_both_run_kinds(self):
        plain = self.client.get(reverse('game:page')).content.decode('utf-8')

        self.client.get(reverse('game:duel_new'), {'mode': 'blitz'})
        gset = GameSet.objects.get(kind='duel')
        duel = self.client.get(
            reverse('game:set_page', args=[gset.code])).content.decode('utf-8')

        self.assertEqual(self._vs_block(plain), self._vs_block(duel))

    def test_the_left_side_is_always_you(self):
        html = self.client.get(reverse('game:page')).content.decode('utf-8')
        block = self._vs_block(html)
        self.assertIn('id="vs-my-score"', block)
        self.assertIn('id="vs-my-correct"', block)
        self.assertIn('id="vs-my-acc"', block)
        self.assertIn('id="vs-my-combo"', block)
        self.assertIn('id="vs-my-time"', block)
        self.assertIn('id="vs-my-tape"', block)

    def test_the_gap_column_stands_between_the_two_cards(self):
        block = self._vs_block(
            self.client.get(reverse('game:page')).content.decode('utf-8'))
        self.assertLess(block.index('id="vs-me"'), block.index('id="vs-gap"'))
        self.assertLess(block.index('id="vs-gap"'), block.index('id="vs-them"'))


class PersonalBestComesWithTheStartTests(TestCase):
    u"""Правая карточка обычного забега — личный рекорд, и он с СЕРВЕРА.

    ⚠️ ВЫБОР ИСТОЧНИКА. Рекорд отдаёт `api_session_start` полем `best`, а не
    отдельный запрос к `api_my_stats`: правая карточка нужна ровно в момент
    старта забега, и вторым запросом она подъезжала бы после первого
    вопроса. Плюс `api_my_stats` — про всю панель рекордов, и вешать на неё
    открытие раунда значит связать раунд с запросом, который не про раунд.
    """

    def setUp(self):
        make_q(20)
        self.me = User.objects.create_user(username='best_user',
                                           password='p12345')

    def test_no_runs_means_no_record_and_no_invented_number(self):
        self.client.force_login(self.me)
        r = self.client.get(reverse('game:session_start'), {'mode': 'blitz'})
        self.assertIsNone(json.loads(r.content.decode('utf-8'))['best'])

    def test_an_anonymous_player_gets_no_record_either(self):
        r = self.client.get(reverse('game:session_start'), {'mode': 'blitz'})
        self.assertIsNone(json.loads(r.content.decode('utf-8'))['best'])

    def test_the_record_run_reports_its_own_accuracy(self):
        u"""Точность — у самого рекордного забега, не средняя за всё время."""
        from game import config as game_config
        GameResult.objects.create(
            user=self.me, mode='blitz', score=900, correct_count=9,
            wrong_count=1, total_count=10,
            economy_version=game_config.ECONOMY_VERSION)
        GameResult.objects.create(
            user=self.me, mode='blitz', score=100, correct_count=1,
            wrong_count=9, total_count=10,
            economy_version=game_config.ECONOMY_VERSION)

        self.client.force_login(self.me)
        r = self.client.get(reverse('game:session_start'), {'mode': 'blitz'})
        best = json.loads(r.content.decode('utf-8'))['best']
        self.assertEqual(best['score'], 900)
        self.assertEqual(best['correct'], 9)
        # 9 из 10 попыток рекордного забега, а не (9+1)/20 по обоим.
        self.assertEqual(best['accuracy'], 90)
        self.assertTrue(best['created_at'])
