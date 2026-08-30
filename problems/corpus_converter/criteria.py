# -*- coding: utf-8 -*-
"""Школково: criteria_tex (проза, структурированная по \\textbf{(метка)} +
\\begin{itemize}) -> кандидат Rubric/RubricCriterion.

Единственный источник банка со структурными критериями (CORPUS-FORMAT.md
§3: "маппинг в Rubric берётся даром" у 836 задач Школково) — но баллы
внутри каждого \\item всё равно нужно вытащить из русской прозы
("3 балла за ...", "1 балл за ..."), это и есть менее тривиальная часть,
явно выделенная спекой в отдельный файл."""
from __future__ import annotations

import re

from problems.corpus_converter.core import convert_text_field

#: «Критериев нет» — так это записано у самого источника (110 задач из
#: 836 с формально непустым `criteria_tex`). Считать их неудачей парсера
#: значит завышать объём непокрытого.
_CRITERIA_NONE_RE = re.compile(r'\A\s*%\s*criteria:\s*none\s*\Z')

#: Заголовок пункта. Прежняя версия знала ровно одну форму —
#: `\textbf{(метка)}` вплотную перед `\begin{itemize}`. Свип по 836
#: непустым `criteria_tex` показал, что это меньшинство: те же критерии
#: пишутся ещё `\subsection*{(а)}` и `\textbf{Пункт (а)} (6 баллов):`.
_PART_HEADER_RE = re.compile(
    r'\\(?:textbf|textit|section|subsection|subsubsection|paragraph)\*?\s*'
    r'\{([^{}]*)\}')
#: Метка внутри заголовка: буква или цифра со скобкой. Именно она
#: отличает ЗАГОЛОВОК ПУНКТА от обычного жирного текста внутри критерия
#: (`\textbf{Штрафы:}`, `\textit{Примечание:}`) — без этой проверки
#: разбиение резало бы пункты пополам.
#: Скобка слева бывает круглой и квадратной (`[А)] Определите…`, живой
#: #167105), буква — и строчной, и прописной.
_PART_LABEL_RE = re.compile(r'(?:\A|[\s(\[])([а-яёА-ЯЁa-zA-Z0-9]{1,2})\)')

#: Список любого рода: `itemize` и `enumerate` разбираются одинаково.
#: Границы ищутся СЧЁТЧИКОМ вложенности, а не нежадным `(.*?)`: у 43 из
#: 362 разобранных задач списки вложены, и `(.*?)` закрывал внешний
#: список на `\end` ВНУТРЕННЕГО — в имя критерия попадал сырой
#: `\begin{itemize}` (живой #167105).
_LIST_TOKEN_RE = re.compile(r'\\(begin|end)\{(?:itemize|enumerate)\}')
_ITEM_OR_LIST_RE = re.compile(
    r'\\(begin|end)\{(?:itemize|enumerate)\}|\\item\b')

#: Баллы «в начале пункта»: «3 балла за ...», «по 1 баллу за ...».
_POINTS_RE = re.compile(r'\A\s*(?:по\s+)?(\d+(?:[.,]\d+)?)[~\s]*(?:балл\w*|б\.)')
#: Баллы где угодно в пункте: у самой частой формы семейства они стоят в
#: КОНЦЕ — «Расчет прибыли ... ~--- 2 балла» (живой #167118).
_POINTS_ANY_RE = re.compile(r'(\d+(?:[.,]\d+)?)[~\s]*(?:балл\w*|б\.)')


def _split_by_part_headers(criteria_tex):
    """`[(метка, тело), ...]` — границы по ЗАГОЛОВКАМ, а не жадным захватом.

    Тот же урок, что у парсера SolveHub (#3498): жадный захват «от
    заголовка до конца» приписывал критерии соседнему пункту."""
    headers = []
    for match in _PART_HEADER_RE.finditer(criteria_tex):
        label_match = _PART_LABEL_RE.search(match.group(1))
        if label_match:
            headers.append((match.start(), match.end(),
                            f'({label_match.group(1)})'))
    if not headers:
        return [('', criteria_tex)]
    blocks = []
    for index, (_start, end, label) in enumerate(headers):
        stop = headers[index + 1][0] if index + 1 < len(headers) else len(criteria_tex)
        blocks.append((label, criteria_tex[end:stop]))
    return blocks


def _points_of(raw_item):
    """Баллы пункта: сначала в начале, потом где угодно. Нет — None."""
    match = _POINTS_RE.match(raw_item) or _POINTS_ANY_RE.search(raw_item)
    if match is None:
        return None
    return float(match.group(1).replace(',', '.'))


def _list_spans(text):
    """`[(начало_\\begin, начало_тела, конец_тела)]` списков ВЕРХНЕГО уровня."""
    spans = []
    depth = 0
    opened_at = body_at = 0
    for match in _LIST_TOKEN_RE.finditer(text):
        if match.group(1) == 'begin':
            if depth == 0:
                opened_at, body_at = match.start(), match.end()
            depth += 1
        elif depth:
            depth -= 1
            if depth == 0:
                spans.append((opened_at, body_at, match.start()))
    return spans


