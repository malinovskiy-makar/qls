"""Синхронизация банка дом → бой обновлением, а не перезаписью (ADR 0107).

`bulk_load_fixtures` только вставляет новые строки (`ignore_conflicts=True`),
поэтому правки в уже существующих на бою задачах туда не доезжают. Здесь —
общий движок двух команд:

* `bank_sync_export` (дома) пишет пакет: `manifest.json`, `refs.json`
  (справочники целиком) и `problems.jsonl` (задача на строку: поля из белого
  списка, связи и дочерние строки по естественным ключам);
* `bank_sync_apply` (на бою) сверяет пакет с базой и меняет ТОЛЬКО
  отличающееся. Задачи, которых в базе нет, не создаёт (это работа переноса
  корпуса); задачи базы вне пакета не трогает.

Связи M2M и дочерние таблицы идут одним механизмом: у каждой строки есть
естественный ключ внутри задачи (порядок подпункта, источник, id тура…), и
множество строк на бою становится равным множеству из пакета.

Снимок хранит старое И новое значение каждой правки. Откат возвращает старое
только там, где сейчас лежит записанное синхронизацией: правку, сделанную
после неё кем-то другим, он не затирает, а называет в отчёте.
"""
import base64
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from django.db import transaction
from django.db.models import QuerySet
from django.db.models.deletion import Collector

from problems.models import (EconConcept, Feature, Hint, OlympiadRef, Problem,
                             ProblemFeature, ProblemFigure, ProblemPart, Source,
                             SourceReference, Tag, Topic)

FORMAT = 1
#: id за один запрос: SQLite падает на десятках тысяч переменных.
CHUNK = 500

#: Белый список полей задачи (утверждён владельцем 17.09.2026). Не везём:
#: владельца, векторы, «похожие», файлы, даты, рубрики, пометки копий.
PROBLEM_FIELDS = (
    # тексты
    'title', 'title_candidate', 'title_source', 'statement', 'answer',
    'solution', 'given', 'find', 'plot', 'difficulty_note',
    'text_quality_note', 'ai_blurb', 'content_format', 'content_hash',
    # обогащение
    'problem_type', 'difficulty', 'difficulty_native', 'answer_consistency',
    'character', 'features', 'task_nature', 'text_quality',
    'topic_confidence', 'search_queries', 'concepts_offlist',
    'enrichment_source', 'enrichment_at', 'multiple_problems',
    'solution_ai_extracted',
    # видимость — дом источник истины и здесь (решение владельца 17.09)
    'status', 'needs_quality_review', 'solution_needs_review', 'human_review',
    'content_status', 'hidden_pending_review',
)


@dataclass(frozen=True)
class Ref:
    """Справочник: обновляется по естественному ключу, не удаляется."""
    name: str
    model: type
    key: str
    fields: tuple


@dataclass(frozen=True)
class Child:
    """Строки, принадлежащие задаче. `key` — чем строка отличается от соседей
    внутри задачи; `ref` — справочник, если ключ ссылается на него; `part` —
    у строки есть ссылка на подпункт (переносится по его `order`)."""
    name: str
    model: type
    key: str
    ref: str = ''
    fields: tuple = ()
    part: bool = False


REFS = {ref.name: ref for ref in (
    Ref('topic', Topic, 'slug', ('name', 'description', 'order', 'is_canonical')),
    Ref('tag', Tag, 'name', ('slug', 'kind')),
    Ref('econ_concept', EconConcept, 'canonical', ('section',)),
    Ref('feature', Feature, 'key', ('label', 'counted_by', 'order')),
    # Источник — по id, а не по имени: имена переименовываются (17.09), а id
    # дома и на бою совпадают (сверка на копии боя: 27 из 27).
    Ref('source', Source, 'id', ('name', 'author', 'year', 'kind', 'note')),
)}


def _through(name):
    return Problem._meta.get_field(name).remote_field.through


