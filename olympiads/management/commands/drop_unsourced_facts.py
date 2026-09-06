"""Удаляет факты БЕЗ ИСТОЧНИКА — то есть демонстрационные заглушки.

⚠️ ЗАЧЕМ ОТДЕЛЬНАЯ КОМАНДА, А НЕ РУЧНАЯ ЧИСТКА. Правило раздела: факта
без источника не бывает. Демо-данные (`seed_olympiads_demo`) источников не
проставляют — это и есть признак, по которому заглушку видно, не гадая по
содержимому. Команда обратима ровно в том смысле, в каком обратим
повторный запуск сеялки.

⚠️ Комплекты заданий (`OlympiadVariant`) НЕ ТРОГАЕТ: на них завязан
тренировочный режим и демо-привязки задач банка, а сбор ссылок на
оригиналы в эту сессию не доехал. Удалить их значило бы сломать
работающий экран ради чистоты таблицы.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from olympiads.models import (OlympiadBenefit, OlympiadEvent,
                              OlympiadLevelYear, OlympiadScore)

TARGETS = (
    (OlympiadEvent, 'даты'),
    (OlympiadScore, 'проходные баллы'),
    (OlympiadBenefit, 'льготы'),
    (OlympiadLevelYear, 'уровни'),
)


class Command(BaseCommand):
    help = ('Удаляет записи без FactSource — демонстрационные заглушки. '
            'Без --yes только печатает план.')

    def add_arguments(self, parser):
        parser.add_argument('--yes', action='store_true')

    def handle(self, *args, **options):
        plan = [(model, human, model.objects.filter(source__isnull=True).count())
                for model, human in TARGETS]
        for _, human, count in plan:
            self.stdout.write('  {:<20} без источника: {}'.format(human, count))
        if not options['yes']:
            self.stdout.write('ПЛАН: ничего не удалено, нужен --yes.')
            return
        with transaction.atomic():
            for model, _, _ in plan:
                model.objects.filter(source__isnull=True).delete()
        self.stdout.write(self.style.SUCCESS('Заглушки без источника удалены.'))
