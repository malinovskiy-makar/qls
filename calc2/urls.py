"""
URL-адреса приложения «Собственный графический движок» (Этап Е, calc2).

    /calc2/             — страница нового калькулятора (D3 + Math.js)
    /calc2/export/pdf/  — сборка PDF из .tex через xelatex (Фаза 5)

Сохранение графиков в базу — задача будущих сессий.
"""

from django.urls import path

from . import views

app_name = 'calc2'

urlpatterns = [
    path('', views.Calc2View.as_view(), name='calculator'),
    path('export/pdf/', views.export_pdf, name='export_pdf'),
]
