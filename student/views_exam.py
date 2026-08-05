"""
Контрольные глазами ученика: до старта → прохождение → результат.

Отдельный модуль, а не ещё одна ветка в `views.py`: у контрольной свой цикл
(старт → таймер → автосохранение → сдача → результат), и мешать его с
домашкой, которую можно дописывать когда угодно, значит однажды перепутать
правила и разрешить дописать контрольную после звонка.

Время везде спрашивается у СЕРВЕРА через `problems.exam_engine`. Ни одна
вьюха здесь не верит клиенту насчёт времени.
"""
import json

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from problems import exam_engine

from .views import exam_schedule_label, student_required


def _exam_or_404(request, pk):
    from problems.models import Assignment

    return get_object_or_404(Assignment, pk=pk, students=request.user,
                             kind=Assignment.Kind.EXAM)


@student_required
def exam_intro(request, pk):
    """Страница до старта: что это, сколько времени, сколько задач.

    Отделена от списка работ намеренно: таймер запускает СЕРВЕР в момент
    нажатия «Начать», и нажатие должно быть осознанным.
    """
    assignment = _exam_or_404(request, pk)
    now = timezone.now()
    attempt = assignment.exam_attempts.filter(student=request.user).first()
    if attempt is not None:
        exam_engine.finalize_if_expired(attempt, now)
        attempt.refresh_from_db()
        if attempt.submitted_at is not None:
            return redirect('student:exam_result', pk=assignment.pk)
        return redirect('student:exam_take', pk=assignment.pk)

    is_open, closed_reason = assignment.open_state_for(request.user, now)
    return render(request, 'student/exam_intro.html', {
        'assignment': assignment,
        'attempt': None,
        'is_open': is_open,
        'closed_reason': closed_reason,
        'schedule': exam_schedule_label(assignment),
        'items_count': assignment.items.count(),
        'starts_at': assignment.starts_at,
        'deadline': assignment.deadline_at,
        'minutes': exam_engine.available_minutes(assignment, now),
        'will_be_cut': exam_engine.will_be_cut(assignment, now),
        'now': now,
    })


@require_POST
@student_required
def exam_start(request, pk):
    """Старт. Момент истечения считает сервер ЗДЕСЬ, в момент нажатия."""
    assignment = _exam_or_404(request, pk)
    try:
        exam_engine.start_attempt(assignment, request.user)
    except exam_engine.ExamError as error:
        messages.error(request, str(error))
        return redirect('student:exam_intro', pk=assignment.pk)
    return redirect('student:exam_take', pk=assignment.pk)


@student_required
def exam_take(request, pk):
    """Страница прохождения: все задачи одним списком, таймер в шапке."""
    from problems.assignment_rows import build_rows

    assignment = _exam_or_404(request, pk)
    now = timezone.now()
    attempt = assignment.exam_attempts.filter(student=request.user).first()
    if attempt is None:
        return redirect('student:exam_intro', pk=assignment.pk)

    if exam_engine.finalize_if_expired(attempt, now):
        messages.warning(request, 'Время вышло — работа сдана автоматически.')
        return redirect('student:exam_result', pk=assignment.pk)
    if attempt.submitted_at is not None:
        return redirect('student:exam_result', pk=assignment.pk)

    from problems.assignment_rows import apply_draft

    rows = build_rows(assignment, request.user, with_comments=False)
    drafts = exam_engine.drafts_map(attempt)
    for row in rows:
        # Форму заполняем ЧЕРНОВИКОМ: ученик вернулся после обрыва и должен
        # увидеть написанное, а не пустые поля. Заодно пересчитывается
        # состояние задачи — «в работе» считается по черновику.
        apply_draft(row, drafts.get(row['item'].pk))

    return render(request, 'student/exam_take.html', {
        'assignment': assignment,
        'attempt': attempt,
        'rows': rows,
        'seconds_left': exam_engine.seconds_remaining(attempt, now),
        'answered_count': sum(1 for row in rows if row['answered']),
    })


@student_required
def exam_time(request, pk):
    """«Сколько осталось» — самый дешёвый запрос страницы.

    Существует ради одного: сверка времени обязана идти по таймеру, а не
    только вместе с автосохранением. Ученик, который смотрит на часы и
    ничего не печатает, раньше не сверялся с сервером вообще.
    """
    assignment = _exam_or_404(request, pk)
    attempt = assignment.exam_attempts.filter(student=request.user).first()
    if attempt is None:
        return JsonResponse({'expired': True, 'seconds_remaining': 0})

    now = timezone.now()
    expired = exam_engine.finalize_if_expired(attempt, now) \
        or attempt.submitted_at is not None
    left = exam_engine.seconds_remaining(attempt, now)
    return JsonResponse({'expired': bool(expired),
                         'seconds_remaining': 0 if expired else left})


