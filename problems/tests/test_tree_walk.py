"""Обходчик дерева проекта — `problems/tests/tree.py`.

Проверки-ревизии ищут образцы прямо в файлах и обходят дерево целиком.
Если обход уходит в чужую рабочую копию, проверка краснеет из-за того, какие
`git worktree` завёл себе разработчик, — а не из-за кода.

Чужая копия здесь собирается синтетически, во временном каталоге: тест
обязан работать и на машине без worktree, и в CI.
"""
import os
import tempfile

from django.conf import settings
from django.test import SimpleTestCase

from problems.tests.tree import (
    FOREIGN_DIR_NAMES,
    is_foreign,
    is_nested_checkout,
    project_files,
    walk_project,
)


def make(root, *parts, content='x'):
    """Создать файл по частям пути, вернуть полный путь."""
    path = os.path.join(root, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(content)
    return path


class ЧужаяКопияTests(SimpleTestCase):
    """Главное свойство: обход не выходит за пределы своего проекта."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='tree_walk_')
        self.addCleanup(__import__('shutil').rmtree, self.root, True)
        self.свой = make(self.root, 'teacher', 'templates', '_note.html')

    def test_worktree_с_файлом_git_не_обходится(self):
        """У `git worktree` `.git` — ФАЙЛ со ссылкой на основной репозиторий.

        Ровно этот случай уронил два теста 02.09.2026:
        `.claude/worktrees/import-new-sources-edbc26`.
        """
        make(self.root, 'somewhere', '.git', content='gitdir: /main/.git/wt')
        чужой = make(self.root, 'somewhere', 'teacher', 'templates', '_note.html')

        found = list(project_files(self.root, '.html'))

        self.assertEqual(found, [self.свой])
        self.assertNotIn(чужой, found)

    def test_клон_с_каталогом_git_не_обходится(self):
        """У обычного клона `.git` — каталог. Различать не нужно."""
        os.makedirs(os.path.join(self.root, 'clone', '.git'))
        чужой = make(self.root, 'clone', 'teacher', 'templates', '_note.html')

        found = list(project_files(self.root, '.html'))

        self.assertEqual(found, [self.свой])
        self.assertNotIn(чужой, found)

    def test_каталог_claude_не_обходится_даже_без_git(self):
        """Имя закрывает то, что известно сегодня, — до проверки на `.git`."""
        чужой = make(self.root, '.claude', 'worktrees', 'x', 'a.html')

        self.assertNotIn(чужой, list(project_files(self.root, '.html')))

    def test_вложенная_копия_на_любой_глубине(self):
        """Признак проверяется у каждого каталога, а не только у верхних."""
        make(self.root, 'a', 'b', 'c', '.git', content='gitdir: /x')
        чужой = make(self.root, 'a', 'b', 'c', 'page.html')
        свой_рядом = make(self.root, 'a', 'b', 'page.html')

        found = set(project_files(self.root, '.html'))

        self.assertIn(свой_рядом, found)
        self.assertNotIn(чужой, found)


class СлужебныеКаталогиTests(SimpleTestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='tree_walk_')
        self.addCleanup(__import__('shutil').rmtree, self.root, True)

    def test_venv_любой_версии_пропускается(self):
        """venv, venv312, venv313, .venv — перечислять поимённо значит забыть."""
        for name in ('venv', 'venv312', 'venv313', '.venv'):
            self.assertTrue(is_foreign(self.root, name), name)

    def test_кэши_инструментов_пропускаются(self):
        for name in ('node_modules', '__pycache__', '.ruff_cache', '.git'):
            self.assertTrue(is_foreign(self.root, name), name)

    def test_обычный_каталог_проекта_обходится(self):
        for name in ('teacher', 'templates', 'problems', 'catalog', 'docs',
                     'student', 'game', 'calc2', 'scripts'):
            self.assertFalse(is_foreign(self.root, name), name)

    def test_под_префикс_venv_попадает_и_venvironment(self):
        """Осознанный компромисс в пользу простоты, зафиксированный явно.

        Правило `startswith('venv')` съедает и `venvironment_docs`, если
        такой каталог однажды заведут. Ловить это точным перечислением
        (`venv`, `venv312`, `venv313`, …) значит однажды забыть новое
        окружение и молча начать обходить его целиком — а это тысячи чужих
        файлов. Цена ошибки в другую сторону несравнимо меньше.
        """
        self.assertTrue(is_foreign(self.root, 'venv-old'))
        self.assertTrue(is_foreign(self.root, 'venvironment_docs'))


class СвойСписокПроверкиTests(SimpleTestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='tree_walk_')
        self.addCleanup(__import__('shutil').rmtree, self.root, True)

    def test_skip_names_добавляется_к_общему_списку(self):
        нужный = make(self.root, 'teacher', 'a.html')
        лишний = make(self.root, 'reports', 'b.html')

        self.assertIn(лишний, list(project_files(self.root, '.html')))
        self.assertNotIn(
            лишний, list(project_files(self.root, '.html', ('reports',))))
        self.assertIn(
            нужный, list(project_files(self.root, '.html', ('reports',))))


class НаЖивомДеревеTests(SimpleTestCase):
    """Проверка на настоящем репозитории, а не на макете."""

    def test_обход_не_выходит_за_пределы_проекта(self):
        """Ни один найденный файл не лежит в чужой рабочей копии.

        На машине с `git worktree` внутри репозитория этот тест краснел бы
        без отсечения; на чистой машине он просто ничего не находит и всё
        равно зелёный.
        """
        чужие = [path for path in project_files(str(settings.BASE_DIR), '.html')
                 if any(part in FOREIGN_DIR_NAMES
                        for part in path.split(os.sep))]
        self.assertEqual(чужие, [])

    def test_шаблоны_проекта_всё_же_находятся(self):
        """Предохранитель: отсечение не должно вычистить обход досуха."""
        found = list(project_files(str(settings.BASE_DIR), '.html'))
        self.assertGreater(len(found), 50)

    def test_walk_project_отдаёт_пары_папка_файлы(self):
        first = next(iter(walk_project(str(settings.BASE_DIR))))
        self.assertEqual(len(first), 2)
        self.assertIsInstance(first[1], list)

    def test_сам_репозиторий_вложенной_копией_не_считается(self):
        """У корня есть свой `.git` — но обход НАЧИНАЕТСЯ с него, а не входит.

        Признак проверяется только у детей: иначе обход останавливался бы,
        не начавшись.
        """
        self.assertTrue(is_nested_checkout(str(settings.BASE_DIR)))
        self.assertGreater(len(list(project_files(str(settings.BASE_DIR),
                                                  '.html'))), 50)
