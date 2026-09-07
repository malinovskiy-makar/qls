# -*- coding: utf-8 -*-
"""Кого из боевых заголовков заменяет `title_candidate` — правило в одном месте.

Решение владельца 07.09.2026 дословно: «замени на хорошие заголовки везде,
никаких обрубков первых строк просто». Оно отменяет пункт 5 решения 06.09
(«боевой `title` перезаписываем только для категорий A и B»).

Но «везде» — не «все 41 307». Карточка решения ставит границу сама: среди
`title_source='kept'` есть авторские заголовки, которые ЛУЧШЕ кандидата
(«Равновесие Нэша в дилемме заключённого» → «Дилемма заключённого» теряет
смысл), и есть бессмысленные клички, где кандидат явно лучше («Подсолнух - 2»,
«It's a life», «Измерение С-37»). Поэтому корзин четыре, и каждая — правило,
а не вкус:

* **A** — обрубок первой строки (`title_source='model-firstline'`). Заменяем
  безусловно: ровно ради них решение и принято.
* **B** — эхо условия: боевой заголовок является префиксом `statement` или
  совпадает с его первым предложением. Такие есть и среди `kept`. Безусловно.
* **C** — спорные `kept`. Заменяем, если заголовок длиннее 40 символов ИЛИ не
  содержит ни одного термина из словаря `data/econ_terms.json`; оставляем,
  если он короткий И термин в нём есть.
* **D** — не трогаем: кандидат негоден (пуст, длиннее 40, с цифрой, `$` или
  обратным слэшем, либо баговое литеральное `'title_candidate'`), или боевой
  заголовок УЖЕ равен кандидату (`model-empty` и `model-broken` — все 4 747 —
  переписаны ещё мержем 06.09, там заменять нечего).

⚠️ Термин ищется по ВСЕМ вариантам морфологического разбора, а не по первому.
Разбор по `parse(word)[0]` даёт 2,61 % молчаливых промахов на контрольном
наборе словаря (`docs/EMBEDDINGS.md`), и промах здесь опаснее обычного: он
означает «термина нет» → заголовок пойдёт под замену, хотя он авторский.
"""
import re
from functools import lru_cache

from problems import econ_terms

#: Потолок длины боевого заголовка. Он же порог корзины C: 12 954
#: опубликованных задачи показывают ученику заголовок длиннее (замер 07.09).
TITLE_LIMIT = 40

#: Имена полей модели, которые баг 07.09 записал вместо значений (882 задачи).
#: Проверяем весь набор, а не одно `'title_candidate'`: если та же ошибка
#: повторится с соседним полем, кандидат «имя поля» не должен пройти молча.
FIELD_NAME_MARKERS = frozenset({
    'title', 'title_candidate', 'title_source', 'enrichment_source',
    'text_quality', 'statement', 'answer', 'solution', 'given', 'find',
    'plot', 'ai_blurb', 'search_queries', 'content_status',
})

#: Кандидат с этими знаками — брак прогона, а не заголовок (инвариант §11).
BAD_CHARS_RE = re.compile(r'[\d$\\]')

#: Слово из этого списка термином НЕ считается, даже если словарь его знает:
#: «Величина Х» — такая же бессмысленная кличка, как «Подсолнух - 2».
GENERIC_WORDS = frozenset({'величина', 'значение', 'задача', 'вопрос',
                           'пример', 'случай', 'ситуация', 'вариант',
                           'условие', 'решение', 'ответ', 'выбор',
                           'обязательство'})

_WORD_RE = re.compile(r'[А-Яа-яЁёA-Za-z][А-Яа-яЁёA-Za-z-]*')
_SENTENCE_END_RE = re.compile(r'(?<=[.!?])\s')
#: Хвост обрубка: многоточие, тире, запятая — их снимаем перед сверкой с
#: условием, иначе «Фирма производит два товара и…» не совпадёт с префиксом.
_TAIL_RE = re.compile(r'[\s.…,;:—–-]+$')


def normalized(text):
    """Свёрнутые пробелы и нижний регистр — общая нормализация сверок."""
    return re.sub(r'\s+', ' ', (text or '')).strip().lower()


def candidate_of(problem):
    return (problem.title_candidate or '').strip()


