# -*- coding: utf-8 -*-
"""Правила сборки эталона v5 для экономики ВП/МОШ (сессия v5, 14.10.2026).

Работают только в профиле `assemble.ECON` и закрывают дефекты нарезки v4:

1. **Блоки отборочных МОШ** (2023/24–2024/25, все классы). Работа поделена на
   «Блок 1…4», внутри блока нумерация с 1, у каждого вопроса три варианта
   подряд (1/1, 1/2, 1/3, 2/1 …). Сборка v3 сливала «Блок 2 № 1» с «Блок 3 № 1»
   в одно задание. Номер задания — СКВОЗНОЙ, как в самой работе: инструкция
   «В задании 7 отнесите…» стоит у «Блок 3, № 2» (mosh-2025-qualifying-7).
   Граница блока — номер вопроса уменьшился (4/3 → 1/1); правило включается,
   только если в файле есть плашка «Блок N» (у ВП файл решений повторяет задачи
   1–5 — это тоже «сброс», но плашек там нет).
2. **Служебный блок — не задание.** Инструкция раздела («Блок 2. Выберите
   несколько правильных ответов…», «Решите задачи, приведите только ответ»,
   «Задания на сопоставление… Посмотрите внимательно…», «Правила проведения
   этапа») без вопроса и вариантов ответа заданием не становится: правила и
   приветствие — во вступление комплекта, инструкция формата ответа — в начало
   условия заданий своего раздела (`lead`), чтобы на сайте выбрать верный вид
   теста. Инструкция с номерами («задание 36 - 45», «вопросы (3) - (5)», «В
   задании 7») — только этим заданиям.
3. **Пункт задачи, а не задание.** Модель иногда размечает пункт «N)» задачи
   отдельным заданием № N (vp-2026-final-11: пункты 1)–5) задачи 1 стали
   заданиями 1–5, mosh-2022-final-11: пункт 5) задачи 4 «Новогодний салют» —
   заданием 5). Блок без названия, чей номер продолжает пункты текущей задачи
   с названием, — пункт: дописывается к задаче с меткой «N) (k баллов)».

Правила v6 (сессия v6, 15.10.2026) — тоже только в профиле ECON:

4. **Эссе — задание.** Файл эссе МОШ 2009/10 (10 и 11 кл.) без номеров:
   «ЭССЕ. ПРОБЛЕМЫ МОНОГОРОДОВ» — безномерный блок в начале файла, и v5 клал
   его во вступление комплекта, а продолжение на следующей странице терял.
   Безномерный блок, начинающий файл с заголовка «Эссе…», заводит задание
   № «эссе» (`ESSAY_NUMBER`); дальше по файлу всё — его.
5. **Повтор вопроса теста в файле ответов.** Файл ответов МОШ повторяет вопрос
   теста с отмеченным ответом под голым номером N, а в комплекте он —
   «тест-N» (тест и задачи нумеруются с 1). v3–v5 заводили второе задание N
   (152 повтора в 21 комплекте). Блок N без своего задания, чей текст
   (без пометок «(отмечено)») совпадает с «тест-N» того же варианта, — ответ
   к «тест-N»; совпал по тексту с другим вопросом того же варианта
   (номер перепутан моделью) — к нему.
6. **Повтор пункта задачи в файле решений** (vp-2019-final-8): файл решений
   повторяет задачу «Задание 3. «…»» и затем пункты «2. (12 баллов) …» —
   модель размечает пункт заданием № 2 без названия. Пункт, текст которого —
   повтор условия текущей задачи, а не задачи № 2, включает правило v5
   «всё между повторами задачи — её», а ответы внутри блока-повтора задачи
   («1. (4 балла) … **Ответ.** …») становятся решением.
"""
from __future__ import annotations

import re

# ── Инструкции раздела ───────────────────────────────────────────────────

_MARKER = re.compile(r'^\W*блок\s*(\d+)\b', re.IGNORECASE)
#: Строка — указание формата ответа (её надо видеть в каждом задании раздела).
_FORMAT_LINE = re.compile(
    r'(выбер\w*|выбрать|отмет\w*)\W+(?:\w+\W+){0,4}?(все|всех|несколько|единственн\w*|один|одного|'
    r'правильн\w*|верн\w*)|ответ на вопрос данного типа|приведите только ответ|'
    r'требу\w+ только записи ответа|требу\w+ записи подробного решения|'
    r'решение не проверяется|соотнесите данные из первого столбца|'
    r'выпадающего списка|отнесите события', re.IGNORECASE)
