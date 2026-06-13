"""
Настройка админки — экрана, где преподаватель мышкой создаёт, ищет и
редактирует задачи. Здесь мы описываем, как каждая «анкета» выглядит в
интерфейсе: какие колонки в списке, какие фильтры, поиск, и что можно
редактировать прямо внутри задачи.
"""

import json

import numpy as np
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    Assignment,
    CalendarEvent,
    Collection,
    DuplicateCandidate,
    ExportRecord,
    FileAsset,
    Hint,
    ImportSession,
    Job,
    Lesson,
    MistakeTag,
    Problem,
    ProblemPart,
    ProblemVersion,
    Rubric,
    RubricCriterion,
    Skill,
    Source,
    SourceReference,
    StudentGroup,
    StudentSkillProgress,
    StudentTopicProgress,
    Submission,
    Subtopic,
    Tag,
    TeacherFeedback,
    Template,
    TheoryPage,
    Topic,
    User,
)

# Заголовки в шапке админки.
admin.site.site_header = 'Платформа задач по экономике'
admin.site.site_title = 'Платформа задач'
admin.site.index_title = 'Управление содержимым'


# --- Пользователь: добавляем колонку и поле «роль» к стандартной админке ---

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'role', 'email', 'first_name', 'last_name',
                    'is_staff')
    list_filter = BaseUserAdmin.list_filter + ('role',)
    # Вставляем поле «Роль» в карточку пользователя.
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Роль на платформе', {'fields': ('role',)}),
    )


# --- Подпункты и источники редактируются прямо внутри задачи (inline) ---

class ProblemPartInline(admin.StackedInline):
    model = ProblemPart
    extra = 0
    fields = ('label', 'statement', 'answer', 'solution', 'points', 'order')


class SourceReferenceInline(admin.TabularInline):
    model = SourceReference
    extra = 0


class ProblemVersionInline(admin.TabularInline):
    model = ProblemVersion
    extra = 0
    fields = ('number', 'note', 'created_by', 'created_at')
    readonly_fields = ('created_at',)


class HintInline(admin.TabularInline):
    """Подсказки к задаче (без привязки к конкретному подпункту)."""
    model = Hint
    extra = 0
    fields = ('order', 'part', 'text')


class RubricInline(admin.StackedInline):
    model = Rubric
    extra = 0
    fields = ('name',)


def _cosine_similarity_batch(query_vec: np.ndarray,
                              matrix: np.ndarray) -> np.ndarray:
    """Косинусное сходство query_vec (dim,) с каждой строкой matrix (N, dim)."""
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1e-9, norms)
    q_norm = np.linalg.norm(query_vec) or 1e-9
    return (matrix / norms) @ (query_vec / q_norm)


def _find_similar(problem_id: int, limit: int = 10):
    """Возвращает список словарей с топ-N похожими задачами."""
    query = Problem.objects.filter(pk=problem_id).only('embedding').first()
    if not query or not query.embedding:
        return None, 'no_embedding'

    raw = bytes(query.embedding)
    query_vec = np.frombuffer(raw, dtype=np.float32)
    dim = query_vec.shape[0]

    results = []
    qs = (Problem.objects
          .exclude(pk=problem_id)
          .filter(embedding__isnull=False)
          .only('id', 'embedding')
          .values_list('id', 'embedding'))

    batch_ids, batch_vecs = [], []
    for pid, raw_emb in qs.iterator(chunk_size=1000):
        raw_b = bytes(raw_emb)
        if len(raw_b) != dim * 4:
            continue
        batch_ids.append(pid)
        batch_vecs.append(np.frombuffer(raw_b, dtype=np.float32))
        if len(batch_ids) >= 1000:
            sims = _cosine_similarity_batch(query_vec, np.stack(batch_vecs))
            results.extend(zip(batch_ids, sims.tolist()))
            batch_ids, batch_vecs = [], []
    if batch_ids:
        sims = _cosine_similarity_batch(query_vec, np.stack(batch_vecs))
        results.extend(zip(batch_ids, sims.tolist()))

    results.sort(key=lambda x: x[1], reverse=True)
    top_ids = [r[0] for r in results[:limit]]
    sim_by_id = {r[0]: r[1] for r in results[:limit]}

    problems = {
        p.pk: p for p in Problem.objects.filter(pk__in=top_ids)
                                         .prefetch_related('topics')
    }
    sources = {}
    for sr in SourceReference.objects.filter(
        problem_id__in=top_ids
    ).select_related('source').order_by('problem_id'):
        if sr.problem_id not in sources:
            sources[sr.problem_id] = sr.source.name

    rows = []
    for pid in top_ids:
        p = problems.get(pid)
        if not p:
            continue
        rows.append({
            'id': pid,
            'title': str(p),
            'similarity': round(sim_by_id[pid], 4),
            'topics': ', '.join(t.name for t in p.topics.all()[:3]) or '—',
            'difficulty': p.difficulty or '—',
            'source': sources.get(pid, '—'),
            'status': p.get_status_display(),
        })
    return rows, None


