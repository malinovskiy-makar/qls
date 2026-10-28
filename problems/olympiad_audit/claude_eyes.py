# -*- coding: utf-8 -*-
"""Аудит оцифровки «глазами Claude»: страница PDF против заданий эталона.

Сессия P2, ночь 28→29.10.2026. Эталон экономики v6 → v7 (ВП, МОШ),
финграм / бизнес / предпринимательство v2 → v3. Прежние версии не трогаются,
в базу сайта ничего не пишется.

**Единица — страница.** Каждая группа полей задания живёт на своих страницах:

* `statement` — название, условие, пункты (страницы `source_pages`);
* `solution`  — решение и ответ (`solution_pages`);
* `criteria`  — критерии (`criteria_pages`).

Группа проверяется ровно один раз — в единице своей ПЕРВОЙ страницы. В единицу
кладутся и следующие страницы группы (всего не больше `MAX_UNIT_PAGES`), чтобы
модель видела поле целиком. Не влезло — группа только проверяется, править её
нельзя (`editable=false`).

Модели уходит: картинки страниц единицы, фрагменты заданий (JSON) и постоянная
инструкция `SYSTEM_PROMPT`. Ответ — строго JSON (`parse_reply`): по каждому
фрагменту вердикт, дефекты с дословной цитатой, ПОЛНЫЙ текст исправленных
полей, рамки пропущенных рисунков, уверенность.

**Проверки ответа детерминированные** (`check_unit`). Правка поля принимается,
только если:

* каждое число правки есть в тексте страницы (слой PDF), в цитатах модели или
  в прежнем тексте фрагментов единицы;
* формулы разбираются KaTeX без ошибок (`katex_errors`, node + vendored KaTeX);
* «Ответ:» не появился там, где его нет ни на странице, ни в цитатах;
* поле не урезано больше чем вдвое без дефекта, который это объясняет;
* уверенность не ниже `MIN_CONFIDENCE`, группа редактируема.

Не прошло — правка не применяется, единица уходит в список на утро.

Ответы получаются двумя путями, проверки у них общие:

* Message Batches API (`submit_batches` / `collect_batches`): ключ из
  `ANTHROPIC_API_KEY`, пространство — `ANTHROPIC_WORKSPACE_ID` (без него ключ
  организации получает 400). Повторный запуск не платит за готовое: сырой
  ответ лежит в `audit_claude/raw/<модель>/<единица>.json`;
* файлы задания для агентов Claude Code (`write_job`): тот же промпт и пути
  к картинкам; агент кладёт ответ в тот же `raw/`.
"""
from __future__ import annotations

import base64
import collections
import csv
import datetime
import hashlib
import io
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field

# ── Константы ────────────────────────────────────────────────────────────

MAX_UNIT_PAGES = 4
MIN_CONFIDENCE = 0.6
#: Поле короче прежнего меньше этой доли — подозрение на урезание.
SHRINK_RATIO = 0.5
#: Классы, которые объясняют сильное сокращение поля.
SHRINK_OK = {'service_block_in_task', 'part_split_wrong', 'solution_misattached', 'other'}
FIG_MARGIN = 0.01
FIG_MIN_AREA = 0.004
FIG_MAX_AREA = 0.75

DEFECT_CLASSES = (
    'missing_text', 'missing_table', 'table_wrong', 'missing_options', 'missing_part',
    'part_split_wrong', 'figure_as_text', 'figure_missing', 'formula_wrong',
    'number_wrong', 'solution_misattached', 'criteria_missing', 'service_block_in_task',
    'title_wrong', 'other')

GROUPS = {
    'statement': ('source_pages', ('title', 'statement_md', 'parts')),
    'solution': ('solution_pages', ('solution_md', 'answer')),
    'criteria': ('criteria_pages', ('criteria_md',)),
}
FIX_FIELDS = {name: fields for name, (_, fields) in GROUPS.items()}

#: Цены за 1 млн токенов, Message Batches API (docs.claude.com/pricing, 28.10.2026):
#: вход, запись в кэш 5 мин, чтение кэша, выход — уже со скидкой 50 %.
BATCH_PRICES = {
    'claude-sonnet-5-5': (1.00, 1.25, 0.05, 5.00),
    'claude-haiku-5-5': (0.05, 0.0625, 0.005, 0.25),
    # второй проход очереди «на утро» (claude_recheck)
    'claude-opus-5-5': (2.00, 2.50, 0.10, 10.00),
}
MODEL_ALIASES = {'sonnet': 'claude-sonnet-5-5', 'haiku': 'claude-haiku-5-5'}

#: Набор → (слаг реестра, версия входа, вход относительно digitized\, версия выхода).
SETS = {
    'vp': ('vp', 'v6', 'v6/reference_problems_v6.jsonl', 'v7'),
    'mosh': ('mosh', 'v6', 'v6/reference_problems_v6.jsonl', 'v7'),
    'vp_fingram': ('vp-fingram', 'v2', 'reference_problems_v2.jsonl', 'v3'),
    'vp_business': ('vp-ob', 'v2', 'reference_problems_v2.jsonl', 'v3'),
    'mosh_fingram': ('mosh-fingram', 'v2', 'reference_problems_v2.jsonl', 'v3'),
    'mosh_entrepreneurship': ('mosh-entrepreneurship', 'v2', 'reference_problems_v2.jsonl', 'v3'),
}
SET_ABBR = {'vp': 'vp', 'mosh': 'mo', 'vp_fingram': 'vf', 'vp_business': 'vb',
            'mosh_fingram': 'mf', 'mosh_entrepreneurship': 'me'}

