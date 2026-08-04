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
]
