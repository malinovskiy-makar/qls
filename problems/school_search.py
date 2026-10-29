# -*- coding: utf-8 -*-
"""Подсказки городов и школ на шаге онбординга «Где вы учитесь?» (раунд 2).

Работает без внешних сервисов: города — свой файл `problems/data/cities_ru.json`
(источник и лицензия — `problems/data/README.md`), школы — таблица `School`
(реестр Рособрнадзора — `manage.py sync_schools`, `load_schools`) и названия, которые
уже ввели другие ученики этого города.

Правила (промпт раунда 2, фаза 4):
* без учёта регистра, «ё» = «е»;
* город: совпадение с начала названия важнее, чем с начала слова, а то — чем в
  середине; внутри — по населению (Москва и Санкт-Петербург первые); синонимы
  «мск», «спб», «питер»;
* школа (раунд 3): по всей стране, школы города из поля «Город» — первыми; число в
  запросе («57», «№57», «школа 57», «57-я», «лицей 1535», «пятьдесят седьмая») ищет по
  номеру; точное совпадение номера — первым, потом номер с начала, потом по названию;
  у подсказки — город (и регион, если город с таким названием не один);
* до 8 вариантов.

⚠️ ЧУЖИЕ ВВОДЫ — ТОЛЬКО ПОВТОРЁННЫЕ. Название школы из профилей других людей
попадает в подсказки, только если его ввели хотя бы `MIN_PEOPLE` (3) разных человек,
НЕ считая того, кто спрашивает: иначе свой профиль работал бы «подсказкой» и по
ответу можно было бы угадать, учится ли в городе хоть кто-то в школе X (проверка
безопасности 30.10.2026). Так в подсказку не утечёт и случайная запись одного
человека («школа, где учится Маша»).
"""
import json
import re
from functools import lru_cache
from pathlib import Path

LIMIT = 8
MIN_PEOPLE = 3
CITIES_FILE = Path(__file__).resolve().parent / 'data' / 'cities_ru.json'
CITY_SYNONYMS = {'мск': 'москва', 'спб': 'санкт-петербург', 'питер': 'санкт-петербург',
                 'петербург': 'санкт-петербург', 'екб': 'екатеринбург', 'нск': 'новосибирск'}


def norm(text):
    """Нижний регистр, «ё» → «е», без лишних пробелов."""
    return ' '.join((text or '').lower().replace('ё', 'е').split())


# ── Города ─────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _cities():
    with open(CITIES_FILE, encoding='utf-8') as handle:
        data = json.load(handle)
    return [(norm(c['name']), c['name'], c['region'], c.get('population') or 0) for c in data]


def _place(name_norm, query):
    """0 — с начала названия, 1 — с начала слова, 2 — в середине, None — нет."""
    if name_norm.startswith(query):
        return 0
    if re.search(r'(^|[\s-])' + re.escape(query), name_norm):
        return 1
    if query in name_norm:
        return 2
    return None


def cities(query, limit=LIMIT):
    """Города по запросу: [{'value', 'label', 'sub'}]."""
    query = norm(query)
    if not query:
        return []
    query = CITY_SYNONYMS.get(query, query)
    found = []
    for name_norm, name, region, population in _cities():
        place = _place(name_norm, query)
        if place is not None:
            found.append((place, -population, name, region))
    found.sort()
    return [{'value': name, 'label': name, 'sub': region if region != name else ''}
            for _place_, _pop, name, region in found[:limit]]


# ── Числительные словами → число ───────────────────────────────────────────

