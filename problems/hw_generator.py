"""
Подбор домашки по описанию словами: ПОИСК ПЕРВЫЙ, МОДЕЛЬ ВТОРАЯ.

⚠️ МЫ НЕ ПРИДУМЫВАЕМ ЗАДАЧИ. Мы подбираем существующие из проверенного
каталога. Битая сгенерированная задача, выданная классу, стоит дороже, чем
вся функция приносит.

⚠️ МОДЕЛЬ НЕ ДОЛЖНА ЗНАТЬ ЭКОНОМИКУ — И НЕ ЗНАЕТ. Живой запрос показал, во
что обходится обратное: на фразу «домашка на КПВ и КТВ» модель написала
«КТВ — альтернативное название КПВ», выдала всем трём строкам одну тему, а
тема работала жёстким фильтром — пул схлопнулся, и вместо пяти задач
нашлось три. КТВ — это кривая ТОРГОВЫХ возможностей, отдельное понятие из
международной торговли.

Вывод, ради которого файл переписан: подтем в олимпиадной экономике сотни,
перечислить их в промпте невозможно, и попытка это сделать и есть источник
ошибок. Словарь предметной области у нас уже есть, и он полный — это сами
31 500 задач каталога. Поэтому порядок теперь такой:

  1. ФРАЗА ЦЕЛИКОМ уходит в поиск ДО всякой модели (`catalog.hybrid`:
     смысл + слова). Тот же поиск, ничего не зная про КТВ, нашёл задачу
     «КТВ двух стран при торговле» — то есть банк знает то, чего не знает
     модель.
  2. Найденные задачи (названия и темы) показываются модели как СЛОВАРЬ.
     Он строится сам и обновляется вместе с каталогом: добавили задачи по
     новой подтеме — она сразу в подсказках, руками никто ничего не пишет.
  3. Модель режет фразу на строки, ВИДЯ этот материал. Обращение
     по-прежнему РОВНО ОДНО на домашку.
  4. Каждая строка ищет себе задачи. Тема больше НЕ фильтр — только
     подсказка ранжированию. Квота заполняется всегда.
"""
import logging

from problems import ai
from problems.text_clean import clean, preview_title

logger = logging.getLogger(__name__)

# Оставлено ради обратной совместимости: вьюхи и тесты ловят эту ошибку.
GeneratorUnavailable = ai.AiUnavailable

MAX_ROWS = 8          # больше строк в плане домашки не бывает осмысленно
MAX_PROBLEMS = 30     # верхняя граница числа задач в подборке
HINT_COUNT = 12       # сколько реальных задач показываем модели словарём
# Потолок «не больше N задач из одного источника». Именно ПОТОЛОК, а не
# запрет: если из-за него не набирается квота, он отступает (см. ниже).
SOURCE_CAP = 3

PLAN_SCHEMA = {
    'type': 'object',
    'properties': {
        'rows': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'label': {'type': 'string'},
                    'query': {'type': 'string'},
                    'topic': {'type': 'string'},
                    'difficulty': {'type': 'integer'},
                    'count': {'type': 'integer'},
                },
                'required': ['label', 'query', 'topic', 'difficulty', 'count'],
                'additionalProperties': False,
            },
        },
        'note': {'type': 'string'},
    },
    'required': ['rows', 'note'],
    'additionalProperties': False,
}


def is_available():
    return ai.is_available()


def unavailable_reason():
    return ai.unavailable_reason()


def used_today(user):
    return ai.used_today(user)


def daily_limit():
    return ai.daily_limit()


def canonical_topics():
    """21 каноническая тема — подсказка модели, а НЕ фильтр выдачи."""
    from problems.management.commands.apply_topic_mapping import CANONICAL

    return list(CANONICAL)


# ---------------------------------------------------------------------------
# Шаг 1. Поиск — ДО модели
# ---------------------------------------------------------------------------

