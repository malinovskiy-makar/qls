"""
Management command: import_matek

Импортирует задачи из LaTeX файлов ZIP-архивов МатЭк (2021–2025).
Распаковывает все ZIP из указанной папки во временную /tmp/matek_tex/,
затем обходит все .tex файлы и импортирует задачи по маркерам \\problem.
Дедупликация по MD5-хэшу условия (поле content_hash на модели Problem).
Статус всех задач — draft.

Поддерживаемые форматы:
  Новый МатЭк: \\problem{метка}[Заголовок]{условие}{\\n подп.} + \\solution{}{решение}
  Старый:      \\problem текст условия \\Subitem вар1 \\Subitem вар2

Запуск:
    python manage.py import_matek
    python manage.py import_matek --zip-dir /path/to/zips
    python manage.py import_matek --dry-run
"""

import hashlib
import re
import shutil
import zipfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from problems.models import Job, Problem, ProblemPart, Source, SourceReference, Topic


DEFAULT_ZIP_DIR = (
    Path(settings.BASE_DIR)
    / 'materials'
    / 'Archive 6'
    / 'Archive 5'
    / 'Archive 3'
    / 'Archive 2'
    / 'Overleaf Projects (20 items)'
)

EXTRACT_DIR = Path('/tmp/matek_tex')
BATCH_SIZE = 50

PART_LABELS = list('абвгдежзиклмнопрстуфхцчшщ')

_HEADIC_RE = re.compile(r'\\headic\{[^}]*\}\{[^}]*\}\{([^}]*)\}\{([^}]*)\}')
_SUBITEM_RE = re.compile(r'\\[Rr]?[Ss]ubitem\b')

_TRANSLIT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e',
    'ё': 'e', 'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k',
    'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
    'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts',
    'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '',
    'э': 'e', 'ю': 'yu', 'я': 'ya', ' ': '-', '+': '-',
}

_FORMAT_CMDS = (
    'textbf', 'emph', 'underline', 'textit', 'textrm',
    'texttt', 'textsc', 'textmd', 'textup', 'text',
)


# ── Вспомогательные функции для парсинга сбалансированных скобок ──────────────

def _find_brace_end(text: str, start: int) -> int:
    """Найти индекс закрывающей } для { в позиции start. -1 если не найдено."""
    depth = 0
    i = start
    n = len(text)
    while i < n:
        c = text[i]
        if c == '\\':
            i += 2  # пропускаем экранированный символ (\{ \} и т.д.)
            continue
        if c == '%':
            # пропускаем строку-комментарий
            nl = text.find('\n', i)
            i = nl + 1 if nl != -1 else n
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _extract_braced(text: str, pos: int):
    """
    Извлечь {содержимое} начиная с pos (после пробелов).
    Возвращает (содержимое, new_pos) или (None, pos).
    """
    i = pos
    while i < len(text) and text[i] in ' \t\n\r':
        i += 1
    if i >= len(text) or text[i] != '{':
        return None, pos
    end = _find_brace_end(text, i)
    if end == -1:
        return None, pos
    return text[i + 1:end], end + 1


def _extract_optional(text: str, pos: int):
    """
    Извлечь [содержимое] начиная с pos (после пробелов).
    Возвращает (содержимое, new_pos) или (None, pos).
    """
    i = pos
    while i < len(text) and text[i] in ' \t\n\r':
        i += 1
    if i >= len(text) or text[i] != '[':
        return None, pos
    depth = 0
    j = i
    while j < len(text):
        c = text[j]
        if c == '\\':
            j += 2
            continue
        if c == '[':
            depth += 1
        elif c == ']':
            depth -= 1
            if depth == 0:
                return text[i + 1:j], j + 1
        j += 1
    return None, pos


def _is_commented(text: str, pos: int) -> bool:
    """Проверить, что позиция pos находится на строке, где до неё есть незащищённый %."""
    line_start = text.rfind('\n', 0, pos) + 1
    before = text[line_start:pos]
    for i, c in enumerate(before):
        if c == '%' and (i == 0 or before[i - 1] != '\\'):
            return True
    return False


def _strip_comment_envs(text: str) -> str:
    """Убрать содержимое \\begin{comment}...\\end{comment}."""
    return re.sub(r'\\begin\{comment\}.*?\\end\{comment\}', '', text, flags=re.DOTALL)


