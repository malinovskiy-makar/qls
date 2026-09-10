# -*- coding: utf-8 -*-
"""Мост между именами ключей в .env и именами, которые читает код продукта.

Владелец кладёт в `.env` четыре имени по названиям провайдеров. Код
продукта два из них читает под другими именами. Переименовывать чужой
файл нельзя, менять `key_env` у живого провайдера ради замера тоже:
`GLM_API_KEY` стоит в боевых настройках и в ранбуке сервера. Значит
пробрасывать значение обязан код замера, и ровно в одном месте.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import envbridge  # noqa: E402


class AliasTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, '.env')

    def write(self, text):
        with open(self.path, 'w', encoding='utf-8') as handle:
            handle.write(text)

    def test_zai_пробрасывается_под_именем_glm(self):
        self.write('ZAI_API_KEY=z-secret\n')
        env = envbridge.load(self.path, {})
        self.assertEqual(env['GLM_API_KEY'], 'z-secret')

    def test_исходное_имя_тоже_остаётся(self):
        self.write('ZAI_API_KEY=z-secret\n')
        env = envbridge.load(self.path, {})
        self.assertEqual(env['ZAI_API_KEY'], 'z-secret')

    def test_совпадающие_имена_не_трогаются(self):
        self.write('OPENAI_API_KEY=o-secret\nANTHROPIC_API_KEY=a-secret\n')
        env = envbridge.load(self.path, {})
        self.assertEqual(env['OPENAI_API_KEY'], 'o-secret')
        self.assertEqual(env['ANTHROPIC_API_KEY'], 'a-secret')

    def test_уже_заданный_glm_сильнее_файла(self):
        # Ключ, выставленный в оболочке осознанно, подменять нельзя.
        self.write('ZAI_API_KEY=from-file\n')
        env = envbridge.load(self.path, {'GLM_API_KEY': 'from-shell'})
        self.assertEqual(env['GLM_API_KEY'], 'from-shell')

    def test_без_zai_ключа_моста_не_возникает(self):
        self.write('OPENAI_API_KEY=o-secret\n')
        self.assertNotIn('GLM_API_KEY', envbridge.load(self.path, {}))


class PresenceTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, '.env')
        with open(self.path, 'w', encoding='utf-8') as handle:
            handle.write('OPENAI_API_KEY=o\nZAI_API_KEY=z\n')

    def test_отчёт_только_да_нет(self):
        report = envbridge.presence(envbridge.load(self.path, {}))
        self.assertEqual(report, {'OPENAI_API_KEY': True,
                                  'ANTHROPIC_API_KEY': False,
                                  'ZAI_API_KEY': True,
                                  'DEEPSEEK_API_KEY': False})

    def test_в_отчёте_нет_ни_одного_значения(self):
        report = envbridge.presence(envbridge.load(self.path, {}))
        self.assertNotIn('o', list(report.values()))
        self.assertTrue(all(isinstance(v, bool) for v in report.values()))

    def test_пустое_значение_считается_отсутствием(self):
        with open(self.path, 'w', encoding='utf-8') as handle:
            handle.write('OPENAI_API_KEY=\n')
        self.assertFalse(envbridge.presence(envbridge.load(self.path, {}))
                         ['OPENAI_API_KEY'])


if __name__ == '__main__':
    unittest.main()