def search_hints(text, limit=HINT_COUNT):
    """Реальные задачи банка по фразе целиком — словарь для модели.

    ⚠️ Это НЕ примеры для подражания и не заготовка ответа. Это словарь:
    по названиям и темам видно, какими словами в ЭТОМ банке называют то,
    что просит репетитор. Заводить такой словарь руками бессмысленно —
    он устареет в тот день, когда в каталог добавят новую подтему.
    """
    from catalog import hybrid
    from problems.models import Problem

    hits = hybrid.search(text, limit=limit)
    if not hits:
        return []
    problems = {p.pk: p for p in Problem.objects.filter(
        pk__in=[hit['id'] for hit in hits]).prefetch_related('topics')}
    hints = []
    for hit in hits:
        problem = problems.get(hit['id'])
        if problem is None:
            continue
        hints.append({
            'title': preview_title(problem, limit=80),
            'topics': [t.name for t in problem.topics.all()
                       if t.name != 'Тест'],
        })
    return hints


# ---------------------------------------------------------------------------
# Шаг 2. Разбор фразы — ОДНО обращение к модели, уже со словарём на руках
# ---------------------------------------------------------------------------

def parse_request(text, params, user):
    """Вольный текст → план домашки. Ровно ОДНО обращение к модели.

    Возвращает `{'rows': [...], 'note': str, 'usage': {...},
    'cached': bool, 'hints': [...]}`. Любой отказ приходит человеческим
    текстом — белого экрана не бывает ни при какой ошибке.
    """
    text = (text or '').strip()
    if not text:
        raise ai.AiUnavailable('Опишите домашку словами — по пустому '
                               'описанию подбирать нечего.')
    if not ai.is_available():
        raise ai.AiUnavailable(ai.unavailable_reason())

    hints = search_hints(text)
    result = ai.run('homework_plan', _user_prompt(text, params, hints),
                    PLAN_SCHEMA, user)

    rows = _clean_rows(result.data.get('rows'), params)
    if not rows:
        # Даже здесь не сдаёмся молча: одна строка на всю фразу — это
        # ровно то, что репетитор и написал, и поиск с ней справится.
        rows = [{'label': text[:120], 'query': text, 'topic': '',
                 'difficulty': _middle(params),
                 'count': int(params.get('count') or 5)}]
    return {'rows': rows, 'note': (result.data.get('note') or '').strip(),
            'usage': result.usage, 'cached': result.cached, 'hints': hints}


