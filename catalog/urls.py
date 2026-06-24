from django.urls import path

from . import views

app_name = 'catalog'

urlpatterns = [
    path('',                                    views.problem_list,       name='problem_list'),
    path('random/',                             views.random_problem,     name='random_problem'),
    path('problem/<int:pk>/',                   views.problem_detail,     name='problem_detail'),
    # Публичный API для модального окна
    path('api/problem/<int:pk>/',               views.catalog_api_problem, name='api_problem'),

    # Семантический поиск (Стадия 1, локальный прототип)
    path('smart-search/',                         views.smart_search,       name='smart_search'),

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
