"""Админка тренажёра ВП.

Смысл один: починить опечатку в условии или эталоне без разработчика.
Редактора вариантов здесь нет, а инлайна из 44 заданий внутри варианта
нарочно нет — страница стала бы неподъёмной.
"""
from django.contrib import admin, messages
from django.db.models import Count, Sum

from vp import loader
from vp.models import VPItem, VPTelegramLink, VPTelegramToken, VPVariant, VPWall


def _comma(value):
    """Число с двумя знаками и запятой: 98,00."""
    return f'{value:.2f}'.replace('.', ',')


@admin.register(VPVariant)
class VPVariantAdmin(admin.ModelAdmin):
    list_display = ('slug', 'title', 'grade_band', 'source_kind',
                    'items_count', 'max_score', 'is_published')
    list_filter = ('grade_band', 'is_published')
    search_fields = ('slug', 'title')

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_items=Count('items'))

    @admin.display(description='Заданий', ordering='_items')
    def items_count(self, obj):
        return obj._items

    def render_change_form(self, request, context, add=False, change=False,
                           form_url='', obj=None):
        # ⚠️ Только предупреждение. `max_score` считает импорт из суммы `points`;
        # править одно поле, не трогая другое, здесь можно, и расхождение надо
        # видеть сразу. Пересчёта на месте нет — вторая арифметика баллов не нужна.
        if obj is not None and obj.pk:
            total = obj.items.aggregate(total=Sum('points'))['total'] or 0
            if total != obj.max_score:
                messages.warning(
                    request,
                    f'Сумма баллов заданий {_comma(total)} ≠ max_score '
                    f'{_comma(obj.max_score)}; пересчитывается импортом.')
        return super().render_change_form(
            request, context, add=add, change=change, form_url=form_url, obj=obj)


@admin.register(VPItem)
class VPItemAdmin(admin.ModelAdmin):
    list_display = ('variant', 'number', 'block', 'kind', 'points', 'short_statement')
    list_filter = ('variant', 'block')
    list_select_related = ('variant',)
    search_fields = ('=number', 'statement')
    # Буквы змейки считаются из `answer`, а не вводятся руками.
    readonly_fields = ('chain_first', 'chain_second')

    @admin.display(description='Условие')
    def short_statement(self, obj):
        text = ' '.join(obj.statement.split())
        return text if len(text) <= 80 else text[:79] + '…'

    def save_model(self, request, obj, form, change):
        # Поправили эталон — буквы связки пересчитываем тем же кодом, что и импорт.
        obj.chain_first, obj.chain_second = loader.chain_letters(obj.chain_word())
        super().save_model(request, obj, form, change)


# ------------------------------------------------------------------ стена 2 тура

class _ReadOnly(admin.ModelAdmin):
    """Только чтение: привязки и коды пишет бот, а не человек в админке."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(VPWall)
class VPWallAdmin(admin.ModelAdmin):
    list_display = ('user', 'contact_via', 'grade', 'tour2_status', 'source',
                    'created_at', 'contact_at', 'survey_at')
    list_filter = ('contact_via', 'grade', 'source', 'tour2_status')
    search_fields = ('user__username',)
    raw_id_fields = ('user',)
    date_hierarchy = 'created_at'


@admin.register(VPTelegramLink)
class VPTelegramLinkAdmin(_ReadOnly):
    list_display = ('user', 'tg_username', 'subscribed', 'linked_at', 'checked_at', 'last_error')
    list_filter = ('subscribed',)
    search_fields = ('user__username', 'tg_username')


@admin.register(VPTelegramToken)
class VPTelegramTokenAdmin(_ReadOnly):
    # Самого кода в базе нет — только отпечаток; его в списке не показываем.
    list_display = ('user', 'slug', 'created_at', 'used_at')
    exclude = ('token_hash',)
    search_fields = ('user__username',)