SYSTEM_PROMPT = """Ты сверяешь оцифровку олимпиадных заданий (экономика, финансовая грамотность, бизнес) с картинками страниц PDF. Тебе даны картинки страниц (Страница 1, Страница 2, …) и JSON с фрагментами оцифровки, которые взяты с этих страниц. Фрагмент — одна группа полей одного задания:
- group="statement": title (название), statement_md (условие), parts (пункты: [{label, text}]), figures (сколько вырезанных рисунков уже есть);
- group="solution": solution_md (решение), answer (ответ);
- group="criteria": criteria_md (критерии оценивания).

Для КАЖДОГО фрагмента сравни поля с картинкой и найди дефекты оцифровки. Классы дефектов:
missing_text — пропущен текст (абзац, фраза, сноска);
missing_table — пропущена таблица;
table_wrong — таблица искажена (ячейки, строки, столбцы);
missing_options — потеряны варианты ответа теста;
missing_part — потерян пункт задания (а, б, 1.2 …);
part_split_wrong — пункты стоят не там (застряли в условии, слиты, разрезаны);
figure_as_text — рисунок/график переписан словами вместо картинки;
figure_missing — рисунок есть на странице, а в фрагменте его нет (figures=0);
formula_wrong — формула искажена;
number_wrong — неверное число;
solution_misattached — решение/критерии другого задания;
criteria_missing — критерии на странице есть, в фрагменте их нет;
service_block_in_task — в поле попал служебный текст (колонтитул, инструкция бланка, правила олимпиады, текст соседнего задания);
title_wrong — название задания неверно (или в название попала формулировка вопроса);
other — прочее.

ПРАВИЛА:
1. Переписывай ДОСЛОВНО, как на картинке. Опечатки авторов — как в оригинале. Ничего не решай, не досочиняй, не добавляй ответов, которых нет на странице.
2. Исправляй только то, что ВИДНО на страницах. Текст задания может продолжаться на страницах, которых тебе не дали: если фрагмент помечен "editable": false — только опиши дефекты, fixes не давай.
3. Колонтитулы, номера страниц, водяные знаки — не дефект и в текст не идут.
4. Разметка: Markdown; формулы — TeX внутри $…$ (KaTeX); таблицы — markdown-таблицами; варианты ответа — списком, по строке на вариант, с исходными буквами/цифрами.
5. Если всё верно (расхождения только в оформлении, пробелах, переносах) — verdict "ok", defects [], fixes {}.
6. В fixes — ПОЛНЫЙ исправленный текст каждого поля с дефектом (не дифф): statement_md, title, answer, solution_md, criteria_md — строкой; parts — полным списком [{"label": …, "text": …}]. Поля без дефекта в fixes не включай.
7. evidence — ДОСЛОВНАЯ цитата с картинки, которая доказывает дефект (для пропуска — сам пропущенный текст целиком, со всеми его числами).
8. Рисунок (график, схема, диаграмма), которого нет в фрагменте или который переписан текстом, — дай его рамку в figure_bboxes: page — номер страницы в этом запросе (1, 2, …), bbox — [x0, y0, x1, y1] в долях ширины и высоты страницы (0…1, от левого верхнего угла), рамка охватывает рисунок с подписями осей, но без соседнего текста. Таблицы — не рисунки, их переписывай текстом.
9. confidence — от 0 до 1: насколько ты уверен в вердикте и правках.
10. unlisted — только задание или пункт, которого на страницах видно, а в списке «задания комплекта в эталоне» его нет. Соседние задания из этого списка (они проверяются в других запросах) в unlisted не пиши.

ПРИНЯТАЯ РАЗМЕТКА ЭТАЛОНА (это НЕ дефекты, не исправляй):
- пункты задания стоят и в statement_md, и в parts — так задумано; дефект — только если пункт потерян, слит с другим или разрезан;
- в начале условия может стоять вступление СВОЕГО раздела (инструкция к тесту: «Выберите один верный ответ…», «Тест 1. Этот раздел состоит из…») — не удаляй его, даже если на этой странице его нет; дефект — текст ЧУЖОГО задания или раздела (заголовок следующего раздела, условие соседней задачи, инструкция бланка ответов);
- в решении/ответе теста пометка «(отмечено)» показывает вариант, отмеченный в ключе, — так задумано;
- в решении может повторяться формулировка вопроса пункта перед ответом — это не дефект.

Ответ — ТОЛЬКО JSON, без пояснений вокруг:
{"tasks": [{"fid": "…", "verdict": "ok"|"needs_fix", "defects": [{"class": "…", "what": "…", "evidence": "…"}], "fixes": {…}, "figure_bboxes": [{"page": 1, "bbox": [0.1, 0.2, 0.9, 0.5], "caption": "…"}], "confidence": 0.9}], "unlisted": [{"what": "…", "evidence": "…"}]}"""


# ── Наборы данных ────────────────────────────────────────────────────────

