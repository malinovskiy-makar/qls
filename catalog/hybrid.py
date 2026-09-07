"""
Два поиска вместо одного: по смыслу и по словам, с объединением списков.

⚠️ ЗАЧЕМ ВТОРОЙ ПОИСК. Смысловой поиск хорошо работает с фразами и плохо —
с редкими сокращениями. «КТВ» для эмбеддинга это три буквы без внятного
значения; поиск по словам находит её идеально, потому что ищет совпадение.
Замер по банку (2026-08-06): «КТВ» встречается в 68 условиях, 51 заголовке
и 83 подпунктах — материал есть, надо просто уметь его достать.

⚠️ ПОЧЕМУ НЕ РАЗРЕЖЕННЫЙ РЕЖИМ BGE-M3. Модель умеет три режима (плотный,
разреженный, многовекторный), но `sentence-transformers` отдаёт ТОЛЬКО
плотный: остальные требуют `FlagEmbedding` и своего формата векторов. То
есть «включить второй режим» — это не настройка, а новый индекс на 31 472
задачи, новое поле в базе и полный пересчёт. Поиск по словам даёт тот же
эффект на редких терминах, стоит ноль и работает НА ПРОДЕ, где плотного
поиска нет вовсе.

ОБЪЕДИНЕНИЕ — ПО РАНГАМ (Reciprocal Rank Fusion), а не по числам похожести.
Причина простая: косинус плотного поиска (0…1) и «сколько слов совпало»
несопоставимы, а любая попытка привести их к общей шкале — это подгонка
коэффициентов на глаз. RRF складывает `1/(k + место в списке)` и не требует
знать ни одной шкалы; k = 60 — общепринятое значение, оно лишь сглаживает
разницу между первым и вторым местом.
"""
import logging
import re

logger = logging.getLogger(__name__)

RRF_K = 60

# Слова, которые есть в каждом втором условии: искать по ним бессмысленно.
STOPWORDS = {
    'задача', 'задачи', 'задач', 'найдите', 'найти', 'определите', 'дано',
    'если', 'при', 'для', 'что', 'как', 'это', 'все', 'его', 'она', 'они',
    'или', 'над', 'под', 'без', 'про', 'том', 'так', 'там', 'уже', 'ещё',
    'штук', 'штуки', 'одна', 'один', 'одно', 'две', 'три', 'домашка',
    'домашку', 'домашке', 'задание', 'заданий', 'тема', 'теме', 'темы',
    'вывод', 'построение', 'сложение', 'первая', 'вторая', 'третья',
}

_WORD = re.compile(r'[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\-]{1,}')


def terms(query, limit=6):
    """Слова запроса, по которым имеет смысл искать буквально.

    Сокращения («КТВ», «MRTS») пропускаем вперёд: именно на них смысловой
    поиск и слепнет, а словарный — точен.
    """
    words = _WORD.findall(query or '')
    picked = []
    for word in words:
        if len(word) < 3:
            continue
        if word.lower() in STOPWORDS:
            continue
        if word.lower() in {w.lower() for w in picked}:
            continue
        picked.append(word)
    # Сокращения (все буквы заглавные) — в начало.
    picked.sort(key=lambda w: (not w.isupper(), len(w)))
    return picked[:limit]


def _variants(term):
    """Регистр букв. SQLite для кириллицы сравнивает LIKE ПО-РАЗНОМУ с
    PostgreSQL, поэтому не полагаемся на `icontains` и перебираем варианты
    сами — иначе локально «КТВ» находится, а на проде «ктв» нет (или
    наоборот), и разобраться в этом потом будет некому."""
    return {term, term.lower(), term.upper(), term.capitalize()}


def lexical_search(query, limit, content_kind='problems'):
    """Поиск по СЛОВАМ: сколько разных слов запроса встретилось в задаче.

    Ищем в заголовке, условии, подпунктах И РЕШЕНИИ: термин часто стоит
    именно в решении («по лемме Хотеллинга…»), а в отпечаток для
    смыслового поиска решение не входит вовсе.

    ⚠️ Покрытие слов считаем В ПИТОНЕ, а не одним `Sum(Case(...))`: с
    join на подпункты SQL сложил бы совпадения по СТРОКАМ join, и задача
    с пятью подпунктами обогнала бы задачу, где совпали все слова.
    Кандидатов тут десятки — это дешевле, чем спорить с SQL.
    """
    from django.db.models import Q

    from problems.models import Problem

    picked = terms(query)
    if not picked:
        return [], {}, []

    queryset = Problem.objects.filter(status=Problem.Status.PUBLISHED,
                                      needs_quality_review=False,
                                      hidden_pending_review=False,
        content_status=Problem.ContentStatus.OK)
    if content_kind == 'problems':
        queryset = queryset.exclude(problem_type__istartswith='тест')
    elif content_kind == 'tests':
        queryset = queryset.filter(problem_type__istartswith='тест')

    hits = {}
    for term in picked:
        condition = Q()
        for variant in _variants(term):
            condition |= (Q(title__contains=variant)
                          | Q(statement__contains=variant)
                          | Q(parts__statement__contains=variant)
                          | Q(solution__contains=variant))
        # Порция на слово ограничена: без ограничения частое слово вроде
        # «спрос» вытащило бы полбанка и утопило редкое «КТВ».
        for pid in queryset.filter(condition).values_list(
                'id', flat=True).distinct()[:limit * 3]:
            hits[pid] = hits.get(pid, 0) + 1

    ordered = sorted(hits, key=lambda pid: (-hits[pid], pid))[:limit]
    return ordered, hits, picked


