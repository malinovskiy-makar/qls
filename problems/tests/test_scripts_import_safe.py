"""`scripts/test_*.py` не выполняют работу при импорте (18.09.2026).

Папка `scripts` — пакет (`__init__.py`, фаза --scope-from-git), поэтому
полный прогон без меток находит `scripts/test_*.py` по шаблону и
ИМПОРТИРУЕТ их. `test_timing.py` держал цикл на верхнем уровне и гнал весь
набор помодульно на SQLite: полный прогон шёл часами и переписывал
`reports/calc2_22aug/timing_plain.json`. На верхнем уровне таких файлов —
только импорты, определения, константы, `sys.path.insert` и
`if __name__ == '__main__'`.
"""
import ast
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

ALLOWED = (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef, ast.Assign,
           ast.AnnAssign, ast.If)


def _is_path_insert(node):
    return (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
            and 'sys.path' in ast.unparse(node.value.func))


def _is_docstring(node):
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)


class ScriptsImportSafeTests(SimpleTestCase):

    def test_no_top_level_work_in_scripts_test_files(self):
        offenders = []
        for path in sorted((Path(settings.BASE_DIR) / 'scripts').glob('test*.py')):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in tree.body:
                if _is_docstring(node) or _is_path_insert(node):
                    continue
                if isinstance(node, ast.If) and '__name__' not in ast.unparse(node.test):
                    offenders.append('%s:%d' % (path.name, node.lineno))
                elif not isinstance(node, ALLOWED):
                    offenders.append('%s:%d' % (path.name, node.lineno))
        self.assertEqual(offenders, [])
