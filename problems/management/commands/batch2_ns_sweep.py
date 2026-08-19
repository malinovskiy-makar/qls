# -*- coding: utf-8 -*-
"""
Свип new_sentence Батча 2 — классификация по происхождению и применение.

Вход — reports/batch2_sweep/new_sentence_candidates.json (361 поле в 292
задачах, пишет batch2_full_sweep) и полный бэкап ДО
(backups/db_backup_before_batch2_apply.sqlite3). Логика классификации —
problems/batch2_ns.py (см. докстринг там; решение — Notion «Решения»
2026-07-21). Три вердикта:

  TABLE_KEEP  — новый \\begin{array} с подтверждённым происхождением:
                оставить, голый блок обернуть в $$...$$;
  MOVED_KEEP  — перенос содержимого из других полей той же задачи:
                оставить как есть;
  REVERT      — происхождение не подтверждено: откат к ДО с
                переприменением механики (revert_with_recleaning, тот же
                трёхуровневый fallback, что у отката digit_sign_change).

Без --confirm — только классификация + превью
reports/batch2_sweep/new_sentence_preview.html (3 секции, стоп-гейт
Макара). С --confirm — запись в базу + контроли (пересвип откатов,
парность $$ после обёртки, идемпотентность повторного прогона) +
reports/batch2_sweep/reverted_new_sentence_ids.txt (кандидаты на
пере-импорт) + ns_affected_ids.txt (на пересчёт эмбеддингов).
"""
from collections import defaultdict
from typing import Dict, List, Tuple
import datetime
import html
import json
import os
import random
import sqlite3

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from problems.batch2_ns import (
    classify_field, build_fund, display_dollar_pairs_balanced,
    wrap_bare_arrays, wrap_invariant_holds)
from problems.batch2_unblock import revert_with_recleaning, sweep_field
from problems.management.commands.glue_pdf_lines import _PREVIEW_TAIL, preview_head
from problems.management.commands.preview_batch2_unblock import diff_block
from problems.models import Problem, ProblemPart

OUT_DIR = "reports/batch2_sweep"
CANDIDATES_PATH = os.path.join(OUT_DIR, "new_sentence_candidates.json")
DEFAULT_BACKUP_DB = "backups/db_backup_before_batch2_apply.sqlite3"
PREVIEW_PATH = os.path.join(OUT_DIR, "new_sentence_preview.html")
CLASSIFICATION_PATH = os.path.join(OUT_DIR, "ns_classification.json")
REVERTED_IDS_PATH = os.path.join(OUT_DIR, "reverted_new_sentence_ids.txt")
AFFECTED_IDS_PATH = os.path.join(OUT_DIR, "ns_affected_ids.txt")
SAMPLE_LIMIT = 40
PREVIEW_SEED = 2026
SQL_CHUNK = 400


def _load_fund_rows(backup_path, pids):
    # type: (str, List[int]) -> Dict[int, Dict]
    """ДО-контекст задач из бэкапа: statement/answer/solution задачи +
    (label, statement, answer) всех подпунктов. Сырым sqlite3 — бэкапу не
    обязана соответствовать текущая схема моделей."""
    con = sqlite3.connect(backup_path)
    cur = con.cursor()
    ctx = {}
    for i in range(0, len(pids), SQL_CHUNK):
        chunk = pids[i:i + SQL_CHUNK]
        # Подставляется только "?,?,?" по числу элементов; значения идут
        # отдельным аргументом execute() — см. batch2_full_sweep.py.
        qmarks = ",".join("?" * len(chunk))
        cur.execute(
            "SELECT id, statement, answer, solution FROM problems_problem "
            "WHERE id IN ({})".format(qmarks), chunk)  # nosec B608
        for pid, stmt, ans, sol in cur.fetchall():
            ctx[pid] = {"statement": stmt or "", "answer": ans or "",
                        "solution": sol or "", "parts": []}
        cur.execute(
            "SELECT problem_id, label, statement, answer FROM problems_problempart "
            "WHERE problem_id IN ({}) ORDER BY \"order\", label".format(qmarks),  # nosec B608
            chunk)
        for pid, label, stmt, ans in cur.fetchall():
            if pid in ctx:
                ctx[pid]["parts"].append(
                    {"label": label, "statement": stmt or "", "answer": ans or ""})
    con.close()
    return ctx