def _top_level_items(body):
    """Куски по `\\item` ВЕРХНЕГО уровня — вложенный список не режется."""
    marks = []
    depth = 0
    for match in _ITEM_OR_LIST_RE.finditer(body):
        if match.group(1) is None:
            if depth == 0:
                marks.append((match.start(), match.end()))
        elif match.group(1) == 'begin':
            depth += 1
        elif depth:
            depth -= 1
    items = []
    for index, (_start, end) in enumerate(marks):
        stop = marks[index + 1][0] if index + 1 < len(marks) else len(body)
        items.append(body[end:stop])
    return items


def _label_from(text):
    """Метка пункта из заголовка, или None."""
    match = _PART_LABEL_RE.search(text or '')
    return f'({match.group(1)})' if match else None


def _collect(body, label, criteria, warnings):
    """Пройти тело списка, собрать критерии. Рекурсивно по вложенным.

    Внешний `\\item`, внутри которого лежит ещё список, — это ЗАГОЛОВОК
    пункта, а не критерий: его собственный текст даёт метку, а баллы
    берутся из вложенных пунктов. Иначе баллы считались бы дважды."""
    for item in _top_level_items(body):
        nested = _list_spans(item)
        if nested:
            heading = item[:nested[0][0]]
            for _begin, start, end in nested:
                _collect(item[start:end], _label_from(heading) or label,
                         criteria, warnings)
            continue
        raw_item = item.strip()
        if not raw_item:
            continue
        max_points = _points_of(raw_item)
        if max_points is None:
            warnings.append(
                f'критерий без баллов в прозе: {label} — {raw_item[:60]}')
        description = convert_text_field(raw_item)['text_md']
        criteria.append({
            'name': f'{label} {description}'.strip(),
            'max_points': max_points,
            'description': description,
            'order': len(criteria),
        })


def parse_shkolkovo_criteria(criteria_tex):
    """criteria_tex -> {'rubric_name', 'criteria': [...], 'warnings': [...]}.

    ⚠️ Разбираются ТОЛЬКО настоящие списки (`itemize`/`enumerate`).
    Свободная проза с баллами («Выставлялось по 5 баллов за каждый верный
    аргумент…», ~360 задач) НЕ разбивается на критерии: где кончается
    один и начинается другой, из текста не следует, и разбиение было бы
    выдуманным, а не импортированным знанием. Такая задача остаётся без
    рубрики и получает предупреждение."""
    if not criteria_tex:
        return {'rubric_name': 'Критерии оценивания', 'criteria': [], 'warnings': []}
    if _CRITERIA_NONE_RE.match(criteria_tex):
        return {'rubric_name': 'Критерии оценивания', 'criteria': [], 'warnings': []}

    criteria = []
    warnings = []

    for label, body in _split_by_part_headers(criteria_tex):
        for _begin, start, end in _list_spans(body):
            _collect(body[start:end], label, criteria, warnings)

    if not criteria:
        warnings.append(
            f'criteria_tex непустой ({len(criteria_tex)} симв.), но списка '
            f'(itemize/enumerate) в нём нет — критерии написаны прозой, '
            f'разбиение на пункты не выводится из текста'
        )

    return {'rubric_name': 'Критерии оценивания', 'criteria': criteria, 'warnings': warnings}


#: SolveHub (атлас: критерии вклеены в answer_md прозой, слово «критери*» у
#: 26 задач, схема «+N баллов» у 41). Заголовок — устойчиво слово «Критерии»
#: в именительном падеже (например «***Критерии****:*») ИЛИ «Критерии
#: проверки»/«Критерии оценивания...» — но НЕ любая словоформа: живой пример
#: #3609 использует «критериям» (дательный падеж, обычная экономическая
#: лексика про ранжирование вузов, не про баллы) — точное слово исключает
#: этот класс ложных срабатываний. Остаточный риск задокументирован ниже.
_SOLVEHUB_CRITERIA_HEADER_RE = re.compile(r'(?i)\bкритерии\b')
#: Пункт — либо "N)", либо "-" в начале строки, перед которыми может стоять
#: markdown-звёздочка (разметка в источнике хаотична: "*1)  Дан ответ...",
#: "*-Если нет..." — живые примеры #6371/#6347).
_SOLVEHUB_ITEM_RE = re.compile(
    r'(?:^|\n)\s*\*?\s*(?:(\d+)\)|-)\s*(.*?)(?=\n\s*\*?\s*(?:\d+\)|-)|\Z)',
    re.DOTALL,
)
#: Баллы — знаковое число внутри $...$, за которым (возможно, через
#: markdown-звёздочку) следует «балл»/«балла»/«баллов». Скобки вокруг НЕ
#: обязательны — у #6347 баллы идут без скобок ("$-15$ баллов").
_SOLVEHUB_POINTS_RE = re.compile(r'\$\s*([+-]?\d+(?:[.,]\d+)?)\s*\$\s*\*?\s*балл')


