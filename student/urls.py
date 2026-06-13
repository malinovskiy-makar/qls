from django.urls import path
from . import views

app_name = 'student'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('assignment/<int:pk>/', views.assignment_detail, name='assignment_detail'),
    path('assignment/<int:pk>/submit/', views.submit_assignment, name='submit_assignment'),
    path('submission/<int:pk>/', views.submission_detail, name='submission_detail'),
    path('progress/', views.progress, name='progress'),
]
