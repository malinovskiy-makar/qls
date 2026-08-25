# -*- coding: utf-8 -*-
"""Сопоставление изменённых путей с тестовыми лейблами Django (--scope-from-git).

Зачем. Полный прогон (2 700+ тестов) осмыслен один раз перед сдачей сессии —
это заведено отдельно (Notion, решение 21.08 «Протокол прогона тестов»). Во
время работы нужен узкий круг: тесты только тех приложений, которые реально
может задеть текущая правка. Модуль отвечает на один вопрос: список
изменённых путей -> набор лейблов `manage.py test`.

Правило сопоставления — по каталогу верхнего уровня:

    catalog/, student/, teacher/, game/, calc2/, calendar_stub/, problems/
        -> свой же лейбл.

`calc2` НЕ импортирует ничего из шести остальных приложений и никем не
импортируется — проверено 2026-08-25 (`grep -rn "from problems" catalog
student teacher game calc2` и обратный обход). Единственное по-настоящему
изолированное приложение.

`problems` — ядро: там живут ВСЕ модели (CLAUDE.md, раздел «Границы
приложений»), и `catalog`, `student`, `teacher`, `game`, `calendar_stub`
реально импортируют из него напрямую. Правка внутри `problems/` (кроме двух
поддеревьев ниже) уходит НЕ сузившись — в лейблы problems + все пятеро.
Единственная альтернатива — искать зависимость по каждому символу отдельно
(AST, разбор `ForeignKey('problems.X', ...)` и т.п.) — отвергнута: в проекте
такое встречается (`problems/models.py:853`), обычный текстовый поиск по
импортам его не увидит, а цена ложного сужения (пропущенный тест на
проде) выше цены лишнего прогона catalog/student/teacher/game/calendar_stub.

Два поддерева внутри `problems/` — исключение из блэнкет-правила, ПОТОМУ
ЧТО код-чек 2026-08-25 показал, что они почти всегда лист:

    problems/management/commands/  — 150+ разовых команд импорта/починки,
        из них внешне используется (напрямую импортируется другим
        приложением) только apply_topic_mapping.py (CANONICAL — читают
        catalog, teacher, game).
    problems/tests/                — тесты сами по себе никто не
        импортирует, КРОМЕ problems/tests/factories.py — его использует
        catalog/tests (make_problem и другие фабрики).

Для этих двух поддеревьев сопоставление узкое: свой файл + лейблы, которые
РЕАЛЬНО импортируют именно этот модуль (см. `build_reverse_import_index`).
Если для конкретного изменённого файла зависимых не нашлось — лейбл только
`problems`, и это большинство случаев в обоих поддеревьях.

Обратные связи вне problems, подтверждённые тем же код-чеком:

    teacher.access      -> calendar_stub (calendar_stub/views.py)
    teacher.picker,
    teacher.views*       -> problems (problems/tests/*.py собирают карточки
                             через teacher.picker и validate через
                             teacher.views_problems/views)
    game.views           -> problems (problems/management/commands/
                             check_vsosh_gates.py и _municip.py)

Эти рёбра не захардкожены отдельным списком, а находятся тем же общим
механизмом `build_reverse_import_index` — единообразно с двумя поддеревьями
problems/ выше, и не протухнут, если импорты переедут.

`search_service/` — отдельный процесс вне Django-приложений, единственный
потребитель — `catalog/search_client.py` (проверено grep). Маппится прямо на
catalog.

Широкий эффект — узить не пытаемся, гоняем всё:

    config/, manage.py, requirements/*, docker-compose*.yml, CLAUDE.md,
    docs/*, templates/*.html (корневые, ОБЩИЕ для всех — не путать с
    <app>/templates/<app>/... — те уже покрыты правилом по каталогу
    верхнего уровня, потому что лежат ВНУТРИ каталога приложения).

Всё остальное (scripts/ — сами вспомогательные скрипты, не Django-код;
data/, materials/, reports/, 2025/, graphs/, deploy*/,
polish_screenshots/, разрозненные .md вне CLAUDE.md/docs/) — тестового
следствия не имеет и в лейблы не попадает.

ВАЖНО: этот модуль — быстрый круг для сессии, не замена полному прогону.
Приближение по прямым импорт-строкам не видит транзитивные и
Django-специфичные связи (сигналы, `ForeignKey('app.Model', ...)`,
миграции). Именно поэтому полный двухшаговый прогон перед сдачей остаётся
обязательным — см. docs/TESTING.md.
"""
import re
import subprocess
from collections import namedtuple
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

APP_LABELS = ('problems', 'catalog', 'student', 'teacher', 'game', 'calc2', 'calendar_stub')

# Внутри problems/ — узкое (по факту импортов), а не блэнкет-сопоставление.
NARROW_PROBLEMS_PREFIXES = ('problems/management/commands/', 'problems/tests/')

# Кто реально импортирует что-то из problems/ напрямую (не narrow-поддеревья).
BLANKET_PROBLEMS_DEPENDENTS = frozenset({'catalog', 'student', 'teacher', 'game', 'calendar_stub'})

# Широкий эффект — полный набор без попытки сузить.
#
# docs/TESTING.md — САМ ОПИСЫВАЕТ методику прогона, поэтому в списке. Но
# `docs/` вообще НЕ здесь: 2026-08-25 код-чек (Фаза 4, зубастость) поймал
# ложную тревогу — правка docs/DATA.md (документация по данным, к тестам
# отношения не имеющая) блэнкетом уходила в полный набор наравне с правкой
# CLAUDE.md. Расширять список докс-триггеров вручную по мере находок, а не
# сваливать всю docs/ в одну кучу.
_FULL_RUN_EXACT = frozenset({'manage.py', 'CLAUDE.md', 'docs/TESTING.md'})
_FULL_RUN_PREFIXES = ('config/', 'requirements/', 'docker-compose', 'templates/')

