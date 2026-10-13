# -*- coding: utf-8 -*-
"""
Фаза 2: скачать каждую задачу из hashes.json и положить на диск как есть.

Обычный скрипт, НЕ management command — Django и база не участвуют
(см. CLAUDE.md сессии: в базу данных не пишем ничего).

Способ — tRPC JSON API сайта: GET .../trpc/problems.getByHash?input={"hash":H}.
Найден и провалидирован в Фазе 0; сверен с альтернативным способом (RSC-поток,
см. rsc_reserve.py) на пяти контрольных задачах — наборы полей идентичны,
значения совпадают побитово (Проверка A, отчёт сессии). Резерв НЕ подключается
сюда автоматически: если tRPC откажет посреди прогона — остановиться и
разобраться, а не молча смешать два способа получения данных в одном банке.

Запуск:
    python scripts/solvehub/fetch_problems.py                # обычный прогон
    python scripts/solvehub/fetch_problems.py --limit 20      # пробный прогон
    python scripts/solvehub/fetch_problems.py --retry-failed  # только то, что отвалилось

Перекачка в новую папку с полным списком пунктов (13.10.2026, баг «только problems[0]»):
    python scripts/solvehub/fetch_problems.py --out-dir <папка>/solvehub_v2/problems --resume

ВАЖНО про формат ответа. SolveHub хранит каждый пункт задачи («б)», «в)»…) отдельной
записью и отдаёт ВСЕ записи в списке problems одного ответа: problems[0] — сама задача,
каждая следующая — пункт (parent_hash = хэш ПРЕДЫДУЩЕЙ записи). Раньше сохранялась
только problems[0], и пункты б), в)… терялись. Теперь в файле: прежние поля первой
записи (обратная совместимость) + `_parts` (все записи по порядку, включая первую) +
`_parts_count`.
"""
import argparse
import copy
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# Все данные — вне репозитория. Меняется в одном месте.
DATA_DIR = Path(r"C:\Users\shipu\weconomics-data\solvehub")
PROBLEMS_DIR = DATA_DIR / "problems"
HASHES_FILE = DATA_DIR / "hashes.json"
FAILED_FILE = DATA_DIR / "failed.json"

API = "https://api.prod.solvehub.app/trpc"
HEADERS = {
    "User-Agent": "Weconomics-import/1.0 (+https://t.me/lengler)",
    "x-subject-label": "econ",
    "Accept": "*/*",
}
REQUEST_TIMEOUT = 40  # секунд с запасом — сеть у нас самих временами медленная, это не отказ
PAUSE_BETWEEN_REQUESTS = 1.5  # секунд, строго один запрос за раз — сервер слабый
RETRY_DELAYS = [5, 15, 45, 120]  # секунд, при 503/429/таймауте/обрыве соединения
PROGRESS_EVERY = 50
MAX_CONSECUTIVE_FAILURES = 20  # если сервер лёг совсем — сдаться честно, а не молотить сутки впустую
RATE_LIMIT_DELAY = 60  # секунд ждать после 429, прежде чем повторить тот же хэш
MAX_CONSECUTIVE_BLOCKS = 3  # 429/403/503 подряд столько раз — остановиться, а не молотить
BLOCK_STATUSES = (429, 403, 503)

# Счётчики на весь процесс: сколько HTTP-запросов ушло и сколько блокировок подряд.
_stats = {"requests": 0, "blocks_in_a_row": 0}


class ServerBlocked(Exception):
    """Сервер отвечает 429/403/503 подряд — прогон нужно остановить, а не продолжать."""


class RequestBudgetExceeded(Exception):
    """Выбран лимит запросов на прогон (--max-requests)."""


# None — без лимита; main() выставляет из --max-requests.
_request_limit = None


def extract_problems(data):
    """Достаёт список записей problems из ответа tRPC. Пустой список — понятная ошибка."""
    try:
        problems = data[0]["result"]["data"]["json"].get("problems") or []
    except (KeyError, IndexError, TypeError, AttributeError) as e:
        raise RuntimeError(f"неожиданная форма ответа problems.getByHash: {e!r}")
    if not problems:
        raise RuntimeError("пустой ответ problems.getByHash (задача не найдена?)")
    return problems


def build_record(problems):
    """Запись для сохранения: поля первой записи как раньше + `_parts` со ВСЕМИ записями.

    `_parts[0]` повторяет саму задачу (глубокая копия, чтобы в JSON не было циклической
    ссылки). `_parts_count` = len(problems).
    """
    record = dict(problems[0])
    record["_parts"] = copy.deepcopy(problems)
    record["_parts_count"] = len(problems)
    return record


