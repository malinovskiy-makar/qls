# -*- coding: utf-8 -*-
"""Решения людей → база и файлы. План, запись, журнал, откат.

Что делает решение по карточке:

* задача уже в банке (`problem_id`):
  - `ok` — позиция закрыта;
  - `accept_proposed` / `edit` — правка полей задачи и подпунктов, перед
    правкой снимок в `ProblemVersion`; поле правится, только если в базе оно
    такое же, каким было в пакете (`card.base`), иначе — конфликт в отчёт;
    подпункты правятся на месте по порядку, недостающие добавляются,
    лишние НЕ удаляются (к ним привязаны подсказки) — меньше пунктов = конфликт;
  - `hide` — `content_status = needs_fix` (текст требует доработки, ученику не
    виден), `not_a_task` — `content_status = junk` (помечено к удалению,
    ничего не удаляется); точечно по id, старое значение — в журнале;
  - `skip` — карточка возвращается в очередь (снимается из `packs_index.json`);
* строки эталона без задачи в банке (`ref_key`) — строка в
  `reference_overrides.jsonl` олимпиады (`overrides.py`); у пары «та же
  задача?» `accept_proposed` = привязать, `ok` = завести новой;
* спор двух рецензентов — в `disputed.jsonl`, позиция остаётся в очереди.

Повтор применения — 0 действий: поле уже новое, строка override с тем же
отпечатком уже есть, позиция уже закрыта.
"""
from __future__ import annotations

import json
import os
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path

from django.db import transaction
from django.db.models import Max

from problems.olympiad_review import common
from problems.olympiad_review import overrides as ov_rules

WRITE_KINDS = ('bank_fields', 'bank_hide', 'override', 'close', 'requeue')
HIDE_STATUS = {'hide': 'needs_fix', 'not_a_task': 'junk'}
AUTO_REVIEWER = 'auto:q1_contour'


class Files:
    """Файлы состояния; на репетиции все записи уходят в копии в `redirect`."""

    def __init__(self, qdir, redirect=None):
        self.qdir = Path(qdir)
        self.redirect = Path(redirect) if redirect else None
        self.map = {}

    def path(self, real):
        real = Path(real)
        if not self.redirect:
            return real
        if real not in self.map:
            name = '_'.join(real.parts[-3:]).replace(':', '')
            target = self.redirect / name
            self.redirect.mkdir(parents=True, exist_ok=True)
            if real.is_file() and not target.exists():
                shutil.copyfile(real, target)
            self.map[real] = target
        return self.map[real]

    def closed(self):
        return self.path(self.qdir / 'queues' / 'closed.jsonl')

    def disputed(self):
        return self.path(self.qdir / 'queues' / 'disputed.jsonl')

    def index(self):
        return self.path(self.qdir / 'packs' / 'packs_index.json')

    def overrides(self, slug):
        return self.path(common.overrides_path(slug))


def load_cards(qdir, pack_ids):
    cards = {}
    for pack_id in pack_ids:
        path = Path(qdir) / 'packs' / pack_id / 'cards.jsonl'
        if not path.is_file():
            raise FileNotFoundError(f'нет снимка карточек пакета {pack_id}: {path}')
        for card in common.read_jsonl(path):
            cards[(pack_id, card['item_id'])] = card
    return cards


def auto_cards(path):
    """Автоисправления Q1 (`auto: true`) → (карточка, решение accept_proposed)."""
    out = []
    if not os.path.isfile(path):
        return out
    for item in common.read_jsonl(path):
        if not item.get('auto') or not item.get('proposed'):
            continue
        current = item.get('current') or {}
        card = {'item_id': item['item_id'], 'olympiad': item.get('olympiad'),
                'ref_key': item.get('ref_key'), 'problem_id': item.get('problem_id'),
                'kind': 'fix', 'items': [item['item_id']], 'current': current,
                'proposed': item['proposed'],
                'base': {k: common.field_sha(v) for k, v in current.items()}}
        out.append((card, {'item_id': item['item_id'], 'decision': 'accept_proposed', 'edited': {},
                           'reviewer': AUTO_REVIEWER, 'comment': item.get('check') or '',
                           'ts': '', 'pack_id': 'auto'}))
    return out


def _bank_value(problem, name):
    if name == 'parts':
        return [{'label': p.label, 'statement': p.statement, 'answer': p.answer}
                for p in problem.parts.order_by('order', 'id')]
    return getattr(problem, name) or ''