#: Правила этапа и приветствие — во вступление комплекта.
_RULES = re.compile(r'^\W*(правила проведения|уважаемый участник)', re.IGNORECASE)
#: Признаки служебного блока целиком.
_SERVICE = re.compile(
    r'^\W*(блок\s*\d+|раздел\s+[ivx]+|часть\s+[ivx]+|тест\s*[ivx\d]*\b|задания на сопоставление|'
    r'внимание!|правила проведения|уважаемый участник)|ответ на вопрос данного типа|'
    r'решите задачи, приведите только ответ|посмотрите внимательно на данные|'
    r'в задании \d+ (от|со)несите|выберите несколько правильных ответов|'
    r'выберите\s+все\s+(верные|правильные)\s+ответ|'
    r'из нескольких вариантов нужно выбрать|внимание!|(необходимо|нужно)\s+выбрать', re.IGNORECASE)
_OPTION = re.compile(r'^\s*(?:[-*•○☐☑]\s+|\(?[1-9а-еa-eА-ЕA-E]\)\s+|[1-9]\.\s+\S)', re.MULTILINE)
_QUESTION = re.compile(r'\?|найдите|определите|рассчитайте|вычислите|сколько|чему равн|'
                       r'какой|какая|какие|каков|во сколько', re.IGNORECASE)
_RANGE = re.compile(r'(?:задани\w*|задач\w*|вопрос\w*)\s*(?:№|с)?\s*(?:[A-ZА-Я]\s*)?\(?(\d{1,2})\)?'
                    r'\s*(?:[-–—]|до|по)\s*(?:[A-ZА-Я]\s*)?\(?(\d{1,2})\)?', re.IGNORECASE)
_SINGLE = re.compile(r'\bв\s+задани[ие]\s+(\d{1,2})\b', re.IGNORECASE)
SERVICE_MAX = 1500


def _text(block):
    return (block.get('text') or '').strip()


def is_service_text(text, title=''):
    """Служебный блок: признак инструкции, без вопроса, вариантов и таблицы."""
    body = f'{title}\n{text}'.strip()
    if not body or len(body) > SERVICE_MAX or not _SERVICE.search(body):
        return False
    if '|' in text and re.search(r'^\s*\|.*\|\s*$', text, re.MULTILINE):
        return False
    if len(_OPTION.findall(text)) >= 2:
        return False
    plain = _SERVICE.sub(' ', body)
    return not _QUESTION.search(plain)


def is_rules_text(text, title=''):
    return bool(_RULES.search(f'{title}\n{text}'.strip()))


def marker_of(block):
    """Номер плашки «Блок N» в названии или первой строке блока (или None)."""
    for source in (block.get('title') or '', _text(block).split('\n', 1)[0]):
        m = _MARKER.match(source.strip().strip('*#').strip())
        if m:
            return int(m.group(1))
    return None


def format_lines(text, title=''):
    """Указания формата ответа из инструкции (строки, абзацы) — то, что идёт в
    начало условия заданий раздела; «Блок 2», время, баллы — нет."""
    out = []
    for para in re.split(r'\n\s*\n', f'{title}\n\n{text}'):
        para = para.strip()
        if not para:
            continue
        clean = _MARKER.sub('', para.strip('*# ')).strip(' .*#')
        if clean and _FORMAT_LINE.search(clean):
            out.append(para if not _MARKER.match(para.strip('*# ')) else clean)
    return out


_COUNT = re.compile(r'(\d{1,2})\s+вопрос', re.IGNORECASE)


def section_count(text):
    """«Тест II (10 вопросов, 20 баллов)», «раздел состоит из 10 вопросов» → 10."""
    m = _COUNT.search(text or '')
    return int(m.group(1)) if m else None


