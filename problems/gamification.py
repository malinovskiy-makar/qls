"""
Движок начисления: опыт, уровни, серия дней, владение темами, достижения.

Здесь И ТОЛЬКО ЗДЕСЬ решается, сколько чего начислить. Ни во вьюхах, ни в
шаблонах логики начисления нет: правила заведомо будут меняться (числа ниже
поставлены расчётом, но не замером), и менять их надо в одном месте, а не в
пятнадцати.

Устройство модуля:
  * КОНСТАНТЫ — все числа правил, в начале файла;
  * ЧИСТЫЕ ФУНКЦИИ правил (`xp_for_solved`, `level_for_xp`, `mastery_for`) —
    без базы, их же использует полный пересчёт;
  * ПРИМЕНЕНИЕ к базе (`process_learning_event`) — неблокирующее.

Почему чистые функции отделены от применения: полный пересчёт
(`recalculate_gamification`) проигрывает историю заново и обязан получить
ТЕ ЖЕ числа, что накопились по одному. Общие правила — единственный способ
это гарантировать; две реализации одного правила расходятся всегда.
"""
import logging
from datetime import timedelta

from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


# ===========================================================================
# КОНСТАНТЫ ПРАВИЛ
# ===========================================================================

# --- Опыт за решённую задачу, по сложности --------------------------------
#
# ⚠️ ГЛАВНОЕ ТРЕБОВАНИЕ: решать лёгкое ради очков должно быть НЕВЫГОДНО
# арифметически. Проверяется не «на глаз», а делением опыта на время.
#
# Оценка времени решения (олимпиадная экономика, 10–11 класс):
#   слож. 1 ≈ 1,5 мин · 2 ≈ 3 мин · 3 ≈ 8 мин · 4 ≈ 20 мин · 5 ≈ 35 мин
#
# Числа из первоначального задания (5/5/15/40/40) давали ровно обратное:
#   слож. 1 — 200 опыта/час, слож. 4 — 120, слож. 5 — 69.
# То есть самый быстрый способ качаться — щёлкать простейшие задачи. Правило
# не работало, поэтому числа пересчитаны:
#
#   слож. 1:  2 опыта →  80 опыта/час
#   слож. 2:  5       → 100
#   слож. 3: 15       → 112
#   слож. 4: 45       → 135
#   слож. 5: 90       → 154
#
# Теперь скорость набора РАСТЁТ со сложностью на всём диапазоне: выгоднее
# всего решать самое трудное, что ученику по силам. Ничего не запрещено —
# лёгкие задачи по-прежнему дают опыт, просто медленнее.
XP_BY_DIFFICULTY = {1: 2, 2: 5, 3: 15, 4: 45, 5: 90}

# Сложность не проставлена. В банке таких задач много (импорт), и оценивать
# их щедро нельзя: «задача без сложности» стала бы самым выгодным фармом.
# Берём нижнюю планку и считаем такую задачу лёгкой для правила затухания.
XP_UNKNOWN_DIFFICULTY = 5

# --- Затухание за фарм лёгкого --------------------------------------------
#
# Второй предохранитель, и он важнее первого: соотношение «опыт/час» держится
# на ОЦЕНКАХ времени, а они могут быть неверны. Затухание же не зависит от
# времени вовсе — только от того, сколько лёгких задач уже решено сегодня.
#
# Первые 5 лёгких задач за день — полный опыт (нормальная разминка).
# С 6-й по 15-ю — половина. С 16-й — пятая часть.
# Час фарма лёгкого: 2·5 + 2·0.5·10 + 2·0.2·25 ≈ 30 опыта против 135 у
# сложности 4. Задачам сложности 3+ затухание не грозит НИКОГДА — за
# честную работу не наказываем.
EASY_MAX_DIFFICULTY = 2
EASY_FULL_PER_DAY = 5
EASY_HALF_UNTIL = 15
EASY_HALF_FACTOR = 0.5
EASY_TAIL_FACTOR = 0.2

# --- Прочие начисления ------------------------------------------------------
XP_HOMEWORK_COMPLETE = 30      # за сданную домашку целиком
EXAM_MULTIPLIER = 1.5          # опыт за задачи контрольной

# --- Уровни -----------------------------------------------------------------
#
# Порог для уровня N = 100 × (N−1)^1.5. Сдвиг на единицу против формулы
# задания сделан намеренно: при 100 × N^1.5 ученик с нулём опыта оказывался
# бы НИЖЕ первого уровня, а «нулевой уровень» — это не начало пути, а
# сообщение «ты никто». Пороги: ур.2 — 100, ур.3 — 283, ур.4 — 520,
# ур.5 — 800, ур.10 — 2 546, ур.20 — 8 285.
LEVEL_BASE = 100
LEVEL_POWER = 1.5
MAX_LEVEL = 100

