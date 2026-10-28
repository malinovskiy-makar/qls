# -*- coding: utf-8 -*-
"""Очередь перечитывания страниц по находкам автопроверок и сверки глазами.

Перенесено из `weconomics-data\\olympiads\\v4_work\\build_queue.py` (13.10.2026)
без изменения правил. Приоритеты:

* 1 — находка сверки глазами с приоритетом 1; класс 1 (смесь алфавитов) не
  в формуле;
* 2 — классы 4, 5, 7, 8; класс 9, кроме «блока коротких строк»; класс 6
  только «нет в слое»;
* 3 — классы 2, 3; формулы класса 1; блок коротких строк класса 9;
  излишек сверх бюджета.

Бюджет приоритетов 1+2 — `cap_usd` / `per_page` страниц (по умолчанию
$5 / $0,006); излишек приоритета 2 уходит в 3. Файл — UTF-8 с BOM, «;»,
колонки `set;page;priority;n_reasons;reasons`, причины через « || ».
"""
from __future__ import annotations

import collections
import csv
import json
import re

COLUMNS = ['set', 'page', 'priority', 'n_reasons', 'reasons']


def read_eye(path):
    with open(path, encoding='utf-8') as handle:
        data = json.load(handle)
    return [(x['set'], x['page'], x['reason'], int(x['priority'])) for x in data['pages']]


def _pages_for(ctx, x):
    if x['field'] == 'page':
        return x['pages'].split()
    pgs = sorted(ctx.tp[x['idx']])
    w = re.search(r'[А-Яа-яЁёA-Za-z]{4,}', x['snippet'])
    out = []
    for pg in pgs:
        pj = ctx.pjson(pg)
        txt = ' '.join((b.get('text') or '') for b in (pj or {}).get('blocks', []))
        if w and w.group(0) in txt:
            out.append(pg)
    return out or pgs[:1]


def _priority(x):
    c = x['cls']
    if c.startswith('1_'):
        return 1 if not x['snippet'].startswith('формула') else 3
    if c.startswith(('4_', '5_', '7_', '8_')):
        return 2
    if c.startswith('9_'):
        return 2 if not x['snippet'].lstrip().startswith('[блок') else 3
    if c.startswith('6_'):
        return 2 if 'нет в слое' in x['snippet'] else None
    if c.startswith(('2_', '3_')):
        return 3
    return None


def build(eye, findings, cap_usd=5.0, per_page=0.006):
    """`eye` — [(set, page, причина, приоритет)]; `findings` — {set: (ctx,
    находки автопроверок)} → строки очереди по порядку (приоритет, −число
    причин, (set, page))."""
    eye = [e for e in eye if e[3] != 9]
    q = collections.defaultdict(lambda: {'reasons': [], 'prio': 9})

    def add(s, pg, reason, prio):
        d = q[(s, pg)]
        if reason not in d['reasons']:
            d['reasons'].append(reason)
        d['prio'] = min(d['prio'], prio)

    sets = set(findings)
    for s, pg, r, p in eye:
        if s in sets:
            add(s, pg, 'глаза: ' + r, p)
    for st, (ctx, res) in findings.items():
        for x in res:
            pr = _priority(x)
            if pr is None:
                continue
            for pg in _pages_for(ctx, x):
                add(st, pg, 'авто %s: %s' % (x['cls'][:1], x['snippet'][:90]), pr)
    cap = int(cap_usd / per_page)
    rows = sorted(q.items(), key=lambda kv: (kv[1]['prio'], -len(kv[1]['reasons']), kv[0]))
    n12 = 0
    for _key, v in rows:
        if v['prio'] <= 2:
            n12 += 1
            if n12 > cap:
                v['prio'] = 3
                v['reasons'].append('(за пределом бюджета $5 — вниз)')
    rows = sorted(q.items(), key=lambda kv: (kv[1]['prio'], -len(kv[1]['reasons']), kv[0]))
    return [{'set': s, 'page': pg, 'priority': v['prio'], 'n_reasons': len(v['reasons']),
             'reasons': ' || '.join(v['reasons'][:6]).replace('\x00', '').replace('\r', ' ')}
            for (s, pg), v in rows]


def write(path, rows):
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';', quoting=csv.QUOTE_ALL)
        w.writerow(COLUMNS)
        for r in rows:
            w.writerow([r[c] for c in COLUMNS])