def fetch_problem(hash_):
    """Возвращает запись задачи со всеми пунктами (см. build_record).

    Бросает исключение, если все попытки исчерпаны. ServerBlocked — если сервер
    MAX_CONSECUTIVE_BLOCKS раз подряд ответил 429/403/503 (дальше молотить нельзя).
    """
    input_obj = {"0": {"json": {"hash": hash_}}}
    params = {"batch": "1", "input": json.dumps(input_obj, separators=(",", ":"))}
    url = f"{API}/problems.getByHash"

    last_exc = None
    for attempt, delay in enumerate([0] + RETRY_DELAYS):
        if delay:
            print(f"    {hash_}: попытка {attempt + 1}/5 через {delay} с...", flush=True)
            time.sleep(delay)
        if _request_limit is not None and _stats["requests"] >= _request_limit:
            raise RequestBudgetExceeded(f"исчерпан лимит запросов ({_request_limit})")
        _stats["requests"] += 1
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        except (requests.ConnectionError, requests.Timeout) as e:
            last_exc = e
            continue
        if r.status_code in BLOCK_STATUSES:
            _stats["blocks_in_a_row"] += 1
            if _stats["blocks_in_a_row"] >= MAX_CONSECUTIVE_BLOCKS:
                raise ServerBlocked(
                    f"{_stats['blocks_in_a_row']} ответа подряд {r.status_code} (хэш {hash_})"
                )
            last_exc = RuntimeError(f"HTTP {r.status_code}")
            if r.status_code == 429:
                # Сервер просит притормозить: ждём минуту и повторяем ТОТ ЖЕ хэш.
                print(f"    {hash_}: 429, пауза {RATE_LIMIT_DELAY} с", flush=True)
                time.sleep(RATE_LIMIT_DELAY)
            continue
        _stats["blocks_in_a_row"] = 0
        r.raise_for_status()
        return build_record(extract_problems(r.json()))
    raise last_exc or RuntimeError("не удалось получить данные")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Фаза 2: скачать задачи SolveHub по списку хэшей")
    p.add_argument("--limit", type=int, default=None, help="скачать не больше N задач (пробный прогон)")
    p.add_argument("--retry-failed", action="store_true", help="повторить только хэши из failed.json")
    p.add_argument("--out-dir", type=Path, default=None,
                   help="куда писать файлы задач (по умолчанию solvehub/problems). "
                        "С ним failed.json и journal.jsonl лежат в родителе этой папки")
    p.add_argument("--hashes-file", type=Path, default=None,
                   help="файл со списком хэшей: JSON {\"hashes\": [...]} или по хэшу в строке (по умолчанию hashes.json)")
    p.add_argument("--resume", action="store_true",
                   help="пропускать хэши, у которых файл уже есть и в нём есть `_parts`")
    p.add_argument("--max-requests", type=int, default=None,
                   help="потолок HTTP-запросов за прогон (включая повторы); по достижении остановиться")
    return p.parse_args(argv)


def load_hashes(path):
    """Хэши из JSON ({"hashes": [...]} или просто список) либо из текста по хэшу в строке."""
    text = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except ValueError:
        return [line.strip() for line in text.splitlines() if line.strip()]
    return data["hashes"] if isinstance(data, dict) else list(data)


def has_parts(path):
    """Файл задачи уже в новом формате (есть `_parts`)? Битый/недописанный файл — нет."""
    try:
        with open(path, encoding="utf-8") as f:
            return "_parts" in json.load(f)
    except (OSError, ValueError):
        return False