# --- Серия дней -------------------------------------------------------------
#
# День засчитывается, если ученик СДАЛ работу либо сделал ≥3 попыток.
# Одна тривиальная задача поздно вечером день не засчитывает — намеренно:
# иначе серия меряет не занятия, а привычку открывать сайт.
STREAK_MIN_ATTEMPTS = 3
FREEZES_PER_MONTH = 2

# --- Владение темой ---------------------------------------------------------
#
# familiar  — решено ≥3
# confident — решено ≥8 и доля верных ≥60%
# mastered  — решено ≥15, доля ≥80%, из них ≥3 повышенной сложности (4–5)
MASTERY_RULES = (
    # (уровень, решено, доля верных, из них сложных)
    ('mastered', 15, 0.80, 3),
    ('confident', 8, 0.60, 0),
    ('familiar', 3, 0.0, 0),
)
HARD_DIFFICULTY = 4


# ===========================================================================
# ЧИСТЫЕ ФУНКЦИИ ПРАВИЛ (без базы — их же гоняет пересчёт и тесты)
# ===========================================================================

def base_xp(difficulty):
    """Опыт за задачу этой сложности, без множителей."""
    if difficulty is None:
        return XP_UNKNOWN_DIFFICULTY
    return XP_BY_DIFFICULTY.get(int(difficulty), XP_UNKNOWN_DIFFICULTY)


def is_easy(difficulty):
    """Считается ли задача лёгкой для правила затухания.

    Задача без сложности — тоже лёгкая: иначе «сложность не проставлена»
    стала бы дырой, через которую фарм и поехал бы.
    """
    if difficulty is None:
        return True
    return int(difficulty) <= EASY_MAX_DIFFICULTY


def easy_decay(easy_solved_today):
    """Множитель за уже решённые сегодня лёгкие задачи.

    `easy_solved_today` — сколько лёгких уже засчитано ДО этой.
    """
    if easy_solved_today < EASY_FULL_PER_DAY:
        return 1.0
    if easy_solved_today < EASY_HALF_UNTIL:
        return EASY_HALF_FACTOR
    return EASY_TAIL_FACTOR


def xp_for_solved(difficulty, source='catalog', easy_solved_today=0):
    """Опыт за одну верно решённую задачу. Целое число.

    Ошибка опыт не даёт и не отнимает — отнимать нельзя: наказанием за
    попытку решить трудное будет отказ решать трудное.
    """
    value = base_xp(difficulty)
    if is_easy(difficulty):
        value *= easy_decay(easy_solved_today)
    if source == 'exam':
        value *= EXAM_MULTIPLIER
    return int(round(value))


def xp_for_level(level):
    """Сколько опыта нужно, чтобы БЫТЬ на этом уровне."""
    if level <= 1:
        return 0
    return int(LEVEL_BASE * ((level - 1) ** LEVEL_POWER))


def level_for_xp(xp):
    """Уровень по опыту. Минимум — первый."""
    xp = max(0, int(xp or 0))
    level = 1
    while level < MAX_LEVEL and xp >= xp_for_level(level + 1):
        level += 1
    return level


def xp_to_next_level(xp):
    """(сколько осталось до следующего, порог следующего). На потолке — (0, None)."""
    level = level_for_xp(xp)
    if level >= MAX_LEVEL:
        return 0, None
    need = xp_for_level(level + 1)
    return max(0, need - int(xp or 0)), need


def level_progress_percent(xp):
    """Насколько заполнена полоса текущего уровня, 0–100."""
    level = level_for_xp(xp)
    if level >= MAX_LEVEL:
        return 100
    low, high = xp_for_level(level), xp_for_level(level + 1)
    if high <= low:
        return 100
    return int(round((int(xp or 0) - low) * 100.0 / (high - low)))


def mastery_for(solved, attempted, solved_hard):
    """Уровень владения темой по счётчикам."""
    if not solved:
        return 'none'
    ratio = (solved / attempted) if attempted else 0.0
    for level, need_solved, need_ratio, need_hard in MASTERY_RULES:
        if (solved >= need_solved and ratio >= need_ratio
                and solved_hard >= need_hard):
            return level
    return 'none'


