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
проверенное человеком (14 458 задач), экран домашки — всё опубликованное без
брака (28 593). Это РАЗНЫЕ правила, и сведение их в одно молча поменяло бы
репетитору набор, из которого он собирает работу. `base_queryset(gate=...)`
называет правило явно.

⚠️ ГРУППА ФИЛЬТРА ПОКАЗЫВАЕТСЯ, ТОЛЬКО ЕСЛИ У НЕЁ ЕСТЬ ВАРИАНТЫ. «Характер
задачи» и «Особенности» в базе не размечены — у них ноль вариантов, и в
разметку они не попадают вовсе. Серый переключатель, который не нажимается,
хуже его отсутствия. Это ОБЩЕЕ правило (`Group.visible`), а не заглушка на
два поля: как только разметка появится, группы включатся сами.
Вариант с нулём внутри показанной группы — другое дело: ноль честно говорит,
что такого формата в банке пока нет.
"""
from __future__ import annotations

from django.db.models import Count, Q

# ── Тема: шесть разделов над двадцатью тремя каноническими темами ────────
#
# ⚠️ ЭТО НЕ РАЗДЕЛЫ КАРТЫ. У карты тем (`catalog/data/topic_map.json`) свои
# семь разделов над таксономией v2 (29 тем). Здесь — группировка ЖИВЫХ тем
# базы, чтобы список из 23 строк читался; названия разделов задал владелец.
TOPIC_GROUPS = (
    ('micro', 'Микроэкономика', (
        'Альтернативные издержки и КПВ',
        'Спрос и предложение',
        'Эластичность',
        'Теория потребителя и полезность',
        'Теория фирмы: производство и издержки',
        'Совершенная конкуренция',
        'Монополия и ценовая дискриминация',
        'Олигополия и теория игр',
        'Вмешательство государства',
        'Рынок труда',
        'Неравенство доходов',
    )),
    ('world', 'Мировая экономика', (
        'Международная торговля',
    )),
    ('macro', 'Макроэкономика', (
        'ВВП и национальные счета',
        'Совокупный спрос и совокупное предложение',
        'Инфляция и безработица',
        'Фискальная политика',
        'Монетарная политика',
        'Экономический рост и циклы',
    )),
    ('fin', 'Финансы', (
        'Финансы и финансовые инструменты',
    )),
    ('math', 'Математика и данные', (
        'Эконометрика и анализ данных',
        'Математика и оптимизация',
    )),
    ('other', 'Прочее', (
        'Введение в экономическую теорию',
        'Поведенческая экономика',
    )),
)

# ── «Задача или тест»: выбор из двух, у теста — продолжение вбок ─────────
#
# ⚠️ ЧЕТЫРЕ ТИПА ТЕСТА ПЕРЕЧИСЛЕНЫ ЗДЕСЬ, А НЕ ВЗЯТЫ ИЗ БАЗЫ. Тип, которого
# в банке нет, обязан показаться с нулём: ноль говорит «такого формата пока
# не завезли», а молчание неотличимо от «фильтр сломался». Сегодня нулём
# идёт «короткий ответ» — 67 задач есть в базе, но все скрыты шлюзами.
TEST_TYPES = (
    ('тест: один ответ', 'один верный'),
    ('тест: верно/неверно', 'верно/неверно'),
    ('тест: все верные', 'выбор всех верных'),
    ('тест: числовой ответ', 'короткий ответ'),
)

# Признак теста один на весь проект: `problem_type` начинается с «тест:».
# Тот же признак у поиска по словам (`catalog.hybrid.lexical_search`).
TEST_PREFIX = 'тест'

# ── Особенности ──────────────────────────────────────────────────────────
#
# ⚠️ «РЕАЛЬНЫЕ ДАННЫЕ» ИЗ СПИСКА УБРАНЫ — решение владельца 01.09.2026.
# Поля в модели пока нет ни у одной особенности, поэтому список ниже —
# заготовка: `_feature_options()` возвращает пустоту, группа скрывается.
FEATURES = (
    ('graph', 'Есть график'),
    ('table', 'Есть таблица'),
    ('proof', 'Требует доказательства'),
)

# Характер задачи — та же заготовка: поля в модели нет.
CHARACTERS = (
    ('calc', 'Расчётная'),
    ('theory', 'Теоретическая'),
    ('applied', 'Прикладная'),
)

# Подписи для двух объяснений на экране: «из 294 по теме „Монополия“» и
# «попробуйте снять фильтр „сложность“». Живут рядом с самими фильтрами,
# чтобы новый фильтр нельзя было завести, забыв, как он называется вслух.
SCOPE_LABEL = {
    'topic': 'по теме «%s»',
    'tag': 'с тегом «%s»',
    'difficulty': 'на сложности %s',
    'kind': 'в формате «%s»',
    'character': 'по характеру «%s»',
    'source': 'из источника «%s»',
    'has_solution': 'с решением%.0s',
    'feature': 'с особенностью «%s»',
}
RELIEF_LABEL = {
    'topic': 'тема',
    'tag': 'тег',
    'difficulty': 'сложность',
    'kind': 'задача или тест',
    'character': 'характер задачи',
    'source': 'источник',
    'has_solution': 'есть решение',
    'feature': 'особенности',
}

# Пять частых фильтров стоят полосой сверху, остальные — за «Все фильтры».
STRIP_KEYS = ('topic', 'difficulty', 'kind', 'source', 'has_solution')

# Раскладка окна «Все фильтры»: слева то, что задаёт КОРПУС, справа —
# то, что его сужает (решение владельца).
MODAL_LEFT = ('topic', 'kind', 'source', 'has_solution')
MODAL_RIGHT = ('tag', 'difficulty', 'character', 'feature')


# ── Разбор ───────────────────────────────────────────────────────────────

def parse(source):
    """Активные фильтры из ЛЮБОГО отображения: `request.GET`, dict, память шага.

    Возвращает словарь с нормализованными значениями. Ключи есть всегда —
    шаблону и запросу не нужно гадать, что пришло, а что нет.
    """
    get = source.get

    def one(name):
        return (get(name) or '').strip()

    # ⚠️ ПАРАМЕТР НАЗЫВАЕТСЯ `type`, А НЕ `kind`, И ЭТО НЕ ВКУСОВЩИНА.
    # У мастера домашки `kind` уже занят видом РАБОТЫ (домашка/контрольная,
    # `teacher.views_work.flow_query`); фильтр с тем же именем ломал бы
    # переключатель на всех трёх шагах. Заодно старые ссылки каталога
    # (`?type=тест: один ответ`) продолжают работать — см. ниже.
    kind = one('type')
    test_type = one('test_type')
    if kind in dict(TEST_TYPES):          # старая ссылка: точный тип теста
        kind, test_type = 'test', kind
    if kind not in ('open', 'test'):
        kind = ''
    if kind != 'test' or test_type not in dict(TEST_TYPES):
        test_type = ''

    difficulty = one('difficulty')
    if not (difficulty.isdigit() and 1 <= int(difficulty) <= 5):
        difficulty = ''

    topic = one('topic')
    if not topic.isdigit():
        topic = ''

    source_id = one('source')
    if not source_id.isdigit():
        source_id = ''

    # Тегов может быть несколько: `?tag=1&tag=2`. У обычного dict метода
    # getlist нет — тогда читаем одиночное значение.
    getlist = getattr(source, 'getlist', None)
    raw_tags = getlist('tag') if getlist else [one('tag')]
    tags = []
    for raw in raw_tags:
        raw = (raw or '').strip()
        if raw.isdigit() and raw not in tags:
            tags.append(raw)

    return {
        'q': one('q'),
        'topic': topic,
        'tags': tags,
        'difficulty': difficulty,
        'kind': kind,
        'test_type': test_type,
        'character': one('character'),
        'source': source_id,
        'has_solution': one('has_solution') == '1',
        'feature': one('feature'),
    }


# Имя фильтра внутри модуля → имя параметра в адресе. Одна таблица на
# разбор и на сборку: разъехаться им теперь негде.
PARAM = {'topic': 'topic', 'difficulty': 'difficulty', 'kind': 'type',
         'test_type': 'test_type', 'character': 'character',
         'source': 'source', 'feature': 'feature'}


def query(carry, active, **changes):
    """Строка параметров с изменёнными фильтрами; всё остальное сохраняется.

    ⚠️ АДРЕСА ВАРИАНТОВ СТРОИТ ПИТОН, А НЕ ШАБЛОН. Пока их клеил шаблон,
    каждый экран терял свой набор «чужих» параметров: каталог — режим
    отображения, домашка — занятие и вид работы. `carry` называет их явно.
    """
    from urllib.parse import urlencode

    state = dict(active)
    state.update(changes)

    pairs = list(carry.items())
    if state.get('q'):
        pairs.append(('q', state['q']))
    for name, param in PARAM.items():
        value = state.get(name)
        if value:
            pairs.append((param, value))
    for tag_id in state.get('tags') or ():
        pairs.append(('tag', tag_id))
    if state.get('has_solution'):
        pairs.append(('has_solution', '1'))
    return ('?' + urlencode(pairs)) if pairs else '?'


def _hidden_fields(carry, active):
    """Пары (имя, значение) для скрытых полей GET-формы. Без `q`."""
    pairs = list(carry.items())
    for name, param in PARAM.items():
        if active.get(name):
            pairs.append((param, active[name]))
    pairs += [('tag', tag_id) for tag_id in active.get('tags') or ()]
    if active.get('has_solution'):
        pairs.append(('has_solution', '1'))
    return pairs


def is_empty(active):
    """Ни один фильтр не выбран (запрос `q` фильтром не считается)."""
    return not any((active['topic'], active['tags'], active['difficulty'],
                    active['kind'], active['character'], active['source'],
                    active['has_solution'], active['feature']))


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

    qs = Problem.objects.filter(status=Problem.Status.PUBLISHED,
                                needs_quality_review=False)
    if gate == 'catalog':
        qs = qs.filter(hidden_pending_review=False)
    return qs


def apply(qs, active, skip=()):
    """Наложить активные фильтры. `skip` — не накладывать эти (для счётчиков)."""
    if 'topic' not in skip and active['topic']:
        qs = qs.filter(topics__id=active['topic'])
    if 'tag' not in skip and active['tags']:
        # Несколько тегов — И, а не ИЛИ: человек сужает, а не расширяет.
        for tag_id in active['tags']:
            qs = qs.filter(tags__id=tag_id)
    if 'difficulty' not in skip and active['difficulty']:
        qs = qs.filter(difficulty=active['difficulty'])
    if 'kind' not in skip and active['kind']:
        if active['kind'] == 'test':
            qs = qs.filter(problem_type__istartswith=TEST_PREFIX)
            if active['test_type']:
                qs = qs.filter(problem_type=active['test_type'])
        else:
            qs = qs.exclude(problem_type__istartswith=TEST_PREFIX)
    if 'source' not in skip and active['source']:
        qs = qs.filter(source_references__source_id=active['source'])
    if 'has_solution' not in skip and active['has_solution']:
        # ⚠️ ТОТ ЖЕ СМЫСЛ, ЧТО В КАТАЛОГЕ: решение есть И оно проверено.
        # На экране домашки проверка решения раньше не спрашивалась —
        # см. `solution_gate` ниже, старое поведение сохранено параметром.
        qs = qs.exclude(solution='')
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
    14 458 первичных ключей в питон и вкладывал их в запрос списком — один
    только разбор такого SQL стоил больше секунды на КАЖДОЙ отрисовке
    каталога. База умеет посчитать это сама, одним GROUP BY.
    """
    return {row[field]: row['n'] for row in
            qs.values(field).annotate(n=Count('id', distinct=True))
            if row[field] is not None}


