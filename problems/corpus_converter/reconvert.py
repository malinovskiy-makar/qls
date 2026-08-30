# -*- coding: utf-8 -*-
r"""Перегенерация сохранённого текста трёх новых источников ИЗ СЫРЬЯ.

Зачем модуль. У новых источников в базе лежит ВЫХОД конвертера
([ADR 0033](../../docs/adr/0033-new-sources-store-converted-text.md)).
Когда в конвертере чинится баг, исправить уже сохранённый текст можно
единственным безопасным способом: взять СЫРОЙ материал с диска и
прогнать `convert_for_import` заново.

⚠️ **Повторная канонизация поверх сохранённого текста запрещена.** Тот
же ADR: второй прогон конвертера по уже канонизированному тексту даёт
ДРУГОЙ результат, и шлюз снова судил бы не то, что на экране. Поэтому
здесь нет ни одной функции, принимающей `problem.statement` на вход, —
только чтение с диска.

Разбор своего формата у каждого источника свой и живёт в командах
импорта. Здесь — только то, что общее: как по внешнему id найти сырьё,
собрать поля ровно теми же вызовами и сравнить со стороннимися.
"""
from __future__ import annotations

import glob
import os

from problems.corpus_converter.criteria import (
    parse_shkolkovo_criteria, parse_solvehub_criteria,
)
from problems.corpus_converter.images import CONTENT_TYPES, replace_images
from problems.corpus_converter.ingest import convert_for_import, data_root
from problems.corpus_converter.lesh import interpret_z_args, parse_z_blocks
from problems.corpus_converter.solvehub import (
    format_answer, options_block, parse_options,
)


class Record:
    """Готовые поля одной задачи: ровно то, что положил бы импорт."""

    __slots__ = ('external_id', 'statement', 'answer', 'solution', 'parts',
                 'warnings', 'figures')

    def __init__(self, external_id, result, warnings=(), figures=()):
        self.external_id = external_id
        self.statement = result['statement_md']
        self.answer = result['answer_md']
        self.solution = result['solution_md']
        #: `[(метка, текст), ...]` в порядке показа.
        self.parts = [(p['label'], p['statement_md']) for p in result['parts']]
        self.warnings = list(warnings)
        #: `[(хеш, ссылка), ...]` — картинки, для которых файл есть на
        #: диске и в тексте стоит маркер. Отсюда их берёт
        #: `build_new_source_figures`.
        self.figures = list(figures)


class ImageResolver:
    """Есть ли файл на диске для этой ссылки — и где именно.

    Один объект на источник: карта читается с диска один раз, а не на
    каждую задачу."""

    def __init__(self, mapping, images_dir):
        #: ссылка → имя файла внутри `images_dir`.
        self.mapping = mapping
        self.images_dir = images_dir

    def __call__(self, reference):
        return self.path_for(reference) is not None

    def path_for(self, reference):
        name = self.mapping.get((reference or '').strip())
        if not name:
            return None
        path = os.path.join(self.images_dir, name)
        return path if os.path.isfile(path) else None


def _no_images(_reference):
    """Источник, у которого файлов картинок нет вовсе.

    Школково: 298 задач ссылаются на картинки (`ela.png`, `7.png`, …),
    и НИ ОДНОЙ из них нет в выгрузке — `QuestionFiles` пуст у всех 3 414
    записей, а 453 скачанных файла принадлежат 328 ДРУГИМ задачам, ни
    одна из которых в импорт не входила (пересечение id — ноль). Ставить
    маркер здесь значило бы молча стереть ссылку: маркер без строки
    `ProblemFigure` на экране исчезает."""
    return False


# ---------------------------------------------------------------------------
# Школково
# ---------------------------------------------------------------------------

def _load_json(path):
    import json
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _shkolkovo_dir(explicit=None):
    base = explicit or os.path.join(data_root(), 'shkolkovo')
    nested = os.path.join(base, 'problems')
    return nested if os.path.isdir(nested) else base


def shkolkovo_records(data_dir=None, only=None):
    """`{внешний id: Record}`. `only` — множество нужных id или None."""
    out = {}
    for path in sorted(glob.glob(os.path.join(_shkolkovo_dir(data_dir), '*.json'))):
        raw = _load_json(path)
        external_id = str(raw.get('Id') or '')
        statement_tex = raw.get('statement_tex') or ''
        if not external_id or not statement_tex:
            continue
        if only is not None and external_id not in only:
            continue
        # `_answer_text` из import_shkolkovo, дословно: развёрнутый ответ
        # приоритетнее краткого.
        answer = raw.get('answer_tex') or ((raw.get('Answer') or {}).get('text') or '')
        # `_no_images`: у Школково файлов картинок нет вовсе — см. её
        # docstring. Вызов оставлен явным, чтобы это было видно в коде,
        # а не подразумевалось отсутствием строки.
        statement_tex, _none = replace_images(statement_tex, _no_images)
        result = convert_for_import(
            statement=statement_tex, answer=answer,
            solution=raw.get('solution_tex') or '', existing_parts=None)
        criteria = parse_shkolkovo_criteria(raw.get('criteria_tex') or '')
        out[external_id] = Record(
            external_id, result, result['warnings'] + criteria['warnings'])
    return out


