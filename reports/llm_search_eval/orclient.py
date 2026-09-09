# -*- coding: utf-8 -*-
"""Клиент офлайн-замера поверх OpenRouterProvider.

Здесь живёт всё, чего НЕТ и не должно быть в поставщике: жёсткий счётчик
бюджета, повторы с паузой, журнал отказов и терпимый разбор ответа.
Поставщик остаётся тонким и одинаковым со своими четырьмя соседями —
см. докстринг `OpenRouterProvider`.

Ничего не пишет в базу. Пишет только два файла: `costs.json` (счётчик) и
`failures.jsonl` (журнал отказов).
"""
import json
import os
import re
import time
from datetime import datetime, timezone

#: Цены OpenRouter, $ за миллион токенов: (вход, выход).
#: Сняты с GET /api/v1/models 09.09.2026. Используются ТОЛЬКО когда
#: посредник не прислал `usage.cost` — своя копия чужих цен устаревает
#: молча, поэтому она запасной путь, а не основной.
PRICES = {
    'z-ai/glm-5.3-flash': (0.075, 0.25),
    'z-ai/glm-5.3': (1.40, 4.40),
    'anthropic/claude-haiku-4.5': (1.00, 5.00),
    'anthropic/claude-sonnet-5': (2.00, 10.00),
    'openai/gpt-5.6-sol': (2.00, 10.00),
    'openai/gpt-5.6-terra': (2.00, 12.00),
    'deepseek/deepseek-v4-pro': (0.87, 1.74),
}

ATTEMPTS = 3
#: Паузы между попытками: 2 с, затем 4 с. После последней попытки паузы нет.
BACKOFF_BASE = 2


class BudgetExceeded(RuntimeError):
    """Вызов не ушёл: он не помещается в остаток бюджета сессии."""


def load_env_file(path, env):
    """Прочитать `.env` в словарь окружения, НЕ перетирая заданное.

    ⚠️ Django этот файл не читает вовсе (`config/settings.py` берёт всё из
    `os.environ`). Ключ, положенный владельцем в `.env`, сам собой в
    процесс не попадёт — поэтому загрузка здесь, в коде замера, а не в
    продуктовом слое: поставщик по-прежнему знает только `os.environ`.

    Уже заданная переменная сильнее файла: если ключ выставлен в
    оболочке осознанно, файл не должен его молча подменять.
    """
    if not os.path.exists(path):
        return env
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            name, _, value = line.partition('=')
            name, value = name.strip(), value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
                value = value[1:-1]
            if name and name not in env:
                env[name] = value
    return env


# ─── Разбор ответа ────────────────────────────────────────────────────────

_FENCE = re.compile(r'^\s*```(?:json)?\s*|\s*```\s*$')
_ID_KEYS = ('id', 'problem_id', 'задача')
_VALUE_KEYS = ('score', 'verdict', 'label', 'value', 'rating', 'балл', 'оценка')


def _strip_fence(text):
    return _FENCE.sub('', text.strip())


def _as_object(data):
    """Массив записей → объект {id: значение}.

    Модель просят ответить объектом, но она регулярно отвечает списком
    вида [{"id": 12, "score": 2}, ...]. Терять из-за формы обёртки целую
    пачку из 25 или 50 кандидатов нельзя — run2 видел это живьём.
    """
    if isinstance(data, dict):
        return data
    if not isinstance(data, list):
        raise ValueError('Ответ не объект и не массив: %r' % type(data))
    out = {}
    for item in data:
        if not isinstance(item, dict):
            raise ValueError('Элемент массива не объект: %r' % (item,))
        key = next((item[k] for k in _ID_KEYS if k in item), None)
        value = next((item[k] for k in _VALUE_KEYS if k in item), None)
        if key is None or value is None:
            raise ValueError('В элементе нет пары «id — значение»: %r' % (item,))
        out[str(key)] = value
    return out


def _repair_truncated(text):
    """Обрезанный JSON → самый длинный разбираемый префикс.

    Обрыв на середине пачки — это потеря последнего кандидата, а не всей
    пачки. Режем по последней запятой верхнего уровня и закрываем скобку.
    """
    if not text or text[0] not in '{[':
        raise ValueError('Не похоже на JSON: %r' % text[:60])
    closing = '}' if text[0] == '{' else ']'
    depth, in_string, escaped, cuts = 0, False, False, []
    for i, ch in enumerate(text):
        if escaped:
            escaped = False
            continue
        if ch == '\\':
            escaped = True
        elif ch == '"':
            in_string = not in_string
        elif not in_string:
            if ch in '{[':
                depth += 1
            elif ch in '}]':
                depth -= 1
            elif ch == ',' and depth == 1:
                cuts.append(i)
    for cut in reversed(cuts):
        try:
            return json.loads(text[:cut] + closing)
        except ValueError:
            continue
    raise ValueError('JSON не восстановить: %r' % text[:60])


