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
import io
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

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

# ---------------------------------------------------------------------------
# План истории витринного ученика (числа — цели, факт печатается отчётом)
# ---------------------------------------------------------------------------

OTHER = '__other__'   # ось «Прочее» радара: тема, которой нет среди канонических

# (тема, попыток, верных, роль). Роль задаёт сложность задач и владение:
#   mastered — «освоил» (≥15 верных, ≥80 %, ≥3 сложных),
#   confident — «разобрался» (≥8 верных, ≥60 %),
#   weak — доля верных ниже 60 % («стоит подтянуть»),
#   misc — тонкие темы, other — ось «Прочее».
TOPIC_PLAN = [
    ('Эластичность', 100, 90, 'mastered'),
    ('Альтернативные издержки и КПВ', 90, 80, 'mastered'),
    ('Теория фирмы: производство и издержки', 80, 70, 'mastered'),
    ('Совершенная конкуренция', 60, 53, 'mastered'),
    ('Вмешательство государства', 60, 44, 'confident'),
    ('Неравенство доходов', 50, 36, 'confident'),
    ('ВВП и национальные счета', 55, 42, 'confident'),
    ('Финансы и финансовые инструменты', 55, 41, 'confident'),
    ('Монетарная политика', 45, 32, 'confident'),
    ('Инфляция и безработица', 40, 29, 'confident'),
    ('Монополия и ценовая дискриминация', 20, 10, 'weak'),
    ('Олигополия и теория игр', 18, 9, 'weak'),
    ('Международная торговля', 16, 8, 'weak'),
    ('Рынок труда', 22, 15, 'misc'),
    ('Экономический рост и циклы', 18, 13, 'misc'),
    ('Фискальная политика', 14, 10, 'misc'),
    ('Теория потребителя и полезность', 12, 9, 'misc'),
    ('Математика и оптимизация', 15, 11, 'misc'),
    ('Спрос и предложение', 4, 3, 'misc'),
    (OTHER, 20, 14, 'other'),
]

# Веса сложности 1..5 для попытки по роли темы. Осторожно: на XP влияет
# резко (15 / 45 / 90 за сложность 3 / 4 / 5) — подбирается замером.
DIFF_WEIGHTS = {
    'mastered': (0.17, 0.43, 0.26, 0.10, 0.04),
    'confident': (0.19, 0.44, 0.27, 0.08, 0.02),
    'weak': (0.16, 0.38, 0.29, 0.12, 0.05),
    'misc': (0.21, 0.45, 0.24, 0.08, 0.02),
    'other': (0.25, 0.47, 0.19, 0.07, 0.02),
}

# (тема, название, номинальный отступ в днях назад, исход)
# исход: reviewed — сдана и проверена; late — то же, но с опозданием;
# submitted — сдана, ждёт проверки (две самые свежие); none — не сдана вовсе
# (старая, НЕ последняя: иначе витринный ученик попал бы в «Требуют внимания»).
HOMEWORKS = [
    ('Альтернативные издержки и КПВ', 'КПВ и альтернативные издержки', 84, 'reviewed'),
    ('Эластичность', 'Эластичность: расчёты', 77, 'reviewed'),
    ('Теория фирмы: производство и издержки', 'Издержки фирмы и оптимальный выпуск', 70, 'late'),
    ('Совершенная конкуренция', 'Совершенная конкуренция: равновесие и излишек', 51, 'reviewed'),
    ('Монополия и ценовая дискриминация', 'Монополия и ценовая дискриминация', 44, 'late'),
    ('Вмешательство государства', 'Налоги, субсидии и потери благосостояния', 37, 'reviewed'),
    ('Неравенство доходов', 'Кривая Лоренца и индекс Джини', 32, 'none'),
    ('ВВП и национальные счета', 'ВВП: способы расчёта', 25, 'reviewed'),
    ('Инфляция и безработица', 'Инфляция и безработица', 18, 'reviewed'),
    ('Монетарная политика', 'Денежная политика центробанка', 11, 'reviewed'),
    ('Олигополия и теория игр', 'Олигополия: равновесие по Нэшу', 3, 'submitted'),
    ('Финансы и финансовые инструменты', 'Финансы: проценты и облигации', 1, 'submitted'),
]
# (название, отступ в днях, [(тема, сколько задач)], сколько из них неверно)
EXAMS = [
    ('Контрольная №1: микроэкономика', 47,
     [('Эластичность', 3), ('Альтернативные издержки и КПВ', 3),
      ('Теория фирмы: производство и издержки', 2), ('Совершенная конкуренция', 2)], 1),
    ('Контрольная №2: макроэкономика и рынки', 9,
     [('ВВП и национальные счета', 2), ('Инфляция и безработица', 2),
      ('Монетарная политика', 2), ('Финансы и финансовые инструменты', 2),
      ('Вмешательство государства', 2), ('Неравенство доходов', 2)], 7),
]

# Метки ошибок и их вес в проверках репетитора: распределение НЕРАВНОМЕРНОЕ —
# блок «Что отмечает преподаватель» осмыслен, только когда видно, что одна-две
# ошибки повторяются. Первые три имени уже есть в справочнике (seed_demo).
MISTAKE_TAGS = [
    ('Арифметическая ошибка в вычислениях', 34),
    ('Эластичность без модуля', 24),
    ('Путает сдвиг и движение вдоль кривой', 18),
    ('Забыл ограничение (область определения)', 12),
    ('Игнорирует доминирующую стратегию', 7),
    ('Не проверил единицы измерения', 5),
]
# (навык, уровень 0–100)
SKILLS = [
    ('Построить КПВ', 88), ('Считать эластичность', 84), ('Читать и строить графики', 76),
    ('Найти MR', 70), ('Посчитать DWL', 62), ('Написать интерпретацию', 51),
    ('Проверить NE', 38),
]
COMMENT_FULL = ('', '', 'Верно.', 'Хорошее решение.', 'Всё чисто, ход мысли понятен.')
COMMENT_PART = ('Ход верный, но часть баллов потеряна — проверь вычисления.',
                'Почти. Обрати внимание на ограничения в условии.',
                'Идея правильная, оформление краткое — распиши шаги.')
COMMENT_FAIL = ('Смотри разбор: неверно выбрана модель. Разберём на занятии.',
                'Не хватает ключевого шага. Вернись к теории по этой теме.',
                'Решение не приводит к ответу — давай посмотрим вместе.')
WORK_COMMENTS = {
    'high': 'Сильная работа: чистые выкладки и верные выводы. Так держать.',
    'mid': 'Хорошая работа, но есть повторяющиеся мелкие ошибки — разберём на занятии.',
    'low': 'Работа тяжёлая. Пройдись по теории темы и пересдай слабые задачи.',
}
TUTOR_NOTE = ('Сильная база по микроэкономике и издержкам. Теория игр и монополия — '
              'слабое место: на следующем занятии разбираем олигополию и ценовую '
              'дискриминацию. Хорошо держит темп, после отпуска вернулся без просадки.')

RUN_LENGTH = 27          # верных подряд: «Двадцать пять» получено, «Пятьдесят» — нет
WEEKDAY_WEIGHT = (1.0, 1.0, 1.0, 1.0, 1.0, 0.55, 0.55)   # будни плотнее выходных


class _DryRun(Exception):
    """Служебное: откатить транзакцию сухого прогона."""


