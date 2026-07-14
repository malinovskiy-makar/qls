"""
Подсчёт «грязных» задач для Батча 2 (чистка на Sonnet) + оценка стоимости.
Только чтение базы. Ничего не меняет, к API не обращается.
Исключаем ILE и склейки (multiple_problems). «не задача» НЕ исключаем.
"""
from typing import List, Tuple
from collections import defaultdict
import re

from django.core.management.base import BaseCommand
from problems.models import Problem

CHARS_PER_TOKEN = 2.23
SYS_EST_CHARS = 1600          # примерная длина инструкции чистки (для оценки)
OUT_FACTOR = 1.1              # вывод ≈ чистое условие + спасённое решение ≈ длина тела
# Sonnet, Batch (-50%): $/млн
IN_RATE = 1.50
OUT_RATE = 7.50

OCR_PUNCT = ["•", "jдолл", "р.j", " :к", ":купа", "\x0c"]


def get_source_name(p) -> str:
    refs = list(p.source_references.all())
    if refs and getattr(refs[0], "source", None):
        return refs[0].source.name or "—"
    return "—"


def body_text(p) -> str:
    parts = []
    if p.statement:
        parts.append(p.statement)
    for part in p.parts.all():
        st = getattr(part, "statement", "") or ""
        if st:
            parts.append(st)
    return "\n".join(parts)


def dirt_score(text: str) -> Tuple[int, List[str]]:
    score = 0
    sig = []
    if ("\\begin{cases}" in text or "\\begin{aligned}" in text) and "\\\\" not in text:
        score += 2; sig.append("битый LaTeX-блок")
    if text.count("$") % 2 == 1:
        score += 1; sig.append("непарные $")
    if re.search(r"[а-яё][a-z][а-яё]", text, re.IGNORECASE):
        score += 2; sig.append("латиница в слове (OCR)")
    if any(s in text for s in OCR_PUNCT):
        score += 2; sig.append("OCR-символы")
    if "((" in text or "))" in text:
        score += 1; sig.append("задвоенные скобки")
    if re.search(r"\b(\w{3,})\s+\1\b", text, re.IGNORECASE):
        score += 1; sig.append("задвоенное слово")
    return score, sig


def money(subset: List[int]) -> float:
    in_tok = sum((SYS_EST_CHARS + b) / CHARS_PER_TOKEN for b in subset)
    out_tok = sum(b * OUT_FACTOR / CHARS_PER_TOKEN for b in subset)
    return in_tok / 1e6 * IN_RATE + out_tok / 1e6 * OUT_RATE


class Command(BaseCommand):
    help = "Подсчёт грязных задач для Батча 2 + оценка стоимости. Только чтение."

    def handle(self, *args, **opts):
        qs = (Problem.objects.filter(status="published", multiple_problems=False)
              .prefetch_related("parts", "source_references__source"))

        total = skipped_ile = 0
        score_hist = defaultdict(int)
        bodies_ge1: List[int] = []       # длины тел грязных (score>=1)
        bodies_ge2: List[int] = []
        dirty_by_source = defaultdict(int)
        total_by_source = defaultdict(int)
        ocr_count = 0

        for p in qs.iterator(chunk_size=300):
            src = get_source_name(p)
            if "ile" in src.lower() or "iloveeconomics" in src.lower():
                skipped_ile += 1
                continue
            total += 1
            total_by_source[src] += 1
            body = body_text(p)
            score, sig = dirt_score(body)
            score_hist[score] += 1
            if "OCR-символы" in sig or "латиница в слове (OCR)" in sig:
                ocr_count += 1
            if score >= 1:
                bodies_ge1.append(len(body))
                dirty_by_source[src] += 1
            if score >= 2:
                bodies_ge2.append(len(body))

        self.stdout.write(f"Опубликованных без ILE и без склеек: {total:,} (ILE исключено: {skipped_ile:,})")
        self.stdout.write("")
        self.stdout.write("=== РАСПРЕДЕЛЕНИЕ ПО «ГРЯЗНОСТИ» (сумма признаков) ===")
        for s in sorted(score_hist):
            self.stdout.write(f"  score {s}: {score_hist[s]:>7,}")

        n1, n2 = len(bodies_ge1), len(bodies_ge2)
        self.stdout.write("")
        self.stdout.write("=== СКОЛЬКО ЧИСТИТЬ И СКОЛЬКО ЭТО СТОИТ (Sonnet + Batch) ===")
        self.stdout.write(f"  порог ≥1 признак: {n1:>7,} задач  →  ~${money(bodies_ge1):.0f}")
        self.stdout.write(f"  порог ≥2 признака: {n2:>7,} задач  →  ~${money(bodies_ge2):.0f}")
        self.stdout.write(f"  (задач с OCR-признаками: {ocr_count:,})")

        self.stdout.write("")
        self.stdout.write("=== ГДЕ КОНЦЕНТРИРУЕТСЯ ГРЯЗЬ (порог ≥1) — топ источников ===")
        self.stdout.write("грязных / всего в источнике (доля):")
        for src in sorted(dirty_by_source, key=lambda s: -dirty_by_source[s])[:15]:
            tot = total_by_source[src]
            share = 100.0 * dirty_by_source[src] / tot if tot else 0
            self.stdout.write(f"  {dirty_by_source[src]:>6,} / {tot:<6,} ({share:4.0f}%)  {src}")
