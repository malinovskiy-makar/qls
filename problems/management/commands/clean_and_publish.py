"""
Management command: clean_and_publish

Очищает LaTeX-артефакты из draft-задач и публикует их.
Математические формулы ($...$, $$...$$, \\(...\\), \\[...\\]) НЕ трогаются.

Запуск:
    ./venv/bin/python manage.py clean_and_publish
    ./venv/bin/python manage.py clean_and_publish --dry-run
    ./venv/bin/python manage.py clean_and_publish --source 3
"""

import re

from django.core.management.base import BaseCommand
from django.db import transaction

from problems.models import Problem, ProblemPart


BATCH_SIZE = 500

# Маркеры LaTeX-шаблонов — такие задачи → archived
TEMPLATE_MARKERS = [r'\IfValueTF', r'\NewDocumentCommand', r'\DeclareDocumentCommand',
                    '#1', '#2', '#3']

# Названия math-окружений, которые нужно защитить
_MATH_ENV_NAMES = (
    'align', 'align*', 'aligned', 'alignat', 'alignat*',
    'equation', 'equation*',
    'gather', 'gather*', 'gathered',
    'multline', 'multline*',
    'eqnarray', 'eqnarray*',
    'cases', 'dcases',
    'array', 'matrix', 'pmatrix', 'bmatrix', 'vmatrix', 'Vmatrix',
    'Bmatrix', 'smallmatrix',
    'split',
)


def _build_math_pattern():
    env_alts = '|'.join(re.escape(e) for e in _MATH_ENV_NAMES)
    return re.compile(
        r'(?:'
        # Именованные math-окружения: \begin{align}...\end{align}
        r'\\begin\{(?:' + env_alts + r')\}.*?\\end\{(?:' + env_alts + r')\}'
        r'|'
        # $$...$$  (до $...$!)
        r'\$\$(?:(?!\$\$).)*?\$\$'
        r'|'
        # $...$
        r'\$(?!\$)(?:(?!\$).)*?\$'
        r'|'
        # \[...\]
        r'\\\[.*?\\\]'
        r'|'
        # \(...\)
        r'\\\(.*?\\\)'
        r')',
        re.DOTALL,
    )


_MATH_RE = _build_math_pattern()

# Одинарный бэкслэш: контент в фигурных скобках (1 уровень вложенности)
_BRACE1 = r'\{((?:[^{}]|\{[^{}]*\})*)\}'


def _protect_math(text):
    """Заменяет math-блоки на плейсхолдеры. Возвращает (new_text, list_of_blocks)."""
    blocks = []

    def _replace(m):
        idx = len(blocks)
        blocks.append(m.group(0))
        return f'\x00M{idx}\x00'

    return _MATH_RE.sub(_replace, text), blocks


def _restore_math(text, blocks):
    for i, block in enumerate(blocks):
        text = text.replace(f'\x00M{i}\x00', block)
    return text


# ─────────────────────────── обработка списков ───────────────────────────────

def _process_list_env(m):
    """\\begin{enumerate/itemize}...\\end{...} → строки с «• »."""
    inner = m.group(1)
    # Разбить по \item (с опциональным [метка])
    parts = re.split(r'\\item(?:\[[^\]]*\])?', inner)
    lines = []
    for part in parts:
        part = part.strip()
        if part:
            lines.append('• ' + part)
    return '\n'.join(lines)


# ─────────────────────────── основная очистка ────────────────────────────────

