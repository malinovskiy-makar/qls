# -*- coding: utf-8 -*-
"""ВсОШ v2 (сессия Q2, фаза 3): ключи тестов из сеток ответов.

В файлах ответов МЭ/РЭ ключ теста часто нарисован сеткой: столбец — номер
вопроса, строка — вариант, отметка — в клетке («| 1 | 2 | 3 |» и ниже «**3)**»
в нужной строке). Сборка P3 такие ключи не разобрала (нумерация разделов
начинается заново, ключ стоит в таблице критериев) — 1 916 вопросов
«тест_без_ключа».

Метод (как у P2 — две модели разных семейств): каждая модель видит картинки
страниц ответов и список вопросов теста комплекта (наш id, начало текста,
варианты с исходными метками) и возвращает «id → ответ». Ключ принимается,
только если ответы двух моделей совпали после нормализации И ответ входит в
варианты своего вопроса (инвариант фазы 3). Иначе — очередь людям.
"""
from __future__ import annotations

import json
import re

#: Метка варианта: «1)», «а)», «А.», «(б)», в начале строки или пункта списка.
_OPT = re.compile(r'(?m)^\s*(?:[-*+]\s+)?\(?([а-еёa-eА-ЕA-E]|[1-9])[.)]\s+(\S.*)$')
_PLAIN = re.compile(r'(?m)^\s*[-*+]\s+(\S.*)$')
#: «Верно / неверно», «да / нет» — двоичный вопрос; варианты могут не печататься.
_BINARY = {'да': 'да', 'верно': 'да', 'нет': 'нет', 'неверно': 'нет'}
_LAT2CYR = str.maketrans({'a': 'а', 'b': 'б', 'c': 'в', 'd': 'г', 'e': 'д'})


def norm_label(x):
    """«3)», «**3)**», «В.», «(в)», «Б» → «3», «в», «в», «б». Латинские a–e
    читаются как русские а–д (модели путают раскладку на сканах)."""
    t = re.sub(r'[*_`()\[\].:;\s]', '', str(x or '')).lower().replace('ё', 'е')
    t = _BINARY.get(t, t)
    if len(t) == 1 and t in 'abcde':
        t = t.translate(_LAT2CYR)
    return t


#: «1) верно», «б. спрос» — метка с текстом варианта: берём метку.
_LEAD = re.compile(r'^\(?([а-еёa-eА-ЕA-E]|[1-9])[.)]\s*\S.*$')


def norm_answer(ans):
    """Ответ модели → отсортированный кортеж меток: «1, 3», «1;3», [1, 3], «13»
    (у вопросов «выберите все верные» метки пишут слитно) — всё в (1, 3)."""
    if isinstance(ans, list):
        items = ans
    else:
        s = str(ans or '').strip()
        if norm_label(s) in ('да', 'нет'):
            return (norm_label(s),)
        items = re.split(r'[,;/\s]+|\bи\b', s)
        if len(items) == 1 and re.fullmatch(r'[1-9]{2,6}', items[0]):
            items = list(items[0])
    out = sorted({norm_label(_LEAD.sub(r'\1', str(x).strip())) for x in items
                  if norm_label(x)})
    return tuple(out)


def options(statement):
    """Варианты вопроса → [(метка, текст)]. Без меток, простым списком —
    метки по порядку «1», «2»… Двоичный вопрос без вариантов — («да», «нет»)."""
    st = statement or ''
    labeled = [(norm_label(a), b.strip()) for a, b in _OPT.findall(st)]
    if len(labeled) >= 2:
        return labeled
    plain = [m.strip() for m in _PLAIN.findall(st)]
    if len(plain) >= 2:
        if all(norm_label(p) in ('да', 'нет') for p in plain):
            return [(norm_label(p), p) for p in plain]
        return [(str(i), p) for i, p in enumerate(plain, 1)]
    return [('да', 'да / верно'), ('нет', 'нет / неверно')]


def options_printed(statement):
    """Напечатаны ли варианты у вопроса (иначе `options` подставил «да/нет»
    по умолчанию — ключ по такому вопросу сам не принимается)."""
    st = statement or ''
    return len(_OPT.findall(st)) >= 2 or len(_PLAIN.findall(st)) >= 2


