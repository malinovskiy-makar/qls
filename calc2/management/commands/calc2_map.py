"""
Собирает автосекцию карты модулей calc2 (docs/calc2/CALC2_MAP.md).

Задача карты — по описанию бага в /calc2/ выбрать два-три нужных файла, а не
гадать по именам. Карта состоит из трёх частей: рукописные разделы (эта
команда их не трогает), автосекция (её строит ЭТА команда) и тест-страж
(problems/tests/test_design_canon.py::Calc2MapMatchesCodeTests или соседний
файл в calc2/tests/ — см. итоговый отчёт сессии), который не даёт автосекции
протухнуть.

Список файлов калькулятора НЕ хардкодится именами. Команда идёт по коду ровно
тем же путём, каким шёл бы человек: calc2/urls.py → calc2/views.py (оттуда
имя шаблона) → сам шаблон → все {% static 'calc2/...' %} ссылки в нём. Это
и есть определение «файл участвует в странице /calc2/».

Запуск:
    ./venv/bin/python manage.py calc2_map
"""

import re
import subprocess
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

START_MARK = '<!-- AUTO:START -->'
END_MARK = '<!-- AUTO:END -->'

# Маркер считается маркером, только когда он стоит ОДИН на всей строке — а не
# когда автосекция сама упоминает его в тексте (например, в пояснении «не
# редактировать руками»). Наивный str.split по подстроке однажды уже резал
# файл не по настоящему маркеру, а по такому упоминанию, и автосекция
# задваивалась с каждым запуском команды.
START_LINE_RE = re.compile(r'^' + re.escape(START_MARK) + r'\s*$', re.MULTILINE)
END_LINE_RE = re.compile(r'^' + re.escape(END_MARK) + r'\s*$', re.MULTILINE)

MAP_PATH = Path(settings.BASE_DIR) / 'docs' / 'calc2' / 'CALC2_MAP.md'
APP_DIR = Path(settings.BASE_DIR) / 'calc2'

STATIC_TAG_RE = re.compile(r"\{%\s*static\s+'(calc2/[^']+)'\s*%\}")
TEMPLATE_NAME_RE = re.compile(r"template_name\s*=\s*['\"]([^'\"]+)['\"]")

# Четыре формы объявления верхнего уровня, которые нас интересуют. «Верхний
# уровень» здесь — колонка 0 (function/const-стрелка/class) либо один-два
# уровня отступа (свойство-функция внутри объектного литерала верхнего
# уровня, вроде записи в реестре). const-объекты с данными (CONFIG, STATE,
# FS) НЕ функции и в индекс не идут — по строке требуется совпадение с «=>»
# на той же строке, что и «const».
FUNC_DECL_RE = re.compile(r'^function\s+([A-Za-z_$][\w$]*)\s*\(', re.MULTILINE)
CONST_ARROW_RE = re.compile(
    r'^const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^\n]*=>', re.MULTILINE
)
CLASS_DECL_RE = re.compile(r'^class\s+([A-Za-z_$][\w$]*)', re.MULTILINE)
PROP_FUNC_RE = re.compile(
    r'^ {2,4}([A-Za-z_$][\w$]*)\s*:\s*function\s*\(', re.MULTILINE
)


def discover_core_files():
    """Route → view → template → статика. Возвращает список Path, в порядке:
    urls.py, views.py, шаблон, статические файлы (в порядке ссылок в шаблоне).
    """
    urls_path = APP_DIR / 'urls.py'
    views_path = APP_DIR / 'views.py'
    if not urls_path.exists():
        raise CommandError('calc2/urls.py не найден — приложение calc2 переехало?')
    if not views_path.exists():
        raise CommandError('calc2/views.py не найден — приложение calc2 переехало?')

    views_src = views_path.read_text(encoding='utf-8')
    m = TEMPLATE_NAME_RE.search(views_src)
    if not m:
        raise CommandError('template_name не найден в calc2/views.py — разбор шаблона невозможен')
    template_rel = m.group(1)
    template_path = APP_DIR / 'templates' / template_rel
    if not template_path.exists():
        raise CommandError(f'Шаблон {template_path} не найден (указан в views.py как {template_rel!r})')

    template_src = template_path.read_text(encoding='utf-8')
    # dict.fromkeys вместо set — сохраняет порядок первого появления в шаблоне.
    static_rel_paths = list(dict.fromkeys(STATIC_TAG_RE.findall(template_src)))
    if not static_rel_paths:
        raise CommandError('В шаблоне не нашлось ни одной ссылки {% static \'calc2/...\' %}')
    static_paths = [APP_DIR / 'static' / rel for rel in static_rel_paths]
    missing = [p for p in static_paths if not p.exists()]
    if missing:
        raise CommandError(
            'В шаблоне указаны статические файлы, которых нет на диске: '
            + ', '.join(str(p) for p in missing)
        )

    return [urls_path, views_path, template_path] + static_paths


