"""Фильтры каталога и экрана домашки — ОДИН компонент на два экрана.

⚠️ ЗАЧЕМ ОБЩИЙ МОДУЛЬ, А НЕ ДВЕ КОПИИ. Разбор параметров жил в двух местах:
`catalog.views.problem_list` и `teacher.picker.picker_context`. Наборы уже
разошлись — в каталоге был «Источник», на домашке нет. В таксономии v2 будет
29 тем, 343 тега и 11 особенностей; каждое добавление пришлось бы делать
дважды, а расхождение замечалось бы не сразу. Решение владельца 01.09.2026:
https://app.notion.com/p/3ceb11c92bc1817d89e1c7274fd0a88c

⚠️ НАБОР АКТИВНЫХ ФИЛЬТРОВ ПРИХОДИТ ИЗВНЕ. `parse()` принимает любое
отображение (`request.GET`, обычный `dict`, состояние мастера) — модуль сам
никуда не лезет за адресом. Поэтому один и тот же разбор работает и там, где
фильтры живут в URL, и там, где они лежат в памяти шага.

⚠️ ВИДИМОСТЬ ЗАДАЧ — ПАРАМЕТР, А НЕ КОНСТАНТА. Каталог показывает только
проверенное человеком, экран домашки — всё опубликованное без брака. Это
РАЗНЫЕ правила, и сведение их в одно молча поменяло бы репетитору набор, из
которого он собирает работу. `base_queryset(gate=...)` называет правило явно.

⚠️ МНОЖЕСТВЕННЫЙ ВЫБОР (решение владельца 04.09.2026): темы, теги, сложность,
источники и особенности — списки; характер и «задача или тест» — одно
значение. Внутри группы значения складываются (ИЛИ), между группами —
пересекаются (И). Исключение — теги: несколько тегов сужают (И), человек
уточняет, а не расширяет. Старые одиночные адреса (`?topic=843`) читаются как
список из одного значения — параметр тот же.

⚠️ ПРАВИЛО НУЛЯ (решение владельца 04.09.2026): вариант, у которого в КОРПУСЕ
ноль задач, не попадает в варианты вовсе; ноль под ТЕКУЩИМИ фильтрами
остаётся с флагом `zero` — чтобы было видно, что снять. Группа без вариантов
не показывается: так «Характер задачи» и «Особенности» молчат, пока поля не
размечены, и включатся сами, когда данные появятся.
"""
from __future__ import annotations

from collections import Counter

from django.db.models import Count, Exists, OuterRef, Q, TextField
from django.db.models.functions import Cast

from problems import problem_types
from problems.enrich import features as enrich_features
from problems.sections import canonical_groups

from .topic_blocks import (
    BLOCK_SECTION, BLOCKS, block_of, is_known, order_in_block, section_of,
)

# ── Тема: пять блоков над двадцатью тремя каноническими темами ───────────
#
# Раскладка живёт в ОДНОМ месте на весь сайт — `problems/sections.py`.
# До 04.09.2026 копий было три (здесь, в `game/filters.py` и своя в
# `problems/stats.py`), и расходились они молча. Те же пять блоков теперь и
# у карты тем: Микро, Макро, Финансы, Математика, Прочее. ADR 0071.
# Окно фильтров редизайна раскладывает темы через `catalog/topic_blocks.py` —
# тонкий слой над тем же `problems/sections.py` (решение 05.09.2026).
#
# Структура кортежа — прежняя `(ключ, подпись, названия тем)`: потребители
# ниже и в `teacher/picker.py` не переписывались.
TOPIC_GROUPS = tuple(
    (key, label, tuple(names)) for key, label, names in canonical_groups()
)

# ── «Задача или тест»: выбор из двух, у теста — форматы ПОД ним ─────────
#
# Форматы — ВИДЫ теста (`problem_types.TEST_KINDS`), а не строки
# `problem_type`: одному виду соответствует несколько строк сразу, потому
# что в банке живут два словаря названий (старый и v2). На экран попадают
# только те виды, что есть в корпусе (правило нуля).
TEST_TYPES = tuple(
    (kind, problem_types.KIND_LABELS[kind]) for kind in problem_types.TEST_KINDS
)

# Признак теста один на весь проект и живёт в `problems.problem_types`.
# Тот же признак у поиска по словам (`catalog.hybrid.lexical_search`).

