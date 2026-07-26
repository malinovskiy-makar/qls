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
    path('api/session/start/', views.api_session_start, name='session_start'),
    path('api/session/start_mistakes/', views.api_session_start_mistakes,
         name='session_start_mistakes'),
    path('api/question/', views.api_question, name='question'),
    path('api/answer/', views.api_answer, name='answer'),
    path('api/session/finish/', views.api_session_finish, name='session_finish'),
]
