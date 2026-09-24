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
    ChatTurn,
    Feedback,
    CustomProblem,
    CustomProblemOption,
    ExamAttempt,
    LearningEvent,
    ProblemComment,
    ProblemReport,
    Event,
    SavedFolder,
    SavedGraph,
    SavedProblem,
    SearchLog,
    UserProfile,
)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'grade', 'school', 'phone', 'created_at']
    list_filter = ['role', 'grade']
    search_fields = ['user__username', 'user__email',
                     'user__first_name', 'user__last_name', 'school']
    raw_id_fields = ['user']
    # ⚠️ АВАТАР — ЧЕРЕЗ ВЬЮХУ `avatar`, А НЕ ШТАТНЫМ ВИДЖЕТОМ (24.09.2026).
    # Штатный виджет ссылается на /media/avatars/…, а nginx на /media/
    # отвечает 404 намеренно (там фото решений детей, docs/SECURITY.md).
    # Новую файловую вьюху не заводим: превью ведёт на ту же `avatar`.
    exclude = ['avatar']
    readonly_fields = ['avatar_preview']
    actions = ['remove_avatar']

    @admin.display(description='Аватар')
    def avatar_preview(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html

        if not obj or not obj.avatar:
            return '—'
        url = reverse('avatar', args=[obj.user_id])
        return format_html(
            '<a href="{}" target="_blank" rel="noopener">'
            '<img src="{}" width="96" height="96" alt="" '
            'style="border-radius:50%;object-fit:cover"></a>', url, url)

    @admin.action(description='Удалить фото профиля')
    def remove_avatar(self, request, queryset):
        removed = 0
        for profile in queryset:
            if profile.avatar:
                profile.avatar.delete(save=True)
                removed += 1
        self.message_user(request, 'Удалено фото: %d.' % removed)


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
                    'has_shot', 'screenshot_note', 'handled')
    list_filter = ('kind', 'page_key', 'handled', 'created_at')
    search_fields = ('other_text', 'comment', 'url', 'user__username')
    readonly_fields = ('created_at', 'kind', 'page_key', 'url', 'choices',
                       'other_text', 'comment', 'viewport', 'theme',
                       'user_agent', 'user', 'shot_link', 'screenshot_note')
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
        from django.urls import reverse
        from django.utils.html import format_html
        if not obj.screenshot:
            return 'нет'
        # ⚠️ АДРЕС ПО ИМЕНИ МАРШРУТА, НЕ ОТНОСИТЕЛЬНЫЙ. «screenshot/» со страницы
        # записи вёл на …/<pk>/change/screenshot/, его ловил общий шаблон
        # админки, и Django писал «не существует, возможно, удалён» (17.09.2026).
        return format_html('<a href="{}" target="_blank" rel="noopener">открыть</a>',
                           reverse('admin:problems_feedback_screenshot', args=[obj.pk]))

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


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    """События беты (решение владельца 15.09.2026): только чтение.

    Разбор после беты — выгрузкой `analytics_export`; админка нужна, чтобы
    глазами убедиться, что события идут и в них нет лишнего."""

    list_display = ('ts', 'name', 'page_key', 'path', 'who', 'visitor_short')
    list_filter = ('name', 'page_key', 'user')
    search_fields = ('path', 'visitor')
    date_hierarchy = 'ts'
    list_select_related = ('user',)
    readonly_fields = ('ts', 'user', 'visitor', 'session_key', 'page_key', 'path',
                       'name', 'props', 'duration_ms', 'viewport', 'user_agent')

    @admin.display(description='Кто')
    def who(self, obj):
        return obj.user.username if obj.user_id else 'гость'

    @admin.display(description='Посетитель')
    def visitor_short(self, obj):
        return obj.visitor[:8]

    def has_add_permission(self, request):
        return False


@admin.register(SearchLog)
class SearchLogAdmin(admin.ModelAdmin):
    """Журнал поиска каталога (18.09.2026): только чтение.

    Разбор качества поиска — выгрузкой `search_export`; здесь — убедиться
    глазами, что строки идут по одной на запрос и оценки доходят."""

    list_display = ('ts', 'query', 'status', 'ms', 'total', 'rating', 'rating_text')
    list_filter = ('rating', 'status', 'degraded')
    search_fields = ('query',)
    date_hierarchy = 'ts'
    readonly_fields = ('ts', 'user', 'visitor', 'session_key', 'query', 'status',
                       'ms', 'total', 'degraded', 'top_ids', 'rating', 'rated_at',
                       'rating_text')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ProblemReport)