# ── Особенности: ВСЕ ДВЕНАДЦАТЬ, прямо из справочника ───────────────────
#
# ⚠️ ФИЛЬТР СПРАШИВАЕТ СВЯЗЬ `ProblemFeature`, А НЕ ВИТРИНУ
# `Problem.features` (13.09.2026). Витрина — это JSON из ТРЁХ ключей
# (`graph`/`table`/`proof`), и фильтровать по ней значило две потери сразу.
# Первая: девять особенностей из двенадцати отфильтровать было НЕЧЕМ —
# витрина о них не знает. Вторая: отбор шёл `Cast(features -> text) LIKE
# '%"graph"%'` (jsonb-вложение умеет только PostgreSQL, а тесты живут на
# SQLite), то есть чтением текста у каждой строки банка. Замер 13.09.2026
# на 41 307 задачах: 0,74 с на клик.
#
# Связь смоделирована правильно и уже проиндексирована внешним ключом —
# новое денормализованное хранилище (массив, jsonb) заводить незачем, и это
# тот самый случай, когда «не сверхинженерить» значит взять то, что уже
# есть. Витрина остаётся как есть: она нужна бейджикам на карточке задачи,
# где «Есть график» — объединение трёх особенностей.
#
# Канон списка — `problems/enrich/features.py`, и дублировать его здесь
# нельзя: два списка разошлись бы молча.
FEATURES = tuple(
    (key, label) for key, label, _by in enrich_features.CATALOG_FEATURES
)

#: Старые адреса каталога несли ключ ВИТРИНЫ (`?feature=graph`). Их надо
#: продолжать понимать: такие ссылки сохранены людьми, и ими же помечены
#: бейджики на карточке задачи. Ключ витрины разворачивается в свои
#: особенности — тот же набор задач, что и раньше.
FEATURE_ALIASES = enrich_features.CATALOG_VIEW_MAP

CHARACTERS = (
    ('qual', 'Качественная'),
    ('quant', 'Количественная'),
)

# Группа фильтра (единственное число, ею зовут `skip` и ключи разметки) →
# ключ активного состояния (у списков — множественное число).
ACTIVE_KEY = {'topic': 'topics', 'tag': 'tags', 'difficulty': 'difficulties',
              'kind': 'kind', 'character': 'character', 'source': 'sources',
              'has_solution': 'has_solution', 'feature': 'features'}
LIST_KEYS = ('topics', 'tags', 'difficulties', 'sources', 'features')

# Ключ состояния → имя параметра адреса. ⚠️ ОДНА ТАБЛИЦА на разбор, сборку
# адреса, скрытые поля формы и скрипт живого обновления (этап 3 сверяет с
# ней имена). Параметр вида зовётся `type`, а не `kind`: у мастера домашки
# `kind` занят видом РАБОТЫ (`teacher.views_work.flow_query`).
PARAM = {'topics': 'topic', 'tags': 'tag', 'difficulties': 'difficulty',
         'kind': 'type', 'test_type': 'test_type', 'character': 'character',
         'sources': 'source', 'features': 'feature',
         'has_solution': 'has_solution'}

# Подписи для двух объяснений на экране: «из 294 по теме „Монополия“» и
# «попробуйте снять фильтр „2 темы“». Три формы: одно значение, несколько
# перечислением, много — числом. Живут рядом с фильтрами, чтобы новый
# фильтр нельзя было завести, забыв, как он называется вслух.
_SCOPE = {
    'topic': ('по теме «%s»', 'по темам %s', 'по %d темам'),
    'tag': ('с тегом «%s»', 'с тегами %s', 'с %d тегами'),
    'difficulty': ('на сложности %s', 'на сложностях %s', 'на сложностях %s'),
    'kind': ('в формате «%s»',) * 3,
    'character': ('по характеру «%s»',) * 3,
    'source': ('из источника «%s»', 'из источников %s', 'из %d источников'),
    'has_solution': ('с решением',) * 3,
    'feature': ('с особенностью «%s»', 'с особенностями %s', 'с %d особенностями'),
}
_RELIEF = {
    'topic': ('тема', 'темы', 'тем'),
    'tag': ('тег', 'тега', 'тегов'),
    'difficulty': ('сложность', 'сложности', 'сложностей'),
    'kind': ('задача или тест',) * 3,
    'character': ('характер задачи',) * 3,
    'source': ('источник', 'источника', 'источников'),
    'has_solution': ('есть решение',) * 3,
    'feature': ('особенность', 'особенности', 'особенностей'),
}

# Раскладка окна «Все фильтры»: слева то, что задаёт КОРПУС, справа — то,
# что его сужает (решение владельца 04.09.2026). STRIP_KEYS — прежняя полоса
# из пяти чипов-групп; каталог её больше не рисует, конструктор домашки
# работает панелью, ключи оставлены для `pick()`.
STRIP_KEYS = ('topic', 'difficulty', 'kind', 'source', 'has_solution')
MODAL_LEFT = ('topic', 'character', 'kind', 'has_solution')
MODAL_RIGHT = ('tag', 'difficulty', 'feature', 'source')


def _plural(n, forms):
    a, b = n % 10, n % 100
    if a == 1 and b != 11:
        return forms[0]
    if 2 <= a <= 4 and not 10 <= b <= 19:
        return forms[1]
    return forms[2]


