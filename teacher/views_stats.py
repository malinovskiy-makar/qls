"""
Статистика глазами репетитора. БЕЗ ГЕЙМИФИКАЦИИ — намеренно.

Ни опыта, ни уровней, ни серий, ни достижений. Это не упущение: чужая
мотивационная механика репетитору не нужна вовсе, а на экране она заняла бы
место, которое должно достаться диагностике. Репетитору нужно за десять
секунд понять, КОМУ ЧТО ЗАДАТЬ, — для этого есть тепловая матрица
«ученики × темы» и список «требуют внимания».
"""
from django.shortcuts import get_object_or_404, render

from problems import stats as stats_module

from .access import own_group_or_404, tutor_required


@tutor_required
def group_stats(request, pk):
    """Статистика группы: таблица, тепловая матрица, кто требует внимания."""
    group = own_group_or_404(request.user, pk)
    period = request.GET.get('period') or 'month'
    if period not in dict(stats_module.PERIODS):
        period = 'month'

    return render(request, 'teacher/groups/stats.html', {
        'group': group,
        'period': period,
        'periods': stats_module.PERIODS,
        'rows': stats_module.group_table(group, period),
        'matrix': stats_module.group_topic_matrix(group, 'all'),
        'attention': stats_module.needs_attention(group),
    })


@tutor_required
def student_stats(request, pk):
    """Один ученик глазами репетитора.

    ⚠️ Доступ проверяется на уровне QUERYSET, а не сравнением после выборки:
    `students__enrolled_groups__teacher` фильтрует ученика по «состоит в моей
    группе», и чужой ученик не находится вовсе — 404, а не 403 с намёком,
    что такой ученик существует.
    """
    from problems.models import User

    student = get_object_or_404(
        User.objects.filter(enrolled_groups__teacher=request.user).distinct(),
        pk=pk)
    period = request.GET.get('period') or 'month'
    if period not in dict(stats_module.PERIODS):
        period = 'month'

    return render(request, 'teacher/groups/student_stats.html', {
        'student': student,
        'period': period,
        'periods': stats_module.PERIODS,
        'overview': stats_module.overview(student, period),
        'topics': stats_module.topic_breakdown(student, period),
        'ranking': stats_module.strongest_weakest(student, 'all'),
        'calendar': stats_module.activity_calendar(student, 180),
        'hardest': stats_module.hardest_problems(student, 'all'),
        'sources': stats_module.source_split(student, 'all'),
        'groups': student.enrolled_groups.filter(teacher=request.user),
    })
