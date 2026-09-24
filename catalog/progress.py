"""Прогресс ученика по задаче каталога (каталог «Стол», 18.09.2026, ADR 0119).

Зачем: статус в строке ленты («не открывал / открывал / решил сам / с
подсказкой / не получилось»), «Как прошло?» под условием и восстановление
панели помощи после перезагрузки (сколько подсказок открыто, открыто ли
решение). Модель — `problems.models_platform.ProblemProgress`.

Правила — только здесь:
* открытие задачи вошедшим заводит строку `opened`, если её нет
  (`note_opened`, неблокирующе: упавшая запись не ломает страницу);
* «решил сам» после открытого решения — отказ (`ProgressError`): иначе
  отметка значила бы «прочитал решение», а не «решил»;
* подсказки только растут, «смотрел решение» не снимается;
* тест ставит статус сам (`note_test_result`, `note_test_revealed`).
"""
import logging

logger = logging.getLogger(__name__)

#: Короткие коды запроса → статус модели. `None` снимает отметку.
STATUS_CODES = {'self': 'solved_self', 'hint': 'solved_hint', 'failed': 'failed'}
SELF_AFTER_SOLUTION = 'Решение уже открыто: отметить «решил сам» нельзя.'
#: Больше подсказок у задачи не бывает (в банке до пяти) — защита от мусора.
HINTS_MAX = 50


class ProgressError(ValueError):
    """Отказ с текстом для человека (ответ 400)."""


def _model():
    from problems.models_platform import ProblemProgress
    return ProblemProgress


def note_opened(user, problem):
    """Открытие задачи вошедшим. Ничего не поднимает."""
    if not getattr(user, 'is_authenticated', False):
        return
    try:
        _model().objects.get_or_create(user=user, problem=problem)
    except Exception:   # noqa: BLE001 — журнал не важнее страницы
        logger.exception('Прогресс не записан: открытие задачи %s', problem.pk)


def note_hint(user, problem, n):
    """Выдана подсказка номер `n`: для восстановления панели после перезагрузки."""
    if not getattr(user, 'is_authenticated', False):
        return
    try:
        update(user, problem, {'hints_opened': n})
    except Exception:   # noqa: BLE001 — подсказка важнее журнала
        logger.exception('Прогресс не записан: подсказка %s к задаче %s', n, problem.pk)


def update(user, problem, data):
    """Правка прогресса из `POST /catalog/api/progress/<id>/` → строка модели.

    `data`: `status` (`self` | `hint` | `failed` | `None` — снять),
    `hints_opened` (число), `solution_viewed` (`True`). Поднимает
    `ProgressError` с текстом для человека.
    """
    Progress = _model()
    row, _created = Progress.objects.get_or_create(user=user, problem=problem)
    if data.get('solution_viewed') is True:
        row.solution_viewed = True
    if 'hints_opened' in data:
        try:
            hints = int(data['hints_opened'])
        except (TypeError, ValueError):
            raise ProgressError('Число подсказок — целое.') from None
        row.hints_opened = max(row.hints_opened, min(max(hints, 0), HINTS_MAX))
    if 'status' in data:
        code = data['status']
        if code is None:
            row.status = Progress.Status.OPENED
        elif code in STATUS_CODES:
            if code == 'self' and row.solution_viewed:
                raise ProgressError(SELF_AFTER_SOLUTION)
            row.status = STATUS_CODES[code]
        else:
            raise ProgressError('Неизвестная отметка.')
    row.save()
    return row


def reset(user, problem):
    """«Решить заново»: экран ученика — как у новой задачи (ADR 0130).

    Подсказки, «смотрел решение» и статус экрана обнуляются, а то, что было
    до сброса, копится в `hints_before_reset` / `solution_before_reset` —
    честные факты не теряются. Чат и попытки не удаляются: экран показывает
    только то, что новее `reset_at`. Повторный вызов безопасен.
    """
    from django.utils import timezone

    Progress = _model()
    row, _created = Progress.objects.get_or_create(user=user, problem=problem)
    row.hints_before_reset = max(row.hints_before_reset, row.hints_opened)
    row.solution_before_reset = row.solution_before_reset or row.solution_viewed
    row.hints_opened = 0
    row.solution_viewed = False
    row.status = Progress.Status.OPENED
    row.reset_at = timezone.now()
    row.save()
    return row


def reset_at(user, problem):
    """Момент последнего «Решить заново» или None — для фильтра экрана."""
    if not getattr(user, 'is_authenticated', False):
        return None
    return (_model().objects.filter(user=user, problem=problem)
            .values_list('reset_at', flat=True).first())


def note_test_result(user, problem, first_try):
    """Тест решён: с первой попытки без подсказок — «решил сам», иначе — «с подсказкой»."""
    if not getattr(user, 'is_authenticated', False):
        return
    Progress = _model()
    row, _created = Progress.objects.get_or_create(user=user, problem=problem)
    alone = first_try and not row.hints_opened and not row.solution_viewed
    row.status = Progress.Status.SOLVED_SELF if alone else Progress.Status.SOLVED_HINT
    row.save(update_fields=['status', 'updated_at'])


def note_test_revealed(user, problem):
    """«Показать ответ» у теста — «не получилось»."""
    if not getattr(user, 'is_authenticated', False):
        return
    Progress = _model()
    row, _created = Progress.objects.get_or_create(user=user, problem=problem)
    row.status = Progress.Status.FAILED
    row.solution_viewed = True
    row.save(update_fields=['status', 'solution_viewed', 'updated_at'])


def statuses_for(user, problem_ids):
    """{id задачи: статус} для страницы строк — одним запросом; гостю пусто."""
    if not getattr(user, 'is_authenticated', False) or not problem_ids:
        return {}
    return dict(_model().objects.filter(user=user, problem_id__in=list(problem_ids))
                .values_list('problem_id', 'status'))


#: Сколько задач в строке «Продолжить» на входе каталога.
CONTINUE_MAX = 3


def continue_for(user, visible_qs):
    """«Продолжить»: до CONTINUE_MAX задач «не получилось» и «открывал», свежие
    первыми. `visible_qs` — задачи за шлюзом качества (решает вызывающий)."""
    if not getattr(user, 'is_authenticated', False):
        return []
    Progress = _model()
    rows = (Progress.objects.filter(user=user, problem__in=visible_qs,
                                    status__in=(Progress.Status.FAILED, Progress.Status.OPENED))
            .select_related('problem').order_by('-updated_at')[:CONTINUE_MAX])
    return [row.problem for row in rows]


def as_json(row):
    return {'status': row.status, 'hints_opened': row.hints_opened,
            'solution_viewed': row.solution_viewed}