@dataclass
class Slot:
    """Одно учебное событие до записи в базу."""
    topic: object
    problem: object
    diff: int
    outcome: str                    # 'solved' | 'failed'
    source: str = 'catalog'         # catalog | homework | exam | game
    work: object = None             # WorkSpec для homework / exam
    when: datetime = None           # локальное МСК-время (aware)
    seconds: int = 0
    payload: dict = field(default_factory=dict)


@dataclass
class WorkSpec:
    """Работа (домашка/контрольная) до записи в базу."""
    idx: int
    kind: str                       # 'homework' | 'exam'
    title: str
    entries: list                   # [(задача, тема, сложность, слот | None)]
    status: str                     # reviewed | submitted | none
    nominal_offset: int
    submit_offset: int = None       # None — витринный ученик не сдавал
    late: bool = False
    assignment: object = None       # Assignment после записи

    @property
    def slots(self):
        return [e[3] for e in self.entries if e[3] is not None]


class TopicPool:
    """Видимые задачи одной темы: с реальной сложностью и без неё.

    У 76 % видимых задач сложность NULL. Как и `seed_platform_demo`, для
    таких задач сложность события берётся из демо-распределения; реальную
    (`Problem.difficulty`) берём, когда она есть и подходит."""

    def __init__(self, topic, problems, rng):
        self.topic = topic
        self.real = defaultdict(list)
        self.nulls = []
        for problem in problems:
            (self.real[problem.difficulty] if problem.difficulty else self.nulls).append(problem)
        for lst in (*self.real.values(), self.nulls):
            rng.shuffle(lst)
        self.everything = [p for p in problems]

    def take(self, want, used, rng):
        """Задача под желаемую сложность: реальная той же сложности, иначе
        без сложности (ей присваивается желаемая), иначе любая свободная."""
        for problem in self.real.get(want, ()):
            if problem.pk not in used:
                used.add(problem.pk)
                return problem, want
        for problem in self.nulls:
            if problem.pk not in used:
                used.add(problem.pk)
                return problem, want
        for level in (5, 4, 3, 2, 1):
            for problem in self.real.get(level, ()):
                if problem.pk not in used:
                    used.add(problem.pk)
                    return problem, level
        problem = rng.choice(self.everything)      # пул исчерпан — повтор
        return problem, problem.difficulty or want


def apportion(total, weights, minimums):
    """Разложить `total` по ключам пропорционально `weights` (не меньше `minimums`)."""
    keys = list(weights)
    base = {k: minimums[k] for k in keys}
    rest = max(0, total - sum(base.values()))
    wsum = sum(weights.values()) or 1
    shares = {k: rest * weights[k] / wsum for k in keys}
    out = {k: base[k] + int(shares[k]) for k in keys}
    left = total - sum(out.values())
    for k in sorted(keys, key=lambda k: (shares[k] - int(shares[k]), k), reverse=True):
        if left <= 0:
            break
        out[k] += 1
        left -= 1
    return out