def parse_json_object(text):
    """Ответ модели → словарь. Терпит массив, обрезку и ``` ``` обрамление.

    Пустой словарь НЕ возвращается при неудаче: он читался бы как
    «модель всё сочла негодным», а это другое утверждение, чем «ответ не
    разобран». Неудача — исключение.
    """
    if not text or not text.strip():
        raise ValueError('Пустой ответ модели')
    body = _strip_fence(text)
    try:
        return _as_object(json.loads(body))
    except ValueError:
        return _as_object(_repair_truncated(body))


# ─── Клиент ───────────────────────────────────────────────────────────────

class Client(object):
    """Один вызов = проверка бюджета, до трёх попыток, запись расхода."""

    def __init__(self, provider, costs_path, failures_path, budget_usd,
                 sleep=time.sleep):
        self.provider = provider
        self.costs_path = costs_path
        self.failures_path = failures_path
        self.budget_usd = float(budget_usd)
        self.sleep = sleep
        self.costs = self._load_costs()
        self.spent = self.costs['total_usd']

    # -- расход ----------------------------------------------------------
    def _load_costs(self):
        if os.path.exists(self.costs_path):
            with open(self.costs_path, encoding='utf-8') as handle:
                return json.load(handle)
        return {'total_usd': 0.0, 'calls': 0, 'by_stage': {}}

    def _save_costs(self):
        os.makedirs(os.path.dirname(self.costs_path) or '.', exist_ok=True)
        with open(self.costs_path, 'w', encoding='utf-8') as handle:
            json.dump(self.costs, handle, ensure_ascii=False, indent=1)

    def price_of(self, model, reply):
        """Стоимость вызова: слово посредника сильнее нашей копии прайса."""
        if reply.cost_usd is not None:
            return float(reply.cost_usd)
        price_in, price_out = PRICES.get(model, (0.0, 0.0))
        full_input = reply.input_tokens + reply.cache_read_tokens
        return (full_input * price_in + reply.output_tokens * price_out) / 1e6

    def _record(self, stage, model, reply, cost):
        by_model = self.costs['by_stage'].setdefault(stage, {})
        row = by_model.setdefault(model, {'usd': 0.0, 'calls': 0,
                                          'input': 0, 'output': 0,
                                          'cache_read': 0, 'reasoning': 0})
        row['usd'] += cost
        row['calls'] += 1
        row['input'] += reply.input_tokens
        row['output'] += reply.output_tokens
        row['cache_read'] += reply.cache_read_tokens
        row['reasoning'] += reply.reasoning_tokens
        self.costs['total_usd'] += cost
        self.costs['calls'] += 1
        self.spent = self.costs['total_usd']
        self._save_costs()

    # -- журнал отказов ---------------------------------------------------
    def _log_failure(self, stage, query_id, model, attempt, error, will_retry):
        original = getattr(error, 'original', None)
        row = {
            'ts': datetime.now(timezone.utc).isoformat(),
            'stage': stage,
            'query_id': query_id,
            'model': model,
            'attempt': attempt,
            'http_status': getattr(original, 'status_code', None),
            'error': '%s: %s' % (type(error).__name__, error),
            'will_retry': will_retry,
        }
        os.makedirs(os.path.dirname(self.failures_path) or '.', exist_ok=True)
        with open(self.failures_path, 'a', encoding='utf-8') as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
            handle.flush()
            os.fsync(handle.fileno())

    # -- вызов -------------------------------------------------------------
    def call(self, stage, query_id, model, system_blocks, user_text, schema,
             max_tokens, timeout=None, estimated_usd=0.0):
        if self.spent + float(estimated_usd) > self.budget_usd:
            raise BudgetExceeded(
                'Бюджет сессии исчерпан: потрачено $%.4f, вызов оценён в '
                '$%.4f, потолок $%.2f. Это остановка, а не «доделать '
                'чуть-чуть».' % (self.spent, estimated_usd, self.budget_usd))

        last = None
        for attempt in range(1, ATTEMPTS + 1):
            try:
                reply = self.provider.complete(
                    system_blocks=system_blocks, user_text=user_text,
                    schema=schema, model=model, max_tokens=max_tokens,
                    timeout=timeout)
            except Exception as error:                      # noqa: BLE001
                will_retry = attempt < ATTEMPTS
                # ⚠️ Журнал ПЕРЕД паузой: иначе обрыв процесса во время
                # ожидания стирает причину отказа. Урок run2.
                self._log_failure(stage, query_id, model, attempt, error,
                                  will_retry)
                last = error
                if not will_retry:
                    break
                self.sleep(BACKOFF_BASE ** attempt)
                continue
            self._record(stage, model, reply, self.price_of(model, reply))
            return reply
        raise last
