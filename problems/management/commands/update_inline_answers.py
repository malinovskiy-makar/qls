"""
Management command: update_inline_answers

Извлекает строки-комментарии вида «% Ответ: текст» или «%Ответ: текст»
из .tex файлов архивов Archive 3 (olmat41), ищет задачи в базе по
content_hash и заполняет поле answer (только если оно пустое).

Маркер ответа ищется ПОСЛЕ условия задачи — от конца условия до
следующего \\problem или до конца файла.

Запуск:
    ./venv/bin/python manage.py update_inline_answers
    ./venv/bin/python manage.py update_inline_answers --dry-run
    ./venv/bin/python manage.py update_inline_answers --zip-dir /path/to/folder
"""

import hashlib
import re
import zipfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from problems.models import Job, Problem


DEFAULT_ZIP_DIR = (
    Path(settings.BASE_DIR)
    / 'materials'
    / 'Archive 6'
    / 'Archive 5'
    / 'Archive 3'
    / 'Archive 3'
    / 'Overleaf Projects (41 items)'
)

# Маркер ответа: % Ответ: ... или %Ответ: ...
_ANSWER_RE = re.compile(r'%\s*[Оо]твет\s*:?\s*(.+)')

# Маркер задачи
_PROBLEM_RE = re.compile(r'\\problem\b')
_SUBITEM_RE = re.compile(r'\\[Rr]?[Ss]ubitem\b')


# ── Утилиты ──────────────────────────────────────────────────────────────────

def _find_brace_end(text: str, start: int) -> int:
    depth = 0
    i = start
    n = len(text)
    while i < n:
        c = text[i]
        if c == '\\':
            i += 2
            continue
        if c == '%':
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


def _strip_comment_envs(text: str) -> str:
    return re.sub(r'\\begin\{comment\}.*?\\end\{comment\}', '', text, flags=re.DOTALL)