def _topic_options(base, active):
    from problems.management.commands.apply_topic_mapping import CANONICAL
    from problems.models import Topic

    tally = _tally(_counted(base, active, 'topic'), 'topics__id')
    by_name = {t.name: t for t in Topic.objects.filter(name__in=CANONICAL)}

    groups = []
    for key, label, names in TOPIC_GROUPS:
        options = []
        for name in names:
            topic = by_name.get(name)
            if topic is None:
                continue
            options.append({'value': str(topic.id), 'label': topic.name,
                            'count': tally.get(topic.id, 0),
                            'active': active['topic'] == str(topic.id)})
        if not options:
            continue
        groups.append({
            'key': key, 'label': label, 'options': options,
            'topics': len(options),
            'count': sum(o['count'] for o in options),
            'open': any(o['active'] for o in options),
        })
    return groups


def _difficulty_options(base, active):
    counted = _counted(base, active, 'difficulty')
    rows = dict(counted.values_list('difficulty')
                .annotate(n=Count('id', distinct=True)))
    return [{'value': str(level), 'label': '★' * level,
             'count': rows.get(level, 0),
             'active': active['difficulty'] == str(level)}
            for level in range(1, 6)]


def _kind_options(base, active):
    # ⚠️ ОДИН ПРОХОД, А НЕ ТРИ. Считать «сколько тестов», «сколько задач» и
    # «сколько каждого типа» тремя запросами стоило 0,37 с из 0,79 с всей
    # сборки: `problem_type__istartswith` индексом не берётся и каждый раз
    # читает таблицу целиком. Одна группировка по `problem_type` даёт всё
    # сразу, а разложить её по вариантам питон умеет мгновенно.
    counted = _counted(base, active, 'kind')
    by_type = _tally(counted, 'problem_type')
    n_test = sum(n for t, n in by_type.items()
                 if (t or '').lower().startswith(TEST_PREFIX))
    n_open = sum(n for t, n in by_type.items()
                 if not (t or '').lower().startswith(TEST_PREFIX))
    return {
        'options': [
            {'value': 'open', 'label': 'Развёрнутая задача', 'count': n_open,
             'active': active['kind'] == 'open'},
            {'value': 'test', 'label': 'Тест', 'count': n_test,
             'active': active['kind'] == 'test'},
        ],
        # Второй столбец: появляется рядом, когда выбран тест.
        'test_types': [
            {'value': value, 'label': label, 'count': by_type.get(value, 0),
             'active': active['test_type'] == value}
            for value, label in TEST_TYPES
        ],
    }


