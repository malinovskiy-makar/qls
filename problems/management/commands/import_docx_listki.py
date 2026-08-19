"""
import_docx_listki — импорт DOCX-листков задач по экономике
===========================================================
Источник: materials/Archive 6/Archive 5/Archive 3/drive-download-…-001 copy/
Структура папки: подпапки по темам (АИ, КПВ, Монополия, …)

Конвертация: pandoc → LaTeX, затем разбивка по маркерам задач.
Четыре стратегии разбивки (применяются по приоритету):
  1. \\textbf{Задача N} — жирные маркеры
  2. ^Задача N.      — обычные маркеры в начале строки
  3. \\item           — элементы верхнего уровня enumerate (арабская нумерация)
  4. ^N. текст       — нумерованные абзацы
  fallback: разбивка по двойным переносам (блоки > 100 символов)

Запуск:
  python manage.py import_docx_listki                          # полный импорт
  python manage.py import_docx_listki --dry-run                # без сохранения
  python manage.py import_docx_listki --file путь/к/файлу.docx # один файл
"""

import hashlib
import re
from pathlib import Path

import pypandoc
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from problems.models import Job, Problem, Source, SourceReference, Topic


# ─────────────────────────────────────────────────────────────────
# Константы
# ─────────────────────────────────────────────────────────────────

BASE_DIR = (
    Path(settings.BASE_DIR)
    / 'materials'
    / 'Archive 6'
    / 'Archive 5'
    / 'Archive 3'
    / 'drive-download-20260513T172045Z-3-001 copy'
)

SOURCE_NAME = 'Листки задач (Overleaf/DOCX)'

FOLDER_TOPIC_MAP = {
    'АИ':          'Альтернативные издержки',
    'КПВ':         'Кривая производственных возможностей',
    'Математика':  'Математика',
    'Монополия':   'Монополия',
    'Неравенство': 'Неравенство в распределении доходов',
    'Оптимизация': 'Оптимизация',
    'Потребитель': 'Теория потребительского поведения',
    'Провалы':     'Провалы рынка',
    'Производство':'Производство и издержки',
    'Рынок':       'Рынок (спрос, предложение, равновесие)',
    'Рынок труда': 'Рынок труда',
    'СК':          'Совершенная конкуренция',
    'Торговля':    'Международная торговля',
    'Финансы':     'Финансы',
    'Формализация':'Формализация',
    'Эластичность':'Эластичность',
}

# Транслитерация для slug (то же, что в import_tex)
_TRANSLIT = {
    'а': 'a',  'б': 'b',  'в': 'v',  'г': 'g',  'д': 'd',  'е': 'e',
    'ё': 'e',  'ж': 'zh', 'з': 'z',  'и': 'i',  'й': 'y',  'к': 'k',
    'л': 'l',  'м': 'm',  'н': 'n',  'о': 'o',  'п': 'p',  'р': 'r',
    'с': 's',  'т': 't',  'у': 'u',  'ф': 'f',  'х': 'h',  'ц': 'ts',
    'ч': 'ch', 'ш': 'sh', 'щ': 'sch','ъ': '',   'ы': 'y',  'ь': '',
    'э': 'e',  'ю': 'yu', 'я': 'ya', ' ': '-',  '+': '-',
}


# ─────────────────────────────────────────────────────────────────
# Вспомогательные функции
# ─────────────────────────────────────────────────────────────────

def get_topic_name(filepath: Path) -> str:
    """Определяет тему по имени верхней подпапки внутри BASE_DIR."""
    try:
        rel = filepath.relative_to(BASE_DIR)
        if len(rel.parts) < 2:
            # Файл прямо в корне (например, Шпицрутен. Часть 2.docx)
            return 'Без темы'
        top_folder = rel.parts[0]
        return FOLDER_TOPIC_MAP.get(top_folder, top_folder)
    except ValueError:
        return 'Без темы'


def make_topic_slug(name: str, existing_slugs: set) -> str:
    """Транслитерирует название темы → slug; добавляет суффикс при коллизии."""
    lowered = name.lower()
    chars = [_TRANSLIT.get(ch, ch) for ch in lowered]
    slug = re.sub(r'[^a-z0-9-]', '', ''.join(chars))[:110] or 'topic'
    base = slug
    n = 2
    while slug in existing_slugs:
        slug = f'{base}-{n}'
        n += 1
    return slug