CARDINALS = {
    'ноль': 0, 'один': 1, 'одна': 1, 'одно': 1, 'два': 2, 'две': 2, 'три': 3, 'четыре': 4,
    'пять': 5, 'шесть': 6, 'семь': 7, 'восемь': 8, 'девять': 9, 'десять': 10,
    'одиннадцать': 11, 'двенадцать': 12, 'тринадцать': 13, 'четырнадцать': 14,
    'пятнадцать': 15, 'шестнадцать': 16, 'семнадцать': 17, 'восемнадцать': 18,
    'девятнадцать': 19, 'двадцать': 20, 'тридцать': 30, 'сорок': 40, 'пятьдесят': 50,
    'шестьдесят': 60, 'семьдесят': 70, 'восемьдесят': 80, 'девяносто': 90, 'сто': 100,
    'двести': 200, 'триста': 300, 'четыреста': 400, 'пятьсот': 500, 'шестьсот': 600,
    'семьсот': 700, 'восемьсот': 800, 'девятьсот': 900,
}
THOUSANDS = ('тысяча', 'тысячи', 'тысяч')
#: Основы порядковых: «пятьдесят седьмая» = 50 + «седьм»+«ая».
ORDINAL_STEMS = {
    'перв': 1, 'втор': 2, 'трет': 3, 'четверт': 4, 'пят': 5, 'шест': 6, 'седьм': 7,
    'восьм': 8, 'девят': 9, 'десят': 10, 'одиннадцат': 11, 'двенадцат': 12,
    'тринадцат': 13, 'четырнадцат': 14, 'пятнадцат': 15, 'шестнадцат': 16,
    'семнадцат': 17, 'восемнадцат': 18, 'девятнадцат': 19, 'двадцат': 20, 'тридцат': 30,
    'сороков': 40, 'пятидесят': 50, 'шестидесят': 60, 'семидесят': 70,
    'восьмидесят': 80, 'девяност': 90, 'сот': 100, 'двухсот': 200, 'трехсот': 300,
    'четырехсот': 400, 'пятисот': 500, 'шестисот': 600, 'семисот': 700,
    'восьмисот': 800, 'девятисот': 900, 'тысячн': 1000, 'двухтысячн': 2000,
    'трехтысячн': 3000,
}
ORDINAL_ENDINGS = ('ый', 'ой', 'ий', 'ая', 'яя', 'ое', 'ее', 'ые', 'ие', 'ого', 'его',
                   'ому', 'ему', 'ом', 'ем', 'ую', 'юю', 'ей', 'ья', 'ье', 'ьи', 'ьего',
                   'ьей', 'ью', 'ьему', 'ьем')
_STEMS_LONGEST_FIRST = sorted(ORDINAL_STEMS, key=len, reverse=True)
MAX_NUMBER = 3000


def _word_value(word):
    """Значение одного слова-числительного или None."""
    if word in CARDINALS:
        return CARDINALS[word]
    if word in THOUSANDS:
        return 1000
    for stem in _STEMS_LONGEST_FIRST:
        if word.startswith(stem) and word[len(stem):] in ORDINAL_ENDINGS:
            return ORDINAL_STEMS[stem]
    return None


def words_to_number(text):
    """«пятьдесят седьмая» → 57, «сто двадцать пятый» → 125, «две тысячи семь» →
    2007. Первая непрерывная цепочка числительных; больше 3000 или нет — None."""
    total, current, seen = 0, 0, False
    for word in re.findall(r'[а-я]+', norm(text)):
        value = _word_value(word)
        if value is None:
            if seen:
                break
            continue
        seen = True
        if value >= 1000 and word in THOUSANDS:
            total += (current or 1) * 1000
            current = 0
        else:
            current += value
    number = total + current
    return number if seen and 0 < number <= MAX_NUMBER else None


def query_number(text):
    """Номер в запросе: «57», «№57», «школа 57», «57-я», «лицей 1535», словами."""
    found = re.search(r'\d+', text or '')
    if found:
        return int(found.group(0))
    return words_to_number(text)


def number_in_name(name):
    """Номер школы из её названия: «Школа № 57», «Лицей №1535», «ГБОУ школа 57»."""
    # «имени 50-летия Октября» — не номер.
    found = (re.search(r'№\s*(\d+)', name or '')
             or re.search(r'(?<![\d.])(\d{1,4})(?![\d.]|\s*-?\s*(?:лет|й\s+лет))', name or ''))
    return int(found.group(1)) if found else None


# ── Школы ──────────────────────────────────────────────────────────────────
#
# Раунд 3 (решение владельца 29.10.2026): школа не зависит от города — человек живёт в
# одном городе, а учится в другом. Подсказки школ — по всей стране; школы города из
# поля «Город» — первыми, дальше остальные (крупные города раньше). Внутри — точный
# номер → номер с начала → совпадение по названию.

#: Сколько строк справочника разбирать за один запрос (на «1» по стране их тысячи).
FETCH_CAP = 4000
AMBIGUOUS_KEY = 'school_search:ambiguous_cities:v1'


@lru_cache(maxsize=1)
def _population():
    """norm названия города → население (для порядка школ других городов)."""
    population = {}
    for name_norm, _name, _region, pop in _cities():
        population[name_norm] = max(pop, population.get(name_norm, 0))
    return population


