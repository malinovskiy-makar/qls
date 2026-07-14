"""
Выгружает детерминированную случайную выборку задач ILE в JSON для ИИ-чистки.
ТОЛЬКО ЧИТАЕТ базу — никаких .save(), никаких изменений данных.

Порядок выгрузки заморожен в reports/ai_cleanup_ile/shuffle_order_seed2026.json.
Перед первым использованием (или после восстановления) запустить:
    ./venv/bin/python manage.py export_ile_for_review --build-order
"""
import json
import random
from datetime import datetime, timezone
from pathlib import Path

from django.core.management.base import BaseCommand

from problems.models import Problem, Source, SourceReference

ORDER_FILE = Path("reports/ai_cleanup_ile/shuffle_order_seed2026.json")

# Файлы уже выгруженных партий — используются в --build-order для восстановления
# задач, которые были скрыты apply_ile_cleanup после выгрузки.
EXISTING_BATCH_FILES = [
    Path("reports/ai_cleanup_ile/pilot_batch_raw.json"),
    Path("reports/ai_cleanup_ile/batch_01_raw.json"),
    Path("reports/ai_cleanup_ile/batch_02_raw.json"),
]


def _load_ile_source():
    return (
        Source.objects.filter(name__icontains="ILE").first()
        or Source.objects.filter(name__icontains="iloveeconomics").first()
        or Source.objects.filter(id=2).first()
    )


def _build_url_map(ile):
    return {
        ref.problem_id: ref.url or ""
        for ref in SourceReference.objects.filter(source=ile).only("problem_id", "url")
    }


def _serialize_problem(p, url_by_problem):
    parts = []
    for part in p.parts.all().order_by("order", "label"):
        parts.append({
            "label": part.label,
            "statement": part.statement,
            "answer": part.answer,
            "points": float(part.points) if part.points is not None else None,
        })
    return {
        "id": p.id,
        "url": url_by_problem.get(p.id, ""),
        "title": p.title,
        "problem_type": p.problem_type,
        "difficulty": p.difficulty,
        "difficulty_native": p.difficulty_native,
        "statement": p.statement,
        "answer": p.answer,
        "solution": p.solution,
        "parts": parts,
    }


