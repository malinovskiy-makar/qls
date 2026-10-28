# -*- coding: utf-8 -*-
"""ВсОШ по экономике: разбор списков источников в строки манифеста.

Источники (карта — `night_20261028\\VSOSH_SOURCES_20261028.md`):
- ILE (iloveeconomics.ru) — страницы `/olimp/{vseros|region|okrug}/{год конца}`;
- ЦПМ (vos.olimpiada.ru) — API `getTasks?subject=econ`, поле `tasks` — HTML;
- olimpiada.ru — манифест разведки (`olimpiada_manifest.csv`).

Этап, сезон, класс и регион берутся из МЕТАДАННЫХ источника (раздел и год
страницы ILE, поля API, подпись ссылки, атрибуты `reg`/`etap`), а не из
имени файла: имена у всех трёх нерегулярные.

Модуль без Django и без сети: только разбор. Сеть — `vsosh_fetch`.
"""
from __future__ import annotations

import html
import re
from urllib.parse import unquote, urljoin

ILE_BASE = 'https://iloveeconomics.ru'
CPM_BASE = 'https://vos.olimpiada.ru'

STAGES = ('final', 'regional', 'municipal', 'school', 'invitational')

#: sid API ЦПМ → этап.
CPM_STAGE = {'1': 'invitational', '2': 'school', '3': 'municipal',
             '4': 'regional', '5': 'final'}

#: Раздел ILE → (этап, олимпиада). `predpr*` — предпринимательство,
#: собирается отдельно и помечается `subject='entrepreneurship'`.
ILE_SECTION = {
    'vseros': ('final', 'econ'),
    'region': ('regional', 'econ'),
    'okrug': ('municipal', 'econ'),
    'predprvseros': ('final', 'entrepreneurship'),
    'predprregion': ('regional', 'entrepreneurship'),
    'predprmosh': ('final', 'entrepreneurship-mosh'),
}

MOSCOW = ('77', 'Москва')
MOSCOW_OBLAST = ('50', 'Московская область')

_FILE_EXT = ('pdf', 'doc', 'docx', 'rtf', 'jpg', 'png', 'zip', 'rar', '7z',
             'xls', 'xlsx', 'ppt', 'pptx', 'odt')


def season_from_end(year_end):
    """Год конца сезона → `2024/25`."""
    y = int(year_end)
    return f'{y - 1}/{y % 100:02d}'


def season_from_start(year_start):
    """Год начала сезона → `2024/25`."""
    y = int(year_start)
    return f'{y}/{(y + 1) % 100:02d}'


def season_from_cpm(yname):
    """`2024/2025` → `2024/25`."""
    m = re.match(r'\s*(\d{4})\s*/\s*(\d{2,4})', str(yname or ''))
    if not m:
        return ''
    return season_from_start(m.group(1))


_GRADE_RANGE = re.compile(
    r'(?<!\d)(\d{1,2})(?:\s*[-–—/]\s*(\d{1,2}))?(?:\s*[-–]?\s*(?:го|й|х|ых))?\s*(?:класс|кл\b|кл\.)',
    re.I)
_GRADE_LIST = re.compile(r'(?<!\d)(\d{1,2})(?:\s*/\s*(\d{1,2}))+(?!\d)')


def parse_grades(text):
    """Подпись → классы строкой: «9-10 классы» → `9-10`, «11 класс» → `11`.

    Несколько упоминаний («Тест 10-11 класс (с ответами)») — первое.
    Нет класса — пустая строка."""
    t = str(text or '').replace('\xa0', ' ')
    m = _GRADE_RANGE.search(t)
    if m:
        a, b = int(m.group(1)), m.group(2)
        if not 1 <= a <= 11:
            return ''
        if b and int(b) != a and 1 <= int(b) <= 11:
            lo, hi = sorted((a, int(b)))
            return f'{lo}-{hi}'
        return str(a)
    return ''


def grades_from_pages(class_pages):
    """`9/10/11` (olimpiada.ru: на страницах каких классов файл) → `9-11`."""
    nums = sorted({int(x) for x in re.findall(r'\d{1,2}', str(class_pages or ''))
                   if 1 <= int(x) <= 11})
    if not nums:
        return ''
    if len(nums) == 1:
        return str(nums[0])
    return f'{nums[0]}-{nums[-1]}'


