# -*- coding: utf-8 -*-
"""Удаление данных человека по его требованию (Политика, раздел 8; часть Б, 09.10.2026).

    manage.py erase_user <логин>             # сухой прогон: что будет удалено
    manage.py erase_user <логин> --apply     # удалить

Порядок и границы – в `problems/erasure.py`. Сухой прогон ничего не меняет и
печатает по каждой модели число строк, по каждому виду – число файлов, отдельно
строку «останется без автора» (авторские материалы: работы, подборки, наборы).

⚠️ Сотрудника (is_staff) командой удалить нельзя. ⚠️ Без `--apply` команда безопасна
на любой базе; с `--apply` на боевой запускает только владелец, по запросу человека.
"""
from django.core.management.base import BaseCommand, CommandError

from problems import erasure


class Command(BaseCommand):
    help = 'Удалить данные человека по его требованию (по умолчанию – сухой прогон).'

    def add_arguments(self, parser):
        parser.add_argument('username', help='логин пользователя')
        parser.add_argument('--apply', action='store_true',
                            help='действительно удалить (без флага – только показать)')

    def handle(self, *args, **options):
        try:
            user = erasure.find_user(options['username'])
            erasure.check_allowed(user)
        except erasure.Refused as exc:
            raise CommandError(str(exc))
        # Логин в вывод не печатаем: журнал оболочки и отчёты не должны его хранить.
        plan = erasure.plan_user(user)
        self._print_plan(user.pk, plan, options['apply'])
        if not options['apply']:
            self.stdout.write('\nСухой прогон: ничего не удалено. Для удаления добавьте --apply.')
            return
        result = erasure.erase_user(user)
        self.stdout.write(self.style.SUCCESS(
            '\nУдалено: строк %(rows)s, файлов %(files)s (не найдено на диске %(files_missing)s, '
            'ошибок %(files_failed)s), сессий %(sessions)s. Запись в журнал удалений сделана.'
            % result))

    def _print_plan(self, pk, plan, apply):
        w = self.stdout.write
        w('Пользователь №%s. %s' % (pk, 'УДАЛЕНИЕ' if apply else 'Сухой прогон'))
        w('\nСтроки «без указания человека», которые удаляются явно:')
        for label, n in sorted(plan['explicit'].items()):
            w('  %-34s %d' % (label, n))
        if not plan['explicit']:
            w('  нет')
        w('\nСтроки, которые уйдут вместе с пользователем (каскад):')
        for label, n in sorted(plan['cascade'].items()):
            w('  %-34s %d' % (label, n))
        w('\nФайлы (найдено на диске из записанных):')
        for kind, n in plan['files'].items():
            w('  %-34s %d (на диске %d)' % (kind, n, plan['files_on_disk'][kind]))
        w('\nСессии: %d' % plan['sessions'])
        w('\nОстанется без автора (авторские материалы, связь с человеком обнулится):')
        for label, n in sorted(plan['orphans'].items()):
            w('  %-44s %d' % (label, n))
        if not plan['orphans']:
            w('  ничего')