#: Порядок важен: подпункты первыми — на них ссылаются подсказки и рисунки.
CHILDREN = (
    Child('parts', ProblemPart, 'order',
          fields=('label', 'statement', 'answer', 'solution', 'points')),
    Child('topics', _through('topics'), 'topic_id', 'topic'),
    Child('tags', _through('tags'), 'tag_id', 'tag'),
    Child('econ_concepts', _through('econ_concepts'), 'econconcept_id', 'econ_concept'),
    Child('features_rel', ProblemFeature, 'feature_id', 'feature', ('source',)),
    Child('source_references', SourceReference, 'source_id', 'source',
          ('stage', 'year', 'grade', 'problem_number', 'page', 'url', 'note')),
    Child('olympiad_refs', OlympiadRef, 'event_id',
          fields=('source_site', 'olympiad_slug', 'olympiad_name', 'academic_year',
                  'year', 'stage', 'grade', 'variant', 'number', 'record_id',
                  'match_method', 'match_score', 'official_url', 'raw_meta',
                  'reviewed_by_human', 'quality_score', 'is_best_in_cluster')),
    Child('hints', Hint, 'order', fields=('text', 'generated_by_ai', 'reviewed'),
          part=True),
    Child('figures', ProblemFigure, 'tikz_hash',
          fields=('source_field', 'tikz_source', 'svg', 'image_data', 'content_type'),
          part=True),
)
CHILD_BY_NAME = {child.name: child for child in CHILDREN}
ALL_FIELDS = PROBLEM_FIELDS + tuple(CHILD_BY_NAME)


# ── Значения ─────────────────────────────────────────────────────────────
def dump(field, value):
    """Значение поля → JSON. Одинаково на SQLite и PostgreSQL: по этому
    виду значения и сравниваются."""
    if value is None:
        return None
    kind = field.get_internal_type()
    if kind == 'BinaryField':
        return base64.b64encode(bytes(value)).decode('ascii')
    if kind == 'DateTimeField':
        # До миллисекунд, как фикстуры Django: бой заливался ими, и дата с
        # микросекундами дома иначе «отличалась» бы у 8 981 задачи без смысла.
        return value.isoformat(timespec='milliseconds')
    if kind == 'DecimalField':
        return str(Decimal(value).quantize(Decimal(1).scaleb(-field.decimal_places)))
    return value


def load(field, raw):
    """JSON → значение поля (обратное `dump`)."""
    if raw is None:
        return None
    kind = field.get_internal_type()
    if kind == 'BinaryField':
        return base64.b64decode(raw)
    if kind == 'DateTimeField':
        return datetime.fromisoformat(raw)
    if kind == 'DecimalField':
        return Decimal(raw)
    return raw


def _field(model, name):
    return model._meta.get_field(name)


def chunks(items, size=CHUNK):
    items = list(items)
    for start in range(0, len(items), size):
        yield items[start:start + size]


def parse_fields(text):
    """«title,tags» → список имён; пусто — весь белый список."""
    names = [name.strip() for name in (text or '').split(',') if name.strip()]
    unknown = [name for name in names if name not in ALL_FIELDS]
    if unknown:
        raise ValueError('Неизвестные поля: %s' % ', '.join(unknown))
    return [name for name in ALL_FIELDS if name in names] if names else list(ALL_FIELDS)


def ref_maps():
    """{справочник: {pk: естественный ключ}} текущей базы."""
    return {ref.name: dict(ref.model.objects.values_list('pk', ref.key))
            for ref in REFS.values()}


# ── Чтение состояния задач ───────────────────────────────────────────────
def _items(child, rows, maps, part_order):
    """Строки таблицы `child` → {pk: {'problem', 'key', поля…}}."""
    out = {}
    key_field = None if child.ref else _field(child.model, child.key)
    for row in rows:
        key = maps[child.ref].get(row[child.key]) if child.ref else dump(key_field, row[child.key])
        item = {'problem': row['problem_id'], 'key': key}
        for name in child.fields:
            item[name] = dump(_field(child.model, name), row[name])
        if child.part:
            item['part'] = part_order.get(row['part_id']) if row['part_id'] else None
        out[row['pk']] = item
    return out


