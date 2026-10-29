# -*- coding: utf-8 -*-
"""Онбординг `/welcome/` — раунд 2 (решения 29.10.2026, макет docs/design/onboarding_r2/).

* Где выбор один — переход сразу: POST одного значения ведёт на следующий шаг.
* У нового человека на «Кто вы?» ничего не выбрано; у старого — его ответ.
* Класс и уровень — один экран, два этапа; «Уже не школьник» пропускает «школу».
* Цели — можно несколько, «Пока не решил» — только одна.
* «Откуда узнали → Другое» пишет текст в `source_other`; иначе он пуст.
* Старому аккаунту без почты — шаг «Добавьте почту» с «Позже».
* Сторож текстов: на шагах нет `<p>`, кроме сноски про Instagram.
* Подвал с документами — в потоке страницы, не в фиксированной полосе.
* «План готов»: состав карточек по целям и классу.
* Миграция 0085 переводит `main_olympiad` в `goals`.
"""
import re
from datetime import date
from pathlib import Path

from django.conf import settings
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from problems import views_onboarding
from problems.models import SocialAccount, StudentGroup
from problems.models_platform import UserProfile
from problems.tests.factories import make_problem, make_user

FORBIDDEN_TEXTS = ('около', 'секунд', 'Дальше —', 'Что мы настроим', 'Им вы входите')
INSTAGRAM_NOTE = ('* Instagram принадлежит компании Meta, которая признана '
                  'экстремистской организацией и запрещена в России.')


def main_html(response):
    """Только середина страницы: шапка, подвал и полоса cookies — не текст шага."""
    html = response.content.decode('utf-8')
    found = re.search(r'<main class="ob-main"[^>]*>(.*?)</main>', html, re.S)
    return found.group(1) if found else ''


def pressed(html, name):
    """Значения кнопок `name`, отмеченных aria-pressed="true"."""
    values = set()
    for tag in re.findall(r'<button\b[^>]*>', html):
        if 'name="%s"' % name in tag and 'aria-pressed="true"' in tag:
            values.add(re.search(r'value="([^"]*)"', tag).group(1))
    return values


class OnboardingBase(TestCase):
    def setUp(self):
        self.user = make_user('learner')
        self.profile = self.user.profile
        self.client.force_login(self.user)

    def post(self, step, data):
        return self.client.post('/welcome/%s/' % step, data)

    def pass_student(self, grade='10', goals=('listed',), source='vk'):
        self.post('role', {'role': 'student'})
        self.post('grade', {'grade': grade})
        self.post('grade', {'level': 'basic'})
        self.post('goals', {'goals': list(goals)})
        if grade != 'none':
            self.post('school', {'city': 'Казань', 'school': 'Лицей 131'})
        return self.post('source', {'source_channel': source})

    def reload(self):
        self.profile.refresh_from_db()
        return self.profile


