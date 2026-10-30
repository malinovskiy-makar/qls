"""Тренировочный режим: прорешать комплект олимпиады прямо на сайте.

ГЛАВНОЕ ПРАВИЛО ЭТОГО ФАЙЛА: ПРОВЕРКУ ОТВЕТА МЫ ЗОВЁМ, А НЕ ПОВТОРЯЕМ.
Единственная точка проверки на всей платформе — `student.views.grade_submission`;
её докстрока прямо говорит, зачем: раньше выбор ветки («тест — так, задача —
эдак») был написан в двух местах и грозил разойтись. Третья копия вернула бы
ровно ту беду: один и тот же ответ был бы верным в тренировке и неверным в
контрольной, молча, а всплыло бы это жалобой школьника.

ВТОРОЕ ПРАВИЛО: ОТ ТРЕНИРОВАВШЕГОСЯ В `problems` НЕ ОСТАЁТСЯ НИЧЕГО.
Проверка требует сохранённого `Submission` (она вешает на него `PartAnswer`
и `TeacherFeedback` по внешнему ключу), поэтому решение создаётся — и тут
же ОТКАТЫВАЕТСЯ вместе со всем, что проверка написала. Иначе тренировка
попала бы в опыт и в серию дней: и то и другое считается по
`Submission.student` без сужения по работе. Обоснование — [ADR 0066].

ТРЕТЬЕ: ВРЕМЯ СЧИТАЕТ СЕРВЕР. Арифметику остатка мы не пишем заново, а
берём из `problems.exam_engine`: `seconds_remaining` и `can_accept`
работают с тренировочной попыткой как есть — поля времени названы
одинаково намеренно. Там же живёт защита «остаток не больше выданного»
от переведённых назад часов, и терять её нельзя.
"""
import logging

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

# ⚠️ ИМПОРТИРУЕМ, А НЕ ПЕРЕПИСЫВАЕМ. Обе функции смотрят только на
# `expires_at`, `started_at` и `submitted_at` — имена полей `TrainingAttempt`
# совпадают с `ExamAttempt` ровно ради этого.
from problems.exam_engine import can_accept, seconds_remaining  # noqa: F401

logger = logging.getLogger(__name__)

# Логин служебного пользователя, на которого оформляется одноразовое
# решение. Неактивен и без пригодного пароля: войти под ним нельзя.
SERVICE_USERNAME = 'olympiad-training'

# Сколько дней живут попытки гостей (см. `cleanup_training_attempts`).
GUEST_LIFETIME_DAYS = 7


class TrainingError(Exception):
    """Ожидаемый отказ: задачи не привязаны, попытка сдана, время вышло."""


class _Rollback(Exception):
    """Внутренний сигнал «откатить одноразовое решение». Наружу не выходит."""


# ---------------------------------------------------------------------------
# Задачи комплекта и постоянное «задание» под них
# ---------------------------------------------------------------------------

def package_items(variant):
    """Позиции комплекта из пакета олимпиад по порядку тура (ночь 30.10, Э5).

    Позиция, которой нет в последнем пакете, в тур не идёт: на ней могут
    висеть старые попытки, но решать её заново незачем. Задание чужого тура
    (`excluded`, день 30.10, Д5) — тоже.
    """
    return list(variant.items.filter(absent_in_last_import=False, excluded=False)
                .select_related('problem').order_by('order', 'id'))


def variant_problems(variant):
    """Задачи комплекта из банка, в порядке номеров тура. Пусто — не привязан.

    ⚠️ С 30.10.2026 СНАЧАЛА ПОЗИЦИИ ПАКЕТА (`OlympiadVariantItem`): у всех
    624 основных комплектов пакета совпадений в `OlympiadRef` ноль, и без
    этого тренировка не открывалась ни на одном из них. Комплект без позиций
    (прежние 12) — по-старому: `OlympiadVariant.ref_event_id` →
    `problems.OlympiadRef.event_id`. Раздел олимпиад в `problems` ничего
    не пишет ([ADR 0063]).
    """
    from problems.models import OlympiadRef

    items = package_items(variant)
    if items:
        seen, problems = set(), []
        for item in items:
            if item.problem_id not in seen:
                seen.add(item.problem_id)
                problems.append(item.problem)
        return problems

    event_id = (variant.ref_event_id or '').strip()
    if not event_id:
        return []

    refs = list(OlympiadRef.objects.filter(event_id=event_id)
                .select_related('problem'))

    def order_key(ref):
        # ⚠️ Номер в туре — строка («3», «3а», «II»). Числовые сортируем
        # числом, иначе «10» встанет между «1» и «2»; остальные — как есть,
        # но ПОСЛЕ числовых, чтобы порядок был устойчивым.
        raw = (ref.number or '').strip()
        digits = ''.join(c for c in raw if c.isdigit())
        return (0, int(digits), raw) if digits else (1, 0, raw)

    refs.sort(key=order_key)
    seen = set()
    problems = []
    for ref in refs:
        if ref.problem_id in seen:
            continue
        seen.add(ref.problem_id)
        problems.append(ref.problem)
    return problems


