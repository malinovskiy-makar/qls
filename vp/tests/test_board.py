"""Таблица лучших попыток: что в неё попадает и в каком порядке (`vp/board.py`).

Правило владельца 22.09.2026: считается ПЕРВАЯ попытка человека по варианту,
начатая с таймером; из таких у каждого берётся лучшая; при равных баллах выше тот,
кто сдал быстрее; гостя в таблице нет.

⚠️ Числа здесь — из фикстуры, а не из головы: сколько людей завели, столько строк
и ждём. Зачётность ставит `views.start`, и отдельный класс ниже проверяет именно его.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from vp import board
from vp.models import VPAttempt
from vp.tests.helpers import make_published

User = get_user_model()


def _user(name):
    return User.objects.create_user(username=name, password='x' * 12)


def _attempt(variant, user, *, score, seconds, ranked=True, timer=True,
             submitted=True, started=None, auto=False):
    """Попытка с заданным баллом и потраченным временем.

    `started_at` ставит `auto_now_add`, поэтому после создания его правим напрямую:
    иначе все попытки теста начались бы в одну и ту же миллисекунду.
    """
    started = started or timezone.now() - timedelta(hours=2)
    attempt = VPAttempt.objects.create(
        variant=variant, user=user, with_timer=timer, is_ranked=ranked,
        max_score=Decimal('100'), public_code=f'c{VPAttempt.objects.count():05d}',
        expires_at=started + timedelta(seconds=variant.duration_seconds) if timer else None,
        is_auto_submitted=auto,
    )
    VPAttempt.objects.filter(pk=attempt.pk).update(
        started_at=started,
        expires_at=(started + timedelta(seconds=variant.duration_seconds)) if timer else None,
        submitted_at=(started + timedelta(seconds=seconds)) if submitted else None,
        score=Decimal(str(score)) if submitted else None,
    )
    attempt.refresh_from_db()
    return attempt


class BoardRowsTests(TestCase):
    """Инварианты 1–3: кто попадает в таблицу, в каком порядке и что видно в топе."""

    @classmethod
    def setUpTestData(cls):
        cls.variant = make_published('board-a')
        cls.other = make_published('board-b')

    def test_01_training_and_guests_stay_out_and_only_the_ranked_one_counts(self):
        """Инвариант 1: в таблице по строке на человека, и это его ЗАЧЁТНАЯ попытка."""
        one, two, three = _user('one'), _user('two'), _user('three')
        _attempt(self.variant, one, score=80, seconds=1200)

        # У второго по одному варианту две попытки с таймером и одна без.
        # Зачётная — первая (60 б), хотя вторая лучше; без таймера — тренировка.
        _attempt(self.variant, two, score=60, seconds=1000)
        _attempt(self.variant, two, score=100, seconds=900, ranked=False)
        _attempt(self.variant, two, score=100, seconds=900, ranked=False, timer=False)

        # У третьего только попытка без таймера — в таблице его нет вовсе.
        _attempt(self.variant, three, score=95, seconds=800, ranked=False, timer=False)

        rows = board.rows()
        self.assertEqual([r['name'] for r in rows], ['one', 'two'])
        self.assertEqual(rows[1]['score'], Decimal('60.00'))
        self.assertNotIn('three', [r['name'] for r in rows])

    def test_02_equal_scores_are_broken_by_time(self):
        """Инвариант 2: при равном балле выше тот, у кого меньше `spent_seconds`."""
        slow, fast = _user('slow'), _user('fast')
        _attempt(self.variant, slow, score=85, seconds=1700)
        _attempt(self.variant, fast, score=85, seconds=900)

        rows = board.rows()
        self.assertEqual([r['name'] for r in rows], ['fast', 'slow'])
        self.assertEqual([r['place'] for r in rows], [1, 2])
        self.assertEqual(rows[0]['seconds'], 900)

    def test_03_auto_submitted_attempt_spends_the_whole_limit(self):
        """Автосдача — весь лимит: работа шла до конца, даже если участник ушёл."""
        away = _user('away')
        attempt = _attempt(self.variant, away, score=40, seconds=120, auto=True)
        self.assertEqual(board.spent_seconds(attempt), self.variant.duration_seconds)

    def test_04_top_ten_and_my_row_below_the_line(self):
        """Инвариант 3: топ — десять строк, своя строка приходит только вне топа."""
        people = []
        for n in range(12):
            person = _user(f'p{n:02d}')
            people.append(person)
            # Балл падает с номером: p00 первый, p11 двенадцатый.
            _attempt(self.variant, person, score=100 - n, seconds=1000)

        head, mine, humans, attempts = board.top(me=people[10])
        self.assertEqual(len(head), board.TOP)
        self.assertEqual(humans, 12)
        self.assertEqual(attempts, 12)
        self.assertIsNotNone(mine)
        self.assertEqual(mine['place'], 11)

        # Третий человек уже в топе — второй раз его не показываем.
        _, inside, _, _ = board.top(me=people[2])
        self.assertIsNone(inside)

    def test_05_best_of_two_ranked_attempts_on_different_variants(self):
        """По варианту зачётная одна, но вариантов много: берём лучшую из них."""
        person = _user('many')
        worse = _attempt(self.variant, person, score=50, seconds=1000)
        better = _attempt(self.other, person, score=90, seconds=1500)

        rows = board.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['attempt'].pk, better.pk)
        self.assertEqual(board.place_of(better), 1)
        # Вторая зачётная попытка человека места не получает: строка на человека одна.
        self.assertIsNone(board.place_of(worse))

    def test_06_unsubmitted_ranked_attempt_is_not_in_the_board_yet(self):
        """Начатая зачётная попытка в таблицу не идёт, пока не сдана."""
        person = _user('running')
        _attempt(self.variant, person, score=0, seconds=0, submitted=False)
        self.assertEqual(board.rows(), [])


class StartMarksRankedTests(TestCase):
    """Инвариант 4: зачётность ставит `views.start`, и ставит ровно по правилу."""

    @classmethod
    def setUpTestData(cls):
        cls.variant = make_published('start-a')
        cls.other = make_published('start-b')

    def setUp(self):
        self.user = _user('starter')
        self.client.force_login(self.user)

    def _start(self, variant, timer=True):
        self.client.post(reverse('vp:start', args=[variant.slug]),
                         {'with_timer': '1' if timer else '0'})
        attempt = VPAttempt.objects.filter(variant=variant).order_by('-id').first()
        # Следующая попытка по тому же варианту не начнётся, пока эта не сдана.
        VPAttempt.objects.filter(pk=attempt.pk).update(submitted_at=timezone.now())
        attempt.refresh_from_db()
        return attempt

    def test_01_first_timed_attempt_is_ranked_and_the_second_is_not(self):
        first = self._start(self.variant)
        second = self._start(self.variant)
        self.assertTrue(first.is_ranked)
        self.assertFalse(second.is_ranked)

    def test_02_attempt_without_timer_is_never_ranked(self):
        self.assertFalse(self._start(self.variant, timer=False).is_ranked)

    def test_03_first_timed_attempt_on_another_variant_is_ranked_again(self):
        self._start(self.variant)
        self.assertTrue(self._start(self.other).is_ranked)

    def test_04_a_timed_attempt_after_an_untimed_one_is_still_ranked(self):
        """Тренировка без таймера не съедает право на зачётную попытку."""
        self._start(self.variant, timer=False)
        self.assertTrue(self._start(self.variant).is_ranked)

    # Гость зачётной попытки не заводит вовсе: старт уводит его на регистрацию.
    # Это проверяет `test_gate.py` — там же, где живёт сама стена.
