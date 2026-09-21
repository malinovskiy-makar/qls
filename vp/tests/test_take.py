"""Прохождение варианта: старт, доступ к попытке, автосохранение, время, сдача.

Нумерация `test_NN_…` — сценарии из задания сессии 2; остальные тесты — рядом.
Время двигается через `at(...)` (патч `django.utils.timezone.now`), пауз нет.
"""
import json
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal as D
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import Client, TestCase
from django.urls import reverse

from problems import exam_engine
from vp import scoring, views
from vp.models import VPAnswer, VPAttempt
from vp.tests.helpers import at, make_published

User = get_user_model()

T0 = datetime(2026, 9, 26, 10, 0, 0, tzinfo=dt_timezone.utc)


class ViewBase(TestCase):
    def setUp(self):
        self.variant = make_published()
        self.guest = Client()
        self.stranger = Client()

    def start(self, client=None, **post):
        client = client or self.guest
        response = client.post(reverse('vp:start', args=[self.variant.slug]), post)
        self.assertEqual(response.status_code, 302, response.content[:300])
        return VPAttempt.objects.order_by('-id').first(), response

    def take_url(self, attempt):
        return reverse('vp:take', args=[attempt.public_code])


class StartTests(ViewBase):
    def test_01_timed_start_expires_exactly_after_the_duration(self):
        with at(T0):
            attempt, response = self.start(with_timer='1')
        self.assertEqual((attempt.expires_at - attempt.started_at).total_seconds(), 1800)
        self.assertRedirects(response, self.take_url(attempt), fetch_redirect_response=False)
        self.assertTrue(attempt.with_timer)

    def test_02_untimed_start_has_no_deadline(self):
        attempt, _ = self.start(with_timer='0')
        self.assertFalse(attempt.with_timer)
        self.assertIsNone(attempt.expires_at)

    def test_03_second_start_returns_to_the_same_attempt(self):
        first, _ = self.start(with_timer='1')
        again, response = self.start(with_timer='0')
        self.assertEqual(first.pk, again.pk)
        self.assertEqual(VPAttempt.objects.count(), 1)
        self.assertRedirects(response, self.take_url(first), fetch_redirect_response=False)
        self.assertTrue(again.with_timer)          # режим уже начатой попытки не меняется

    def test_04_foreign_code_is_404_on_take(self):
        attempt, _ = self.start()
        self.assertEqual(self.stranger.get(self.take_url(attempt)).status_code, 404)
        self.assertEqual(Client().get(self.take_url(attempt)).status_code, 404)
        other = User.objects.create_user('vp_other', password='p12345')
        client = Client()
        client.force_login(other)
        self.assertEqual(client.get(self.take_url(attempt)).status_code, 404)

    def test_owner_opens_the_page(self):
        attempt, _ = self.start()
        response = self.guest.get(self.take_url(attempt))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'noindex')

    def test_unknown_code_is_404(self):
        self.assertEqual(self.guest.get(reverse('vp:take', args=['net-takoi'])).status_code, 404)

    def test_default_is_with_timer_and_zero_is_without(self):
        attempt, _ = self.start()
        self.assertTrue(attempt.with_timer)
        other = Client()
        attempt, _ = self.start(other, with_timer='0')
        self.assertFalse(attempt.with_timer)

    def test_get_start_is_not_allowed(self):
        self.assertEqual(self.guest.get(reverse('vp:start', args=['vp-t'])).status_code, 405)

    def test_start_requires_csrf(self):
        strict = Client(enforce_csrf_checks=True)
        response = strict.post(reverse('vp:start', args=['vp-t']), {'with_timer': '1'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(VPAttempt.objects.count(), 0)

    def test_variant_without_items_cannot_be_started(self):
        self.variant.items.all().delete()
        response = self.guest.post(reverse('vp:start', args=['vp-t']), {'with_timer': '1'})
        self.assertEqual(response.status_code, 404)

    def test_draft_variant_is_closed_to_public_but_open_to_staff(self):
        self.variant.is_published = False
        self.variant.save()
        self.assertEqual(self.guest.get(reverse('vp:intro', args=['vp-t'])).status_code, 404)
        self.assertEqual(self.guest.post(reverse('vp:start', args=['vp-t'])).status_code, 404)
        self.assertNotContains(self.guest.get(reverse('vp:index')), 'Тестовый вариант')
        staff = User.objects.create_user('vp_staff', password='p12345', is_staff=True)
        client = Client()
        client.force_login(staff)
        self.assertEqual(client.get(reverse('vp:intro', args=['vp-t'])).status_code, 200)
        self.assertContains(client.get(reverse('vp:index')), 'Не опубликован')


class OwnerTests(ViewBase):
    def test_guest_gets_a_session_and_the_code_is_remembered(self):
        attempt, _ = self.start()
        self.assertEqual(len(attempt.public_code), 12)
        self.assertIsNone(attempt.user)
        self.assertTrue(attempt.session_key)
        self.assertEqual(attempt.session_key, self.guest.session.session_key)
        self.assertEqual(self.guest.session['vp_attempts'], [attempt.public_code])

    def test_logged_in_user_owns_by_user(self):
        user = User.objects.create_user('vp_u', password='p12345')
        client = Client()
        client.force_login(user)
        attempt, _ = self.start(client)
        self.assertEqual(attempt.user, user)
        self.assertEqual(attempt.session_key, '')
        self.assertEqual(client.get(self.take_url(attempt)).status_code, 200)

    def test_user_attempt_is_closed_after_logout(self):
        user = User.objects.create_user('vp_u2', password='p12345')
        client = Client()
        client.force_login(user)
        attempt, _ = self.start(client)
        client.logout()
        self.assertEqual(client.get(self.take_url(attempt)).status_code, 404)

    def test_guest_attempt_survives_login(self):
        """Ключ сессии при входе меняется, а код в данных сессии остаётся."""
        attempt, _ = self.start()
        user = User.objects.create_user('vp_late', password='p12345')
        self.assertTrue(self.guest.login(username='vp_late', password='p12345'))
        self.assertEqual(self.guest.get(self.take_url(attempt)).status_code, 200)

    def test_same_session_key_opens_a_guest_attempt_even_without_the_list(self):
        attempt, _ = self.start()
        session = self.guest.session
        session['vp_attempts'] = []
        session.save()
        self.assertEqual(self.guest.get(self.take_url(attempt)).status_code, 200)

    def test_list_in_session_opens_a_guest_attempt_after_key_rotation(self):
        attempt, _ = self.start()
        VPAttempt.objects.filter(pk=attempt.pk).update(session_key='другой-ключ')
        self.assertEqual(self.guest.get(self.take_url(attempt)).status_code, 200)

    def test_two_guests_do_not_share_attempts(self):
        mine, _ = self.start(self.guest)
        theirs, _ = self.start(self.stranger)
        self.assertNotEqual(mine.pk, theirs.pk)
        self.assertEqual(self.guest.get(self.take_url(theirs)).status_code, 404)
        self.assertEqual(self.stranger.get(self.take_url(mine)).status_code, 404)

    def test_session_remembers_only_the_last_fifty_codes(self):
        request = SimpleNamespace(session={})
        for number in range(60):
            views._remember(request, f'code-{number}')
        codes = request.session['vp_attempts']
        self.assertEqual(len(codes), 50)
        self.assertEqual(codes[0], 'code-10')
        self.assertEqual(codes[-1], 'code-59')
        views._remember(request, 'code-30')          # повтор не плодит дубль, а уходит в конец
        self.assertEqual(request.session['vp_attempts'].count('code-30'), 1)
        self.assertEqual(request.session['vp_attempts'][-1], 'code-30')

    def test_public_codes_are_twelve_chars_and_distinct(self):
        codes = {views._new_code() for _ in range(50)}
        self.assertTrue(all(len(c) == 12 for c in codes))
        self.assertGreater(len(codes), 45)


class IntroTests(ViewBase):
    def test_intro_numbers_come_from_the_database(self):
        html = self.guest.get(reverse('vp:intro', args=['vp-t'])).content.decode()
        for expected in ('1–30', 'Змейка, короткий ответ', '60 б.', '31–35', '10 б.',
                         '36–40', '15 б.', '41–42', '6 б.', '43–44', '9 б.'):
            self.assertIn(expected, html)
        self.assertIn('44 задания', html)
        self.assertIn('100 баллов', html)
        self.assertIn('30:00', html)
        # Меняем данные — страница следует за ними, а не за шаблоном.
        item = self.variant.items.get(number=1)
        item.points = D('3')
        item.save()
        other = self.variant.items.get(number=44)
        other.points = D('9')
        other.save()
        html = self.guest.get(reverse('vp:intro', args=['vp-t'])).content.decode()
        self.assertIn('61 б.', html)
        self.assertIn('13 б.', html)

    def test_rules_ranges_and_penalty_example_follow_the_data(self):
        html = self.guest.get(reverse('vp:intro', args=['vp-t'])).content.decode()
        self.assertIn('Задания 1–35 и 43–44 — или полный балл, или ноль.', html)
        self.assertIn('В заданиях 36–42 балл делится', html)
        self.assertIn('верный даёт +1,5, лишний — −1', html)     # для трёхбалльных
        for item in self.variant.items.filter(block__in=('multi', 'analytic')):
            item.points = D('6')
            item.save()
        html = self.guest.get(reverse('vp:intro', args=['vp-t'])).content.decode()
        self.assertIn('верный даёт +3, лишний — −2', html)

    def test_intro_shows_the_chain_example_and_mode_choice(self):
        html = self.guest.get(reverse('vp:intro', args=['vp-t'])).content.decode()
        self.assertIn('Что такое змейка', html)
        self.assertIn('ликвидность', html)
        self.assertRegex(html, r'name="with_timer" value="1" checked')
        self.assertRegex(html, r'name="with_timer" value="0"')
        self.assertIn('С таймером — 30 минут', html)
        self.assertIn('Начать вариант', html)

    def test_intro_with_unfinished_attempt_offers_to_continue(self):
        attempt, _ = self.start()
        html = self.guest.get(reverse('vp:intro', args=['vp-t'])).content.decode()
        self.assertIn('У вас есть начатая работа: отвечено 0 из 44', html)
        self.assertIn('Продолжить вариант', html)
        self.assertNotIn('name="with_timer"', html)
        # Чужому браузеру начатая работа не видна.
        html = self.stranger.get(reverse('vp:intro', args=['vp-t'])).content.decode()
        self.assertNotIn('начатая работа', html)
        self.assertIn('Начать вариант', html)

    def test_unknown_variant_is_404(self):
        self.assertEqual(self.guest.get(reverse('vp:intro', args=['net-takogo'])).status_code, 404)

    def test_index_lists_published_variants_by_band(self):
        eleven = make_published('vp-eleven')
        eleven.grade_band = '11'
        eleven.title = 'Вариант для 11 класса'
        eleven.save()
        html = self.guest.get(reverse('vp:index')).content.decode()
        self.assertIn('9–10 классы', html)
        self.assertIn('11 класс', html)
        self.assertIn(reverse('vp:intro', args=['vp-t']), html)
        self.assertIn(reverse('vp:intro', args=['vp-eleven']), html)

    def test_empty_index_is_honest(self):
        self.variant.is_published = False
        self.variant.save()
        self.assertContains(self.guest.get(reverse('vp:index')), 'Варианты появятся здесь')


class PenaltyExampleTests(TestCase):
    """Пример на входе считает scoring и совпадает с настоящим подсчётом баллов."""

    def test_example_matches_score_item(self):
        from vp.scoring import penalty_example, score_item
        from vp.tests.test_scoring import multi
        for points in ('3', '6', '2.5'):
            per_right, per_wrong = penalty_example(D(points))
            item = multi([1, 2], points=points)              # 2 верных, 3 неверных
            self.assertEqual(score_item(item, [1])[0], per_right)
            self.assertEqual(score_item(item, [1, 2, 3])[0], D(points) - per_wrong)


class SaveTests(ViewBase):
    def save_url(self, attempt):
        return reverse('vp:save', args=[attempt.public_code])

    def post(self, client, attempt, answers, **extra):
        return client.post(self.save_url(attempt), json.dumps({'answers': answers}),
                           content_type='application/json', **extra)

    def rows(self, attempt):
        return {a.item.number: a for a in attempt.answers.select_related('item')}

    def test_05_save_writes_raw_and_a_repeat_updates_the_row(self):
        attempt, _ = self.start()
        self.assertEqual(self.post(self.guest, attempt, [{'item': 1, 'raw': 'первый'}]).status_code, 200)
        self.post(self.guest, attempt, [{'item': 1, 'raw': 'второй'}])
        rows = self.rows(attempt)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[1].raw, 'второй')
        self.assertEqual(VPAnswer.objects.filter(attempt=attempt).count(), 1)

    def test_twelve_fields_make_twelve_rows_with_raw_and_no_score(self):
        attempt, _ = self.start()
        batch = [{'item': n, 'raw': f'ответ {n}'} for n in range(1, 13)]
        response = self.post(self.guest, attempt, batch)
        self.assertEqual(response.json()['saved'], 12)
        rows = VPAnswer.objects.filter(attempt=attempt)
        self.assertEqual(rows.count(), 12)
        self.assertEqual(rows.exclude(raw__isnull=True).count(), 12)
        self.assertEqual(rows.filter(score__isnull=True, max_score__isnull=True,
                                     is_correct__isnull=True).count(), 12)

    def test_response_shape_is_saved_and_seconds_remaining(self):
        with at(T0):
            attempt, _ = self.start(with_timer='1')
        with at(T0 + timedelta(seconds=100)):
            body = self.post(self.guest, attempt, [{'item': 1, 'raw': 'x'}]).json()
        self.assertEqual(body, {'saved': 1, 'seconds_remaining': 1700})

    def test_untimed_response_has_null_seconds(self):
        attempt, _ = self.start(with_timer='0')
        body = self.post(self.guest, attempt, [{'item': 1, 'raw': 'x'}]).json()
        self.assertEqual(body, {'saved': 1, 'seconds_remaining': None})

    def test_every_kind_is_saved_as_its_own_shape(self):
        attempt, _ = self.start()
        item = self.variant.items.get(number=44)
        item.kind, item.options, item.correct = 'match', [{'n': 1, 'text': 'а'}, {'n': 2, 'text': 'б'}], {'к1': 2, 'к2': 1}
        item.save()
        batch = [{'item': 1, 'raw': '  картель '}, {'item': 31, 'raw': 2},
                 {'item': 36, 'raw': [3, 1, 3]}, {'item': 44, 'raw': {'к1': 2, 'к2': ''}}]
        self.assertEqual(self.post(self.guest, attempt, batch).status_code, 200)
        raws = {n: a.raw for n, a in self.rows(attempt).items()}
        self.assertEqual(raws, {1: 'картель', 31: 2, 36: [1, 3], 44: {'к1': 2}})

    def test_clearing_an_answer_keeps_the_row_with_null(self):
        attempt, _ = self.start()
        self.post(self.guest, attempt, [{'item': 1, 'raw': 'x'}, {'item': 36, 'raw': [1]}])
        self.post(self.guest, attempt, [{'item': 1, 'raw': ''}, {'item': 36, 'raw': []}])
        rows = self.rows(attempt)
        self.assertIsNone(rows[1].raw)
        self.assertIsNone(rows[36].raw)
        self.assertEqual(len(rows), 2)

    def test_repeated_item_in_one_batch_last_one_wins(self):
        attempt, _ = self.start()
        self.post(self.guest, attempt, [{'item': 1, 'raw': 'старый'}, {'item': 1, 'raw': 'новый'}])
        self.assertEqual(self.rows(attempt)[1].raw, 'новый')

    def test_reload_shows_what_was_saved(self):
        attempt, _ = self.start()
        self.post(self.guest, attempt, [{'item': 1, 'raw': 'мой ответ'}, {'item': 31, 'raw': 3},
                                        {'item': 36, 'raw': [1, 4]}])
        html = self.guest.get(self.take_url(attempt)).content.decode()
        self.assertIn('value="мой ответ"', html)
        self.assertRegex(html, r'name="item-31" value="3" checked')
        self.assertRegex(html, r'name="item-36" value="4" checked')
        self.assertRegex(html, r'отвечено <b id="vp-answered">3</b> из 44')

    def test_04b_foreign_code_is_404_on_save_and_saves_nothing(self):
        attempt, _ = self.start()
        other = User.objects.create_user('vp_o', password='p12345')
        logged = Client()
        logged.force_login(other)
        for client in (self.stranger, Client(), logged):
            response = self.post(client, attempt, [{'item': 1, 'raw': 'подмена'}])
            self.assertEqual(response.status_code, 404)
        self.assertEqual(VPAnswer.objects.filter(attempt=attempt).count(), 0)

    def test_a_bad_entry_rejects_the_whole_batch(self):
        attempt, _ = self.start()
        cases = [
            [{'item': 1, 'raw': 'ок'}, {'item': 99, 'raw': 'x'}],           # нет такого задания
            [{'item': 1, 'raw': 'ок'}, {'item': 31, 'raw': 9}],             # нет такого варианта
            [{'item': 1, 'raw': 'ок'}, {'item': 36, 'raw': [1, 8]}],
            [{'item': 1, 'raw': 'ок'}, {'item': 2, 'raw': 'я' * 201}],      # длиннее предела
            [{'item': 1, 'raw': 'ок'}, {'raw': 'нет номера'}],
            [{'item': 1, 'raw': 'ок'}, {'item': True, 'raw': 'x'}],
            [{'item': 1, 'raw': 'ок'}, 'не словарь'],
        ]
        for batch in cases:
            self.assertEqual(self.post(self.guest, attempt, batch).status_code, 400, batch)
        self.assertEqual(VPAnswer.objects.filter(attempt=attempt).count(), 0)

    def test_malformed_bodies_are_400(self):
        attempt, _ = self.start()
        url = self.save_url(attempt)
        for body in ('не json', '[]', '{"answers": "нет"}', '{}', '{"answers": %s}' % json.dumps([{'item': 1, 'raw': 'x'}] * 101)):
            response = self.guest.post(url, body, content_type='application/json')
            self.assertEqual(response.status_code, 400, body[:30])

    def test_oversized_body_is_rejected(self):
        attempt, _ = self.start()
        body = json.dumps({'answers': [{'item': 1, 'raw': 'x' * 30000}]})
        response = self.guest.post(self.save_url(attempt), body, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(VPAnswer.objects.filter(attempt=attempt).count(), 0)

    def test_csrf_is_enforced_for_json(self):
        attempt, _ = self.start()
        strict = Client(enforce_csrf_checks=True)
        strict.cookies = self.guest.cookies
        response = self.post(strict, attempt, [{'item': 1, 'raw': 'x'}])
        self.assertEqual(response.status_code, 403)
        self.assertEqual(VPAnswer.objects.filter(attempt=attempt).count(), 0)

    def test_beacon_form_with_token_and_payload_is_accepted(self):
        """sendBeacon не ставит заголовки: токен и пачка едут полями формы."""
        attempt, _ = self.start()
        strict = Client(enforce_csrf_checks=True)
        strict.cookies = self.guest.cookies
        token = strict.get(self.take_url(attempt)).cookies['csrftoken'].value
        payload = json.dumps({'answers': [{'item': 3, 'raw': 'по маяку'}]})
        response = strict.post(self.save_url(attempt),
                               {'csrfmiddlewaretoken': token, 'payload': payload})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.rows(attempt)[3].raw, 'по маяку')
        response = strict.post(self.save_url(attempt),
                               {'csrfmiddlewaretoken': 'чужой', 'payload': payload})
        self.assertEqual(response.status_code, 403)

    def test_get_is_not_allowed(self):
        attempt, _ = self.start()
        self.assertEqual(self.guest.get(self.save_url(attempt)).status_code, 405)

    def test_saving_into_a_submitted_attempt_is_409(self):
        attempt, _ = self.start()
        VPAttempt.objects.filter(pk=attempt.pk).update(submitted_at=T0)
        response = self.post(self.guest, attempt, [{'item': 1, 'raw': 'поздно'}])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(VPAnswer.objects.filter(attempt=attempt).count(), 0)

    def test_racing_insert_falls_back_to_update(self):
        """Второй INSERT об уникальность (attempt, item) не должен стать 500."""
        attempt, _ = self.start()
        item = self.variant.items.get(number=1)
        VPAnswer.objects.create(attempt=attempt, item=item, raw='чужой')
        with mock.patch.object(VPAnswer.objects, 'update_or_create',
                               side_effect=IntegrityError('dup')):
            response = self.post(self.guest, attempt, [{'item': 1, 'raw': 'мой'}])
        self.assertEqual(response.status_code, 200)
        self.assertEqual([a.raw for a in VPAnswer.objects.filter(attempt=attempt, item=item)], ['мой'])

    def test_a_server_failure_is_reported_as_retry_never_as_500(self):
        attempt, _ = self.start()
        with mock.patch('vp.answers.save_answers', side_effect=RuntimeError('boom')):
            response = self.post(self.guest, attempt, [{'item': 1, 'raw': 'x'}])
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['retry'])
        self.assertNotIn('saved', response.json())


