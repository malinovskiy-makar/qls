"""Ночь 30.10, Э1: навигатор раздела и «Мои олимпиады».

Проверки на настоящей базе ночи — `claude/night_olymp_20261030/tools/
real_db_checks.py` (тестовая база Django пустая, настоящую трогать нельзя).
"""
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from olympiads import navigator as nav
from olympiads.models import OlympiadFollow, OlympiadVariant, TrainingAttempt

from . import night_fixtures as fx

User = get_user_model()


def final_grid(page):
    return [g for g in page['grids'] if g['code'] == 'final'][0]


def row(grid, label):
    return [r for r in grid['rows'] if r['label'] == label][0]


class GridTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.olymp, cls.final, cls.kits = fx.mini_vsosh()

    def page(self, **kw):
        return nav.olympiad_page(self.olymp, **kw)

    def test_31_rows_30_seasons_from_1995(self):
        grid = final_grid(self.page())
        self.assertEqual(len(grid['rows']), 31)
        self.assertEqual(grid['seasons'], 30)
        self.assertEqual(grid['first_label'], '1995/96')
        self.assertEqual(grid['rows'][0]['label'], '2025/26')

    def test_empty_season_inside_range_is_an_empty_row(self):
        empty = row(final_grid(self.page()), '2019/20')
        self.assertTrue(empty['empty'])
        self.assertEqual(empty['cells'], [])

    def test_neighbour_grades_of_one_kit_merge_into_one_cell(self):
        cells = row(final_grid(self.page()), '2018/19')['cells']
        self.assertEqual([(c['grades'], c['colspan']) for c in cells],
                         [([9], 1), ([10, 11], 2)])
        self.assertEqual(cells[1]['grades_label'], '10–11 классы')

    def test_kit_without_grades_is_one_wide_cell_without_label(self):
        cells = row(final_grid(self.page()), '2016/17')['cells']
        self.assertEqual(len(cells), 1)
        self.assertEqual(cells[0]['colspan'], 3)
        self.assertEqual(cells[0]['grades_label'], '')
        self.assertEqual(len(cells[0]['tours']), 2)

    def test_two_tours_210_minutes_48_points(self):
        cell = row(final_grid(self.page()), '2025/26')['cells'][2]
        self.assertEqual(cell['grades'], [11])
        self.assertEqual([t['label'] for t in cell['tours']], ['1 тур', '2 тур'])
        for tour in cell['tours']:
            self.assertEqual(tour['minutes'], 210)
            self.assertEqual(tour['max_score'], 48.0)
            self.assertEqual(tour['tasks'], 4)
        self.assertEqual(cell['tasks_label'], '8 заданий')

    def test_unscored_item_falls_back_to_stage_maximum(self):
        variant = self.kits['2024/25'][0]
        variant.items.update(max_score=None)
        cell = row(final_grid(self.page()), '2024/25')['cells'][0]
        self.assertEqual(cell['tours'][0]['max_score'], 48.0)

    def test_duplicate_kit_does_not_enter_the_grid(self):
        original = self.kits['2025/26'][0]
        copy = fx.kit(self.olymp, self.final, '2025/26', tour='1', grades=(9,))
        copy.duplicate_of = original
        copy.save()
        cell = row(final_grid(self.page()), '2025/26')['cells'][0]
        self.assertEqual(len(cell['tours']), 2)
        self.assertNotIn(copy.pk, [t['pk'] for t in cell['tours']])

    def test_hidden_and_placeholder_kits_are_out(self):
        self.kits['2024/25'][0].__class__.objects.filter(
            pk=self.kits['2024/25'][0].pk).update(
            visibility=OlympiadVariant.Visibility.HIDDEN)
        cell = row(final_grid(self.page()), '2024/25')['cells'][0]
        self.assertEqual(len(cell['tours']), 1)

    def test_facts_count_distinct_problems_and_seasons(self):
        facts = self.page()['facts']
        self.assertEqual(facts['seasons'], 30)
        expected = sum(len(v.items.all()) for kits in self.kits.values()
                       for v in kits)
        self.assertEqual(facts['problems'], expected)

    def test_page_is_built_in_few_queries_without_n_plus_one(self):
        with CaptureQueriesContext(connection) as ctx:
            nav.olympiad_page(self.olymp)
        self.assertLessEqual(len(ctx), 30)
        # И число запросов не растёт с числом сезонов.
        self.assertLessEqual(len(ctx), 12)


class StateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.olymp, cls.final, cls.kits = fx.mini_vsosh()
        cls.user = User.objects.create_user('pupil', password='x')
        cls.other = User.objects.create_user('other', password='x')

    def cell(self, **kw):
        page = nav.olympiad_page(self.olymp, **kw)
        return row(final_grid(page), '2025/26')['cells'][2]

    def attempt(self, variant, user=None, session='', score=None, done=True):
        return TrainingAttempt.objects.create(
            variant=variant, user=user, session_key=session,
            submitted_at=timezone.now() if done else None,
            score=score, max_score=48 if done else None)

    def test_not_started_started_and_solved(self):
        tour1, tour2 = self.kits['2025/26'][4], self.kits['2025/26'][5]
        self.assertEqual(self.cell(user=self.user)['state']['status'], 'none')
        self.attempt(tour1, user=self.user, score=34)
        state = self.cell(user=self.user)['state']
        self.assertEqual((state['status'], state['label']),
                         ('started', '1 тур из 2'))
        self.attempt(tour2, user=self.user, score=47)
        state = self.cell(user=self.user)['state']
        self.assertEqual((state['status'], state['label']), ('done', '81 из 96'))

    def test_guest_sees_only_own_session_attempts(self):
        tour1 = self.kits['2025/26'][4]
        self.attempt(tour1, user=self.other, session='s-guest', score=40)
        self.attempt(tour1, session='s-someone', score=20)
        self.assertEqual(self.cell(session_key='s-guest')['state']['status'],
                         'none')
        self.attempt(tour1, session='s-guest', score=10)
        self.assertEqual(self.cell(session_key='s-guest')['state']['status'],
                         'started')

    def test_other_user_attempt_is_not_mine(self):
        self.attempt(self.kits['2025/26'][4], user=self.other, score=40)
        self.assertEqual(self.cell(user=self.user)['state']['status'], 'none')


class HomeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.olymp, cls.final, cls.kits = fx.mini_vsosh()
        cls.hidden = fx.olympiad('hid', is_published=False)
        cls.stub = fx.olympiad('stub', is_placeholder=True)
        cls.empty = fx.olympiad('empty', manual_rank=10)

    def test_home_numbers_equal_page_numbers(self):
        rows = {r['olympiad'].slug: r for r in nav.home_rows()}
        facts = nav.olympiad_page(self.olymp)['facts']
        self.assertEqual(rows['vs']['seasons'], facts['seasons'])
        self.assertEqual(rows['vs']['problems'], facts['problems'])

    def test_hidden_and_placeholders_are_not_listed(self):
        slugs = [r['olympiad'].slug for r in nav.home_rows()]
        self.assertEqual(slugs, ['vs', 'empty'])

    def test_empty_olympiad_has_no_grids(self):
        page = nav.olympiad_page(self.empty)
        self.assertEqual(page['grids'], [])
        self.assertEqual(page['facts']['problems'], 0)


@override_settings(OLYMPIADS_PUBLIC=True)
class FollowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.olymp = fx.olympiad('vs')
        cls.user = User.objects.create_user('pupil', password='x')

    def url(self):
        return reverse('olympiads:follow', args=['vs'])

    def test_guest_goes_to_login_and_base_is_untouched(self):
        response = self.client.post(self.url())
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])
        self.assertIn('next=', response['Location'])
        self.assertEqual(OlympiadFollow.objects.count(), 0)

    def test_add_twice_is_one_row_and_remove_works(self):
        self.client.force_login(self.user)
        self.client.post(self.url())
        self.client.post(self.url())
        self.assertEqual(OlympiadFollow.objects.count(), 1)
        self.assertTrue(nav.home_rows(self.user)[0]['followed'])
        self.client.post(self.url(), {'action': 'remove'})
        self.assertEqual(OlympiadFollow.objects.count(), 0)

    def test_get_is_not_allowed(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url()).status_code, 405)

    def test_csrf_is_enforced(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.url()).status_code, 403)

    def test_foreign_next_is_not_followed(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url(), {'next': 'https://evil.example/'})
        self.assertEqual(response['Location'], reverse('olympiads:detail',
                                                       args=['vs']))

    def test_hidden_olympiad_cannot_be_followed(self):
        fx.olympiad('hid', is_published=False)
        self.client.force_login(self.user)
        response = self.client.post(reverse('olympiads:follow', args=['hid']))
        self.assertEqual(response.status_code, 404)
