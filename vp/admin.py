"""Админка тренажёра ВП.

Смысл один: починить опечатку в условии или эталоне без разработчика.
Редактора вариантов здесь нет, а инлайна из 44 заданий внутри варианта
нарочно нет — страница стала бы неподъёмной.
"""
from django.contrib import admin
from django.db.models import Count

from vp import loader
from vp.models import VPItem, VPVariant


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
