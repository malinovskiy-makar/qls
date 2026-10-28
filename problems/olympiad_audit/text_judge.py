# -*- coding: utf-8 -*-
"""Судья-модель над парами «задача банка ↔ официальное задание» (ночь 28.10.2026).

Два вопроса, оба — одной думающей модели (Claude, `claude-sonnet-5-5`):

* **замена** (решение 28.10 «…если официальный текст полнее задачи банка —
  заменяем текст банка официальным…»): у пары `link` модель сравнивает
  официальный текст, картинки страниц PDF и текст задачи банка и отвечает
  JSON `{replace, missing, reasons, evidence, confidence}`. Менять —
  только при `replace` и `confidence ≥ 0,8`; задачу, одобренную человеком,
  — только при структурной потере (таблица, варианты, пункты, рисунок).
  Запись — `apply_official_text` (снимок в `ProblemVersion`, журнал, откат);
* **сомнительная пара** (2.7): то же задание или другое — `{same:
  same|different|unsure, evidence, confidence}`. Ответ превращается в строку
  разметки `link_review_decisions.json` (`decided_by = claude:<модель>`);
  её применяет `import_olympiad_reference --decisions`. «Не уверен» и
  уверенность ниже порога — `unsure`, то есть на проверку человеку.

Наружу уходят только тексты заданий олимпиады, задачи банка и картинки
страниц PDF — данных учеников в них нет (решение 14.10 о Claude и
олимпиадах). Вызов модели — `call_model`; тесты подменяют его.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import datetime

MODEL = 'claude-sonnet-5-5'
#: $ за миллион токенов (вход, выход) — сверено 28.10.2026 (skill claude-api, кэш 06.10).
PRICES = {'claude-sonnet-5-5': (2.0, 10.0)}
#: Message Batches — половина цены за все токены.
BATCH_DISCOUNT = 0.5
#: Глубина размышления: medium — сверка двух текстов, не олимпиадное решение.
EFFORT = 'medium'
#: С размышлением вывод длиннее самого JSON — запас, чтобы ответ не обрезался.
MAX_TOKENS = 8000
MISSING_KINDS = ('text', 'table', 'options', 'parts', 'figure', 'numbers')
STRUCTURAL = frozenset({'table', 'options', 'parts', 'figure'})
REPLACE_MIN_CONFIDENCE = 0.8
PAIR_MIN_CONFIDENCE = 0.85
MAX_PAGES = 4

REPLACE_SYSTEM = (
    'Ты сверяешь задачу из банка сайта с официальным текстом той же задачи олимпиады '
    '(расшифровка PDF организатора; картинки страниц PDF приложены). Реши, не хватает ли '
    'в версии банка чего-то существенного по сравнению с официальной: куска текста '
    'условия, таблицы, вариантов ответа, пунктов, рисунка, чисел. Косметика (пробелы, '
    'разметка, кавычки, нумерация, порядок фраз) — не повод. Если версия банка — '
    'намеренная адаптация (другие числа, другой сюжет) или официальная расшифровка сама '
    'хуже банка — replace=false. Каждую причину подтверди дословной цитатой из PDF '
    '(evidence). Ответь строго одним JSON-объектом без пояснений: {"replace": true|false, '
    '"missing": [подмножество ["text","table","options","parts","figure","numbers"]], '
    '"reasons": "коротко по-русски", "evidence": ["дословная цитата", ...], '
    '"confidence": число от 0 до 1}.')

PAIR_SYSTEM = (
    'Ты сверяешь официальное задание олимпиады (расшифровка PDF организатора, картинки '
    'страниц приложены) с задачей из банка сайта. Это та же задача (тот же сюжет и те же '
    'данные, возможно с другой разметкой или неполная копия), другая задача (другой '
    'сюжет, другие числа, переделка) или нельзя сказать уверенно? Подтверди ответ '
    'дословными цитатами из обоих текстов. Ответь строго одним JSON-объектом без '
    'пояснений: {"same": "same"|"different"|"unsure", "evidence": ["цитата", ...], '
    '"reasons": "коротко по-русски", "confidence": число от 0 до 1}.')


# ── Тексты и картинки ─────────────────────────────────────────────────────

def official_text(fields, row):
    """Официальное задание текстом: условие, пункты, ответ, решение."""
    out = [f'УСЛОВИЕ:\n{fields["statement"]}']
    for p in fields.get('parts') or []:
        out.append(f'ПУНКТ {p["label"]}: {p["statement_md"]}')
    if (row.get('answer') or '').strip():
        out.append(f'ОТВЕТ: {row["answer"]}')
    return '\n\n'.join(out)


def bank_text(problem):
    out = [f'ЗАГОЛОВОК: {problem.title}', f'УСЛОВИЕ:\n{problem.statement}']
    for p in problem.parts.order_by('order', 'id'):
        out.append(f'ПУНКТ {p.label}: {p.statement}')
    if (problem.answer or '').strip():
        out.append(f'ОТВЕТ: {problem.answer}')
    return '\n\n'.join(out)


_HASH_CACHE = {}


def _file_hash16(path):
    if path not in _HASH_CACHE:
        h = hashlib.sha256()
        with open(path, 'rb') as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b''):
                h.update(chunk)
        _HASH_CACHE[path] = h.hexdigest()[:16]
    return _HASH_CACHE[path]


def page_images(row, subdir, digitized_dir, limit=MAX_PAGES):
    """PNG страниц условия: `digitized/pages/<sha256(pdf)[:16]>/p<N>.png`."""
    out = []
    for ref in row.get('source_pages') or []:
        if '#p' not in ref:
            continue
        rel, page = ref.rsplit('#p', 1)
        pdf = os.path.join(subdir, rel)
        if not os.path.isfile(pdf):
            continue
        png = os.path.join(digitized_dir, 'pages', _file_hash16(pdf), f'p{page}.png')
        if os.path.isfile(png) and png not in out:
            out.append(png)
        if len(out) >= limit:
            break
    return out


def _image_block(path):
    with open(path, 'rb') as handle:
        data = base64.b64encode(handle.read()).decode('ascii')
    return {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png', 'data': data}}


def build_content(official, bank, images):
    content = [_image_block(p) for p in images]
    content.append({'type': 'text', 'text': f'=== ОФИЦИАЛЬНЫЙ ТЕКСТ ===\n{official}\n\n'
                                            f'=== ЗАДАЧА БАНКА ===\n{bank}'})
    return content


# ── Вызов модели ──────────────────────────────────────────────────────────

def cost_of(model, usage, batch=False):
    pin, pout = PRICES.get(model, (2.0, 10.0))
    usd = ((usage.get('input_tokens') or 0) * pin
           + (usage.get('cache_creation_input_tokens') or 0) * pin * 1.25
           + (usage.get('cache_read_input_tokens') or 0) * pin * 0.1
           + (usage.get('output_tokens') or 0) * pout) / 1e6
    return usd * BATCH_DISCOUNT if batch else usd


def request_params(system, content, model=MODEL, max_tokens=MAX_TOKENS):
    """Тело запроса Messages. `temperature` не шлём: у Sonnet 5.5 значение не по
    умолчанию — ошибка 400 (а с версии API 2026-10-21 — у всех моделей)."""
    return {'model': model, 'max_tokens': max_tokens, 'system': system,
            'output_config': {'effort': EFFORT},
            'messages': [{'role': 'user', 'content': content}]}


def client():
    """Клиент Claude. Ключ из окружения `ANTHROPIC_API_KEY`; ключ без привязки к
    рабочему пространству требует `ANTHROPIC_WORKSPACE_ID` (заголовок
    `anthropic-workspace-id`)."""
    import anthropic
    headers = {}
    if os.environ.get('ANTHROPIC_WORKSPACE_ID'):
        headers['anthropic-workspace-id'] = os.environ['ANTHROPIC_WORKSPACE_ID']
    return anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'),
                               default_headers=headers or None, max_retries=4)


def _usage(message):
    u = message.usage
    return u.model_dump() if hasattr(u, 'model_dump') else dict(u)


def reply_text(message):
    """Текст ответа; обрезанный по max_tokens или отказ — ошибка, а не пустой JSON."""
    if message.stop_reason in ('max_tokens', 'refusal'):
        raise ValueError(f'stop_reason={message.stop_reason}')
    return ''.join(getattr(b, 'text', '') for b in message.content if b.type == 'text')


def call_model(system, content, model=MODEL, max_tokens=MAX_TOKENS):
    """(текст ответа, usage) — один синхронный вызов Messages API."""
    reply = client().messages.create(**request_params(system, content, model, max_tokens))
    return reply_text(reply), _usage(reply)


def submit_batch(requests):
    """requests: [(custom_id, params)] → id пакета Message Batches."""
    batch = client().messages.batches.create(
        requests=[{'custom_id': cid, 'params': params} for cid, params in requests])
    return batch.id


def batch_status(batch_id):
    b = client().messages.batches.retrieve(batch_id)
    return b.processing_status, b.request_counts.model_dump() if hasattr(b.request_counts, 'model_dump')         else dict(b.request_counts)


def batch_results(batch_id):
    """{custom_id: (текст, usage) | исключение} — результаты в любом порядке, ключ — custom_id."""
    out = {}
    # Клиент держим в переменной: временный объект закрывает сокет посреди потока результатов.
    api = client()
    for item in api.messages.batches.results(batch_id):
        res = item.result
        if res.type == 'succeeded':
            try:
                out[item.custom_id] = (reply_text(res.message), _usage(res.message))
            except ValueError as error:
                out[item.custom_id] = error
        else:
            out[item.custom_id] = RuntimeError(f'пакет: {res.type} '
                                               f'{getattr(getattr(res, "error", None), "type", "")}')
    return out


def parse_json(text):
    t = (text or '').strip()
    a, b = t.find('{'), t.rfind('}')
    if a < 0 or b <= a:
        raise ValueError('в ответе нет JSON')
    return json.loads(t[a:b + 1])


# ── Разбор ответов и правила ─────────────────────────────────────────────

def parse_replace(text):
    data = parse_json(text)
    missing = [m for m in data.get('missing') or [] if m in MISSING_KINDS]
    conf = float(data.get('confidence') or 0)
    if not 0 <= conf <= 1:
        raise ValueError(f'confidence вне 0..1: {conf}')
    return {'replace': bool(data.get('replace')), 'missing': missing,
            'reasons': str(data.get('reasons') or '')[:500],
            'evidence': [str(e) for e in data.get('evidence') or []][:10], 'confidence': conf}


def replace_decision(verdict, human_approved):
    """(менять?, почему). Правило решения 28.10 и 2.1 ночи."""
    if not verdict.get('replace'):
        return False, 'судья: замена не нужна'
    if verdict.get('confidence', 0) < REPLACE_MIN_CONFIDENCE:
        return False, f'уверенность {verdict.get("confidence")} < {REPLACE_MIN_CONFIDENCE}'
    if not verdict.get('evidence'):
        return False, 'нет цитат из PDF'
    if human_approved and not (set(verdict.get('missing') or []) & STRUCTURAL):
        return False, 'задача одобрена человеком, потеря не структурная'
    return True, 'замена: ' + ', '.join(verdict.get('missing') or []) + ' — ' + verdict.get('reasons', '')


def parse_pair(text):
    data = parse_json(text)
    same = data.get('same')
    if same not in ('same', 'different', 'unsure'):
        raise ValueError(f'same={same!r}')
    conf = float(data.get('confidence') or 0)
    return {'same': same, 'evidence': [str(e) for e in data.get('evidence') or []][:10],
            'reasons': str(data.get('reasons') or '')[:500], 'confidence': conf}


def pair_decision(verdict):
    """Ответ судьи → решение разметки: link / new / unsure."""
    if verdict['same'] == 'unsure' or verdict['confidence'] < PAIR_MIN_CONFIDENCE \
            or not verdict['evidence']:
        return 'unsure'
    return 'link' if verdict['same'] == 'same' else 'new'


def human_approved(problem):
    """Одобрена человеком (а не автопубликацией импорта)."""
    from problems.models import Problem, ReviewVerdict
    if problem.human_review != Problem.HumanReview.APPROVED:
        return False
    return ReviewVerdict.objects.filter(problem=problem).exclude(reviewer__startswith='auto:').exists()


def stamp():
    return datetime.now().strftime('%Y%m%d_%H%M%S')
