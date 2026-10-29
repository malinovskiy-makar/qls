# -*- coding: utf-8 -*-
"""Онбординг `/welcome/` (фазы 3–4, решения 29.10.2026).

* Шаги по порядку, без ответа — ошибка у поля и `onboarded_at` пуст.
* Полный проход ученика и преподавателя пишет ответы в профиль.
* Старый профиль видит свои ответы выбранными (`aria-pressed="true"`).
* Прыжок через шаг — редирект на первый незаполненный.
* Сторож текстов: на шагах нет «пояснялок» и ни одного `<p>`, кроме сноски про
  Instagram (экран = заголовок + элементы управления).
* «План готов»: сложность по уровню, один набор на человека и день.
* `next` переживает онбординг.
"""
import re
from datetime import date

from django.test import TestCase, override_settings
from django.utils import timezone

from problems import views_onboarding
from problems.models import SocialAccount, StudentGroup
from problems.models_platform import UserProfile
from problems.tests.factories import make_problem, make_user

FORBIDDEN_TEXTS = ('около', 'секунд', 'Дальше —', 'Что мы настроим')


def main_html(response):
    """Только середина страницы: шапка, полоса и полоса cookies — не текст шага."""
    html = response.content.decode('utf-8')
    found = re.search(r'<main class="ob-main">(.*?)</main>', html, re.S)
    return found.group(1) if found else ''


def pressed_values(html, name):
    """Значения вариантов `name`, отмеченных aria-pressed="true"."""
    return set(re.findall(
        r'aria-pressed="true">\s*<input type="(?:radio|checkbox)" name="%s" value="([^"]+)"'
        % re.escape(name), html))


class OnboardingBase(TestCase):
    def setUp(self):
        self.user = make_user('learner')
        self.profile = self.user.profile
        self.client.force_login(self.user)

    def post(self, step, data):
        return self.client.post('/welcome/%s/' % step, data)

    def pass_student(self):
        self.post('role', {'role': 'student'})
        self.post('grade', {'grade': '10', 'level': 'basic'})
        self.post('olympiad', {'main_olympiad': 'hse', 'source_channel': 'vk'})
        return self.post('place', {'city': 'Казань', 'school': 'Лицей 131'})

    def reload(self):
        self.profile.refresh_from_db()
        return self.profile


class StudentFlowTests(OnboardingBase):
    def test_entry_starts_with_who_are_you(self):
        self.assertRedirects(self.client.get('/welcome/'), '/welcome/role/',
                             fetch_redirect_response=False)

    def test_post_without_answer_is_an_error_at_the_field(self):
        self.post('role', {'role': 'student'})
        response = self.post('grade', {'grade': '10'})              # уровень не выбран
        self.assertEqual(response.status_code, 200)
        self.assertIn('ob-err', main_html(response))
        self.assertIsNone(self.reload().onboarded_at)
        self.assertEqual(self.profile.grade, '')                   # ничего не записано

    def test_full_pass_writes_the_profile(self):
        response = self.pass_student()
        self.assertRedirects(response, '/welcome/plan/', fetch_redirect_response=False)
        profile = self.reload()
        self.assertEqual((profile.role, profile.grade, profile.level), ('student', '10', 'basic'))
        self.assertEqual((profile.main_olympiad, profile.source_channel), ('hse', 'vk'))
        self.assertEqual((profile.city, profile.school), ('Казань', 'Лицей 131'))
        self.assertIsNotNone(profile.onboarded_at)

    def test_each_step_saves_right_away(self):
        self.post('role', {'role': 'student'})
        self.post('grade', {'grade': '8', 'level': 'novice'})
        self.assertEqual((self.reload().grade, self.profile.level), ('8', 'novice'))
        self.assertIsNone(self.profile.onboarded_at)

    def test_old_profile_answers_are_preselected(self):
        UserProfile.objects.filter(pk=self.profile.pk).update(grade='9', level='region')
        html = main_html(self.client.get('/welcome/grade/'))
        self.assertEqual(pressed_values(html, 'grade'), {'9'})
        self.assertEqual(pressed_values(html, 'level'), {'region'})

    def test_jump_over_a_step_goes_to_the_first_empty_one(self):
        response = self.client.get('/welcome/olympiad/')
        self.assertRedirects(response, '/welcome/grade/', fetch_redirect_response=False)
        response = self.post('place', {'city': 'X', 'school': 'Y'})
        self.assertRedirects(response, '/welcome/grade/', fetch_redirect_response=False)
        self.assertIsNone(self.reload().onboarded_at)

    def test_unknown_step_is_404(self):
        self.assertEqual(self.client.get('/welcome/nope/').status_code, 404)

    def test_next_survives_onboarding(self):
        self.client.get('/welcome/?next=/vp/vp-2026-t2-10/')
        response = self.pass_student()
        self.assertEqual(response['Location'], '/vp/vp-2026-t2-10/')

    def test_landing_next_shows_the_plan(self):
        self.client.get('/welcome/?next=%2Fprofile%2F%3Fwelcome%3D1')
        self.assertRedirects(self.pass_student(), '/welcome/plan/',
                             fetch_redirect_response=False)

    def test_foreign_next_is_ignored(self):
        self.client.get('/welcome/?next=https://evil.example/')
        self.assertRedirects(self.pass_student(), '/welcome/plan/',
                             fetch_redirect_response=False)

    def test_onboarded_entry_goes_to_the_plan(self):
        self.pass_student()
        self.assertRedirects(self.client.get('/welcome/'), '/welcome/plan/',
                             fetch_redirect_response=False)

    def test_anonymous_goes_to_login(self):
        self.client.logout()
        response = self.client.get('/welcome/role/')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('/login/'))

    @override_settings(MAIL_ENABLED=True)
    def test_service_account_without_email_goes_to_the_email_page_first(self):
        SocialAccount.objects.create(user=self.user, provider='vk', uid='1', created_user=True)
        response = self.client.get('/welcome/')
        self.assertEqual(response['Location'], '/account/email/?next=/welcome/')

    @override_settings(MAIL_ENABLED=True)
    def test_old_account_without_email_is_not_blocked(self):
        self.assertRedirects(self.client.get('/welcome/'), '/welcome/role/',
                             fetch_redirect_response=False)