def _columns(child):
    return ['pk', 'problem_id', child.key, *child.fields] + (['part_id'] if child.part else [])


def _part_order(part_ids):
    order = {}
    for chunk in chunks(part_ids):
        order.update(ProblemPart.objects.filter(pk__in=chunk).values_list('pk', 'order'))
    return order


def collect(ids, names, maps):
    """Задачи `ids` в форме строки пакета, кусками по CHUNK, по возрастанию id.

    Строки дочерних таблиц несут ещё и `pk` — по нему пишет apply; в пакет
    `pk` не попадает (`package_line`)."""
    pfields = [name for name in names if name in PROBLEM_FIELDS]
    children = [child for child in CHILDREN if child.name in names]
    for chunk in chunks(sorted(ids)):
        data = {}
        for row in Problem.objects.filter(id__in=chunk).values('id', *pfields):
            data[row['id']] = {'id': row['id'],
                               'fields': {f: dump(_field(Problem, f), row[f]) for f in pfields},
                               **{child.name: [] for child in children}}
        for child in children:
            rows = list(child.model.objects.filter(problem_id__in=chunk).values(*_columns(child)))
            part_order = _part_order({r['part_id'] for r in rows if r['part_id']}) if child.part else {}
            for pk, item in _items(child, rows, maps, part_order).items():
                if item['problem'] in data:
                    data[item['problem']][child.name].append(dict(item, pk=pk))
        for pid in sorted(data):
            for child in children:
                data[pid][child.name].sort(key=lambda item: item['key'])
            yield data[pid]


def package_line(entry):
    """Строка пакета: без pk и без повтора номера задачи в дочерних строках."""
    line = {'id': entry['id'], 'fields': entry['fields']}
    for child in CHILDREN:
        if child.name in entry:
            line[child.name] = [{k: v for k, v in item.items() if k not in ('pk', 'problem')}
                                for item in entry[child.name]]
    return line


# ── Экспорт ──────────────────────────────────────────────────────────────
def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def used_refs(names):
    return sorted({CHILD_BY_NAME[name].ref for name in names
                   if name in CHILD_BY_NAME and CHILD_BY_NAME[name].ref})


def export(ids, names, out, scope='', head=''):
    """Пишет пакет в `out` (каталог создаётся, существующий — ошибка)."""
    out = Path(out)
    out.mkdir(parents=True)
    maps = ref_maps()
    count = 0
    with (out / 'problems.jsonl').open('w', encoding='utf-8', newline='\n') as fh:
        for entry in collect(ids, names, maps):
            fh.write(json.dumps(package_line(entry), ensure_ascii=False, sort_keys=True) + '\n')
            count += 1
    refs = {}
    for name in used_refs(names):
        ref = REFS[name]
        refs[name] = [dict({'key': dump(_field(ref.model, ref.key), getattr(obj, ref.key))},
                           **{f: dump(_field(ref.model, f), getattr(obj, f)) for f in ref.fields})
                      for obj in ref.model.objects.order_by(ref.key)]
    (out / 'refs.json').write_text(json.dumps(refs, ensure_ascii=False, indent=1),
                                   encoding='utf-8')
    manifest = {
        'format': FORMAT, 'created_at': datetime.now().astimezone().isoformat(),
        'git_head': head, 'scope': scope, 'fields': names, 'problems': count,
        'refs': {name: len(rows) for name, rows in refs.items()},
        'files': {name: _sha256(out / name) for name in ('problems.jsonl', 'refs.json')},
    }
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                                       encoding='utf-8')
    return manifest