@admin.register(Problem)
class ProblemAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'get_source', 'status', 'difficulty',
                    'difficulty_native', 'owner', 'updated_at')
    list_filter = ('status', 'difficulty', 'topics', 'tags', 'skills',
                   'mistakes')
    search_fields = ('title', 'statement', 'answer', 'solution')
    filter_horizontal = ('topics', 'subtopics', 'tags', 'files', 'skills',
                         'mistakes')
    inlines = (ProblemPartInline, SourceReferenceInline, HintInline,
               RubricInline, ProblemVersionInline)
    readonly_fields = ('similar_problems_link', 'duplicate_of_link', 'possible_duplicates_list')

    def get_queryset(self, request):
        return super().get_queryset(request)

    def get_source(self, obj):
        try:
            ref = obj.source_references.select_related('source').first()
            return ref.source.name if ref else '—'
        except Exception:
            return '—'
    get_source.short_description = 'Источник'

    def duplicate_of_link(self, obj):
        if not obj.pk or not obj.duplicate_of_id:
            return '—'
        orig = obj.duplicate_of
        url = f'/admin/problems/problem/{orig.pk}/change/'
        label = str(orig)[:80]
        return format_html('<a href="{}">#{} — {}</a>', url, orig.pk, label)
    duplicate_of_link.short_description = 'Оригинал (эта задача — возможный дубль)'

    def possible_duplicates_list(self, obj):
        if not obj.pk:
            return '—'
        dupes = obj.possible_duplicates.all()
        if not dupes:
            return '—'
        parts = []
        for d in dupes[:20]:
            url = f'/admin/problems/problem/{d.pk}/change/'
            parts.append(format_html('<a href="{}">#{} — {}</a>', url, d.pk, str(d)[:60]))
        html = format_html('<br>'.join('{}' for _ in parts), *parts)
        if dupes.count() > 20:
            html = format_html('{}<br><em>…и ещё {}</em>', html, dupes.count() - 20)
        return html
    possible_duplicates_list.short_description = 'Задачи, ссылающиеся на эту как на дубль'

    def similar_problems_link(self, obj):
        if not obj.pk:
            return '—'
        url = f'/admin/problems/problem/{obj.pk}/find-similar/'
        return format_html(
            '<a class="button" href="{}" target="_blank">'
            '🔍 Найти похожие задачи</a>', url
        )
    similar_problems_link.short_description = 'Похожие задачи (Этап 5а)'

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('<int:problem_id>/find-similar/',
                 self.admin_site.admin_view(self.find_similar_view),
                 name='problem_find_similar'),
        ]
        return custom + urls

    def find_similar_view(self, request, problem_id):
        problem = get_object_or_404(Problem, pk=problem_id)
        rows, error = _find_similar(problem_id, limit=10)
        context = {
            **self.admin_site.each_context(request),
            'problem': problem,
            'rows': rows,
            'error': error,
            'title': f'Похожие задачи для: {problem}',
        }
        return TemplateResponse(
            request,
            'admin/problems/problem/find_similar.html',
            context,
        )

    fieldsets = (
        ('Условие', {
            'fields': ('title', 'statement', 'answer', 'solution'),
        }),
        ('Классификация', {
            'fields': ('problem_type', 'difficulty', 'difficulty_native',
                       'topics', 'subtopics', 'tags'),
        }),
        ('Педагогика (Этап 2)', {
            'fields': ('skills', 'mistakes'),
        }),
        ('Публикация и владелец', {
            'fields': ('status', 'owner'),
        }),
        ('Файлы', {
            'fields': ('files',),
        }),
        ('Дедупликация (Этап 5б)', {
            'fields': ('duplicate_of', 'duplicate_of_link', 'possible_duplicates_list'),
            'classes': ('collapse',),
        }),
        ('Этап 5а — движок похожих задач', {
            'fields': ('similar_problems_link',),
            'classes': ('collapse',),
        }),
    )