def targets(text):
    """Номера заданий, к которым относится инструкция: «задание 36 - 45»,
    «вопросы (3) - (5)», «В задании 7»; пусто — раздел целиком."""
    nums = []
    for a, b in _RANGE.findall(text or ''):
        a, b = int(a), int(b)
        if a < b <= a + 60:
            nums.extend(range(a, b + 1))
    nums.extend(int(n) for n in _SINGLE.findall(text or ''))
    return sorted(set(nums))


def split_leading_instruction(block):
    """Реальное задание, начинающееся с инструкции раздела (плашка в названии,
    первый абзац — «Ответ на вопрос данного типа…»): (блок без инструкции,
    текст инструкции | '')."""
    title = (block.get('title') or '').strip()
    paras = re.split(r'\n\s*\n', _text(block))
    lead = []
    if title and (marker_of({'title': title}) or _FORMAT_LINE.search(title)):
        lead.append(title)
        title = ''
    while len(paras) > 1 and (_FORMAT_LINE.search(paras[0]) or _MARKER.match(paras[0].strip('*# '))) \
            and not _QUESTION.search(_SERVICE.sub(' ', paras[0])):
        lead.append(paras.pop(0))
    if not lead:
        return block, ''
    return dict(block, title=title, text='\n\n'.join(paras).strip()), '\n\n'.join(lead)


# ── Блоки отборочных МОШ ─────────────────────────────────────────────────

TASK_KINDS = ('task', 'task_continuation', 'solution', 'criteria', 'figure')


def _int_number(block):
    raw = str(block.get('number') or '').strip()
    return int(raw) if re.fullmatch(r'\d{1,2}', raw) else None


def qualifying_blocks(items, report=None):
    """Файл отборочного МОШ с блоками → сквозная нумерация и служебные блоки.

    `items` — [(файл, страница, запись, блок)] из `collect`. В файле с плашкой
    «Блок N» (в любом блоке) номера вопросов идут блоками по три варианта;
    блок кончается, когда номер вопроса уменьшился. Служебные блоки (без
    варианта и без вопроса) помечаются `_service`, номер у них снимается;
    инструкция в начале реального вопроса отрезается в `_lead`. Номер вопроса
    → смещение блока + номер. Плашка «Блок K» в инструкции → инструкция
    блока K, иначе — блока ближайшего вопроса перед ней."""
    by_file = {}
    for i, (entry, _page, _record, block) in enumerate(items):
        if block is not None:
            by_file.setdefault(entry['file'], []).append(i)
    items = list(items)
    for idxs in by_file.values():
        if not any(marker_of(items[i][3]) for i in idxs):
            continue
        # 1. Служебные блоки и инструкции в начале вопросов.
        seq = []          # (i, номер) реальных вопросов по порядку
        leads = []        # (i, явный блок | None, текст)
        for i in idxs:
            entry, page, record, block = items[i]
            kind = block.get('type')
            if kind not in ('task', 'task_continuation', 'solution', 'criteria'):
                if kind in ('noise', 'header') and marker_of(block):
                    leads.append((i, marker_of(block), ''))
                continue
            text, title = _text(block), (block.get('title') or '')
            if is_rules_text(text, title) and str(block.get('task_variant') or '').strip():
                # Правила этапа и первый вопрос в одном блоке через «---»
                # (mosh-2024-qualifying-6, 1/3): правила — отдельным служебным
                # блоком, вопрос остаётся заданием.
                head, sep, tail = text.rpartition('\n---\n')
                if sep and tail.strip() and not is_rules_text(tail):
                    block = dict(block, text=tail.strip(), title='', _rules_head=head)
                    items[i] = (entry, page, record, block)
                    text, title = block['text'], ''
            if is_rules_text(text, title) or (not str(block.get('task_variant') or '').strip()
                                              and is_service_text(text, title)):
                items[i] = (entry, page, record, dict(block, number='', _service=True))
                if not is_rules_text(text, title):      # правила — только во вступление
                    leads.append((i, marker_of(block), '\n\n'.join(format_lines(text, title))))
                if report is not None:
                    report['v5: служебный блок — не задание'] += 1
                continue
            n = _int_number(block)
            if not n:
                continue
            if kind == 'task':
                new, lead = split_leading_instruction(block)
                if lead:
                    items[i] = (entry, page, record, new)
                    leads.append((i, marker_of({'title': lead}), '\n\n'.join(format_lines(lead))))
            seq.append((i, n))
        # 2. Границы блоков: пара (номер, вариант) уже была в текущем блоке —
        # начался следующий (4/3 → 1/1; блок из одного вопроса: 1/3 → 1/1).
        # Вопрос без варианта границу не задаёт. Смещения — по наибольшему номеру.
        block_of, maxes, b, seen = {}, {1: 0}, 1, set()
        for i, n in seq:
            variant = str(items[i][3].get('task_variant') or '').strip()
            if variant and (n, variant) in seen:
                b += 1
                maxes[b] = 0
                seen = set()
            if variant:
                seen.add((n, variant))
            block_of[i] = b
            maxes[b] = max(maxes[b], n)
        if b < 2:
            continue              # блоков нет: файл не трогаем
        for i in idxs:            # файл с блоками: ответы сверяются по тексту вопроса
            entry, page, record, block = items[i]
            items[i] = (entry, page, record, dict(block, _qfile=True))
        offset, acc = {}, 0
        for k in sorted(maxes):
            offset[k] = acc
            acc += maxes[k]
        for i, n in seq:
            entry, page, record, block = items[i]
            k = block_of[i]
            items[i] = (entry, page, record, dict(block, number=str(offset[k] + n), _block=k))
        if report is not None:
            report['v5: блоки отборочного МОШ — сквозная нумерация'] += 1
        # 3. Инструкции → блок (явный «Блок K» или блок ближайшего вопроса).
        ranges = {k: list(range(offset[k] + 1, offset[k] + maxes[k] + 1)) for k in maxes}
        for pos, (i, explicit, text) in enumerate(leads):
            if not text:
                continue
            k = explicit if explicit in ranges else None
            if k is None:
                before = [block_of[j] for j, _n in seq if j < i]
                after = [block_of[j] for j, _n in seq if j > i]
                k = before[-1] if before else (after[0] if after else None)
            if k is None:
                continue
            entry, page, record, block = items[i]
            nums = targets(text) or ranges[k]
            items[i] = (entry, page, record, dict(block, _lead=text, _lead_numbers=nums))
    return items