# ---------------------------------------------------------------------------
# SolveHub
# ---------------------------------------------------------------------------

def _solvehub_dir(explicit=None):
    base = explicit or os.path.join(data_root(), 'solvehub')
    nested = os.path.join(base, 'problems')
    return nested if os.path.isdir(nested) else base


def solvehub_resolver(data_dir=None):
    """Карта «URL картинки → файл в `images/`» из выгрузки SolveHub."""
    base = data_dir or os.path.join(data_root(), 'solvehub')
    if os.path.basename(base) == 'problems':
        base = os.path.dirname(base)
    map_path = os.path.join(base, 'image_map.json')
    mapping = _load_json(map_path) if os.path.isfile(map_path) else {}
    return ImageResolver(mapping, os.path.join(base, 'images'))


def solvehub_records(data_dir=None, only=None):
    out = {}
    resolve = solvehub_resolver(data_dir)
    for path in sorted(glob.glob(os.path.join(_solvehub_dir(data_dir), '*.json'))):
        raw = _load_json(path)
        external_id = str(raw.get('hash') or '')
        md = raw.get('md') or ''
        if not external_id or not md:
            continue
        if only is not None and external_id not in only:
            continue
        opts = parse_options(raw.get('check_options'))
        local = []
        answer_text = format_answer(raw.get('correct_answer'), opts, local)
        block = options_block(raw.get('check_type'), opts)
        statement_src = f'{md}\n\n{block}' if block else md
        solution_src = raw.get('answer_md') or ''
        # Маркеры ставятся по СЫРОМУ тексту, до конвертера: он их не
        # трогает, а второй прогон находит ноль ссылок (идемпотентно).
        figures = []
        statement_src, found = replace_images(statement_src, resolve)
        figures += found
        solution_src, found = replace_images(solution_src, resolve)
        figures += found
        result = convert_for_import(
            statement=statement_src, answer=answer_text,
            solution=solution_src, existing_parts=None)
        criteria = parse_solvehub_criteria(raw.get('answer_md') or '')
        out[external_id] = Record(
            external_id, result,
            local + result['warnings'] + criteria['warnings'],
            figures=figures)
    return out


# ---------------------------------------------------------------------------
# ЛЭШ Гамма
# ---------------------------------------------------------------------------

def lesh_records(data_dir=None, only=None):
    """Ключ у ЛЭШ — хэш префикса условия (`import_lesh.external_key`),
    числовых id у источника нет вовсе."""
    from problems.management.commands.import_lesh import (
        DEDUP_PREFIX, _iter_tex_files, _is_reshalka, _lesh_dir, external_key,
        solution_text,
    )
    root = _lesh_dir(data_dir)
    # У ЛЭШ карты картинок нет: `\includegraphics{Подборки/…/image.png}`
    # указывает прямо на файл внутри архива. Карта строится обходом.
    lesh_map = {}
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if os.path.splitext(name)[1].lower() not in CONTENT_TYPES:
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace('\\', '/')
            lesh_map[rel] = full
            lesh_map.setdefault(name, full)
    resolve = ImageResolver(
        {key: os.path.relpath(path, root) for key, path in lesh_map.items()},
        root)

    conditions, solutions_by_name = [], {}
    for path, rel in _iter_tex_files(root):
        with open(path, encoding='utf-8', errors='replace') as f:
            text = f.read()
        blocks, _warnings = parse_z_blocks(text)
        for block in blocks:
            parsed = interpret_z_args(block)
            if _is_reshalka(rel):
                if parsed['name']:
                    solutions_by_name.setdefault(parsed['name'], parsed)
            else:
                conditions.append((rel, parsed))

    seen, out = set(), {}
    for _rel, parsed in conditions:
        statement = parsed['statement']
        if not statement:
            continue
        prefix = statement[:DEDUP_PREFIX]
        if prefix in seen:
            continue
        seen.add(prefix)
        key = external_key(statement)
        if only is not None and key not in only:
            continue
        sol = solutions_by_name.get(parsed['name']) if parsed['name'] else None
        figures = []
        statement_src, found = replace_images(statement, resolve)
        figures += found
        solution_src, found = replace_images(solution_text(sol), resolve)
        figures += found
        existing_parts = []
        for i, sub in enumerate(parsed['subpoints']):
            sub, found = replace_images(sub, resolve)
            figures += found
            existing_parts.append((str(i + 1), sub))
        result = convert_for_import(
            statement=statement_src, answer='', solution=solution_src,
            existing_parts=existing_parts)
        out[key] = Record(key, result, result['warnings'], figures=figures)
    return out


#: slug → (человеческое имя источника, загрузчик сырья).
LOADERS = {
    'shkolkovo': ('Школково — банк задач по экономике', shkolkovo_records),
    'solvehub': ('SolveHub — банк задач по экономике', solvehub_records),
    'lesh': ('ЛЭШ 2026 — Гамма', lesh_records),
}