def scope_label(key, labels):
    """«по теме «X»», «по темам «X», «Y»», «по 5 темам» — второе число счётчика."""
    one, few, many = _SCOPE[key]
    labels = list(labels)
    if key == 'difficulty':
        text = difficulty_label(labels, star=False) if labels else ''
        return (one if len(labels) <= 1 else few) % text
    if len(labels) <= 1:
        return one % (labels[0] if labels else '')
    if len(labels) <= 3:
        return few % ', '.join('«%s»' % label for label in labels)
    return many % len(labels)


def relief_label(key, n):
    """Как назвать фильтр в совете «попробуйте снять …»: «тема», «2 темы»."""
    if n <= 1:
        return _RELIEF[key][0]
    return '%d %s' % (n, _plural(n, _RELIEF[key]))


# ── Разбор ───────────────────────────────────────────────────────────────

def parse(source):
    """Активные фильтры из ЛЮБОГО отображения: `request.GET`, dict, память шага.

    Возвращает словарь с нормализованными значениями. Ключи есть всегда —
    шаблону и запросу не нужно гадать, что пришло, а что нет. Списки — без
    повторов, в порядке появления; мусор (не число, не из перечня) отброшен.
    """
    get = source.get
    getlist = getattr(source, 'getlist', None)

    def one(name):
        return (get(name) or '').strip()

    def many(name, ok):
        # У QueryDict есть getlist; у обычного dict значение может быть
        # строкой (старый одиночный адрес) или уже списком (память шага).
        raw = getlist(name) if getlist else get(name)
        if raw is None:
            raw = []
        elif isinstance(raw, str):
            raw = [raw]
        out = []
        for value in raw:
            value = str(value or '').strip()
            if value and ok(value) and value not in out:
                out.append(value)
        return out

    kind = one('type')
    test_type = one('test_type')
    # Старые ссылки несли в этих параметрах точную строку `problem_type`
    # («тест: один ответ»). Переводим её в вид теста, чтобы сохранённые
    # людьми адреса продолжали открывать тот же фильтр.
    if problem_types.is_test(kind):
        kind, test_type = 'test', problem_types.test_kind(kind)
    if problem_types.is_test(test_type):
        test_type = problem_types.test_kind(test_type)
    if kind not in ('open', 'test'):
        kind = ''
    if kind != 'test' or test_type not in problem_types.TEST_KINDS:
        test_type = ''

    character = one('character')
    if character not in dict(CHARACTERS):
        character = ''

    return {
        'q': one('q'),
        'topics': many('topic', str.isdigit),
        'tags': many('tag', str.isdigit),
        'difficulties': many('difficulty',
                             lambda v: v.isdigit() and 1 <= int(v) <= 5),
        'kind': kind,
        'test_type': test_type,
        'character': character,
        'sources': many('source', str.isdigit),
        'has_solution': one('has_solution') == '1',
        'features': _feature_keys(many(
            'feature', lambda v: v in dict(FEATURES) or v in FEATURE_ALIASES)),
    }


def _pairs(carry, state, with_query):
    pairs = list(carry.items())
    if with_query and state.get('q'):
        pairs.append(('q', state['q']))
    for name, param in PARAM.items():
        value = state.get(name)
        if name in LIST_KEYS:
            pairs += [(param, v) for v in value or ()]
        elif name == 'has_solution':
            if value:
                pairs.append((param, '1'))
        elif value:
            pairs.append((param, value))
    return pairs


def query(carry, active, **changes):
    """Строка параметров с изменёнными фильтрами; всё остальное сохраняется.

    ⚠️ АДРЕСА ВАРИАНТОВ СТРОИТ ПИТОН, А НЕ ШАБЛОН. Пока их клеил шаблон,
    каждый экран терял свой набор «чужих» параметров: каталог — режим
    отображения, домашка — занятие и вид работы. `carry` называет их явно.
    Списки уезжают повторами параметра: `?topic=1&topic=2`.
    """
    from urllib.parse import urlencode

    state = dict(active)
    state.update(changes)
    pairs = _pairs(carry, state, with_query=True)
    return ('?' + urlencode(pairs)) if pairs else '?'


def _hidden_fields(carry, active):
    """Пары (имя, значение) для скрытых полей GET-формы. Без `q`."""
    return _pairs(carry, active, with_query=False)


def is_empty(active):
    """Ни один фильтр не выбран (запрос `q` фильтром не считается)."""
    return not any(active[key] for key in ACTIVE_KEY.values())


def selected_count(active):
    """Сколько значений выбрано — бейдж на кнопке «Все фильтры».

    Список — по числу значений; вид вместе с форматом теста — одно
    значение (и один чип); характер и решение — по одному.
    """
    return (sum(len(active[key]) for key in LIST_KEYS)
            + bool(active['kind']) + bool(active['character'])
            + bool(active['has_solution']))


def _toggle(values, value):
    """Список без значения, если оно там было, иначе — с ним."""
    values = list(values)
    if value in values:
        values.remove(value)
    else:
        values.append(value)
    return values


