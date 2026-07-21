# -*- coding: utf-8 -*-
"""
Свип подмен содержания по ВСЕМ 4 930 задачам июньского Батча 2 (применён
2026-07-04, `apply_batch2.py`). Тот же принцип, что и ревизия группы Б
(`batch2_unblock_sweep.py`, 95 задач, найдено 68 подмен) — но источник ДО
другой: там был JSON-бэкап конструктора применения, здесь готового снимка
нет — используется полный бэкап SQLite ПЕРЕД применением
(`backups/db_backup_before_batch2_apply.sqlite3`).

Задача 1 (реконструкция + покрытие): та же классификация, что
`apply_batch2._classify_record` использовал 2026-07-04 (stmt/parts_update
по совпадению меток), но db_problem берётся из БЭКАПА напрямую через
raw sqlite3 (не Django ORM — бэкапу не обязана соответствовать текущая
схема моделей, а нужны всего 2 таблицы по 3-4 колонки). Классификация
детерминирована: тот же вход даёт то же решение, что 2026-07-04, так что
ни один id из changed_problem_ids.txt не должен провалить bad_trim/
unknown_label заново — если проваливает, это аномалия реконструкции
(в отчёт, не в свип). Решения (`has_solution`, 1 097 задач) исключены
из сравнения намеренно — Sonnet писал их с нуля, «ДО» не существует.
Так же исключены `parts_create` (пункты, которых в ДО не было вовсе).

Задача 2 (свип): `sweep_field(ДО из бэкапа, ПОСЛЕ из текущей базы)` на
каждом покрытом поле. ПОСЛЕ — ТЕКУЩАЯ база, а не текст сразу после
Батча 2: между ними легли `fix_latex_junk` и `glue_pdf_lines` v1 — обе
проверены не трогать числа/знаки по построению (тесты, идемпотентность),
так что разница числовых/знаковых токенов по-прежнему однозначно
указывает на правку Sonnet, а не на более поздние проходы.

СТОП-УСЛОВИЕ: если digit_sign_change нашёлся более чем в STOP_RATIO
(40%) покрытых ЗАДАЧ (не полей) — вероятна ошибка детектора на
июньском формате текста, а не реальный масштаб подмен. Прогон
останавливается ПЕРЕД любым применением (даже с --confirm), пишет
превью 30 случайных срабатываний и отчёт, ничего не трогает в базе.

Задача 3 (откат, только --confirm и только если стоп-условие не
сработало): поле откатывается к ДО (бэкап), затем ПОВТОРНО прогоняется
через `fix_latex_junk.clean_text` и `glue_pdf_lines.glue_field`
(эквивалентно самим командам — они таргетируются по source/limit, не по
списку id) — иначе откат стёр бы июльскую механическую чистку вместе с
подменой. Контроль: пересвип (ДО-бэкап vs финальный записанный текст)
обязан быть 'same' — если чистка сама что-то поменяла в числах, это
баг чистки, а не эта команда.

Без --confirm — только измерение и отчёты, база не меняется.
"""
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple
import html
import json
import os
import random
import sqlite3

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from problems.batch2_unblock import apply_glue, sweep_field
from problems.management.commands.apply_batch2 import _is_suspicious_trim, _problem_id
from problems.management.commands.fix_latex_junk import SKIP_SHRINK_RATIO, clean_text
from problems.management.commands.glue_pdf_lines import _PREVIEW_TAIL, preview_head
from problems.management.commands.preview_batch2_unblock import diff_block
from problems.models import Problem, ProblemPart

OUT_DIR = "reports/batch2_sweep"
DEFAULT_BACKUP_DB = "backups/db_backup_before_batch2_apply.sqlite3"
DEFAULT_PARSED = "batch2_parsed.jsonl"
DEFAULT_IDS_FILE = "reports/batch2/changed_problem_ids.txt"
STOP_RATIO = 0.40
SQL_CHUNK = 400
PREVIEW_SEED = 2026
PREVIEW_N = 30


# ---------------------------------------------------------------------------
# Загрузка входных данных
# ---------------------------------------------------------------------------

def _load_parsed_by_id(path: str) -> Dict[int, Dict]:
    by_id = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            pid = _problem_id(rec["custom_id"])
            if pid is not None:
                by_id[pid] = rec
    return by_id


