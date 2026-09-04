"""Фаза 5.3: эндпоинт проверки попытки и экран результата."""
import json

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from catalog.tests.test_attempts import _reply
from problems.models import CatalogAttempt
from problems.tests.factories import make_problem, make_topic, make_user


class AttemptApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.topic = make_topic('Монополия и ценовая дискриминация')
        self.problem = make_problem('Спрос $Q_d = 120 - P$, найдите сборы.',
                                    title='Вмешательство — 5', topic=self.topic,
                                    solution='Полное эталонное решение задачи о налогах.',
                                    answer='1800')
        self.user = make_user('ученик', first_name='Пётр', email='petr@example.org')
        self.url = reverse('catalog:api_attempt')
        self.page = reverse('catalog:problem_detail', args=[self.problem.pk])

    def _post(self, **payload):
        body = {'problem_id': self.problem.pk, 'text': 'Моё решение: t1 = t2 = 40'}
        body.update(payload)
        return self.client.post(self.url, json.dumps(body), content_type='application/json')

    @override_settings(AI_PROVIDER='fake')
    def test_anonymous_sees_login_link_and_gets_403(self):
        html = self.client.get(self.page).content.decode()
        self.assertNotIn('id="sv-submit"', html)
        self.assertIn('href="/login/?next=', html)
        self.assertIn('Войти, чтобы отправить на проверку', html)
        self.assertNotIn('id="sv-remaining"', html)
        resp = self._post()
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(json.loads(resp.content)['error'], 'login')
        self.assertEqual(CatalogAttempt.objects.count(), 0)

    @override_settings(AI_PROVIDER='fake')
    def test_checked_attempt_renders_partial_with_first_error(self):
        self.client.force_login(self.user)
        html = self.client.get(self.page).content.decode()
        self.assertIn('id="sv-submit"', html)
        self.assertIn('осталось сегодня <b id="sv-remaining">30</b>', html)
        self.assertIn('id="chk-busy"', html)
        self.assertIn('"attemptUrl": "/catalog/api/attempt/"', html)
        with override_settings(AI_FAKE_REPLY=_reply()):
            resp = self._post(solution_viewed_before=True)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(data['status'], 'checked')
        self.assertEqual(data['remaining'], 29)
        self.assertIn('Частично верно', data['html'])
        self.assertIn('<div class="chk-score">5<small> / 10</small></div>', data['html'])
        self.assertIn('Выбор Арслана<span class="chk-flag">ПЕРВАЯ ОШИБКА</span>', data['html'])
        self.assertIn('class="chk-step is-first"', data['html'])
        self.assertIn('Предварительная оценка ИИ: может ошибаться.', data['html'])
        self.assertIn('data-retry', data['html'])
        self.assertNotIn('преподавател', data['html'])
        attempt = CatalogAttempt.objects.get(pk=data['attempt_id'])
        self.assertTrue(attempt.solution_viewed_before)
        self.assertEqual(attempt.user, self.user)
        # Последняя попытка показана при загрузке страницы тем же партиалом.
        html = self.client.get(self.page).content.decode()
        self.assertIn('id="chk" data-attempt="%d"' % attempt.pk, html)
        self.assertIn('Частично верно', html)

    @override_settings(AI_PROVIDER='fake')
    def test_needs_human_has_no_score_and_no_teacher_button(self):
        self.client.force_login(self.user)
        with override_settings(AI_FAKE_REPLY=_reply(needs_human=True)):
            data = json.loads(self._post().content)
        self.assertEqual(data['status'], 'needs_human')
        self.assertIn('<div class="chk-score">–</div>', data['html'])
        self.assertIn('Модель не ставит балл: ход решения нестандартный', data['html'])
        self.assertNotIn('Отправить преподавателю', data['html'])

    @override_settings(AI_PROVIDER='fake', AI_GENERATOR_DAILY_LIMIT=1)
    def test_limit_gives_a_human_message_not_500(self):
        self.client.force_login(self.user)
        with override_settings(AI_FAKE_REPLY=_reply()):
            first = json.loads(self._post().content)
            self.assertEqual(first['remaining'], 0)
            second = self._post(text='Совсем другое решение')
        self.assertEqual(second.status_code, 200)
        data = json.loads(second.content)
        self.assertEqual(data['error'], 'limit')
        self.assertEqual(data['message'], 'Лимит проверок на сегодня исчерпан: завтра снова 1')
        self.assertEqual(CatalogAttempt.objects.filter(status='checked').count(), 1)
        html = self.client.get(self.page).content.decode()
        self.assertIn('осталось сегодня <b id="sv-remaining">0</b>', html)

    @override_settings(AI_PROVIDER='fake')
    def test_off_schema_reply_is_an_error_attempt_with_a_message(self):
        self.client.force_login(self.user)
        with override_settings(AI_FAKE_REPLY=json.dumps({'foo': 1})):
            data = json.loads(self._post().content)
        self.assertEqual(data['status'], 'error')
        self.assertIn('Проверка не удалась', data['html'])
        self.assertIn('не по схеме', data['html'])
        # Неудачная попытка при загрузке страницы не показывается.
        html = self.client.get(self.page).content.decode()
        self.assertNotIn('id="chk" data-attempt=', html)

    @override_settings(AI_PROVIDER='fake')
    def test_empty_text_is_400(self):
        self.client.force_login(self.user)
        resp = self._post(text='   ')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(CatalogAttempt.objects.count(), 0)

    @override_settings(AI_PROVIDER='anthropic')
    def test_without_key_there_is_no_button_no_limit_line_no_config(self):
        self.client.force_login(self.user)
        html = self.client.get(self.page).content.decode()
        self.assertEqual(self.client.get(self.page).status_code, 200)
        self.assertNotIn('id="sv-submit"', html)
        self.assertNotIn('id="sv-remaining"', html)
        self.assertNotIn('id="chk-busy"', html)
        self.assertNotIn('attemptUrl', html)
        resp = self._post()
        self.assertEqual(json.loads(resp.content)['error'], 'no_key')