# ── Набор задач ──────────────────────────────────────────────────────────

def base_queryset(gate='catalog'):
    """Исходный набор задач ДО фильтров.

    `gate='catalog'` — только проверенное человеком: публичный каталог.
    `gate='tutor'`   — всё опубликованное без брака: экран домашки видит
                       и то, что человек ещё не смотрел (так было всегда,
                       и менять это молча нельзя — репетитор собирает
                       работу из другого набора).
    """
    from problems.models import Problem

    # ⚠️ Четвёртый признак невидимости — состояние ТЕКСТА задачи
    # (ADR про content_status): битый текст скрыт независимо от того,
    # смотрел ли его человек и что сказал детектор качества.
    qs = Problem.objects.filter(status=Problem.Status.PUBLISHED,
                                needs_quality_review=False,
                                content_status=Problem.ContentStatus.OK)
    if gate == 'catalog':
        qs = qs.filter(hidden_pending_review=False)
    return qs


def _feature_keys(values):
    """Ключи витрины разворачиваются в особенности, порядок сохраняется."""
    out = []
    for value in values:
        for key in FEATURE_ALIASES.get(value, (value,)):
            if key not in out:
                out.append(key)
    return out


def _with_features_text(qs):
    """Особенности как текст — для вхождения ключа на любой базе.

    ⚠️ НЕ `features__contains`: jsonb-вложение умеет только PostgreSQL, а
    тесты живут на SQLite. Ключ в JSON всегда стоит в кавычках, поэтому
    «"graph"» не совпадёт с чужим ключом; список плоский, вложенных
    объектов в поле нет.
    """
    if 'features_text' in qs.query.annotations:
        return qs
    return qs.annotate(features_text=Cast('features', TextField()))


def apply(qs, active, skip=()):
    """Наложить активные фильтры. `skip` — не накладывать эти (для счётчиков)."""
    if 'topic' not in skip and active['topics']:
        qs = qs.filter(topics__id__in=active['topics'])
    if 'tag' not in skip and active['tags']:
        # Несколько тегов — И, а не ИЛИ: человек сужает, а не расширяет.
        for tag_id in active['tags']:
            qs = qs.filter(tags__id=tag_id)
    if 'difficulty' not in skip and active['difficulties']:
        qs = qs.filter(difficulty__in=[int(d) for d in active['difficulties']])
    if 'kind' not in skip and active['kind']:
        if active['kind'] == 'test':
            qs = qs.filter(problem_type__in=problem_types.TEST_TYPE_VALUES)
            if active['test_type']:
                qs = qs.filter(
                    problem_type__in=problem_types.TYPES_BY_KIND[active['test_type']])
        else:
            qs = qs.exclude(problem_type__in=problem_types.TEST_TYPE_VALUES)
    if 'character' not in skip and active['character']:
        qs = qs.filter(character=active['character'])
    if 'source' not in skip and active['sources']:
        qs = qs.filter(source_references__source_id__in=active['sources'])
    if 'has_solution' not in skip and active['has_solution']:
        # ⚠️ ТОТ ЖЕ СМЫСЛ, ЧТО В КАТАЛОГЕ: решение есть И оно проверено.
        # На экране домашки проверка решения раньше не спрашивалась —
        # см. `apply_solution_review`, старое поведение сохранено параметром.
        qs = qs.exclude(solution='')
    if 'feature' not in skip and active['features']:
        # ⚠️ EXISTS, А НЕ СОЕДИНЕНИЕ С `distinct()`. У задачи
        # особенностей несколько; обычное соединение размножило бы её
        # строку по числу совпавших ключей, и `count()` соврал бы.
        # `distinct()` это чинит, но ценой сортировки всего результата.
        # EXISTS не размножает ничего и останавливается на первом
        # совпадении.
        from problems.models import ProblemFeature
        qs = qs.filter(Exists(ProblemFeature.objects.filter(
            problem=OuterRef('pk'),
            feature__key__in=active['features'])))
    return qs


def apply_solution_review(qs, active, strict=True):
    """Довесок к «есть решение»: показывать ли непроверенные решения.

    Каталог всегда прятал решения с `solution_needs_review=True`, экран
    домашки — нет. Разводим параметром, а не двумя копиями фильтра.
    """
    if active['has_solution'] and strict:
        qs = qs.filter(solution_needs_review=False)
    return qs


# ── Варианты и числа по ним ──────────────────────────────────────────────

def _counted(qs, active, key):
    """Набор для счётчика варианта: все фильтры, КРОМЕ считаемого."""
    return apply(qs, active, skip=(key,))


