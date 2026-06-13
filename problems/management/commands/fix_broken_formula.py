# -*- coding: utf-8 -*-
"""
Сессия H3, этап 2 — разорванные формулы (самый деликатный класс).

РЕШЕНИЕ ПО ИТОГАМ DRY-RUN: автоматическая склейка НЕ применяется.
Причина: «безопасный» подкласс (два соседних инлайн-$…$, разделённых переносом,
с висячим оператором) на реальных данных на 23/41 поле приходится на источник
#23 КСИГМА (OCR-мусор), где окружающий текст формулы нечитаем и склейка двух
обрывков ничего не чинит, а лишь маскирует один симптом. Риск молча испортить
формулу выше пользы. По ТЗ этапа 2: «лучше недочинить, чем сломать».

Поэтому команда — ТОЛЬКО детектор (ничего не меняет). Выдаёт три списка:
  02_broken_formula_ids.txt       — все задачи-кандидаты (запись);
  02_broken_formula_gate_ids.txt  — реально битые формулы В УСЛОВИИ среди
                                     ВИДИМЫХ задач → на шлюз (этап 7);
  02_broken_formula_manual.txt    — поля на ручной разбор (cases/√/знаменатель).

Запуск: ./venv/bin/python manage.py fix_broken_formula [--examples N] [--source-id N]
"""
import os
import re

from django.core.management.base import BaseCommand

from problems.models import Problem, ProblemPart, SourceReference

REPORT_DIR = 'reports/sessionH3'

# настоящие глифы систем уравнений, собранные PDF по символу на строку
# (БЕЗ литерального «{» — иначе ловит любую LaTeX-команду)
CASES_GLYPHS = '⎧⎨⎩⎰⎱﹛︷︸'
# два соседних инлайн-$…$-блока, разделённых только пробелами/переносом
ADJ_RE = re.compile(r'\$[^$\n]*\$[ \t]*\n[ \t]*\$[^$\n]*\$')
JOIN = re.compile(r'\$[ \t]*\n[ \t]*\$')
# висячий мат-оператор в конце куска формулы (формула не закончена)
DANGLING = re.compile(r'(?:[-+=<>≤≥⩽⩾⋅·*/−±]|\\le|\\ge|\\leqslant|\\geqslant'
                      r'|\\cdot|\\times|\\pm|\\to|\\frac|\\sqrt)\s*$')
# дробь, разорванная переносом: «…число$\n$переменная…» (100$\n$Q = 100/Q)
FRACTION_SPLIT = re.compile(r'\d[ \t]*\$[ \t]*\n[ \t]*\$[ \t]*[A-Za-zА-Яа-яЁё]')
MATH_FRAG = re.compile(r'[=<>≤≥⩽⩾+\-*/^_√∑∏∫∈≠≈⋅·−±]|\$|\\[a-zA-Z]')


def has_cases(text):
    return any(g in text for g in CASES_GLYPHS)


def short_run(text, maxlen=12, need=3):
    """≥3 подряд коротких (<maxlen) строк-мат-фрагментов без длинных слов."""
    run = 0
    for ln in text.split('\n'):
        s = ln.strip()
        if 0 < len(s) <= maxlen and MATH_FRAG.search(s) \
           and not re.search(r'[А-Яа-яA-Za-z]{4,}', s):
            run += 1
            if run >= need:
                return True
        else:
            run = 0
    return False


def dangling_join(text):
    """Перед/после границы $\\n$ висит оператор (формула продолжается)."""
    for m in JOIN.finditer(text):
        head = text[:m.start() + 1]
        lo = head.rfind('$', 0, len(head) - 1)
        inner = head[lo + 1:-1] if lo != -1 else head
        if DANGLING.search(inner):
            return True
        tail = text[m.end() - 1:]
        nc = tail.find('$', 1)
        ni = tail[1:nc] if nc != -1 else tail[1:]
        if re.match(r'\s*(?:[-+=<>≤≥⋅·*/−±]|\\le|\\ge|\\cdot)', ni):
            return True
    return False


def field_signal(text):
    """Какой сигнал разорванной формулы у поля (или None). Для записи/ручного
    разбора — широкий набор сигналов."""
    if not text:
        return None
    if has_cases(text):
        return 'cases'
    if short_run(text):
        return 'short_run'
    if ADJ_RE.search(text):
        if FRACTION_SPLIT.search(text):
            return 'fraction_split'
        if dangling_join(text):
            return 'dangling'
        return 'adj_benign'   # два полных соседних $…$ — обычно НЕ битьё
    return None