class StudentFlowTests(OnboardingBase):
    def test_entry_starts_with_who_are_you(self):
        self.assertRedirects(self.client.get('/welcome/'), '/welcome/role/',
                             fetch_redirect_response=False)

    def test_new_person_sees_nothing_preselected(self):
        html = main_html(self.client.get('/welcome/role/'))
        self.assertEqual(html.count('name="role"'), 2)
        self.assertNotIn('aria-pressed="true"', html)

    def test_old_student_sees_the_role_preselected(self):
        UserProfile.objects.filter(pk=self.profile.pk).update(grade='9', level='region')
        self.assertEqual(pressed(main_html(self.client.get('/welcome/role/')), 'role'),
                         {'student'})

    def test_role_without_a_next_button_goes_straight_on(self):
        html = main_html(self.client.get('/welcome/role/'))
        self.assertNotIn('Дальше', html)
        self.assertRegex(html, r'<button type="submit" name="role" value="student"')
        response = self.post('role', {'role': 'student'})
        self.assertRedirects(response, '/welcome/grade/', fetch_redirect_response=False)

    def test_grade_then_level_on_one_screen(self):
        self.post('role', {'role': 'student'})
        html = main_html(self.client.get('/welcome/grade/'))
        self.assertIn('В каком вы классе?', html)
        self.assertIn('Уже не школьник', html)
        self.assertNotIn('name="level"', html)
        for code in ('le7', '8', '9', '10', '11', 'none'):
            self.assertIn('name="grade" value="%s"' % code, html)
        response = self.post('grade', {'grade': '10'})
        self.assertRedirects(response, '/welcome/grade/', fetch_redirect_response=False)
        self.assertEqual(self.reload().grade, '10')
        html = main_html(self.client.get('/welcome/grade/'))
        self.assertIn('Ваш уровень', html)
        self.assertIn('10 класс<span>Изменить</span>', html)
        self.assertNotIn('name="grade"', html)
        self.assertIn('В каком вы классе?', main_html(self.client.get('/welcome/grade/?change=1')))
        response = self.post('grade', {'level': 'basic'})
        self.assertRedirects(response, '/welcome/goals/', fetch_redirect_response=False)

    def test_post_without_answer_is_an_error_at_the_field(self):
        self.post('role', {'role': 'student'})
        self.post('grade', {'grade': '10'})
        self.post('grade', {'level': 'basic'})
        response = self.post('goals', {})
        self.assertEqual(response.status_code, 200)
        self.assertIn('ob-err', main_html(response))
        self.assertEqual(self.reload().goals, [])
        self.assertIsNone(self.profile.onboarded_at)

    def test_undecided_does_not_go_with_another_goal(self):
        self.post('role', {'role': 'student'})
        self.post('grade', {'grade': '10'})
        self.post('grade', {'level': 'basic'})
        response = self.post('goals', {'goals': ['vsosh', 'undecided']})
        self.assertEqual(response.status_code, 200)
        self.assertIn('не сочетается', main_html(response))
        self.assertEqual(self.reload().goals, [])
        self.post('goals', {'goals': ['vsosh', 'listed']})
        self.assertEqual(self.reload().goals, ['vsosh', 'listed'])

    def test_full_pass_writes_the_profile(self):
        response = self.pass_student(goals=('vsosh', 'listed'))
        self.assertRedirects(response, '/welcome/build/', fetch_redirect_response=False)
        profile = self.reload()
        self.assertEqual((profile.role, profile.grade, profile.level), ('student', '10', 'basic'))
        self.assertEqual(profile.goals, ['vsosh', 'listed'])
        self.assertEqual((profile.city, profile.school), ('Казань', 'Лицей 131'))
        self.assertEqual((profile.source_channel, profile.source_other), ('vk', ''))
        self.assertIsNotNone(profile.onboarded_at)

    def test_not_a_pupil_skips_the_school_step(self):
        self.post('role', {'role': 'student'})
        self.post('grade', {'grade': 'none'})
        self.post('grade', {'level': 'novice'})
        response = self.post('goals', {'goals': ['knowledge']})
        self.assertRedirects(response, '/welcome/source/', fetch_redirect_response=False)
        page = self.client.get('/welcome/source/')
        self.assertContains(page, '4 из 4')
        self.assertNotIn('Школа', main_html(page))                 # строки «Школа» нет
        self.assertRedirects(self.client.get('/welcome/school/'), '/welcome/',
                             fetch_redirect_response=False)
        self.assertRedirects(self.post('source', {'source_channel': 'friend'}),
                             '/welcome/build/', fetch_redirect_response=False)
        self.assertIsNotNone(self.reload().onboarded_at)

    def test_pupil_has_five_steps(self):
        self.post('role', {'role': 'student'})
        self.assertContains(self.client.get('/welcome/grade/'), '2 из 5')

    def test_other_source_keeps_the_text(self):
        self.pass_student(source='other')
        self.assertEqual(self.reload().source_other, '')
        self.post('source', {'source_channel': 'other', 'source_other': '  кружок в ДДТ  '})
        self.assertEqual(self.reload().source_other, 'кружок в ДДТ')
        self.post('source', {'source_channel': 'vk', 'source_other': 'не то'})
        self.assertEqual((self.reload().source_channel, self.profile.source_other), ('vk', ''))

    def test_jump_over_a_step_goes_to_the_first_empty_one(self):
        response = self.client.get('/welcome/goals/')
        self.assertRedirects(response, '/welcome/grade/', fetch_redirect_response=False)
        response = self.post('school', {'city': 'X', 'school': 'Y'})
        self.assertRedirects(response, '/welcome/grade/', fetch_redirect_response=False)
        self.assertIsNone(self.reload().onboarded_at)

    def test_round_one_addresses_lead_to_the_start(self):
        for old in ('olympiad', 'place'):
            self.assertRedirects(self.client.get('/welcome/%s/' % old), '/welcome/',
                                 fetch_redirect_response=False)

    def test_unknown_step_is_404(self):
        self.assertEqual(self.client.get('/welcome/nope/').status_code, 404)

    def test_next_survives_onboarding_and_build_is_short(self):
        self.client.get('/welcome/?next=/vp/vp-2026-t2-10/')
        response = self.pass_student()
        self.assertEqual(response['Location'], '/welcome/build/?to=%2Fvp%2Fvp-2026-t2-10%2F')
        page = self.client.get(response['Location'])
        self.assertContains(page, 'data-ob-target="/vp/vp-2026-t2-10/"')
        self.assertEqual(main_html(page).count('<li '), 2)          # две строки, без плана

    def test_build_without_next_goes_to_the_plan(self):
        self.pass_student()
        page = self.client.get('/welcome/build/')
        self.assertContains(page, 'data-ob-target="/welcome/plan/"')
        html = main_html(page)
        self.assertIn('Подбираем задачи для 10 класса', html)
        self.assertIn('Смотрим ближайшие туры', html)
        self.assertIn('Собираем план', html)
        self.assertContains(page, '<noscript><meta http-equiv="refresh" content="0; url=/welcome/plan/">')

    def test_build_for_not_a_pupil(self):
        self.pass_student(grade='none', goals=('knowledge',))
        self.assertIn('Подбираем задачи под ваш уровень',
                      main_html(self.client.get('/welcome/build/')))

    def test_foreign_build_target_is_ignored(self):
        self.pass_student()
        page = self.client.get('/welcome/build/?to=https://evil.example/')
        self.assertContains(page, 'data-ob-target="/welcome/plan/"')

    def test_landing_and_foreign_next_show_the_plan(self):
        for target in ('%2Fprofile%2F%3Fwelcome%3D1', 'https://evil.example/'):
            self.client.get('/welcome/?next=' + target)
        self.assertRedirects(self.pass_student(), '/welcome/build/',
                             fetch_redirect_response=False)

    def test_onboarded_entry_goes_to_the_build(self):
        self.pass_student()
        self.assertRedirects(self.client.get('/welcome/'), '/welcome/build/',
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
        page = self.client.get(response['Location'])
        self.assertContains(page, 'Осталась почта')
        self.assertContains(page, 'VK ID её не передал.')


@override_settings(MAIL_ENABLED=True)
class EmailStepTests(OnboardingBase):
    """Старый аккаунт без подтверждённой почты: шаг «Добавьте почту» с «Позже»
    (решение раунда 2: мягко, без блокировки — решение 26.10)."""

    def test_old_account_without_email_gets_the_step_last(self):
        self.assertRedirects(self.client.get('/welcome/'), '/welcome/role/',
                             fetch_redirect_response=False)
        response = self.pass_student()
        self.assertRedirects(response, '/welcome/email/', fetch_redirect_response=False)
        page = self.client.get('/welcome/email/')
        self.assertContains(page, '6 из 6')
        html = main_html(page)
        self.assertIn('Добавьте почту', html)
        self.assertIn('Получить код', html)
        self.assertIn('action="/account/email/"', html)
        self.assertIn('name="src" value="onb"', html)
        self.assertIn('>Позже</button>', html)
        self.assertIsNotNone(self.reload().onboarded_at)          # почта не держит онбординг

    def test_later_goes_on_and_does_not_come_back(self):
        self.pass_student()
        response = self.post('email', {'later': '1'})
        self.assertRedirects(response, '/welcome/build/', fetch_redirect_response=False)
        self.assertRedirects(self.client.get('/welcome/'), '/welcome/build/',
                             fetch_redirect_response=False)

    def test_code_page_looks_like_the_login_screen(self):
        self.pass_student()
        page = self.client.get('/account/email/?src=onb&next=/welcome/')
        self.assertTemplateUsed(page, 'registration/need_email.html')
        self.assertContains(page, 'Добавьте почту')

    def test_verified_email_means_no_step(self):
        self.user.email = 'learner@mail.ru'
        self.user.email_verified_at = timezone.now()
        self.user.save()
        self.assertRedirects(self.pass_student(), '/welcome/build/',
                             fetch_redirect_response=False)


class TextGuardTests(OnboardingBase):
    """Экран = заголовок + элементы управления (решение 29.10.2026)."""

    def _pages(self):
        UserProfile.objects.filter(pk=self.profile.pk).update(
            role='student', grade='10', level='basic', goals=['listed'], city='Казань',
            school='1', source_channel='vk')
        pages = {step: main_html(self.client.get('/welcome/%s/' % step))
                 for step in ('role', 'grade', 'goals', 'school', 'source')}
        pages['grade_stage'] = main_html(self.client.get('/welcome/grade/?change=1'))
        with self.settings(MAIL_ENABLED=True):
            pages['email'] = main_html(self.client.get('/welcome/email/'))
        UserProfile.objects.filter(pk=self.profile.pk).update(
            role='tutor', teach_places=['school'], teach_grades=['9'])
        for step in ('teach', 'group'):
            pages[step] = main_html(self.client.get('/welcome/%s/' % step))
        return pages

    def test_every_step_renders(self):
        for step, html in self._pages().items():
            self.assertIn('class="ob-h"', html, step)

    def test_no_filler_texts(self):
        for step, html in self._pages().items():
            for text in FORBIDDEN_TEXTS:
                self.assertNotIn(text, html, step)

    def test_no_paragraphs_besides_the_instagram_note(self):
        for step, html in self._pages().items():
            paragraphs = re.findall(r'<p\b[^>]*>(.*?)</p>', html, re.S)
            others = [p for p in paragraphs if 'Instagram принадлежит' not in p]
            self.assertEqual(others, [], step)

    def test_instagram_note_is_word_for_word(self):
        self.assertIn(INSTAGRAM_NOTE, self._pages()['source'])

    def test_level_tiles_carry_the_profile_hints(self):
        html = self._pages()['grade']
        for code, label in UserProfile.Level.choices:
            self.assertIn(label, html)
            self.assertIn(UserProfile.LEVEL_HINTS[code], html)

    def test_source_pills_in_wall_order_and_other_field(self):
        html = self._pages()['source']
        labels = re.findall(r'name="source_channel" value="[^"]+"[^>]*>([^<]+)</button>', html)
        self.assertEqual(labels, [label for _code, label in UserProfile.SourceChannel.choices])
        self.assertIn('placeholder="Где именно?"', html)
        self.assertIn('maxlength="120"', html)

    def test_goal_tiles_with_real_logos(self):
        html = self._pages()['goals']
        for label in ('ВсОШ', 'Перечневые олимпиады', 'Высшая проба, МОШ, РАНХиГС и другие',
                      'Международные олимпиады', 'IEO и другие', 'Разобраться в экономике',
                      'Пока не решил'):
            self.assertIn(label, html)
        for logo in ('vsosh_econ_top.png', 'vp_logo.png', 'ranepa_mark.png', 'nes_mark.png',
                     'ieo_mark.png'):
            self.assertIn('onboarding/logos/' + logo, html)
            self.assertTrue((Path(settings.BASE_DIR) / 'static' / 'onboarding' / 'logos' / logo).exists())


class FooterTests(OnboardingBase):
    """Раунд 4 (решение владельца 29.10.2026): на шагах онбординга подвала с документами
    НЕТ — согласие человек уже дал на регистрации или «Почти готово», и там подвал
    есть (`test_footer_r4.FooterPagesTests`). По 152-ФЗ Политика должна быть
    опубликована и доступна на сайте, а не стоять на каждой странице."""

    def test_no_footer_on_the_steps(self):
        UserProfile.objects.filter(pk=self.profile.pk).update(role='student', grade='10',
                                                              level='basic')
        for url in ('/welcome/role/', '/welcome/goals/'):
            html = self.client.get(url).content.decode('utf-8')
            self.assertNotIn('<p class="legal-foot">', html, url)
            self.assertNotIn('<div class="site-version">', html, url)
            self.assertIn('id="cookie-bar"', html, url)

    def test_login_and_register_keep_the_footer(self):
        self.client.logout()
        for url in ('/login/', '/register/'):
            html = self.client.get(url).content.decode('utf-8')
            self.assertEqual(html.count('<p class="legal-foot">'), 1, url)

    def test_no_fixed_bar_in_the_styles(self):
        css = (Path(settings.BASE_DIR) / 'static' / 'onboarding' / 'onboarding.css').read_text(
            encoding='utf-8')
        self.assertNotRegex(css, r'position:\s*fixed')


class ProfileCardTests(OnboardingBase):
    def test_rows_and_current_step(self):
        self.post('role', {'role': 'student'})
        html = main_html(self.client.get('/welcome/grade/'))
        rows = re.findall(r'<li class="([^"]*)"><span class="ob-me-k">([^<]+)</span>', html)
        self.assertEqual([label for _cls, label in rows],
                         ['Роль', 'Класс', 'Уровень', 'Цели', 'Школа', 'Откуда'])
        self.assertIn('is-now', dict((label, cls) for cls, label in rows)['Класс'])
        self.assertIn('is-new', dict((label, cls) for cls, label in rows)['Роль'])

    def test_not_a_pupil_has_no_school_row(self):
        self.post('role', {'role': 'student'})
        self.post('grade', {'grade': 'none'})
        self.assertNotIn('>Школа<', main_html(self.client.get('/welcome/grade/')))

    def test_tutor_rows(self):
        self.post('role', {'role': 'tutor'})
        html = main_html(self.client.get('/welcome/teach/'))
        labels = re.findall(r'<span class="ob-me-k">([^<]+)</span>', html)
        self.assertEqual(labels, ['Роль', 'Где', 'Классы', 'Откуда', 'Группа'])


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

    def plan_for(self, grade, goals):
        self.pass_student(grade=grade, goals=goals)
        return main_html(self.client.get('/welcome/plan/'))

    def assert_common(self, html):
        self.assertIn('Три задачи для старта', html)
        self.assertEqual(html.count('class="pl-task"'), 3)
        self.assertIn('Вызов дня', html)
        self.assertIn('href="/game/daily/"', html)
        self.assertIn('Умный поиск', html)
        self.assertIn('задача про монополию с налогом', html)
        self.assertIn('/catalog/?q=', html)
        self.assertEqual(html.count('Скоро'), 1)                  # единственное обещание
        self.assertIn('Подбор задач по вашим ошибкам', html)
        self.assertIn('href="/welcome/grade/?change=1"', html)    # «Изменить»

    def test_tenth_grade_listed_gets_the_vp_trainer(self):
        html = self.plan_for('10', ('listed',))
        self.assert_common(html)
        self.assertIn('Тренажёр 2 тура «Высшей пробы»', html)
        self.assertIn('vp_logo.png', html)
        self.assertNotIn('Карта тем', html)

    def test_eighth_grade_vsosh_gets_vsosh_tasks(self):
        html = self.plan_for('8', ('vsosh',))
        self.assert_common(html)
        self.assertIn('Задачи ВсОШ', html)
        self.assertNotIn('Высшей пробы', html)
        self.assertRegex(html, r'href="/catalog/\?[^"]*difficulty=2')

    def test_not_a_pupil_knowledge_gets_the_map(self):
        html = self.plan_for('none', ('knowledge',))
        self.assert_common(html)
        self.assertIn('Карта тем', html)
        self.assertIn('href="/catalog/map/"', html)
        self.assertNotIn('Высшей пробы', html)

    def test_plan_heading_and_chips(self):
        self.user.first_name = 'Мария'
        self.user.save()
        html = self.plan_for('10', ('vsosh', 'listed'))
        self.assertIn('Мария, план готов', html)
        for chip in ('10 класс', 'Начинающий', 'ВсОШ', 'Перечневые'):
            self.assertIn('>%s<' % chip, html)

    def test_plan_before_onboarding_goes_to_onboarding(self):
        self.assertRedirects(self.client.get('/welcome/plan/'), '/welcome/',
                             fetch_redirect_response=False)


class TutorFlowTests(OnboardingBase):
    def pass_tutor(self):
        self.post('role', {'role': 'tutor'})
        self.post('teach', {'teach_places': ['school', 'private'], 'teach_grades': ['9', '11']})
        return self.post('source', {'source_channel': 'teacher'})

    def test_full_pass_with_a_group(self):
        response = self.post('role', {'role': 'tutor'})
        self.assertRedirects(response, '/welcome/teach/', fetch_redirect_response=False)
        response = self.post('teach', {'teach_places': ['school', 'private'],
                                       'teach_grades': ['9', '11']})
        self.assertRedirects(response, '/welcome/source/', fetch_redirect_response=False)
        self.assertIsNone(self.reload().onboarded_at)
        response = self.post('source', {'source_channel': 'teacher'})
        self.assertRedirects(response, '/welcome/group/', fetch_redirect_response=False)
        profile = self.reload()
        self.assertEqual(profile.teach_places, ['school', 'private'])
        self.assertEqual(profile.teach_grades, ['9', '11'])
        self.assertIsNotNone(profile.onboarded_at)
        self.user.refresh_from_db()
        self.assertEqual((profile.role, self.user.role), ('tutor', 'teacher'))

        page = self.client.get('/welcome/group/')
        self.assertContains(page, '4 из 4')
        code = re.search(r'data-copy-src>([A-Z0-9]{4}-[A-Z0-9]{4})<', page.content.decode()).group(1)
        before = StudentGroup.objects.count()
        response = self.post('group', {'name': '10 Б', 'invite_code': 'AAAA-AAAA'})
        self.assertRedirects(response, '/teacher/', fetch_redirect_response=False)
        self.assertEqual(StudentGroup.objects.count(), before + 1)
        group = StudentGroup.objects.get(teacher=self.user)
        self.assertEqual(group.invite_code, code)               # тот, что показали, а не из формы

    def test_later_means_no_group_but_onboarded(self):
        self.pass_tutor()
        html = main_html(self.client.get('/welcome/group/'))
        self.assertIn('href="/teacher/">Позже', html)
        self.assertEqual(StudentGroup.objects.filter(teacher=self.user).count(), 0)
        self.assertIsNotNone(self.reload().onboarded_at)

    def test_without_places_is_an_error(self):
        self.post('role', {'role': 'tutor'})
        response = self.post('teach', {'teach_grades': ['9']})
        self.assertEqual(response.status_code, 200)
        self.assertIn('ob-err', main_html(response))

    def test_without_grades_is_an_error(self):
        self.post('role', {'role': 'tutor'})
        response = self.post('teach', {'teach_places': ['school']})
        self.assertIn('ob-err', main_html(response))

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


@override_settings(ONBOARDING_ENABLED=True)
class SignupGoalTests(OnboardingBase):
    """Роль выбирают в онбординге: вид регистрации уточняет «Кто вы?», один раз."""

    def test_role_step_sets_the_signup_kind_once(self):
        from problems import signup_source
        from problems.models_platform import SignupSource
        SignupSource.objects.create(user=self.user, signup_kind=SignupSource.Kind.STUDENT)
        session = self.client.session
        session[signup_source.GOAL_PENDING_KEY] = True
        session.save()
        self.post('role', {'role': 'tutor'})
        self.assertEqual(SignupSource.objects.get(user=self.user).signup_kind,
                         SignupSource.Kind.TEACHER)
        self.assertNotIn(signup_source.GOAL_PENDING_KEY, self.client.session)
        self.post('role', {'role': 'student'})                    # второй раз — не трогаем
        self.assertEqual(SignupSource.objects.get(user=self.user).signup_kind,
                         SignupSource.Kind.TEACHER)


class OnboardedAtIsKeptTests(OnboardingBase):
    def test_editing_later_keeps_the_first_date(self):
        self.pass_student()
        first = self.reload().onboarded_at
        self.post('grade', {'grade': '11'})
        self.post('grade', {'level': 'final'})
        self.post('goals', {'goals': ['international']})
        self.post('source', {'source_channel': 'friend'})
        self.assertEqual(self.reload().onboarded_at, first)
        self.assertEqual((self.profile.grade, self.profile.goals), ('11', ['international']))
        self.assertLessEqual(first, timezone.now())


class GoalsMigrationTests(TransactionTestCase):
    """0085: `main_olympiad` → `goals` (hse/mosh/listed → listed, ieo → international)."""

    def test_three_examples(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        leaf = [node for node in executor.loader.graph.leaf_nodes() if node[0] == 'problems']
        executor.migrate([('problems', '0084_login_onboarding')])
        old = executor.loader.project_state([('problems', '0084_login_onboarding')]).apps
        OldUser = old.get_model('problems', 'User')
        OldProfile = old.get_model('problems', 'UserProfile')
        for name, value in (('a', 'hse'), ('b', 'ieo'), ('c', 'undecided'), ('d', '')):
            user = OldUser.objects.create(username=name)
            OldProfile.objects.update_or_create(user=user, defaults={'main_olympiad': value})
        executor = MigrationExecutor(connection)
        executor.migrate(leaf)
        goals = dict(UserProfile.objects.values_list('user__username', 'goals'))
        self.assertEqual(goals['a'], ['listed'])
        self.assertEqual(goals['b'], ['international'])
        self.assertEqual(goals['c'], ['undecided'])
        self.assertEqual(goals['d'], [])
