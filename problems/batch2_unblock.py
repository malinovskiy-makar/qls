# -*- coding: utf-8 -*-
"""
Разблокировка группы Б: заблокированные правки Батча 2 (250 задач).

Общая библиотека для конструктора-превью (`preview_batch2_unblock`) и
будущей команды применения (следующая сессия, после стоп-гейта Макара) —
чтобы превью и применение не разошлись логикой, как учит опыт склейки
нарезки (`glue_pdf_lines.preview_head`).

Контекст: при применении Батча 2 (2026-07-04, `apply_batch2.py`) фильтры
заблокировали готовые (уже оплаченные) правки Sonnet для 250 задач —
конфликт решения (118), неизвестная метка подпункта (106), подозрительное
сокращение условия >80% (26). Правки лежат в `batch2_parsed.jsonl`.
Группу `missing_figure`/`truncated` (1 772) эта библиотека НЕ трогает.

КРИТИЧНО: правки Sonnet сделаны ДО склейки построчной нарезки
(`glue_pdf_lines`, применена 2026-07-19). Конвейер для каждого поля:
    текст Sonnet → glue_field() → финальный текст.
Один проход apply_glue() ничего не портит на уже опрятном тексте — glue_field
не находит \\n и возвращает исходный текст без изменений (проверено
идемпотентностью glue_pdf_lines).

Переоценка, а не слепое доверие: `apply_batch2.py` проверял поля
ПОСЛЕДОВАТЕЛЬНО (statement → parts → solution) и останавливался на первом
блокере — так что «неизвестная метка» ничего не знает о состоянии solution
у той же записи, а «конфликт решения» видел statement/parts ТОГДАШНЕЙ базы
(2026-07-04), которая с тех пор могла измениться (в первую очередь — склейкой
нарезки). Поэтому здесь всё перепроверяется заново против ТЕКУЩЕЙ базы.

Маппинг меток подпунктов — по содержанию, не по написанию. Ревью реальных
случаев показало, что Sonnet путает латиницу/кириллицу («b»/«б»/«в»/«с» вперемешку)
и не для каждой задачи трогает все пункты (`cleaned_parts` — заплатка, только
изменённые). Один существующий испорченный ярлык в базе («Ь» вместо «б» —
находка ревью) довершает путаницу. Побуквенное сопоставление ненадёжно;
пункты сопоставляются по СХОДСТВУ ТЕКСТА (`difflib.SequenceMatcher`) —
предложение Sonnet почти всегда пересекается с текстом ИМЕННО того пункта,
который оно чистит. Жадное паросочетание, разрешается только когда КАЖДАЯ
модельная запись получила уникальный уверенный (`MIN_LABEL_SCORE`) и
монотонный по порядку пункт — иначе вся задача в остаток («порядок спорный»/
«число подпунктов не совпало» — ловит и расщепление пункта надвое, и
пропущенный в базе пункт, реальные случаи ревью #49939/#50130).
"""
from typing import Dict, List, Optional, Tuple
import difflib

from problems.management.commands.apply_batch2 import _is_suspicious_trim
from problems.management.commands.glue_pdf_lines import glue_field

MIN_LABEL_SCORE = 0.55


def apply_glue(text):
    # type: (str) -> str
    """Sonnet текст → glue_field(). Не применяет результат, если сработал
    предохранитель (тексту Sonnet это не грозит, но конвейер обязан вести
    себя так же осторожно, как боевая команда)."""
    if not text:
        return text
    res = glue_field(text)
    if res.new_text is None or res.borderline:
        return text
    return res.new_text


def _text_sim(a, b):
    # type: (str, str) -> float
    a = (a or '').strip().lower()
    b = (b or '').strip().lower()
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def match_parts_by_content(existing, cleaned_parts):
    # type: (List[Tuple[int, str, str]], Dict[str, str]) -> Optional[Dict[int, str]]
    """existing — [(pk, label, текущий_текст), ...] в истинном порядке
    (Meta.ordering = order, label). cleaned_parts — {метка_Sonnet: новый
    текст} в порядке JSON (== порядок, в котором Sonnet шёл по пунктам).

    Жадно сопоставляет каждую запись Sonnet с существующим пунктом по
    сходству текста (не по метке — метки как раз и есть проблема).
    Возвращает {pk: новый_текст} ТОЛЬКО если сопоставление однозначно:
    каждая запись Sonnet получила своего уникального адресата с оценкой
    >= MIN_LABEL_SCORE, и порядок адресатов монотонен (совпадает с
    порядком, в котором Sonnet вернул записи) — иначе None (в остаток).
    """
    model_items = list(cleaned_parts.items())
    if not model_items or not existing:
        return None

    pairs = []
    for mi, (_, new_text) in enumerate(model_items):
        for ei, (_, _, old_text) in enumerate(existing):
            pairs.append((_text_sim(old_text, new_text), mi, ei))
    pairs.sort(key=lambda t: -t[0])

    used_m, used_e = set(), set()
    assign = {}  # mi -> (ei, score)
    for score, mi, ei in pairs:
        if mi in used_m or ei in used_e:
            continue
        assign[mi] = (ei, score)
        used_m.add(mi)
        used_e.add(ei)

    if len(assign) < len(model_items):
        return None  # хотя бы одна запись Sonnet осталась без адресата
    if any(assign[mi][1] < MIN_LABEL_SCORE for mi in range(len(model_items))):
        return None  # неуверенное сопоставление

    ei_seq = [assign[mi][0] for mi in range(len(model_items))]
    if ei_seq != sorted(ei_seq) or len(set(ei_seq)) != len(ei_seq):
        return None  # порядок спорный / задвоение

    return {
        existing[assign[mi][0]][0]: new_text
        for mi, (_, new_text) in enumerate(model_items)
    }