# --- Темы, подтемы, теги ---

class SubtopicInline(admin.TabularInline):
    model = Subtopic
    extra = 0
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ('name', 'order')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    inlines = (SubtopicInline,)


@admin.register(Subtopic)
class SubtopicAdmin(admin.ModelAdmin):
    list_display = ('name', 'topic', 'order')
    list_filter = ('topic',)
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}


# --- Источники ---

@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'author', 'year', 'kind')
    search_fields = ('name', 'author')
    list_filter = ('year', 'kind')


@admin.register(SourceReference)
class SourceReferenceAdmin(admin.ModelAdmin):
    list_display = ('source', 'problem', 'stage', 'grade', 'problem_number',
                    'page')
    list_filter = ('source', 'stage', 'grade')
    search_fields = ('problem_number', 'page')


# --- Файлы ---

@admin.register(FileAsset)
class FileAssetAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'kind', 'uploaded_by', 'created_at')
    list_filter = ('kind',)
    search_fields = ('caption',)


# ===========================================================================
# Этап 2 — педагогический слой
# ===========================================================================

@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name', 'description')
    list_filter = ('topics',)
    filter_horizontal = ('topics',)


@admin.register(StudentSkillProgress)
class StudentSkillProgressAdmin(admin.ModelAdmin):
    list_display = ('student', 'skill', 'level', 'updated_at')
    list_filter = ('skill', 'student')
    search_fields = ('student__username', 'skill__name')


@admin.register(MistakeTag)
class MistakeTagAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name', 'description')
    list_filter = ('topics',)
    filter_horizontal = ('topics',)


@admin.register(Hint)
class HintAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'order', 'problem', 'part')
    list_filter = ('problem',)
    search_fields = ('text',)


class RubricCriterionInline(admin.TabularInline):
    model = RubricCriterion
    extra = 0
    fields = ('order', 'name', 'max_points', 'description')


@admin.register(Rubric)
class RubricAdmin(admin.ModelAdmin):
    list_display = ('name', 'problem')
    search_fields = ('name', 'problem__title')
    inlines = (RubricCriterionInline,)


@admin.register(TheoryPage)
class TheoryPageAdmin(admin.ModelAdmin):
    list_display = ('title', 'topic', 'updated_at')
    list_filter = ('topic',)
    search_fields = ('title', 'body')
    filter_horizontal = ('mistakes', 'problems')


# ===========================================================================
# Этап 3 — цикл «ученик ↔ преподаватель»
# ===========================================================================

