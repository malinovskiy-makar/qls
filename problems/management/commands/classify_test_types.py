# -*- coding: utf-8 -*-
u"""classify_test_types: подвид теста по ДВУМ независимым сигналам.

Пишется ТОЛЬКО поле `problem_type`. Условие, ответ и решение не трогаются
никогда: это запрет P0 корневого CLAUDE.md.

Сигнал 1, главный: структура сырого источника из C:/Users/shipu/weconomics-data.
    SolveHub отдаёт по файлу JSON на задачу, и в файле лежит готовый ответ
    источника на оба вопроса: `is_test` (тест это или полноценная задача) и
    `check_type` (форма ответа). Ключ к банку точный: имя файла равно полю
    `hash`, а оно легло в `SourceReference.problem_number`.

Сигнал 2, контрольный: содержимое задачи в банке, БЕЗ подглядывания в сырьё.
    Варианты берутся из подпунктов `ProblemPart`, а если их нет, разбирается
    блок «Варианты ответа:» внутри `statement`. Правильный ответ читается из
    `Problem.answer`: номер варианта, буква метки подпункта, слово «Верно» или
    «Неверно», либо число.

Пишем только там, где сигналы СОШЛИСЬ. Расхождение уходит в корзину
«спорные» без записи, и в отчёте оба сигнала стоят рядом.

Ловушка, на которой споткнулась эвристика прошлой сессии (дала 3 366 «тестов»
там, где тестов 2 730). Полноценная задача с подпунктами «а) Выведите функцию
спроса, б) Найдите равновесие» выглядит как перечень вариантов, но это НЕ
тест: подпункты повелительные, блока «Варианты ответа:» нет, а `answer` хранит
ответ задачи (или пуст), а не номер выбранного варианта. Различает их
`looks_like_subtasks`, и различие показано в отчёте отдельной таблицей.

Тесты других форматов («установите соответствие», «расположите по порядку»)
в четыре типа не втискиваются: для них корзина «тест другого формата».

Запуск:
    manage.py classify_test_types --source "SolveHub" --preview
    manage.py classify_test_types --source "SolveHub" --confirm
    manage.py classify_test_types --revert
"""
import html
import json
import os
import random
import re
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from game.views import parse_exact_number
from problems.models import Problem, Source

# Четыре подвида теста. Значения совпадают с ключами GAME_TYPES сборщика пула
# (game/management/commands/build_game_pool.py): расхождение отрезало бы
# типизированные задачи от игры молча.
T_BOOL = 'тест: верно/неверно'
T_ONE = 'тест: один ответ'
T_ALL = 'тест: все верные'
T_NUM = 'тест: числовой ответ'
FOUR_TYPES = (T_BOOL, T_ONE, T_ALL, T_NUM)

# Корзины, в которые ничего не пишется.
B_DISPUTED = 'спорные'
B_OTHER_FORMAT = 'тест другого формата'
B_FULL_PROBLEM = 'полноценные задачи'
B_NO_SOURCE = 'нет в сыром источнике'
BUCKETS = (B_DISPUTED, B_OTHER_FORMAT, B_FULL_PROBLEM, B_NO_SOURCE)

RAW_ROOT = r'C:\Users\shipu\weconomics-data'

# check_type сырого SolveHub в наш подвид теста. Форматы вне этой таблицы
# («установите соответствие», несколько подвопросов, свободный текст) в
# четыре типа не втискиваем.
SOLVEHUB_TYPE = {
    'single_choice': T_ONE,
    'true_false': T_BOOL,
    'multiple_choice': T_ALL,
}
SOLVEHUB_OTHER_FORMAT = {'matching_list', 'multiple_questions'}

OPTIONS_MARKER = 'Варианты ответа:'
NUM_OPTION_RE = re.compile(r'^\s*(\d{1,2})\.\s+(.*)$')

# Подпункт полноценной задачи: буква со скобкой в начале строки.
SUBTASK_RE = re.compile(r'(?m)^\s*[а-еa-e]\)\s*\S')
# Повелительное наклонение выдаёт задание, а не вариант ответа.
IMPERATIVE_RE = re.compile(
    r'\b(?:выведите|найдите|определите|постройте|рассчитайте|вычислите'
    r'|докажите|объясните|нарисуйте|укажите,\s|сравните|оцените'
    r'|derive|find|calculate|determine|explain|draw)\b',
    re.IGNORECASE)

