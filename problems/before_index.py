"""Индекс «версия ДО» — текст задачи до ПЕРВОЙ применённой к ней правки.

⚠️ ЧИТАЕТ ТОЛЬКО ФАЙЛЫ ИСТОРИИ. В базу не ходит и ничего не пишет.

Зачем отдельный модуль: «до» лежит в пяти разных семействах файлов, у каждого
свой формат и своя дата. Собирать это заново в каждой команде значит
гарантированно разъехаться: один соберёт «до» от июля, другой от июня, и два
отчёта об одной задаче будут спорить друг с другом.

ПРАВИЛО ВЫБОРА: побеждает САМЫЙ РАННИЙ снимок. Источники перебираются по дате
от старых к новым, и поле, уже записанное более старым источником, новым НЕ
перезаписывается. Задача могла правиться несколькими патчами подряд; нужно
состояние до первого из них, а не до последнего.

⚠️ ЧЕГО НЕТ, ТОГО НЕТ. Источник, которого нет на диске, молча пропускается, а
поле без снимка остаётся отсутствующим — вызывающий обязан показать «версия ДО
не найдена», а НЕ подставлять текущий текст базы. Подстановка текущего текста
превратила бы столбец «до» в копию столбца «после», и разбор потерял бы смысл.

⚠️ `batch2_parsed.jsonl` (снимки Батча 2 от 2026-07-04) в переданной копии
проекта ОТСУТСТВУЕТ, полного бэкапа базы от той даты тоже нет. Правки Батча 2
у задач, не попавших в более поздние бэкапы, поэтому к «до» не откатываются —
это дыра покрытия, а не ошибка индекса.
"""

import glob
import json
import os

# Источники по возрастанию даты. Каждый: (ключ, подпись, дата, маска, вид).
#   вид 'list_id'  — список записей с полем id (ILE);
#   вид 'sections' — словарь разделов {раздел: {ключ: текст}}.
SOURCES = [
    ('ile_raw', 'снимок «БЫЛО» до ИИ-чистки ILE', '2026-06',
     'reports/ai_cleanup_ile/*_raw.json', 'list_id'),
    ('ile_backup', 'бэкап перед патчем ИИ-чистки ILE', '2026-06',
     'reports/ai_cleanup_ile/backup_before_apply_*.json', 'list_id'),
    ('glue_lines', 'бэкап перед склейкой строк', '2026-07-19',
     'reports/glue_lines/backup_apply_20260719.json', 'sections'),
    ('batch2_unblock', 'бэкап перед разблокировкой Батча 2', '2026-07-19',
     'reports/batch2_unblock/backup_apply_20260719.json', 'sections'),
    ('batch2_sweep', 'бэкап перед откатом свипа Батча 2', '2026-07-21',
     'reports/batch2_sweep/backup_revert_*.json', 'sections'),
]

SOURCE_LABEL = {key: label for key, label, _d, _p, _k in SOURCES}
SOURCE_DATE = {key: date for key, _l, date, _p, _k in SOURCES}

# Как называется раздел в разных бэкапах. Слева — имя в файле, справа — что это.
SECTION_MAP = {
    'problems': ('problem', 'statement'),
    'statement': ('problem', 'statement'),
    'solution': ('problem', 'solution'),
    'answer': ('problem', 'answer'),
    'parts': ('part', 'statement'),
    'part': ('part', 'statement'),
}

PROBLEM_FIELDS = ('statement', 'solution', 'answer')


def _blank():
    return {'problem': {}, 'part': {}, 'origin': {}}


def _put(idx, scope, key, field, value, source_key):
    """Записать поле, если его ещё не записал более ранний источник."""
    if value is None:
        return
    try:
        key = int(key)
    except (TypeError, ValueError):
        return
    slot = idx[scope].setdefault(key, {})
    if field in slot:
        return                      # более ранний источник уже сказал своё
    slot[field] = value
    idx['origin'].setdefault((scope, key), {})[field] = source_key


def _load_list_id(idx, path, source_key):
    try:
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return
    if isinstance(data, dict):      # старый формат pilot_apply_v1: {tasks: [...]}
        data = data.get('tasks') or []
    if not isinstance(data, list):
        return
    for rec in data:
        if not isinstance(rec, dict) or 'id' not in rec:
            continue
        for field in PROBLEM_FIELDS:
            if field in rec:
                _put(idx, 'problem', rec['id'], field, rec[field], source_key)
        parts = rec.get('parts')
        if isinstance(parts, list):
            for part in parts:
                if not isinstance(part, dict):
                    continue
                pk = part.get('pk', part.get('id'))
                if pk is None:
                    continue
                _put(idx, 'part', pk, 'statement', part.get('statement'),
                     source_key)
                if 'answer' in part:
                    _put(idx, 'part', pk, 'answer', part.get('answer'),
                         source_key)


def _load_sections(idx, path, source_key):
    try:
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return
    if not isinstance(data, dict):
        return
    for section, payload in data.items():
        if section not in SECTION_MAP or not isinstance(payload, dict):
            continue
        scope, field = SECTION_MAP[section]
        for key, value in payload.items():
            _put(idx, scope, key, field, value, source_key)


def build_index():
    """Собрать индекс «до» из всех доступных источников.

    Возвращает словарь:
      {'problem': {pid: {поле: текст}},
       'part':    {part_pk: {поле: текст}},
       'origin':  {(вид, ключ): {поле: ключ источника}},
       'sources': [{'key','label','date','files'}]}
    """
    idx = _blank()
    used = []
    for key, label, date, pattern, kind in SOURCES:
        files = sorted(glob.glob(pattern))
        if not files:
            continue
        for path in files:
            if kind == 'list_id':
                _load_list_id(idx, path, key)
            else:
                _load_sections(idx, path, key)
        used.append({'key': key, 'label': label, 'date': date,
                     'files': [os.path.basename(f) for f in files]})
    idx['sources'] = used
    return idx


def before_for(idx, problem, parts):
    """Состояние «до» для одной задачи.

    `problem` — объект Problem, `parts` — список ProblemPart.
    Возвращает словарь полей плюс признак `found` и список ключей источников.
    """
    got = idx['problem'].get(problem.id, {})
    sources = set(idx['origin'].get(('problem', problem.id), {}).values())

    out_parts = []
    for part in parts:
        rec = idx['part'].get(part.pk)
        if not rec:
            continue
        out_parts.append({
            'pk': part.pk,
            'label': getattr(part, 'label', '') or '',
            'statement': rec.get('statement'),
            'answer': rec.get('answer'),
        })
        sources.update(idx['origin'].get(('part', part.pk), {}).values())

    out = {
        'statement': got.get('statement'),
        'solution': got.get('solution'),
        'answer': got.get('answer'),
        'parts': out_parts,
        'sources': sorted(sources),
    }
    out['found'] = (any(out[f] is not None for f in PROBLEM_FIELDS)
                    or bool(out_parts))
    return out