def dense_search(query, limit=60, content_kind='problems'):
    """Поиск по смыслу. Модели нет (прод) — честно возвращаем пусто."""
    from catalog import semantic

    # ⚠️ ВЫКЛЮЧЕНО НАСТРОЙКОЙ — ЭТО НЕ ОШИБКА, И В ЖУРНАЛ ЭТО НЕ ПИШЕТСЯ.
    # Проверка стоит здесь, до вызова semantic.search, по двум причинам.
    # Первая: `semantic.search` начинается с кодирования запроса, то есть
    # с загрузки модели — 2,12 ГБ на каждый воркер (мина №1).
    # Вторая: раньше выключенный поиск попадал в `except Exception` ниже и
    # писал traceback на КАЖДЫЙ поисковый запрос. Журнал, в котором штатное
    # поведение выглядит как авария, перестают читать — и настоящая авария
    # теряется среди шума.
    if not semantic.is_enabled():
        return [], {}

    from catalog.search_client import SearchServiceUnavailable

    try:
        hits = semantic.search(query, limit=limit, content_kind=content_kind)
        return ([hit['problem'].pk for hit in hits],
                {hit['problem'].pk: hit['score'] for hit in hits})
    except SearchServiceUnavailable as exc:
        # ⚠️ ТИПИЗИРОВАННОЕ СОБЫТИЕ, БЕЗ TRACEBACK, И ЭТО ПРИНЦИПИАЛЬНО.
        # Лежащий сервис — состояние, а не происшествие: пока он лежит,
        # сюда приходит КАЖДЫЙ поисковый запрос. Полная трассировка на
        # каждый из них за минуту заливает журнал одинаковыми простынями,
        # и настоящая авария в них тонет. Одна строка с причиной говорит
        # ровно столько же, сколько нужно, чтобы понять и починить.
        logger.warning('search service unavailable: %s — идём по словам', exc)
        return [], {}
    except Exception:
        # А вот это уже неожиданное: чинить надо код, и трассировка нужна.
        logger.exception('Смысловой поиск сломался — идём только по словам')
        return [], {}


def search(query, limit=20, content_kind='problems'):
    """Оба поиска и объединение по рангам.

    Возвращает список словарей:
        {'id', 'score', 'how', 'dense_score', 'term_hits', 'term_total'}
    `how` — 'both' / 'dense' / 'lexical': чем именно нашли. Это не
    украшение, а то, из чего собирается пометка уверенности на экране.
    """
    query = (query or '').strip()
    if not query:
        return []

    dense_ids, dense_scores = dense_search(query, limit=limit * 3,
                                           content_kind=content_kind)
    lex_ids, lex_hits, picked = lexical_search(query, limit * 3,
                                              content_kind)

    fused = {}
    for rank, pid in enumerate(dense_ids):
        fused[pid] = fused.get(pid, 0.0) + 1.0 / (RRF_K + rank + 1)
    for rank, pid in enumerate(lex_ids):
        fused[pid] = fused.get(pid, 0.0) + 1.0 / (RRF_K + rank + 1)

    dense_set = set(dense_ids)
    lex_set = set(lex_ids)
    order = sorted(fused, key=lambda pid: (-fused[pid], pid))[:limit]
    results = []
    for pid in order:
        if pid in dense_set and pid in lex_set:
            how = 'both'
        elif pid in dense_set:
            how = 'dense'
        else:
            how = 'lexical'
        results.append({
            'id': pid,
            'score': fused[pid],
            'how': how,
            'dense_score': dense_scores.get(pid),
            'term_hits': lex_hits.get(pid, 0),
            'term_total': len(picked),
        })
    return results


# Пометки уверенности — ровно три, и они про ФАКТ, а не про красоту числа.
CONFIDENCE_LABELS = {
    'exact': 'точное совпадение',
    'close': 'близко',
    'far': 'ближайшее что нашлось',
}


def confidence(hit):
    """Насколько уверенно задача подошла. Молча подсовывать чужую нельзя.

    «Точное» — нашли ОБА поиска, либо совпали все значимые слова запроса,
    либо смысловая близость выше 0,75. «Близко» — нашёл один из двух с
    приличным результатом. Остальное честно называется «ближайшее что
    нашлось»: репетитор должен понимать, откуда взялась эта задача.
    """
    if hit is None:
        return 'far'
    dense = hit.get('dense_score')
    total = hit.get('term_total') or 0
    hits = hit.get('term_hits') or 0
    if hit.get('how') == 'both':
        return 'exact'
    if total and hits >= total:
        return 'exact'
    if dense is not None and dense >= 0.75:
        return 'exact'
    if dense is not None and dense >= 0.55:
        return 'close'
    if total and hits >= max(1, total // 2):
        return 'close'
    return 'far'