def all_correct_batch(variant):
    """Пачка автосохранения со ВСЕМИ верными ответами варианта."""
    batch = []
    for item in variant.items.all():
        if item.kind == 'short_text':
            raw = item.answer
        elif item.kind == 'single':
            raw = item.correct[0]
        else:
            raw = item.correct
        batch.append({'item': item.number, 'raw': raw})
    return batch


class TimeAndFinishBase(ViewBase):
    def post_save(self, client, attempt, answers):
        return client.post(reverse('vp:save', args=[attempt.public_code]),
                           json.dumps({'answers': answers}), content_type='application/json')

    def finish(self, client, attempt, **fields):
        return client.post(reverse('vp:finish', args=[attempt.public_code]), fields)

    def time(self, client, attempt):
        return client.get(reverse('vp:time', args=[attempt.public_code]))

    def result_url(self, attempt):
        return reverse('vp:result', args=[attempt.public_code])

    def started(self, **post):
        with at(T0):
            attempt, _ = self.start(**post)
        return attempt


class ExpiryTests(TimeAndFinishBase):
    def test_06_save_after_expiry_is_409_and_the_attempt_is_auto_submitted(self):
        attempt = self.started(with_timer='1')
        with at(T0 + timedelta(seconds=100)):
            self.post_save(self.guest, attempt, [{'item': 1, 'raw': 'термин 1'}])
        with at(T0 + timedelta(seconds=1800 + 60)):
            response = self.post_save(self.guest, attempt, [{'item': 2, 'raw': 'термин 2'}])
        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.json()['expired'])
        attempt.refresh_from_db()
        self.assertIsNotNone(attempt.submitted_at)
        self.assertTrue(attempt.is_auto_submitted)
        self.assertEqual(attempt.submitted_at, attempt.expires_at)
        self.assertEqual(attempt.score, D('2.00'))               # то, что успело сохраниться
        self.assertIsNone(attempt.answers.get(item__number=2).raw)   # поздний ответ не принят

    def test_every_request_finalizes_an_expired_attempt(self):
        late = T0 + timedelta(seconds=1800 + 60)
        for name in ('take', 'save', 'time', 'finish', 'result'):
            with self.subTest(name):
                self.guest = Client()
                attempt = self.started(with_timer='1')
                url = reverse(f'vp:{name}', args=[attempt.public_code])
                with at(late):
                    if name in ('save', 'finish'):
                        self.guest.post(url, json.dumps({'answers': []}), content_type='application/json')
                    else:
                        self.guest.get(url)
                attempt.refresh_from_db()
                if name == 'result':
                    # Результат сам не закрывает: несданную владельца он ведёт к заданиям.
                    self.assertIsNone(attempt.submitted_at)
                else:
                    self.assertTrue(attempt.is_auto_submitted, name)
                    self.assertEqual(attempt.submitted_at, attempt.expires_at)

    def test_grace_window_still_accepts_the_last_answers(self):
        attempt = self.started(with_timer='1')
        inside = T0 + timedelta(seconds=1800 + exam_engine.GRACE_SECONDS - 2)
        with at(inside):
            response = self.post_save(self.guest, attempt, [{'item': 1, 'raw': 'термин 1'}])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['seconds_remaining'], 0)
        attempt.refresh_from_db()
        self.assertIsNone(attempt.submitted_at)

    def test_time_inside_grace_says_expired_without_closing(self):
        attempt = self.started(with_timer='1')
        with at(T0 + timedelta(seconds=1801)):
            body = self.time(self.guest, attempt).json()
        self.assertEqual(body, {'expired': True, 'seconds_remaining': 0})
        attempt.refresh_from_db()
        self.assertIsNone(attempt.submitted_at)

    def test_start_closes_a_lapsed_attempt_and_makes_a_new_one(self):
        old = self.started(with_timer='1')
        with at(T0 + timedelta(hours=2)):
            html = self.guest.get(reverse('vp:intro', args=['vp-t'])).content.decode()
            self.assertNotIn('начатая работа', html)
            new, _ = self.start(with_timer='1')
        old.refresh_from_db()
        self.assertTrue(old.is_auto_submitted)
        self.assertNotEqual(old.pk, new.pk)

    def test_untimed_attempt_never_lapses(self):
        attempt = self.started(with_timer='0')
        with at(T0 + timedelta(days=30)):
            self.assertEqual(self.post_save(self.guest, attempt, [{'item': 1, 'raw': 'x'}]).status_code, 200)
            self.assertEqual(self.guest.get(self.take_url(attempt)).status_code, 200)
        attempt.refresh_from_db()
        self.assertIsNone(attempt.submitted_at)


