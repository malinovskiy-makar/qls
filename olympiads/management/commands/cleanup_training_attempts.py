"""Уборка гостевых попыток тренировки.

⚠️ ПОПЫТКИ ВОШЕДШИХ НЕ ТРОГАЕТ НИКОГДА. Гостевая попытка живёт ровно
столько, сколько живёт смысл к ней вернуться: ключ сессии протухает, и
запись становится недостижимой ни для кого. Попытка вошедшего — его
история, и удалять её командой уборки нельзя ни при каком сроке.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from olympiads.models import TrainingAttempt
from olympiads.training_engine import GUEST_LIFETIME_DAYS


class Command(BaseCommand):
    help = ('Удаляет гостевые попытки тренировки старше {} дней. '
            'Попытки вошедших не трогает.'.format(GUEST_LIFETIME_DAYS))

    def add_arguments(self, parser):
        parser.add_argument(
            '--days', type=int, default=GUEST_LIFETIME_DAYS,
            help='Сколько дней хранить гостевые попытки.')
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Только напечатать, сколько удалит, и ничего не трогать.')

    def handle(self, *args, **options):
        days = options['days']
        edge = timezone.now() - timezone.timedelta(days=days)
        # Сужение по `user__isnull=True` — не проверка после выборки, а
        # часть самого запроса: забытая проверка это удалённая история
        # живого человека, забытое сужение — пустая выдача.
        stale = TrainingAttempt.objects.filter(user__isnull=True,
                                               started_at__lt=edge)
        count = stale.count()

        if options['dry_run']:
            self.stdout.write(
                'Удалило бы гостевых попыток старше {} дней: {}. '
                'Ничего не тронуто.'.format(days, count))
            return

        stale.delete()
        self.stdout.write(self.style.SUCCESS(
            'Удалено гостевых попыток старше {} дней: {}.'.format(days, count)))
