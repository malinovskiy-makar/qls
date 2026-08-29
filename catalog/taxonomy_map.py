"""Справочник тем и тегов для карты корпуса (/catalog/map/).

⚠️ ЭТО ВРЕМЕННЫЙ СЛОЙ ДАННЫХ, И ОН ИЗОЛИРОВАН НАМЕРЕННО.

Новой таксономии в базе ещё НЕТ: в таблице `Tag` на 29.08.2026 лежит 551
запись — мусор от импорта (авторы, ссылки, обрывки комментариев), прогон
разметки не сделан. Поэтому карта строится по справочнику из репозитория,
а не по базе.

Весь доступ к данным идёт через ОДНУ функцию `build_map()`. После прогона
разметки достаточно переписать её (брать темы и теги из базы), и ни
шаблон, ни JavaScript карты трогать не придётся.

Источник дерева — `catalog/data/taxonomy_tree.md`, раздел «## 4. Полное
дерево». Результат сборки — `catalog/data/topic_map.json`, он коммитится
в репозиторий; пересобрать после правки дерева: `manage.py build_topic_map`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / 'data'
TREE_PATH = DATA_DIR / 'taxonomy_tree.md'
JSON_PATH = DATA_DIR / 'topic_map.json'


# ── Семь разделов корпуса ────────────────────────────────────────────────
#
# Мета-группировка тем: 29 «одуванчиков» человек взглядом не охватывает, а
# семь смысловых блоков — охватывает. Цвета — ОТДЕЛЬНЫЙ ПРЕДМЕТНЫЙ СЛОЙ,
# по образцу цветов кривых в /calc2/: они означают раздел корпуса, а не
# оформление. Сигнальные зелёный/амбер/красный (правило 1.1.2 канона) сюда
# не заходят и наоборот.
#
# ⚠️ Сами значения живут в токенах (`--g-base` … `--g-tools` в
# `templates/_tokens.html`), JavaScript читает их через getComputedStyle и
# перечитывает при смене темы. Здесь они продублированы ТОЛЬКО как запасной
# вариант на случай, если токен не найден, и как документация состава групп.
GROUPS = (
    # ключ,     название,                   светлая,   тёмная,   темы
    ('base',   'Основы и выбор',            '#1F5FD0', '#6FA8FF', (1, 2)),
    ('market', 'Рынок и потребитель',       '#0E8578', '#3FD0BE', (3, 4, 5)),
    ('firm',   'Фирма и структуры рынка',   '#C24A2E', '#FF8A6B', (6, 7, 8, 9)),
    ('state',  'Государство и доходы',      '#9A6512', '#E8A93C', (10, 11, 12, 13, 14)),
    ('macro',  'Мир и макроэкономика',      '#2E8B40', '#5FCE72',
     (15, 16, 17, 18, 19, 20, 21, 22, 23)),
    ('fin',    'Финансы и инвестиции',      '#7A34C9', '#B98BFF', (24, 25)),
    ('tools',  'Методы и прочее',           '#4F6076', '#93A6BE', (26, 27, 28, 29)),
)


# ── 82 перекрёстные связи между тегами разных тем ────────────────────────
#
# ⚠️ ЭТИ ПАРЫ ЗАДАНЫ ВРУЧНУЮ, И ЭТО ВРЕМЕННО.
# Смысл связи — родственные теги из разных тем: «Эластичность и
# распределение налогового бремени» ↔ «Распределение налогового бремени
# между сторонами», «Монопсония и покупательная власть» ↔ «Монопсония на
# рынке труда», «Гиперболическое дисконтирование» ↔ «Дисконтирование и
# приведённая стоимость».
#
# После прогона разметки их надо ПЕРЕСЧИТАТЬ ПО КОРПУСУ — по совместной
# встречаемости тегов в задачах либо по близости эмбеддингов BGE-M3. До тех
# пор это оценка человека, а не факт о банке задач. Отдельная карточка в
# Notion, направление «Каталог и поиск».
#
# Формат: «тема.тег-тема.тег», нумерация — как в дереве.
CROSS_LINKS_RAW = """
4.9-10.5   2.11-15.1  2.12-15.2  3.11-10.12 5.14-13.2  6.7-7.2    8.12-10.11
8.15-13.4  8.11-10.8  9.17-12.5  9.10-11.8  10.7-21.4  10.16-14.6 11.3-10.1
11.11-26.6 12.1-5.1   12.10-28.13 12.2-25.8 13.6-10.9  13.8-23.3  13.10-25.1
14.2-27.2  14.1-28.14 15.5-10.10 16.8-20.1  16.1-18.7  17.6-18.1  17.7-18.3
18.7-24.8  18.6-19.8  19.7-23.8  19.6-20.2  20.7-21.2  20.8-5.13  20.9-22.7
21.9-25.11 21.5-25.5  22.8-18.1  22.3-28.8  22.6-24.3  23.4-6.4   23.5-9.15
24.2-28.8  25.1-5.13  25.9-12.10 26.5-25.1  26.3-12.1  26.8-1.5   27.8-28.10
28.5-5.4   28.5-6.9   28.3-6.7   28.7-6.13  28.1-3.4   28.6-3.8   28.6-6.10
1.6-11.5   1.1-2.2    1.4-5.1    1.8-17.1   3.13-4.4   3.14-8.3   5.5-2.14
5.9-4.5    6.11-8.9   7.12-8.12  9.18-7.1   29.2-24.10 2.1-6.14   11.10-23.10
15.10-1.9  13.11-1.6  7.3-3.2    8.13-9.1   9.8-8.1    14.6-21.1  16.7-17.1
19.1-13.9  22.11-25.10 27.7-26.9 10.14-11.7 12.3-8.4
"""


def parse_cross_links(raw: str = CROSS_LINKS_RAW) -> list[tuple[int, int, int, int]]:
    """«4.9-10.5» → (4, 9, 10, 5). Порядок сохраняется, дубли не убираются."""
    out = []
    for token in raw.split():
        m = re.fullmatch(r'(\d+)\.(\d+)-(\d+)\.(\d+)', token)
        if not m:
            raise ValueError('не разобрана перекрёстная связь: %r' % token)
        out.append(tuple(int(g) for g in m.groups()))
    return out


def parse_tree(md_text: str) -> list[dict]:
    """Разбирает раздел «## 4. Полное дерево» в список тем с тегами.

    Тема — строка «### 8. Монополия и ценовая дискриминация».
    Определение — следующая строка целиком в звёздочках.
    Тег — строка «12. Потери общества от монополии (DWL) (207)».
    """
    themes: list[dict] = []
    cur: dict | None = None
    for ln in md_text.split('\n'):
        m = re.match(r'^### (\d+)\.\s+(.+?)\s*$', ln)
        if m:
            cur = {'n': int(m.group(1)), 'title': m.group(2), 'desc': '', 'tags': []}
            themes.append(cur)
            continue
        if cur is None:
            continue
        if ln.startswith('*') and not cur['desc'] and ln.strip().endswith('*'):
            cur['desc'] = ln.strip().strip('*')
            continue
        m = re.match(r'^(\d+)\.\s+(.+?)\s*$', ln)
        if m:
            label, cnt = m.group(2), None
            # ⚠️ Пояснение внутри скобки начинается с БУКВЫ, а не с цифры и
            # не со слэша: «(338 суммарно по экстерналиям)» — счётчик 338 и
            # пояснение, «(3 153)» — одно число с разделителем разрядов,
            # «(110 / 197)» — два паттерна. Если разрешить пояснению
            # начинаться с чего угодно, «3 153» превращается в «3», а
            # «110 / 197» — в «110»: молча, без единой ошибки.
            cm = re.search(r'\(([\d\s/]+?)(?:\s+[^\d)/][^)]*)?\)\s*$', label)
            if cm:
                cnt = _sum_counts(cm.group(1))
                if cnt is not None:
                    label = label[:cm.start()].strip()
            cur['tags'].append({'i': int(m.group(1)), 'label': label, 'count': cnt})
    return themes


def _sum_counts(chunk: str) -> int | None:
    """«110 / 197» → 307, «3 153» → 3153, «338» → 338.

    ⚠️ ПРОБЕЛ ВНУТРИ ЧИСЛА — ЭТО РАЗРЯДЫ, А НЕ ВТОРОЕ ЧИСЛО.
    В дереве два тега записаны с пробелом-разделителем тысяч: «(3 153)» у
    структуры издержек и «(1 792)» у средних и предельных издержек. Наивный
    разбор «все числа подряд и сложить» превращал их в 156 и 793 — то есть
    самый крупный тег корпуса выглядел на карте вдвадцатеро мельче правды.
    Слэш разделяет ДВА паттерна («110 / 197»), пробел — разряды одного числа.
    """
    parts = [p for p in chunk.split('/') if p.strip()]
    total, seen = 0, False
    for part in parts:
        digits = re.sub(r'\s+', '', part)
        if not digits.isdigit():
            continue
        total += int(digits)
        seen = True
    return total if seen else None


def load_tree(path: Path = TREE_PATH) -> list[dict]:
    """Читает файл дерева и разбирает из него ТОЛЬКО раздел 4."""
    src = path.read_text(encoding='utf-8')
    start = src.index('## 4. Полное дерево')
    # ⚠️ Границу ищем по НАЧАЛУ СТРОКИ, а не подстрокой «## 5.».
    # Подстрока «## 5.» входит в «### 5. Теория потребителя и полезность»,
    # и раздел обрезался на четвёртой теме: 4 темы вместо 29, и ни одной
    # ошибки — просто молча неполные данные.
    m5 = re.search(r'^## 5\.', src[start:], re.M)
    end = start + m5.start() if m5 else len(src)
    return parse_tree(src[start:end])


def build_map(tree: list[dict] | None = None) -> dict:
    """Единственная точка сборки данных карты.

    ⚠️ Именно эту функцию переписывают, когда таксономия появится в базе:
    формат ответа менять нельзя, источник — можно.
    """
    themes = tree if tree is not None else load_tree()
    theme_by_n = {th['n']: th for th in themes}
    group_of: dict[int, str] = {}

    groups = []
    for key, label, light, dark, nums in GROUPS:
        groups.append({'k': key, 'l': label, 'cl': light, 'cd': dark,
                       'themes': list(nums)})
        for n in nums:
            group_of[n] = key

    missing = sorted(set(theme_by_n) - set(group_of))
    if missing:
        raise ValueError('темы вне разделов корпуса: %s' % missing)

    nodes, links = [], []
    for th in themes:
        counted = [t['count'] for t in th['tags'] if t['count'] is not None]
        nodes.append({
            'id': 't%d' % th['n'], 'k': 'theme', 'n': th['n'],
            'l': th['title'], 'd': th['desc'], 'g': group_of[th['n']],
            'c': sum(counted) if counted else None,
        })
        for tag in th['tags']:
            nodes.append({
                'id': 't%d.%d' % (th['n'], tag['i']), 'k': 'tag', 'n': th['n'],
                'l': tag['label'], 'd': '', 'g': group_of[th['n']],
                'c': tag['count'],
            })
            links.append({'s': 't%d' % th['n'],
                          't': 't%d.%d' % (th['n'], tag['i']), 'k': 'tree'})

    known = {n['id'] for n in nodes}
    seen_pairs: set[frozenset] = set()
    for a_theme, a_tag, b_theme, b_tag in parse_cross_links():
        a = 't%d.%d' % (a_theme, a_tag)
        b = 't%d.%d' % (b_theme, b_tag)
        for side in (a, b):
            if side not in known:
                raise ValueError('перекрёстная связь ссылается на несуществующий '
                                 'тег: %s (пара %s ↔ %s)' % (side, a, b))
        if a_theme == b_theme:
            raise ValueError('перекрёстная связь внутри одной темы: %s ↔ %s' % (a, b))
        pair = frozenset((a, b))
        if pair in seen_pairs:
            raise ValueError('перекрёстная связь задана дважды: %s ↔ %s' % (a, b))
        seen_pairs.add(pair)
        links.append({'s': a, 't': b, 'k': 'cross'})

    return {'groups': groups, 'nodes': nodes, 'links': links}


def write_map(data: dict, path: Path = JSON_PATH) -> int:
    """Пишет JSON и возвращает его размер в байтах."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    path.write_text(text, encoding='utf-8')
    return len(text.encode('utf-8'))


def read_map(path: Path = JSON_PATH) -> dict:
    """Читает собранный JSON с диска."""
    return json.loads(path.read_text(encoding='utf-8'))