def _override_line(card, dec, action, fields=None, bank_id=None):
    line = {'ref_key': card['ref_key'], 'action': action, 'fields': fields or {},
            'bank_id': bank_id, 'item_id': card['item_id'], 'reviewer': dec['reviewer'],
            'comment': dec.get('comment') or '', 'decided_at': dec.get('ts') or '',
            'pack_id': dec.get('pack_id')}
    line['sha'] = common.field_sha([action, fields or {}, bank_id])
    return line


def plan(pairs, files, closed=None, index=None):
    """[(карточка, решение)] → действия. Ничего не пишет."""
    from problems.models import Problem
    closed = closed if closed is not None else _closed_ids(files.closed())
    index = index if index is not None else _load_index(files.index())
    have = {}
    actions = []
    for card, dec in pairs:
        base = {'item_id': card['item_id'], 'pack_id': dec.get('pack_id'), 'decision': dec['decision'],
                'reviewer': dec['reviewer'], 'olympiad': card.get('olympiad'),
                'problem_id': card.get('problem_id'), 'ref_key': card.get('ref_key'),
                'items': card.get('items') or [card['item_id']], 'comment': dec.get('comment') or ''}
        decision = dec['decision']
        if decision == 'skip':
            entry = index.get(card['item_id'])
            if entry and entry.get('pack') == dec.get('pack_id'):
                actions.append(dict(base, kind='requeue'))
            else:
                actions.append(dict(base, kind='noop', why='карточка уже не в выданных'))
            continue
        open_items = [i for i in base['items'] if i not in closed]
        if card.get('problem_id'):
            problem = Problem.objects.filter(pk=card['problem_id']).first()
            if problem is None:
                actions.append(dict(base, kind='conflict', why='задачи нет в базе'))
                continue
            if decision in ('accept_proposed', 'edit'):
                new = (dict(card.get('proposed') or {}) if decision == 'accept_proposed'
                       else dict(dec.get('edited') or {}))
                new.pop('link_to', None)
                new = common.norm_fields(new)
                changes, why = {}, []
                for name, value in new.items():
                    current = _bank_value(problem, name)
                    if current == value:
                        continue
                    if common.field_sha(current) != (card.get('base') or {}).get(name):
                        why.append(f'{name}: в базе уже не то, что было в пакете')
                        continue
                    if name == 'parts' and len(value) < len(current):
                        why.append(f'parts: пунктов меньше ({len(value)} < {len(current)}) — '
                                   'удалять подпункты нельзя, руками')
                        continue
                    changes[name] = {'old': current, 'new': value}
                if why:
                    actions.append(dict(base, kind='conflict', why='; '.join(why)))
                    continue
                if changes:
                    actions.append(dict(base, kind='bank_fields', changes=changes,
                                        visible_before=None))
            elif decision in HIDE_STATUS:
                status = HIDE_STATUS[decision]
                if problem.content_status != status:
                    actions.append(dict(base, kind='bank_hide', status_old=problem.content_status,
                                        status_new=status))
        else:
            if not card.get('ref_key'):
                actions.append(dict(base, kind='conflict', why='нет ни problem_id, ни ref_key'))
                continue
            line = _plan_override(card, dec)
            if line is None:
                actions.append(dict(base, kind='conflict', why='решение не переводится в override'))
                continue
            slug = card['olympiad']
            if slug not in have:
                path = files.overrides(slug)
                have[slug] = {(r.get('item_id'), r.get('sha')) for r in common.read_jsonl(path)} \
                    if path.is_file() else set()
            if (line['item_id'], line['sha']) not in have[slug]:
                actions.append(dict(base, kind='override', slug=slug, line=line))
                have[slug].add((line['item_id'], line['sha']))
        if open_items:
            actions.append(dict(base, kind='close', close_items=open_items))
    return actions


def _plan_override(card, dec):
    decision = dec['decision']
    pair = card.get('kind') == 'pair' and card.get('pair_bank')
    edited = common.norm_fields(dec.get('edited') or {}) or {}
    if pair:
        if decision == 'accept_proposed':
            return _override_line(card, dec, 'link', bank_id=card['pair_bank']['id'])
        if decision == 'ok':
            return _override_line(card, dec, 'new')
        if decision == 'edit':
            return _override_line(card, dec, 'new', fields=edited)
    if decision == 'ok':
        return _override_line(card, dec, 'ok')
    if decision == 'accept_proposed':
        fields = common.norm_fields(card.get('proposed') or {}) or {}
        return _override_line(card, dec, 'edit', fields=fields) if fields else None
    if decision == 'edit':
        return _override_line(card, dec, 'edit', fields=edited)
    if decision in ('hide', 'not_a_task'):
        return _override_line(card, dec, decision)
    return None


