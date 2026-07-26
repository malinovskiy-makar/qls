u"""purge_figure_questions — полный откат вопросов режима «График».

Отдельная команда, а не флаг у `purge_generated`: сюжеты «Графика» —
другое семейство, и снос семнадцати архетипов не должен уносить их за
компанию (и наоборот).

Запуск: ./venv/bin/python manage.py purge_figure_questions
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from game.figures.base import QUESTION_TYPE
from game.models import GameQuestion


class Command(BaseCommand):
    help = u'Удаляет все вопросы режима «График» (figure_audit).'

    def handle(self, *args, **options):
        by_key = {}
        for key in GameQuestion.objects.filter(
                question_type=QUESTION_TYPE).values_list('generator_key',
                                                         flat=True):
            by_key[key] = by_key.get(key, 0) + 1
        with transaction.atomic():
            deleted, _ = GameQuestion.objects.filter(
                question_type=QUESTION_TYPE).delete()
        self.stdout.write(self.style.SUCCESS(
            u'Удалено вопросов «Графика»: %d' % deleted))
        for key, n in sorted(by_key.items()):
            self.stdout.write(u'  %s: %d' % (key, n))
