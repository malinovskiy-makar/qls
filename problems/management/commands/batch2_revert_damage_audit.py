"""Аудит уже применённых откатов свипа Батча 2 (только чтение, ничего не чинит).

Сравнивает по каждому из 1 762 откаченных полей состояние ДО отката
(post-Sonnet, лежит в reports/batch2_sweep/backup_revert_*.json) с текущим
состоянием в базе и считает семь признаков ухудшения (problems/revert_damage.py).

Порядок ради экономии времени: шесть текстовых признаков считаются здесь без
браузера; на рендер (седьмой признак) уходят ТОЛЬКО отмеченные поля плюс
случайная контрольная выборка неотмеченных — если предфильтр слеп к
KaTeX-ошибкам, это видно по контрольной выборке.

    ./venv/bin/python manage.py batch2_revert_damage_audit
    ./venv/bin/python manage.py batch2_revert_damage_audit --control 100 --seed 20260728

Выход:
    reports/batch2_sweep/applied_revert_damage.txt   — список id
    reports/batch2_sweep/applied_revert_audit.md     — отчёт
    reports/batch2_sweep/render_queue.json           — задание рендер-проверке
"""

import json
import os
import random
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand, CommandError

from problems.models import Problem, ProblemPart
from problems.revert_damage import compare_field, flag_labels

OUT_DIR = "reports/batch2_sweep"
DEFAULT_BACKUP = os.path.join(OUT_DIR, "backup_revert_20260721_112821.json")
RENDER_QUEUE = os.path.join(OUT_DIR, "render_queue.json")
RENDER_RESULT = os.path.join(OUT_DIR, "render_result.json")
DAMAGE_IDS = os.path.join(OUT_DIR, "applied_revert_damage.txt")
REPORT = os.path.join(OUT_DIR, "applied_revert_audit.md")

AA_SOURCE_NAME = "Сборник тестов АА"


