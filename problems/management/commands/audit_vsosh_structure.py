# -*- coding: utf-8 -*-
"""
audit_vsosh_structure — инвентаризация структурных элементов (таблицы,
списки) в PDF ВсОШ-региона и сверка с тем, что попало в parsed_<год>.json.

Класс дефекта: структура, размазанная в строку текста. Формально текст
«валиден» (глифы целы, KaTeX не ругается), поэтому обычная вычитка на
битые символы его не ловит. Здесь ищем именно ПОТЕРЮ СТРУКТУРЫ.

Детекция таблицы (геометрия PDF):
- ≥2 горизонтальные линейки с общим x-диапазоном (booktabs) очерчивают зону;
- внутри зоны ячейки (спаны) выстраиваются в КОЛОНКИ: ≥2 колонки, каждая
  заполнена ≥2 разными строками (базовыми линиями). Формула (выключная
  дробь) этот тест не проходит — её ячейки на одной базовой линии.

Атрибуция: таблица приписывается вопросу, чей номер (маркер «N.M.») ближе
всего сверху; таблицы вне тест-вопросов (Часть 4, сетки ответов) отсеиваются
сверкой с parsed_<год>.json.

Запуск: ./venv/bin/python manage.py audit_vsosh_structure
"""
import glob
import hashlib
import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand

CYR = re.compile(r'[а-яёА-ЯЁ]{3,}')
SECTION_RE = re.compile(r'^(Часть|Задание)\s+\d|Правильные ответы|Региональн'
                        r'|Первый тур|олимпиад|Ответы, решения')
# сквозная («12.») и двухуровневая («3.2.») нумерация вопросов
QMARK = re.compile(r'^(\d{1,2})\.(?:(\d{1,2})\.)?\s')
# сигнатуры сводной сетки ответов / бланка (не контент вопроса)
ANSGRID_RE = re.compile(r'Образец|Бланк|Конкурс|заполнени|'
                        r'(?:\d\.\d\.\s*){2,}\d\.\d\.')
NUM_CELL = re.compile(r'^[-−]?\d')
BULLET_RE = re.compile(r'[•·▪‣]')


def _is_math(sp):
    return 'Math' in sp['font']


def _hrules(page, page_h):
    """Горизонтальные линейки-кандидаты в границы таблицы. Ширина 90–490pt:
    у́же — черта дроби, ши́ре — полностраничный разделитель/артефакт."""
    rs = []
    for d in page.get_drawings():
        for it in d['items']:
            if it[0] == 'l':
                p1, p2 = it[1], it[2]
                if abs(p1.y - p2.y) < 0.8:
                    rs.append((min(p1.x, p2.x), max(p1.x, p2.x), p1.y))
            elif it[0] == 're':
                r = it[1]
                if r.height < 2:
                    rs.append((r.x0, r.x1, (r.y0 + r.y1) / 2))
    return [r for r in rs
            if 0.06 * page_h < r[2] < 0.94 * page_h
            and 90 <= r[1] - r[0] <= 490]


def _rows_in(page, y0, y1):
    rows = {}
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines', []):
            for sp in line['spans']:
                yy = sp['origin'][1]
                if y0 - 3 < yy < y1 + 3 and sp['text'].strip():
                    rows.setdefault(round(yy), []).append(sp)
    return [(y, sorted(v, key=lambda s: s['bbox'][0]))
            for y, v in sorted(rows.items())]


def _columns_consistent(rows):
    """≥2 колонки, каждая заполнена ≥2 разными строками. Колонка — кластер
    x-стартов ячеек (зазор > 22pt). Возвращает число колонок или 0."""
    # x-старт каждой ячейки с её строкой
    marks = []
    for y, cells in rows:
        for sp in cells:
            marks.append((sp['bbox'][0], y))
    if not marks:
        return 0
    marks.sort()
    cols = []          # [(xmin, xmax, set(строк))]
    for x, y in marks:
        if cols and x - cols[-1][1] <= 22:
            cols[-1][1] = max(cols[-1][1], x)
            cols[-1][2].add(y)
        else:
            cols.append([x, x, {y}])
    multi = [c for c in cols if len(c[2]) >= 2]
    return len(multi)


