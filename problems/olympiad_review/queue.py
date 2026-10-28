# -*- coding: utf-8 -*-
"""Позиции → карточки: склейка по задаче, приоритет, состояние очереди.

Карточка (`human_queue.jsonl`, строка) — одна задача: все позиции с тем же
`problem_id` или тем же `ref_key` (транзитивно). Поля карточки:
`item_id` (id карточки, его же пишет рецензент в решении), `items` (исходные
позиции), `current`/`proposed` (поля банка), `base` (отпечатки текущих полей —
по ним `apply` узнаёт, что задачу правили после сборки пакета).

Состояние очереди — файлы в `queues\\`: `closed.jsonl` (позиции, решённые и
применённые) и `disputed.jsonl` (спор двух рецензентов). Закрытая позиция в
карточку не попадает; карточка, у которой закрыты все позиции, — тоже.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from problems.olympiad_review import common


def card_id_for(problem_id, ref_key):
    return f'p{problem_id}' if problem_id else f'r:{ref_key}'


def merge(items):
    """Склеить позиции об одной задаче: union-find по problem_id и ref_key."""
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    seen = {}
    for i, it in enumerate(items):
        for tag in ((f'p{it["problem_id"]}' if it.get('problem_id') else None),
                    (f'r:{it["ref_key"]}' if it.get('ref_key') else None)):
            if tag is None:
                continue
            if tag in seen:
                parent[find(i)] = find(seen[tag])
            else:
                seen[tag] = i
    groups = defaultdict(list)
    for i, it in enumerate(items):
        groups[find(i)].append(it)
    return [_card(group) for group in groups.values()]


def _card(group):
    group = sorted(group, key=lambda it: it['item_id'])
    pid = next((it['problem_id'] for it in group if it.get('problem_id')), None)
    ref_keys = sorted({it['ref_key'] for it in group if it.get('ref_key')})
    first = next((it for it in group if it.get('current')), group[0])
    proposed, clash = {}, []
    for it in group:
        for name, value in (it.get('proposed') or {}).items():
            if name in proposed and proposed[name] != value:
                clash.append(name)
                continue
            proposed[name] = value
    pair = next((it.get('pair_bank') for it in group if it.get('pair_bank')), None)
    if pair:
        proposed.pop('link_to', None)
    figures = {}
    images = []
    for it in group:
        figures.update(it.get('figures') or {})
        for png in it.get('page_images') or []:
            if png not in images:
                images.append(png)
    current = first.get('current') or {}
    confidences = [it['confidence'] for it in group if it.get('confidence') is not None]
    card = {
        'item_id': card_id_for(pid, ref_keys[0] if ref_keys else ''),
        'olympiad': first.get('olympiad'),
        'stage': next((it.get('stage') for it in group if it.get('stage')), ''),
        'ref_key': ref_keys[0] if ref_keys else None,
        'ref_keys': ref_keys,
        'problem_id': pid,
        'kind': 'pair' if pair else 'fix',
        'pair_bank': pair,
        'sources': sorted({it['source'] for it in group}),
        'checks': [it['check'] for it in group],
        'details': [f'[{it["check"]}] {it.get("details") or ""}'.strip() for it in group],
        'items': [it['item_id'] for it in group],
        'page_images': images,
        'current': current,
        'current_from': first.get('current_from') or 'bank',
        'proposed': proposed or None,
        'proposed_clash': sorted(set(clash)),
        'base': {name: common.field_sha(value) for name, value in current.items()},
        'confidence': min(confidences) if confidences else None,
        'figures': figures,
        'auto': all(it.get('auto') for it in group),
    }
    return card


def priority(card, visible):
    """Сначала видимые на сайте, затем ВП → МОШ → ВсОШ ЗЭ/РЭ → остальное."""
    return (0 if visible else 1, common.olympiad_rank(card['olympiad'], card.get('stage') or ''),
            card['olympiad'] or '', card['ref_key'] or '', card['problem_id'] or 0)


def build(items, *, closed=(), is_visible=lambda pid: False):
    """(карточки людям по приоритету, автоисправления, сводка)."""
    closed = set(closed)
    open_items = [it for it in items if it['item_id'] not in closed]
    auto = [it for it in open_items if it.get('auto')]
    human = [it for it in open_items if not it.get('auto')]
    cards = merge(human)
    for card in cards:
        card['visible'] = bool(card['problem_id'] and is_visible(card['problem_id']))
    cards.sort(key=lambda c: priority(c, c['visible']))
    summary = {
        'позиций всего': len(items),
        'закрыто раньше': len(items) - len(open_items),
        'автоисправлений (людям не показываются)': len(auto),
        'позиций людям': len(human),
        'карточек': len(cards),
        'склеено (позиций − карточек)': len(human) - len(cards),
        'видимых на сайте': sum(1 for c in cards if c['visible']),
        'позиций по источникам': dict(Counter(it['source'] for it in human)),
        'карточек по олимпиадам': dict(Counter(c['olympiad'] for c in cards)),
        'карточек по видам': dict(Counter(c['kind'] for c in cards)),
    }
    return cards, auto, summary


def load_closed(path):
    import os
    if not os.path.isfile(path):
        return set()
    return {r['item'] for r in common.read_jsonl(path)}
