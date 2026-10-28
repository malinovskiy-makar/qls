# -*- coding: utf-8 -*-
"""Соответствие ключей заданий двух версий эталона (v4 → v5, сессия v5, 14.10.2026).

Ключ задания — (event_id, number, task_variant). Каждое задание старой версии
получает ровно одну строку таблицы с итогом:

* `тот же ключ` — комплект не перенумерован, или задание с тем же ключом —
  то же по тексту;
* `удалено: служебный блок` — правила этапа / инструкция формата ответа, в
  новой версии — во вступлении комплекта или в `section_md`;
* `удалено: …` — известный дефект комплекта (`defect_kits`: {комплект: пояснение},
  `defect_targets`: {комплект: ключ, куда ушёл текст});
* `перенумеровано` — найдено по тексту в том же комплекте (сходство ≥ 75);
* `не найдено в v5`.

v5 → v6 (сессия v6, 15.10.2026, `repeats=True`):

* `удалено: повтор вопроса из файла ответов` — задание старой версии было
  повтором вопроса теста, заведённым файлом ответов («6» при «тест-6»); в новой
  версии его ответ — у вопроса, на который оно похоже (адрес — в строке);
* `новое задание` (`new_rows=True`) — ключ новой версии, которого не было, или
  ключ, под которым раньше лежал повтор (эссе МОШ 2009/10; вопрос второго
  теста, который v5 прятал под повтором);
* `kit_notes` — пояснение к строкам «тот же ключ» комплектов, где ключи те же,
  а решения пересобраны (правило v6 для файлов решений ВП 2019–2020).

Без модели и без базы: только сравнение строк эталонов.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from rapidfuzz import fuzz

from . import econ_rules

COLUMNS = ['set', 'v4_event', 'v4_number', 'v4_variant', 'v5_event', 'v5_number',
           'v5_variant', 'итог', 'пояснение']
SAME, RENUMBERED, SERVICE, MISSING = ('тот же ключ', 'перенумеровано',
                                      'удалено: служебный блок', 'не найдено в v5')
REPEAT, NEW = 'удалено: повтор вопроса из файла ответов', 'новое задание'


def columns(old='v4', new='v5'):
    """Заголовок таблицы для пары версий (v5 → v6: columns('v5', 'v6'))."""
    names = {'v4_': f'{old}_', 'v5_': f'{new}_'}
    return [names[c[:3]] + c[3:] if c[:3] in names else c for c in COLUMNS]


def key(r):
    return (r['event_id'], r['number'], r.get('task_variant') or '')


def plain(t):
    return re.sub(r'\s+', ' ', re.sub(r'[*#_|$>\\]', ' ', t or '')).strip().lower()


def core(text):
    """Текст без абзацев-инструкций формата ответа (у v4 они стояли в начале условия)."""
    paras = [x for x in re.split(r'\n\s*\n', text or '')
             if x.strip() and not econ_rules.format_lines(x) and not econ_rules.marker_of({'title': x})]
    return plain('\n\n'.join(paras))


def sim(a, b):
    a, b = a[:300], b[:600]
    return max(fuzz.partial_ratio(a, b), fuzz.token_set_ratio(a, b)) if a and b else 0


def body(r):
    """Условие без инструкции раздела новой версии (`section_md`)."""
    text = r.get('statement_md') or ''
    for lead in (r.get('section_md') or '').split('\n\n'):
        text = text.replace(lead, '')
    return plain(text)


def question(r):
    """Название + условие без инструкции раздела (у вопросов теста формулировка
    бывает в названии), простым текстом."""
    text = r.get('statement_md') or ''
    for lead in (r.get('section_md') or '').split('\n\n'):
        if lead.strip():
            text = text.replace(lead, '')
    return plain(f"{r.get('title') or ''}\n\n{text}")


def duplicates(rows):
    return [k for k, c in Counter(key(r) for r in rows).items() if c > 1]


def key_table(old, new, set_name='', defect_kits=None, defect_targets=None, repeats=False,
              new_rows=False, kit_notes=None):
    """(строки таблицы по COLUMNS, {комплект: (заданий было, стало)} с другими ключами).
    `repeats`, `new_rows`, `kit_notes` — v5 → v6 (см. описание модуля)."""
    defect_kits = defect_kits or {}
    defect_targets = defect_targets or {}
    kit_notes = kit_notes or {}
    rows, changed = _old_rows(old, new, set_name, defect_kits, defect_targets, repeats, kit_notes)
    if new_rows:
        rows.extend(_new_rows(old, new, rows, set_name))
    return rows, changed


def _is_repeat(r, best):
    """Старое задание — повтор вопроса из файла ответов: его номер — хвост
    «тест-N» найденного задания, или условие было только из файла ответов."""
    return (econ_rules.twin_number(best[1]) == r['number']
            or bool(r.get('statement_from_solution_file')))


def _new_rows(old, new, rows, set_name):
    """Ключи новой версии, которых не было, и ключи, чьё старое задание ушло."""
    k_old = {key(r) for r in old}
    reused = {tuple(x[1:4]) for x in rows if x[7] != SAME and tuple(x[1:4]) in {key(r) for r in new}}
    out = []
    for r in new:
        k = key(r)
        if k in k_old and k not in reused:
            continue
        if k[1] == econ_rules.ESSAY_NUMBER:
            note = 'эссе комплекта (в старой версии — во вступлении комплекта, продолжение терялось)'
        elif r.get('statement_from_solution_file'):
            note = 'условие только из файла ответов' + (
                '; в старой версии под этим ключом лежал повтор вопроса теста' if k in k_old else '')
        else:
            note = 'ключа не было' if k not in k_old else 'ключ занят другим заданием'
        out.append([set_name, '', '', '', *k, NEW, note])
    return out


def _old_rows(old, new, set_name, defect_kits, defect_targets, repeats, kit_notes):
    k_new = {key(r): r for r in new}
    by_old, by_new = defaultdict(list), defaultdict(list)
    for r in old:
        by_old[r['event_id']].append(r)
    for r in new:
        by_new[r['event_id']].append(r)
    rows, changed = [], {}
    for ev in sorted(set(by_old) | set(by_new)):
        a = {key(r) for r in by_old[ev]}
        b = {key(r) for r in by_new[ev]}
        if a != b:
            changed[ev] = (len(a), len(b))
        for r in by_old[ev]:
            k = key(r)
            if k in k_new and a == b:
                rows.append([set_name, *k, *k, SAME, kit_notes.get(ev, '')])
                continue
            if k in k_new and ((r.get('statement_md') or '') == (k_new[k].get('statement_md') or '')
                               or body(k_new[k])[:200] and fuzz.partial_ratio(
                                   body(r)[:200], body(k_new[k])) >= 85):
                rows.append([set_name, *k, *k, SAME, 'в комплекте удалены повторы, это задание — то же'
                             if repeats else 'комплект перенумерован, это задание — то же'])
                continue
            st = (r.get('statement_md') or '').replace('**', '')
            if econ_rules.is_rules_text(st, r.get('title') or '') or (
                    econ_rules.is_service_text(st, r.get('title') or '') and not r.get('answer')):
                rows.append([set_name, *k, '', '', '', SERVICE,
                             'текст — во вступлении комплекта или в начале условий раздела (section_md)'])
                continue
            if ev in defect_kits and k not in k_new:
                note = defect_kits[ev]
                target = defect_targets.get(ev) or ('', '', '')
                rows.append([set_name, *k, *target,
                             'удалено: ' + note.split(': ', 1)[1] if ': ' in note else 'удалено', note])
                continue
            # по тексту: задания новой версии того же комплекта того же варианта
            cands = [x for x in by_new[ev] if (x.get('task_variant') or '') == k[2]] or by_new[ev]
            if repeats:       # v6: у «тест-N» формулировка вопроса бывает в названии
                mine = plain(econ_rules.unmark(st))
                scored = sorted(((sim(mine, question(x)), key(x)) for x in cands
                                 if key(x) != k), reverse=True)
            else:
                scored = sorted(((sim(core(st), core(x.get('statement_md'))), key(x)) for x in cands),
                                reverse=True)
            if repeats and scored and scored[0][0] >= 75 and _is_repeat(r, scored[0][1]):
                rows.append([set_name, *k, *scored[0][1], REPEAT,
                             'ответ и решение — у этого вопроса (правило v6: повтор вопроса теста '
                             'в файле ответов)'])
                continue
            if scored and scored[0][0] >= 75:
                best = scored[0][1]
                note = 'сквозная нумерация блоков отборочного МОШ (дефект 1)'
                if len(plain(st)) > 1.6 * max(1, len(body(k_new[best]))):
                    note += ('; в v4 в это задание были слиты несколько вопросов разных блоков — '
                             'см. остальные задания v5 этого комплекта')
                rows.append([set_name, *k, *best, RENUMBERED, note])
            else:
                rows.append([set_name, *k, '', '', '', MISSING, 'см. отчёт'])
    return rows, changed
