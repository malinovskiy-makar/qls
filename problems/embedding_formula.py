# -*- coding: utf-8 -*-
"""Формула поискового отпечатка — спецификация как ДАННЫЕ, реализация одна.

Зачем модуль вообще. Обогащение записало в банк «Дано», «Найти», понятия,
поисковые запросы, заголовки и сюжеты, а формула v1 (`problem_to_text` в
`build_embeddings.py`) их не видит: она собирает `title + statement[:500] +
подпункты + темы + навыки + ai_blurb[:400] + теги`. `ai_blurb` пуст у
24 109 задач, то есть у 22 057 задач смысловой блок отпечатка пуст, хотя
данные для него в базе есть. Хуже: после замены таксономии блок «Теги» v1
срабатывает у **108** задач из 41 307 (старый список `CANONICAL_TAG_NAMES`
— 222 имени времён Батча 1, а в банке 344 канонических тега с другими
названиями), а блок «Навыки» — у трёх задач. Пересчитывать корпус на
арендованной видеокарте по такой формуле значит платить за формулу, которая
игнорирует главный результат обогащения.

Что здесь есть. `FormulaSpec` — вариант формулы данными: имя, версия,
порядок блоков, бюджеты. `build_text(problem, spec)` — единственная
реализация сборки. `SPECS` — словарь вариантов замера.

⚠️ **Спецификация `v1` обязана воспроизводить `problem_to_text` СИМВОЛ В
СИМВОЛ.** Не «похоже» и не «эквивалентно». Это единственная гарантия, что
сравнение v1 против v2 честное, а не сравнение v2 с новой опечаткой. Держит
тест `problems/tests/test_embedding_formula.py`, выборка ≥ 2 000 реальных
задач. Ради байт-в-байт у v1 свой диалект отрисовки (`'v1'` в `options`):
заголовок без метки, условие без метки и добавляется ДАЖЕ ПУСТЫМ, бюджет
подпунктов суммарный, теги по старому списку. Диалект законсервирован —
править его нельзя, иначе контроль перестанет быть контролем.

⚠️ **Весов у блоков нет, и это надо понимать буквально.** Формула склеивает
одну строку, модель кодирует её в один вектор на 1024 измерения. Вес
возникает сам, из трёх вещей: доли токенов (главный рычаг), позиции и
повтора. Ручки «вес блока» в этой архитектуре не существует; настоящие
числовые веса появятся только с многовекторной схемой — свой вектор на
блок, веса коэффициентами при поиске, — и тогда их можно будет крутить БЕЗ
пересчёта корпуса. Пока каждая попытка «поменять вес» стоит новой аренды.

⚠️ Требует `prefetch_related(*PREFETCH)` при батч-запросе, иначе на 41
тысяче задач N+1 сделает сборку текстов дольше самого кодирования.
"""
import re
from dataclasses import dataclass, field
from typing import Mapping

from problems import econ_terms

#: Связи, без которых сборка отпечатка вырождается в N+1.
PREFETCH = ('parts', 'topics', 'skills', 'tags', 'econ_concepts',
            'features_rel', 'hints', 'olympiad_refs')

#: Техническая метка импорта, не смысловая тема. Убрана из отпечатка ещё в v1.
TOPIC_TECHNICAL = 'Тест'

#: Сложность 1–5 — словом, а не цифрой (решение 07.09.2026). Голая цифра
#: модели ничего не говорит и рискует смешаться с числами условия.
DIFFICULTY_WORDS = {
    1: 'очень лёгкая', 2: 'лёгкая', 3: 'средняя',
    4: 'трудная', 5: 'очень трудная',
}

#: `character` — служебный код quant/qual; в отпечаток он идёт словом.
#: Нужен только там, где `task_nature` пуст (2 306 задач).
CHARACTER_WORDS = {'quant': 'расчётная', 'qual': 'качественная'}

