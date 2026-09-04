# -*- coding: utf-8 -*-
"""Сколько запросов делает кабинет ученика (Фаза 8, 04.09.2026).

⚠️ СТОРОЖИТСЯ РОСТ, А НЕ ЧИСЛО. Точное число запросов меняется от любой
безобидной правки шаблона или контекстного процессора, и тест на точное
число краснел бы каждую неделю по ложному поводу. Настоящий дефект выглядит
иначе: добавили строку — прибавилось запросов. Поэтому замер идёт ДВАЖДЫ,
на разном объёме данных, и сравниваются разности.

⚠️ Блок «Мои работы» здесь НЕ сторожится и растёт по числу работ — это
известное и НЕ наше: `calc_assignment_stats` вызывается на каждую работу и
живёт в кабинете с самого его появления. Замер есть в журнале фазы,
карточка заведена. Трогать чужой цикл в сессии полировки нельзя.
"""
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from problems.models import StudentGroup, User

PASSWORD = 'dashq-probe-2026'


class GroupCardsQueryTests(TestCase):
    """Карточки занятий не должны стоить по запросу за штуку."""

    def setUp(self):
        self.teacher = User.objects.create_user(
            username='dashq_tu', password=PASSWORD, role='teacher')
        self.pupil = User.objects.create_user(
            username='dashq_st', password=PASSWORD, role='student')
        self.client.force_login(self.pupil)

    def _enroll(self, count):
        for number in range(count):
            group = StudentGroup.objects.create(
                name='Занятие %d' % number, teacher=self.teacher)
            group.students.add(self.pupil)

    def _queries_now(self):
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get('/student/')
            self.assertEqual(response.status_code, 200)
            # Ленивый queryset выполняется при отрисовке шаблона, а она уже
            # прошла: `render` отдаёт готовый ответ.
        return len(captured)

    def test_group_cards_do_not_cost_a_query_each(self):
        self._enroll(1)
        with_one = self._queries_now()
        self._enroll(9)          # стало десять
        with_ten = self._queries_now()

        # На девять занятий больше — а запросов столько же. Порог 2 оставлен
        # на служебный шум (сессия, пользователь), но не на девять карточек.
        self.assertLessEqual(
            with_ten - with_one, 2,
            'девять занятий добавили %d запросов: %d → %d'
            % (with_ten - with_one, with_one, with_ten))

    def test_teacher_name_and_work_count_come_with_the_group(self):
        """Имя учителя и счётчик работ — в том же запросе, что и занятие.

        Именно их печатает карточка; вытащи их отдельно — и получится по два
        лишних запроса на карточку. Считаются запросы к тем таблицам, откуда
        карточка берёт данные: пользователи (учитель) и работы (счётчик).

        ⚠️ Имена таблиц спрашиваются у моделей, а не пишутся строкой. Две
        предыдущие версии этого теста не проверяли НИЧЕГО именно из-за
        строк: первая искала `studentgroup` (и обращение к учителю, и
        `g.assignments.count()` идут к другим таблицам), вторая — `auth_user`
        (пользователь в проекте свой, таблица `problems_user`). Обе были
        зелёными при сломанном запросе.
        """
        from django.contrib.auth import get_user_model

        from problems.models import Assignment

        user_table = get_user_model()._meta.db_table.lower()
        work_table = Assignment._meta.db_table.lower()

        self._enroll(5)
        with CaptureQueriesContext(connection) as captured:
            self.client.get('/student/')
        texts = [q['sql'].lower() for q in captured.captured_queries]
        users = [s for s in texts if user_table in s]
        works = [s for s in texts if work_table in s]
        # Пять карточек — а запросов к пользователям и работам единицы:
        # столько же, сколько было бы при одной.
        self.assertLessEqual(
            len(users), 3,
            'при пяти карточках %d запросов к пользователям' % len(users))
        self.assertLessEqual(
            len(works), 4,
            'при пяти карточках %d запросов к работам' % len(works))
