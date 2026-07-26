from django.urls import path
from . import views
from . import game_sets

app_name = 'teacher'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('assignment/<int:pk>/', views.assignment_detail, name='assignment_detail'),
    path('submission/<int:pk>/review/', views.review_submission, name='review_submission'),
    # Этап Е — Группы
    path('groups/', views.groups_list, name='groups'),
    path('groups/create/', views.group_create, name='group_create'),
    path('groups/<int:pk>/', views.group_detail, name='group_detail'),
    # Прогресс ученика глазами учителя
    path('student/<int:pk>/progress/', views.student_progress, name='student_progress'),
    # Сессия 2 Этапа Е — Конструктор домашек
    path('assignment/create/', views.assignment_create, name='assignment_create'),
    path('api/problem/<int:pk>/', views.api_problem_detail, name='api_problem_detail'),
    path('api/assignment/<int:pk>/add_problem/', views.api_assignment_add_problem, name='api_assignment_add_problem'),
    # Игровые наборы Econ Rush (конструктор + доска)
    path('game-sets/', game_sets.game_sets_list, name='game_sets'),
    path('game-sets/new/', game_sets.game_set_create, name='game_set_create'),
    path('game-sets/<str:code>/', game_sets.game_set_detail,
         name='game_set_detail'),
    path('api/game-set/fill/', game_sets.api_game_set_fill,
         name='api_game_set_fill'),
]