def read_jsonl(path):
    with open(path, encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')


def task_key(row):
    return '%s|%s|%s' % (row['event_id'], row['number'], row.get('task_variant') or '')


@dataclass
class DataSet:
    """Один эталон: строки, манифест страниц, пути."""
    name: str
    digitized: str
    rows: list
    manifest: dict          # «файл#pN» → запись манифеста
    in_version: str
    out_version: str

    @property
    def audit_dir(self):
        return os.path.join(self.digitized, 'audit_claude')

    def png(self, ref):
        return os.path.join(self.digitized, self.manifest[ref]['png'])

    def layer(self, ref):
        item = self.manifest[ref]
        path = os.path.join(self.digitized, item['page_dir'], 'p%d.txt' % item['page'])
        if os.path.exists(path):
            with open(path, encoding='utf-8', errors='replace') as handle:
                return handle.read()
        return ''


def load_manifest(digitized):
    out = {}
    with open(os.path.join(digitized, 'pages_manifest.jsonl'), encoding='utf-8') as handle:
        for line in handle:
            if line.strip():
                item = json.loads(line)
                out['%s#p%d' % (item['file'], item['page'])] = item
    return out


def load_set(name, data_root, audit_dirs):
    """`audit_dirs` — слаг реестра → папка аудита (из `registry`, не правим его)."""
    slug, in_version, rel, out_version = SETS[name]
    digitized = os.path.join(data_root, audit_dirs[slug], 'digitized')
    rows = read_jsonl(os.path.join(digitized, rel))
    return DataSet(name, digitized, rows, load_manifest(digitized), in_version, out_version)


# ── Единицы аудита ───────────────────────────────────────────────────────

def _uniq(items):
    seen, out = set(), []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def page_id(ref, manifest):
    item = manifest[ref]
    return '%s_p%d' % (item['page_dir'].split('/')[-1], item['page'])


def fragment_fields(row, group):
    out = {}
    for name in FIX_FIELDS[group]:
        value = row.get(name)
        if name == 'parts':
            out[name] = [{'label': p.get('label', ''), 'text': p.get('text', '')}
                         for p in (value or []) if isinstance(p, dict)]
        else:
            out[name] = value or ''
    if group == 'statement':
        out['figures'] = len(row.get('figures') or [])
    if group == 'solution':
        out['figures'] = len(row.get('solution_figures') or [])
    return out


def build_units(ds, max_pages=MAX_UNIT_PAGES):
    """Единицы набора: {unit_id: {pages: [ref…], fragments: […]}} в порядке
    первого появления. Группа без страниц (docx) или с неизвестной страницей
    не проверяется — она попадает в `skipped` с причиной."""
    units = collections.OrderedDict()
    skipped = []
    for row in ds.rows:
        for group, (pages_key, _) in GROUPS.items():
            refs = _uniq(row.get(pages_key) or [])
            if not refs:
                continue
            missing = [r for r in refs if r not in ds.manifest]
            if missing:
                skipped.append((task_key(row), group, 'страница не в манифесте: %s' % missing[0]))
                continue
            uid = '%s_%s' % (SET_ABBR[ds.name], page_id(refs[0], ds.manifest))
            unit = units.setdefault(uid, {'unit': uid, 'set': ds.name, 'pages': [],
                                          'fragments': []})
            for ref in refs:
                if ref not in unit['pages'] and len(unit['pages']) < max_pages:
                    unit['pages'].append(ref)
            editable = all(r in unit['pages'] for r in refs)
            unit['fragments'].append({
                'fid': '%s#%s' % (task_key(row), group),
                'task': {'event_id': row['event_id'], 'number': row['number'],
                         'task_variant': row.get('task_variant') or ''},
                'group': group,
                'editable': editable,
                'own_pages': [unit['pages'].index(r) + 1 for r in refs if r in unit['pages']],
                'fields': fragment_fields(row, group),
            })
    by_event = collections.defaultdict(list)
    for row in ds.rows:
        head = re.sub(r'\s+', ' ', row.get('title') or row.get('statement_md') or '')[:50]
        variant = ('/' + row['task_variant']) if row.get('task_variant') else ''
        by_event[row['event_id']].append('%s%s «%s»' % (row['number'], variant, head))
    for unit in units.values():
        events = {f['task']['event_id'] for f in unit['fragments']}
        unit['event_tasks'] = {ev: by_event[ev] for ev in sorted(events)}
    return units, skipped


def unit_prompt(unit):
    """Текст пользовательского сообщения (без картинок)."""
    pages = ['Страница %d: %s, стр. %s' % (i + 1, ref.split('#')[0].split('/')[-1],
                                            ref.rsplit('#p', 1)[-1])
             for i, ref in enumerate(unit['pages'])]
    payload = [{k: f[k] for k in ('fid', 'group', 'editable', 'own_pages', 'fields')}
               for f in unit['fragments']]
    catalog = ''
    if unit.get('event_tasks'):
        catalog = '\n\nЗадания комплекта в эталоне (номер: начало условия):\n' + '\n'.join(
            '%s: %s' % (ev, '; '.join(items)) for ev, items in sorted(unit['event_tasks'].items()))
    return ('Страницы в этом запросе:\n' + '\n'.join(pages) + catalog +
            '\n\nФрагменты оцифровки (own_pages — на каких страницах запроса лежит фрагмент):\n' +
            json.dumps(payload, ensure_ascii=False, indent=1) +
            '\n\nПроверь каждый фрагмент и верни JSON по правилам.')


def image_block(path):
    with open(path, 'rb') as handle:
        data = base64.b64encode(handle.read()).decode('ascii')
    return {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png', 'data': data}}


def request_params(unit, ds, model, max_tokens=16000):
    content = []
    for i, ref in enumerate(unit['pages']):
        content.append({'type': 'text', 'text': 'Страница %d:' % (i + 1)})
        content.append(image_block(ds.png(ref)))
    content.append({'type': 'text', 'text': unit_prompt(unit)})
    return {
        'model': model,
        'max_tokens': max_tokens,
        'output_config': {'effort': 'low'},
        'system': [{'type': 'text', 'text': SYSTEM_PROMPT, 'cache_control': {'type': 'ephemeral'}}],
        'messages': [{'role': 'user', 'content': content}],
    }


def write_job(unit, ds, jobs_dir):
    """Файл задания для агента Claude Code: инструкция, пути картинок, фрагменты."""
    os.makedirs(jobs_dir, exist_ok=True)
    lines = ['# Единица %s' % unit['unit'], '', '## Картинки (прочитай каждую)', '']
    for i, ref in enumerate(unit['pages']):
        lines.append('- Страница %d: `%s`' % (i + 1, os.path.abspath(ds.png(ref))))
    lines += ['', '## Запрос', '', unit_prompt(unit), '']
    path = os.path.join(jobs_dir, unit['unit'] + '.md')
    with open(path, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write('\n'.join(lines))
    return path


# ── Сырые ответы ─────────────────────────────────────────────────────────

def raw_path(ds, model, uid):
    return os.path.join(ds.audit_dir, 'raw', model, uid + '.json')


def save_raw(ds, model, uid, text, source, usage=None):
    path = raw_path(ds, model, uid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as handle:
        json.dump({'unit': uid, 'model': model, 'source': source, 'text': text,
                   'usage': usage or {}, 'saved': datetime.datetime.now().isoformat(timespec='seconds')},
                  handle, ensure_ascii=False, indent=1)
    return path


def load_raw(ds, model, uid):
    path = raw_path(ds, model, uid)
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


_FENCE = re.compile(r'^\s*```(?:json)?\s*|\s*```\s*$')


def parse_reply(text):
    """Ответ → {'tasks': […], 'unlisted': […]} или {'_parse_error': …}. Не бросает."""
    body = _FENCE.sub('', (text or '').strip())
    candidates = [body]
    start, end = body.find('{'), body.rfind('}')
    if 0 <= start < end:
        candidates.append(body[start:end + 1])
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(data, dict) and isinstance(data.get('tasks'), list):
            data.setdefault('unlisted', [])
            return data
    # Несколько объектов подряд (модель поправила себя вторым JSON) или рассуждение
    # с фигурными скобками перед ответом: берём ПОСЛЕДНИЙ целый объект со списком tasks.
    decoder, found = json.JSONDecoder(), None
    pos = body.find('{')
    while pos != -1:
        try:
            data, end = decoder.raw_decode(body, pos)
        except ValueError:
            pos = body.find('{', pos + 1)
            continue
        if isinstance(data, dict) and isinstance(data.get('tasks'), list):
            found = data
        pos = body.find('{', end)
    if found is not None:
        found.setdefault('unlisted', [])
        return found
    return {'tasks': [], 'unlisted': [], '_parse_error': 'не JSON со списком tasks'}


# ── Проверки ─────────────────────────────────────────────────────────────

_THOUSANDS = re.compile(r'(?<=\d)(?:[    ]|\\,|\\ |\{\\,\}|~)(?=\d{3}(?!\d))')
_DECIMAL_TEX = re.compile(r'\{,\}')
_NUM = re.compile(r'\d+')


def numbers(text):
    """Множество чисел текста: группы разрядов склеены («1 000» → 1000),
    «{,}» — десятичная запятая; число — максимальная серия цифр."""
    text = _DECIMAL_TEX.sub(',', text or '')
    prev = None
    while prev != text:
        prev, text = text, _THOUSANDS.sub('', text)
    return set(_NUM.findall(text))


def field_text(value):
    # Метка пункта и текст — через табуляцию: через пробел `numbers` склеил бы
    # «2» + «500» в «2 500» → чужое число 2500.
    if isinstance(value, list):
        return '\n'.join('%s\t%s' % (p.get('label', ''), p.get('text', ''))
                         for p in value if isinstance(p, dict))
    return value if isinstance(value, str) else ''


_ANSWER = re.compile(r'Ответ\s*:', re.I)

_MATH = re.compile(r'\$\$(.+?)\$\$|\$(.+?)\$|\\\((.+?)\\\)|\\\[(.+?)\\\]', re.S)


def math_segments(text):
    out = []
    for m in _MATH.finditer(text or ''):
        display = m.group(1) is not None or m.group(4) is not None
        expr = next(g for g in m.groups() if g is not None)
        out.append((expr, display))
    return out


_KATEX_JS = r"""
const fs = require('fs');
const katex = require(process.argv[2]);
const items = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const out = items.map(([expr, display]) => {
  try { katex.renderToString(expr, {throwOnError: true, displayMode: display, strict: 'ignore'}); return null; }
  catch (e) { return String(e.message || e).slice(0, 200); }
});
fs.writeFileSync(process.argv[4], JSON.stringify(out));
"""


def katex_path():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, '..', '..', 'static', 'vendor',
                                         'katex-0.16.9', 'katex.min.js'))


def katex_errors(segments):
    """[(expr, display)] → [ошибка или None] одним вызовом node."""
    if not segments:
        return []
    with tempfile.TemporaryDirectory() as tmp:
        script = os.path.join(tmp, 'k.js')
        src = os.path.join(tmp, 'in.json')
        dst = os.path.join(tmp, 'out.json')
        with open(script, 'w', encoding='utf-8') as handle:
            handle.write(_KATEX_JS)
        with open(src, 'w', encoding='utf-8') as handle:
            json.dump([[e, d] for e, d in segments], handle, ensure_ascii=False)
        subprocess.run(['node', script, katex_path(), src, dst], check=True,
                       capture_output=True, timeout=300)
        with open(dst, encoding='utf-8') as handle:
            return json.load(handle)


@dataclass
class FixCheck:
    fid: str
    field: str
    new: object
    old: object
    ok: bool = True
    reasons: list = field(default_factory=list)


def check_unit(unit, reply, page_texts, katex=katex_errors, min_confidence=MIN_CONFIDENCE):
    """Ответ единицы → (принятые правки, отказы, сводка по фрагментам).

    `page_texts` — текст слоя PDF страниц единицы (может быть пустым у скана).
    Возвращает `accepted`: [FixCheck], `rejected`: [FixCheck или (fid, причина)],
    `verdicts`: {fid: {...ответ модели по фрагменту...}}.
    """
    frags = {f['fid']: f for f in unit['fragments']}
    old_corpus = '\n'.join(field_text(v) for f in unit['fragments']
                           for v in f['fields'].values())
    layer = '\n'.join(page_texts)
    accepted, rejected, verdicts = [], [], {}
    checks = []
    if reply.get('_parse_error'):
        return [], [(None, 'ответ не разобран: %s' % reply['_parse_error'])], {}
    for item in reply.get('tasks') or []:
        if not isinstance(item, dict):
            continue
        fid = item.get('fid')
        if fid not in frags:
            rejected.append((fid, 'чужой fid'))
            continue
        verdicts[fid] = item
        fixes = item.get('fixes') or {}
        if not isinstance(fixes, dict) or not fixes:
            continue
        frag = frags[fid]
        evidence = '\n'.join(str(d.get('evidence') or '') for d in item.get('defects') or []
                             if isinstance(d, dict))
        classes = {d.get('class') for d in item.get('defects') or [] if isinstance(d, dict)}
        corpus_nums = numbers(layer) | numbers(evidence) | numbers(old_corpus)
        corpus_text = '\n'.join((layer, evidence, old_corpus))
        try:
            confidence = float(item.get('confidence', 0))
        except (TypeError, ValueError):
            confidence = 0.0
        for name, new in fixes.items():
            chk = FixCheck(fid, name, new, frag['fields'].get(name))
            if name not in FIX_FIELDS[frag['group']]:
                chk.reasons.append('поле %s не из группы %s' % (name, frag['group']))
            if not frag['editable']:
                chk.reasons.append('группа видна не целиком (editable=false)')
            if confidence < min_confidence:
                chk.reasons.append('уверенность %.2f < %.2f' % (confidence, min_confidence))
            if name == 'parts':
                if not (isinstance(new, list) and all(isinstance(p, dict) and 'text' in p for p in new)):
                    chk.reasons.append('parts не список {label, text}')
            elif not isinstance(new, str):
                chk.reasons.append('поле не строка')
            text = field_text(new)
            alien = sorted(numbers(text) - corpus_nums, key=lambda s: (len(s), s))
            if alien:
                chk.reasons.append('чужие числа: %s' % ', '.join(alien[:8]))
            if _ANSWER.search(text) and not _ANSWER.search(corpus_text):
                chk.reasons.append('«Ответ:» которого нет на странице')
            old_len = len(field_text(chk.old).strip())
            if old_len >= 80 and len(text.strip()) < SHRINK_RATIO * old_len and not (classes & SHRINK_OK):
                chk.reasons.append('поле урезано: %d → %d знаков' % (old_len, len(text.strip())))
            if text.strip() == field_text(chk.old).strip():
                chk.reasons.append('правка совпадает с прежним текстом')
            checks.append((chk, math_segments(text)))
    segs = [s for _, ss in checks for s in ss]
    errors = katex(segs) if segs else []
    pos = 0
    for chk, ss in checks:
        errs = [e for e in errors[pos:pos + len(ss)] if e]
        pos += len(ss)
        if errs:
            chk.reasons.append('KaTeX: %s' % errs[0])
        chk.ok = not chk.reasons
        (accepted if chk.ok else rejected).append(chk)
    return accepted, rejected, verdicts


# ── Рисунки ──────────────────────────────────────────────────────────────

def valid_bbox(bbox):
    try:
        x0, y0, x1, y1 = (float(v) for v in bbox)
    except (TypeError, ValueError):
        return None
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        return None
    area = (x1 - x0) * (y1 - y0)
    if not FIG_MIN_AREA <= area <= FIG_MAX_AREA:
        return None
    return x0, y0, x1, y1


def crop_figure(png_path, bbox, out_path, margin=FIG_MARGIN):
    """Вырезка по нормированной рамке (с полем `margin`) → PNG. Возвращает
    размер вырезки (w, h) или None, если рамка негодная."""
    from PIL import Image
    box = valid_bbox(bbox)
    if box is None:
        return None
    with Image.open(png_path) as image:
        w, h = image.size
        x0, y0, x1, y1 = box
        px = (max(0, int((x0 - margin) * w)), max(0, int((y0 - margin) * h)),
              min(w, int(round((x1 + margin) * w))), min(h, int(round((y1 + margin) * h))))
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        image.crop(px).save(out_path)
        return px[2] - px[0], px[3] - px[1]


def contact_sheet(paths, out_path, thumb=360, cols=4):
    """Контактный лист вырезок с подписью-номером: для просмотра глазами."""
    from PIL import Image, ImageDraw
    if not paths:
        return None
    rows = (len(paths) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * thumb, rows * (thumb + 24)), 'white')
    draw = ImageDraw.Draw(sheet)
    for i, path in enumerate(paths):
        with Image.open(path) as image:
            image = image.convert('RGB')
            image.thumbnail((thumb - 8, thumb - 8))
            x, y = (i % cols) * thumb, (i // cols) * (thumb + 24)
            sheet.paste(image, (x + 4, y + 24))
            draw.text((x + 4, y + 4), '%d %s' % (i + 1, os.path.basename(path)[:44]), fill='black')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    sheet.save(out_path)
    return out_path


# ── Деньги ───────────────────────────────────────────────────────────────

def usage_cost(model, usage):
    price = BATCH_PRICES[model]
    return ((usage.get('input_tokens', 0) * price[0] +
             usage.get('cache_creation_input_tokens', 0) * price[1] +
             usage.get('cache_read_input_tokens', 0) * price[2] +
             usage.get('output_tokens', 0) * price[3]) / 1e6)


def spent(ledger_path):
    if not os.path.exists(ledger_path):
        return 0.0
    return sum(json.loads(line).get('usd', 0) for line in open(ledger_path, encoding='utf-8')
               if line.strip())


# ── Message Batches API ──────────────────────────────────────────────────

def make_client():
    """Клиент Anthropic. Ключ организации без пространства получает 400 —
    заголовок `anthropic-workspace-id` берётся из ANTHROPIC_WORKSPACE_ID."""
    import anthropic
    headers = {}
    if os.environ.get('ANTHROPIC_WORKSPACE_ID'):
        headers['anthropic-workspace-id'] = os.environ['ANTHROPIC_WORKSPACE_ID']
    return anthropic.Anthropic(default_headers=headers or None)


def custom_id(uid):
    """custom_id пакета: ≤ 64 знаков, [A-Za-z0-9_-]."""
    clean = re.sub(r'[^A-Za-z0-9_-]', '-', uid)
    if len(clean) > 64:
        clean = clean[:47] + '-' + hashlib.sha1(uid.encode()).hexdigest()[:16]
    return clean


def submit_batches(client, ds, units, model, chunk=200, params=None):
    """Отправить пакеты по единицам без сырого ответа. Состояние —
    audit_claude/batches.jsonl ({batch_id, model, ids: {custom_id: unit}}).
    `params(unit)` — своя сборка запроса (второй проход); по умолчанию `request_params`."""
    todo = [u for u in units if load_raw(ds, model, u['unit']) is None]
    state = os.path.join(ds.audit_dir, 'batches.jsonl')
    pending = set()
    if os.path.exists(state):
        for item in read_jsonl(state):
            if item['model'] == model and not item.get('collected'):
                pending.update(item['ids'].values())
    todo = [u for u in todo if u['unit'] not in pending]
    sent = []
    for i in range(0, len(todo), chunk):
        part = todo[i:i + chunk]
        ids = {custom_id(u['unit']): u['unit'] for u in part}
        batch = client.messages.batches.create(requests=[
            {'custom_id': cid, 'params': params(u) if params else request_params(u, ds, model)}
            for cid, u in zip(ids, part)])
        record = {'batch_id': batch.id, 'model': model, 'ids': ids, 'collected': False,
                  'created': datetime.datetime.now().isoformat(timespec='seconds')}
        os.makedirs(ds.audit_dir, exist_ok=True)
        with open(state, 'a', encoding='utf-8', newline='\n') as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + '\n')
        sent.append(batch.id)
    return sent


def collect_batches(client, ds, ledger_path):
    """Забрать готовые пакеты: сырой ответ → raw/, расход → ledger.
    Возвращает (собрано, ещё в работе)."""
    state = os.path.join(ds.audit_dir, 'batches.jsonl')
    if not os.path.exists(state):
        return 0, 0
    records = read_jsonl(state)
    done = waiting = 0
    for record in records:
        if record.get('collected'):
            continue
        batch = client.messages.batches.retrieve(record['batch_id'])
        if batch.processing_status != 'ended':
            waiting += 1
            continue
        with open(ledger_path, 'a', encoding='utf-8', newline='\n') as ledger:
            for result in client.messages.batches.results(record['batch_id']):
                uid = record['ids'].get(result.custom_id)
                if uid is None or result.result.type != 'succeeded':
                    continue
                msg = result.result.message
                text = ''.join(b.text for b in msg.content if b.type == 'text')
                usage = msg.usage.model_dump() if hasattr(msg.usage, 'model_dump') else dict(msg.usage)
                save_raw(ds, record['model'], uid, text, 'batch:' + record['batch_id'], usage)
                ledger.write(json.dumps({'set': ds.name, 'unit': uid, 'model': record['model'],
                                         'usd': round(usage_cost(record['model'], usage), 6)}) + '\n')
                done += 1
        record['collected'] = True
    write_jsonl(state, records)
    return done, waiting


# ── Слой правок и сборка версии ──────────────────────────────────────────

def layer_entry(chk, unit, model):
    return {'key': chk.fid.split('#')[0], 'group': chk.fid.split('#')[1], 'field': chk.field,
            'value': chk.new, 'unit': unit['unit'], 'model': model,
            'old_sha1': hashlib.sha1(json.dumps(chk.old, ensure_ascii=False).encode()).hexdigest()[:12]}


def apply_layer(rows, layer):
    """Строки + слой правок → новые строки (копии) и журнал [(key, field, status)].
    Правка применяется, только если поле не менялось с момента аудита
    (sha1 прежнего значения совпал)."""
    import copy
    out = [copy.deepcopy(r) for r in rows]
    index = {task_key(r): r for r in out}
    log = []
    for entry in layer:
        row = index.get(entry['key'])
        if row is None:
            log.append((entry['key'], entry['field'], 'нет задания'))
            continue
        if entry['field'] in ('figure',):
            row.setdefault(entry['target'], []).append(entry['value'])
            log.append((entry['key'], entry['field'], 'applied'))
            continue
        current = row.get(entry['field'])
        if entry['field'] == 'parts':
            current = [{'label': p.get('label', ''), 'text': p.get('text', '')}
                       for p in (current or []) if isinstance(p, dict)]
        elif current is None:
            current = ''
        sha = hashlib.sha1(json.dumps(current, ensure_ascii=False).encode()).hexdigest()[:12]
        if sha != entry['old_sha1']:
            log.append((entry['key'], entry['field'], 'поле изменилось после аудита'))
            continue
        row[entry['field']] = entry['value']
        log.append((entry['key'], entry['field'], 'applied'))
    return out, log


def write_csv(path, header, rows):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle, delimiter=';')
        writer.writerow(header)
        writer.writerows(rows)


