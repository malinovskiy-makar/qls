"""
Профиль пользователя: данные, сохранённое (задачи и графики), статистика.

Живёт в `problems`, а не в `teacher`/`student`: профиль есть у всех ролей,
и класть его в кабинет одной из них значило бы закрыть его для остальных.
"""
import json

from django.utils import formats

from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import SetPasswordForm
from django.core.files.base import ContentFile
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

# Problem нужен и в профиле (пометка «снята с публикации»), и при
# сохранении — поднимаем импорт на уровень модуля.
from .models import Problem
from .forms_accounts import AvatarForm, ProfileForm
from .models_platform import (
    CustomProblem,
    SavedFolder,
    SavedGraph,
    SavedProblem,
    UserProfile,
)


# ---------------------------------------------------------------------------
# Фаза 15 — страница профиля
# ---------------------------------------------------------------------------

def _profile_facts(user, profile_obj):
    """Полоса фактов над карточкой профиля: три-четыре числа, не больше.

    ⚠️ СВОЕГО РАСЧЁТА ЗДЕСЬ НЕТ. Берём то, что уже посчитано и закэшировано
    в `problems.stats.full_stats`; если оно почему-то недоступно, показываем
    только дату регистрации. Заводить ради шапки профиля второй счётчик
    решённых задач значило бы завести второе число, которое разойдётся с
    первым.
    """
    facts = [('на сайте с', formats.date_format(user.date_joined, 'd.m.Y'))]
    try:
        from .stats import full_stats
        data = full_stats(user, 'all') or {}
        head = data.get('profile') or {}
        overview = data.get('overview') or {}
        solved = head.get('solved', overview.get('solved'))
        if solved is not None:
            facts.append(('решено задач', str(solved)))
        streak = head.get('streak_days', head.get('streak'))
        if streak is not None:
            facts.append(('серия дней', str(streak)))
        level = head.get('level')
        if level is not None:
            facts.append(('уровень', str(level)))
    except Exception:      # noqa: BLE001
        # Статистика — украшение шапки. Её отказ не должен ронять профиль,
        # где человек, возможно, пришёл менять пароль.
        pass
    return facts


@login_required(login_url='/login/')
def password_change(request):
    """Старый адрес смены пароля — рабочий, а не редирект.

    ⚠️ ЭКРАН СМЕНЫ ПАРОЛЯ ЖИВЁТ ВО ВКЛАДКЕ «БЕЗОПАСНОСТЬ», но адрес
    `/password/change/` остаётся РАБОЧИМ: на него ведут закладки, чужие
    ссылки и, главное, существующая проверка
    `test_auth_hardening::test_password_change_kills_other_sessions`.
    Ломать её переездом экрана нельзя — она сторожит то, что смена пароля
    закрывает ВСЕ ОСТАЛЬНЫЕ сессии, а это единственная компенсация за отказ
    от старого пароля (ADR 0073).

    ⚠️ Поле `old_password`, если его прислали, форма просто не заметит:
    `SetPasswordForm` о нём не знает.
    """
    if request.method != 'POST':
        return redirect('/profile/?tab=security')
    form = SetPasswordForm(request.user, request.POST)
    if not form.is_valid():
        return render(request, 'platform/profile.html', {
            'profile': UserProfile.objects.get_or_create(user=request.user)[0],
            'form': ProfileForm(instance=request.user.profile),
            'password_form': form,
            'tab': 'security',
            'subtab': 'problems',
            'grades': range(5, 12),
            'levels': [(value, label, UserProfile.LEVEL_HINTS.get(value, ''))
                       for value, label in UserProfile.Level.choices],
            'facts': _profile_facts(request.user, request.user.profile),
            'avatar_error': '',
        })
    form.save()
    update_session_auth_hash(request, request.user)
    return redirect('/profile/?tab=security&changed=1')