def detect_tables(page, page_h):
    rules = sorted(_hrules(page, page_h), key=lambda t: t[2])
    # группа = линейки с СОВПАДАЮЩИМ x-охватом (±16pt по обоим концам) —
    # верх/шапка/низ одной таблицы имеют один и тот же x-пролёт; черта дроби
    # и полностраничный разделитель этот тест не проходят
    groups = []
    for r in rules:
        for g in groups:
            if (abs(g[0][0] - r[0]) < 16 and abs(g[0][1] - r[1]) < 16
                    and r[2] - g[-1][2] < 230):
                g.append(r)
                break
        else:
            groups.append([r])
    out = []
    for g in groups:
        if len(g) < 2:
            continue
        y0 = min(x[2] for x in g)
        y1 = max(x[2] for x in g)
        rows = [(y, c) for y, c in _rows_in(page, y0, y1) if c]
        if len(rows) < 2:
            continue
        alltext = ' '.join(''.join(s['text'] for s in c) for _, c in rows)
        if SECTION_RE.search(alltext.strip()[:45]):
            continue
        if ANSGRID_RE.search(alltext):
            continue     # сводная сетка ответов / бланк
        ncols = _columns_consistent(rows)
        if ncols < 2:
            continue     # формула/проза — колонки не держатся по строкам
        # строка-заголовок: ≥2 кириллич. ячейки не у самого левого поля
        # страницы (прозаическая строка формулы жмётся к x≈28). Линейки уже
        # отфильтрованы по ширине/x-охвату, так что порог мягкий.
        hdr = any(sum(1 for s in c
                      if CYR.search(s['text']) and s['bbox'][0] > 55) >= 2
                  for _, c in rows)
        # числовая матрица: ≥2 строк с ≥3 числовыми ячейками
        nummat = sum(1 for _, c in rows
                     if sum(1 for s in c
                            if NUM_CELL.match(s['text'].strip())) >= 3) >= 2
        if not (hdr or nummat):
            continue
        out.append((round(y0), round(y1), len(rows), ncols, alltext[:90]))
    return out


class Command(BaseCommand):
    help = 'Инвентаризация таблиц/списков в PDF ВсОШ и сверка с parsed_<год>'

    def handle(self, *args, **options):
        import fitz

        rows = []   # (year, qnum, grades, kind, where, dims, preview)
        for year in range(2016, 2026):
            parsed = Path(f'materials/vsosh_region/{year}/parsed_{year}.json')
            if not parsed.exists():
                continue
            data = json.loads(parsed.read_text(encoding='utf-8'))
            qnums = {q['number'] for q in data['questions']}
            by_num = {q['number']: q for q in data['questions']}

            seen = set()
            for pdf in sorted(glob.glob(
                    f'materials/vsosh_region/{year}/test_answers_*.pdf')):
                h = hashlib.md5(open(pdf, 'rb').read(), usedforsecurity=False).hexdigest()
                if h in seen:
                    continue
                seen.add(h)
                doc = fitz.open(pdf)
                for pno in range(len(doc)):
                    page = doc[pno]
                    tbls = detect_tables(page, page.rect.height)
                    for y0, y1, nr, nc, pv in tbls:
                        qn = self._attribute(page, y0)
                        in_test = qn in qnums
                        rows.append((year, qn, in_test, nr, nc, pv))

        # --- вывод карты ---
        self.stdout.write('=== ТАБЛИЦЫ В ТЕСТ-ВОПРОСАХ (потеряна структура) ===')
        test_tabs = [r for r in rows if r[2]]
        # дедуп по (year, qnum) — общий вопрос в файлах классов
        seen_q = set()
        for year, qn, _, nr, nc, pv in test_tabs:
            key = (year, qn)
            if key in seen_q:
                continue
            seen_q.add(key)
            q = json.loads(Path(
                f'materials/vsosh_region/{year}/parsed_{year}.json'
            ).read_text())['questions']
            gr = next((x['grades'] for x in q if x['number'] == qn), '?')
            self.stdout.write(
                f'  {year} №{qn} классы {gr}: {nr}×{nc} — {pv[:70]!r}')

        self.stdout.write('')
        self.stdout.write('=== таблицы ВНЕ тест-вопросов (Часть 4 / сетки — '
                          'игнор) ===')
        for year, qn, in_test, nr, nc, pv in rows:
            if not in_test:
                self.stdout.write(f'  {year} ≈{qn}: {nr}×{nc} — {pv[:55]!r}')

        # --- списки: маркеры «•» в parsed ---
        self.stdout.write('')
        self.stdout.write('=== вопросы со списками (маркеры • в parsed) ===')
        for year in range(2016, 2026):
            p = Path(f'materials/vsosh_region/{year}/parsed_{year}.json')
            if not p.exists():
                continue
            for q in json.loads(p.read_text())['questions']:
                blob = q['statement'] + q.get('solution', '')
                if BULLET_RE.search(blob):
                    n = len(BULLET_RE.findall(blob))
                    self.stdout.write(f'  {year} №{q["number"]}: {n} маркеров •')

    def _attribute(self, page, y0):
        """Номер вопроса ближайшего маркера сверху таблицы. Поддержаны обе
        схемы: сквозная «12.» → '12', двухуровневая «3.2.» → '3.2'."""
        qn = None
        for block in page.get_text('dict')['blocks']:
            for line in block.get('lines', []):
                t = ''.join(sp['text'] for sp in line['spans']).strip()
                m = QMARK.match(t)
                if m and line['bbox'][1] < y0:
                    qn = f'{m.group(1)}.{m.group(2)}' if m.group(2) \
                        else m.group(1)
        return qn
