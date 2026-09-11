# -*- coding: utf-8 -*-
"""Провенанс эмбеддингов (С13) — честный backfill учётных полей и защита текстов.

Поля `embedding_version` / `embedding_model_build` / `embedding_source_hash` /
`embedding_built_at` завела сессия С5 (миграция 0044), но НЕ заполнила: у
31 694 существующих векторов все четыре пусты. Здесь — значения, которыми их
честно заполнить задним числом, и отпечаток, которым сессия доказывает, что
не тронула тексты задач.

⚠️ **Почему `embedding_source_hash` остаётся пустым, а не считается по тексту.**
Соблазн посчитать MD5 текущего текста велик: поле заполнится, `--stale`
заработает «правильно». Но исторического текста, на котором вектор реально
считали 04.07.2026, у нас нет. Хеш текущего текста утверждал бы «вектор
соответствует этому тексту» — и был бы ЛОЖЬЮ ровно для тех задач, чей текст
правили ПОСЛЕ пересчёта (aa_fixed 22.08, фикс-пак МатЭк 27.08). То есть соврал
бы в сторону «всё актуально» именно про те задачи, ради которых диагностика и
затевалась. Пустая строка — «провенанс неизвестен» — оставляет вектор
устаревшим, и это честная сторона ошибки.
"""
import hashlib
from datetime import datetime, timezone as dt_timezone

from problems.embedding_config import EMBEDDING_MODEL_BUILD

# Дата последнего известного массового пересчёта на BGE-M3.
# Источник: CLAUDE_ARCHIVE.md «Финал пайплайна: отпечаток + полный пересчёт
# BGE-M3 — СДЕЛАН (2026-07-04)», коммит 2ec03e0 (2026-07-04), лог
# reports/recompute_2026-07/recompute.log — 31 472 вектора, пропущено 0.
#
# ⚠️ 218 задач ВсОШ-регион пересчитаны позже, 2026-07-13 (пере-импорт).
# Ставим всем единую раннюю дату сознательно: она ошибается только в сторону
# «вектор старее, чем на самом деле», то есть может пометить лишнее как
# устаревшее, но никогда не объявит устаревший вектор свежим. Обратный выбор
# был бы небезопасен. На числа Фазы 1 это не влияет: все текстовые правки,
# которые мы ищем, сделаны в августе — позже обеих дат.
LEGACY_BUILT_AT = datetime(2026, 7, 4, 0, 0, tzinfo=dt_timezone.utc)

# Легаси-метка версии формулы. НЕ настоящая версия: формулы v2 ещё не было,
# а чем считали в июле — константами не зафиксировано. Ноль отличается от
# любой боевой EMBEDDING_FORMULA_VERSION (она >= 1), поэтому is_stale()
# продолжает считать такие векторы устаревшими. Это и есть цель: провенанс
# неизвестен — значит, доверия нет.
LEGACY_FORMULA_VERSION = 0

# Сборка модели на момент пересчёта. fp32, не int8: переезд в отдельный
# контейнер (С4) снял потребность в квантизации — docs/adr/0015.
LEGACY_MODEL_BUILD = EMBEDDING_MODEL_BUILD

# Поля, которые этой сессии запрещено менять у любой задачи.
PROTECTED_FIELDS = (
    'statement', 'solution', 'answer',
    'embedding', 'content_format', 'human_review',
)

# ⚠️ То же самое БЕЗ `embedding` — для команд, чья работа и есть запись
# вектора (`embeddings_import_vectors`). Полный список там неприменим: свип
# краснел бы всегда, а сторож, который краснеет всегда, перестают читать.
# Защищать при ввозе надо ровно тексты: вектор меняется по определению,
# условие, решение и ответ не смеют измениться ни у одной задачи.
TEXT_PROTECTED_FIELDS = tuple(f for f in PROTECTED_FIELDS if f != 'embedding')

_SEP_FIELD = b'\x1f'
_SEP_ROW = b'\x1e'


def protected_fingerprint(queryset, fields=PROTECTED_FIELDS):
    """MD5 по защищённым полям набора — свидетельство «тексты не тронуты».

    `fields` по умолчанию — весь `PROTECTED_FIELDS`. Команде, которая пишет
    вектор осознанно, передают `TEXT_PROTECTED_FIELDS`: иначе свип краснеет
    на собственной работе команды.

    ⚠️ `embedding` — BinaryField, и он отдаёт `memoryview`, а не `bytes`
    (ловушка описана в docs/EMBEDDINGS.md). Приводим явно, иначе отпечаток
    зависел бы от типа обёртки, а не от содержимого.
    """
    digest = hashlib.md5(usedforsecurity=False)
    rows = queryset.order_by('pk').values_list('pk', *fields)
    for row in rows.iterator(chunk_size=2000):
        for value in row:
            if isinstance(value, memoryview):
                value = bytes(value)
            digest.update(value if isinstance(value, bytes) else str(value).encode())
            digest.update(_SEP_FIELD)
        digest.update(_SEP_ROW)
    return digest.hexdigest()


def legacy_values(has_embedding):
    """Четыре учётных поля для задачи, чей вектор посчитан до версионирования.

    Задача без вектора получает все четыре пустыми: заполнять их значило бы
    утверждать, что расчёт был.
    """
    if not has_embedding:
        return {
            'embedding_version': None,
            'embedding_model_build': '',
            'embedding_source_hash': '',
            'embedding_built_at': None,
        }
    return {
        'embedding_version': LEGACY_FORMULA_VERSION,
        'embedding_model_build': LEGACY_MODEL_BUILD,
        # Пусто намеренно — см. предупреждение в шапке модуля.
        'embedding_source_hash': '',
        'embedding_built_at': LEGACY_BUILT_AT,
    }


def apply_log_problem_ids(log):
    """id ЗАДАЧ из журнала применения правок.

    ⚠️ Журнал адресует правки к двум таблицам. У строки `problems_problempart`
    поле `id` — это pk подпункта, а задача лежит в `problem_id`. Наивный разбор
    по одному `id` завышает охват (в журнале АА: 151 «задача» вместо 94) и
    приписывает правки задачам с номерами подпунктов.
    """
    ids = set()
    for entry in log:
        raw = entry.get('problem_id') if entry.get('table') == 'problems_problempart' else entry.get('id')
        if raw is not None:
            ids.add(int(raw))
    return ids


def stale_after(edited_at, built_at):
    """Устарел ли вектор: текст правили позже, чем считали вектор.

    `built_at is None` — вектора нет вовсе. Это отдельная категория
    («никогда не считали»), а не устаревание, и смешивать их нельзя.
    """
    if built_at is None:
        return False
    return edited_at > built_at