def clean_text(text: str) -> str:
    """Очищает один текстовый блок от LaTeX-форматирования."""
    if not text:
        return text

    # 1. Защитить математику плейсхолдерами
    text, math_blocks = _protect_math(text)

    # 2. Убрать \headic{}{}{}{} (метаданные ЛШ-файлов) — ДО чистки %,
    #    чтобы хвостовые «\headic{...} %comment» не остались
    text = re.sub(r'\\headic' + r'\{[^}]*\}' * 4, '', text)

    # 3. Убрать строки-комментарии (начинаются с %, возможно со пробелами)
    text = re.sub(r'(?m)^[ \t]*%[^\n]*', '', text)

    # 4. \href{url}{текст} → текст
    text = re.sub(r'\\href' + r'\{[^}]*\}' + _BRACE1, r'\1', text)

    # 5. enumerate / itemize → маркированный список
    _list_re = re.compile(
        r'\\begin\{(?:enumerate|itemize)\}(.*?)\\end\{(?:enumerate|itemize)\}',
        re.DOTALL,
    )
    # Применяем пока есть совпадения (вложенные списки)
    prev = None
    while prev != text:
        prev = text
        text = _list_re.sub(_process_list_env, text)

    # 6. Оставшиеся \item → «• »
    text = re.sub(r'\\item(?:\[[^\]]*\])?', '• ', text)

    # 7. \textbf{текст} → **текст**
    text = re.sub(r'\\textbf' + _BRACE1, r'**\1**', text)

    # 8. \emph{текст}, \textit{текст} → *текст*
    text = re.sub(r'\\(?:emph|textit)' + _BRACE1, r'*\1*', text)

    # 9. \text{текст} → текст (вне math; внутри math уже защищено)
    text = re.sub(r'\\text' + _BRACE1, r'\1', text)

    # 10. \section*?{...}, \subsection*?{...}, \subsubsection*?{...} → текст
    text = re.sub(r'\\(?:sub)*section\*?' + _BRACE1, r'\1', text)

    # 11. \rule[opt]{...}{...} → удалить
    text = re.sub(r'\\rule(?:\[[^\]]*\])?\{[^}]*\}\{[^}]*\}', '', text)

    # 12. \label{...}, \ref{...}, \eqref{...}, \cite{...} → удалить
    text = re.sub(r'\\(?:label|ref|eqref|cite|pageref)\{[^}]*\}', '', text)

    # 13. Одиночные inline-команды без аргументов → удалить
    #    Используем (?![a-zA-Z]) вместо \b — \b не работает перед кириллицей
    _inline_cmds = (
        r'noindent|medskip|bigskip|smallskip|newline|par|clearpage|newpage'
        r'|hfill|vfill|centering|raggedright|raggedleft'
    )
    text = re.sub(r'\\(?:' + _inline_cmds + r')(?![a-zA-Z])', '', text)

    # 14. \vspace*?{...}, \hspace*?{...} → удалить
    text = re.sub(r'\\[vh]space\*?\{[^}]*\}', '', text)

    # 15. Удалить оставшиеся \begin{...}[opt]{...} и \end{...} теги
    #     (содержимое оставляем — убираем только теги окружений)
    text = re.sub(r'\\begin\{[^}]*\}(?:\[[^\]]*\])*(?:\{[^}]*\})*', '', text)
    text = re.sub(r'\\end\{[^}]*\}', '', text)

    # 16. \\ (перенос строки в LaTeX) → newline
    text = re.sub(r'\\\\[ \t]*', '\n', text)

    # 17. ~ (неразрывный пробел) → обычный пробел
    text = text.replace('~', ' ')

    # 18. Убрать одиночные висячие фигурные скобки (артефакты окружений)
    text = re.sub(r'^\s*[{}]\s*$', '', text, flags=re.MULTILINE)

    # 19. Нормализовать пустые строки: 3+ подряд → одна
    text = re.sub(r'\n{3,}', '\n\n', text)

    # 20. Убрать пробелы в начале/конце строк и всего текста
    lines = [line.rstrip() for line in text.split('\n')]
    text = '\n'.join(lines).strip()

    # 21. Восстановить математику
    text = _restore_math(text, math_blocks)

    return text


# ─────────────────────────── классификация ───────────────────────────────────

def classify(statement: str) -> str:
    """Возвращает 'archived' или 'published'."""
    if len(statement) < 15:
        return 'archived'
    for marker in TEMPLATE_MARKERS:
        if marker in statement:
            return 'archived'
    return 'published'


def archive_reason(statement: str) -> str:
    if len(statement) < 15:
        return f'короткий текст ({len(statement)} симв.)'
    for marker in TEMPLATE_MARKERS:
        if marker in statement:
            return f'шаблон ({marker})'
    return ''


