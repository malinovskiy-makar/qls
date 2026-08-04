"""
Админка моделей платформы для репетиторов.

Отдельный модуль по той же причине, что и `models_platform.py`: не раздувать
общий `admin.py`, который правят параллельные ветки. Импортируется одной
строкой в конце `problems/admin.py`.
"""
from django.contrib import admin

from .models_platform import (
    AnswerDraft,
    AssignmentItem,
    CustomProblem,
    CustomProblemOption,
    ExamAttempt,
    ProblemComment,
    SavedFolder,
    SavedGraph,
    SavedProblem,
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


@admin.register(SavedFolder)
class SavedFolderAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'kind', 'order', 'created_at']
    list_filter = ['kind']
    search_fields = ['name', 'owner__username']
    raw_id_fields = ['owner']


@admin.register(SavedProblem)
class SavedProblemAdmin(admin.ModelAdmin):
    list_display = ['owner', 'problem_title', 'folder', 'is_deleted',
                    'created_at']
    list_filter = ['is_deleted']
    raw_id_fields = ['owner', 'catalog_problem', 'custom_problem', 'folder']


@admin.register(SavedGraph)
class SavedGraphAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'folder', 'is_deleted', 'created_at']
    list_filter = ['is_deleted']
    search_fields = ['name', 'owner__username']
    raw_id_fields = ['owner', 'folder']


@admin.register(ExamAttempt)
class ExamAttemptAdmin(admin.ModelAdmin):
    list_display = ['assignment', 'student', 'started_at', 'expires_at',
                    'submitted_at', 'is_auto_submitted']
    list_filter = ['is_auto_submitted']
    raw_id_fields = ['assignment', 'student']
    date_hierarchy = 'started_at'


@admin.register(AnswerDraft)
class AnswerDraftAdmin(admin.ModelAdmin):
    list_display = ['attempt', 'problem_item', 'updated_at']
    raw_id_fields = ['attempt', 'problem_item']