def file_kind(path: Path) -> str:
    if path.suffix == '.html':
        return 'шаблон'
    if path.suffix == '.css':
        return 'CSS'
    if path.suffix == '.js':
        return 'JS'
    if path.suffix == '.py':
        return 'python'
    return path.suffix.lstrip('.') or '?'


def rel(path: Path) -> str:
    return str(path.relative_to(settings.BASE_DIR)).replace('\\', '/')


def function_index(path: Path):
    """Объявления верхнего уровня в JS-файле: [(строка, имя), ...] по строке."""
    src = path.read_text(encoding='utf-8')
    found = []
    for regex in (FUNC_DECL_RE, CONST_ARROW_RE, CLASS_DECL_RE, PROP_FUNC_RE):
        for m in regex.finditer(src):
            line_no = src.count('\n', 0, m.start()) + 1
            found.append((line_no, m.group(1)))
    found.sort(key=lambda pair: pair[0])
    return found


def git_short_head():
    try:
        out = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            capture_output=True, text=True, cwd=settings.BASE_DIR, timeout=10,
        )
        return out.stdout.strip() or '(неизвестно)'
    except Exception:
        return '(неизвестно)'


def build_auto_section():
    from datetime import date

    core_files = discover_core_files()

    rows = []
    total_lines = 0
    total_bytes = 0
    for p in core_files:
        text = p.read_bytes()
        n_lines = text.count(b'\n') + (0 if text.endswith(b'\n') or not text else 1)
        n_bytes = len(text)
        total_lines += n_lines
        total_bytes += n_bytes
        rows.append((rel(p), n_lines, round(n_bytes / 1024, 1), file_kind(p)))

    lines = [START_MARK, '']
    lines.append(f'*Автоматически собрано командой `manage.py calc2_map`. '
                 f'Дата: {date.today().isoformat()}. HEAD: `{git_short_head()}`. '
                 f'Не редактировать руками — вся эта часть файла, от отметки '
                 f'начала автосекции и до отметки её конца, перезаписывается '
                 f'заново при каждом запуске команды.*')
    lines.append('')
    lines.append('### Файлы (маршрут → представление → шаблон → статика)')
    lines.append('')
    lines.append('| Путь | Строк | КБ | Тип |')
    lines.append('|---|---:|---:|---|')
    for path_str, n_lines, kb, kind in rows:
        lines.append(f'| `{path_str}` | {n_lines} | {kb} | {kind} |')
    lines.append('')
    lines.append(f'**Итого: {len(rows)} файлов, {total_lines} строк, '
                  f'{round(total_bytes / 1024, 1)} КБ.**')
    lines.append('')

    lines.append('### Индекс функций (объявления верхнего уровня, по возрастанию строки)')
    lines.append('')
    total_funcs = 0
    for p in core_files:
        if p.suffix != '.js':
            continue
        idx = function_index(p)
        total_funcs += len(idx)
        lines.append(f'#### `{rel(p)}`')
        lines.append('')
        if not idx:
            lines.append('*(объявлений верхнего уровня не найдено)*')
        else:
            for line_no, name in idx:
                lines.append(f'- строка {line_no} — `{name}`')
        lines.append('')
    lines.append(f'**Итого функций в индексе: {total_funcs}.**')
    lines.append('')
    lines.append(END_MARK)
    return '\n'.join(lines) + '\n'


DEFAULT_SKELETON = """# Карта модулей calc2

<!-- AUTO:START -->
<!-- AUTO:END -->
"""


class Command(BaseCommand):
    help = 'Пересобирает автосекцию docs/calc2/CALC2_MAP.md (карта модулей calc2)'

    def handle(self, *args, **options):
        MAP_PATH.parent.mkdir(parents=True, exist_ok=True)

        if MAP_PATH.exists():
            content = MAP_PATH.read_text(encoding='utf-8')
        else:
            content = DEFAULT_SKELETON

        start_m = START_LINE_RE.search(content)
        end_m = END_LINE_RE.search(content)
        if not start_m or not end_m or end_m.start() < start_m.end():
            raise CommandError(
                f'В {MAP_PATH} нет маркеров {START_MARK} / {END_MARK} каждый на '
                'своей отдельной строке (в правильном порядке) — файл повреждён, '
                'автосекцию вписать некуда'
            )

        before = content[:start_m.start()]
        after = content[end_m.end():]
        new_content = before + build_auto_section() + after

        with open(MAP_PATH, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(new_content)

        self.stdout.write(self.style.SUCCESS(f'Автосекция карты обновлена: {MAP_PATH}'))
