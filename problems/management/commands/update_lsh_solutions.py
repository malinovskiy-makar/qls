r"""
Management command: update_lsh_solutions

Ищет решения (\solution{}{}) к задачам ЛШ Олмат 2025, которые были
импортированы без них. Обрабатывает как папку ЛШ Олмат 2025, так и
все .zip-архивы из той же папки (ЛШ/ВШ Олмат 2024, Команда 23-24 и т.д.),
где встречаются \solution — находит задачи в базе по content_hash и
обновляет поле solution или answer.

Логика:
  - Если \solution — только буква или их сочетание (а, б, аб, абв…) →
    пишем в Problem.answer (краткий ответ теста).
  - Иначе → пишем в Problem.solution (развёрнутое решение).
  - Обновляем только задачи, где целевое поле пустое.

Запуск:
    ./venv/bin/python manage.py update_lsh_solutions
    ./venv/bin/python manage.py update_lsh_solutions --dry-run
    ./venv/bin/python manage.py update_lsh_solutions --zip-dir /path/to/folder
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

from problems.models import Job, Problem


DEFAULT_ZIP_DIR = (
    Path(settings.BASE_DIR)
    / 'materials'
    / 'Archive 6'
    / 'Archive 5'
    / 'Archive 3'
    / 'Archive 2'
    / 'Overleaf Projects (41 items)'
)

EXTRACT_DIR = Path('/tmp/lsh_update')

# ── Утилиты скобочного парсинга (скопированы из import_archive3) ──────────────

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


def _is_commented(text: str, pos: int) -> bool:
    line_start = text.rfind('\n', 0, pos) + 1
    before = text[line_start:pos]
    for i, c in enumerate(before):
        if c == '%' and (i == 0 or before[i - 1] != '\\'):
            return True
    return False


def _strip_comment_envs(text: str) -> str:
    return re.sub(r'\\begin\{comment\}.*?\\end\{comment\}', '', text, flags=re.DOTALL)


# ── Форматирование ──────────────────────────────────────────────────────────

_FORMAT_CMDS = (
    'textbf', 'emph', 'underline', 'textit', 'textrm',
    'texttt', 'textsc', 'textmd', 'textup', 'text',
)
_SUBITEM_RE = re.compile(r'\\[Rr]?[Ss]ubitem\b')


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


def _is_letter_answer(text: str) -> bool:
    """Проверяет, является ли текст кратким буквенным ответом (а, б, аб, абвг...)."""
    stripped = text.strip().lower()
    return bool(re.fullmatch(r'[абвгдеж]{1,5}', stripped))


# ── Парсинг задач с решением ──────────────────────────────────────────────────

def extract_solutions_from_tex(content: str):
    r"""
    Возвращает список пар (stmt_hash, solution_text) для задач,
    у которых есть \solution{}{} или \solution{} с непустым содержимым.
    Хэш считается от очищенного условия.
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

    if not problem_positions or not solution_positions:
        return []

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
            # Новый МатЭк формат: {метка}[заголовок]{условие}
            label, pos = _extract_braced(content, pos)
            if label is None:
                continue
            title, pos_after_title = _extract_optional(content, pos)
            if title is not None:
                pos = pos_after_title
            stmt, pos = _extract_braced(content, pos)
            if not stmt or not stmt.strip():
                continue
            stmt_clean = clean_latex(stmt.strip())
        else:
            # Старый формат: \problem текст до \Subitem
            chunk = content[pstart + len('\\problem'):next_pstart]
            parts = _SUBITEM_RE.split(chunk)
            stmt_raw = parts[0]
            stmt_clean = clean_latex(stmt_raw)

        if not stmt_clean or len(stmt_clean) < 15:
            continue

        # Ищем \solution между этой задачей и следующей
        solution_text = ''
        for sstart in solution_positions:
            if sstart <= pstart or sstart >= next_pstart:
                continue
            spos = sstart + len('\\solution')
            s_arg1, spos2 = _extract_braced(content, spos)
            if s_arg1 is not None:
                s_arg2, _ = _extract_braced(content, spos2)
                if s_arg2 is not None:
                    text_only = re.sub(
                        r'\\includegraphics(?:\[[^\]]*\])?\{[^}]*\}', '', s_arg2
                    ).strip()
                    if text_only:
                        solution_text = s_arg2.strip()
                    elif s_arg1.strip() and '\\includegraphics' not in s_arg1:
                        solution_text = s_arg1.strip()
                else:
                    if s_arg1.strip() and '\\includegraphics' not in s_arg1:
                        solution_text = s_arg1.strip()
            break

        if not solution_text:
            continue

        sol_clean = clean_latex(solution_text)
        if not sol_clean:
            continue

        stmt_hash = hashlib.md5(stmt_clean.encode()).hexdigest()
        results.append((stmt_hash, sol_clean))

    return results


