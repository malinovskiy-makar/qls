# -*- coding: utf-8 -*-
"""Смок-тест беты (ночь 18.09.2026): главные экраны отвечают и новые пути живы.

Быстрый, без браузера. Не заменяет модульные тесты разделов — только
сторожит, что утром сайт открывается у гостя, ученика и учителя.
"""
from django.core.cache import cache
from django.test import TestCase, override_settings

from problems.models_platform import Feedback, SearchLog, UserProfile
from problems.tests.factories import make_problem, make_topic, make_user


@override_settings(AI_PROVIDER='fake', CATALOG_CHAT_PROVIDER='fake')
class BetaSmokeTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        topic = make_topic('Монополия и ценовая дискриминация', is_canonical=True)
        cls.problem = make_problem('Монополист с двумя заводами выбирает выпуск.', topic=topic)
        cls.student = make_user('smoke_student')
        cls.teacher = make_user('smoke_teacher', role='teacher')

    def setUp(self):
        cache.clear()

    def test_guest_screens_answer_200(self):
        for url in ('/', '/catalog/', '/catalog/?q=монополия',
                    '/catalog/problem/%d/' % self.problem.pk, '/game/',
                    '/login/', '/register/', '/healthz/'):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_student_profile_saves_every_new_field(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get('/profile/').status_code, 200)
        response = self.client.post('/profile/', {
            'action': 'data', 'username': 'smoke_student', 'first_name': '', 'last_name': '',
            'email': '', 'grade': 'le7', 'school': 'Школа', 'city': 'Пермь', 'level': 'novice',
            'goal': 'Регион', 'prep_mode': ['self'], 'hours_week': 'lt1',
            'source_channel': 'friend', 'olympiad_history': ['none'], 'phone': ''})
        self.assertEqual(response.status_code, 302)
        profile = UserProfile.objects.get(user=self.student)
        self.assertEqual((profile.grade, profile.hours_week, profile.olympiad_history),
                         ('le7', 'lt1', ['none']))

    def test_student_problem_page_offers_several_files(self):
        self.client.force_login(self.student)
        with override_settings(CATALOG_CHAT_PROVIDER='fake'):
            html = self.client.get('/catalog/problem/%d/' % self.problem.pk).content.decode()
        self.assertRegex(html, r'id="ai-file" multiple')

    def test_pulse_is_accepted(self):
        self.client.force_login(self.student)
        response = self.client.post('/api/feedback/', {'kind': 'pulse', 'url': '/catalog/',
                                                       'choices': ['like']})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Feedback.objects.get().kind, 'pulse')

    def test_teacher_cabinet_answers_200(self):
        self.client.force_login(self.teacher)
        # `/teacher/` ведёт редиректом на рабочий экран кабинета.
        response = self.client.get('/teacher/', follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.request['PATH_INFO'].startswith('/teacher/'))

    def test_rating_someone_elses_search_is_404(self):
        row = SearchLog.objects.create(query='чужой запрос', visitor='visitor-zzzz-9999')
        self.client.cookies['weco_vid'] = 'visitor-aaaa-1111'
        response = self.client.post('/api/search-rating/', {'log': row.pk, 'rating': 'yes'})
        self.assertEqual(response.status_code, 404)