def _source_options(base, active):
    from problems.models import Source

    tally = _tally(_counted(base, active, 'source'),
                   'source_references__source_id')
    rows = Source.objects.filter(id__in=tally).order_by('name')
    return [{'value': str(s.id), 'label': s.name, 'count': tally[s.id],
             'active': active['source'] == str(s.id)} for s in rows]


def _solution_option(base, active):
    counted = _counted(base, active, 'has_solution').exclude(solution='')
    return {'value': '1', 'label': 'Есть решение',
            'count': counted.distinct().count(),
            'active': active['has_solution']}


def _tag_options(base, active):
    """Теги ВЫБРАННОЙ ТЕМЫ списком плюс уже выбранные чипами.

    ⚠️ СПИСКОМ ВСЕ ТЕГИ НЕ ПОКАЗАТЬ. Их 552 сегодня и 343 в таксономии v2 —
    это поле ввода с подсказками, а не набор переключателей. Списком под
    полем идут только теги выбранной темы: медиана 11 на тему, помещаются.
    """
    from problems.models import Tag

    counted = _counted(base, active, 'tag')
    listed = []
    if active['topic']:
        # Теги считаем ТОЛЬКО при выбранной теме: без темы это перебор всех
        # 552 тегов по всему корпусу ради списка, которого на экране нет.
        tally = _tally(counted, 'tags__id')
        top = sorted(tally.items(), key=lambda kv: -kv[1])[:40]
        names = {t.id: t.name for t in Tag.objects.filter(id__in=dict(top))}
        listed = [{'value': str(tid), 'label': names.get(tid, ''), 'count': n,
                   'active': str(tid) in active['tags']}
                  for tid, n in top if tid in names]
        listed.sort(key=lambda o: (-o['count'], o['label']))

    chosen = []
    if active['tags']:
        for tag in Tag.objects.filter(id__in=active['tags']):
            chosen.append({'value': str(tag.id), 'label': tag.name,
                           'count': None, 'active': True})

    return {'listed': listed, 'chosen': chosen}