#: Короткий стоп-лист совсем общих слов для блока «Понятия» (правило 3
#: чистки, раздел 3.1.1 задания). Применяется к ОБОИМ источникам понятий —
#: и к словарным `EconConcept`, и к `concepts_offlist`.
#:
#: ⚠️ Контринтуитивный замер, который стоит знать: общие слова сидят не в
#: offlist, а в СЛОВАРНЫХ понятиях. «цена» стоит у 7 645 задач (18,5 %
#: банка), «спрос» у 6 989, «издержки» у 3 528. Термин у каждой пятой
#: задачи не различает их ничем. Список намеренно короткий: правило,
#: выбрасывающее больше сотни терминов, скорее всего неверно и показывается
#: владельцу, а не применяется молча.
CONCEPT_STOPWORDS = frozenset({
    'выбор', 'оценка', 'обязательство', 'результат', 'значение',
    'величина', 'показатель', 'данные', 'задача', 'условие',
})

#: Минимальная длина термина понятия (правило 1 чистки).
CONCEPT_MIN_LEN = 3

_DIGITS_RE = re.compile(r'\d+')
_ONLY_PUNCT_RE = re.compile(r'^[\W\d_]+$', re.UNICODE)
_CYRILLIC_RE = re.compile(r'[а-яёА-ЯЁ]')

#: Чем заменяются числовые последовательности в варианте `v2_masked_numbers`.
#: ⚠️ Только в ТЕКСТЕ ОТПЕЧАТКА; в базе не меняется ничего. На дедуп это не
#: влияет — тот сверяет числовые токены по самому тексту, а не по отпечатку.
NUMBER_MASK = '#'


@dataclass(frozen=True)
class FormulaSpec:
    """Вариант формулы — данные, а не код.

    :param name: имя варианта, оно же ключ в `SPECS`.
    :param version: штампуется в `Problem.embedding_version`.
    :param blocks: порядок блоков. Имя, встреченное дважды, отрисуется
        дважды — так выражается повтор (`v2_focus_repeat`), отдельного поля
        для этого не нужно.
    :param budgets: потолок символов на блок; `None` — без ограничения,
        отсутствие ключа — тоже без ограничения. Зарезервированный ключ
        `'queries_count'` — не символы, а максимальное число поисковых фраз.
    :param options: флаги отрисовки, которых не выразить бюджетом
        (см. `OPTIONS` ниже). Поле сверх наброска задания: без него диалект
        v1 и обезличивание чисел пришлось бы кодировать именами блоков, а
        блоков ровно девятнадцать и размножать их нельзя.
    """

    name: str
    version: int
    blocks: tuple[str, ...]
    budgets: Mapping[str, int | None] = field(default_factory=dict)
    options: frozenset[str] = frozenset()

    def budget(self, block):
        return self.budgets.get(block)

    def has(self, option):
        return option in self.options


#: Флаги `FormulaSpec.options`, все — про отрисовку, не про состав.
OPTIONS = {
    'v1': 'диалект формулы v1: заголовок и условие без меток, условие '
          'добавляется даже пустым, бюджет подпунктов суммарный. '
          'Законсервирован ради байт-в-байт совпадения с problem_to_text.',
    'legacy_tags': 'теги по старому списку CANONICAL_TAG_NAMES (222 имени) '
                   'вместо Tag.kind = canonical (344 тега в банке).',
    'no_offlist': 'блок «Понятия» — только словарные EconConcept, без '
                  'concepts_offlist.',
    'model_features_only': 'особенности только те, что считает модель '
                           '(Feature.counted_by = model).',
    'mask_numbers': 'числовые последовательности в условии, подпунктах и '
                    'решении заменяются одним знаком.',
}


# ---------------------------------------------------------------------------
# Чистка понятий (раздел 3.1.1 задания). Одинакова для обоих источников.
# ---------------------------------------------------------------------------