@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ('name', 'date', 'duration_minutes', 'author')
    list_filter = ('date', 'author')
    search_fields = ('name', 'goals', 'warm_up')
    # Три набора задач выбираются двойным списком (удобнее, чем inline).
    filter_horizontal = ('main_problems', 'challenge_problems',
                         'homework_problems')
    fieldsets = (
        ('Основное', {
            'fields': ('name', 'date', 'duration_minutes', 'author', 'goals'),
        }),
        ('Ход занятия', {
            'fields': ('warm_up', 'main_problems', 'challenge_problems'),
        }),
        ('Домашнее задание после занятия', {
            'fields': ('homework_problems',),
        }),
        ('Заметки преподавателя (видны только вам)', {
            'fields': ('teacher_notes',),
            'classes': ('collapse',),
        }),
    )


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'lesson', 'deadline', 'author', 'created_at')
    list_filter = ('lesson', 'author', 'deadline')
    search_fields = ('name',)
    # Задачи и список учеников — через двойной список.
    filter_horizontal = ('problems', 'students')
    fieldsets = (
        ('Основное', {
            'fields': ('name', 'lesson', 'author', 'deadline'),
        }),
        ('Задачи и ученики', {
            'fields': ('problems', 'students'),
        }),
    )


class TeacherFeedbackInline(admin.StackedInline):
    """Проверка преподавателя редактируется прямо внутри страницы решения."""
    model = TeacherFeedback
    extra = 0
    fields = ('score', 'comment', 'mistakes', 'reviewed_by')
    filter_horizontal = ('mistakes',)


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ('student', 'assignment', 'problem', 'status',
                    'submitted_at')
    list_filter = ('status', 'student', 'assignment')
    search_fields = ('student__username', 'submitted_answer', 'solution_text')
    filter_horizontal = ('opened_hints',)
    inlines = (TeacherFeedbackInline,)
    fieldsets = (
        ('Кто и что', {
            'fields': ('student', 'assignment', 'problem'),
        }),
        ('Ответ ученика', {
            'fields': ('solution_text', 'solution_file', 'submitted_answer',
                       'opened_hints', 'status', 'submitted_at'),
        }),
    )


@admin.register(TeacherFeedback)
class TeacherFeedbackAdmin(admin.ModelAdmin):
    list_display = ('submission', 'score', 'reviewed_by', 'reviewed_at')
    list_filter = ('reviewed_by', 'reviewed_at')
    search_fields = ('comment', 'submission__student__username')
    filter_horizontal = ('mistakes',)


@admin.register(StudentTopicProgress)
class StudentTopicProgressAdmin(admin.ModelAdmin):
    list_display = ('student', 'topic', 'level', 'updated_at')
    list_filter = ('topic', 'student')
    search_fields = ('student__username', 'topic__name')


# ===========================================================================
# Этап 4а — инфраструктура импорта/экспорта
# ===========================================================================

# --- Admin action: скачать выбранные задачи как JSON ---

def export_problems_as_json(modeladmin, request, queryset):
    """Экспортирует выбранные задачи в JSON-файл и отдаёт браузеру
    как скачивание. Включает подпункты, теги, темы и навыки."""

    data = []
    for problem in queryset.prefetch_related(
            'parts', 'tags', 'topics', 'skills', 'mistakes'):
        parts = [
            {
                'label': part.label,
                'statement': part.statement,
                'answer': part.answer,
                'solution': part.solution,
                'points': str(part.points) if part.points is not None else None,
                'order': part.order,
            }
            for part in problem.parts.all()
        ]
        data.append({
            'id': problem.pk,
            'title': problem.title,
            'statement': problem.statement,
            'answer': problem.answer,
            'solution': problem.solution,
            'problem_type': problem.problem_type,
            'difficulty': problem.difficulty,
            'difficulty_native': problem.difficulty_native,
            'status': problem.status,
            'topics': list(problem.topics.values_list('name', flat=True)),
            'tags': list(problem.tags.values_list('name', flat=True)),
            'skills': list(problem.skills.values_list('name', flat=True)),
            'mistakes': list(problem.mistakes.values_list('name', flat=True)),
            'parts': parts,
        })

    payload = json.dumps(data, ensure_ascii=False, indent=2)
    response = HttpResponse(payload, content_type='application/json')
    response['Content-Disposition'] = (
        'attachment; filename="problems_export.json"')
    return response


export_problems_as_json.short_description = (
    'Экспортировать выбранные задачи как JSON')