def _tally(qs, field):
    """Сколько задач набора приходится на каждое значение `field`.

    ⚠️ ГРУППИРОВКОЙ, А НЕ СПИСКОМ `id__in`. Первый вариант вытаскивал все
    первичные ключи в питон и вкладывал их в запрос списком — один только
    разбор такого SQL стоил больше секунды на КАЖДОЙ отрисовке каталога.
    База умеет посчитать это сама, одним GROUP BY.
    """
    return {row[field]: row['n'] for row in
            qs.values(field).annotate(n=Count('id', distinct=True))
            if row[field] is not None}


def _feature_tally(qs):
    """Сколько задач у каждой из двенадцати особенностей.

    Одна группировка по связи `ProblemFeature`, а не чтение JSON у каждой
    строки банка. `distinct=True` обязателен: у задачи особенностей
    несколько, и считать надо ЗАДАЧИ, а не строки связи.
    """
    from problems.models import ProblemFeature

    rows = (ProblemFeature.objects
            .filter(problem__in=qs.values('pk'))
            .values('feature__key')
            .annotate(n=Count('problem_id', distinct=True)))
    return Counter({row['feature__key']: row['n'] for row in rows})


def _corpus(base):
    """Что вообще есть в корпусе — считается один раз на сборку.

    ⚠️ ВИДИМОСТЬ ВАРИАНТА И ГРУППЫ СЧИТАЕТСЯ ПО КОРПУСУ, ЧИСЛА — ПО СУЖЕНИЮ.
    Первый вариант решал и то и другое по отфильтрованному набору, и
    фильтры ИСЧЕЗАЛИ по мере сужения: выбрал тему и сложность — пропала
    строка «Источник», а вместе с ней и способ снять уже выбранный
    источник. Правило нуля — про то, есть ли такое в банке вообще, а не
    про то, что осталось после трёх галочек.
    """
    return {
        'topics': _tally(base, 'topics__id'),
        'difficulty': _tally(base, 'difficulty'),
        'types': _tally(base, 'problem_type'),
        'sources': _tally(base, 'source_references__source_id'),
        'character': _tally(base, 'character'),
        'features': _feature_tally(base),
        'tags': base.filter(tags__isnull=False).exists(),
        'solution': base.exclude(solution='').exists(),
    }


def _option(value, label, count, active, **extra):
    return dict({'value': value, 'label': label, 'count': count,
                 'zero': count == 0, 'active': active}, **extra)


def _topic_options(base, active, corpus):
    """Темы по пяти блокам владельца; в блоке — только темы с задачами."""
    from problems.models import Topic

    tally = _tally(_counted(base, active, 'topic'), 'topics__id')
    by_block = {}
    for topic in Topic.objects.filter(id__in=list(corpus['topics'])):
        if is_known(topic.name):
            by_block.setdefault(block_of(topic.name), []).append(topic)

    groups = []
    for key, label, _names in BLOCKS:
        rows = sorted(by_block.get(key, ()), key=lambda t: order_in_block(t.name))
        if not rows:
            continue
        options = [_option(str(t.id), t.name, tally.get(t.id, 0),
                           str(t.id) in active['topics'],
                           section=section_of(t.name)) for t in rows]
        groups.append({
            'key': key, 'label': label, 'section': BLOCK_SECTION[key],
            'options': options,
            'topics': len(options),
            'count': sum(o['count'] for o in options),
            'selected': sum(1 for o in options if o['active']),
            'open': any(o['active'] for o in options),
        })
    return groups


def _difficulty_options(base, active, corpus):
    counted = _tally(_counted(base, active, 'difficulty'), 'difficulty')
    return [_option(str(level), '★' * level, counted.get(level, 0),
                    str(level) in active['difficulties'])
            for level in range(1, 6) if corpus['difficulty'].get(level)]


def _is_test(problem_type):
    return problem_types.is_test(problem_type)


def _kind_tally(by_type, kind):
    """Сколько задач у ВИДА теста: сумма по всем строкам `problem_type`,
    которые ему отвечают. Строк у вида несколько — словаря названий два."""
    return sum(by_type.get(value, 0) for value in problem_types.TYPES_BY_KIND[kind])


def _kind_options(base, active, corpus):
    # ⚠️ ОДИН ПРОХОД, А НЕ ТРИ. Одна группировка по `problem_type` даёт и
    # «сколько тестов», и «сколько задач», и «сколько каждого формата».
    by_type = _tally(_counted(base, active, 'kind'), 'problem_type')
    n_test = sum(n for t, n in by_type.items() if _is_test(t))
    n_open = sum(n for t, n in by_type.items() if not _is_test(t))
    has_test = any(_is_test(t) for t in corpus['types'])
    has_open = any(not _is_test(t) for t in corpus['types'])
    options = []
    if has_open:
        options.append(_option('open', 'Развёрнутая задача', n_open,
                               active['kind'] == 'open'))
    if has_test:
        options.append(_option('test', 'Тест', n_test, active['kind'] == 'test'))
    return {
        'options': options,
        # Форматы теста — ПОД «Тест»; только те, что есть в корпусе.
        # Счёт вида — сумма по всем строкам типа, которые ему отвечают.
        'test_types': [_option(kind, label, _kind_tally(by_type, kind),
                               active['test_type'] == kind)
                       for kind, label in TEST_TYPES
                       if _kind_tally(corpus['types'], kind)],
    }


