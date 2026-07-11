from django.contrib import admin

from .models import GameQuestion


@admin.register(GameQuestion)
class GameQuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'problem', 'question_type', 'difficulty', 'lang', 'short_question')
    list_filter = ('question_type', 'difficulty', 'lang')
    search_fields = ('question',)
    raw_id_fields = ('problem', 'part')

    @admin.display(description='Вопрос')
    def short_question(self, obj):
        return obj.question[:80]
