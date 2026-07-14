"""
Выгрузка случайной выборки опубликованных задач в текстовый файл — для ручного
превью ИИ-обогащения (дано/найти + теги + чистка). ТОЛЬКО ЧТЕНИЕ: база не меняется,
API не вызывается.
"""
from typing import List, Optional
import random

from django.core.management.base import BaseCommand
from problems.models import Problem


def get_source_name(problem) -> str:
    """
    Источник задачи идёт через SourceReference (не прямой FK).
    Берём первую ссылку; если их нет — «—».
    """
    refs = list(problem.source_references.all())
    if refs:
        return refs[0].source.name
    return "—"


class Command(BaseCommand):
    help = "Выгрузить N случайных опубликованных задач в файл для превью (только чтение)."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=25,
                            help="Сколько задач выгрузить (по умолчанию 25).")
        parser.add_argument("--exclude-source", type=str, default="ILE",
                            help="Исключить источник по подстроке имени (регистр неважен).")
        parser.add_argument("--out", type=str, default="sample_for_preview.txt",
                            help="Имя файла (по умолчанию sample_for_preview.txt в корне проекта).")
        parser.add_argument("--seed", type=int, default=None,
                            help="Зерно случайности для воспроизводимости (необязательно).")

    def handle(self, *args, **opts):
        count = opts["count"]
        exclude = (opts["exclude_source"] or "").strip().lower()
        out_path = opts["out"]
        if opts["seed"] is not None:
            random.seed(opts["seed"])

        # source_references__source — один prefetch покрывает и ссылки, и источник
        qs = (Problem.objects
              .filter(status="published")
              .prefetch_related("parts", "topics", "source_references__source"))

        all_published = list(qs)
        self.stdout.write(f"Опубликованных задач всего: {len(all_published):,}")

        # Собираем статистику по источникам
        counts = {}
        for p in all_published:
            name = get_source_name(p)
            counts[name] = counts.get(name, 0) + 1

        self.stdout.write("")
        self.stdout.write("=== ИСТОЧНИКИ (опубликованные) ===")
        for name in sorted(counts, key=lambda k: -counts[k]):
            mark = "  <-- ИСКЛЮЧЁН" if (exclude and exclude in name.lower()) else ""
            self.stdout.write(f"  {counts[name]:>6,}  {name}{mark}")

        # Кандидаты — без исключённого источника
        if exclude:
            eligible = [p for p in all_published if exclude not in get_source_name(p).lower()]
        else:
            eligible = list(all_published)

        excluded_n = len(all_published) - len(eligible)
        self.stdout.write("")
        if exclude and excluded_n == 0:
            self.stdout.write(
                f"⚠️  Источник по подстроке «{opts['exclude_source']}» НЕ найден — "
                f"в выборку попадут ВСЕ опубликованные. Посмотри список выше и "
                f"перезапусти: manage.py export_preview_sample "
                f"--exclude-source \"<имя из списка>\""
            )
        else:
            self.stdout.write(
                f"Исключено по «{opts['exclude_source']}»: {excluded_n:,}. "
                f"Кандидатов: {len(eligible):,}."
            )

        if not eligible:
            self.stdout.write("Нет подходящих задач — нечего выгружать.")
            return

        k = min(count, len(eligible))
        sample = random.sample(eligible, k)

        lines: List[str] = []
        lines.append(f"Случайная выборка опубликованных задач для превью обогащения. Всего: {k}.")
        lines.append(f"(Исключён источник по подстроке: «{opts['exclude_source']}».)")
        lines.append("")

        for p in sample:
            topics = ", ".join(t.name for t in p.topics.all()) or "—"
            diff = getattr(p, "difficulty_native", None) or getattr(p, "difficulty", None) or "—"
            has_sol = "да" if (getattr(p, "solution", "") or "").strip() else "нет"
            has_ans = "да" if (getattr(p, "answer", "") or "").strip() else "нет"

            lines.append("=" * 80)
            lines.append(f"ЗАДАЧА #{p.id}")
            lines.append(f"Источник: {get_source_name(p)}")
            lines.append(f"Темы: {topics}")
            lines.append(f"Сложность: {diff}   |   Есть решение: {has_sol}   |   Есть ответ: {has_ans}")
            lines.append("-" * 80)
            lines.append(f"ЗАГОЛОВОК: {p.title or '—'}")
            lines.append("")
            lines.append("УСЛОВИЕ:")
            lines.append((p.statement or "—").strip())

            parts = list(p.parts.all())
            if parts:
                lines.append("")
                lines.append("ПОДПУНКТЫ:")
                for part in parts:
                    st = (part.statement or "").strip()
                    label = part.label or str(part.order)
                    lines.append(f"  ({label}) {st}")

            lines.append("")

        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        self.stdout.write("")
        self.stdout.write(f"✅ Готово. Выгружено задач: {k}. Файл: {out_path}")