@login_required(login_url='/login/')
def avatar(request, user_id):
    """Отдаёт аватар. ПЕРВАЯ вьюха проекта, отдающая файл.

    ⚠️ ЧТО ЗДЕСЬ СДЕЛАНО, ЧТОБЫ ЭТО НЕ БЫЛО ДЫРОЙ:

    * путь к файлу берётся ИЗ ПОЛЯ МОДЕЛИ, а не из запроса. Из запроса
      приходит только целое число — номер пользователя;
    * отдаётся ровно один файл на пользователя, и он наш собственный: форма
      пересжала картинку Pillow в JPEG и сама назвала её `avatars/<id>.jpg`;
    * гостю нельзя вовсе (`login_required`): аватар — лицо ребёнка, и
      выкладывать его в открытый доступ мы не будем;
    * `Content-Type` задан жёстко, из файла не угадывается.

    Почему аватар видит любой ВОШЕДШИЙ, а не только владелец: его показывает
    шапка, доска набора, список учеников группы — то есть человек и так
    видит лица тех, с кем занимается. Сужать до владельца значило бы, что
    аватар не видно нигде, кроме собственного профиля.
    """
    profile_obj = get_object_or_404(UserProfile, user_id=user_id)
    if not profile_obj.avatar:
        raise Http404('Аватара нет')
    try:
        handle = profile_obj.avatar.open('rb')
    except (FileNotFoundError, OSError):
        # Файл потерялся (перенос, чистка media) — это не 500.
        raise Http404('Аватара нет')
    response = FileResponse(handle, content_type='image/jpeg')
    # Приватно: общий кэш (nginx, прокси) держать чужое лицо не должен.
    response['Cache-Control'] = 'private, max-age=86400'
    return response


