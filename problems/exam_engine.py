"""
Серверный таймер контрольной — самая ответственная механика сессии.

ГЛАВНОЕ ПРАВИЛО: ВРЕМЯ СЧИТАЕТ СЕРВЕР. Часам на устройстве ученика доверия
нет — перевести системное время назад умеет любой школьник, а расширение
браузера умеет ещё и подменять `Date.now()`. Клиент получает готовый момент
истечения и только рисует обратный отсчёт; решение «время вышло» принимает
сервер и никто больше.

Второе правило: РАБОТА НЕ ТЕРЯЕТСЯ. Оборвалась связь, закрылась вкладка,
сервер спал полминуты и просыпался — написанное остаётся. Ради этого
существует `AnswerDraft` и автосохранение.

Третье: ЗАВЕРШЕНИЕ ЛЕНИВОЕ. Фонового задания, которое ходит и закрывает
истёкшие попытки, у нас нет и на бесплатном хостинге быть не может (там нет
даже Shell). Поэтому попытка закрывается при ЛЮБОМ обращении к ней, а
временем сдачи ставится `expires_at`, а не «когда заметили»: иначе ученик,
уснувший над работой, получил бы время сдачи в три часа ночи.
"""
import logging
import math

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# Запас на дорогу ответа до сервера. Ученик нажал «Отправить» за секунду до
# конца — пакет шёл, сервер уже видит «время вышло». Десять секунд закрывают
# и медленную сеть, и просыпающийся бесплатный хостинг Render (~30 с на
# холодный старт мы всё равно не покроем, см. ограничения в отчёте).
GRACE_SECONDS = 10

# Границы, в которых репетитор может задать контрольную. Пять минут снизу —
# меньше не успеть даже прочитать условия; пять часов сверху — дольше
# школьник не пишет, а опечатка «300» вместо «30» иначе выдала бы работу
# на пять суток.
MIN_WINDOW_MINUTES = 5
MIN_DURATION_MINUTES = 5
MAX_DURATION_MINUTES = 300


class ExamError(Exception):
    """Ожидаемый отказ (окно не открылось, срок прошёл, работа сдана)."""


def start_attempt(assignment, student, now=None):
    """Начинает попытку. Повторный вызов возвращает ту же — второй не создаёт.

    ⚠️ `expires_at` считается ЗДЕСЬ, в момент нажатия «Начать», а не при
    загрузке страницы. На бесплатном хостинге приложение засыпает и
    просыпается около тридцати секунд; если бы момент истечения считался
    при отрисовке страницы, эти секунды съели бы время ученика ещё до того,
    как он увидел первую задачу.
    """
    from .models import Assignment, ExamAttempt

    now = now or timezone.now()

    existing = ExamAttempt.objects.filter(assignment=assignment,
                                          student=student).first()
    if existing is not None:
        finalize_if_expired(existing, now)
        return existing

    is_open, reason = assignment.open_state_for(student, now)
    if not is_open:
        raise ExamError(reason or 'Сейчас писать нельзя.')

    expires_at = None
    if assignment.exam_mode == Assignment.ExamMode.WINDOW:
        expires_at = assignment.ends_at
    elif assignment.exam_mode == Assignment.ExamMode.LIMIT:
        if assignment.duration_minutes:
            expires_at = now + timezone.timedelta(
                minutes=assignment.duration_minutes)
        # Лимит РЕЖЕТСЯ по крайнему сроку: стартовавший за минуту до дедлайна
        # не должен получить лишний час.
        if assignment.deadline and (expires_at is None
                                    or expires_at > assignment.deadline):
            expires_at = assignment.deadline

    with transaction.atomic():
        attempt, _ = ExamAttempt.objects.get_or_create(
            assignment=assignment, student=student,
            defaults={'expires_at': expires_at, 'last_heartbeat': now})
    return attempt