def png_data_uri(path, max_side=1100):
    from PIL import Image
    with Image.open(path) as image:
        image = image.convert('RGB')
        image.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        image.save(buf, 'JPEG', quality=70)
    return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


# ── Проверка набора и сведение моделей ───────────────────────────────────

def units_index(ds):
    units, _ = build_units(ds)
    return units


def _confidence(item):
    try:
        return float(item.get('confidence', 0))
    except (TypeError, ValueError):
        return 0.0


def check_set(ds, model, units=None, katex=katex_errors):
    """Все сырые ответы модели по набору → audit_claude/checked_<модель>.jsonl."""
    units = units or units_index(ds)
    out = []
    for uid, unit in units.items():
        raw = load_raw(ds, model, uid)
        if raw is None:
            continue
        reply = parse_reply(raw.get('text'))
        texts = [ds.layer(ref) for ref in unit['pages']]
        accepted, rejected, verdicts = check_unit(unit, reply, texts, katex=katex)
        frags = {f['fid']: f for f in unit['fragments']}
        figures = []
        for fid, item in verdicts.items():
            for fig in item.get('figure_bboxes') or []:
                if not isinstance(fig, dict):
                    continue
                try:
                    page = int(fig.get('page', 1))
                except (TypeError, ValueError):
                    page = 0
                inside = 1 <= page <= len(unit['pages'])
                reason = ''
                if not inside or valid_bbox(fig.get('bbox')) is None:
                    reason = 'негодная рамка'
                elif frags[fid]['group'] not in ('statement', 'solution'):
                    reason = 'рисунок у критериев'
                elif not frags[fid]['editable']:
                    reason = 'группа видна не целиком'
                elif _confidence(item) < MIN_CONFIDENCE:
                    reason = 'низкая уверенность'
                figures.append({'fid': fid, 'page_ref': unit['pages'][page - 1] if inside else None,
                                'bbox': fig.get('bbox'), 'caption': str(fig.get('caption') or ''),
                                'ok': not reason, 'reason': reason})
        out.append({
            'unit': uid, 'model': model,
            'parse_error': reply.get('_parse_error', ''),
            'verdicts': {fid: {'verdict': v.get('verdict'), 'defects': v.get('defects') or [],
                               'confidence': v.get('confidence')} for fid, v in verdicts.items()},
            'missing_fids': sorted(set(frags) - set(verdicts)),
            'accepted': [{'fid': c.fid, 'field': c.field, 'value': c.new,
                          'old_sha1': _sha(c.old)} for c in accepted],
            'rejected': [({'fid': c.fid, 'field': c.field, 'value': c.new, 'reasons': c.reasons}
                          if isinstance(c, FixCheck) else {'fid': c[0], 'field': '', 'reasons': [c[1]]})
                         for c in rejected],
            'figures': figures,
            'unlisted': reply.get('unlisted') or [],
        })
    write_jsonl(os.path.join(ds.audit_dir, 'checked_%s.jsonl' % model), out)
    return out