# ── Сбор .tex файлов из папки или zip-архива ──────────────────────────────────

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


def iter_tex_files(source_dir: Path):
    """
    Обходит source_dir: читает .tex напрямую из подпапок и
    распаковывает zip-архивы во extract_dir (временно).
    Yield: (display_name: str, content: str)
    """
    # 1. Прямые .tex файлы (рекурсивно из подпапок — не zip)
    for tex_path in source_dir.rglob('*.tex'):
        if tex_path.is_file() and not _should_skip(tex_path.name, tex_path.stat().st_size):
            try:
                content = tex_path.read_text(encoding='utf-8', errors='replace')
                yield str(tex_path.relative_to(source_dir)), content
            except Exception:
                pass

    # 2. ZIP-архивы
    for zip_path in sorted(source_dir.glob('*.zip')):
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
        except Exception:
            pass


# ── Команда ─────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = (
        'Ищет \\solution в архивах ЛШ Олмат 2025, обновляет solution/answer '
        'у задач в базе (только если поле пустое)'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--zip-dir', type=str, default=str(DEFAULT_ZIP_DIR),
            help='Папка с архивами и подпапками',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Только считать, ничего не писать',
        )

    def handle(self, *args, **options):
        source_dir = Path(options['zip_dir'])
        dry_run = options['dry_run']

        if not source_dir.exists():
            self.stderr.write(self.style.ERROR(f'Папка не найдена: {source_dir}'))
            return

        self.stdout.write(f'Папка: {source_dir}')
        if dry_run:
            self.stdout.write('(dry-run: в базу ничего не пишем)')

        # Job
        job = Job.objects.create(
            kind=Job.Kind.IMPORT,
            status=Job.Status.RUNNING,
            params={'zip_dir': str(source_dir), 'dry_run': dry_run},
        )
        self.stdout.write(f'Job #{job.pk} создан')

        # Загрузим все content_hash задач в память (для быстрого поиска)
        self.stdout.write('Загружаю хэши задач из базы...')
        hash_to_pk = {
            row[0]: row[1]
            for row in Problem.objects.exclude(content_hash='').values_list('content_hash', 'pk')
        }
        self.stdout.write(f'Задач в базе с хэшем: {len(hash_to_pk)}')

        # Статистика
        files_processed = 0
        pairs_found = 0       # пар (хэш, решение) найдено в файлах
        updated_solution = 0  # обновили solution
        updated_answer = 0    # обновили answer (только буква)
        not_in_db = 0         # хэш не нашли в базе
        already_filled = 0    # поле уже было заполнено
        errors = 0

        for display_name, content in iter_tex_files(source_dir):
            if '\\solution' not in content:
                continue

            files_processed += 1
            try:
                pairs = extract_solutions_from_tex(content)
            except Exception as exc:
                errors += 1
                self.stderr.write(f'  Ошибка парсинга «{display_name}»: {exc}')
                continue

            for stmt_hash, sol_text in pairs:
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

                if _is_letter_answer(sol_text):
                    # Краткий буквенный ответ → поле answer
                    if p.answer:
                        already_filled += 1
                        continue
                    if not dry_run:
                        with transaction.atomic():
                            p.answer = sol_text.strip().lower()
                            p.save(update_fields=['answer'])
                    updated_answer += 1
                    self.stdout.write(
                        f'  [answer] pk={pk}: «{sol_text.strip()}»'
                    )
                else:
                    # Развёрнутое решение → поле solution
                    if p.solution:
                        already_filled += 1
                        continue
                    if not dry_run:
                        with transaction.atomic():
                            p.solution = sol_text
                            p.save(update_fields=['solution'])
                    updated_solution += 1

        # Завершаем Job
        result = {
            'files_with_solution': files_processed,
            'pairs_found': pairs_found,
            'updated_solution': updated_solution,
            'updated_answer': updated_answer,
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
            f'  Файлов с \\solution:    {files_processed}\n'
            f'  Пар (хэш+решение):     {pairs_found}\n'
            f'  Обновлено solution:    {updated_solution}\n'
            f'  Обновлено answer:      {updated_answer}\n'
            f'  Не найдено в базе:     {not_in_db}\n'
            f'  Уже заполнено:         {already_filled}\n'
            f'  Ошибок парсинга:       {errors}\n'
            f'  Job #{job.pk}: {job.status if not dry_run else "dry-run"}'
        ))
