"""Чистка грязи оцифровки в задачах, залитых из пакета олимпиад (S4, ADR 0172).

Три беды, которые ученик увидит в режимах «На время» и «Без времени»:

- **A.** Условие записано дважды подряд, в двух редакциях.
- **B.** Ответ или решение вклеены в условие (по явной метке в начале строки).
- **C.** Поле решения — копия условия, разбора на деле нет.

Модуль только РЕШАЕТ, что с текстом сделать; пишет `clean_olympiad_package_tasks`.
Функции чистые: принимают текст, отдают текст и события, базу не трогают.

⚠️ ПРИНЦИП: ЧИНИТЬ ТОЛЬКО МЕХАНИЧЕСКОЕ И ОДНОЗНАЧНОЕ. Всё сомнительное текст
не меняет, а даёт причину для пометки «под вопросом» на позиции комплекта.

⚠️ СРАВНЕНИЕ ТЕКСТОВ — `bank_match` (сходство ≥ 0,90 на нормализованном
тексте, ни одно число не заменено), плюс подпись чисел и знаков операций
(`signature`). Третьего сравнения здесь нет. Подпись нужна потому, что
`operator_sequence` из `bank_match` считает «равна −3» и «равна $-3$» разными
(тире перед цифрой в прозе знаком не считается), а для двух редакций одного
условия это одно и то же.

⚠️ МЕТКИ РИСУНКОВ `[[FIGURE:…]]` НЕ ТЕРЯЕМ. Метка — единственная связь текста с
`ProblemFigure`; отрезанный кусок отдаёт свои метки: из условия — в конец
условия, из решения — в конец решения.
"""
import difflib
import re

from olympiads import bank_match as bm
from olympiads.tasks_import import _SOLUTION_CRITERIA_START, solution_flags

DOUBLED_MIN = 0.85      # сходство редакций, с которого условие считается удвоенным
HALF_MIN = 60           # короче (после нормализации) — «половиной» не считается
HALF_LEN_RATIO = 0.70   # при сходстве ≥ 0,85 длины отличаются не более чем так
ORPHAN_BLOCK = 25       # общий кусок короче не считается: формулы совпадают сами собой
ORPHAN_MIN = 300        # вырезанного текста без аналога в условии и решении — не меньше
STUB_MIN = 40           # условие после отрезания короче — отрезать вслепую нельзя

REASON_DOUBLED = 'условие в двух редакциях с разными числами'
REASON_DOUBLED_LOOSE = 'условие в двух редакциях, сходство ниже 0,90'
REASON_DOUBLED_MARKS = 'условие в двух редакциях, отметки верных вариантов различаются'
REASON_COPY_EXTRA = 'решение — копия условия с дописанным текстом'
REASON_ANSWER = 'ответ внутри условия'
REASON_TWO_TASKS = 'задача собрана из двух заданий'
REASON_RESIDUAL = 'в условии осталось решение'
REASON_MESS = 'варианты теста записаны дважды, внутри бланк ответа: разобрать вручную'
REASON_TWICE = 'условие осталось дважды'
REASON_CRITERIA = 'в условии критерии'
REASON_ALIEN = 'в условии чужой текст'
REASON_BALLS_LOST = 'в оставленной редакции нет баллов по пунктам'
REASON_COMPLEMENT = 'редакции дополняют друг друга: основа условия в одной, баллы в другой'
REASON_BROKEN = 'в оставленной редакции разорванные слова'
REASON_ORPHAN = 'из условия вырезан текст, которого нет в решении — разобрать вручную'
REASON_SEVERAL = 'в условии несколько заданий'
REASON_STUB = 'после отрезания ответа в конце условия остался обрывок'

_FIGURE = re.compile(r'\[\[FIGURE:[0-9a-fA-F]+\]\]')
_HAS_LETTER_OR_DIGIT = re.compile(r'[0-9A-Za-zА-Яа-яЁё]')
_CYRILLIC = re.compile(r'[А-Яа-яЁё]')
# Отметка верного варианта в тесте. Это ответ, а не оформление: её нельзя терять.
_MARK = re.compile(r'\(\s*отмечено\s*\)', re.IGNORECASE)


def figure_markers(text):
    return _FIGURE.findall(text or '')


def strip_markers(text):
    return _FIGURE.sub('', text or '')


def _append_markers(text, markers):
    """Дописать в конец метки, которых в тексте ещё нет."""
    missing = []
    for marker in markers:
        if marker not in (text or '') and marker not in missing:
            missing.append(marker)
    return '\n\n'.join(p for p in [(text or '').rstrip()] + missing if p)


# ── подпись чисел и знаков ───────────────────────────────────────────────