def _source_options(base, active, corpus):
    from problems.models import Source

    tally = _tally(_counted(base, active, 'source'),
                   'source_references__source_id')
    rows = Source.objects.filter(id__in=list(corpus['sources'])).order_by('name')
    return [_option(str(s.id), s.name, tally.get(s.id, 0),
                    str(s.id) in active['sources']) for s in rows]


def _solution_option(base, active):
    counted = _counted(base, active, 'has_solution').exclude(solution='')
    return _option('1', 'Есть решение', counted.distinct().count(),
                   active['has_solution'])


def _tag_options(base, active):
    """Теги ВЫБРАННЫХ ТЕМ списком плюс уже выбранные чипами.

    ⚠️ СПИСКОМ ВСЕ ТЕГИ НЕ ПОКАЗАТЬ. Их 552 сегодня и 343 в таксономии v2 —
    это поле ввода с подсказками, а не набор переключателей. Списком под
    полем идут только теги выбранных тем: медиана 11 на тему, помещаются.
    """
    from problems.models import Tag

    counted = _counted(base, active, 'tag')
    listed = []
    if active['topics']:
        tally = _tally(counted, 'tags__id')
        top = sorted(tally.items(), key=lambda kv: -kv[1])[:40]
        names = {t.id: t.name for t in Tag.objects.filter(id__in=dict(top))}
        listed = [_option(str(tid), names.get(tid, ''), n, str(tid) in active['tags'])
                  for tid, n in top if tid in names]
        listed.sort(key=lambda o: (-o['count'], o['label']))

    chosen = []
    if active['tags']:
        for tag in Tag.objects.filter(id__in=active['tags']):
            chosen.append({'value': str(tag.id), 'label': tag.name,
                           'count': None, 'zero': False, 'active': True})

    return {'listed': listed, 'chosen': chosen}


def _character_options(base, active, corpus):
    """Характер задачи — из поля `Problem.character`; пусто в корпусе → нет группы."""
    tally = _tally(_counted(base, active, 'character'), 'character')
    return [_option(value, label, tally.get(value, 0), active['character'] == value)
            for value, label in CHARACTERS if corpus['character'].get(value)]


def _feature_options(base, active, corpus):
    """Особенности — из связи `ProblemFeature`.

    Два порога, и они про разное. ПРАВИЛО НУЛЯ: особенности, которой в
    корпусе нет ни у одной задачи, в списке нет вовсе — пустой фильтр хуже
    отсутствующего, он обещает отбор и возвращает ноль. ПОРОГ ПОКРЫТИЯ
    (`catalog_visible_keys`, решение владельца 07.09.2026): «С реальной
    олимпиады» ждёт, пока признак наберётся хотя бы у десятой части задач.
    Первый порог — про наличие данных вообще, второй — про их полноту.
    """
    total = base.count() if corpus['features'] else 0
    coverage = {key: (n / total if total else 0.0)
                for key, n in corpus['features'].items()}
    visible = set(enrich_features.catalog_visible_keys(coverage))
    tally = _feature_tally(_counted(base, active, 'feature'))
    return [_option(value, label, tally.get(value, 0), value in active['features'])
            for value, label in FEATURES
            if corpus['features'].get(value) and value in visible]


# ── Сборка контекста для шаблона ─────────────────────────────────────────

def difficulty_label(levels, star=True):
    """«★ 4–5»: соседние ступени схлопнуты в диапазон, разрывы — запятой."""
    levels = sorted({int(x) for x in levels})
    ranges = []
    start = prev = None
    for level in levels:
        if start is None:
            start = prev = level
        elif level == prev + 1:
            prev = level
        else:
            ranges.append((start, prev))
            start = prev = level
    if start is not None:
        ranges.append((start, prev))
    text = ', '.join(str(a) if a == b else '%d–%d' % (a, b) for a, b in ranges)
    return ('★ ' + text) if star else text


