# -*- coding: utf-8 -*-
"""Связь «задача в базе → фрагмент исходного `.tex` в Overleaf-архиве».

Зачем это нужно. До 2026-08-30 конвертер чинил текст, который уже лежал
в базе: исходников под рукой не было. Из-за этого 150 карточек аудита
(`INCOMP`, `MISS`) были принципиально нечинимы — потерянный рисунок или
недостающий подпункт неоткуда взять. Владелец выгрузил 67 zip-проектов
Overleaf, и теперь исходник есть. Этот модуль ищет, ГДЕ именно в
исходнике лежит конкретная задача.

Как ищется. У сырого `.tex` и у сохранённого текста задачи общий
инвариант — русская проза: формулы и разметка у них разные (LaTeX против
выхода конвертера), а слова условия те же. Обе стороны сводятся к
последовательности русских слов, из неё берутся 8-словные «черепицы», и
задача связывается с файлом по их пересечению.

Почему 8 слов. Это порог доказательности: восемь значимых слов подряд,
совпавших дословно, случайно не встречаются даже на 41 307 задачах.
Меньшее окно начало бы ловить общие обороты («найдите равновесную цену
на рынке»), большее — рассыпалось бы на любой мелкой правке текста.

Главное свойство: у совпадения известны координаты в символах исходного
файла. Поэтому можно взять не «файл, где-то в котором есть эта задача»,
а ровно тот кусок, который ей соответствует, — и искать `\\includegraphics`
внутри него, а не во всём листочке на 40 задач.
"""
import hashlib
import os
import re
import unicodedata

BS = chr(92)

_RE_TEX_COMMENT = re.compile(r'(?<!' + BS + BS + r')%.*')
_RE_MATH_DD = re.compile(r'\$\$.*?\$\$', re.S)
_RE_MATH_BR = re.compile(re.escape(BS + '[') + r'.*?' + re.escape(BS + ']'), re.S)
_RE_MATH_PR = re.compile(re.escape(BS + '(') + r'.*?' + re.escape(BS + ')'), re.S)
_RE_MATH_D = re.compile(r'\$[^$]*\$', re.S)
_RE_CMD = re.compile(BS + BS + r'[A-Za-z@]+\*?')
_RE_WORD = re.compile(r'[а-яё]+')

#: Слова, которые есть в любом листочке и ничего не различают. Выкидываются
#: ДО нарезки на черепицы, иначе окно из восьми слов наполовину состояло бы
#: из предлогов и перестало бы что-либо доказывать.
STOP = frozenset((
    'и', 'в', 'на', 'с', 'по', 'не', 'что', 'а', 'из', 'за', 'то', 'как',
    'для', 'от', 'к', 'у', 'же', 'но', 'о', 'до', 'при', 'бы', 'это', 'все',
))

K = 8


def _blank(match):
    """Заменить кусок пробелами той же длины: смещения символов не едут."""
    return ' ' * (match.end() - match.start())


def mask_tex(text):
    """Скрыть комментарии, математику и команды, СОХРАНИВ длину строки.

    Длина сохраняется намеренно: по индексу слова потом восстанавливается
    позиция в ИСХОДНОМ файле, а значит и границы фрагмента задачи."""
    text = _RE_TEX_COMMENT.sub(_blank, text)
    for rx in (_RE_MATH_DD, _RE_MATH_BR, _RE_MATH_PR, _RE_MATH_D, _RE_CMD):
        text = rx.sub(_blank, text)
    return text


def words_with_pos(text, tex=False, mask=True):
    """`[(слово, начало, конец)]` — значимые русские слова и их координаты.

    `mask=False` отключает скрытие математики. Нужно там, где текст —
    ЗАРАНЕЕ ОБРЕЗАННЫЙ кусок файла: обрезка почти всегда рассекает
    `$$…$$` пополам, после чего парность `$` ломается и регулярка
    «съедает» абзацы обычной прозы между уцелевшими долларами. Для
    поиска это неважно (ищем по целым файлам), а для измерения
    покрытия давало заниженные 7–17 % на заведомо верных совпадениях."""
    if not text:
        return []
    text = unicodedata.normalize('NFKC', text)
    if mask:
        if tex:
            text = mask_tex(text)
        else:
            for rx in (_RE_MATH_DD, _RE_MATH_BR, _RE_MATH_PR, _RE_MATH_D,
                       _RE_CMD):
                text = rx.sub(_blank, text)
    text = text.lower().replace('ё', 'е')
    out = []
    for m in _RE_WORD.finditer(text):
        w = m.group(0)
        if len(w) > 1 and w not in STOP:
            out.append((w, m.start(), m.end()))
    return out