_SIGNS = [
    (re.compile(r'\\(?:frac|dfrac|tfrac|over|div)(?![a-zA-Z])|÷'), ' / '),
    (re.compile(r'\\(?:cdot|times|ast)(?![a-zA-Z])|[·⋅∙]'), ' × '),
    (re.compile(r'\\(?:leqslant|leq|le)(?![a-zA-Z])|⩽'), ' ≤ '),
    (re.compile(r'\\(?:geqslant|geq|ge)(?![a-zA-Z])|⩾'), ' ≥ '),
    (re.compile(r'\\(?:neq|ne)(?![a-zA-Z])'), ' ≠ '),
    (re.compile(r'\\lt(?![a-zA-Z])'), ' < '),
    (re.compile(r'\\gt(?![a-zA-Z])'), ' > '),
]
_TOKEN = re.compile(r'\d+(?:\.\d+)?|[+=<>≤≥≠×/]|[-−‐‑‒–—―]')
_DASHES = '-−‐‑‒–—―'
_MATHY_LEFT = re.compile(r'[0-9A-Za-z)}\]]')
_MATHY_RIGHT = re.compile(r'[0-9A-Za-z(\\]')


def signature(text):
    """Числа и знаки операций по порядку, в одном написании.

    «Равна −3» и «равна $-3$», «0,5» и «0.5», «1 200» и «1200», «\\frac» и «/»
    дают одно и то же; «100 − 2Q» и «100 + 2Q», «15» и «5» — разное.
    """
    t = strip_markers(text).replace('$', '')
    for mark in ('\\,', '\\;', '\\!', '\\ ', '~'):
        t = t.replace(mark, ' ' if mark in ('\\ ', '~') else '')
    t = t.replace('{,}', '.')
    for pattern, sign in _SIGNS:
        t = pattern.sub(sign, t)
    t = re.sub(r'(?<=\d)[   ](?=\d{3}(?!\d))', '', t)
    t = re.sub(r'(?<=\d),(?=\d)', '.', t)
    out = []
    for m in _TOKEN.finditer(t):
        token = m.group()
        if token not in _DASHES:
            out.append(token)
            continue
        before = t[:m.start()].rstrip()
        after = t[m.end():]
        # Знак — это тире, прижатое к числу или букве справа («−3», «−P»)
        # либо стоящее между «формульными» соседями («100 - 2Q»). «кто-то» и
        # «спрос — это» знаком не считаются.
        attached = bool(after) and (after[0].isdigit()
                                    or (after[0].isascii() and after[0].isalpha()))
        between = (before and _MATHY_LEFT.match(before[-1])
                   and after.lstrip() and _MATHY_RIGHT.match(after.lstrip()[0]))
        if attached or between:
            out.append('-')
    return out


def same_text(a, b):
    """Приговор `bank_match` по двум текстам и подпись чисел и знаков."""
    na, nb = bm.norm(a), bm.norm(b)
    if na == nb:
        return signature(a) == signature(b)
    if len(na) < bm.MIN_LEN or len(nb) < bm.MIN_LEN:
        return False
    if bm.ratio(na, nb) < bm.ACCEPT or bm.number_replaced(na, nb):
        return False
    return signature(a) == signature(b)


def _ratio_at_least(na, nb, floor):
    sm = difflib.SequenceMatcher(None, na, nb, autojunk=False)
    if sm.real_quick_ratio() < floor or sm.quick_ratio() < floor:
        return 0.0
    return sm.ratio()


# ── беда A: условие дважды ───────────────────────────────────────────────

# Баллы за пункт «(4 балла)», в том числе жирным, — не число условия.
_BALLS = re.compile(r'[*_]*\(\s*\d+(?:[.,]\d+)?\s*балл\w*\s*\)[*_]*', re.IGNORECASE)
_LIST_LINE = re.compile(r'(?m)^[ \t]*(?:[-*•]|\(?[0-9а-яa-z]{1,2}[).])[ \t]')
_VARIANT_START = re.compile(r'\A[-*\s]*\+?\s*\(?[A-DА-Гa-dа-г1-9]\)')
_BULLET_START = re.compile(r'\A(?:[-*•][ \t]|\*\*[^*\n]{1,40}\*\*|[A-DА-Г][ \t]*[:.][ \t])')
_FN_INLINE = re.compile(r'\$\^\{?(\d{1,2})\}?\$|<sup>(\d{1,2})</sup>|([¹²³⁴⁵⁶⁷⁸⁹⁰]+)')
_FN_LINE = re.compile(r'(?m)^[ \t]*(?:\$\^\{?(\d{1,2})\}?\$|<sup>(\d{1,2})</sup>|([¹²³⁴⁵⁶⁷⁸⁹⁰]+))[ \t]*\S')
_SUP = str.maketrans('⁰¹²³⁴⁵⁶⁷⁸⁹', '0123456789')
_SUP_CHARS = dict(zip('0123456789', '⁰¹²³⁴⁵⁶⁷⁸⁹'))


def strip_balls(text):
    return _BALLS.sub('', text or '')


def _richness(text):
    """Чем больше, тем полнее запись: отметки, баллы, формулы, списки, длина."""
    return (len(_MARK.findall(text)), len(_BALLS.findall(text)), text.count('$'),
            len(_LIST_LINE.findall(text)), len(bm.norm(text)))


