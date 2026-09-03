"""Админка раздела олимпиад.

Главный экран здесь — не справочник, а `FactUpdateProposal`: очередь
расхождений, найденных фоновой проверкой источников. Ничего не
применяется автоматически, всё через две кнопки и глаза человека.
"""
from django.contrib import admin, messages
from django.apps import apps
from django.utils import timezone

from .models import (
    FactSource, FactUpdateProposal, Olympiad, OlympiadBenefit, OlympiadEvent,
    OlympiadLevelYear, OlympiadScore, OlympiadStage, OlympiadVariant,
    RegionalCoordinator, UniversityProgram,
)

# ⚠️ БЕЛЫЙ СПИСОК — ГРАНИЦА, А НЕ УДОБСТВО.
# Предложение правки приходит из фоновой проверки чужих сайтов и несёт
# ИМЯ модели и ИМЯ поля строками. Без этого списка достаточно подменить
# строку, чтобы через админку записать что угодно куда угодно — например
# в User.is_superuser. Разрешаем только справочные поля раздела.
ALLOWED_TARGETS = {
    ('olympiads', 'Olympiad'): {
        'name_full', 'name_short', 'organizer', 'official_url', 'archive_url',
        'registration_url', 'description', 'grade_min', 'grade_max',
        'language',
    },
    ('olympiads', 'OlympiadLevelYear'): {
        'level', 'order_number', 'approval_status',
    },
    ('olympiads', 'OlympiadStage'): {
        'name', 'format', 'duration_minutes', 'max_score', 'how_to_qualify',
    },
    ('olympiads', 'OlympiadEvent'): {
        'approx_text', 'date_status', 'date_start', 'date_end', 'region',
    },
    ('olympiads', 'OlympiadBenefit'): {
        'benefit_type', 'score_100_subject', 'confirm_subject',
        'confirm_min_score', 'required_level', 'grades_note',
    },
    ('olympiads', 'OlympiadScore'): {'value', 'max_value'},
    ('olympiads', 'OlympiadVariant'): {
        'problem_count', 'duration_minutes', 'max_score', 'has_solutions',
        'original_url', 'original_source',
    },
    ('olympiads', 'RegionalCoordinator'): {
        'url', 'contact_note', 'region_code',
    },
    ('olympiads', 'UniversityProgram'): {
        'university_name', 'program_name', 'city', 'admission_rules_url',
    },
}


class OlympiadLevelYearInline(admin.TabularInline):
    model = OlympiadLevelYear
    extra = 0


class OlympiadStageInline(admin.TabularInline):
    model = OlympiadStage
    extra = 0


@admin.register(Olympiad)
class OlympiadAdmin(admin.ModelAdmin):
    list_display = ('name_short', 'name_full', 'kind', 'display_group',
                    'is_placeholder', 'is_published')
    list_filter = ('kind', 'display_group', 'is_placeholder', 'is_published')
    search_fields = ('slug', 'name_short', 'name_full', 'organizer')
    prepopulated_fields = {'slug': ('name_short',)}
    inlines = [OlympiadLevelYearInline, OlympiadStageInline]


@admin.register(OlympiadEvent)
class OlympiadEventAdmin(admin.ModelAdmin):
    list_display = ('olympiad', 'stage', 'kind', 'date_start', 'approx_text',
                    'date_status')
    list_filter = ('date_status', 'academic_year', 'kind')
    search_fields = ('olympiad__name_short', 'approx_text', 'region')
    autocomplete_fields = ('olympiad',)


@admin.register(OlympiadBenefit)
class OlympiadBenefitAdmin(admin.ModelAdmin):
    list_display = ('olympiad', 'program', 'admission_year', 'benefit_type',
                    'confirm_min_score')
    list_filter = ('admission_year', 'benefit_type')
    search_fields = ('olympiad__name_short', 'program__university_short')
    autocomplete_fields = ('olympiad',)


@admin.register(OlympiadVariant)
class OlympiadVariantAdmin(admin.ModelAdmin):
    list_display = ('olympiad', 'year', 'stage', 'grade', 'problem_count',
                    'has_solutions')
    list_filter = ('year', 'has_solutions', 'original_source')
    search_fields = ('olympiad__name_short', 'variant_label', 'ref_event_id')
    autocomplete_fields = ('olympiad',)