class TimeLeftTests(TimeAndFinishBase):
    def test_10_time_left_decreases_between_calls(self):
        attempt = self.started(with_timer='1')
        with at(T0 + timedelta(seconds=10)):
            first = self.time(self.guest, attempt).json()
        with at(T0 + timedelta(seconds=70)):
            second = self.time(self.guest, attempt).json()
        self.assertEqual(first, {'expired': False, 'seconds_remaining': 1790})
        self.assertEqual(second, {'expired': False, 'seconds_remaining': 1730})

    def test_02b_untimed_time_answers_null(self):
        attempt = self.started(with_timer='0')
        self.assertEqual(self.time(self.guest, attempt).json(),
                         {'expired': False, 'seconds_remaining': None})

    def test_time_never_exceeds_what_was_granted(self):
        """Часы «перевели назад»: остаток не больше выданных 1800 секунд."""
        attempt = self.started(with_timer='1')
        with at(T0 - timedelta(minutes=10)):
            self.assertEqual(self.time(self.guest, attempt).json()['seconds_remaining'], 1800)

    def test_submitted_attempt_reports_expired(self):
        attempt = self.started(with_timer='1')
        with at(T0 + timedelta(seconds=30)):
            self.finish(self.guest, attempt)
            self.assertEqual(self.time(self.guest, attempt).json(),
                             {'expired': True, 'seconds_remaining': 0})

    def test_time_is_404_for_a_stranger_and_post_is_not_allowed(self):
        attempt = self.started(with_timer='1')
        self.assertEqual(self.time(self.stranger, attempt).status_code, 404)
        response = self.guest.post(reverse('vp:time', args=[attempt.public_code]))
        self.assertEqual(response.status_code, 405)


