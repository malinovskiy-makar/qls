# -*- coding: utf-8 -*-
"""ВсОШ: сверка эталона v1 с оцифровкой ILE (`/print-all-tasks/{nid}`).

ILE — сайт ЦПМК; на печатной странице года: `h2` — классы, `h3` — «N. Название»,
внутри `div.task` — `div.condition` (условие) и решение (LaTeX в `$…$`). Эталон — PDF; ILE служит
мерилом: задание v1 ищется среди задач ILE того же этапа и сезона по тексту
без разметки (rapidfuzz). Нашлось с низким сходством — флаг
`расхождение_с_ILE`; нашлось уверенно — название ILE пишется в `ile_title`
(кандидат заголовка, решение Notion 15.10: официальное название — из источника).
"""
from __future__ import annotations

import os
import re

from problems.olympiad_audit import vsosh_sources as S

#: Сходство (token_set_ratio) «та же задача» и «расходится сильно».
SAME = 0.80
STRONG_DIFF = 0.60


def parse_print_page(html_text):
    """HTML печатной страницы → [{grades, number, title, text}]."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html_text, 'lxml')
    out, grades = [], ''
    for el in soup.find_all(['h2', 'h3']):
        if el.name == 'h2':
            grades = S.parse_grades(el.get_text(' ', strip=True)) or grades
            continue
        head = el.get_text(' ', strip=True)
        m = re.match(r'\s*(\d+)\s*[.)]\s*(.*)', head)
        # `h3` стоит внутри своего `div.task`; условие — `div.condition`, решение рядом не берём.
        box = el.find_parent('div', class_='task')
        cond = box.find('div', class_='condition') if box else None
        text = cond.get_text('\n', strip=True) if cond else ''
        out.append({'grades': grades, 'number': m.group(1) if m else '',
                    'title': (m.group(2) if m else head).strip(), 'text': text})
    return out


def load_ile_tasks(data_root, extras):
    """Печатные страницы, скачанные в raw/ile/print → задачи с этапом и сезоном."""
    tasks = []
    for e in extras:
        if e.get('kind') != 'ile_print':
            continue
        path = os.path.join(data_root, 'raw', 'ile', 'print', S.dest_name(e['url']) + '.html')
        if not os.path.isfile(path):
            continue
        with open(path, encoding='utf-8', errors='replace') as fh:
            for t in parse_print_page(fh.read()):
                tasks.append(dict(t, stage=e['stage'], season=e['season'], url=e['url'],
                                  subject=e.get('subject', 'econ')))
    return tasks


def compare(rows, ile_tasks):
    """Каждой строке v1 — лучшая задача ILE того же этапа и сезона.
    Возвращает отчёт [{key, best, ile_url, ile_title, verdict}] и правит rows."""
    from rapidfuzz import fuzz

    from problems.olympiad_official import markup_free_key
    by = {}
    for t in ile_tasks:
        by.setdefault((t['stage'], t['season']), []).append((t, markup_free_key(t['text'])))
    report = []
    for r in rows:
        cands = by.get((r.get('stage'), r.get('academic_year')))
        if not cands:
            continue
        key = markup_free_key(r.get('statement_md') or '')
        if len(key) < 40:
            continue
        best, bt = 0.0, None
        for t, k in cands:
            if not k:
                continue
            s = fuzz.token_set_ratio(key[:4000], k[:4000]) / 100
            if s > best:
                best, bt = s, t
        verdict = 'совпало' if best >= SAME else 'сильно_расходится' if best >= STRONG_DIFF else 'нет_пары'
        if verdict == 'совпало' and bt.get('title'):
            r['ile_title'] = bt['title']
        if verdict == 'сильно_расходится':
            r.setdefault('flags', [])
            if 'расхождение_с_ILE' not in r['flags']:
                r['flags'].append('расхождение_с_ILE')
        report.append({'event_id': r['event_id'], 'number': r['number'], 'best': round(best, 3),
                       'ile_url': bt['url'] if bt else '', 'ile_title': bt['title'] if bt else '',
                       'verdict': verdict})
    return report
