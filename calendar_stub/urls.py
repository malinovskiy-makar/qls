from django.urls import path

from . import views

app_name = 'calendar_stub'

urlpatterns = [
    path('', views.calendar_view, name='calendar'),

    # JSON API для FullCalendar
    path('api/events/', views.events_api, name='events_api'),
    path('api/events/create/', views.event_create, name='event_create'),
    path('api/events/<int:pk>/', views.event_detail, name='event_detail'),
    path('api/events/<int:pk>/update/', views.event_update, name='event_update'),
    path('api/events/<int:pk>/delete/', views.event_delete, name='event_delete'),
]
