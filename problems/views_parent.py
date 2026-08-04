"""
Кабинет родителя.

⚠️ ЧЕГО РОДИТЕЛЬ НЕ ВИДИТ — И ЭТО РЕШЕНИЕ, А НЕ НЕДОДЕЛКА:
никаких показателей работы РЕПЕТИТОРА. Ни скорости проверки, ни времени
ответа на вопрос, ни числа проведённых занятий, ни «сколько домашек
преподаватель ещё не проверил». Платит нам репетитор; инструмент контроля
над ним, вложенный в руки его клиента, убивает продажу — родитель начнёт
предъявлять по нашим цифрам, а виноватыми окажемся мы оба.

Родитель видит ровно одно: занимается ли ребёнок и что у него получается.
Геймификации здесь тоже нет — «серия 12 дней» родителю не говорит ничего,
а «эластичность просела» говорит.
"""
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, render

from . import stats as stats_module


def _children(user):
    """Дети этого родителя. Пусто у всех остальных."""
    from .models import User
    return User.objects.filter(parent_links__parent=user).distinct()


@login_required
def parent_home(request):
    """Список детей. Кто не родитель — увидит пустой список, и это честно."""
    children = list(_children(request.user))
    rows = []
    for child in children:
        overview = stats_module.overview(child, 'month')
        rows.append({
            'student': child,
            'solved': overview['solved'],
            'accuracy': overview['accuracy'],
            'minutes': overview['minutes'],
        })
    return render(request, 'platform/parent_home.html', {'rows': rows})


@login_required
def parent_student(request, pk):
    """Статистика одного ребёнка.

    Доступ строго через связь: `_children()` — это queryset «мои дети», и
    чужой ребёнок не находится вовсе. 404, а не 403: существование чужого
    ребёнка в системе — тоже сведения, которых родителю знать незачем.
    """
    student = get_object_or_404(_children(request.user), pk=pk)
    period = request.GET.get('period') or 'month'
    if period not in dict(stats_module.PERIODS):
        period = 'month'

    return render(request, 'platform/parent_student.html', {
        'student': student,
        'period': period,
        'periods': stats_module.PERIODS,
        'overview': stats_module.overview(student, period),
        'quarter': stats_module.overview(student, 'month'),
        'ranking': stats_module.strongest_weakest(student, 'all'),
        'calendar': stats_module.activity_calendar(student, 90),
        'works': _works(student),
    })


def _works(student, limit=10):
    """Сданные работы и оценки — без единого слова про репетитора.

    Показываем ЧТО сдал ребёнок и КАКОЙ балл получил. Не показываем, когда
    репетитор проверил и сколько ждал ребёнок: это показатель работы
    репетитора, а не ученика.
    """
    from .models import Submission

    rows = (Submission.objects
            .filter(student=student, status__in=('submitted', 'reviewed'))
            .select_related('assignment', 'feedback')
            .order_by('-submitted_at'))
    by_assignment = {}
    for submission in rows:
        bucket = by_assignment.setdefault(submission.assignment_id, {
            'assignment': submission.assignment,
            'submitted_at': submission.submitted_at,
            'total': 0, 'reviewed': 0, 'score': 0.0, 'has_score': False,
        })
        bucket['total'] += 1
        feedback = getattr(submission, 'feedback', None)
        if feedback is not None and feedback.score is not None:
            bucket['reviewed'] += 1
            bucket['score'] += float(feedback.score)
            bucket['has_score'] = True
    return list(by_assignment.values())[:limit]
