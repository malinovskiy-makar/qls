# -*- coding: utf-8 -*-
"""Фаза 1.3: задача, забракованная ПОСЛЕ сохранения, помечается.

Хвост сессии 3А. Вход уже закрыт: `api_save_problem` берёт задачу только
опубликованную и не зафлагованную, черновик к себе не положить. Осталось
второе — что делать с той, которую сохранили ВЧЕРА, а шлюз забраковал
СЕГОДНЯ.

**Решение владельца (сессия 3Б):** показывать, но с пометкой «снята с
публикации», и без ссылки на публичную страницу.

Почему не два очевидных варианта:

* *молча спрятать* — подборка ученика «худеет» без объяснения, и он решит,
  что потерял свою работу;
* *молча показать со ссылкой* — тогда шлюз качества не работает: ссылка
  ведёт на страницу, которой для этого ученика нет.
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from problems.models import Problem
from problems.models_platform import SavedProblem

User = get_user_model()

PASSWORD = 'proverka12345'

GOOD_TITLE = 'Хорошая задача про КПВ'
FLAGGED_TITLE = 'Забракованная задача про эластичность'


class SavedFlaggedProblemTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.student = User.objects.create_user('saved_pupil',
                                               password=PASSWORD,
                                               role='student')
        cls.good = Problem.objects.create(
            title=GOOD_TITLE, statement='Условие хорошей',
            status=Problem.Status.PUBLISHED, needs_quality_review=False)
        # Сохранена, КОГДА была в порядке; забракована после.
        cls.flagged = Problem.objects.create(
            title=FLAGGED_TITLE, statement='Условие забракованной',
            status=Problem.Status.PUBLISHED, needs_quality_review=False)
        SavedProblem.objects.create(owner=cls.student,
                                    catalog_problem=cls.good)
        SavedProblem.objects.create(owner=cls.student,
                                    catalog_problem=cls.flagged)
        cls.flagged.needs_quality_review = True
        cls.flagged.save(update_fields=['needs_quality_review'])

    def setUp(self):
        self.client = Client()
        self.assertTrue(
            self.client.login(username='saved_pupil', password=PASSWORD))
        self.body = self.client.get(
            reverse('profile') + '?tab=saved'
        ).content.decode('utf-8', 'replace')

    # ── что обещано владельцем ──────────────────────────────────────────
    def test_flagged_problem_stays_in_the_list(self):
        self.assertIn(
            FLAGGED_TITLE, self.body,
            'Забракованная задача исчезла из «Сохранённого» — подборка '
            'ученика «худеет» без объяснения.')

    def test_flagged_problem_is_marked(self):
        self.assertIn(
            'снята с публикации', self.body,
            'Задача показана без пометки — ученик не поймёт, почему по ней '
            'некуда нажать.')

    def test_flagged_problem_has_no_link_to_the_public_page(self):
        link = reverse('catalog:problem_detail', args=[self.flagged.pk])
        self.assertNotIn(
            'href="%s"' % link, self.body,
            'На забракованную задачу ведёт ссылка — шлюз качества не '
            'работает.')

    def test_the_public_page_really_is_closed(self):
        """Проверяем не только отсутствие ссылки, но и саму страницу.

        Иначе «ссылки нет» доказывало бы лишь аккуратность разметки.
        """
        response = self.client.get(
            reverse('catalog:problem_detail', args=[self.flagged.pk]))
        self.assertEqual(response.status_code, 404)

    # ── контроль: обычная задача не пострадала ──────────────────────────
    def test_good_problem_is_linked(self):
        link = reverse('catalog:problem_detail', args=[self.good.pk])
        self.assertIn(
            'href="%s"' % link, self.body,
            'У обычной задачи пропала ссылка — тогда пометка у соседней '
            'ничего не объясняет.')

    def test_good_problem_is_not_marked(self):
        # Пометка ровно одна — у забракованной.
        self.assertEqual(self.body.count('снята с публикации'), 1)

    def test_good_page_opens(self):
        response = self.client.get(
            reverse('catalog:problem_detail', args=[self.good.pk]))
        self.assertEqual(response.status_code, 200)
