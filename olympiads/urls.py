"""Адреса раздела «Олимпиады».

⚠️ ПОРЯДОК ВАЖЕН: `calendar/` и `compare/` объявлены ДО `<slug>/`.
Иначе Django разберёт их как слаг олимпиады и покажет 404 вместо
календаря — маршрут со слагом жаднее любого фиксированного слова.
"""
from django.urls import path

from . import views, views_training

app_name = 'olympiads'

urlpatterns = [
    path('', views.olympiad_list, name='list'),
    path('calendar/', views.calendar, name='calendar'),
    path('compare/', views.compare, name='compare'),
    # Тренировка: семь адресов по образцу контрольной. Вход не требуется
    # ни на одном — решать комплект может любой посетитель.
    path('<slug:slug>/variant/<int:pk>/', views_training.training_intro,
         name='training_intro'),
    path('<slug:slug>/variant/<int:pk>/start/', views_training.training_start,
         name='training_start'),
    path('<slug:slug>/variant/<int:pk>/take/', views_training.training_take,
         name='training_take'),
    path('<slug:slug>/variant/<int:pk>/autosave/',
         views_training.training_autosave, name='training_autosave'),
    path('<slug:slug>/variant/<int:pk>/time/', views_training.training_time,
         name='training_time'),
    path('<slug:slug>/variant/<int:pk>/finish/',
         views_training.training_finish, name='training_finish'),
    path('<slug:slug>/variant/<int:pk>/result/',
         views_training.training_result, name='training_result'),
    path('<slug:slug>/', views.olympiad_detail, name='detail'),
]
