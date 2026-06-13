"""
Management command: import_olmat_reshаlki

Импортирует задачи из файлов «Решалки» в архивах Archive 3 (olmat41).
Файл считается решалкой, если в его пути есть «решалк» (без учёта регистра)
или слово «Solution».

Форматы задач:
  1. Новый МатЭк: \\problem{метка}[заголовок]{условие} + \\solution{}{решение}
  2. Старый: \\problem текст \\Subitem ...
     — внутри старого формата решение выделяется маркером
       \\hrulefill или «\\textbf{Решение» (в любом регистре).

Дедупликация по content_hash (MD5 очищенного условия).
Статус: draft. Источник: «Решалки Олмат (olmat41)».

Запуск:
    ./venv/bin/python manage.py import_olmat_reshаlki
    ./venv/bin/python manage.py import_olmat_reshаlki --dry-run
    ./venv/bin/python manage.py import_olmat_reshаlki --zip-dir /path/to/folder
"""

import hashlib
import re
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
    / 'Archive 3'
    / 'Overleaf Projects (41 items)'
)

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

# Маркер «Решение:» в старом формате (после \hrulefill или как \textbf{...Решение...})
_SOLUTION_MARKER_RE = re.compile(
    r'(?:\\hrulefill\s*\n|\\newline\s*\n?)'
    r'|'
    r'\\textbf\{[^}]*[Рр]ешени[ея][^}]*\}'
    r'|'
    r'\\underline\{[^}]*[Рр]ешени[ея][^}]*\}'
    r'|'
    r'^[^\n]*\*\*[Рр]ешени[ея]'
    r'|'
    r'^\s*\{?\\it(?:shape)?\s+[Рр]ешени',
    re.MULTILINE,
)


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


def _is_commented(text: str, pos: int) -> bool:
    line_start = text.rfind('\n', 0, pos) + 1
    before = text[line_start:pos]
    for i, c in enumerate(before):
        if c == '%' and (i == 0 or before[i - 1] != '\\'):
            return True
    return False


def _strip_comment_envs(text: str) -> str:
    return re.sub(r'\\begin\{comment\}.*?\\end\{comment\}', '', text, flags=re.DOTALL)


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


def _make_topic_slug(name: str) -> str:
    lowered = name.lower()
    chars = [_TRANSLIT.get(ch, ch) for ch in lowered]
    slug = ''.join(c for c in ''.join(chars) if c.isalnum() or c == '-')
    return slug[:110] or 'topic'


def _split_old_stmt_solution(chunk: str):
    """
    Для старого формата разделяет условие и решение по маркеру-решения.
    Возвращает (stmt_raw, solution_raw).
    solution_raw пустой, если маркера нет.
    """
    m = _SOLUTION_MARKER_RE.search(chunk)
    if not m:
        return chunk, ''
    return chunk[:m.start()], chunk[m.end():]


# ── Основной парсер ───────────────────────────────────────────────────────────

