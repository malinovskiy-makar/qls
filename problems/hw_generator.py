"""
Подбор домашки по описанию словами.

⚠️ МЫ НЕ ПРИДУМЫВАЕМ ЗАДАЧИ. Мы подбираем существующие из проверенного
каталога. Битая сгенерированная задача, выданная классу, стоит дороже, чем
вся функция приносит — это принятое решение проекта, и здесь оно ровно то
же самое: ИИ разбирает ФРАЗУ, а не сочиняет условия.

АРХИТЕКТУРА (главное, ради чего файл существует):
  1. ОДНО обращение к модели на всю домашку. Вход — вольный текст плюс
     параметры, выход — СТРУКТУРА: список строк «тема · сложность ·
     сколько задач». Обращение на каждую задачу было бы и дорого, и
     медленно, и незачем.
  2. Каждая строка структуры уходит в СУЩЕСТВУЮЩИЙ поиск по банку
     отдельным запросом. Это бесплатно: эмбеддинги посчитаны заранее.
  3. Результаты собираются в подборку с дедупликацией и разбросом по
     источникам.

Две вещи, без которых схема разваливается:
  * модель выбирает темы ИЗ ГОТОВОГО МЕНЮ 21 канонической темы. Иначе
    вернёт «микроэкономика рынков», под которую в банке ничего нет;
  * ДЕДУПЛИКАЦИЯ при сборке. Два запроса по монополии легко вернут одну
    задачу дважды, а поиск — пять задач подряд из одного сборника.
"""
import hashlib
import json
import logging
import os
import re
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

# Модель разбора — САМАЯ ДЕШЁВАЯ ИЗ ПОДХОДЯЩИХ. Задача простая: разложить
# фразу по готовому меню тем, никакой экономики модель не считает.
DEFAULT_MODEL = 'claude-haiku-4-5'
# Цена за миллион токенов, доллары. Держим здесь, а не в коде расчёта:
# тариф меняется, и он должен меняться в одном месте.
DEFAULT_PRICES = {'claude-haiku-4-5': (1.0, 5.0)}

# Потолок обращений в сутки на репетитора и время жизни кэша.
DEFAULT_DAILY_LIMIT = 30
DEFAULT_CACHE_SECONDS = 900

MAX_ROWS = 8          # больше строк в плане домашки не бывает осмысленно
MAX_PROBLEMS = 30     # верхняя граница числа задач в подборке


class GeneratorUnavailable(Exception):
    """Функция выключена или недоступна — сообщение уже человеческое."""


def _setting(name, default):
    return getattr(settings, name, default)


def api_key():
    """Ключ ТОЛЬКО из переменной окружения. Ни в коде, ни в репозитории."""
    return os.environ.get('ANTHROPIC_API_KEY', '').strip()


def is_available():
    """Можно ли пользоваться. Нет ключа — функция аккуратно выключена."""
    if not api_key():
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def unavailable_reason():
    if not api_key():
        return ('Подбор по описанию выключен: не задан ключ ANTHROPIC_API_KEY. '
                'Соберите домашку вручную — поиск и фильтры справа работают '
                'как обычно.')
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return ('Подбор по описанию выключен: на этом сервере не установлена '
                'библиотека anthropic. Соберите домашку вручную.')
    return ''


def canonical_topics():
    """21 каноническая тема — МЕНЮ, из которого выбирает модель."""
    from problems.management.commands.apply_topic_mapping import CANONICAL

    return list(CANONICAL)


