"""
Одно хранилище собираемой работы, привязанное к занятию (ревью 16.08, ф. 2).

⚠️ ЧТО БЫЛО. Хранилищ жило ЧЕТЫРЕ сразу: `work_cart` (живой), `hw_cart` и
`exam_cart` (мёртвые, от версии с двумя корзинами) и ключ с ПУСТЫМ ИМЕНЕМ.
В пустой ключ уезжало подобранное по описанию: экран «Описать словами»
рисовал имя ключа из переменной контекста, которой вьюха туда не клала, —
`{{ cart_key }}` превращалось в пустую строку, а `setItem('', …)` это
законная запись. Конструктор читал соседний ключ и показывал ПРОШЛУЮ
корзину: экран непустой, чужие задачи, и понять, что подбор пропал, нельзя.

Отсюда две проверки этого файла: имя ключа собирает СЕРВЕР (пустым оно
стать не может), и на каждом экране создания оно одно и то же.
"""
from django.test import TestCase

from problems.models import StudentGroup, User
from teacher import picker


class StorageKeysTests(TestCase):
    """Имена хранилищ — чистая функция, её и спрашиваем."""

    def test_cart_key_carries_the_lesson(self):
        keys = picker.storage_keys(7)
        self.assertEqual(keys['cart'], 'work_cart:7')
        self.assertEqual(keys['order'], 'work_cart:7_order')
        self.assertEqual(keys['settings'], 'hw_settings:7')
        self.assertEqual(keys['manual'], 'hw_manual_order:7')

    def test_lessons_do_not_share_a_cart(self):
        """Собранное для группы не имеет права всплыть в индивидуальном."""
        self.assertNotEqual(picker.storage_keys(2)['cart'],
                            picker.storage_keys(4)['cart'])

    def test_no_lesson_is_zero_not_empty(self):
        """⚠️ Пустое имя ключа — это и есть чинимый дефект."""
        for value in (None, '', 0):
            keys = picker.storage_keys(value)
            self.assertEqual(keys['cart'], 'work_cart:0')
            for name in ('cart', 'order', 'settings', 'manual'):
                self.assertTrue(keys[name])

    def test_junk_list_names_the_empty_key(self):
        self.assertIn('', picker.JUNK_KEYS)
        self.assertIn('hw_cart', picker.JUNK_KEYS)
        self.assertIn('exam_cart', picker.JUNK_KEYS)

    def test_migration_moves_old_common_keys(self):
        """Общий ключ прошлой версии ПЕРЕЕЗЖАЕТ, а не стирается."""
        pairs = dict((a, b) for a, b in picker.storage_keys(3)['migrate'])
        self.assertEqual(pairs['work_cart'], 'work_cart:3')
        self.assertEqual(pairs['hw_settings'], 'hw_settings:3')


class CreateScreensTests(TestCase):
    """Все экраны создания говорят об одном и том же хранилище."""

    URLS = ('/teacher/assignment/create/',
            '/teacher/assignment/build/',
            '/teacher/assignment/generate/')

    @classmethod
    def setUpTestData(cls):
        cls.tutor = User.objects.create_user('cart_tutor', password='x',
                                             role='teacher')
        cls.group = StudentGroup.objects.create(name='Занятие корзины',
                                                teacher=cls.tutor)

    def setUp(self):
        self.client.force_login(self.tutor)

    def urls_with_group(self):
        return [u + '?group=%d' % self.group.pk for u in self.URLS] + [
            '/teacher/groups/%d/exams/new/' % self.group.pk]

    def test_every_screen_knows_the_lesson_cart(self):
        want = picker.storage_keys(self.group.pk)['cart']
        for url in self.urls_with_group():
            body = self.client.get(url).content.decode()
            self.assertIn(want, body, url)

    def test_no_screen_writes_an_unnamed_key(self):
        """⚠️ ГЛАВНАЯ ПРОВЕРКА ЭТОЙ ФАЗЫ.

        Имя ключа рисуется из контекста; если вьюха его не положила, в
        разметку попадёт `setItem('', …)`. Ищем ровно эту запись.
        """
        for url in self.urls_with_group() + list(self.URLS):
            body = self.client.get(url).content.decode()
            for call in ("setItem('',", 'setItem("",', "getItem('')",
                         'getItem("")'):
                self.assertNotIn(call, body, '%s: %s' % (url, call))

    def test_screens_clean_the_junk(self):
        """Мусорные ключи удаляются при загрузке любого экрана создания."""
        for url in self.urls_with_group():
            body = self.client.get(url).content.decode()
            self.assertIn("removeItem('hw_cart')", body, url)
            self.assertIn("removeItem('exam_cart')", body, url)
            self.assertIn("removeItem('')", body, url)

    def test_settings_are_tied_to_the_lesson_too(self):
        """Срок и название живут рядом с корзиной и чистятся вместе с ней."""
        want = picker.storage_keys(self.group.pk)['settings']
        body = self.client.get(
            '/teacher/assignment/create/?group=%d' % self.group.pk
        ).content.decode()
        self.assertIn(want, body)

    def test_key_name_is_never_hardcoded_in_screens(self):
        """Имя ключа не пишется в шаблонах руками — иначе они разъедутся."""
        for path in ('teacher/templates/teacher/_picker_js.html',
                     'teacher/templates/teacher/assignment_build.html',
                     'teacher/templates/teacher/generate.html',
                     'teacher/templates/teacher/_build_keep.html'):
            with open(path, encoding='utf-8') as fh:
                text = fh.read()
            self.assertNotIn("'work_cart'", text, path)
            self.assertNotIn("'hw_settings'", text, path)
