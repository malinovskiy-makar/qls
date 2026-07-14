"""
Точная оценка стоимости Батча 2 (чистка + вынос решений) по реальной базе.
API НЕ вызывается, деньги не тратятся, база не меняется (только чтение).
Ввод считается точно; вывод — вилкой по сценариям (доля грязных × доля решений).
"""
from typing import Optional, List
from django.core.management.base import BaseCommand
from problems.models import Problem

SYS_EST_CHARS = 1600          # длина системной инструкции (оценка)
VERDICT_TOKENS = 120          # короткий JSON-вердикт на каждую задачу
SOLUTION_OUT_FRACTION = 0.60  # вынесенное решение ≈ 60% длины тела (грубо)
DIRTY_SHARES = [0.10, 0.15, 0.20]
SOLUTION_SHARES = [0.10, 0.20, 0.30]
# Sonnet: (ввод, вывод) $/млн
RATE_BATCH = (1.50, 7.50)
RATE_FULL = (3.00, 15.00)


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


def load_tok():
    try:
        import tiktoken
        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


class Command(BaseCommand):
    help = "Точная оценка стоимости Батча 2 по реальной базе. API НЕ вызывается."

    def handle(self, *args, **opts):
        enc = load_tok()
        qs = (Problem.objects.filter(status="published", multiple_problems=False)
              .prefetch_related("parts", "source_references__source"))

        n = 0
        skipped_ile = 0
        body_tokens_total = 0      # токены тел задач (для вывода-переписывания)
        input_tokens_total = 0     # ввод: (инструкция + тело) на каждую задачу
        char_fallback = 0

        for p in qs.iterator(chunk_size=300):
            src = get_source_name(p)
            if "ile" in src.lower() or "iloveeconomics" in src.lower():
                skipped_ile += 1
                continue
            n += 1
            body = body_text(p)
            if enc is not None:
                bt = len(enc.encode(body))
                it = len(enc.encode("x" * SYS_EST_CHARS)) + bt  # инструкция + тело
            else:
                bt = int(len(body) / 2.23)
                it = int((SYS_EST_CHARS + len(body)) / 2.23)
                char_fallback += 1
            body_tokens_total += bt
            input_tokens_total += it

        self.stdout.write(f"Пул (опубликованные без ILE и склеек): {n:,} (ILE исключено: {skipped_ile:,})")
        if enc is None:
            self.stdout.write("⚠️ tiktoken не установлен — считаю по среднему (2.23 симв/токен, ±15%).")
            self.stdout.write("   Для точности: ./venv/bin/pip install tiktoken  и запусти снова.")
        self.stdout.write("")
        self.stdout.write(f"ВВОД (точно): {input_tokens_total/1e6:.2f} млн токенов "
                          f"(чтение всех задач + инструкция).")
        self.stdout.write(f"Суммарный объём тел задач: {body_tokens_total/1e6:.2f} млн токенов.")
        verdict_total = VERDICT_TOKENS * n
        self.stdout.write(f"Короткие вердикты (фикс): {verdict_total/1e6:.2f} млн токенов вывода.")
        self.stdout.write("")

        def total_cost(dirty_share, sol_share, rate):
            in_rate, out_rate = rate
            out_tok = verdict_total
            out_tok += dirty_share * body_tokens_total            # переписанные грязные
            out_tok += sol_share * body_tokens_total * SOLUTION_OUT_FRACTION  # вынесенные решения
            return input_tokens_total / 1e6 * in_rate + out_tok / 1e6 * out_rate

        self.stdout.write("=== СТОИМОСТЬ, Sonnet + Batch API (−50%) ===")
        self.stdout.write("строки — доля грязных; столбцы — доля задач с запечённым решением")
        header = "  грязь\\решен " + "".join(f"{int(s*100):>8}%" for s in SOLUTION_SHARES)
        self.stdout.write(header)
        for d in DIRTY_SHARES:
            row = f"  {int(d*100):>9}%  " + "".join(
                f"{'$'+format(total_cost(d, s, RATE_BATCH), '.0f'):>9}" for s in SOLUTION_SHARES)
            self.stdout.write(row)

        # Опорная точка + верхняя граница без Batch.
        mid = total_cost(0.15, 0.20, RATE_BATCH)
        hi = total_cost(0.20, 0.30, RATE_FULL)
        self.stdout.write("")
        self.stdout.write(f"Опорная оценка (грязь 15%, решения 20%, Batch): ~${mid:.0f}")
        self.stdout.write(f"Верхняя граница (грязь 20%, решения 30%, БЕЗ Batch): ~${hi:.0f}")
        self.stdout.write("")
        self.stdout.write("Примечание: ввод посчитан точно; вывод зависит от реальных долей "
                          "грязных задач и запечённых решений — отсюда вилка.")