#: Причины выброса — ключи отчёта `clean_concepts(..., stats=...)`.
CONCEPT_DROP_REASONS = ('короче 3 символов или без букв',
                        'обозначение, а не слово',
                        'общее слово из стоп-листа')


def _is_bare_notation(term):
    """Термин — голое обозначение (`P`, `S`, `AVC`, `π`), а не слово.

    ⚠️ Тонкость, из-за которой нельзя звать `normalizable_notation()`
    напрямую: та возвращает термин только для ОДНОЗНАЧНОГО символа, а
    выбросить надо как раз неоднозначные (`P` — это цена, уровень цен и
    put-опцион). Признак «символ вообще есть в словаре обозначений» ловит и
    те, и другие.

    Кириллица защищает настоящие термины-аббревиатуры («ВВП», «ППС»): они
    слова русского языка, а не математические обозначения.
    """
    if _CYRILLIC_RE.search(term):
        return False
    return econ_terms.lookup_notation(term) is not None


def clean_concepts(terms, stats=None):
    """Отфильтрованные и отсортированные понятия без дублей.

    Четыре правила задания: короче 3 символов или только знаки → вон;
    голое обозначение → вон; общее слово из стоп-листа → вон; **термин с
    цифрой внутри остаётся** («денежный агрегат М1», «правило 70»,
    «выбросы CO2 на душу населения» — их всего 15 и все законные).

    Отсечки по частоте нет намеренно: замерено, что при пороге «частота ≥ 2»
    теряется 6 649 терминов и 13,2 % упоминаний, а хвост чистый — именно
    редкий термин и делает задачу находимой.
    """
    оставленные = []
    for сырой in terms:
        термин = (сырой or '').strip()
        if not термин:
            continue
        if len(термин) < CONCEPT_MIN_LEN or _ONLY_PUNCT_RE.match(термин):
            причина = CONCEPT_DROP_REASONS[0]
        elif _is_bare_notation(термин):
            причина = CONCEPT_DROP_REASONS[1]
        elif термин.lower() in CONCEPT_STOPWORDS:
            причина = CONCEPT_DROP_REASONS[2]
        else:
            оставленные.append(термин)
            continue
        if stats is not None:
            stats.setdefault(причина, []).append(термин)
    return sorted(set(оставленные))


# ---------------------------------------------------------------------------
# Блоки. Каждый возвращает строку или '' («пустые блоки не добавляются»),
# кроме условия в диалекте v1 — там пустое условие добавляется намеренно.
# ---------------------------------------------------------------------------

def _cut(text, budget):
    text = text or ''
    return text if budget is None else text[:budget]


def _mask(text, spec):
    return _DIGITS_RE.sub(NUMBER_MASK, text) if spec.has('mask_numbers') else text


def _b_topics(p, spec):
    """⚠️ В v2 темы берутся КАНОНИЧЕСКИЕ (`Topic.is_canonical`), в v1 — все
    подряд. Разница не косметическая: тем в банке 865, канонических из них
    29, а остальные — импортные названия листков вроде «Best of тачки» и
    «<<Ух, как напроинтерпритируемся!>>». В отпечатке такое имя не помогает
    найти задачу, а мешает. Покрытие каноническими темами — 40 681 задача
    (98,5 %) против 40 960 (99,2 %) всеми темами."""
    темы = p.topics.all() if spec.has('v1') else [
        t for t in p.topics.all() if t.is_canonical]
    имена = [t.name for t in темы if t.name != TOPIC_TECHNICAL]
    return 'Темы: ' + ', '.join(имена) + '.' if имена else ''


