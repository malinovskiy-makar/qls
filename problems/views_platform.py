"""
Профиль пользователя: данные, сохранённое (задачи и графики), статистика.

Живёт в `problems`, а не в `teacher`/`student`: профиль есть у всех ролей,
и класть его в кабинет одной из них значило бы закрыть его для остальных.
"""
import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models_platform import (
    CustomProblem,
    SavedFolder,
    SavedGraph,
    SavedProblem,
)


# ---------------------------------------------------------------------------
# Фаза 15 — страница профиля
# ---------------------------------------------------------------------------

@login_required(login_url='/login/')
def profile(request):
    profile_obj = request.user.profile
    tab = request.GET.get('tab', 'data')
    if tab not in ('data', 'saved', 'stats'):
        tab = 'data'
    subtab = request.GET.get('sub', 'problems')
    if subtab not in ('problems', 'graphs'):
        subtab = 'problems'

    if request.method == 'POST' and tab == 'data':
        # Почта и роль — только просмотр: почта это логин связи с человеком,
        # роль меняет права. И то и другое меняется не самим пользователем.
        request.user.first_name = (request.POST.get('first_name') or '').strip()
        request.user.last_name = (request.POST.get('last_name') or '').strip()
        request.user.save(update_fields=['first_name', 'last_name'])

        profile_obj.phone = (request.POST.get('phone') or '').strip()
        profile_obj.school = (request.POST.get('school') or '').strip()
        grade = (request.POST.get('grade') or '').strip()
        profile_obj.grade = int(grade) if grade.isdigit() else None
        profile_obj.save()
        return redirect('profile')

    context = {
        'profile': profile_obj,
        'tab': tab,
        'subtab': subtab,
        'grades': range(5, 12),
    }

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
    from .models import Problem

    data = _body(request)
    catalog_id = data.get('catalog_problem_id')
    custom_id = data.get('custom_problem_id')
    if not catalog_id and not custom_id:
        return JsonResponse({'error': 'Не указана задача'}, status=400)

    lookup = {'owner': request.user}
    if catalog_id:
        lookup['catalog_problem'] = get_object_or_404(Problem, pk=catalog_id)
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
