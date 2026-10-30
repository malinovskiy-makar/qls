"""Ночь 30.10, Э3: главная раздела по макетам Home и HomePhone."""
import re

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from olympiads import navigator as nav
from olympiads.models import Olympiad, OlympiadFollow, TrainingAttempt

from . import night_fixtures as fx

User = get_user_model()


def desk_slugs(response):
    """Слаги олимпиад в таблицах компьютера, по порядку."""
    html = response.content.decode()
    return re.findall(r'class="hl-name" href="/olympiads/([\w-]+)/"', html)


@override_settings(OLYMPIADS_PUBLIC=True)
class HomeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.vs, cls.final, cls.kits = fx.mini_vsosh()
        fx.olympiad('young', kind=Olympiad.Kind.OTHER, grade_min=7, grade_max=8,
                    manual_rank=50)
        fx.olympiad('senior', kind=Olympiad.Kind.PERECHEN, grade_min=10,
                    grade_max=11, manual_rank=60)
        fx.olympiad('nogr', kind=Olympiad.Kind.OTHER, grade_min=None,
                    grade_max=None, manual_rank=40)
        fx.olympiad('vp-fingram', kind=Olympiad.Kind.PERECHEN, manual_rank=70)
        fx.olympiad('hid', is_published=False)
        fx.olympiad('stub', is_placeholder=True)
        cls.user = User.objects.create_user('pupil', password='x')

    def get(self, **params):
        return self.client.get(reverse('olympiads:list'), params)

    def test_list_is_published_non_placeholders_in_rank_order(self):
        self.assertEqual(desk_slugs(self.get()),
                         ['vs', 'senior', 'young', 'nogr', 'vp-fingram'])

    def test_fin_section_is_separate(self):
        html = self.get().content.decode()
        fin = html.split('Финансовая грамотность и Основы бизнеса', 1)[1]
        self.assertIn('/olympiads/vp-fingram/', fin)
        self.assertNotIn('/olympiads/vs/', fin)

    def test_grade_11_excludes_7_8_and_unknown(self):
        self.assertEqual(desk_slugs(self.get(grade='11')),
                         ['vs', 'senior', 'vp-fingram'])

    def test_le7_is_grade_min_at_most_7(self):
        self.assertEqual(desk_slugs(self.get(grade='le7')), ['young'])

    def test_kind_and_tasks_filters_combine(self):
        self.assertEqual(desk_slugs(self.get(kind='vsosh')), ['vs'])
        self.assertEqual(desk_slugs(self.get(tasks='1')), ['vs'])
        self.assertEqual(desk_slugs(self.get(kind='perechen', grade='11')),
                         ['senior', 'vp-fingram'])

    def test_nothing_found_offers_reset(self):
        response = self.get(kind='international')
        self.assertContains(response, 'Под эти фильтры олимпиад нет')

    def test_numbers_come_from_navigator(self):
        facts = nav.olympiad_page(self.vs)['facts']
        self.assertContains(self.get(), '{} сезонов'.format(facts['seasons']))

    def test_guest_star_is_a_login_link_and_writes_nothing(self):
        html = self.get().content.decode()
        self.assertNotIn(reverse('olympiads:follow', args=['vs']), html)
        self.assertIn('/login/?next=', html)
        self.assertEqual(OlympiadFollow.objects.count(), 0)

    def test_my_olympiads_and_mine_filter(self):
        self.client.force_login(self.user)
        OlympiadFollow.objects.create(user=self.user, olympiad=self.vs)
        response = self.get()
        self.assertContains(response, 'Мои олимпиады')
        self.assertEqual(desk_slugs(self.get(mine='1')), ['vs'])

    def test_guest_mine_filter_is_ignored(self):
        self.assertEqual(len(desk_slugs(self.get(mine='1'))), 5)

    def test_continue_block_only_with_open_attempt(self):
        self.client.force_login(self.user)
        self.assertNotContains(self.get(), 'Продолжить</h2>')
        tour1 = self.kits['2025/26'][4]
        TrainingAttempt.objects.create(variant=tour1, user=self.user,
                                       submitted_at=timezone.now(), score=30,
                                       max_score=48)
        TrainingAttempt.objects.create(variant=self.kits['2025/26'][5],
                                       user=self.user, with_timer=False)
        response = self.get()
        self.assertContains(response, 'Продолжить</h2>')
        self.assertContains(response, '1 тур — 30 из 48')
        self.assertContains(response, 'Решать 2 тур')