_IMPORT_RE = re.compile(r'^\s*(?:from|import)\s+([\w.]+)', re.MULTILINE)

ScopeResult = namedtuple('ScopeResult', ['labels', 'full_run', 'notes'])


def _normalize(path):
    return path.replace('\\', '/').strip()


def _dotted_module(path):
    """'problems/management/commands/x.py' -> 'problems.management.commands.x'.

    Для файлов не на Python (шаблоны и т.п.) возвращает None — у них нет
    модуля, который можно было бы искать в индексе импортов.
    """
    if not path.endswith('.py'):
        return None
    parts = path[:-3].split('/')
    if parts and parts[-1] == '__init__':
        parts = parts[:-1]
    if not parts or parts[0] == '':
        return None
    return '.'.join(parts)


def _is_full_run_trigger(path):
    if path in _FULL_RUN_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in _FULL_RUN_PREFIXES)


def build_reverse_import_index(repo=BASE):
    """Кто (какой лейбл) импортирует какой модуль напрямую.

    Однопроходное сканирование `*.py` внутри каждого из APP_LABELS.
    Возвращает {dotted_module: frozenset(лейблы, которые его импортируют)}.
    Считаются только импорты из НАШИХ приложений (problems.*, teacher.* и
    т.д.) — импорт стандартной библиотеки или сторонних пакетов не нужен.
    """
    index = {}
    for label in APP_LABELS:
        app_dir = repo / label
        if not app_dir.is_dir():
            continue
        for py_file in app_dir.rglob('*.py'):
            try:
                text = py_file.read_text(encoding='utf-8')
            except (UnicodeDecodeError, OSError):
                continue
            for match in _IMPORT_RE.finditer(text):
                module = match.group(1)
                if module.split('.', 1)[0] in APP_LABELS:
                    index.setdefault(module, set()).add(label)
    return {module: frozenset(labels) for module, labels in index.items()}


def resolve_labels(paths, reverse_index=None):
    """Список изменённых путей -> ScopeResult(labels, full_run, notes)."""
    reverse_index = reverse_index or {}
    paths = [_normalize(p) for p in paths if _normalize(p)]

    if not paths:
        return ScopeResult(frozenset(), False, ['нет изменённых путей — тестов не запускаем'])

    labels = set()
    full_run = False
    notes = []

    for path in paths:
        if _is_full_run_trigger(path):
            full_run = True
            notes.append('%s -> широкий эффект, полный набор' % path)
            continue

        if path == 'search_service' or path.startswith('search_service/'):
            labels.add('catalog')
            notes.append('%s -> catalog (единственный потребитель search_service)' % path)
            continue

        top = path.split('/', 1)[0]

        if top == 'problems':
            narrow = any(path.startswith(prefix) for prefix in NARROW_PROBLEMS_PREFIXES)
            if narrow:
                labels.add('problems')
                module = _dotted_module(path)
                extra = reverse_index.get(module, frozenset()) if module else frozenset()
                labels |= extra
                notes.append('%s -> problems%s' % (
                    path, (' + ' + ', '.join(sorted(extra)) if extra else ' (изолирован)')))
            else:
                labels.add('problems')
                labels |= BLANKET_PROBLEMS_DEPENDENTS
                notes.append('%s -> problems + всё, что от него зависит' % path)
            continue

        if top in APP_LABELS:  # catalog/student/teacher/game/calc2/calendar_stub
            labels.add(top)
            module = _dotted_module(path)
            extra = (reverse_index.get(module, frozenset()) - {top}) if module else frozenset()
            labels |= extra
            notes.append('%s -> %s%s' % (
                path, top, (' + ' + ', '.join(sorted(extra)) if extra else '')))
            continue

        notes.append('%s -> нет тестового следствия' % path)

    return ScopeResult(frozenset(labels), full_run, notes)


def _run_git(args, repo=BASE):
    result = subprocess.run(
        ['git'] + args, cwd=str(repo), capture_output=True, text=True, encoding='utf-8')
    if result.returncode != 0:
        raise RuntimeError('git %s: %s' % (' '.join(args), result.stderr.strip()))
    return result.stdout


def _parse_status_porcelain(output):
    """Пути untracked/изменённых файлов из `git status --porcelain`."""
    paths = []
    for line in output.splitlines():
        if not line.strip():
            continue
        # 'XY путь' либо 'XY старый -> новый' при переименовании
        rest = line[3:] if len(line) > 3 else line.lstrip()
        if ' -> ' in rest:
            rest = rest.split(' -> ', 1)[1]
        paths.append(rest.strip().strip('"'))
    return paths


def changed_files(base_ref=None, repo=BASE):
    """Объединение git diff --name-only <base>...HEAD и git status --porcelain.

    base_ref=None -> diff от последнего коммита (git diff --name-only HEAD).
    """
    if base_ref:
        diff_output = _run_git(['diff', '--name-only', '%s...HEAD' % base_ref], repo=repo)
    else:
        diff_output = _run_git(['diff', '--name-only', 'HEAD'], repo=repo)
    status_output = _run_git(['status', '--porcelain'], repo=repo)

    paths = set()
    for line in diff_output.splitlines():
        line = line.strip()
        if line:
            paths.add(line)
    for path in _parse_status_porcelain(status_output):
        if path:
            paths.add(path)
    return sorted(paths)
