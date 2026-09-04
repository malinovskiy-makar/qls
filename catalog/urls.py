from django.urls import path

from . import views

app_name = 'catalog'

urlpatterns = [
    path('',                                    views.problem_list,       name='problem_list'),
    path('random/',                             views.random_problem,     name='random_problem'),
    path('problem/<int:pk>/',                   views.problem_detail,     name='problem_detail'),
    # Сгенерированные системой картинки (TikZ -> SVG). Отдаются ТОЛЬКО
    # по первичному ключу ProblemFigure — адрес никогда не берётся из
    # текста задачи (см. problems/figures.py).
    path('figure/<int:pk>.svg',                 views.problem_figure_svg, name='problem_figure_svg'),
    # Публичный API для модального окна
    path('api/problem/<int:pk>/',               views.catalog_api_problem, name='api_problem'),
    # Подсказки тегов для поля фильтра: тегов 552, списком их не показать.
    path('api/tags/',                           views.api_tags,           name='api_tags'),
    # Живое состояние фильтров: числа по вариантам, чипы и список одним
    # ответом — окно «Все фильтры» обновляет выдачу, не закрываясь.
    path('api/filter-state/',                   views.api_filter_state,   name='api_filter_state'),
    # Попытка решения на странице задачи → проверка ИИ (только вход, ADR 0071).
    path('api/attempt/',                        views.api_attempt,        name='api_attempt'),

    # ⚠️ ОТДЕЛЬНОГО ЭКРАНА УМНОГО ПОИСКА БОЛЬШЕ НЕТ (решение владельца
    # 01.09.2026): он слился с каталогом, поиск там один и всегда по
    # смыслу. Адрес оставлен ПОСТОЯННЫМ редиректом — по нему ходят
    # закладки и поисковые системы, а маршрут ещё зовут по имени
    # `catalog:smart_search` старые ссылки в шаблонах и тестах.
    path('smart-search/',                         views.smart_search,       name='smart_search'),

    # Карта тем и тегов — трёхмерный граф корпуса.
    # Пока живёт отдельной страницей; позже станет всплывающим окном-фильтром
    # в переработанном поиске+каталоге (карточка идеи в Notion).
    path('map/',                                views.topic_map,          name='topic_map'),
    path('map/data.json',                       views.topic_map_data,     name='topic_map_data'),
    # Стенд предпросмотра карты для чужого экрана. Не в навигации: он нужен
    # приёмке встраиваемого режима, а не человеку в каталоге.
    path('map/preview-demo/',                   views.topic_map_preview_demo,
         name='topic_map_preview_demo'),

    # Конструктор подборок (Этап Б1)
    path('collection/new/',                     views.collection_new,     name='collection_new'),
    path('collection/<str:token>/',             views.collection_detail,  name='collection_detail'),
    path('collection/<str:token>/add/',         views.collection_add,     name='collection_add'),
    path('collection/<str:token>/remove/',      views.collection_remove,  name='collection_remove'),
    path('collection/<str:token>/reorder/',     views.collection_reorder,      name='collection_reorder'),
    path('collection/<str:token>/export/',      views.collection_export,        name='collection_export'),
    path('collection/<str:token>/download/pdf/', views.collection_download_pdf,  name='collection_download_pdf'),
    path('collection/<str:token>/download/tex/', views.collection_download_tex,  name='collection_download_tex'),
]
