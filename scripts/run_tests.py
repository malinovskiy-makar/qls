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
    --scope-from-git [BASE_REF]   быстрый круг сессии — только тесты
                    приложений, задетых изменениями с BASE_REF (по
                    умолчанию — с последнего коммита). ПОЛНЫЙ прогон
                    (без этого флага) перед сдачей сессии остаётся
                    обязательным — см. docs/TESTING.md, «Быстрый круг».
    --summary       сводка + полный traceback упавших в терминал, весь
                    verbosity=2 лог — в файл .test-logs/. Включается сам
                    собой вместе с --scope-from-git; --no-summary гасит.
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
sys.path.insert(0, str(BASE))  # чтобы `import scripts.*` работал и при
                                # прямом запуске `python scripts/run_tests.py`

from scripts.output_summary import extract_failure_blocks, parse_summary  # noqa: E402
from scripts.scope_from_git import build_reverse_import_index, changed_files, resolve_labels  # noqa: E402

SERIAL_TAG = 'serial'
_LAST_COMMIT = '__последний_коммит__'


def _run(название, аргументы, окружение, log_path=None):
    """Один шаг прогона. Возвращает (код возврата, секунды).

    log_path=None -> вывод идёт прямо на экран вживую (как раньше — владелец
    должен видеть ход прогона, иначе получасовое молчание неотличимо от
    зависшего процесса). log_path задан -> вывод пишется в файл, а на экран
    после завершения шага идёт только сводка (см. _print_step_summary).
    """
    команда = [sys.executable, 'manage.py', 'test'] + аргументы
    заголовок = '\n' + '=' * 72 + '\n%s: %s\n' % (название, ' '.join(команда[1:])) + '=' * 72
    print(заголовок, flush=True)
    начало = time.monotonic()

    if log_path is None:
        итог = subprocess.run(команда, cwd=str(BASE), env=окружение)
        return итог.returncode, time.monotonic() - начало

    смещение = log_path.stat().st_size if log_path.exists() else 0
    with open(log_path, 'a', encoding='utf-8') as лог:
        лог.write(заголовок + '\n')
        лог.flush()
        итог = subprocess.run(команда, cwd=str(BASE), env=окружение,
                               stdout=лог, stderr=subprocess.STDOUT)
    секунды = time.monotonic() - начало
    _print_step_summary(log_path, смещение)
    return итог.returncode, секунды


def _print_step_summary(log_path, смещение):
    """Печатает сводку и ПОЛНЫЙ traceback упавших для среза лога с offset'а."""
    with open(log_path, 'r', encoding='utf-8') as лог:
        лог.seek(смещение)
        текст = лог.read()

    сводка = parse_summary(текст)
    if сводка.ran is None:
        print('  (сводка не найдена в выводе — смотри %s)' % log_path)
        return

    print('  Ran %d test(s) in %.1fs  —  %s'
          % (сводка.ran, сводка.seconds,
             'OK' if сводка.ok else 'FAILED (failures=%d, errors=%d)'
             % (сводка.failures, сводка.errors)))
    if сводка.skipped:
        print('  skipped=%d' % сводка.skipped)

    for блок in extract_failure_blocks(текст):
        print('\n' + '-' * 72)
        print(блок)
    print('  полный лог (verbosity=2): %s' % log_path, flush=True)


def _resolve_scope(base_ref_arg):
    """--scope-from-git -> (labels: list[str] | None, full_run: bool, skip: bool)."""
    base_ref = None if base_ref_arg == _LAST_COMMIT else base_ref_arg
    пути = changed_files(base_ref=base_ref)
    индекс = build_reverse_import_index()
    итог = resolve_labels(пути, reverse_index=индекс)

    print('--scope-from-git: изменённые пути (%d):' % len(пути))
    for заметка in итог.notes:
        print('  ' + заметка)

    if итог.full_run:
        print('--scope-from-git: широкий эффект -> полный набор без сужения')
        return None, True, False
    if not итог.labels:
        print('--scope-from-git: тестового следствия нет — прогон пропущен')
        return None, False, True
    лейблы = sorted(итог.labels)
    print('--scope-from-git: лейблы = %s' % ', '.join(лейблы))
    return лейблы, False, False


def main():
    разбор = argparse.ArgumentParser(add_help=False)
    разбор.add_argument('--parallel', default='auto')
    разбор.add_argument('--keepdb', action='store_true')
    разбор.add_argument('--only-parallel', action='store_true')
    разбор.add_argument('--only-serial', action='store_true')
    разбор.add_argument('--scope-from-git', nargs='?', const=_LAST_COMMIT, default=None,
                         metavar='BASE_REF')
    разбор.add_argument('--summary', action='store_true')
    разбор.add_argument('--no-summary', action='store_true')
    свои, чужие = разбор.parse_known_args()

    лейблы = None
    if свои.scope_from_git is not None:
        лейблы, полный, пропустить = _resolve_scope(свои.scope_from_git)
        if пропустить:
            return 0
    else:
        полный = False

    сводка_режим = (свои.summary or (свои.scope_from_git is not None)) and not свои.no_summary
    log_path = None
    if сводка_режим:
        log_path = BASE / '.test-logs' / ('run-%s.log' % time.strftime('%Y%m%d-%H%M%S'))
        log_path.parent.mkdir(parents=True, exist_ok=True)

    общие = list(чужие) + (лейблы or [])
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
            env_a, log_path)
        шаги.append(('A (параллельный)', код, секунды))

    if not свои.only_parallel:
        # ⚠️ Шаг B идёт БЕЗ QLS_TEST_LOCAL_CACHE: здесь Redis настоящий,
        # ради него эти тесты сюда и вынесены.
        код, секунды = _run(
            'ШАГ B — последовательный (только serial)',
            общие + ['--tag', SERIAL_TAG],
            окружение, log_path)
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
    if log_path is not None:
        print('  полный лог (verbosity=2, оба шага): %s' % log_path)
    return провал


if __name__ == '__main__':
    sys.exit(main())
