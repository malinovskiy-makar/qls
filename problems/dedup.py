# -*- coding: utf-8 -*-
"""Правила дедупа: из чего складывается группа и кто в ней фаворит.

Здесь живёт ВСЯ логика решения и ни одного обращения к базе — чтобы её
можно было проверить тестами на выдуманных задачах, без фикстур и без
41 307 строк. Команда `manage.py dedup_apply` достаёт данные и зовёт эти
функции; больше она ничего не решает.

Два источника рёбер, объединяются в одну связную компоненту:

1. **Точное совпадение ****`content_hash`****, прошедшее гейт по подпунктам.**
   `content_hash` — MD5 одного поля `statement`, подпунктов он не видит:
   самая большая «группа точного совпадения» в банке — 30 РАЗНЫХ тестовых
   заданий с общей шапкой. Гейт требует совпадения ещё и числа подпунктов
   с их отпечатком; на замере 11.09 он ужал 345 групп до 286, и обе
   известные ложные группы (30 заданий и 9 пустых условий) рассыпались
   нацело.

2. **Косинус ****`v1`**** ≥ 0,98 И числовой гейт И текстовый гейт ≥ 0,80.**
   Косинус в одиночку не выпускается ни на какой формуле: пара `51615` /
   `51609` («три группы покупателей и четыре продавцов» против «двух и
   трёх») даёт 0,9885 на `v1`, а это РАЗНЫЕ задачи. Разводит их числовой
   гейт.

Группы бывают из трёх и более задач: рёбра склеиваются в связные
компоненты, а не разбираются попарно.
"""
import hashlib

from problems.dedup_gates import compare_numbers, parts_key, text_jaccard, trigrams
from problems.models import DupMark

#: Правила, при которых фаворит назначается. Всё остальное — на глаз человеку.
#:
#: ⚠️ Это ЕДИНСТВЕННОЕ место, где живёт уверенность. Отдельного поля
#: `confidence` в `DupMark` нет намеренно: два хранимых поля вместо одного
#: вычисляемого рано или поздно разойдутся.
CONFIDENT_RULES = frozenset({
    DupMark.Rule.APPROVED,
    DupMark.Rule.COMPLETENESS_MARGIN,
})

#: Порог косинуса явного уровня. 0,98, а не 0,97: в полосе 0,97–0,98 живут
#: ложные пары, которых гейты не ловят (замер 11.09).
COS_THRESHOLD = 0.98
#: Порог символьной близости полных условий.
JACCARD_THRESHOLD = 0.80
#: Отрыв по полноте, ниже которого лидер не считается доказанным.
COMPLETENESS_MARGIN = 2


def is_confident(rule):
    return rule in CONFIDENT_RULES


# ── Рёбра ───────────────────────────────────────────────────────────────

def hash_edges(rows):
    """Рёбра по точному совпадению `content_hash` с гейтом по подпунктам.

    `rows` — последовательность `(problem_id, content_hash, parts)`, где
    `parts` — список пар `(statement, answer)` подпунктов по порядку.
    Задачи с пустым хешем пропускаются: пустой хеш — это «не считали»,
    а не «одинаковые».

    Внутри выжившей подгруппы соединяем всех с первым (звезда): для связной
    компоненты этого достаточно, а пар получается n-1, а не n(n-1)/2.
    """
    корзины = {}
    for pid, content_hash, parts in rows:
        if not content_hash:
            continue
        корзины.setdefault((content_hash, parts_key(parts)), []).append(pid)

    рёбра = []
    for члены in корзины.values():
        if len(члены) < 2:
            continue
        члены = sorted(члены)
        рёбра.extend((члены[0], other) for other in члены[1:])
    return рёбра


def cosine_edge_passes(sim, text_a, text_b,
                       cos_threshold=COS_THRESHOLD,
                       jaccard_threshold=JACCARD_THRESHOLD):
    """Проходит ли пара явный уровень: косинус И числа И текст.

    `text_a` / `text_b` — ПОЛНЫЙ текст задачи (условие вместе с подпунктами).
    Часть чисел живёт именно в подпунктах, и числовой гейт, читающий один
    `statement`, их не увидит.
    """
    if sim < cos_threshold:
        return False
    if compare_numbers(text_a, text_b) != 'совпадают':
        return False
    return text_jaccard(trigrams(text_a), trigrams(text_b)) >= jaccard_threshold


