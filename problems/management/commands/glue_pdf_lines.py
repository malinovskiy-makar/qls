# -*- coding: utf-8 -*-
"""
Склейка построчной PDF/LaTeX-нарезки в текстах задач (Problem.statement и
ProblemPart.statement).

Зачем: полный скан 2026-07 (reports/diagnostic_sample/full_scan_summary.md)
показал, что 16 источников — 13 603 задачи, 73% видимого каталога — хранят
текст с жёсткой построчной нарезкой из PDF/LaTeX: перенос строки стоит
посреди предложения через каждые ~60–100 символов. Сейчас браузер это прячет
(white-space: normal схлопывает переносы), но нарезка шумит в эмбеддингах,
ломает детекторы дефектов и блокирует включение white-space: pre-line.

Что делает: детерминированно склеивает одиночные \\n, которые выглядят как
техническая нарезка (предыдущая строка обрывается «плохо», следующая
начинается как продолжение), и НЕ трогает структурные переносы (списки,
служебные метки, display-математику, таблицы, абзацные \\n\\n).

Поле solution в v1 НЕ обрабатывается — осознанно:
  1) классификация «73% — нарезка» считалась ТОЛЬКО по statement
     (collect_line_stats в problems/diagnostics.py); для решений профиль
     переносов никто не мерил, а устроены они иначе: пошаговые выкладки,
     где перенос строки чаще содержательный («новый шаг»), чем технический;
  2) 1 097 решений писал Sonnet (Батч 2, solution_ai_extracted) — они уже
     нормально свёрстаны, клеить там нечего;
  3) цель этапа — подготовить statement к включению pre-line; решения можно
     пройти отдельной сессией тем же движком, когда правила подтвердятся
     глазами на условиях.

Правила для границы между строками A и B (одиночный \\n):
  НЕ клеим, если:
    - \\n находится внутри формулы ($...$, $$...$$, \\(..\\), \\[..\\],
      \\begin{...}...\\end{...}) — содержимое формул не трогаем никогда;
    - одна из строк пустая (абзацные \\n\\n сохраняются как есть);
    - B начинается с маркера подпункта: а) (б) в. 1. 2) (3) • — - \\item;
    - B начинается со служебной метки: «Решение:», «Ответ:», «Дано:», ...;
    - A заканчивается двоеточием (намеренный ввод списка/формулы);
    - A или B — строка display-математики ($$..$$, \\[..\\], \\begin{..});
    - A или B похожа на строку таблицы (| ... |, \\hline, два и более &);
    - A или B — строка из одних цифр/знаков без букв (столбики чисел с осей
      графиков, разъехавшиеся строки таблиц — реальные случаи из замера);
    - A и B обе вида «Метка: число» (псевдотаблица показателей, #50095);
    - B начинается с формулы или LaTeX-команды — в v1 не рискуем: по замеру
      это на треть перечни формул построчно, склейка их испортила бы
      (исключение — экранированный доллар-валюта \\$);
    - B начинается с заглавной буквы, а конец A не «сильный» (см. ниже);
    - A заканчивается завершающей пунктуацией . ? ! ; …
  Клеим (\\n → пробел), если конец A «плохой» (без завершающей пунктуации) и:
    - B начинается со строчной буквы (кириллица или латиница) — главный
      случай, 22% всех границ по замеру 1 500 задач;
    - B начинается с , ; ) » — продолжение конструкции («, где $C$ — ...»);
    - B начинается с = — разорванная строка формулы без $ («Ld» / «= 80-w»);
    - B начинается с ( + строчная буква;
    - B начинается с цифры, а A кончается строчной буквой/запятой/висячим
      словом («...составляет» → «4800 млрд р.») и B не строка одних цифр;
    - B начинается с заглавной, НО конец A «сильный»: запятая, открывающая
      скобка/кавычка, оператор (= + − × · /), тире или висячее служебное
      слово (предлог/союз/частица из HANGING_WORDS: «...цена и» → «Спрос»).
  Дефисный разрыв слова («предло-\\nжение»): дефис удаляется, половинки
  клеятся встык ТОЛЬКО если обе кириллические, длиной ≥2 и не похожи на
  осмысленное дефисное слово (во-первых, кое-кто, что-либо, юго-запад —
  списки LEFT_DOUBT/RIGHT_DOUBT). Сомнительные случаи не трогаются вовсе и
  логируются в reports/glue_lines/hyphen_doubtful.txt.

Предохранитель (поле аномально — вся задача пропускается и пишется в
reports/glue_lines/borderline.txt; изменения к ней НЕ применяются):
  - в одном поле больше MAX_GLUES_PER_FIELD склеек — типичное условие даёт
    5–30, сотня склеек значит свалку/псевдотаблицу, пусть смотрят глаза;
  - склейка собрала абзац длиннее MAX_GLUED_PARA_LEN символов из
    MIN_LINES_FOR_PARA_GUARD и более строк — вероятно, склеено структурное.

Идемпотентность: повторный прогон по уже склеенному тексту даёт 0 изменений
(проверяется на каждом изменённом поле, нарушения попадают в отчёт).

Запуск (без --confirm НИЧЕГО не пишется в базу — это режим по умолчанию):
    ./venv/bin/python manage.py glue_pdf_lines                  # dry-run, 16 источников нарезки
    ./venv/bin/python manage.py glue_pdf_lines --source-id 13   # только МатЭк
    ./venv/bin/python manage.py glue_pdf_lines --limit 200      # быстрая проба
    ./venv/bin/python manage.py glue_pdf_lines --examples 5     # + примеры в md-отчёт
    ./venv/bin/python manage.py glue_pdf_lines --preview        # + reports/glue_lines/preview.html
    ./venv/bin/python manage.py glue_pdf_lines --confirm        # ЗАПИСЬ (только после «да» Макара)
"""
from typing import Dict, List, Optional, Tuple
from collections import Counter
import html as html_lib
import os
import random
import re
import shutil
from datetime import datetime

