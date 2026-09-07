"""Обход дерева проекта для тестов-ревизий. Одно место, один список.

Часть проверок ищет образцы не в базе, а прямо в файлах: многострочный
`{# … #}`, вторая форма заметки, хвосты старых экранов. Такие тесты обходят
дерево целиком — и обязаны при этом видеть ТОЛЬКО этот проект.

⚠️ ЧУЖАЯ РАБОЧАЯ КОПИЯ ВНУТРИ РЕПОЗИТОРИЯ — НЕ ТЕОРИЯ. На машине владельца
`git worktree` ветки `feat/import-new-sources` лежит в
`.claude/worktrees/import-new-sources-edbc26`, то есть ВНУТРИ рабочего
дерева, а рядом — junction на соседний репозиторий с ещё одной копией
проекта. Полный прогон 02.09.2026 покраснел двумя тестами: они нашли по
три `teacher/templates/teacher/_tutor_note.html` вместо одного. Тест не
имеет права зависеть от того, какие worktree завёл себе разработчик.

⚠️ JUNCTION НЕ ЛОВИТСЯ ФЛАГОМ `followlinks`. `os.walk` по умолчанию не идёт
по симлинкам, но на Windows соседний репозиторий подключён точкой
соединения (junction): `os.path.islink` про неё говорит `False`, а
`os.path.isdir` — `True`, и обход спокойно уходит внутрь. Поэтому чужие
копии узнаются не по типу записи, а по имени и по наличию своего `.git`.

⚠️ ПРИЗНАК «СВОЙ `.git` ВНУТРИ» ВАЖНЕЕ СПИСКА ИМЁН. Список закрывает то, что
известно сегодня; признак закрывает и завтрашний worktree, который положат
в каталог с любым другим названием. У worktree `.git` — файл со ссылкой на
основной репозиторий, у клона — каталог; проверяется существование, а не тип.
"""
import os

#: Каталоги, внутрь которых не ходит ни одна проверка проекта: чужой код,
#: кэши инструментов и служебное хозяйство редактора.
FOREIGN_DIR_NAMES = frozenset({
    '.git', '.claude', '.hg', '.svn',
    'node_modules', '__pycache__',
    '.tox', '.nox', '.mypy_cache', '.ruff_cache', '.pytest_cache',
    '.hypothesis', 'htmlcov', '.idea', '.vscode',
})

#: Виртуальные окружения проекта: `venv`, `venv312`, `venv313`, `.venv`.
#: Проверяется префиксом — номер версии в имени меняется от окружения
#: к окружению, а перечислять их поимённо значит однажды забыть новое.
VENV_PREFIXES = ('venv', '.venv')


def is_nested_checkout(path):
    """Каталог — чужая рабочая копия: у него есть собственный `.git`.

    У `git worktree` это файл со ссылкой на основной репозиторий, у клона —
    каталог. Различать не нужно: важно, что дерево внутри — не наше.
    """
    return os.path.exists(os.path.join(path, '.git'))


def is_foreign(parent, name):
    """Не ходить ли внутрь каталога `name`, лежащего в `parent`."""
    if name in FOREIGN_DIR_NAMES:
        return True
    if name.startswith(VENV_PREFIXES):
        return True
    return is_nested_checkout(os.path.join(parent, name))


def walk_project(root, skip_names=()):
    """`os.walk` по проекту, минуя чужие копии и служебные каталоги.

    `skip_names` — то, что данная проверка исключает СВЕРХ общего списка
    (`reports`, `materials`, `staticfiles` и подобное). Список у каждой
    проверки свой и намеренно не сведён в общий: он говорит, что проверка
    считает своим предметом, а не что в дереве постороннее.

    Отдаёт `(folder, files)`. Каталоги отсекаются на месте, через
    `dirs[:]`, — то есть обход внутрь них не идёт вовсе, а не отбрасывает
    результат после.
    """
    skip = frozenset(skip_names)
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs
                   if d not in skip and not is_foreign(folder, d)]
        yield folder, files


def project_files(root, suffix, skip_names=()):
    """Пути ко всем файлам проекта с данным окончанием имени."""
    for folder, files in walk_project(root, skip_names):
        for name in files:
            if name.endswith(suffix):
                yield os.path.join(folder, name)