class ProblemReportAdmin(admin.ModelAdmin):
    """«Плохая задача?» из каталога и игры. Читается глазами, как обратная связь.

    Задача — ссылкой на её страницу в каталоге: разборщик должен увидеть
    задачу так, как её увидел школьник."""

    list_display = ('created_at', 'source', 'kind', 'problem_link',
                    'game_question_id', 'who', 'short', 'handled')
    list_filter = ('kind', 'source', 'handled', 'created_at')
    search_fields = ('text', 'url', 'user__username')
    readonly_fields = ('created_at', 'source', 'kind', 'problem_link',
                       'game_question_id', 'text', 'url', 'user_agent', 'user')
    fields = readonly_fields + ('handled', 'note')
    date_hierarchy = 'created_at'
    list_select_related = ('problem', 'user')

    @admin.display(description='Кто')
    def who(self, obj):
        return obj.user.username if obj.user_id else 'гость'

    @admin.display(description='Задача')
    def problem_link(self, obj):
        from django.utils.html import format_html
        if not obj.problem_id:
            return 'нет'
        return format_html('<a href="/catalog/problem/{}/" target="_blank" '
                           'rel="noopener">№ {}</a>', obj.problem_id, obj.problem_id)


# ═══════════════════════════════════════════════════════════════════════
# Чат на странице задачи: полный журнал беты (решение владельца 15.09.2026)
# ═══════════════════════════════════════════════════════════════════════

@admin.register(ChatTurn)
class ChatTurnAdmin(admin.ModelAdmin):
    """Реплики чата глазами: как модель прочитала фото и что ответила.

    Только чтение — журнал пишет `catalog.chat.answer`; выгрузка по
    разговорам — команда `chat_export`."""

    list_display = ('created_at', 'mode', 'who', 'problem_link', 'short', 'has_file',
                    'model', 'cost_usd', 'latency_ms', 'failed')
    list_filter = ('mode', 'model', 'user')
    search_fields = ('user_text', 'reply', 'vision_text')
    date_hierarchy = 'created_at'
    list_select_related = ('user', 'problem', 'attachment')
    readonly_fields = ('created_at', 'user', 'problem_link', 'thread', 'mode', 'user_text',
                       'file_link', 'vision_text', 'reply', 'error', 'provider', 'model',
                       'vision_input_tokens', 'vision_output_tokens', 'input_tokens',
                       'output_tokens', 'cost_usd', 'latency_ms')
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    @admin.display(description='Кто')
    def who(self, obj):
        return obj.user.username if obj.user_id else '—'

    @admin.display(description='Реплика')
    def short(self, obj):
        return obj.user_text.strip()[:70]

    @admin.display(description='Файл', boolean=True)
    def has_file(self, obj):
        return bool(obj.attachment_id)

    @admin.display(description='Ошибка', boolean=True)
    def failed(self, obj):
        return bool(obj.error)

    @admin.display(description='Задача')
    def problem_link(self, obj):
        from django.utils.html import format_html
        if not obj.problem_id:
            return 'нет'
        return format_html('<a href="/catalog/problem/{}/" target="_blank" '
                           'rel="noopener">№ {}</a>', obj.problem_id, obj.problem_id)

    @admin.display(description='Файл решения')
    def file_link(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html
        if not obj.attachment_id:
            return 'нет'
        return format_html('<a href="{}" target="_blank" rel="noopener">{}, картинок в '
                           'модель {}: открыть</a>',
                           reverse('admin:problems_chatturn_file', args=[obj.pk]),
                           obj.attachment.mime, obj.attachment.pages)

    # ⚠️ ТРЕТЬЯ ФАЙЛОВАЯ ВЬЮХА ПРОЕКТА — ТОТ ЖЕ МЕХАНИЗМ, ЧТО У СНИМКА ЭКРАНА
    # (`FeedbackAdmin.screenshot_view`): внутри админки, `admin_site.admin_view`
    # требует staff, путь берётся из поля модели, из адреса — только номер
    # записи. Сверх того — право на просмотр журнала у самого сотрудника. PDF
    # отдаётся скачиванием: встроенному просмотрщику на нашем домене файл,
    # присланный учеником, открывать незачем.
    def get_urls(self):
        from django.urls import path
        custom = [
            path('<int:pk>/file/', self.admin_site.admin_view(self.file_view),
                 name='problems_chatturn_file'),
        ]
        return custom + super().get_urls()

    def file_view(self, request, pk):
        from django.core.exceptions import PermissionDenied
        from django.http import FileResponse, Http404
        from django.shortcuts import get_object_or_404

        turn = get_object_or_404(ChatTurn.objects.select_related('attachment'), pk=pk)
        if not self.has_view_permission(request, turn):
            raise PermissionDenied
        attachment = turn.attachment
        if attachment is None or not attachment.file:
            raise Http404('Файла нет')
        try:
            handle = attachment.file.open('rb')
        except (FileNotFoundError, OSError):
            raise Http404('Файла нет')
        pdf = attachment.mime == 'application/pdf'
        response = FileResponse(handle, content_type=attachment.mime, as_attachment=pdf,
                                filename='chat_%d.%s' % (turn.pk,
                                                         attachment.file.name.rsplit('.', 1)[-1]))
        response['Cache-Control'] = 'private, max-age=60'
        return response