def parse_solvehub_criteria(answer_md):
    """answer_md -> {'rubric_name', 'criteria': [...], 'warnings': [...]}.

    Известное ограничение: парсер уверенно распознаёт только пункты вида
    «N)»/«-» с баллами в $...$. Остальные форматы (сплошная проза без
    пунктов, схема «- $N$ **балл**» без $-обёртки числа) дают 0 критериев
    для своего раздела с явным предупреждением — молчания на непонятном
    формате нет. Слово «Критерии» изредка встречается не как заголовок
    баллов, а как обычный термин (пример #5578: «Критерии оптимума для
    функций полезности...») — такой случай тоже даёт пустой список с
    предупреждением, ложного извлечения баллов из математики он не
    совершает.

    Дефект, найденный ревью 2026-08-26 (задача #3498 — three-part answer,
    "1) ... 2) ... 3) ..." с ТРЕМЯ отдельными разделами «Критерии», по
    одному на часть): раньше искали только ПЕРВЫЙ заголовок «Критерии» и
    сканировали пункты до КОНЦА всего answer_md — regex «N)» цеплял
    границы следующих частей ответа ("2)", "3)") как будто это пункты
    критериев, а настоящие (неномерованные, прозой) критерии части 1
    терялись без единого warning. Починка в две части:
    1. Обрабатываются ВСЕ заголовки «Критерии» (через finditer), каждый —
       в границах до СЛЕДУЮЩЕГО заголовка (не до конца строки).
    2. Если первый найденный номер последовательности "N)" внутри раздела
       — не "1" (значит распознали границу ЧАСТИ ответа, а не пункт
       критерия — настоящие критерии всегда начинаются с "1)"), раздел
       НЕ разбирается вовсе — лучше честный warning, чем чужой текст в
       описании критерия.
    Плюс отдельная страховка после всех разделов: любое "N баллов" в
    прозе, не попавшее в текст ни одного извлечённого критерия, поднимает
    предупреждение — так неномерованные критерии части 1 задачи #3498
    (раньше терялись молча) теперь как минимум видны в отчёте."""
    if not answer_md:
        return {'rubric_name': 'Критерии оценивания', 'criteria': [], 'warnings': []}

    headers = list(_SOLVEHUB_CRITERIA_HEADER_RE.finditer(answer_md))
    if not headers:
        return {'rubric_name': 'Критерии оценивания', 'criteria': [], 'warnings': []}

    criteria = []
    warnings = []
    order = 0
    claimed_spans = []

    for i, header in enumerate(headers):
        region_end = headers[i + 1].start() if i + 1 < len(headers) else len(answer_md)
        tail = answer_md[header.end():region_end]

        items = list(_SOLVEHUB_ITEM_RE.finditer(tail))
        numbered = [m for m in items if m.group(1)]
        if numbered and numbered[0].group(1) != '1':
            warnings.append(
                f'заголовок «Критерии» найден, но следующие "N)" похожи на границы частей '
                f'ответа, а не на пункты критериев (первая метка "{numbered[0].group(1)})", '
                f'не "1)") — раздел пропущен, нужен ручной разбор'
            )
            continue

        found_any = False
        for item_match in items:
            raw_item = item_match.group(2).strip()
            if not raw_item:
                continue
            points_match = _SOLVEHUB_POINTS_RE.search(raw_item)
            if points_match:
                max_points = float(points_match.group(1).replace(',', '.'))
            else:
                max_points = None
                warnings.append(f'критерий без баллов в прозе: {raw_item[:60]}')
            description = convert_text_field(raw_item)['text_md']
            criteria.append({
                'name': description[:80],
                'max_points': max_points,
                'description': description,
                'order': order,
            })
            order += 1
            found_any = True
            claimed_spans.append((header.end() + item_match.start(), header.end() + item_match.end()))

        if not found_any:
            warnings.append(
                f'заголовок «Критерии» найден ({len(tail)} симв. до следующего раздела/конца), '
                f'но не распознано ни одного пункта вида «N)» или «-» с баллами в $...$'
            )

    for points_match in _SOLVEHUB_POINTS_RE.finditer(answer_md):
        if any(start <= points_match.start() < end for start, end in claimed_spans):
            continue
        snippet = answer_md[max(0, points_match.start() - 20):points_match.end() + 60]
        warnings.append(
            f'баллы в прозе вне извлечённых критериев (возможна частичная потеря): '
            f'"...{snippet}..."'
        )

    return {'rubric_name': 'Критерии оценивания', 'criteria': criteria, 'warnings': warnings}
