# -*- coding: utf-8 -*-
from django.contrib import admin

from problems.models_legal import ConsentRecord


@admin.register(ConsentRecord)
class ConsentRecordAdmin(admin.ModelAdmin):
    """Согласия только на просмотр: это доказательство, а не настройка.

    Править и удалять запись руками нельзя: строка, которую можно поправить
    задним числом, ничего не доказывает. Отзыв делает сам человек в профиле.
    """

    list_display = ('user', 'kind', 'version', 'source', 'given_at', 'revoked_at', 'superseded_at')
    list_filter = ('kind', 'version', 'source')
    search_fields = ('user__username',)
    date_hierarchy = 'given_at'
    raw_id_fields = ('user',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
