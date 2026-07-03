"""
Применить результаты Батча 2 (чистка текста + вынос решений) из batch2_parsed.jsonl.

Два режима:
  Без аргументов — ПРЕДПРОСМОТР: ничего не пишет в базу, создаёт:
    reports/batch2/preview_summary.md   — сводка по типам правок и причинам пропуска
    reports/batch2/preview_apply.html   — стратифицированная выборка «БЫЛО / СТАНЕТ»

  --confirm — ЗАПИСЬ в базу:
    Перед записью делает бэкап db.sqlite3 → backups/db_backup_before_batch2_apply.sqlite3
    Пишет батчами по 500 в транзакциях.
    Создаёт:
      reports/batch2/apply_report.md
      reports/batch2/skipped_flagged.txt
      reports/batch2/skipped_conflict_solution.txt
      reports/batch2/skipped_conflict_parts.txt
      reports/batch2/skipped_bad_trim.txt
      reports/batch2/skipped_not_found.txt
      reports/batch2/changed_problem_ids.txt   (для пересчёта эмбеддингов)
"""
from typing import Optional, List, Tuple, Dict, Any
import html
import json
import os
import random
import shutil

from django.core.management.base import BaseCommand
from django.db import transaction

from problems.models import Problem, ProblemPart

PARSED_FILE = "batch2_parsed.jsonl"
REPORT_DIR = "reports/batch2"
BACKUP_PATH = "backups/db_backup_before_batch2_apply.sqlite3"
DB_PATH = "db.sqlite3"

# Зафиксированный seed для воспроизводимой выборки предпросмотра.
PREVIEW_SEED = 42
PREVIEW_STMT = 20   # задач с чисткой условия
PREVIEW_SOL = 15    # задач с вынесенным решением
PREVIEW_PARTS = 15  # задач с переписанными подпунктами

BATCH_SIZE = 500


def _load_parsed(path: str) -> List[Dict]:
    records = []
    if not os.path.exists(path):
        return records
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _problem_id(custom_id: str) -> Optional[int]:
    """'p12345' → 12345; None при ошибке."""
    s = custom_id.lstrip("p")
    try:
        return int(s)
    except ValueError:
        return None


def _is_suspicious_trim(old: str, new: str) -> bool:
    """Очищенное условие пустое или короче 20% оригинала → брак."""
    if not new.strip():
        return True
    if len(old) > 0 and len(new) < 0.20 * len(old):
        return True
    return False


def _classify_record(rec: Dict, db_problem: Optional[Problem]) -> Dict[str, Any]:
    """
    Возвращает словарь с полями:
      skip: bool
      skip_reason: str (если skip)
      changes: dict  — какие правки будут применены
        - stmt: новое условие (str) или None
        - parts_update: {label: text} для обновления
        - parts_create: {label: text} для создания новых ProblemPart
        - parts_delete: [label] для удаления
        - solution: extracted text (str) или None
    """
    data = rec.get("data", {})
    flags = data.get("flags", [])
    custom_id = rec["custom_id"]

    if flags:
        return {"skip": True, "skip_reason": f"flags:{','.join(flags)}", "changes": {}}

    if db_problem is None:
        return {"skip": True, "skip_reason": "not_found", "changes": {}}

    if db_problem.multiple_problems:
        return {"skip": True, "skip_reason": "multiple_problems", "changes": {}}

    changes: Dict[str, Any] = {}

    # --- Условие ---
    cleaned_stmt = (data.get("cleaned_statement") or "").strip()
    if cleaned_stmt and cleaned_stmt != (db_problem.statement or "").strip():
        if _is_suspicious_trim(db_problem.statement or "", cleaned_stmt):
            return {"skip": True, "skip_reason": "bad_trim", "changes": {}}
        changes["stmt"] = cleaned_stmt

    # --- Подпункты ---
    cleaned_parts: Dict[str, str] = data.get("cleaned_parts") or {}
    if cleaned_parts and isinstance(cleaned_parts, dict):
        existing_parts = list(db_problem.parts.all())
        existing_by_label = {p.label: p for p in existing_parts}
        existing_labels = set(existing_by_label.keys())
        model_labels = set(cleaned_parts.keys())

        if existing_labels == model_labels:
            # Наборы меток совпадают — просто обновляем тексты.
            parts_update = {}
            for lbl, new_text in cleaned_parts.items():
                if new_text.strip() != (existing_by_label[lbl].statement or "").strip():
                    parts_update[lbl] = new_text
            if parts_update:
                changes["parts_update"] = parts_update
        elif existing_parts:
            # Наборы различаются — проверяем, безопасно ли принять разметку модели.
            has_answers = any(
                (p.answer or "").strip() or p.points is not None
                for p in existing_parts
            )
            if has_answers:
                return {"skip": True, "skip_reason": "conflict_parts", "changes": {}}
            # Безопасно: принимаем разметку модели целиком.
            parts_update = {}
            parts_create = {}
            parts_delete = []
            for lbl, new_text in cleaned_parts.items():
                if lbl in existing_by_label:
                    old_text = (existing_by_label[lbl].statement or "").strip()
                    if new_text.strip() != old_text:
                        parts_update[lbl] = new_text
                else:
                    parts_create[lbl] = new_text
            for lbl in existing_labels:
                if lbl not in model_labels:
                    parts_delete.append(lbl)
            if parts_update:
                changes["parts_update"] = parts_update
            if parts_create:
                changes["parts_create"] = parts_create
            if parts_delete:
                changes["parts_delete"] = parts_delete
        else:
            # Подпунктов в базе нет, модель нашла — создаём.
            changes["parts_create"] = dict(cleaned_parts)

    # --- Решение ---
    if data.get("has_solution"):
        extracted = (data.get("extracted_solution") or "").strip()
        if extracted:
            existing_solution = (db_problem.solution or "").strip()
            if existing_solution:
                return {"skip": True, "skip_reason": "conflict_solution", "changes": {}}
            changes["solution"] = extracted

    if not changes:
        return {"skip": False, "skip_reason": "", "changes": {}}

    return {"skip": False, "skip_reason": "", "changes": changes}