def linked_event_ids(variants):
    """Множество `ref_event_id`, у которых в банке ЕСТЬ задачи. Один запрос.

    ⚠️ Нужен именно так, а не вызовом `variant_items` на каждый комплект:
    та функция создаёт постоянное «задание», и страница олимпиады заводила
    бы работы для всех комплектов сразу, включая те, что никто не откроет.
    """
    from problems.models import OlympiadRef

    wanted = {(v.ref_event_id or '').strip() for v in variants}
    wanted.discard('')
    if not wanted:
        return set()
    return set(OlympiadRef.objects.filter(event_id__in=wanted)
               .values_list('event_id', flat=True).distinct())


def service_user():
    """Служебный «ученик», на которого оформляется одноразовое решение.

    ⚠️ ОН НЕАКТИВЕН И БЕЗ ПАРОЛЯ. Войти под ним нельзя, ни в одну группу он
    не входит, ни у одного репетитора не числится. Настоящий человек (и уж
    тем более гость) на решение не попадает никогда — иначе тренировка
    пошла бы в опыт и в серию дней.
    """
    User = get_user_model()
    user, created = User.objects.get_or_create(
        username=SERVICE_USERNAME,
        defaults={'is_active': False, 'role': User.Role.VIEWER,
                  'first_name': 'Тренировка', 'last_name': 'олимпиад'})
    if created:
        user.set_unusable_password()
        user.save(update_fields=['password'])
    return user


def training_assignment(variant):
    """Постоянное «задание» комплекта: работа со служебным автором и позиции.

    ⚠️ ПОЧЕМУ ПОСТОЯННОЕ, А НЕ СОБРАННОЕ НА ЛЕТУ. Автопроверка каталожной
    задачи берёт эталон ТОЛЬКО из `AssignmentItem.answer_override` —
    из того, что подтвердил живой человек (`part_grading.grade_part`,
    отката к каталожному ответу там нет намеренно). Позиция, созданная на
    один прогон, никогда не будет утверждена, и балл был бы нулевым всегда.

    ⚠️ ПОЧЕМУ ЕЁ НИКТО НЕ УВИДИТ. Автор служебный, учеников нет, группы
    нет, — а все списки работ сужены: репетитору по `author`, ученику по
    `students`, календарю по `author | group__teacher`.
    """
    from problems.models import Assignment
    from problems.models_platform import AssignmentItem

    problems = variant_problems(variant)
    if not problems:
        raise TrainingError('Задания ещё не привязаны.')

    name = 'Олимпиадная тренировка #{}: {}'.format(variant.pk, variant)[:300]
    assignment, _ = Assignment.objects.get_or_create(
        author=service_user(),
        name=name,
        defaults={'kind': Assignment.Kind.EXAM},
    )

    # Балл позиции пакета — балл задания в туре. Нет его — правило всей
    # системы (`AssignmentItem.save`: задаче 10, тесту 3).
    points = {i.problem_id: i.max_score for i in package_items(variant)
              if i.max_score is not None}
    existing = {item.catalog_problem_id: item
                for item in assignment.items.all()}
    for order, problem in enumerate(problems, start=1):
        item = existing.get(problem.pk)
        if item is None:
            AssignmentItem.objects.create(assignment=assignment,
                                          catalog_problem=problem,
                                          order=order,
                                          points=points.get(problem.pk))
        else:
            changed = []
            if item.order != order:
                item.order = order
                changed.append('order')
            if problem.pk in points and item.points != points[problem.pk]:
                item.points = points[problem.pk]
                changed.append('points')
            if changed:
                item.save(update_fields=changed)
    return assignment


