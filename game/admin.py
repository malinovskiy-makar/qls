from django.contrib import admin

from .models import GameQuestion


@admin.register(GameQuestion)
class GameQuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'problem', 'difficulty', 'lang', 'short_question')
    list_filter = ('difficulty', 'lang')
    search_fields = ('question',)
    raw_id_fields = ('problem',)

    @admin.display(description='Вопрос')
    def short_question(self, obj):
        return obj.question[:80]
