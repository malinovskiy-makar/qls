"""
Представления для календаря. Главная страница + JSON-эндпоинты для FullCalendar.
"""

import datetime
import json

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from problems.jsonsafe import dumps_for_script
from problems.models import (
    Assignment, CalendarEvent, StudentGroup, Submission,
)
# Проверка роли — ОДНА на проект. `teacher/access.py` для того и заведён
# («переиспользуемый — его ждут все новые экраны»); свою копию здесь
# заводить нельзя, иначе систем ролей снова станет две.
from teacher.access import is_student, is_tutor

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

EVENT_COLORS = {
    'lesson':   '#3b82f6',
    'homework': '#f97316',
    'olympiad': '#10b981',
    'other':    '#6b7280',
}
OVERDUE_COLOR = '#ef4444'


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _visible_qs(user):
    """QuerySet событий, видимых пользователю.

    ⚠️ РОЛЬ СПРАШИВАЕТСЯ У `teacher.access`, А НЕ У ПОЛЯ `user.role`.
    Здесь стояло `getattr(user, 'role', '') == 'teacher'` — то есть третье
    в проекте место, знающее только СТАРУЮ систему ролей. Репетитор,
    заведённый через `UserProfile`, попадал в последнюю ветку и не видел
    в календаре даже собственных событий. `is_tutor` и `is_student` смотрят
    обе системы; вторых реализаций проверки роли в проекте больше нет.
    """
    base = CalendarEvent.objects.select_related(
        'author', 'assignment',
    ).prefetch_related('groups')

    if user.is_superuser:
        return base.all()

    if is_student(user):
        my_groups = user.enrolled_groups.all()
        return base.filter(
            Q(is_global=True) | Q(groups__in=my_groups)
        ).distinct()

    if is_tutor(user):
        my_groups = user.teaching_groups.all()
        return base.filter(
            Q(is_global=True) | Q(author=user) | Q(groups__in=my_groups)
        ).distinct()

    return base.filter(is_global=True)


def _format_event(event, user, now=None):
    """Форматирует CalendarEvent для FullCalendar."""
    if now is None:
        now = timezone.now()

    # Пользовательский цвет имеет приоритет над типовым
    if event.color:
        bg_color = event.color
    else:
        bg_color = EVENT_COLORS.get(event.event_type, '#6b7280')
        # Просроченные домашки перекрашиваем только если нет ручного цвета
        if (event.event_type == 'homework'
                and event.assignment
                and event.assignment.deadline
                and event.assignment.deadline <= now):
            bg_color = OVERDUE_COLOR

    local_start = timezone.localtime(event.start_datetime)
    time_str = local_start.strftime('%H:%M')
    short_title = f'{time_str} {event.title[:10]}'

    tutor = user.is_superuser or is_tutor(user)
    can_edit = user.is_superuser or event.author_id == user.pk

    assignment_url = None
    if event.assignment_id:
        if tutor:
            assignment_url = f'/teacher/assignment/{event.assignment_id}/'
        elif is_student(user):
            assignment_url = f'/student/assignment/{event.assignment_id}/'

    submissions_info = None
    if event.assignment_id and tutor:
        total = event.assignment.students.count()
        submitted = Submission.objects.filter(
            assignment_id=event.assignment_id,
            status__in=['submitted', 'reviewed'],
        ).values('student').distinct().count()
        submissions_info = {'submitted': submitted, 'total': total}

    data = {
        'id': event.pk,
        'title': short_title,
        'start': event.start_datetime.isoformat(),
        'backgroundColor': bg_color,
        'borderColor': bg_color,
        'textColor': '#ffffff',
        'extendedProps': {
            'event_type': event.event_type,
            'event_color': event.color,   # для предзаполнения в форме редактирования
            'full_title': event.title,
            'description': event.description,
            'assignment_id': event.assignment_id,
            'assignment_url': assignment_url,
            'is_recurring': event.is_recurring,
            'parent_event_id': event.parent_event_id,
            'can_edit': can_edit,
            'submissions_info': submissions_info,
        },
    }
    if event.end_datetime:
        data['end'] = event.end_datetime.isoformat()
    return data