def _middle(params):
    low = int(params.get('min_difficulty') or 1)
    high = int(params.get('max_difficulty') or 5)
    return max(low, min(high, (low + high) // 2))


def _user_prompt(text, params, hints):
    """ВСЁ переменное живёт здесь и только здесь.

    ⚠️ В системную часть (ядро + профиль) не попадает ни одно изменяемое
    слово — иначе кэш префикса перестанет срабатывать: совпадение
    проверяется побайтно.
    """
    lines = ['Параметры от репетитора:',
             '- всего задач: %d' % int(params.get('count') or 5),
             '- сложность: от %s до %s' % (params.get('min_difficulty') or 1,
                                           params.get('max_difficulty') or 5)]
    if params.get('topics'):
        lines.append('- заданные темы: %s' % ', '.join(params['topics']))

    lines.append('')
    lines.append('Описание домашки словами репетитора:')
    lines.append(text)

    lines.append('')
    lines.append('Список тем платформы (подсказка для поля topic; если '
                 'подходящей нет — оставь пустую строку):')
    lines.extend('- ' + name for name in canonical_topics())

    lines.append('')
    if hints:
        lines.append('Задачи, которые УЖЕ НАШЛИСЬ в банке по этому описанию '
                     '(название — темы). Это словарь банка, а не образец '
                     'ответа:')
        for hint in hints:
            lines.append('- %s — %s' % (
                hint['title'], ', '.join(hint['topics']) or 'тема не указана'))
    else:
        lines.append('По этому описанию поиск ничего не нашёл. Разбей фразу '
                     'по словам репетитора, тему оставь пустой.')
    return '\n'.join(lines)


def _clean_rows(rows, params):
    """Приводим ответ модели к тому, что мы умеем искать.

    ⚠️ Тема больше НЕ отбрасывает строку. Раньше строка с темой, которой
    нет в меню, выбрасывалась целиком — и вместе с ней исчезала часть
    просьбы репетитора. Теперь несопоставленная тема просто становится
    пустой: искать всё равно будем по СЛОВАМ репетитора, а тема лишь
    подсказывает порядок.
    """
    topics = canonical_topics()
    by_lower = {name.lower(): name for name in topics}
    low = int(params.get('min_difficulty') or 1)
    high = int(params.get('max_difficulty') or 5)

    cleaned = []
    for row in (rows or [])[:MAX_ROWS]:
        if not isinstance(row, dict):
            continue
        query = str(row.get('query') or '').strip()[:200]
        label = str(row.get('label') or query).strip()[:200]
        if not query:
            continue
        name = str(row.get('topic') or '').strip()
        topic = by_lower.get(name.lower(), '')
        if not topic and name:
            for candidate in topics:
                if (name.lower() in candidate.lower()
                        or candidate.lower() in name.lower()):
                    topic = candidate
                    break
        try:
            difficulty = int(row.get('difficulty'))
        except (TypeError, ValueError):
            difficulty = _middle(params)
        try:
            count = int(row.get('count'))
        except (TypeError, ValueError):
            count = 1
        cleaned.append({
            'label': label,
            'query': query,
            'topic': topic,
            'difficulty': max(low, min(high, max(1, min(5, difficulty)))),
            'count': max(1, min(MAX_PROBLEMS, count)),
        })
    return _fit_total(cleaned, int(params.get('count') or 5))


def _fit_total(rows, wanted):
    """Сумма по строкам обязана равняться запрошенному числу задач.

    Модель считает неплохо, но «пять задач» — это обещание пользователю, а
    не пожелание модели. Расхождение правим сами: лишнее снимаем с конца,
    недостающее добавляем в последнюю строку.
    """
    if not rows or wanted <= 0:
        return rows
    total = sum(row['count'] for row in rows)
    while total > wanted:
        for row in reversed(rows):
            if row['count'] > 1 and total > wanted:
                row['count'] -= 1
                total -= 1
            elif total > wanted and len(rows) > 1 and row['count'] == 1:
                rows.remove(row)
                total -= 1
                break
        else:
            break
    if total < wanted:
        rows[-1]['count'] += wanted - total
    return rows


# ---------------------------------------------------------------------------
# Шаг 3. Подбор задач — бесплатно, обращений к модели не стоит
# ---------------------------------------------------------------------------

def find_problems(rows, has_solution=False, sources=None, exclude=()):
    """Каждая строка плана → свой поиск. Возвращает (найденное, недобор).

    ⚠️ КВОТА ЗАПОЛНЯЕТСЯ ВСЕГДА. «Не хватило задач» — не результат:
    репетитор просил пять задач, а получал три и предупреждение. Порядок
    отступления такой:
      1. кандидаты своей строки (смысл + слова, тема — бонус к рангу);
      2. те же кандидаты, но с ослабленным потолком по источнику;
      3. добор из общего поиска по ФРАЗЕ ЦЕЛИКОМ.
    Порога похожести как жёсткой отсечки нет вовсе — он и раньше только
    прятал задачи, а не улучшал их.

    ⚠️ НО ЧЕСТНО ПОМЕЧАЕМ. У каждой задачи есть `confidence`: точное
    совпадение / близко / ближайшее что нашлось. Молча подсунуть чужую
    задачу нельзя — репетитор потом не поймёт, откуда она взялась.
    """
    from catalog import hybrid

    found = []
    taken = set(exclude)
    per_source = {}
    short_rows = []

    for index, row in enumerate(rows):
        candidates = search_row(row, has_solution=has_solution,
                                sources=sources)
        picked = _take(candidates, row['count'], taken, per_source,
                       found, index, cap=SOURCE_CAP)
        if picked < row['count']:
            # Потолок по источнику — предпочтение, а не запрет. Лучше
            # пять задач из двух сборников, чем три и извинение.
            picked += _take(candidates, row['count'] - picked, taken,
                            per_source, found, index, cap=None)
        if picked < row['count']:
            short_rows.append({'row': index, 'missing': row['count'] - picked,
                               'label': row['label']})

    # Добор: то, чего не хватило строкам, берём из общего поиска и честно
    # помечаем как «ближайшее что нашлось».
    # ⚠️ ДОБОР ИДЁТ ПО КАЖДОЙ НЕДОБРАВШЕЙ СТРОКЕ ОТДЕЛЬНО И УВАЖАЕТ ТИП.
    # Раньше весь недобор сваливался на первую короткую строку общим куском,
    # а последний рубеж («просто опубликованные задачи») не смотрел на тип
    # вовсе. Итог: репетитор просил три теста, а получал три открытые
    # задачи — молча, под видом выполненной просьбы. Тип нельзя подменять:
    # тест и задача — разная работа для ученика.
    whole = ' '.join(row['query'] for row in rows)
    for gap in list(short_rows):
        need = gap['missing']
        if need <= 0:
            continue
        index = gap['row']
        kind = rows[index].get('kind')

        for source in ('search', 'any'):
            if need <= 0:
                break
            if source == 'search':
                pool = _materialise(hybrid.search(whole, limit=need * 12 + 24),
                                    has_solution, sources)
            else:
                pool = _materialise(_any_problems(rows, need * 8, kind),
                                    has_solution, sources)
            if kind == 'open':
                pool = [i for i in pool if not is_test_problem(i['problem'])]
            elif kind == 'test':
                pool = [i for i in pool if is_test_problem(i['problem'])]
            added = _take(pool, need, taken, per_source, found, index,
                          cap=None, force_far=True)
            need -= added

    still_short = _recount(rows, found)
    return found, still_short


def _recount(rows, found):
    """Чего в итоге не хватило. Считаем ПО ФАКТУ, а не по намерению."""
    by_row = {}
    for item in found:
        by_row[item['row']] = by_row.get(item['row'], 0) + 1
    short = []
    for index, row in enumerate(rows):
        got = by_row.get(index, 0)
        if got < row['count']:
            short.append({'row': index, 'missing': row['count'] - got,
                          'label': row['label']})
    return short


def _take(candidates, need, taken, per_source, found, row_index, cap,
          force_far=False):
    """Берёт до `need` задач, соблюдая потолок по источнику, если он задан."""
    picked = 0
    for candidate in candidates:
        if picked >= need:
            break
        problem = candidate['problem']
        if problem.pk in taken:
            continue
        source = _source_of(problem)
        if cap is not None and source and per_source.get(source, 0) >= cap:
            continue
        taken.add(problem.pk)
        if source:
            per_source[source] = per_source.get(source, 0) + 1
        found.append({
            'problem': problem,
            'row': row_index,
            'confidence': 'far' if force_far else candidate['confidence'],
            'how': candidate.get('how', ''),
        })
        picked += 1
    return picked



# Слова, которыми репетитор расставляет порядок задач прямо в описании.
# ⚠️ Ищем ИМЕННО порядковые указания, а не любые числительные: «две задачи
# на КПВ» — это количество, а «вторая задача — тест» это порядок.
ORDER_WORDS = (
    'перв', 'втор', 'треть', 'четвёрт', 'четверт', 'пят',
    'шест', 'седьм', 'восьм', 'девят', 'десят',
    'последн', 'в конце', 'в начале', 'сначала', 'затем', 'потом',
    'вначале', 'первым', 'последним',
)


def describes_order(text):
    """Задал ли репетитор порядок задач словами.

    Если задал — автоматическая перестановка «сначала тесты, потом задачи»
    ОТМЕНЯЕТСЯ (`Assignment.manual_order`, правило фазы 4). Он расставлял
    задачи по смыслу урока, и наш формальный признак тут не главнее.
    """
    low = (text or '').lower()
    return any(word in low for word in ORDER_WORDS)

def is_test_problem(problem):
    """Тест ли это. Признак — ТИП задачи, как во всём проекте."""
    return (problem.problem_type or '').startswith('тест')


def allocate(total, weights):
    """Раздать `total` мест по весам МЕТОДОМ НАИБОЛЬШЕГО ОСТАТКА.

    Тот же приём, что в работе над ошибками игры. Обычное округление теряет
    или добавляет места: репетитор просит четыре задачи, а получает три или
    пять. Здесь сумма ВСЕГДА равна total.
    """
    if total <= 0 or not weights:
        return [0] * len(weights)
    pool = sum(weights) or len(weights)
    weights = weights if sum(weights) else [1] * len(weights)
    exact = [total * w / pool for w in weights]
    base = [int(value) for value in exact]
    left = total - sum(base)
    order = sorted(range(len(weights)),
                   key=lambda i: (exact[i] - base[i]), reverse=True)
    for i in range(left):
        base[order[i % len(order)]] += 1
    return base


def split_by_kind(rows, want_open, want_test):
    """План → два плана: под открытые задачи и под тесты.

    ⚠️ ЗАЧЕМ. Поле «сколько задач» было ОДНО, и разделить нельзя было
    никак: репетитор, которому нужны четыре задачи и три теста, получал
    семь чего попало. Темы при этом остаются те же — делим только квоту,
    по весам исходных строк.
    """
    if not rows:
        return []
    weights = [row.get('count', 1) or 1 for row in rows]
    opens = allocate(want_open, weights)
    tests = allocate(want_test, weights)

    plan = []
    for row, count in zip(rows, opens):
        if count:
            item = dict(row)
            item['count'] = count
            item['kind'] = 'open'
            plan.append(item)
    for row, count in zip(rows, tests):
        if count:
            item = dict(row)
            item['count'] = count
            item['kind'] = 'test'
            item['label'] = '%s — тест' % row['label']
            plan.append(item)
    return plan


def search_row(row, has_solution=False, sources=None):
    """Кандидаты под ОДНУ строку плана. Обращений к модели не стоит.

    ⚠️ ТЕМА — БОНУС К РАНГУ, А НЕ ФИЛЬТР. Именно жёсткий фильтр по теме и
    схлопнул выдачу на живом запросе: модель ошиблась темой, и правильные
    задачи, которые поиск уже нашёл, были выброшены до показа.
    """
    from catalog import hybrid

    # Просим с запасом: часть кандидатов отсеется по типу задачи.
    limit = row['count'] * 8 + 12
    kind = row.get('kind')
    if kind in ('open', 'test'):
        limit = row['count'] * 20 + 30
    hits = hybrid.search(row['query'], limit=limit)
    items = _materialise(hits, has_solution, sources)
    # ⚠️ Тип — ЖЁСТКИЙ отбор, в отличие от темы. «Три теста» это просьба
    # именно про тесты: подсунуть вместо теста открытую задачу нельзя, это
    # другая работа для ученика.
    if kind == 'open':
        items = [i for i in items if not is_test_problem(i['problem'])]
    elif kind == 'test':
        items = [i for i in items if is_test_problem(i['problem'])]
    return _rank(items, row)


def _materialise(hits, has_solution, sources):
    """id из поиска → сами задачи, в том же порядке."""
    from catalog import hybrid
    from problems.models import Problem

    ids = [hit['id'] for hit in hits]
    if not ids:
        return []
    queryset = Problem.objects.filter(pk__in=ids).prefetch_related(
        'topics', 'source_references')
    if has_solution:
        queryset = queryset.exclude(solution='').filter(solution__isnull=False)
    by_id = {p.pk: p for p in queryset}

    allowed = {int(s) for s in (sources or []) if str(s).isdigit()}
    items = []
    for hit in hits:
        problem = by_id.get(hit['id'])
        if problem is None:
            continue
        if allowed and not any(r.source_id in allowed
                               for r in problem.source_references.all()):
            continue
        items.append({'problem': problem, 'hit': hit,
                      'confidence': hybrid.confidence(hit),
                      'how': hit.get('how', '')})
    return items


def _rank(items, row):
    """Порядок с учётом темы и сложности. Ничего не выбрасывает."""
    topic = (row.get('topic') or '').strip().lower()
    wanted = row.get('difficulty')

    def key(item, order=[0]):
        problem = item['problem']
        bonus = 0.0
        if topic and any((t.name or '').lower() == topic
                         for t in problem.topics.all()):
            bonus += 0.5
        if wanted and problem.difficulty:
            # Близкая сложность лучше далёкой, но задача другой сложности
            # всё равно лучше пустого места.
            bonus += 0.25 / (1 + abs(int(problem.difficulty) - int(wanted)))
        return -(item['hit']['score'] * 10 + bonus)

    return sorted(items, key=key)


def _any_problems(rows, limit, kind=None):
    """Последний рубеж добора: опубликованные задачи подходящей сложности.

    ⚠️ `kind` ОБЯЗАТЕЛЕН, когда строка просит тесты. Раньше эта выборка
    жёстко ИСКЛЮЧАЛА тесты — и была права, пока подбор умел просить только
    открытые задачи. С появлением поля «сколько тестов» это исключение
    превратилось в тихую подмену: репетитор просил три теста, а последний
    рубеж подсовывал три открытые задачи. Тест и задача — разная работа
    для ученика, подменять их нельзя.
    """
    from problems.models import Problem

    levels = {row['difficulty'] for row in rows if row.get('difficulty')}
    queryset = Problem.objects.filter(status=Problem.Status.PUBLISHED,
                                      needs_quality_review=False)
    if kind == 'test':
        queryset = queryset.filter(problem_type__istartswith='тест')
    else:
        queryset = queryset.exclude(problem_type__istartswith='тест')
    if levels:
        queryset = queryset.filter(difficulty__in=list(levels))
    ids = list(queryset.order_by('?').values_list('id', flat=True)[:limit])
    return [{'id': pid, 'how': '', 'dense_score': None, 'term_hits': 0,
             'term_total': 0, 'score': 0.0} for pid in ids]


def _source_of(problem):
    reference = problem.source_references.all()[:1]
    return reference[0].source_id if reference else None


def problem_card(problem, confidence='', how=''):
    """Как задача выглядит на экране подтверждения и в корзине."""
    from catalog import hybrid

    return {
        'problem': problem,
        'id': problem.pk,
        'title': preview_title(problem, limit=90),
        'preview': clean((problem.statement or ''))[:220],
        'topics': ', '.join(t.name for t in problem.topics.all()
                            if t.name != 'Тест'),
        'difficulty': problem.difficulty,
        'confidence': confidence,
        'confidence_label': hybrid.CONFIDENCE_LABELS.get(confidence, ''),
        'how': how,
    }


def preview_rows(rows, has_solution=False, sources=None, per_row=3):
    """Что нашлось по каждой строке — для экрана подтверждения.

    ⚠️ СТОП-ГЕЙТ ПОКАЗЫВАЕТ ЗАДАЧИ, А НЕ ТЕМЫ. Раньше на нём стояли темы,
    выбранные моделью, и проверить их репетитор не мог: нашей таксономии он
    не знает. Именно там и пряталась ошибка с КТВ — «Альтернативные
    издержки и КПВ» выглядит правдоподобно, пока не увидишь, что нашлось.
    Названия двух-трёх задач репетитор проверяет за пять секунд.

    Обращений к модели не стоит — это тот же поиск по банку.
    """
    from catalog import hybrid

    previews = []
    for index, row in enumerate(rows):
        items = search_row(row, has_solution=has_solution, sources=sources)
        cards = [problem_card(item['problem'], item['confidence'],
                              item.get('how', ''))
                 for item in items[:per_row]]
        best = items[0]['confidence'] if items else 'far'
        previews.append({
            'index': index,
            'row': row,
            'cards': cards,
            'total': len(items),
            'confidence': best if items else '',
            'confidence_label': (hybrid.CONFIDENCE_LABELS.get(best, '')
                                 if items else 'ничего не нашлось'),
        })
    return previews
