# -*- coding: utf-8 -*-
"""С15 — путь отчёта диагностики обязан настраиваться.

Команда писала в жёстко зашитый `corpus_diagnostics_c13.json`. Второй прогон
молча затирал отчёт первого — а это не машинный черновик, а база сравнения:
на числа С13 (снимок 31 699 задач) ссылаются отчёты и карточки Notion, и
пересобрать их после импорта уже нельзя, потому что банк вырос.

Ровно этим 29.08 и кончился прогон на полном корпусе: файл С13 был перезаписан
числами С15 и восстанавливался из git. Та же ловушка уже ловилась в
`backfill_embedding_provenance` — там путь снимка сделали настраиваемым после
того, как прогон тестов затёр боевой журнал отката (комментарий в её коде).
"""
import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from problems.management.commands import corpus_diagnostics


class ПутьОтчётаДиагностикиTests(TestCase):
    """⚠️ Тесты обязаны быть безвредны и на СЛОМАННОМ коде.

    Если правку откатить, команда снова пишет по жёсткому пути — и тест,
    честно её вызвав, затрёт боевой отчёт репозитория числами тестовой базы.
    Ровно это и произошло при проверке отката 29.08. Поэтому файл по
    умолчанию снимается до теста и восстанавливается после, что бы код ни
    делал: тест проверяет команду, а не портит артефакты рядом.
    """

    def setUp(self):
        парсер = corpus_diagnostics.Command().create_parser('manage.py', 'x')
        self._боевой = Path(парсер.get_default('out'))
        self._было = (self._боевой.read_bytes()
                      if self._боевой.exists() else None)

    def tearDown(self):
        if self._было is None:
            if self._боевой.exists():
                self._боевой.unlink()
        elif self._боевой.read_bytes() != self._было:
            self._боевой.write_bytes(self._было)

    def test_out_пишет_туда_куда_сказали(self):
        with tempfile.TemporaryDirectory() as d:
            путь = Path(d) / 'диагностика.json'
            call_command('corpus_diagnostics', skip_external=True,
                         out=str(путь), verbosity=0)
            self.assertTrue(путь.exists())
            данные = json.loads(путь.read_text(encoding='utf-8'))
            self.assertIn('корпус', данные)

    def test_умолчание_не_изменилось(self):
        """Прежнее имя остаётся умолчанием — старые инструкции не ломаем."""
        парсер = corpus_diagnostics.Command().create_parser('manage.py',
                                                            'corpus_diagnostics')
        умолчание = парсер.get_default('out')
        self.assertTrue(str(умолчание).endswith('corpus_diagnostics_c13.json'))

    def test_чужой_отчёт_не_затирается(self):
        """Прогон с --out не трогает файл, лежащий по умолчанию."""
        with tempfile.TemporaryDirectory() as d:
            чужой = Path(d) / 'чужой.json'
            чужой.write_text('{"это": "чужие числа"}', encoding='utf-8')
            свой = Path(d) / 'свой.json'
            call_command('corpus_diagnostics', skip_external=True,
                         out=str(свой), verbosity=0)
            self.assertEqual(json.loads(чужой.read_text(encoding='utf-8')),
                             {'это': 'чужие числа'})
