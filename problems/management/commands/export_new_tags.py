"""
Выгрузка новых тегов (вне канона) с частотой ≥ порога из batch1_parsed.jsonl в файл.
Только чтение файла. Ничего не меняет, к API/базе не обращается.
"""
import json
from collections import Counter

from django.core.management.base import BaseCommand

# Исходный канон (совпадает с ALLOWED_TAGS из submit_batch1.py).
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

THRESHOLD = 20


def norm(tag: str) -> str:
    return (tag or "").strip().lower()


class Command(BaseCommand):
    help = "Выгрузить новые теги (вне канона) с частотой ≥20 из batch1_parsed.jsonl в файл."

    def add_arguments(self, parser):
        parser.add_argument("--file", type=str, default="batch1_parsed.jsonl")
        parser.add_argument("--out", type=str, default="new_tags_ge20.txt")
        parser.add_argument("--threshold", type=int, default=THRESHOLD)

    def handle(self, *args, **opts):
        thr = opts["threshold"]
        allowed_norm = {norm(t) for t in ALLOWED_TAGS}

        counter = Counter()
        display = {}
        lines = 0

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
                    if not n or n in allowed_norm:
                        continue
                    counter[n] += 1
                    if n not in display:
                        display[n] = tg.strip()

        passed = sorted([(c, display[t]) for t, c in counter.items() if c >= thr], reverse=True)

        with open(opts["out"], "w", encoding="utf-8") as fout:
            fout.write(f"# Новые теги с частотой >= {thr}. Всего: {len(passed)}.\n")
            fout.write(f"# (прочитано строк: {lines}; разных новых тегов всего: {len(counter)})\n\n")
            for c, t in passed:
                fout.write(f"{c}\t{t}\n")

        self.stdout.write(f"Прочитано строк: {lines:,}")
        self.stdout.write(f"Новых тегов всего: {len(counter):,}")
        self.stdout.write(f"С частотой ≥{thr}: {len(passed)} — записаны в {opts['out']}")
