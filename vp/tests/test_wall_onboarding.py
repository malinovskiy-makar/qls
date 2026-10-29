"""Стена ВП и онбординг: человек отвечает о себе один раз (раунд 2 входа, 30.10.2026).

* Профиль знает класс 9–11 и «откуда узнали» → анкета стены спрашивает только «Вы
  прошли во 2 тур?»; значения сервер берёт из профиля, а не из формы.
* Класс не 9–11 → вопрос о классе показан.
* Анкета стены раньше онбординга → онбординг показывает класс и источник выбранными.
* Путь «гость → регистрация со стены → онбординг → назад в вариант».
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from problems.models_platform import UserProfile
from vp import wall
from vp.models import VPAttempt, VPWall
from vp.tests.helpers import load_demo

User = get_user_model()
WALL = override_settings(VP_WALL_ENABLED=True, MAIL_ENABLED=False, TELEGRAM_BOT_TOKEN='',
                         TELEGRAM_BOT_USERNAME='', TELEGRAM_WEBHOOK_SECRET='')


@WALL
class WallAsksOnlyTheUnknownTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.variant = load_demo('10')

    def setUp(self):
        self.user = User.objects.create_user('ivan_site', password='p12345')
        self.client = Client()
        self.client.force_login(self.user)
        wall.pass_contact(self.user, 'email')
        self.intro = reverse('vp:intro', args=[self.variant.slug])
        self.survey = reverse('vp:wall_survey', args=[self.variant.slug])

    def page(self):
        return self.client.get(self.intro, {'wall': '1'}).content.decode()

    def test_known_grade_and_source_leave_one_question(self):
        UserProfile.objects.filter(user=self.user).update(grade='10', source_channel='vk')
        html = self.page()
        self.assertIn('Последний вопрос – и начинаем', html)
        self.assertIn('Вы прошли во 2 тур?', html)
        self.assertNotIn('name="grade"', html)
        self.assertNotIn('name="source"', html)
        response = self.client.post(self.survey, {'tour2_status': 'waiting',
                                                  'grade': '11', 'source': 'tiktok'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(VPAttempt.objects.filter(user=self.user).exists())
        saved = VPWall.objects.get(user=self.user)
        self.assertEqual((saved.grade, saved.source, saved.tour2_status), ('10', 'vk', 'waiting'))

    def test_eighth_grade_is_asked_the_grade(self):
        UserProfile.objects.filter(user=self.user).update(grade='8', source_channel='vk')
        html = self.page()
        self.assertIn('Два вопроса – и начинаем', html)
        self.assertIn('name="grade"', html)
        self.assertNotIn('name="source"', html)

    def test_empty_profile_gets_all_three(self):
        html = self.page()
        self.assertIn('Три вопроса – и начинаем', html)
        for name in ('grade', 'tour2_status', 'source'):
            self.assertIn('name="%s"' % name, html)

    def test_wall_first_then_onboarding_shows_the_answers(self):
        self.client.post(self.survey, {'grade': '10', 'tour2_status': 'passed', 'source': 'vk'})
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual((profile.grade, profile.source_channel), ('10', 'vk'))
        with override_settings(ONBOARDING_ENABLED=True):
            self.client.post('/welcome/role/', {'role': 'student'})
            grade_page = self.client.get('/welcome/grade/').content.decode()
            self.assertIn('10 класс<span>Изменить</span>', grade_page)   # класс уже выбран
            source_page = self.client.get('/welcome/source/')
        if source_page.status_code == 302:                               # шаги до него пусты
            UserProfile.objects.filter(user=self.user).update(level='basic', goals=['listed'],
                                                              city='Казань', school='1')
            source_page = self.client.get('/welcome/source/')
        html = source_page.content.decode()
        self.assertRegex(html, r'name="source_channel" value="vk"[^>]*aria-pressed="true"')

    def test_sources_are_one_list_on_the_site(self):
        self.assertEqual(list(VPWall.SOURCE_CHOICES), list(UserProfile.SourceChannel.choices))


@WALL
@override_settings(ONBOARDING_ENABLED=True)
class GuestPathTests(TestCase):
    """Гость → регистрация со стены (`next` на вариант) → онбординг → вариант; дальше
    стена не спрашивает ни класс, ни источник."""

    @classmethod
    def setUpTestData(cls):
        cls.variant = load_demo('10')

    def test_whole_path(self):
        cache.clear()
        intro = reverse('vp:intro', args=[self.variant.slug])
        response = self.client.post('/register/?next=' + intro, {
            'username': 'gost_vp', 'password1': 'Ochen-Dlinnyi-Parol-77', 'consent': 'on',
            'next': intro})
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username='gost_vp')
        # Шлюз ведёт на онбординг с `next` на вариант.
        gate = self.client.get(intro)
        self.assertEqual(gate.status_code, 302)
        self.assertIn('/welcome/', gate['Location'])
        self.client.get(gate['Location'])
        for step, data in (('role', {'role': 'student'}), ('grade', {'grade': '10'}),
                           ('grade', {'level': 'basic'}), ('goals', {'goals': ['listed']}),
                           ('school', {'city': 'Москва', 'school': 'Школа № 57'})):
            self.client.post('/welcome/%s/' % step, data)
        done = self.client.post('/welcome/source/', {'source_channel': 'friend'})
        self.assertEqual(done['Location'], '/welcome/build/?to=' + intro.replace('/', '%2F'))
        build = self.client.get(done['Location']).content.decode()
        self.assertIn('data-ob-target="%s"' % intro, build)
        # Назад в вариант: стена после контакта спрашивает только про 2 тур.
        wall.pass_contact(user, 'email')
        html = self.client.get(intro, {'wall': '1'}).content.decode()
        self.assertIn('Вы прошли во 2 тур?', html)
        self.assertNotIn('name="grade"', html)
        self.assertNotIn('name="source"', html)
