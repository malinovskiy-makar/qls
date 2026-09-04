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
    Feedback,
    CustomProblem,
    CustomProblemOption,
    ExamAttempt,
    LearningEvent,
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


@admin.register(LearningEvent)
class LearningEventAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'user', 'session_key', 'source',
                    'event_type', 'topic', 'difficulty']
    list_filter = ['source', 'event_type', 'difficulty']
    search_fields = ['user__username', 'session_key']
    raw_id_fields = ['user', 'catalog_problem', 'custom_problem',
                     'assignment', 'topic']
    date_hierarchy = 'created_at'


# ═══════════════════════════════════════════════════════════════════════
# Обратная связь беты (04.09.2026, ADR 0076)
# ═══════════════════════════════════════════════════════════════════════

@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    """Разбор жалоб и предложений. Читается глазами, а не выгружается."""

    list_display = ('created_at', 'kind', 'page_key', 'who', 'short',
                    'has_shot', 'handled')
    list_filter = ('kind', 'page_key', 'handled', 'created_at')
    search_fields = ('other_text', 'comment', 'url', 'user__username')
    readonly_fields = ('created_at', 'kind', 'page_key', 'url', 'choices',
                       'other_text', 'comment', 'viewport', 'theme',
                       'user_agent', 'user', 'shot_link')
    fields = readonly_fields + ('handled', 'note')
    date_hierarchy = 'created_at'

    @admin.display(description='Кто')
    def who(self, obj):
        return obj.user.username if obj.user_id else 'гость'

    @admin.display(description='Снимок', boolean=True)
    def has_shot(self, obj):
        return bool(obj.screenshot)

    @admin.display(description='Снимок экрана')
    def shot_link(self, obj):
        from django.utils.html import format_html
        if not obj.screenshot:
            return 'нет'
        return format_html('<a href="{}" target="_blank">открыть</a>',
                           'screenshot/')

    # ⚠️ ВТОРАЯ И ПОСЛЕДНЯЯ ФАЙЛОВАЯ ВЬЮХА ПРОЕКТА. Живёт ВНУТРИ админки, а
    # не отдельным маршрутом: `admin_site.admin_view` сам требует staff,
    # ставит заголовки против кэширования и держит проверку в одном месте с
    # остальной админкой. Путь берётся из поля модели; из адреса приходит
    # только номер записи.
    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom = [
            path('<int:pk>/screenshot/',
                 self.admin_site.admin_view(self.screenshot_view),
                 name='problems_feedback_screenshot'),
        ]
        return custom + urls

    def screenshot_view(self, request, pk):
        from django.http import FileResponse, Http404
        from django.shortcuts import get_object_or_404

        entry = get_object_or_404(Feedback, pk=pk)
        if not entry.screenshot:
            raise Http404('Снимка нет')
        try:
            handle = entry.screenshot.open('rb')
        except (FileNotFoundError, OSError):
            raise Http404('Снимка нет')
        response = FileResponse(handle, content_type='image/jpeg')
        response['Cache-Control'] = 'private, max-age=60'
        return response