def classify_conflict_solution(problem, rec):
    # type: (object, Dict) -> Dict
    """Задача 2: solution НИКОГДА не трогаем. Statement/подпункты —
    заново проверяем против ТЕКУЩЕЙ базы (могла измениться со склейки).
    Извлечённое решение Sonnet — только в лог, не в базу."""
    data = rec.get('data', {})
    reasons = []
    changes = {}  # 'stmt_raw' | 'parts_raw' (pk -> text)

    cur_stmt = problem.statement or ''
    cleaned_stmt = (data.get('cleaned_statement') or '').strip()
    if cleaned_stmt and cleaned_stmt != cur_stmt.strip():
        if _is_suspicious_trim(cur_stmt, cleaned_stmt):
            reasons.append('stmt_suspicious_trim_vs_current')
        else:
            changes['stmt_raw'] = cleaned_stmt

    cleaned_parts = data.get('cleaned_parts') or {}
    if cleaned_parts:
        existing = [(p.pk, p.label, p.statement or '') for p in problem.parts.all()]
        existing_labels = {e[1] for e in existing}
        model_labels = set(cleaned_parts.keys())
        if model_labels - existing_labels:
            match = match_parts_by_content(existing, cleaned_parts)
            if match is None:
                reasons.append('parts_ambiguous_vs_current')
            else:
                changes['parts_raw'] = match
        else:
            by_label = {e[1]: e for e in existing}
            upd = {}
            for lbl, txt in cleaned_parts.items():
                pk, _, old = by_label[lbl]
                if txt.strip() != (old or '').strip():
                    upd[pk] = txt
            if upd:
                changes['parts_raw'] = upd

    extracted_solution = ''
    if data.get('has_solution'):
        extracted_solution = (data.get('extracted_solution') or '').strip()

    if reasons:
        return {'apply': False, 'reasons': reasons, 'changes': {},
                'extracted_solution': extracted_solution}
    if not changes:
        return {'apply': False, 'reasons': ['no_net_change_besides_solution'],
                'changes': {}, 'extracted_solution': extracted_solution}
    return {'apply': True, 'reasons': [], 'changes': changes,
            'extracted_solution': extracted_solution}


def classify_unknown_label(problem, rec):
    # type: (object, Dict) -> Dict
    """Задача 3: детерминированный маппинг меток по содержанию. Заодно
    честно проверяет statement (мог быть тоже испорчен) и solution (не
    проверялось в исходном прогоне — parts блокировали раньше)."""
    data = rec.get('data', {})
    reasons = []
    changes = {}

    cleaned_parts = data.get('cleaned_parts') or {}
    existing = [(p.pk, p.label, p.statement or '') for p in problem.parts.all()]
    match = match_parts_by_content(existing, cleaned_parts) if cleaned_parts else None
    if cleaned_parts and match is None:
        reasons.append('parts_ambiguous')
    elif match:
        changes['parts_raw'] = match

    cur_stmt = problem.statement or ''
    cleaned_stmt = (data.get('cleaned_statement') or '').strip()
    if cleaned_stmt and cleaned_stmt != cur_stmt.strip():
        if _is_suspicious_trim(cur_stmt, cleaned_stmt):
            reasons.append('stmt_suspicious_trim_vs_current')
        else:
            changes['stmt_raw'] = cleaned_stmt

    extracted_solution = ''
    if data.get('has_solution'):
        extracted = (data.get('extracted_solution') or '').strip()
        if extracted:
            existing_solution = (problem.solution or '').strip()
            if existing_solution:
                extracted_solution = extracted  # конфликт — только в лог
            else:
                changes['solution_raw'] = extracted  # свободно — та же логика apply_batch2

    if reasons:
        return {'apply': False, 'reasons': reasons, 'changes': {},
                'extracted_solution': extracted_solution}
    if not changes:
        return {'apply': False, 'reasons': ['no_net_change'],
                'changes': {}, 'extracted_solution': extracted_solution}
    return {'apply': True, 'reasons': [], 'changes': changes,
            'extracted_solution': extracted_solution}


def classify_bad_trim(problem, rec):
    # type: (object, Dict) -> Dict
    """Задача 4: без автоматики — только диагностика для поштучного
    вердикта Макара в превью."""
    data = rec.get('data', {})
    cur_stmt = problem.statement or ''
    cleaned_stmt = (data.get('cleaned_statement') or '').strip()
    old_len = len(cur_stmt)
    new_len = len(cleaned_stmt)
    shrink_pct = round(100.0 * (1 - new_len / old_len), 1) if old_len else 0.0

    notes = []
    if old_len < 50:
        notes.append('current_statement_very_short')  # находка ревью, #30402

    return {
        'apply': False,
        'reasons': ['manual_review_required'],
        'changes': {'stmt_raw': cleaned_stmt} if cleaned_stmt else {},
        'shrink_pct': shrink_pct,
        'old_len': old_len,
        'new_len': new_len,
        'notes': notes,
    }


def pipeline_changes(changes):
    # type: (Dict) -> Dict
    """changes с сырым текстом Sonnet ('stmt_raw'/'parts_raw'/'solution_raw')
    → тот же словарь, но текст прогнан через glue_field (кроме solution —
    в v1 glue_pdf_lines его не обрабатывает, см. докстринг там же)."""
    out = {}
    if 'stmt_raw' in changes:
        out['stmt'] = apply_glue(changes['stmt_raw'])
    if 'parts_raw' in changes:
        out['parts'] = {pk: apply_glue(txt) for pk, txt in changes['parts_raw'].items()}
    if 'solution_raw' in changes:
        out['solution'] = changes['solution_raw']
    return out
