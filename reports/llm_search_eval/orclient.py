# -*- coding: utf-8 -*-
"""Клиент офлайн-замера поверх прямых провайдеров.

Здесь живёт всё, чего НЕТ и не должно быть в поставщике: счётчик потолка
по каждому провайдеру, повторы с паузой, журнал отказов и терпимый разбор
ответа. Поставщики остаются тонкими и одинаковыми между собой — см.
докстринги `DeepSeekProvider` и `OpenRouterProvider`.

⚠️ ПОСРЕДНИКА БОЛЬШЕ НЕТ. С 10.09.2026 работаем с четырьмя прямыми
провайдерами: OpenAI, Anthropic, Z.ai, DeepSeek. `OpenRouterProvider` в
коде оставлен, но не используется.

Ничего не пишет в базу. Пишет только два файла: `costs.json` (счётчик) и
`failures.jsonl` (журнал отказов).
"""
import json
import os
import re
import time
from datetime import datetime, timezone

#: ПРЯМЫЕ прайсы провайдеров, $ за миллион токенов: (вход, выход).
#: Сняты со страниц тарифов 10.09.2026. Кэш префикса в СМЕТЕ не
#: учитывается — указание владельца: кэш экономит, но полагаться на него
#: при планировании потолка нельзя.
#:
#: ⚠️ У DeepSeek цена зависит от ЧАСА: в пик (01:00–04:00 и 06:00–10:00
#: UTC по будням) она вдвое выше. Здесь лежит НЕ пиковая; множитель
#: накладывает `price_of_tokens`.
PRICES = {
    ('zai', 'glm-5.3-flash'): (0.15, 0.50),
    ('zai', 'glm-5.3'): (1.40, 4.40),
    ('anthropic', 'claude-haiku-4-5'): (1.00, 5.00),
    ('anthropic', 'claude-sonnet-5'): (2.00, 10.00),
    ('openai', 'gpt-5.6-sol'): (4.00, 20.00),
    ('openai', 'gpt-5.6-terra'): (2.00, 12.00),
    ('deepseek', 'deepseek-v4-pro'): (0.66, 1.98),
    ('deepseek', 'deepseek-flash'): (0.15, 0.60),
}

#: Цена чтения из кэша, $ за млн. В смету не входит, но ФАКТИЧЕСКИЙ расход
#: считается по ней: провайдер уже применил скидку, и делать вид, что кэша
#: не было, значит завышать счётчик и упереться в потолок раньше времени.
CACHE_READ_PRICES = {
    ('zai', 'glm-5.3-flash'): 0.03,
    ('zai', 'glm-5.3'): 0.26,
    ('anthropic', 'claude-haiku-4-5'): 0.10,
    ('anthropic', 'claude-sonnet-5'): 0.20,
    ('openai', 'gpt-5.6-sol'): 0.40,
    ('openai', 'gpt-5.6-terra'): 0.20,
    ('deepseek', 'deepseek-v4-pro'): 0.022,
    ('deepseek', 'deepseek-flash'): 0.003,
}

#: Потолки по провайдерам: у каждого свой баланс, общего кошелька нет.
BUDGETS = {'openai': 19.0, 'deepseek': 5.0, 'zai': 12.5, 'anthropic': 9.5}

#: Пик DeepSeek: часы UTC (начало включительно, конец нет) по будням.
DEEPSEEK_PEAK_HOURS = ((1, 4), (6, 10))
PEAK_MULTIPLIER = 2.0

ATTEMPTS = 3
#: Паузы между попытками: 2 с, затем 4 с. После последней паузы нет.
BACKOFF_BASE = 2


class BudgetExceeded(RuntimeError):
    """Вызов не ушёл: он не помещается в остаток потолка СВОЕГО провайдера."""


def is_peak(moment=None):
    """Идёт ли сейчас пиковый тариф DeepSeek.

    Будни по UTC, 01:00–04:00 и 06:00–10:00. В пик и вход, и выход стоят
    вдвое, поэтому вызовы судьи планируются вне этих окон.
    """
    moment = moment or datetime.now(timezone.utc)
    if moment.weekday() >= 5:      # суббота и воскресенье всегда вне пика
        return False
    hour = moment.hour + moment.minute / 60.0
    return any(start <= hour < end for start, end in DEEPSEEK_PEAK_HOURS)


