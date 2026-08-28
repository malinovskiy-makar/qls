# -*- coding: utf-8 -*-
"""Команда backfill_embedding_provenance — Фаза 0 сессии С13.

Команда пишет ровно в четыре учётных поля и обязана доказать, что не тронула
ничего другого. Проверяется и то, и другое: что заполняет правильно и что
падает, если защищённые поля разошлись.
"""
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from problems import embedding_provenance as prov
from problems.models import Problem


class BackfillCommandTests(TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.with_vector = Problem.objects.create(
            statement='Условие с вектором', embedding=b'\x00' * 4,
        )
        self.without_vector = Problem.objects.create(statement='Условие без вектора')

    def _run(self, *args):
        """Прогон команды со снимком в свою временную папку.

        Путь подставляется всегда, когда тест не задал его сам: без этого
        каждый вызов --apply писал бы в боевой
        reports/embeddings_scaleup/provenance_backfill_backup.json и затирал
        журнал отката настоящего backfill.
        """
        out = StringIO()
        if '--backup-path' not in args:
            args = args + ('--backup-path', str(Path(self.tmp.name) / 'snapshot.json'))
        call_command('backfill_embedding_provenance', *args, stdout=out, stderr=out)
        return out.getvalue()

    def test_сухой_прогон_ничего_не_пишет(self):
        """Запуск без --apply обязан быть безвредным.

        Правило проекта: случайный запуск без флага не делает ничего.
        """
        self._run()
        self.with_vector.refresh_from_db()
        self.assertIsNone(self.with_vector.embedding_built_at)

    def test_сухой_прогон_называет_число_кандидатов(self):
        self.assertIn('1', self._run())

    def test_apply_заполняет_задачу_с_вектором(self):
        self._run('--apply')
        self.with_vector.refresh_from_db()
        self.assertEqual(self.with_vector.embedding_built_at, prov.LEGACY_BUILT_AT)
        self.assertEqual(self.with_vector.embedding_version, prov.LEGACY_FORMULA_VERSION)
        self.assertEqual(self.with_vector.embedding_model_build, prov.LEGACY_MODEL_BUILD)

    def test_apply_оставляет_хеш_пустым(self):
        """Хеш текущего текста соврал бы «вектор актуален». См. модуль."""
        self._run('--apply')
        self.with_vector.refresh_from_db()
        self.assertEqual(self.with_vector.embedding_source_hash, '')

    def test_задача_без_вектора_остаётся_нетронутой(self):
        self._run('--apply')
        self.without_vector.refresh_from_db()
        self.assertIsNone(self.without_vector.embedding_version)
        self.assertIsNone(self.without_vector.embedding_built_at)

    def test_apply_не_меняет_updated_at(self):
        """auto_now сжёг бы единственную улику Фазы 1.

        `updated_at` — независимое свидетельство о том, когда правили текст
        (745 задач МатЭк 27.08). Пройтись по банку через .save() значило бы
        проштамповать все 31 699 задач сегодняшней датой и уничтожить его.
        """
        before = Problem.objects.get(pk=self.with_vector.pk).updated_at
        self._run('--apply')
        self.assertEqual(Problem.objects.get(pk=self.with_vector.pk).updated_at, before)

    def test_повторный_прогон_даёт_ноль(self):
        """Идемпотентность: так ловятся правила, доедающие данные на втором проходе."""
        self._run('--apply')
        self.assertIn('0', self._run())

    def test_расхождение_защищённых_полей_роняет_команду(self):
        """Свип-тест обязан быть предохранителем, а не украшением.

        Подменяем отпечаток так, чтобы «после» разошлось с «до»: команда
        обязана упасть CommandError, а не досчитать и промолчать.
        """
        with mock.patch.object(prov, 'protected_fingerprint', side_effect=['до', 'после']):
            with self.assertRaises(CommandError):
                self._run('--apply')

    def test_путь_снимка_настраивается(self):
        """Иначе прогон тестов затирает боевой журнал отката.

        Команда писала снимок в фиксированный
        reports/embeddings_scaleup/provenance_backfill_backup.json. Тест,
        вызывающий --apply, честно писал туда же — и боевой журнал,
        снятый перед правкой 31 694 записей, подменялся одной тестовой
        строкой. Обнаружено по размеру файла: 124 байта вместо ожидаемых сотен КБ.
        """
        import json as _json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'snapshot.json'
            self._run('--apply', '--backup-path', str(target))
            self.assertTrue(target.exists(), 'снимок не записан по указанному пути')
            self.assertEqual(len(_json.loads(target.read_text(encoding='utf-8'))), 1)
