"""
purge_generated — полный откат сгенерированных вопросов Econ Rush.

Удаляет GameQuestion с is_generated=True (любых generator_key) — то есть
семнадцать архетипов из `game/generators/`. Вопросы из тестов
(is_generated=False) и контент-таблицы не затрагиваются: пул возвращается
ровно к состоянию до генерации.

⚠️ Вопросы режима «График» (figure_audit) эта команда НЕ трогает, хотя у них
тоже стоит is_generated=True (без него их снесла бы пересборка пула). Это
другое семейство (`game/figures/`), у него свой флаг и своя команда отката
— `purge_figure_questions`. Снос архетипов не должен уносить сюжеты за
компанию.

Запуск: ./venv/bin/python manage.py purge_generated
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from game.figures.base import QUESTION_TYPE as FIGURE_AUDIT
from game.models import GameQuestion


class Command(BaseCommand):
    help = 'Удаляет все сгенерированные вопросы (is_generated=True).'

    def handle(self, *args, **options):
        target = GameQuestion.objects.filter(is_generated=True).exclude(
            question_type=FIGURE_AUDIT)
        by_type = {}
        for qtype in target.values_list('question_type', flat=True):
            by_type[qtype] = by_type.get(qtype, 0) + 1

        with transaction.atomic():
            deleted, _ = target.delete()

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
