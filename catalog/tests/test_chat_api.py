"""Фаза 5.4: чат по задаче — одна реплика, история на клиенте, режим домашки."""
import json
from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from catalog import chat
from problems.models import CatalogAttempt, StudentGroup
from problems.tests.factories import (
    make_assignment, make_problem, make_topic, make_user,
)


def _capture(store, reply='Начните с функции реакции второго игрока. Что он видит?'):
    def fake(system_blocks, user_text):
        store['text'] = user_text
        store['system'] = ' '.join(system_blocks)
        return json.dumps({'reply': reply}, ensure_ascii=False)
    return fake


@override_settings(AI_PROVIDER='fake')
class ChatApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.topic = make_topic('Олигополия и теория игр')
        self.problem = make_problem('Две фирмы выбирают выпуск последовательно.',
                                    title='Штакельберг', topic=self.topic, answer='q1 = 30')
        self.user = make_user('маша', first_name='Мария', email='masha@example.org')
        self.teacher = make_user('репетитор', role='teacher')
        self.url = reverse('catalog:api_chat')
        self.page = reverse('catalog:problem_detail', args=[self.problem.pk])

    def _post(self, message='С чего начать?', history=None, **extra):
        body = {'problem_id': self.problem.pk, 'message': message, 'history': history or []}
        body.update(extra)
        return self.client.post(self.url, json.dumps(body), content_type='application/json')

    def test_reply_comes_back_and_prompt_has_no_profile_fields(self):
        self.client.force_login(self.user)
        seen = {}
        with override_settings(AI_FAKE_REPLY=_capture(seen)):
            data = json.loads(self._post(history=[{'role': 'me', 'text': 'Привет'},
                                                  {'role': 'ai', 'text': 'Здравствуйте'}]).content)
        self.assertEqual(data['reply'], 'Начните с функции реакции второго игрока. Что он видит?')
        self.assertEqual(data['remaining'], 29)
        text = seen['text']
        for present in ('Две фирмы выбирают выпуск последовательно.', 'Ученик: Привет',
                        'Помощник: Здравствуйте', 'ВОПРОС УЧЕНИКА:', 'С чего начать?'):
            self.assertIn(present, text)
        for absent in ('Мария', 'masha@example.org', 'маша'):
            self.assertNotIn(absent, text)
            self.assertNotIn(absent, seen['system'])
        self.assertNotIn(chat.HOMEWORK_MODE, text)
        self.assertNotIn('q1 = 30', text)   # ответ задачи помощнику не даётся

    def test_last_attempt_and_its_result_reach_the_helper(self):
        self.client.force_login(self.user)
        CatalogAttempt.objects.create(user=self.user, problem=self.problem, text='q1 = 45',
                                      status='checked', verdict='wrong', score=2,
                                      steps=[{'n': 1, 'title': 'Выбор лидера', 'verdict': 'bad',
                                              'comment': ''}], first_error_step=1)
        seen = {}
        with override_settings(AI_FAKE_REPLY=_capture(seen)):
            self._post('Почему неверно?')
        self.assertIn('ПОСЛЕДНЯЯ ПОПЫТКА УЧЕНИКА:', seen['text'])
        self.assertIn('q1 = 45', seen['text'])
        self.assertIn('РЕЗУЛЬТАТ ПРОВЕРКИ: неверно, 2 из 10; первая ошибка в шаге 1: Выбор лидера',
                      seen['text'])

    def test_homework_mode_for_open_assignment_by_list_and_by_group(self):
        self.client.force_login(self.user)
        seen = {}
        make_assignment(self.teacher, students=[self.user], problems=[self.problem],
                        deadline=timezone.now() + timedelta(days=3))
        with override_settings(AI_FAKE_REPLY=_capture(seen)):
            self._post()
        self.assertIn(chat.HOMEWORK_MODE, seen['text'])
        self.assertIn('ТОЛЬКО НАВОДЯЩИЕ ВОПРОСЫ', seen['system'])

    def test_homework_mode_via_group_and_not_after_deadline(self):
        self.client.force_login(self.user)
        group = StudentGroup.objects.create(teacher=self.teacher, name='9А')
        group.students.add(self.user)
        closed = make_assignment(self.teacher, problems=[self.problem],
                                 deadline=timezone.now() - timedelta(days=1))
        closed.group = group
        closed.save(update_fields=['group'])
        self.assertFalse(chat.in_active_homework(self.user, self.problem))
        open_work = make_assignment(self.teacher, problems=[self.problem], deadline=None)
        open_work.group = group
        open_work.save(update_fields=['group'])
        self.assertTrue(chat.in_active_homework(self.user, self.problem))

    def test_anonymous_gets_403_and_a_login_link_instead_of_the_field(self):
        html = self.client.get(self.page).content.decode()
        self.assertIn('<h2>Спросить ИИ</h2>', html)
        self.assertNotIn('id="ai-text"', html)
        self.assertIn('Войти, чтобы спросить', html)
        self.assertEqual(self._post().status_code, 403)

    def test_logged_in_page_has_field_send_button_and_three_suggestions(self):
        self.client.force_login(self.user)
        html = self.client.get(self.page).content.decode()
        for needle in ('id="ai-text"', 'id="ai-send"', 'data-q="Объясни условие проще"',
                       'data-q="С чего начать?"', 'data-q="Проверь мою идею"',
                       '"chatUrl": "/catalog/api/chat/"'):
            self.assertIn(needle, html)

    @override_settings(AI_GENERATOR_DAILY_LIMIT=1)
    def test_limit_is_shared_with_the_check_and_is_a_human_reply(self):
        self.client.force_login(self.user)
        with override_settings(AI_FAKE_REPLY=_capture({})):
            self.assertEqual(json.loads(self._post().content)['remaining'], 0)
            data = json.loads(self._post('Ещё вопрос').content)
        self.assertEqual(data['error'], 'limit')
        self.assertEqual(data['reply'], 'Лимит проверок на сегодня исчерпан: завтра снова 1')

    def test_history_is_trimmed_and_reply_is_capped(self):
        history = [{'role': 'me', 'text': 'реплика %d' % i} for i in range(10)]
        self.assertEqual([h['text'] for h in chat.clean_history(history)],
                         ['реплика %d' % i for i in range(4, 10)])
        self.client.force_login(self.user)
        with override_settings(AI_FAKE_REPLY=_capture({}, reply='x' * 2000)):
            data = json.loads(self._post().content)
        self.assertEqual(len(data['reply']), chat.REPLY_MAX)

    @override_settings(AI_PROVIDER='anthropic')
    def test_without_key_page_has_no_chat_card(self):
        self.client.force_login(self.user)
        resp = self.client.get(self.page)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertNotIn('Спросить ИИ', html)
        self.assertNotIn('id="ai-text"', html)
        self.assertNotIn('chatUrl', html)