def sample_without_replacement(rng, population, weights, k):
    """k элементов без возвращения с вероятностью ∝ вес (Эфраимидис — Спиракис)."""
    keyed = sorted(((rng.random() ** (1.0 / w), item) for item, w in zip(population, weights)),
                   reverse=True)
    return {item for _, item in keyed[:k]}


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
        """Заполнить содержимое демо-аккаунтов."""
        self.rng = random.Random(self.opts['seed'])
        self._load_pools()
        self._plan_main()
        self._plan_mates()
        self._write_catalog_events()
        self._write_works()
        self._write_extras()
        self._write_game()
        self._gamify()
        self._report()

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

    # -----------------------------------------------------------------------
    # ЧАСТЬ 2: история решений
    # -----------------------------------------------------------------------

    def _load_pools(self):
        """Видимые задачи каталога по темам — ЗАПРОСОМ, а не по номерам:
        на бою банк другой. Фильтр тот же, что `catalog/views.py::_visible_problem`."""
        from problems.models import Problem
        from problems.sections import CANONICAL_SECTION
        visible = (Problem.objects
                   .filter(status=Problem.Status.PUBLISHED, needs_quality_review=False,
                           hidden_pending_review=False,
                           content_status=Problem.ContentStatus.OK)
                   .prefetch_related('topics').order_by('pk'))
        by_topic = defaultdict(list)      # имя темы -> [(задача)]
        topic_obj = {}
        other = defaultdict(list)
        other_obj = {}
        for problem in visible:
            topics = list(problem.topics.all())        # порядок Topic.order, name
            if not topics:
                continue
            canon = [t for t in topics if t.name in CANONICAL_SECTION]
            if canon:
                by_topic[canon[0].name].append(problem)     # первая каноническая тема
                topic_obj.setdefault(canon[0].name, canon[0])
            else:
                other[topics[0].name].append(problem)
                other_obj.setdefault(topics[0].name, topics[0])
        rng = random.Random(f'{self.opts["seed"]}:pools')
        self.pools = {name: TopicPool(topic_obj[name], probs, rng)
                      for name, probs in by_topic.items()}
        if other:      # самая «населённая» неканоническая тема — ось «Прочее»
            name = max(other, key=lambda n: (len(other[n]), n))
            self.pools[OTHER] = TopicPool(other_obj[name], other[name], rng)
        with_topic = sum(len(v) for v in by_topic.values()) + sum(len(v) for v in other.values())
        real = sum(1 for v in by_topic.values() for p in v if p.difficulty)
        self.stdout.write(f'Банк: видимых задач с темой {with_topic}, из них с реальной сложностью '
                          f'{real}, каноничных тем {len(by_topic)}.')
        if with_topic < 1500:
            self.stdout.write(self.style.WARNING(
                'Банк тонкий (<1500 видимых задач с темой): задачи в истории будут '
                'повторяться, цели таблицы могут не достичься. Смотрите отчёт ниже '
                'и не записывайте, пока он не зелёный.'))
        missing = [t for t, *_ in TOPIC_PLAN if t not in self.pools]
        if missing:
            self.stdout.write(self.style.WARNING(
                'В банке нет видимых задач по темам: ' + '; '.join(missing) +
                ' — эти темы в истории пропущены.'))

    def _plan_days(self, rng):
        """offset (0 = сегодня) -> вид дня: streak | gap | vac | counted | light.

        Форма истории: свежая серия до СЕГОДНЯ, три дня разрыва, длинная серия
        (нужен непрерывный отрезок ≥30 дней ради «Месяц без пропусков»),
        целая календарная неделя отпуска, дальше разрозненные дни."""
        D, today = self.opts['days'], self.today
        kinds = {}
        s1 = max(3, round(D * 0.2))
        gap = 3 if D >= 21 else 1
        for off in range(s1):
            kinds[off] = 'streak'
        for off in range(s1, s1 + gap):
            kinds[off] = 'gap'
        old_start = s1 + gap
        vacation = set()
        if D >= 60:
            anchor = today - timedelta(days=round(D * 0.66))
            monday = anchor - timedelta(days=anchor.weekday())
            vacation = {(today - (monday + timedelta(days=i))).days for i in range(7)}
        s2_end = (min(vacation) - 1) if vacation else D - 1
        for off in range(old_start, s2_end + 1):
            kinds[off] = 'streak'
        for off in vacation:
            kinds[off] = 'vac'
        scatter = [o for o in range(max(vacation) + 1, D)] if vacation else []
        if scatter:
            target_active = round(D * 0.69)
            have = sum(1 for k in kinds.values() if k == 'streak')
            take = max(2, min(len(scatter), target_active - have))
            chosen = sorted(rng.sample(scatter, take))
            light = set(rng.sample(chosen, max(1, round(take * 0.4))))
            for off in chosen:
                kinds[off] = 'light' if off in light else 'counted'
        return kinds

    def _plan_main(self):
        """Слоты событий витринного ученика: темы → сложность → исход →
        порядок во времени → дни → часы."""
        rng = random.Random(f'{self.opts["seed"]}:main')
        D = self.opts['days']
        scale = D / 90
        used = self.used_main = set()
        self.topic_slots = {}
        for name, attempts, solved, role in TOPIC_PLAN:
            pool = self.pools.get(name)
            if pool is None:
                continue
            A = max(3, round(attempts * scale))
            S = min(A, max(1, round(A * solved / attempts)))
            self.topic_slots[name] = self._topic_slots(rng, pool, A, S, role, used)
        self.kinds = self._plan_days(rng)
        self._plan_works(rng)
        self._schedule_main(rng)

    def _topic_slots(self, rng, pool, A, S, role, used):
        weights = DIFF_WEIGHTS[role]
        diffs = [rng.choices((1, 2, 3, 4, 5), weights)[0] for _ in range(A)]
        # Трудные задачи чаще решаются неверно, чем лёгкие.
        fails = sample_without_replacement(rng, range(A), [1 + 1.2 * (d - 1) for d in diffs], A - S)
        slots = []
        for i, want in enumerate(diffs):
            problem, diff = pool.take(want, used, rng)
            slots.append(Slot(topic=pool.topic, problem=problem, diff=diff,
                              outcome='failed' if i in fails else 'solved'))
        return slots

    def _day_counts(self, rng, total_events):
        """Сколько событий в каждый активный день (offset -> число)."""
        light = {o: rng.randint(1, 2) for o, k in self.kinds.items() if k == 'light'}
        counted = [o for o, k in self.kinds.items() if k in ('streak', 'counted')]
        rest = max(total_events - sum(light.values()), 3 * len(counted))
        weights = {o: WEEKDAY_WEIGHT[(self.today - timedelta(days=o)).weekday()]
                   * rng.uniform(0.6, 1.5) for o in counted}
        minimum = {o: 3 for o in counted}
        for work in self.works:                  # день с работой вмещает её целиком
            if work.submit_offset in minimum:
                minimum[work.submit_offset] = len(work.slots) + 2
        rest = max(rest, sum(minimum.values()))
        counts = apportion(rest, weights, minimum)
        counts.update(light)
        return counts

    def _host_day(self, target, taken):
        """Ближайший к `target` обычный день, куда можно поставить сдачу работы."""
        ok = [o for o, k in self.kinds.items()
              if k in ('streak', 'counted') and o >= 1 and o not in taken]
        return min(ok, key=lambda o: (abs(o - target), o))

    def _plan_works(self, rng):
        """Домашки и контрольные. Их события вынимаются из тематических
        слотов, а не рождаются рядом: иначе разбивка «где решаешь» разошлась
        бы с числом сданных работ, а квоты тем — с картой тем."""
        D = self.opts['days']
        full = D >= 60
        hw_defs = HOMEWORKS if full else [HOMEWORKS[i] for i in (1, 4, 6, 10)]
        ex_defs = EXAMS if full else EXAMS[:1]
        self.works, taken = [], set()
        for idx, (topic, title, nominal, mode) in enumerate(hw_defs):
            pool, slots = self.pools.get(topic), self.topic_slots.get(topic)
            if pool is None or not slots:
                continue
            n = rng.randint(5, 8)
            work = WorkSpec(idx=idx, kind='homework', title=title, entries=[],
                            status='reviewed' if mode in ('reviewed', 'late') else mode,
                            late=(mode == 'late'), nominal_offset=max(1, round(nominal * D / 90)))
            if mode == 'none':      # работа выдана, но витринный ученик её не сдал
                for _ in range(n):
                    problem, diff = pool.take(3, self.used_main, rng)
                    work.entries.append((problem, pool.topic, diff, None))
            else:
                free = [s for s in slots if s.source == 'catalog']
                for slot in rng.sample(free, min(n, len(free))):
                    slot.source, slot.work = 'homework', work
                    work.entries.append((slot.problem, slot.topic, slot.diff, slot))
                work.submit_offset = self._host_day(work.nominal_offset, taken)
                taken.add(work.submit_offset)
            if len(work.entries) >= 3:
                self.works.append(work)
        for idx, (title, nominal, quota, fails) in enumerate(ex_defs, start=100):
            work = WorkSpec(idx=idx, kind='exam', title=title, entries=[], status='reviewed',
                            nominal_offset=max(1, round(nominal * D / 90)))
            free = {t: [s for s in self.topic_slots.get(t, []) if s.source == 'catalog']
                    for t, _ in quota}
            for lst in free.values():
                rng.shuffle(lst)
            picked = {t: [] for t, _ in quota}
            room = {t: k for t, k in quota}
            need_fail = min(fails, sum(len([s for s in v if s.outcome == 'failed']) for v in free.values()))
            for outcome, wanted in (('failed', need_fail), ('solved', None)):
                for t in [t for t, _ in quota]:
                    for slot in [s for s in free[t] if s.outcome == outcome]:
                        if room[t] <= 0 or (wanted is not None and wanted <= 0):
                            break
                        picked[t].append(slot)
                        room[t] -= 1
                        wanted = wanted - 1 if wanted is not None else None
            for t, chosen in picked.items():
                for slot in chosen:
                    slot.source, slot.work = 'exam', work
                    work.entries.append((slot.problem, slot.topic, slot.diff, slot))
            if len(work.entries) >= 3:
                work.submit_offset = self._host_day(work.nominal_offset, taken)
                taken.add(work.submit_offset)
                self.works.append(work)
        self.work_slots = [s for w in self.works for s in w.slots]

    def _schedule_main(self, rng):
        """Разложить оставшиеся («каталожные») слоты по дням и часам."""
        total = sum(len(v) for v in self.topic_slots.values())   # работы уже внутри
        self.day_counts = self._day_counts(rng, total)
        # Дни, где стоят домашки/контрольные, отдают им часть своей квоты.
        cluster_days = defaultdict(list)          # offset -> [WorkSpec]
        for work in self.works:
            if work.submit_offset is not None:
                cluster_days[work.submit_offset].append(work)
        catalog = []
        centers = {}
        for name, slots in self.topic_slots.items():
            role = next(r for t, _a, _s, r in TOPIC_PLAN if t == name)
            centers[name] = (rng.uniform(0.7, 0.95) if role == 'weak'
                             else rng.uniform(0.15, 0.6) if role == 'mastered'
                             else rng.uniform(0.1, 0.9))
            for slot in slots:
                if slot.source == 'catalog':
                    catalog.append((centers[name] + rng.gauss(0, 0.28), slot))
        catalog.sort(key=lambda pair: pair[0])
        ordered = [slot for _, slot in catalog]
        offsets = sorted(self.day_counts, reverse=True)            # от старых к новым
        quota = {o: max(0, self.day_counts[o] - sum(len(w.slots) for w in cluster_days.get(o, ())))
                 for o in offsets}
        overflow = len(ordered) - sum(quota.values())
        for o in reversed(offsets):        # лишнее — в самые свежие/жирные дни
            if overflow <= 0:
                break
            quota[o] += 1
            overflow -= 1
        by_day, cursor = {}, 0
        for o in offsets:
            by_day[o] = ordered[cursor:cursor + quota[o]]
            cursor += quota[o]
        for slot in ordered[cursor:]:
            by_day[offsets[-1]].append(slot)
        self._plant_run(rng, ordered, by_day, cluster_days)
        used_times = set()
        for o in offsets:
            day = self.today - timedelta(days=o)
            self._place_day(rng, day, by_day[o], [w.slots for w in cluster_days.get(o, ())],
                            used_times)
        self.catalog_slots = ordered

    def _plant_run(self, rng, ordered, by_day, cluster_days):
        """Заложить один непрерывный кусок из RUN_LENGTH верных подряд по
        ВСЕМ событиям (домашка и игра в это окно не попадают) — ради
        достижения «Двадцать пять подряд». Пятьдесят подряд при доле верных
        ~78 % не набирается случайно."""
        self.run_dates = set()
        L = min(RUN_LENGTH, max(10, len(ordered) // 8))
        offs = sorted(by_day, reverse=True)
        s2 = [o for o in offs if self.kinds.get(o) == 'streak' and o >= 21 and o not in cluster_days]
        candidates = s2[len(s2) // 3:] or [o for o in offs if o not in cluster_days]
        for start_off in candidates:
            span, count = [], 0
            for o in offs[offs.index(start_off):]:
                if o in cluster_days:
                    break
                span.append(o)
                count += len(by_day[o])
                if count >= L:
                    break
            if count < L:
                continue
            first = sum(len(by_day[o]) for o in offs[:offs.index(start_off)])
            window = range(first, first + L)
            for i in window:
                if ordered[i].outcome == 'failed':
                    self._swap_to_solved(rng, ordered, i, window)
            # Соседи окна — неверные: серия ровно L, а не L + случайный хвост.
            for i in (first - 1, first + L):
                if 0 <= i < len(ordered) and ordered[i].outcome == 'solved':
                    self._swap_to_failed(rng, ordered, i, window)
            self.run_dates = {self.today - timedelta(days=o) for o in span}
            return

    def _swap_to_solved(self, rng, ordered, i, window):
        """Поменять исход «неверно» в окне на «верно» с ближайшей по теме
        задачей вне окна — квота верных по теме остаётся прежней."""
        slot = ordered[i]
        same = [j for j, s in enumerate(ordered)
                if s.outcome == 'solved' and j not in window and s.topic is slot.topic]
        pool = same or [j for j, s in enumerate(ordered) if s.outcome == 'solved' and j not in window]
        if pool:
            j = rng.choice(pool)
            ordered[j].outcome, slot.outcome = 'failed', 'solved'

    def _swap_to_failed(self, rng, ordered, i, window):
        slot = ordered[i]
        near = set(range(window.start - 2, window.stop + 2))
        same = [j for j, s in enumerate(ordered)
                if s.outcome == 'failed' and j not in near and s.topic is slot.topic]
        pool = same or [j for j, s in enumerate(ordered) if s.outcome == 'failed' and j not in near]
        if pool:
            j = rng.choice(pool)
            ordered[j].outcome, slot.outcome = 'solved', 'failed'

    def _place_day(self, rng, day, catalog, clusters, used):
        """Проставить время всем событиям дня (МСК): будни 16–22 с пиком
        18–20, выходные 11–16; между событиями 4–12 минут."""
        weekend = day.weekday() >= 5
        hour = (rng.choices((11, 12, 13, 14, 15), (1, 2, 3, 2, 1))[0] if weekend
                else rng.choices((16, 17, 18, 19, 20, 21), (1, 2, 4, 4, 3, 1))[0])
        start = datetime.combine(day, time(hour, rng.randint(0, 45), rng.randint(0, 59)))
        blocks = [(catalog, (240, 720))]
        for cluster in clusters:
            blocks.append((cluster, (360, 900)))
        seq, cursor = [], start
        for slots, (lo, hi) in blocks:
            for slot in slots:
                seq.append((slot, cursor))
                cursor += timedelta(seconds=rng.randint(lo, hi))
            cursor += timedelta(minutes=rng.randint(20, 40))
        if not seq:
            return
        last = seq[-1][1]
        limit = datetime.combine(day, time(23, 40))
        if day == self.today:
            limit = timezone.localtime(self.now).replace(tzinfo=None) - timedelta(minutes=3)
        if last > limit:
            shift = last - limit
            first_allowed = datetime.combine(day, time(0, 1))
            if seq[0][1] - shift < first_allowed:       # рано утром: сжать
                step = max(timedelta(seconds=20), (limit - first_allowed) / max(1, len(seq)))
                seq = [(s, first_allowed + step * i) for i, (s, _) in enumerate(seq)]
            else:
                seq = [(s, t - shift) for s, t in seq]
        for slot, t in seq:
            while t in used:
                t += timedelta(seconds=1)
            used.add(t)
            slot.when = timezone.make_aware(t, self.tz)
            slot.seconds = min(900, max(60, int(rng.gauss(120 + 130 * (slot.diff or 2), 90))))

    def _plan_mates(self):
        """Одноклассники: та же механика, но легче и по-разному. Один отстал
        (последний день — 16 дней назад), иначе «Требуют внимания» пусто."""
        D, scale = self.opts['days'], self.opts['days'] / 90
        names = [t for t, *_ in TOPIC_PLAN if t in self.pools and t != OTHER]
        profiles = [   # (попыток, доля верных, активных дней, первый offset, последний offset, «хвост до сегодня»)
            (300, 0.85, 52, 0, 89, 9),
            (230, 0.72, 44, 2, 89, 0),
            (160, 0.60, 36, 16, 80, 0),
        ]
        self.mate_slots, self.mate_last, self.mate_used = {}, {}, {}
        for mate, (n, acc, active, first, last, tail) in zip(self.mates, profiles):
            rng = random.Random(f'{self.opts["seed"]}:{mate.username}')
            n = max(24, round(n * scale))
            first, last = min(first, D - 1), min(last, D - 1)
            span = list(range(first, last + 1))
            active = min(len(span), max(6, round(active * scale)))
            forced = [o for o in range(first, first + tail) if o in span]
            rest = [o for o in span if o not in forced]
            offsets = sorted(set(forced) | set(rng.sample(rest, max(0, active - len(forced)))))
            weights = {o: WEEKDAY_WEIGHT[(self.today - timedelta(days=o)).weekday()]
                       * rng.uniform(0.5, 1.5) for o in offsets}
            counts = apportion(n, weights, {o: 3 for o in offsets})
            picked = rng.sample(names, min(len(names), rng.randint(9, 12)))
            shares = {t: rng.uniform(0.4, 1.6) * (len(self.pools[t].everything) ** 0.5)
                      for t in picked}
            per_topic = apportion(n, shares, {t: 2 for t in picked})
            used, slots = set(), []
            for t, a in per_topic.items():
                slots += self._topic_slots(rng, self.pools[t], a, round(a * acc), 'misc', used)
            rng.shuffle(slots)
            times, cursor, by_day = set(), 0, {}
            for o in sorted(offsets, reverse=True):
                by_day[o] = slots[cursor:cursor + counts[o]]
                cursor += counts[o]
            by_day[min(offsets)] += slots[cursor:]
            for o, day_slots in by_day.items():
                self._place_day(rng, self.today - timedelta(days=o), day_slots, [], times)
            self.mate_slots[mate.pk] = slots
            self.mate_last[mate.pk] = min(offsets)
            self.mate_used[mate.pk] = times

    def _save_events(self, user, slots):
        """bulk_create + bulk_update(created_at): created_at — auto_now_add, а
        bulk_create перетирает переданную дату. bulk_update не зовёт pre_save,
        так что задуманная дата остаётся. Тест 3 держит эту ловушку."""
        from problems.models import LearningEvent
        objs = []
        for slot in slots:
            objs.append(LearningEvent(
                user=user, source=slot.source, event_type=slot.outcome,
                catalog_problem=slot.problem, topic=slot.topic, difficulty=slot.diff,
                assignment=getattr(slot.work, 'assignment', None) if slot.work else None,
                time_spent_seconds=slot.seconds,
                payload={DEMO_MARKER: True, **slot.payload}))
        LearningEvent.objects.bulk_create(objs, batch_size=400)
        if any(o.pk is None for o in objs):
            raise CommandError('База не вернула pk после bulk_create: нужна SQLite ≥ 3.35 '
                               'или PostgreSQL.')
        for obj, slot in zip(objs, slots):
            obj.created_at = slot.when
        LearningEvent.objects.bulk_update(objs, ['created_at'], batch_size=400)
        return objs

    def _write_catalog_events(self):
        objs = self._save_events(self.student, self.catalog_slots)
        self.stdout.write(f'Каталожных событий записано: {len(objs)}.')
        for mate in self.mates:
            self._save_events(mate, self.mate_slots[mate.pk])
        self.stdout.write('Одноклассники: ' + ', '.join(
            f'{m.username} — {len(self.mate_slots[m.pk])}' for m in self.mates) + ' событий.')

    # -----------------------------------------------------------------------
    # ЧАСТЬ 3: домашки, контрольные, проверки
    # -----------------------------------------------------------------------

    def _local(self, day, hour, minute):
        return timezone.make_aware(datetime.combine(day, time(hour, minute)), self.tz)

    def _ensure_tags(self):
        from problems.models import MistakeTag
        return [(MistakeTag.objects.get_or_create(name=name)[0], weight)
                for name, weight in MISTAKE_TAGS]

    def _write_works(self):
        """Работы репетитора, сдачи, проверки, попытки контрольных — и события
        по ним (те же слоты, что вынуты из тематических квот)."""
        from problems.models import Assignment, AssignmentItem
        rng = random.Random(f'{self.opts["seed"]}:works')
        self.tags = self._ensure_tags()
        self.submitted = defaultdict(list)       # pk ученика -> [WorkSpec]
        extra_slots = defaultdict(list)          # pk ученика -> слоты для записи событий
        students = [self.student, *self.mates]
        join = [(0.92, 0.85), (0.75, 0.72), (0.55, 0.60)]       # (сдаёт, доля верных)
        for work in sorted(self.works, key=lambda w: -(w.nominal_offset if w.submit_offset is None
                                                       else w.submit_offset)):
            slots = work.slots
            first = min((s.when for s in slots), default=None)
            last = max((s.when for s in slots), default=None)
            fields = {}
            if work.kind == 'exam':
                deadline = last + timedelta(minutes=30)
                fields = {'exam_mode': 'window', 'starts_at': first - timedelta(minutes=10),
                          'ends_at': deadline}
            elif last is None:      # не сдана: срок прошёл на номинальный день
                deadline = self._local(self.today - timedelta(days=work.nominal_offset), 23, 59)
            else:
                day = timezone.localtime(last).date()
                deadline = self._local(day - timedelta(days=1) if work.late
                                       else day + timedelta(days=1), 23, 59)
            assignment = Assignment.objects.create(
                name=work.title, author=self.tutor, group=self.group,
                deadline=deadline, kind=work.kind, **fields)
            assignment.students.set(students)
            assignment.problems.set([e[0] for e in work.entries])
            Assignment.objects.filter(pk=assignment.pk).update(
                created_at=(first or deadline) - timedelta(days=5))
            work.assignment = assignment
            work.items = [AssignmentItem.objects.create(assignment=assignment, order=i,
                                                        catalog_problem=e[0])
                          for i, e in enumerate(work.entries, start=1)]
            if slots:
                self._submit_work(work, self.student, [e[3] for e in work.entries], rng)
                self.submitted[self.student.pk].append(work)
            for mate, (p_join, acc) in zip(self.mates, join):
                mate_slots = self._mate_slots(work, mate, p_join, acc, rng)
                if mate_slots:
                    self._submit_work(work, mate, mate_slots, rng)
                    self.submitted[mate.pk].append(work)
                    extra_slots[mate.pk] += mate_slots
        self._save_events(self.student, self.work_slots)
        for mate in self.mates:
            if extra_slots[mate.pk]:
                self._save_events(mate, extra_slots[mate.pk])
        n = Counter(w.status for w in self.works)
        self.stdout.write(f'Работ выдано: {len(self.works)} (домашек '
                          f'{sum(1 for w in self.works if w.kind == "homework")}, контрольных '
                          f'{sum(1 for w in self.works if w.kind == "exam")}); витринный ученик: '
                          f'проверено {n["reviewed"]}, ждут проверки {n["submitted"]}, '
                          f'не сдано {n["none"]}.')

    def _mate_slots(self, work, mate, p_join, acc, rng):
        """Слоты одноклассника по работе (или None, если он её не сдавал)."""
        offset = work.submit_offset if work.submit_offset is not None else work.nominal_offset
        if work.submit_offset is None and work.kind == 'homework' and rng.random() > 0.35:
            return None                     # «не сдана» — не сдаёт и большинство группы
        if offset < self.mate_last[mate.pk] or rng.random() > p_join:
            return None                     # уже «пропал» из группы либо не сдал
        slots = [Slot(topic=e[1], problem=e[0], diff=e[2], source=work.kind, work=work,
                      outcome='solved' if rng.random() < acc else 'failed')
                 for e in work.entries]
        used = self.mate_used[mate.pk]
        if work.kind == 'exam':      # внутрь окна главного ученика, чуть позже него
            base = [s.when for s in work.slots]
            for slot, when in zip(slots, base):
                t = timezone.localtime(when).replace(tzinfo=None) + timedelta(
                    minutes=rng.randint(1, 4), seconds=rng.randint(0, 59))
                while t in used:
                    t += timedelta(seconds=1)
                used.add(t)
                slot.when = timezone.make_aware(t, self.tz)
                slot.seconds = rng.randint(120, 600)
        else:
            shift = 1 if (rng.random() < 0.3 and offset > 1) else 0
            self._place_day(rng, self.today - timedelta(days=offset - shift), [], [slots], used)
        return slots

    def _submit_work(self, work, student, slots, rng):
        """Submission (+ проверка) на каждую позицию; событие получает pk сдачи.
        Домашку, не проверенную репетитором, боевой код журналирует как
        `attempted`; контрольную проверяет машина (reviewed_by = NULL)."""
        from problems.models import Submission, TeacherFeedback
        exam = work.kind == 'exam'
        by_slot_time = sorted(slots, key=lambda s: s.when)
        recent = timezone.localtime(by_slot_time[-1].when).date() >= self.today - timedelta(days=3)
        reviewed = exam or (work.status == 'reviewed' if student == self.student else not recent)
        for item, slot in zip(work.items, slots):
            problem = item.catalog_problem
            sub = Submission.objects.create(
                student=student, assignment=work.assignment, problem=problem, problem_item=item,
                status='reviewed' if reviewed else 'submitted', submitted_at=slot.when,
                submitted_answer=(((problem.answer or '').strip()[:80] or 'см. решение')
                                  if slot.outcome == 'solved' else 'Ответ получить не удалось'),
                solution_text=('Решил(а) по стандартной схеме: записал условия и нашёл ответ.'
                               if slot.outcome == 'solved'
                               else 'Дошёл(ла) до середины, финальный шаг не получился.'))
            slot.payload['submission_id'] = sub.pk
            if not reviewed:
                slot.outcome = 'attempted'
                continue
            points = Decimal(str(item.points or 1))
            factor = (rng.choice((1, 1, 1, 1, 0.9, 0.8, 0.7)) if slot.outcome == 'solved'
                      else rng.choice((0, 0, 0, 0.05)))
            score = (points * Decimal(str(factor)) * 2).quantize(Decimal('1'), ROUND_HALF_UP) / 2
            full = score >= points
            comment = '' if exam else rng.choice(
                COMMENT_FULL if full else COMMENT_PART if slot.outcome == 'solved' else COMMENT_FAIL)
            feedback = TeacherFeedback.objects.create(
                submission=sub, score=score, comment=comment,
                reviewed_by=None if exam else self.tutor)
            if not full and not exam:
                tags = rng.choices([t for t, _ in self.tags], [w for _, w in self.tags],
                                   k=1 if rng.random() < 0.7 else 2)
                feedback.mistakes.set(set(tags))
            TeacherFeedback.objects.filter(pk=feedback.pk).update(
                reviewed_at=min(self.now - timedelta(minutes=1),
                                slot.when + timedelta(hours=rng.randint(6, 40)) if not exam
                                else slot.when + timedelta(minutes=5)))
        if exam:
            from problems.models import ExamAttempt
            first, last = by_slot_time[0].when, by_slot_time[-1].when
            attempt = ExamAttempt.objects.create(
                assignment=work.assignment, student=student,
                expires_at=work.assignment.ends_at, submitted_at=last + timedelta(minutes=3))
            ExamAttempt.objects.filter(pk=attempt.pk).update(started_at=first - timedelta(minutes=3))
        elif reviewed and student == self.student:
            from problems.models import WorkFeedback
            done = sum(1 for s in slots if s.outcome == 'solved') / max(1, len(slots))
            WorkFeedback.objects.update_or_create(
                assignment=work.assignment, student=student,
                defaults={'author': self.tutor,
                          'comment': WORK_COMMENTS['high' if done >= 0.8 else 'mid' if done >= 0.55 else 'low']})

    def _write_extras(self):
        """Навыки, оценки сложности работ (ставит ученик), заметка репетитора."""
        from problems.models import Skill, StudentSkillProgress
        from problems.models_platform import TutorNote, WorkDifficulty
        for name, level in SKILLS:
            skill, _ = Skill.objects.get_or_create(name=name)
            StudentSkillProgress.objects.update_or_create(
                student=self.student, skill=skill, defaults={'level': level})
        votes = {self.student.pk: (4, 5, 6, 6, 7, 6, 7), self.mates[0].pk: (5, 6, 5),
                 self.mates[1].pk: (6, 7)}
        for user in (self.student, *self.mates):
            homework = [w for w in self.submitted[user.pk] if w.kind == 'homework'
                        and (user != self.student or w.status == 'reviewed')]
            homework.sort(key=lambda w: w.assignment.pk)
            for work, value in zip(homework, votes.get(user.pk, ())):
                WorkDifficulty.objects.update_or_create(
                    assignment=work.assignment, student=user, defaults={'value': value})
        TutorNote.objects.update_or_create(tutor=self.tutor, student=self.student,
                                           defaults={'text': TUTOR_NOTE})

    # -----------------------------------------------------------------------
    # (конец части 3)
    # -----------------------------------------------------------------------
    # ЧАСТЬ 4: игра, пересчёт, даты достижений
    # -----------------------------------------------------------------------

    def _write_game(self):
        """События Wecon Rush (source='game'). GameResult НЕ создаём — см.
        docstring модуля. Сессии — вечером после обычных занятий дня, в дни,
        которые не пересекают окно «верных подряд»; у КАЖДОГО события тема,
        иначе список «Чаще всего промахиваешься в игре» пуст."""
        rng = random.Random(f'{self.opts["seed"]}:game')
        scale = self.opts['days'] / 90
        total = max(24, round(200 * scale))
        sessions = max(3, round(14 * scale))
        last_of_day = {}
        for slot in [*self.catalog_slots, *self.work_slots]:
            day = timezone.localtime(slot.when).date()
            last_of_day[day] = max(last_of_day.get(day, slot.when), slot.when)
        days = sorted(d for d in last_of_day
                      if d < self.today and d not in self.run_dates
                      and self.kinds.get((self.today - d).days) in ('streak', 'counted'))
        days = sorted(rng.sample(days, min(sessions, len(days))))
        modes = [('bullet', 'blitz', 'rapid', 'classic')[i % 4] for i in range(len(days))]
        rng.shuffle(modes)
        weak = [t for t, _a, _s, role in TOPIC_PLAN if role == 'weak' and t in self.pools]
        every = [t for t, *_ in TOPIC_PLAN if t in self.pools and t != OTHER]
        per = apportion(total, {d: 1 for d in days}, {d: 1 for d in days})
        used = {timezone.localtime(s.when).replace(tzinfo=None)
                for s in [*self.catalog_slots, *self.work_slots]}
        slots = []
        for day, mode in zip(days, modes):
            cursor = (timezone.localtime(last_of_day[day]).replace(tzinfo=None)
                      + timedelta(minutes=rng.randint(15, 30)))
            for _ in range(per[day]):
                solved = rng.random() < 0.65
                name = rng.choice(every if solved else weak * 4 + every)
                t = cursor
                while t in used:
                    t += timedelta(seconds=1)
                used.add(t)
                slots.append(Slot(
                    topic=self.pools[name].topic, problem=None, diff=rng.choice((1, 2, 2, 3)),
                    outcome='solved' if solved else 'failed', source='game',
                    when=timezone.make_aware(t, self.tz), seconds=rng.randint(6, 25),
                    payload={'mode': mode}))
                cursor += timedelta(seconds=rng.randint(20, 60))
        self._save_events(self.student, slots)
        self.stdout.write(f'Игра: {len(slots)} событий в {len(days)} сессиях, режимы '
                          f'{", ".join(sorted(set(modes)))}. GameResult не создаётся.')

    def _weekly_goal(self):
        """Цель недели так, чтобы полоса на экране была заполнена на ~80 %:
        60–100 % выглядит живо, 0 и ровно 100 % — как подстроенное."""
        from problems.stats import solved_by_day
        monday = self.today - timedelta(days=self.today.weekday())
        done = sum(v for d, v in solved_by_day(self.student).items() if monday <= d <= self.today)
        return max(3, -(-done * 5 // 4))          # ceil(done / 0.8)

    def _gamify(self):
        """Свёртки — ТОЛЬКО пересчётом из событий, по одному ученику (никогда
        без --user-id: на бою команда без ключа обошла бы всех пользователей)."""
        from problems import stats
        from problems.management.commands.seed_achievements import ACHIEVEMENTS
        from problems.models_gamification import Achievement, StudentProgressProfile
        if Achievement.objects.count() < len(ACHIEVEMENTS):
            # Справочник ОБЩИЙ: заведя его, мы включаем награды для всех
            # учеников платформы, а не только для демо. Поэтому — громко.
            self.stdout.write(self.style.WARNING(
                f'Справочник достижений неполон ({Achievement.objects.count()} из '
                f'{len(ACHIEVEMENTS)}) — завожу его командой seed_achievements. '
                'Он общий для всей платформы.'))
            call_command('seed_achievements', stdout=io.StringIO())
        profile, _ = StudentProgressProfile.objects.get_or_create(user=self.student)
        profile.weekly_goal = self._weekly_goal()          # ДО пересчёта: он её не трогает
        profile.save(update_fields=['weekly_goal'])
        for user in (self.student, *self.mates):
            call_command('recalculate_gamification', user_id=user.pk, verbosity=0)
        for user in (self.student, *self.mates):
            self._backdate(user)
        if self.apply:
            for user in (self.student, *self.mates):
                stats.invalidate(user)
            cache.delete('achv_rarity_map')

    def _backdate(self, user):
        """Даты «получено» и рекордов задним числом: пересчёт пишет их
        «сейчас» (auto_now_add / auto_now), и все награды выглядели бы
        полученными сегодня. Ставим `.update()` на день, когда условие
        впервые выполнилось: реальные правила гоняем по префиксам истории
        в откатываемых точках сохранения (данные не трогаются)."""
        from problems.models import LearningEvent, Submission
        from problems.models_gamification import EarnedAchievement, PersonalRecord
        earned = list(EarnedAchievement.objects.filter(user=user).select_related('achievement'))
        events = list(LearningEvent.objects.filter(user=user).order_by('created_at', 'pk'))
        if not earned or not events:
            return
        local = timezone.localtime
        by_day = defaultdict(list)
        for e in events:
            by_day[local(e.created_at).date()].append(e.created_at)
        for sub in Submission.objects.filter(student=user, submitted_at__isnull=False):
            by_day[local(sub.submitted_at).date()].append(sub.submitted_at)
        days = sorted(by_day)
        step = max(1, len(days) // 40)                       # не больше ~40 проб на ученика
        probes = sorted(set(days[step - 1::step]) | {days[-1]})
        want, found = {e.achievement.code for e in earned}, {}
        for cut in probes:
            end = timezone.make_aware(datetime.combine(cut, time(23, 59, 59)), self.tz)
            point = transaction.savepoint()
            try:
                LearningEvent.objects.filter(user=user, created_at__gt=end).delete()
                Submission.objects.filter(student=user, submitted_at__gt=end).delete()
                EarnedAchievement.objects.filter(user=user).delete()
                PersonalRecord.objects.filter(user=user).delete()
                call_command('recalculate_gamification', user_id=user.pk, verbosity=0)
                got = set(EarnedAchievement.objects.filter(user=user)
                          .values_list('achievement__code', flat=True))
            finally:
                transaction.savepoint_rollback(point)
            for code in got - set(found):
                found[code] = cut
            if want <= set(found):
                break
        weekly = {code: self._goal_week_end(user, int(code.rsplit('_', 1)[1]))
                  for code in want if code.startswith('weekly_goal_')}
        for row in earned:
            code = row.achievement.code
            day = weekly.get(code) or found.get(code) or days[-1]
            stamps = by_day.get(day) or [self.now]
            when = min(self.now - timedelta(minutes=1), max(stamps) + timedelta(minutes=1))
            EarnedAchievement.objects.filter(pk=row.pk).update(earned_at=when)
        self._backdate_records(user, events)

    def _goal_week_end(self, user, weeks):
        """Воскресенье, на котором набралась `weeks`-я подряд неделя с
        выполненной целью (счёт назад от прошлой недели, как в геймификации)."""
        from problems.models_gamification import StudentProgressProfile
        from problems.stats import solved_by_day
        goal = StudentProgressProfile.objects.get(user=user).weekly_goal
        rows = solved_by_day(user)
        monday = self.today - timedelta(days=self.today.weekday())
        run, week = [], monday - timedelta(days=7)
        while sum(v for d, v in rows.items() if week <= d < week + timedelta(days=7)) >= goal:
            run.append(week)
            week -= timedelta(days=7)
        if len(run) < weeks:
            return None
        return run[-1] + timedelta(days=7 * (weeks - 1) + 6)

    def _backdate_records(self, user, events):
        from problems.models_gamification import PersonalRecord
        streak = best = 0
        best_end = None
        for e in events:
            if e.event_type == 'solved':
                streak += 1
                if streak > best:
                    best, best_end = streak, e.created_at
            elif e.event_type == 'failed':
                streak = 0
        for record in PersonalRecord.objects.filter(user=user):
            when = None
            if record.kind == 'best_correct_streak':
                when = best_end
            elif record.kind == 'hardest_solved':
                when = next((e.created_at for e in events if e.event_type == 'solved'
                             and (e.difficulty or 0) >= record.value), None)
            elif record.kind == 'most_productive_day':
                day = record.payload.get('date')
                when = max((e.created_at for e in events if e.event_type == 'solved'
                            and str(timezone.localtime(e.created_at).date()) == day), default=None)
            if when:
                PersonalRecord.objects.filter(pk=record.pk).update(achieved_at=when)

    # -----------------------------------------------------------------------
    # ЧАСТЬ 5: отчёт «факт против цели»
    # -----------------------------------------------------------------------

    def _metrics(self):
        """Числа витринного ученика — ТОЛЬКО из базы, как их увидит экран."""
        from problems.models import LearningEvent
        from problems.sections import section_of
        events = list(LearningEvent.objects.filter(user=self.student)
                      .select_related('topic').order_by('created_at', 'pk'))
        learn = [e for e in events if e.source != 'game']
        tries = [e for e in learn if e.event_type in ('solved', 'failed')]
        solved = [e for e in tries if e.event_type == 'solved']
        days = {timezone.localtime(e.created_at).date() for e in events}
        by_topic = defaultdict(lambda: [0, 0])          # тема -> [попыток, верных]
        for e in tries:
            if e.topic_id:
                by_topic[e.topic.name][0] += 1
                by_topic[e.topic.name][1] += e.event_type == 'solved'
        streak = best = 0
        for e in events:            # серия верных подряд — по ВСЕМ источникам
            if e.event_type == 'solved':
                streak += 1
                best = max(best, streak)
            elif e.event_type == 'failed':
                streak = 0
        src = Counter(e.source for e in tries)
        n = sum(src.values()) or 1
        return {
            'active_days': len(days),
            'solved': len(solved),
            'accuracy': round(100 * len(solved) / max(1, len(tries)), 1),
            'hard_solved': sum(1 for e in solved if (e.difficulty or 0) >= 4),
            'levels': sorted({e.difficulty for e in solved if e.difficulty}),
            'topics': len(by_topic),
            'weak_topics': sum(1 for a, s in by_topic.values() if a >= 5 and s / a < 0.6),
            'sections': len({section_of(t) for t in by_topic}),
            'split': {k: round(100 * src.get(k, 0) / n) for k in ('catalog', 'homework', 'exam')},
            'game': sum(1 for e in events if e.source == 'game'),
            'run': best,
            'events': len(events),
        }

    def _report(self):
        """Таблица «факт против цели» с отметками ✓/✗. Цели — из задания;
        расхождение по источникам (Д1) отмечено в журнале сессии."""
        m = self._metrics()
        g = self._gamification()
        w = self.stdout.write

        def inside(value, lo=None, hi=None):
            return (lo is None or value >= lo) and (hi is None or value <= hi)

        rows = [
            ('активных дней', '52–68 из 90', m['active_days'], inside(m['active_days'], 52, 68)),
            ('решено верно (без игры)', '550–650', m['solved'], inside(m['solved'], 550, 650)),
            ('доля верных, %', '74–82', m['accuracy'], inside(m['accuracy'], 74, 82)),
            ('решено сложности 4–5', '≥55', m['hard_solved'], m['hard_solved'] >= 55),
            ('уровни сложности', 'все пять', ','.join(map(str, m['levels'])), m['levels'] == [1, 2, 3, 4, 5]),
            ('тем затронуто', '≥12', m['topics'], m['topics'] >= 12),
            ('слабых тем (<60 %)', '2–3', m['weak_topics'], inside(m['weak_topics'], 2, 3)),
            ('разделов паутинки непустых', '5 из 5', m['sections'], m['sections'] == 5),
            ('источники catalog/homework/exam, %', '≈45/40/15, см. Д1',
             '/'.join(str(m['split'][k]) for k in ('catalog', 'homework', 'exam')), None),
            ('событий игры', '150–250', m['game'], inside(m['game'], 150, 250)),
            ('верных подряд (макс.)', '25–49', m['run'], inside(m['run'], 25, 49)),
            ('всего событий', '—', m['events'], None),
            ('уровень', '≥12', g['level'], g['level'] >= 12),
            ('опыт', '—', g['xp'], None),
            ('серия текущая / лучшая', '12–25 / ≥30', f'{g["cur"]} / {g["best"]}',
             inside(g['cur'], 12, 25) and g['best'] >= 30),
            ('тем mastered / confident', '≥3 / ≥4', f'{g["mastered"]} / {g["confident"]}',
             g['mastered'] >= 3 and g['confident'] >= 4),
            (f'достижений получено из {g["total"]}', '16–24', g['got'], inside(g['got'], 16, 24)),
            ('достижений НЕ получено', '≥5', g['total'] - g['got'], g['total'] - g['got'] >= 5),
            ('сдано работ / проверено', '10–12 / ≥8', f'{g["submitted"]} / {g["reviewed"]}',
             inside(g['submitted'], 10, 12) and g['reviewed'] >= 8),
            ('контрольных пройдено', '2', g['exams'], g['exams'] == 2),
            ('игра: режимов / тем промахов', '4 / ≥3', f'{g["modes"]} / {g["miss"]}',
             g['modes'] == 4 and g['miss'] >= 3),
            ('недельная цель: сделано / цель', '60–100 %',
             f'{g["done"]} / {g["goal"]} = {g["fill"]} %', inside(g['fill'], 60, 100)),
            ('редкость достижений min / max, %', '—', g['rarity'], None),
            ('навыков / проверок с метками', '5–8 / —', f'{g["skills"]} / {g["tagged"]}',
             inside(g['skills'], 5, 8)),
        ]
        w('')
        w('Факт против цели (витринный ученик):')
        for name, goal, fact, ok in rows:
            mark = '  ' if ok is None else ('✓ ' if ok else '✗ ')
            w(f'  {mark}{name:<36} цель {goal:<20} факт {fact}')
        missed = [name for name, _g, _f, ok in rows if ok is False]
        if missed:
            w(self.style.WARNING('Не достигнуто: ' + '; '.join(missed) +
                                 '. Попробуйте другое зерно: --seed <число>.'))
        else:
            w(self.style.SUCCESS('Все цели достигнуты.'))
        self._report_details()

    def _gamification(self):
        from problems.models import (ExamAttempt, LearningEvent, StudentSkillProgress,
                                     StudentTopicProgress, Submission, TeacherFeedback)
        from problems.models_gamification import (Achievement, EarnedAchievement,
                                                  StudentProgressProfile, rarity_map)
        from problems.stats import solved_by_day
        profile = StudentProgressProfile.objects.filter(user=self.student).first()
        levels = Counter(StudentTopicProgress.objects.filter(student=self.student)
                         .values_list('mastery_level', flat=True))
        rarity = rarity_map() if profile and profile.xp_total else {}
        mine = [rarity[a] for a in EarnedAchievement.objects.filter(user=self.student)
                .values_list('achievement_id', flat=True) if a in rarity]
        works = Submission.objects.filter(student=self.student, assignment__kind='homework',
                                          status__in=('submitted', 'reviewed'))
        game = LearningEvent.objects.filter(user=self.student, source='game')
        monday = self.today - timedelta(days=self.today.weekday())
        done = sum(v for d, v in solved_by_day(self.student).items() if monday <= d <= self.today)
        goal = profile.weekly_goal if profile else 0
        return {
            'level': profile.level if profile else 0, 'xp': profile.xp_total if profile else 0,
            'cur': profile.current_streak if profile else 0,
            'best': profile.longest_streak if profile else 0,
            'mastered': levels['mastered'], 'confident': levels['confident'],
            'total': Achievement.objects.count(),
            'got': EarnedAchievement.objects.filter(user=self.student).count(),
            'submitted': works.values('assignment').distinct().count(),
            'reviewed': works.filter(status='reviewed').values('assignment').distinct().count(),
            'exams': ExamAttempt.objects.filter(student=self.student,
                                                submitted_at__isnull=False).count(),
            'modes': len({e.payload.get('mode') for e in game}),
            'miss': len({e.topic_id for e in game.filter(event_type='failed') if e.topic_id}),
            'done': done, 'goal': goal, 'fill': min(100, round(100 * done / max(1, goal))),
            'rarity': f'{min(mine):.0f} / {max(mine):.0f}' if mine else '—',
            'skills': StudentSkillProgress.objects.filter(student=self.student).count(),
            'tagged': TeacherFeedback.objects.filter(submission__student=self.student,
                                                     mistakes__isnull=False).distinct().count(),
        }

    def _report_details(self):
        """Что не получено, рекорды, метки ошибок: глазами проверить, что
        картина осмысленна, а не только числа сошлись."""
        from problems.models import LearningEvent, TeacherFeedback
        from problems.models_gamification import Achievement, EarnedAchievement, PersonalRecord
        w = self.stdout.write
        have = set(EarnedAchievement.objects.filter(user=self.student)
                   .values_list('achievement__code', flat=True))
        w('  не получено: ' + ', '.join(sorted(Achievement.objects.exclude(code__in=have)
                                                  .values_list('code', flat=True))))
        for r in PersonalRecord.objects.filter(user=self.student):
            w(f'  рекорд {r.kind}: {r.value:g} {r.payload.get("date", "")}')
        tags = Counter()
        for fb in TeacherFeedback.objects.filter(submission__student=self.student).prefetch_related('mistakes'):
            tags.update(m.name for m in fb.mistakes.all())
        w('  метки ошибок: ' + '; '.join(f'{n} ×{c}' for n, c in tags.most_common(4)))
        w('  сводка по классу: ' + ', '.join(
            f'{m.username} {LearningEvent.objects.filter(user=m).count()} соб.'
            for m in self.mates))