# Форматы, которые тестом являются, но ни в один из четырёх не ложатся.
OTHER_FORMAT_RE = re.compile(
    r'установите\s+соответствие|расположите\s+в\s+порядке'
    r'|расположите\s+по\s+порядку|соотнесите|заполните\s+пропуск',
    re.IGNORECASE)

YES_WORDS = {'верно', 'да', 'true', 'yes', 'истина'}
NO_WORDS = {'неверно', 'нет', 'false', 'no', 'ложь'}

MIN_OPTIONS_FOR_CHOICE = 3   # «один ответ» требует не меньше трёх вариантов
MIN_OPTIONS_FOR_MULTI = 2


# ---------------------------------------------------------------------------
# Разбор содержимого банка (сигнал 2)
# ---------------------------------------------------------------------------

def split_inline_options(statement):
    u"""Разобрать блок «Варианты ответа:» внутри условия.

    Возвращает (вопрос, [варианты]) либо (None, None), если блока нет или
    нумерация рваная. Нумерация обязана идти 1, 2, 3 подряд: дыра в номерах
    означает, что мы приняли за варианты что-то другое.
    """
    if OPTIONS_MARKER not in statement:
        return None, None
    head, _, tail = statement.partition(OPTIONS_MARKER)
    options = []
    expected = 1
    for line in tail.splitlines():
        if not line.strip():
            continue
        matched = NUM_OPTION_RE.match(line)
        if not matched:
            # Строка без номера продолжает предыдущий вариант (перенос).
            if options:
                options[-1] += ' ' + line.strip()
                continue
            return None, None
        if int(matched.group(1)) != expected:
            return None, None
        options.append(matched.group(2).strip())
        expected += 1
    if not options:
        return None, None
    return head.strip(), options


def normalize_label(value):
    return (value or '').strip().strip('.)').strip().lower()


def collect_options(problem):
    u"""Варианты задачи и откуда они взяты.

    Сначала подпункты ProblemPart (так лежит Сборник АА), затем встроенный
    блок «Варианты ответа:» (так лежит SolveHub). Возвращает
    (варианты, метки, источник вариантов).
    """
    parts = list(problem.parts.all())
    if 2 <= len(parts) <= 6:
        return ([(p.statement or '').strip() for p in parts],
                [normalize_label(p.label) for p in parts],
                'подпункты ProblemPart')
    _, inline = split_inline_options(problem.statement or '')
    if inline:
        return inline, [str(i + 1) for i in range(len(inline))], 'блок в условии'
    return [], [], 'вариантов нет'


def answer_positions(answer, labels):
    u"""Какие варианты названы в Problem.answer, позициями с нуля.

    Понимает две записи: строки вида «3. дохода» (номер варианта) и голые
    метки подпунктов «аб», «а, в».
    """
    text = answer or ''
    found = []
    for line in text.splitlines():
        matched = NUM_OPTION_RE.match(line)
        if matched:
            index = int(matched.group(1)) - 1
            if 0 <= index < len(labels):
                found.append(index)
    if found:
        return sorted(set(found)), 'номер варианта'
    letters = [ch for ch in text.strip().lower() if ch.isalpha()]
    if letters and all(ch in labels for ch in letters):
        return sorted({labels.index(ch) for ch in letters}), 'буква метки'
    return [], 'не распознан'


def looks_like_subtasks(problem):
    u"""Правда ли это полноценная задача с подпунктами, а не тест.

    Признак: в условии есть подпункты «а)», «б)» И нет блока вариантов,
    И хотя бы один подпункт написан в повелительном наклонении. Одного
    только «а)» мало: у теста тоже бывают буквенные метки.
    """
    statement = problem.statement or ''
    if OPTIONS_MARKER in statement:
        return False
    if not SUBTASK_RE.search(statement):
        return False
    return bool(IMPERATIVE_RE.search(statement))