def candidate_is_usable(candidate):
    """Кандидат годен к переносу в боевой заголовок.

    ⚠️ Пробелы снимаются ЗДЕСЬ, а не только в `candidate_of`: иначе кандидат
    из одних пробелов прошёл бы проверку и стёр боевой заголовок в пустоту.
    """
    candidate = (candidate or '').strip()
    if not candidate:
        return False
    if candidate.lower() in FIELD_NAME_MARKERS:
        return False
    if len(candidate) > TITLE_LIMIT:
        return False
    return not BAD_CHARS_RE.search(candidate)


def is_echo_of_statement(title, statement):
    """Заголовок — начало условия, а не название задачи."""
    заголовок = _TAIL_RE.sub('', normalized(title))
    условие = normalized(statement)
    if len(заголовок) < 12 or not условие:
        # Короткая строка совпала бы с началом условия случайно
        # («Монополия» и «Монополия выпускает…»), и это ещё не эхо.
        return False
    if условие.startswith(заголовок):
        return True
    первое = _TAIL_RE.sub('', _SENTENCE_END_RE.split(условие, 1)[0])
    return заголовок == первое


# --- Словарь терминов ------------------------------------------------------

@lru_cache(maxsize=1)
def _morph():
    import pymorphy3  # локальный импорт: pymorphy3 живёт в requirements/dev.in
    return pymorphy3.MorphAnalyzer()


def _lemmas(word, morph):
    """ВСЕ нормальные формы слова, а не самая вероятная (см. шапку модуля)."""
    return {p.normal_form for p in morph.parse(word)} | {word.lower()}


@lru_cache(maxsize=1)
def _term_index():
    """Первая лемма термина -> список терминов как списков лемм по словам.

    Индекс по первому слову нужен ради скорости: заголовков десятки тысяч,
    а написаний терминов — десятки тысяч, и перебор «каждый против каждого»
    занял бы часы.
    """
    morph = _morph()
    индекс = {}
    for entry in econ_terms.terms():
        формы = [entry.get('canonical', '')]
        формы += list(entry.get('synonyms') or [])
        формы += list(entry.get('english') or [])
        формы += list((entry.get('word_forms') or {}).values())
        for форма in формы:
            слова = _WORD_RE.findall(форма or '')
            if not слова or len(слова) > 4:
                continue
            леммы = [_lemmas(w, morph) for w in слова]
            if len(слова) == 1 and леммы[0] & GENERIC_WORDS:
                continue
            for первая in леммы[0]:
                индекс.setdefault(первая, []).append(леммы)
    return индекс


def has_econ_term(title):
    """В заголовке есть хотя бы один термин словаря олимпиадной экономики."""
    слова = _WORD_RE.findall(title or '')
    if not слова:
        return False
    morph = _morph()
    индекс = _term_index()
    леммы = [_lemmas(w, morph) for w in слова]
    for i, набор in enumerate(леммы):
        for первая in набор:
            for термин in индекс.get(первая, ()):
                if i + len(термин) > len(слова):
                    continue
                if all(термин[k] & леммы[i + k] for k in range(len(термин))):
                    return True
    return False


# --- Корзины ---------------------------------------------------------------

#: Корзины, задачи которых получают новый заголовок.
REPLACED = ('A', 'B', 'C')

BUCKETS = REPLACED + ('C-оставляем', 'D-совпадает', 'D-кандидат негоден')


def bucket(problem):
    """Корзина задачи. Чистая функция: базу не трогает. Порядок проверок
    важен — A раньше B, иначе обрубок-эхо попал бы в B и числа разъехались."""
    кандидат = candidate_of(problem)
    if not candidate_is_usable(кандидат):
        return 'D-кандидат негоден'
    if (problem.title or '').strip() == кандидат:
        return 'D-совпадает'
    if problem.title_source == 'model-firstline':
        return 'A'
    if is_echo_of_statement(problem.title, problem.statement):
        return 'B'
    if problem.title_source == 'kept':
        длинный = len(normalized(problem.title)) > TITLE_LIMIT
        return 'C' if (длинный or not has_econ_term(problem.title)) else 'C-оставляем'
    return 'D-кандидат негоден'