def _character_options(base, active):
    """Характер задачи. Поля в модели НЕТ — вариантов ноль, группа скрыта."""
    return []


def _feature_options(base, active):
    """Особенности. Поля в модели НЕТ — вариантов ноль, группа скрыта."""
    return []


def _has_data(base):
    """Есть ли у фильтра данные ВО ВСЁМ КОРПУСЕ (а не в текущей выдаче).

    ⚠️ ВИДИМОСТЬ ГРУППЫ СЧИТАЕТСЯ ПО КОРПУСУ, ЧИСЛА — ПО СУЖЕНИЮ. Первый
    вариант решал и то и другое по отфильтрованному набору, и фильтры
    ИСЧЕЗАЛИ по мере сужения: выбрал тему и сложность — пропала строка
    «Источник», а вместе с ней и способ снять уже выбранный источник.
    Правило «показываем, только если есть данные» — про то, размечено ли
    поле вообще, а не про то, что осталось после трёх галочек.
    """
    return {
        'topic': True,       # 23 канонические темы есть всегда
        'difficulty': True,  # пять ступеней — постоянный список
        'kind': True,        # «задача или тест» — постоянный выбор из двух
        'tag': base.filter(tags__isnull=False).exists(),
        'source': base.filter(source_references__isnull=False).exists(),
        'has_solution': base.exclude(solution='').exists(),
    }


