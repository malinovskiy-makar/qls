#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def force_utf8_output():
    """Вывод команд — всегда UTF-8, независимо от кодировки консоли.

    ⚠️ На Windows консоль по умолчанию cp1251, и `print` любой строки с
    кириллицей или значком ⚠️ в перенаправленный вывод роняет команду
    UnicodeEncodeError'ом на середине — молча теряя часть работы. Лечится
    переменной PYTHONUTF8=1, но она доходит только до процессов, запущенных
    ПОСЛЕ её установки: уже открытый терминал (и запущенный из него агент)
    наследует старый блок окружения и продолжает падать.

    Поэтому не полагаемся на окружение вовсе, а переключаем потоки сами.
    На системе, где вывод и так UTF-8, ничего не делаем.
    """
    for stream in (sys.stdout, sys.stderr):
        encoding = getattr(stream, 'encoding', None) or ''
        if encoding.lower().replace('-', '') != 'utf8':
            try:
                stream.reconfigure(encoding='utf-8', errors='replace')
            except (AttributeError, ValueError):
                pass    # поток без reconfigure (перехвачен тестами) — не беда


def main():
    """Run administrative tasks."""
    force_utf8_output()
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
