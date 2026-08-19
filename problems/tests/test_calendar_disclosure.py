# -*- coding: utf-8 -*-
"""Фаза 1.1: календарь не подтверждает существование чужого события.

Дыры здесь не было: право проверялось верно, чужое событие не правилось и
не удалялось. Неправильным было ДРУГОЕ — по коду ответа можно было
отличить «событие есть, но не ваше» от «события нет»:

    чужой существующий pk  -> 403 «Нет прав»
    несуществующий pk      -> 404

Перебором номеров так составляется список существующих событий. После
правки оба случая отвечают одинаково.

⚠️ **Этот файл появился потому, что без него правка была бы не проверена.**
В сессии 3А ровно так и вышло с `_own_assignment`: правка была, теста не
было, и вернувшаяся дыра никого не разбудила. Соседний
`test_access_boundaries` трогает `event_update`, но проверяет там другое —
привязку чужой работы.

⚠️ Номер заведомо отсутствующего события берётся как `max(pk) + 1000`, а
не константой: счётчики в PostgreSQL не откатываются транзакцией теста
(см. docs/TESTING.md).
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from problems.models import CalendarEvent

User = get_user_model()

PASSWORD = 'proverka12345'


class CalendarDisclosureTests(TestCase):
    """Чужое и несуществующее событие неотличимы по ответу."""

    @classmethod
    def setUpTestData(cls):
        cls.mine = User.objects.create_user('cal_mine', password=PASSWORD,
                                            role='teacher')
        cls.other = User.objects.create_user('cal_other', password=PASSWORD,
                                             role='teacher')
        now = timezone.now()
        cls.alien = CalendarEvent.objects.create(
            title='ЧУЖОЕ событие', author=cls.other, start_datetime=now)
        cls.own = CalendarEvent.objects.create(
            title='Моё событие', author=cls.mine, start_datetime=now)

    def setUp(self):
        self.client = Client()
        self.assertTrue(
            self.client.login(username='cal_mine', password=PASSWORD))

    @property
    def missing_pk(self):
        return CalendarEvent.objects.order_by('-pk').first().pk + 1000

    def _update(self, pk):
        return self.client.post(
            reverse('calendar_stub:event_update', args=[pk]),
            data='{"title": "Переименовано"}',
            content_type='application/json')

    def _delete(self, pk):
        return self.client.post(
            reverse('calendar_stub:event_delete', args=[pk]),
            data='{}', content_type='application/json')

    def _detail(self, pk):
        return self.client.get(
            reverse('calendar_stub:event_detail', args=[pk]))

    # ── правка ──────────────────────────────────────────────────────────
    def test_update_of_a_foreign_event_is_404(self):
        response = self._update(self.alien.pk)
        self.assertEqual(
            response.status_code, 404,
            'Чужое событие отвечает не так, как несуществующее — перебором '
            'номеров составляется список существующих событий.')

    def test_update_of_a_missing_event_is_404_too(self):
        self.assertEqual(self._update(self.missing_pk).status_code, 404)

    def test_both_answers_are_byte_for_byte_equal(self):
        """Разница должна отсутствовать не «по смыслу», а физически."""
        foreign = self._update(self.alien.pk)
        missing = self._update(self.missing_pk)
        self.assertEqual(foreign.status_code, missing.status_code)
        self.assertEqual(foreign.content, missing.content)

    def test_foreign_event_is_not_changed(self):
        """Код ответа — половина дела; в базе тоже ничего не поменялось."""
        self._update(self.alien.pk)
        self.alien.refresh_from_db()
        self.assertEqual(self.alien.title, 'ЧУЖОЕ событие')

    def test_answer_does_not_carry_the_title(self):
        """404 с названием чужого события в теле — всё ещё утечка."""
        body = self._update(self.alien.pk).content.decode('utf-8', 'replace')
        self.assertNotIn('ЧУЖОЕ', body)

    # ── удаление ────────────────────────────────────────────────────────
    def test_delete_of_a_foreign_event_is_404(self):
        self.assertEqual(self._delete(self.alien.pk).status_code, 404)
        self.assertTrue(
            CalendarEvent.objects.filter(pk=self.alien.pk).exists(),
            'чужое событие удалено — это уже дыра, а не разглашение')

    def test_delete_of_a_missing_event_is_404_too(self):
        self.assertEqual(self._delete(self.missing_pk).status_code, 404)

    # ── просмотр ────────────────────────────────────────────────────────
    def test_detail_of_an_invisible_event_is_404(self):
        """У просмотра своё правило: не «автор», а «видно»."""
        self.assertEqual(self._detail(self.alien.pk).status_code, 404)

    def test_detail_of_a_missing_event_is_404_too(self):
        self.assertEqual(self._detail(self.missing_pk).status_code, 404)

    # ── ответ остаётся JSON ─────────────────────────────────────────────
    def test_refusal_is_json_not_a_django_page(self):
        """Экран календаря разбирает ТЕЛО ответа, а не код.

        Скрипт делает `r.json()` и смотрит `d.status`. Отдай мы здесь
        страницу Django «не найдено», разбор упал бы, и человек увидел бы
        не сообщение, а ничего.
        """
        response = self._update(self.alien.pk)
        self.assertEqual(response.headers['Content-Type'], 'application/json')
        self.assertIn('error', response.json())

    # ── контроль ────────────────────────────────────────────────────────
    def test_own_event_still_updates(self):
        """Иначе «починку» можно сделать запретом всего."""
        response = self._update(self.own.pk)
        self.assertEqual(response.status_code, 200)
        self.own.refresh_from_db()
        self.assertEqual(self.own.title, 'Переименовано')

    def test_own_event_is_visible(self):
        self.assertEqual(self._detail(self.own.pk).status_code, 200)