def _relation(sa, sb):
    """'equal', 'a_superset', 'b_superset' или 'conflict' для подписей."""
    ops = difflib.SequenceMatcher(None, sa, sb, autojunk=False).get_opcodes()
    kinds = {op for op, *_ in ops} - {'equal'}
    if not kinds:
        return 'equal'
    if kinds == {'delete'}:
        return 'a_superset'
    if kinds == {'insert'}:
        return 'b_superset'
    return 'conflict'


def _covered(small, big):
    """Доля нормализованного текста `small`, найденная в `big` (куски ≥ 8 знаков)."""
    if not small:
        return 1.0
    sm = difflib.SequenceMatcher(None, small, big, autojunk=False)
    return sum(b.size for b in sm.get_matching_blocks() if b.size >= 8) / len(small)


def orphan_chars(removed, keepers):
    """Сколько знаков вырезанного текста не нашлось ни в одном из `keepers`."""
    r = bm.norm(strip_markers(removed))
    mask = bytearray(len(r))
    for keeper in keepers:
        nk = bm.norm(strip_markers(keeper))
        if not r or not nk:
            continue
        sm = difflib.SequenceMatcher(None, r, nk, autojunk=False)
        for pos, _other, size in sm.get_matching_blocks():
            if size >= ORPHAN_BLOCK:
                mask[pos:pos + size] = b'\x01' * size
    return len(r) - sum(mask)


def _same_start(kept, removed):
    """Начало убранной редакции совпадает с началом оставшегося условия.

    Исключение — дубль одних вариантов теста: убранное начинается с метки
    варианта («1)», «А)», «- А)»), и весь его текст уже есть в оставшемся.
    """
    nk, nr = bm.norm(kept), bm.norm(removed)
    if bm.ratio(nk[:200], nr[:200]) >= DOUBLED_MIN:
        return True
    if ((_VARIANT_START.match(removed.strip()) or _BULLET_START.match(removed.strip()))
            and _covered(nr, nk) >= 0.95):
        return True
    return False


def _fn_numbers(regex, text):
    out = set()
    for m in regex.finditer(text):
        digits = m.group(1) or m.group(2) or (m.group(3) or '').translate(_SUP)
        if digits.isdigit():
            out.add(int(digits))
    return out


def restore_footnotes(kept, removed):
    """Сноска, знак которой остался в условии, а строка ушла с убранной редакцией."""
    missing = _fn_numbers(_FN_INLINE, kept) - _fn_numbers(_FN_LINE, kept)
    lines = []
    for number in sorted(missing):
        marker = r'(?:\$\^\{?%d\}?\$|<sup>%d</sup>|%s)' % (
            number, number, ''.join(_SUP_CHARS[d] for d in str(number)))
        pattern = re.compile(r'\A[ \t]*' + marker + r'[ \t]*\S')
        candidates = [p.strip() for p in re.split(r'\n\s*\n', removed)
                      if pattern.match(p) and len(p.strip()) <= 400]
        if candidates:
            lines.append(min(candidates, key=len))
    return '\n\n'.join([kept.rstrip()] + lines) if lines else kept


def _broken_words(text, other):
    """Сколько слов `text` разорвано пробелом: в `other` они стоят слитно.

    «Объяс ните», «высоко технологичных» против «Объясните»,
    «высокотехнологичных». Словарь не нужен: вторая редакция — свидетель.
    """
    tokens = re.findall(r'[А-Яа-яЁё]+', text.lower())
    mine, theirs = set(tokens), set(re.findall(r'[А-Яа-яЁё]+', other.lower()))
    return sum(1 for a, b in zip(tokens, tokens[1:])
               if a + b in theirs and a + b not in mine)