@login_required(login_url='/login/')
def profile(request):
    profile_obj, _ = UserProfile.objects.get_or_create(user=request.user)
    tab = request.GET.get('tab', 'data')
    # ⚠️ ВКЛАДКИ ЧЕТЫРЕ, И «СТАТИСТИКА» СРЕДИ НИХ — ССЫЛКА, А НЕ ВКЛАДКА:
    # готовый экран `/profile/stats/` переезжать не должен, у него свои
    # расчёты. Здесь она есть только для полосы вкладок.
    if tab not in ('data', 'security', 'saved'):
        tab = 'data'
    subtab = request.GET.get('sub', 'problems')
    if subtab not in ('problems', 'graphs'):
        subtab = 'problems'

    form = ProfileForm(instance=profile_obj)
    password_form = SetPasswordForm(request.user)
    avatar_error = ''

    if request.method == 'POST':
        action = request.POST.get('action') or 'data'
        if action == 'data':
            form = ProfileForm(request.POST, instance=profile_obj)
            if form.is_valid():
                form.save()
                return redirect('/profile/?saved=1')
        elif action == 'password':
            # ⚠️ БЕЗ СТАРОГО ПАРОЛЯ — решение владельца 04.09.2026 (ADR 0073).
            # Форма Django, своей проверки пароля у нас нет.
            password_form = SetPasswordForm(request.user, request.POST)
            if password_form.is_valid():
                password_form.save()
                # Иначе смена пароля выкинула бы и самого человека.
                update_session_auth_hash(request, request.user)
                return redirect('/profile/?tab=security&changed=1')
            tab = 'security'
        elif action == 'avatar':
            avatar_form = AvatarForm(request.POST, request.FILES)
            if avatar_form.is_valid():
                # Имя файла НАШЕ, а не из запроса: `avatars/<id>.jpg`.
                profile_obj.avatar.save(
                    'avatars/%d.jpg' % request.user.pk,
                    ContentFile(avatar_form.squared_jpeg().read()),
                    save=True)
                return redirect('/profile/?saved=1')
            avatar_error = ' '.join(
                avatar_form.errors.get('avatar', ['Не получилось загрузить.']))
        elif action == 'avatar_remove':
            if profile_obj.avatar:
                profile_obj.avatar.delete(save=True)
            return redirect('/profile/')

    context = {
        'profile': profile_obj,
        'form': form,
        'password_form': password_form,
        'avatar_error': avatar_error,
        'tab': tab,
        'subtab': subtab,
        'grades': range(5, 12),
        # Уровень отдаём тройками (значение, название, описание): фильтра
        # «взять по ключу» в проекте нет, а заводить его ради одного экрана
        # значит завести ещё одну общую вещь.
        'levels': [(value, label, UserProfile.LEVEL_HINTS.get(value, ''))
                   for value, label in UserProfile.Level.choices],
        'welcome': request.GET.get('welcome') == '1',
        'saved_ok': request.GET.get('saved') == '1',
        'password_changed': request.GET.get('changed') == '1',
        'facts': _profile_facts(request.user, profile_obj),
    }
    if profile_obj.is_tutor:
        from .models import User as UserModel
        context['tutor_groups'] = request.user.teaching_groups.count()
        context['tutor_students'] = (
            UserModel.objects.filter(enrolled_groups__teacher=request.user)
            .distinct().count())

    if tab == 'saved':
        kind = (SavedFolder.Kind.GRAPHS if subtab == 'graphs'
                else SavedFolder.Kind.PROBLEMS)
        folders = list(SavedFolder.objects.filter(owner=request.user,
                                                  kind=kind))
        if subtab == 'graphs':
            saved = list(SavedGraph.objects.filter(owner=request.user,
                                                   is_deleted=False)
                         .select_related('folder'))
        else:
            saved = list(SavedProblem.objects.filter(owner=request.user,
                                                     is_deleted=False)
                         .select_related('folder', 'catalog_problem',
                                         'custom_problem'))
            # ⚠️ РЕШЕНИЕ ВЛАДЕЛЬЦА (сессия 3Б): задачу, которую шлюз качества
            # забраковал ПОСЛЕ сохранения, показываем — но с пометкой.
            #
            # Молча спрятать нельзя: подборка ученика «похудеет» без всякого
            # объяснения, и он решит, что что-то потерял. Молча показать со
            # ссылкой тоже нельзя: тогда шлюз не работает — ссылка ведёт на
            # страницу, которой для него нет.
            #
            # Признак считается ЗДЕСЬ, а не в шаблоне: шаблон не должен
            # ходить в базу и не должен знать правила шлюза.
            for item in saved:
                problem = item.catalog_problem
                item.is_public = bool(
                    problem is not None
                    and problem.status == Problem.Status.PUBLISHED
                    and not problem.needs_quality_review
                )
        # Группируем по папкам; «Без папки» всегда последняя — это не папка,
        # а её отсутствие.
        groups = [{'folder': f,
                   'items': [s for s in saved if s.folder_id == f.pk]}
                  for f in folders]
        groups.append({'folder': None,
                       'items': [s for s in saved if s.folder_id is None]})
        context.update({'folders': folders, 'groups': groups})

    return render(request, 'platform/profile.html', context)


# ---------------------------------------------------------------------------
# JSON-эндпоинты «Сохранённого» (кнопка «Сохранить» работает без перезагрузки)
# ---------------------------------------------------------------------------

def _body(request):
    try:
        return json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return {}


@require_POST
@login_required(login_url='/login/')
def api_save_problem(request):
    """Сохранить/убрать задачу. Переключатель: повторный вызов снимает.

    Удаление мягкое — запись остаётся с `is_deleted=True`. Тогда «сохранил →
    убрал → сохранил снова» не спотыкается об ограничение уникальности.
    """

    data = _body(request)
    catalog_id = data.get('catalog_problem_id')
    custom_id = data.get('custom_problem_id')
    if not catalog_id and not custom_id:
        return JsonResponse({'error': 'Не указана задача'}, status=400)

    lookup = {'owner': request.user}
    if catalog_id:
        # ⚠️ ФИЛЬТР ПО ОПУБЛИКОВАННОСТИ ЗДЕСЬ ОБЯЗАТЕЛЕН. Раньше стояло просто
        # `get_object_or_404(Problem, pk=catalog_id)`, и это была утечка
        # чернового контента: любой вошедший подставлял в этот эндпоинт номер
        # черновика, скрытой или зафлагованной шлюзом задачи, она ложилась ему
        # в «Сохранённое» и оттуда показывалась на `/profile/?tab=saved`
        # вместе с условием. Каталог такие задачи не отдаёт — а этот путь
        # отдавал, в обход шлюза качества.
        lookup['catalog_problem'] = get_object_or_404(
            Problem, pk=catalog_id, status=Problem.Status.PUBLISHED,
            needs_quality_review=False)
    else:
        lookup['custom_problem'] = get_object_or_404(
            CustomProblem, pk=custom_id, owner=request.user)

    saved = SavedProblem.objects.filter(**lookup).first()
    if saved is None:
        SavedProblem.objects.create(**lookup)
        return JsonResponse({'saved': True})
    saved.is_deleted = not saved.is_deleted
    saved.save(update_fields=['is_deleted'])
    return JsonResponse({'saved': not saved.is_deleted})