def clean_latex(text: str) -> str:
    """
    Убирает структурные LaTeX-команды, сохраняет текст и математику.
    Формулы \\(…\\) и \\[…\\] остаются нетронутыми.
    """
    # Таблицы → метка
    text = re.sub(
        r'\{\\def\\LTcaptype[^}]*\}', '', text, flags=re.DOTALL
    )
    text = re.sub(
        r'\\begin\{longtable\}.*?\\end\{longtable\}',
        '[таблица]', text, flags=re.DOTALL
    )
    text = re.sub(
        r'\\begin\{tabular\}.*?\\end\{tabular\}',
        '[таблица]', text, flags=re.DOTALL
    )
    # Картинки → метка
    text = re.sub(r'\\includegraphics(?:\[[^\]]*\])?\{[^}]*\}', '[рисунок]', text)
    # minipage — убираем окружение, содержимое сохраняем
    text = re.sub(r'\\begin\{minipage\}[^\n]*\n', '', text)
    text = re.sub(r'\\end\{minipage\}', '', text)
    # Списки: убираем окружения, \item → новая строка
    text = re.sub(r'\\begin\{(enumerate|itemize)\}\n?', '', text)
    text = re.sub(r'\\end\{(enumerate|itemize)\}\n?', '', text)
    text = re.sub(r'\\def\\label\w+\{[^}]*\}\n?', '', text)
    text = re.sub(r'\\setcounter\{[^}]+\}\{[^}]+\}\n?', '', text)
    text = re.sub(r'\\begin\{quote\}\n?', '', text)
    text = re.sub(r'\\end\{quote\}\n?', '', text)
    text = re.sub(r'\\item\s*', '\n', text)
    # Форматирование текста — убираем команду, оставляем содержимое
    for cmd in ('textbf', 'emph', 'textit', 'underline', 'ul', 'textnormal'):
        text = re.sub(r'\\' + cmd + r'\{([^}]*)\}', r'\1', text)
    # Артефакты таблиц
    for pat in (
        r'\\toprule', r'\\midrule', r'\\bottomrule',
        r'\\endhead', r'\\endlastfoot',
        r'\\noalign\{[^}]*\}', r'\\raggedright', r'\\arraybackslash',
        r'\\begin\{@\{\}\}', r'@\{\}',
    ):
        text = re.sub(pat, '', text)
    # Типографика
    text = text.replace('~', ' ')   # неразрывный пробел
    text = text.replace('---', '—').replace('--', '–')
    # Убираем лишние пустые строки
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def extract_top_level_items(latex: str) -> list:
    """
    Извлекает элементы верхнего уровня из enumerate-блоков
    с арабской нумерацией (\\arabic) — это задачи.
    Блоки с буквенной нумерацией (\\alph) — подпункты, пропускаются.
    """
    items = []
    depth = 0
    current_item = []
    is_arabic = False  # тип нумерации текущего блока

    for line in latex.split('\n'):
        stripped = line.strip()

        if re.match(r'\\begin\{(enumerate|itemize)\}', stripped):
            depth += 1
            if depth > 1:
                current_item.append(line)

        elif re.match(r'\\end\{(enumerate|itemize)\}', stripped):
            if depth == 1:
                if current_item and is_arabic:
                    items.append('\n'.join(current_item).strip())
                current_item = []
                is_arabic = False
            else:
                current_item.append(line)
            depth = max(0, depth - 1)

        elif depth == 1 and re.match(r'\\def\\labelenumi\b', stripped):
            # Определяем тип нумерации для этого блока
            is_arabic = r'\arabic' in stripped

        elif depth == 1 and re.match(r'\\item\b', stripped):
            if current_item and is_arabic:
                items.append('\n'.join(current_item).strip())
            current_item = [line]

        elif depth >= 1:
            # Пропускаем служебные строки верхнего уровня
            if depth == 1 and re.match(r'\\(setcounter|def\\)\b', stripped):
                pass
            else:
                current_item.append(line)

        # depth == 0: межблочный текст — пропускаем

    if current_item and is_arabic:
        items.append('\n'.join(current_item).strip())

    return [i for i in items if len(i) > 20]