def find_doubling(statement):
    """dict(kept, removed, verdict, reason, side) или None.

    Граница — абзац. Вторая часть похожа на первую (≥ 0,85 на нормализованном
    тексте — порог подсчёта S5). Числа и знаки сравниваются БЕЗ баллов
    «(N балла)». Оставляется ПОЛНАЯ редакция: та, что содержит всё, что есть в
    другой, плюс баллы, списки, формулы, отметки «(отмечено)» или лишние
    пункты; при равенстве — богаче по этому набору, при ничьей — первая.
    'flag' — если каждая редакция содержит то, чего нет в другой; во второй
    больше отметок верных вариантов, чем в оставленной; сходство ниже 0,90,
    а одна редакция не вложена в другую целиком; убранная редакция не
    совпадает с началом оставшегося условия (в условии несколько заданий).
    """
    text = (statement or '').strip()
    best = None
    for m in re.finditer(r'\n[ \t]*\n', text):
        left, right = text[:m.start()].strip(), text[m.end():].strip()
        # Сноска первой редакции стоит на границе: к правой половине не относится.
        first, _sep, rest = right.partition('\n\n')
        if rest.strip() and len(first) <= 400 and _FN_LINE.match(first):
            left, right = left + '\n\n' + first.strip(), rest.strip()
        nl, nr = bm.norm(left), bm.norm(right)
        if min(len(nl), len(nr)) < HALF_MIN:
            continue
        if min(len(nl), len(nr)) / max(len(nl), len(nr)) < HALF_LEN_RATIO:
            continue
        score = _ratio_at_least(nl, nr, DOUBLED_MIN)
        if score >= DOUBLED_MIN and (best is None or score > best[0]):
            best = (score, left, right)
    if best is None:
        return None
    score, left, right = best

    def result(verdict, reason, kept, removed, side):
        return {'kept': kept, 'removed': removed, 'verdict': verdict,
                'reason': reason, 'side': side, 'score': score}

    ls, rs = strip_balls(left), strip_balls(right)
    relation = _relation(signature(ls), signature(rs))
    if relation == 'conflict' or bm.number_replaced(bm.norm(ls), bm.norm(rs)):
        return result('flag', REASON_DOUBLED, left, right, 'left')
    if relation == 'a_superset':
        side = 'left'
    elif relation == 'b_superset':
        side = 'right'
    else:
        side = 'right' if _richness(right) > _richness(left) else 'left'
    # Баллы по пунктам нужны ИИ-проверке и важнее мелкой разницы в тексте:
    # если текст без баллов совпадает (≥ 0,90), а баллы есть только в одной
    # редакции, оставляется она — при условии, что она не теряет чисел другой.
    balls_l, balls_r = len(_BALLS.findall(left)), len(_BALLS.findall(right))
    if balls_l != balls_r:
        want = 'left' if balls_l > balls_r else 'right'
        if bm.ratio(bm.norm(ls), bm.norm(rs)) >= bm.ACCEPT:
            side = want
        elif side != want:
            # Баллы пропали бы, а редакции слишком различны, чтобы выбрать по ним.
            kept, removed = (left, right) if side == 'left' else (right, left)
            return result('flag', REASON_BALLS_LOST, kept, removed, side)
    kept, removed = (left, right) if side == 'left' else (right, left)
    if _broken_words(kept, removed) > _broken_words(removed, kept):
        return result('flag', REASON_BROKEN, kept, removed, side)
    if score < bm.ACCEPT:
        # Ниже 0,90 чиним, только если одна редакция вложена в другую целиком.
        small, big = sorted((bm.norm(left), bm.norm(right)), key=len)
        if _covered(small, big) < 0.97 or len(bm.norm(kept)) < len(bm.norm(removed)):
            return result('flag', REASON_DOUBLED_LOOSE, kept, removed, side)
    # Теряется ответ, только если в убираемой редакции отметок больше.
    if len(_MARK.findall(removed)) > len(_MARK.findall(kept)):
        return result('flag', REASON_DOUBLED_MARKS, kept, removed, side)
    if not _same_start(kept, removed):
        fragment = (_VARIANT_START.match(kept.strip()) or _BULLET_START.match(kept.strip()))
        if fragment and _covered(bm.norm(kept), bm.norm(removed)) >= 0.95:
            return result('flag', REASON_COMPLEMENT, kept, removed, side)
        return result('flag', REASON_SEVERAL, kept, removed, side)
    return result('fix', '', kept, removed, side)


# ── беда B: ответ или решение внутри условия ─────────────────────────────

# Метка — слово в НАЧАЛЕ строки, за которым идёт «:» или «.» (в том числе
# внутри жирного), либо которое стоит на строке одно («**Решение**»).
# «Решение фирмы о выпуске…» — не метка: после слова нет ни знака, ни конца
# строки.
_LABEL = re.compile(
    r'(?im)^[ \t]*[*#_>]*[ \t]*'
    r'(?P<word>ответы?|решение|разбор|критерии(?:[ \t]+(?:оценивания|проверки|оценки))?'
    r'|схема[ \t]+(?:проверки|оценивания))'
    r'[ \t]*[*_]*[ \t]*(?:(?P<mark>[:.])[ \t]*[*_]*|(?=[ \t]*$))')
# Что остаётся от «Ответ: ________ *(1 балл)*», если убрать подчёркивания,
# точки, звёздочки и «(N балла)»: пусто — это бланк для ответа ученика.
_BLANK_FILLER = re.compile(r'\(\s*\d+[.,]?\d*\s*балл\w*\s*\)|[_.…*\s\-–—]+', re.IGNORECASE)
_PART_LABEL = re.compile(r'(?m)^[ \t]*[*_(]*([а-яa-z0-9]{1,3})[*_]*[).][ \t]')
_NEW_TASK = re.compile(r'(?im)^[ \t]*[*#_>]*[ \t]*(?:задача|задание|вопрос)[ \t]*№?[ \t]*\d')


def _part_keys(text):
    return {m.group(1) for m in _PART_LABEL.finditer(text)}