def signal_content(problem):
    u"""Сигнал 2: что говорит содержимое задачи в банке.

    Возвращает (вердикт, пояснение). Вердикт это один из четырёх типов,
    либо название корзины.
    """
    statement = problem.statement or ''
    answer = (problem.answer or '').strip()

    if OTHER_FORMAT_RE.search(statement):
        return B_OTHER_FORMAT, 'в условии просьба сопоставить или упорядочить'

    if looks_like_subtasks(problem):
        return B_FULL_PROBLEM, 'подпункты в повелительном наклонении, блока вариантов нет'

    options, labels, origin = collect_options(problem)
    plain = normalize_label(answer)

    if not options:
        if plain in YES_WORDS or plain in NO_WORDS:
            return T_BOOL, 'вариантов нет, ответ это «верно» или «неверно»'
        if answer and parse_exact_number(answer) is not None:
            return T_NUM, 'вариантов нет, ответ разобрался как число'
        return B_FULL_PROBLEM, 'вариантов нет, ответ не число и не данетка (%s)' % origin

    # Данетка, разложенная на подпункты «Верно» и «Неверно».
    texts = sorted(normalize_label(o) for o in options)
    if texts == ['верно', 'неверно']:
        positions, how = answer_positions(answer, labels)
        if len(positions) == 1:
            return T_BOOL, 'два подпункта «Верно» и «Неверно», ответ по %s' % how
        return B_DISPUTED, 'данетка, но правильный вариант не определился'

    positions, how = answer_positions(answer, labels)
    if not positions:
        return B_DISPUTED, 'варианты есть (%s), но ответ не сопоставился' % origin
    if len(positions) == 1:
        if len(options) >= MIN_OPTIONS_FOR_CHOICE:
            return T_ONE, '%d варианта (%s), ответ называет один, по %s' % (
                len(options), origin, how)
        return B_DISPUTED, 'один ответ, но вариантов всего %d' % len(options)
    if len(options) >= MIN_OPTIONS_FOR_MULTI:
        return T_ALL, '%d варианта (%s), ответ называет %d, по %s' % (
            len(options), origin, len(positions), how)
    return B_DISPUTED, 'несколько ответов при %d вариантах' % len(options)


# ---------------------------------------------------------------------------
# Сырые источники (сигнал 1)
# ---------------------------------------------------------------------------

def load_solvehub_raw(root=RAW_ROOT):
    u"""Прочитать выгрузку SolveHub: hash задачи в её паспорт.

    Папка сырья открыта ТОЛЬКО НА ЧТЕНИЕ, ничего в неё не пишем.
    """
    folder = os.path.join(root, 'solvehub', 'problems')
    if not os.path.isdir(folder):
        raise CommandError('нет папки сырья SolveHub: %s' % folder)
    index = {}
    for name in os.listdir(folder):
        if not name.endswith('.json'):
            continue
        with open(os.path.join(folder, name), encoding='utf-8') as fh:
            data = json.load(fh)
        index[name[:-5]] = {
            'is_test': bool(data.get('is_test')),
            'check_type': data.get('check_type') or '',
            'title': data.get('title') or '',
        }
    return index


def solvehub_signal(passport):
    u"""Сигнал 1 для SolveHub: вердикт источника и как он записан."""
    if passport is None:
        return B_NO_SOURCE, 'задачи нет в выгрузке источника'
    kind = passport['check_type']
    if not passport['is_test']:
        return B_FULL_PROBLEM, 'is_test = false, check_type = %s' % (kind or 'пусто')
    if kind in SOLVEHUB_TYPE:
        return SOLVEHUB_TYPE[kind], 'is_test = true, check_type = %s' % kind
    if kind in SOLVEHUB_OTHER_FORMAT:
        return B_OTHER_FORMAT, 'is_test = true, check_type = %s' % kind
    return B_DISPUTED, 'is_test = true, но check_type = %s' % (kind or 'пусто')