def _apply_changes_to_problem(problem: Problem, changes: Dict) -> List[str]:
    """Применяет изменения к объекту Problem и его ProblemPart.
    Возвращает список типов применённых правок."""
    applied = []

    if "stmt" in changes:
        problem.statement = changes["stmt"]
        applied.append("stmt")

    if "solution" in changes:
        problem.solution = changes["solution"]
        problem.solution_ai_extracted = True
        applied.append("solution")

    # Для подпунктов: update + create + delete.
    parts_update = changes.get("parts_update", {})
    parts_create = changes.get("parts_create", {})
    parts_delete = changes.get("parts_delete", [])

    if parts_update:
        by_label = {p.label: p for p in problem.parts.all()}
        bulk = []
        for lbl, new_text in parts_update.items():
            if lbl in by_label:
                by_label[lbl].statement = new_text
                bulk.append(by_label[lbl])
        if bulk:
            ProblemPart.objects.bulk_update(bulk, ["statement"])
        applied.append("parts_update")

    if parts_delete:
        problem.parts.filter(label__in=parts_delete).delete()
        applied.append("parts_delete")

    if parts_create:
        existing_labels = set(problem.parts.values_list("label", flat=True))
        new_parts = []
        for idx, (lbl, text) in enumerate(parts_create.items()):
            if lbl not in existing_labels:
                new_parts.append(ProblemPart(
                    problem=problem,
                    label=lbl,
                    statement=text,
                    answer="",
                    order=1000 + idx,
                ))
        if new_parts:
            ProblemPart.objects.bulk_create(new_parts)
        applied.append("parts_create")

    return applied


# ---------------------------------------------------------------------------
# HTML-предпросмотр
# ---------------------------------------------------------------------------

def _html_escape(text: str) -> str:
    return html.escape(text or "")


def _problem_row(pid: int, problem: Problem, changes: Dict, section: str) -> str:
    """Генерирует HTML-блок для одной задачи в предпросмотре."""
    title = html.escape(problem.title or f"Задача #{pid}")

    rows = []

    # Условие
    if "stmt" in changes:
        rows.append(_diff_row(
            "Условие",
            problem.statement or "",
            changes["stmt"],
        ))
    elif section == "stmt":
        rows.append(_diff_row("Условие", problem.statement or "", problem.statement or ""))

    # Подпункты
    parts_update = changes.get("parts_update", {})
    parts_create = changes.get("parts_create", {})
    parts_delete = changes.get("parts_delete", [])
    by_label = {p.label: p for p in problem.parts.all()}

    if parts_update or parts_create or parts_delete or section == "parts":
        for lbl in sorted(by_label.keys()):
            if lbl in parts_update:
                rows.append(_diff_row(
                    f"Подп. [{lbl}]",
                    by_label[lbl].statement or "",
                    parts_update[lbl],
                ))
            elif section == "parts":
                rows.append(_diff_row(
                    f"Подп. [{lbl}]",
                    by_label[lbl].statement or "",
                    by_label[lbl].statement or "",
                ))
        for lbl in sorted(parts_create.keys()):
            rows.append(_diff_row(f"Подп. [{lbl}] (новый)", "", parts_create[lbl]))
        for lbl in sorted(parts_delete):
            rows.append(_diff_row(f"Подп. [{lbl}] (удаление)", by_label.get(lbl, None) and by_label[lbl].statement or "", "❌ УДАЛЁН"))

    # Решение
    if "solution" in changes:
        rows.append(_diff_row(
            "Решение (извлечено)",
            problem.solution or "(пусто)",
            changes["solution"],
        ))
    elif section == "solution":
        rows.append(_diff_row(
            "Решение (извлечено)",
            problem.solution or "(пусто)",
            "— (будет добавлено)",
        ))

    rows_html = "\n".join(rows)
    return f"""
<div class="card">
  <div class="card-header">
    <span class="pid">#{pid}</span>
    <span class="title">{title}</span>
    <span class="section-tag">{section}</span>
  </div>
  <table class="diff-table">
    <thead><tr><th>Поле</th><th>БЫЛО</th><th>СТАНЕТ</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
</div>"""