def parse_problems_from_tex(content: str):
    """
    Парсит .tex файл, возвращает список:
      {title, statement, subitems, solution}

    Поддерживает:
      - Новый МатЭк: \\problem{}{stmt}{\\n sub1 \\n sub2} + \\solution{}{}
      - Старый: \\problem текст [\\Subitem] + [\\textbf{Решение} / \\hrulefill + решение]
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

        opt_num, pos_after_num = _extract_optional(content, pos)
        if opt_num is not None and opt_num.strip().isdigit():
            pos = pos_after_num

        peek = pos
        while peek < len(content) and content[peek] in ' \t':
            peek += 1

        if peek < len(content) and content[peek] == '{':
            # ── Новый МатЭк формат ──────────────────────────────────────
            label, pos = _extract_braced(content, pos)
            if label is None:
                continue

            title, pos_after_title = _extract_optional(content, pos)
            if title is not None:
                pos = pos_after_title
            else:
                title = ''

            stmt, pos = _extract_braced(content, pos)
            if not stmt or not stmt.strip():
                continue
            stmt = stmt.strip()

            subitems_raw = ''
            peek2 = pos
            while peek2 < len(content) and content[peek2] in ' \t\n\r':
                peek2 += 1
            if peek2 < len(content) and content[peek2] == '{':
                sub_content, pos = _extract_braced(content, pos)
                if sub_content is not None:
                    subitems_raw = sub_content

            # Ищем \solution
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
            # ── Старый формат ──────────────────────────────────────────
            chunk = content[pstart + len('\\problem'):next_pstart]

            # Разбиваем на подпункты
            parts = _SUBITEM_RE.split(chunk)
            main_raw = parts[0]
            subitems_raw_list = parts[1:]

            # В основном тексте ищем маркер решения
            stmt_raw, solution_raw = _split_old_stmt_solution(main_raw)

            results.append({
                'title': '',
                'statement': stmt_raw,
                'subitems': subitems_raw_list,
                'solution': solution_raw,
            })

    return results


# ── Вспомогательное: является ли путь «решалкой» ─────────────────────────────

def _is_reshалка(member_name: str) -> bool:
    nl = member_name.lower()
    return 'решалк' in nl or 'solution' in nl.split('/')[-1].lower()


# ── Команда ──────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = 'Импортирует задачи из файлов Решалки в архивах Archive 3 (olmat41)'

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

        # ── Источник ─────────────────────────────────────────────────────────
        source, created_src = Source.objects.get_or_create(
            name='Решалки Олмат (olmat41)',
            defaults={
                'kind': 'авторские материалы',
                'note': 'Файлы из папок «Решалки» архива olmat41 (Archive 3). '
                        'Задачи с развёрнутыми решениями.',
            },
        )
        self.stdout.write(
            f'Источник «{source.name}» '
            f'{"создан" if created_src else "найден"}: #{source.pk}'
        )

        job = Job.objects.create(
            kind=Job.Kind.IMPORT,
            status=Job.Status.RUNNING,
            params={'zip_dir': str(zip_dir), 'dry_run': dry_run},
        )
        self.stdout.write(f'Job #{job.pk} создан')

        existing_hashes: set = set(
            Problem.objects.exclude(content_hash='').values_list('content_hash', flat=True)
        )
        topic_cache: dict = {t.name: t for t in Topic.objects.all()}

        # ── Шаг 1: парсим решалки ─────────────────────────────────────────────
        all_records = []
        files_with_problems = 0
        tex_files_checked = 0

        for zip_path in sorted(zip_dir.glob('*.zip')):
            try:
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    for member in zf.infolist():
                        if not member.filename.endswith('.tex'):
                            continue
                        if member.file_size < 300:
                            continue
                        nl = member.filename.lower()
                        if 'preamble' in nl or nl.endswith('main.tex'):
                            continue

                        # Только файлы из папок Решалки / Solution
                        if not _is_reshалка(member.filename):
                            continue

                        tex_files_checked += 1
                        try:
                            content = zf.read(member).decode('utf-8', errors='replace')
                        except Exception:
                            continue

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

                        source_note = f'{zip_path.name} / {member.filename}'
                        if author:
                            source_note += f' (автор: {author})'

                        try:
                            problems_raw = parse_problems_from_tex(content)
                        except Exception as exc:
                            self.stderr.write(
                                f'  Ошибка парсинга «{source_note[:60]}»: {exc}'
                            )
                            continue

                        if problems_raw:
                            files_with_problems += 1

                        for rec in problems_raw:
                            stmt = clean_latex(rec['statement'])
                            if not stmt or len(stmt) < 15:
                                continue
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

            except zipfile.BadZipFile as exc:
                self.stderr.write(f'  Повреждённый архив: {zip_path.name}: {exc}')
            except Exception as exc:
                self.stderr.write(f'  Ошибка {zip_path.name}: {exc}')

        total = len(all_records)
        unique_count = sum(
            1 for r in all_records if r['content_hash'] not in existing_hashes
        )

        self.stdout.write(
            f'Проверено .tex Решалки файлов: {tex_files_checked}\n'
            f'Файлов с задачами: {files_with_problems}\n'
            f'Задач собрано: {total}, уникальных: {unique_count}'
        )

        if dry_run:
            job.status = Job.Status.DONE
            job.finished_at = timezone.now()
            job.result = {'dry_run': True, 'unique': unique_count, 'total': total}
            job.save(update_fields=['status', 'finished_at', 'result'])
            self.stdout.write(self.style.SUCCESS(
                f'\nDry-run завершён.\n'
                f'  Уникальных: {unique_count} из {total}\n'
                f'  Дублей с базой: {total - unique_count}'
            ))
            return

        # ── Шаг 2: сохраняем ─────────────────────────────────────────────────
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
                        self.stderr.write(
                            f'  Ошибка записи «{rec["title"][:50]}»: {exc}'
                        )

            done = min(batch_start + BATCH_SIZE, total)
            progress = int(done / total * 100) if total else 100

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
            f'  Файлов Решалки с задачами: {files_with_problems}\n'
            f'  Создано задач:             {created}\n'
            f'  Пропущено (дубли):         {skipped}\n'
            f'  Ошибок:                    {errors}\n'
            f'  Job #{job.pk}: {job.status}'
        ))