def available_minutes(assignment, now=None):
    """Сколько минут реально останется, если начать прямо сейчас.

    Нужно ДО старта: «на решение 90 минут», а срок через 20 — честнее
    предупредить, чем дать начать и оборвать.
    """
    from .models import Assignment

    now = now or timezone.now()
    if assignment.exam_mode == Assignment.ExamMode.WINDOW:
        if not assignment.ends_at:
            return None
        return max(0, int((assignment.ends_at - now).total_seconds() // 60))
    if assignment.exam_mode == Assignment.ExamMode.LIMIT:
        limit = assignment.duration_minutes
        if assignment.deadline:
            until_due = int((assignment.deadline - now).total_seconds() // 60)
            if limit is None:
                return max(0, until_due)
            return max(0, min(limit, until_due))
        return limit
    return None


def will_be_cut(assignment, now=None):
    """Урежется ли лимит крайним сроком — предупредить ДО старта."""
    if assignment.exam_mode != assignment.ExamMode.LIMIT:
        return False
    if not (assignment.duration_minutes and assignment.deadline):
        return False
    return available_minutes(assignment, now) < assignment.duration_minutes


def seconds_remaining(attempt, now=None):
    """Сколько секунд осталось по СЕРВЕРНОМУ времени. None — без ограничения.

    ⚠️ ОСТАТОК НЕ МОЖЕТ БЫТЬ БОЛЬШЕ ВЫДАННОГО. `expires_at` — момент
    абсолютный и подделке не поддаётся, но `now` берётся у ЧАСОВ МАШИНЫ, а
    на разработке сервер живёт на том же ноутбуке, что и браузер: ученик
    перевёл системное время на десять минут назад — и сервер честно насчитал
    себе десять лишних минут. Верхняя граница «сколько дали при старте»
    закрывает этот случай: больше выданного не бывает никогда, ни по какой
    законной причине.
    """
    if attempt.expires_at is None:
        return None
    now = now or timezone.now()
    left = max(0, int((attempt.expires_at - now).total_seconds()))
    if attempt.started_at is not None:
        # ⚠️ Округляем ВВЕРХ. `started_at` ставит база (`auto_now_add`) на
        # доли секунды позже, чем считался `expires_at`, и округление вниз
        # съедало бы у каждого ученика по секунде честного времени.
        granted = int(math.ceil((attempt.expires_at - attempt.started_at)
                                .total_seconds()))
        if granted >= 0:
            left = min(left, granted)
    return left


def can_accept(attempt, now=None):
    """Можно ли ещё принять ответ (с запасом на дорогу)."""
    if attempt.submitted_at is not None:
        return False
    if attempt.expires_at is None:
        return True
    now = now or timezone.now()
    return now <= attempt.expires_at + timezone.timedelta(
        seconds=GRACE_SECONDS)


def finalize_if_expired(attempt, now=None):
    """Ленивое завершение: истёкшая попытка закрывается при любом обращении.

    Время сдачи — `expires_at`, а НЕ «когда заметили». Ученик уснул над
    работой, вернулся через сутки — работа сдана тогда, когда кончилось
    время, а не когда он проснулся.
    """
    now = now or timezone.now()
    if attempt.submitted_at is not None:
        return False
    if attempt.expires_at is None or now <= attempt.expires_at:
        return False

    attempt.submitted_at = attempt.expires_at
    attempt.is_auto_submitted = True
    attempt.save(update_fields=['submitted_at', 'is_auto_submitted'])
    grade_attempt(attempt)
    return True


def save_draft(attempt, item, answer='', solution='', now=None):
    """Автосохранение одного ответа. Возвращает секунды до конца.

    ⚠️ ГОНКА ДВУХ СОХРАНЕНИЙ — найдена браузерной проверкой, питон-тесты её
    не видели. Автосейв уходит и по остановке ввода, и по потере фокуса, и
    по смене варианта; два запроса по одной задаче легко оказываются в
    полёте одновременно. `update_or_create` в этот момент делает
    SELECT → INSERT, оба видят «записи нет», второй INSERT ломается об
    уникальность (attempt, problem_item) — и ученик получает 500 на
    сохранении своей работы. Дороже ошибки в этой сессии нет.

    Лечим здесь, а не только на клиенте: клиента можно открыть в двух
    вкладках, и «мы же не шлём параллельно» перестаёт быть правдой.
    Повторная попытка идёт как ОБНОВЛЕНИЕ — побеждает тот, кто пришёл
    последним, что для черновика ровно и нужно.
    """
    from django.db import IntegrityError

    from .models import AnswerDraft

    values = {'answer_draft': answer or '', 'solution_draft': solution or ''}
    try:
        with transaction.atomic():
            AnswerDraft.objects.update_or_create(
                attempt=attempt, problem_item=item, defaults=values)
    except IntegrityError:
        AnswerDraft.objects.filter(attempt=attempt,
                                   problem_item=item).update(**values)

    attempt.last_heartbeat = now or timezone.now()
    attempt.save(update_fields=['last_heartbeat'])
    return seconds_remaining(attempt, now)


def drafts_map(attempt):
    """{id позиции: черновик} — чем заполнить форму при возврате."""
    from .models import AnswerDraft

    return {d.problem_item_id: d
            for d in AnswerDraft.objects.filter(attempt=attempt)}


def submit_attempt(attempt, now=None, auto=False):
    """Сдача работы: фиксируем момент и оцениваем.

    Идемпотентна: повторная сдача (две вкладки, двойной клик) ничего не
    меняет и не создаёт второй записи.
    """
    now = now or timezone.now()
    if attempt.submitted_at is not None:
        return False
    attempt.submitted_at = now
    attempt.is_auto_submitted = auto
    attempt.save(update_fields=['submitted_at', 'is_auto_submitted'])
    grade_attempt(attempt)
    return True


def grade_attempt(attempt):
    """Переносит черновики в решения и проверяет то, что проверяется машиной.

    Тесты и задачи с эталонным ответом проверяются сразу, открытые остаются
    «ждёт проверки». Опыт за контрольную идёт с множителем — через обычное
    логирование событий, отдельной ветки начисления нет.
    """
    from .assignment_rows import get_or_create_submission
    from .event_log import log_problem_event
    from .models import AnswerDraft

    assignment = attempt.assignment
    student = attempt.student
    drafts = {d.problem_item_id: d
              for d in AnswerDraft.objects.filter(attempt=attempt)}

    for item in assignment.items.select_related('catalog_problem',
                                                'custom_problem'):
        submission = get_or_create_submission(student, assignment, item)
        if submission.status in ('submitted', 'reviewed'):
            continue
        draft = drafts.get(item.pk)
        submission.submitted_answer = draft.answer_draft if draft else ''
        submission.solution_text = draft.solution_draft if draft else ''
        submission.status = 'submitted'
        submission.submitted_at = attempt.submitted_at
        submission.save()

        _autocheck(submission, item)
        try:
            feedback = getattr(submission, 'feedback', None)
            event_type = 'attempted'
            if submission.status == 'reviewed' and feedback is not None \
                    and feedback.score is not None:
                event_type = ('solved' if float(feedback.score) > 0
                              else 'failed')
            log_problem_event('exam', event_type, student, item.problem,
                              assignment=assignment,
                              payload={'attempt_id': attempt.pk})
        except Exception:
            logger.exception('Не удалось записать событие контрольной — '
                             'сдача не тронута')


def _autocheck(submission, item):
    """Машинная проверка — тем же движком, что у домашки. Второго не заводим."""
    from student.views import auto_check_custom, auto_check_submission

    try:
        if item.is_custom:
            auto_check_custom(submission, item)
        elif submission.problem_id:
            auto_check_submission(submission)
    except Exception:
        logger.exception('Автопроверка контрольной упала — решение осталось '
                         '«ждёт проверки»')


def attempt_summary(attempt):
    """Результат попытки для экрана ученика и таблицы репетитора.

    ⚠️ В строке ЕСТЬ ВСЁ, ЧТО СДЕЛАЛ ПРЕПОДАВАТЕЛЬ: балл, комментарий,
    отмеченные типовые ошибки и признак «проверял человек, а не машина».
    Раньше отсюда уходил только `state` («верно»/«неверно»), и поставленные
    репетитором десять баллов вместе с комментарием НЕ ДОЕЗЖАЛИ до ученика
    вообще — экран показывал вердикт автопроверки и молчал про остальное.
    Это рвало главный цикл продукта: проверил → увидел → понял.
    """
    from .assignment_rows import get_or_create_submission, submitted_display

    rows = []
    scored = max_score = 0.0
    pending = 0
    reviewed_by_teacher = 0
    for item in (attempt.assignment.items
                 .select_related('catalog_problem', 'custom_problem')
                 .prefetch_related('catalog_problem__parts',
                                   'custom_problem__options')
                 .order_by('order', 'id')):
        submission = get_or_create_submission(attempt.student,
                                              attempt.assignment, item)
        feedback = getattr(submission, 'feedback', None)
        points = float(item.points) if item.points is not None else 1.0
        max_score += points
        if feedback is not None and feedback.score is not None:
            scored += float(feedback.score)
            state = 'correct' if float(feedback.score) > 0 else 'wrong'
        elif not (submission.submitted_answer or submission.solution_text):
            state = 'empty'
        else:
            state = 'pending'
            pending += 1
        # Кто поставил балл. У автопроверки `reviewed_by` пуст — по нему и
        # различаем: «машина сверила ответ» и «преподаватель прочитал
        # решение» для ученика вещи очень разные.
        by_teacher = bool(feedback is not None and feedback.reviewed_by_id)
        if by_teacher:
            reviewed_by_teacher += 1
        rows.append({
            'item': item,
            'submission': submission,
            'answer': submitted_display(item, submission),
            'correct_answer': item.correct_answer,
            'score': float(feedback.score) if feedback is not None
            and feedback.score is not None else None,
            'points': points,
            'state': state,
            'feedback': feedback,
            'by_teacher': by_teacher,
            'comment': (feedback.comment or '') if feedback else '',
            'mistakes': list(feedback.mistakes.all()) if by_teacher else [],
        })

    return {
        'rows': rows,
        'scored': round(scored, 2),
        'max_score': round(max_score, 2),
        'pending': pending,
        'reviewed_by_teacher': reviewed_by_teacher,
        'graded_max': round(max_score - sum(
            r['points'] for r in rows if r['state'] == 'pending'), 2),
    }