def price_of_tokens(provider, model, input_tokens, output_tokens,
                    cache_read_tokens=0, peak=None):
    """Стоимость по прямому прайсу провайдера, $."""
    price_in, price_out = PRICES.get((provider, model), (0.0, 0.0))
    price_cache = CACHE_READ_PRICES.get((provider, model), price_in * 0.1)
    if provider == 'deepseek':
        peak = is_peak() if peak is None else peak
        if peak:
            price_in *= PEAK_MULTIPLIER
            price_out *= PEAK_MULTIPLIER
            price_cache *= PEAK_MULTIPLIER
    return (input_tokens * price_in + output_tokens * price_out
            + cache_read_tokens * price_cache) / 1e6


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
        # ⚠️ Обёртка «rows» — не каприз, а следствие строгого режима
        # OpenAI: объект с ПРОИЗВОЛЬНЫМИ ключами ({"12": 2}) в
        # json_schema со `strict: true` не выразить вовсе, там каждое
        # свойство надо перечислить заранее. Поэтому судей и реранкеров
        # просят отвечать {"rows": [{"id": …, "score": …}]}, одинаково у
        # всех четырёх провайдеров: разные формы ответа у разных моделей
        # означали бы разный разбор и разные ошибки.
        rows = data.get('rows')
        if isinstance(rows, list):
            return _as_object(rows)
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
    """Один вызов = проверка потолка провайдера, до трёх попыток, учёт.

    Потолок у КАЖДОГО провайдера свой: деньги лежат на четырёх разных
    счетах, и исчерпание одного не повод останавливать вызовы к другому.
    Общего кошелька у сессии нет, поэтому нет и общего потолка.
    """

    def __init__(self, providers, costs_path, failures_path, budgets,
                 sleep=time.sleep):
        self.providers = dict(providers)
        self.costs_path = costs_path
        self.failures_path = failures_path
        self.budgets = dict(budgets)
        self.sleep = sleep
        self.costs = self._load_costs()
        self.spent = {name: self.costs['by_provider'].get(name, {}).get('usd', 0.0)
                      for name in self.budgets}

    # -- расход ----------------------------------------------------------
    def _load_costs(self):
        if os.path.exists(self.costs_path):
            with open(self.costs_path, encoding='utf-8') as handle:
                costs = json.load(handle)
            costs.setdefault('by_provider', {})
            return costs
        return {'total_usd': 0.0, 'calls': 0, 'by_stage': {}, 'by_provider': {}}

    def _save_costs(self):
        os.makedirs(os.path.dirname(self.costs_path) or '.', exist_ok=True)
        with open(self.costs_path, 'w', encoding='utf-8') as handle:
            json.dump(self.costs, handle, ensure_ascii=False, indent=1)

    def price_of(self, provider, model, reply):
        """Стоимость вызова: слово провайдера сильнее нашей копии прайса.

        Прямые провайдеры цену в ответе не присылают — её называл только
        посредник. Обычный путь здесь прайс; ветка с `cost_usd` оставлена
        ради `OpenRouterProvider`, который в коде остался.
        """
        if reply.cost_usd is not None:
            return float(reply.cost_usd)
        return price_of_tokens(provider, model, reply.input_tokens,
                               reply.output_tokens, reply.cache_read_tokens)

    def _record(self, stage, provider, model, reply, cost):
        # ⚠️ ПЕРЕЧИТЫВАЕМ ФАЙЛ ПЕРЕД ЗАПИСЬЮ. Прогоны идут в разных
        # процессах одновременно: пакетный судья ждёт OpenAI часами, а
        # рядом работают сортировщики. Процесс, державший свою копию с
        # начала работы, переписывал файл целиком и стирал чужой расход —
        # 10.09.2026 так молча исчезли $4,36 обоих сортировщиков.
        # Перечитывание не делает запись атомарной, но окно сужается с
        # часов до миллисекунд, а деньги перестают теряться классом.
        self.costs = self._load_costs()
        by_model = self.costs['by_stage'].setdefault(stage, {})
        row = by_model.setdefault(model, {'usd': 0.0, 'calls': 0,
                                          'input': 0, 'output': 0,
                                          'cache_read': 0, 'reasoning': 0})
        prov = self.costs['by_provider'].setdefault(
            provider, {'usd': 0.0, 'calls': 0})
        for target in (row, prov):
            target['usd'] += cost
            target['calls'] += 1
        row['input'] += reply.input_tokens
        row['output'] += reply.output_tokens
        row['cache_read'] += reply.cache_read_tokens
        row['reasoning'] += reply.reasoning_tokens
        self.costs['total_usd'] += cost
        self.costs['calls'] += 1
        self.spent[provider] = prov['usd']
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
    def remaining(self, provider):
        """Сколько ещё можно потратить у этого провайдера."""
        return self.budgets.get(provider, 0.0) - self.spent.get(provider, 0.0)

    def call(self, stage, query_id, provider, model, system_blocks, user_text,
             schema, max_tokens, timeout=None, estimated_usd=0.0):
        spent = self.spent.get(provider, 0.0)
        ceiling = self.budgets.get(provider, 0.0)
        if spent + float(estimated_usd) > ceiling:
            raise BudgetExceeded(
                'Потолок провайдера %s исчерпан: потрачено $%.4f, вызов '
                'оценён в $%.4f, потолок $%.2f. Это остановка, а не '
                '«доделать чуть-чуть».'
                % (provider, spent, estimated_usd, ceiling))

        last = None
        for attempt in range(1, ATTEMPTS + 1):
            try:
                reply = self.providers[provider].complete(
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
            self._record(stage, provider, model, reply,
                         self.price_of(provider, model, reply))
            return reply
        raise last
