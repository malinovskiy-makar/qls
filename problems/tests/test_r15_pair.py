# -*- coding: utf-8 -*-
"""Фаза 15 объединённого ревью 15.08: чужое занятие в адресе и сверка пар.

⚠️ ЧТО БЫЛО. Подстановка несуществующего занятия
(`/teacher/assignment/create/?group=13`) открывала экран создания как ни в
чём не бывало: крошка молча теряла имя (`group_label_param` отдаёт пустую
строку и ТЕМ САМЫМ МАСКИРУЕТ ошибку), работа собиралась, а переключатель
«Контрольная» уводил на `/teacher/groups/13/exams/new/` и выдавал страницу
Django «No StudentGroup matches the given query» — текст для разработчика,
через три шага после самой ошибки.

Теперь отказ приходит СРАЗУ и с возвратом на «Ученики», а прямой адрес
несуществующего занятия отдаёт 404 со своей разметкой (при DEBUG=True
Django по-прежнему показывает свою отладочную страницу — это его режим, а
не наша разметка).
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from problems.models import Assignment, StudentGroup

User = get_user_model()

# Экраны, принимающие занятие параметром `?group=`.
# ⚠️ СПИСОК ПЕРЕСЧИТАН (ревью 17.08, п. 4.5): прежние конструкторы удалены,
# занятие в адресе несут шаги потока. Требование прежнее — чужое и
# несуществующее занятие получает отказ, а не тихий экран.
GROUP_PARAM_SCREENS = [
    '/teacher/work/',
    '/teacher/work/compose/',
    '/teacher/work/give/',
    '/teacher/assignment/generate/',
    '/teacher/problems/new/',
]


class ForeignGroupParamTests(TestCase):
    """Чужое и несуществующее занятие в `?group=`."""

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('t15', password='x',
                                             role='teacher')
        cls.other = User.objects.create_user('t15x', password='x',
                                             role='teacher')
        cls.mine = StudentGroup.objects.create(name='Моё', teacher=cls.tutor)
        cls.alien = StudentGroup.objects.create(name='Чужое',
                                                teacher=cls.other)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.tutor)

    def test_missing_group_is_refused_with_a_way_back(self):
        for url in GROUP_PARAM_SCREENS:
            response = self.client.get(url, {'group': 999999})
            self.assertEqual(response.status_code, 302, url)
            self.assertEqual(response['Location'], '/teacher/groups/', url)

    def test_alien_group_is_refused_too(self):
        for url in GROUP_PARAM_SCREENS:
            response = self.client.get(url, {'group': self.alien.pk})
            self.assertEqual(response.status_code, 302, url)

    def test_refusal_explains_itself(self):
        response = self.client.get('/teacher/work/',
                                   {'group': 999999}, follow=True)
        self.assertContains(response, 'Такого занятия нет')

    def test_own_group_still_works(self):
        for url in GROUP_PARAM_SCREENS:
            response = self.client.get(url, {'group': self.mine.pk})
            self.assertEqual(response.status_code, 200, url)

    def test_no_group_at_all_is_legal(self):
        """Работу создают и без занятия — пустой параметр не ошибка."""
        for url in GROUP_PARAM_SCREENS:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_non_numeric_group_still_does_not_crash(self):
        """⚠️ `?group=abc` когда-то отвечал пятисоткой — правило остаётся."""
        for bad in ('abc', 'null', '1; drop', '-3'):
            response = self.client.get('/teacher/work/',
                                       {'group': bad})
            self.assertIn(response.status_code, (200, 302), bad)

    @override_settings(DEBUG=False)
    def test_direct_address_gives_our_own_page(self):
        response = self.client.get('/teacher/groups/999999/')
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, 'К ученикам', status_code=404)

    @override_settings(DEBUG=False)
    def test_exam_constructor_of_a_missing_group(self):
        """Тот самый адрес из разбора владельца."""
        response = self.client.get('/teacher/groups/999999/exams/new/')
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, 'Такой страницы нет', status_code=404)


class GroupAndSoloPairTests(TestCase):
    """Сверка: экран занятия у группы и у одного ученика — одно устройство.

    Законные различия (решение владельца, не трогаем): у индивидуального
    нет теплокарты и таблицы учеников, вместо них карточки-показатели и
    прогресс по темам; «Кому выдать» у контрольной выглядит иначе.
    """

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('t15p', password='x',
                                             role='teacher')
        cls.student = User.objects.create_user('s15p', password='x',
                                               role='student',
                                               first_name='Мария')
        cls.group = StudentGroup.objects.create(
            name='Группа', teacher=cls.tutor, kind='group')
        cls.solo = StudentGroup.objects.create(
            name='Мария Ким', teacher=cls.tutor, kind='individual')
        for lesson in (cls.group, cls.solo):
            lesson.students.add(cls.student)
            work = Assignment.objects.create(name='Работа %s' % lesson.pk,
                                             author=cls.tutor, group=lesson)
            work.students.add(cls.student)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.tutor)

    def tabs(self, lesson, tab=''):
        url = '/teacher/groups/%d/' % lesson.pk
        response = self.client.get(url, {'tab': tab} if tab else {})
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_both_have_the_same_three_tabs(self):
        for lesson in (self.group, self.solo):
            html = self.tabs(lesson)
            for name in ('Обзор', 'Задания', 'Материалы'):
                self.assertIn(name, html, '%s: %s' % (lesson.name, name))

    def test_both_tabs_open(self):
        for lesson in (self.group, self.solo):
            for tab in ('assignments', 'materials'):
                self.assertEqual(
                    self.client.get('/teacher/groups/%d/' % lesson.pk,
                                    {'tab': tab}).status_code, 200)

    def test_creation_paths_exist_for_both(self):
        for lesson in (self.group, self.solo):
            for url in GROUP_PARAM_SCREENS:
                self.assertEqual(
                    self.client.get(url, {'group': lesson.pk}).status_code,
                    200, '%s %s' % (lesson.name, url))

    def test_exam_constructor_exists_for_both(self):
        """⚠️ Конструктор контрольной жил внутри занятия и удалён: вид
        работы стал параметром потока (ревью 17.08, п. 4.5)."""
        for lesson in (self.group, self.solo):
            self.assertEqual(
                self.client.get('/teacher/work/?group=%d&kind=exam'
                                % lesson.pk).status_code, 200, lesson.name)

    def test_solo_screen_drops_the_group_only_blocks(self):
        """Законное различие: теплокарты и таблицы учеников у одного нет."""
        # ⚠️ Ищем РАЗМЕТКУ, а не имя класса: набор стилей вклеен в
        # страницу, и поиск по имени класса краснеет всегда. По проекту
        # наступали на это пять раз — режем страницу по `</style>`.
        solo = self.tabs(self.solo).split('</style>')[-1]
        group = self.tabs(self.group).split('</style>')[-1]
        # У одного вместо таблицы учеников — блок «Прогресс по темам»,
        # у группы его нет: там та же картина лежит в матрице «ученики ×
        # темы». Это законное различие, а не расхождение.
        self.assertIn('Прогресс по темам', solo)
        self.assertNotIn('Прогресс по темам', group)
        # Таблица учеников — только у группы.
        self.assertIn('id="students-table"', group)
        self.assertNotIn('id="students-table"', solo)
