"""
Команда `seed_showcase_student`: витринный ученик, репетитор, группа.

Что стерегут тесты (каждый — против одного класса поломок, а не «на всякий»):
* сухой прогон не пишет ничего (иначе «посмотреть» стало бы «записать»);
* повторный --apply не дублирует и не меняет ни одного числа;
* события разложены по РАЗНЫМ дням до сегодняшнего (`created_at` — auto_now_add,
  а bulk_create перетирает переданную дату: без этого вся история схлопнется в
  один день и серия/графики умрут);
* пересчёт геймификации идемпотентен и совпадает с тем, что оставила команда
  (значит, ни одно число не вбито руками в свёртку);
* --purge не оставляет ни одной строки с демо-логинами и не трогает чужих;
* экран /profile/stats/ не содержит ни одной фразы пустого состояния, а
  карточка ученика у репетитора открывается (не редирект на занятие).

Числа маленькие (`--days 14`): тест идёт секунды, а не минуты. Полные цели
90-дневной истории проверяет отчёт самой команды («факт против цели»).
Пароль генерируется на лету: в публичный репозиторий его класть нельзя.
"""
import io
import re
import secrets

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase
from django.utils import timezone

from game.models import GameResult
from problems.management.commands.seed_showcase_student import all_logins
from problems.models import (
    Assignment, ExamAttempt, LearningEvent, StudentGroup, StudentProgressProfile,
    StudentSkillProgress, Submission, TeacherFeedback, User,
)
from problems.models_gamification import DailySummary, EarnedAchievement, PersonalRecord
from problems.models_platform import TutorNote, WorkDifficulty
from problems.sections import CANONICAL_SECTION
from problems.tests.factories import make_problem, make_topic, make_user

PASSWORD = secrets.token_urlsafe(12)
DAYS = 14
LOGINS = all_logins('demo')

# Точные строки пустых состояний из stats.html и stats.py — если хоть одна
# на экране, значит, какой-то блок витрины пуст.
EMPTY_PHRASES = [
    'Пока нет данных', 'Ты ещё не играл', 'Реши первую задачу',
    'Ещё нет решённых задач с темой', 'нет ответов', 'Решённых задач пока мало',
    'Ни одна тема пока не набрала', 'Порог в 5 попыток', 'Пока не из чего считать',
]


def build_bank(cls):
    """Мини-банк: все канонические темы + одна неканоническая (ось «Прочее»),
    по 25 видимых задач в каждой; у части задач есть реальная сложность."""
    cls.topics = {name: make_topic(name) for name in CANONICAL_SECTION}
    cls.topics['legacy'] = make_topic('Рыночные структуры')
    for name, topic in cls.topics.items():
        for i in range(25):
            make_problem(statement=f'Условие {name} № {i}', topic=topic,
                         difficulty=4 if i % 6 == 0 else 5 if i % 11 == 0 else None)


def run(*extra, apply=True):
    out = io.StringIO()
    args = ['--password', PASSWORD, '--days', str(DAYS), *extra]
    if apply:
        args.append('--apply')
    call_command('seed_showcase_student', *args, stdout=out)
    return out.getvalue()


def demo_users():
    return User.objects.filter(username__in=LOGINS)


def snapshot():
    """Всё, что должно совпасть между двумя одинаковыми запусками."""
    users = demo_users()
    profiles = {p.user.username: (p.xp_total, p.level, p.current_streak, p.longest_streak,
                                  p.weekly_goal)
                for p in StudentProgressProfile.objects.filter(user__in=users)}
    events = sorted(
        (e.user.username, e.source, e.event_type, e.topic.name if e.topic_id else None,
         e.difficulty, timezone.localtime(e.created_at).date().isoformat())
        for e in LearningEvent.objects.filter(user__in=users).select_related('user', 'topic'))
    counts = {model.__name__: model.objects.count() for model in (
        Assignment, Submission, TeacherFeedback, ExamAttempt, DailySummary, EarnedAchievement,
        PersonalRecord, WorkDifficulty, StudentSkillProgress, TutorNote, StudentGroup)}
    counts['users'] = users.count()
    return {'profiles': profiles, 'events': events, 'counts': counts}


class ShowcaseDryRunAndPurgeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        build_bank(cls)

    # 1. Сухой прогон не пишет в базу ни одной строки.
    def test_dry_run_writes_nothing(self):
        before = snapshot()
        out = run(apply=False)
        self.assertIn('СУХОЙ ПРОГОН', out)
        self.assertIn('Факт против цели', out)          # но всё посчитано и напечатано
        self.assertEqual(snapshot(), before)
        self.assertFalse(demo_users().exists())
        self.assertEqual(LearningEvent.objects.count(), 0)

    # 2. --apply создаёт аккаунты и группу; повтор ничего не дублирует.
    def test_apply_creates_accounts_and_repeat_changes_nothing(self):
        run()
        first = snapshot()
        self.assertEqual(first['counts']['users'], 5)
        self.assertEqual(first['counts']['StudentGroup'], 1)
        run()
        self.assertEqual(snapshot(), first)

    # 5. --purge не оставляет ни одной строки, ссылающейся на демо-логины.
    def test_purge_leaves_no_row_referencing_demo_users(self):
        run()
        pks = list(demo_users().values_list('pk', flat=True))
        self.assertEqual(len(pks), 5)
        call_command('seed_showcase_student', '--password', PASSWORD, '--purge',
                     stdout=io.StringIO())
        self.assertFalse(User.objects.filter(pk__in=pks).exists())
        left = {}
        for rel in User._meta.related_objects:          # все обратные связи на User
            model, name = rel.related_model, rel.field.name
            n = model.objects.filter(**{f'{name}__in': pks}).count()
            if n:
                left[f'{model.__name__}.{name}'] = n
        self.assertEqual(left, {})
        # SET_NULL-связи (автор работы) после удаления пользователя не нашлись
        # бы по ключу — поэтому в тестовой базе не должно остаться и самих строк.
        for model in (Assignment, Submission, LearningEvent, StudentGroup, TutorNote,
                      DailySummary, EarnedAchievement, PersonalRecord, ExamAttempt):
            self.assertEqual(model.objects.count(), 0, model.__name__)

    def test_purge_does_not_touch_other_users(self):
        bystander = make_user('bystander', password=PASSWORD)
        LearningEvent.objects.create(user=bystander, source='catalog', event_type='solved')
        StudentProgressProfile.objects.create(user=bystander, xp_total=5)
        run()
        call_command('seed_showcase_student', '--password', PASSWORD, '--purge',
                     stdout=io.StringIO())
        self.assertTrue(User.objects.filter(username='bystander').exists())
        self.assertEqual(LearningEvent.objects.filter(user=bystander).count(), 1)
        self.assertEqual(StudentProgressProfile.objects.get(user=bystander).xp_total, 5)

    def test_password_is_required(self):
        with self.assertRaises(CommandError):
            call_command('seed_showcase_student', stdout=io.StringIO())


