"""Адреса тренажёра «Высшая проба, 1 тур».

⚠️ ПОРЯДОК ВАЖЕН: `a/…`, `r/…`, `variants/` и `my/` объявлены ДО `<slug:slug>/…`.
Маршрут со слагом жаднее любого фиксированного слова, а вариант со слагом
«variants» или «my» тоже возможен – тогда он просто не откроется по своему
адресу, зато экраны раздела останутся на месте.

Вход требуется на `<слаг>/start/` и на `my/` (решение владельца 22.09.2026):
пройти вариант и посмотреть свой список попыток может только вошедший. Всё
остальное публично. Чужую попытку не откроет никто, кроме её владельца, — это
проверяет `views._get_attempt`.
"""
from django.urls import path

from vp import views

app_name = 'vp'

urlpatterns = [
    path('', views.index, name='index'),
    path('variants/', views.variants, name='variants'),
    path('my/', views.my_attempts, name='my'),
    path('a/<str:code>/', views.take, name='take'),
    path('a/<str:code>/save/', views.save, name='save'),
    path('a/<str:code>/time/', views.time_left, name='time'),
    path('a/<str:code>/finish/', views.finish, name='finish'),
    path('a/<str:code>/practice-check/', views.practice_check, name='practice'),
    path('r/<str:code>/', views.result, name='result'),
    path('<slug:slug>/', views.intro, name='intro'),
    path('<slug:slug>/start/', views.start, name='start'),
]