def classify_label(text):
    """Подпись ссылки → (kind, tour, with_solutions).

    kind: tasks | solutions | answers | criteria | tasks+solutions | test |
    essay | methodical. tour: test | problems | essay | blitz | 1 | 2 | ''.
    `with_solutions` — в файле есть решения/ответы (для пар не нужен
    отдельный файл решений)."""
    t = str(text or '').lower().replace('\xa0', ' ').replace('ё', 'е')
    with_sol = bool(re.search(r'с\s+(решени|ответ|разбор|ключ)', t)) or 'и решени' in t \
        or 'и ответ' in t or 'решебник' in t
    without = bool(re.search(r'без\s+(решени|ответ)', t))
    if without:
        with_sol = False
    tour = ''
    if re.search(r'перв\w*\s+тур|1\s*тур|тур\s*1|i\s+тур', t):
        tour = '1'
    elif re.search(r'втор\w*\s+тур|2\s*тур|тур\s*2|ii\s+тур', t):
        tour = '2'
    if 'тест' in t:
        tour = tour or 'test'
    elif 'эссе' in t:
        tour = tour or 'essay'
    elif 'блиц' in t:
        tour = tour or 'blitz'
    elif re.search(r'задач', t):
        tour = tour or 'problems'

    if re.search(r'методич|рекомендац|требовани', t):
        kind = 'methodical'
    elif re.search(r'критери', t) and not re.search(r'задан|задач', t):
        kind = 'criteria'
    elif re.search(r'^\s*(решени|решебник|разбор)', t) or (
            re.search(r'решени', t) and not re.search(r'задан|задач|тест|эссе', t)):
        kind = 'solutions'
    elif re.search(r'^\s*(ответ|ключ)', t) or (
            re.search(r'ответ', t) and not re.search(r'задан|задач|тест|эссе', t)):
        kind = 'answers'
    elif 'тест' in t and not re.search(r'задан|задач', t):
        kind = 'test'
    elif 'эссе' in t and not re.search(r'задан|задач', t):
        kind = 'essay'
    else:
        kind = 'tasks+solutions' if with_sol else 'tasks'
    return kind, tour, with_sol


def _ext(url):
    path = unquote(str(url).split('?', 1)[0]).rsplit('/', 1)[-1]
    if '.' not in path:
        return ''
    return path.rsplit('.', 1)[-1].lower()


def ile_rows(pages):
    """Страницы ILE из разведки (`ile_files.json`) → строки манифеста.

    Возвращает (files, extras): files — файлы заданий; extras — архивы
    «всё за год», печатные страницы `/print-all-tasks/` и прочее (не файлы
    заданий, но качаются для сверки)."""
    files, extras = [], []
    for page in pages:
        sec, y_raw = page['sec'], str(page['y'])
        stage, subject = ILE_SECTION.get(sec, ('', 'econ'))
        y = int(re.match(r'\d{4}', y_raw).group(0))
        season = season_from_end(y)
        region_code, region_name = ('ru', '') if stage in ('final', 'regional') else MOSCOW
        if subject == 'entrepreneurship-mosh':
            region_code, region_name = MOSCOW
        page_url = f'{ILE_BASE}/olimp/{sec}/{y_raw}'
        for f in page.get('files', []):
            href = html.unescape(f.get('href') or '')
            url = urljoin(ILE_BASE + '/', href)
            label = (f.get('text') or '').strip()
            row = dict(source='ile', url=url, stage=stage, season=season,
                       region_code=region_code, region_name=region_name,
                       label=label, page_url=page_url, subject=subject,
                       size_hint=f.get('len'))
            notes = []
            if sec == 'okrug':
                low = (href + ' ' + label).lower()
                if y_raw == '2002' or 'oblast' in low or 'raion' in low or \
                        'район' in low or 'област' in low:
                    row['region_code'], row['region_name'] = MOSCOW_OBLAST
                    notes.append('мо_по_разделу_okrug')
                if y <= 2009:
                    notes.append('окружной_тур_МГО')
            kind, tour, with_sol = classify_label(label)
            row.update(kind=kind, tour=tour, with_solutions=with_sol,
                       grades=parse_grades(label), notes=notes)
            if '/print-all-tasks/' in href:
                row['kind'] = 'ile_print'
                extras.append(row)
            elif href.startswith('/z/') or '/zadacha/' in href:
                row['kind'] = 'ile_task_page'
                extras.append(row)
            elif _ext(url) == 'zip' and 'olymp_files' in url:
                row['kind'] = 'archive_year'
                extras.append(row)
            elif _ext(url) in _FILE_EXT and 'iloveeconomics.ru' in url:
                row['format'] = _ext(url)
                files.append(row)
            else:
                row['kind'] = 'external_link'
                extras.append(row)
    return files, extras


