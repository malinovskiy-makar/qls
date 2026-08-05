from django.urls import path

from . import views, views_exam

app_name = 'student'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('assignment/<int:pk>/', views.assignment_detail, name='assignment_detail'),
    path('assignment/<int:pk>/submit/', views.submit_assignment, name='submit_assignment'),
    path('submission/<int:pk>/', views.submission_detail, name='submission_detail'),
    path('progress/', views.progress, name='progress'),

    # Контрольные (Часть C). Свой раздел адресов: у контрольной свой цикл.
    path('exam/<int:pk>/', views_exam.exam_intro, name='exam_intro'),
    path('exam/<int:pk>/start/', views_exam.exam_start, name='exam_start'),
    path('exam/<int:pk>/take/', views_exam.exam_take, name='exam_take'),
    path('exam/<int:pk>/autosave/', views_exam.exam_autosave,
         name='exam_autosave'),
    path('exam/<int:pk>/time/', views_exam.exam_time, name='exam_time'),
    path('exam/<int:pk>/finish/', views_exam.exam_finish, name='exam_finish'),
    path('exam/<int:pk>/result/', views_exam.exam_result, name='exam_result'),
]
