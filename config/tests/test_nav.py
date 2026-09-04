# -*- coding: utf-8 -*-
"""Шапка сайта: состав по ролям, метка версии, выход, узкий экран.

⚠️ ПОЧЕМУ ПРОВЕРКИ ПО ОТРИСОВАННОЙ СТРАНИЦЕ, А НЕ ПО ШАБЛОНУ. До 04.09.2026
`_nav.html` держал четыре копии одного ряда ссылок, и старые тесты считали в
файле литералы («ровно четыре „Тренажёр"», «ровно восемь условий подсветки»).
Копий больше нет: состав собирает `config/context_processors.py::site_meta`.
Считать в файле стало нечего — и это к лучшему: важно, что видит человек.
"""
import re

from django.test import TestCase

from problems.models import User

PASSWORD = 'nav-probe-2026'

# Семь шаблонов подключают `_nav.html`. По одному адресу на каждый — метка
# версии обязана быть на всех: «угол, который ничем не закрыт».
# Роль указана потому, что кабинеты закрыты друг от друга: `/student/`
# отдаёт учителю 403, и это правильно.
TEMPLATE_PAGES = (
    ('/catalog/', 'catalog/base.html', 'student'),
    ('/student/', 'student/base.html', 'student'),
    # `/teacher/` — редирект по устройству (своего экрана у корня нет).
    ('/teacher/groups/', 'teacher/base.html', 'teacher'),
    ('/profile/', 'platform/base.html', 'student'),
    ('/calc2/', 'calc2/calc2.html', 'student'),
    ('/game/', 'game/game.html', 'student'),
    ('/calendar/', 'calendar_stub/calendar.html', 'student'),
)


def nav_labels(html):
    """Подписи пунктов ряда в шапке (не в панели узкого экрана)."""
    block = html.split('<div class="nav-links">', 1)[-1].split('</div>', 1)[0]
    return re.findall(r'class="nav-link[^"]*"[^>]*>([^<]+)</a>', block)


class MenuByRoleTests(TestCase):
    """Состав меню зависит от роли — и только от неё."""

    def _labels(self, user=None, url='/catalog/'):
        if user is not None:
            self.client.force_login(user)
        return nav_labels(self.client.get(url).content.decode('utf-8'))

    def test_guest(self):
        self.assertEqual(
            self._labels(),
            ['Каталог', 'Учебник', 'Олимпиады', 'Графики', 'Тренажёр'])

    def test_student_has_lessons_and_no_stats(self):
        user = User.objects.create_user(username='nav_st', password=PASSWORD,
                                        role='student')
        labels = self._labels(user)
        self.assertEqual(
            labels,
            ['Занятия', 'Каталог', 'Учебник', 'Олимпиады', 'Календарь',
             'Графики', 'Тренажёр'])
        # Статистика живёт в профиле; двух входов в одно место быть не должно.
        self.assertNotIn('Статистика', labels)

    def test_teacher(self):
        user = User.objects.create_user(username='nav_tu', password=PASSWORD,
                                        role='teacher')
        self.assertEqual(
            self._labels(user),
            ['Ученики', 'Каталог', 'Учебник', 'Олимпиады', 'Календарь',
             'Графики', 'Тренажёр'])

    def test_staff_gets_admin_item(self):
        user = User.objects.create_user(username='nav_ad', password=PASSWORD,
                                        role='teacher', is_staff=True)
        self.assertIn('Админка', self._labels(user))

    def test_textbook_stands_right_after_catalog_for_every_role(self):
        """Порядок задан владельцем и одинаков у всех ролей."""
        users = [
            None,
            User.objects.create_user(username='nav_o1', password=PASSWORD, role='student'),
            User.objects.create_user(username='nav_o2', password=PASSWORD, role='teacher'),
        ]
        for user in users:
            self.client.logout()
            labels = self._labels(user)
            self.assertEqual(labels.count('Учебник'), 1, labels)
            self.assertEqual(labels[labels.index('Каталог') + 1], 'Учебник', labels)

    def test_every_item_appears_once(self):
        user = User.objects.create_user(username='nav_once', password=PASSWORD,
                                        role='teacher')
        labels = self._labels(user)
        self.assertEqual(len(labels), len(set(labels)), labels)


class ActiveItemTests(TestCase):
    """«Где я сейчас» — подчёркивание плюс фон (ADR 0072)."""

    def test_only_the_current_item_is_active(self):
        for url, expected in (('/catalog/', 'Каталог'),
                              ('/olympiads/', 'Олимпиады'),
                              ('/game/', 'Тренажёр'),
                              ('/textbook/', 'Учебник')):
            html = self.client.get(url).content.decode('utf-8')
            active = re.findall(r'class="nav-link is-active"[^>]*>([^<]+)</a>', html)
            self.assertEqual(set(active), {expected}, '%s → %s' % (url, active))

    def test_active_style_has_both_underline_and_background(self):
        """Одного подчёркивания мало на графите, одного фона — при смене темы."""
        html = self.client.get('/catalog/').content.decode('utf-8')
        rule = html.split('.nav-link.is-active {', 1)[1].split('}', 1)[0]
        self.assertIn('border-bottom-color: var(--accent)', rule)
        self.assertIn('background: rgba(255, 255, 255, .12)', rule)