def _closed_ids(path):
    if not Path(path).is_file():
        return set()
    return {r['item'] for r in common.read_jsonl(path)}


def _load_index(path):
    if not Path(path).is_file():
        return {}
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


def summary(actions):
    kinds = Counter(a['kind'] for a in actions)
    return {
        'действий': dict(kinds),
        'задач банка правится': kinds['bank_fields'],
        'задач скрывается': kinds['bank_hide'],
        'строк override': kinds['override'],
        'карточек закрывается': kinds['close'],
        'вернуть в очередь': kinds['requeue'],
        'конфликтов': kinds['conflict'],
        'пишущих действий': sum(kinds[k] for k in WRITE_KINDS),
        'решений по видам': dict(Counter(a['decision'] for a in actions if a['kind'] != 'close')),
    }


# ── Запись ──────────────────────────────────────────────────────────────

def execute(actions, files, *, journal_path, note='проверка людьми (Q3)'):
    """Записать план. Журнал — на каждый шаг, чтобы откат был полным."""
    from problems.management.commands.apply_official_text import snapshot_of
    from problems.models import Problem, ProblemPart, ProblemVersion
    journal = {'command': 'olympiad_review apply', 'applied': True,
               'at': datetime.now().isoformat(timespec='seconds'), 'changes': [], 'hides': [],
               'files': {}, 'index_removed': {}}

    def remember(path):
        key = str(path)
        if key not in journal['files']:
            journal['files'][key] = {'size_before': path.stat().st_size if path.is_file() else -1}
        return path

    for a in actions:
        if a['kind'] == 'bank_fields':
            with transaction.atomic():
                problem = Problem.objects.select_for_update().get(pk=a['problem_id'])
                number = (problem.versions.aggregate(n=Max('number'))['n'] or 0) + 1
                version = ProblemVersion.objects.create(
                    problem=problem, number=number, snapshot=snapshot_of(problem),
                    note=f'{note}: {a["decision"]} {a["reviewer"]} '
                         f'({", ".join(a["changes"])})'[:300])
                rec = {'id': problem.id, 'item_id': a['item_id'], 'version_id': version.id,
                       'fields': {}, 'parts_old': [], 'created_part_ids': []}
                for name, ch in a['changes'].items():
                    if name == 'parts':
                        continue
                    rec['fields'][name] = {'old': ch['old'], 'new': ch['new']}
                    setattr(problem, name, ch['new'])
                if rec['fields']:
                    problem.save(update_fields=list(rec['fields']))
                if 'parts' in a['changes']:
                    bank = list(problem.parts.order_by('order', 'id'))
                    for i, p in enumerate(a['changes']['parts']['new']):
                        if i < len(bank):
                            bp = bank[i]
                            rec['parts_old'].append({'id': bp.id, 'label': bp.label,
                                                     'statement': bp.statement, 'answer': bp.answer,
                                                     'new': [p['label'][:10], p['statement'], p['answer']]})
                            bp.label, bp.statement, bp.answer = p['label'][:10], p['statement'], p['answer']
                            bp.save(update_fields=['label', 'statement', 'answer'])
                        else:
                            order = (bank[-1].order + 1 + i - len(bank)) if bank else i
                            rec['created_part_ids'].append(ProblemPart.objects.create(
                                problem=problem, label=p['label'][:10], statement=p['statement'],
                                answer=p['answer'], order=order).id)
                journal['changes'].append(rec)
        elif a['kind'] == 'bank_hide':
            n = Problem.objects.filter(pk=a['problem_id'], content_status=a['status_old']) \
                .update(content_status=a['status_new'])
            if n:
                journal['hides'].append({'id': a['problem_id'], 'item_id': a['item_id'],
                                         'old': a['status_old'], 'new': a['status_new']})
        elif a['kind'] == 'override':
            path = remember(files.overrides(a['slug']))
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'a', encoding='utf-8') as handle:
                handle.write(json.dumps(dict(a['line'], applied_at=journal['at']),
                                        ensure_ascii=False) + '\n')
        elif a['kind'] == 'close':
            path = remember(files.closed())
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'a', encoding='utf-8') as handle:
                for item in a['close_items']:
                    handle.write(json.dumps({'item': item, 'card': a['item_id'], 'decision': a['decision'],
                                             'reviewer': a['reviewer'], 'pack_id': a['pack_id'],
                                             'applied_at': journal['at'], 'journal': str(journal_path)},
                                            ensure_ascii=False) + '\n')
        elif a['kind'] == 'requeue':
            path = files.index()
            index = _load_index(path)
            if a['item_id'] in index:
                journal['index_removed'][a['item_id']] = index.pop(a['item_id'])
                _save_json(path, index)
    journal['index_path'] = str(files.index())
    _save_json(journal_path, journal)
    return journal


