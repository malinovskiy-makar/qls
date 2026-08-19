"""
Management command: import_tex

Импортирует задачи из LaTeX файлов Overleaf-проектов ЛШ Олмат 2025.
Дедупликация по MD5-хэшу условия (поле content_hash на модели Problem).
Статус всех задач — draft (авторские материалы, преподаватель решает сам).

Запуск:
    python manage.py import_tex
    python manage.py import_tex --dir /path/to/overleaf
    python manage.py import_tex --dry-run   # только считает, не пишет
"""

import hashlib
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from problems.models import Job, Problem, ProblemPart, Source, SourceReference, Topic


DEFAULT_DIR = (
    Path(settings.BASE_DIR)
    / 'materials'
    / 'Archive 6'
    / 'Archive 5'
    / 'Archive 3'
    / 'Archive 2'
    / 'Overleaf Projects (41 items)'
)

BATCH_SIZE = 50

# Метки подпунктов — русский алфавит
PART_LABELS = list('абвгдежзиклмнопрстуфхцчшщ')

# \headic{}{дата}{Тема}{Автор}
_HEADIC_RE = re.compile(r'\\headic\{[^}]*\}\{[^}]*\}\{([^}]*)\}\{([^}]*)\}')

# \problem или \problem[n]
_PROBLEM_RE = re.compile(r'\\problem(?:\[\d+\])?')

# \Subitem, \subitem, \Rsubitem, \rsubitem
_SUBITEM_RE = re.compile(r'\\[Rr]?[Ss]ubitem\b')

# Транслит для slug тем
_TRANSLIT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e',
    'ё': 'e', 'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k',
    'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
    'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts',
    'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '',
    'э': 'e', 'ю': 'yu', 'я': 'ya', ' ': '-', '+': '-',
}

# Форматирующие команды — убираем обёртку, оставляем содержимое
_FORMAT_CMDS = (
    'textbf', 'emph', 'underline', 'textit', 'textrm',
    'texttt', 'textsc', 'textmd', 'textup', 'text',
)


# ---------------------------------------------------------------------------
# LaTeX-утилиты
# ---------------------------------------------------------------------------

def _strip_wrapper(text: str, cmd: str) -> str:
    """
    Заменяет \\cmd{content} → content по всему тексту.
    Корректно обрабатывает вложенные скобки.
    """
    result = []
    i = 0
    pattern = '\\' + cmd + '{'
    while i < len(text):
        idx = text.find(pattern, i)
        if idx == -1:
            result.append(text[i:])
            break
        result.append(text[i:idx])
        # j — позиция открывающей '{'; start — первый символ содержимого
        j = idx + len(pattern) - 1
        start = j + 1
        depth = 0
        while j < len(text):
            if text[j] == '{':
                depth += 1
            elif text[j] == '}':
                depth -= 1
                if depth == 0:
                    result.append(text[start:j])
                    i = j + 1
                    break
            j += 1
        else:
            # Незакрытая скобка — оставляем как есть
            result.append(text[idx:])
            break
    return ''.join(result)


def clean_latex(text: str) -> str:
    """
    Убирает форматирующие LaTeX-команды, оставляет математику.

    Удаляет обёртки: \\textbf{}, \\emph{}, \\text{} и т.д.
    Удаляет служебные команды: \\includegraphics, \\hspace, \\label…
    Оставляет: $...$, \\(...\\), \\[...\\], \\frac, \\begin{tabular}...
    """
    # 1. Снимаем форматирующие обёртки (содержимое остаётся)
    for cmd in _FORMAT_CMDS:
        text = _strip_wrapper(text, cmd)

    # 2. Удаляем структурные команды с аргументами полностью
    text = re.sub(r'\\includegraphics(?:\[[^\]]*\])?\{[^}]*\}', '', text)
    text = re.sub(r'\\hspace\*?\{[^}]*\}', '', text)
    text = re.sub(r'\\vspace\*?\{[^}]*\}', '', text)
    text = re.sub(r'\\setlength\{[^}]*\}\{[^}]*\}', '', text)
    text = re.sub(r'\\label\{[^}]*\}', '', text)
    text = re.sub(r'\\ref\{[^}]*\}', '', text)
    text = re.sub(r'\\def\\[A-Za-z]+\{[^}]*\}', '', text)

    # 3. Одиночные команды без аргументов — просто удалить
    text = re.sub(
        r'\\(noindent|centering|hrulefill|displaystyle|heart'
        r'|quad|qquad|smallskip|medskip|bigskip|newline'
        r'|clearpage|newpage|displaypage)\b',
        '', text,
    )
    # \\ (перенос строки в LaTeX) → реальный перенос
    text = re.sub(r'\\\\', '\n', text)

    # 4. Снимаем безобидные обёртки окружений (оставляем содержимое)
    text = re.sub(r'\\begin\{center\}', '', text)
    text = re.sub(r'\\end\{center\}', '', text)
    text = re.sub(r'\\begin\{document\}', '', text)
    text = re.sub(r'\\end\{document\}', '', text)

    # 5. Нормализуем пробелы
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)

    return text.strip()


