"""
Проверка роли — одна на все экраны платформы.

Раньше проверка жила прямо в `teacher/views.py` (`teacher_required`) и знала
только про старое поле `User.role`. Теперь ролей две системы: старая (`User.role`)
и новая (`UserProfile.role`), и они синхронизируются. Декоратор ниже смотрит
обе, поэтому одинаково пускает и репетитора из профиля, и «преподавателя»,
заведённого до появления профилей.

Переиспользуемый — его ждут все новые экраны: группы, редактор задач,
проверка решений, дашборд.
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def is_tutor(user):
    """Репетитор ли это. Персонал (is_staff) пускаем всегда — это отладка."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    if user.is_staff:
        return True
    profile = getattr(user, 'profile', None)
    if profile is not None and profile.role == 'tutor':
        return True
    # Пользователи, заведённые до появления профилей.
    return getattr(user, 'role', '') == 'teacher'


def is_student(user):
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    profile = getattr(user, 'profile', None)
    if profile is not None and profile.role == 'student':
        return True
    return getattr(user, 'role', '') == 'student'


def tutor_required(view_func):
    """Только для репетитора. Иначе 403, а не «пустая страница»."""
    @login_required(login_url='/login/')
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not is_tutor(request.user):
            raise PermissionDenied('Эта страница только для репетитора.')
        return view_func(request, *args, **kwargs)
    return wrapper


def own_group_or_404(user, group_id):
    """Группа этого репетитора — или 404.

    Именно 404, а не 403: чужая группа для репетитора не «запрещена»,
    её для него просто не существует, и номер чужой группы не должен
    подтверждаться сообщением об ошибке.
    """
    from django.shortcuts import get_object_or_404

    from problems.models import StudentGroup

    if user.is_staff:
        return get_object_or_404(StudentGroup, pk=group_id)
    return get_object_or_404(StudentGroup, pk=group_id, teacher=user)


def group_assignment_or_404(group, assignment_id):
    """Задание внутри этой группы — или 404."""
    from django.shortcuts import get_object_or_404

    from problems.models import Assignment

    return get_object_or_404(Assignment, pk=assignment_id, group=group)


def group_id_param(request):
    """Номер занятия из адреса — ТОЛЬКО если это число, иначе пусто.

    ⚠️ ЗАЧЕМ. Экраны создания работы таскают номер занятия через `?group=`,
    и он уходит прямо в `{% url 'teacher:group_detail' group_id %}` в общей
    шапке. Django на нечисловом значении бросает `NoReverseMatch`, и все три
    экрана создания отвечали ПЯТИСОТКОЙ на `?group=abc`.

    Найдено в сессии 10 своей же проверкой (сценарий подставил `group=null`).
    Дефект был и до сведения панели — шапка `_build_head.html` разбирала
    значение так с самого её появления.

    Проверять существование занятия здесь НЕ надо: номер тут нужен только
    чтобы собрать ссылку и не потеряться между экранами, а всё, что меняет
    данные, идёт через `own_group_or_404`.
    """
    raw = (request.POST.get('group') or request.GET.get('group') or '').strip()
    return raw if raw.isdigit() else ''