def _b_tags(p, spec):
    """⚠️ В v2 теги берутся по `Tag.kind = 'canonical'`, а НЕ по списку
    `CANONICAL_TAG_NAMES`: список — старый, из 222 имён времён Батча 1, а
    таксономия v2 положила в банк 344 канонических тега с другими
    названиями. Замерено: блок «Теги» формулы v1 срабатывает у 108 задач из
    41 307, при том что хотя бы один канонический тег есть у 40 425. То есть
    в v1 блок фактически мёртв, и мёртв молча."""
    if spec.has('legacy_tags'):
        # ⚠️ Импорт внутри функции, а не в шапке модуля, и это не небрежность:
        # `embedding_config` в самом конце импортирует `SPECS` отсюда, чтобы
        # выставить ACTIVE_SPEC. Импорт `CANONICAL_TAG_NAMES` в шапке замкнул
        # бы кольцо и ронял бы любой код, который первым тронул
        # `embedding_formula`.
        from problems.embedding_config import CANONICAL_TAG_NAMES
        имена = sorted(t.name for t in p.tags.all()
                       if t.name in CANONICAL_TAG_NAMES)
    else:
        имена = sorted(t.name for t in p.tags.all() if t.kind == 'canonical')
    return 'Теги: ' + ', '.join(имена) + '.' if имена else ''


def _b_concepts(p, spec):
    """Словарные `EconConcept` и `concepts_offlist` — вместе, одним блоком,
    на равных правах (решение владельца 07.09.2026). Замер, стоящий за этим
    решением: в offlist 10 347 уникальных терминов на 50 504 упоминания, и
    хвост с частотой 1 при проверке глазами оказался матчастью, а не
    мусором, — тогда как в СЛОВАРНЫХ понятиях сидят «цена» (18,5 % банка) и
    «спрос» (16,9 %), не различающие ничего."""
    термины = [c.canonical for c in p.econ_concepts.all()]
    if not spec.has('no_offlist'):
        термины += list(p.concepts_offlist or [])
    очищенные = clean_concepts(термины)
    return 'Понятия: ' + ', '.join(очищенные) + '.' if очищенные else ''


def _b_queries(p, spec):
    фразы = [str(q).strip() for q in (p.search_queries or []) if str(q).strip()]
    предел = spec.budgets.get('queries_count')
    if предел:
        фразы = фразы[:предел]
    if not фразы:
        return ''
    return _cut('Запросы: ' + '; '.join(фразы) + '.', spec.budget('queries'))


def _b_find(p, spec):
    текст = _cut((p.find or '').strip(), spec.budget('find'))
    return 'Найти: ' + текст if текст else ''


def _b_given(p, spec):
    текст = _cut((p.given or '').strip(), spec.budget('given'))
    return 'Дано: ' + текст if текст else ''


def _b_solution(p, spec):
    """⚠️ Единственный блок, который отменяет правило v1 «решение и ответ в
    отпечаток не входят». Отмена сознательная — блок 7 списка владельца
    07.09; цену блока меряет вариант `v2_no_solution`.

    Ответ (`answer`) не входит ни в один вариант: медианная длина ответа в
    банке — 2 символа, то есть это число. «Ответ: 6» не помогает найти
    задачу ничем."""
    текст = _cut(_mask((p.solution or '').strip(), spec), spec.budget('solution'))
    return 'Решение: ' + текст if текст else ''


def _b_statement(p, spec):
    """⚠️ В диалекте v1 условие добавляется ВСЕГДА, даже пустое — так делает
    `problem_to_text`, и от этого зависит байт-в-байт совпадение (пустой
    элемент даёт двойной пробел в `' '.join`)."""
    сырое = p.statement or ''
    if spec.has('v1'):
        return _cut(сырое, spec.budget('statement'))
    текст = _cut(_mask(сырое, spec), spec.budget('statement')).strip()
    return 'Условие: ' + текст if текст else ''