def find_answer_label(statement, part_labels=()):
    """(условие до метки, отрезанный текст, вердикт, причина) или None.

    Вердикт 'fix' — после метки только продолжение разбора; 'flag' — после
    метки снова идёт текст задания (пункт, которого до метки не было, или
    «Задача N»), либо резать нечем (метка в самом начале, остаётся обрывок
    короче `STUB_MIN`). Метка `Ответ:` без содержания («Ответ: _____»)
    меткой не считается: это строка для ответа ученика.
    """
    text = statement or ''
    for m in _LABEL.finditer(text):
        rest = text[m.end():]
        if m.group('word').lower().startswith('ответ'):
            # Бланк для ответа ученика — не ответ: «Ответ: ____ (1 балл)» и
            # голое слово «Ответ» над пустой таблицей.
            first_line = next((ln for ln in strip_markers(rest).split('\n') if ln.strip()), '')
            if not _HAS_LETTER_OR_DIGIT.search(_BLANK_FILLER.sub('', strip_markers(rest))):
                continue
            if m.group('mark') is None and first_line.lstrip().startswith('|'):
                continue
        head, cut = text[:m.start()].rstrip(), text[m.start():]
        if len(bm.norm(head)) < STUB_MIN:
            return head, cut, 'flag', REASON_ANSWER
        seen = _part_keys(head) | {str(k).strip().strip('().').lower() for k in part_labels}
        new_parts = _part_keys(rest) - seen
        if new_parts or _NEW_TASK.search(rest):
            # Длинный текст с новыми пунктами после метки — второе задание.
            return head, cut, 'flag', (REASON_TWO_TASKS if len(rest) >= 800
                                       else REASON_ANSWER)
        return head, cut, 'fix', ''
    return None


def tail_is_stub(head):
    """Хвост условия после отрезания похож на обрывок решения.

    Последний абзац без единой русской буквы («25 < e < 50.») либо его
    последняя строка кончается баллами «после выкладки» («… = 990 рублей.
    (2 балла)»). Самого условия в таком хвосте нет, и резать дальше вслепую
    нельзя — позиция «под вопросом».
    """
    last = [p for p in re.split(r'\n\s*\n', strip_markers(head).strip()) if p.strip()]
    if len(last) < 2:
        return False
    return (not _CYRILLIC.search(last[-1])) or _ball_line(last[-1].split('\n')[-1])


# ── остаток решения в условии и бланк ответа ─────────────────────────────

# Голос разбора: «Итак», «Следовательно», «Найдём»… «Рассмотрим», «Пусть» и
# «Обозначим» сюда НЕ входят — так начинают и условия.
_STRONG = re.compile(
    r'(?i)\b(?:следовательно|итак|отсюда|откуда|получаем|получим|'
    r'подставим|подставив|выразим|заметим|найд[её]м)\b')
_BALLS_AT_END = re.compile(
    r'(?i)(?:\(\s*\d+(?:[.,]\d+)?\s*балл\w*\s*\)|[–—-]\s*\d+(?:[.,]\d+)?\s*балл\w*)'
    r'[ \t*_]*[:.;]?[ \t]*$')
# Строка-задание («б) Найдите … (2 балла)») баллы в конце не делают разбором.
_ASK_LINE = re.compile(
    r'(?i)^[ \t]*[-*]?[ \t]*(?:\(?[а-яa-z0-9]{1,2}[).][ \t]+)?'
    r'(?:найдите|определите|рассчитайте|вычислите|объясните|укажите|выберите|покажите|'
    r'докажите|постройте|запишите|сколько|чему|как|какова|какой|каков|будет ли|что|'
    r'вычислить|найти|определить|показать|объяснить)\b')
_PART_START = re.compile(
    r'(?i)^[ \t]*[-*•]?[ \t]*(?:\(?[а-яa-z]{1,2}[).]+|\d+(?:\.\d+)*[.)]+)[ \t]')
_BULLET_LINE = re.compile(r'^[ \t]*[-*•][ \t]')
# Баллы за весь тест или раздел — инструкция участнику, а не разбор.
_BALLS_TOTAL = re.compile(r'(?i)\b(?:всего|итого|оценива\w*|максимум\w*|максимальн\w*)\b')


_OPTION_LINE = re.compile(r'^[ \t]*[A-DА-Г][).]')


def _voice_count(text):
    """Сколько раз в строках (кроме пунктов списка и вариантов) слышен голос разбора."""
    return sum(len(_STRONG.findall(ln)) for ln in text.split('\n')
               if not _BULLET_LINE.match(ln) and not _OPTION_LINE.match(ln))


def _ball_line(line):
    return (bool(_BALLS_AT_END.search(line)) and not _ASK_LINE.match(line) and '?' not in line
            and not _PART_START.match(line) and not _BULLET_LINE.match(line)
            and not _BALLS_TOTAL.search(line))
_BLANK = re.compile(r'_{3,}|\(\s*комментарий\s*\)|\(\s*продолжение комментария\s*\)',
                    re.IGNORECASE)
_VARIANT_LABEL = re.compile(r'(?m)^[ \t]*[-*]?[ \t]*\+?[ \t]*([A-DА-Г])\)')
# Новое задание внутри вырезаемого: предложение-поручение с заглавной буквы.
_NEW_TASK_ASK = re.compile(
    r'(?:^|[.!?»]\s+|\n)(?:Найдите|Определите|Рассчитайте|Вычислите|Объясните|Помогите|'
    r'Выберите|Докажите|Постройте|Сколько|Какова|Каков)\b')