def extract_title(statement: str) -> str:
    """Первые 80 символов условия до первой точки или переноса строки."""
    end = len(statement)
    for i, ch in enumerate(statement):
        if ch in ('.', '\n') and i > 5:
            end = i
            break
    return statement[:end][:80].strip()


def parse_headic(content: str):
    """Возвращает (topic_name, author_name) из \\headic{}{}{}{}."""
    m = _HEADIC_RE.search(content)
    if not m:
        return '', ''
    topic = m.group(1).strip()
    author = m.group(2).strip()
    # Заглушки из шаблона — не берём
    if topic.lower() in ('тема', ''):
        topic = ''
    if author.lower() in ('автор', ''):
        author = ''
    return topic, author


def parse_problems_from_tex(content: str):
    """
    Разбивает файл по \\problem — каждый кусок до следующего \\problem.
    Внутри каждого куска разбивает по \\Subitem / \\subitem / \\Rsubitem.

    Возвращает список (main_text_raw, [subitem_text_raw, ...]).
    """
    chunks = _PROBLEM_RE.split(content)
    result = []
    for chunk in chunks[1:]:   # chunks[0] — шапка файла до первого \problem
        parts = _SUBITEM_RE.split(chunk)
        main_text = parts[0]
        subitems = parts[1:]
        result.append((main_text, subitems))
    return result


def _make_topic_slug(name: str) -> str:
    """Транслитерирует название темы в ASCII slug."""
    lowered = name.lower()
    chars = []
    for ch in lowered:
        chars.append(_TRANSLIT.get(ch, ch))
    slug = ''.join(c for c in ''.join(chars) if c.isalnum() or c == '-')
    return slug[:110] or 'topic'