def write_disputes(files, disputes, at):
    if not disputes:
        return 0
    path = files.disputed()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'a', encoding='utf-8') as handle:
        for d in disputes:
            handle.write(json.dumps(dict(d, at=at), ensure_ascii=False) + '\n')
    return len(disputes)


def _save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with open(tmp, 'w', encoding='utf-8') as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1, default=str)
    os.replace(tmp, path)


def rollback(journal):
    """Вернуть базу и файлы по журналу записи. Поле — только если его с тех пор не меняли."""
    from problems.models import Problem, ProblemPart, ProblemVersion
    report = Counter()
    with transaction.atomic():
        for rec in journal['changes']:
            for name, v in rec['fields'].items():
                report['поле'] += Problem.objects.filter(pk=rec['id'], **{name: v['new']}).update(
                    **{name: v['old']})
            for p in rec['parts_old']:
                label, statement, answer = p['new']
                report['подпункт'] += ProblemPart.objects.filter(
                    pk=p['id'], label=label, statement=statement, answer=answer).update(
                    label=p['label'], statement=p['statement'], answer=p['answer'])
            report['созданный подпункт'] += ProblemPart.objects.filter(
                pk__in=rec['created_part_ids']).delete()[0]
            report['версия'] += ProblemVersion.objects.filter(pk=rec['version_id']).delete()[0]
        for h in journal['hides']:
            report['скрытие'] += Problem.objects.filter(pk=h['id'], content_status=h['new']).update(
                content_status=h['old'])
    for path, info in journal['files'].items():
        path = Path(path)
        if info['size_before'] < 0:
            if path.is_file():
                path.unlink()
                report['файл'] += 1
        elif path.is_file():
            with open(path, 'r+b') as handle:
                handle.truncate(info['size_before'])
            report['файл'] += 1
    if journal.get('index_removed'):
        index = _load_index(journal['index_path'])
        index.update(journal['index_removed'])
        _save_json(journal['index_path'], index)
        report['пакет'] += len(journal['index_removed'])
    return dict(report)


# ── Счётчики и снимок для инвариантов ──────────────────────────────────

def counts():
    from catalog.filters import base_queryset
    from problems.models import OlympiadRef, Problem, ProblemPart, ProblemVersion
    return {
        'Problem': Problem.objects.count(),
        'видимых': base_queryset('catalog').count(),
        'OlympiadRef': OlympiadRef.objects.count(),
        'ProblemVersion': ProblemVersion.objects.count(),
        'ProblemPart': ProblemPart.objects.count(),
        'content_status≠ok': Problem.objects.exclude(content_status='ok').count(),
    }


def digest(problem_ids):
    """Отпечаток затронутых задач: поля, подпункты, состояние текста, число версий."""
    from problems.management.commands.apply_official_text import snapshot_of
    from problems.models import Problem
    out = {}
    for p in Problem.objects.filter(pk__in=sorted(problem_ids)):
        snap = snapshot_of(p)
        snap['content_status'] = p.content_status
        snap['versions'] = p.versions.count()
        out[p.id] = common.field_sha(snap)
    return common.field_sha(out)


def invariants(actions, before, after, visible_hidden):
    kinds = Counter(a['kind'] for a in actions)
    checks = {
        'Problem не изменилось': after['Problem'] == before['Problem'],
        'OlympiadRef не изменилось': after['OlympiadRef'] == before['OlympiadRef'],
        'ProblemVersion + изменённые задачи':
            after['ProblemVersion'] - before['ProblemVersion'] == kinds['bank_fields'],
        'скрыто = решений hide/not_a_task':
            after['content_status≠ok'] - before['content_status≠ok'] == kinds['bank_hide'],
        'видимых − скрытые видимые': before['видимых'] - after['видимых'] == visible_hidden,
    }
    return checks
