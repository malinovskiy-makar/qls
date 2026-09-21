"""Адреса тренажёра «Высшая проба, 1 тур».

⚠️ ПОРЯДОК ВАЖЕН: `a/…` и `r/…` объявлены ДО `<slug:slug>/…`. Маршрут со слагом
жаднее любого фиксированного слова, а вариант с названием «a» тоже возможен.

Вход не требуется ни на одном адресе (решение владельца): чужую попытку не
откроет никто, кроме её владельца, — это проверяет `views._get_attempt`.
"""
from django.urls import path

from vp import views

app_name = 'vp'

urlpatterns = [
    path('', views.index, name='index'),
    path('a/<str:code>/', views.take, name='take'),
    path('a/<str:code>/save/', views.save, name='save'),
    path('<slug:slug>/', views.intro, name='intro'),
    path('<slug:slug>/start/', views.start, name='start'),
]