def read(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f, delimiter=';'))


# ── Подсказки для судьи и перечитывания (сессия v5) ──────────────────────

#: Класс автопроверки → что проверить на картинке (человеческими словами).
CLASS_HINTS = {
    '1': 'возможна путаница кириллицы и латиницы (А/A, В/B, С/C, Е/E, Р/P, Х/X, У/Y, М/M): '
         'переменные и обозначения в формулах (P — цена, X, Y — товары) — латиницей; русские '
         'слова и сокращения русских слов в индексах (Y_{Р} — «Россия») — кириллицей',
    '2': 'повтор строки «Ответ:» — на картинке, скорее всего, одна',
    '3': 'строка «Ответ» с числом, которого нет в тексте страницы, — возможно, выдумана',
    '4': 'сноска: маркер или текст сноски внизу страницы потерян',
    '5': 'артефакт расшифровки (нечитаемо, мягкий перенос, остаток переноса)',
    '6': 'слово не найдено ни в словаре, ни в текстовом слое PDF — возможно, искажено',
    '7': 'на странице рисунок или таблица: таблица — Markdown-таблицей целиком, по ячейкам; '
         'рисунок/график — блоком figure с рамкой и подписью, числа и подписи на нём — в подписи',
    '8': 'служебный блок (инструкция раздела) оформлен как задание',
    '9': 'строки текстового слоя PDF не найдены в расшифровке — возможно, потеряны таблица, '
         'сноска, вступление или служебная строка',
}

_EYE_ROW = re.compile(r'^\|\s*([vmoc]\d{2,3})\s*\|\s*([0-9a-f]{16}/p\d+)\s*\|[^|]*\|\s*[^|]*\|\s*(.+?)\s*\|\s*$')


def eye_findings(md_text):
    """Таблицы `EYE_REVIEW_FINDINGS_*.md` → {«<sha16>/pN»: (номер, что исправить)}."""
    out = {}
    for line in md_text.splitlines():
        m = _EYE_ROW.match(line.strip())
        if m:
            out[m.group(2)] = (m.group(1), m.group(3))
    return out


def _reason_hint(reason):
    """(класс автопроверки | None, текст подсказки)."""
    reason = reason.strip()
    if reason.startswith('глаза:'):
        return None, 'сверка глазами: ' + reason[len('глаза:'):].strip()
    m = re.match(r'авто (\d):\s*(.*)$', reason, re.S)
    if m:
        return m.group(1), m.group(2).strip()[:100]
    return None, reason[:300]


def page_hints(queue_rows, eye=None, fixes=None, extra=None, set_name=None):
    """Подсказки по страницам очереди: {«<sha16>/pN»: [строка, …]}.

    Источники: причины очереди (класс автопроверки — человеческими словами),
    формулировка сверки глазами (`eye`, приоритетнее короткой причины),
    правки v4 этой страницы (`fixes`: «на картинке «…», а не «…»») — чтобы
    перечитывание не вернуло ошибку, уже исправленную в v4, и `extra`
    (подсказки владельца по сомнительным страницам)."""
    out = {}
    for row in queue_rows:
        if set_name and row['set'] != set_name:
            continue
        page = row['page']
        hints = []
        if eye and page in eye:
            hints.append(f'сверка глазами ({eye[page][0]}): {eye[page][1]}')
        by_class = {}
        for reason in str(row.get('reasons') or '').split(' || '):
            if not reason.strip() or reason.startswith('(за пределом'):
                continue
            if reason.startswith('глаза:') and eye and page in eye:
                continue
            cls, hint = _reason_hint(reason)
            if cls is None:
                if hint not in hints:
                    hints.append(hint)
            elif hint not in by_class.setdefault(cls, []):
                by_class[cls].append(hint)
        for cls, examples in by_class.items():
            hints.append(f'{CLASS_HINTS.get(cls, "автопроверка")}. Где: '
                         + '; '.join(f'«{e}»' for e in examples[:5]))
        for fx in fixes or []:
            s, fpage, op, find, rep = fx[:5]
            if (set_name and s != set_name) or fpage != page or op != 'lit' or not rep:
                continue
            hints.append(f'на картинке «{rep}», а не «{find}»')
        for hint in (extra or {}).get(page, []):
            hints.append(hint)
        out[page] = hints
    return out
