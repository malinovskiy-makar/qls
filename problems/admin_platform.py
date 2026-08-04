"""
Админка моделей платформы для репетиторов.

Отдельный модуль по той же причине, что и `models_platform.py`: не раздувать
общий `admin.py`, который правят параллельные ветки. Импортируется одной
строкой в конце `problems/admin.py`.
"""
from django.contrib import admin

from .models_platform import (
    AssignmentItem,
    CustomProblem,
    CustomProblemOption,
    ProblemComment,
    UserProfile,
)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'grade', 'school', 'phone', 'created_at']
    list_filter = ['role', 'grade']
    search_fields = ['user__username', 'user__email',
                     'user__first_name', 'user__last_name', 'school']
    raw_id_fields = ['user']


class CustomProblemOptionInline(admin.TabularInline):
    model = CustomProblemOption
    extra = 0


@admin.register(CustomProblem)
class CustomProblemAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'owner', 'kind', 'topic', 'difficulty',
                    'is_deleted', 'created_at']
    list_filter = ['kind', 'is_deleted', 'difficulty']
    search_fields = ['title', 'statement', 'owner__username']
    raw_id_fields = ['owner', 'topic']
    inlines = [CustomProblemOptionInline]


@admin.register(AssignmentItem)
class AssignmentItemAdmin(admin.ModelAdmin):
    list_display = ['assignment', 'order', 'catalog_problem',
                    'custom_problem', 'points']
    raw_id_fields = ['assignment', 'catalog_problem', 'custom_problem']
    search_fields = ['assignment__name']


@admin.register(ProblemComment)
class ProblemCommentAdmin(admin.ModelAdmin):
    list_display = ['assignment', 'problem_item', 'author', 'visibility',
                    'is_deleted', 'created_at']
    list_filter = ['visibility', 'is_deleted']
    search_fields = ['text', 'author__username']
    raw_id_fields = ['assignment', 'problem_item', 'author', 'recipient']
    date_hierarchy = 'created_at'
