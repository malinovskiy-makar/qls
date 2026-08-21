"""Тест-страж карты модулей calc2 (docs/calc2/CALC2_MAP.md).

Карта нужна, чтобы по описанию бага в /calc2/ выбрать два-три файла, а не
гадать. Устаревшая карта хуже отсутствия карты: она уверенно указывает не
туда. Этот тест НЕ проверяет содержание рукописных разделов (это работа
человека) — он проверяет две механические вещи:

1. Множество файлов, которые ДЕЙСТВИТЕЛЬНО участвуют в странице /calc2/
   (тем же способом, каким их находит `manage.py calc2_map` — разбором
   маршрута → представления → шаблона → статики), совпадает с тем, что
   перечислено в таблице автосекции карты. Если файл появился в коде и не
   попал в карту, или пропал из кода, а в карте остался — тест падает.
2. Каждое имя функции, упомянутое в индексе функций автосекции, реально
   встречается в своём файле. Номера строк НЕ проверяются намеренно — они
   смещаются при каждой правке, и проверка стала бы шумной и её начали бы
   игнорировать (см. CLAUDE.md).
"""
import re

from django.conf import settings
from django.test import SimpleTestCase

from calc2.management.commands.calc2_map import (
    MAP_PATH,
    START_LINE_RE,
    END_LINE_RE,
    discover_core_files,
    function_index,
    rel,
)

FIX_HINT = 'запусти venv/bin/python manage.py calc2_map (на Windows — venv313\\Scripts\\python.exe manage.py calc2_map)'

# Строка таблицы автосекции: | `путь` | строк | КБ | тип |
TABLE_ROW_RE = re.compile(r'^\|\s*`([^`]+)`\s*\|', re.MULTILINE)
# Заголовок блока функций внутри автосекции: #### `путь`
FUNC_HEADING_RE = re.compile(r'^####\s+`([^`]+)`\s*$', re.MULTILINE)
# Строка индекса: - строка N — `имя`
FUNC_LINE_RE = re.compile(r'^- строка \d+ — `([^`]+)`\s*$', re.MULTILINE)


def _read_auto_section():
    if not MAP_PATH.exists():
        raise AssertionError(f'{MAP_PATH} не существует. {FIX_HINT}')
    content = MAP_PATH.read_text(encoding='utf-8')
    start_m = START_LINE_RE.search(content)
    end_m = END_LINE_RE.search(content)
    if not start_m or not end_m or end_m.start() < start_m.end():
        raise AssertionError(
            f'В {MAP_PATH} нет маркеров автосекции каждый на своей строке '
            f'(в правильном порядке) — файл повреждён. {FIX_HINT}'
        )
    return content[start_m.end():end_m.start()]


def _mapped_files(auto_section):
    """Пути из таблицы файлов автосекции, в порядке появления."""
    return TABLE_ROW_RE.findall(auto_section)


def _mapped_function_index(auto_section):
    """{путь: [имена функций]} из индекса функций автосекции."""
    headings = list(FUNC_HEADING_RE.finditer(auto_section))
    result = {}
    for i, h in enumerate(headings):
        path = h.group(1)
        block_start = h.end()
        block_end = headings[i + 1].start() if i + 1 < len(headings) else len(auto_section)
        block = auto_section[block_start:block_end]
        result[path] = FUNC_LINE_RE.findall(block)
    return result


class Calc2MapMatchesCodeTests(SimpleTestCase):
    """Множество файлов calc2 и карта не разошлись."""

    def test_file_set_matches_code(self):
        auto_section = _read_auto_section()
        mapped = set(_mapped_files(auto_section))

        actual_paths = [rel(p) for p in discover_core_files()]
        actual = set(actual_paths)

        # Не полагаемся на то, что порядок совпал — только на множество.
        self.assertEqual(
            len(actual_paths), len(actual),
            'discover_core_files() вернул дубликаты — это баг самого разбора шаблона',
        )

        appeared = actual - mapped
        vanished = mapped - actual

        # Второе измерение дрейфа: файл лежит физически в каталоге статики
        # calc2, но НЕ подключён в шаблоне (значит его нет и в
        # discover_core_files(), и в карте). Такой файл — либо забытый
        # мусор, либо новый скрипт, который забыли подключить строкой
        # <script src="{% static ... %}"> в calc2.html. И то и другое стоит
        # заметить, а не молчать: карта не должна выглядеть полной, пока на
        # диске лежит файл, которого она не видит вовсе.
        static_dir = settings.BASE_DIR / 'calc2' / 'static' / 'calc2'
        on_disk = {
            rel(p) for p in static_dir.glob('*')
            if p.is_file() and p.suffix in ('.js', '.css')
        }
        orphaned = on_disk - actual

        if appeared or vanished or orphaned:
            parts = []
            if appeared:
                parts.append(
                    'появился в коде, но не описан в карте: ' + ', '.join(sorted(appeared))
                )
            if vanished:
                parts.append(
                    'исчез из кода, но остался в карте: ' + ', '.join(sorted(vanished))
                )
            if orphaned:
                parts.append(
                    'лежит в calc2/static/calc2/, но не подключён в шаблоне и не в карте: '
                    + ', '.join(sorted(orphaned))
                )
            self.fail('Карта calc2 разошлась с кодом — ' + '; '.join(parts) + f'. {FIX_HINT}')

    def test_function_index_matches_code(self):
        auto_section = _read_auto_section()
        mapped_index = _mapped_function_index(auto_section)
        self.assertTrue(
            mapped_index,
            'В автосекции карты не нашлось ни одного индекса функций — похоже, файл пуст. '
            + FIX_HINT,
        )

        base_dir = settings.BASE_DIR
        errors = []
        for path_str, names in mapped_index.items():
            full_path = base_dir / path_str
            if not full_path.exists():
                errors.append(f'{path_str}: файл из индекса функций не существует')
                continue
            source = full_path.read_text(encoding='utf-8')
            for name in names:
                # Слово целиком (\b), не подстрока: "fmt" не должен считаться
                # найденным внутри "fmtLinear".
                if not re.search(r'\b' + re.escape(name) + r'\b', source):
                    errors.append(f'{path_str}: функция `{name}` из карты не найдена в файле')

        if errors:
            self.fail(
                'Индекс функций карты calc2 разошёлся с кодом:\n  '
                + '\n  '.join(errors)
                + f'\n{FIX_HINT}'
            )

    def test_static_files_have_matching_disk_files(self):
        """Сама вспомогательная функция rel()/discover_core_files() не врёт:
        каждый найденный файл реально существует и читается (защита от
        ложно-зелёного теста на пустом множестве)."""
        core_files = discover_core_files()
        self.assertGreaterEqual(
            len(core_files), 20,
            'discover_core_files() нашёл подозрительно мало файлов — разбор шаблона сломан?',
        )
        for p in core_files:
            self.assertTrue(p.is_file(), f'{p} не файл или не существует')