from django.core.management.base import BaseCommand

from problems.models import Problem, ProblemPart, Source

REPORT_DIR = 'reports/glue_lines'

# 16 источников группы «жёсткая нарезка» из полного скана 2026-07
# (reports/diagnostic_sample/source_linebreak_stats.md), id по базе:
#   3 ЛШ Олмат 2025 · 4 Бахарев-сборник · 5 Шпицруттен · 6 Сборник тестов АА ·
#   7 IEO · 8 AP Mock FRQ · 9 Курс 822 · 10 КСИ Кыльчик · 14 Overleaf Archive 3 ·
#   18 AP Real Exams · 19 ОЭШ Олмат 2022 · 20 AP Homeworks · 21 AP CollegeBoard ·
#   22 AP Course Mocks · 23 КСИГМА · 24 Акимова
# МатЭк (13) — смешанный профиль, в набор по умолчанию НЕ входит (решение
# о нём принимает преподаватель); ILE (2) — структурные переносы, не трогаем.
HARD_WRAP_SOURCE_IDS = [3, 4, 5, 6, 7, 8, 9, 10, 14, 18, 19, 20, 21, 22, 23, 24]

# ── Пороги предохранителя ────────────────────────────────────────────────────
# MAX_GLUES_PER_FIELD: по dry-run 99-й перцентиль склеек на поле — 27, максимум
# у нормальных задач — десятки; всё, что выше 80, — свалка текста, не условие.
# MAX_GLUED_PARA_LEN: типичный абзац после склейки — 300–900 символов; 2500 —
# это ~35 склеенных строк подряд без единой точки, так предложения не выглядят.
MAX_GLUES_PER_FIELD = 80
MAX_GLUED_PARA_LEN = 2500
MIN_LINES_FOR_PARA_GUARD = 3

MATH_CH = ''  # символ-заглушка: им в «тени» текста заменена математика
TERMINAL_PUNCT = '.?!;…'
LINE_CLOSERS = ')]"\'»”'

# ── Маска математики ─────────────────────────────────────────────────────────
# По образцу _math_mask из fix_latex_junk, плюс \begin{...}...\end{...} и
# защита от экранированного доллара-валюты (\$): содержимое формул не трогаем
# ни при каких условиях.
_MATH_RE = re.compile(
    r'(?<!\\)\$\$[\s\S]{0,3000}?\$\$'
    r'|(?<!\\)\$(?:\\.|[^$\\\n]){0,400}?\$'
    r'|\\\([\s\S]{0,800}?\\\)'
    r'|\\\[[\s\S]{0,3000}?\\\]'
    r'|\\begin\{([A-Za-z*]+)\}[\s\S]{0,4000}?\\end\{\1\}'
)


def _math_mask(text):
    # type: (str) -> List[bool]
    mask = [False] * len(text)
    for m in _MATH_RE.finditer(text):
        for k in range(m.start(), m.end()):
            mask[k] = True
    return mask


def build_shadow(text):
    # type: (str) -> Tuple[str, List[bool]]
    """Возвращает («тень» текста, [i-й \\n внутри формулы?]).

    В тени каждый символ формулы заменён MATH_CH, но переводы строк
    сохранены на своих местах — тень построчно совпадает с оригиналом по
    длинам, и правила границ могут не бояться содержимого формул.
    """
    mask = _math_mask(text)
    chars = []
    nl_in_math = []
    for i, ch in enumerate(text):
        if ch == '\n':
            chars.append('\n')
            nl_in_math.append(mask[i])
        else:
            chars.append(MATH_CH if mask[i] else ch)
    return ''.join(chars), nl_in_math


# ── Регулярки структурных строк ──────────────────────────────────────────────

# Маркеры подпунктов/списков в начале строки. Требуем пробел после «а)»/«1.» —
# так «г. Москва» в середине фразы не примет город за пункт списка (а если
# примет — мы просто НЕ склеим, ошибка в безопасную сторону).
LIST_MARKER_RE = re.compile(
    r'^\s*(?:'
    r'[•‣▪◦*]\s*'
    r'|[-–—]\s+'
    r'|\(?[а-яёa-zА-ЯЁA-Z][.)]\s'
    r'|\(?\d{1,3}[.)]\s'
    r'|\(\d{1,3}\)\s*'
    r'|\\item\b'
    r')'
)

SERVICE_LABEL_RE = re.compile(
    r'^\s*\(?(?:решение|ответ|дано|найти|примечание|подсказка|указание|'
    r'пояснение|комментарий|критерии|обоснование|справочно|источник|вопрос|'
    r'задача|задание|часть|вариант|пункт|итого|вывод|solution|answer|hint|note)'
    r'\s*(?:\d{1,3}\s*)?[:.)]', re.IGNORECASE)

_DISPLAY_OPEN_RE = re.compile(r'^\s*(?:\$\$|\\\[|\\begin\{)')
_DISPLAY_CLOSE_RE = re.compile(r'(?:\$\$|\\\]|\\end\{[A-Za-z*]+\})\s*[.,;:]?\s*$')

_TABLE_SEP_RE = re.compile(r'^\s*\|?[\s:|-]+\|[\s:|-]*$')

