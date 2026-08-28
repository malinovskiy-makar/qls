# -*- coding: utf-8 -*-
"""С14 — команда `build_eval_set_b` (обратная генерация запросов).

Прогон идёт на подставном поставщике (`AI_PROVIDER='fake'`): к настоящей
модели тесты не ходят и денег не тратят. Проверяется весь слой целиком —
профиль, схема, разбор ответа, сборка набора.

⚠️ ГЛАВНОЕ ЗДЕСЬ — ТЕСТ НА `--dry-run` ПО УМОЛЧАНИЮ. Команда тратит деньги, и
случайный запуск без флага обязан не сделать ничего. Регламент слоя команд
требует этого от любой массовой команды; здесь цена ошибки прямая, в рублях.
"""
import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase, override_settings

from problems.models import Problem
from problems.tests.factories import make_problem

ОТВЕТ = json.dumps(
    {'queries': ['потоварный налог на монополию',
                 'фирма выбирает выпуск при налоге',
                 'найти ставку, максимизирующую сборы']},
    ensure_ascii=False)


@override_settings(AI_PROVIDER='fake', AI_FAKE_REPLY=ОТВЕТ)
class BuildEvalSetBTests(TestCase):

    def setUp(self):
        # Условие длиннее 200 символов — короткие команда отбрасывает
        # намеренно: на огрызке модель напишет три одинаковые общие фразы.
        for н in range(3):
            p = make_problem(statement=f'Задача номер {н}. ' + 'Текст. ' * 40)
            Problem.objects.filter(pk=p.pk).update(
                status=Problem.Status.PUBLISHED, needs_quality_review=False,
                hidden_pending_review=False, embedding=b'\x00' * 4096)

    def _путь(self, d):
        return str(Path(d) / 'eval_set_b.json')

    def test_без_apply_ничего_не_пишется(self):
        with tempfile.TemporaryDirectory() as d:
            путь = self._путь(d)
            call_command('build_eval_set_b', limit=3, out=путь, verbosity=0)
            self.assertFalse(Path(путь).exists())

    def test_с_apply_набор_собирается_по_три_запроса_на_задачу(self):
        with tempfile.TemporaryDirectory() as d:
            путь = self._путь(d)
            call_command('build_eval_set_b', limit=3, out=путь, apply=True,
                         verbosity=0)
            данные = json.loads(Path(путь).read_text(encoding='utf-8'))
        self.assertEqual(данные['count'], 9)
        self.assertEqual(данные['mode'], 'text')

    def test_каждый_запрос_ведёт_на_свою_задачу(self):
        with tempfile.TemporaryDirectory() as d:
            путь = self._путь(d)
            call_command('build_eval_set_b', limit=3, out=путь, apply=True,
                         verbosity=0)
            данные = json.loads(Path(путь).read_text(encoding='utf-8'))
        ids = {c['relevant_ids'][0] for c in данные['cases']}
        self.assertEqual(ids, set(Problem.objects.values_list('id', flat=True)))

    def test_запрет_на_абсолютные_цифры_записан_в_самом_файле(self):
        # Правило обязано ехать вместе с данными. Лежи оно только в отчёте
        # сессии — через месяц по набору B назовут абсолютное качество поиска,
        # и число будет завышено примерно на 0,2 nDCG@10.
        with tempfile.TemporaryDirectory() as d:
            путь = self._путь(d)
            call_command('build_eval_set_b', limit=3, out=путь, apply=True,
                         verbosity=0)
            данные = json.loads(Path(путь).read_text(encoding='utf-8'))
        предупреждения = ' '.join(данные['warnings'])
        self.assertIn('ЗАПРЕЩЕНО', предупреждения)
        self.assertIn('РАЗРЕШЕНО', предупреждения)

    def test_выборка_повторяема_при_том_же_зерне(self):
        # Иначе повторный прогон стоил бы денег и дал бы ДРУГОЙ эталон:
        # сравнивать замеры между собой стало бы нельзя.
        наборы = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as d:
                путь = self._путь(d)
                call_command('build_eval_set_b', limit=2, out=путь,
                             apply=True, seed=777, verbosity=0)
                данные = json.loads(Path(путь).read_text(encoding='utf-8'))
            наборы.append([c['relevant_ids'] for c in данные['cases']])
        self.assertEqual(наборы[0], наборы[1])

    def test_команда_не_меняет_защищённые_поля(self):
        поля = ('statement', 'solution', 'answer', 'embedding',
                'content_format', 'human_review')
        до = list(Problem.objects.order_by('id').values('id', *поля))
        with tempfile.TemporaryDirectory() as d:
            call_command('build_eval_set_b', limit=3, out=self._путь(d),
                         apply=True, verbosity=0)
        после = list(Problem.objects.order_by('id').values('id', *поля))
        self.assertEqual(до, после)
