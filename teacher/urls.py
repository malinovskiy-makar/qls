from django.urls import path
from . import views

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
]