def _sha(value):
    return hashlib.sha1(json.dumps(value, ensure_ascii=False).encode()).hexdigest()[:12]


def load_checked(ds, model):
    path = os.path.join(ds.audit_dir, 'checked_%s.jsonl' % model)
    return read_jsonl(path) if os.path.exists(path) else []


def resolve(checked_by_model, primary='claude-sonnet-5-5', secondary='claude-haiku-5-5'):
    """Сводит проверенные ответы моделей по фрагментам. Мнение `primary`
    (Sonnet) сильнее; правки и рисунки `secondary` (Haiku) без второго мнения
    не применяются — уходят на утро."""
    final, fixes = {}, collections.defaultdict(list)
    rejected, figures = collections.defaultdict(list), collections.defaultdict(list)
    unlisted, parse_errors = [], []
    for model in (secondary, primary):           # primary перезаписывает
        for rec in checked_by_model.get(model) or []:
            if rec.get('parse_error'):
                parse_errors.append((rec['unit'], model, rec['parse_error']))
            for fid, v in rec['verdicts'].items():
                final[fid] = dict(v, model=model, unit=rec['unit'])
                for bucket in (fixes, rejected, figures):
                    bucket.pop(fid, None)
            for acc in rec['accepted']:
                fixes[acc['fid']].append(dict(acc, model=model, unit=rec['unit']))
            for rej in rec['rejected']:
                if rej.get('fid') in final:
                    rejected[rej['fid']].append(dict(rej, model=model, unit=rec['unit']))
            for fig in rec['figures']:
                figures[fig['fid']].append(dict(fig, model=model, unit=rec['unit']))
            for item in rec['unlisted']:
                unlisted.append(dict(item if isinstance(item, dict) else {'what': str(item)},
                                     unit=rec['unit'], model=model))
    for fid in list(fixes):
        if final[fid]['model'] == secondary:
            for acc in fixes.pop(fid):
                rejected[fid].append(dict(acc, reasons=['нет второго мнения Sonnet']))
    for fid, figs in figures.items():
        if final[fid]['model'] == secondary:
            for fig in figs:
                if fig['ok']:
                    fig['ok'], fig['reason'] = False, 'нет второго мнения Sonnet'
    return {'final': final, 'fixes': dict(fixes), 'rejected': dict(rejected),
            'figures': dict(figures), 'unlisted': unlisted, 'parse_errors': parse_errors}