def _load_old_state(backup_path: str, ids: List[int]):
    """Читает problems_problem.statement и problems_problempart(id, label,
    statement) из бэкапа СЫРЫМ sqlite3 — бэкапу не обязана соответствовать
    текущая схема Django-моделей."""
    con = sqlite3.connect(backup_path)
    cur = con.cursor()
    old_stmt: Dict[int, str] = {}
    old_parts: Dict[int, List[Tuple[int, str, str]]] = defaultdict(list)
    for i in range(0, len(ids), SQL_CHUNK):
        chunk = ids[i:i + SQL_CHUNK]
        qmarks = ",".join("?" * len(chunk))
        cur.execute(
            "SELECT id, statement FROM problems_problem WHERE id IN ({})".format(qmarks),
            chunk)
        for pid, stmt in cur.fetchall():
            old_stmt[pid] = stmt or ""
        cur.execute(
            "SELECT id, problem_id, label, statement FROM problems_problempart "
            "WHERE problem_id IN ({})".format(qmarks), chunk)
        for pk, pid, label, stmt in cur.fetchall():
            old_parts[pid].append((pk, label, stmt or ""))
    con.close()
    return old_stmt, old_parts


# ---------------------------------------------------------------------------
# Задача 1: реконструкция классификации apply_batch2 против ДО
# ---------------------------------------------------------------------------

def _reconstruct_fields(pid, rec, old_stmt_map, old_parts_map):
    """Возвращает (fields, notes).
    fields — [{'kind': 'statement'|'part', 'pid', 'pk', 'label', 'old'}, ...]
    notes  — строки-причины (аномалии реконструкции ИЛИ легитимные
    исключения — solution/parts_create, ни у одной из них ДО не бывает)."""
    data = rec.get("data", {})
    notes: List[str] = []
    fields: List[Dict] = []

    if pid not in old_stmt_map:
        notes.append("not_in_old_backup")
        return fields, notes

    old_stmt = old_stmt_map[pid]
    cleaned_stmt = (data.get("cleaned_statement") or "").strip()
    if cleaned_stmt and cleaned_stmt != old_stmt.strip():
        if _is_suspicious_trim(old_stmt, cleaned_stmt):
            notes.append("anomaly_bad_trim_on_reclassify")
        else:
            fields.append({"kind": "statement", "pid": pid, "pk": None,
                           "label": None, "old": old_stmt})

    cleaned_parts = data.get("cleaned_parts") or {}
    if cleaned_parts and isinstance(cleaned_parts, dict):
        existing = old_parts_map.get(pid, [])
        by_label = {lbl: (pk, stmt) for pk, lbl, stmt in existing}
        model_labels = set(cleaned_parts.keys())
        existing_labels = set(by_label.keys())
        if not existing:
            notes.append("parts_create_no_do")
        else:
            unknown = model_labels - existing_labels
            if unknown:
                notes.append("anomaly_unknown_label_on_reclassify")
            else:
                for lbl, new_text in cleaned_parts.items():
                    pk, old_text = by_label[lbl]
                    if new_text.strip() != (old_text or "").strip():
                        fields.append({"kind": "part", "pid": pid, "pk": pk,
                                       "label": lbl, "old": old_text})

    if data.get("has_solution"):
        extracted = (data.get("extracted_solution") or "").strip()
        if extracted:
            notes.append("solution_extracted_excluded")

    return fields, notes


