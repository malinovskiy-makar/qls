"""Админка тренажёра ВП.

Смысл один: починить опечатку в условии или эталоне без разработчика.
Редактора вариантов здесь нет, а инлайна из 44 заданий внутри варианта
нарочно нет — страница стала бы неподъёмной.
"""
from django.contrib import admin, messages
from django.db.models import Count, Sum

from vp import loader
from vp.models import VPItem, VPVariant


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