@require_POST
@login_required(login_url='/login/')
def api_folder_create(request):
    data = _body(request)
    name = (data.get('name') or '').strip()
    kind = data.get('kind') or SavedFolder.Kind.PROBLEMS
    if not name:
        return JsonResponse({'error': 'Пустое название'}, status=400)
    folder, created = SavedFolder.objects.get_or_create(
        owner=request.user, kind=kind, name=name)
    return JsonResponse({'id': folder.pk, 'name': folder.name,
                         'created': created})


@require_POST
@login_required(login_url='/login/')
def api_folder_rename(request):
    data = _body(request)
    folder = get_object_or_404(SavedFolder, pk=data.get('folder_id'),
                               owner=request.user)
    name = (data.get('name') or '').strip()
    if not name:
        return JsonResponse({'error': 'Пустое название'}, status=400)
    folder.name = name
    folder.save(update_fields=['name'])
    return JsonResponse({'id': folder.pk, 'name': folder.name})


@require_POST
@login_required(login_url='/login/')
def api_saved_move(request):
    """Переместить сохранённое в папку (или «без папки»)."""
    data = _body(request)
    folder_id = data.get('folder_id') or None
    folder = None
    if folder_id:
        folder = get_object_or_404(SavedFolder, pk=folder_id,
                                   owner=request.user)

    if data.get('kind') == 'graph':
        obj = get_object_or_404(SavedGraph, pk=data.get('id'),
                                owner=request.user)
    else:
        obj = get_object_or_404(SavedProblem, pk=data.get('id'),
                                owner=request.user)
    obj.folder = folder
    obj.save(update_fields=['folder'])
    return JsonResponse({'ok': True,
                         'folder': folder.name if folder else 'Без папки'})


@require_POST
@login_required(login_url='/login/')
def api_saved_delete(request):
    """Мягкое удаление из сохранённого."""
    data = _body(request)
    model = SavedGraph if data.get('kind') == 'graph' else SavedProblem
    obj = get_object_or_404(model, pk=data.get('id'), owner=request.user)
    obj.is_deleted = True
    obj.save(update_fields=['is_deleted'])
    return JsonResponse({'ok': True})


# ---------------------------------------------------------------------------
# Фаза 19.2 — приём графика от калькулятора
# ---------------------------------------------------------------------------

@require_POST
@login_required(login_url='/login/')
def api_graph_save(request):
    """Сохранить график: {name, scene, preview}.

    ⚠️ Серверная половина функции «создать новый график». Формат `scene`
    здесь НЕ разбирается и НЕ проверяется по существу: calc2 в этой сессии
    не трогали, и что именно он положит в сцену — вопрос отдельной задачи.
    Эндпоинт готов принять её, как только калькулятор научится отдавать.
    """
    data = _body(request)
    name = (data.get('name') or '').strip()
    if not name:
        return JsonResponse({'error': 'Нужно название графика'}, status=400)

    scene = data.get('scene')
    if not isinstance(scene, dict):
        return JsonResponse({'error': 'Сцена должна быть объектом'},
                            status=400)

    graph = SavedGraph.objects.create(
        owner=request.user, name=name, scene=scene,
        preview=(data.get('preview') or '')[:500])
    return JsonResponse({'id': graph.pk, 'name': graph.name})
