# -*- coding: utf-8 -*-
from django.urls import path

from . import views

app_name = 'legal'

# ⚠️ Слаги документов совпадают со ссылками внутри самих текстов
# (/legal/privacy/, /legal/cookies/, /legal/terms/, /legal/recommendations/).
urlpatterns = [
    path('', views.index, name='index'),
    path('accept/', views.accept, name='accept'),
    path('metrika.js', views.metrika_boot, name='metrika_boot'),
    path('ai/grant/', views.ai_grant, name='ai_grant'),
    path('ai/revoke/', views.ai_revoke, name='ai_revoke'),
    path('<slug:slug>/', views.document, name='document'),
]
