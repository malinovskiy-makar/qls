"""Адреса раздела «Олимпиады».

⚠️ ПОРЯДОК ВАЖЕН: `calendar/` и `compare/` объявлены ДО `<slug>/`.
Иначе Django разберёт их как слаг олимпиады и покажет 404 вместо
календаря — маршрут со слагом жаднее любого фиксированного слова.
"""
from django.urls import path

from . import views

app_name = 'olympiads'

urlpatterns = [
    path('', views.olympiad_list, name='list'),
    path('calendar/', views.calendar, name='calendar'),
    path('compare/', views.compare, name='compare'),
    path('<slug:slug>/variant/<int:pk>/solve/', views.variant_solve,
         name='variant_solve'),
    path('<slug:slug>/', views.olympiad_detail, name='detail'),
]