def _b_parts(p, spec):
    """⚠️ Бюджет в v2 — НА КАЖДЫЙ подпункт (решение 19.08, пункт 8); в v1 он
    суммарный, 500 символов на все подпункты вместе."""
    куски = [sp.statement for sp in p.parts.all() if sp.statement]
    if not куски:
        return ''
    бюджет = spec.budget('parts')
    if spec.has('v1'):
        return _cut(' '.join(куски), бюджет)
    текст = ' '.join(_mask(_cut(k, бюджет), spec) for k in куски).strip()
    return 'Подпункты: ' + текст if текст else ''


def _b_hints(p, spec):
    тексты = [h.text.strip() for h in p.hints.all() if (h.text or '').strip()]
    if not тексты:
        return ''
    текст = _cut(' '.join(тексты), spec.budget('hints'))
    return 'Подсказки: ' + текст if текст else ''


def _b_features(p, spec):
    """Особенности связью `ProblemFeature`, по `Feature.label`, а не по
    `key`: в ключах подчёркивания, модель их словами не читает."""
    особенности = list(p.features_rel.all())
    if spec.has('model_features_only'):
        особенности = [f for f in особенности if f.counted_by == 'model']
    имена = sorted(f.label for f in особенности if f.label)
    return 'Особенности: ' + ', '.join(имена) + '.' if имена else ''


def _b_kind(p, spec):
    тип = (p.problem_type or '').strip().replace('_', ' ')
    характер = (p.task_nature or '').strip().replace('_', ' ')
    if not характер:
        характер = CHARACTER_WORDS.get((p.character or '').strip(), '')
    куски = [k for k in (тип, характер) if k]
    return 'Тип: ' + ', '.join(куски) + '.' if куски else ''


def _b_olympiad(p, spec):
    """⚠️ Только НАЗВАНИЕ олимпиады, этап и год — никаких ссылок на
    агрегатора (решение владельца 07.09.2026): при источнике-агрегаторе
    признак врёт."""
    видел, строки = set(), []
    for ref in p.olympiad_refs.all():
        имя = (ref.olympiad_name or '').strip()
        if not имя:
            continue
        ключ = (имя, (ref.stage or '').strip(), ref.year)
        if ключ in видел:
            continue
        видел.add(ключ)
        строки.append(', '.join(
            [имя] + [x for x in ((ref.stage or '').strip(),
                                 str(ref.year) if ref.year else '') if x]))
    return 'Олимпиада: ' + '; '.join(sorted(строки)) + '.' if строки else ''


def _b_difficulty_note(p, spec):
    текст = _cut((p.difficulty_note or '').strip(), spec.budget('difficulty_note'))
    return 'Обоснование сложности: ' + текст if текст else ''


def _b_difficulty(p, spec):
    слово = DIFFICULTY_WORDS.get(p.difficulty)
    return 'Сложность: %s.' % слово if слово else ''


def _b_title(p, spec):
    """В v2 — `title_candidate` при непустом, иначе `title`; в v1 остаётся
    старый `title` без метки.

    ⚠️ `API_RUN_MASTER` §5.8 заголовок из отпечатка ЗАПРЕЩАЛ — но запрет был
    про старый `title` (7 098 заголовков-обрубков). `title_candidate`
    заполнен у 41 307 задач из 41 307 и по инвариантам §11 не длиннее 40
    символов и без цифр; к нему то возражение не относится."""
    if spec.has('v1'):
        return p.title + '.' if p.title else ''
    текст = _cut(((p.title_candidate or '').strip() or (p.title or '').strip()),
                 spec.budget('title'))
    return 'Заголовок: ' + текст + '.' if текст else ''


def _b_blurb(p, spec):
    """Не входит в `v2`: списка владельца 07.09 его не содержит, а список —
    полный и явный. Цену возврата меряет вариант `v2_plus_blurb`."""
    return _cut((p.ai_blurb or '').strip(), spec.budget('blurb'))


def _b_plot(p, spec):
    """Убран решением владельца 07.09.2026, хотя `API_RUN_MASTER` §9 его
    включал четвёртым блоком. Остаётся для `v2_core` — исторической точки
    «как было решено до 07.09»."""
    текст = _cut((p.plot or '').strip(), spec.budget('plot'))
    return 'Сюжет: ' + текст if текст else ''


