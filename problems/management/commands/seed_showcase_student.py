"""
Демо-ученик для витрины: экран /profile/stats/ заполнен целиком.

Зачем: платформу начинают рекламировать, а статистика ученика на бою пуста
у всех. Команда заводит ОДИН аккаунт ученика (`demo`) с историей за 90 дней,
его домашками и контрольными, взглядом репетитора (`demo-tutor`) и трёх
одноклассников (`demo-2/3/4`) — без них таблица группы и матрица «ученики ×
темы» из одной строки выглядят сломанными, а редкость каждой награды
показывает 100 %.

Ученик намеренно НЕ идеальный: слабые темы, провальная неделя (отпуск),
недобранные награды. Витрина, где всё на 100 %, читается как заглушка.

ГЛАВНЫЙ ПРИНЦИП: пишем ПЕРВОИСТОЧНИК — LearningEvent, Submission, ExamAttempt,
TeacherFeedback. Опыт, уровень, серию, владение темами, достижения и рекорды
собирает `recalculate_gamification --user-id` (по одному ученику, никогда без
ключа). Ни одного числа, вбитого прямо в свёртки (StudentProgressProfile,
DailySummary, StudentTopicProgress, EarnedAchievement, PersonalRecord).
Не сходится с целью — чинится ГЕНЕРАТОР событий, а не свёртка.

БЕЗ ИГРОВЫХ РЕЗУЛЬТАТОВ: записей `GameResult` команда НЕ создаёт — решение
владельца. У игры публичная таблица рекордов, и выдуманный счёт демо-аккаунта
встал бы в неё рядом с настоящими забегами бета-тестеров. Блок «Игра» на
экране статистики берёт данные из событий LearningEvent(source='game'),
этого достаточно. Не «дочинивать».

Режимы:
  без --apply  — сухой прогон: всё считается и печатается ТОЧНО так же, но
                 внутри транзакции, которая откатывается (в базу ничего);
  --apply      — пишет; повторный прогон с теми же аргументами ничего не
                 дублирует и даёт те же числа (содержимое демо-аккаунтов
                 пересобирается с нуля, зерно фиксировано);
  --purge      — удаляет ВСЁ, что относится к демо-аккаунтам, и сами
                 аккаунты. Единственный путь отката.

Пароль — обязательный аргумент `--password`, значения по умолчанию нет
(репозиторий публичный).
"""
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

# Метка на каждом событии: единственный способ потом отличить витринные
# события от боевых в аналитике (analytics_export, счётчики беты).
DEMO_MARKER = 'demo_showcase'

GROUP_NAME = 'Демо · Олимпиадная экономика, 10 класс'
DEFAULT_SEED = 20260921


class _DryRun(Exception):
    """Служебное: откатить транзакцию сухого прогона."""


def logins_for(username):
    """Пять логинов демо-контура от логина витринного ученика."""
    return {
        'student': username,
        'tutor': f'{username}-tutor',
        'mates': [f'{username}-2', f'{username}-3', f'{username}-4'],
    }


def all_logins(username):
    lg = logins_for(username)
    return [lg['student'], lg['tutor'], *lg['mates']]


