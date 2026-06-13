"""
Views для графического калькулятора Desmos (Этап 6а).

Все представления требуют входа в систему (@login_required).
Модель DesmosGraph живёт в problems.models — не дублируем её здесь.

Роли:
  - teacher → видит и может загружать/удалять все графики
  - student  → видит только свои графики
"""

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import TemplateView

from problems.models import DesmosGraph


def _json_body(request):
    """Читает тело запроса как JSON. Возвращает dict или пустой dict."""
    try:
        return json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return {}


def _is_teacher(user):
    return getattr(user, 'role', None) == 'teacher'


# ---------------------------------------------------------------------------
# Главная страница калькулятора
# ---------------------------------------------------------------------------

@method_decorator(login_required, name='dispatch')
class DesmosView(TemplateView):
    """Рендерит шаблон с встроенным калькулятором Desmos."""
    template_name = 'graphs/desmos.html'


# ---------------------------------------------------------------------------
# Сохранение графика
# ---------------------------------------------------------------------------

@method_decorator(login_required, name='dispatch')
class SaveGraphView(View):
    """POST {title, state, id?} → создаёт или обновляет DesmosGraph.
    Возвращает {id, title, updated_at}.
    """

    def post(self, request):
        data = _json_body(request)
        title = (data.get('title') or '').strip() or 'Без названия'
        state = data.get('state')
        graph_id = data.get('id')

        if state is None:
            return JsonResponse({'error': 'Нет поля state'}, status=400)

        if graph_id:
            # Обновляем существующий — только если пользователь является автором
            # (или преподаватель может редактировать любой).
            qs = DesmosGraph.objects.filter(pk=graph_id)
            if not _is_teacher(request.user):
                qs = qs.filter(author=request.user)
            graph = qs.first()
            if not graph:
                return JsonResponse({'error': 'График не найден'}, status=404)
            graph.title = title
            graph.state = state
            graph.save(update_fields=['title', 'state', 'updated_at'])
        else:
            # Создаём новый
            graph = DesmosGraph.objects.create(
                title=title,
                author=request.user,
                state=state,
            )

        return JsonResponse({
            'id': graph.pk,
            'title': graph.title,
            'updated_at': graph.updated_at.strftime('%d.%m.%Y %H:%M'),
        })


# ---------------------------------------------------------------------------
# Список графиков
# ---------------------------------------------------------------------------

@method_decorator(login_required, name='dispatch')
class GraphListView(View):
    """GET → JSON-список графиков.
    Учитель видит все; ученик — только свои.
    """

    def get(self, request):
        if _is_teacher(request.user):
            qs = DesmosGraph.objects.select_related('author').all()
        else:
            qs = DesmosGraph.objects.filter(author=request.user)

        graphs = [
            {
                'id': g.pk,
                'title': g.title,
                'author_name': str(g.author),
                'updated_at': g.updated_at.strftime('%d.%m.%Y %H:%M'),
            }
            for g in qs[:100]   # не более 100 последних
        ]
        return JsonResponse({'graphs': graphs})


# ---------------------------------------------------------------------------
# Загрузка конкретного графика
# ---------------------------------------------------------------------------

@method_decorator(login_required, name='dispatch')
class LoadGraphView(View):
    """GET /desmos/load/<pk>/ → {id, title, state}.
    Учитель может загрузить любой; ученик — только свой.
    """

    def get(self, request, pk):
        qs = DesmosGraph.objects.filter(pk=pk)
        if not _is_teacher(request.user):
            qs = qs.filter(author=request.user)
        graph = qs.first()
        if not graph:
            return JsonResponse({'error': 'График не найден'}, status=404)

        return JsonResponse({
            'id': graph.pk,
            'title': graph.title,
            'state': graph.state,
        })


# ---------------------------------------------------------------------------
# Удаление графика
# ---------------------------------------------------------------------------

@method_decorator(login_required, name='dispatch')
class DeleteGraphView(View):
    """POST /desmos/delete/<pk>/ → удаляет график.
    Учитель может удалить любой; ученик — только свой.
    """

    def post(self, request, pk):
        qs = DesmosGraph.objects.filter(pk=pk)
        if not _is_teacher(request.user):
            qs = qs.filter(author=request.user)
        deleted, _ = qs.delete()
        if not deleted:
            return JsonResponse({'error': 'График не найден'}, status=404)
        return JsonResponse({'ok': True})