class FinishTests(TimeAndFinishBase):
    def test_07_all_correct_answers_give_exactly_one_hundred(self):
        attempt = self.started(with_timer='1')
        with at(T0 + timedelta(seconds=60)):
            self.assertEqual(self.post_save(self.guest, attempt, all_correct_batch(self.variant)).status_code, 200)
        with at(T0 + timedelta(seconds=120)):
            response = self.finish(self.guest, attempt)
        self.assertRedirects(response, self.result_url(attempt), fetch_redirect_response=False)
        attempt.refresh_from_db()
        self.assertEqual(attempt.score, D('100.00'))
        self.assertEqual(attempt.max_score, D('100'))
        self.assertFalse(attempt.is_auto_submitted)
        self.assertEqual(attempt.submitted_at, T0 + timedelta(seconds=120))
        self.assertEqual(attempt.answers.count(), 44)
        self.assertTrue(all(a.is_correct is True for a in attempt.answers.all()))

    def test_08_a_second_finish_changes_neither_score_nor_time(self):
        attempt = self.started(with_timer='1')
        with at(T0 + timedelta(seconds=60)):
            self.post_save(self.guest, attempt, all_correct_batch(self.variant))
        with at(T0 + timedelta(seconds=120)):
            self.finish(self.guest, attempt)
        attempt.refresh_from_db()
        first = (attempt.score, attempt.submitted_at, attempt.is_auto_submitted)
        # Ответ «испортили» в базе и подождали: пересчёт был бы виден.
        VPAnswer.objects.filter(attempt=attempt, item__number=1).update(raw='испорчено')
        with at(T0 + timedelta(seconds=500)):
            response = self.finish(self.guest, attempt, **{'item-1': 'подмена', 'auto': '1'})
        self.assertRedirects(response, self.result_url(attempt), fetch_redirect_response=False)
        attempt.refresh_from_db()
        self.assertEqual((attempt.score, attempt.submitted_at, attempt.is_auto_submitted), first)
        self.assertEqual(attempt.score, D('100.00'))
        self.assertEqual(attempt.answers.get(item__number=1).raw, 'испорчено')   # форма не принята

    def test_09_take_of_a_submitted_attempt_redirects_to_result(self):
        attempt = self.started()
        self.finish(self.guest, attempt)
        response = self.guest.get(self.take_url(attempt))
        self.assertRedirects(response, self.result_url(attempt), fetch_redirect_response=False)

    def test_04c_foreign_code_is_404_on_finish_and_nothing_is_submitted(self):
        attempt = self.started()
        other = User.objects.create_user('vp_o2', password='p12345')
        logged = Client()
        logged.force_login(other)
        for client in (self.stranger, Client(), logged):
            self.assertEqual(self.finish(client, attempt, **{'item-1': 'подмена'}).status_code, 404)
        attempt.refresh_from_db()
        self.assertIsNone(attempt.submitted_at)
        self.assertEqual(attempt.answers.count(), 0)

    def test_unanswered_items_get_rows_with_zero_and_none(self):
        attempt = self.started()
        with at(T0 + timedelta(seconds=30)):
            self.post_save(self.guest, attempt, [{'item': 1, 'raw': 'термин 1'}, {'item': 2, 'raw': 'мимо'}])
            self.finish(self.guest, attempt)
        rows = {a.item.number: a for a in attempt.answers.select_related('item')}
        self.assertEqual(len(rows), 44)
        self.assertEqual((rows[1].score, rows[1].is_correct), (D('2.00'), True))
        self.assertEqual((rows[2].score, rows[2].is_correct), (D('0.00'), False))
        self.assertEqual((rows[3].score, rows[3].is_correct, rows[3].raw), (D('0.00'), None, None))
        self.assertEqual(rows[3].max_score, D('2.00'))
        self.assertEqual(rows[44].max_score, D('5.00'))

    def test_wrong_penalty_never_hits_unanswered_items(self):
        for item in self.variant.items.filter(number__in=(1, 2)):
            item.wrong_penalty = D('1')
            item.save()
        attempt = self.started()
        with at(T0 + timedelta(seconds=30)):
            self.post_save(self.guest, attempt, [{'item': 1, 'raw': 'мимо'}])
            self.finish(self.guest, attempt)
        rows = {a.item.number: a for a in attempt.answers.select_related('item')}
        self.assertEqual((rows[1].score, rows[1].is_correct), (D('-1.00'), False))
        self.assertEqual((rows[2].score, rows[2].is_correct), (D('0.00'), None))
        attempt.refresh_from_db()
        self.assertEqual(attempt.score, D('0.00'))               # итог не ниже нуля

    def test_stored_total_is_the_scoring_module_total(self):
        attempt = self.started()
        with at(T0 + timedelta(seconds=30)):
            self.post_save(self.guest, attempt, [{'item': 1, 'raw': 'термин 1'}, {'item': 36, 'raw': [1, 2, 3]},
                                                 {'item': 31, 'raw': 3}])
            self.finish(self.guest, attempt)
        attempt.refresh_from_db()
        self.assertEqual(attempt.score, scoring.score_attempt(attempt))
        self.assertEqual(attempt.score, D('6.00'))               # 2 + 2 (36: 3 − 1) + 2

    def test_final_form_fields_are_saved_before_scoring(self):
        """Последняя порция набранного не теряется, даже если автосейв отстал."""
        attempt = self.started()
        with at(T0 + timedelta(seconds=30)):
            self.post_save(self.guest, attempt, [{'item': 36, 'raw': [1, 2]}])
        with at(T0 + timedelta(seconds=60)):
            self.finish(self.guest, attempt, **{
                'item-1': 'термин 1', 'item-31': ['', '3'],
                'item-37': ['', '1', '3'], 'item-2': 'вставлено не тем'})
        rows = {a.item.number: a.raw for a in attempt.answers.select_related('item')}
        self.assertEqual(rows[1], 'термин 1')
        self.assertEqual(rows[31], 3)
        self.assertEqual(rows[37], [1, 3])
        attempt.refresh_from_db()
        self.assertEqual(attempt.score, D('7.50'))               # 2 + 2 + 36: 3/2 − 3/3 + 37: 3

    def test_blank_form_value_never_erases_a_saved_answer(self):
        """Страница, отрисованная раньше последней записи, несёт устаревшие пустые
        поля: «побеждает последний» затёр бы ими сохранённое."""
        attempt = self.started()
        with at(T0 + timedelta(seconds=30)):
            self.post_save(self.guest, attempt, [
                {'item': 1, 'raw': 'термин 1'}, {'item': 31, 'raw': 3}, {'item': 36, 'raw': [1, 3]}])
        with at(T0 + timedelta(seconds=60)):
            self.finish(self.guest, attempt, **{'item-1': '', 'item-31': [''], 'item-36': ['']})
        rows = {a.item.number: a.raw for a in attempt.answers.select_related('item')}
        self.assertEqual((rows[1], rows[31], rows[36]), ('термин 1', 3, [1, 3]))
        attempt.refresh_from_db()
        self.assertEqual(attempt.score, D('7.00'))               # 2 + 2 + 3: всё уцелело

    def test_an_answer_is_cleared_only_through_save(self):
        attempt = self.started()
        with at(T0 + timedelta(seconds=30)):
            self.post_save(self.guest, attempt, [{'item': 1, 'raw': 'термин 1'}])
            self.post_save(self.guest, attempt, [{'item': 1, 'raw': ''}])       # участник стёр
            self.finish(self.guest, attempt)
        self.assertIsNone(attempt.answers.get(item__number=1).raw)

    def test_a_garbage_field_does_not_break_the_submission(self):
        attempt = self.started()
        self.finish(self.guest, attempt, **{'item-31': ['', '99'], 'item-1': 'ок', 'item-999': 'x'})
        attempt.refresh_from_db()
        self.assertIsNotNone(attempt.submitted_at)
        self.assertEqual(attempt.answers.get(item__number=1).raw, 'ок')
        self.assertIsNone(attempt.answers.get(item__number=31).raw)

    def test_match_fields_of_the_final_form(self):
        item = self.variant.items.get(number=44)
        item.kind, item.options, item.correct = 'match', [{'n': 1, 'text': 'а'}, {'n': 2, 'text': 'б'}], {'к1': 2, 'к2': 1}
        item.points = D('5')
        item.save()
        attempt = self.started()
        self.finish(self.guest, attempt, **{'item-44.к1': '2', 'item-44.к2': ''})
        self.assertEqual(attempt.answers.get(item__number=44).raw, {'к1': 2})

    def test_auto_flag_is_honoured_only_near_the_deadline(self):
        early = self.started(with_timer='1')
        with at(T0 + timedelta(seconds=100)):
            self.finish(self.guest, early, auto='1')
        early.refresh_from_db()
        self.assertFalse(early.is_auto_submitted)            # серверные часы не согласны

        self.guest = Client()
        late = self.started(with_timer='1')
        with at(T0 + timedelta(seconds=1799)):
            self.finish(self.guest, late, auto='1')
        late.refresh_from_db()
        self.assertTrue(late.is_auto_submitted)
        self.assertEqual(late.submitted_at, late.expires_at)     # автосдача — по сроку, не «сейчас»

    def test_finish_inside_grace_takes_the_final_fields_and_is_marked_auto(self):
        attempt = self.started(with_timer='1')
        with at(T0 + timedelta(seconds=1803)):
            self.finish(self.guest, attempt, **{'item-1': 'термин 1'})
        attempt.refresh_from_db()
        self.assertTrue(attempt.is_auto_submitted)
        self.assertEqual(attempt.submitted_at, attempt.expires_at)
        self.assertEqual(attempt.score, D('2.00'))

    def test_finish_after_grace_ignores_late_fields(self):
        attempt = self.started(with_timer='1')
        with at(T0 + timedelta(seconds=1800 + 60)):
            self.finish(self.guest, attempt, **{'item-1': 'термин 1'})
        attempt.refresh_from_db()
        self.assertTrue(attempt.is_auto_submitted)
        self.assertEqual(attempt.score, D('0.00'))

    def test_manual_finish_before_the_deadline_uses_now(self):
        attempt = self.started(with_timer='1')
        with at(T0 + timedelta(seconds=600)):
            self.finish(self.guest, attempt)
        attempt.refresh_from_db()
        self.assertEqual(attempt.submitted_at, T0 + timedelta(seconds=600))
        self.assertFalse(attempt.is_auto_submitted)

    def test_finish_of_an_untimed_attempt_is_never_auto(self):
        attempt = self.started(with_timer='0')
        with at(T0 + timedelta(days=2)):
            self.finish(self.guest, attempt, auto='1')
        attempt.refresh_from_db()
        self.assertFalse(attempt.is_auto_submitted)
        self.assertEqual(attempt.submitted_at, T0 + timedelta(days=2))

    def test_finish_requires_post_and_csrf(self):
        attempt = self.started()
        url = reverse('vp:finish', args=[attempt.public_code])
        self.assertEqual(self.guest.get(url).status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        strict.cookies = self.guest.cookies
        self.assertEqual(strict.post(url, {'item-1': 'x'}).status_code, 403)
        attempt.refresh_from_db()
        self.assertIsNone(attempt.submitted_at)

    def test_finalize_is_one_function_for_manual_and_auto(self):
        manual = self.started()
        with at(T0 + timedelta(seconds=30)):
            self.assertTrue(views._finalize(manual, auto=False))
            self.assertFalse(views._finalize(manual, auto=True))     # повтор ничего не меняет
        manual.refresh_from_db()
        self.assertFalse(manual.is_auto_submitted)
        self.assertEqual(manual.answers.count(), 44)


class ResultTests(TimeAndFinishBase):
    def submitted(self, **fields):
        attempt = self.started(with_timer='1')
        with at(T0 + timedelta(seconds=60)):
            self.post_save(self.guest, attempt, [{'item': 1, 'raw': 'термин 1'},
                                                 {'item': 7, 'raw': 'мой личный ответ'}])
        with at(T0 + timedelta(seconds=90)):
            self.finish(self.guest, attempt)
        return attempt

    def html(self, client, attempt):
        response = client.get(self.result_url(attempt))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_minimal_result_has_score_blocks_time_and_button(self):
        attempt = self.submitted()
        html = self.html(self.guest, attempt)
        self.assertRegex(html, r'<b>2</b><span>из 100</span>')
        for name in ('Змейка, 1–30', 'Пропущенные слова, 31–35', 'Все верные, 36–40',
                     'Рисунок и таблица, 41–42', 'Расчётные, 43–44'):
            self.assertIn(name, html)
        self.assertIn('2 / 60', html)
        self.assertIn('01:30 из 30:00', html)          # сдано на 90-й секунде
        self.assertNotIn('сдано по истечении времени', html)
        self.assertIn('Пройти другой вариант', html)
        self.assertIn(reverse('vp:index'), html)
        self.assertIn('noindex', html)

    def test_auto_submitted_result_says_so(self):
        attempt = self.started(with_timer='1')
        with at(T0 + timedelta(hours=1)):
            self.guest.get(self.take_url(attempt))
        html = self.html(self.guest, attempt)
        self.assertIn('сдано по истечении времени', html)
        self.assertIn('30:00 из 30:00', html)

    def test_untimed_result_says_so(self):
        attempt = self.started(with_timer='0')
        self.finish(self.guest, attempt)
        self.assertIn('без таймера', self.html(self.guest, attempt))

    def test_result_is_public_by_code_but_shows_no_answers(self):
        attempt = self.submitted()
        for client in (self.stranger, Client()):
            html = self.html(client, attempt)
            self.assertRegex(html, r'<b>2</b><span>из 100</span>')
            for private in ('мой личный ответ', 'термин 1', 'термин 7', 'эталон'):
                self.assertNotIn(private, html)

    def test_shared_result_does_not_name_the_owner(self):
        """Ни имя, ни фамилия, ни логин вошедшего автора чужому не видны (сессия 4, ADR 0127)."""
        user = User.objects.create_user('vp_named', password='p12345',
                                        first_name='Иван', last_name='Секретов')
        client = Client()
        client.force_login(user)
        attempt, _ = self.start(client)
        with at(T0 + timedelta(seconds=30)):
            self.finish(client, attempt)
        html = self.html(Client(), attempt)
        self.assertNotIn('Секретов', html)
        self.assertNotIn('Иван', html)
        self.assertNotIn('vp_named', html)
        self.assertIn('Участник', html)         # положительный контроль: страница не пустая

    def test_unsubmitted_attempt_is_not_a_result(self):
        attempt = self.started()
        self.assertRedirects(self.guest.get(self.result_url(attempt)), self.take_url(attempt),
                             fetch_redirect_response=False)
        self.assertEqual(self.stranger.get(self.result_url(attempt)).status_code, 404)
        self.assertEqual(Client().get(self.result_url(attempt)).status_code, 404)

    def test_unknown_code_is_404(self):
        self.assertEqual(Client().get(reverse('vp:result', args=['net-takoi'])).status_code, 404)

    def test_owner_of_a_lapsed_attempt_lands_on_the_result_after_take(self):
        attempt = self.started(with_timer='1')
        with at(T0 + timedelta(hours=1)):
            first = self.guest.get(self.result_url(attempt))
            self.assertRedirects(first, self.take_url(attempt), fetch_redirect_response=False)
            second = self.guest.get(self.take_url(attempt))
            self.assertRedirects(second, self.result_url(attempt), fetch_redirect_response=False)
            self.assertContains(self.guest.get(self.result_url(attempt)), 'сдано по истечении времени')

    def test_block_totals_sum_to_the_score(self):
        attempt = self.started()
        with at(T0 + timedelta(seconds=30)):
            self.post_save(self.guest, attempt, all_correct_batch(self.variant))
            self.finish(self.guest, attempt)
        attempt.refresh_from_db()
        totals = scoring.block_totals(attempt)
        self.assertEqual(list(totals), ['snake', 'gapfill', 'multi', 'analytic', 'single'])
        self.assertEqual(totals['single'], (D('9.00'), D('9.00')))
        self.assertEqual(sum(got for got, _ in totals.values()), attempt.score)
        self.assertEqual(sum(top for _, top in totals.values()), D('100.00'))