# ---------------------------------------------------------------------------
# Команда
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = ('Демо-ученик для витрины: история за 90 дней, домашки, контрольные, '
            'репетитор, группа. Без --apply — сухой прогон (откат). '
            '--purge удаляет всё демо. Пароль — обязательный --password.')

    def add_arguments(self, parser):
        parser.add_argument('--password', required=True,
                            help='Пароль всех демо-аккаунтов (обязателен, без умолчания).')
        parser.add_argument('--apply', action='store_true',
                            help='Записать. Без флага — сухой прогон с откатом.')
        parser.add_argument('--purge', action='store_true',
                            help='Удалить все демо-сущности и выйти.')
        parser.add_argument('--username', default='demo',
                            help='Логин витринного ученика (по умолчанию demo).')
        parser.add_argument('--first-name', default='Демо', dest='first_name')
        parser.add_argument('--last-name', default='Ученик', dest='last_name')
        parser.add_argument('--seed', type=int, default=DEFAULT_SEED,
                            help='Зерно случайности (фиксированное по умолчанию).')
        parser.add_argument('--days', type=int, default=90,
                            help='Глубина истории в днях (по умолчанию 90).')

    # -- вход ---------------------------------------------------------------

    def handle(self, *args, **opts):
        if opts['days'] < 7:
            raise CommandError('--days: история короче недели не имеет смысла.')
        self.opts = opts
        self.apply = opts['apply']
        self.stdout.write(self.style.MIGRATE_HEADING(
            'seed_showcase_student — ' + ('ЗАПИСЬ' if self.apply or opts['purge']
                                          else 'СУХОЙ ПРОГОН (в базу ничего не пишется)')))
        if opts['purge']:
            with transaction.atomic():
                self._purge()
            return
        try:
            with transaction.atomic():
                self._run()
                if not self.apply:
                    raise _DryRun
        except _DryRun:
            self.stdout.write(self.style.WARNING(
                'Сухой прогон: транзакция откатена, в базе ничего не изменилось. '
                'Для записи добавьте --apply.'))

    # -- основной ход ---------------------------------------------------------

    def _run(self):
        self.today = timezone.localdate()
        self.now = timezone.now()
        self.tz = timezone.get_current_timezone()
        accounts = self._ensure_accounts()
        self.student = accounts['student']
        self.tutor = accounts['tutor']
        self.mates = accounts['mates']
        self.group = self._ensure_group()
        self._erase_content()
        self.stdout.write(f'Аккаунты: {", ".join(all_logins(self.opts["username"]))}; '
                          f'группа «{self.group.name}» (id {self.group.pk}).')
        # Части 2–4 (история, домашки, игра, пересчёт) подключаются ниже.
        self._build_all()

    def _build_all(self):
        """Заполнить содержимое демо-аккаунтов. Дописывается по фазам."""

    # -- аккаунты -------------------------------------------------------------

    def _ensure_accounts(self):
        from problems.models import User
        opts = self.opts
        lg = logins_for(opts['username'])

        def make(login, role, first, last, grade=None, city='', goal='', level=''):
            user, created = User.objects.get_or_create(
                username=login,
                defaults={'role': role, 'first_name': first, 'last_name': last,
                          'email': f'{login}@demo.invalid'})
            # Сигнал post_save сам создал UserProfile (роль по User.role).
            fields = []
            for name, value in (('first_name', first), ('last_name', last)):
                if getattr(user, name) != value:
                    setattr(user, name, value)
                    fields.append(name)
            if user.role != role:
                user.role = role
                fields.append('role')
            if not user.check_password(opts['password']):
                user.set_password(opts['password'])
                fields.append('password')
            if fields:
                user.save(update_fields=fields)
            profile = user.profile
            changed = False
            for name, value in (('grade', grade), ('city', city),
                                ('goal', goal), ('level', level)):
                if value not in (None, '') and getattr(profile, name) != value:
                    setattr(profile, name, value)
                    changed = True
            if changed:
                profile.save()
            return user

        student = make(lg['student'], 'student', opts['first_name'], opts['last_name'],
                       grade=10, city='Москва', level='region',
                       goal='Призёр регионального этапа ВсОШ по экономике')
        tutor = make(lg['tutor'], 'teacher', 'Демо', 'Преподаватель',
                     city='Москва')
        mates = [make(login, 'student', 'Демо', f'Ученик {i}', grade=10,
                      city='Москва', level='basic')
                 for i, login in enumerate(lg['mates'], start=2)]
        return {'student': student, 'tutor': tutor, 'mates': mates}

    def _ensure_group(self):
        from problems.models import StudentGroup
        group, _ = StudentGroup.objects.get_or_create(
            teacher=self.tutor, name=GROUP_NAME,
            defaults={'kind': StudentGroup.Kind.GROUP,
                      'description': 'Витринная группа: подготовка к олимпиадам по экономике.'})
        group.students.set([self.student, *self.mates])
        return group

    # -- стирание --------------------------------------------------------------

    def _demo_users(self):
        from problems.models import User
        return list(User.objects.filter(username__in=all_logins(self.opts['username'])))

    def _erase_content(self):
        """Стереть всё СОДЕРЖИМОЕ демо-аккаунтов (аккаунты, профили и группу
        оставляем): и повторный --apply, и --purge начинают отсюда.

        Свёртки геймификации стираем тоже и обязательно: recalculate_gamification
        не отнимает достижения и не снижает рекорды, а значит, после смены
        истории оставил бы «привидения» прошлого прогона."""
        from problems.models import (Assignment, LearningEvent, StudentSkillProgress,
                                     StudentTopicProgress, Submission)
        from problems.models_gamification import (DailySummary, EarnedAchievement,
                                                  PersonalRecord, StudentProgressProfile)
        # TutorNote и WorkDifficulty из problems.models не реэкспортируются.
        from problems.models_platform import TutorNote
        users = self._demo_users()
        if not users:
            return
        LearningEvent.objects.filter(user__in=users).delete()
        DailySummary.objects.filter(user__in=users).delete()
        EarnedAchievement.objects.filter(user__in=users).delete()
        PersonalRecord.objects.filter(user__in=users).delete()
        StudentTopicProgress.objects.filter(student__in=users).delete()
        StudentSkillProgress.objects.filter(student__in=users).delete()
        StudentProgressProfile.objects.filter(user__in=users).delete()
        Submission.objects.filter(student__in=users).delete()
        # Работы автора-репетитора: каскадом уходят позиции, сдачи, проверки,
        # попытки контрольных, оценки сложности, комментарии ко всей работе.
        Assignment.objects.filter(author__in=users).delete()
        TutorNote.objects.filter(tutor__in=users).delete()

    def _purge(self):
        """Откат: удалить ВСЁ демо, включая аккаунты и группу."""
        from problems.models import StudentGroup, User
        users = self._demo_users()
        if not users:
            self.stdout.write('Демо-аккаунтов нет — удалять нечего.')
            return
        self.tutor = next((u for u in users if u.username == logins_for(self.opts['username'])['tutor']), None)
        self._erase_content()
        StudentGroup.objects.filter(teacher__in=users).delete()
        names = [u.username for u in users]
        User.objects.filter(pk__in=[u.pk for u in users]).delete()
        self._drop_caches(users)
        self.stdout.write(self.style.SUCCESS(f'Удалено: аккаунты {", ".join(names)} и всё их содержимое.'))
        self.stdout.write('Справочники (Achievement, MistakeTag, Skill) общие и остаются.')

    def _drop_caches(self, users):
        from problems import stats
        for user in users:
            stats.invalidate(user)
        cache.delete('achv_rarity_map')

    # ЧАСТЬ 2: история решений
    # ЧАСТЬ 3: домашки, контрольные, проверки
    # ЧАСТЬ 4: игра, пересчёт, даты достижений
    # ЧАСТЬ 5: отчёт «факт против цели»