def load_aa_index(root=RAW_ROOT, source_id=None):
    u"""Сигнал 1 для Сборника АА: тип, снятый с заголовков блоков PDF.

    Сырьё АА это PDF «Сборник тестов АА», и его структура («Вопросы типа
    "Верно/Неверно"», «Вопросы на один правильный ответ», «Вопросы на все
    верные ответы») была разобрана при импорте командой import_pdf_shivarov
    и записана прямо в problem_type. Самого PDF в рабочей копии нет, поэтому
    сигналом 1 служит эта запись импортёра: она и есть структура источника,
    просто снятая заранее. Здесь мы её ПРОВЕРЯЕМ содержимым, а не сочиняем
    заново, и ничего не переписываем.
    """
    index = {}
    query = Problem.objects.all()
    if source_id is not None:
        query = query.filter(source_references__source_id=source_id).distinct()
    for pid, ptype in query.values_list('id', 'problem_type'):
        index[str(pid)] = {'recorded': ptype}
    return index


def aa_signal(passport):
    if passport is None:
        return B_NO_SOURCE, 'задачи нет в разборе источника'
    recorded = passport['recorded']
    if recorded in FOUR_TYPES:
        return recorded, 'заголовок блока PDF, снят импортёром: %s' % recorded
    if recorded:
        return B_OTHER_FORMAT, 'импортёр записал нетестовый тип: %s' % recorded
    return B_FULL_PROBLEM, 'импортёр не записал тип'


def key_by_problem_number(problem, source_id):
    for ref in problem.source_references.all():
        if ref.source_id == source_id and ref.problem_number:
            return ref.problem_number
    return ''


def key_by_id(problem, source_id):
    return str(problem.id)


# Источники, у которых сигнал 1 доступен. mode='classify' значит, что тип
# будет записан; mode='verify' значит, что тип уже стоит и мы его проверяем.
RAW_ADAPTERS = {
    'solvehub': {
        'label': 'SolveHub',
        'loader': load_solvehub_raw,
        'key': key_by_problem_number,
        'signal': solvehub_signal,
        'mode': 'classify',
    },
    'аа': {
        'label': 'Сборник тестов АА',
        'loader': load_aa_index,
        'key': key_by_id,
        'signal': aa_signal,
        'mode': 'verify',
    },
}


# ---------------------------------------------------------------------------
# Свод двух сигналов
# ---------------------------------------------------------------------------

def combine(source_verdict, content_verdict):
    u"""Итог по двум сигналам. Пишем только при полном согласии.

    ⚠️ МОЛЧАНИЕ КОНТРОЛЬНОГО СИГНАЛА ЭТО НЕ СПОР. Сигнал 2 разбирает форму
    ответа и потому силён на тестах и слаб на открытых задачах: у задачи
    «посчитайте выручку» ответ «4» разбирается как число, и наивное правило
    записало бы её в числовой тест. Поэтому спором считается только случай,
    когда содержимое ЗАЯВЛЯЕТ один из четырёх типов вопреки источнику, а не
    случай, когда оно просто не смогло ничего подтвердить.

    Без этой оговорки корзина «спорные» разбухала до 1 147 задач против 60,
    и 1 109 открытых задач SolveHub выглядели бы требующими разбора руками.
    """
    if source_verdict == B_OTHER_FORMAT or content_verdict == B_OTHER_FORMAT:
        return B_OTHER_FORMAT, 'формат теста вне четырёх типов'
    if source_verdict == B_NO_SOURCE:
        return B_NO_SOURCE, 'сигнала источника нет'

    if source_verdict in FOUR_TYPES:
        if source_verdict == content_verdict:
            return source_verdict, 'сигналы совпали'
        return B_DISPUTED, 'источник назвал тип, содержимое его не подтвердило'

    # Источник говорит, что это не тест. Возражением считаем только заявку
    # содержимого на конкретный тип, а не его неспособность разобраться.
    #
    # ⚠️ «ЧИСЛОВОЙ ОТВЕТ» ЭТО ВЕРДИКТ ПОДТВЕРЖДАЮЩИЙ, А НЕ ЗАЯВЛЯЮЩИЙ. Числом
    # разбирается ответ и у теста, и у открытой расчётной задачи, и в банке
    # они выглядят одинаково: вариантов нет ни там, ни там. Замер по SolveHub
    # 2026-09-02: содержимое назвало «числовой ответ» у 0 объявленных тестов
    # и у 708 объявленных задач, причём даже самые короткие из них («В каждом
    # пункте найдите недостающее значение») это задачи. Порога по длине,
    # который бы их разделил, не существует. Поэтому голое число в ответе
    # возражением против источника не считается.
    if content_verdict in FOUR_TYPES and content_verdict != T_NUM:
        return B_DISPUTED, 'источник говорит «задача», содержимое видит тест'
    return B_FULL_PROBLEM, 'источник говорит «задача», содержимое не возражает'