def gate_worthy_statement(text):
    """ВЫСОКОТОЧНЫЙ сигнал «формула реально разорвана В УСЛОВИИ»:
    либо глифы cases-системы, либо ≥2 границ $…$\\n$…$ (одиночная граница часто
    легитимна — две формулы; ≥2 — почти всегда шреддинг формулы по строкам).
    Одиночные dangling/fraction/short_run НЕ гейтим (ложные срабатывания на
    индексах q_2$\\n$q_1 и вариантах MCQ «а) 1/5 б) 1/4»)."""
    if not text:
        return False
    if has_cases(text):
        return True
    return len(JOIN.findall(text)) >= 2


class Command(BaseCommand):
    help = 'H3 этап 2: ДЕТЕКТОР разорванных формул (без правок)'

    def add_arguments(self, parser):
        parser.add_argument('--examples', type=int, default=20)
        parser.add_argument('--source-id', type=int, default=None)

    def handle(self, *args, **o):
        os.makedirs(REPORT_DIR, exist_ok=True)
        pid_src = dict(
            SourceReference.objects.values_list('problem_id', 'source_id'))

        # видимость
        visible = set(
            Problem.objects.filter(status='published',
                                   needs_quality_review=False)
            .values_list('id', flat=True))

        cand_ids = set()
        gate_ids = set()          # битьё В УСЛОВИИ среди видимых
        manual_rows = []          # (kind, pid, partid, fld, signal, snippet)
        examples = []

        def consider(kind, pid, partid, fld, text):
            sig = field_signal(text)
            if sig is None or sig == 'adj_benign':
                # adj_benign фиксируем только в кандидаты (для записи)
                if sig == 'adj_benign':
                    cand_ids.add(pid)
                return
            cand_ids.add(pid)
            is_statement = (fld == 'statement')
            if is_statement and pid in visible and gate_worthy_statement(text):
                gate_ids.add(pid)
            manual_rows.append((kind, pid, partid, fld, sig, text[:120]))
            if len(examples) < o['examples']:
                examples.append((kind, pid, partid, fld, sig, text))

        pq = Problem.objects.all().only('id', 'statement', 'answer', 'solution')
        if o['source_id']:
            pq = pq.filter(source_references__source_id=o['source_id'])
        for p in pq:
            for fld in ('statement', 'answer', 'solution'):
                consider('Problem', p.id, None, fld, getattr(p, fld))
        ptq = ProblemPart.objects.all().only('id', 'problem_id',
                                             'statement', 'answer')
        if o['source_id']:
            ptq = ptq.filter(
                problem__source_references__source_id=o['source_id'])
        for pt in ptq:
            for fld in ('statement', 'answer'):
                consider('ProblemPart', pt.problem_id, pt.id, fld,
                         getattr(pt, fld))

        # сигналы по типам
        from collections import Counter
        sig_count = Counter(r[4] for r in manual_rows)
        self.stdout.write(f'Задач-кандидатов (любой сигнал): {len(cand_ids)}')
        self.stdout.write(f'Полей с битьём (не benign): {len(manual_rows)} '
                          f'{dict(sig_count)}')
        self.stdout.write(f'На ШЛЮЗ (битьё в условии, видимые): {len(gate_ids)}')

        # списки
        with open(os.path.join(REPORT_DIR, '02_broken_formula_ids.txt'),
                  'w', encoding='utf-8') as f:
            f.write('# все задачи-кандидаты разорванных формул (этап 2 H3)\n')
            f.write('\n'.join(map(str, sorted(cand_ids))) + '\n')
        with open(os.path.join(REPORT_DIR, '02_broken_formula_gate_ids.txt'),
                  'w', encoding='utf-8') as f:
            f.write('# битьё формул В УСЛОВИИ среди видимых → шлюз (этап 7)\n')
            f.write('\n'.join(map(str, sorted(gate_ids))) + '\n')
        with open(os.path.join(REPORT_DIR, '02_broken_formula_manual.txt'),
                  'w', encoding='utf-8') as f:
            f.write('# поля на ручной разбор разорванных формул (этап 2 H3)\n')
            f.write('# kind\tproblem_id\tpart_id\tfield\tсигнал\tфрагмент\n')
            for kind, pid, partid, fld, sig, snip in sorted(manual_rows,
                                                            key=lambda r: r[1]):
                snip1 = snip.replace('\n', '⏎')
                f.write(f'{kind}\t{pid}\t{partid}\t{fld}\t{sig}\t{snip1}\n')

        self.stdout.write(f'\n=== ПРИМЕРЫ (до {o["examples"]}) ===')
        for kind, pid, partid, fld, sig, text in examples:
            src = pid_src.get(pid)
            self.stdout.write(f'--- {kind} #{pid} part={partid} .{fld} '
                              f'[{sig}] src={src} ---')
            self.stdout.write(f'  {text[:200]!r}')

        self.stdout.write(self.style.WARNING(
            '\nДЕТЕКТОР: ничего не изменено. Авто-склейка по этому классу '
            'НЕ применяется (см. docstring). Списки в reports/sessionH3/.'))
