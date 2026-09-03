# -*- coding: utf-8 -*-
"""Сканер длинного тире «—» в тексте, который видит пользователь.

Правило владельца: в текстах сайта длинное тире не используем. Максимум —
короткое «–» (U+2013), и только там, где оно действительно нужно.

⚠️ ПОЧЕМУ НЕТ `--fix`. Автозамена «—» → «–» испортила бы половину мест:
где-то тире надо не заменить, а УБРАТЬ, где-то — перестроить фразу. Сканер
только считает и показывает, правит человек (или Claude Code) руками.

⚠️ ЧТО НЕ СЧИТАЕТСЯ. Комментарии — их пользователь не видит:
`{% comment %}`, `{# #}`, `<!-- -->`, `/* */` и `//` вне строк. Скобочные
комментарии вырезаются целиком, `//` — с учётом кавычек, чтобы не срезать
`https://` и не съесть текст внутри строки.

Запуск:
    python scripts/check_em_dash.py                # весь боевой текст сайта
    python scripts/check_em_dash.py game templates # только эти каталоги
    python scripts/check_em_dash.py --json         # машинный вывод
"""
import json
import os
import re
import sys

DASH = '—'

# Каталоги приложений, чей текст видит пользователь.
APP_DIRS = ['templates', 'problems', 'catalog', 'teacher', 'student',
            'game', 'calc2', 'calendar_stub', 'shtrikh', 'config']

# Что НЕ смотрим: документация, отчёты, служебное, сборки.
SKIP_PARTS = ('docs', 'reports', 'scripts', '.claude', 'node_modules',
              'migrations', '__pycache__', 'venv', 'staticfiles')

# Файлы-исключения: только определения токенов (там одни комментарии).
SKIP_FILES = {os.path.join('templates', '_tokens.html')}


def _blank(match):
    """Комментарий → столько же ПЕРЕВОДОВ СТРОК, сколько в нём было.

    ⚠️ Не пустая строка. Раньше многострочный комментарий вырезался
    целиком, и все номера строк ПОСЛЕ него уезжали вверх: сканер честно
    считал 271 знак, но показывал их на чужих строках, и по его выводу
    правились не те места. Счётчик от этого не страдал, поэтому баг жил
    незамеченным.
    """
    return '\n' * match.group(0).count('\n')


def strip_comments(text, ext):
    """Убрать из текста всё, чего пользователь не увидит."""
    if ext == '.html':
        text = re.sub(r'\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}', _blank,
                      text, flags=re.S)
        text = re.sub(r'\{#.*?#\}', _blank, text, flags=re.S)
        text = re.sub(r'<!--.*?-->', _blank, text, flags=re.S)
    if ext in ('.html', '.js', '.css'):
        text = re.sub(r'/\*.*?\*/', _blank, text, flags=re.S)
        text = '\n'.join(_strip_line_comment(ln) for ln in text.split('\n'))
    if ext == '.py':
        text = '\n'.join(_strip_py_comment(ln) for ln in text.split('\n'))
    return text


def _scan_quotes(line, opener):
    """Пройти строку, отдавая индексы символов ВНЕ кавычек.

    Кавычки в коде бывают внутри кавычек другого рода, поэтому состояние
    ведём честно, а не регуляркой.
    """
    quote = None
    i = 0
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == '\\':
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in '\'"`':
            quote = ch
        else:
            yield i
        i += 1


def _strip_line_comment(line):
    """Срезать `//`-комментарий, не тронув `https://` и текст в кавычках."""
    for i in _scan_quotes(line, None):
        if line.startswith('//', i) and (i == 0 or line[i - 1] != ':'):
            return line[:i]
    return line


def _strip_py_comment(line):
    """Срезать `#`-комментарий вне строк."""
    for i in _scan_quotes(line, None):
        if line[i] == '#':
            return line[:i]
    return line


def wanted(path):
    parts = path.replace('\\', '/').split('/')
    if any(p in SKIP_PARTS for p in parts):
        return False
    if path.replace('/', os.sep) in SKIP_FILES:
        return False
    ext = os.path.splitext(path)[1]
    if ext == '.html':
        return True
    # Боевые скрипты и стили — только те, что реально отдаются браузеру.
    if ext in ('.js', '.css'):
        return 'static' in parts
    return False


def scan(roots):
    found = []
    for root in roots:
        if os.path.isfile(root):
            files = [root]
        else:
            files = []
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in SKIP_PARTS]
                files += [os.path.join(dirpath, f) for f in filenames]
        for f in files:
            f = os.path.relpath(f).replace('\\', '/')
            if not wanted(f):
                continue
            try:
                raw = open(f, encoding='utf-8').read()
            except (UnicodeDecodeError, OSError):
                continue
            if DASH not in raw:
                continue
            body = strip_comments(raw, os.path.splitext(f)[1])
            n = body.count(DASH)
            if n:
                lines = [i + 1 for i, ln in enumerate(body.split('\n'))
                         if DASH in ln]
                found.append({'file': f, 'count': n, 'lines': lines})
    return sorted(found, key=lambda r: -r['count'])


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    as_json = '--json' in sys.argv
    roots = args or APP_DIRS
    roots = [r for r in roots if os.path.exists(r)]
    rows = scan(roots)
    total = sum(r['count'] for r in rows)
    if as_json:
        print(json.dumps({'total': total, 'files': rows}, ensure_ascii=False))
    else:
        for r in rows:
            print(f"{r['count']:5}  {r['file']}")
        print(f"\nвсего «{DASH}» вне комментариев: {total} в {len(rows)} файлах")
    return 1 if total else 0


if __name__ == '__main__':
    sys.exit(main())
