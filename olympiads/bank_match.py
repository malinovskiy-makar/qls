"""Сопоставление задания пакета олимпиад с задачей, которая УЖЕ есть в банке.

Перенос правила разведки 30.10.2026 (скрипты сессии `q1_verify.py` и
`q1_rule2.py`, в репозиторий они не попадали). Проверено тогда: эталон 170
из 173, глазами 120 из 120 принятых и 25 из 25 отвергнутых. Правило:

1. **Сито.** Ищем кандидата по нормализованному условию: точное совпадение
   условия, условия с пунктами, первых 150 знаков, иначе — по 12-символьным
   фрагментам (≥ 85 % общих в обе стороны). Если не нашлось — ещё раз без
   вступления раздела теста (`section_md`), потом по тексту задачи банка
   пакета (`bank/problems.jsonl`): там текст «как в банке».
2. **Приговор — только по тексту САМОГО задания.** Сходство (`ratio`
   difflib на нормализованном тексте) ≥ 0,90 И ни одно число не заменено
   другим числом И последовательность знаков операций та же
   (`operator_sequence`). Дописанное или выпавшее число — не замена; «15»
   вместо «5» — другой вариант задачи, такая пара отвергается.

⚠️ `bank.problem_id` ПАКЕТА — НЕ НАШ id. Номера — из локальной базы Андрея:
из 1 349 совпавших по номеру у 743 другое название. Номер здесь не
участвует нигде; текст задачи банка пакета — только сито из шага 1, а
приговор выносит текст задания.

⚠️ Нормализация здесь СВОЯ, а не `problems.text_dedup.normalize_for_compare`:
правило замерено именно на ней (буквы и цифры, без TeX-команд), и порог
0,90 откалиброван под неё. Другая нормализация — другой порог.
"""
import collections
import difflib
import re

ACCEPT = 0.90          # порог сходства текста (приговор)
SIEVE_SHARE = 0.85     # доля общих фрагментов у кандидата сита
SHINGLE = 12           # длина фрагмента сита
MIN_LEN = 40           # короче — сито не ищет: слишком много случайных совпадений
PREFIX = 150           # длина префикса для третьего признака сита
BUCKET_MAX = 300       # фрагменты, встречающиеся чаще, — шум («спрос и предложение»)

_FIGURE = re.compile(r'\[\[figure:[0-9a-f]+\]\]')
_TEX = re.compile(r'\\[a-z]+')
_NOT_ALNUM = re.compile(r'[^0-9a-zа-я]+')
_DIGIT = re.compile(r'\d')


def norm(text):
    """Только буквы и цифры, нижний регистр, «ё» = «е», без TeX-команд."""
    text = (text or '').lower().replace('ё', 'е')
    text = _FIGURE.sub(' ', text)
    text = _TEX.sub(' ', text)
    return _NOT_ALNUM.sub('', text)


def ratio(a, b):
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def stem(task):
    """Условие без вступления раздела теста: у банка его обычно нет."""
    return task['statement_md'].replace(task.get('section_md') or '', '', 1)


def part_texts(task):
    return [p.get('text') or '' for p in task.get('parts') or []]


# ── знаки операций ────────────────────────────────────────────────────────
#
# ⚠️ НОРМАЛИЗАЦИЯ `norm` СЛЕПА К ЗНАКАМ: «P = 100 − 2Q» и «P = 100 + 2Q» для
# неё один текст, а правило «ни одно число не заменено» знак не ловит —
# числа там одинаковые. Поэтому отдельный приговор: последовательность
# знаков операций и сравнений в задании и в кандидате обязана совпасть
# (решение владельца 30.10). Разные виды записи одного знака сводятся к
# одному: все минусы и тире → «−», `\cdot`, `\times`, `·` → «×», `\frac`,
# `\over`, `\div`, `÷` → «/», `\le`, `⩽` → «≤» и т. д.
#
# Что знаком НЕ считается (замер 30.10 на 1 310 связях — это был шум
# счётчика, а не формулы): `*` (это «Q*», оптимум, и жирный Markdown),
# маркер списка «- » в начале строки, косые черты в ссылках, диапазоны
# без пробелов «22-23», «5—8» вне формулы.
_TEX_OPS = [
    (re.compile(r'\\(?:cdot|times|ast)(?![a-zA-Z])'), '×'),
    (re.compile(r'\\(?:frac|dfrac|tfrac|over|div)(?![a-zA-Z])'), '/'),
    (re.compile(r'\\(?:leq|leqslant|le)(?![a-zA-Z])'), '≤'),
    (re.compile(r'\\(?:geq|geqslant|ge)(?![a-zA-Z])'), '≥'),
    (re.compile(r'\\(?:neq|ne)(?![a-zA-Z])'), '≠'),
    (re.compile(r'\\(?:lt)(?![a-zA-Z])'), '<'),
    (re.compile(r'\\(?:gt)(?![a-zA-Z])'), '>'),
]
_CHAR_OPS = str.maketrans({'·': '×', '∙': '×', '⋅': '×', '÷': '/', '⩽': '≤',
                           '⩾': '≥', '＝': '='})