# ---------------------------------------------------------------------------
# Команда
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = 'Импортирует задачи из LaTeX файлов Overleaf-проектов ЛШ Олмат 2025'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dir', type=str, default=str(DEFAULT_DIR),
            help='Путь к папке с .tex файлами',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Только считать, ничего не писать в базу',
        )

    def handle(self, *args, **options):
        tex_dir = Path(options['dir'])
        dry_run = options['dry_run']

        if not tex_dir.exists():
            self.stderr.write(self.style.ERROR(f'Папка не найдена: {tex_dir}'))
            return

        # ── Сбор .tex файлов ─────────────────────────────────────────────────
        all_tex = list(tex_dir.rglob('*.tex'))

        def _should_skip(p: Path) -> bool:
            if p.suffix == '.sty':
                return True
            if p.name.lower() == 'main.tex':
                return True
            if p.stat().st_size < 500:
                return True
            return False

        tex_files = [f for f in all_tex if not _should_skip(f)]
        self.stdout.write(
            f'Найдено .tex файлов: {len(all_tex)}, после фильтра: {len(tex_files)}'
        )

        if dry_run:
            self.stdout.write('(dry-run: в базу ничего не пишем)')

        # ── Источник ─────────────────────────────────────────────────────────
        source, created_src = Source.objects.get_or_create(
            name='ЛШ Олмат 2025 (Overleaf)',
            defaults={
                'kind': 'авторские материалы',
                'note': 'LaTeX файлы из Overleaf-проектов летней школы ЛШ Олмат 2025.',
            },
        )
        self.stdout.write(
            f'Источник «{source.name}» '
            f'{"создан" if created_src else "найден"}: #{source.pk}'
        )

        # ── Job ──────────────────────────────────────────────────────────────
        job = Job.objects.create(
            kind=Job.Kind.IMPORT,
            status=Job.Status.RUNNING,
            params={'dir': str(tex_dir), 'dry_run': dry_run},
        )
        self.stdout.write(f'Job #{job.pk} создан')

        # ── Кэши ─────────────────────────────────────────────────────────────
        existing_hashes: set = set(
            Problem.objects.exclude(content_hash='').values_list('content_hash', flat=True)
        )
        topic_cache: dict = {t.name: t for t in Topic.objects.all()}

        # ── Шаг 1: парсим все файлы, собираем записи ─────────────────────────
        all_records = []
        files_with_problems = 0

        for tex_path in tex_files:
            try:
                with open(tex_path, encoding='utf-8', errors='replace') as fh:
                    content = fh.read()

                if '\\problem' not in content:
                    continue

                topic_name, author = parse_headic(content)

                # Тема: найти или создать (только если не dry-run)
                topic_obj = None
                if topic_name:
                    if topic_name in topic_cache:
                        topic_obj = topic_cache[topic_name]
                    elif not dry_run:
                        base_slug = _make_topic_slug(topic_name)
                        slug = base_slug
                        counter = 1
                        while Topic.objects.filter(slug=slug).exists():
                            slug = f'{base_slug}-{counter}'
                            counter += 1
                        topic_obj = Topic.objects.create(
                            name=topic_name, slug=slug
                        )
                        topic_cache[topic_name] = topic_obj

                source_note = tex_path.name
                if author:
                    source_note += f' (автор: {author})'

                problems_raw = parse_problems_from_tex(content)
                files_with_problems += 1

                for main_raw, subitems_raw in problems_raw:
                    stmt = clean_latex(main_raw)
                    if not stmt:
                        continue

                    title = extract_title(stmt)
                    stmt_hash = hashlib.md5(stmt.encode(), usedforsecurity=False).hexdigest()
                    parts = [
                        clean_latex(s) for s in subitems_raw
                        if clean_latex(s)
                    ]

                    all_records.append({
                        'title': title,
                        'statement': stmt,
                        'content_hash': stmt_hash,
                        'topic': topic_obj,
                        'source_note': source_note[:299],
                        'parts': parts,
                    })

            except Exception as exc:
                self.stderr.write(
                    f'  Ошибка файла «{tex_path.name}»: {exc}'
                )

        total = len(all_records)
        self.stdout.write(
            f'Файлов с задачами: {files_with_problems}, '
            f'задач собрано: {total}'
        )

        # ── Шаг 2: сохраняем батчами по {BATCH_SIZE} задач ───────────────────
        created = skipped = errors = 0

        for batch_start in range(0, total, BATCH_SIZE):
            batch = all_records[batch_start:batch_start + BATCH_SIZE]

            with transaction.atomic():
                for rec in batch:
                    if rec['content_hash'] in existing_hashes:
                        skipped += 1
                        continue

                    try:
                        with transaction.atomic():
                            if not dry_run:
                                p = Problem.objects.create(
                                    title=rec['title'],
                                    statement=rec['statement'],
                                    status=Problem.Status.DRAFT,
                                    content_hash=rec['content_hash'],
                                    problem_type='',
                                )
                                if rec['topic']:
                                    p.topics.add(rec['topic'])

                                SourceReference.objects.create(
                                    problem=p,
                                    source=source,
                                    note=rec['source_note'],
                                )

                                for idx, part_text in enumerate(rec['parts']):
                                    label = (
                                        PART_LABELS[idx]
                                        if idx < len(PART_LABELS)
                                        else str(idx + 1)
                                    )
                                    ProblemPart.objects.create(
                                        problem=p,
                                        label=label,
                                        statement=part_text,
                                        answer='',
                                        order=idx,
                                    )

                            existing_hashes.add(rec['content_hash'])
                            created += 1

                    except Exception as exc:
                        errors += 1
                        self.stderr.write(
                            f'  Ошибка записи «{rec["title"][:50]}»: {exc}'
                        )

            done = min(batch_start + BATCH_SIZE, total)
            progress = int(done / total * 100) if total else 100

            if not dry_run:
                job.progress = progress
                job.result = {
                    'files': files_with_problems,
                    'created': created,
                    'skipped': skipped,
                    'errors': errors,
                }
                job.save(update_fields=['progress', 'result'])

            self.stdout.write(
                f'  [{done:4d}/{total}]  '
                f'создано: {created},  '
                f'пропущено: {skipped},  '
                f'ошибок: {errors}'
            )

        # ── Завершаем Job ─────────────────────────────────────────────────────
        if not dry_run:
            job.status = Job.Status.DONE
            job.progress = 100
            job.finished_at = timezone.now()
            job.result = {
                'files': files_with_problems,
                'created': created,
                'skipped': skipped,
                'errors': errors,
            }
            job.save(update_fields=['status', 'progress', 'finished_at', 'result'])

        self.stdout.write(self.style.SUCCESS(
            f'\nГотово!\n'
            f'  Файлов обработано:     {files_with_problems}\n'
            f'  Создано задач:         {created}\n'
            f'  Пропущено (дубли):     {skipped}\n'
            f'  Ошибок:                {errors}\n'
            f'  Job #{job.pk}: {job.status}'
        ))