class TextGuardTests(OnboardingBase):
    """Экран = заголовок + элементы управления (решение 29.10.2026)."""

    def _pages(self):
        UserProfile.objects.filter(pk=self.profile.pk).update(
            grade='10', level='basic', main_olympiad='hse', source_channel='vk')
        pages = {step: main_html(self.client.get('/welcome/%s/' % step))
                 for step in views_onboarding.STUDENT_STEPS}
        UserProfile.objects.filter(pk=self.profile.pk).update(
            role='tutor', teach_places=['school'], teach_grades=['9'])
        for step in ('teach', 'group'):
            pages[step] = main_html(self.client.get('/welcome/%s/' % step))
        return pages

    def test_no_filler_texts(self):
        for step, html in self._pages().items():
            self.assertTrue(html, step)
            for text in FORBIDDEN_TEXTS:
                self.assertNotIn(text, html, step)

    def test_no_paragraphs_besides_the_instagram_note(self):
        for step, html in self._pages().items():
            paragraphs = re.findall(r'<p\b[^>]*>(.*?)</p>', html, re.S)
            others = [p for p in paragraphs if 'Instagram принадлежит' not in p]
            self.assertEqual(others, [], step)

    def test_instagram_note_is_word_for_word(self):
        html = self._pages()['olympiad']
        self.assertIn('* Instagram принадлежит компании Meta, которая признана '
                      'экстремистской организацией и запрещена в России.', html)

    def test_level_tiles_carry_the_profile_hints(self):
        html = self._pages()['grade']
        for code, label in UserProfile.Level.choices:
            self.assertIn(label, html)
            self.assertIn(UserProfile.LEVEL_HINTS[code], html)

    def test_source_pills_in_wall_order(self):
        html = self._pages()['olympiad']
        labels = re.findall(r'name="source_channel" value="[^"]+"[^>]*>\s*<span>([^<]+)</span>', html)
        self.assertEqual(labels, [label for _code, label in UserProfile.SourceChannel.choices])


class PlanTests(OnboardingBase):
    def setUp(self):
        super().setUp()
        for difficulty in (1, 2, 3, 4, 5):
            for n in range(3):
                make_problem(statement='Задача %d-%d' % (difficulty, n), difficulty=difficulty,
                             solution='Решение' if n else '')

    def test_tasks_follow_the_level(self):
        for level, (low, high) in views_onboarding.DIFFICULTY_BY_LEVEL.items():
            self.profile.level = level
            tasks = views_onboarding.plan_problems(self.profile, date(2026, 10, 29))
            self.assertEqual(len(tasks), 3, level)
            for task in tasks:
                self.assertTrue(low <= task.difficulty <= high, (level, task.difficulty))

    def test_same_user_same_day_same_set(self):
        self.profile.level = 'basic'
        day = date(2026, 10, 29)
        first = [p.pk for p in views_onboarding.plan_problems(self.profile, day)]
        second = [p.pk for p in views_onboarding.plan_problems(self.profile, day)]
        self.assertEqual(first, second)

    def test_problems_with_solution_come_first(self):
        self.profile.level = 'final'                      # 6 задач, из них 4 с решением
        tasks = views_onboarding.plan_problems(self.profile, date(2026, 10, 29))
        self.assertTrue(all(task.solution for task in tasks))

    def test_hidden_problems_never_get_in(self):
        from problems.models import Problem
        Problem.objects.filter(difficulty__in=(2, 3)).update(hidden_pending_review=True)
        self.profile.level = 'basic'
        self.assertEqual(views_onboarding.plan_problems(self.profile, date(2026, 10, 29)), [])

    def test_plan_page(self):
        self.pass_student()
        response = self.client.get('/welcome/plan/')
        html = main_html(response)
        self.assertIn('План готов', html)
        self.assertIn('10 класс', html)
        self.assertIn('Казань', html)
        self.assertIn('Три задачи', html)
        self.assertIn('Тренажёр 2 тура «Высшей пробы»', html)
        self.assertIn('Вызов дня', html)
        self.assertIn('href="/game/daily/"', html)
        self.assertIn('href="/welcome/grade/"', html)          # «Изменить»
        self.assertEqual(html.count('class="ob-task"'), 3)

    def test_no_vp_card_for_eighth_grade_without_hse(self):
        self.post('role', {'role': 'student'})
        self.post('grade', {'grade': '8', 'level': 'basic'})
        self.post('olympiad', {'main_olympiad': 'vsosh', 'source_channel': 'vk'})
        self.post('place', {'city': 'Омск', 'school': '1'})
        html = main_html(self.client.get('/welcome/plan/'))
        self.assertNotIn('Высшей пробы', html)
        self.assertIn('href="/olympiads/"', html)

    def test_plan_before_onboarding_goes_to_onboarding(self):
        self.assertRedirects(self.client.get('/welcome/plan/'), '/welcome/',
                             fetch_redirect_response=False)


