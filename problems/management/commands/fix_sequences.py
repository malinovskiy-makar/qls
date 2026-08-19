"""Выравнивание счётчиков автоинкремента (sequence) в PostgreSQL.

ЗАЧЕМ. `bulk_load_fixtures` и любая заливка фикстур вставляют записи с ЯВНЫМИ
номерами (`id`). Счётчик таблицы при этом не двигается: PostgreSQL считает, что
раз номер задали руками, то и следить за ним будут руками. Дальше кто-то
создаёт запись БЕЗ номера — счётчик выдаёт следующее по своей памяти значение,
а оно давно занято залитой записью:

    django.db.utils.IntegrityError: duplicate key value violates unique
    constraint "problems_problem_pkey"

Ломается не заливка, а первое обычное действие человека ПОСЛЕ неё — создание
задачи, сдача работы, комментарий. И виноватым выглядит оно, а не заливка,
которая прошла неделю назад.

⚠️ НА SQLITE ЭТО НЕ ВОСПРОИЗВОДИТСЯ ВООБЩЕ. SQLite выдаёт `max(rowid) + 1` и
про отставшие счётчики не знает. Поэтому мина не видна локально и срабатывает
только на проде — ради этого команда и написана.

Как пользоваться:

    manage.py fix_sequences              # только показать (по умолчанию)
    manage.py fix_sequences --apply      # выровнять

Обязательный шаг после любой заливки фикстур — см. docs/RUNBOOK.md.
"""
from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, models


class Command(BaseCommand):
    help = ('Выровнять счётчики автоинкремента по фактическому максимуму id. '
            'По умолчанию только показывает; правит с --apply.')

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Применить сдвиг. Без него команда ничего не меняет.')
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Явно попросить холостой прогон. Это и так поведение '
                 'по умолчанию, флаг оставлен ради читаемости команд в '
                 'RUNBOOK и в истории оболочки.')
        parser.add_argument(
            '--app', action='append', dest='apps', metavar='ЯРЛЫК',
            help='Ограничиться приложением. Можно повторять. '
                 'Без флага — все приложения проекта.')

    # ------------------------------------------------------------------
    def handle(self, *args, **options):
        if connection.vendor != 'postgresql':
            raise CommandError(
                'Команда только для PostgreSQL, а сейчас база — «%s». '
                'У SQLite отставших счётчиков не бывает: он выдаёт '
                'max(rowid) + 1. Поднимите PostgreSQL '
                '(docker compose -f docker-compose.dev.yml up -d) либо '
                'укажите --settings=config.settings_test_pg.'
                % connection.vendor)

        apply = options['apply']
        only = set(options.get('apps') or [])

        targets = self._collect(only)
        if not targets:
            raise CommandError(
                'Не нашлось ни одной таблицы со счётчиком. '
                'Проверьте --app: указано %s.' % (sorted(only) or '—'))

        behind, checked = self._inspect(targets)

        self.stdout.write('Проверено таблиц со счётчиком: %d' % checked)

        if not behind:
            self.stdout.write(self.style.SUCCESS(
                'Отставших счётчиков нет — выравнивать нечего.'))
            return

        self.stdout.write('')
        self.stdout.write('Отстают счётчики (%d):' % len(behind))
        self.stdout.write('')
        width = max(len(row['table']) for row in behind)
        for row in behind:
            self.stdout.write(
                '  %-*s  выдаст %-10s  занято до %-10s  отставание %d'
                % (width, row['table'], row['next'], row['max_id'],
                   row['gap']))

        self.stdout.write('')
        if not apply:
            self.stdout.write(self.style.WARNING(
                'Холостой прогон: ничего не изменено. '
                'Повторите с --apply, чтобы выровнять.'))
            return

        moved = self._apply(behind)
        self.stdout.write(self.style.SUCCESS(
            'Выровнено счётчиков: %d.' % moved))
        self.stdout.write(
            'Проверка: повторный запуск без --apply обязан сказать '
            '«отставших счётчиков нет».')

    # ------------------------------------------------------------------
    def _collect(self, only):
        """Таблицы и колонки, за которыми стоит счётчик.

        `include_auto_created=True` — это не мелочь: у промежуточных таблиц
        связей «многие ко многим» Django заводит свой `id` со своим
        счётчиком, и отстать он может ровно так же. Пропустить их значит
        починить половину.
        """
        targets = []
        for model in apps.get_models(include_auto_created=True):
            if model._meta.proxy or not model._meta.managed:
                continue
            if only and model._meta.app_label not in only:
                continue
            for field in model._meta.local_fields:
                if isinstance(field, models.AutoField):
                    targets.append((model._meta.db_table, field.column))
        # По одной записи на таблицу+колонку и в устойчивом порядке:
        # отчёт, который перетасовывается между запусками, невозможно
        # сравнить с предыдущим.
        return sorted(set(targets))

    # ------------------------------------------------------------------
    def _inspect(self, targets):
        """Сравнивает, что счётчик выдаст дальше, с тем, что уже занято."""
        behind = []
        checked = 0
        with connection.cursor() as cur:
            for table, column in targets:
                cur.execute('SELECT pg_get_serial_sequence(%s, %s)',
                            [table, column])
                row = cur.fetchone()
                seq = row[0] if row else None
                if not seq:
                    # Колонка без счётчика — например, ключ, назначаемый
                    # кодом. Молча пропускаем: это не поломка.
                    continue
                checked += 1

                # last_value + is_called вместе дают ответ на вопрос
                # «какое число выдадут следующим». Только last_value его
                # НЕ даёт: у свежей последовательности last_value = 1, но
                # единицу она ещё не выдавала.
                #
                # ⚠️ Имя последовательности подставляется в текст запроса, и
                # иначе никак: имя таблицы или последовательности в SQL не
                # может быть связанным параметром — параметром бывает
                # значение, а не идентификатор. Подставляемое здесь пришло
                # от самой PostgreSQL (pg_get_serial_sequence выше), а не от
                # пользователя, поэтому подставлять нечего.
                cur.execute(
                    'SELECT last_value, is_called FROM %s' % seq)  # nosec B608
                last_value, is_called = cur.fetchone()
                next_value = last_value + 1 if is_called else last_value

                # То же самое: имена берутся из метаданных Django и
                # экранируются quote_name.
                cur.execute('SELECT max(%s) FROM %s'  # nosec B608
                            % (connection.ops.quote_name(column),
                               connection.ops.quote_name(table)))
                max_id = cur.fetchone()[0]
                if max_id is None:
                    continue

                if max_id >= next_value:
                    behind.append({
                        'table': table,
                        'column': column,
                        'sequence': seq,
                        'next': next_value,
                        'max_id': max_id,
                        'gap': max_id - next_value + 1,
                    })
        return behind, checked

    # ------------------------------------------------------------------
    def _apply(self, behind):
        """Двигает счётчики на фактический максимум.

        `setval(seq, max, true)` означает «значение max уже выдано»,
        поэтому следующим придёт max + 1. Третий аргумент обязателен:
        без него следующим придёт сам max, то есть занятый номер, и
        ошибка повторится ровно один раз — самый неприятный вид починки.
        """
        moved = 0
        with connection.cursor() as cur:
            for row in behind:
                cur.execute('SELECT setval(%s, %s, true)',
                            [row['sequence'], row['max_id']])
                self.stdout.write(
                    '  %s: %s -> %s'
                    % (row['table'], row['next'], row['max_id'] + 1))
                moved += 1
        return moved