def day_counts_for_streak(problems_attempted, submitted_work):
    """Засчитан ли день в серию."""
    return bool(submitted_work) or problems_attempted >= STREAK_MIN_ATTEMPTS


def month_start(day):
    return day.replace(day=1)


# ===========================================================================
# ПРИМЕНЕНИЕ К БАЗЕ
# ===========================================================================

def process_learning_event(event):
    """Точка входа: событие произошло — начисли, что положено.

    ⚠️ НЕБЛОКИРУЮЩАЯ, как и сама запись событий. Ученик сдаёт домашку — он
    должен её сдать, даже если начисление опыта упало на ровном месте. Опыт
    восстановим командой `recalculate_gamification`, потерянную сдачу — нет.
    """
    try:
        return _apply_event(event)
    except Exception:
        logger.exception('Не удалось начислить за событие %s — основной '
                         'сценарий не тронут', getattr(event, 'pk', '?'))
        return None


def _apply_event(event):
    from .models import (DailySummary, StudentProgressProfile,
                         StudentTopicProgress)

    if event is None or event.user_id is None:
        return None

    profile, _ = StudentProgressProfile.objects.get_or_create(user=event.user)
    day = timezone.localtime(event.created_at or timezone.now()).date()
    summary, _ = DailySummary.objects.get_or_create(user_id=event.user_id,
                                                    date=day)

    gained = 0
    if event.event_type in ('attempted', 'failed', 'solved'):
        summary.problems_attempted += 1
    if event.time_spent_seconds:
        summary.time_spent_seconds += int(event.time_spent_seconds)

    if event.event_type == 'solved':
        summary.problems_solved += 1
        if _first_solve(event):
            gained = xp_for_solved(
                event.difficulty, event.source,
                easy_solved_today=_easy_solved_today(event, day))
            summary.xp_earned += gained

    summary.save()

    if gained:
        profile.xp_total += gained
        profile.level = level_for_xp(profile.xp_total)

    _update_topic(event)
    _update_streak(profile, summary, day)
    profile.save()

    update_records(event.user)
    check_achievements(event.user)
    return gained


def _first_solve(event):
    """Даёт ли эта задача опыт впервые.

    Повторное решение той же задачи опыта НЕ даёт: иначе самая выгодная
    стратегия — открывать одну задачу и «решать» её сто раз.
    """
    from .models import LearningEvent

    queryset = LearningEvent.objects.filter(user_id=event.user_id,
                                            event_type='solved')
    if event.catalog_problem_id:
        queryset = queryset.filter(catalog_problem_id=event.catalog_problem_id)
    elif event.custom_problem_id:
        queryset = queryset.filter(custom_problem_id=event.custom_problem_id)
    else:
        # Событие без задачи (игра) — опыт даём, повтор не отследить.
        return True
    return not queryset.exclude(pk=event.pk).filter(
        created_at__lt=event.created_at or timezone.now()).exists()


def _easy_solved_today(event, day):
    """Сколько лёгких задач уже засчитано в этот день ДО текущего события."""
    from .models import LearningEvent

    start = timezone.make_aware(
        timezone.datetime.combine(day, timezone.datetime.min.time()),
        timezone.get_current_timezone())
    return LearningEvent.objects.filter(
        user_id=event.user_id, event_type='solved',
        created_at__gte=start,
        created_at__lt=event.created_at or timezone.now(),
    ).filter(
        models.Q(difficulty__isnull=True)
        | models.Q(difficulty__lte=EASY_MAX_DIFFICULTY)
    ).exclude(pk=event.pk).count()


def _update_topic(event):
    """Пересчёт владения темой — счётчики и уровень."""
    from .models import StudentTopicProgress

    if event.topic_id is None or event.event_type not in ('solved', 'failed'):
        return
    row, _ = StudentTopicProgress.objects.get_or_create(
        student_id=event.user_id, topic_id=event.topic_id)
    row.attempted += 1
    if event.event_type == 'solved':
        row.solved += 1
        if event.difficulty and int(event.difficulty) >= HARD_DIFFICULTY:
            row.solved_hard += 1
    row.mastery_level = mastery_for(row.solved, row.attempted, row.solved_hard)
    row.last_activity_at = event.created_at or timezone.now()
    # Старое поле level (0–100) оставлено и держится в согласии с новым:
    # на него смотрит страница прогресса и панель учителя.
    row.level = min(100, int(round(
        row.solved * 100.0 / max(row.attempted, 1)))) if row.attempted else 0
    row.save()