def variant_items(variant):
    """Позиции комплекта по порядку — то, из чего собран экран и проверка.

    ⚠️ Только задачи, которые комплект даёт СЕЙЧАС (`variant_problems`).
    Служебное задание постоянное: позиция задачи, ушедшей из тура (задание
    чужого тура, Д5), в нём остаётся — удалять её нельзя, на ней висят
    ответы старых попыток, — но ни экран, ни сумма тура её не видят.
    """
    assignment = training_assignment(variant)
    wanted = [p.pk for p in variant_problems(variant)]
    return list(assignment.items.filter(catalog_problem_id__in=wanted)
                .select_related('catalog_problem')
                .prefetch_related('catalog_problem__parts')
                .order_by('order', 'id'))


def variant_max_score(variant):
    """Максимум баллов за комплект. None — задачи не привязаны."""
    from problems.assignment_rows import item_max_score

    try:
        items = variant_items(variant)
    except TrainingError:
        return None
    return sum(float(item_max_score(item)) for item in items)


# ---------------------------------------------------------------------------
# Попытка
# ---------------------------------------------------------------------------

def start_attempt(variant, user=None, session_key='', with_timer=True,
                  now=None):
    """Начинает попытку. Перерешивать можно сколько угодно раз.

    ⚠️ `expires_at` считается ЗДЕСЬ, в момент нажатия «Решать», а не при
    отрисовке страницы — та же причина, что у контрольной: на медленном
    хостинге секунды пробуждения съели бы время решающего.
    """
    from .models import TrainingAttempt

    now = now or timezone.now()
    # Проверяем привязку ДО создания попытки: попытка по комплекту без
    # задач — мусор, который потом некуда деть.
    variant_items(variant)

    from .navigator import tour_minutes

    expires_at = None
    if with_timer:
        # ⚠️ У комплектов пакета своего времени нет — время тура задаёт
        # этап (ВсОШ, заключительный — 210 минут). Одна функция на экран и
        # на таймер: иначе на входе одно число, а на часах другое.
        minutes = tour_minutes(variant)
        if not minutes:
            raise TrainingError('Время тура неизвестно.')
        expires_at = now + timezone.timedelta(minutes=minutes)

    return TrainingAttempt.objects.create(
        variant=variant,
        user=user if (user is not None and user.is_authenticated) else None,
        session_key=session_key or '',
        with_timer=bool(with_timer),
        expires_at=expires_at,
    )


def current_attempt(variant, user=None, session_key=''):
    """Последняя НЕсданная попытка этого решающего. None — такой нет."""
    from .models import TrainingAttempt

    queryset = TrainingAttempt.objects.filter(variant=variant,
                                              submitted_at__isnull=True)
    if user is not None and user.is_authenticated:
        queryset = queryset.filter(user=user)
    elif session_key:
        queryset = queryset.filter(user__isnull=True, session_key=session_key)
    else:
        return None
    return queryset.order_by('-started_at').first()