def _ambiguous_cities():
    """Названия городов, которые есть больше чем в одном регионе: у их школ в подсказке
    — ещё и регион («Берёзовка, Пермский край»). Кэш на час: справочник меняется раз в
    неделю."""
    from django.core.cache import cache
    from django.db.models import Count

    from problems.models import School

    found = cache.get(AMBIGUOUS_KEY)
    if found is None:
        # Города из справочника городов — по нему (он точный): в реестре попадаются
        # московские школы с регионом «Московская область», и «Москва» иначе стала бы
        # «неоднозначной». По таблице школ — только сёла и посёлки, которых там нет.
        seen = {}
        for name_norm, _name, region, _pop in _cities():
            seen.setdefault(name_norm, set()).add(region)
        found = {name for name, regions in seen.items() if len(regions) > 1}
        found |= set(School.objects.filter(is_active=True).exclude(city_norm='')
                     .exclude(city_norm__in=list(seen))
                     .values('city_norm').annotate(n=Count('region', distinct=True))
                     .filter(n__gt=1).values_list('city_norm', flat=True))
        cache.set(AMBIGUOUS_KEY, found, 3600)
    return found


def _number_q(number):
    """Номер ровно или «с начала»: 57 → 57, 570–579, 5700–5799."""
    from django.db.models import Q

    q = Q(number=number)
    for digits in (1, 2, 3):
        low, high = number * 10 ** digits, (number + 1) * 10 ** digits - 1
        if low > MAX_NUMBER:
            break
        q |= Q(number__range=(low, high))
    return q


def _words_q(words):
    from django.db.models import Q

    q = Q()
    for word in words:
        q &= Q(name_norm__contains=word)
    return q


def _typed(city, asker_id):
    """Повторённые вводы других людей этого города (≥ MIN_PEOPLE, спрашивающий не в счёт)."""
    from django.db.models import Count

    from problems.models_platform import UserProfile

    rows = (UserProfile.objects.filter(city__iexact=city.strip()).exclude(school='')
            .exclude(user_id=asker_id).values('school')
            .annotate(people=Count('user', distinct=True)).filter(people__gte=MIN_PEOPLE))
    return [{'label': row['school'].strip(), 'full': False, 'number': number_in_name(row['school']),
             'city': city.strip(), 'region': '', 'name_n': norm(row['school'])} for row in rows]


def schools(city, query, limit=LIMIT, asker_id=None):
    """Школы по запросу по всей стране: [{'value', 'label', 'full', 'number', 'sub', 'city'}].

    `city` необязателен и влияет только на порядок: школы этого города — первыми.
    """
    from django.db.models import Q

    from problems.models import School

    query_n, city = norm(query), (city or '').strip()
    if not query_n:
        return []
    city_n = norm(CITY_SYNONYMS.get(norm(city), city))
    number = query_number(query)
    words = [w for w in re.findall(r'[a-zа-я]+', query_n)
             if _word_value(w) is None and w not in ('школа', 'шк', 'номер')]
    if number is not None:
        cond = _number_q(number) | (_words_q(words) if words else Q(pk__in=[]))
    else:
        cond = _words_q(words) if words else Q(name_norm__contains=query_n)
    fields = ('name', 'short_name', 'number', 'city', 'region', 'city_norm', 'name_norm')
    active = School.objects.filter(is_active=True).filter(cond)
    rows = []
    if city_n:
        rows += list(active.filter(city_norm=city_n).values(*fields)[:FETCH_CAP])
        rows += list(active.exclude(city_norm=city_n).values(*fields)[:FETCH_CAP])
    else:
        rows += list(active.values(*fields)[:FETCH_CAP])
    candidates = [{'label': r['short_name'] or r['name'], 'full': not r['short_name'],
                   'number': r['number'], 'city': r['city'], 'region': r['region'],
                   'name_n': r['name_norm']} for r in rows]
    if city:
        known = {(c['name_n'], norm(c['city'])) for c in candidates}
        candidates += [t for t in _typed(city, asker_id) if (t['name_n'], city_n) not in known]

    population = _population()
    scored = []
    for row in candidates:
        has_words = all(w in row['name_n'] for w in words) if words else False
        if number is not None and row['number'] is not None:
            if row['number'] == number:
                rank = 0
            elif str(row['number']).startswith(str(number)):
                rank = 1
            elif has_words:
                rank = 2
            else:
                continue
        elif has_words or (number is None and query_n in row['name_n']):
            rank = 2
        else:
            continue
        here = 0 if city_n and norm(row['city']) == city_n else 1
        scored.append(((here, rank, -population.get(norm(row['city']), 0),
                        row['number'] if row['number'] is not None else 10 ** 6, row['name_n']),
                       row))
    scored.sort(key=lambda item: item[0])
    ambiguous = _ambiguous_cities() if scored else set()
    results = []
    for _key, row in scored[:limit]:
        sub = row['city']
        if row['city'] and row['region'] and norm(row['city']) in ambiguous:
            sub = '%s, %s' % (row['city'], row['region'])
        results.append({'value': row['label'], 'label': row['label'], 'full': row['full'],
                        'number': row['number'] if row['number'] is not None else '',
                        'sub': sub, 'city': row['city']})
    return results