# ── Форматирование и очистка ──────────────────────────────────────────────────

def _strip_wrapper(text: str, cmd: str) -> str:
    result = []
    i = 0
    pattern = '\\' + cmd + '{'
    while i < len(text):
        idx = text.find(pattern, i)
        if idx == -1:
            result.append(text[i:])
            break
        result.append(text[i:idx])
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
            result.append(text[idx:])
            break
    return ''.join(result)


def clean_latex(text: str) -> str:
    for cmd in _FORMAT_CMDS:
        text = _strip_wrapper(text, cmd)

    text = re.sub(r'\\includegraphics(?:\[[^\]]*\])?\{[^}]*\}', '', text)
    text = re.sub(r'\\hspace\*?\{[^}]*\}', '', text)
    text = re.sub(r'\\vspace\*?\{[^}]*\}', '', text)
    text = re.sub(r'\\setlength\{[^}]*\}\{[^}]*\}', '', text)
    text = re.sub(r'\\label\{[^}]*\}', '', text)
    text = re.sub(r'\\ref\{[^}]*\}', '', text)
    text = re.sub(r'\\def\\[A-Za-z]+\{[^}]*\}', '', text)

    text = re.sub(
        r'\\(noindent|centering|hrulefill|displaystyle|heart'
        r'|quad|qquad|smallskip|medskip|bigskip|newline'
        r'|clearpage|newpage|displaypage)\b',
        '', text,
    )
    # \\n — кастомная МатЭк-макрокоманда «новый подпункт» → переход строки
    text = re.sub(r'\\n\b', '\n', text)
    text = re.sub(r'\\\\', '\n', text)
    text = re.sub(r'\\begin\{center\}', '', text)
    text = re.sub(r'\\end\{center\}', '', text)
    text = re.sub(r'\\begin\{document\}', '', text)
    text = re.sub(r'\\end\{document\}', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


def extract_title(statement: str) -> str:
    end = len(statement)
    for i, ch in enumerate(statement):
        if ch in ('.', '\n') and i > 5:
            end = i
            break
    return statement[:end][:80].strip()


def parse_headic(content: str):
    m = _HEADIC_RE.search(content)
    if not m:
        return '', ''
    topic = m.group(1).strip()
    author = m.group(2).strip()
    if topic.lower() in ('тема', ''):
        topic = ''
    if author.lower() in ('автор', ''):
        author = ''
    return topic, author


def parse_problems_from_tex(content: str):
    """
    Парсит задачи из .tex файла. Поддерживает два формата:

    Новый МатЭк (\\problem{}: следующий символ после \\problem — '{'):
      \\problem{метка}[Заголовок]{условие}{\\n подп1 \\n подп2} + \\solution{}{решение}

    Старый (\\problem <текст>):
      \\problem текст условия ... \\Subitem вар1 \\Subitem вар2

    Возвращает список словарей:
      {title: str, statement: str, subitems: list[str], solution: str}
    """
    content = _strip_comment_envs(content)

    problem_positions = [
        m.start() for m in re.finditer(r'\\problem\b', content)
        if not _is_commented(content, m.start())
    ]
    solution_positions = [
        m.start() for m in re.finditer(r'\\solution\b', content)
        if not _is_commented(content, m.start())
    ]

    results = []

    for pi, pstart in enumerate(problem_positions):
        pos = pstart + len('\\problem')
        next_pstart = (
            problem_positions[pi + 1] if pi + 1 < len(problem_positions) else len(content)
        )

        # Пропустить необязательный числовой аргумент [\d+]
        opt_num, pos_after_num = _extract_optional(content, pos)
        if opt_num is not None and opt_num.strip().isdigit():
            pos = pos_after_num

        # Определяем формат по первому непробельному символу
        peek = pos
        while peek < len(content) and content[peek] in ' \t':
            peek += 1

        if peek < len(content) and content[peek] == '{':
            # ── Новый МатЭк формат ──────────────────────────────────────
            # {метка}
            label, pos = _extract_braced(content, pos)
            if label is None:
                continue

            # [Заголовок] — необязательный
            title, pos_after_title = _extract_optional(content, pos)
            if title is not None:
                pos = pos_after_title
            else:
                title = ''

            # {условие} — обязательный
            stmt, pos = _extract_braced(content, pos)
            if stmt is None:
                continue
            stmt = stmt.strip()
            if not stmt:
                continue

            # {подпункты} или [источник] — необязательный
            subitems_raw = ''
            peek2 = pos
            while peek2 < len(content) and content[peek2] in ' \t\n\r':
                peek2 += 1

            if peek2 < len(content) and content[peek2] == '{':
                sub_content, pos = _extract_braced(content, pos)
                if sub_content is not None:
                    subitems_raw = sub_content
                # Необязательный [источник] после подпунктов — пропускаем
                _extract_optional(content, pos)
            elif peek2 < len(content) and content[peek2] == '[':
                # Необязательный [источник] без подпунктов — пропускаем
                _extract_optional(content, pos)

            # Ищем \\solution между этой задачей и следующей
            solution_text = ''
            for sstart in solution_positions:
                if sstart <= pstart or sstart >= next_pstart:
                    continue
                spos = sstart + len('\\solution')
                s_arg1, spos2 = _extract_braced(content, spos)
                if s_arg1 is not None:
                    s_arg2, _ = _extract_braced(content, spos2)
                    if s_arg2 is not None:
                        # Двухаргументная форма: \\solution{}{текст решения}
                        text_only = re.sub(
                            r'\\includegraphics(?:\[[^\]]*\])?\{[^}]*\}', '', s_arg2
                        ).strip()
                        if text_only:
                            solution_text = s_arg2.strip()
                        elif s_arg1.strip() and '\\includegraphics' not in s_arg1:
                            solution_text = s_arg1.strip()
                    else:
                        # Одноаргументная форма
                        if '\\includegraphics' not in s_arg1:
                            solution_text = s_arg1.strip()
                break  # берём только первое \\solution после задачи

            # Разбиваем подпункты по маркеру \n (МатЭк-макрокоманда)
            subitems: list = []
            if subitems_raw:
                parts = re.split(r'\\n\b', subitems_raw)
                subitems = [p.strip() for p in parts if p.strip()]

            results.append({
                'title': title.strip(),
                'statement': stmt,
                'subitems': subitems,
                'solution': solution_text,
            })

        else:
            # ── Старый формат: \\problem <текст> \\Subitem ... ──────────
            chunk = content[pstart + len('\\problem'):next_pstart]
            parts = _SUBITEM_RE.split(chunk)
            main_text = parts[0]
            subitems_raw_list = parts[1:]

            results.append({
                'title': '',
                'statement': main_text,
                'subitems': subitems_raw_list,
                'solution': '',
            })

    return results


def _make_topic_slug(name: str) -> str:
    lowered = name.lower()
    chars = []
    for ch in lowered:
        chars.append(_TRANSLIT.get(ch, ch))
    slug = ''.join(c for c in ''.join(chars) if c.isalnum() or c == '-')
    return slug[:110] or 'topic'


class Command(BaseCommand):
    help = 'Импортирует задачи из LaTeX ZIP-архивов МатЭк (2021–2025)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--zip-dir', type=str, default=str(DEFAULT_ZIP_DIR),
            help='Папка с ZIP-архивами',
        )
        parser.add_argument(
            '--extract-dir', type=str, default=str(EXTRACT_DIR),
            help='Папка для распаковки (будет очищена)',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Только считать, ничего не писать в базу',
        )
        parser.add_argument(
            '--keep-extracted', action='store_true',
            help='Не удалять распакованные файлы после импорта',
        )

    def handle(self, *args, **options):
        zip_dir = Path(options['zip_dir'])
        extract_dir = Path(options['extract_dir'])
        dry_run = options['dry_run']
        keep_extracted = options['keep_extracted']

        if not zip_dir.exists():
            self.stderr.write(self.style.ERROR(f'Папка не найдена: {zip_dir}'))
            return

        # ── Шаг 1: распаковка ZIP ────────────────────────────────────────────
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True)

        zip_files = sorted(zip_dir.glob('*.zip'))
        self.stdout.write(f'ZIP-архивов найдено: {len(zip_files)}')

        unzip_errors = 0
        for zf_path in zip_files:
            try:
                dest = extract_dir / zf_path.stem
                dest.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(zf_path, 'r') as zf:
                    zf.extractall(dest)
                self.stdout.write(f'  Распакован: {zf_path.name}')
            except Exception as exc:
                unzip_errors += 1
                self.stderr.write(f'  Ошибка распаковки {zf_path.name}: {exc}')

        self.stdout.write(f'Распаковано архивов: {len(zip_files) - unzip_errors} (ошибок: {unzip_errors})')

        # ── Шаг 2: сбор .tex файлов ──────────────────────────────────────────
        all_tex = list(extract_dir.rglob('*.tex'))

        def _should_skip(p: Path) -> bool:
            if p.suffix == '.sty':
                return True
            name_lower = p.name.lower()
            if name_lower == 'main.tex':
                return True
            if 'preamble' in name_lower:
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
            name='МатЭк — Overleaf архивы (2021–2025)',
            defaults={
                'kind': 'авторские материалы',
                'note': 'LaTeX файлы из Overleaf-проектов МатЭк 2021–2025 (кружок, интенсивы, мини-группы).',
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
            params={'zip_dir': str(zip_dir), 'dry_run': dry_run},
        )
        self.stdout.write(f'Job #{job.pk} создан')

        # ── Кэши ─────────────────────────────────────────────────────────────
        existing_hashes: set = set(
            Problem.objects.exclude(content_hash='').values_list('content_hash', flat=True)
        )
        topic_cache: dict = {t.name: t for t in Topic.objects.all()}

        # ── Шаг 3: парсим все .tex файлы ─────────────────────────────────────
        all_records = []
        files_with_problems = 0

        for tex_path in tex_files:
            try:
                with open(tex_path, encoding='utf-8', errors='replace') as fh:
                    content = fh.read()

                if '\\problem' not in content:
                    continue

                topic_name, author = parse_headic(content)

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

                try:
                    rel_path = tex_path.relative_to(extract_dir)
                    source_note = str(rel_path)
                except ValueError:
                    source_note = tex_path.name
                if author:
                    source_note += f' (автор: {author})'

                problems_raw = parse_problems_from_tex(content)
                if problems_raw:
                    files_with_problems += 1

                for rec in problems_raw:
                    stmt = clean_latex(rec['statement'])
                    if not stmt or len(stmt) < 15:
                        continue
                    # Пропускаем LaTeX-шаблонный мусор (определения команд)
                    if '#1' in stmt or '#2' in stmt or r'\IfValueTF' in stmt:
                        continue

                    title = rec['title'] or extract_title(stmt)
                    solution = clean_latex(rec['solution']) if rec['solution'] else ''
                    stmt_hash = hashlib.md5(stmt.encode()).hexdigest()
                    parts = [
                        clean_latex(s) for s in rec['subitems']
                        if clean_latex(s)
                    ]

                    all_records.append({
                        'title': title,
                        'statement': stmt,
                        'solution': solution,
                        'content_hash': stmt_hash,
                        'topic': topic_obj,
                        'source_note': source_note[:299],
                        'parts': parts,
                    })

            except Exception as exc:
                self.stderr.write(f'  Ошибка файла «{tex_path.name}»: {exc}')

        total = len(all_records)
        self.stdout.write(
            f'Файлов с задачами: {files_with_problems}, '
            f'задач собрано: {total}'
        )

        # ── Шаг 4: сохраняем батчами ──────────────────────────────────────────
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
                                    solution=rec['solution'],
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
                        self.stderr.write(f'  Ошибка записи «{rec["title"][:50]}»: {exc}')

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

        # ── Очистка временной папки ───────────────────────────────────────────
        if not keep_extracted and not dry_run:
            shutil.rmtree(extract_dir, ignore_errors=True)
            self.stdout.write(f'Временная папка {extract_dir} удалена')

        self.stdout.write(self.style.SUCCESS(
            f'\nГотово!\n'
            f'  ZIP-архивов:           {len(zip_files)}\n'
            f'  Файлов с задачами:     {files_with_problems}\n'
            f'  Создано задач:         {created}\n'
            f'  Пропущено (дубли):     {skipped}\n'
            f'  Ошибок:                {errors}\n'
            f'  Job #{job.pk}: {job.status}'
        ))