def _b_skills(p, spec):
    """Три задачи из 41 307 (0,01 %). Живёт только ради спецификации v1."""
    имена = [s.name for s in p.skills.all()]
    return 'Навыки: ' + ', '.join(имена) + '.' if имена else ''


#: Девятнадцать блоков. Боевая спецификация `v2` включает шестнадцать;
#: `blurb`, `plot` и `skills` реализованы, но в неё не входят.
BLOCKS = {
    'topics': _b_topics,
    'tags': _b_tags,
    'concepts': _b_concepts,
    'queries': _b_queries,
    'find': _b_find,
    'given': _b_given,
    'solution': _b_solution,
    'statement': _b_statement,
    'parts': _b_parts,
    'hints': _b_hints,
    'features': _b_features,
    'kind': _b_kind,
    'olympiad': _b_olympiad,
    'difficulty_note': _b_difficulty_note,
    'difficulty': _b_difficulty,
    'title': _b_title,
    'blurb': _b_blurb,
    'plot': _b_plot,
    'skills': _b_skills,
}


def build_text(problem, spec):
    """Текст отпечатка задачи по спецификации. Единственная реализация."""
    куски = []
    for имя in spec.blocks:
        try:
            блок = BLOCKS[имя]
        except KeyError:
            raise KeyError('неизвестный блок формулы: %r (известны: %s)'
                           % (имя, ', '.join(sorted(BLOCKS))))
        кусок = блок(problem, spec)
        # ⚠️ Проверка `is not None`, а не на истинность: в диалекте v1 пустое
        # условие добавляется намеренно и обязано попасть в склейку.
        if кусок or (имя == 'statement' and spec.has('v1')):
            куски.append(кусок)
    return ' '.join(куски)


# ---------------------------------------------------------------------------
# Варианты замера. Порядок и состав `v2` — решение владельца 07.09.2026,
# не предложение: шестнадцать блоков ровно в этом порядке.
# ---------------------------------------------------------------------------

#: Зафиксированный порядок блоков v2. Жирные пять («темы, теги, понятия,
#: найти, дано») — блоки упора: запрос владельца был «одинаковый вес, но с
#: упором на них». Настоящей ручки веса нет (см. шапку модуля), упор
#: выражается долей токенов и позицией.
V2_BLOCKS = ('topics', 'tags', 'concepts', 'queries', 'find', 'given',
             'solution', 'statement', 'parts', 'hints', 'features', 'kind',
             'olympiad', 'difficulty_note', 'difficulty', 'title')

#: Блоки упора — их же повторяет `v2_focus_repeat`.
FOCUS_BLOCKS = ('topics', 'tags', 'concepts', 'find', 'given')

#: Метаданные (блоки 11–16). `v2_meta_first` переносит их в голову.
META_BLOCKS = ('features', 'kind', 'olympiad', 'difficulty_note',
               'difficulty', 'title')

V2_BUDGETS = {
    'find': 400,            # p90 = 279
    'given': 500,           # p90 = 463
    'solution': 800,
    'statement': 1500,
    'parts': 1500,          # НА КАЖДЫЙ подпункт, = бюджету условия
    'hints': 800,           # p90 = 804, суммарно
    'difficulty_note': 250,  # p90 = 223
    'title': 40,
}

#: Бюджеты `v2_focus`: урезаны длинные блоки, «Найти» и «Дано» не режутся.
FOCUS_BUDGETS = dict(V2_BUDGETS, statement=800, parts=500, solution=400,
                     hints=400, queries=250, queries_count=4,
                     difficulty_note=120)


def _spec(name, version, blocks, budgets=None, options=()):
    return FormulaSpec(name=name, version=version, blocks=tuple(blocks),
                       budgets=dict(budgets or {}),
                       options=frozenset(options))