# Подключаем action к ProblemAdmin — добавляем его к уже зарегистрированному
# классу через monkey-patch, чтобы не переписывать весь блок.
ProblemAdmin.actions = [export_problems_as_json]


# --- Коллекция ---

@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'author', 'created_at')
    search_fields = ('name', 'description')
    list_filter = ('author',)
    filter_horizontal = ('problems',)


# --- Фоновые задачи ---

@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ('kind', 'status', 'progress', 'started_by', 'created_at',
                    'finished_at')
    list_filter = ('kind', 'status')
    search_fields = ('error_message',)
    # Поля, которые заполняются программой, а не руками — только для чтения.
    readonly_fields = ('created_at', 'finished_at', 'progress', 'result')


# --- LaTeX-шаблоны ---

@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'font_size', 'show_answers', 'show_solutions',
                    'updated_at')
    search_fields = ('name',)
    fieldsets = (
        ('Основное', {
            'fields': ('name', 'font_size', 'numbering_style',
                       'show_answers', 'show_solutions'),
        }),
        ('Поля страницы (см)', {
            'fields': (('margin_top', 'margin_bottom'),
                       ('margin_left', 'margin_right')),
        }),
        ('LaTeX-содержимое', {
            'fields': ('preamble', 'header'),
            'classes': ('collapse',),
        }),
        ('Превью', {
            'fields': ('preview_html',),
            'classes': ('collapse',),
        }),
    )


# --- Записи об экспортах ---

@admin.register(ExportRecord)
class ExportRecordAdmin(admin.ModelAdmin):
    list_display = ('format', 'status', 'created_by', 'created_at')
    list_filter = ('format', 'status')
    search_fields = ('created_by__username',)
    readonly_fields = ('created_at',)


# --- Сессии импорта ---

@admin.register(ImportSession)
class ImportSessionAdmin(admin.ModelAdmin):
    list_display = ('source_file', 'source', 'status', 'imported_count',
                    'created_by', 'created_at')
    list_filter = ('status', 'source')
    search_fields = ('source_file', 'created_by__username')
    readonly_fields = ('created_at', 'imported_count')


# ===========================================================================
# Этап 5б — дедупликация через эмбеддинги
# ===========================================================================

def _confirm_duplicates(modeladmin, request, queryset):
    """Action: подтвердить как дубль — задача B получает статус duplicate."""
    now = timezone.now()
    updated = 0
    for candidate in queryset.select_related('problem_b'):
        candidate.status = 'confirmed'
        candidate.reviewed_at = now
        candidate.reviewed_by = request.user
        candidate.save(update_fields=['status', 'reviewed_at', 'reviewed_by'])
        # Задача B помечается как дубликат
        candidate.problem_b.status = Problem.Status.DUPLICATE
        candidate.problem_b.save(update_fields=['status'])
        updated += 1
    modeladmin.message_user(
        request,
        f'Подтверждено дублей: {updated}. Задачи B переведены в статус «Дубликат».',
    )


_confirm_duplicates.short_description = '✅ Подтвердить как дубликат'


def _reject_duplicates(modeladmin, request, queryset):
    """Action: отклонить — пара не является дублём."""
    now = timezone.now()
    updated = queryset.update(
        status='rejected',
        reviewed_at=now,
        reviewed_by=request.user,
    )
    modeladmin.message_user(request, f'Отклонено пар: {updated}.')


_reject_duplicates.short_description = '❌ Отклонить (не дубль)'