_FORMAT_CMDS = (
    'textbf', 'emph', 'underline', 'textit', 'textrm',
    'texttt', 'textsc', 'textmd', 'textup', 'text',
)


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
    text = re.sub(r'\\n\b', '\n', text)
    text = re.sub(r'\\\\', '\n', text)
    text = re.sub(r'\\begin\{center\}', '', text)
    text = re.sub(r'\\end\{center\}', '', text)
    text = re.sub(r'\\begin\{document\}', '', text)
    text = re.sub(r'\\end\{document\}', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


def _is_commented(text: str, pos: int) -> bool:
    line_start = text.rfind('\n', 0, pos) + 1
    before = text[line_start:pos]
    for i, c in enumerate(before):
        if c == '%' and (i == 0 or before[i - 1] != '\\'):
            return True
    return False


# ── Основной парсер — ищет пары (stmt_hash, answer) ──────────────────────────

def extract_inline_answers(content: str):
    """
    Для каждого \\problem находит строку «% Ответ: ...» в теле задачи
    (до следующего \\problem). Возвращает список (stmt_hash, answer_text).

    Хэш считается ИДЕНТИЧНО import_archive3.py:
      — старый формат: md5(clean_latex(text_after_\\problem))
      — новый МатЭк:   md5(clean_latex(content_of_{stmt}))
    """
    content = _strip_comment_envs(content)

    problem_positions = [
        m.start() for m in _PROBLEM_RE.finditer(content)
        if not _is_commented(content, m.start())
    ]

    if not problem_positions:
        return []

    results = []

    for pi, pstart in enumerate(problem_positions):
        pos = pstart + len('\\problem')
        next_pstart = (
            problem_positions[pi + 1] if pi + 1 < len(problem_positions) else len(content)
        )

        # Полный блок задачи — для поиска % Ответ:
        full_block = content[pstart:next_pstart]
        m = _ANSWER_RE.search(full_block)
        if not m:
            continue

        answer_raw = m.group(1).strip()
        answer_raw = re.split(r'%|\\end\{', answer_raw)[0].strip()
        if not answer_raw or len(answer_raw) > 500:
            continue

        # Пропустить необязательный числовой аргумент [\d+] (как в import_archive3)
        opt_num, pos_after_num = _extract_optional(content, pos)
        if opt_num is not None and opt_num.strip().isdigit():
            pos = pos_after_num

        # Определяем формат
        peek = pos
        while peek < len(content) and content[peek] in ' \t':
            peek += 1

        if peek < next_pstart and content[peek] == '{':
            # Новый МатЭк: {метка}[заголовок]{условие}
            label, pos2 = _extract_braced(content, pos)
            if label is None:
                continue
            title, pos3 = _extract_optional(content, pos2)
            if title is not None:
                pos2 = pos3
            stmt, _ = _extract_braced(content, pos2)
            if not stmt:
                continue
            stmt_clean = clean_latex(stmt.strip())
        else:
            # Старый формат: текст ПОСЛЕ \\problem (pos уже сдвинут),
            # идентично import_archive3.py: chunk = content[pos:next_pstart]
            raw_block = content[pos:next_pstart]
            # Убираем % Ответ и всё после него перед хэшированием
            raw_block = re.sub(r'%\s*[Оо]твет.*', '', raw_block)
            # Берём только условие (до первого \Subitem)
            parts = _SUBITEM_RE.split(raw_block)
            stmt_clean = clean_latex(parts[0])

        if not stmt_clean or len(stmt_clean) < 15:
            continue
        if '#1' in stmt_clean or '#2' in stmt_clean:
            continue

        stmt_hash = hashlib.md5(stmt_clean.encode(), usedforsecurity=False).hexdigest()
        results.append((stmt_hash, answer_raw))

    return results


# ── Сбор .tex файлов из zip-архивов ──────────────────────────────────────────

def _should_skip(name: str, size: int) -> bool:
    nl = name.lower()
    if nl.endswith('.sty'):
        return True
    if nl.endswith('main.tex'):
        return True
    if 'preamble' in nl:
        return True
    if size < 500:
        return True
    return False


def iter_zip_tex(zip_dir: Path):
    """Перебирает .tex файлы из всех .zip в zip_dir."""
    for zip_path in sorted(zip_dir.glob('*.zip')):
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                for member in zf.infolist():
                    if not member.filename.endswith('.tex'):
                        continue
                    if _should_skip(member.filename, member.file_size):
                        continue
                    try:
                        content = zf.read(member).decode('utf-8', errors='replace')
                        display = f'{zip_path.name} / {member.filename}'
                        yield display, content
                    except Exception:
                        pass
        except Exception as exc:
            pass


# ── Команда ──────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = (
        'Извлекает % Ответ: из .tex файлов olmat41, обновляет поле answer '
        'у задач в базе (только если пустое)'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--zip-dir', type=str, default=str(DEFAULT_ZIP_DIR),
            help='Папка с ZIP-архивами',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Только считать, ничего не писать',
        )

    def handle(self, *args, **options):
        zip_dir = Path(options['zip_dir'])
        dry_run = options['dry_run']

        if not zip_dir.exists():
            self.stderr.write(self.style.ERROR(f'Папка не найдена: {zip_dir}'))
            return

        self.stdout.write(f'Папка: {zip_dir}')
        if dry_run:
            self.stdout.write('(dry-run: в базу ничего не пишем)')

        job = Job.objects.create(
            kind=Job.Kind.IMPORT,
            status=Job.Status.RUNNING,
            params={'zip_dir': str(zip_dir), 'dry_run': dry_run},
        )
        self.stdout.write(f'Job #{job.pk} создан')

        self.stdout.write('Загружаю хэши задач из базы...')
        hash_to_pk = {
            row[0]: row[1]
            for row in Problem.objects.exclude(content_hash='').values_list('content_hash', 'pk')
        }
        self.stdout.write(f'Задач в базе с хэшем: {len(hash_to_pk)}')

        files_processed = 0
        pairs_found = 0
        updated = 0
        not_in_db = 0
        already_filled = 0
        errors = 0

        for display_name, content in iter_zip_tex(zip_dir):
            # Быстрая проверка: есть ли маркер ответа
            if not re.search(r'%\s*[Оо]твет', content):
                continue

            files_processed += 1
            try:
                pairs = extract_inline_answers(content)
            except Exception as exc:
                errors += 1
                self.stderr.write(f'  Ошибка парсинга «{display_name}»: {exc}')
                continue

            for stmt_hash, answer_text in pairs:
                pairs_found += 1

                pk = hash_to_pk.get(stmt_hash)
                if pk is None:
                    not_in_db += 1
                    continue

                try:
                    p = Problem.objects.get(pk=pk)
                except Problem.DoesNotExist:
                    not_in_db += 1
                    continue

                if p.answer:
                    already_filled += 1
                    continue

                if not dry_run:
                    with transaction.atomic():
                        p.answer = answer_text
                        p.save(update_fields=['answer'])
                updated += 1

        result = {
            'files_with_answer': files_processed,
            'pairs_found': pairs_found,
            'updated': updated,
            'not_in_db': not_in_db,
            'already_filled': already_filled,
            'errors': errors,
        }
        if not dry_run:
            job.status = Job.Status.DONE
            job.progress = 100
            job.finished_at = timezone.now()
            job.result = result
            job.save(update_fields=['status', 'progress', 'finished_at', 'result'])

        self.stdout.write(self.style.SUCCESS(
            f'\nГотово!\n'
            f'  Файлов с % Ответ:      {files_processed}\n'
            f'  Пар (хэш+ответ):       {pairs_found}\n'
            f'  Обновлено answer:      {updated}\n'
            f'  Не найдено в базе:     {not_in_db}\n'
            f'  Уже заполнено:         {already_filled}\n'
            f'  Ошибок парсинга:       {errors}\n'
            f'  Job #{job.pk}: {job.status if not dry_run else "dry-run"}'
        ))
