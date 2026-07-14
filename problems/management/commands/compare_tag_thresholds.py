"""
Сравнение порогов частоты для НОВЫХ тегов из batch1_parsed.jsonl.
Только чтение файла. Ничего не меняет, к API/базе не обращается.
"""
import json
from collections import Counter

from django.core.management.base import BaseCommand

# Исходный канон (должен совпадать с ALLOWED_TAGS из submit_batch1.py).
ALLOWED_TAGS = [
    "эластичность спроса по цене", "точечная эластичность", "постоянная эластичность",
    "линейный спрос", "рыночное равновесие", "потребительский излишек",
    "функция издержек", "предельные издержки", "кусочные издержки",
    "функция предложения фирмы", "минимизация издержек", "многозаводская фирма",
    "дискретный выпуск", "совершенная конкуренция", "монополия",
    "монополистическая конкуренция", "олигополия", "вход и выход фирм",
    "долгосрочное равновесие", "ценовая дискриминация первой степени",
    "ценовая дискриминация второй степени", "ценовая дискриминация третьей степени",
    "двухчастный тариф", "нелинейное ценообразование", "отрицательная экстерналия",
    "общественное благосостояние", "потоварный налог", "государственное регулирование",
    "прямые и косвенные налоги", "бюджетная система РФ", "обратная индукция",
    "последовательные игры", "голосование", "кривая производственных возможностей",
    "альтернативные издержки", "сравнительные преимущества", "выгоды обмена",
    "относительные цены", "совокупный спрос", "уровень цен", "темп инфляции",
    "номинальные и реальные величины", "экономический рост", "человеческий капитал",
    "качественный вопрос", "тестовый вопрос", "открытый ответ",
]

THRESHOLDS = [50, 40, 30]


def norm(tag: str) -> str:
    return (tag or "").strip().lower()


class Command(BaseCommand):
    help = "Сравнить пороги частоты для новых тегов (только чтение batch1_parsed.jsonl)."

    def add_arguments(self, parser):
        parser.add_argument("--file", type=str, default="batch1_parsed.jsonl")

    def handle(self, *args, **opts):
        allowed_norm = {norm(t) for t in ALLOWED_TAGS}

        new_counter = Counter()   # частота новых тегов (по нормализованному виду)
        display = {}              # нормализованный -> первый встреченный «красивый» вид
        lines = 0
        leaked_into_allowed = 0   # «новые», которые на деле уже в каноне (модель ошиблась)

        with open(opts["file"], encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                lines += 1
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                data = rec.get("data") or {}
                for tg in (data.get("new_tags") or []):
                    n = norm(tg)
                    if not n:
                        continue
                    if n in allowed_norm:
                        leaked_into_allowed += 1
                        continue
                    new_counter[n] += 1
                    if n not in display:
                        display[n] = tg.strip()

        self.stdout.write(f"Строк прочитано: {lines:,}")
        self.stdout.write(f"Разных новых тегов всего: {len(new_counter):,}")
        self.stdout.write(f"(«новых», по факту уже в каноне — пропущено: {leaked_into_allowed:,})")
        self.stdout.write("")

        self.stdout.write("=== СВОДКА ПО ПОРОГАМ ===")
        self.stdout.write(f"{'порог':>6} {'новых тегов':>12} {'итого канон':>12}")
        for thr in THRESHOLDS:
            passed = [t for t, c in new_counter.items() if c >= thr]
            self.stdout.write(f"{thr:>6} {len(passed):>12} {len(ALLOWED_TAGS) + len(passed):>12}")

        # Подробно: какие теги добавляет каждый порог (по «слоям»).
        srt = sorted(THRESHOLDS, reverse=True)  # 50, 40, 30
        prev = None
        for thr in srt:
            passed = sorted([(c, t) for t, c in new_counter.items() if c >= thr], reverse=True)
            self.stdout.write("")
            if prev is None:
                self.stdout.write(f"=== Теги с частотой ≥{thr} ({len(passed)} шт.) ===")
                for c, t in passed:
                    self.stdout.write(f"  {c:>5}  {display[t]}")
            else:
                # только новый слой: те, что проходят ≥thr, но не проходили ≥prev
                layer = sorted([(c, t) for t, c in new_counter.items()
                                if thr <= c < prev], reverse=True)
                self.stdout.write(f"=== Добавится при снижении порога {prev}→{thr} (+{len(layer)} шт.) ===")
                for c, t in layer:
                    self.stdout.write(f"  {c:>5}  {display[t]}")
            prev = thr