def finalize_if_expired(attempt, now=None):
    """Ленивое завершение истёкшей попытки. Своё, не из `exam_engine`.

    ⚠️ ЗАЧЕМ СВОЁ. `exam_engine.finalize_if_expired` в конце зовёт
    `exam_engine.grade_attempt` — проверку КОНТРОЛЬНОЙ, которая ходит в
    `attempt.assignment` и `attempt.student`. У тренировочной попытки таких
    полей нет. Поведение при этом повторяем дословно, включая главное:

    ⚠️ ВРЕМЯ СДАЧИ — `expires_at`, А НЕ «КОГДА ЗАМЕТИЛИ». Школьник закрыл
    вкладку и вернулся через сутки — работа сдана в момент конца времени,
    а не в три часа ночи.
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


def submit_attempt(attempt, now=None, auto=False):
    """Сдача. Идемпотентна: повторная ничего не меняет и не считает заново."""
    now = now or timezone.now()
    if attempt.submitted_at is not None:
        return False
    attempt.submitted_at = now
    attempt.is_auto_submitted = auto
    attempt.save(update_fields=['submitted_at', 'is_auto_submitted'])
    grade_attempt(attempt)
    return True


# ---------------------------------------------------------------------------
# Черновики
# ---------------------------------------------------------------------------

def save_draft(attempt, problem, answer=None, solution=None, part=None):
    """Автосохранение одного поля. Возвращает секунды до конца (или None).

    ⚠️ ГОНКА ДВУХ СОХРАНЕНИЙ — лечение перенесено из
    `exam_engine.save_draft` дословно, и не «на всякий случай». Автосейв
    уходит по остановке ввода, по потере фокуса и по смене варианта; два
    запроса по одной задаче легко оказываются в полёте одновременно.
    `update_or_create` в этот момент делает SELECT → INSERT, оба видят
    «записи нет», второй INSERT ломается об уникальность — и решающий
    получает 500 на сохранении своей работы. Открытая в двух вкладках
    страница делает эту гонку реальной, поэтому лечим на СЕРВЕРЕ, а не
    обещанием клиента не слать параллельно.

    Повторная попытка идёт как ОБНОВЛЕНИЕ: побеждает пришедший последним —
    для черновика ровно это и нужно.
    """
    from .models import TrainingDraft

    # ⚠️ `None` = «не трогать это поле». Ответ и решение уезжают РАЗНЫМИ
    # запросами; запись обоих на каждый запрос затирала бы соседнее пустотой.
    values = {}
    if answer is not None:
        values['answer_draft'] = answer
    if solution is not None:
        values['solution_draft'] = solution
    if not values:
        return seconds_remaining(attempt)

    try:
        with transaction.atomic():
            TrainingDraft.objects.update_or_create(
                attempt=attempt, problem=problem, part=part, defaults=values)
    except IntegrityError:
        TrainingDraft.objects.filter(
            attempt=attempt, problem=problem, part=part).update(**values)
    return seconds_remaining(attempt)


def drafts_map(attempt):
    """{(id задачи, ключ пункта): черновик} — чем заполнить форму."""
    from .models import TrainingDraft

    return {(d.problem_id, d.part_id): d
            for d in TrainingDraft.objects.filter(attempt=attempt)}


# ---------------------------------------------------------------------------
# Проверка: одноразовое решение
# ---------------------------------------------------------------------------

def graded_problem_ids(attempt):
    """Задачи попытки, у которых итог уже есть — в режиме «Без времени» это
    сданные по одной задачи: править их больше нельзя."""
    from .models import TrainingItemResult

    return set(TrainingItemResult.objects.filter(attempt=attempt)
               .values_list('problem_id', flat=True))


def grade_item(attempt, item):
    """«Сдать задание» без времени: проверить ОДНУ задачу и записать итог.

    Повторная сдача той же задачи ничего не меняет — итог уже снят.
    Возвращает `TrainingItemResult`.
    """
    from problems.assignment_rows import item_max_score

    from .models import TrainingItemResult

    problem = item.catalog_problem
    done = TrainingItemResult.objects.filter(attempt=attempt,
                                             problem=problem).first()
    if done is not None:
        return done
    items = variant_items(attempt.variant)
    order = next((n for n, i in enumerate(items, start=1) if i.pk == item.pk), 0)
    drafts = drafts_map(attempt)
    values = _draft_values(item, drafts, problem)
    row = _grade_one(service_user(), training_assignment(attempt.variant), item,
                     values, _joined_answer(item, values), order, problem,
                     float(item_max_score(item)),
                     has_work=_has_work(attempt, drafts, problem))
    return TrainingItemResult.objects.create(
        attempt=attempt, problem=problem, order=order, score=row['score'],
        max_score=row['max_score'], is_pending=row['pending'],
        comment=row['comment'])


def grade_attempt(attempt):
    """Проверяет попытку ВЫЗОВОМ `grade_submission` и сохраняет итог.

    ⚠️ УЖЕ СДАННЫЕ ЗАДАЧИ НЕ ПЕРЕПРОВЕРЯЮТСЯ (ночь 30.10): в режиме «Без
    времени» итог задачи снят при «Сдать задание», а позже его может
    уточнить ИИ-проверка (Э7) — пересчёт при сдаче тура стёр бы и то и другое.

    ⚠️ РЕШЕНИЕ ОДНОРАЗОВОЕ. `Submission`, `PartAnswer` и `TeacherFeedback`
    создаются внутри точки сохранения и откатываются: проверке нужен
    сохранённый объект (она вешает записи по внешнему ключу), а нам не
    нужна ни одна из них. Результат уносим обычными числами.

    ⚠️ ЖУРНАЛ СОБЫТИЙ НЕ ТРОГАЕМ. `log_problem_event` зовёт
    `exam_engine.grade_attempt`, а не сама проверка, — поэтому откат ничего
    постороннего не задевает. Проверено по коду перед выбором пути.
    """
    from problems.assignment_rows import item_max_score

    from .models import TrainingItemResult

    items = variant_items(attempt.variant)
    drafts = drafts_map(attempt)
    student = service_user()
    assignment = training_assignment(attempt.variant)

    done = graded_problem_ids(attempt)
    rows = []
    for order, item in enumerate(items, start=1):
        problem = item.catalog_problem
        if problem.pk in done:
            continue
        maximum = float(item_max_score(item))
        values = _draft_values(item, drafts, problem)
        answer_text = _joined_answer(item, values)
        rows.append(_grade_one(student, assignment, item, values, answer_text,
                               order, problem, maximum,
                               has_work=_has_work(attempt, drafts, problem)))

    # Пишем итоги ПОСЛЕ отката — иначе они уехали бы вместе с ним.
    TrainingItemResult.objects.bulk_create([
        TrainingItemResult(attempt=attempt, problem_id=row['problem_id'],
                           order=row['order'], score=row['score'],
                           max_score=row['max_score'],
                           is_pending=row['pending'],
                           comment=row['comment'])
        for row in rows])
    recount(attempt)
    return rows


def package_points(variant):
    """{задача: балл позиции пакета или None} — балл задания в туре.

    ⚠️ None — «балл неизвестен», и числа на экране нет (день 30.10, У4).
    Служебная позиция задания (`AssignmentItem.points`) у такой задачи —
    правило системы (10 задаче, 3 тесту), выдумка для тура: показывать и
    складывать её нельзя.
    """
    return {i.problem_id: (float(i.max_score) if i.max_score is not None else None)
            for i in package_items(variant)}


def tour_maximum(variant):
    """Максимум тура по правилу навигатора: сумма баллов, если они есть у всех
    заданий, иначе максимум этапа, иначе None (`navigator.tour_max_score`)."""
    from . import navigator
    from .models import OlympiadVariant

    if not package_items(variant):
        return None
    annotated = navigator._annotated(OlympiadVariant.objects.filter(pk=variant.pk)).get()
    return navigator.tour_max_score(annotated)


def recount(attempt):
    """Итог попытки — сумма итогов по задачам (после проверки и после ИИ).

    Максимум — максимум тура (`tour_maximum`), а не сумма служебных баллов:
    у задания без балла там выдуманные 10 (день 30.10, У4). Комплект без
    позиций пакета (прежние 12) — как раньше, сумма по задачам.
    """
    from .models import TrainingItemResult

    results = list(TrainingItemResult.objects.filter(attempt=attempt))
    attempt.score = sum(float(r.score) for r in results if r.score is not None)
    maximum = tour_maximum(attempt.variant)
    attempt.max_score = (maximum if maximum is not None or package_items(attempt.variant)
                         else sum(float(r.max_score) for r in results))
    attempt.pending_count = sum(1 for r in results if r.is_pending)
    attempt.save(update_fields=['score', 'max_score', 'pending_count'])


def _has_work(attempt, drafts, problem):
    """Сдано ли развёрнутое решение: текст «Моё решение» или листы."""
    whole = drafts.get((problem.pk, None))
    if whole is not None and (whole.solution_draft or '').strip():
        return True
    return attempt.uploads.filter(problem=problem).exists()


def _draft_values(item, drafts, problem):
    """{ключ пункта: ответ} — ровно в том виде, какой ждёт проверка."""
    from problems.assignment_rows import answer_parts, part_key

    values = {}
    for part in answer_parts(item):
        draft = drafts.get((problem.pk, part.pk if part is not None else None))
        values[part_key(part)] = (draft.answer_draft if draft else '') or ''
    return values


def _joined_answer(item, values):
    """Ответ одной строкой — для задач, которые идут не по пунктам (тесты)."""
    from problems.part_grading import join_answers

    return join_answers(item, values)


def _grade_one(student, assignment, item, values, answer_text, order, problem,
               maximum, has_work=False):
    """Одна задача: создать решение, проверить, снять числа, откатить.

    Возвращает обычный словарь — он переживает откат, объекты базы нет.
    """
    from problems.models import Submission, TeacherFeedback
    from problems.part_grading import applies

    from student.views import grade_submission

    result = {'problem_id': problem.pk, 'order': order,
              'max_score': maximum, 'score': None, 'pending': True,
              'comment': ''}
    if has_work and not any((v or '').strip() for v in values.values()):
        # ⚠️ РАЗВЁРНУТОЕ РЕШЕНИЕ БЕЗ КРАТКОГО ОТВЕТА — НЕ НОЛЬ (ночь 30.10).
        # Экран тура по макету даёт открытому заданию только «Решение» —
        # фото или текст, полей ответа нет. Машина поставила бы ноль «ответа
        # не было» человеку, который решение сдал. Такое задание ждёт
        # проверки: ИИ по критериям (Э7) или самопроверки по разбору.
        return result
    try:
        with transaction.atomic():
            submission = Submission.objects.create(
                student=student, assignment=assignment, problem_item=item,
                problem=problem, status='submitted',
                submitted_answer=answer_text,
                submitted_at=timezone.now())
            grade_submission(submission, item,
                             values=values if applies(item) else None)
            # ⚠️ Спрашиваем базу, а не `submission.feedback`. Проверка
            # сама однажды обращается к этому свойству ДО создания записи,
            # и Django кэширует на объекте «связи нет»; после создания
            # кэш обновляется присваиванием, но полагаться на порядок двух
            # чужих строк ради собственного балла — плохая ставка.
            feedback = TeacherFeedback.objects.filter(
                submission=submission).first()
            if feedback is not None and feedback.score is not None:
                result['score'] = float(feedback.score)
                result['pending'] = False
                result['comment'] = feedback.comment or ''
            raise _Rollback
    except _Rollback:
        pass
    except Exception:
        # Проверка упала — задача честно остаётся «ждёт проверки». Молчаливый
        # ноль был бы враньём: решающий не ошибся, сломались мы.
        logger.exception('Проверка тренировки упала на задаче %s', problem.pk)
    return result


# ---------------------------------------------------------------------------
# Результат для экрана
# ---------------------------------------------------------------------------

def _shown_max(points, problem_id, stored, item):
    """Максимум задания для экрана: балл позиции пакета; неизвестен — None."""
    from problems.assignment_rows import item_max_score

    if problem_id in points:
        return points[problem_id]
    return float(stored.max_score) if stored else float(item_max_score(item))


def attempt_result(attempt):
    """Разбор попытки: по задаче — что ответил, что верно, полное решение."""
    from problems.assignment_rows import (answer_parts, item_max_score,
                                          part_correct_answer)

    from .models import TrainingItemResult

    items = variant_items(attempt.variant)
    drafts = drafts_map(attempt)
    results = {r.problem_id: r
               for r in TrainingItemResult.objects.filter(attempt=attempt)}
    points = package_points(attempt.variant)

    rows = []
    for number, item in enumerate(items, start=1):
        problem = item.catalog_problem
        stored = results.get(problem.pk)
        whole = drafts.get((problem.pk, None))
        parts = []
        for part in answer_parts(item):
            key = part.pk if part is not None else None
            draft = drafts.get((problem.pk, key))
            parts.append({
                'part': part,
                'label': (part.label if part is not None else '') or '',
                'given': (draft.answer_draft if draft else '') or '',
                'correct': part_correct_answer(item, part),
            })
        solution_given = (whole.solution_draft if whole else '') or ''
        rows.append({
            'number': number,
            'item': item,
            'problem': problem,
            'parts': parts,
            'has_parts': len(parts) > 1 or parts[0]['part'] is not None,
            # ⚠️ «НЕ ОТВЕЧАЛ» И «ОШИБСЯ» — РАЗНЫЕ ВЕЩИ. Машина ставит ноль и
            # за пустоту тоже (`part_grading.BLANK_COMMENT`), и разбор
            # честно писал «неверно» у задачи, которую человек не открывал.
            # Для тренировки это прямая неправда: он не ошибся, он не дошёл.
            'answered': any(p['given'].strip() for p in parts)
            or bool(solution_given.strip()),
            'solution_given': solution_given,
            'solution_text': item.solution_text,
            'score': float(stored.score) if stored and stored.score is not None
            else None,
            'max_score': _shown_max(points, problem.pk, stored, item),
            'pending': stored.is_pending if stored else True,
            'comment': stored.comment if stored else '',
        })

    return {
        'rows': rows,
        'scored': round(float(attempt.score or 0), 2),
        'max_score': (round(float(attempt.max_score), 2)
                      if attempt.max_score is not None else None),
        'pending': attempt.pending_count,
    }
