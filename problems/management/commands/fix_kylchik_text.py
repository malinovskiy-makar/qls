"""
Чистка текстов КСИ Кыльчик (Source #10, 137 задач).

Что делает:
  1. Убирает «Задача N.» / «Задача N (описание).» в начале statement.
  2. Убирает OCR-мусор «adeft» в конце текста.
  3. Оборачивает чисто-математические строки в $…$:
       строки без длинных (3+) кириллических слов, с = / ≤ / ≥.
  4. Разбивает подпункты (a)/(b)/…/(а)/(б)/…/(1) из statement
       на отдельные ProblemPart — если частей ещё нет.

Запуск:
  ./venv/bin/python manage.py fix_kylchik_text              # боевой режим
  ./venv/bin/python manage.py fix_kylchik_text --dry-run    # показать до/после
"""

import re

from django.core.management.base import BaseCommand
from django.db import transaction

from problems.models import Problem, ProblemPart, Source

# ── регулярные выражения ────────────────────────────────────────────────────

# «Задача 4.» или «Задача 2 (Тренировка).»
PREFIX_RE = re.compile(r'^Задача\s+\d+(?:\s*\([^)]+\))?\.\s*')

# OCR-артефакт «adeft» в конце
ADEFT_RE = re.compile(r'\n+adeft\s*$')

# Маркер подпункта в начале строки или строки текста:
# (a), (b), …, (а), (б), …, (1) — одна буква/цифра в скобках
SPLIT_RE = re.compile(r'(?:^|\n+)\s*(\([a-zA-ZА-ЯЁа-яё1]\))\s*')

# 3+ кирилличных символа подряд = русское слово → строка не чисто-математическая
LONG_CYR = re.compile(r'[а-яёА-ЯЁ]{3,}')

# Признак уравнения/неравенства
HAS_EQ = re.compile(r'[=≤≥]')


# ── вспомогательные функции ─────────────────────────────────────────────────

def _remove_prefix(text: str) -> tuple:
    """Убрать «Задача N (описание). » в начале. Возвращает (новый_текст, изменён)."""
    m = PREFIX_RE.match(text)
    if m:
        return text[m.end():], True
    return text, False


def _remove_adeft(text: str) -> tuple:
    """Убрать «\\n\\nadeft» в конце. Возвращает (новый_текст, изменён)."""
    new = ADEFT_RE.sub('', text)
    return new, new != text


def _maybe_wrap_line(line: str) -> str:
    """
    Если строка — чисто-математическое выражение (с = / ≤ / ≥, без длинных
    кирилличных слов, без уже существующих $), оборачивает в $…$.
    """
    stripped = line.strip()
    if not stripped:
        return line
    if '$' in stripped:  # уже обёрнуто или частично — не трогаем
        return line
    if not HAS_EQ.search(stripped):
        return line
    if LONG_CYR.search(stripped):  # есть русское слово — не чисто-мат.
        return line
    # Trim trailing punctuation outside the $
    content = stripped.rstrip('.,;:')
    trailing = stripped[len(content):]
    return f'${content}${trailing}'


def _wrap_lines(text: str) -> tuple:
    """Применить _maybe_wrap_line к каждой строке. Возвращает (текст, кол-во изменений)."""
    lines = text.split('\n')
    new_lines = [_maybe_wrap_line(ln) for ln in lines]
    changed = sum(1 for a, b in zip(lines, new_lines) if a != b)
    return '\n'.join(new_lines), changed


def _split_subproblems(text: str) -> tuple:
    """
    Разбить текст на (вводная_часть, [(метка, текст), …]).
    Маркеры: (a)/(b)/…/(а)/(б)/…/(1) в начале строки или в начале строки текста.
    """
    parts = SPLIT_RE.split(text)
    # parts[0] = введение, parts[1::2] = метки «(a)» и т.д., parts[2::2] = тексты
    intro = parts[0].strip()
    subs = []
    for i in range(1, len(parts), 2):
        label = parts[i].strip('()')       # '(a)' → 'a'
        subtext = parts[i + 1].strip() if i + 1 < len(parts) else ''
        if subtext:
            subs.append((label, subtext))
    return intro, subs


# ── команда ─────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = 'Чистка задач КСИ Кыльчик: убрать prefix/adeft, обернуть мат., разбить подпункты'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Показать изменения, не сохранять',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        try:
            src = Source.objects.get(pk=10)
        except Source.DoesNotExist:
            self.stderr.write('Source #10 не найден.')
            return

        probs = Problem.objects.filter(source_references__source=src).order_by('pk')
        total = probs.count()
        self.stdout.write(f'Задач в Source #10: {total}')

        updated_stmts = 0
        created_parts = 0
        shown = 0
        MAX_SHOW = 10  # в dry-run показываем не более 10 примеров

        for p in probs:
            orig = p.statement
            text = orig

            # 1. убрать префикс
            text, did_prefix = _remove_prefix(text)

            # 2. убрать adeft
            text, did_adeft = _remove_adeft(text)

            # 3. разбить на подпункты
            intro, subs = _split_subproblems(text)

            # 4. обернуть чисто-мат. строки во вводной части
            intro_wrapped, intro_eq_cnt = _wrap_lines(intro)

            # 5. обернуть чисто-мат. строки в каждом подпункте
            subs_wrapped = []
            sub_eq_cnt = 0
            for label, subtext in subs:
                wrapped, n = _wrap_lines(subtext)
                subs_wrapped.append((label, wrapped))
                sub_eq_cnt += n

            # Новый statement = введение (подпункты уходят в ProblemPart)
            new_stmt = intro_wrapped

            has_parts_already = p.parts.count() > 0
            stmt_changed = new_stmt != orig
            will_split = bool(subs_wrapped) and not has_parts_already

            if not stmt_changed and not will_split:
                continue

            if dry_run:
                if shown < MAX_SHOW:
                    self.stdout.write(f'\n{"─" * 60}')
                    self.stdout.write(f'#{p.pk}  prefix={did_prefix}  adeft={did_adeft}  '
                                      f'подпунктов={len(subs_wrapped)}  '
                                      f'мат.строк={intro_eq_cnt + sub_eq_cnt}')
                    self.stdout.write(f'  ДО  : {repr(orig[:180])}')
                    self.stdout.write(f'  STMT: {repr(new_stmt[:180])}')
                    for lbl, st in subs_wrapped:
                        self.stdout.write(f'  ({lbl}): {repr(st[:120])}')
                    shown += 1
            else:
                with transaction.atomic():
                    p.statement = new_stmt
                    p.save(update_fields=['statement'])

                    if will_split:
                        for order, (label, subtext) in enumerate(subs_wrapped):
                            ProblemPart.objects.create(
                                problem=p,
                                label=label,
                                statement=subtext,
                                answer='',
                                order=order,
                            )
                            created_parts += 1

            updated_stmts += 1

        if dry_run:
            self.stdout.write(f'\n{"═" * 60}')
            self.stdout.write(
                f'DRY RUN: будет обновлено {updated_stmts} задач'
                f' (показано {shown} из {updated_stmts}).'
            )
        else:
            self.stdout.write(
                f'Обновлено задач: {updated_stmts}. '
                f'Создано подпунктов: {created_parts}.'
            )