# ---------------------------------------------------------------------------
# Шаг 1. Разбор запроса — ОДНО обращение к модели
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """Ты помогаешь репетитору по олимпиадной экономике собрать
домашнее задание из уже существующего банка задач.

Твоя работа — разложить его описание на строки плана. Ты НЕ придумываешь
задачи и НЕ пишешь условия: задачи потом найдутся в банке поиском.

Правила:
1. Тема каждой строки — СТРОГО из предложенного списка тем. Ничего своего
   не выдумывай: под выдуманную тему в банке ничего не найдётся.
2. Сложность — целое от 1 до 5.
3. Сумма задач по всем строкам должна равняться запрошенному числу задач.
4. Если репетитор просит «одну посложнее в конце» — сделай отдельную строку
   с большей сложностью и одной задачей, и поставь её последней.
5. `query` — короткая фраза для поиска по смыслу (по-русски, 3–8 слов),
   описывающая, о чём должны быть задачи этой строки.
6. Тем в плане не больше четырёх, строк не больше восьми."""

PLAN_SCHEMA = {
    'type': 'object',
    'properties': {
        'rows': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'topic': {'type': 'string'},
                    'difficulty': {'type': 'integer'},
                    'count': {'type': 'integer'},
                    'query': {'type': 'string'},
                },
                'required': ['topic', 'difficulty', 'count', 'query'],
                'additionalProperties': False,
            },
        },
        'note': {'type': 'string'},
    },
    'required': ['rows', 'note'],
    'additionalProperties': False,
}


def _cache_key(text, params):
    payload = json.dumps([text, sorted(params.items())], ensure_ascii=False,
                         sort_keys=True)
    return 'hwgen:' + hashlib.sha256(payload.encode('utf-8')).hexdigest()[:32]


def used_today(user):
    from .models import AiUsageLog

    start = timezone.localtime(timezone.now()).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return AiUsageLog.objects.filter(user=user, created_at__gte=start).count()


def daily_limit():
    return _setting('AI_GENERATOR_DAILY_LIMIT', DEFAULT_DAILY_LIMIT)


def parse_request(text, params, user):
    """Вольный текст → план домашки. ОДНО обращение к модели.

    Возвращает `{'rows': [...], 'note': str, 'usage': {...}, 'cached': bool}`.
    Бросает `GeneratorUnavailable` с человеческим текстом — белого экрана
    не бывает ни при какой ошибке.
    """
    if not is_available():
        raise GeneratorUnavailable(unavailable_reason())

    text = (text or '').strip()
    if not text:
        raise GeneratorUnavailable('Опишите домашку словами — по пустому '
                                   'описанию подбирать нечего.')

    key = _cache_key(text, params)
    cached = cache.get(key)
    if cached is not None:
        # Тот же запрос в пределах короткого времени не гоняем повторно.
        result = dict(cached)
        result['cached'] = True
        return result

    limit = daily_limit()
    if used_today(user) >= limit:
        raise GeneratorUnavailable(
            'На сегодня лимит обращений исчерпан (%d в сутки). Соберите '
            'домашку вручную или попробуйте завтра.' % limit)

    plan = _ask_model(text, params, user)
    cache.set(key, plan, _setting('AI_GENERATOR_CACHE_SECONDS',
                                  DEFAULT_CACHE_SECONDS))
    plan = dict(plan)
    plan['cached'] = False
    return plan