def split_into_problems(latex: str):
    """
    Разбивает LaTeX-текст на задачи.
    Возвращает (метод: str, куски: list[str]).

    Приоритет стратегий:
      1. \\textbf{Задача N} / \\textbf{Задание N} — явные жирные маркеры
      2. ^Задача N. / ^Задание N. — обычные маркеры в начале строки
      3. \\item верхнего уровня enumerate (арабская нумерация)
      4. ^N. Текст — нумерованные абзацы
      fallback — двойные переносы строк
    """
    # ── 1. Жирные маркеры ──────────────────────────────────────────
    bold_hits = re.findall(
        r'\\textbf\{(?:Задача|Задание)\s+\d+', latex
    )
    if len(bold_hits) >= 2:
        parts = re.split(
            r'(?=\\textbf\{(?:Задача|Задание)\s+\d+)', latex
        )
        good = [p.strip() for p in parts if len(p.strip()) > 50]
        if good:
            return 'textbf-маркер', good

    # ── 2. Обычные маркеры «Задача N.» в начале строки ─────────────
    plain_hits = re.findall(
        r'^(?:Задача|Задание)\s+\d+[\.\s]', latex, re.MULTILINE
    )
    if len(plain_hits) >= 2:
        parts = re.split(
            r'(?=^(?:Задача|Задание)\s+\d+[\.\s])',
            latex, flags=re.MULTILINE
        )
        good = [p.strip() for p in parts if len(p.strip()) > 50]
        if good:
            return 'задача-маркер', good

    # ── 3. Элементы верхнего уровня enumerate ──────────────────────
    items = extract_top_level_items(latex)
    if len(items) >= 2:
        return 'enumerate-item', items

    # ── 4. Нумерованные абзацы «N. Текст» ──────────────────────────
    num_hits = re.findall(r'^\d+\.\s+\S', latex, re.MULTILINE)
    if len(num_hits) >= 2:
        parts = re.split(
            r'(?=^\d+\.\s+\S)', latex, flags=re.MULTILINE
        )
        good = [p.strip() for p in parts if len(p.strip()) > 50]
        if good:
            return 'нумерованный-абзац', good

    # ── Fallback: двойные переносы ──────────────────────────────────
    parts = [p.strip() for p in re.split(r'\n\n+', latex) if len(p.strip()) > 100]
    return 'двойной-перенос', parts


# ─────────────────────────────────────────────────────────────────
# Нормализация (сессия B, 2026-06-12): артефакты pandoc и Unicode в формулах.
# Применяется ПОСЛЕ clean_latex и ДО вычисления хэша — чтобы дедупликация
# не зависела от вида тире/пробелов.
# ─────────────────────────────────────────────────────────────────

_NBSP_RE = re.compile('[    ]')          # неразрывные пробелы
_MATH_SPAN_RE = re.compile(r'\\\((.+?)\\\)|\\\[(.+?)\\\]', re.DOTALL)


def _normalize_math_body(body: str) -> str:
    """Внутри \\(…\\): тире любых видов → минус, × → \\times (KaTeX
    не понимает – и — внутри формул — именно это «рвало» рендер)."""
    body = re.sub('[–—−]', '-', body)
    body = body.replace('×', r'\times ')
    return body