# ---------------------------------------------------------------------------
# Отчёт
# ---------------------------------------------------------------------------

def esc(value):
    return html.escape(str(value or ''))


def cut(value, limit=420):
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    return text if len(text) <= limit else text[:limit] + '…'


REPORT_CSS = """
body{font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;
     background:#f7f7f8;color:#1c1c1e}
main{max-width:1100px;margin:0 auto;padding:32px 24px 80px}
h1{font-size:26px;margin:0 0 4px} h2{font-size:20px;margin:36px 0 10px}
h3{font-size:16px;margin:24px 0 8px;color:#3c3c43}
.lead{color:#5c5c62;margin:0 0 24px}
table{border-collapse:collapse;width:100%;background:#fff;margin:10px 0 18px;
      box-shadow:0 1px 2px rgba(0,0,0,.07)}
th,td{padding:8px 11px;border-bottom:1px solid #e6e6ea;text-align:left;
      vertical-align:top;font-size:14px}
th{background:#efeff2;font-weight:600}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.card{background:#fff;border:1px solid #e6e6ea;border-radius:8px;padding:12px 14px;
      margin:0 0 10px}
.card .q{margin:0 0 6px}
.meta{font-size:13px;color:#5c5c62;margin:2px 0}
.ok{color:#1a7f37;font-weight:600}
.warn{color:#9a6700;font-weight:600}
.bad{color:#b3261e;font-weight:600}
code{background:#f0f0f3;padding:1px 5px;border-radius:4px;font-size:13px}
.rules li{margin:5px 0}
"""


class ReportBuilder(object):
    u"""Складывает HTML отчёта кусками, чтобы не держать одну простыню."""

    def __init__(self, title):
        self.parts = ['<!doctype html><html lang="ru"><meta charset="utf-8">',
                      '<title>%s</title>' % esc(title),
                      '<style>%s</style><main>' % REPORT_CSS,
                      '<h1>%s</h1>' % esc(title)]

    def add(self, chunk):
        self.parts.append(chunk)

    def table(self, headers, rows):
        out = ['<table><tr>']
        for head in headers:
            css = ' class="num"' if head.startswith('#') else ''
            out.append('<th%s>%s</th>' % (css, esc(head.lstrip('#'))))
        out.append('</tr>')
        for row in rows:
            out.append('<tr>')
            for head, cell in zip(headers, row):
                css = ' class="num"' if head.startswith('#') else ''
                out.append('<td%s>%s</td>' % (css, cell))
            out.append('</tr>')
        out.append('</table>')
        self.add(''.join(out))

    def html(self):
        return ''.join(self.parts) + '</main></html>'


def render_example(item):
    u"""Одна карточка примера в отчёте."""
    problem = item['problem']
    options = item['options']
    if options:
        shown = '; '.join('%d) %s' % (i + 1, cut(o, 90))
                          for i, o in enumerate(options[:6]))
    else:
        shown = 'вариантов не найдено'
    return (
        '<div class="card">'
        '<p class="q"><b>#%s</b> %s</p>'
        '<p class="meta">Ответ в банке: <code>%s</code></p>'
        '<p class="meta">Распознано вариантов: %s</p>'
        '<p class="meta">Сигнал 1, источник: <b>%s</b> (%s)</p>'
        '<p class="meta">Сигнал 2, содержимое: <b>%s</b> (%s)</p>'
        '<p class="meta">Итог: <b>%s</b></p>'
        '</div>' % (
            esc(problem.id), esc(cut(problem.statement)),
            esc(cut(problem.answer, 160) or 'пусто'),
            esc(shown),
            esc(item['source_verdict']), esc(item['source_why']),
            esc(item['content_verdict']), esc(item['content_why']),
            esc(item['final'])))