# ── Хвосты v6 (экономика) ────────────────────────────────────────────────

_OPTION_LINE = re.compile(r'^\s*(?:\d{1,2}|[а-гa-dА-ГA-D])[.)]\s')


def tail_rules_econ(rows, set_name, skip_keys=()):
    """Детерминированные правила для хвостов v6 → (строки, журнал, удалённые).

    1. МОШ 2012–2014: формулировка вопроса теста лежит в `title` — ставится в
       условие перед первым вариантом ответа, `title` очищается.
    2. mosh-2011-final-10 «10» — пункт 5 задачи 3 (в условии задачи 3 он уже
       есть), а его решение — настоящее решение задачи 3. Задание «10»
       убирается, его решение становится решением задачи 3; прежний текст
       решения задачи 3 сохраняется в `solution_md_v6` и идёт на утро.

    `skip_keys` — задания, чьё условие уже правит Claude: правило 1 их не трогает.
    """
    log, removed = [], {}
    if set_name != 'mosh':
        return rows, log, removed
    out = []
    for row in rows:
        title = (row.get('title') or '').strip()
        if (task_key(row) not in skip_keys
                and row.get('year') in (2012, 2013, 2014) and str(row['number']).startswith('тест')
                and title and title not in (row.get('statement_md') or '')):
            lines = (row.get('statement_md') or '').split('\n')
            at = next((i for i, line in enumerate(lines) if _OPTION_LINE.match(line)), None)
            if at is None:
                lines += ['', title]
            else:
                lines[at:at] = [title, '']
            row = dict(row, statement_md='\n'.join(lines).strip(), title='')
            log.append((task_key(row), 'statement_md,title', 'вопрос из title → в условие'))
        out.append(row)
    index = {task_key(r): r for r in out}
    k10, k3 = 'mosh-2011-final-10-v1|10|', 'mosh-2011-final-10-v1|3|'
    if k10 in index and k3 in index and index[k10]['statement_md'].strip() in index[k3]['statement_md']:
        t10, t3 = index[k10], index[k3]
        log.append((k3, 'solution_md', 'решение «задания 10» → решение задачи 3; прежнее решение '
                    'задачи 3 — в solution_md_v6 (на утро)'))
        t3['solution_md_v6'] = t3['solution_md']
        t3['solution_md'] = t10['solution_md']
        t3['solution_pages'] = _uniq(list(t10['solution_pages']))
        out = [r for r in out if task_key(r) != k10]
        removed[k10] = 'пункт 5 задачи 3 (mosh-2011-final-10-v1|3|): условие уже в задаче 3, решение перенесено'
    return out, log, removed


# ── Ответы к тестам из ключа ─────────────────────────────────────────────

_ANSWER_TOKEN = re.compile(r'^[0-9]{1,2}$|^[а-еa-eА-ЕA-E]$')


def answer_entries(rows, replies, key_texts, min_confidence=MIN_CONFIDENCE):
    """Ответы агента по ключу → (записи слоя для пустых `answer`, отказы).

    `replies` — [{event_id, answers: [{number, answer, evidence, confidence}]}],
    `key_texts` — {event_id: текст слоя страниц ключа}. Ответ принимается, если
    у теста поле `answer` пустое, каждый вариант ответа есть среди меток пунктов
    (или пунктов нет, а метка — цифра/буква), числа цитаты есть в слое ключа
    (если слой есть) и уверенность не ниже порога."""
    index = {(r['event_id'], r['number']): r for r in rows}
    entries, rejected = [], []
    for rep in replies:
        ev = rep.get('event_id')
        layer = key_texts.get(ev, '')
        for item in rep.get('answers') or []:
            row = index.get((ev, item.get('number')))
            why = []
            if row is None:
                rejected.append((ev, item.get('number'), 'нет такого теста'))
                continue
            if (row.get('answer') or '').strip():
                why.append('ответ уже есть')
            tokens = [t.strip().rstrip(').') for t in str(item.get('answer') or '').split(',') if t.strip()]
            labels = {str(p.get('label', '')).strip().rstrip(').') for p in row.get('parts') or []
                      if isinstance(p, dict)}
            if not tokens or not all(_ANSWER_TOKEN.match(t) for t in tokens):
                why.append('ответ не метка варианта: %r' % item.get('answer'))
            elif labels and not set(tokens) <= labels:
                why.append('нет такого варианта: %s' % ','.join(sorted(set(tokens) - labels)))
            evidence = str(item.get('evidence') or '')
            if layer.strip() and numbers(evidence) - numbers(layer):
                why.append('цитаты нет в ключе')
            if _confidence(item) < min_confidence:
                why.append('уверенность %.2f' % _confidence(item))
            if why:
                rejected.append((ev, item.get('number'), '; '.join(why)))
                continue
            entries.append({'key': task_key(row), 'group': 'solution', 'field': 'answer',
                            'value': ', '.join(tokens), 'old_sha1': _sha(row.get('answer') or ''),
                            'unit': 'answers:' + ev, 'model': 'claude-sonnet-5-5',
                            'evidence': evidence[:200]})
    return entries, rejected


# ── Сборка версии ────────────────────────────────────────────────────────

def _same_figure(old, page_item, bbox, min_iou=0.3):
    """Уже вырезанный рисунок той же страницы с заметным пересечением рамок.
    У прежних рисунков рамка `bbox_model` — в тысячных долях страницы."""
    if not isinstance(old, dict) or old.get('page') != page_item['page'] \
            or old.get('page_dir') != page_item['page_dir'] or not old.get('bbox_model'):
        return False
    try:
        a = [float(v) / 1000 for v in old['bbox_model']]
        b = [float(v) for v in bbox]
    except (TypeError, ValueError):
        return False
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return union > 0 and inter / union >= min_iou