def write_json_atomic(path, obj):
    """Пишем во временный файл и переименовываем: оборванный прогон не оставит полфайла."""
    tmp = Path(str(path) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def append_journal(path, hash_, status, parts, error=None):
    """Чекпоинт после каждого хэша: одна строка JSON."""
    if path is None:
        return
    row = {
        "hash": hash_,
        "status": status,
        "parts": parts,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    if error:
        row["error"] = str(error)[:300]
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_failed(path):
    if not path.exists():
        return set()
    with open(path, encoding="utf-8") as f:
        return set(json.load(f).get("failed", []))


def save_failed(path, failed_set):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {"updated_at": datetime.now(timezone.utc).isoformat(), "failed": sorted(failed_set)},
            f,
            ensure_ascii=False,
            indent=2,
        )


def main(argv=None):
    global _request_limit
    args = parse_args(argv)
    _request_limit = args.max_requests

    problems_dir = args.out_dir or PROBLEMS_DIR
    hashes_file = args.hashes_file or HASHES_FILE
    if args.out_dir:
        failed_file = args.out_dir.parent / "failed.json"
        journal_file = args.out_dir.parent / "journal.jsonl"
    else:
        failed_file = FAILED_FILE
        journal_file = None

    if not hashes_file.exists():
        print(f"Не найден {hashes_file} — сначала запусти collect_hashes.py")
        raise SystemExit(1)

    problems_dir.mkdir(parents=True, exist_ok=True)
    all_hashes = load_hashes(hashes_file)
    failed_set = load_failed(failed_file)

    if args.retry_failed:
        todo = [h for h in all_hashes if h in failed_set]
        print(f"Режим --retry-failed: к повтору {len(todo)} хэшей из {failed_file.name}")
    else:
        if args.resume:
            todo = [h for h in all_hashes if not has_parts(problems_dir / f"{h}.json")]
        else:
            todo = [h for h in all_hashes if not (problems_dir / f"{h}.json").exists()]
        already_done = len(all_hashes) - len(todo)
        print(f"Всего хэшей: {len(all_hashes)}. Уже скачано: {already_done}. К выгрузке: {len(todo)}")

    if args.limit:
        todo = todo[: args.limit]
        print(f"--limit {args.limit}: ограничиваю прогон {len(todo)} задачами")

    total = len(todo)
    if total == 0:
        print("Нечего скачивать.")
        return

    start_time = time.time()
    done = 0
    newly_failed = 0
    consecutive_failures = 0

    for i, h in enumerate(todo):
        try:
            problem = fetch_problem(h)
            problem["_fetched_at"] = datetime.now(timezone.utc).isoformat()
            problem["_source_url"] = f"https://solvehub.app/econ/problems/{h}"
            write_json_atomic(problems_dir / f"{h}.json", problem)
            append_journal(journal_file, h, "ok", problem["_parts_count"])
            failed_set.discard(h)
            consecutive_failures = 0
        except (ServerBlocked, RequestBudgetExceeded) as e:
            # Не молотим: чекпоинт уже на диске (файлы + журнал), сообщаем, как продолжить.
            append_journal(journal_file, h, "stopped", 0, e)
            save_failed(failed_file, failed_set)
            resume_cmd = "python scripts/solvehub/fetch_problems.py --resume"
            if args.out_dir:
                resume_cmd += f' --out-dir "{args.out_dir}"'
            if args.hashes_file:
                resume_cmd += f' --hashes-file "{args.hashes_file}"'
            print(
                f"\nОСТАНОВКА: {e}. Сделано в этом прогоне: {done} из {total}. "
                f"Продолжить позже командой:\n    {resume_cmd}",
                flush=True,
            )
            return
        except Exception as e:
            print(f"    {h}: ОТКАЗ после всех попыток — {e}", flush=True)
            append_journal(journal_file, h, "failed", 0, e)
            failed_set.add(h)
            newly_failed += 1
            consecutive_failures += 1

        done += 1

        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            save_failed(failed_file, failed_set)
            print(
                f"\nСервер похоже недоступен: {consecutive_failures} задач подряд ушли "
                f"в отказ. Остановился на задаче {done} из {total}. Запусти скрипт снова "
                f"позже — уже скачанное и список отказов сохранены, продолжится с места "
                f"остановки.",
                flush=True,
            )
            return

        if done % PROGRESS_EVERY == 0 or done == total:
            elapsed = time.time() - start_time
            rate = elapsed / done
            remaining = total - done
            eta_min = remaining * rate / 60
            print(
                f"[{done}/{total}] отказов в этом прогоне: {newly_failed}, "
                f"осталось ~{eta_min:.0f} мин",
                flush=True,
            )
            save_failed(failed_file, failed_set)  # сохраняем прогресс по отказам по ходу, не только в конце

        if i < len(todo) - 1:
            time.sleep(PAUSE_BETWEEN_REQUESTS)

    save_failed(failed_file, failed_set)
    print(
        f"\nГотово. Обработано в этом прогоне: {done}. "
        f"Новых отказов: {newly_failed}. Всего в {failed_file.name}: {len(failed_set)}.",
        flush=True,
    )


if __name__ == "__main__":
    main()