def _parse_aware_dt(date_str, time_str):
    """Возвращает timezone-aware datetime или None при ошибке."""
    if not date_str:
        return None
    try:
        raw = datetime.datetime.fromisoformat(
            f'{date_str}T{time_str}' if time_str else f'{date_str}T00:00:00'
        )
        return timezone.make_aware(raw)
    except (ValueError, OverflowError):
        return None


def _own_assignment(user, assignment_id):
    """Работа, которую этот пользователь вправе привязать к событию. Или None.

    ⚠️ ЗАЧЕМ ЭТО ПОЯВИЛОСЬ. Раньше и в создании, и в правке события стояло
    просто `Assignment.objects.get(pk=assignment_id)` — БЕЗ проверки владения.
    Репетитор мог подставить номер ЧУЖОЙ работы, и календарь начинал
    показывать про неё `submissions_info`: сколько всего учеников и сколько
    уже сдали. То есть номер чужой работы обменивался на сведения о её ходе.

    Сужаем queryset, а не проверяем после загрузки: забытая проверка — дыра,
    забытое сужение — пустая выдача.
    """
    if not assignment_id:
        return None
    assignments = Assignment.objects.all()
    if not user.is_superuser:
        assignments = assignments.filter(
            Q(author=user) | Q(group__teacher=user)
        ).distinct()
    return assignments.filter(pk=assignment_id).first()


def _own_event(user, pk):
    """Событие, которое этот пользователь вправе ПРАВИТЬ. Или None.

    ⚠️ ЗАЧЕМ ЭТО ПОЯВИЛОСЬ (сессия 3Б, хвост сессии 3А). Правка и удаление
    брали объект `get_object_or_404(CalendarEvent, pk=pk)` и только потом
    смотрели на автора. Дыры не было — проверка по существу верная, — но
    коды ответа рассказывали лишнее:

        чужой существующий pk  -> 403 «Нет прав»
        несуществующий pk      -> 404

    То есть перебором номеров можно было составить список существующих
    событий, не имея к ним доступа. Сужение делает оба случая
    неотличимыми: для этого человека такого события просто нет.

    Сужаем queryset, а не проверяем после загрузки: забытая проверка —
    дыра, забытое сужение — пустая выдача.
    """
    events = CalendarEvent.objects.all()
    if not user.is_superuser:
        events = events.filter(author=user)
    return events.filter(pk=pk).first()


def _not_found():
    """Один и тот же отказ на «нет такого» и «не ваше».

    Ответ остаётся JSON: экран календаря разбирает тело (`d.status`), а не
    код ответа, и страница Django «не найдено» сломала бы ему разбор.
    """
    return JsonResponse({'error': 'Событие не найдено'}, status=404)


def _set_groups(event, group_ids, user, is_global):
    """Устанавливает группы события с проверкой прав."""
    if is_global:
        event.groups.clear()
        return
    if not group_ids:
        event.groups.clear()
        return
    qs = StudentGroup.objects.filter(pk__in=group_ids)
    if not user.is_superuser:
        qs = qs.filter(teacher=user)
    event.groups.set(qs)


# ---------------------------------------------------------------------------
# Главная страница
# ---------------------------------------------------------------------------

@login_required(login_url='/login/')
def calendar_view(request):
    """Единая страница календаря для всех ролей."""
    user = request.user
    role = getattr(user, 'role', '')

    if user.is_superuser:
        groups = list(StudentGroup.objects.values('id', 'name'))
        assignments = list(
            Assignment.objects.order_by('-created_at').values('id', 'name')[:50]
        )
    elif role == 'teacher':
        groups = list(user.teaching_groups.values('id', 'name'))
        now = timezone.now()
        assignments = list(
            Assignment.objects.filter(author=user)
            .filter(Q(deadline__isnull=True) | Q(deadline__gte=now))
            .order_by('-created_at')
            .values('id', 'name')[:50]
        )
    else:
        groups = []
        assignments = []

    return render(request, 'calendar_stub/calendar.html', {
        'user_role': 'admin' if user.is_superuser else role,
        # ⚠️ НЕ `json.dumps`. Названия занятий и работ печатает репетитор, а
        # уезжают они прямо внутрь тега <script>. `json.dumps` оставляет `<`
        # как есть, поэтому занятие с названием `</script><img ...>` закрывало
        # наш скрипт и открывало свой. `dumps_for_script` экранирует `<`, `>`
        # и `&` — как штатный `json_script` Django.
        'groups_json': dumps_for_script(groups),
        'assignments_json': dumps_for_script(assignments),
    })