def _chips(carry, active, topics, tags, kind, character, sources, feature):
    """Полоса под полем: ТОЛЬКО выбранное, по чипу на значение.

    Порядок — как в мокапе владельца 04.09.2026: темы, теги, сложность,
    вид, характер, решение, особенности, источники. У каждого чипа адрес,
    который снимает ровно его: крестик работает и без JavaScript.

    ⚠️ ЧИП ТЕМЫ НЕСЁТ РАЗДЕЛ КАРТЫ (`section`) — им красится чип, чтобы
    полоса, 3D-карта и страница задачи говорили одним цветом.
    """
    chips = []
    for group in topics:
        for option in group['options']:
            if option['active']:
                chips.append({'kind': 'topic', 'value': option['value'],
                              'label': option['label'], 'section': option['section'],
                              'remove_url': query(carry, active, topics=_toggle(
                                  active['topics'], option['value']))})
    for option in tags['chosen']:
        chips.append({'kind': 'tag', 'value': option['value'],
                      'label': option['label'],
                      'remove_url': query(carry, active, tags=_toggle(
                          active['tags'], option['value']))})
    if active['difficulties']:
        chips.append({'kind': 'difficulty', 'value': ','.join(active['difficulties']),
                      'label': difficulty_label(active['difficulties']),
                      'remove_url': query(carry, active, difficulties=[])})
    if active['kind']:
        label = 'Развёрнутая задача' if active['kind'] == 'open' else 'Тест'
        if active['test_type']:
            label = 'Тест · ' + problem_types.KIND_LABELS[active['test_type']]
        chips.append({'kind': 'kind', 'value': active['kind'], 'label': label,
                      'remove_url': query(carry, active, kind='', test_type='')})
    if active['character']:
        chips.append({'kind': 'character', 'value': active['character'],
                      'label': dict(CHARACTERS)[active['character']],
                      'remove_url': query(carry, active, character='')})
    if active['has_solution']:
        chips.append({'kind': 'solution', 'value': '1', 'label': 'С решением ✓',
                      'remove_url': query(carry, active, has_solution=False)})
    for key in active['features']:
        chips.append({'kind': 'feature', 'value': key, 'label': dict(FEATURES)[key],
                      'remove_url': query(carry, active, features=_toggle(
                          active['features'], key))})
    names = {o['value']: o['label'] for o in sources}
    missing = [s for s in active['sources'] if s not in names]
    if missing:
        # ⚠️ ИСТОЧНИК ВЫБРАН, НО В КОРПУСЕ ЕГО ЗАДАЧ НЕТ (например, все
        # скрыты шлюзом): в вариантах его нет, а чип обязан быть — иначе
        # фильтр нечем снять, и бейдж врёт числом.
        from problems.models import Source
        names.update({str(pk): name for pk, name in
                      Source.objects.filter(pk__in=missing).values_list('pk', 'name')})
    for value in active['sources']:
        if names.get(value):
            chips.append({'kind': 'source', 'value': value, 'label': names[value],
                          'remove_url': query(carry, active, sources=_toggle(
                              active['sources'], value))})
    return chips


