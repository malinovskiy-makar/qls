# -*- coding: utf-8 -*-
"""ВсОШ v2 (сессия Q2, фаза 4): второй проход Claude Opus по флагам ЗЭ и РЭ.

Метод P2 (`claude_recheck` ветки `feat/olympiad-v7` — образец, не импортируется):
по каждой позиции с флагом проверки v1 модель видит картинки страниц задания
(и соседние — уменьшенными), текущие поля эталона и флаги и решает: «верно»,
«исправить» (полный новый текст поля) или «человеку». Принимается только при
уверенности ≥ 0,9 и с дословной цитатой, найденной в текстовом слое показанных
страниц; правка — ещё и без чисел, которых нет ни на страницах, ни в старом
тексте, и без урезания условия. 0,75–0,9 — повтор с effort `high`.

Пишет только файлы в `digitized\\v2\\q2\\recheck\\`; эталон v1 не трогает.
"""
from __future__ import annotations

import json
import os
import re

from problems.olympiad_audit import transcribe
from problems.olympiad_audit import vsosh_verify as vv

MODEL = 'claude-opus-5-5'
MAX_FULL = 4
NEIGHBOR_SIDE = 1000
FIX_FIELDS = ('statement_md', 'title', 'answer', 'solution_md', 'criteria_md', 'parts')
#: Флаги, которые разбирает второй проход. «тест_без_ключа» в одиночку — фаза 3.
FLAG_NOTES = {
    'числа_не_со_страницы': 'в условии эталона есть числа, которых нет в текстовом слое страницы: {nums}',
    'расходится_со_слоем': 'текст эталона заметно расходится со страницей (пропуск или лишний текст)',
    'тест_без_вариантов': 'вопрос теста без вариантов ответа — проверь, есть ли варианты на странице',
    'тест_без_ключа': 'у вопроса теста нет ответа — если ключ виден на страницах, дай answer',
    'нет_решения': 'у задачи нет решения и критериев, хотя у комплекта есть файл решений',
    'пустое_условие': 'условие пустое',
    'пункты_не_разобраны': 'в условии есть пункты а), б)…, но они не разобраны в parts',
    'скан_на_глаза': 'страница-скан без текстового слоя — сверь текст с картинкой целиком',
    'рисунок_плохая_вырезка': 'вырезка рисунка плохая (рисунок обрезан или лишнее)',
    'рисунок_лишний_текст': 'в вырезке рисунка — чужой текст',
    'расхождение_с_ILE': 'текст расходится с оцифровкой ILE',
    'katex': 'формула в эталоне исправлена правилом (непарная \\right / экранирование) — проверь формулу по картинке',
}
SKIP_ONLY = {'тест_без_ключа'}
INFO = {'ключа_нет_в_источнике'}

