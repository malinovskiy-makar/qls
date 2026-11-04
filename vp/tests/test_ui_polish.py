"""Согласованный экран ВП: личный класс, порядок и сохранность чужого формата попытки."""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from problems.models_platform import UserProfile
from vp.models import VPAttempt, VPVariant, VPWall
from vp.tests.helpers import load_demo


class UIPolishTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.demos = {band: load_demo(band) for band in ('9', '10', '11')}

    def setUp(self):
        self.user = get_user_model().objects.create_user('ui_student')
        self.profile, _ = UserProfile.objects.get_or_create(user=self.user)
        self.client.force_login(self.user)

    def band(self, client=None, query=''):
        response = (client or self.client).get(reverse('vp:index') + query)
        self.assertEqual(response.status_code, 200)
        return next(b['band'] for b in response.context['boards'] if b['active'])

    def test_profile_class_maps_to_format_without_changing_profile(self):
        for grade, band in [('5', '9'), ('le7', '9'), ('8', '9'), ('9', '9'), ('10', '10'), ('11', '11')]:
            with self.subTest(grade=grade):
                self.profile.grade = grade
                self.profile.save()
                self.assertEqual(self.band(), band)
                self.profile.refresh_from_db()
                self.assertEqual(self.profile.grade, grade)

    def test_manual_session_profile_survey_attempt_priority(self):
        VPAttempt.objects.create(user=self.user, variant=self.demos['11'], public_code='ui-priority')
        VPWall.objects.create(user=self.user, grade='9')
        self.assertEqual(self.band(), '9')
        self.profile.grade = '10'
        self.profile.save()
        self.assertEqual(self.band(), '10')
        self.assertEqual(self.band(query='?band=11'), '11')
        self.assertEqual(self.band(query='?band=bad'), '11')
        self.assertEqual(self.band(query='?board=9'), '9')
        self.assertEqual(self.client.get(reverse('vp:variants')).context['current']['code'], '9')

    def test_unknown_guest_teacher_and_invalid_class_default_to_eleven(self):
        self.assertEqual(self.band(Client(), '?band=bad'), '11')
        for grade in ('', 'none', 'garbage'):
            self.profile.grade = grade
            self.profile.save()
            self.assertEqual(self.band(), '11')
        self.profile.role, self.profile.grade = 'tutor', '9'
        self.profile.save()
        self.assertEqual(self.band(), '11')
        self.profile.role = 'student'
        self.profile.save()
        self.user.role = 'teacher'
        self.user.save()
        self.assertEqual(self.band(), '11')
        self.profile.delete()
        self.assertEqual(self.band(), '11')

    def test_demo_precedes_numeric_author_order_on_cards_and_next(self):
        self.demos['11'].order = 999
        self.demos['11'].save()
        authors = []
        for n, order in [(10, -20), (2, -10), (1, 100)]:
            authors.append(VPVariant.objects.create(
                title=f'Вариант от Weconomics – {n}', slug=f'ui-author-{n}',
                tour=2, grade_band='11', year=2026, source_kind='author',
                is_published=True, order=order))
        response = self.client.get(reverse('vp:variants') + '?band=11')
        self.assertEqual([c['variant'].pk for c in response.context['cards']],
                         [self.demos['11'].pk, authors[2].pk, authors[1].pk, authors[0].pk])
        self.assertContains(response, 'Вариант Weconomics № 2')
        self.assertContains(response, 'Официальная демоверсия')
        response = self.client.get(reverse('vp:index'))
        self.assertEqual(response.context['mine']['next_variant'], self.demos['11'])

    def test_other_class_resume_keeps_its_variant_and_url(self):
        attempt = VPAttempt.objects.create(user=self.user, variant=self.demos['10'],
                                           public_code='ui-resume', with_timer=False)
        response = self.client.get(reverse('vp:index') + '?band=9')
        self.assertEqual(response.context['mine']['current'], attempt)
        self.assertContains(response, reverse('vp:take', args=[attempt.public_code]))
        self.assertContains(response, '10 класс')
        self.assertNotContains(response, 'Продолжить:')
        self.assertContains(response, reverse('vp:my'))

    def test_selected_format_and_real_data_follow_class(self):
        for band, count in [('9', 17), ('10', 18), ('11', 18)]:
            response = self.client.get(reverse('vp:index') + f'?band={band}')
            comp = response.context['composition']
            self.assertEqual((comp['count'], comp['label'], comp['others']),
                             (count, f'{band} класс', []))
        item = self.demos['9'].items.last()
        item.points += 1
        item.save()
        response = self.client.get(reverse('vp:index') + '?band=9')
        self.assertEqual(response.context['composition']['total'], 101)
        self.assertContains(response, '73 балла')
        item.delete()
        response = self.client.get(reverse('vp:index') + '?band=9')
        self.assertEqual(response.context['composition']['count'], 16)