_PART_QUESTION = re.compile(r'(?m)^[ \t]*\(?[а-яa-z][).][^\n]*\?')
RESIDUAL_MIN = 200      # знаков рассуждения после начала разбора


def residual_solution(text):
    """(True, начало остатка) если в условии осталось рассуждение решения.

    Рассуждение начинается с первой строки, где слышен голос разбора
    («Так как…», «Следовательно…»), либо стоят баллы в КОНЦЕ строки («после
    выкладки», а не «а) (3 балла) Найдите…»). Остаток — от неё до конца
    условия; признак: не меньше 200 знаков и либо два голоса разбора, либо
    голос плюс баллы или две строки-выкладки со знаком «=», либо два раза
    баллы в конце строки.
    """
    body = strip_markers(text)
    lines = body.split('\n')
    start = None
    offset = 0
    for i, line in enumerate(lines):
        if i > 0 and (_voice_count(line) or _ball_line(line)):
            start = offset
            break
        offset += len(line) + 1
    if start is None:
        return False, ''
    tail = body[start:]
    strong = _voice_count(tail)
    balls = sum(1 for ln in tail.split('\n') if _ball_line(ln))
    equations = sum(1 for ln in tail.split('\n') if '=' in ln)
    if len(tail.strip()) < RESIDUAL_MIN:
        return False, ''
    if strong >= 2 or (strong >= 1 and (balls >= 1 or equations >= 2)) or balls >= 2:
        return True, tail
    return False, ''


def is_blank_form(cut):
    """Бланк для ответа ученика: подчёркивания, «(комментарий)»."""
    return bool(_BLANK.search(cut))


def repeated_variants(text):
    """Метка варианта теста («А)», «- B)») встречается больше одного раза."""
    labels = _VARIANT_LABEL.findall(text)
    return any(labels.count(x) > 1 for x in set(labels))


# ── беда C: решение — копия условия ──────────────────────────────────────

def split_solution(solution):
    """(текст решения до критериев, раздел критериев вместе с заголовком)."""
    text = solution or ''
    m = _SOLUTION_CRITERIA_START.search(text)
    if m is None:
        return text, ''
    return text[:m.start()], text[m.start():]


_TITLE_LINE = re.compile(
    r'\A[ \t]*[*#_>]*[ \t]*(?:задача|задание|вопрос)[ \t]*№?[ \t]*\d+[^\n]*\n')


def is_copy(head, statements):
    """'exact', 'near' или None: часть решения до критериев — копия условия?

    'exact' — после нормализации (`bm.norm`: буквы и цифры, регистр, «ё») текст
    решения РАВЕН условию и подпись чисел и знаков та же: убрать нечего
    терять. 'near' — сходство ≥ 0,90, но в решении есть дописанный текст
    (чаще всего «(отмечено)» у верных вариантов теста — это ответ). Такую
    копию не трогаем, позиция «под вопросом».

    Строка-заголовок «Задача 1. (5 баллов)» перед копией не мешает: это
    шапка листа проверки, а не текст решения.
    """
    body = _TITLE_LINE.sub('', strip_markers(head).strip() + '\n', count=1).strip()
    if not body:
        return None
    nb = bm.norm(body)
    for statement in statements:
        if statement and nb == bm.norm(statement) and signature(body) == signature(statement):
            return 'exact'
    if any(same_text(body, st) for st in statements if st):
        return 'near'
    return None


# ── всё вместе для одной задачи ──────────────────────────────────────────

# ── проверки итогового условия после правки A или B ──────────────────────

_GRADING = re.compile(
    r'(?i)комментарий к оцениванию|критерии оценивания|оценка снижается|'
    r'не более\s+\d+(?:[.,]\d+)?\s*балл|оценить\b[^.\n]{0,40}баллов|баллов ставится')
_VOICE_ANYWHERE = re.compile(r'(?i)\b(?:итого|решая|получаем)\b|изменил\w*\s+на\s+\d')
_ENDS_WITH_NUMBER = re.compile(
    r'=\s*[-−]?\s*\d[\d.,\s{}]*(?:\\?%|[\w.]{0,12})?\$?[.\s]*$')
RESULT_TAIL = 600       # последние знаки итогового условия для голоса разбора
TWICE_HEAD = 60         # знаков начала условия, которые не должны повториться ниже
ALIEN_MIN = 60          # хвостовой абзац длиннее, которого нет во второй редакции


