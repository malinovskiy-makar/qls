"""Маршруты игры Econ Rush."""
from django.urls import path

from . import views

app_name = 'game'

urlpatterns = [
    path('', views.game_page, name='page'),
    path('api/session/start/', views.api_session_start, name='session_start'),
    path('api/question/', views.api_question, name='question'),
    path('api/answer/', views.api_answer, name='answer'),
]
