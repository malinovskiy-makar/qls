from django.urls import path

from . import views, views_groups, views_problems, views_stats

app_name = 'teacher'

urlpatterns = [
    # Дашборд входящих — НАВИГАЦИЯ, а не рабочая поверхность.
    path('', views_groups.dashboard, name='dashboard'),

    # ---- Вкладка «Группы»: вся работа с группой живёт здесь --------------
    path('groups/', views_groups.groups_list, name='groups'),
    path('groups/create/', views_groups.group_create, name='group_create'),
    path('groups/<int:pk>/', views_groups.group_detail, name='group_detail'),
    path('groups/<int:group_id>/assignments/<int:assignment_id>/',
         views_groups.group_assignment_detail, name='group_assignment'),
    path('groups/<int:group_id>/assignments/<int:assignment_id>/submissions/',
         views_groups.group_submissions, name='group_submissions'),
    path('groups/<int:group_id>/submissions/<int:submission_id>/',
         views_groups.group_review_submission, name='group_review_submission'),

    # Комментарии к задачам (JSON, без перезагрузки страницы).
    path('api/comment/create/', views_groups.api_comment_create,
         name='api_comment_create'),

    path('api/item/solution/', views_groups.api_item_solution,
         name='api_item_solution'),

    # Статистика — БЕЗ геймификации (см. teacher/views_stats.py).
    path('groups/<int:pk>/stats/', views_stats.group_stats,
         name='group_stats'),
    path('students/<int:pk>/stats/', views_stats.student_stats,
         name='student_stats'),

    # Прогресс ученика глазами учителя (старый экран, оставлен).
    path('student/<int:pk>/progress/', views.student_progress,
         name='student_progress'),

    # Редактор своих задач.
    path('problems/', views_problems.problem_list, name='problem_list'),
    path('problems/new/', views_problems.problem_form, name='problem_new'),
    path('problems/<int:pk>/edit/', views_problems.problem_form,
         name='problem_edit'),

    # Конструктор домашек.
    path('assignment/create/', views.assignment_create,
         name='assignment_create'),
    path('api/problem/<int:pk>/', views.api_problem_detail,
         name='api_problem_detail'),
    path('api/assignment/<int:pk>/add_problem/',
         views.api_assignment_add_problem, name='api_assignment_add_problem'),

    # ---- устарело, удалить после сессии 5 --------------------------------
    # Старые адреса проверки решений. Ведут редиректом на групповые, чтобы
    # не сломать закладки и ссылки.
    path('assignment/<int:pk>/', views.legacy_assignment_detail,
         name='assignment_detail'),
    path('submission/<int:pk>/review/', views.legacy_review_submission,
         name='review_submission'),
]