def _ask_model(text, params, user):
    import anthropic

    from .models import AiUsageLog

    model = _setting('AI_GENERATOR_MODEL', DEFAULT_MODEL)
    topics = canonical_topics()
    wanted = int(params.get('count') or 5)

    user_prompt = (
        'Список тем (выбирай ТОЛЬКО из него):\n'
        + '\n'.join('- ' + name for name in topics)
        + '\n\nПараметры от репетитора:\n'
        + '- всего задач: %d\n' % wanted
        + '- сложность: от %s до %s\n' % (params.get('min_difficulty') or 1,
                                          params.get('max_difficulty') or 5)
        + ('- заданные темы: %s\n' % ', '.join(params['topics'])
           if params.get('topics') else '')
        + '\nОписание домашки словами:\n' + text
    )

    client = anthropic.Anthropic(api_key=api_key())
    try:
        response = client.messages.create(
            model=model,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': user_prompt}],
            output_config={'format': {'type': 'json_schema',
                                      'schema': PLAN_SCHEMA}},
        )
    except anthropic.APIConnectionError:
        _log_usage(user, model, 0, 0, ok=False, note='нет сети')
        raise GeneratorUnavailable(
            'Не удалось связаться с сервисом разбора запроса. Проверьте сеть '
            'или соберите домашку вручную.')
    except anthropic.RateLimitError:
        _log_usage(user, model, 0, 0, ok=False, note='rate limit')
        raise GeneratorUnavailable(
            'Сервис разбора сейчас перегружен. Попробуйте через минуту или '
            'соберите домашку вручную.')
    except anthropic.APIStatusError as error:
        _log_usage(user, model, 0, 0, ok=False,
                   note='status %s' % error.status_code)
        raise GeneratorUnavailable(
            'Сервис разбора вернул ошибку (%s). Соберите домашку вручную.'
            % error.status_code)

    usage = _log_usage(user, model, response.usage.input_tokens,
                       response.usage.output_tokens)

    raw = ''.join(block.text for block in response.content
                  if block.type == 'text')
    try:
        data = json.loads(raw)
    except ValueError:
        raise GeneratorUnavailable(
            'Разбор запроса вернул неожиданный ответ. Попробуйте описать '
            'домашку иначе или соберите её вручную.')

    rows = _clean_rows(data.get('rows'), topics, params)
    if not rows:
        raise GeneratorUnavailable(
            'Из описания не удалось понять, какие темы нужны. Уточните '
            'описание или выберите темы в фильтрах.')
    return {'rows': rows, 'note': (data.get('note') or '').strip(),
            'usage': usage}


def _clean_rows(rows, topics, params):
    """Приводим ответ модели к тому, что мы умеем искать.

    ⚠️ Тему, которой нет в меню, НЕ выбрасываем молча и не подставляем
    наугад: пытаемся сопоставить по названию, а не совпало — отбрасываем
    строку. Придуманная тема всё равно ничего не найдёт.
    """
    by_lower = {name.lower(): name for name in topics}
    low = int(params.get('min_difficulty') or 1)
    high = int(params.get('max_difficulty') or 5)

    cleaned = []
    for row in (rows or [])[:MAX_ROWS]:
        if not isinstance(row, dict):
            continue
        name = str(row.get('topic') or '').strip()
        topic = by_lower.get(name.lower())
        if topic is None:
            for candidate in topics:
                if name and (name.lower() in candidate.lower()
                             or candidate.lower() in name.lower()):
                    topic = candidate
                    break
        if topic is None:
            continue
        try:
            difficulty = int(row.get('difficulty'))
            count = int(row.get('count'))
        except (TypeError, ValueError):
            continue
        difficulty = max(1, min(5, difficulty))
        # Границы сложности задал репетитор — модель их не переопределяет,
        # кроме «одной посложнее», которая всё равно упирается в потолок.
        difficulty = max(low, min(high, difficulty))
        count = max(1, min(MAX_PROBLEMS, count))
        cleaned.append({'topic': topic, 'difficulty': difficulty,
                        'count': count,
                        'query': str(row.get('query') or topic).strip()[:200]})
    return cleaned


def _log_usage(user, model, input_tokens, output_tokens, ok=True, note=''):
    from .models import AiUsageLog

    prices = _setting('AI_GENERATOR_PRICES', DEFAULT_PRICES)
    price_in, price_out = prices.get(model, DEFAULT_PRICES[DEFAULT_MODEL])
    cost = (Decimal(input_tokens) * Decimal(str(price_in))
            + Decimal(output_tokens) * Decimal(str(price_out))) / Decimal(10 ** 6)
    cost = cost.quantize(Decimal('0.000001'))
    try:
        AiUsageLog.objects.create(
            user=user, model_name=model, input_tokens=input_tokens,
            output_tokens=output_tokens, cost_usd=cost, ok=ok, note=note)
    except Exception:
        logger.exception('Не удалось записать расход на ИИ — основной '
                         'сценарий не тронут')
    return {'input_tokens': input_tokens, 'output_tokens': output_tokens,
            'cost_usd': float(cost), 'model': model}


