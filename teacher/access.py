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
    данные, идёт через `own_group_or_404`. Отказ по чужому и
    несуществующему занятию даёт `group_param_refusal` — см. ниже.
    """
    raw = (request.POST.get('group') or request.GET.get('group') or '').strip()
    return raw if raw.isdigit() else ''


def group_param_refusal(request):
    """ Отказ, если `?group=` называет ЧУЖОЕ или несуществующее занятие.

    Возвращает готовый ответ-перенаправление или None, если всё в порядке.

    ВНИМАНИЕ: ЗАЧЕМ ОТДЕЛЬНАЯ ПРОВЕРКА (ревью 15.08, фаза 15). Подстановка
    `?group=13` открывала экран создания как ни в чём не бывало: крошка
    молча теряла имя занятия (`group_label_param` отдаёт пустую строку и
    ТЕМ САМЫМ МАСКИРУЕТ ошибку), работа собиралась, а переключатель
    «Контрольная» уводил на `/teacher/groups/13/exams/new/` и выдавал
    страницу Django «No StudentGroup matches the given query». То есть
    отказ был, но приходил через три шага и на чужом языке.

    Отказ обязан быть СРАЗУ и с возвратом туда, откуда можно продолжить, —
    на «Ученики». Пустой параметр законен: работу создают и без занятия.
    """
    from django.contrib import messages
    from django.shortcuts import redirect
    from django.urls import reverse

    from problems.models import StudentGroup

    raw = (request.POST.get('group') or request.GET.get('group') or '').strip()
    if not raw:
        return None
    if (raw.isdigit()
            and StudentGroup.objects.filter(pk=int(raw),
                                            teacher=request.user).exists()):
        return None
    messages.error(request, 'Такого занятия нет — выберите его из списка.')
    return redirect(reverse('teacher:groups'))


def lesson_for_student(user, student, request=None):
    """Занятие, в контексте которого смотрят на ученика. Нужно КРОШКЕ.

    ⚠️ ЗАЧЕМ. На карточке ученика вместо крошки стояла ссылка
    `javascript:history.back()` — «Назад» уводило туда, откуда пришли, то
    есть куда угодно: из поиска, из соседней вкладки, с обновлённой
    страницы — никуда. Крошка обязана вести в ОБЗОР ЗАНЯТИЯ, а для этого
    занятие надо назвать.

    Правило выбора:
    1. Пришли из занятия (`?group=`) — берём его, но только если оно этого
       репетитора И в нём есть этот ученик. Чужой номер в адресе не должен
       подписывать крошку чужим названием.
    2. Иначе — занятие этого репетитора с этим учеником, первое по
       алфавиту. У ученика их обычно одно; когда их два, порядок обязан
       быть устойчивым, иначе крошка меняется от загрузки к загрузке.
    3. Ни одного — None, и крошка обходится двумя звеньями.
    """
    from problems.models import StudentGroup

    lessons = StudentGroup.objects.filter(students=student)
    if not user.is_staff:
        lessons = lessons.filter(teacher=user)

    if request is not None:
        raw = group_id_param(request)
        if raw:
            asked = lessons.filter(pk=raw).first()
            if asked is not None:
                return asked

    # ⚠️ Сортируем УЖЕ ВЫБРАННЫЕ, а не в базе: у индивидуального занятия на
    # экране стоит имя ученика (`display_name`), а в базе — название группы,
    # и «первое по алфавиту» по названию выбрало бы не то, что видно глазам.
    return min(lessons, key=lambda g: g.display_name.lower(), default=None)


def solo_lesson_for(user, student):
    """Индивидуальное занятие, которое ЗАМЕНЯЕТ карточку ученика. Или None.

    ⚠️ ЗАЧЕМ (решение владельца 17.08). У индивидуального ученика «занятие»
    и «ученик» — одно лицо, и два экрана про него показывали почти одно и
    то же. Экран занятия забрал себе заметки, а старый адрес карточки ведёт
    на него — но ТОЛЬКО когда карточке нечего показать отдельно.

    Условий два, и оба обязательны:
    1. у этого ученика с этим репетитором РОВНО ОДНО занятие;
    2. и это занятие индивидуальное.

    Иначе карточка работает как раньше: ученик может одновременно ходить в
    группу и заниматься индивидуально, и тогда экран занятия рассказывает
    только про одну половину его учёбы.

    ⚠️ Предикат «индивидуальное» ОДИН на проект — `single_student` (он же
    даёт шаблонам переменную `solo`). Второго рядом не заводим: на этой
    ловушке проект уже стоял с двумя предикатами «это тест».
    """
    from problems.models import StudentGroup

    lessons = StudentGroup.objects.filter(students=student)
    if not user.is_staff:
        lessons = lessons.filter(teacher=user)
    lessons = list(lessons[:2])
    if len(lessons) != 1:
        return None
    lesson = lessons[0]
    return lesson if lesson.single_student is not None else None


def group_label_param(request):
    """Название занятия из `?group=` — для крошки экранов создания.

    ⚠️ ЗАЧЕМ. Крошка писала подчёркнутое слово «занятие» вместо настоящего
    названия: `Ученики → занятие → новая работа`. Номер в адресе был, имени
    в шаблоне не было, и ссылка выглядела заглушкой.

    Пусто, если номера нет, занятие не найдено или принадлежит другому
    репетитору. Пустое имя убирает саму крошку — подставлять в неё название
    чужой группы нельзя, а показывать ссылку без слов бессмысленно.
    """
    from problems.models import StudentGroup

    raw = group_id_param(request)
    if not raw:
        return ''
    groups = StudentGroup.objects.filter(pk=raw)
    if not request.user.is_staff:
        groups = groups.filter(teacher=request.user)
    group = groups.first()
    return group.display_name if group is not None else ''
