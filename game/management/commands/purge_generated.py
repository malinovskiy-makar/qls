"""
purge_generated — полный откат сгенерированных вопросов Econ Rush.

Удаляет ВСЕ GameQuestion с is_generated=True (любых generator_key).
Вопросы из тестов (is_generated=False) и контент-таблицы не затрагиваются:
пул возвращается ровно к состоянию до генерации.

Запуск: ./venv/bin/python manage.py purge_generated
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from game.models import GameQuestion


class Command(BaseCommand):
    help = 'Удаляет все сгенерированные вопросы (is_generated=True).'

    def handle(self, *args, **options):
        by_type = {}
        for qtype in GameQuestion.objects.filter(
                is_generated=True).values_list('question_type', flat=True):
            by_type[qtype] = by_type.get(qtype, 0) + 1

        with transaction.atomic():
            deleted, _ = GameQuestion.objects.filter(
                is_generated=True).delete()

        self.stdout.write(self.style.SUCCESS(
            'Удалено сгенерированных вопросов: {}'.format(deleted)))
        for qtype, n in sorted(by_type.items()):
            self.stdout.write('  {}: {}'.format(qtype, n))

        self.stdout.write('Остаток пула по типам (ru + en, только тесты):')
        rest = {}
        for qtype in GameQuestion.objects.values_list(
                'question_type', flat=True):
            rest[qtype] = rest.get(qtype, 0) + 1
        for qtype in ('boolean', 'single', 'multi', 'numeric'):
            self.stdout.write('  {}: {}'.format(qtype, rest.get(qtype, 0)))