def _submitted_work_on(user_id, day):
    """Сдавал ли ученик в этот день работу целиком (домашку или контрольную)."""
    from .models import Submission

    return Submission.objects.filter(
        student_id=user_id, submitted_at__date=day,
        status__in=('submitted', 'reviewed')).exists()


def _update_streak(profile, summary, day):
    """Серия дней: продление, заморозка, обнуление.

    Считается ТОЛЬКО в момент, когда день впервые становится зачтённым —
    иначе каждое следующее событие того же дня продлевало бы серию заново.
    """
    if summary.counted_for_streak:
        return          # день уже зачтён, второй раз не продлеваем
    if not day_counts_for_streak(summary.problems_attempted,
                                 _submitted_work_on(profile.user_id, day)):
        return
    summary.counted_for_streak = True
    summary.save(update_fields=['counted_for_streak'])

    _reset_freezes_if_new_month(profile, day)
    last = profile.last_active_date

    if last is None:
        profile.current_streak = 1
    elif last == day:
        return
    else:
        gap = (day - last).days
        if gap == 1:
            profile.current_streak += 1
        elif gap > 1:
            missed = gap - 1
            if missed <= profile.freezes_available:
                # Заморозка спасает серию: пропуск оплачен.
                profile.freezes_available -= missed
                profile.freezes_used_this_month += missed
                profile.current_streak += 1
            else:
                profile.current_streak = 1
    profile.last_active_date = day
    profile.longest_streak = max(profile.longest_streak,
                                 profile.current_streak)


def _reset_freezes_if_new_month(profile, day):
    """Заморозки обновляются первого числа — без фонового задания.

    Обнуление происходит при первом обращении в новом месяце: cron ради двух
    чисел заводить незачем, а «первого числа в 00:00» никому не нужно.
    """
    period = month_start(day)
    if profile.freezes_period != period:
        profile.freezes_period = period
        profile.freezes_available = FREEZES_PER_MONTH
        profile.freezes_used_this_month = 0


def award_homework_bonus(user, assignment):
    """+30 опыта за сданную домашку целиком. Один раз на работу."""
    from .models import DailySummary, LearningEvent, StudentProgressProfile

    try:
        if user is None or not getattr(user, 'is_authenticated', False):
            return 0
        marker = {'homework_bonus': assignment.pk}
        if LearningEvent.objects.filter(
                user=user, assignment=assignment,
                event_type='solved', payload__homework_bonus=assignment.pk
        ).exists():
            return 0

        amount = XP_HOMEWORK_COMPLETE
        if getattr(assignment, 'is_exam', False):
            amount = int(round(amount * EXAM_MULTIPLIER))

        # Отметка живёт событием — так она переживает пересчёт и не требует
        # ещё одного поля. Задачи у неё нет, поэтому в «решено задач» она не
        # попадает (см. фильтр в `user_facts`).
        LearningEvent.objects.create(
            user=user, assignment=assignment,
            source='exam' if assignment.is_exam else 'homework',
            event_type='solved', payload=marker)
        profile, _ = StudentProgressProfile.objects.get_or_create(user=user)
        profile.xp_total += amount
        profile.level = level_for_xp(profile.xp_total)
        profile.save()

        day = timezone.localdate()
        summary, _ = DailySummary.objects.get_or_create(user=user, date=day)
        summary.xp_earned += amount
        summary.save(update_fields=['xp_earned'])
        _update_streak(profile, summary, day)
        profile.save()
        return amount
    except Exception:
        logger.exception('Не удалось начислить бонус за работу')
        return 0


# ===========================================================================
# Личные рекорды
# ===========================================================================

def update_records(user):
    """Обновляет личные рекорды. Рекорд только растёт."""
    from .models import LearningEvent, PersonalRecord

    events = list(LearningEvent.objects.filter(
        user=user, event_type__in=('solved', 'failed'))
        .order_by('created_at').values_list('event_type', 'difficulty',
                                            'created_at'))

    best_row = row = 0
    hardest = 0
    for kind, difficulty, _ in events:
        if kind == 'solved':
            row += 1
            best_row = max(best_row, row)
            if difficulty:
                hardest = max(hardest, int(difficulty))
        else:
            row = 0

    _bump(user, PersonalRecord.Kind.BEST_CORRECT_STREAK, best_row)
    _bump(user, PersonalRecord.Kind.HARDEST_SOLVED, hardest)

    from .models import DailySummary
    best_day = DailySummary.objects.filter(user=user).order_by(
        '-problems_solved').first()
    if best_day is not None:
        _bump(user, PersonalRecord.Kind.MOST_PRODUCTIVE_DAY,
              best_day.problems_solved, {'date': str(best_day.date)})