# Строка из одних цифр/знаков (без единой буквы): столбики значений осей
# графика («700», «1980 1985 1990 1995»), номера страниц, куски таблиц.
_NUMERIC_LINE_RE = re.compile(r'^[\d\s.,;:%()+*/^=<>≈±−–—-]+$')

# Строка-показатель «Метка: число» (national accounts из #50095 и подобные).
_LABEL_NUM_RE = re.compile(r'^[^:]{1,80}:\s*[+−-]?[\d\s.,%]+$')

# Висячие служебные слова: строка, оборванная на предлоге/союзе/частице, —
# верный признак технического переноса, клеим даже перед заглавной буквой.
HANGING_WORDS = frozenset('''
в во на за к ко с со у о об обо от ото до по под подо над надо при про для
без безо через сквозь между перед передо около вокруг из изо среди против
вдоль возле кроме помимо согласно благодаря вопреки а и но да или либо ни
не же ль ли бы б что чтобы как когда если хотя пока чем тем то
a an the of in on at to for and or nor but is are was were be been am by
with from as that which this these those it its if than then so such not
'''.split())

_HANG_TAIL_RE = re.compile(r'(?:^|[\s(«„"])([а-яёa-z]{1,9})$')

# ── Дефисные разрывы слова ───────────────────────────────────────────────────
# Левые половинки, при которых дефис похож на осмысленный (компоненты
# дефисных слов), — такие случаи не трогаем, а логируем:
LEFT_DOUBT = frozenset('''во кое по из пол полу юго северо южно западно
восточно экс вице санкт нью сан общественно социально научно учебно
кол
'''.split())  # «кол» — сокращение «кол-во/кол-ву»: дефис в нём настоящий (#42377)
# Правые половинки-частицы и хвосты наречий (во-первых, по-моему, что-либо):
RIGHT_DOUBT = frozenset('''то либо нибудь таки ка де мол первых вторых
третьих четвертых четвёртых пятых шестых седьмых восьмых девятых десятых
моему твоему своему нашему вашему его ее её их прежнему новому старому
другому разному летнему зимнему русски английски французски немецки
видимому настоящему
'''.split())

_HYPH_LEFT_RE = re.compile(r'([а-яё]+)-$')
_HYPH_RIGHT_RE = re.compile(r'^([а-яё]+)')
_LATIN_LEFT_RE = re.compile(r'([A-Za-z]+)-$')


def _is_display_math_line(line):
    # type: (str) -> bool
    s = line.strip()
    if not s:
        return False
    return bool(_DISPLAY_OPEN_RE.match(s) or _DISPLAY_CLOSE_RE.search(s))


def _is_tableish(shadow_line):
    # type: (str) -> bool
    s = shadow_line.strip()
    if not s:
        return False
    if '\\hline' in s:
        return True
    if s.startswith('|') and s.count('|') >= 2:
        return True
    if s.count('&') >= 2:
        return True
    return bool(_TABLE_SEP_RE.match(s))


def _is_numeric_line(shadow_line):
    # type: (str) -> bool
    s = shadow_line.strip()
    if not s:
        return False
    return any(c.isdigit() for c in s) and bool(_NUMERIC_LINE_RE.match(s))


def _strong_ending(tail):
    # type: (str) -> bool
    """«Сильный» обрыв A: конструкция очевидно не закончена, продолжение
    клеим даже если оно начинается с заглавной буквы или цифры."""
    last = tail[-1]
    if last in ',(«„':
        return True
    if last in '=+*/×·−':
        return True
    if last in '–—':
        return True
    m = _HANG_TAIL_RE.search(tail)
    return bool(m and m.group(1) in HANGING_WORDS)


def classify_boundary(ra, rb, sa, sb):
    # type: (str, str, str, str) -> Tuple[str, str]
    """Решение по границе между строками A и B.

    ra/rb — реальные строки, sa/sb — их «тени» (математика заменена MATH_CH).
    Возвращает пару (действие, деталь):
      ('glue', вид) | ('hyphen_join', слово) | ('hyphen_doubt', контекст) |
      ('keep', причина).
    """
    rb_l = rb.lstrip()
    sb_l = sb.lstrip()
    sa_r = sa.rstrip()

    # 1. Структурные признаки — приоритет у «не трогать».
    if LIST_MARKER_RE.match(rb):
        return ('keep', 'list_marker')
    if SERVICE_LABEL_RE.match(rb_l):
        return ('keep', 'service_label')
    if _is_display_math_line(ra) or _is_display_math_line(rb):
        return ('keep', 'display_math')
    if _is_tableish(sa_r) or _is_tableish(sb_l):
        return ('keep', 'table_row')
    if _is_numeric_line(sa_r) or _is_numeric_line(sb_l):
        return ('keep', 'numeric_line')
    if _LABEL_NUM_RE.match(sa_r.strip()) and _LABEL_NUM_RE.match(sb_l.strip()):
        return ('keep', 'label_number_pair')

    # 2. Как заканчивается A (закрывашки не мешают увидеть пунктуацию).
    tail = sa_r
    while tail and tail[-1] in LINE_CLOSERS:
        tail = tail[:-1]
    tail = tail.rstrip()
    if not tail:
        return ('keep', 'empty_tail')
    last = tail[-1]
    if last in TERMINAL_PUNCT:
        return ('keep', 'terminated')
    if last == ':':
        return ('keep', 'colon_intro')

    # 3. Дефисный разрыв слова.
    if last == '-':
        m_left = _HYPH_LEFT_RE.search(tail)
        m_right = _HYPH_RIGHT_RE.match(rb_l)
        if m_left and m_right:
            left, right = m_left.group(1), m_right.group(1)
            if (len(left) >= 2 and len(right) >= 2
                    and left not in LEFT_DOUBT and right not in RIGHT_DOUBT):
                return ('hyphen_join', left + '-' + right)
            return ('hyphen_doubt', left + '-' + right)
        m_lat = _LATIN_LEFT_RE.search(tail)
        if m_lat and rb_l and rb_l[0].isalpha():
            # латиница: по ТЗ дефис убираем только у кириллицы — в лог
            return ('hyphen_doubt', m_lat.group(1) + '-' + rb_l[:12])
        return ('hyphen_doubt', tail[-12:] + ' | ' + rb_l[:12])

    # 4. Как начинается B.
    first = sb_l[0]
    if first == MATH_CH:
        return ('keep', 'math_start')
    if first == '\\':
        if rb_l.startswith('\\$') and len(rb_l) > 2 and rb_l[2].isdigit():
            # экранированный доллар-валюта: «...price is\n\$10, which...»
            if (last.isalpha() and last.islower()) or last == ',' or _strong_ending(tail):
                return ('glue', 'currency')
        return ('keep', 'latex_command_start')
    if first.isalpha() and first.islower():
        return ('glue', 'lowercase')
    if first in ',;)»':
        return ('glue', 'punct_continuation')
    if first == '=':
        return ('glue', 'operator')
    if first.isdigit():
        if (last.isalpha() and last.islower()) or last == ',' or _strong_ending(tail):
            return ('glue', 'digit_continuation')
        return ('keep', 'digit_unclear')
    if first == '(' and len(sb_l) > 1 and sb_l[1].isalpha() and sb_l[1].islower():
        return ('glue', 'paren_continuation')
    if first.isalpha() and first.isupper():
        if _strong_ending(tail):
            return ('glue', 'upper_after_strong')
        return ('keep', 'upper_start')
    return ('keep', 'other_start')