_DASH_CHARS = '-‐‑‒–—―−'
_MATH = re.compile(r'\$\$.+?\$\$|\$.+?\$', re.S)
_OPS_IN_MATH = re.compile(r'[+\-‐‑‒–—―−×/=<>≤≥≠]')
_OPS_IN_PROSE = re.compile(r'[+×/=<>≤≥≠]|(?P<dash>[-‐‑‒–—―−])')
# Тире вне формулы — знак, только если стоит между «формульными» соседями
# (цифра, латиница, скобка): «100 - 2P» — минус, «предложение — функцией»
# и «кто-то» — нет.
_MATHY = re.compile(r'[0-9A-Za-z)(\]\[}{]')
_URL = re.compile(r'https?://\S+|www\.\S+')
_RANGE = re.compile(r'(?<!\w)(?<!\d[.,])(\d+)[-‐‑‒–—―−](\d+)(?!\w)(?![.,]\d)')


def _prose_ops(text):
    out = []
    for m in _OPS_IN_PROSE.finditer(text):
        if m.group('dash') is None:
            if m.group() == '>' and not text[:m.start()].split('\n')[-1].strip():
                continue            # цитата Markdown «> …» в начале строки, не знак
            out.append(m.group())
            continue
        line_before = text[:m.start()].split('\n')[-1]
        if not line_before.strip():
            continue                # маркер списка «- …», не минус
        left = text[:m.start()].rstrip()
        right = text[m.end():].lstrip()
        if left and right and _MATHY.match(left[-1]) and _MATHY.match(right[0]):
            out.append('−')
    return out


def operator_sequence(text):
    """Знаки операций и сравнений текста по порядку, в одном написании."""
    text = text or ''
    for pattern, sign in _TEX_OPS:
        text = pattern.sub(sign, text)
    text = text.translate(_CHAR_OPS)
    text = _URL.sub(' ', text)
    out, pos = [], 0
    for m in _MATH.finditer(text):
        out += _prose_ops(_RANGE.sub(r'\1 \2', text[pos:m.start()]))
        for op in _OPS_IN_MATH.findall(m.group()):
            out.append('−' if op in _DASH_CHARS else op)
        pos = m.end()
    out += _prose_ops(_RANGE.sub(r'\1 \2', text[pos:]))
    return out


def number_replaced(a, b):
    """Заменено ли в `b` хоть одно число из `a` другим числом."""
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return any(op == 'replace' and _DIGIT.search(a[i1:i2])
               and _DIGIT.search(b[j1:j2])
               for op, i1, i2, j1, j2 in matcher.get_opcodes())