def figure_layer(ds, resolved):
    """Принятые рамки рисунков → вырезки `<vN>/figures_<vN>/` и записи слоя.
    Возвращает (записи слоя, плохие рамки для утра)."""
    entries, bad = [], []
    version = ds.out_version
    # Вырезки, забракованные при просмотре контактного листа глазами (имя файла в строке).
    rejected_path = os.path.join(ds.audit_dir, 'figures_rejected.txt')
    eyes_bad = set()
    if os.path.exists(rejected_path):
        with open(rejected_path, encoding='utf-8') as handle:
            eyes_bad = {line.split('#')[0].strip() for line in handle if line.split('#')[0].strip()}
    existing = {task_key(r): (r.get('figures') or []) + (r.get('solution_figures') or [])
                for r in ds.rows}
    for fid, figs in sorted(resolved['figures'].items()):
        key, group = fid.split('#')
        n = 0
        for fig in figs:
            if not fig.get('ok'):
                bad.append(dict(fig, fid=fid))
                continue
            n += 1
            ev, num, var = key.split('|')
            name = '%s_%s%s_c%d%s.png' % (ev, re.sub(r'[^\w-]', '_', num), ('_' + var) if var else '',
                                          n, 's' if group == 'solution' else '')
            rel = '%s/figures_%s/%s' % (version, version, name)
            if name in eyes_bad:
                bad.append(dict(fig, fid=fid, reason='вырезка забракована при просмотре глазами'))
                continue
            item = ds.manifest[fig['page_ref']]
            if any(_same_figure(old, item, fig['bbox']) for old in existing.get(key, [])):
                bad.append(dict(fig, fid=fid, reason='такой рисунок уже есть в эталоне'))
                continue
            size = crop_figure(ds.png(fig['page_ref']), fig['bbox'], os.path.join(ds.digitized, rel))
            if size is None:
                bad.append(dict(fig, fid=fid, reason='вырезка не удалась'))
                continue
            item = ds.manifest[fig['page_ref']]
            entries.append({'key': key, 'field': 'figure',
                            'target': 'figures' if group == 'statement' else 'solution_figures',
                            'value': {'path': rel, 'caption': fig.get('caption', ''), 'flag': 'claude',
                                      'page': item['page'], 'page_dir': item['page_dir'],
                                      'bbox_norm': fig['bbox'], 'size': list(size),
                                      'model': fig.get('model', '')},
                            'unit': fig.get('unit', ''), 'model': fig.get('model', '')})
    return entries, bad


def text_layer(resolved):
    """Принятые правки полей → записи слоя (по одной на поле; при нескольких
    правках одного поля — последняя, т. е. старшей модели)."""
    entries = {}
    for fid, accs in sorted(resolved['fixes'].items()):
        key, group = fid.split('#')
        for acc in accs:
            entries[(key, acc['field'])] = {'key': key, 'group': group, 'field': acc['field'],
                                            'value': acc['value'], 'old_sha1': acc['old_sha1'],
                                            'unit': acc['unit'], 'model': acc['model']}
    return list(entries.values())


def build_version(ds, resolved, audited_units, out_dir=None, answers=()):
    """База (v6 / v2) + хвосты v6 + слой правок Claude → новая версия.

    Пишет в `<digitized>/<vN>/`: reference_problems_<vN>.jsonl, claude_<vN>.json
    (слой), <vIn>_to_<vN>_keys.csv, changes_<vN>.md (счётчики и примеры). Входной
    файл не трогается. Возвращает сводку и инварианты."""
    version, base = ds.out_version, ds.in_version
    out_dir = out_dir or os.path.join(ds.digitized, version)
    texts = text_layer(resolved)
    claude_statement = {e['key'] for e in texts if e['field'] in ('statement_md', 'title')}
    rows, tail_log, removed = tail_rules_econ([dict(r) for r in ds.rows], ds.name, claude_statement)
    # Правки Claude к заданию, которое правило хвоста убрало или чьё поле оно
    # уже переписало, не применяются (уходят в журнал хвостов).
    base_by_key = {task_key(r): r for r in ds.rows}
    after_by_key = {task_key(r): r for r in rows}
    kept = []
    for e in texts:
        after = after_by_key.get(e['key'])
        if after is None or after.get(e['field']) != base_by_key[e['key']].get(e['field']):
            tail_log.append((e['key'], e['field'], 'правка Claude уступила правилу хвоста v6'))
            continue
        kept.append(e)
    texts = kept
    taken = {(e['key'], e['field']) for e in texts}
    texts += [a for a in answers if (a['key'], a['field']) not in taken]
    figs, bad_figs = figure_layer(ds, resolved)
    new_rows, log = apply_layer(rows, texts + figs)
    for row in new_rows:
        changed = sorted({f for k, f, s in log if k == task_key(row) and s == 'applied'})
        if changed:
            row['claude_audit'] = {'version': version, 'fields': changed}
    path = os.path.join(out_dir, 'reference_problems_%s.jsonl' % version)
    if os.path.abspath(path) == os.path.abspath(os.path.join(ds.digitized, SETS[ds.name][2])):
        raise ValueError('выход совпал со входом — отказ')
    write_jsonl(path, new_rows)
    with open(os.path.join(out_dir, 'claude_%s.json' % version), 'w', encoding='utf-8', newline='\n') as h:
        json.dump({'set': ds.name, 'base': base, 'version': version,
                   'fixes': texts, 'figures': figs, 'tail_rules': tail_log}, h, ensure_ascii=False, indent=1)
    # Ключи
    new_keys = {task_key(r) for r in new_rows}
    key_rows = []
    for row in ds.rows:
        k = task_key(row)
        if k in new_keys:
            key_rows.append([k, k, 'тот же'])
        else:
            key_rows.append([k, '', removed.get(k, 'НЕТ ПРИЧИНЫ')])
    write_csv(os.path.join(out_dir, '%s_to_%s_keys.csv' % (base, version)),
              ['%s_key' % base, '%s_key' % version, 'судьба'], key_rows)
    # Инварианты
    keys = [task_key(r) for r in new_rows]
    applied = [x for x in log if x[2] == 'applied']
    math = [s for r in new_rows for f in ('statement_md', 'solution_md', 'answer', 'criteria_md', 'title')
            for s in math_segments(r.get(f) or '')]
    math += [s for r in new_rows for p in (r.get('parts') or []) if isinstance(p, dict)
             for s in math_segments(p.get('text') or '')]
    base_math = [s for r in ds.rows for f in ('statement_md', 'solution_md', 'answer', 'criteria_md', 'title')
                 for s in math_segments(r.get(f) or '')]
    base_math += [s for r in ds.rows for p in (r.get('parts') or []) if isinstance(p, dict)
                  for s in math_segments(p.get('text') or '')]
    new_err = sum(1 for e in katex_errors(math) if e)
    base_err = sum(1 for e in katex_errors(base_math) if e)
    inv = {
        'tasks_in': len(ds.rows), 'tasks_out': len(new_rows),
        'lost_without_reason': sum(1 for r in key_rows if r[2] == 'НЕТ ПРИЧИНЫ'),
        'duplicate_keys': len(keys) - len(set(keys)),
        'katex_errors_out': new_err, 'katex_errors_in': base_err,
        'katex_errors_new': max(0, new_err - base_err),
        'layer_entries': len(texts) + len(figs), 'layer_applied': len(applied),
        'layer_not_applied': [x for x in log if x[2] != 'applied'],
        'units_audited': audited_units,
    }
    inv['ok'] = (inv['lost_without_reason'] == 0 and inv['duplicate_keys'] == 0
                 and inv['katex_errors_new'] == 0 and not inv['layer_not_applied'])
    with open(os.path.join(out_dir, 'invariants_%s.json' % version), 'w', encoding='utf-8', newline='\n') as h:
        json.dump(inv, h, ensure_ascii=False, indent=1)
    return {'rows': new_rows, 'texts': texts, 'figures': figs, 'bad_figures': bad_figs,
            'tail_log': tail_log, 'removed': removed, 'log': log, 'invariants': inv, 'path': path}