def normalize_pandoc(text: str) -> str:
    """Чистка артефактов pandoc + нормализация Unicode внутри формул."""
    text = _NBSP_RE.sub(' ', text)
    text = text.replace('−', '-')           # − (минус) и в прозе
    text = text.replace('\\-', '')               # discretionary hyphen pandoc
    text = text.replace('\\protect', '')
    text = re.sub(r'\\texorpdfstring\{([^{}]*)\}\{[^{}]*\}', r'\1', text)
    text = re.sub(r'\\tightlist\n?', '', text)

    def _math(m):
        if m.group(1) is not None:
            return '\\(' + _normalize_math_body(m.group(1)) + '\\)'
        return '\\[' + _normalize_math_body(m.group(2)) + '\\]'
    text = _MATH_SPAN_RE.sub(_math, text)

    # Хвосты вложенных longtable, которые не взял clean_latex
    text = re.sub(r'(?m)^\s*%[^\n]*$', '', text)             # комментарии pandoc
    text = re.sub(r'\\(?:begin|end)\{longtable\}[^\n]*', '[таблица]', text)
    text = re.sub(r'(?m)^[ \t{}]+$', '', text)               # строки из скобок
    text = re.sub(r' *\\\\ *(?=\n|$)', '', text)             # \\ в конце строк
    text = re.sub(r'(?:\[таблица\]\s*){2,}', '[таблица] ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


_MARKER_START_RE = re.compile(r'^(?:Задача|Задание)\s*№?\s*\d+[\.\:]?\s*',
                              re.IGNORECASE)
_MARKER_LINE_RE = re.compile(r'(?m)^(?:Задача|Задание)\s*№?\s*\d+[\.\:]?\s*$')
_PLACEHOLDER_RE = re.compile(r'\[(?:рисунок|таблица)\]')


def strip_leading_marker(text: str) -> str:
    """Срезает маркер «Задача N.» с начала условия (он не часть текста)."""
    return _MARKER_START_RE.sub('', text, count=1).strip()


def is_junk_chunk(stmt: str) -> bool:
    """Кусок без содержимого (только маркеры/картинки) или блок ответов."""
    if re.match(r'^\s*Ответы?\b', stmt):
        return True
    gist = _PLACEHOLDER_RE.sub('', stmt)
    gist = _MARKER_LINE_RE.sub('', gist)
    return len(gist.strip()) < 30


def canonical_for_hash(text: str) -> str:
    """Каноническая форма для хэша: все тире → -, схлопнутые пробелы."""
    t = re.sub('[–—−]', '-', text)
    t = re.sub(r'\s+', ' ', t)
    return t.strip()


def make_title(statement: str) -> str:
    """Заголовок — первые ≤80 символов первой строки без маркера задачи."""
    first = statement.split('\n')[0].strip()
    # Убираем маркер «Задача N.» / «Задание N.» с начала
    first = re.sub(r'^(?:Задача|Задание)\s+\d+[\.\:]\s*', '', first)
    if len(first) > 80:
        cut = first[:80]
        sp = cut.rfind(' ')
        first = (cut[:sp] if sp > 40 else cut) + '…'
    return first or 'Задача'


def content_hash(text: str) -> str:
    return hashlib.md5(text.strip().encode('utf-8'), usedforsecurity=False).hexdigest()


# ─────────────────────────────────────────────────────────────────
# Команда
# ─────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = 'Импорт DOCX-листков задач (Листки задач (Overleaf/DOCX))'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Показать что будет импортировано без сохранения в БД',
        )
        parser.add_argument(
            '--file', type=str, default=None,
            help='Обработать только указанный файл (можно передать несколько через запятую)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        single_file = options['file']

        if dry_run:
            self.stdout.write(self.style.WARNING(
                '══════════════════════════════════════════════\n'
                '  DRY-RUN: изменений в базе данных не будет\n'
                '══════════════════════════════════════════════'
            ))

        # ── Список файлов ──────────────────────────────────────────
        if single_file:
            # Можно передать несколько путей через запятую
            # resolve() превращает относительный путь в абсолютный
            files = [Path(p.strip()).resolve() for p in single_file.split(',')]
        else:
            files = sorted(
                f for f in BASE_DIR.rglob('*.docx')
                if not f.name.startswith('~$')
            )
            # Добавляем .doc файлы (если есть)
            files += sorted(
                f for f in BASE_DIR.rglob('*.doc')
                if not f.name.startswith('~$')
            )

        self.stdout.write(f'Файлов для обработки: {len(files)}')

        # ── Инициализация БД (только для полного импорта) ──────────
        if not dry_run:
            source, src_created = Source.objects.get_or_create(
                name=SOURCE_NAME,
                defaults={'kind': 'листки задач'},
            )
            self.stdout.write(
                f'Источник «{SOURCE_NAME}» '
                f'{"создан" if src_created else "найден"}: #{source.pk}'
            )
            job = Job.objects.create(
                kind=Job.Kind.IMPORT,
                status=Job.Status.RUNNING,
                params={'source': SOURCE_NAME, 'files': len(files)},
                started_by=None,
            )
            self.stdout.write(f'Job #{job.pk} запущен')

            # Кэш тем (чтобы не делать N запросов к БД)
            topic_cache = {t.name: t for t in Topic.objects.all()}
            existing_slugs = {t.slug for t in Topic.objects.all()}
        else:
            source = None
            job = None
            topic_cache = {}
            existing_slugs = set()

        total_created = 0
        total_skipped = 0
        total_errors = 0

        # ── Обработка файлов ───────────────────────────────────────
        for i, filepath in enumerate(files):
            try:
                rel = filepath.relative_to(BASE_DIR)
            except ValueError:
                rel = filepath  # файл вне BASE_DIR (при --file с абс. путём)

            # Конвертация pandoc → LaTeX
            try:
                latex = pypandoc.convert_file(
                    str(filepath),
                    'latex',
                    extra_args=['--wrap=none'],
                )
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f'  ✗ Конвертация не удалась ({rel.name}): {e}'
                ))
                total_errors += 1
                continue

            # Определяем тему и разбиваем на задачи
            topic_name = get_topic_name(filepath)
            method, raw_parts = split_into_problems(latex)

            # ── DRY-RUN: вывод ────────────────────────────────────
            if dry_run:
                self.stdout.write(f'\n{"─" * 60}')
                self.stdout.write(f'Файл : {rel}')
                self.stdout.write(
                    f'Тема : {topic_name}  │  '
                    f'Метод: {method}  │  '
                    f'Задач: {len(raw_parts)}'
                )
                for j, raw in enumerate(raw_parts[:6], 1):
                    stmt = strip_leading_marker(
                        normalize_pandoc(clean_latex(raw).strip()))
                    preview = stmt[:150].replace('\n', ' ')
                    suffix = '…' if len(stmt) > 150 else ''
                    self.stdout.write(f'  [{j}] {preview}{suffix}')
                if len(raw_parts) > 6:
                    self.stdout.write(
                        f'       … ещё {len(raw_parts) - 6} задач'
                    )
                continue

            # ── Сохранение в БД ───────────────────────────────────
            # Получаем/создаём тему
            if topic_name not in topic_cache:
                slug = make_topic_slug(topic_name, existing_slugs)
                existing_slugs.add(slug)
                topic_obj = Topic.objects.get_or_create(
                    name=topic_name,
                    defaults={'slug': slug},
                )[0]
                topic_cache[topic_name] = topic_obj
            topic_obj = topic_cache[topic_name]

            file_created = 0
            for raw in raw_parts:
                # legacy-пайплайн (как в первом импорте) — только для хэша,
                # чтобы не потерять кросс-источниковую дедупликацию (#13/#14)
                legacy_stmt = clean_latex(raw).strip()
                stmt = strip_leading_marker(normalize_pandoc(legacy_stmt))
                if len(stmt) < 30 or is_junk_chunk(stmt):
                    continue
                chash = content_hash(canonical_for_hash(stmt))
                legacy_hash = content_hash(legacy_stmt)
                if Problem.objects.filter(
                        content_hash__in=[chash, legacy_hash]).exists():
                    total_skipped += 1
                    continue
                title = make_title(stmt)
                try:
                    with transaction.atomic():
                        p = Problem.objects.create(
                            title=title[:200],
                            statement=stmt,
                            status=Problem.Status.DRAFT,
                            content_hash=chash,
                        )
                        p.topics.add(topic_obj)
                        SourceReference.objects.create(
                            problem=p,
                            source=source,
                            note=str(rel),
                        )
                    total_created += 1
                    file_created += 1
                except Exception as e:
                    total_errors += 1
                    self.stdout.write(self.style.ERROR(
                        f'  ✗ Ошибка сохранения ({rel.name}): {e}'
                    ))

            if file_created:
                self.stdout.write(
                    f'  ✓ {rel.name[:50]:50s} → {file_created} задач ({topic_name})'
                )

            # Обновляем прогресс каждые 10 файлов
            if job and (i + 1) % 10 == 0:
                job.progress = int((i + 1) / len(files) * 100)
                job.save(update_fields=['progress'])

        # ── Итог ──────────────────────────────────────────────────
        if job:
            job.status = Job.Status.DONE
            job.result = {
                'created': total_created,
                'skipped': total_skipped,
                'errors': total_errors,
            }
            job.progress = 100
            job.save()

        self.stdout.write(self.style.SUCCESS(
            f'\n✓ Готово: создано {total_created}, '
            f'пропущено {total_skipped}, '
            f'ошибок {total_errors}'
        ))
