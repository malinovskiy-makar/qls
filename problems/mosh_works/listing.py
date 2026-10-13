"""Таблицы призёров МОШ → строки index.jsonl. Чистые функции, без Django и сети.

⚠️ ФИО НЕ ХРАНИМ. Столбец «Ф.И.О.» таблицы отбрасывается ПРЯМО В РАЗБОРЩИКЕ:
текст его ячеек не накапливается даже во временных списках. Строка index
строится из белого списка полей (`INDEX_FIELDS`). Участник = номер работы.

⚠️ АДРЕС zip БЕРЁТСЯ ТОЛЬКО ИЗ ССЫЛКИ В ТАБЛИЦЕ. Четыре цифры в конце имени
файла у каждой работы свои, формулы нет; подбирать их, соседние номера или
другие папки на reg.olimpiada.ru — запрещено. Ссылка, не похожая на
ожидаемую, не «чинится», а отбрасывается (zip_url=None, строка в списке
нарушений).
"""
import re
from html.parser import HTMLParser

YEARS = (2021, 2022, 2023, 2024, 2025)

#: Предмет → слаг в адресах организатора. `econ` — экономика (по умолчанию,
#: поведение прежнее), `fin` — финансовая грамотность (таблицы
#: mosh-fingram-Y-prizewinners найдены 13.10.2026, та же вёрстка).
SUBJECTS = {'econ': 'mosh-econ', 'fin': 'mosh-fingram'}

PAGE_URL = ('https://reg.cpm.moscow/register/mosh-econ-%d-prizewinners/'
            'olympiad-protocol-static')

#: Единственный допустимый вид адреса zip: хост, папка года, номер работы
#: и «хвост» из четырёх цифр. Хвост мы НЕ вычисляем — только проверяем, что
#: ссылка из таблицы выглядит именно так.
ZIP_URL_RE = re.compile(
    r'^https://reg\.olimpiada\.ru/files/scans-public-by-oa/mosh-econ-(\d{4})/(\d{8})(\d{4})\.zip$')


def page_url(year, subject='econ'):
    """Адрес таблицы призёров года по предмету."""
    return ('https://reg.cpm.moscow/register/%s-%d-prizewinners/olympiad-protocol-static'
            % (SUBJECTS[subject], year))


def zip_url_re(subject='econ'):
    """Регулярка допустимого адреса zip предмета (у `econ` — ровно ZIP_URL_RE)."""
    if subject == 'econ':
        return ZIP_URL_RE
    return re.compile(r'^https://reg\.olimpiada\.ru/files/scans-public-by-oa/%s-(\d{4})/(\d{8})(\d{4})\.zip$'
                      % re.escape(SUBJECTS[subject]))

#: Ровно эти поля и только они попадают в строку index при разборе таблицы.
INDEX_FIELDS = ('work_id', 'year', 'season', 'grade_participation', 'grade',
                'total_listed', 'result', 'prize_degree', 'zip_url', 'listed_at')

#: Заголовки столбцов (нижний регистр) → служебное имя. 'fio' не читается.
HEADERS = {
    'номер работы': 'work',
    'ф.и.о.': 'fio',
    'класс участия': 'grade_participation',
    'класс': 'grade',
    'сумма': 'total',
    'результат': 'result',
}


def season_of(year):
    """2025 → «2024/2025» (год заключительного этапа = конец учебного года)."""
    return '%d/%d' % (year - 1, year)


def _norm(text):
    return re.sub(r'\s+', ' ', text or '').strip()