# ---------------------------------------------------------------------------
# API-эндпоинты
# ---------------------------------------------------------------------------

@login_required(login_url='/login/')
def events_api(request):
    """GET /calendar/api/events/ — список событий для FullCalendar."""
    start_str = request.GET.get('start', '')
    end_str   = request.GET.get('end', '')

    qs = _visible_qs(request.user)

    if start_str:
        try:
            start_dt = datetime.datetime.fromisoformat(
                start_str.replace('Z', '+00:00')
            )
            qs = qs.filter(start_datetime__gte=start_dt)
        except ValueError:
            pass

    if end_str:
        try:
            end_dt = datetime.datetime.fromisoformat(
                end_str.replace('Z', '+00:00')
            )
            qs = qs.filter(start_datetime__lte=end_dt)
        except ValueError:
            pass

    now = timezone.now()
    return JsonResponse([_format_event(e, request.user, now) for e in qs], safe=False)


@login_required(login_url='/login/')
@require_http_methods(['POST'])
def event_create(request):
    """POST /calendar/api/events/create/"""
    user = request.user

    # Роль — через общую проверку, а не через старое поле `user.role`:
    # репетитор из `UserProfile` иначе не может создать событие вовсе.
    if not (user.is_superuser or is_tutor(user)):
        return JsonResponse({'error': 'Нет прав'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Неверный JSON'}, status=400)

    title       = data.get('title', '').strip()
    event_type  = data.get('event_type', 'lesson')
    date_str    = data.get('date', '')
    time_start  = data.get('time_start', '')
    time_end    = data.get('time_end', '')
    description = data.get('description', '')
    group_ids   = data.get('group_ids', [])
    is_global   = bool(data.get('is_global', False)) and user.is_superuser
    assignment_id = data.get('assignment_id')
    is_recurring  = bool(data.get('is_recurring', False))
    recur_weeks   = max(1, int(data.get('recur_weeks', 4)))
    color         = data.get('color', '').strip()
    if color and not color.startswith('#'):
        color = ''

    if not title:
        return JsonResponse({'error': 'Укажите название'}, status=400)

    if event_type == 'olympiad' and not user.is_superuser:
        event_type = 'other'

    start_dt = _parse_aware_dt(date_str, time_start)
    if start_dt is None:
        return JsonResponse({'error': 'Укажите корректную дату'}, status=400)

    end_dt = _parse_aware_dt(date_str, time_end) if time_end else None

    assignment = None
    if assignment_id and event_type == 'homework':
        # Чужая работа сюда не привяжется — см. `_own_assignment`.
        assignment = _own_assignment(user, assignment_id)

    event = CalendarEvent.objects.create(
        title=title,
        event_type=event_type,
        color=color,
        start_datetime=start_dt,
        end_datetime=end_dt,
        description=description,
        assignment=assignment,
        author=user,
        is_global=is_global,
        is_recurring=is_recurring,
        recur_weeks=recur_weeks,
    )
    _set_groups(event, group_ids, user, is_global)

    if is_recurring and recur_weeks > 1:
        for week in range(1, recur_weeks):
            delta = datetime.timedelta(weeks=week)
            copy = CalendarEvent.objects.create(
                title=title,
                event_type=event_type,
                color=color,
                start_datetime=start_dt + delta,
                end_datetime=(end_dt + delta) if end_dt else None,
                description=description,
                assignment=assignment,
                author=user,
                is_global=is_global,
                is_recurring=True,
                recur_weeks=recur_weeks,
                parent_event=event,
            )
            _set_groups(copy, group_ids, user, is_global)

    return JsonResponse({'status': 'ok', 'id': event.pk})


@login_required(login_url='/login/')
def event_detail(request, pk):
    """GET /calendar/api/events/<pk>/"""
    # Сначала сузить до видимого, потом взять. Порядок важен: обратный
    # отвечал 403 на чужое существующее событие и 404 на несуществующее,
    # и разница между ответами сама была ответом.
    event = _visible_qs(request.user).filter(pk=pk).first()
    if event is None:
        return _not_found()
    return JsonResponse(_format_event(event, request.user))


@login_required(login_url='/login/')
@require_http_methods(['POST'])
def event_update(request, pk):
    """POST /calendar/api/events/<pk>/update/"""
    user  = request.user
    event = _own_event(user, pk)
    if event is None:
        return _not_found()

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Неверный JSON'}, status=400)

    title = data.get('title', event.title).strip()
    if not title:
        return JsonResponse({'error': 'Укажите название'}, status=400)

    event_type  = data.get('event_type', event.event_type)
    date_str    = data.get('date', '')
    time_start  = data.get('time_start', '')
    time_end    = data.get('time_end', '')
    description = data.get('description', event.description)
    group_ids   = data.get('group_ids', [])
    is_global   = bool(data.get('is_global', event.is_global)) and user.is_superuser
    assignment_id = data.get('assignment_id')
    color         = data.get('color', event.color).strip()
    if color and not color.startswith('#'):
        color = event.color

    if event_type == 'olympiad' and not user.is_superuser:
        event_type = event.event_type

    if date_str:
        start_dt = _parse_aware_dt(date_str, time_start)
        if start_dt is None:
            return JsonResponse({'error': 'Неверный формат даты'}, status=400)
        event.start_datetime = start_dt
        event.end_datetime = _parse_aware_dt(date_str, time_end) if time_end else None

    event.title       = title
    event.event_type  = event_type
    event.color       = color
    event.description = description
    event.is_global   = is_global

    if assignment_id and event_type == 'homework':
        # Чужая работа сюда не привяжется — см. `_own_assignment`.
        event.assignment = _own_assignment(user, assignment_id)
    elif not assignment_id:
        event.assignment = None

    event.save()
    _set_groups(event, group_ids, user, is_global)
    return JsonResponse({'status': 'ok'})


@login_required(login_url='/login/')
@require_http_methods(['POST'])
def event_delete(request, pk):
    """POST /calendar/api/events/<pk>/delete/"""
    user  = request.user
    event = _own_event(user, pk)
    if event is None:
        return _not_found()

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = {}

    if data.get('delete_all', False):
        # ⚠️ ПРАВО ПРОВЕРЕНО НА ОДНОМ ЗВЕНЕ, А УДАЛЯЕТСЯ ВСЯ ЦЕПОЧКА.
        # Так было раньше: выше проверяется авторство `event`, а `.delete()`
        # шёл по `parent` и всем его потомкам без единой проверки. Достаточно
        # быть автором ОДНОГО звена, чтобы снести серию целиком — а звенья
        # серии не обязаны быть одного автора: `parent_event` — обычный
        # внешний ключ, и админка позволяет его переставить.
        #
        # Сужаем сам queryset, а не добавляем ещё одну проверку рядом:
        # забытая проверка — это дыра, забытое сужение — пустая выдача.
        parent = event.parent_event or event
        chain = CalendarEvent.objects.filter(
            Q(pk=parent.pk) | Q(parent_event=parent)
        )
        if not user.is_superuser:
            chain = chain.filter(author=user)
        # ⚠️ ВЫБРАНО «УДАЛИТЬ ТОЛЬКО СВОЁ», А НЕ «ОТКАЗАТЬ ЦЕЛИКОМ».
        # Отказ целиком означал бы, что репетитор не может убрать свою серию
        # из-за чужого звена, которое он не видит и исправить не может, —
        # тупик без выхода. «Только своё» предсказуемо: чужое не трогается
        # никогда, а своё уходит полностью.
        #
        # Осиротевшие чужие звенья не ломаются: `parent_event` объявлен
        # с `on_delete=SET_NULL`, они просто перестают быть частью серии.
        deleted = chain.delete()[0]
    else:
        event.delete()
        deleted = 1

    return JsonResponse({'status': 'ok', 'deleted': deleted})