# ---------------------------------------------------------------------------
# Шаг 2. Подбор задач — бесплатно, по уже посчитанным эмбеддингам
# ---------------------------------------------------------------------------

def find_problems(rows, has_solution=False, sources=None, exclude=()):
    """Каждая строка плана → свой поиск. Возвращает (найденное, пустые строки).

    ⚠️ ДЕДУПЛИКАЦИЯ И РАЗБРОС ПО ИСТОЧНИКАМ здесь, а не «как-нибудь потом».
    Два запроса по монополии вернут одну задачу дважды, а поиск любит
    отдавать подряд пять задач из одного сборника — на листке это видно
    сразу.
    """
    found = []
    taken = set(exclude)
    per_source = {}
    empty_rows = []

    for index, row in enumerate(rows):
        candidates = _search_row(row, has_solution=has_solution,
                                 sources=sources)
        picked = 0
        for problem in candidates:
            if picked >= row['count']:
                break
            if problem.pk in taken:
                continue
            source = _source_of(problem)
            # Не больше трёх задач подряд из одного источника на всю
            # подборку: иначе «домашка» превращается в кусок одного сборника.
            if source and per_source.get(source, 0) >= 3:
                continue
            taken.add(problem.pk)
            per_source[source] = per_source.get(source, 0) + 1
            found.append({'problem': problem, 'row': index})
            picked += 1
        if picked < row['count']:
            empty_rows.append({'row': index, 'missing': row['count'] - picked,
                               'topic': row['topic']})
    return found, empty_rows


def _source_of(problem):
    reference = problem.source_references.all()[:1]
    return reference[0].source_id if reference else None


def _search_row(row, has_solution=False, sources=None):
    """Кандидаты под одну строку плана.

    Сначала пробуем семантический поиск (эмбеддинги уже посчитаны, платить
    не за что). Модели нет на машине — честно откатываемся на фильтры и
    поиск по тексту: это хуже, но работает и ничего не выдумывает.
    """
    from problems.models import Problem

    limit = row['count'] * 6 + 6
    try:
        from catalog import semantic

        hits = semantic.search(row['query'], topic_id=_topic_id(row['topic']),
                               difficulty=row['difficulty'],
                               has_solution=has_solution, limit=limit)
        problems = [hit['problem'] for hit in hits]
        if problems:
            return _apply_filters(problems, sources)
    except Exception:
        logger.info('Семантический поиск недоступен — идём по фильтрам',
                    exc_info=True)

    queryset = Problem.objects.filter(status=Problem.Status.PUBLISHED,
                                      needs_quality_review=False)
    topic_id = _topic_id(row['topic'])
    if topic_id:
        queryset = queryset.filter(topics__id=topic_id)
    if row['difficulty']:
        queryset = queryset.filter(difficulty=row['difficulty'])
    if has_solution:
        queryset = queryset.exclude(solution='')
    words = [w for w in re.split(r'\W+', row['query']) if len(w) > 4][:2]
    if words:
        from django.db.models import Q

        condition = Q()
        for word in words:
            condition |= Q(statement__icontains=word)
        queryset = queryset.filter(condition)
    problems = list(queryset.prefetch_related('topics', 'source_references')
                    .order_by('?')[:limit])
    if not problems and topic_id:
        problems = list(
            Problem.objects.filter(status=Problem.Status.PUBLISHED,
                                   needs_quality_review=False,
                                   topics__id=topic_id)
            .prefetch_related('topics', 'source_references')
            .order_by('?')[:limit])
    return _apply_filters(problems, sources)


def _apply_filters(problems, sources):
    if not sources:
        return problems
    allowed = {int(s) for s in sources if str(s).isdigit()}
    if not allowed:
        return problems
    return [p for p in problems
            if any(r.source_id in allowed for r in p.source_references.all())]


def _topic_id(name):
    from problems.models import Topic

    topic = Topic.objects.filter(name=name).first()
    return topic.pk if topic else None