_CPM_DIV = re.compile(r'<div>\s*<span class="name">(.*?)</span>(.*?)</div>', re.S)
_CPM_A = re.compile(r'<a\s+href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_SPAN = re.compile(r'<span class="(class|format)">(.*?)</span>', re.S)


def cpm_rows(api_data):
    """Ответ `getTasks?subject=econ` → строки манифеста.

    `span.name` — тип (Задания / Решения / Ответы / Критерии), `span.class`
    — класс, `span.format` — тур. Регион: ЗЭ и РЭ — `ru` (комплект общий),
    остальные этапы ЦПМ — Москва."""
    out = []
    for rec in api_data.get('data', api_data if isinstance(api_data, list) else []):
        stage = CPM_STAGE.get(str(rec.get('sid') or rec.get('stage')), '')
        season = season_from_cpm(rec.get('yname'))
        reg = ('ru', '') if stage in ('final', 'regional') else MOSCOW
        for name, body in _CPM_DIV.findall(rec.get('tasks') or ''):
            name = html.unescape(re.sub('<[^>]+>', '', name)).strip()
            for href, inner in _CPM_A.findall(body):
                spans = dict(_SPAN.findall(inner))
                cls = html.unescape(re.sub('<[^>]+>', '', spans.get('class', ''))).strip()
                fmt = html.unescape(re.sub('<[^>]+>', '', spans.get('format', ''))).strip()
                if not cls and not fmt:
                    cls = html.unescape(re.sub('<[^>]+>', '', inner)).strip()
                url = urljoin(CPM_BASE + '/', html.unescape(href))
                label = ' '.join(x for x in (name, cls, fmt) if x)
                kind, tour, with_sol = classify_label(name + ' ' + fmt)
                fkind, ftour, _ = classify_label(fmt)
                if fmt and ftour:
                    tour = ftour
                out.append(dict(source='cpm', url=url, stage=stage, season=season,
                                region_code=reg[0], region_name=reg[1], label=label,
                                kind=kind, tour=tour if fmt else ('' if tour == 'problems' else tour),
                                with_solutions=with_sol,
                                grades=parse_grades(cls) or parse_grades(fmt),
                                format=_ext(url), subject='econ', notes=[],
                                page_url=f'{CPM_BASE}/api/getTasks?subject=econ',
                                cpm_id=str(rec.get('id') or '')))
    return out


_OLIMPIADA_STAGE = {'final', 'regional', 'municipal', 'school', 'invitational'}


def olimpiada_rows(csv_rows):
    """Строки `olimpiada_manifest.csv` → строки манифеста.

    Этап и регион — из атрибутов страницы (`etap`, `reg`, `rname`), классы —
    по страницам `?class=N`, на которых файл найден (`class_pages`)."""
    out = []
    for r in csv_rows:
        stage = r.get('stage', '')
        if stage not in _OLIMPIADA_STAGE:
            continue
        reg_id = str(r.get('region_id') or '').strip()
        if stage in ('final', 'regional') or reg_id in ('', '0'):
            code, name = 'ru', ''
        else:
            code, name = reg_id, (r.get('region') or '').strip()
        if stage in ('school', 'invitational') and code == 'ru':
            code, name = MOSCOW
        label = (r.get('label') or '').strip()
        kind, tour, with_sol = classify_label(label)
        url = html.unescape(r['url'])
        out.append(dict(source='olimpiada', url=url, stage=stage,
                        season=season_from_start(r['season_start']),
                        region_code=code, region_name=name, label=label,
                        kind=kind, tour='' if tour == 'problems' else tour,
                        with_solutions=with_sol,
                        grades=grades_from_pages(r.get('class_pages')),
                        format=_ext(url), subject='econ', notes=[],
                        page_url=f"https://olimpiada.ru/activity/86/tasks/{r['season_start']}",
                        recon_status=r.get('http_status', ''),
                        size_hint=int(r['bytes']) if str(r.get('bytes', '')).isdigit() else None))
    return out


def dest_name(url):
    """Имя файла на диске из адреса: путь без домена, `/` → `__`.

    Регистр сохраняется (`.PDF` ≠ `.pdf`), кириллица раскодируется, длинные
    имена укорачиваются с сохранением расширения."""
    from hashlib import sha1
    path = unquote(url.split('://', 1)[-1].split('?', 1)[0])
    name = re.sub(r'[<>:"\\|?*\x00-\x1f]', '_', path).replace('/', '__')
    if len(name) > 150:
        ext = name.rsplit('.', 1)[-1] if '.' in name[-6:] else ''
        name = name[:110] + '_' + sha1(url.encode()).hexdigest()[:12] + (('.' + ext) if ext else '')
    return name