def plain_words(text, tex=False, mask=True):
    """Только слова, без координат — для стороны базы."""
    return [w for w, _s, _e in words_with_pos(text, tex=tex, mask=mask)]


def h64(text):
    """Устойчивый 64-битный хеш: встроенный `hash()` рандомизируется от
    запуска к запуску, а индекс переживает несколько прогонов."""
    return int.from_bytes(
        hashlib.blake2b(text.encode('utf-8'), digest_size=8).digest(), 'big')


def shingles(words, k=K, stride=1):
    """Множество хешей k-словных окон.

    Текст короче окна отдаёт одну черепицу целиком — иначе короткие задачи
    («Найдите равновесие», список из трёх пунктов) вообще не искались бы.

    `stride > 1` прореживает индекс базы. Это безопасно: если проза
    совпадает дословно, окно базы найдётся среди окон сырого файла,
    взятых с шагом 1."""
    if len(words) < 4:
        return set()
    if len(words) < k:
        return {h64(' '.join(words))}
    return {h64(' '.join(words[i:i + k]))
            for i in range(0, len(words) - k + 1, stride)}


def shingle_positions(words_pos, k=K):
    """`хеш -> [индексы слов]` для сырого файла: нужны координаты попаданий."""
    out = {}
    words = [w for w, _s, _e in words_pos]
    if len(words) < 4:
        return out
    if len(words) < k:
        out.setdefault(h64(' '.join(words)), []).append(0)
        return out
    for i in range(len(words) - k + 1):
        out.setdefault(h64(' '.join(words[i:i + k])), []).append(i)
    return out


#: Разрыв в значимых словах, по которому совпадения считаются разными
#: местами файла. Задача — это 30–150 значимых слов подряд; окна внутри
#: неё идут почти вплотную, а до следующей задачи расстояние заметно
#: больше.
CLUSTER_GAP = 60


def span_of(words_pos, indices, k=K, gap=CLUSTER_GAP):
    """Границы САМОГО ПЛОТНОГО совпадения в символах: `(начало, конец, окон)`.

    Не `min..max`: пара шаблонных оборотов, случайно совпавших в другом
    конце листочка на сорок задач, растянула бы фрагмент на весь файл.
    Проверка глазами это и показала — «покрытие 100 %» получалось из
    окна во весь документ, а показанный кусок к задаче не относился.
    Поэтому совпадения группируются по близости, и берётся группа с
    наибольшим числом окон."""
    if not indices:
        return None
    uniq = sorted(set(indices))
    clusters = [[uniq[0]]]
    for i in uniq[1:]:
        if i - clusters[-1][-1] <= gap:
            clusters[-1].append(i)
        else:
            clusters.append([i])
    best = max(clusters, key=len)
    lo = best[0]
    hi = min(best[-1] + k - 1, len(words_pos) - 1)
    return words_pos[lo][1], words_pos[hi][2], len(best)


# --- чтение файлов ---------------------------------------------------------

def read_text(path):
    """Текст файла. Overleaf пишет UTF-8, но в старых проектах попадается
    cp1251 — молча падать на этом нельзя, иначе проект просто выпадет."""
    with open(path, 'rb') as fh:
        raw = fh.read()
    for enc in ('utf-8', 'cp1251', 'koi8-r'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', errors='replace')


def iter_tex(root):
    """`(относительный путь, полный путь)` для всех `.tex` внутри проекта."""
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in sorted(filenames):
            if name.lower().endswith('.tex'):
                full = os.path.join(dirpath, name)
                yield os.path.relpath(full, root).replace(os.sep, '/'), full
