"""
Где живут грязь и решения: в основном условии (statement) или в подпунктах (parts)?
Только чтение. Ничего не меняет, к API не обращается.
Отвечает на вопрос: достаточно ли чистить только statement для Батча 2.
"""
import re
from django.core.management.base import BaseCommand
from problems.models import Problem

OCR_MARKERS = ["jдолл", "р.j", "\x0c", ":купа"]


def is_ile(p):
    for ref in p.source_references.all():
        name = (getattr(getattr(ref, "source", None), "name", "") or "").lower()
        if "iloveeconomics" in name:
            return True
    return False


def parts_text(p):
    out = []
    for part in p.parts.all():
        st = (getattr(part, "statement", "") or "").strip()
        if st:
            out.append(st)
    return "\n".join(out)


def is_dirty(text):
    if not text:
        return False
    for m in re.finditer(r"\\begin\{(cases|aligned)\}(.*?)\\end\{\1\}", text, re.S):
        if "\\\\" not in m.group(2):
            return True
    if re.search(r"[а-яё][a-z]{1,2}[а-яё]", text, re.I):
        return True
    if re.search(r"[а-яё]:[а-яё]", text):
        return True
    if any(mk in text for mk in OCR_MARKERS):
        return True
    if re.search(r"\b(\w{3,})\s+\1\b", text, re.I):
        return True
    return False


def has_solution_marker(text):
    if not text:
        return False
    return bool(re.search(r"критери|\bрешение\s*[:\n]|\\Subitem|\{\\large|\d+\s*балл", text, re.I))


class Command(BaseCommand):
    help = "Где живут грязь и решения: в statement или в подпунктах. Только чтение."

    def handle(self, *args, **opts):
        qs = (Problem.objects.filter(status="published", multiple_problems=False)
              .prefetch_related("parts", "source_references__source"))

        total = skipped_ile = 0
        d_stmt = d_parts = d_parts_only = 0
        s_stmt = s_parts = s_parts_only = 0
        has_parts = 0

        for p in qs.iterator(chunk_size=300):
            if is_ile(p):
                skipped_ile += 1
                continue
            total += 1
            stmt = p.statement or ""
            pts = parts_text(p)
            if pts:
                has_parts += 1

            ds, dp = is_dirty(stmt), is_dirty(pts)
            if ds:
                d_stmt += 1
            if dp:
                d_parts += 1
            if dp and not ds:
                d_parts_only += 1

            ss, sp = has_solution_marker(stmt), has_solution_marker(pts)
            if ss:
                s_stmt += 1
            if sp:
                s_parts += 1
            if sp and not ss:
                s_parts_only += 1

        self.stdout.write(f"Пул (published, без ILE и склеек): {total:,} (ILE исключено: {skipped_ile:,})")
        self.stdout.write(f"Из них с подпунктами: {has_parts:,}")
        self.stdout.write("")
        self.stdout.write("=== ГРЯЗЬ ===")
        self.stdout.write(f"  в основном условии:            {d_stmt:>6,}")
        self.stdout.write(f"  в подпунктах:                  {d_parts:>6,}")
        self.stdout.write(f"  ТОЛЬКО в подпунктах (условие чистое) → statement-only ПРОПУСТИТ: {d_parts_only:,}")
        self.stdout.write("")
        self.stdout.write("=== ПРИЗНАК ЗАПЕЧЁННОГО РЕШЕНИЯ ===")
        self.stdout.write(f"  в основном условии:            {s_stmt:>6,}")
        self.stdout.write(f"  в подпунктах:                  {s_parts:>6,}")
        self.stdout.write(f"  ТОЛЬКО в подпунктах → вынос-из-условия ПРОПУСТИТ: {s_parts_only:,}")
