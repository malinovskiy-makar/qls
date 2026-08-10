"""
Статистика глазами репетитора. БЕЗ ГЕЙМИФИКАЦИИ — намеренно.

Ни опыта, ни уровней, ни серий, ни достижений. Это не упущение: чужая
мотивационная механика репетитору не нужна вовсе, а на экране она заняла бы
место, которое должно достаться диагностике. Репетитору нужно за десять
секунд понять, КОМУ ЧТО ЗАДАТЬ, — для этого есть тепловая матрица
«ученики × темы» и список «требуют внимания».
"""
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from problems import stats as stats_module

from .access import own_group_or_404, tutor_required


@tutor_required
def group_stats(request, pk):
    """устарело → вкладка «Обзор» страницы группы.

    ⚠️ Статистика ПЕРЕЕХАЛА на первую вкладку группы и стала вкладкой по
    умолчанию. Причина: это самый содержательный экран кабинета (тепловая
    матрица «ученики × темы» и «требуют внимания»), а лежал он четвёртым, и
    на нём ПРОПАДАЛ ряд вкладок — у страницы был свой шаблон без навигации.

    Адрес оставлен редиректом: он мог попасть в закладки и в переписку, а
    страница, отвечающая 404 там, где вчера был экран, — это сломанный
    продукт, а не «мы переехали».
    """
    group = own_group_or_404(request.user, pk)
    period = request.GET.get('period') or ''
    url = reverse('teacher:group_detail', args=[group.pk]) + '?tab=overview'
    if period:
        url += '&period=%s' % period
    return redirect(url)


@tutor_required
def student_stats(request, pk):
    """устарело → карточка ученика `/teacher/student/<id>/progress/`.

    ⚠️ РЕШЕНИЕ СТОП-ГЕЙТА ФАЗЫ 10.1 (сессия 7). Об одном ученике было ДВА
    экрана, и оба стояли ссылками в ОДНОЙ таблице обзора группы: репетитор
    видел две кнопки на одного человека и не мог знать, чем они отличаются.
    Основным оставлена карточка `student_progress` — на неё ведёт кнопка
    «открыть» и именно её ревьюил владелец. Всё, чего там не было
    («сильные и слабые стороны», теплокарта активности за полгода),
    перенесено туда; этот адрес оставлен редиректом ради закладок.
    """
    from problems.models import User

    student = get_object_or_404(
        User.objects.filter(enrolled_groups__teacher=request.user).distinct(),
        pk=pk)
    return redirect('teacher:student_progress', pk=student.pk)


def _student_stats_legacy(request, pk):
    """Прежний экран статистики ученика. Не подключён к маршрутам.

    Оставлен справкой на одну сессию: по нему видно, что именно перенесено
    в карточку ученика. Удалить после приёмки.
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