def _v2(name, version, blocks=V2_BLOCKS, budgets=None, options=()):
    return _spec(name, version, blocks, budgets or V2_BUDGETS, options)


def _without(*dropped):
    return tuple(b for b in V2_BLOCKS if b not in dropped)


SPECS = {
    # Контроль. Ровно нынешняя problem_to_text — байт в байт, держится тестом.
    'v1': _spec('v1', 1,
                ('title', 'statement', 'parts', 'topics', 'skills', 'blurb',
                 'tags'),
                {'statement': 500, 'parts': 500, 'blurb': 400},
                ('v1', 'legacy_tags')),

    # Основной кандидат: зафиксированный порядок, условие 1500.
    'v2': _v2('v2', 2),

    # Бюджет условия.
    'v2_500': _v2('v2_500', 91, budgets=dict(V2_BUDGETS, statement=500, parts=500)),
    'v2_3000': _v2('v2_3000', 92, budgets=dict(V2_BUDGETS, statement=3000, parts=3000)),
    'v2_nolimit': _v2('v2_nolimit', 93,
                      budgets=dict(V2_BUDGETS, statement=None, parts=None)),

    # Упор: доля пяти блоков 33,2 % → 37,5 % → 54,0 %.
    'v2_focus': _v2('v2_focus', 94, budgets=FOCUS_BUDGETS),
    'v2_focus_repeat': _v2('v2_focus_repeat', 95,
                           blocks=V2_BLOCKS + FOCUS_BLOCKS,
                           budgets=FOCUS_BUDGETS),

    # Цена ПОРЯДКА в чистом виде: состав и бюджеты те же, метаданные в голове.
    'v2_meta_first': _v2('v2_meta_first', 96,
                         blocks=META_BLOCKS + tuple(
                             b for b in V2_BLOCKS if b not in META_BLOCKS)),

    # Абляции: v2 минус ровно один блок.
    'v2_no_solution': _v2('v2_no_solution', 97, blocks=_without('solution')),
    'v2_no_hints': _v2('v2_no_hints', 98, blocks=_without('hints')),
    'v2_no_queries': _v2('v2_no_queries', 99, blocks=_without('queries')),
    'v2_no_offlist': _v2('v2_no_offlist', 100, options=('no_offlist',)),
    'v2_no_code_features': _v2('v2_no_code_features', 101,
                               options=('model_features_only',)),
    'v2_no_tail_meta': _v2('v2_no_tail_meta', 102, blocks=_without(*META_BLOCKS)),

    # Вернуть ai_blurb, выпавший из списка владельца. Место — четвёртое,
    # как в §9 API_RUN_MASTER: сразу после понятий.
    'v2_plus_blurb': _v2('v2_plus_blurb', 103,
                         blocks=V2_BLOCKS[:3] + ('blurb',) + V2_BLOCKS[3:],
                         budgets=dict(V2_BUDGETS, blurb=400)),

    # Обезличенные числа — только в тексте отпечатка, в базе ничего не меняется.
    'v2_masked_numbers': _v2('v2_masked_numbers', 104, options=('mask_numbers',)),

    # Историческая точка: девять блоков §9, «как было решено до 07.09».
    'v2_core': _spec('v2_core', 105,
                     ('topics', 'tags', 'concepts', 'blurb', 'find', 'given',
                      'plot', 'statement', 'parts'),
                     dict(V2_BUDGETS, blurb=400)),
}

#: Версии обязаны быть различны: версия штампуется в `embedding_version`, и
#: две спецификации с одной версией сделали бы провенанс вектора ложью.
assert len({s.version for s in SPECS.values()}) == len(SPECS), \
    'версии спецификаций не уникальны'
assert all(b in BLOCKS for s in SPECS.values() for b in s.blocks), \
    'спецификация ссылается на неизвестный блок'