class Command(BaseCommand):
    help = "Измерить, что натворил применённый 21 июля откат свипа Батча 2."

    def add_arguments(self, parser):
        parser.add_argument("--backup", default=DEFAULT_BACKUP)
        parser.add_argument("--control", type=int, default=100,
                            help="Размер контрольной выборки неотмеченных полей.")
        parser.add_argument("--seed", type=int, default=20260728)
        parser.add_argument("--with-render", action="store_true",
                            help="Влить результаты рендера из render_result.json.")
        parser.add_argument("--render-all", action="store_true",
                            help="Отправить на рендер ВСЕ поля, а не только "
                                 "отмеченные предфильтром (нужно, когда "
                                 "контрольная выборка показала слепые пятна).")

    # ── чтение состояний ────────────────────────────────────────────────

    def _load_pairs(self, backup_path):
        """[(kind, key, pid, part_pk, old_text, new_text)] по всем 1 762 полям."""
        if not os.path.exists(backup_path):
            raise CommandError("Бэкап отката не найден: {}".format(backup_path))
        with open(backup_path, encoding="utf-8") as f:
            backup = json.load(f)

        stmt_old = {int(k): v for k, v in backup.get("statement", {}).items()}
        part_old = {int(k): v for k, v in backup.get("part", {}).items()}

        stmt_now = dict(Problem.objects.filter(id__in=stmt_old)
                        .values_list("id", "statement"))
        parts_now = {p.pk: (p.statement, p.problem_id, p.label)
                     for p in ProblemPart.objects.filter(pk__in=part_old)}

        pairs, missing = [], []
        for pid, old in stmt_old.items():
            if pid not in stmt_now:
                missing.append(("statement", pid))
                continue
            pairs.append({"kind": "statement", "pid": pid, "pk": None, "label": "",
                          "old": old, "new": stmt_now[pid] or ""})
        for pk, old in part_old.items():
            if pk not in parts_now:
                missing.append(("part", pk))
                continue
            text, pid, label = parts_now[pk]
            pairs.append({"kind": "part", "pid": pid, "pk": pk, "label": label or "",
                          "old": old, "new": text or ""})
        return pairs, missing

    def _source_names(self, pids):
        """id задачи → имя первого источника (для разбивки отчёта)."""
        names = {}
        qs = (Problem.objects.filter(id__in=pids)
              .prefetch_related("source_references__source"))
        for p in qs:
            ref = next(iter(p.source_references.all()), None)
            names[p.id] = ref.source.name if ref and ref.source else "(без источника)"
        return names

    # ── главный ход ─────────────────────────────────────────────────────

    def handle(self, *args, **opts):
        pairs, missing = self._load_pairs(opts["backup"])
        self.stdout.write("Полей к сравнению: {} (не найдено в базе: {})"
                          .format(len(pairs), len(missing)))

        for item in pairs:
            item["flags"] = compare_field(item["old"], item["new"])

        flagged = [p for p in pairs if p["flags"]]
        clean = [p for p in pairs if not p["flags"]]

        rnd = random.Random(opts["seed"])
        control = rnd.sample(clean, min(opts["control"], len(clean)))
        for c in control:
            c["control"] = True

        if opts["render_all"]:
            self._write_render_queue(pairs, [])
        else:
            self._write_render_queue(flagged, control)
        self.stdout.write("Текстовые признаки: отмечено {} полей из {}."
                          .format(len(flagged), len(pairs)))

        render = self._load_render(opts["with_render"])
        if render is not None:
            self._merge_render(pairs, render)
            flagged = [p for p in pairs if p["flags"]]

        self._write_report(pairs, flagged, control, missing, render is not None)
        self.stdout.write(self.style.SUCCESS(
            "Готово. Ухудшено полей: {} (задач: {}). Отчёт → {}"
            .format(len(flagged), len({p['pid'] for p in flagged}), REPORT)))

    # ── рендер ──────────────────────────────────────────────────────────

    def _write_render_queue(self, flagged, control):
        """Задание рендер-проверке: отмеченные + контрольная выборка."""
        queue = []
        for item in flagged + control:
            queue.append({"kind": item["kind"], "pid": item["pid"], "pk": item["pk"],
                          "control": bool(item.get("control")),
                          "old": item["old"], "new": item["new"]})
        os.makedirs(OUT_DIR, exist_ok=True)
        with open(RENDER_QUEUE, "w", encoding="utf-8") as f:
            json.dump(queue, f, ensure_ascii=False)
        self.stdout.write("Задание рендеру ({} полей) → {}".format(len(queue), RENDER_QUEUE))

    def _load_render(self, want):
        if not want:
            return None
        if not os.path.exists(RENDER_RESULT):
            raise CommandError(
                "Нет {} — сначала прогоните рендер: node scripts/katex_render_check.js"
                .format(RENDER_RESULT))
        with open(RENDER_RESULT, encoding="utf-8") as f:
            return json.load(f)

    def _merge_render(self, pairs, render):
        by_key = {(r["kind"], r["pid"], r["pk"]): r for r in render}
        self.rendered = 0
        for item in pairs:
            if (item["kind"], item["pid"], item["pk"]) in by_key:
                self.rendered += 1
        for item in pairs:
            r = by_key.get((item["kind"], item["pid"], item["pk"]))
            if not r:
                continue
            item["katex_old"] = r["errors_old"]
            item["katex_new"] = r["errors_new"]
            if r["errors_new"] > r["errors_old"] and "katex_errors_up" not in item["flags"]:
                item["flags"].append("katex_errors_up")

    # ── отчёт ───────────────────────────────────────────────────────────

    def _write_report(self, pairs, flagged, control, missing, has_render):
        labels = flag_labels()
        by_flag = Counter()
        for item in flagged:
            for f in item["flags"]:
                by_flag[f] += 1

        damaged_pids = sorted({p["pid"] for p in flagged})
        names = self._source_names({p["pid"] for p in pairs})
        by_source = defaultdict(set)
        for item in flagged:
            by_source[names.get(item["pid"], "(без источника)")].add(item["pid"])

        aa_pids = sorted(pid for pid in damaged_pids
                         if names.get(pid) == AA_SOURCE_NAME)

        with open(DAMAGE_IDS, "w", encoding="utf-8") as f:
            for pid in damaged_pids:
                f.write("{}\n".format(pid))

        blind = [c for c in control if "katex_errors_up" in c.get("flags", [])]

        lines = []
        lines.append("# Шлюз «не навреди» по уже применённым откатам (Задача 1)\n")
        lines.append("Сравнение: ДО отката (post-Sonnet, `backup_revert_20260721_112821.json`) "
                     "против ТЕКУЩЕЙ базы. Ничего не чинилось — только замер.\n")
        lines.append("## Итог\n")
        lines.append("Полей проверено: **{}** (statement {}, подпунктов {})."
                     .format(len(pairs),
                             sum(1 for p in pairs if p["kind"] == "statement"),
                             sum(1 for p in pairs if p["kind"] == "part")))
        lines.append("")
        lines.append("**Ухудшено полей: {} ({:.1f}%), задач: {}.**"
                     .format(len(flagged), 100.0 * len(flagged) / max(1, len(pairs)),
                             len(damaged_pids)))
        lines.append("")
        if missing:
            lines.append("Не найдено в базе (удалены после отката): {}.\n".format(len(missing)))

        lines.append("## По признакам\n")
        lines.append("| Признак | Полей |")
        lines.append("|---|---:|")
        for key in ("bare_table_markup", "raw_latex_noslash", "shrunk_15",
                    "bad_start", "collapsed_to_stub", "lost_list_header",
                    "katex_errors_up"):
            mark = "" if has_render or key != "katex_errors_up" else " *(рендер не прогонялся)*"
            lines.append("| {}{} | {} |".format(labels[key], mark, by_flag.get(key, 0)))
        lines.append("")

        lines.append("## По источникам (задач с ухудшением)\n")
        lines.append("| Источник | Задач |")
        lines.append("|---|---:|")
        for src, pids in sorted(by_source.items(), key=lambda kv: -len(kv[1])):
            lines.append("| {} | {} |".format(src, len(pids)))
        lines.append("")

        lines.append("## Сборник тестов АА\n")
        lines.append("Задач источника «{}» среди ухудшенных: **{}**."
                     .format(AA_SOURCE_NAME, len(aa_pids)))
        if aa_pids:
            lines.append("")
            lines.append("id: {}".format(", ".join("#{}".format(i) for i in aa_pids)))
        lines.append("")

        lines.append("## Годен ли текстовый предфильтр\n")
        if has_render:
            rendered = getattr(self, "rendered", 0)
            lines.append("Полей прогнано через рендер: **{}** из {}."
                         .format(rendered, len(pairs)))
            lines.append("")
            lines.append("Контрольная выборка неотмеченных предфильтром полей: **{}**."
                         .format(len(control)))
            lines.append("")
            if blind:
                lines.append("⚠️ **Предфильтр НЕ ГОДЕН.** В контрольной выборке "
                             "**{}** полей с выросшим числом ошибок KaTeX, которых "
                             "текстовые признаки не поймали ({:.0f}% выборки). "
                             "Шесть текстовых признаков к KaTeX-ошибкам слепы, "
                             "поэтому рендер прогнан по ВСЕМ полям, а не по "
                             "отмеченным."
                             .format(len(blind), 100.0 * len(blind) / max(1, len(control))))
                lines.append("")
                lines.append("Слепые пятна выборки: {}".format(
                    ", ".join("#{}".format(c["pid"]) for c in blind)))
                lines.append("")
                lines.append("Вывод на будущее: экономить рендер текстовым "
                             "предфильтром нельзя — «сломанная формула» это то, "
                             "что решил KaTeX, а не то, что мы про него думаем.")
            else:
                lines.append("В контрольной выборке ухудшений рендера не найдено — "
                             "предфильтр на этой выборке слепых пятен не показал.")
        else:
            lines.append("Рендер не прогонялся — годность предфильтра не проверена.")
        lines.append("")

        lines.append("## Список id\n")
        lines.append("Полный список ухудшенных задач — `{}`.".format(DAMAGE_IDS))

        with open(REPORT, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
