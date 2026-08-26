# -*- coding: utf-8 -*-
"""ЛЭШ_2026_Гамма: разбор собственного макроса \\z{...} (CORPUS_FORMAT_ATLAS
§"Специфика новых источников" — задачи размечены `\\z[Название][баллы]
{Текст}{\\n Пункт1; \\n Пункт2;}[Источник]`, аргументы не плоские, внутри
могут быть вложенные фигурные скобки (формулы), поэтому парсер читает
аргументы с учётом баланса скобок, а не одной regex-строкой.

Живой пример (Подборки/Макроэкономика/Фискальная политика.tex):
\\z[Остров Мадагаскар]{В закрытой экономике...}{
\\n Определите ВВП острова Мадагаскар
\\n Как изменится ВВП...
}
"""
from __future__ import annotations

import re

_Z_RE = re.compile(r'\\z\b')


def _read_arg(text, pos):
    """Прочитать один аргумент макроса, начинающийся с '[' или '{' на
    позиции pos, с учётом вложенных скобок ТОГО ЖЕ типа (формулы внутри
    аргумента могут содержать свои {} — баланс это учитывает).

    Возвращает (содержимое, позиция_после_закрывающей_скобки)."""
    open_ch = text[pos]
    close_ch = ']' if open_ch == '[' else '}'
    depth = 0
    start = pos + 1
    i = pos
    while i < len(text):
        if text[i] == open_ch:
            depth += 1
        elif text[i] == close_ch:
            depth -= 1
            if depth == 0:
                return text[start:i], i + 1
        i += 1
    raise ValueError('несбалансированные скобки аргумента \\z')


def parse_z_blocks(text):
    """Найти все \\z[...][...]{...}{...}[...] МЕЖДУ \\begin{document} и
    \\end{document} (в шапке файла \\z упоминается ещё в комментарии-
    инструкции — атлас: наивный grep даёт 187 вместо 152 по всему архиву).

    Возвращает (blocks, warnings), blocks — список списков аргументов вида
    [(open_ch, content), ...] в порядке появления, без интерпретации ролей
    (роли — задача interpret_z_args)."""
    doc_match = re.search(r'\\begin\{document\}(.*?)\\end\{document\}', text, re.DOTALL)
    body = doc_match.group(1) if doc_match else text

    blocks = []
    warnings = []
    for match in _Z_RE.finditer(body):
        pos = match.end()
        args = []
        try:
            while True:
                # Аргументы макроса могут разделяться пробелами/переносами
                # строк (живой пример: "\\z[Название]\n{Текст}" — обёртка
                # на следующей строке). Без пропуска пробела чтение
                # останавливалось после первого аргумента, а "{Текст}" и
                # дальнейшие пункты молча терялись.
                skip = pos
                while skip < len(body) and body[skip].isspace():
                    skip += 1
                if skip >= len(body) or body[skip] not in '[{':
                    break
                pos = skip
                open_ch = body[pos]
                content, pos = _read_arg(body, pos)
                args.append((open_ch, content))
        except ValueError:
            warnings.append(f'\\z на позиции {match.start()}: несбалансированные скобки, блок пропущен')
            continue
        if args:
            blocks.append(args)
    return blocks, warnings


def interpret_z_args(args):
    """[(open_ch, content), ...] -> {'name', 'points', 'statement',
    'subpoints', 'source'}. Роли определяются по ПОЗИЦИИ и ТИПУ скобки:
    '[' до первой '{' — name, затем points; '{' — statement, затем
    subpoints; '[' после '{' — source. Все три [...] необязательны
    (атлас: "Можно добавить... или только что-то из этого")."""
    name = None
    points = None
    braces = []
    trailing_brackets = []
    seen_brace = False
    for open_ch, content in args:
        if open_ch == '{':
            seen_brace = True
            braces.append(content)
        else:
            if not seen_brace:
                if name is None:
                    name = content
                elif points is None:
                    points = content
            else:
                trailing_brackets.append(content)

    statement = braces[0].strip() if braces else ''
    subpoints_raw = braces[1] if len(braces) > 1 else ''
    subpoints = [
        item.strip().rstrip(';').strip()
        for item in subpoints_raw.split('\\n')
        if item.strip().rstrip(';').strip()
    ]
    source = trailing_brackets[0] if trailing_brackets else None

    return {
        'name': name,
        'points': points,
        'statement': statement,
        'subpoints': subpoints,
        'source': source,
    }