@admin.register(DuplicateCandidate)
class DuplicateCandidateAdmin(admin.ModelAdmin):
    """Страница просмотра и разметки кандидатов на дублики."""

    list_display = (
        'get_similarity_pct',
        'get_problem_a_link',
        'get_problem_b_link',
        'status',
        'created_at',
    )
    list_filter = ('status',)
    # Поиск по ID задачи: введи число — найдёт в обоих полях
    search_fields = ('problem_a__id', 'problem_b__id',
                     'problem_a__title', 'problem_b__title')
    ordering = ('-similarity',)
    actions = [_confirm_duplicates, _reject_duplicates]

    # На странице детали показываем тексты обеих задач целиком
    readonly_fields = (
        'get_similarity_pct',
        'created_at', 'reviewed_at', 'reviewed_by',
        'problem_a_text_preview',
        'problem_b_text_preview',
    )

    fieldsets = (
        ('Пара задач', {
            'fields': ('problem_a', 'problem_b', 'get_similarity_pct'),
        }),
        ('Условие задачи A', {
            'fields': ('problem_a_text_preview',),
        }),
        ('Условие задачи B', {
            'fields': ('problem_b_text_preview',),
        }),
        ('Статус проверки', {
            'fields': ('status', 'reviewed_at', 'reviewed_by', 'created_at'),
        }),
    )

    # --- Колонки в списке ---

    def get_similarity_pct(self, obj):
        """Сходство в процентах, 2 знака после запятой."""
        return f'{obj.similarity * 100:.2f}%'
    get_similarity_pct.short_description = 'Сходство'
    get_similarity_pct.admin_order_field = 'similarity'

    def get_problem_a_link(self, obj):
        """Ссылка на задачу A: ID + начало текста."""
        preview = (obj.problem_a.title or obj.problem_a.statement)[:60]
        url = f'/admin/problems/problem/{obj.problem_a_id}/change/'
        return format_html(
            '<a href="{}" target="_blank">#{} {}</a>',
            url, obj.problem_a_id, preview,
        )
    get_problem_a_link.short_description = 'Задача A'

    def get_problem_b_link(self, obj):
        """Ссылка на задачу B: ID + начало текста."""
        preview = (obj.problem_b.title or obj.problem_b.statement)[:60]
        url = f'/admin/problems/problem/{obj.problem_b_id}/change/'
        return format_html(
            '<a href="{}" target="_blank">#{} {}</a>',
            url, obj.problem_b_id, preview,
        )
    get_problem_b_link.short_description = 'Задача B'

    # --- Поля на странице детали ---

    def problem_a_text_preview(self, obj):
        """Первые 500 символов условия задачи A + ссылка «открыть»."""
        p = obj.problem_a
        text = (p.statement or '')[:500]
        url = f'/admin/problems/problem/{p.pk}/change/'
        return format_html(
            '<div style="white-space:pre-wrap; background:#f8f8f8; '
            'padding:10px; border-radius:4px;">{}</div>'
            '<p><a href="{}" target="_blank">Открыть задачу #{} →</a></p>',
            text, url, p.pk,
        )
    problem_a_text_preview.short_description = 'Текст задачи A'

    def problem_b_text_preview(self, obj):
        """Первые 500 символов условия задачи B + ссылка «открыть»."""
        p = obj.problem_b
        text = (p.statement or '')[:500]
        url = f'/admin/problems/problem/{p.pk}/change/'
        return format_html(
            '<div style="white-space:pre-wrap; background:#f8f8f8; '
            'padding:10px; border-radius:4px;">{}</div>'
            '<p><a href="{}" target="_blank">Открыть задачу #{} →</a></p>',
            text, url, p.pk,
        )
    problem_b_text_preview.short_description = 'Текст задачи B'

    def get_queryset(self, request):
        """Подгружаем связанные задачи сразу — без лишних запросов в базу."""
        return super().get_queryset(request).select_related(
            'problem_a', 'problem_b', 'reviewed_by'
        )



@admin.register(StudentGroup)
class StudentGroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'teacher', 'created_at']
    list_filter = ['teacher']
    filter_horizontal = ['students']
    search_fields = ['name', 'teacher__username']


@admin.register(CalendarEvent)
class CalendarEventAdmin(admin.ModelAdmin):
    list_display = ['title', 'event_type', 'start_datetime', 'author', 'is_global', 'is_recurring']
    list_filter = ['event_type', 'is_global', 'is_recurring', 'author']
    filter_horizontal = ['groups']
    search_fields = ['title', 'description']
    date_hierarchy = 'start_datetime'
    raw_id_fields = ['assignment', 'parent_event']