# ── Чипы полосы выбранного ───────────────────────────────────────────────

def difficulty_label(levels):
    """«★ 4–5»: соседние ступени схлопнуты в диапазон, разрывы — запятой.

    Одна ступень — «★ 4». Функция готова к списку ступеней (множественный
    выбор сложности, этап 2), хотя сегодня активна одна.
    """
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
    return '★ ' + ', '.join(str(a) if a == b else '%d–%d' % (a, b)
                             for a, b in ranges)


def _chips(carry, active, topics, tags, sources):
    """Полоса под полем: ТОЛЬКО выбранное, по чипу на значение.

    Порядок — как в мокапе владельца 04.09.2026: темы, теги, сложность,
    вид, характер, решение, особенности, источник. У каждого чипа адрес,
    который снимает ровно его: крестик работает и без JavaScript.

    ⚠️ ЧИП ТЕМЫ НЕСЁТ РАЗДЕЛ КАРТЫ (`section`) — им красится чип, чтобы
    полоса, 3D-карта и страница задачи говорили одним цветом.
    """
    from .topic_blocks import section_of

    chips = []
    for group in topics:
        for option in group['options']:
            if option['active']:
                chips.append({'kind': 'topic', 'value': option['value'],
                              'label': option['label'],
                              'section': section_of(option['label']),
                              'remove_url': query(carry, active, topic='')})
    for option in tags['chosen']:
        rest = [t for t in active['tags'] if t != option['value']]
        chips.append({'kind': 'tag', 'value': option['value'],
                      'label': option['label'],
                      'remove_url': query(carry, active, tags=rest)})
    if active['difficulty']:
        chips.append({'kind': 'difficulty', 'value': active['difficulty'],
                      'label': difficulty_label([active['difficulty']]),
                      'remove_url': query(carry, active, difficulty='')})
    if active['kind']:
        label = 'Развёрнутая задача' if active['kind'] == 'open' else 'Тест'
        if active['test_type']:
            label = 'Тест · ' + dict(TEST_TYPES)[active['test_type']]
        chips.append({'kind': 'kind', 'value': active['kind'], 'label': label,
                      'remove_url': query(carry, active, kind='', test_type='')})
    if active['character'] in dict(CHARACTERS):
        chips.append({'kind': 'character', 'value': active['character'],
                      'label': dict(CHARACTERS)[active['character']],
                      'remove_url': query(carry, active, character='')})
    if active['has_solution']:
        chips.append({'kind': 'solution', 'value': '1', 'label': 'С решением ✓',
                      'remove_url': query(carry, active, has_solution=False)})
    if active['feature'] in dict(FEATURES):
        chips.append({'kind': 'feature', 'value': active['feature'],
                      'label': dict(FEATURES)[active['feature']],
                      'remove_url': query(carry, active, feature='')})
    if active['source']:
        label = next((o['label'] for o in sources if o['active']), '')
        if not label:
            # ⚠️ ИСТОЧНИК ВЫБРАН, НО ПОД ОСТАЛЬНЫМИ ФИЛЬТРАМИ У НЕГО НОЛЬ
            # ЗАДАЧ: в список вариантов он не попал (там только счётные),
            # а чип обязан быть — иначе фильтр нечем снять, и бейдж на
            # «Все фильтры» врёт числом. Поймано глазами 04.09.2026.
            from problems.models import Source
            label = (Source.objects.filter(pk=active['source'])
                     .values_list('name', flat=True).first() or '')
        if label:
            chips.append({'kind': 'source', 'value': active['source'],
                          'label': label,
                          'remove_url': query(carry, active, source='')})
    return chips


