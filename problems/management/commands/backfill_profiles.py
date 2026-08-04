"""
Создаёт недостающие профили (`UserProfile`) существующим пользователям.

Сигнал `post_save` заводит профиль только новым пользователям — те, кто были
в базе раньше, остались без профиля. Команда идемпотентна: повторный запуск
ничего не создаёт и ничего не переписывает.

Роль берём из старого поля `User.role`: преподаватель → репетитор, всё
остальное → ученик (как и требует ТЗ; преподавателей при этом не разжалуем —
иначе команда сама сломала бы доступ к панели учителя).

    ./venv/bin/python manage.py backfill_profiles
    ./venv/bin/python manage.py backfill_profiles --dry-run
"""
from django.core.management.base import BaseCommand

from problems.models import User
from problems.models_platform import USER_ROLE_TO_PROFILE_ROLE, UserProfile


class Command(BaseCommand):
    help = 'Создаёт профили пользователям, у которых их ещё нет.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Только показать, ничего не записывать.')

    def handle(self, *args, **options):
        dry = options['dry_run']
        without = User.objects.filter(profile__isnull=True).order_by('pk')
        total = without.count()

        if not total:
            self.stdout.write(self.style.SUCCESS(
                'Все пользователи уже с профилями — делать нечего.'))
            return

        created = 0
        for user in without:
            role = USER_ROLE_TO_PROFILE_ROLE.get(
                user.role, UserProfile.Role.STUDENT)
            self.stdout.write(f'  {user.username}: role={user.role} → {role}')
            if not dry:
                UserProfile.objects.get_or_create(
                    user=user, defaults={'role': role})
                created += 1

        if dry:
            self.stdout.write(self.style.WARNING(
                f'Пробный прогон: создалось бы {total} профилей.'))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Создано профилей: {created}.'))