def _fund_texts(row):
    # type: (Dict) -> List[str]
    """Фонд происхождения по решению 2026-07-21: statement + текст и answer
    всех подпунктов + Problem.answer + Problem.solution."""
    texts = [row["statement"], row["answer"], row["solution"]]
    for p in row["parts"]:
        texts.append(p["statement"])
        texts.append(p["answer"])
    return texts


class Command(BaseCommand):
    help = ("Классификация new_sentence Батча 2 по происхождению "
            "(TABLE_KEEP/MOVED_KEEP/REVERT). Без --confirm база не меняется.")

    def add_arguments(self, parser):
        parser.add_argument("--backup-db", default=DEFAULT_BACKUP_DB)
        parser.add_argument("--confirm", action="store_true",
                            help="Применить: обёртки таблиц + откаты REVERT.")

    def handle(self, *args, **opts):
        os.makedirs(OUT_DIR, exist_ok=True)
        backup_path = opts["backup_db"]
        if not os.path.exists(CANDIDATES_PATH):
            raise CommandError("{} не найден — сначала batch2_full_sweep.".format(
                CANDIDATES_PATH))
        if not os.path.exists(backup_path):
            raise CommandError("Бэкап не найден: {}".format(backup_path))

        with open(CANDIDATES_PATH, encoding="utf-8") as f:
            cards = json.load(f)
        pids = sorted({c["pid"] for c in cards})
        self.stdout.write("Кандидатов new_sentence: {} полей в {} задачах".format(
            len(cards), len(pids)))

        ctx = _load_fund_rows(backup_path, pids)
        funds = {pid: build_fund(_fund_texts(row)) for pid, row in ctx.items()}

        problems = {p.pk: p for p in Problem.objects.filter(pk__in=pids)}
        part_pks = {c["pk"] for c in cards if c["kind"] == "part"}
        parts = {p.pk: p for p in ProblemPart.objects.filter(pk__in=part_pks)}

        # ---- Классификация (текущий текст — из БАЗЫ, карточка — на сверку) ----
        classified = []
        stale = []
        missing = []
        for c in cards:
            if c["kind"] == "statement":
                obj = problems.get(c["pid"])
                current = obj.statement if obj else None
            else:
                obj = parts.get(c["pk"])
                current = obj.statement if obj else None
            if current is None:
                missing.append((c["kind"], c.get("pk") or c["pid"]))
                continue
            if current != c["current"]:
                stale.append((c["kind"], c.get("pk") or c["pid"]))
            fund = funds.get(c["pid"],
                             {"nums": set(), "signs": set(), "words": set()})
            res = classify_field(c["old"], current, fund)
            classified.append({**c, "current": current, **res})

        by_verdict = defaultdict(list)
        for c in classified:
            by_verdict[c["verdict"]].append(c)
        n_table = len(by_verdict["TABLE_KEEP"])
        n_moved = len(by_verdict["MOVED_KEEP"])
        n_revert = len(by_verdict["REVERT"])

        self.stdout.write("TABLE_KEEP: {} полей в {} задачах".format(
            n_table, len({c['pid'] for c in by_verdict['TABLE_KEEP']})))
        self.stdout.write("MOVED_KEEP: {} полей в {} задачах".format(
            n_moved, len({c['pid'] for c in by_verdict['MOVED_KEEP']})))
        self.stdout.write("REVERT:     {} полей в {} задачах".format(
            n_revert, len({c['pid'] for c in by_verdict['REVERT']})))
        if stale:
            self.stdout.write(self.style.WARNING(
                "Текст в базе разошёлся с карточкой (взят текст БАЗЫ): {} — {}".format(
                    len(stale), stale[:10])))
        if missing:
            self.stdout.write(self.style.WARNING(
                "Поля исчезли из базы: {} — {}".format(len(missing), missing[:10])))

        with open(CLASSIFICATION_PATH, "w", encoding="utf-8") as f:
            json.dump([{k: v for k, v in c.items() if k != "detail"}
                       for c in classified], f, ensure_ascii=False, indent=1)
        self.stdout.write("Классификация → {}".format(CLASSIFICATION_PATH))

        self._write_preview(by_verdict, problems, ctx)

        if not opts["confirm"]:
            self.stdout.write(
                "Режим классификации: база НЕ изменена. Превью — {}. "
                "Применение — только после «да» Макара (--confirm).".format(
                    PREVIEW_PATH))
            return

        self._apply(by_verdict, problems, parts)

    # ------------------------------------------------------------------
    # Превью (стоп-гейт)
    # ------------------------------------------------------------------

    def _write_preview(self, by_verdict, problems, ctx):
        rng = random.Random(PREVIEW_SEED)
        head = preview_head(
            "Свип new_sentence — классификация по происхождению",
            "Свип new_sentence Батча 2 — TABLE_KEEP / MOVED_KEEP / REVERT",
            "Критерий — происхождение (решение 2026-07-21): новые строки "
            "остаются, только если их содержимое есть в ДО этой же задачи "
            "(любое поле: условие, подпункты, ответы, решение). Таблицы с "
            "происхождением оборачиваются в маркеры display-математики "
            "(двойной доллар) и рендерятся ниже. "
            "Всё без происхождения — откат к ДО с переприменением механики. "
            "База НЕ менялась — это превью для стоп-гейта.")
        out = [head]

        def meta_line(num, c, extra=""):
            problem = problems.get(c["pid"])
            title = html.escape(problem.title if problem else "")
            label = (" (Условие)" if c["kind"] == "statement"
                     else " (подп. [{}], pk={})".format(
                         html.escape(c["label"] or ""), c["pk"]))
            reasons = "; ".join(c["reasons"])
            chips = ('<span class="chip">{}</span>'.format(html.escape(reasons))
                     if reasons else "")
            return ('<div class="meta"><b>№{num}</b> <b>#{pid}</b>{label} — '
                    '{title}{extra}{chips} — <a href="http://127.0.0.1:8000/'
                    'catalog/problem/{pid}/" target="_blank">открыть в каталоге'
                    '</a></div>'.format(num=num, pid=c["pid"], label=label,
                                        title=title, extra=extra, chips=chips))

        def id_list(cards_):
            ids = sorted({c["pid"] for c in cards_})
            return ('<p class="meta">Полный список задач ({}): {}</p>'.format(
                len(ids), ", ".join(str(i) for i in ids)))

        def sample_of(cards_):
            if len(cards_) <= SAMPLE_LIMIT:
                return cards_, False
            return rng.sample(cards_, SAMPLE_LIMIT), True

        def do_context_html(pid):
            row = ctx.get(pid)
            if not row:
                return ""
            blocks = ['<div class="fieldlabel">Условие (ДО)</div>'
                      '<div class="field-text">{}</div>'.format(
                          html.escape(row["statement"]))]
            for p in row["parts"]:
                blocks.append(
                    '<div class="fieldlabel">Подпункт [{}] (ДО)</div>'
                    '<div class="field-text">{}</div>'.format(
                        html.escape(p["label"] or ""), html.escape(p["statement"])))
                if p["answer"]:
                    blocks.append(
                        '<div class="fieldlabel">Ответ [{}] (ДО)</div>'
                        '<div class="field-text">{}</div>'.format(
                            html.escape(p["label"] or ""), html.escape(p["answer"])))
            if row["answer"]:
                blocks.append('<div class="fieldlabel">Ответ (ДО)</div>'
                              '<div class="field-text">{}</div>'.format(
                                  html.escape(row["answer"])))
            if row["solution"]:
                blocks.append('<div class="fieldlabel">Решение (ДО)</div>'
                              '<div class="field-text">{}</div>'.format(
                                  html.escape(row["solution"])))
            return ('<details><summary>Полный ДО-контекст задачи (фонд '
                    'происхождения)</summary>{}</details>'.format("".join(blocks)))

        # Секция A: TABLE_KEEP — ПОСЛЕ с обёрнутой таблицей (как будет в базе).
        table_cards = sorted(by_verdict["TABLE_KEEP"], key=lambda c: c["pid"])
        sample, truncated = sample_of(table_cards)
        out.append('<h2 class="section">A. TABLE_KEEP — {} полей'
                   '{}</h2>'.format(len(table_cards),
                                    " (выборка {})".format(len(sample))
                                    if truncated else ""))
        if truncated:
            out.append(id_list(table_cards))
        for i, c in enumerate(sorted(sample, key=lambda c: c["pid"]), 1):
            wrapped, n = wrap_bare_arrays(c["current"])
            extra = ' — обёрнуто блоков: {}'.format(n)
            out.append('<div class="card">{}{}{}</div>'.format(
                meta_line(i, c, extra),
                diff_block("Текст", c["old"], wrapped),
                do_context_html(c["pid"])))
        if not table_cards:
            out.append("<p><em>Пусто.</em></p>")

        # Секция B: MOVED_KEEP — ДО/ПОСЛЕ + раскрывающийся полный ДО-контекст.
        moved_cards = sorted(by_verdict["MOVED_KEEP"], key=lambda c: c["pid"])
        sample, truncated = sample_of(moved_cards)
        out.append('<h2 class="section">B. MOVED_KEEP — {} полей'
                   '{}</h2>'.format(len(moved_cards),
                                    " (выборка {})".format(len(sample))
                                    if truncated else ""))
        if truncated:
            out.append(id_list(moved_cards))
        for i, c in enumerate(sorted(sample, key=lambda c: c["pid"]), 1):
            out.append('<div class="card">{}{}{}</div>'.format(
                meta_line(i, c),
                diff_block("Текст", c["old"], c["current"]),
                do_context_html(c["pid"])))
        if not moved_cards:
            out.append("<p><em>Пусто.</em></p>")

        # Секция C: REVERT — текущее ПОСЛЕ / к чему откатим (все карточки).
        revert_cards = sorted(by_verdict["REVERT"], key=lambda c: c["pid"])
        out.append('<h2 class="section">C. REVERT — {} полей</h2>'.format(
            len(revert_cards)))
        for i, c in enumerate(revert_cards, 1):
            target = revert_with_recleaning(c["old"])["final"]
            out.append('<div class="card">{}{}</div>'.format(
                meta_line(i, c),
                diff_block("Сейчас в базе → станет после отката",
                           c["current"], target)))
        if not revert_cards:
            out.append("<p><em>Пусто.</em></p>")

        out.append(_PREVIEW_TAIL)
        with open(PREVIEW_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(out))
        self.stdout.write("Превью → {} (A {}, B {}, C {})".format(
            PREVIEW_PATH, len(table_cards), len(moved_cards), len(revert_cards)))

    # ------------------------------------------------------------------
    # Применение (только после «да» Макара)
    # ------------------------------------------------------------------

    def _apply(self, by_verdict, problems, parts):
        ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_json = os.path.join(OUT_DIR, "backup_ns_apply_{}.json".format(ts))
        backup = {"statement": {}, "part": {}}

        stmt_updates = {}   # pid -> text
        part_updates = {}   # pk -> text
        resweep_bad = []
        parity_bad = []
        wrap_broken = []
        levels = defaultdict(int)
        glue_not_idempotent = []
        wrapped_fields = 0
        wrapped_blocks = 0
        noop = 0

        for c in by_verdict["TABLE_KEEP"]:
            wrapped, n = wrap_bare_arrays(c["current"])
            if n == 0 or wrapped == c["current"]:
                noop += 1
                continue
            # Обёртка не имеет права менять ничего, кроме вставленных $$
            # и валютного \$ → \textdollar внутри блока.
            if not wrap_invariant_holds(c["current"], wrapped):
                wrap_broken.append((c["kind"], c.get("pk") or c["pid"]))
                continue
            if not display_dollar_pairs_balanced(wrapped):
                parity_bad.append((c["kind"], c.get("pk") or c["pid"]))
                continue
            wrapped_fields += 1
            wrapped_blocks += n
            self._stage(c, wrapped, backup, stmt_updates, part_updates)

        for c in by_verdict["REVERT"]:
            res = revert_with_recleaning(c["old"])
            levels[res["level"]] += 1
            if not res["glue_idempotent"]:
                glue_not_idempotent.append((c["kind"], c.get("pk") or c["pid"]))
            # Пересвип: откат не имеет права оставить подмену числа/знака.
            if sweep_field(c["old"], res["final"])["verdict"] == "digit_sign_change":
                resweep_bad.append((c["kind"], c.get("pk") or c["pid"]))
                continue
            if res["final"] == c["current"]:
                noop += 1
                continue
            self._stage(c, res["final"], backup, stmt_updates, part_updates)

        with open(backup_json, "w", encoding="utf-8") as f:
            json.dump(backup, f, ensure_ascii=False, indent=1)
        self.stdout.write("Бэкап перезаписываемых значений → {}".format(backup_json))

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
                Problem.objects.bulk_update(
                    to_save_problems, ["statement"], batch_size=200)
            if to_save_parts:
                ProblemPart.objects.bulk_update(
                    to_save_parts, ["statement"], batch_size=200)

        reverted_pids = sorted({c["pid"] for c in by_verdict["REVERT"]})
        with open(REVERTED_IDS_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(str(i) for i in reverted_pids) + "\n")

        affected = sorted(
            set(stmt_updates.keys())
            | {parts[pk].problem_id for pk in part_updates})
        with open(AFFECTED_IDS_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(str(i) for i in affected) + "\n")

        self.stdout.write(self.style.SUCCESS(
            "Записано: {} statement, {} подпунктов ({} задач). "
            "Обёрнуто таблиц: {} блоков в {} полях. Откатов: {} "
            "(full={}, glue_only={}, raw={}). No-op: {}.".format(
                len(stmt_updates), len(part_updates), len(affected),
                wrapped_blocks, wrapped_fields, len(by_verdict["REVERT"]),
                levels["full"], levels["glue_only"], levels["raw"], noop)))
        self.stdout.write("Кандидаты на пере-импорт → {} ({} задач)".format(
            REVERTED_IDS_PATH, len(reverted_pids)))
        self.stdout.write("На пересчёт эмбеддингов → {} ({} задач)".format(
            AFFECTED_IDS_PATH, len(affected)))

        for name, bad in [("Пересвип отката нашёл подмену (поле НЕ записано)",
                           resweep_bad),
                          ("Парность $$ нарушена (поле НЕ записано)", parity_bad),
                          ("Обёртка изменила не только $$ (поле НЕ записано)",
                           wrap_broken),
                          ("glue не идемпотентна на финальном тексте",
                           glue_not_idempotent)]:
            if bad:
                self.stdout.write(self.style.WARNING(
                    "{}: {} — {}".format(name, len(bad), bad[:20])))
        if not (resweep_bad or parity_bad or wrap_broken or glue_not_idempotent):
            self.stdout.write("Контроли применения: все чисты.")

    @staticmethod
    def _stage(c, text, backup, stmt_updates, part_updates):
        if c["kind"] == "statement":
            backup["statement"][str(c["pid"])] = c["current"]
            stmt_updates[c["pid"]] = text
        else:
            backup["part"][str(c["pk"])] = c["current"]
            part_updates[c["pk"]] = text