class VersionBadgeTests(TestCase):
    """Метка версии — на всех семи шаблонах, которые подключают шапку."""

    def setUp(self):
        self.users = {
            'student': User.objects.create_user(
                username='nav_ver_st', password=PASSWORD, role='student'),
            'teacher': User.objects.create_user(
                username='nav_ver_tu', password=PASSWORD, role='teacher'),
        }

    def test_version_on_every_template(self):
        for url, template, role in TEMPLATE_PAGES:
            self.client.force_login(self.users[role])
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200,
                             '%s (%s, %s)' % (url, template, role))
            html = response.content.decode('utf-8')
            # Ровно два: один в шапке, один в панели узкого экрана. Это одна
            # и та же метка в двух видах, а не две разные.
            self.assertEqual(html.count('beta 0.0'), 2,
                             '%s (%s)' % (url, template))

    def test_version_comes_from_settings(self):
        self.client.force_login(self.users['student'])
        with self.settings(SITE_VERSION='beta 9.9'):
            html = self.client.get('/catalog/').content.decode('utf-8')
        self.assertIn('beta 9.9', html)
        self.assertNotIn('beta 0.0', html)


class LogoutTests(TestCase):
    """Выход — POST. Прежняя GET-ссылка отдавала 405: это и была «ошибка»."""

    def setUp(self):
        self.user = User.objects.create_user(username='nav_out',
                                             password=PASSWORD, role='student')

    def test_post_logs_out_and_goes_home(self):
        self.client.force_login(self.user)
        response = self.client.post('/logout/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/')

    def test_get_is_405_and_that_is_normal(self):
        """Так решил Django 5. Чинить нечего — чинить надо было ссылку."""
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/logout/').status_code, 405)

    def test_header_shows_guest_buttons_after_logout(self):
        self.client.force_login(self.user)
        self.client.post('/logout/')
        html = self.client.get('/catalog/').content.decode('utf-8')
        self.assertIn('class="nav-login"', html)
        self.assertIn('Создать аккаунт', html)
        self.assertNotIn('class="nav-user"', html)

    def test_header_form_is_post_with_csrf(self):
        self.client.force_login(self.user)
        html = self.client.get('/catalog/').content.decode('utf-8')
        form = html.split('<form class="nav-logout"', 1)[1].split('</form>', 1)[0]
        self.assertIn('method="post"', form)
        self.assertIn('csrfmiddlewaretoken', form)


class ProfileChipTests(TestCase):
    """Плашка профиля: круг с инициалами и имя, всё — одна ссылка."""

    def test_initials_from_first_and_last_name(self):
        user = User.objects.create_user(username='nav_chip', password=PASSWORD,
                                        role='student', first_name='Иван',
                                        last_name='Петров')
        self.client.force_login(user)
        html = self.client.get('/catalog/').content.decode('utf-8')
        chip = html.split('<a class="nav-user"', 1)[1].split('</a>', 1)[0]
        self.assertIn('ИП', chip)
        self.assertIn('Иван Петров', chip)
        self.assertIn('href="/profile/"', html.split('<a class="nav-user"', 1)[0][-40:]
                      + '<a class="nav-user"' + chip)

    def test_initials_fall_back_to_username(self):
        user = User.objects.create_user(username='zebra', password=PASSWORD,
                                        role='student')
        self.client.force_login(user)
        html = self.client.get('/catalog/').content.decode('utf-8')
        chip = html.split('<a class="nav-user"', 1)[1].split('</a>', 1)[0]
        self.assertIn('Z', chip)


class NavMarkupTests(TestCase):
    """Разметка: инлайновых стилей почти не осталось."""

    def test_almost_no_inline_styles(self):
        """Было 32 атрибута `style`, договорились не больше трёх."""
        import io
        src = io.open('templates/_nav.html', encoding='utf-8').read()
        self.assertLessEqual(src.count('style="'), 3, 'инлайновые стили вернулись')

    def test_no_four_copies_of_the_row(self):
        """Ряд ссылок в разметке ровно один цикл на шапку и один на панель."""
        import io
        src = io.open('templates/_nav.html', encoding='utf-8').read()
        self.assertEqual(src.count('{% for item in nav_items %}'), 2)


class TextbookTests(TestCase):
    """Учебник — заглушка «Скоро», и ничего больше."""

    def test_page_opens_for_guest(self):
        response = self.client.get('/textbook/')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        self.assertIn('Скоро.', html)
        self.assertIn('Мы уже пишем.', html)

    def test_no_forms_or_buttons_on_the_stub(self):
        """Обещать на заглушке нечего: ни формы почты, ни кнопки."""
        html = self.client.get('/textbook/').content.decode('utf-8')
        body = html.split('<div class="tb">', 1)[1].split('</div>', 1)[0]
        self.assertNotIn('<form', body)
        self.assertNotIn('<button', body)
        self.assertNotIn('<input', body)


class ContentWidthTests(TestCase):
    """П10: 960 везде, 860 только на страницах чтения."""

    def test_tokens_are_actually_read(self):
        import io
        for path in ('catalog/templates/catalog/base.html',
                     'student/templates/student/base.html'):
            src = io.open(path, encoding='utf-8').read()
            self.assertIn('max-width: var(--w-page);', src, path)
            self.assertNotIn('max-width: 860px;', src, path)

    def test_reading_pages_narrow_themselves(self):
        import io
        for path in ('catalog/templates/catalog/problem_detail.html',
                     'student/templates/student/assignment_detail.html',
                     'student/templates/student/work_review.html',
                     'student/templates/student/submission_detail.html',
                     'student/templates/student/exam_take.html'):
            src = io.open(path, encoding='utf-8').read()
            self.assertIn('.page-wrap { max-width: var(--w-read); }', src, path)
