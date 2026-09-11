# -*- coding: utf-8 -*-
"""Ключи провайдеров: чтение `.env` и проброс под именами кода продукта.

Владелец кладёт в `.env` четыре имени по названиям провайдеров:
`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `ZAI_API_KEY`, `DEEPSEEK_API_KEY`.

Два из четырёх имён совпадают с тем, что читает `problems/ai/providers.py`,
одно — нет: реализация GLM читает `GLM_API_KEY`. Переименовывать имя в
живом коде ради замера нельзя — оно стоит в боевых настройках сервера и
в ранбуке. Просить владельца переименовать строку в своём файле тоже
незачем. Поэтому проброс делает код замера, ровно в одном месте.

⚠️ ЗНАЧЕНИЯ КЛЮЧЕЙ НЕ ПЕЧАТАЮТСЯ НИГДЕ. Наружу этот модуль отдаёт только
булев признак «есть / нет» (`presence`). Ни один отчёт, журнал или
сообщение в чат значения не получает.
"""
import os

#: Имя в `.env` → имя, которое читает реализация провайдера.
ALIASES = {'ZAI_API_KEY': 'GLM_API_KEY'}

#: Имена, о наличии которых отчитываемся владельцу.
EXPECTED = ('OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'ZAI_API_KEY',
            'DEEPSEEK_API_KEY')

DEFAULT_PATH = '.env'


def load(path=DEFAULT_PATH, env=None):
    """`.env` + проброс псевдонимов. Заданное в оболочке не перетирается."""
    env = dict(os.environ) if env is None else env
    if os.path.exists(path):
        with open(path, encoding='utf-8') as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                name, _, value = line.partition('=')
                name, value = name.strip(), value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
                    value = value[1:-1]
                if name and name not in env:
                    env[name] = value
    for source, target in ALIASES.items():
        if env.get(source) and target not in env:
            env[target] = env[source]
    return env


def presence(env):
    """{имя: есть ли значение}. Только булевы, никаких значений."""
    return {name: bool(env.get(name)) for name in EXPECTED}


def apply_to_process(path=DEFAULT_PATH):
    """Положить ключи в `os.environ` — провайдеры читают только оттуда."""
    env = load(path)
    for name, value in env.items():
        if value and name not in os.environ:
            os.environ[name] = value
    return presence(env)
