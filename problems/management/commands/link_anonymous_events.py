"""
Связывает анонимные учебные события с аккаунтом по ключу сессии.

Зачем: игра Econ Rush работает БЕЗ входа, поэтому её события пишутся
с `user=None` и ключом сессии. Если человек потом заводит аккаунт (или
входит в существующий) в той же сессии — партии, сыгранные до входа,
должны стать его.

Как определяем владельца: берём события, у которых пользователь УЖЕ
проставлен, и по их `session_key` понимаем, чья это была сессия. Если по
одному ключу нашлось два разных пользователя — ключ пропускаем: это общий
компьютер, и приписывать чужие партии нельзя.

    ./venv/bin/python manage.py link_anonymous_events --dry-run
    ./venv/bin/python manage.py link_anonymous_events
    ./venv/bin/python manage.py link_anonymous_events --session KEY --user LOGIN
"""
from django.core.management.base import BaseCommand, CommandError

from problems.models import User
from problems.models_platform import LearningEvent


class Command(BaseCommand):
    help = 'Привязывает анонимные учебные события к аккаунтам по session_key.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Только показать, ничего не записывать.')
        parser.add_argument('--session', default='',
                            help='Привязать один конкретный ключ сессии.')
        parser.add_argument('--user', default='',
                            help='Логин, к которому привязать (с --session).')

    def handle(self, *args, **options):
        dry = options['dry_run']

        if options['session']:
            if not options['user']:
                raise CommandError('С --session нужен и --user.')
            try:
                user = User.objects.get(username=options['user'])
            except User.DoesNotExist:
                raise CommandError(f'Нет пользователя {options["user"]}')
            qs = LearningEvent.objects.filter(user__isnull=True,
                                              session_key=options['session'])
            count = qs.count()
            if not dry:
                qs.update(user=user)
            self.stdout.write(self.style.SUCCESS(
                f'{"Привязалось бы" if dry else "Привязано"}: {count} событий '
                f'→ {user.username}'))
            return

        # Автоматический режим: ключ сессии → владелец, если он однозначен.
        owners = {}
        ambiguous = set()
        known = (LearningEvent.objects
                 .filter(user__isnull=False)
                 .exclude(session_key='')
                 .values_list('session_key', 'user_id')
                 .distinct())
        for key, user_id in known:
            if key in owners and owners[key] != user_id:
                ambiguous.add(key)
            owners[key] = user_id

        for key in ambiguous:
            owners.pop(key, None)

        if ambiguous:
            self.stdout.write(self.style.WARNING(
                f'Пропущено ключей с двумя владельцами (общий компьютер): '
                f'{len(ambiguous)}'))

        total = 0
        for key, user_id in owners.items():
            qs = LearningEvent.objects.filter(user__isnull=True,
                                              session_key=key)
            count = qs.count()
            if not count:
                continue
            total += count
            if not dry:
                qs.update(user_id=user_id)

        if dry:
            self.stdout.write(self.style.WARNING(
                f'Пробный прогон: привязалось бы {total} событий.'))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Привязано событий: {total}.'))