def _bump(user, kind, value, payload=None):
    from .models import PersonalRecord

    if not value:
        return
    record, created = PersonalRecord.objects.get_or_create(
        user=user, kind=kind, defaults={'value': value,
                                        'payload': payload or {}})
    if not created and value > record.value:
        record.value = value
        record.payload = payload or record.payload
        record.save()


# ===========================================================================
# Достижения
# ===========================================================================

def user_facts(user):
    """Всё, по чему проверяются условия достижений — одним снимком.

    Собирается разом, а не по одному запросу на достижение: достижений
    больше двадцати пяти, и двадцать пять запросов на каждое решение задачи
    — это ровно тот «расчёт на лету», от которого мы уходим.
    """
    from .models import (DailySummary, EarnedAchievement, LearningEvent,
                         PersonalRecord, StudentProgressProfile,
                         StudentTopicProgress, Submission)

    profile = StudentProgressProfile.objects.filter(user=user).first()
    topics = list(StudentTopicProgress.objects.filter(student=user)
                  .values_list('mastery_level', flat=True))
    # Только события С ЗАДАЧЕЙ: служебная отметка «работа сдана целиком»
    # и партии игры задачами не являются и «решено задач» не раздувают.
    solved = LearningEvent.objects.filter(
        user=user, event_type='solved').filter(
        models.Q(catalog_problem__isnull=False)
        | models.Q(custom_problem__isnull=False))
    records = {r.kind: r.value for r in PersonalRecord.objects.filter(user=user)}

    return {
        'level': profile.level if profile else 1,
        'xp': profile.xp_total if profile else 0,
        'streak': profile.longest_streak if profile else 0,
        'topics_mastered': sum(1 for t in topics if t == 'mastered'),
        'topics_confident': sum(1 for t in topics
                                if t in ('confident', 'mastered')),
        'problems_solved': solved.count(),
        'hard_solved': solved.filter(
            difficulty__gte=HARD_DIFFICULTY).count(),
        'correct_in_row': records.get('best_correct_streak', 0),
        'hardest_solved': records.get('hardest_solved', 0),
        'homeworks_submitted': Submission.objects.filter(
            student=user, status__in=('submitted', 'reviewed'),
            assignment__kind='homework').values('assignment').distinct().count(),
        'exams_taken': Submission.objects.filter(
            student=user, status__in=('submitted', 'reviewed'),
            assignment__kind='exam').values('assignment').distinct().count(),
        'active_days': DailySummary.objects.filter(
            user=user, counted_for_streak=True).count(),
        'weekly_goal_streak': weekly_goal_streak(user, profile),
        'earned': set(EarnedAchievement.objects.filter(user=user)
                      .values_list('achievement__code', flat=True)),
    }


def weekly_goal_streak(user, profile=None):
    """Сколько недель ПОДРЯД (считая от прошлой) выполнена недельная цель."""
    from .models import DailySummary, StudentProgressProfile

    profile = profile or StudentProgressProfile.objects.filter(
        user=user).first()
    goal = profile.weekly_goal if profile else 20
    if goal <= 0:
        return 0

    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    rows = {r['date']: r['problems_solved'] for r in
            DailySummary.objects.filter(user=user)
            .values('date', 'problems_solved')}
    streak = 0
    for back in range(1, 53):
        start = week_start - timedelta(days=7 * back)
        total = sum(v for d, v in rows.items()
                    if start <= d < start + timedelta(days=7))
        if total >= goal:
            streak += 1
        else:
            break
    return streak


def check_achievements(user):
    """Выдаёт всё заслуженное. Возвращает список новых достижений."""
    from .models import Achievement, EarnedAchievement

    facts = user_facts(user)
    new = []
    for achievement in Achievement.objects.all():
        if achievement.code in facts['earned']:
            continue
        if not condition_met(achievement.condition or {}, facts):
            continue
        obj, created = EarnedAchievement.objects.get_or_create(
            user=user, achievement=achievement)
        if created:
            new.append(achievement)
    return new


def condition_met(condition, facts):
    """Проверка одного условия достижения.

    Формат: `{"type": "<факт>", "value": N}`. Неизвестный тип НЕ выдаёт
    достижение — молчаливая выдача за опечатку в справочнике хуже, чем
    невыданная награда.
    """
    kind = condition.get('type')
    if kind not in facts:
        return False
    need = condition.get('value', 1)
    try:
        return facts[kind] >= need
    except TypeError:
        return False