class BankIndex:
    """Индекс банка в памяти. Строится один раз на прогон.

    `rows` — (id, statement, status, duplicate_of_id, human_review),
    `parts` — {id задачи: [тексты пунктов по порядку]}. Из базы —
    `BankIndex.from_db()`; конструктор базу не трогает, чтобы правило можно
    было проверить в отдельном процессе без Django.
    """

    @classmethod
    def from_db(cls):
        from problems.models import Problem, ProblemPart
        rows = Problem.objects.values_list(
            'id', 'statement', 'status', 'duplicate_of_id', 'human_review')
        parts = collections.defaultdict(list)
        for pid, text in (ProblemPart.objects.order_by('problem_id', 'order', 'id')
                          .values_list('problem_id', 'statement')):
            parts[pid].append(text or '')
        return cls(rows, parts)

    def __init__(self, rows, parts):
        self.ours = {row[0]: tuple(row[1:]) for row in rows}
        self.idx_stmt = collections.defaultdict(set)
        self.idx_full = collections.defaultdict(set)
        self.idx_pref = collections.defaultdict(set)
        self.inv = collections.defaultdict(set)
        self.ournorm, self.ourfull, self.ourraw = {}, {}, {}
        for pid, (statement, _s, _d, _h) in self.ours.items():
            # Сырой текст «условие + пункты» — для приговора по знакам.
            self.ourraw[pid] = '\n'.join([statement or ''] + list(parts.get(pid, ())))
            n = norm(statement)
            self.ournorm[pid] = n
            if len(n) >= MIN_LEN:
                self.idx_stmt[n].add(pid)
                self.idx_pref[n[:PREFIX]].add(pid)
                for i in range(len(n) - SHINGLE):
                    self.inv[n[i:i + SHINGLE]].add(pid)
            full = n + norm(''.join(parts.get(pid, ())))
            self.ourfull[pid] = full
            if len(full) >= MIN_LEN:
                self.idx_full[full].add(pid)

    def find(self, statement, parts):
        """Сито: (признак, множество кандидатов)."""
        n = norm(statement)
        full = n + norm(''.join(parts))
        if len(n) >= MIN_LEN and self.idx_stmt.get(n):
            return 'stmt', self.idx_stmt[n]
        if len(full) >= MIN_LEN and self.idx_full.get(full):
            return 'full', self.idx_full[full]
        if len(n) >= PREFIX and self.idx_pref.get(n[:PREFIX]):
            return 'prefix150', self.idx_pref[n[:PREFIX]]
        if len(n) < MIN_LEN:
            return 'short', set()
        mine = {n[i:i + SHINGLE] for i in range(max(1, len(n) - SHINGLE))}
        counts = collections.Counter()
        for shingle in mine:
            bucket = self.inv.get(shingle, ())
            if len(bucket) < BUCKET_MAX:
                for pid in bucket:
                    counts[pid] += 1
        # ⚠️ Сортировка с номером задачи, а не `most_common`: при равных
        # счётах тот отдаёт порядок вставки, а он зависит от случайного
        # хеширования строк — от запуска к запуску разные кандидаты.
        top = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:5]
        best = {pid for pid, k in top
                if k / max(1, len(mine)) >= SIEVE_SHARE
                and k / max(1, len(self.ournorm[pid]) - SHINGLE) >= SIEVE_SHARE}
        return ('fuzzy85', best) if best else ('none', set())

    def original(self, pid):
        """По цепочке `duplicate_of` — к оригиналу."""
        seen = set()
        while (self.ours[pid][2] and self.ours[pid][2] in self.ours
               and pid not in seen):
            seen.add(pid)
            pid = self.ours[pid][2]
        return pid

    def rank(self, pid):
        """Чем меньше, тем лучше: опубликованная, одобренная, не копия."""
        status, human = self.ours[pid][1], self.ours[pid][3]
        return (status != 'published', human != 'approved',
                status == 'duplicate', pid)

    def score(self, task, pid):
        mine = norm(stem(task))
        return max(ratio(mine + norm(''.join(part_texts(task))),
                         self.ourfull[pid]),
                   ratio(mine, self.ournorm[pid]))

    def verdict(self, task, pid):
        """(сходство, причина отказа или None) для одного кандидата."""
        score = self.score(task, pid)
        if score < ACCEPT:
            return score, 'текст < 0,90'
        if number_replaced(norm(stem(task)), self.ournorm[pid]):
            return score, 'текст ≥ 0,90, число заменено'
        mine = '\n'.join([stem(task)] + part_texts(task))
        if operator_sequence(mine) != operator_sequence(self.ourraw[pid]):
            return score, 'знаки операций не совпали'
        return score, None

    def pick(self, task, ids):
        """Из нескольких кандидатов — одна задача (оригиналы по `duplicate_of`).

        ⚠️ ПРИГОВОР — КАЖДОМУ КАНДИДАТУ, ВЫБОР — СРЕДИ ПРОШЕДШИХ. Разведка
        сначала выбирала лучшего по статусу, а приговор выносила только ему.
        При двух одобренных «Линейная кривая предложения…» и «Ломаная
        линейная кривая…» решал порядок в множестве — то есть случайное
        хеширование строк. Теперь: прошедшие приговор → лучший по статусу
        → при равенстве самый похожий текст → меньший номер.
        """
        resolved = {self.original(pid) for pid in ids}
        verdicts = {pid: self.verdict(task, pid) for pid in resolved}
        passed = [pid for pid, (_, why) in verdicts.items() if why is None]
        pool = passed or list(resolved)

        def key(pid):
            status, human, dup, number = self.rank(pid)
            return (status, human, dup, -round(verdicts[pid][0], 6), number)
        if passed:
            best = min(pool, key=key)
        else:   # для отчёта — самый похожий из отвергнутых
            best = min(pool, key=lambda pid: (-verdicts[pid][0], pid))
        return best, verdicts[best]

    def match(self, task, package_bank=None):
        """Вердикт по заданию: dict(problem_id|None, how, ratio, reason).

        `package_bank` — словарь задач банка пакета по их номеру; нужен
        только как запасное сито (см. шапку модуля).
        """
        parts = part_texts(task)
        how, ids = self.find(task['statement_md'], parts)
        if not ids:
            how, ids = self.find(stem(task), parts)
        bank = task.get('bank')
        if not ids and bank and package_bank and bank['problem_id'] in package_bank:
            record = package_bank[bank['problem_id']]
            how, ids = self.find(
                record['statement'],
                [p.get('text') or p.get('statement') or ''
                 for p in record.get('parts') or []])
            how = 'bank:' + how
        if not ids:
            return {'problem_id': None, 'how': how, 'ratio': None,
                    'reason': 'нет кандидата'}
        pid, (score, reason) = self.pick(task, ids)
        if reason is None:
            return {'problem_id': pid, 'how': how, 'ratio': score,
                    'reason': 'принято'}
        return {'problem_id': None, 'how': how, 'ratio': score,
                'reason': reason, 'candidate': pid}