class ShowcaseAppliedTests(TestCase):
    """Один запуск на класс, дальше читаем результат."""

    @classmethod
    def setUpTestData(cls):
        build_bank(cls)
        run()
        cls.student = User.objects.get(username='demo')
        cls.tutor = User.objects.get(username='demo-tutor')

    # 3. События разложены по РАЗНЫМ дням, последний — сегодня.
    def test_events_spread_over_days_up_to_today(self):
        events = LearningEvent.objects.filter(user=self.student)
        days = {timezone.localtime(e.created_at).date() for e in events}
        self.assertGreater(len(days), 1)
        self.assertEqual(max(days), timezone.localdate())
        self.assertGreaterEqual(len(days), DAYS // 2)
        # и ни одного «из будущего»: часть выборок такое событие не видит
        self.assertFalse(events.filter(created_at__gt=timezone.now()).exists())

    # 4. После пересчёта опыт, уровень и серия живые.
    def test_gamification_is_alive(self):
        profile = StudentProgressProfile.objects.get(user=self.student)
        self.assertGreater(profile.xp_total, 0)
        self.assertGreater(profile.level, 1)
        self.assertGreater(profile.current_streak, 0)

    # 6. Пересчёт идемпотентен и не расходится с тем, что оставила команда.
    def test_recalculation_is_idempotent_and_matches_command_output(self):
        def numbers():
            p = StudentProgressProfile.objects.get(user=self.student)
            return p.xp_total, p.level, p.current_streak, p.longest_streak
        after_command = numbers()
        for _ in range(2):
            call_command('recalculate_gamification', user_id=self.student.pk, verbosity=0)
            self.assertEqual(numbers(), after_command)

    # 7. Экран статистики: 200 и ни одной фразы пустого состояния.
    def test_stats_screen_has_no_empty_states(self):
        client = Client()
        client.force_login(self.student)
        response = client.get('/profile/stats/')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertEqual([p for p in EMPTY_PHRASES if p in html], [])

    # 8. Карточка ученика у репетитора: 200, а не редирект на занятие.
    def test_tutor_sees_student_card(self):
        client = Client()
        client.force_login(self.tutor)
        response = client.get(f'/teacher/student/{self.student.pk}/progress/')
        self.assertEqual(response.status_code, 200)
        text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', response.content.decode()))
        self.assertIn(self.student.first_name, text)
        self.assertIn(self.student.last_name, text)
        self.assertRegex(text, r'\d,\d из 10')          # «средняя сложность работ» из WorkDifficulty

    def test_group_overview_opens_for_tutor(self):
        group = StudentGroup.objects.get(teacher=self.tutor)
        self.assertEqual(group.students.count(), 4)
        client = Client()
        client.force_login(self.tutor)
        self.assertEqual(client.get(f'/teacher/groups/{group.pk}/?tab=overview').status_code, 200)

    # Прочее из задания
    def test_every_event_is_marked_and_has_a_topic_where_needed(self):
        events = LearningEvent.objects.filter(user__in=demo_users())
        self.assertFalse([e.pk for e in events if not e.payload.get('demo_showcase')])
        game = events.filter(user=self.student, source='game')
        self.assertGreater(game.count(), 0)
        self.assertFalse(game.filter(topic__isnull=True).exists())   # без темы блок промахов пуст
        self.assertTrue(game.filter(event_type='failed').exists())

    def test_no_game_results_are_created(self):
        self.assertEqual(GameResult.objects.count(), 0)

    def test_history_stays_within_visible_problems(self):
        for event in LearningEvent.objects.filter(user=self.student, catalog_problem__isnull=False):
            problem = event.catalog_problem
            self.assertEqual(problem.status, 'published')
            self.assertFalse(problem.needs_quality_review or problem.hidden_pending_review)

    def test_works_have_the_expected_shape(self):
        homework = Assignment.objects.filter(author=self.tutor, kind='homework')
        self.assertGreaterEqual(homework.count(), 3)
        self.assertEqual(Assignment.objects.filter(kind='exam').count(), 1)     # при --days 14
        # каждая работа привязана и к группе, и к ученикам, и к автору
        for work in Assignment.objects.all():
            self.assertIsNotNone(work.group_id)
            self.assertIsNotNone(work.author_id)
            self.assertEqual(work.students.count(), 4)
        # хотя бы одна сдана с опозданием и одна не сдана
        late = [s for s in Submission.objects.filter(student=self.student)
                if s.submitted_at and s.assignment.deadline and s.submitted_at > s.assignment.deadline]
        self.assertTrue(late)
        unsubmitted = Assignment.objects.exclude(
            submissions__student=self.student, submissions__status__in=('submitted', 'reviewed'))
        self.assertGreaterEqual(unsubmitted.count(), 1)
        self.assertTrue(TeacherFeedback.objects.filter(mistakes__isnull=False).exists())
        self.assertTrue(TutorNote.objects.filter(tutor=self.tutor, student=self.student).exists())

    def test_every_submission_has_a_matching_event(self):
        """События по домашкам — часть той же истории: у каждой сдачи витринного
        ученика есть событие с тем же assignment и задачей."""
        for sub in Submission.objects.filter(student=self.student):
            self.assertTrue(LearningEvent.objects.filter(
                user=self.student, assignment=sub.assignment,
                catalog_problem=sub.problem, source__in=('homework', 'exam')).exists())

    def test_history_dates_reach_the_past(self):
        oldest = min(timezone.localtime(e.created_at).date()
                     for e in LearningEvent.objects.filter(user=self.student))
        self.assertGreaterEqual((timezone.localdate() - oldest).days, DAYS - 3)
        self.assertLessEqual((timezone.localdate() - oldest).days, DAYS)
