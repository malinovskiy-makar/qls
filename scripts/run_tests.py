# -*- coding: utf-8 -*-
"""Полный прогон в ДВА ШАГА: параллельный и последовательный.

    venv313/Scripts/python.exe scripts/run_tests.py            # Windows
    ./venv313/bin/python scripts/run_tests.py                  # macOS

Зачем. Полный набор шёл 26–57 минут ЛИНЕЙНО из-за горстки тестов, которые
поднимают настоящий сервер с браузером. Остальные 2 600 к параллельности
претензий не имеют. Теперь:

    шаг A — всё, кроме помеченных `serial`, в `--parallel auto`;
    шаг B — только помеченные `serial`, последовательно.

⚠️ ПОЧЕМУ ЭТО СКРИПТ, А НЕ ДВЕ КОМАНДЫ В СТРОКУ. Две команды подряд очень
легко написать так, что виден код возврата только второй: `A && B` скроет
падение A, если B тоже упадёт, а `A; B` скроет падение A всегда. Здесь
итоговый код ненулевой, если упал ЛЮБОЙ шаг, и в конце печатается сводка.

⚠️ ПОЧЕМУ НА ШАГЕ A КЭШ УВОДИТСЯ В ПАМЯТЬ (QLS_TEST_LOCAL_CACHE=1).
Django даёт каждому воркеру свою тестовую базу, но Redis остаётся один на
всех: `cache.clear()` у Redis — это FLUSHDB, и один воркер обнулял бы кэш
остальным посреди их работы. Разделить префиксом ключей нельзя — FLUSHDB
чистит базу целиком. Разделить по базам Redis тоже нельзя: их всего 16,
четыре заняты, а воркеров по числу ядер. Подробности — docs/TESTING.md.

Ключи командной строки скрипта:
    --keepdb        передаётся обоим шагам (см. docs/TESTING.md)
    --parallel N    сколько воркеров на шаге A (по умолчанию auto)
    --only-parallel / --only-serial   прогнать один шаг
Всё остальное уезжает в `manage.py test` обоих шагов как есть, например
`--settings=config.settings_test_pg` или `--verbosity 2`.
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SERIAL_TAG = 'serial'


def _run(название, аргументы, окружение):
    """Один шаг прогона. Возвращает (код возврата, секунды)."""
    команда = [sys.executable, 'manage.py', 'test'] + аргументы
    print('\n' + '=' * 72)
    print('%s: %s' % (название, ' '.join(команда[1:])))
    print('=' * 72, flush=True)
    начало = time.monotonic()
    # Без capture_output: владелец должен видеть ход прогона вживую, иначе
    # получасовое молчание неотличимо от зависшего процесса.
    итог = subprocess.run(команда, cwd=str(BASE), env=окружение)
    return итог.returncode, time.monotonic() - начало


def main():
    разбор = argparse.ArgumentParser(add_help=False)
    разбор.add_argument('--parallel', default='auto')
    разбор.add_argument('--keepdb', action='store_true')
    разбор.add_argument('--only-parallel', action='store_true')
    разбор.add_argument('--only-serial', action='store_true')
    свои, чужие = разбор.parse_known_args()

    общие = list(чужие)
    if свои.keepdb:
        общие.append('--keepdb')

    окружение = dict(os.environ)
    # Вывод команд по-русски: без явной кодировки Windows отдаёт его в cp1251.
    окружение['PYTHONIOENCODING'] = 'utf-8'
    окружение['PYTHONUTF8'] = '1'

    шаги = []

    if not свои.only_serial:
        env_a = dict(окружение, QLS_TEST_LOCAL_CACHE='1')
        код, секунды = _run(
            'ШАГ A — параллельный (всё, кроме serial)',
            общие + ['--parallel', свои.parallel,
                     '--exclude-tag', SERIAL_TAG],
            env_a)
        шаги.append(('A (параллельный)', код, секунды))

    if not свои.only_parallel:
        # ⚠️ Шаг B идёт БЕЗ QLS_TEST_LOCAL_CACHE: здесь Redis настоящий,
        # ради него эти тесты сюда и вынесены.
        код, секунды = _run(
            'ШАГ B — последовательный (только serial)',
            общие + ['--tag', SERIAL_TAG],
            окружение)
        шаги.append(('B (последовательный)', код, секунды))

    print('\n' + '=' * 72)
    print('ИТОГ')
    print('=' * 72)
    всего = 0.0
    провал = 0
    for название, код, секунды in шаги:
        всего += секунды
        провал = провал or код
        print('  шаг %-22s код %s   %6.1f с  (%4.1f мин)'
              % (название, код, секунды, секунды / 60))
    print('  ' + '-' * 60)
    print('  всего %36.1f с  (%4.1f мин)' % (всего, всего / 60))
    print('  общий код возврата: %s%s'
          % (провал, '' if провал else '  — оба шага зелёные'))
    return провал


if __name__ == '__main__':
    sys.exit(main())
