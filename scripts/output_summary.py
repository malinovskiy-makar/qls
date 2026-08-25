# -*- coding: utf-8 -*-
"""Разбор текстового вывода `manage.py test` (--verbosity 2) в сводку.

Зачем. `--verbosity 2` печатает по строке на каждый тест — на полный набор
это тысячи строк, которые незачем видеть в контексте Claude Code. Полный
текст пишется в файл (`--summary` в run_tests.py), а на экран идёт только
то, что реально нужно для решения: сколько прошло/упало/пропущено, сколько
заняло, и — если что-то упало — ПОЛНЫЙ traceback каждого падения без обрезки.
"""
import re
from collections import namedtuple

RunSummary = namedtuple('RunSummary', ['ran', 'failures', 'errors', 'skipped', 'ok', 'seconds'])

_RAN_RE = re.compile(r'^Ran (\d+) tests? in ([\d.]+)s', re.MULTILINE)
_FAILED_RE = re.compile(r'^FAILED \(([^)]*)\)', re.MULTILINE)
_OK_RE = re.compile(r'^OK(?:\s*\(([^)]*)\))?\s*$', re.MULTILINE)
_COUNT_RE = re.compile(r'(failures|errors|skipped)=(\d+)')

_BLOCK_SEP_RE = re.compile(r'^={70}$\n', re.MULTILINE)
_TAIL_RE = re.compile(r'\n-{70}\nRan \d+ tests?.*\Z', re.DOTALL)


def _counts(paren_contents):
    counts = {'failures': 0, 'errors': 0, 'skipped': 0}
    if paren_contents:
        for name, value in _COUNT_RE.findall(paren_contents):
            counts[name] = int(value)
    return counts


def parse_summary(text):
    """Текст прогона -> RunSummary. Отсутствие итоговой строки — не ok."""
    ran_match = _RAN_RE.search(text)
    if not ran_match:
        return RunSummary(ran=None, failures=0, errors=0, skipped=0, ok=False, seconds=None)

    ran = int(ran_match.group(1))
    seconds = float(ran_match.group(2))

    failed_match = _FAILED_RE.search(text)
    if failed_match:
        counts = _counts(failed_match.group(1))
        return RunSummary(
            ran=ran, failures=counts['failures'], errors=counts['errors'],
            skipped=counts['skipped'], ok=False, seconds=seconds)

    ok_match = _OK_RE.search(text)
    if ok_match:
        counts = _counts(ok_match.group(1))
        return RunSummary(
            ran=ran, failures=0, errors=0, skipped=counts['skipped'], ok=True, seconds=seconds)

    # "Ran N тестов" нашли, а ни OK, ни FAILED следом нет — вывод оборван.
    return RunSummary(ran=ran, failures=0, errors=0, skipped=0, ok=False, seconds=seconds)


def extract_failure_blocks(text):
    """Список блоков 'FAIL: ...'/'ERROR: ...' с полным traceback, без обрезки."""
    chunks = _BLOCK_SEP_RE.split(text)
    blocks = []
    for chunk in chunks:
        if not (chunk.startswith('FAIL:') or chunk.startswith('ERROR:')):
            continue
        chunk = _TAIL_RE.sub('', chunk)
        blocks.append(chunk.rstrip('\n'))
    return blocks
