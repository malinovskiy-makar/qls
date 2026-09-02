"""Маршруты игры Econ Rush."""
from django.urls import path

from . import views

app_name = 'game'

urlpatterns = [
    path('', views.game_page, name='page'),
    # Публичная страница результата: короткий код, без логина.
    path('r/<str:code>/', views.result_page, name='result'),
    # Служебная статистика пула — только для персонала.
    path('stats/', views.stats_page, name='stats'),
    # Вызов дня: четыре набора в сутки, по одному на режим.
    path('daily/', views.daily_page, name='daily'),
    path('daily/<str:mode>/', views.daily_board, name='daily_board'),
    path('daily/<str:mode>/<str:day>/', views.daily_board,
         name='daily_board_day'),
    # Дуэль: создание (сразу в игру) и страница сравнения.
    path('duel/new/', views.duel_new, name='duel_new'),
    path('d/<str:code>/', views.duel_page, name='duel'),
    # Набор: забег по коду и доска результатов набора.
    path('s/<str:code>/', views.set_page, name='set_page'),
    path('s/<str:code>/board/', views.set_board, name='set_board'),
    path('api/session/start_set/<str:code>/', views.api_session_start_set,
         name='session_start_set'),
    path('api/session/start/', views.api_session_start, name='session_start'),
    path('api/session/start_mistakes/', views.api_session_start_mistakes,
         name='session_start_mistakes'),
    path('api/question/', views.api_question, name='question'),
    path('api/answer/', views.api_answer, name='answer'),
    path('api/session/finish/', views.api_session_finish, name='session_finish'),
]
