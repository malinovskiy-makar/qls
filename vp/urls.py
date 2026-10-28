"""Адреса тренажёра «Высшая проба, 1 тур».

⚠️ ПОРЯДОК ВАЖЕН: `a/…`, `r/…`, `wall/…`, `tg/…`, `variants/`, `my/`, `band/` и `format/`
объявлены ДО `<slug:slug>/…`.
Маршрут со слагом жаднее любого фиксированного слова, а вариант со слагом
«variants» или «my» тоже возможен – тогда он просто не откроется по своему
адресу, зато экраны раздела останутся на месте.

Вход требуется на `<слаг>/start/` и на `my/` (решение владельца 22.09.2026):
пройти вариант и посмотреть свой список попыток может только вошедший. Всё
остальное публично. Чужую попытку не откроет никто, кроме её владельца, — это
проверяет `views._get_attempt`.
"""
from django.urls import path

from vp import views, views_wall

app_name = 'vp'

urlpatterns = [
    path('', views.index, name='index'),
    path('variants/', views.variants, name='variants'),
    path('my/', views.my_attempts, name='my'),
    path('band/', views.remember_band, name='remember_band'),
    path('format/', views.drill, name='drill'),
    path('format/check/', views.format_check, name='format_check'),
    path('wall/email/<slug:slug>/', views_wall.wall_email, name='wall_email'),
    path('wall/tg/<slug:slug>/', views_wall.wall_tg, name='wall_tg'),
    path('wall/check/<slug:slug>/', views_wall.wall_check, name='wall_check'),
    path('wall/state/', views_wall.wall_state, name='wall_state'),
    path('wall/survey/<slug:slug>/', views_wall.wall_survey, name='wall_survey'),
    path('tg/hook/', views_wall.tg_hook, name='tg_hook'),
    path('a/<str:code>/', views.take, name='take'),
    path('a/<str:code>/save/', views.save, name='save'),
    path('a/<str:code>/time/', views.time_left, name='time'),
    path('a/<str:code>/finish/', views.finish, name='finish'),
    path('a/<str:code>/practice-check/', views.practice_check, name='practice'),
    path('r/<str:code>/', views.result, name='result'),
    path('<slug:slug>/', views.intro, name='intro'),
    path('<slug:slug>/start/', views.start, name='start'),
]