def read_manifest(package):
    package = Path(package)
    manifest = json.loads((package / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('format') != FORMAT:
        raise ValueError('Формат пакета %s, команда понимает %s' % (manifest.get('format'), FORMAT))
    for name, digest in manifest['files'].items():
        if _sha256(package / name) != digest:
            raise ValueError('Файл пакета %s повреждён: хеш не совпал с manifest.json' % name)
    return manifest


def _package_chunks(package):
    batch = []
    with (Path(package) / 'problems.jsonl').open(encoding='utf-8') as fh:
        for raw in fh:
            if raw.strip():
                batch.append(json.loads(raw))
            if len(batch) == CHUNK:
                yield batch
                batch = []
    if batch:
        yield batch


# ── План ─────────────────────────────────────────────────────────────────
def _diff(old, new, names):
    changed = [name for name in names if old.get(name) != new.get(name)]
    return {n: old.get(n) for n in changed}, {n: new.get(n) for n in changed}


def _part_dependents(pks):
    """{pk подпункта: [таблицы, которые на него ссылаются]} — такие не удаляем."""
    found = {}
    for rel in ProblemPart._meta.related_objects:
        column = rel.field.name + '_id'
        for chunk in chunks(pks):
            for pk in rel.related_model.objects.filter(**{column + '__in': chunk}) \
                    .values_list(column, flat=True).distinct():
                found.setdefault(pk, []).append(rel.related_model._meta.label)
    return found


def plan(package, names):
    """Что изменится в текущей базе. Только чтение."""
    refs_pkg = json.loads((Path(package) / 'refs.json').read_text(encoding='utf-8'))
    result = {'refs': {}, 'problems': [], 'missing': [], 'skipped': [],
              'children': {child.name: {'create': [], 'update': [], 'delete': [], 'kept': []}
                           for child in CHILDREN if child.name in names}}
    creatable = {}
    for name in used_refs(names):
        ref = REFS[name]
        db = {dump(_field(ref.model, ref.key), getattr(obj, ref.key)): obj
              for obj in ref.model.objects.all()}
        ops = {'create': [], 'update': []}
        for row in refs_pkg.get(name, []):
            new = {f: row[f] for f in ref.fields}
            obj = db.get(row['key'])
            if obj is None:
                if ref.key == 'id':
                    result['skipped'].append((name, row['key'], 'справочника с таким id в базе нет'))
                else:
                    ops['create'].append({'key': row['key'], 'row': new})
                continue
            old = {f: dump(_field(ref.model, f), getattr(obj, f)) for f in ref.fields}
            before, after = _diff(old, new, ref.fields)
            if after:
                ops['update'].append({'pk': obj.pk, 'key': row['key'], 'old': before, 'new': after})
        result['refs'][name] = ops
        creatable[name] = set(db) | {c['key'] for c in ops['create']}

    pfields = [name for name in names if name in PROBLEM_FIELDS]
    children = [child for child in CHILDREN if child.name in names]
    maps = ref_maps()
    for batch in _package_chunks(package):
        current = {entry['id']: entry for entry in collect([b['id'] for b in batch], names, maps)}
        doomed_parts = []
        for line in batch:
            pid = line['id']
            if pid not in current:
                result['missing'].append(pid)
                continue
            cur = current[pid]
            before, after = _diff(cur['fields'], line['fields'], pfields)
            if after:
                result['problems'].append({'id': pid, 'old': before, 'new': after})
            for child in children:
                if child.name not in line:
                    # Таблицы нет в строке пакета — это «не везли», а не
                    # «пусто»: иначе все её строки на бою ушли бы в удаление.
                    continue
                ops = result['children'][child.name]
                have = {item['key']: item for item in cur[child.name]}
                want = {item['key']: item for item in line.get(child.name, [])}
                columns = list(child.fields) + (['part'] if child.part else [])
                for key, item in want.items():
                    row = {c: item.get(c) for c in columns}
                    if key not in have:
                        if child.ref and key not in creatable.get(child.ref, ()):
                            result['skipped'].append((child.name, pid, 'нет в справочнике: %s' % key))
                        else:
                            ops['create'].append({'problem': pid, 'key': key, 'row': row})
                        continue
                    old, new = _diff(have[key], row, columns)
                    if new:
                        ops['update'].append({'pk': have[key]['pk'], 'problem': pid, 'key': key,
                                              'old': old, 'new': new})
                for key, item in have.items():
                    if key not in want:
                        gone = {'pk': item['pk'], 'problem': pid, 'key': key,
                                'row': {c: item.get(c) for c in columns}}
                        ops['delete'].append(gone)
                        if child.name == 'parts':
                            doomed_parts.append(gone)
        if doomed_parts:
            refs = _part_dependents([p['pk'] for p in doomed_parts])
            ops = result['children']['parts']
            for gone in doomed_parts:
                if gone['pk'] in refs:
                    ops['delete'].remove(gone)
                    ops['kept'].append(dict(gone, reason='на подпункт ссылаются: '
                                                         + ', '.join(sorted(set(refs[gone['pk']])))))
    return result


def is_empty(result):
    return not (result['problems']
                or any(ops['create'] or ops['update'] for ops in result['refs'].values())
                or any(ops['create'] or ops['update'] or ops['delete']
                       for ops in result['children'].values()))


def changed_ids(result):
    ids = {p['id'] for p in result['problems']}
    for ops in result['children'].values():
        for kind in ('create', 'update', 'delete'):
            ids.update(item['problem'] for item in ops[kind])
    return sorted(ids)


# ── Запись ───────────────────────────────────────────────────────────────
def _key_pk(maps):
    return {name: {key: pk for pk, key in mapping.items()} for name, mapping in maps.items()}


def _part_pks(problem_ids):
    found = {}
    for chunk in chunks(sorted(set(problem_ids))):
        for pk, pid, order in ProblemPart.objects.filter(problem_id__in=chunk) \
                .values_list('pk', 'problem_id', 'order'):
            found[(pid, order)] = pk
    return found


def _where(item):
    return '#%s [%s]' % (item['problem'], item['key'])


def _set_row(obj, child, row, parts, skipped):
    """Записать значения `row` (JSON) в объект; False — подпункт не найден.

    Подпункт проверяется ДО остальных полей: иначе объект остался бы
    записанным наполовину."""
    raw_part = row.get('part')
    part = parts.get((obj.problem_id, raw_part)) if raw_part is not None else None
    if raw_part is not None and part is None:
        skipped.append((child.name, '#%s' % obj.problem_id, 'нет подпункта с order=%s' % raw_part))
        return False
    for name, raw in row.items():
        if name == 'part':
            obj.part_id = part
        else:
            setattr(obj, name, load(_field(child.model, name), raw))
    return True


def _new_child(child, item, keys, parts, skipped, pk=None):
    if child.ref and item['key'] not in keys[child.ref]:
        skipped.append((child.name, _where(item), 'нет в справочнике'))
        return None
    key = keys[child.ref][item['key']] if child.ref else load(_field(child.model, child.key), item['key'])
    obj = child.model(problem_id=item['problem'], **{child.key: key})
    if pk is not None:
        obj.pk = pk
    return obj if _set_row(obj, child, item['row'], parts, skipped) else None


def execute(result, names, package, snapshot_path):
    """Записывает план одной транзакцией и кладёт снимок. Снимок пишется
    ВНУТРИ транзакции: не записался — не записалось и остальное."""
    skipped = result['skipped']
    with transaction.atomic():
        for name, ops in result['refs'].items():
            ref = REFS[name]
            for upd in ops['update']:
                obj = ref.model.objects.get(pk=upd['pk'])
                for f, raw in upd['new'].items():
                    setattr(obj, f, load(_field(ref.model, f), raw))
                obj.save(update_fields=list(upd['new']))
            for new in ops['create']:
                obj = ref.model(**{ref.key: new['key']},
                                **{f: load(_field(ref.model, f), raw) for f, raw in new['row'].items()})
                obj.save()
                new['pk'] = obj.pk

        for batch in chunks(result['problems']):
            fields = sorted({f for item in batch for f in item['new']})
            objs = Problem.objects.only(*fields).in_bulk([item['id'] for item in batch])
            for item in batch:
                for f, raw in item['new'].items():
                    setattr(objs[item['id']], f, load(_field(Problem, f), raw))
            Problem.objects.bulk_update(objs.values(), fields)

        keys = _key_pk(ref_maps())
        for child in CHILDREN:
            if child.name not in result['children']:
                continue
            ops = result['children'][child.name]
            for batch in chunks([item['pk'] for item in ops['delete']]):
                child.model.objects.filter(pk__in=batch).delete()
            parts = _part_pks([i['problem'] for kind in ('update', 'create')
                               for i in ops[kind]]) if child.part else {}
            for batch in chunks(ops['update']):
                objs = child.model.objects.in_bulk([item['pk'] for item in batch])
                fields = set()
                for item in batch:
                    if _set_row(objs[item['pk']], child, item['new'], parts, skipped):
                        fields.update(item['new'])
                if fields:
                    child.model.objects.bulk_update(objs.values(), sorted(fields))
            fresh = [(item, _new_child(child, item, keys, parts, skipped)) for item in ops['create']]
            fresh = [(item, obj) for item, obj in fresh if obj is not None]
            ops['create'] = [item for item, _obj in fresh]
            created = child.model.objects.bulk_create([obj for _item, obj in fresh], batch_size=CHUNK)
            for (item, _obj), obj in zip(fresh, created):
                item['pk'] = obj.pk

        snapshot = {'format': FORMAT, 'package': str(package), 'fields': names,
                    'applied_at': datetime.now().astimezone().isoformat(),
                    'refs': result['refs'], 'problems': result['problems'],
                    'children': {name: {k: ops[k] for k in ('create', 'update', 'delete')}
                                 for name, ops in result['children'].items()}}
        Path(snapshot_path).write_text(json.dumps(snapshot, ensure_ascii=False), encoding='utf-8')
    return snapshot


# ── Откат ────────────────────────────────────────────────────────────────
def _has_dependents(obj):
    collector = Collector(using=obj._state.db)
    collector.collect([obj])
    rows = sum(len(objs) for objs in collector.data.values())
    fast = sum(q.count() if isinstance(q, QuerySet) else len(q) for q in collector.fast_deletes)
    return rows > 1 or fast > 0


def _current_items(child, pks, maps):
    rows = []
    for batch in chunks(pks):
        rows += child.model.objects.filter(pk__in=batch).values(*_columns(child))
    part_order = _part_order({r['part_id'] for r in rows if r['part_id']}) if child.part else {}
    return _items(child, rows, maps, part_order)


def revert(snapshot_path):
    """Возвращает снимок `bank_sync_apply`. Счётчики и список конфликтов."""
    snap = json.loads(Path(snapshot_path).read_text(encoding='utf-8'))
    stats, conflicts = Counter(), []
    children = [child for child in CHILDREN if child.name in snap['children']]
    with transaction.atomic():
        maps = ref_maps()
        # Проход 1, с конца: убрать созданное, вернуть обновлённое.
        for child in reversed(children):
            ops = snap['children'][child.name]
            current = _current_items(child, [i['pk'] for i in ops['create'] + ops['update']], maps)
            parts = _part_pks([i['problem'] for i in ops['update']]) if child.part else {}
            columns = list(child.fields) + (['part'] if child.part else [])
            doomed = []
            for item in ops['create']:
                cur = current.get(item['pk'])
                if cur is None:
                    stats[child.name + ': созданное уже удалено'] += 1
                elif cur['key'] != item['key'] or {c: cur.get(c) for c in columns} != item['row']:
                    conflicts.append((child.name, _where(item), 'созданную строку изменили'))
                else:
                    doomed.append(item['pk'])
            for batch in chunks(doomed):
                child.model.objects.filter(pk__in=batch).delete()
            stats[child.name + ': удалено созданных'] += len(doomed)
            for item in ops['update']:
                cur = current.get(item['pk'])
                if cur is None:
                    conflicts.append((child.name, _where(item), 'строки больше нет'))
                    continue
                back = {f: old for f, old in item['old'].items() if cur.get(f) == item['new'][f]}
                if len(back) < len(item['old']):
                    conflicts.append((child.name, _where(item), 'поле изменили после синхронизации'))
                obj = child.model.objects.get(pk=item['pk'])
                if back and _set_row(obj, child, back, parts, conflicts):
                    obj.save(update_fields=list(back))
                    stats[child.name + ': возвращено строк'] += 1
        # Проход 2, с начала: вернуть удалённое с прежним pk.
        keys = _key_pk(ref_maps())
        for child in children:
            ops = snap['children'][child.name]
            parts = _part_pks([i['problem'] for i in ops['delete']]) if child.part else {}
            existing = set()
            for batch in chunks([i['pk'] for i in ops['delete']]):
                existing.update(child.model.objects.filter(pk__in=batch).values_list('pk', flat=True))
            objs = []
            for item in ops['delete']:
                if item['pk'] in existing:
                    conflicts.append((child.name, _where(item), 'pk уже занят'))
                    continue
                obj = _new_child(child, item, keys, parts, conflicts, pk=item['pk'])
                if obj is not None:
                    objs.append(obj)
            child.model.objects.bulk_create(objs, batch_size=CHUNK)
            stats[child.name + ': восстановлено удалённых'] += len(objs)
        # Поля задач.
        for batch in chunks(snap['problems']):
            fields = sorted({f for item in batch for f in item['new']})
            objs = Problem.objects.only(*fields).in_bulk([item['id'] for item in batch])
            touched = []
            for item in batch:
                obj = objs.get(item['id'])
                if obj is None:
                    conflicts.append(('problem', '#%s' % item['id'], 'задачи больше нет'))
                    continue
                changed = False
                for f, old in item['old'].items():
                    field = _field(Problem, f)
                    if dump(field, getattr(obj, f)) == item['new'][f]:
                        setattr(obj, f, load(field, old))
                        changed = True
                    else:
                        conflicts.append(('problem', '#%s %s' % (item['id'], f),
                                          'поле изменили после синхронизации'))
                if changed:
                    touched.append(obj)
            if touched:
                Problem.objects.bulk_update(touched, fields)
            stats['задачи: возвращено'] += len(touched)
        # Справочники.
        for name, ops in snap['refs'].items():
            ref = REFS[name]
            for item in ops['update']:
                obj = ref.model.objects.get(pk=item['pk'])
                back = [f for f in item['old']
                        if dump(_field(ref.model, f), getattr(obj, f)) == item['new'][f]]
                for f in back:
                    setattr(obj, f, load(_field(ref.model, f), item['old'][f]))
                if back:
                    obj.save(update_fields=back)
                    stats[name + ': возвращено'] += 1
                if len(back) < len(item['old']):
                    conflicts.append((name, item['key'], 'поле изменили после синхронизации'))
            for item in ops['create']:
                obj = ref.model.objects.filter(pk=item.get('pk')).first()
                if obj is None:
                    continue
                if _has_dependents(obj):
                    conflicts.append((name, item['key'], 'на созданную запись уже ссылаются'))
                else:
                    obj.delete()
                    stats[name + ': удалено созданных'] += 1
    return stats, conflicts


# ── Отчёт ────────────────────────────────────────────────────────────────
def short(value, limit=160):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = text.replace('\n', ' ⏎ ').replace('|', '\\|')
    return text if len(text) <= limit else text[:limit] + '…'


def empty_plan(refs=(), children=()):
    """Пустой план в формате `plan()` — его заполняют команды правок дома."""
    return {'refs': {name: {'create': [], 'update': []} for name in refs},
            'problems': [], 'missing': [], 'skipped': [],
            'children': {name: {'create': [], 'update': [], 'delete': [], 'kept': []}
                         for name in children}}


def report_lines(result, snapshot=None, examples=20):
    """Тело отчёта: справочники, поля задач, связи, пропуски. Шапку пишет команда."""
    lines = ['- Задач с изменениями: %d' % len(changed_ids(result))]
    if snapshot:
        lines += ['', '**Записано.** Снимок для отката: `%s`' % snapshot]
    if result['missing']:
        lines += ['', 'Нет в базе, не создаются: %d (первые 50: %s)'
                  % (len(result['missing']), ', '.join(map(str, result['missing'][:50])))]
    lines.append('')

    lines += ['## Справочники', '', '| справочник | создать | обновить |', '|---|---|---|']
    lines += ['| %s | %d | %d |' % (name, len(ops['create']), len(ops['update']))
              for name, ops in result['refs'].items()]
    for name, ops in result['refs'].items():
        for item in ops['update'][:examples]:
            lines.append('- `%s` %s: %s → %s' % (name, short(item['key'], 60),
                                                  short(item['old']), short(item['new'])))
        for item in ops['create'][:examples]:
            lines.append('- `%s` создать %s: %s' % (name, short(item['key'], 60), short(item['row'])))
    lines.append('')

    by_field = Counter(f for item in result['problems'] for f in item['new'])
    lines += ['## Поля задач', '', '| поле | изменится у задач |', '|---|---|']
    lines += ['| %s | %d |' % (f, n) for f, n in sorted(by_field.items())]
    for f in sorted(by_field):
        lines += ['', '### %s — примеры' % f, '', '| id | было | станет |', '|---|---|---|']
        sample = [item for item in result['problems'] if f in item['new']][:examples]
        lines += ['| %d | %s | %s |' % (item['id'], short(item['old'][f]), short(item['new'][f]))
                  for item in sample]
    lines.append('')

    lines += ['## Связи и дочерние строки', '',
              '| таблица | добавить | обновить | удалить | не удалено (ссылки) |', '|---|---|---|---|---|']
    lines += ['| %s | %d | %d | %d | %d |' % (name, len(ops['create']), len(ops['update']),
                                              len(ops['delete']), len(ops['kept']))
              for name, ops in result['children'].items()]
    for name, ops in result['children'].items():
        if not any(ops[k] for k in ('create', 'update', 'delete', 'kept')):
            continue
        lines += ['', '### %s — примеры' % name, '']
        for item in ops['update'][:examples]:
            lines.append('- #%d [%s] обновить: %s → %s' % (item['problem'], short(item['key'], 60),
                                                            short(item['old']), short(item['new'])))
        for item in ops['create'][:examples]:
            lines.append('- #%d [%s] добавить: %s' % (item['problem'], short(item['key'], 60),
                                                       short(item['row'])))
        for item in ops['delete'][:examples]:
            lines.append('- #%d [%s] удалить: %s' % (item['problem'], short(item['key'], 60),
                                                      short(item['row'])))
        for item in ops['kept'][:examples]:
            lines.append('- #%d [%s] НЕ удалён: %s' % (item['problem'], short(item['key'], 60),
                                                        item['reason']))
    if result['skipped']:
        lines += ['', '## Пропуски', '', '| таблица | задача/ключ | причина |', '|---|---|---|']
        lines += ['| %s | %s | %s |' % (a, short(b, 60), c) for a, b, c in result['skipped'][:200]]
        if len(result['skipped']) > 200:
            lines.append('… всего %d' % len(result['skipped']))
    return lines
