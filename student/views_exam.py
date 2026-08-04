"""
Контрольные глазами ученика.

Отдельный модуль, а не ещё одна ветка в `views.py`: у контрольной свой цикл
(старт → таймер → автосохранение → сдача → результат), и мешать его с
домашкой, которую можно дописывать когда угодно, значит однажды перепутать
правила и разрешить дописать контрольную после звонка.

Фаза 0.4 — только страница «до старта». Прохождение, автосохранение и
результаты — Часть C.
"""
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from .views import exam_schedule_label, student_required


@student_required
def exam_intro(request, pk):
    """Страница контрольной до старта: что это, сколько времени, сколько задач.

    Кнопка «Начать» намеренно отделена от списка работ: таймер запускает
    СЕРВЕР в момент нажатия, и нажатие должно быть осознанным.
    """
    from problems.models import Assignment

    assignment = get_object_or_404(Assignment, pk=pk, students=request.user,
                                   kind=Assignment.Kind.EXAM)
    now = timezone.now()
    attempt = assignment.exam_attempts.filter(student=request.user).first()
    is_open, closed_reason = assignment.open_state_for(request.user, now)

    return render(request, 'student/exam_intro.html', {
        'assignment': assignment,
        'attempt': attempt,
        'is_open': is_open,
        'closed_reason': closed_reason,
        'schedule': exam_schedule_label(assignment),
        'items_count': assignment.items.count(),
        'starts_at': assignment.starts_at,
        'deadline': assignment.deadline_at,
        'now': now,
    })