class TutorFlowTests(OnboardingBase):
    def test_full_pass_with_a_group(self):
        response = self.post('role', {'role': 'tutor'})
        self.assertRedirects(response, '/welcome/teach/', fetch_redirect_response=False)
        response = self.post('teach', {'teach_places': ['school', 'private'],
                                       'teach_grades': ['9', '11']})
        self.assertRedirects(response, '/welcome/group/', fetch_redirect_response=False)
        profile = self.reload()
        self.assertEqual(profile.teach_places, ['school', 'private'])
        self.assertEqual(profile.teach_grades, ['9', '11'])
        self.assertIsNotNone(profile.onboarded_at)
        self.user.refresh_from_db()
        self.assertEqual((profile.role, self.user.role), ('tutor', 'teacher'))

        before = StudentGroup.objects.count()
        response = self.post('group', {'name': '10 Б', 'kind': 'group'})
        self.assertEqual(StudentGroup.objects.count(), before + 1)
        group = StudentGroup.objects.get(teacher=self.user)
        self.assertRegex(group.invite_code, r'^[A-Z0-9]{4}-[A-Z0-9]{4}$')
        html = main_html(response)
        self.assertIn(group.invite_code, html)
        self.assertIn('Скопировать', html)
        self.assertIn('В кабинет', html)

    def test_individual_without_a_student(self):
        self.post('role', {'role': 'tutor'})
        self.post('teach', {'teach_places': ['private'], 'teach_grades': ['10']})
        self.post('group', {'name': 'Маша', 'kind': 'individual'})
        self.assertEqual(StudentGroup.objects.get(teacher=self.user).kind, 'individual')

    def test_later_means_no_group_but_onboarded(self):
        self.post('role', {'role': 'tutor'})
        self.post('teach', {'teach_places': ['circle'], 'teach_grades': ['7']})
        html = main_html(self.client.get('/welcome/group/'))
        self.assertIn('href="/teacher/">Позже', html)
        self.assertEqual(StudentGroup.objects.filter(teacher=self.user).count(), 0)
        self.assertIsNotNone(self.reload().onboarded_at)

    def test_without_places_is_an_error(self):
        self.post('role', {'role': 'tutor'})
        response = self.post('teach', {'teach_grades': ['9']})
        self.assertEqual(response.status_code, 200)
        self.assertIn('ob-err', main_html(response))
        self.assertIsNone(self.reload().onboarded_at)

    def test_without_grades_is_an_error(self):
        self.post('role', {'role': 'tutor'})
        response = self.post('teach', {'teach_places': ['school']})
        self.assertIn('ob-err', main_html(response))
        self.assertIsNone(self.reload().onboarded_at)

    def test_tutor_with_groups_stays_a_tutor(self):
        self.profile.role = 'tutor'
        self.profile.save()
        StudentGroup.objects.create(name='Старая', teacher=self.user)
        response = self.post('role', {'role': 'student'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.reload().role, 'tutor')

    def test_student_steps_are_closed_to_a_tutor(self):
        self.post('role', {'role': 'tutor'})
        self.assertRedirects(self.client.get('/welcome/grade/'), '/welcome/',
                             fetch_redirect_response=False)


class OnboardedAtIsKeptTests(OnboardingBase):
    def test_editing_later_keeps_the_first_date(self):
        self.pass_student()
        first = self.reload().onboarded_at
        self.post('grade', {'grade': '11', 'level': 'final'})
        self.post('olympiad', {'main_olympiad': 'mosh', 'source_channel': 'friend'})
        self.post('place', {'city': 'Казань', 'school': 'Лицей 131'})
        self.assertEqual(self.reload().onboarded_at, first)
        self.assertEqual(self.profile.grade, '11')
        self.assertLessEqual(first, timezone.now())
