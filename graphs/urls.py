"""
URL-адреса приложения «Графический калькулятор Desmos» (Этап 6а).

    /desmos/              — страница калькулятора
    /desmos/save/         — сохранить график (POST JSON)
    /desmos/list/         — список сохранённых графиков (GET JSON)
    /desmos/load/<pk>/    — загрузить конкретный график (GET JSON)
    /desmos/delete/<pk>/  — удалить график (POST JSON)
"""

from django.urls import path

from . import views

app_name = 'graphs'

urlpatterns = [
    path('',              views.DesmosView.as_view(),      name='calculator'),
    path('save/',         views.SaveGraphView.as_view(),   name='save'),
    path('list/',         views.GraphListView.as_view(),   name='list'),
    path('load/<int:pk>/', views.LoadGraphView.as_view(), name='load'),
    path('delete/<int:pk>/', views.DeleteGraphView.as_view(), name='delete'),
]