SYSTEM = """Ты — второй, строгий проверяющий оцифровки олимпиадных заданий по экономике (Всероссийская олимпиада, заключительный и региональный этапы). Первый проход (модель Claude Sonnet) переписал страницы PDF в эталон, автоматическая проверка поставила заданию флаги. Твоя задача — по картинкам страниц решить, верна ли версия эталона, и если нет — исправить.

Тебе даны картинки: «проверяемые» страницы задания (и страницы решений, если есть) — в полном размере, «соседние» (предыдущая и следующая) — уменьшенные, для контекста: задание может начинаться или продолжаться на соседней странице. Дано: текущие поля задания (current), флаги и их смысл.

Решения (поле decision):
- "fix" — исправить: в fixes дай ПОЛНЫЙ исправленный текст каждого исправляемого поля (statement_md, title, answer, solution_md, criteria_md — строкой; parts — полным списком [{"label": …, "text": …}]). Только поля этого задания.
- "keep" — менять ничего не надо: текущий текст верен, флаг ложный (например, числа есть на картинке, но слой PDF их потерял; решения у этой задачи в источнике действительно нет).
- "human" — по этим страницам надёжно не решить (нужного текста на страницах нет, страница нечитаема, надо разбивать задание на несколько).

ПРАВИЛА:
1. Переписывай ДОСЛОВНО, как на картинке. Опечатки авторов — как в оригинале. Ничего не решай, не досочиняй, не добавляй ответов, которых нет на странице.
2. Исправляй только то, что ВИДНО на страницах.
3. Колонтитулы, номера страниц, водяные знаки в текст не идут.
4. Разметка: Markdown; формулы — TeX внутри $…$ (KaTeX); знак доллара в тексте — \\$; таблицы — markdown-таблицами; варианты ответа — списком, по строке на вариант, с исходными буквами/цифрами.
5. Принятая разметка эталона — НЕ дефект: пункты стоят и в statement_md, и в parts; вступление своего раздела в начале условия теста; «(отмечено)» у варианта в решении теста.
6. evidence — ОБЯЗАТЕЛЬНО: дословная цитата со страницы (несколько слов подряд, как напечатано), которая доказывает решение.
7. confidence — от 0 до 1. 0.9 и выше — только если уверен полностью; сомневаешься — "human".

Ответ — ТОЛЬКО JSON, без текста вокруг:
{"decision": "fix"|"keep"|"human", "fixes": {…}, "evidence": "…", "why": "коротко", "confidence": 0.95}"""


def flags_of(r):
    return sorted(set(r.get('check_flags') or []) - INFO)


def needs_recheck(r):
    """Позиция второго прохода: ЗЭ/РЭ, есть флаг, и это не только «нет ключа»
    (ключи — фаза 3), плюс формулы, исправленные правилом P3."""
    if r.get('stage') not in ('final', 'regional'):
        return False
    f = set(flags_of(r))
    if r.get('math_star_unescaped'):
        f.add('katex')
    return bool(f - SKIP_ONLY)


def item_flags(r):
    f = flags_of(r)
    if r.get('math_star_unescaped') and 'katex' not in f:
        f.append('katex')
    return f


def ref_page(index, ref):
    """«файл.pdf#pN» → (page_dir, N) по индексу рендера."""
    pdf, _, page = ref.rpartition('#p')
    pd = index.get(pdf)
    return (pd, int(page)) if pd and page.isdigit() else None


def solution_candidates(r, ev, jobs, limit=2):
    """Для «нет_решения» без страниц решения: страницы файлов решений
    комплекта, где в слое стоит заголовок этой задачи."""
    num = re.escape(str(r.get('number') or ''))
    if not num:
        return []
    pat = re.compile(rf'(?im)(?:задач\w*|задани\w*|№)\s*{num}\b|^\s*{num}\s*[.)]')
    out = []
    for key in ('solution_files', 'criteria_files'):
        for f in ev.get(key) or []:
            for p in range(1, int(f.get('pages') or 0) + 1):
                job = jobs.get(f"{f['page_dir']}/p{p}")
                if job and pat.search(job.layer or ''):
                    out.append((f['page_dir'], p))
    return out[:limit]


def item_pages(r, ev, index, jobs):
    """→ (полноразмерные [(page_dir, N)], соседние [(page_dir, N)])."""
    full = []
    for ref in (r.get('source_pages') or []) + (r.get('solution_pages') or []) + \
            (r.get('criteria_pages') or []):
        x = ref_page(index, ref)
        if x and x not in full:
            full.append(x)
    if 'нет_решения' in item_flags(r) and not (r.get('solution_pages') or r.get('criteria_pages')):
        for x in solution_candidates(r, ev, jobs):
            if x not in full:
                full.append(x)
    full = full[:MAX_FULL]
    near = []
    for pd, p in full[:1] + full[-1:]:
        for n in (p - 1, p + 1):
            if (pd, n) not in full and (pd, n) not in near and f'{pd}/p{n}' in jobs:
                near.append((pd, n))
    return full, near[:2]