def final_checks(statement, removed=''):
    """Причины, по которым итоговое условие нельзя считать починенным.

    Запускается после ЛЮБОЙ правки A или B. Сработала хоть одна — текст не
    меняется, позиция «под вопросом»:

    1. начало условия (первые 60 знаков без разметки) встречается ниже ещё раз;
    2. текст оценивания: «Комментарий к оцениванию», «не более N баллов»…;
    3. голос разбора в последних 600 знаках где угодно («Итого», «Решая»,
       «получаем», «изменилось на N») либо последняя строка — `… = число` без
       вопроса;
    4. только для A (`removed` задан): хвостовой абзац длиннее 60 знаков, которого
       нет в убранной редакции, — чужой текст.
    """
    body = strip_markers(statement)
    reasons = []
    norm = bm.norm(body)
    if len(norm) > 2 * TWICE_HEAD and norm[:TWICE_HEAD] in norm[TWICE_HEAD:]:
        reasons.append(REASON_TWICE)
    if _GRADING.search(body):
        reasons.append(REASON_CRITERIA)
    last_line = next((ln for ln in reversed(body.split('\n')) if ln.strip()), '')
    if (_VOICE_ANYWHERE.search(body[-RESULT_TAIL:])
            or ('?' not in last_line and _ENDS_WITH_NUMBER.search(last_line.strip()))):
        reasons.append(REASON_RESIDUAL)
    if removed:
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', body) if p.strip()]
        last = paragraphs[-1] if paragraphs else ''
        if len(last) > ALIEN_MIN and _covered(bm.norm(last), bm.norm(removed)) < 0.5:
            reasons.append(REASON_ALIEN)
    return reasons


def _clean(statement, solution, part_labels, part_texts, blocked=None):
    """Результат чистки одной задачи (ничего не пишет).

    dict: statement, solution — новые тексты; events — что найдено и что
    сделано ({bug, action: 'fixed'|'flagged', ...}); reasons — причины
    пометки позиции; detached — отрезанное, но не записанное нигде
    (его сохранит отчёт). `blocked` — причины итоговой проверки: правки A и B
    тогда не делаются, а позиция получает эти причины.
    """
    original = statement or ''
    cur = original
    events, reasons, detached = [], [], ''
    stmt_markers = figure_markers(original)
    head_sol, criteria = split_solution(solution or '')

    def flag(bug, why):
        events.append({'bug': bug, 'action': 'flagged', 'detail': why})
        if why not in reasons:
            reasons.append(why)

    # A. Условие дважды. Цикл до устойчивости: идемпотентность.
    for _ in range(3):
        found = find_doubling(cur)
        if found is None:
            break
        if found['verdict'] != 'fix':
            flag('A', found['reason'])
            break
        if blocked:
            for why in blocked:
                flag('A', why)
            break
        kept = restore_footnotes(found['kept'], found['removed'])
        cur = _append_markers(kept, figure_markers(found['removed']) + figure_markers(cur))
        events.append({'bug': 'A', 'action': 'fixed', 'removed': found['removed'],
                       'kept_side': found['side']})
        if orphan_chars(found['removed'], [kept, head_sol]) >= ORPHAN_MIN:
            flag('A', REASON_ORPHAN)

    # B. Ответ или решение внутри условия.
    cut, blank, cut_applied = '', False, False
    found = find_answer_label(cur, part_labels)
    if found is not None:
        head, tail, verdict, why = found
        if verdict != 'fix':
            flag('B', why)
        else:
            blank = is_blank_form(tail)
            if blank and repeated_variants(head + '\n' + tail):
                flag('B', REASON_MESS)
            elif residual_solution(head)[0]:
                flag('B', REASON_RESIDUAL)
                # Вырезаемое целиком чужое для решения — второе задание в условии.
                if (len(tail) >= 800 and (_NEW_TASK_ASK.search(tail) or _PART_QUESTION.search(tail))
                        and orphan_chars(tail, [head, head_sol]) >= len(bm.norm(tail)) / 2):
                    flag('B', REASON_TWO_TASKS)
            elif blocked or any(ev['bug'] == 'A' and ev['action'] == 'flagged'
                                for ev in events):
                # Условие ещё не очищено от дубля (A помечен) — резать нельзя.
                for why in blocked or [REASON_ANSWER]:
                    flag('B', why)
            else:
                cut_markers = figure_markers(tail)
                cut = strip_markers(tail).strip()
                cur = _append_markers(head, cut_markers + figure_markers(cur))
                cut_applied = True
                events.append({'bug': 'B', 'action': 'fixed', 'cut': cut})
                if tail_is_stub(head):
                    flag('B', REASON_STUB)
    if not cut_applied and REASON_RESIDUAL not in reasons and residual_solution(cur)[0]:
        flag('B', REASON_RESIDUAL)

    # C. Поле решения — копия условия.
    new_solution = solution or ''
    statements = [original, cur]
    if part_texts:
        statements += ['\n'.join([original] + list(part_texts)),
                       '\n'.join([cur] + list(part_texts))]
    kind = is_copy(head_sol, statements)
    copy = kind == 'exact'
    solution_empty = not strip_markers(head_sol).strip()
    if copy:
        events.append({'bug': 'C', 'action': 'fixed'})
    elif kind == 'near':
        flag('C', REASON_COPY_EXTRA)
    if cut:
        if (copy or solution_empty) and not blank:
            keep = figure_markers(head_sol) if copy else []
            new_solution = '\n\n'.join(p for p in [cut] + keep + [criteria.strip()] if p)
        else:
            detached = cut
            events.append({'bug': 'B', 'action': 'kept_in_report'})
            # Вырезанное, которого нет ни в условии, ни в решении, — только в отчёте.
            norm_len = len(bm.norm(cut))
            if (not blank and len(cut) > ORPHAN_MIN
                    and orphan_chars(cut, [cur, head_sol]) >= norm_len / 2):
                flag('B', REASON_ORPHAN)
    elif copy:
        keep = figure_markers(head_sol)
        new_solution = '\n\n'.join(p for p in keep + [criteria.strip()] if p)

    return {'statement': cur, 'solution': new_solution, 'events': events,
            'reasons': reasons, 'detached': detached,
            'markers_ok': set(stmt_markers) <= set(figure_markers(cur))}