def build(base, active, *, mode='strip', action='', hidden=(), carry=None,
          solution_strict=True):
    """Всё, что нужно шаблонам фильтров, и отфильтрованный набор.

    Возвращает `(queryset, context)`. Оба экрана кладут `context` в свой
    контекст под именем `filters`: каталог рисует полосу чипов и окно,
    конструктор домашки — панель `catalog/_filters.html`.

    `carry` — параметры экрана, которые обязаны пережить смену фильтра
    (режим отображения у каталога; занятие и вид работы у домашки).
    """
    carry = dict(carry or {})
    qs = apply_solution_review(apply(base, active), active,
                               strict=solution_strict)
    corpus = _corpus(base)

    topics = _topic_options(base, active, corpus)
    kind = _kind_options(base, active, corpus)
    tags = _tag_options(base, active)
    sources = _source_options(base, active, corpus)
    difficulty = _difficulty_options(base, active, corpus)
    solution = _solution_option(base, active)
    character = _character_options(base, active, corpus)
    feature = _feature_options(base, active, corpus)

    # ── Адреса вариантов: повторный выбор СНИМАЕТ значение, так что «✕» на
    #    чипе и сам вариант ведут в одно место.
    for group in topics:
        for option in group['options']:
            option['url'] = query(carry, active,
                                  topics=_toggle(active['topics'], option['value']))
    for option in difficulty:
        option['url'] = query(carry, active,
                              difficulties=_toggle(active['difficulties'], option['value']))
    for option in kind['options']:
        option['url'] = query(carry, active, test_type='',
                              kind='' if option['active'] else option['value'])
    for option in kind['test_types']:
        option['url'] = query(carry, active, kind='test',
                              test_type='' if option['active'] else option['value'])
    for option in sources:
        option['url'] = query(carry, active,
                              sources=_toggle(active['sources'], option['value']))
    solution['url'] = query(carry, active, has_solution=not active['has_solution'])
    for option in tags['listed'] + tags['chosen']:
        option['url'] = query(carry, active,
                              tags=_toggle(active['tags'], option['value']))
    for option in character:
        option['url'] = query(carry, active,
                              character='' if option['active'] else option['value'])
    for option in feature:
        option['url'] = query(carry, active,
                              features=_toggle(active['features'], option['value']))

    topic_labels = [o['label'] for g in topics for o in g['options'] if o['active']]
    tag_labels = [t['label'] for t in tags['chosen']]
    source_labels = [o['label'] for o in sources if o['active']]
    feature_labels = [o['label'] for o in feature if o['active']]
    character_labels = [o['label'] for o in character if o['active']]
    kind_label = next((o['label'] for o in kind['options'] if o['active']), '')
    if active['test_type']:
        kind_label = next((o['label'] for o in kind['test_types']
                           if o['active']), kind_label)

    groups = [
        {'key': 'topic', 'label': 'Тема', 'type': 'topic',
         'groups': topics, 'visible': bool(topics),
         'value': ','.join(active['topics']), 'labels': topic_labels,
         'value_label': ', '.join(topic_labels)},
        {'key': 'tag', 'label': 'Тег', 'type': 'tag',
         'tags': tags, 'visible': corpus['tags'],
         'value': ','.join(active['tags']), 'labels': tag_labels,
         'value_label': ', '.join(tag_labels)},
        {'key': 'difficulty', 'label': 'Сложность', 'type': 'choice',
         'options': difficulty, 'visible': bool(difficulty),
         'value': ','.join(active['difficulties']),
         'labels': sorted(active['difficulties'], key=int),
         'value_label': (difficulty_label(active['difficulties'], star=False)
                         if active['difficulties'] else '')},
        {'key': 'kind', 'label': 'Задача или тест', 'type': 'kind',
         'options': kind['options'], 'test_types': kind['test_types'],
         'visible': bool(kind['options']),
         'value': active['kind'], 'labels': [kind_label] if kind_label else [],
         'value_label': kind_label},
        {'key': 'character', 'label': 'Характер задачи', 'type': 'choice',
         'options': character, 'visible': bool(character),
         'value': active['character'], 'labels': character_labels,
         'value_label': ', '.join(character_labels)},
        {'key': 'source', 'label': 'Источник', 'type': 'select',
         'options': sources, 'visible': bool(sources),
         'value': ','.join(active['sources']), 'labels': source_labels,
         'value_label': ', '.join(source_labels)},
        {'key': 'has_solution', 'label': 'Есть решение', 'type': 'flag',
         'option': solution, 'visible': corpus['solution'],
         'value': '1' if active['has_solution'] else '',
         'labels': ['Есть решение'] if active['has_solution'] else [],
         'value_label': 'Есть решение' if active['has_solution'] else ''},
        {'key': 'feature', 'label': 'Особенности', 'type': 'choice',
         'options': feature, 'visible': bool(feature),
         'value': ','.join(active['features']), 'labels': feature_labels,
         'value_label': ', '.join(feature_labels)},
    ]
    # Снять группу целиком — «снять» в окне и в панели конструктора.
    clear = {'topic': {'topics': []}, 'tag': {'tags': []},
             'difficulty': {'difficulties': []},
             'kind': {'kind': '', 'test_type': ''},
             'character': {'character': ''}, 'source': {'sources': []},
             'has_solution': {'has_solution': False}, 'feature': {'features': []}}
    for group in groups:
        group['clear_url'] = query(carry, active, **clear[group['key']])

    by_key = {g['key']: g for g in groups}
    shown = [g for g in groups if g['visible']]
    chosen = [g for g in shown if g['value']]

    def pick(keys):
        return [by_key[k] for k in keys if by_key[k]['visible']]

    return qs, {
        'mode': mode,
        'action': action,
        'hidden': list(hidden),
        'active': active,
        'groups': shown,
        # Порядок раскладок задан модулем, а не шаблоном: экраны обязаны
        # показывать ОДИН набор, и решать это должен общий код.
        'strip': pick(STRIP_KEYS),
        'modal_left': pick(MODAL_LEFT),
        'modal_right': pick(MODAL_RIGHT),
        'chosen': chosen,
        'has_any': not is_empty(active),
        'carry': carry,
        # Полоса под полем каталога: только выбранное, по чипу на значение.
        'chips': _chips(carry, active, topics, tags, kind, character,
                        sources, feature),
        'selected_count': selected_count(active),
        # Подпись второго числа счётчика: «из 294 по теме „Монополия“».
        'scope': scope_label(chosen[0]['key'], chosen[0]['labels']) if chosen else '',
        # ⚠️ АКТИВНЫЕ ФИЛЬТРЫ СКРЫТЫМИ ПОЛЯМИ — ДЛЯ ЛЮБОЙ GET-ФОРМЫ НА
        # ЭКРАНЕ. Чипы — ссылки, а поиск — форма; без этих полей отправка
        # молча снимала бы всё выбранное. Своего `q` здесь нет: его
        # печатают в самой форме.
        'hidden_fields': _hidden_fields(carry, active),
        # Сброс снимает ФИЛЬТРЫ, но не запрос: человек, нажавший «сбросить
        # фильтры», не просил забыть, что он искал.
        'reset_url': query(carry, {'q': active['q']}),
        'total_url': query(carry, active),
    }


def field_keys(context):
    """Ключи показанных фильтров — для теста «наборы экранов совпадают»."""
    return [g['key'] for g in context['groups']]