class FieldResult(object):
    """Итог склейки одного текстового поля (statement или подпункт)."""

    def __init__(self):
        self.glue_count = 0        # склеек \n → пробел
        self.hyphen_count = 0      # дефисных склеек встык
        self.doubtful = []         # type: List[str]  # сомнительные дефисы
        self.keep_reasons = Counter()
        self.glue_kinds = Counter()
        self.borderline = None     # type: Optional[str]  # причина предохранителя
        self.new_text = None       # type: Optional[str]  # None = не изменилось

    @property
    def changes(self):
        # type: () -> int
        return self.glue_count + self.hyphen_count


def glue_field(text):
    # type: (str) -> FieldResult
    """Склеивает нарезку в одном поле. Чистая функция: базы не касается.

    При сработавшем предохранителе new_text всё равно заполняется (чтобы
    предпросмотр мог показать, ЧТО получилось бы), но res.borderline
    непуст — применять такое поле нельзя.
    """
    res = FieldResult()
    if not text or '\n' not in text:
        return res

    shadow, nl_in_math = build_shadow(text)
    rlines = text.split('\n')
    slines = shadow.split('\n')

    out = []           # готовые строки результата
    paras = []         # (длина, из скольких строк собрана) — для предохранителя
    cur_r, cur_s = rlines[0], slines[0]
    merged = 1

    for k in range(len(rlines) - 1):
        nxt_r, nxt_s = rlines[k + 1], slines[k + 1]
        if nl_in_math[k]:
            action = ('keep', 'inside_math')
        elif not cur_r.strip() or not nxt_r.strip():
            action = ('keep', 'blank')
        else:
            action = classify_boundary(cur_r, nxt_r, cur_s, nxt_s)

        kind = action[0]
        if kind == 'glue':
            res.glue_count += 1
            res.glue_kinds[action[1]] += 1
            cur_r = cur_r.rstrip() + ' ' + nxt_r.lstrip()
            cur_s = cur_s.rstrip() + ' ' + nxt_s.lstrip()
            merged += 1
        elif kind == 'hyphen_join':
            res.hyphen_count += 1
            res.glue_kinds['hyphen'] += 1
            cur_r = cur_r.rstrip()[:-1] + nxt_r.lstrip()
            cur_s = cur_s.rstrip()[:-1] + nxt_s.lstrip()
            merged += 1
        else:
            if kind == 'hyphen_doubt':
                res.doubtful.append(action[1])
                res.keep_reasons['hyphen_doubt'] += 1
            else:
                res.keep_reasons[action[1]] += 1
            paras.append((len(cur_r), merged))
            out.append(cur_r)
            cur_r, cur_s = nxt_r, nxt_s
            merged = 1

    paras.append((len(cur_r), merged))
    out.append(cur_r)

    if res.changes == 0:
        return res

    new_text = '\n'.join(out)
    if new_text == text:
        return res
    res.new_text = new_text

    if res.changes > MAX_GLUES_PER_FIELD:
        res.borderline = 'too_many_glues: {} склеек'.format(res.changes)
        return res
    for plen, pmerged in paras:
        if plen > MAX_GLUED_PARA_LEN and pmerged >= MIN_LINES_FOR_PARA_GUARD:
            res.borderline = 'giant_paragraph: {} симв. из {} строк'.format(
                plen, pmerged)
            return res
    return res


