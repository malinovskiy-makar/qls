# -*- coding: utf-8 -*-
"""
Задача 4 сессии свипа Батча 2: превью «новых предложений» — фрагментов,
которых не было в ДО (бэкап sqlite до 2026-07-04), но которые есть в
ПОСЛЕ (текущая база). Числа/знаки в них не тронуты (иначе попали бы в
digit_sign_change и были откачены автоматически) — похоже на восстановленный
Sonnet текст, а не подмену. НЕ откатывается автоматически — только
информационная карточка, вердикт по умолчанию «оставляем как есть».

Читает reports/batch2_sweep/new_sentence_candidates.json (пишет
batch2_full_sweep), берёт 30 случайных карточек (фиксированный seed —
воспроизводимая выборка), собирает HTML тем же конвейером, что и превью
группы Б (`preview_head`/`diff_block` — класс `field-text`, НЕ `text`,
чтобы не столкнуться с KaTeX-классом `mord text` у `\\text{...}`).
"""
import html
import json
import os
import random

from django.core.management.base import BaseCommand, CommandError

from problems.management.commands.glue_pdf_lines import _PREVIEW_TAIL, preview_head
from problems.management.commands.preview_batch2_unblock import diff_block
from problems.models import Problem

OUT_DIR = "reports/batch2_sweep"
CANDIDATES_PATH = os.path.join(OUT_DIR, "new_sentence_candidates.json")
PREVIEW_SEED = 2026
PREVIEW_N = 30


class Command(BaseCommand):
    help = ("Превью 30 случайных карточек «новых предложений» из свипа "
            "Батча 2 (reports/batch2_sweep/new_sentence_candidates.json).")

    def add_arguments(self, parser):
        parser.add_argument("--n", type=int, default=PREVIEW_N)
        parser.add_argument("--seed", type=int, default=PREVIEW_SEED)

    def handle(self, *args, **opts):
        if not os.path.exists(CANDIDATES_PATH):
            raise CommandError(
                "{} не найден — сначала прогони batch2_full_sweep.".format(
                    CANDIDATES_PATH))
        with open(CANDIDATES_PATH, encoding="utf-8") as f:
            cards = json.load(f)

        rng = random.Random(opts["seed"])
        n = opts["n"]
        sample = rng.sample(cards, min(n, len(cards)))

        pids = {c["pid"] for c in sample}
        problems = {p.pk: p for p in Problem.objects.filter(pk__in=pids)}

        head = preview_head(
            "Свип Батча 2 — восстановленные предложения",
            "Свип Батча 2 — {} случайных карточек «новых предложений» "
            "(из {} всего)".format(len(sample), len(cards)),
            "Фрагменты, которых не было в ДО (бэкап до 2026-07-04), но "
            "которые есть в ПОСЛЕ (текущая база) — числа/знаки не тронуты "
            "(иначе ушли бы в автооткат), похоже на восстановленный Sonnet "
            "текст. Информационно: по умолчанию оставляем как есть, вердикт "
            "не требуется.")
        out = [head]
        out.append('<h2 class="section">{} карточек</h2>'.format(len(sample)))
        if not sample:
            out.append("<p><em>Пусто.</em></p>")
        for i, c in enumerate(sample, start=1):
            problem = problems.get(c["pid"])
            title = html.escape(problem.title if problem else "")
            label = (" (Условие)" if c["kind"] == "statement"
                     else " (подп. [{}], pk={})".format(
                         html.escape(c["label"] or ""), c["pk"]))
            out.append(
                '<div class="card"><div class="meta"><b>№{num}</b> <b>#{pid}</b>'
                '{label} — {title} — <a href="http://127.0.0.1:8000/catalog/problem/'
                '{pid}/" target="_blank">открыть в каталоге</a></div>{diff}</div>'.format(
                    num=i, pid=c["pid"], label=label, title=title,
                    diff=diff_block("Текст", c["old"], c["current"])))
        out.append(_PREVIEW_TAIL)

        out_path = os.path.join(OUT_DIR, "reconstructed_preview.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(out))
        self.stdout.write("Превью новых предложений → {} ({} карточек)".format(
            out_path, len(sample)))