# ── Сборка контекста для шаблона ─────────────────────────────────────────

def build(base, active, *, mode='strip', action='', hidden=(), carry=None,
          solution_strict=True):
    """Всё, что нужно шаблону `catalog/_filters.html`, и отфильтрованный набор.

    Возвращает `(queryset, context)`. Оба экрана кладут `context` в свой
    контекст под именем `filters` и показывают компонент включением.

    `carry` — параметры экрана, которые обязаны пережить смену фильтра
    (режим отображения у каталога; занятие и вид работы у домашки).
    """
    carry = dict(carry or {})
    qs = apply_solution_review(apply(base, active), active,
                               strict=solution_strict)

    topics = _topic_options(base, active)
    kind = _kind_options(base, active)
    tags = _tag_options(base, active)
    sources = _source_options(base, active)
    difficulty = _difficulty_options(base, active)
    solution = _solution_option(base, active)
    character = _character_options(base, active)
    feature = _feature_options(base, active)

    # ── Адреса вариантов. Повторный выбор СНИМАЕТ фильтр: тогда «✕» на
    #    чипе и сам чип ведут в одно и то же место, и объяснять два разных
    #    способа снять фильтр не приходится.
    for group in topics:
        for option in group['options']:
            option['url'] = query(carry, active,
                                  topic='' if option['active'] else option['value'])
    for option in difficulty:
        option['url'] = query(carry, active,
                              difficulty='' if option['active'] else option['value'])
    for option in kind['options']:
        option['url'] = query(carry, active, test_type='',
                              kind='' if option['active'] else option['value'])
    for option in kind['test_types']:
        option['url'] = query(carry, active, kind='test',
                              test_type='' if option['active'] else option['value'])
    for option in sources:
        option['url'] = query(carry, active,
                              source='' if option['active'] else option['value'])
    solution['url'] = query(carry, active, has_solution=not active['has_solution'])
    for option in tags['listed'] + tags['chosen']:
        rest = [t for t in active['tags'] if t != option['value']]
        option['url'] = query(carry, active,
                              tags=rest if option['active']
                              else active['tags'] + [option['value']])

    topic_label = ''
    for group in topics:
        for option in group['options']:
            if option['active']:
                topic_label = option['label']
    source_label = next((o['label'] for o in sources if o['active']), '')
    kind_label = next((o['label'] for o in kind['options'] if o['active']), '')
    if active['test_type']:
        kind_label = next((o['label'] for o in kind['test_types']
                           if o['active']), kind_label)

    data = _has_data(base)
    groups = [
        {'key': 'topic', 'label': 'Тема', 'type': 'topic',
         'groups': topics, 'visible': data['topic'] and bool(topics),
         'value': active['topic'], 'value_label': topic_label},
        {'key': 'tag', 'label': 'Тег', 'type': 'tag',
         'tags': tags, 'visible': data['tag'],
         'value': ','.join(active['tags']),
         'value_label': ', '.join(t['label'] for t in tags['chosen'])},
        {'key': 'difficulty', 'label': 'Сложность', 'type': 'choice',
         'options': difficulty, 'visible': data['difficulty'],
         'value': active['difficulty'],
         'value_label': '★' * int(active['difficulty'] or 0)},
        {'key': 'kind', 'label': 'Задача или тест', 'type': 'kind',
         'options': kind['options'], 'test_types': kind['test_types'],
         'visible': data['kind'],
         'value': active['kind'], 'value_label': kind_label},
        {'key': 'character', 'label': 'Характер задачи', 'type': 'choice',
         'options': character, 'visible': bool(character),
         'value': active['character'], 'value_label': ''},
        {'key': 'source', 'label': 'Источник', 'type': 'select',
         'options': sources, 'visible': data['source'],
         'value': active['source'], 'value_label': source_label},
        {'key': 'has_solution', 'label': 'Есть решение', 'type': 'flag',
         'option': solution, 'visible': data['has_solution'],
         'value': '1' if active['has_solution'] else '',
         'value_label': 'Есть решение' if active['has_solution'] else ''},
        {'key': 'feature', 'label': 'Особенности', 'type': 'choice',
         'options': feature, 'visible': bool(feature),
         'value': active['feature'], 'value_label': ''},
    ]
    # Снять один фильтр — крестик на чипе полосы.
    clear = {'topic': {'topic': ''}, 'tag': {'tags': []},
             'difficulty': {'difficulty': ''},
             'kind': {'kind': '', 'test_type': ''},
             'character': {'character': ''}, 'source': {'source': ''},
             'has_solution': {'has_solution': False}, 'feature': {'feature': ''}}
    for group in groups:
        group['clear_url'] = query(carry, active, **clear[group['key']])

    by_key = {g['key']: g for g in groups}
    shown = [g for g in groups if g['visible']]

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
        'chosen': [g for g in shown if g['value']],
        # Полоса под полем каталога: только выбранное (этап 1 редизайна).
        'chips': _chips(carry, active, topics, tags, sources),
        'has_any': not is_empty(active),
        'carry': carry,
        # ⚠️ АКТИВНЫЕ ФИЛЬТРЫ СКРЫТЫМИ ПОЛЯМИ — ДЛЯ ЛЮБОЙ GET-ФОРМЫ НА
        # ЭКРАНЕ. Варианты фильтров это ссылки, а поиск — форма; без этих
        # полей нажатие «Найти» молча снимало бы всё выбранное. Своего `q`
        # здесь нет: его печатают в самой форме.
        'hidden_fields': _hidden_fields(carry, active),
        # Сброс снимает ФИЛЬТРЫ, но не запрос: человек, нажавший «сбросить
        # фильтры», не просил забыть, что он искал.
        'reset_url': query(carry, {'q': active['q']}),
        'total_url': query(carry, active),
    }


def field_keys(context):
    """Ключи показанных фильтров — для теста «наборы экранов совпадают»."""
    return [g['key'] for g in context['groups']]