def answer_in_options(ans, opts):
    """Инвариант: каждая метка ответа есть среди меток вариантов вопроса."""
    labels = {lab for lab, _t in opts}
    return bool(ans) and all(a in labels for a in ans)


KEY_SYSTEM = """Ты читаешь КЛЮЧ ответов к тесту олимпиады по экономике со страниц файла ответов. Ключ бывает сеткой (столбцы — номера вопросов, строки — варианты; правильный отмечен знаком, буквой, цифрой, жирным, закрашенной клеткой), таблицей «номер — ответ», строкой «1 – 3); 2 – 2)» или вопросами с отмеченным вариантом.

Тебе дан список вопросов теста (id, раздел, начало текста, варианты с исходными метками). Нумерация на странице ключа может начинаться заново в каждом разделе — сопоставляй по разделам и порядку, сверяясь с текстом вопросов.

Для каждого вопроса верни ответ МЕТКАМИ его вариантов, как они даны в списке (например "3", "б", "да"); если верных несколько — все метки списком. Если в ключе ответ буквой или цифрой по порядку (А, Б… при вариантах «Да / Нет»), переведи его в метку варианта на том же месте. Вопрос с открытым ответом (число, слово) — ответ строкой, как напечатан в ключе. Если ключа к вопросу на страницах нет или клетку нельзя прочитать надёжно — answer: null. Ничего не решай сам: только то, что напечатано в ключе.

Ответ — ОДИН JSON-объект без текста вокруг:
{"answers": [{"id": "q1", "answer": ["3"], "confidence": 0.95, "where": "раздел 2, столбец 1"}]}"""


def question_list(rows):
    """Вопросы теста комплекта для модели: id — номер строки в комплекте."""
    out = []
    for i, r in enumerate(rows, 1):
        st = r.get('statement_md') or ''
        out.append({'id': f'q{i}', 'number': str(r.get('number')),
                    'text': re.sub(r'\s+', ' ', st)[:220],
                    'options': [f'{lab}) {t[:60]}' for lab, t in options(st)]})
    return out


def parse_reply(text):
    """Ответ модели → {id: (кортеж меток | None, уверенность)}."""
    from problems.olympiad_audit import transcribe
    data = transcribe.tolerant_parse(text)
    out = {}
    for a in data.get('answers') or [] if isinstance(data.get('answers'), list) else []:
        if not isinstance(a, dict) or not a.get('id'):
            continue
        try:
            conf = float(a.get('confidence') or 0)
        except (TypeError, ValueError):
            conf = 0.0
        ans = a.get('answer')
        out[str(a['id'])] = (norm_answer(ans) if ans not in (None, '', []) else None, conf)
    return out


#: Ниже этой уверенности ответ модели не считается (даже при совпадении).
MIN_KEY_CONFIDENCE = 0.8


def decide(rows, reply_a, reply_b):
    """Сведение двух моделей → [(строка, ответ | None, причина)]. Принято —
    причина пустая: обе модели дали одно и то же, уверенно, и ответ среди
    вариантов вопроса."""
    out = []
    for i, r in enumerate(rows, 1):
        qid = f'q{i}'
        a, ca = reply_a.get(qid, (None, 0.0))
        b, cb = reply_b.get(qid, (None, 0.0))
        opts = options(r.get('statement_md') or '')
        if a is None or b is None:
            why = 'нет_ответа_модели'
        elif a != b:
            why = 'модели_разошлись'
        elif min(ca, cb) < MIN_KEY_CONFIDENCE:
            why = 'низкая_уверенность'
        elif not answer_in_options(a, opts):
            why = 'ответ_не_среди_вариантов'
        elif not options_printed(r.get('statement_md') or ''):
            why = 'варианты_не_напечатаны'
        else:
            out.append((r, a, ''))
            continue
        out.append((r, None, why))
    return out


def answer_text(ans, opts):
    """Принятый ключ → строка `answer` эталона: «3)», «1), 3)», «Да», «б»."""
    labels = dict(opts)
    if ans in (('да',), ('нет',)):
        return 'Да' if ans == ('да',) else 'Нет'
    style = ')' if any(re.match(r'^\d$', lab) for lab in labels) else ''
    return ', '.join(f'{a}{style}' for a in ans)


def to_json(x):
    return json.dumps(x, ensure_ascii=False)
