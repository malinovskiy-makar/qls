"""
Выгрузка N самых грязных задач (порог ≥1) для ручной проверки перед Батчем 2.
Только чтение. Ничего не меняет, к API не обращается.
Детекторы те же, что в count_dirty.py.
"""
from typing import List, Tuple
import re

from django.core.management.base import BaseCommand
from problems.models import Problem

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
    if "((" in text or "))) " in text:
        score += 1; sig.append("задвоенные скобки")
    if re.search(r"\b(\w{3,})\s+\1\b", text, re.IGNORECASE):
        score += 1; sig.append("задвоенное слово")
    return score, sig


class Command(BaseCommand):
    help = "Выгрузить 25 самых грязных задач для ручной проверки. Только чтение."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=25)
        parser.add_argument("--out", type=str, default="dirty_sample.txt")

    def handle(self, *args, **opts):
        qs = (Problem.objects.filter(status="published", multiple_problems=False)
              .prefetch_related("parts", "source_references__source"))

        scored = []  # (score, sig, id, source, body)
        for p in qs.iterator(chunk_size=300):
            src = get_source_name(p)
            if "ile" in src.lower() or "iloveeconomics" in src.lower():
                continue
            body = body_text(p)
            score, sig = dirt_score(body)
            if score >= 1:
                scored.append((score, sig, p.id, src, body))

        scored.sort(key=lambda t: -t[0])
        sample = scored[:opts["count"]]

        lines = [f"25 самых грязных задач (из {len(scored):,} с порогом ≥1). "
                 f"Проверь: это настоящая порча текста или ложное срабатывание?", ""]
        for score, sig, pid, src, body in sample:
            lines.append("=" * 80)
            lines.append(f"ЗАДАЧА #{pid} | {src} | грязь={score}")
            lines.append(f"сработали признаки: {', '.join(sig)}")
            lines.append("-" * 80)
            lines.append(body.strip())
            lines.append("")

        with open(opts["out"], "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        self.stdout.write(f"Грязных задач всего (≥1): {len(scored):,}")
        self.stdout.write(f"Выгружено {len(sample)} самых грязных в {opts['out']}")
