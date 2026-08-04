"""
Админка моделей платформы для репетиторов.

Отдельный модуль по той же причине, что и `models_platform.py`: не раздувать
общий `admin.py`, который правят параллельные ветки. Импортируется одной
строкой в конце `problems/admin.py`.
"""
from django.contrib import admin

from .models_platform import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'grade', 'school', 'phone', 'created_at']
    list_filter = ['role', 'grade']
    search_fields = ['user__username', 'user__email',
                     'user__first_name', 'user__last_name', 'school']
    raw_id_fields = ['user']