# ---------------------------------------------------------------------------
# Команда
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = ("Свип подмен содержания по всем 4930 задачам июньского Батча 2 "
            "(ДО из полного бэкапа sqlite). Без --confirm — только измерение.")

    def add_arguments(self, parser):
        parser.add_argument("--backup-db", default=DEFAULT_BACKUP_DB)
        parser.add_argument("--parsed", default=DEFAULT_PARSED)
        parser.add_argument("--ids-file", default=DEFAULT_IDS_FILE)
        parser.add_argument("--confirm", action="store_true",
                            help="Записать откаты + переприменённую чистку в базу.")

    def handle(self, *args, **opts):
        os.makedirs(OUT_DIR, exist_ok=True)
        backup_path = opts["backup_db"]
        parsed_path = opts["parsed"]
        ids_path = opts["ids_file"]
        confirm = opts["confirm"]

        if not os.path.exists(backup_path):
            raise CommandError("Бэкап не найден: {}".format(backup_path))
        if not os.path.exists(parsed_path):
            raise CommandError("Файл разбора не найден: {}".format(parsed_path))

        with open(ids_path, encoding="utf-8") as f:
            ids = [int(x) for x in f.read().split() if x.strip()]
        self.stdout.write("Задач в списке применённых Батча 2: {:,}".format(len(ids)))

        parsed = _load_parsed_by_id(parsed_path)
        missing_parsed = [pid for pid in ids if pid not in parsed]

        self.stdout.write("Читаю ДО из бэкапа {}…".format(backup_path))
        old_stmt_map, old_parts_map = _load_old_state(backup_path, ids)

        # ---- Задача 1: реконструкция ----
        all_fields: List[Dict] = []
        pid_notes: Dict[int, List[str]] = defaultdict(list)
        for pid in ids:
            rec = parsed.get(pid)
            if rec is None:
                pid_notes[pid].append("no_parsed_record")
                continue
            fields, notes = _reconstruct_fields(pid, rec, old_stmt_map, old_parts_map)
            pid_notes[pid].extend(notes)
            all_fields.extend(fields)

        anomalies = {pid: notes for pid, notes in pid_notes.items()
                    if any(n.startswith("anomaly_") for n in notes)}
        solution_only_pids = [
            pid for pid, notes in pid_notes.items()
            if "solution_extracted_excluded" in notes
            and not any(f["pid"] == pid for f in all_fields)
        ]
        parts_create_pids = [pid for pid, notes in pid_notes.items()
                             if "parts_create_no_do" in notes]
        solution_extracted_pids = [pid for pid, notes in pid_notes.items()
                                   if "solution_extracted_excluded" in notes]

        if anomalies:
            self.stdout.write(self.style.WARNING(
                "АНОМАЛИИ реконструкции (не совпало с оригинальным прогоном 2026-07-04): "
                "{}".format(len(anomalies))))

        # ---- Сверка с текущей базой ----
        stmt_pids = {f["pid"] for f in all_fields if f["kind"] == "statement"}
        part_field_pids = {f["pid"] for f in all_fields if f["kind"] == "part"}
        part_pks = {f["pk"] for f in all_fields if f["kind"] == "part"}
        all_pids = stmt_pids | part_field_pids

        problems = {p.pk: p for p in Problem.objects
                   .filter(pk__in=all_pids)
                   .prefetch_related("source_references__source")}
        parts = {p.pk: p for p in ProblemPart.objects.filter(pk__in=part_pks)}

        covered: List[Tuple[Dict, str]] = []
        uncovered: List[Tuple[Dict, str]] = []
        for f in all_fields:
            if f["kind"] == "statement":
                problem = problems.get(f["pid"])
                if problem is None:
                    uncovered.append((f, "problem_deleted_since"))
                    continue
                covered.append((f, problem.statement or ""))
            else:
                part = parts.get(f["pk"])
                if part is None:
                    uncovered.append((f, "part_deleted_since"))
                    continue
                covered.append((f, part.statement or ""))

        covered_pids = {f["pid"] for f, _ in covered}
        applied_total = len(ids)

        # ---- Задача 2: свип ----
        same = other = digit_n = new_sentence_n = 0
        digit_candidates: List[Dict] = []
        new_sentence_cards: List[Dict] = []
        by_source_digit_pids: Dict[str, set] = defaultdict(set)
        pid_has_digit: set = set()
        pid_has_new_sentence: set = set()

        def _source_name(problem) -> str:
            refs = list(problem.source_references.all())
            if refs:
                return refs[0].source.name
            return "Без источника"

        for f, current_text in covered:
            r = sweep_field(f["old"], current_text)
            if r["verdict"] == "same":
                same += 1
            elif r["verdict"] == "other":
                other += 1
            elif r["verdict"] == "digit_sign_change":
                digit_n += 1
                pid_has_digit.add(f["pid"])
                problem = problems.get(f["pid"])
                src = _source_name(problem) if problem else "Без источника"
                by_source_digit_pids[src].add(f["pid"])
                digit_candidates.append({**f, "current": current_text, "detail": r["detail"]})
            elif r["verdict"] == "new_sentence":
                new_sentence_n += 1
                pid_has_new_sentence.add(f["pid"])
                new_sentence_cards.append({**f, "current": current_text, "detail": r["detail"]})

        n_covered_pids = len(covered_pids)
        ratio = (len(pid_has_digit) / n_covered_pids) if n_covered_pids else 0.0

        visible_pids = set(Problem.objects.filter(
            status="published", needs_quality_review=False,
            pk__in=(pid_has_digit | pid_has_new_sentence),
        ).values_list("pk", flat=True))

        top5_sources = sorted(
            ((src, len(pids)) for src, pids in by_source_digit_pids.items()),
            key=lambda t: -t[1])[:5]

        stats = {
            "applied_total": applied_total,
            "missing_parsed": len(missing_parsed),
            "anomalies": len(anomalies),
            "solution_only_pids": len(solution_only_pids),
            "solution_extracted_pids": len(solution_extracted_pids),
            "parts_create_pids": len(parts_create_pids),
            "fields_total": len(all_fields),
            "fields_covered": len(covered),
            "fields_uncovered": len(uncovered),
            "problems_covered": n_covered_pids,
            "same": same, "other": other,
            "digit_n": digit_n, "new_sentence_n": new_sentence_n,
            "pid_has_digit": len(pid_has_digit),
            "pid_has_new_sentence": len(pid_has_new_sentence),
            "pid_new_sentence_only": len(pid_has_new_sentence - pid_has_digit),
            "pid_overlap": len(pid_has_digit & pid_has_new_sentence),
            "visible_digit": len(pid_has_digit & visible_pids),
            "visible_new_sentence": len(pid_has_new_sentence & visible_pids),
            "ratio": ratio,
            "top5_sources": top5_sources,
        }

        self._write_coverage_report(stats, uncovered, anomalies, pid_notes)
        self._write_sweep_stats(stats)
        self._write_digit_candidates_json(digit_candidates)
        self._write_new_sentence_json(new_sentence_cards)

        self.stdout.write("Покрыто задач: {:,} / {:,}".format(n_covered_pids, applied_total))
        self.stdout.write("digit_sign_change: {:,} задач ({:.1%} от покрытых)".format(
            len(pid_has_digit), ratio))
        self.stdout.write("new_sentence: {:,} задач".format(len(pid_has_new_sentence)))

        if ratio > STOP_RATIO:
            self.stdout.write(self.style.ERROR(
                "СТОП-УСЛОВИЕ: digit_sign_change в {:.1%} покрытых задач "
                "(порог {:.0%}). База НЕ тронута, даже если передан --confirm. "
                "Смотри reports/batch2_sweep/stop_preview.html.".format(
                    ratio, STOP_RATIO)))
            self._write_stop_preview(digit_candidates, problems)
            return

        if not confirm:
            self.stdout.write(
                "Режим измерения: база НЕ изменена. Для отката добавь --confirm.")
            return

        self.stdout.write("⚠️  Режим --confirm: откатываю {:,} полей.".format(
            len(digit_candidates)))
        self._apply_reverts(digit_candidates, problems, parts)

    # -----------------------------------------------------------------
    # Отчёты
    # -----------------------------------------------------------------

    def _write_coverage_report(self, stats, uncovered, anomalies, pid_notes):
        path = os.path.join(OUT_DIR, "coverage_report.md")
        lines = ["# Свип Батча 2 — покрытие «ДО» (Задача 1)", ""]
        lines.append("Применённых задач Батча 2 (2026-07-04): {:,}".format(
            stats["applied_total"]))
        lines.append("")
        lines.append("Полей-кандидатов к сравнению (statement + parts_update): {:,}".format(
            stats["fields_total"]))
        lines.append("  из них покрыто (ДО из бэкапа + ПОСЛЕ из текущей базы): {:,}".format(
            stats["fields_covered"]))
        lines.append("  из них непокрыто: {:,}".format(stats["fields_uncovered"]))
        lines.append("")
        lines.append("Исключены из сравнения (нет «ДО» по построению):")
        lines.append("  задачи только с вынесенным решением (has_solution, ДО не было): "
                     "{:,}".format(stats["solution_only_pids"]))
        lines.append("  всего задач с вынесенным решением (may overlap с др. правками): "
                     "{:,}".format(stats["solution_extracted_pids"]))
        lines.append("  задачи, где Sonnet СОЗДАЛ пункты с нуля (parts_create): "
                     "{:,}".format(stats["parts_create_pids"]))
        lines.append("")
        lines.append("Аномалии реконструкции (реклассификация разошлась с "
                     "прогоном 2026-07-04 — не должно быть): {:,}".format(
                         stats["anomalies"]))
        for pid, notes in list(anomalies.items())[:20]:
            lines.append("  #{}: {}".format(pid, notes))
        lines.append("")
        lines.append("Непокрытые поля (задача/пункт удалены из базы после "
                     "2026-07-04):")
        if not uncovered:
            lines.append("  пусто — все реконструированные поля покрыты.")
        for f, reason in uncovered[:50]:
            ident = f["pk"] if f["kind"] == "part" else f["pid"]
            lines.append("  {} {} (#{}): {}".format(f["kind"], ident, f["pid"], reason))
        if len(uncovered) > 50:
            lines.append("  … ещё {:,}".format(len(uncovered) - 50))
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        self.stdout.write("Отчёт покрытия → {}".format(path))

    def _write_sweep_stats(self, stats):
        path = os.path.join(OUT_DIR, "sweep_stats.md")
        lines = ["# Свип Батча 2 — замер (Задача 2)", ""]
        lines.append("Покрыто задач: {:,}".format(stats["problems_covered"]))
        lines.append("Покрыто полей: {:,} (same={:,}, other={:,}, "
                     "digit_sign_change={:,}, new_sentence={:,})".format(
                         stats["fields_covered"], stats["same"], stats["other"],
                         stats["digit_n"], stats["new_sentence_n"]))
        lines.append("")
        lines.append("Задач с хотя бы одной подменой числа/знака: {:,} "
                     "({:.1%} от покрытых, порог стоп-условия {:.0%})".format(
                         stats["pid_has_digit"], stats["ratio"], STOP_RATIO))
        lines.append("Задач с хотя бы одним восстановленным предложением: "
                     "{:,}".format(stats["pid_has_new_sentence"]))
        lines.append("  из них ТОЛЬКО новые предложения (без подмен): {:,}".format(
            stats["pid_new_sentence_only"]))
        lines.append("  пересечение (и подмена, и новое предложение в одной "
                     "задаче): {:,}".format(stats["pid_overlap"]))
        lines.append("")
        lines.append("Видимый пул (published, не зафлагован needs_quality_review):")
        lines.append("  с подменой чисел/знаков: {:,}".format(stats["visible_digit"]))
        lines.append("  с новым предложением: {:,}".format(stats["visible_new_sentence"]))
        lines.append("")
        lines.append("Топ-5 источников по числу задач с подменой:")
        if not stats["top5_sources"]:
            lines.append("  пусто.")
        for src, n in stats["top5_sources"]:
            lines.append("  {} — {:,}".format(src, n))
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        self.stdout.write("Отчёт замера → {}".format(path))

    def _write_digit_candidates_json(self, digit_candidates):
        path = os.path.join(OUT_DIR, "digit_sign_candidates.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(digit_candidates, f, ensure_ascii=False, indent=1)
        self.stdout.write("Кандидаты на откат → {} ({:,})".format(
            path, len(digit_candidates)))

    def _write_new_sentence_json(self, cards):
        path = os.path.join(OUT_DIR, "new_sentence_candidates.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cards, f, ensure_ascii=False, indent=1)
        self.stdout.write("Восстановленные предложения → {} ({:,})".format(
            path, len(cards)))

    def _write_stop_preview(self, digit_candidates, problems):
        path = os.path.join(OUT_DIR, "stop_preview.html")
        rng = random.Random(PREVIEW_SEED)
        sample = rng.sample(digit_candidates, min(PREVIEW_N, len(digit_candidates)))
        head = preview_head(
            "Свип Батча 2 — СТОП-УСЛОВИЕ сработало",
            "Свип Батча 2 — {} случайных срабатываний digit_sign_change".format(
                len(sample)),
            "Доля подмен превысила порог {:.0%} — возможна ошибка детектора "
            "на июньском формате. Ничего не откачено. Смотри карточки ниже "
            "и реши, применять ли автоматику дальше.".format(STOP_RATIO))
        out = [head]
        for i, c in enumerate(sample, start=1):
            problem = problems.get(c["pid"])
            title = html.escape(problem.title if problem else "")
            label = (" (Условие)" if c["kind"] == "statement"
                     else " (подп. [{}], pk={})".format(
                         html.escape(c["label"] or ""), c["pk"]))
            out.append(
                '<div class="card"><div class="meta"><b>№{num}</b> <b>#{pid}</b>'
                '{label} — {title}</div>{diff}</div>'.format(
                    num=i, pid=c["pid"], label=label, title=title,
                    diff=diff_block("Текст", c["old"], c["current"])))
        out.append(_PREVIEW_TAIL)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(out))
        self.stdout.write("Стоп-превью → {} ({} карточек)".format(path, len(sample)))

    # -----------------------------------------------------------------
    # Задача 3: откат + переприменение чистки
    # -----------------------------------------------------------------

    def _apply_reverts(self, digit_candidates, problems, parts):
        import datetime
        ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(OUT_DIR, "backup_revert_{}.json".format(ts))

        backup = {"statement": {}, "part": {}}
        stmt_updates: Dict[int, str] = {}
        part_updates: Dict[int, str] = {}
        shrink_guard_hits = []
        recheck_ok = 0
        fallback_glue_only = []   # clean_text само внесло подмену — откачено на glue-only
        fallback_raw = []         # даже glue внёс подмену — откачено на чистый ДО
        glue_not_idempotent = []

        for c in digit_candidates:
            old_backup_text = c["old"]
            current_text = c["current"]

            if c["kind"] == "statement":
                backup["statement"][str(c["pid"])] = current_text
            else:
                backup["part"][str(c["pk"])] = current_text

            # Попытка 1: полный конвейер (fix_latex_junk.clean_text → glue_field).
            # ВАЖНО: обе функции разрабатывались и проверялись на тексте,
            # который уже прошёл июньскую чистку Sonnet (более короткие,
            # разбитые на предложения абзацы). Здесь они впервые применяются
            # к СЫРОМУ до-Sonnet тексту — находка этого прогона (#4357):
            # junk_comment режет до ПЕРВОГО '\n' после '%', а в сыром тексте
            # (не прошедшем склейку) этот перенос может оказаться на сотни
            # символов дальше настоящей границы комментария, и паттерн
            # съедает реальный кусок условия. Три попытки по убыванию
            # чистки, каждая проверяется пересвипом против ДО — гарантия
            # «этот прогон никогда не вносит НОВУЮ подмену числа/знака»
            # важнее полноты июльской чистки на единичных проблемных полях.
            cleaned, applied_patterns, needs_manual = clean_text(old_backup_text)
            if old_backup_text and len(cleaned) < SKIP_SHRINK_RATIO * len(old_backup_text):
                cleaned = old_backup_text
                shrink_guard_hits.append((c["kind"], c.get("pk") or c["pid"]))
            candidate_1 = apply_glue(cleaned)
            recheck_1 = sweep_field(old_backup_text, candidate_1)

            if recheck_1["verdict"] != "digit_sign_change":
                final_text = candidate_1
                recheck_ok += 1
            else:
                # Попытка 2: без clean_text, только glue (склейка нарезки
                # числа/знаки не трогает по построению — но проверяем и её).
                candidate_2 = apply_glue(old_backup_text)
                recheck_2 = sweep_field(old_backup_text, candidate_2)
                if recheck_2["verdict"] != "digit_sign_change":
                    final_text = candidate_2
                    fallback_glue_only.append((c["kind"], c.get("pk") or c["pid"]))
                else:
                    # Попытка 3: гарантированно безопасный откат — сырой ДО
                    # без какой-либо переприменённой механики.
                    final_text = old_backup_text
                    fallback_raw.append((c["kind"], c.get("pk") or c["pid"]))

            # Контроль идемпотентности склейки на финальном тексте.
            glue_again = apply_glue(final_text)
            if glue_again != final_text:
                glue_not_idempotent.append((c["kind"], c.get("pk") or c["pid"]))

            if c["kind"] == "statement":
                stmt_updates[c["pid"]] = final_text
            else:
                part_updates[c["pk"]] = final_text

        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(backup, f, ensure_ascii=False, indent=1)
        self.stdout.write("Бэкап откатываемых текущих значений → {}".format(backup_path))

        to_save_problems = []
        for pid, text in stmt_updates.items():
            p = problems[pid]
            p.statement = text
            to_save_problems.append(p)
        to_save_parts = []
        for pk, text in part_updates.items():
            part = parts[pk]
            part.statement = text
            to_save_parts.append(part)

        with transaction.atomic():
            if to_save_problems:
                Problem.objects.bulk_update(to_save_problems, ["statement"], batch_size=200)
            if to_save_parts:
                ProblemPart.objects.bulk_update(to_save_parts, ["statement"], batch_size=200)

        affected_ids = sorted(
            set(stmt_updates.keys())
            | {parts[pk].problem_id for pk in part_updates})
        with open(os.path.join(OUT_DIR, "affected_problem_ids.txt"), "w",
                 encoding="utf-8") as f:
            f.write("\n".join(str(i) for i in affected_ids) + "\n")

        self._write_recleaning_report(
            recheck_ok, shrink_guard_hits, fallback_glue_only, fallback_raw,
            glue_not_idempotent)

        self.stdout.write(self.style.SUCCESS(
            "Откачено: {:,} statement, {:,} подпунктов. Затронуто задач: {:,}.".format(
                len(stmt_updates), len(part_updates), len(affected_ids))))
        self.stdout.write("Полный конвейер (clean_text+glue) прошёл пересвип: "
                          "{:,}".format(recheck_ok))
        self.stdout.write("Предохранитель fix_latex_junk сработал (shrink >50%): "
                          "{:,}".format(len(shrink_guard_hits)))
        if fallback_glue_only:
            self.stdout.write(self.style.WARNING(
                "ОТКАЧЕНО на glue-only (clean_text сам внёс подмену числа/знака): "
                "{:,} — {}".format(len(fallback_glue_only), fallback_glue_only[:10])))
        if fallback_raw:
            self.stdout.write(self.style.WARNING(
                "ОТКАЧЕНО на чистый ДО без переприменения (glue тоже внёс подмену): "
                "{:,} — {}".format(len(fallback_raw), fallback_raw[:10])))
        if not fallback_glue_only and not fallback_raw:
            self.stdout.write(
                "Гарантия «пересвип ДО-vs-финальный = 0 подмен» выполнена без откатов "
                "запасного уровня.")
        if glue_not_idempotent:
            self.stdout.write(self.style.WARNING(
                "ВНИМАНИЕ: glue_field не идемпотентна на {} финальных текстах: "
                "{}".format(len(glue_not_idempotent), glue_not_idempotent[:20])))
        else:
            self.stdout.write("Идемпотентность склейки на откаченных текстах подтверждена.")

    def _write_recleaning_report(self, recheck_ok, shrink_guard_hits,
                                 fallback_glue_only, fallback_raw,
                                 glue_not_idempotent):
        path = os.path.join(OUT_DIR, "recleaning_report.md")
        lines = ["# Свип Батча 2 — переприменение чистки поверх отката (Задача 3)", ""]
        lines.append(
            "Каждое откаченное поле проходит fix_latex_junk.clean_text и "
            "glue_pdf_lines.glue_field заново (иначе откат стёр бы июльскую "
            "механическую чистку). После КАЖДОЙ попытки — пересвип ДО-vs-"
            "финальный; попытка принимается, только если пересвип не находит "
            "digit_sign_change.")
        lines.append("")
        lines.append("Полный конвейер (clean_text + glue) принят: {:,}".format(recheck_ok))
        lines.append("  из них предохранитель fix_latex_junk (shrink >50%) "
                     "пропустил clean_text: {:,}".format(len(shrink_guard_hits)))
        lines.append("Откачено на glue-only (clean_text сам внёс подмену "
                     "числа/знака — находка этого прогона, #4357 и похожие: "
                     "junk_comment режет до первого '\\n' после '%', в сыром "
                     "до-склейки тексте это может утащить абзацы реального "
                     "условия): {:,}".format(len(fallback_glue_only)))
        for kind, ident in fallback_glue_only[:100]:
            lines.append("  {} {}".format(kind, ident))
        lines.append("")
        lines.append("Откачено на чистый ДО без переприменения (glue тоже "
                     "внёс подмену): {:,}".format(len(fallback_raw)))
        for kind, ident in fallback_raw[:100]:
            lines.append("  {} {}".format(kind, ident))
        lines.append("")
        lines.append("Не идемпотентна склейка на финальном тексте (требует "
                     "внимания отдельно): {:,}".format(len(glue_not_idempotent)))
        for kind, ident in glue_not_idempotent[:50]:
            lines.append("  {} {}".format(kind, ident))
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        self.stdout.write("Отчёт переприменения чистки → {}".format(path))