def clean_problem(statement, solution, part_labels=(), part_texts=()):
    """Результат чистки одной задачи (ничего не пишет), см. `_clean`.

    После правки A или B итоговое условие проходит `final_checks`; не прошло —
    чистка повторяется без правок текста, причины идут в пометку позиции.
    """
    result = _clean(statement, solution, part_labels, part_texts)
    if result['statement'] == (statement or ''):
        return result
    removed = '\n\n'.join(ev['removed'] for ev in result['events']
                          if ev['bug'] == 'A' and ev['action'] == 'fixed')
    bad = final_checks(result['statement'], removed)
    if not bad:
        return result
    return _clean(statement, solution, part_labels, part_texts, blocked=bad)


def item_flags(solution):
    """(есть решение, есть критерии) — тем же правилом, что в S4."""
    return solution_flags(solution)


# ── план по базе ─────────────────────────────────────────────────────────

def s4_problem_ids(only=''):
    """Задачи, созданные заливкой S4: только они правятся.

    Признак — все четыре вместе: черновик, скрыт до ревью, ревью пустое,
    `content_format='markdown'` (S4 пишет именно его; 22 прежних черновика
    июня с позициями — 'plain') и на задачу указывает позиция комплекта.
    Прежние задачи банка и задачи с непустым `human_review` сюда не попадают
    никогда.
    """
    from olympiads.models import OlympiadVariantItem
    from problems.models import Problem
    items = OlympiadVariantItem.objects.all()
    if only:
        items = items.filter(variant__olympiad__slug=only)
    return set(Problem.objects.filter(
        id__in=items.values('problem_id'), status=Problem.Status.DRAFT,
        hidden_pending_review=True, human_review=Problem.HumanReview.NONE,
        content_format=Problem.ContentFormat.MARKDOWN,
    ).values_list('id', flat=True))


def _dollar_odd(text):
    return strip_markers(text).replace('\\$', '').count('$') % 2


def _brace_balance(text):
    t = strip_markers(text).replace('\\{', '').replace('\\}', '')
    return abs(t.count('{') - t.count('}'))


def worse(before, after):
    """Стало ли хуже по парности `$` и балансу `{}` (дифференциально)."""
    return (_dollar_odd(after) > _dollar_odd(before)
            or _brace_balance(after) > _brace_balance(before))


def build_plan(only=''):
    """План чистки: что найдено у каждой задачи и что станет с позициями.

    Ничего не пишет. Прежние задачи, на которые указывают позиции, только
    ЧИТАЮТСЯ — для отчёта «нашлось, не тронуто».
    """
    import collections
    from olympiads.models import OlympiadVariantItem
    from problems.models import Problem, ProblemPart

    items_qs = OlympiadVariantItem.objects.all()
    if only:
        items_qs = items_qs.filter(variant__olympiad__slug=only)
    editable = s4_problem_ids(only)
    by_problem = collections.defaultdict(list)
    for item in items_qs.select_related('variant__olympiad'):
        by_problem[item.problem_id].append(item)
    ids = sorted(by_problem)
    parts = collections.defaultdict(list)
    answered = set()
    for pid, label, text, answer in (ProblemPart.objects.filter(problem_id__in=ids)
                                     .order_by('problem_id', 'order', 'id')
                                     .values_list('problem_id', 'label', 'statement',
                                                  'answer')):
        parts[pid].append((label or '', text or ''))
        if answer == 'верно':
            answered.add(pid)

    problems, legacy = [], []
    for row in (Problem.objects.filter(id__in=ids)
                .values_list('id', 'statement', 'solution', 'answer', 'title')):
        pid, statement, solution, answer, title = row
        result = clean_problem(statement or '', solution or '',
                               [label for label, _ in parts[pid]],
                               [text for _, text in parts[pid]])
        if not result['events']:
            continue
        entry = {
            'id': pid, 'title': title or '', 'editable': pid in editable,
            'statement_before': statement or '', 'solution_before': solution or '',
            'statement_after': result['statement'], 'solution_after': result['solution'],
            'answer': answer or '', 'has_answer': bool((answer or '').strip()) or pid in answered,
            'events': result['events'], 'reasons': result['reasons'],
            'detached': result['detached'],
            'olympiads': sorted({i.variant.olympiad.slug for i in by_problem[pid]}),
            'items': [i.pk for i in by_problem[pid]],
        }
        (problems if pid in editable else legacy).append(entry)
    return {'problems': problems, 'legacy': legacy, 'editable_total': len(editable),
            'items_of': {pid: [i.pk for i in by_problem[pid]] for pid in ids}}