# ─────────────────────────── команда ─────────────────────────────────────────

class Command(BaseCommand):
    help = 'Очищает LaTeX из draft-задач и публикует их (или архивирует мусор).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Только статистика, без изменений в базе.',
        )
        parser.add_argument(
            '--source', type=int, default=None,
            help='ID источника (Source). Обрабатывать только задачи из него.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        source_id = options['source']

        qs = Problem.objects.filter(status='draft')
        if source_id:
            qs = qs.filter(source_references__source_id=source_id)
        qs = qs.prefetch_related('parts').order_by('id')

        # Сразу собираем все ID — иначе при публикации queryset меняется
        # и offset-based пагинация пропускает задачи
        all_ids = list(qs.values_list('id', flat=True))
        total = len(all_ids)
        self.stdout.write(f'Найдено draft-задач: {total}' +
                          (f' (источник #{source_id})' if source_id else ''))
        if total == 0:
            return

        n_published = 0
        n_archived = 0
        archive_reasons: dict[str, int] = {}
        n_cleaned = 0  # задач, где что-то изменилось

        offset = 0
        while offset < total:
            batch_ids = all_ids[offset:offset + BATCH_SIZE]
            if not batch_ids:
                break

            batch = list(
                Problem.objects.filter(id__in=batch_ids)
                .prefetch_related('parts')
            )

            updates_problem = []
            updates_parts: list[ProblemPart] = []

            for problem in batch:
                orig_stmt = problem.statement
                orig_ans = problem.answer
                orig_sol = problem.solution

                new_stmt = clean_text(orig_stmt)
                new_ans = clean_text(orig_ans)
                new_sol = clean_text(orig_sol)

                new_status = classify(new_stmt)
                changed = (
                    new_stmt != orig_stmt
                    or new_ans != orig_ans
                    or new_sol != orig_sol
                    or new_status != problem.status
                )
                if changed:
                    n_cleaned += 1

                if new_status == 'archived':
                    n_archived += 1
                    reason = archive_reason(new_stmt)
                    archive_reasons[reason] = archive_reasons.get(reason, 0) + 1
                else:
                    n_published += 1

                if not dry_run:
                    problem.statement = new_stmt
                    problem.answer = new_ans
                    problem.solution = new_sol
                    problem.status = new_status
                    updates_problem.append(problem)

                # Подпункты
                for part in problem.parts.all():
                    p_stmt = clean_text(part.statement)
                    p_ans = clean_text(part.answer)
                    p_sol = clean_text(part.solution)
                    if not dry_run and (
                        p_stmt != part.statement
                        or p_ans != part.answer
                        or p_sol != part.solution
                    ):
                        part.statement = p_stmt
                        part.answer = p_ans
                        part.solution = p_sol
                        updates_parts.append(part)

            if not dry_run:
                with transaction.atomic():
                    Problem.objects.bulk_update(
                        updates_problem, ['statement', 'answer', 'solution', 'status'],
                    )
                    if updates_parts:
                        ProblemPart.objects.bulk_update(
                            updates_parts, ['statement', 'answer', 'solution'],
                        )

            offset += BATCH_SIZE
            self.stdout.write(
                f'  обработано {min(offset, total)}/{total}...',
                ending='\r',
            )

        self.stdout.write('')
        mode = '[DRY-RUN] ' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(
            f'\n{mode}Готово. Всего задач: {total}'
        ))
        self.stdout.write(f'  Изменено текстов:  {n_cleaned}')
        self.stdout.write(self.style.SUCCESS(
            f'  → опубликовано:    {n_published}'
        ))
        self.stdout.write(self.style.WARNING(
            f'  → заархивировано: {n_archived}'
        ))
        if archive_reasons:
            self.stdout.write('  Причины архивации:')
            for reason, cnt in sorted(archive_reasons.items(),
                                       key=lambda x: -x[1]):
                self.stdout.write(f'    {reason}: {cnt}')
