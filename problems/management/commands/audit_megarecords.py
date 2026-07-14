"""
АУДИТ (только чтение): ищем «мега-записи» — несколько задач, слитых в одну
(дефект OCR-импорта). Прокси — длина текста условия. Группируем по источнику.
Ничего не меняет, API не вызывает.
"""
from typing import Dict
from collections import defaultdict

from django.core.management.base import BaseCommand
from problems.models import Problem

OCR_SIGNALS = ["•", "jдолл", "р.j", " :к", ":купа", "CIIA", "\x0c"]


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


class Command(BaseCommand):
    help = "Аудит мега-записей (только чтение): длинные слитые записи по источникам."

    def add_arguments(self, parser):
        parser.add_argument("--threshold", type=int, default=2500,
                            help="Длина (символов), выше которой запись считается подозрительной.")
        parser.add_argument("--show-ids", type=int, default=10,
                            help="Сколько id самых длинных записей показать.")

    def handle(self, *args, **opts):
        thr = opts["threshold"]
        qs = (Problem.objects.filter(status="published")
              .prefetch_related("parts", "source_references__source"))

        total = 0
        skipped_ile = 0
        buckets = {"<1500": 0, "1500-2500": 0, "2500-4000": 0, ">4000": 0}
        long_by_source: Dict[str, int] = defaultdict(int)
        total_by_source: Dict[str, int] = defaultdict(int)
        ocr_by_source: Dict[str, int] = defaultdict(int)
        longest = []  # (len, id, source)

        for p in qs.iterator(chunk_size=300):
            src = get_source_name(p)
            if "ile" in src.lower() or "iloveeconomics" in src.lower():
                skipped_ile += 1
                continue
            total += 1
            total_by_source[src] += 1
            body = body_text(p)
            n = len(body)
            if n < 1500:
                buckets["<1500"] += 1
            elif n < 2500:
                buckets["1500-2500"] += 1
            elif n < 4000:
                buckets["2500-4000"] += 1
            else:
                buckets[">4000"] += 1
            if n >= thr:
                long_by_source[src] += 1
                longest.append((n, p.id, src))
            if any(sig in body for sig in OCR_SIGNALS):
                ocr_by_source[src] += 1

        self.stdout.write(f"Опубликованных без ILE: {total:,} (ILE исключено: {skipped_ile:,})")
        self.stdout.write("")
        self.stdout.write("=== ДЛИНА ТЕКСТА (символов) ===")
        for k in ["<1500", "1500-2500", "2500-4000", ">4000"]:
            self.stdout.write(f"  {k:<12} {buckets[k]:>7,}")

        long_total = sum(long_by_source.values())
        self.stdout.write("")
        self.stdout.write(f"=== ДЛИННЫЕ записи (≥{thr} симв.) — подозрение на склейку: {long_total:,} ===")
        self.stdout.write("по источникам (длинных / всего записей источника, доля):")
        for src in sorted(long_by_source, key=lambda s: -long_by_source[s]):
            tot = total_by_source[src]
            share = 100.0 * long_by_source[src] / tot if tot else 0
            self.stdout.write(f"  {long_by_source[src]:>5,} / {tot:<6,} ({share:4.0f}%)  {src}")

        ocr_total = sum(ocr_by_source.values())
        self.stdout.write("")
        self.stdout.write(f"=== Записи с OCR-артефактами (•, jдолл, :к …): {ocr_total:,} ===")
        for src in sorted(ocr_by_source, key=lambda s: -ocr_by_source[s])[:15]:
            self.stdout.write(f"  {ocr_by_source[src]:>5,}  {src}")

        longest.sort(reverse=True)
        self.stdout.write("")
        self.stdout.write(f"=== Самые длинные записи (top {opts['show_ids']}) ===")
        for n, pid, src in longest[:opts["show_ids"]]:
            self.stdout.write(f"  #{pid:<6} {n:>6,} симв.  {src}")