# ── Команда ──────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = ('Склейка построчной PDF-нарезки в условиях задач. '
            'Без --confirm — только dry-run и отчёты, база не меняется.')

    def add_arguments(self, parser):
        parser.add_argument('--confirm', action='store_true',
                            help='Записать изменения в базу (по умолчанию dry-run).')
        parser.add_argument('--source-id', default='',
                            help='Список id источников через запятую '
                                 '(по умолчанию — 16 источников жёсткой нарезки).')
        parser.add_argument('--limit', type=int, default=0,
                            help='Обработать только первые N задач (быстрая проба).')
        parser.add_argument('--examples', type=int, default=0,
                            help='Сколько примеров ДО/ПОСЛЕ на источник добавить в md-отчёт.')
        parser.add_argument('--preview', action='store_true',
                            help='Собрать HTML-предпросмотр reports/glue_lines/preview.html.')
        parser.add_argument('--include-flagged', action='store_true',
                            help='Обрабатывать и задачи с needs_quality_review '
                                 '(по умолчанию — только видимый пул, как в полном скане).')

    def handle(self, *args, **opts):
        confirm = opts['confirm']
        os.makedirs(REPORT_DIR, exist_ok=True)

        if opts['source_id']:
            source_ids = [int(x) for x in opts['source_id'].split(',') if x.strip()]
        else:
            source_ids = list(HARD_WRAP_SOURCE_IDS)
        source_names = dict(Source.objects.filter(
            id__in=source_ids).values_list('id', 'name'))

        qs = (Problem.objects
              .filter(source_references__source_id__in=source_ids,
                      status='published')
              .distinct()
              .order_by('id')
              .prefetch_related('parts', 'source_references'))
        if not opts['include_flagged']:
            qs = qs.filter(needs_quality_review=False)
        if opts['limit']:
            qs = qs[:opts['limit']]

        self.stdout.write('Источники: {}'.format(
            ', '.join('{} ({})'.format(sid, source_names.get(sid, '?'))
                      for sid in source_ids)))

        # records: id, sid, поля-диффы; агрегаты по источникам
        records = []          # type: List[Dict]
        per_source = {sid: Counter() for sid in source_ids}
        non_idempotent = []   # type: List[Tuple[int, str]]
        doubtful_rows = []    # type: List[str]
        borderline_rows = []  # type: List[str]
        total_keep = Counter()   # почему границы НЕ склеены (вся выборка)
        total_glue = Counter()   # виды склеек (вся выборка)

        for p in qs:
            ref_sids = [r.source_id for r in p.source_references.all()]
            sid = next((s for s in ref_sids if s in per_source), None)
            if sid is None:
                continue
            agg = per_source[sid]
            agg['problems'] += 1

            fields = []  # (метка, старый, новый, FieldResult)
            for label, value in self._iter_fields(p):
                r = glue_field(value)
                total_keep.update(r.keep_reasons)
                total_glue.update(r.glue_kinds)
                for d in r.doubtful:
                    doubtful_rows.append('#{}\t{}\t{}'.format(p.id, label, d))
                    agg['hyphen_doubtful'] += 1
                if r.new_text is not None:
                    fields.append((label, value, r.new_text, r))

            if not fields:
                continue

            border = next((r.borderline for _, _, _, r in fields if r.borderline), None)
            record = {
                'id': p.id, 'sid': sid,
                'title': p.title or '',
                'fields': fields,
                'glues': sum(r.changes for _, _, _, r in fields),
                'borderline': border,
            }
            records.append(record)

            if border:
                # предохранитель: задача пропускается целиком
                agg['borderline'] += 1
                for label, _, _, r in fields:
                    if r.borderline:
                        borderline_rows.append('#{}\t{}\t{}'.format(
                            p.id, label, r.borderline))
                continue

            agg['changed'] += 1
            agg['glued_lines'] += record['glues']
            agg['hyphens'] += sum(r.hyphen_count for _, _, _, r in fields)

            # идемпотентность: повторная склейка уже склеенного = 0 изменений
            for label, _, new_text, _ in fields:
                second = glue_field(new_text)
                if second.new_text is not None:
                    non_idempotent.append((p.id, label))

        self._print_table(per_source, source_names, source_ids)
        self.stdout.write('')
        self.stdout.write('Виды склеек: ' + ', '.join(
            '{}: {:,}'.format(k, v) for k, v in total_glue.most_common()))
        self.stdout.write('Причины «не клеить»: ' + ', '.join(
            '{}: {:,}'.format(k, v) for k, v in total_keep.most_common()))
        self.stdout.write('Идемпотентность: {}'.format(
            'все изменённые поля прошли' if not non_idempotent
            else '{} полей НЕ прошли'.format(len(non_idempotent))))
        for pid, label in non_idempotent[:10]:
            self.stdout.write('  WARN не идемпотентно: #{} {}'.format(pid, label))

        self._write_logs(doubtful_rows, borderline_rows)
        self._write_stats_md(per_source, source_names, source_ids, records,
                             opts['examples'], total_keep, total_glue)
        if opts['preview']:
            self._write_preview(records, source_names)

        if not confirm:
            self.stdout.write('Режим dry-run: база НЕ изменена. '
                              'Для записи добавьте --confirm.')
            return

        self._apply(records)

    # ── Обход полей ──────────────────────────────────────────────────────────

    @staticmethod
    def _iter_fields(problem):
        # type: (Problem) -> List[Tuple[str, str]]
        fields = []
        if problem.statement:
            fields.append(('statement', problem.statement))
        for part in problem.parts.all():
            if part.statement:
                fields.append(('part:{}'.format(part.label), part.statement))
        return fields

    # ── Отчёты ───────────────────────────────────────────────────────────────

    def _print_table(self, per_source, source_names, source_ids):
        header = ('{:<4} {:<42} {:>7} {:>9} {:>9} {:>7} {:>8} {:>8}'.format(
            'id', 'источник', 'задач', 'изменится', 'склеек', 'дефис',
            'предохр', 'дефис?'))
        self.stdout.write('')
        self.stdout.write(header)
        self.stdout.write('-' * len(header))
        tot = Counter()
        for sid in source_ids:
            agg = per_source[sid]
            for key in ('problems', 'changed', 'glued_lines', 'hyphens',
                        'borderline', 'hyphen_doubtful'):
                tot[key] += agg[key]
            self.stdout.write('{:<4} {:<42} {:>7} {:>9} {:>9} {:>7} {:>8} {:>8}'.format(
                sid, (source_names.get(sid, '?'))[:42], agg['problems'],
                agg['changed'], agg['glued_lines'], agg['hyphens'],
                agg['borderline'], agg['hyphen_doubtful']))
        self.stdout.write('-' * len(header))
        self.stdout.write('{:<4} {:<42} {:>7} {:>9} {:>9} {:>7} {:>8} {:>8}'.format(
            '', 'ИТОГО', tot['problems'], tot['changed'], tot['glued_lines'],
            tot['hyphens'], tot['borderline'], tot['hyphen_doubtful']))

    def _write_logs(self, doubtful_rows, borderline_rows):
        doubt_path = os.path.join(REPORT_DIR, 'hyphen_doubtful.txt')
        with open(doubt_path, 'w', encoding='utf-8') as f:
            f.write('# Сомнительные дефисные разрывы — НЕ тронуты, ждут глаз\n')
            f.write('# формат: #id<TAB>поле<TAB>левая-правая половинки\n')
            for row in doubtful_rows:
                f.write(row + '\n')
        border_path = os.path.join(REPORT_DIR, 'borderline.txt')
        with open(border_path, 'w', encoding='utf-8') as f:
            f.write('# Задачи, пропущенные предохранителем — изменения НЕ применяются\n')
            f.write('# формат: #id<TAB>поле<TAB>причина\n')
            for row in borderline_rows:
                f.write(row + '\n')
        self.stdout.write('Сомнительные дефисы → {} ({})'.format(
            doubt_path, len(doubtful_rows)))
        self.stdout.write('Пограничные (предохранитель) → {} ({})'.format(
            border_path, len(borderline_rows)))

    def _write_stats_md(self, per_source, source_names, source_ids, records,
                        examples_per_source, total_keep=None, total_glue=None):
        path = os.path.join(REPORT_DIR, 'dry_run_stats.md')
        lines = []
        lines.append('# Склейка построчной нарезки — dry-run')
        lines.append('')
        lines.append('Дата: {}. База НЕ менялась.'.format(
            datetime.now().strftime('%Y-%m-%d %H:%M')))
        lines.append('')
        lines.append('Пороги предохранителя: > {} склеек на поле или абзац > {} симв. '
                     'из ≥ {} строк → задача пропускается.'.format(
                         MAX_GLUES_PER_FIELD, MAX_GLUED_PARA_LEN,
                         MIN_LINES_FOR_PARA_GUARD))
        lines.append('')
        lines.append('| id | Источник | Задач | Изменится | Строк склеено | Дефисных | Предохранитель | Дефис-сомнения |')
        lines.append('|---:|---|---:|---:|---:|---:|---:|---:|')
        tot = Counter()
        for sid in source_ids:
            agg = per_source[sid]
            for key in ('problems', 'changed', 'glued_lines', 'hyphens',
                        'borderline', 'hyphen_doubtful'):
                tot[key] += agg[key]
            lines.append('| {} | {} | {} | {} | {} | {} | {} | {} |'.format(
                sid, source_names.get(sid, '?'), agg['problems'],
                agg['changed'], agg['glued_lines'], agg['hyphens'],
                agg['borderline'], agg['hyphen_doubtful']))
        lines.append('| — | **ИТОГО** | **{}** | **{}** | **{}** | **{}** | **{}** | **{}** |'.format(
            tot['problems'], tot['changed'], tot['glued_lines'],
            tot['hyphens'], tot['borderline'], tot['hyphen_doubtful']))
        lines.append('')

        if total_glue:
            lines.append('Виды склеек: ' + ', '.join(
                '{}: {:,}'.format(k, v) for k, v in total_glue.most_common()) + '.')
            lines.append('')
        if total_keep:
            lines.append('Причины «не клеить»: ' + ', '.join(
                '{}: {:,}'.format(k, v) for k, v in total_keep.most_common()) + '.')
            lines.append('')

        # распределение склеек на задачу — обоснование порогов предохранителя
        glue_counts = sorted(r['glues'] for r in records if not r['borderline'])
        if glue_counts:
            def pct(q):
                return glue_counts[min(len(glue_counts) - 1,
                                       int(q * len(glue_counts)))]
            lines.append('Склеек на изменённую задачу: медиана {}, p90 {}, p99 {}, максимум {}.'.format(
                pct(0.5), pct(0.9), pct(0.99), glue_counts[-1]))
            lines.append('')

        if examples_per_source:
            rng = random.Random(2026)
            lines.append('## Примеры ДО/ПОСЛЕ')
            by_sid = {}
            for r in records:
                if not r['borderline']:
                    by_sid.setdefault(r['sid'], []).append(r)
            for sid in source_ids:
                pool = by_sid.get(sid, [])
                if not pool:
                    continue
                lines.append('')
                lines.append('### #{} {}'.format(sid, source_names.get(sid, '?')))
                for rec in rng.sample(pool, min(examples_per_source, len(pool))):
                    label, old, new, _ = rec['fields'][0]
                    lines.append('')
                    lines.append('**#{}** ({}):'.format(rec['id'], label))
                    lines.append('```')
                    lines.append('ДО:    ' + old[:400].replace('\n', '⏎'))
                    lines.append('ПОСЛЕ: ' + new[:400].replace('\n', '⏎'))
                    lines.append('```')
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        self.stdout.write('Отчёт → ' + path)

    # ── HTML-предпросмотр ────────────────────────────────────────────────────

    def _write_preview(self, records, source_names):
        path = os.path.join(REPORT_DIR, 'preview.html')
        html = build_preview_html(records, source_names)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(html)
        self.stdout.write('Предпросмотр → ' + path)

    # ── Запись в базу ────────────────────────────────────────────────────────

    def _apply(self, records):
        # Бэкапим именно ту базу, в которую пишем (в тестах это тестовая БД,
        # и копировать боевой db.sqlite3 не нужно).
        from django.db import connection
        db_path = str(connection.settings_dict.get('NAME') or '')
        if (os.path.basename(db_path) == 'db.sqlite3'
                and os.path.exists(db_path)):
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            os.makedirs('backups', exist_ok=True)
            bk = os.path.join('backups', 'before_glue_lines_{}.sqlite3'.format(ts))
            shutil.copy2(db_path, bk)
            self.stdout.write('Бэкап → {}'.format(bk))

        stmt_map = {}   # pid -> новый statement
        part_map = {}   # (pid, label) -> новый текст подпункта
        changed_pids = set()
        for rec in records:
            if rec['borderline']:
                continue  # предохранитель: не применяем
            for label, _, new_text, _ in rec['fields']:
                if label == 'statement':
                    stmt_map[rec['id']] = new_text
                else:
                    part_map[(rec['id'], label.split(':', 1)[1])] = new_text
                changed_pids.add(rec['id'])

        if stmt_map:
            updates = []
            for p in Problem.objects.filter(id__in=list(stmt_map.keys())):
                p.statement = stmt_map[p.id]
                updates.append(p)
            Problem.objects.bulk_update(updates, ['statement'], batch_size=500)
            self.stdout.write('Обновлено statement: {:,}'.format(len(updates)))

        if part_map:
            pids = list({pid for pid, _ in part_map})
            updates = []
            for part in ProblemPart.objects.filter(problem_id__in=pids):
                key = (part.problem_id, part.label)
                if key in part_map:
                    part.statement = part_map[key]
                    updates.append(part)
            ProblemPart.objects.bulk_update(updates, ['statement'], batch_size=500)
            self.stdout.write('Обновлено подпунктов: {:,}'.format(len(updates)))

        ids_path = os.path.join(REPORT_DIR, 'changed_ids.txt')
        with open(ids_path, 'w', encoding='utf-8') as f:
            for pid in sorted(changed_pids):
                f.write('{}\n'.format(pid))
        self.stdout.write('Изменено задач: {:,}. Список для пересчёта '
                          'эмбеддингов → {}'.format(len(changed_pids), ids_path))
        self.stdout.write('НЕ ЗАБЫТЬ: пересчитать эмбеддинги изменённых id '
                          '(см. CLAUDE.md, «ловушка done-файла»).')