@admin.register(RegionalCoordinator)
class RegionalCoordinatorAdmin(admin.ModelAdmin):
    list_display = ('region_name', 'region_code', 'url', 'url_status',
                    'url_checked_at', 'is_verified')
    list_filter = ('url_status', 'is_verified')
    search_fields = ('region_name', 'region_code')


@admin.register(FactUpdateProposal)
class FactUpdateProposalAdmin(admin.ModelAdmin):
    list_display = ('target_model', 'field_name', 'old_value', 'new_value',
                    'source', 'status')
    list_filter = ('status', 'target_model', 'field_name')
    search_fields = ('target_model', 'field_name', 'new_value')
    actions = ('accept_proposals', 'reject_proposals')

    @admin.action(description='Принять предложенные изменения')
    def accept_proposals(self, request, queryset):
        applied = skipped = 0
        for proposal in queryset.filter(status=FactUpdateProposal.Status.PENDING):
            allowed_fields = ALLOWED_TARGETS.get(
                (proposal.target_app, proposal.target_model))
            if allowed_fields is None or proposal.field_name not in allowed_fields:
                skipped += 1
                self.message_user(
                    request,
                    'Пропущено: {}.{}.{} нет в белом списке — ничего не '
                    'изменено.'.format(proposal.target_app,
                                       proposal.target_model,
                                       proposal.field_name),
                    level=messages.WARNING,
                )
                continue
            try:
                model = apps.get_model(proposal.target_app, proposal.target_model)
                obj = model.objects.get(pk=proposal.target_pk)
            except (LookupError, ValueError):
                skipped += 1
                self.message_user(
                    request,
                    'Пропущено: модель {}.{} не найдена.'.format(
                        proposal.target_app, proposal.target_model),
                    level=messages.WARNING,
                )
                continue
            except model.DoesNotExist:
                skipped += 1
                self.message_user(
                    request,
                    'Пропущено: записи #{} больше нет.'.format(proposal.target_pk),
                    level=messages.WARNING,
                )
                continue
            # Через setattr по имени из белого списка. Никакого eval:
            # значение приходит с чужого сайта, выполнять его нельзя.
            setattr(obj, proposal.field_name, proposal.new_value)
            obj.save(update_fields=[proposal.field_name])
            proposal.status = FactUpdateProposal.Status.ACCEPTED
            proposal.reviewed_at = timezone.now()
            proposal.save(update_fields=['status', 'reviewed_at'])
            applied += 1
        self.message_user(
            request, 'Применено: {}. Пропущено: {}.'.format(applied, skipped))

    @admin.action(description='Отклонить')
    def reject_proposals(self, request, queryset):
        count = queryset.filter(
            status=FactUpdateProposal.Status.PENDING,
        ).update(
            status=FactUpdateProposal.Status.REJECTED,
            reviewed_at=timezone.now(),
        )
        self.message_user(request, 'Отклонено: {}.'.format(count))


@admin.register(FactSource)
class FactSourceAdmin(admin.ModelAdmin):
    list_display = ('title', 'doc_type', 'publisher', 'verified_at',
                    'http_status')
    list_filter = ('doc_type', 'publisher')
    search_fields = ('title', 'url', 'publisher')


@admin.register(UniversityProgram)
class UniversityProgramAdmin(admin.ModelAdmin):
    list_display = ('order', 'university_short', 'program_name', 'city')
    search_fields = ('university_short', 'university_name', 'program_name')


@admin.register(OlympiadScore)
class OlympiadScoreAdmin(admin.ModelAdmin):
    list_display = ('olympiad', 'year', 'grade', 'score_type', 'value',
                    'max_value', 'scope')
    list_filter = ('year', 'score_type', 'scope')
    autocomplete_fields = ('olympiad',)


@admin.register(OlympiadStage)
class OlympiadStageAdmin(admin.ModelAdmin):
    list_display = ('olympiad', 'order', 'name', 'code', 'format',
                    'duration_minutes', 'max_score')
    list_filter = ('format',)
    autocomplete_fields = ('olympiad',)


@admin.register(OlympiadLevelYear)
class OlympiadLevelYearAdmin(admin.ModelAdmin):
    list_display = ('olympiad', 'academic_year', 'level', 'order_number',
                    'approval_status')
    list_filter = ('academic_year', 'level', 'approval_status')
    autocomplete_fields = ('olympiad',)