class Command(BaseCommand):
    help = (
        "Выгружает детерминированную выборку задач ILE в JSON для ИИ-чистки "
        "(ТОЛЬКО чтение). Порядок читается из заморозки; "
        "используй --build-order для первоначальной генерации файла порядка."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--seed", type=int, default=2026,
            help="Зерно случайности (по умолч. 2026); должно совпадать с файлом порядка",
        )
        parser.add_argument(
            "--offset", type=int, default=0,
            help="Пропустить первые N задач из порядкового списка",
        )
        parser.add_argument(
            "--count", type=int, default=30,
            help="Сколько задач выгрузить",
        )
        parser.add_argument(
            "--out", type=str,
            default="reports/ai_cleanup_ile/pilot_batch_raw.json",
            help="Путь к выходному JSON-файлу",
        )
        parser.add_argument(
            "--build-order", action="store_true",
            help=(
                "Построить (или пересобрать) файл заморозки порядка. "
                "Валидирует против уже выгруженных партий (пилот, 01, 02). "
                "Только если все проверки PASS — записывает файл."
            ),
        )

    # ------------------------------------------------------------------ #
    #  Режим --build-order                                                 #
    # ------------------------------------------------------------------ #

    def _run_build_order(self, seed):
        self.stdout.write("=== Режим --build-order ===")

        ile = _load_ile_source()
        if not ile:
            self.stderr.write("ОШИБКА: источник ILE не найден.")
            return
        self.stdout.write(f"Источник ILE: id={ile.id}, name={ile.name!r}")

        url_by_problem = _build_url_map(ile)

        # Шаг 1: текущий пул published
        published_ids = set(
            Problem.objects.filter(
                id__in=list(url_by_problem.keys()),
                status="published",
            ).values_list("id", flat=True)
        )
        self.stdout.write(f"Текущих published ILE: {len(published_ids)}")

        # Шаг 2: дочитать id из уже выгруженных файлов (восстановление скрытых)
        extra_ids = set()
        for batch_file in EXISTING_BATCH_FILES:
            if batch_file.exists():
                data = json.loads(batch_file.read_text(encoding="utf-8"))
                file_ids = {r["id"] for r in data}
                new_here = file_ids - published_ids - extra_ids
                self.stdout.write(
                    f"  {batch_file.name}: {len(file_ids)} id "
                    f"({len(new_here)} не в published — восстановлено)"
                )
                extra_ids |= file_ids
            else:
                self.stdout.write(f"  {batch_file.name}: файл не найден, пропускаем")

        full_pool = sorted(published_ids | extra_ids)
        self.stdout.write(f"Полный пул (published ∪ выгруженные ранее): {len(full_pool)}")

        # Шаг 3: тасовка — тот же способ, что и исходная команда
        rng = random.Random(seed)
        shuffled = full_pool[:]
        rng.shuffle(shuffled)

        # Шаг 4: валидация против трёх уже выгруженных файлов
        validation_specs = [
            ("пилот",     0,   30,  EXISTING_BATCH_FILES[0]),
            ("batch_01",  30,  330, EXISTING_BATCH_FILES[1]),
            ("batch_02",  330, 630, EXISTING_BATCH_FILES[2]),
        ]

        all_pass = True
        for name, lo, hi, batch_file in validation_specs:
            if not batch_file.exists():
                self.stdout.write(f"  [{name}] SKIP — файл отсутствует")
                continue

            expected = {r["id"] for r in json.loads(batch_file.read_text(encoding="utf-8"))}
            actual   = set(shuffled[lo:hi])
            inter    = expected & actual
            missing  = expected - actual
            extra    = actual - expected

            if expected == actual:
                self.stdout.write(self.style.SUCCESS(
                    f"  [{name}] PASS — {len(inter)} id совпали (offset {lo}..{hi})"
                ))
            else:
                self.stderr.write(
                    f"  [{name}] FAIL — "
                    f"совпало {len(inter)}/{len(expected)}, "
                    f"недостаёт {len(missing)}, лишних {len(extra)}\n"
                    f"    Примеры недостающих: {sorted(missing)[:10]}\n"
                    f"    Примеры лишних:      {sorted(extra)[:10]}"
                )
                all_pass = False

        if not all_pass:
            self.stderr.write(
                "\nФайл порядка НЕ записан — одна или несколько валидаций FAIL.\n"
                "Проверь: (1) пул строится так же, как при первоначальной выгрузке, "
                "(2) все batch-файлы не повреждены."
            )
            return

        # Шаг 5: идемпотентная запись файла порядка
        ORDER_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "seed": seed,
            "pool_size": len(full_pool),
            "built_at": datetime.now(timezone.utc).isoformat(),
            "order": shuffled,
        }
        ORDER_FILE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(
            f"\nВсе проверки PASS. Файл порядка записан → {ORDER_FILE} "
            f"(pool_size={len(full_pool)}, seed={seed})"
        ))

    # ------------------------------------------------------------------ #
    #  Обычный режим выгрузки                                             #
    # ------------------------------------------------------------------ #

    def _run_export(self, seed, offset, count, out_path):
        # Загрузить файл порядка
        if not ORDER_FILE.exists():
            self.stderr.write(
                f"ОШИБКА: файл порядка не найден ({ORDER_FILE}).\n"
                "Сначала запустите:\n"
                "  ./venv/bin/python manage.py export_ile_for_review --build-order"
            )
            return

        order_data = json.loads(ORDER_FILE.read_text(encoding="utf-8"))
        if order_data["seed"] != seed:
            self.stderr.write(
                f"ОШИБКА: --seed={seed} не совпадает с seed={order_data['seed']} "
                f"в файле порядка ({ORDER_FILE})."
            )
            return

        full_order = order_data["order"]
        self.stdout.write(
            f"Файл порядка: pool_size={order_data['pool_size']}, seed={order_data['seed']}, "
            f"built_at={order_data['built_at']}"
        )

        target_ids = full_order[offset: offset + count]
        self.stdout.write(
            f"Выбрано {len(target_ids)} задач (offset={offset}, count={count})."
        )

        # Источник ILE нужен для url_by_problem
        ile = _load_ile_source()
        if not ile:
            self.stderr.write("ОШИБКА: источник ILE не найден.")
            return
        url_by_problem = _build_url_map(ile)

        # Достаём задачи без фильтра по статусу (порядок задаёт файл)
        found_qs = (
            Problem.objects.filter(id__in=target_ids)
            .prefetch_related("parts")
        )
        found_ids = {p.id for p in found_qs}

        # Предупреждение о пропущенных id
        missing = set(target_ids) - found_ids
        if missing:
            self.stdout.write(
                self.style.WARNING(
                    f"Предупреждение: {len(missing)} id не найдены в БД: {sorted(missing)}"
                )
            )

        hidden_ids = {
            p.id for p in found_qs
            if p.status not in ("published", "draft", "needs_review", "archived")
        }
        if hidden_ids:
            self.stdout.write(
                self.style.WARNING(
                    f"Предупреждение: {len(hidden_ids)} задач не в published: {sorted(hidden_ids)}"
                )
            )

        # Сериализация в порядке target_ids
        order_map = {pid: i for i, pid in enumerate(target_ids)}
        records = sorted(
            [_serialize_problem(p, url_by_problem) for p in found_qs],
            key=lambda r: order_map[r["id"]],
        )

        # Запись JSON
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(
            f"Записано {len(records)} задач → {out_path}"
        ))

        # Мета-файл
        meta_path = out_path.with_name(out_path.stem + "_meta.txt")
        meta_path.write_text(
            f"seed={seed}\n"
            f"offset={offset}\n"
            f"count={count}\n"
            f"ile_source_id={ile.id}\n"
            f"order_file={ORDER_FILE}\n"
            f"chosen_ids={','.join(str(i) for i in target_ids)}\n",
            encoding="utf-8",
        )
        self.stdout.write(f"Мета → {meta_path}")

    # ------------------------------------------------------------------ #
    #  Точка входа                                                         #
    # ------------------------------------------------------------------ #

    def handle(self, *args, **opts):
        seed = opts["seed"]

        if opts["build_order"]:
            self._run_build_order(seed)
        else:
            out_path = Path(opts["out"])
            self._run_export(seed, opts["offset"], opts["count"], out_path)