@require_POST
@student_required
def exam_autosave(request, pk):
    """Автосохранение одного ответа.

    Ответ — JSON, потому что уходит по ходу набора, без перезагрузки.
    В ответе ВСЕГДА `seconds_remaining`: клиент по нему пересинхронизирует
    свой отсчёт, и подкрутка часов на устройстве ничего не даёт.
    """
    from problems.models import AssignmentItem

    assignment = _exam_or_404(request, pk)
    attempt = assignment.exam_attempts.filter(student=request.user).first()
    if attempt is None:
        return JsonResponse({'error': 'Попытка не начата'}, status=400)

    now = timezone.now()
    if exam_engine.finalize_if_expired(attempt, now) or \
            not exam_engine.can_accept(attempt, now):
        return JsonResponse({'error': 'Время вышло', 'expired': True,
                             'seconds_remaining': 0}, status=409)

    try:
        body = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': 'Неверный формат'}, status=400)

    item = get_object_or_404(AssignmentItem, pk=body.get('item_id'),
                             assignment=assignment)
    try:
        left = exam_engine.save_draft(attempt, item,
                                      answer=body.get('answer') or '',
                                      solution=body.get('solution') or '',
                                      now=now)
    except Exception:
        # ⚠️ Автосохранение НИКОГДА не отвечает пятисоткой. Пятисотка для
        # клиента неотличима от «сохранилось», и он выбросил бы значение из
        # очереди. Отвечаем «попробуй ещё» — написанное остаётся на странице
        # и уедет следующей попыткой или вместе с кнопкой «Завершить».
        import logging
        logging.getLogger(__name__).exception(
            'Автосохранение не удалось (попытка %s, позиция %s)',
            attempt.pk, item.pk)
        return JsonResponse(
            {'error': 'Не удалось сохранить, пробуем ещё', 'retry': True,
             'seconds_remaining': exam_engine.seconds_remaining(attempt, now)},
            status=503)

    from problems import timefmt

    return JsonResponse({'ok': True, 'seconds_remaining': left,
                         'saved_at': timefmt.fmt(now, '%H:%M:%S')})


@require_POST
@student_required
def exam_finish(request, pk):
    """Сдача. Последние значения полей принимаем вместе с нажатием.

    Форма шлёт всё содержимое ещё раз: последняя порция набранного могла
    не успеть уехать автосохранением, а терять её нельзя.
    """
    from problems.assignment_rows import read_answer

    assignment = _exam_or_404(request, pk)
    attempt = assignment.exam_attempts.filter(student=request.user).first()
    if attempt is None:
        return redirect('student:exam_intro', pk=assignment.pk)

    now = timezone.now()
    if exam_engine.finalize_if_expired(attempt, now):
        messages.warning(request, 'Время вышло — работа сдана автоматически.')
        return redirect('student:exam_result', pk=assignment.pk)

    if exam_engine.can_accept(attempt, now):
        for item in assignment.items.select_related('catalog_problem',
                                                    'custom_problem'):
            answer, solution, _ = read_answer(request, item)
            if answer or solution:
                exam_engine.save_draft(attempt, item, answer, solution, now)

    exam_engine.submit_attempt(attempt, now)
    messages.success(request, 'Работа сдана.')
    return redirect('student:exam_result', pk=assignment.pk)


@student_required
def exam_result(request, pk):
    """Результат ученику. Честно помечает, что ещё не проверено человеком."""
    assignment = _exam_or_404(request, pk)
    attempt = assignment.exam_attempts.filter(student=request.user).first()
    if attempt is None:
        return redirect('student:exam_intro', pk=assignment.pk)
    exam_engine.finalize_if_expired(attempt)
    attempt.refresh_from_db()
    if attempt.submitted_at is None:
        return redirect('student:exam_take', pk=assignment.pk)

    summary = exam_engine.attempt_summary(attempt)
    for row in summary['rows']:
        row['solution_visible'] = row['item'].is_solution_visible_for(
            request.user)
        row['solution_hint'] = row['item'].solution_unlock_hint()

    spent = None
    if attempt.started_at and attempt.submitted_at:
        spent = int((attempt.submitted_at - attempt.started_at)
                    .total_seconds() // 60)

    return render(request, 'student/exam_result.html', {
        'assignment': assignment,
        'attempt': attempt,
        'summary': summary,
        'spent_minutes': spent,
        'group_average': _group_average(assignment),
        # ⚠️ «Придержать результат до проверки» относится к АВТОПРОВЕРКЕ.
        # Как только преподаватель проверил хоть одну задачу руками, баллы
        # показываем: он их и ставил для ученика.
        'show_scores': (assignment.show_results_immediately
                        or summary['reviewed_by_teacher'] > 0),
    })


def _group_average(assignment):
    """Средний балл группы — ТОЛЬКО при включённом рейтинге.

    Сравнение с другими включает репетитор (`leaderboard_enabled`), и по
    умолчанию оно выключено: не всякой группе полезно знать, кто где.
    """
    group = assignment.group
    if group is None or not group.leaderboard_enabled:
        return None

    from django.db.models import Avg

    from problems.models import TeacherFeedback

    average = TeacherFeedback.objects.filter(
        submission__assignment=assignment,
        score__isnull=False).aggregate(value=Avg('score'))['value']
    return round(float(average), 2) if average is not None else None