# ── Пункты задачи ────────────────────────────────────────────────────────

_ITEM = re.compile(r'(?m)^\s*(?:\*\*)?\(?(\d{1,2})[).](?:\*\*)?\s')


def items_in(text):
    """Сколько пунктов «1) … 2) …» подряд с 1 в тексте задачи."""
    seen = {int(n) for n in _ITEM.findall(text or '')}
    k = 0
    while k + 1 in seen:
        k += 1
    return k


def points_word(n):
    n = int(n)
    if n % 10 == 1 and n % 100 != 11:
        return 'балл'
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return 'балла'
    return 'баллов'


def item_label(number, points, text):
    """«N) (k баллов) » перед текстом пункта — если в тексте метки ещё нет."""
    body = (text or '').lstrip()
    if re.match(r'^\(?\**' + re.escape(str(number)) + r'[).]', body):
        return text
    head = f'{number})'
    if points not in (None, '') and not re.match(r'^\*{0,2}\(\d+\s*балл', body):
        head += f' ({points} {points_word(points)})'
    return f'{head} {body}'


# ── Правила v6 ───────────────────────────────────────────────────────────

ESSAY_NUMBER = 'эссе'
_ESSAY = re.compile(r'^\W*эссе\b', re.IGNORECASE)
_MARK = re.compile(r'\(\s*отмечено[^()]{0,8}\)', re.IGNORECASE)
_TEST_TWIN = re.compile(r'тест-(?:\d+\.)?(\d+)')


def is_essay(block):
    """Блок начинается с заголовка «Эссе…» (в названии или первой строке)."""
    for source in ((block.get('title') or '').strip(), _text(block).split('\n', 1)[0].strip()):
        if _ESSAY.match(source.strip('*# ')):
            return True
    return False


def unmark(text):
    """Текст вопроса из файла ответов без пометок «(отмечено)»."""
    return _MARK.sub(' ', text or '')


def twin_number(task_number):
    """«тест-7», «тест-2.7» → «7» (номер, под которым вопрос повторяет файл ответов)."""
    m = _TEST_TWIN.fullmatch(task_number or '')
    return m.group(1) if m else None