def current_fields(r):
    out = {k: r.get(k) for k in FIX_FIELDS if r.get(k)}
    return out


def request_params(r, full, near, root, effort='medium', max_tokens=16000):
    content = []
    for i, (pd, p) in enumerate(full, 1):
        mt, data = vv.image_b64(os.path.join(root, pd, f'p{p}.png'))
        content += [{'type': 'text', 'text': f'Проверяемая страница {i}: {pd}/p{p}'},
                    {'type': 'image', 'source': {'type': 'base64', 'media_type': mt, 'data': data}}]
    for pd, p in near:
        mt, data = vv.image_b64(os.path.join(root, pd, f'p{p}.png'), NEIGHBOR_SIDE)
        content += [{'type': 'text', 'text': f'Соседняя страница (уменьшена): {pd}/p{p}'},
                    {'type': 'image', 'source': {'type': 'base64', 'media_type': mt, 'data': data}}]
    notes = [FLAG_NOTES.get(f, f).format(nums=', '.join(r.get('numbers_not_on_page') or []))
             for f in item_flags(r)]
    text = (f'Задание: {r["event_id"]}, № {r["number"]}'
            + (f', вариант {r["task_variant"]}' if r.get('task_variant') else '') + '.\n'
            'Флаги проверки:\n- ' + '\n- '.join(notes) + '\n\ncurrent:\n'
            + json.dumps(current_fields(r), ensure_ascii=False))
    content.append({'type': 'text', 'text': text})
    return {'model': MODEL, 'max_tokens': max_tokens,
            'system': [{'type': 'text', 'text': SYSTEM, 'cache_control': {'type': 'ephemeral'}}],
            'output_config': {'effort': effort},
            'messages': [{'role': 'user', 'content': content}]}


#: Новый текст условия короче этой доли старого — урезание, человеку.
MIN_KEEP_SHARE = 0.5


def judge(reply_text, r, layers):
    """Ответ Opus → (итог, правки | None, причины, данные). Итоги: `keep`,
    `fix`, `retry` (0,75–0,9), `human`."""
    data = transcribe.tolerant_parse(reply_text)
    dec = str(data.get('decision') or '').strip()
    try:
        conf = float(data.get('confidence') or 0)
    except (TypeError, ValueError):
        conf = 0.0
    if dec not in ('fix', 'keep', 'human'):
        return 'human', None, ['ответ_не_разобран'], data
    if dec == 'human':
        return 'human', None, ['модель: человеку'], data
    layer = '\n'.join(layers)
    why = []
    if not vv.evidence_on_page(data.get('evidence'), layer):
        why.append('нет_цитаты_со_страницы')
    if conf < vv.MIN_CONFIDENCE:
        why.append(f'уверенность_{conf:.2f}')
    fixes = None
    if dec == 'fix':
        raw = data.get('fixes') if isinstance(data.get('fixes'), dict) else {}
        fixes = {k: v for k, v in raw.items() if k in FIX_FIELDS and v not in (None, '')}
        if not fixes:
            why.append('правка_пустая')
        page_nums = set(vv.numbers(layer)) if len(layer.strip()) >= vv.MIN_LAYER else None
        for k, v in fixes.items():
            text = json.dumps(v, ensure_ascii=False) if k == 'parts' else str(v)
            old = json.dumps(r.get(k), ensure_ascii=False) if k == 'parts' else str(r.get(k) or '')
            if page_nums is not None and set(vv.numbers(text)) - page_nums - set(vv.numbers(old)):
                why.append(f'числа_не_со_страницы:{k}')
            if k == 'statement_md' and len(text) < MIN_KEEP_SHARE * len(old):
                why.append('урезание_условия')
    if why:
        if why == [f'уверенность_{conf:.2f}'] and vv.RETRY_CONFIDENCE[0] <= conf < vv.RETRY_CONFIDENCE[1]:
            return 'retry', None, why, data
        return 'human', None, why, data
    return dec, fixes, [], data