def _diff_row(label: str, old: str, new: str) -> str:
    changed = old.strip() != new.strip()
    cls = "changed" if changed else ""
    return f"""<tr class="{cls}">
      <td class="field-name">{html.escape(label)}</td>
      <td><pre class="pre-wrap">{html.escape(old)}</pre></td>
      <td><pre class="pre-wrap">{html.escape(new)}</pre></td>
    </tr>"""


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Батч 2 — предпросмотр применения</title>
<style>
  body {{ font-family: sans-serif; font-size: 13px; background: #f5f5f5; margin: 0; padding: 16px; }}
  h1 {{ font-size: 18px; }}
  h2 {{ font-size: 15px; margin-top: 32px; border-bottom: 2px solid #ccc; padding-bottom: 4px; }}
  .card {{ background: #fff; border: 1px solid #ddd; border-radius: 6px; margin: 12px 0; padding: 12px; }}
  .card-header {{ margin-bottom: 8px; }}
  .pid {{ font-weight: bold; color: #555; margin-right: 8px; }}
  .title {{ font-weight: bold; }}
  .section-tag {{ float: right; background: #e0e7ff; color: #3730a3; border-radius: 4px; padding: 1px 7px; font-size: 11px; }}
  .diff-table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
  .diff-table th {{ background: #f0f0f0; padding: 4px 8px; text-align: left; width: 12%; }}
  .diff-table th:nth-child(2), .diff-table th:nth-child(3) {{ width: 44%; }}
  .diff-table td {{ padding: 4px 8px; border-top: 1px solid #eee; vertical-align: top; }}
  .diff-table tr.changed td {{ background: #fffbeb; }}
  .field-name {{ font-weight: bold; color: #555; font-size: 11px; white-space: nowrap; }}
  .pre-wrap {{ white-space: pre-wrap; word-break: break-word; margin: 0; font-family: monospace; font-size: 12px; }}
  .summary {{ background: #fff; border: 1px solid #ccc; border-radius: 6px; padding: 16px; margin-bottom: 24px; }}
  .summary pre {{ margin: 0; font-size: 13px; }}
</style>
</head>
<body>
<h1>Батч 2 — предпросмотр применения</h1>
<div class="summary"><pre>{summary}</pre></div>

<h2>Раздел 1: задачи с чисткой условия (~{n_stmt} из выборки)</h2>
{section_stmt}

<h2>Раздел 2: задачи с вынесенным решением (~{n_sol} из выборки)</h2>
{section_sol}

<h2>Раздел 3: задачи с переписанными подпунктами (~{n_parts} из выборки)</h2>
{section_parts}
</body>
</html>"""


class Command(BaseCommand):
    help = (
        "Применить Батч 2 (чистка текста + вынос решений). "
        "Без --confirm — только предпросмотр, в базу не пишет."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm", action="store_true",
            help="Записать изменения в базу (по умолчанию только предпросмотр).",
        )
        parser.add_argument(
            "--input", type=str, default=PARSED_FILE,
            help=f"Путь к разобранному файлу (по умолчанию {PARSED_FILE}).",
        )

    def handle(self, *args, **opts):
        confirm = opts["confirm"]
        input_path = opts["input"]

        os.makedirs(REPORT_DIR, exist_ok=True)

        self.stdout.write(f"Читаю {input_path}…")
        records = _load_parsed(input_path)
        if not records:
            self.stderr.write(f"❌ Файл {input_path} не найден или пуст.")
            return
        self.stdout.write(f"  Загружено {len(records):,} записей.")

        # Подгружаем все задачи одним запросом.
        self.stdout.write("Подгружаю задачи из базы…")
        all_ids = []
        for rec in records:
            pid = _problem_id(rec["custom_id"])
            if pid is not None:
                all_ids.append(pid)

        problems_qs = (
            Problem.objects
            .filter(pk__in=all_ids)
            .prefetch_related("parts")
        )
        problems_map: Dict[int, Problem] = {p.pk: p for p in problems_qs}
        self.stdout.write(f"  Найдено в базе: {len(problems_map):,} из {len(all_ids):,}.")

        # Классифицируем каждую запись.
        classified = []  # (pid, problem_or_None, result_dict)
        for rec in records:
            pid = _problem_id(rec["custom_id"])
            problem = problems_map.get(pid) if pid else None
            result = _classify_record(rec, problem)
            classified.append((pid, problem, result))

        # Счётчики.
        n_total = len(classified)
        n_skip_flags = sum(1 for _, _, r in classified if r["skip"] and "flags:" in r["skip_reason"])
        n_skip_not_found = sum(1 for _, _, r in classified if r["skip_reason"] == "not_found")
        n_skip_multiple = sum(1 for _, _, r in classified if r["skip_reason"] == "multiple_problems")
        n_skip_bad_trim = sum(1 for _, _, r in classified if r["skip_reason"] == "bad_trim")
        n_skip_sol = sum(1 for _, _, r in classified if r["skip_reason"] == "conflict_solution")
        n_skip_parts = sum(1 for _, _, r in classified if r["skip_reason"] == "conflict_parts")
        n_no_changes = sum(
            1 for _, _, r in classified
            if not r["skip"] and not r["changes"]
        )

        # Задачи с конкретными правками.
        will_stmt = [(pid, p, r) for pid, p, r in classified if not r["skip"] and "stmt" in r["changes"]]
        will_sol = [(pid, p, r) for pid, p, r in classified if not r["skip"] and "solution" in r["changes"]]
        will_parts = [
            (pid, p, r) for pid, p, r in classified
            if not r["skip"] and (
                r["changes"].get("parts_update") or
                r["changes"].get("parts_create") or
                r["changes"].get("parts_delete")
            )
        ]
        will_change = set(
            pid for pid, p, r in classified
            if not r["skip"] and r["changes"]
        )

        n_will_stmt = len(will_stmt)
        n_will_sol = len(will_sol)
        n_will_parts = len(will_parts)
        n_will_change = len(will_change)

        summary_lines = [
            f"Записей в файле:                     {n_total:>7,}",
            f"",
            f"Будет изменено (итого уникальных):   {n_will_change:>7,}",
            f"  из них с чисткой условия:           {n_will_stmt:>7,}",
            f"  из них с вынесенным решением:       {n_will_sol:>7,}",
            f"  из них с переписанными подпунктами: {n_will_parts:>7,}",
            f"",
            f"Без изменений (dirty=False или нет правок): {n_no_changes:>5,}",
            f"",
            f"Пропущено — причины:",
            f"  флаги missing_figure/truncated:    {n_skip_flags:>7,}",
            f"  задача не найдена в базе:          {n_skip_not_found:>7,}",
            f"  multiple_problems=True:            {n_skip_multiple:>7,}",
            f"  подозрительное сокращение (20%):   {n_skip_bad_trim:>7,}",
            f"  конфликт решения (уже есть):       {n_skip_sol:>7,}",
            f"  конфликт подпунктов (есть ответы): {n_skip_parts:>7,}",
        ]
        summary = "\n".join(summary_lines)

        self.stdout.write("\n" + "=" * 60)
        for line in summary_lines:
            self.stdout.write(line)
        self.stdout.write("=" * 60)

        # Сохраняем summary.
        summary_path = os.path.join(REPORT_DIR, "preview_summary.md")
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("# Батч 2 — сводка предпросмотра\n\n```\n")
            f.write(summary)
            f.write("\n```\n")
        self.stdout.write(f"\nСводка → {summary_path}")

        if not confirm:
            self._write_preview_html(
                will_stmt, will_sol, will_parts, summary,
                n_will_stmt, n_will_sol, n_will_parts,
            )
            self.stdout.write(
                "\n⏸  ПРЕДПРОСМОТР завершён. База НЕ изменена."
                "\nЗапусти с --confirm чтобы применить изменения."
            )
            return

        # ---------------------------------------------------------------
        # Режим --confirm: запись в базу.
        # ---------------------------------------------------------------
        self.stdout.write("\n⚠️  Режим --confirm: записываю изменения в базу.")

        # Бэкап.
        if os.path.exists(DB_PATH):
            os.makedirs(os.path.dirname(BACKUP_PATH), exist_ok=True)
            shutil.copy2(DB_PATH, BACKUP_PATH)
            self.stdout.write(f"Бэкап базы → {BACKUP_PATH}")

        to_process = [
            (pid, p, r) for pid, p, r in classified
            if not r["skip"] and r["changes"]
        ]
        self.stdout.write(f"Задач к записи: {len(to_process):,}")

        n_applied = 0
        applied_ids = []
        skipped_flagged = []
        skipped_bad_trim = []
        skipped_sol = []
        skipped_parts = []
        skipped_not_found = []

        # Собираем списки пропущенных.
        for pid, p, r in classified:
            if not r["skip"]:
                continue
            reason = r["skip_reason"]
            entry = str(pid or "?")
            if reason.startswith("flags:"):
                skipped_flagged.append(entry + "\t" + reason)
            elif reason == "bad_trim":
                skipped_bad_trim.append(entry)
            elif reason == "conflict_solution":
                skipped_sol.append(entry)
            elif reason == "conflict_parts":
                skipped_parts.append(entry)
            elif reason == "not_found":
                skipped_not_found.append(entry)

        # Пишем батчами.
        chunk_size = BATCH_SIZE
        for chunk_start in range(0, len(to_process), chunk_size):
            chunk = to_process[chunk_start:chunk_start + chunk_size]
            problems_to_save = []
            with transaction.atomic():
                for pid, problem, result in chunk:
                    changes = result["changes"]
                    _apply_changes_to_problem(problem, changes)
                    problems_to_save.append(problem)

                update_fields = ["statement", "solution", "solution_ai_extracted", "updated_at"]
                Problem.objects.bulk_update(problems_to_save, update_fields)

            n_applied += len(chunk)
            applied_ids.extend(p.pk for _, p, _ in chunk)
            self.stdout.write(f"  … применено {n_applied:,} / {len(to_process):,}")

        # Отчёты.
        _write_lines(os.path.join(REPORT_DIR, "skipped_flagged.txt"), skipped_flagged)
        _write_lines(os.path.join(REPORT_DIR, "skipped_bad_trim.txt"), skipped_bad_trim)
        _write_lines(os.path.join(REPORT_DIR, "skipped_conflict_solution.txt"), skipped_sol)
        _write_lines(os.path.join(REPORT_DIR, "skipped_conflict_parts.txt"), skipped_parts)
        _write_lines(os.path.join(REPORT_DIR, "skipped_not_found.txt"), skipped_not_found)
        _write_lines(
            os.path.join(REPORT_DIR, "changed_problem_ids.txt"),
            [str(i) for i in sorted(applied_ids)],
        )

        report_lines = ["# Батч 2 — отчёт применения\n", "```"] + summary_lines + [
            "",
            f"Фактически применено:                {n_applied:>7,}",
            "```",
        ]
        with open(os.path.join(REPORT_DIR, "apply_report.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(report_lines) + "\n")

        self.stdout.write(f"\n✅ Готово. Применено: {n_applied:,} задач.")
        self.stdout.write(f"   changed_problem_ids.txt — {len(applied_ids):,} id для пересчёта эмбеддингов.")

    # -------------------------------------------------------------------
    # Генерация HTML-предпросмотра
    # -------------------------------------------------------------------
    def _write_preview_html(
        self,
        will_stmt, will_sol, will_parts, summary,
        n_will_stmt, n_will_sol, n_will_parts,
    ):
        rng = random.Random(PREVIEW_SEED)

        def _sample(items, k):
            return rng.sample(items, min(k, len(items)))

        sample_stmt = _sample(will_stmt, PREVIEW_STMT)
        sample_sol = _sample(will_sol, PREVIEW_SOL)
        sample_parts = _sample(will_parts, PREVIEW_PARTS)

        def _render_section(items, section_tag):
            blocks = []
            for pid, problem, result in items:
                if problem is None:
                    continue
                blocks.append(_problem_row(pid, problem, result["changes"], section_tag))
            return "\n".join(blocks) if blocks else "<p><em>Нет данных</em></p>"

        html_content = HTML_TEMPLATE.format(
            summary=html.escape(summary),
            n_stmt=len(sample_stmt),
            n_sol=len(sample_sol),
            n_parts=len(sample_parts),
            section_stmt=_render_section(sample_stmt, "stmt"),
            section_sol=_render_section(sample_sol, "solution"),
            section_parts=_render_section(sample_parts, "parts"),
        )

        out_path = os.path.join(REPORT_DIR, "preview_apply.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        self.stdout.write(f"HTML-предпросмотр → {out_path}")


def _write_lines(path: str, lines: List[str]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))
