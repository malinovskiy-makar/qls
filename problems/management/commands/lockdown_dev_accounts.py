"""Гасит учётные записи с публично известными дев-паролями.

Зачем: пароли `admin12345`, `teacher12345`, `student12345`, `demo12345`
лежат в открытом коде (`seed_demo`, `seed_platform_demo`) и в документации
проекта. Любой, кто видел репозиторий, может войти этими данными куда угодно,
где эти пользователи существуют.

Команда НИЧЕГО не делает по умолчанию — только показывает найденное.
Боевой прогон включается флагом `--apply`.

    python manage.py lockdown_dev_accounts            # только показать
    python manage.py lockdown_dev_accounts --apply    # погасить

Новые пароли печатаются ТОЛЬКО в stdout: команда их никуда не пишет и не
логирует. Скопируйте из терминала сразу, второй раз узнать их будет негде.

Команда работает с той базой, на которую настроен Django. Никаких сетевых
обращений к продакшену она не делает: чтобы погасить аккаунты на проде, надо
осознанно запустить её с прод-настройками и прод-DATABASE_URL — это делает
владелец руками.
"""

from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.crypto import get_random_string

from problems.models import User

# Пароли из seed-команд и документации. Публично известны — считаем скомпрометированными.
KNOWN_DEV_PASSWORDS = [
    'admin12345',
    'teacher12345',
    'student12345',
    'demo12345',
]

# Логины из seed-команд. Проверяются даже если пароль уже сменили:
# такой аккаунт всё равно стоит показать владельцу.
KNOWN_DEV_USERNAMES = ['admin', 'teacher1', 'student1']

NEW_PASSWORD_LENGTH = 32


def find_dev_accounts():
    """Возвращает список (user, matched_password | None).

    Аккаунт попадает в список, если его пароль совпал с одним из известных
    дев-паролей ИЛИ его логин совпал с seed-логином.
    """
    found = []
    for user in User.objects.all().order_by('username'):
        matched = None
        for password in KNOWN_DEV_PASSWORDS:
            if user.check_password(password):
                matched = password
                break
        if matched is not None or user.username in KNOWN_DEV_USERNAMES:
            found.append((user, matched))
    return found


def kill_sessions(user_ids):
    """Завершает все сессии перечисленных пользователей.

    Сессия хранит id пользователя внутри зашифрованных данных, поэтому
    отобрать нужные запросом нельзя — приходится расшифровывать каждую.
    """
    wanted = {str(uid) for uid in user_ids}
    doomed = []
    for session in Session.objects.all():
        try:
            data = session.get_decoded()
        except Exception:
            # Битую сессию всё равно нет смысла хранить.
            doomed.append(session.pk)
            continue
        if str(data.get('_auth_user_id', '')) in wanted:
            doomed.append(session.pk)
    if doomed:
        Session.objects.filter(pk__in=doomed).delete()
    return len(doomed)


class Command(BaseCommand):
    help = ('Гасит учётные записи с публично известными дев-паролями. '
            'Без --apply только показывает найденное.')

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Боевой прогон: сменить пароли, погасить неслужебные, снять сессии.',
        )

    def handle(self, *args, **options):
        apply_changes = options['apply']
        found = find_dev_accounts()

        if not found:
            self.stdout.write(self.style.SUCCESS(
                'Учётных записей с известными дев-паролями не найдено.'))
            return

        self.stdout.write(f'Найдено учётных записей: {len(found)}\n')
        for user, matched in found:
            kind = 'служебная (is_staff)' if user.is_staff else 'обычная'
            status = 'активна' if user.is_active else 'отключена'
            reason = (f'пароль «{matched}»' if matched
                      else 'seed-логин, пароль уже другой')
            self.stdout.write(
                f'  {user.username:<20} {kind:<22} {status:<10} — {reason}')

        if not apply_changes:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                'Пробный прогон: ничего не изменено. '
                'Боевой запуск — с флагом --apply.'))
            return

        # Боевой прогон.
        self.stdout.write('')
        with transaction.atomic():
            new_passwords = []
            for user, _matched in found:
                password = get_random_string(NEW_PASSWORD_LENGTH)
                user.set_password(password)
                # Служебные аккаунты оставляем активными: иначе владелец
                # потеряет вход в админку. Обычные — отключаем.
                if not user.is_staff:
                    user.is_active = False
                user.save(update_fields=['password', 'is_active'])
                new_passwords.append((user, password))

            killed = kill_sessions([u.pk for u, _ in found])

        self.stdout.write(self.style.SUCCESS('Готово. Новые пароли:\n'))
        for user, password in new_passwords:
            note = 'оставлен активным' if user.is_staff else 'ОТКЛЮЧЁН (is_active=False)'
            self.stdout.write(f'  {user.username:<20} {password}   [{note}]')

        self.stdout.write('')
        self.stdout.write(f'Сессий завершено: {killed}')
        self.stdout.write(self.style.WARNING(
            'Пароли выше НИГДЕ не сохранены. Скопируйте их сейчас.\n'
            'У Django нет встроенного флага «требовать смену пароля при входе», '
            'поэтому служебным аккаунтам смените пароль вручную через '
            '/admin/password_change/ после первого входа.'))
