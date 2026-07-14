"""
Оценка стоимости ИИ-обогащения (Пакет 1+2: дано/найти + темы/теги + чистка текста).
Считает РЕАЛЬНЫЙ объём текста по всей базе и переводит его в токены и доллары.
API НЕ вызывается, деньги не тратятся, база не меняется (только чтение).
Опционально использует локальный токенайзер tiktoken (если установлен) для уточнения.
"""
from typing import Optional, List, Dict
from collections import defaultdict
import statistics
import random

from django.core.management.base import BaseCommand
from problems.models import Problem

# Расценки Anthropic, $ за миллион токенов (ввод / вывод)
PRICING = {
    "Haiku 4.5":  {"in": 1.0,  "out": 5.0},
    "Sonnet 4.6": {"in": 3.0,  "out": 15.0},
}
BATCH = 0.5                 # Batch API: -50% на всё
INSTR_TOKENS = 500          # размер инструкции модели (фикс, на каждый запрос)
STRUCT_OUT_TOKENS = 200     # дано/найти + темы/теги в ответе
CPT_BAND = {"Дороже (конс.)": 2.5, "Центр": 2.8, "Дешевле (опт.)": 3.2}  # символ/токен


def build_input_text(p) -> str:
    """Полный текст условия, который увидит модель: заголовок + условие + подпункты."""
    chunks: List[str] = []
    if p.title:
        chunks.append(p.title)
    if p.statement:
        chunks.append(p.statement)
    for part in p.parts.all():
        s = getattr(part, "statement", None)
        if s:
            chunks.append(s)
    return "\n".join(chunks)


def load_tiktoken():
    try:
        import tiktoken
        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


def money(content_tokens: float, count: int, rate: Dict[str, float], batch: bool) -> float:
    input_tokens = content_tokens + INSTR_TOKENS * count
    output_tokens = content_tokens + STRUCT_OUT_TOKENS * count
    cost = input_tokens / 1e6 * rate["in"] + output_tokens / 1e6 * rate["out"]
    return cost * (BATCH if batch else 1.0)


class Command(BaseCommand):
    help = "Оценка стоимости ИИ-обогащения (Пакет 1+2) по реальной базе. API НЕ вызывается."

    def add_arguments(self, parser):
        parser.add_argument("--sample", type=int, default=500,
                            help="Размер выборки для замера ratio через tiktoken.")

    def handle(self, *args, **opts):
        sample_size = opts["sample"]
        qs = Problem.objects.all().prefetch_related("parts")
        total = qs.count()
        self.stdout.write(f"Задач в базе: {total:,}")
        if total == 0:
            self.stdout.write("Нет задач — нечего считать.")
            return

        enc = load_tiktoken()
        sample_ids = set()
        if enc is not None and total > sample_size:
            all_ids = list(Problem.objects.values_list("id", flat=True))
            sample_ids = set(random.sample(all_ids, sample_size))

        char_counts: List[int] = []
        total_chars = 0
        status_chars: Dict[str, int] = defaultdict(int)
        status_count: Dict[str, int] = defaultdict(int)
        sample_chars = 0
        sample_tokens = 0

        # chunk_size обязателен: иначе prefetch_related не работает с .iterator() в Django 4.2
        for p in qs.iterator(chunk_size=500):
            text = build_input_text(p)
            n = len(text)
            char_counts.append(n)
            total_chars += n
            st = getattr(p, "status", "—") or "—"
            status_chars[st] += n
            status_count[st] += 1
            if enc is not None and (p.id in sample_ids or not sample_ids):
                sample_chars += n
                sample_tokens += len(enc.encode(text))

        measured_cpt: Optional[float] = (sample_chars / sample_tokens) if (enc and sample_tokens) else None
        cpt_main = measured_cpt if measured_cpt is not None else CPT_BAND["Центр"]

        mean_c = statistics.mean(char_counts)
        median_c = statistics.median(char_counts)
        srt = sorted(char_counts)
        p90 = srt[int(0.90 * (len(srt) - 1))]
        p95 = srt[int(0.95 * (len(srt) - 1))]
        mx = srt[-1]

        self.stdout.write("")
        self.stdout.write("=== ОБЪЁМ ТЕКСТА (точно, по всей базе) ===")
        self.stdout.write(f"Всего символов в условиях: {total_chars:,}")
        self.stdout.write(f"На задачу: среднее {mean_c:.0f}, медиана {median_c:.0f}, "
                          f"p90 {p90:,}, p95 {p95:,}, макс {mx:,}")

        self.stdout.write("")
        self.stdout.write("=== РАЗБИВКА ПО СТАТУСУ (стоимость Haiku + Batch) ===")
        for st in sorted(status_chars, key=lambda k: -status_chars[k]):
            ct = status_chars[st] / cpt_main
            c = money(ct, status_count[st], PRICING["Haiku 4.5"], batch=True)
            self.stdout.write(f"  {st:<14} {status_count[st]:>6,} задач   "
                              f"{status_chars[st]:>12,} симв.   ${c:>6.0f}")

        self.stdout.write("")
        self.stdout.write("=== СТОИМОСТЬ — ВСЯ БАЗА ===")
        if measured_cpt is not None:
            shown = min(sample_size, total)
            self.stdout.write(f"ratio (замер tiktoken по {shown} задачам): {measured_cpt:.2f} символ/токен")
            self.stdout.write("  (tiktoken — токенайзер OpenAI, близкий, но не идентичный Anthropic; ±~15%)")
            self._table(total_chars, total, measured_cpt)
        else:
            self.stdout.write("tiktoken не установлен — показываю диапазон по типичному ratio для русского.")
            self.stdout.write("Чтобы уточнить: ./venv/bin/pip install tiktoken  и запусти снова.")
            for label, cpt in CPT_BAND.items():
                self.stdout.write("")
                self.stdout.write(f"-- {label}, ratio {cpt:.2f} --")
                self._table(total_chars, total, cpt)

        instr_full = (INSTR_TOKENS * total) / 1e6 * PRICING["Haiku 4.5"]["in"] * BATCH
        instr_cached = instr_full * 0.1
        self.stdout.write("")
        self.stdout.write(f"Кэширование инструкции (Haiku+Batch): экономия ~${instr_full - instr_cached:.0f} "
                          f"(инструкция ${instr_full:.0f} -> ${instr_cached:.0f}).")
        self.stdout.write("")
        self.stdout.write("ИТОГ: ориентир — строка 'Haiku 4.5 ... Batch'. Это рекомендуемый вариант.")

    def _table(self, chars: int, count: int, cpt: float):
        ct = chars / cpt
        input_tok = ct + INSTR_TOKENS * count
        output_tok = ct + STRUCT_OUT_TOKENS * count
        self.stdout.write(f"Токены: ввод ~{input_tok/1e6:.2f} млн, вывод ~{output_tok/1e6:.2f} млн")
        self.stdout.write(f"{'Модель':<12} {'полная':>10} {'Batch':>10}")
        for model, rate in PRICING.items():
            full = money(ct, count, rate, batch=False)
            batch = money(ct, count, rate, batch=True)
            full_s = "$" + format(full, ".0f")
            batch_s = "$" + format(batch, ".0f")
            self.stdout.write(f"{model:<12} {full_s:>10} {batch_s:>10}")