class Command(BaseCommand):
    help = ('Проставить подвид теста в Problem.problem_type по двум сигналам: '
            'структура сырого источника и содержимое задачи в банке.')

    def add_arguments(self, parser):
        parser.add_argument('--source', type=str, default='',
                            help='имя источника; пусто значит все известные')
        parser.add_argument('--preview', action='store_true',
                            help='только посчитать и собрать отчёт')
        parser.add_argument('--confirm', action='store_true',
                            help='боевая запись problem_type')
        parser.add_argument('--revert', action='store_true',
                            help='откат по журналу применения')
        parser.add_argument('--report', type=str,
                            default=os.path.join('reports', 'game',
                                                 'test_types_preview.html'))
        parser.add_argument('--applied', type=str,
                            default=os.path.join('reports', 'game',
                                                 'test_types_applied.json'))
        parser.add_argument('--examples', type=int, default=40,
                            help='сколько примеров показывать на группу')
        parser.add_argument('--raw-root', type=str, default=RAW_ROOT)

    # -- разбор -----------------------------------------------------------

    def analyse(self, source, raw_index, adapter):
        u"""Пройти задачи источника и разложить их по группам."""
        problems = (Problem.objects
                    .filter(source_references__source=source)
                    .distinct()
                    .prefetch_related('parts', 'source_references'))
        signal_fn = adapter['signal']
        key_fn = adapter['key']
        items = []
        for problem in problems:
            key = key_fn(problem, source.id)
            passport = raw_index.get(key) if key else None
            source_verdict, source_why = signal_fn(passport)
            content_verdict, content_why = signal_content(problem)
            final, why = combine(source_verdict, content_verdict)
            options, _, _ = collect_options(problem)
            items.append({
                'problem': problem,
                'key': key,
                'options': options,
                'source_verdict': source_verdict, 'source_why': source_why,
                'content_verdict': content_verdict, 'content_why': content_why,
                'final': final, 'why': why,
            })
        return items

    # -- отчёт ------------------------------------------------------------

    @staticmethod
    def _coverage(blocks, token):
        u"""Доля сопоставленных с сырьём для строки описи."""
        for block in blocks:
            if block['token'] == token:
                total = len(block['items'])
                return (block['matched'], total,
                        100.0 * block['matched'] / max(total, 1))
        return (0, 0, 0.0)

    def build_report(self, path, blocks, examples):
        report = ReportBuilder('Подвид теста: SolveHub и Сборник АА')
        report.add('<p class="lead">Отчёт команды <code>classify_test_types</code>. '
                   'Ничего не записано: это предпросмотр.</p>')

        report.add('<h2>1. Правила словами</h2><ul class="rules">'
                   '<li><b>Сигнал 1, главный.</b> Структура сырого источника. '
                   'У SolveHub это поля <code>is_test</code> и '
                   '<code>check_type</code> в файле задачи.</li>'
                   '<li><b>Сигнал 2, контрольный.</b> Содержимое задачи в банке: '
                   'варианты из подпунктов либо из блока «Варианты ответа:», '
                   'правильный вариант из <code>answer</code>.</li>'
                   '<li><b>Пишем только при согласии сигналов.</b> Разошлись, '
                   'значит корзина «спорные» и никакой записи.</li>'
                   '<li><b>Задача с подпунктами это не тест.</b> Признак задачи: '
                   'подпункты «а)», «б)» в повелительном наклонении и нет блока '
                   '«Варианты ответа:». У теста ответ называет номер варианта.</li>'
                   '<li><b>Другие форматы не втискиваем.</b> «Установите '
                   'соответствие» и «расположите по порядку» идут в свою корзину.</li>'
                   '<li>Записывается ровно одно поле: <code>problem_type</code>.</li>'
                   '<li><b>«Числовой ответ» только подтверждает.</b> Числом '
                   'разбирается ответ и у теста, и у открытой расчётной задачи, '
                   'так что сам по себе он тест не доказывает.</li>'
                   '</ul>')

        report.add('<h2>2. Опись сырых источников</h2>')
        report.table(
            ['Источник', 'Где лежит', 'Формат', 'Чем помечен тест',
             '#Сопоставлено'],
            [['SolveHub',
              '<code>%s</code>' % esc(os.path.join(RAW_ROOT, 'solvehub')),
              'по одному файлу JSON на задачу',
              'поля <code>is_test</code> и <code>check_type</code>; ключ к банку '
              'это имя файла, оно же <code>SourceReference.problem_number</code>',
              '%d из %d (%.2f %%)' % self._coverage(blocks, 'solvehub')],
             ['Сборник тестов АА',
              'PDF «Сборник тестов АА», в рабочей копии отсутствует',
              'PDF с разделами и блоками вопросов',
              'заголовки блоков «Вопросы типа "Верно/Неверно"», «Вопросы на один '
              'правильный ответ», «Вопросы на все верные ответы»; сняты при '
              'импорте командой <code>import_pdf_shivarov</code> прямо в '
              '<code>problem_type</code>',
              '%d из %d (%.2f %%)' % self._coverage(blocks, 'аа')]])

        rnd = random.Random(20260902)
        step = 2
        for block in blocks:
            step += 1
            items = block['items']
            counts = Counter(item['final'] for item in items)
            written = sum(counts.get(t, 0) for t in FOUR_TYPES)
            verify = block['adapter']['mode'] == 'verify'
            report.add('<h2>%d. %s</h2>' % (step, esc(block['source'].name)))
            if verify:
                report.add('<p class="lead">Тип уже проставлен импортёром. '
                           'Здесь он <b>проверяется</b> содержимым: запись '
                           'ничего не изменит.</p>')
            rows = []
            for name in list(FOUR_TYPES) + list(BUCKETS):
                if counts.get(name):
                    mark = 'ok' if name in FOUR_TYPES else 'warn'
                    action = 'подтверждён' if verify else 'запись'
                    rows.append(['<span class="%s">%s</span>' % (mark, esc(name)),
                                 counts[name],
                                 action if name in FOUR_TYPES else 'без записи'])
            report.table(['Группа', '#Сколько', 'Действие'], rows)
            report.add('<p>С типом из четырёх: <b>%d</b>. Без типа: <b>%d</b>.</p>'
                       % (written, len(items) - written))

            declared = [p for p in block['raw_index'].values() if 'is_test' in p]
            if declared:
                declared_tests = sum(1 for p in declared if p['is_test'])
                report.add('<h3>Сверка с объявленным составом источника</h3>')
                report.table(
                    ['Что', '#Источник', '#У нас', '#Разница'],
                    [['Тестов', declared_tests, written, written - declared_tests],
                     ['Полноценных задач', len(declared) - declared_tests,
                      counts.get(B_FULL_PROBLEM, 0),
                      counts.get(B_FULL_PROBLEM, 0) - (len(declared) - declared_tests)]])

            if verify:
                bad = [i for i in items if i['final'] not in FOUR_TYPES]
                report.add('<h3>Задачи без тестового типа: %d</h3>' % len(bad))
                if bad:
                    report.add('<p class="lead">Список целиком, с предложением '
                               'по двум сигналам.</p>')
                    for item in bad:
                        report.add(render_example(item))
                else:
                    report.add('<p class="ok">Пусто: тип из четырёх стоит '
                               'у каждой задачи источника.</p>')

            pairs = Counter((item['source_verdict'], item['content_verdict'])
                            for item in items if item['final'] == B_DISPUTED)
            if pairs:
                report.add('<h3>Из чего сложилась корзина «спорные»</h3>')
                report.add('<p class="lead">Каждая строка это настоящее '
                           'разногласие: либо источник назвал тип, а содержимое '
                           'его не подтвердило, либо наоборот. Ни одна из этих '
                           'задач тип не получит.</p>')
                report.table(['Сигнал 1, источник', 'Сигнал 2, содержимое',
                              '#Сколько'],
                             [[esc(a), esc(b), n] for (a, b), n in pairs.most_common()])

            by_group = defaultdict(list)
            for item in items:
                by_group[item['final']].append(item)
            report.add('<h3>Примеры по группам</h3>')
            for name in list(FOUR_TYPES) + list(BUCKETS):
                group = by_group.get(name) or []
                if not group:
                    continue
                sample = rnd.sample(group, min(examples, len(group)))
                report.add('<h3>%s (%d, показано %d)</h3>'
                           % (esc(name), len(group), len(sample)))
                for item in sample:
                    report.add(render_example(item))

        every = [i for block in blocks for i in block['items']]
        border = [item for item in every if looks_like_subtasks(item['problem'])]
        report.add('<h2>%d. Граница «задача с подпунктами» против теста</h2>'
                   % (step + 1))
        report.add('<p class="lead">Задач с подпунктами в повелительном '
                   'наклонении: <b>%d</b>. Прошлая эвристика считала их тестами, '
                   'и оттого насчитала лишние сотни.</p>' % len(border))
        for item in rnd.sample(border, min(examples, len(border))):
            report.add(render_example(item))

        folder = os.path.dirname(path)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(report.html())

    # -- запись и откат ---------------------------------------------------

    def do_confirm(self, items, applied_path):
        planned = [item for item in items if item['final'] in FOUR_TYPES]
        journal = {}
        changed = 0
        with transaction.atomic():
            for item in planned:
                problem = item['problem']
                if problem.problem_type == item['final']:
                    continue
                journal[str(problem.id)] = {
                    'before': problem.problem_type,
                    'after': item['final'],
                }
                Problem.objects.filter(pk=problem.pk).update(
                    problem_type=item['final'])
                changed += 1
        folder = os.path.dirname(applied_path)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        with open(applied_path, 'w', encoding='utf-8') as fh:
            json.dump(journal, fh, ensure_ascii=False, indent=1)
        return changed, len(planned)

    def do_revert(self, applied_path):
        if not os.path.exists(applied_path):
            raise CommandError('нет журнала применения: %s' % applied_path)
        with open(applied_path, encoding='utf-8') as fh:
            journal = json.load(fh)
        restored = 0
        with transaction.atomic():
            for pid, record in journal.items():
                updated = Problem.objects.filter(
                    pk=int(pid), problem_type=record['after']).update(
                        problem_type=record['before'])
                restored += updated
        return restored, len(journal)

    # -- точка входа ------------------------------------------------------

    def handle(self, *args, **options):
        if options['revert']:
            restored, total = self.do_revert(options['applied'])
            self.stdout.write('Откат: возвращено %d из %d записей журнала'
                              % (restored, total))
            return

        if not (options['preview'] or options['confirm']):
            raise CommandError('нужен --preview, --confirm или --revert')

        wanted = (options['source'] or '').strip().lower()
        tokens = [t for t in RAW_ADAPTERS if not wanted or t in wanted]
        if not tokens:
            raise CommandError(
                'для источника «%s» нет чтения сырья. Известны: %s'
                % (options['source'],
                   ', '.join(spec['label'] for spec in RAW_ADAPTERS.values())))

        blocks = []
        for token in tokens:
            adapter = RAW_ADAPTERS[token]
            source = Source.objects.filter(name__icontains=adapter['label']).first()
            if source is None:
                raise CommandError('источник «%s» не найден в банке'
                                   % adapter['label'])
            if token == 'аа':
                raw_index = adapter['loader'](options['raw_root'],
                                              source_id=source.id)
            else:
                raw_index = adapter['loader'](options['raw_root'])
            items = self.analyse(source, raw_index, adapter)
            matched = sum(1 for item in items if item['key'] in raw_index)
            blocks.append({'token': token, 'adapter': adapter, 'source': source,
                           'items': items, 'raw_index': raw_index,
                           'matched': matched})

            self.stdout.write('')
            self.stdout.write('%s: %d задач в банке, сопоставлено с сырьём %d'
                              % (source.name, len(items), matched))
            counts = Counter(item['final'] for item in items)
            for group in list(FOUR_TYPES) + list(BUCKETS):
                if counts.get(group):
                    self.stdout.write('  %6d  %s' % (counts[group], group))

        planned = sum(1 for block in blocks for item in block['items']
                      if item['final'] in FOUR_TYPES)

        if options['preview']:
            self.build_report(options['report'], blocks, options['examples'])
            self.stdout.write('')
            self.stdout.write('Отчёт: %s' % options['report'])
            self.stdout.write('Записи НЕ было. Тип из четырёх стоял бы у %d'
                              % planned)
            return

        every = [item for block in blocks for item in block['items']]
        changed, total = self.do_confirm(every, options['applied'])
        self.stdout.write('')
        self.stdout.write('Записано: %d, уже стояло верно: %d'
                          % (changed, total - changed))
        self.stdout.write('Журнал отката: %s' % options['applied'])
