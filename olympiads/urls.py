"""Адреса раздела «Олимпиады».

⚠️ ПОРЯДОК ВАЖЕН: `calendar/` и `compare/` объявлены ДО `<slug>/`.
Иначе Django разберёт их как слаг олимпиады и покажет 404 вместо
календаря — маршрут со слагом жаднее любого фиксированного слова.
"""
from django.urls import path

from . import training_files, views, views_training

app_name = 'olympiads'

urlpatterns = [
    path('', views.olympiad_list, name='list'),
    path('calendar/', views.calendar, name='calendar'),
    path('compare/', views.compare, name='compare'),
    # Телефон по QR (Э6): `u/` объявлен ДО `<slug>/` по той же причине.
    path('u/<str:token>/', views_training.phone_upload, name='phone_upload'),
    path('u/<str:token>/sheet/<int:sheet_id>/', training_files.phone_sheet,
         name='phone_sheet'),
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
    path('<slug:slug>/variant/<int:pk>/item/', views_training.training_item_submit,
         name='training_item_submit'),
    path('<slug:slug>/variant/<int:pk>/upload/', views_training.training_upload,
         name='training_upload'),
    path('<slug:slug>/variant/<int:pk>/sheet/<int:sheet_id>/',
         training_files.training_sheet, name='training_sheet'),
    path('<slug:slug>/variant/<int:pk>/sheet/<int:sheet_id>/delete/',
         views_training.training_sheet_delete, name='training_sheet_delete'),
    path('<slug:slug>/variant/<int:pk>/sheets/', views_training.training_sheets,
         name='training_sheets'),
    path('<slug:slug>/variant/<int:pk>/check-next/',
         views_training.training_check_next, name='training_check_next'),
    path('<slug:slug>/variant/<int:pk>/result/',
         views_training.training_result, name='training_result'),
    path('<slug:slug>/follow/', views.follow, name='follow'),
    path('<slug:slug>/', views.olympiad_detail, name='detail'),
]