# ── Сборка HTML-предпросмотра (вынесена из класса для тестируемости) ─────────

PREVIEW_PER_SOURCE = 4
PREVIEW_TOP_N = 10
PREVIEW_BORDERLINE_N = 20

_PREVIEW_HEAD = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Склейка нарезки — предпросмотр ДО/ПОСЛЕ</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js" onload="initKaTeX()"></script>
<style>
body { font-family: -apple-system, 'Segoe UI', sans-serif; margin: 0;
       background: #f4f4f6; color: #1a1a1a; }
header { background: #1a1f2e; color: #fff; padding: 14px 26px; }
header h1 { margin: 0; font-size: 19px; }
header p { margin: 6px 0 0; font-size: 13px; color: #cbd0dc; }
main { max-width: 1280px; margin: 0 auto; padding: 22px; }
h2.section { margin: 34px 0 10px; font-size: 18px; border-bottom: 2px solid #BE185D;
             padding-bottom: 6px; }
h3.source { margin: 22px 0 8px; font-size: 15px; color: #444; }
.card { background: #fff; border: 1px solid #ddd; border-radius: 10px;
        padding: 14px 18px; margin: 12px 0; }
.card.borderline { border-color: #b26b00; background: #fffaf2; }
.meta { font-size: 12px; color: #666; margin-bottom: 8px; }
.meta b { color: #1a1a1a; }
.meta .chip { background: #f0f0f2; border-radius: 20px; padding: 2px 8px; margin-left: 6px; }
.meta .warn { background: #fdf1de; color: #b26b00; }
.fieldlabel { font-size: 11px; font-weight: 600; text-transform: uppercase;
              color: #888; margin: 10px 0 4px; }
.cols { display: flex; gap: 14px; }
.col { flex: 1; min-width: 0; }
.col-label { font-size: 11px; font-weight: 700; color: #666; margin-bottom: 4px; }
.text { background: #fafafa; border: 1px solid #e5e5e5; border-radius: 8px;
        padding: 10px 12px; font-size: 14px; line-height: 1.6;
        white-space: pre-line; word-wrap: break-word; }
.col.after .text { background: #f2fbf5; border-color: #cde8d6; }
@media (max-width: 900px) { .cols { flex-direction: column; } }
</style>
</head>
<body>
<header>
<h1>Склейка построчной нарезки — предпросмотр ДО/ПОСЛЕ</h1>
<p>Обе колонки показаны с white-space: pre-line — так видно фактические переносы строк.
Слева — как текст хранится сейчас, справа — как он будет храниться после склейки. База НЕ менялась.</p>
</header>
<main>
"""

# JS-обработка валютных долларов — как в problems/diagnostics.py, чтобы \\$
# не спаривались в псевдоформулы при рендере KaTeX.
_PREVIEW_TAIL = """
</main>
<script>
var DOLLAR_SENTINEL = '\\uE000';
function maskEscapedDollars(root) {
  var walker = document.createTreeWalker(root || document.body, NodeFilter.SHOW_TEXT, null);
  var node;
  while ((node = walker.nextNode())) {
    var p = node.parentNode && node.parentNode.nodeName;
    if (p === 'SCRIPT' || p === 'STYLE' || p === 'TEXTAREA') continue;
    if (node.nodeValue.indexOf('\\\\$') !== -1) {
      node.nodeValue = node.nodeValue.split('\\\\$').join(DOLLAR_SENTINEL);
    }
  }
}
function fixCurrencyDollars(root) {
  var walker = document.createTreeWalker(root || document.body, NodeFilter.SHOW_TEXT, null);
  var node;
  while ((node = walker.nextNode())) {
    var p = node.parentNode && node.parentNode.nodeName;
    if (p === 'SCRIPT' || p === 'STYLE' || p === 'TEXTAREA') continue;
    var v = node.nodeValue;
    if (v.indexOf(DOLLAR_SENTINEL) !== -1 || v.indexOf('\\\\$') !== -1 ||
        v.indexOf('\\\\_') !== -1 || v.indexOf('\\\\&') !== -1 ||
        v.indexOf('\\\\#') !== -1) {
      node.nodeValue = v.split(DOLLAR_SENTINEL).join('$').split('\\\\$').join('$')
                        .split('\\\\_').join('_').split('\\\\&').join('&')
                        .split('\\\\#').join('#');
    }
  }
}
function initKaTeX() {
  maskEscapedDollars(document.body);
  renderMathInElement(document.body, {
    delimiters: [
      { left: '$$',  right: '$$',  display: true  },
      { left: '$',   right: '$',   display: false },
      { left: '\\\\[', right: '\\\\]', display: true  },
      { left: '\\\\(', right: '\\\\)', display: false }
    ],
    throwOnError: false
  });
  fixCurrencyDollars(document.body);
}
document.addEventListener('DOMContentLoaded', function () {
  fixCurrencyDollars(document.body);
});
</script>
</body>
</html>
"""


def _preview_card(rec, source_names):
    # type: (Dict, Dict) -> str
    esc = html_lib.escape
    chips = '<span class="chip">склеек: {}</span>'.format(rec['glues'])
    if rec['borderline']:
        chips += '<span class="chip warn">предохранитель: {}</span>'.format(
            esc(rec['borderline']))
    parts = ['<div class="card{}">'.format(' borderline' if rec['borderline'] else '')]
    parts.append(
        '<div class="meta"><b>#{pid}</b> — {src}{chips} — '
        '<a href="http://127.0.0.1:8000/catalog/{pid}/" target="_blank">открыть в каталоге</a></div>'.format(
            pid=rec['id'], src=esc(source_names.get(rec['sid'], '?')), chips=chips))
    for label, old, new, _ in rec['fields']:
        parts.append('<div class="fieldlabel">{}</div>'.format(esc(label)))
        parts.append('<div class="cols">')
        parts.append('<div class="col before"><div class="col-label">ДО</div>'
                     '<div class="text">{}</div></div>'.format(esc(old)))
        parts.append('<div class="col after"><div class="col-label">ПОСЛЕ</div>'
                     '<div class="text">{}</div></div>'.format(esc(new)))
        parts.append('</div>')
    parts.append('</div>')
    return '\n'.join(parts)


def build_preview_html(records, source_names):
    # type: (List[Dict], Dict) -> str
    esc = html_lib.escape
    rng = random.Random(2026)
    clean = [r for r in records if not r['borderline']]
    border = [r for r in records if r['borderline']]

    shown = set()
    out = [_PREVIEW_HEAD]

    out.append('<h2 class="section">По источникам — по {} случайные задачи</h2>'.format(
        PREVIEW_PER_SOURCE))
    by_sid = {}
    for r in clean:
        by_sid.setdefault(r['sid'], []).append(r)
    for sid in sorted(by_sid, key=lambda s: -len(by_sid[s])):
        pool = by_sid[sid]
        sample = rng.sample(pool, min(PREVIEW_PER_SOURCE, len(pool)))
        out.append('<h3 class="source">#{} {} (изменится задач: {})</h3>'.format(
            sid, esc(source_names.get(sid, '?')), len(pool)))
        for rec in sorted(sample, key=lambda r: r['id']):
            shown.add(rec['id'])
            out.append(_preview_card(rec, source_names))

    out.append('<h2 class="section">Топ-{} по числу склеек</h2>'.format(PREVIEW_TOP_N))
    top = sorted(clean, key=lambda r: -r['glues'])[:PREVIEW_TOP_N]
    for rec in top:
        if rec['id'] in shown:
            continue
        shown.add(rec['id'])
        out.append(_preview_card(rec, source_names))

    out.append('<h2 class="section">Пограничные — пропущены предохранителем '
               '(показано до {}; правая колонка — что ПОЛУЧИЛОСЬ БЫ, '
               'но применяться не будет)</h2>'.format(PREVIEW_BORDERLINE_N))
    if not border:
        out.append('<p>Предохранитель не сработал ни разу.</p>')
    for rec in border[:PREVIEW_BORDERLINE_N]:
        out.append(_preview_card(rec, source_names))

    out.append(_PREVIEW_TAIL)
    return '\n'.join(out)