class _TableParser(HTMLParser):
    """Первая таблица страницы → строки [(текст, [ссылки])…] БЕЗ столбца ФИО."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.header = None          # служебные имена столбцов по порядку
        self._row = None
        self._cell = None           # [текст, ссылки]
        self._col = 0
        self._depth = 0             # <table> внутри <table>: берём только первую

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self._depth += 1
        elif self._depth != 1:
            return
        elif tag == 'tr':
            self._row, self._col = [], 0
        elif tag in ('td', 'th') and self._row is not None:
            self._cell = ['', []]
        elif tag == 'a' and self._cell is not None:
            href = dict(attrs).get('href')
            if href:
                self._cell[1].append(href.strip())

    def handle_endtag(self, tag):
        if tag == 'table':
            self._depth -= 1
        elif self._depth != 1:
            return
        elif tag in ('td', 'th') and self._cell is not None and self._row is not None:
            self._row.append((_norm(self._cell[0]), self._cell[1]))
            self._cell = None
            self._col += 1
        elif tag == 'tr' and self._row is not None:
            if self.header is None and self._row and _norm(self._row[0][0]).lower().startswith('номер'):
                self.header = [HEADERS.get(_norm(t).lower(), '?') for t, _ in self._row]
            elif self.header is not None:
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is None or self._depth != 1:
            return
        # Столбец ФИО — после того как заголовок известен — не накапливаем.
        if self.header is not None and self._col < len(self.header) \
                and self.header[self._col] == 'fio':
            return
        self._cell[0] += data


def parse_result(text):
    """«победитель» → ('winner', None); «призёр 2 степени» → ('prizewinner', 2)."""
    t = _norm(text).lower().replace('ё', 'е')
    if t == 'победитель':
        return 'winner', None
    m = re.fullmatch(r'призер(?: (\d) степени)?', t)
    if m:
        return 'prizewinner', int(m.group(1)) if m.group(1) else None
    return None, None


def parse_number(text):
    """«74» → 74, «74,5» → 74.5, мусор/пусто → None."""
    t = _norm(text).replace(',', '.')
    if not re.fullmatch(r'\d+(\.\d+)?', t):
        return None
    value = float(t)
    return int(value) if value.is_integer() else value


def parse_int(text):
    t = _norm(text)
    return int(t) if t.isdigit() else None


def parse_table(html_text, year, listed_at, subject='econ'):
    """Страница призёров → список записей index (строка на работу).

    Заголовок обязан содержать все столбцы из HEADERS — иначе ValueError
    (вёрстку сменили: молча угадывать столбцы нельзя).
    """
    parser = _TableParser()
    parser.feed(html_text)
    parser.close()
    if parser.header is None:
        raise ValueError('В таблице нет строки заголовка («Номер работы…»)')
    missing = set(HEADERS.values()) - set(parser.header)
    if missing:
        raise ValueError('В заголовке нет столбцов: %s' % ', '.join(sorted(missing)))
    where = {name: i for i, name in enumerate(parser.header) if name != '?'}
    records = []
    for cells in parser.rows:
        if len(cells) < len(parser.header):
            continue
        work_text, links = cells[where['work']]
        work_id = work_text if work_text.isdigit() else None
        if work_id is None:
            continue
        result, degree = parse_result(cells[where['result']][0])
        record = {
            'work_id': work_id,
            'year': year,
            'season': season_of(year),
            'grade_participation': parse_int(cells[where['grade_participation']][0]),
            'grade': parse_int(cells[where['grade']][0]),
            'total_listed': parse_number(cells[where['total']][0]),
            'result': result,
            'prize_degree': degree,
            'zip_url': pick_zip_url(links, year, work_id, subject),
            'listed_at': listed_at,
        }
        records.append({k: record[k] for k in INDEX_FIELDS})
    return records


def pick_zip_url(links, year, work_id, subject='econ'):
    """Ссылка на zip из ячейки «Номер работы» — как есть, если она ожидаемого вида.

    Ничего не достраиваем: нет ссылки или вид не тот (в т.ч. папка ДРУГОГО
    предмета) — None.
    """
    pattern = zip_url_re(subject)
    for href in links:
        m = pattern.match(href)
        if m and int(m.group(1)) == year and m.group(2) == work_id:
            return href
    return None


def check_index(records, expected_rows=None):
    """Инварианты Фазы 2. Нарушения — список строк, а не падение.

    `expected_rows` — {год: число строк в таблице}, как при разведке.
    """
    problems = []
    ids = [(r['year'], r['work_id']) for r in records]
    dup = len(ids) - len(set(ids))
    if dup:
        problems.append('повторов work_id: %d' % dup)
    by_year = {}
    for r in records:
        by_year[r['year']] = by_year.get(r['year'], 0) + 1
    for year, n in (expected_rows or {}).items():
        if by_year.get(year, 0) != n:
            problems.append('%d: строк %d, а ожидалось %d' % (year, by_year.get(year, 0), n))
    no_total = [r['work_id'] for r in records if r['total_listed'] is None]
    no_result = [r['work_id'] for r in records if r['result'] is None]
    no_zip = [r['work_id'] for r in records if not r['zip_url']]
    if no_total:
        problems.append('без суммы: %d (%s)' % (len(no_total), ', '.join(no_total[:10])))
    if no_result:
        problems.append('без результата: %d (%s)' % (len(no_result), ', '.join(no_result[:10])))
    return {'rows': len(records), 'by_year': by_year, 'duplicates': dup,
            'no_total': no_total, 'no_result': no_result, 'no_zip': no_zip,
            'problems': problems}
