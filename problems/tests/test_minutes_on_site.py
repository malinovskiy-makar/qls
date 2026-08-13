"""
Минуты на сайте при КОРОТКИХ ЗАХОДАХ (сессия 10, фаза 3).

Гипотеза владельца: минуты считаются расстоянием между соседними событиями,
поэтому одиночное событие, у которого нет пары внутри получасового окна,
даёт ноль. Тогда у ученика, который решает по одной задаче за заход,
счётчик вечно показывает почти ноль.

Проверяем НА СИНТЕТИКЕ, а не на тестовом аккаунте: у живого аккаунта
«6 минут при 23 попытках» может быть и правдой, по нему ничего не докажешь.

⚠️ Тесты остаются в наборе независимо от исхода: подсчёт времени легко
сломать незаметно — страница отдаст 200, а число будет врать.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from problems import stats
from problems.models import LearningEvent, User


def make_student(name='min_student'):
    user = User.objects.create_user(username=name, password='x',
                                    email=f'{name}@test.local')
    user.role = 'student'
    user.save()
    return user


def put_event(user, when):
    """Событие с ЗАДАННЫМ моментом.

    ⚠️ `created_at` стоит `auto_now_add=True`, поэтому момент проставляется
    вторым запросом: иначе все события легли бы «сейчас» и любой замер
    расстояний дал бы ноль — тест краснел бы по своей же вине.
    """
    event = LearningEvent.objects.create(
        user=user, source=LearningEvent.Source.HOMEWORK,
        event_type=LearningEvent.EventType.SOLVED)
    LearningEvent.objects.filter(pk=event.pk).update(created_at=when)
    return event


class MinutesOnSiteTests(TestCase):
    """Три набора из карточки владельца."""

    def setUp(self):
        self.user = make_student()
        # Считаем от фиксированного «сейчас»: период `month` — 30 дней назад.
        self.now = timezone.now()

    def minutes(self, period='month'):
        return stats.minutes_on_site(self.user, period, now=self.now)

    # ── набор 1 ───────────────────────────────────────────────────────────
    def test_ten_single_visits_on_ten_days(self):
        """Десять одиночных заходов: по одному событию в день.

        По здравому смыслу это НЕ ноль: человек десять раз открывал сайт и
        решал задачу. Ноль означал бы, что его там не было.
        """
        for day in range(1, 11):
            put_event(self.user, self.now - timedelta(days=day, hours=1))

        got = self.minutes()
        self.assertEqual(LearningEvent.objects.filter(user=self.user).count(), 10)
        self.assertGreater(
            got, 0,
            'десять заходов не могут весить ноль минут: одиночное событие '
            'без пары внутри окна не должно пропадать')
        # Оценка снизу — по минуте на заход; потолок — чтобы не приписать
        # человеку время, которого он не проводил.
        self.assertGreaterEqual(got, 10)
        self.assertLessEqual(got, 40, 'десять коротких заходов — не полчаса')

    # ── набор 2 ───────────────────────────────────────────────────────────
    def test_dense_session_of_ten_events(self):
        """Плотная сессия: десять событий с промежутком в две минуты.

        Между первым и последним событием 18 минут. Столько человек точно
        провёл; плюс время на последнее действие, которое замерить нечем.
        """
        base = self.now - timedelta(days=1)
        for step in range(10):
            put_event(self.user, base + timedelta(minutes=2 * step))

        got = self.minutes()
        self.assertGreaterEqual(got, 18, 'промежутки внутри сессии — 18 минут')
        self.assertLessEqual(got, 25,
                             'приписывать сессии лишние минуты тоже нельзя')

    # ── набор 3 ───────────────────────────────────────────────────────────
    def test_mixed_dense_session_and_three_single_visits(self):
        """Плотная сессия плюс три одиночных события в разные дни."""
        base = self.now - timedelta(days=1)
        for step in range(10):
            put_event(self.user, base + timedelta(minutes=2 * step))
        for day in (3, 5, 7):
            put_event(self.user, self.now - timedelta(days=day, hours=2))

        dense_only = 18
        got = self.minutes()
        self.assertGreater(
            got, dense_only,
            'три отдельных захода обязаны что-то добавить к плотной сессии')

    # ── правила, которые чинить не надо ──────────────────────────────────
    def test_long_pause_is_not_counted(self):
        """Пауза длиннее получаса — уход, а не «сидел и думал»."""
        base = self.now - timedelta(days=1)
        put_event(self.user, base)
        put_event(self.user, base + timedelta(hours=5))

        got = self.minutes()
        self.assertLess(got, 3 * stats.SESSION_GAP_MINUTES,
                        'пятичасовой перерыв не должен попасть в зачёт')

    def test_no_events_is_zero(self):
        """Ни одного события — честный ноль, а не выдуманный минимум."""
        self.assertEqual(self.minutes(), 0)

    def test_two_sessions_in_one_day_count_separately(self):
        """Утро и вечер одного дня — две сессии, а не одна длинная."""
        base = self.now - timedelta(days=1)
        for step in range(3):
            put_event(self.user, base + timedelta(minutes=3 * step))
        for step in range(3):
            put_event(self.user, base + timedelta(hours=6, minutes=3 * step))

        got = self.minutes()
        # Шесть минут промежутков в каждой сессии, разрыв между ними — мимо.
        self.assertGreaterEqual(got, 12)
        self.assertLess(got, 60)

    def test_period_bounds_are_respected(self):
        """События вне периода не считаются."""
        old = self.now - timedelta(days=200)
        for step in range(5):
            put_event(self.user, old + timedelta(minutes=2 * step))
        self.assertEqual(self.minutes('month'), 0)
        self.assertGreater(self.minutes('all'), 0)


class MinutesExactNumbers(TestCase):
    """Точные числа ПОСЛЕ починки — чтобы правило нельзя было сдвинуть молча.

    Правило: сумма промежутков внутри сессий плюс `SESSION_TAIL_MINUTES` за
    каждую сессию.
    """

    def setUp(self):
        self.user = make_student('min_exact')
        self.now = timezone.now()

    def minutes(self):
        return stats.minutes_on_site(self.user, 'month', now=self.now)

    def test_ten_single_visits_give_ten_tails(self):
        for day in range(1, 11):
            put_event(self.user, self.now - timedelta(days=day, hours=1))
        self.assertEqual(self.minutes(), 10 * stats.SESSION_TAIL_MINUTES)

    def test_dense_session_is_gaps_plus_one_tail(self):
        base = self.now - timedelta(days=1)
        for step in range(10):
            put_event(self.user, base + timedelta(minutes=2 * step))
        self.assertEqual(self.minutes(), 18 + stats.SESSION_TAIL_MINUTES)

    def test_mixed_set_adds_up(self):
        base = self.now - timedelta(days=1)
        for step in range(10):
            put_event(self.user, base + timedelta(minutes=2 * step))
        for day in (3, 5, 7):
            put_event(self.user, self.now - timedelta(days=day, hours=2))
        # 18 минут промежутков + четыре сессии (одна плотная и три коротких).
        self.assertEqual(self.minutes(), 18 + 4 * stats.SESSION_TAIL_MINUTES)

    def test_one_event_is_one_tail_not_zero(self):
        put_event(self.user, self.now - timedelta(hours=3))
        self.assertEqual(self.minutes(), stats.SESSION_TAIL_MINUTES)