# ── Связные компоненты ──────────────────────────────────────────────────

def build_groups(edges):
    """Связные компоненты по рёбрам. Возвращает dict `group_id -> [ids]`.

    Идентификатор группы — md5 от её состава, поэтому повторный прогон на
    тех же данных даёт ТЕ ЖЕ идентификаторы: это и есть идемпотентность.
    Одиночные задачи в результат не попадают — группы из одного не бывает.
    """
    родитель = {}

    def корень(x):
        родитель.setdefault(x, x)
        while родитель[x] != x:
            родитель[x] = родитель[родитель[x]]
            x = родитель[x]
        return x

    for a, b in edges:
        ra, rb = корень(a), корень(b)
        if ra != rb:
            родитель[max(ra, rb)] = min(ra, rb)

    компоненты = {}
    for узел in родитель:
        компоненты.setdefault(корень(узел), []).append(узел)

    группы = {}
    for члены in компоненты.values():
        if len(члены) < 2:
            continue
        члены = sorted(члены)
        группы[group_id(члены)] = члены
    return группы


def group_id(members):
    """Устойчивый идентификатор группы по её составу.

    Префикс `d` — чтобы группы этой команды нельзя было спутать с разметкой
    ночи 08.09 в `Problem.dup_group` (там `g` и 12 знаков).
    """
    сырое = ','.join(str(i) for i in sorted(members)).encode('utf-8')
    return 'd' + hashlib.md5(сырое, usedforsecurity=False).hexdigest()[:16]


# ── Выбор фаворита ──────────────────────────────────────────────────────

def completeness_score(member):
    """Балл полноты 0–6: по одному за каждый признак заполненности.

    `member` — словарь с ключами `parts`, `solution`, `figures`, `tags`,
    `topics`, `content_format`.
    """
    return (
        int(member['parts'] > 0)
        + int(bool((member['solution'] or '').strip()))
        + int(member['figures'] > 0)
        + int(member['tags'] >= 1)
        + int(member['topics'] >= 1)
        + int(member['content_format'] == 'markdown')
    )


def choose_best(members):
    """Кто фаворит группы. Возвращает `(правило, id фаворита или None)`.

    `members` — список словарей с ключами `id`, `approved`, `figures` и
    всем, что нужно `completeness_score`.

    Порядок веток — и есть правило старшинства:

    1. **Больше одной approved** — всегда на глаз, независимо от картинок.
       Случай редкий, но молча выбирать одну из двух проверенных человеком
       версий команда не имеет права.
    2. **Ровно одна approved.** Она фаворит — кроме случая, когда у неё нет
       картинки, а у кого-то из двойников есть: картинка в условии несёт
       содержание, и потерять её молча нельзя. Тогда группа уходит на глаз
       и фаворита не получает никто.
    3. **approved нет вовсе** — считаем полноту. Фаворит назначается, только
       если лидер один И отрывается от ближайшего на 2 балла и больше.
       Иначе на глаз; победителя «по умолчанию» (например, по меньшему id)
       не назначаем — ровно этим и был плох `process_duplicates`.
    """
    approved = [m for m in members if m['approved']]

    if len(approved) > 1:
        return DupMark.Rule.NEEDS_REVIEW_MULTI_APPROVED, None

    if len(approved) == 1:
        фаворит = approved[0]
        если_картинка = (
            фаворит['figures'] == 0
            and any(m['figures'] > 0 for m in members
                    if m['id'] != фаворит['id'])
        )
        if если_картинка:
            return DupMark.Rule.APPROVED_PICTURE_REVIEW, None
        return DupMark.Rule.APPROVED, фаворит['id']

    баллы = sorted(((completeness_score(m), m['id']) for m in members),
                   key=lambda пара: (-пара[0], пара[1]))
    лучший, второй = баллы[0], баллы[1]
    один_лидер = sum(1 for балл, _ in баллы if балл == лучший[0]) == 1
    if один_лидер and лучший[0] - второй[0] >= COMPLETENESS_MARGIN:
        return DupMark.Rule.COMPLETENESS_MARGIN, лучший[1]
    return DupMark.Rule.NEEDS_REVIEW_TIE, None