def defect_counts(resolved):
    found, fixed = collections.Counter(), collections.Counter()
    fixed_fids = set(resolved['fixes'])
    for fid, v in resolved['final'].items():
        for d in v.get('defects') or []:
            if isinstance(d, dict):
                cls = d.get('class') if d.get('class') in DEFECT_CLASSES else 'other'
                found[cls] += 1
                if fid in fixed_fids:
                    fixed[cls] += 1
    return found, fixed


def changes_md(ds, result, resolved, title):
    found, fixed = defect_counts(resolved)
    inv = result['invariants']
    lines = ['# %s' % title, '',
             'База: `%s`, версия `%s`. Единиц аудита с ответом: %d. Фрагментов с вердиктом: %d '
             '(needs_fix: %d).' % (ds.in_version, ds.out_version, inv['units_audited'],
                                   len(resolved['final']),
                                   sum(1 for v in resolved['final'].values() if v.get('verdict') == 'needs_fix')),
             '', '## Дефекты по классам', '', '| класс | найдено | исправлено |', '|---|---|---|']
    for cls in DEFECT_CLASSES:
        if found[cls]:
            lines.append('| %s | %d | %d |' % (cls, found[cls], fixed[cls]))
    lines += ['', 'Правок полей применено: %d; новых рисунков: %d; правил хвостов v6: %d.' % (
        len(result['texts']), len(result['figures']), len(result['tail_log'])), '',
        '## Инварианты', '', '```', json.dumps({k: v for k, v in inv.items() if k != 'layer_not_applied'},
                                                ensure_ascii=False, indent=1), '```', '']
    if result['tail_log']:
        lines += ['## Хвосты v6', '']
        lines += ['- `%s` — %s: %s' % x for x in result['tail_log']]
        lines.append('')
    lines += ['## Примеры правок', '']
    base = {task_key(r): r for r in ds.rows}
    for entry in result['texts'][:15]:
        old = base[entry['key']].get(entry['field'])
        lines += ['### `%s` · %s (%s)' % (entry['key'], entry['field'], entry['model']), '',
                  'Было:', '', '```', field_text(old)[:800], '```', '', 'Стало:', '', '```',
                  field_text(entry['value'])[:800], '```', '']
    with open(os.path.join(os.path.dirname(result['path']), 'changes_%s.md' % ds.out_version),
              'w', encoding='utf-8', newline='\n') as h:
        h.write('\n'.join(lines))


def morning_items(ds, resolved, result, units):
    """Нерешённое для владельца: отказы проверок, низкая уверенность, правки
    без второго мнения, плохие рамки, неразобранные ответы, «лишнее» на странице."""
    items = []
    unit_of = {f['fid']: uid for uid, u in units.items() for f in u['fragments']}
    for fid, rejs in sorted(resolved['rejected'].items()):
        for rej in rejs:
            items.append({'kind': 'правка не принята', 'fid': fid, 'unit': rej.get('unit') or unit_of.get(fid),
                          'why': '; '.join(rej.get('reasons') or []), 'field': rej.get('field', ''),
                          'text': field_text(rej.get('value'))[:3000], 'model': rej.get('model', '')})
    for fid, v in sorted(resolved['final'].items()):
        if v.get('verdict') == 'needs_fix' and fid not in resolved['fixes'] and fid not in resolved['rejected']:
            items.append({'kind': 'дефект без правки', 'fid': fid, 'unit': v['unit'],
                          'why': '; '.join('%s: %s' % (d.get('class'), d.get('what')) for d in v['defects']
                                           if isinstance(d, dict))[:600],
                          'field': '', 'text': '', 'model': v['model']})
    for fig in result['bad_figures']:
        items.append({'kind': 'рисунок не вырезан', 'fid': fig['fid'], 'unit': fig.get('unit'),
                      'why': fig.get('reason', ''), 'field': 'figure', 'text': fig.get('caption', ''),
                      'model': fig.get('model', '')})
    for unit, model, err in resolved['parse_errors']:
        items.append({'kind': 'ответ не разобран', 'fid': '', 'unit': unit, 'why': err, 'field': '',
                      'text': '', 'model': model})
    for item in resolved['unlisted']:
        items.append({'kind': 'на странице есть, в эталоне нет', 'fid': '', 'unit': item.get('unit'),
                      'why': str(item.get('what', ''))[:400], 'field': '',
                      'text': str(item.get('evidence', ''))[:1500], 'model': item.get('model', '')})
    for item in items:
        unit = units.get(item['unit'])
        item['set'] = ds.name
        item['pngs'] = [os.path.abspath(ds.png(ref)) for ref in unit['pages']] if unit else []
    return items


def review_html(items, out_path, title):
    """Страница для владельца: картинка страницы рядом с текстом, только нерешённое."""
    import html
    css = ('body{font:14px/1.45 system-ui,sans-serif;margin:16px;background:#f6f6f4}'
           '.c{display:flex;gap:12px;background:#fff;border:1px solid #ddd;margin:10px 0;padding:10px}'
           '.c img{width:520px;border:1px solid #ccc}.t{flex:1;min-width:0}'
           'pre{white-space:pre-wrap;background:#fafafa;border:1px solid #eee;padding:6px;max-height:420px;overflow:auto}'
           '.k{font-weight:600;color:#a33}')
    out = ['<!doctype html><meta charset="utf-8"><title>%s</title><style>%s</style>' % (html.escape(title), css),
           '<h1>%s</h1><p>Всего пунктов: %d. Только нерешённое: отказы проверок, низкая уверенность, '
           'правки без второго мнения, плохие вырезки, неразобранные ответы.</p>' % (html.escape(title), len(items))]
    counts = collections.Counter(i['kind'] for i in items)
    out.append('<ul>%s</ul>' % ''.join('<li>%s — %d</li>' % (html.escape(k), n) for k, n in counts.most_common()))
    for n, item in enumerate(items, 1):
        imgs = ''.join('<img src="file:///%s" loading="lazy">' % p.replace('\\', '/') for p in item['pngs'][:2])
        out.append('<div class="c"><div>%s</div><div class="t"><div class="k">%d. %s</div>'
                   '<div>%s · <code>%s</code> · %s · %s</div><p>%s</p>%s</div></div>' % (
                       imgs, n, html.escape(item['kind']), html.escape(item['set']),
                       html.escape(item['fid'] or item['unit'] or ''), html.escape(item['field']),
                       html.escape(item['model']), html.escape(item['why']),
                       ('<pre>%s</pre>' % html.escape(item['text'])) if item['text'] else ''))
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    with open(out_path, 'w', encoding='utf-8', newline='\n') as h:
        h.write('\n'.join(out))
    return out_path
