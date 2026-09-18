# -*- coding: utf-8 -*-
"""Зубастость к падению прода 18.09.2026: 0069 валила миграцию на непустой базе.

ЧТО ЗДЕСЬ ДОКАЗЫВАЕТСЯ. На проде после слияния `feat/beta-prep` в `main`
контейнер `web` упал в цикл перезапуска на `Applying problems.0069_beta_profile_fields...`
с `OperationalError: cannot ALTER TABLE "problems_userprofile" because it has
pending trigger events`. Ночной прогон на PostgreSQL был зелёным — потому что
тестовая база миграций пуста: `UPDATE ... WHERE grade IN (...)` не находит
строк, отложенное событие FK-триггера (Django создаёт ВСЕ foreign key на
PostgreSQL как DEFERRABLE INITIALLY DEFERRED — проверено эмпирически по
всей схеме, не только у этой таблицы) не встаёт в очередь, и следующий
ALTER TABLE проходит беспрепятственно. На проде таблица `problems_userprofile`
НЕ пуста — там были профили с классом 5–7 или NULL, UPDATE их менял, и вот
тогда ALTER TABLE в той же транзакции упирался в непустую очередь. Тест
поэтому мигрирует НЕПУСТУЮ базу — со строкой, которая реально попадает под
UPDATE (`grade='7'`) — иначе баг не ловится: первая версия этого теста
ставила `grade='9'` (мимо условий UPDATE) и проходила даже на сломанной
миграции.

Цель миграции намеренно НЕ называется по имени файла (было `0069_...`
целиком, после фикса — цепочка `0069`→`0070`→`0071`): тест мигрирует
`problems` до 0068, вставляет строку, затем накатывает всё приложение до
актуального состояния через `call_command('migrate', 'problems')` — так
тест не зависит от того, сколько файлов и как именно разбит переход.

⚠️ ТОЛЬКО POSTGRESQL. На SQLite нет понятия отложенных (DEFERRED) событий
триггера в этом смысле, мина не воспроизводится.

    manage.py test problems.tests.test_migration_0069_beta_profile_fields \
        --settings=config.settings_test_pg
"""
import unittest

from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

PRE_0069 = ('problems', '0068_chat_turn_attachment')


@unittest.skipUnless(connection.vendor == 'postgresql',
                     'Мина pending trigger events есть только в PostgreSQL.')
class Migration0069PendingTriggerTests(TransactionTestCase):
    """Откатывает problems до 0068, вставляет строку "как на проде до

    перехода" (класс числом, реально задетым UPDATE), накатывает переход
    класса на код — должно пройти БЕЗ исключений и с верным результатом.
    """

    def tearDown(self):
        # После возможной ошибки соединение может остаться в состоянии
        # aborted transaction — закрыть его, дать Django открыть новое.
        connection.close()
        with connection.cursor() as cur:
            cur.execute(
                "DELETE FROM problems_userprofile WHERE user_id IN "
                "(SELECT id FROM problems_user WHERE username = 'migr0069')")
            cur.execute(
                "DELETE FROM problems_user WHERE username = 'migr0069'")
        # Вернуть граф миграций в актуальное состояние для следующих тестов
        # процесса — иначе все тесты после этого в том же воркере получат
        # базу, откатанную на 0068.
        call_command('migrate', 'problems', verbosity=0, interactive=False)
        super().tearDown()

    def test_grade_migration_succeeds_on_nonempty_table(self):
        call_command('migrate', 'problems', PRE_0069[1], verbosity=0,
                     interactive=False)

        executor = MigrationExecutor(connection)
        state = executor.loader.project_state(PRE_0069)
        historical_apps = state.apps
        User = historical_apps.get_model('problems', 'User')
        UserProfile = historical_apps.get_model('problems', 'UserProfile')

        user = User.objects.using(connection.alias).create(
            username='migr0069', password='x')
        # grade должен реально попасть под UPDATE перевода (IN ('5','6','7')
        # или NULL) — иначе миграция ничего не меняет и баг не ловится.
        UserProfile.objects.using(connection.alias).create(
            user=user, grade='7')

        # Не должно кидать OperationalError о pending trigger events.
        call_command('migrate', 'problems', verbosity=0, interactive=False)

        from problems.models import UserProfile as LiveUserProfile
        profile = LiveUserProfile.objects.using(connection.alias).get(
            user__username='migr0069')
        self.assertEqual(profile.grade, 'le7')
