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
"""
import argparse
import json
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


def fetch_problem(hash_):
    """Возвращает распакованный объект задачи. Бросает исключение, если все попытки исчерпаны."""
    input_obj = {"0": {"json": {"hash": hash_}}}
    params = {"batch": "1", "input": json.dumps(input_obj, separators=(",", ":"))}
    url = f"{API}/problems.getByHash"

    last_exc = None
    for attempt, delay in enumerate([0] + RETRY_DELAYS):
        if delay:
            print(f"    {hash_}: попытка {attempt + 1}/5 через {delay} с...")
            time.sleep(delay)
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        except (requests.ConnectionError, requests.Timeout) as e:
            last_exc = e
            continue
        if r.status_code in (503, 429):
            last_exc = RuntimeError(f"HTTP {r.status_code}")
            continue
        r.raise_for_status()
        data = r.json()
        problems = data[0]["result"]["data"]["json"].get("problems") or []
        if not problems:
            raise RuntimeError("пустой ответ problems.getByHash (задача не найдена?)")
        return problems[0]
    raise last_exc or RuntimeError("не удалось получить данные")


def parse_args():
    p = argparse.ArgumentParser(description="Фаза 2: скачать задачи SolveHub по списку хэшей")
    p.add_argument("--limit", type=int, default=None, help="скачать не больше N задач (пробный прогон)")
    p.add_argument("--retry-failed", action="store_true", help="повторить только хэши из failed.json")
    return p.parse_args()


def load_failed():
    if not FAILED_FILE.exists():
        return set()
    with open(FAILED_FILE, encoding="utf-8") as f:
        return set(json.load(f).get("failed", []))


def save_failed(failed_set):
    with open(FAILED_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {"updated_at": datetime.now(timezone.utc).isoformat(), "failed": sorted(failed_set)},
            f,
            ensure_ascii=False,
            indent=2,
        )


def main():
    args = parse_args()

    if not HASHES_FILE.exists():
        print(f"Не найден {HASHES_FILE} — сначала запусти collect_hashes.py")
        raise SystemExit(1)

    PROBLEMS_DIR.mkdir(parents=True, exist_ok=True)

    with open(HASHES_FILE, encoding="utf-8") as f:
        all_hashes = json.load(f)["hashes"]

    failed_set = load_failed()

    if args.retry_failed:
        todo = [h for h in all_hashes if h in failed_set]
        print(f"Режим --retry-failed: к повтору {len(todo)} хэшей из failed.json")
    else:
        todo = [h for h in all_hashes if not (PROBLEMS_DIR / f"{h}.json").exists()]
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
            out_path = PROBLEMS_DIR / f"{h}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(problem, f, ensure_ascii=False, indent=2)
            failed_set.discard(h)
            consecutive_failures = 0
        except Exception as e:
            print(f"    {h}: ОТКАЗ после всех попыток — {e}")
            failed_set.add(h)
            newly_failed += 1
            consecutive_failures += 1

        done += 1

        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            save_failed(failed_set)
            print(
                f"\nСервер похоже недоступен: {consecutive_failures} задач подряд ушли "
                f"в отказ. Остановился на задаче {done} из {total}. Запусти скрипт снова "
                f"позже — уже скачанное и список отказов сохранены, продолжится с места "
                f"остановки."
            )
            return

        if done % PROGRESS_EVERY == 0 or done == total:
            elapsed = time.time() - start_time
            rate = elapsed / done
            remaining = total - done
            eta_min = remaining * rate / 60
            print(
                f"[{done}/{total}] отказов в этом прогоне: {newly_failed}, "
                f"осталось ~{eta_min:.0f} мин"
            )
            save_failed(failed_set)  # сохраняем прогресс по отказам по ходу, не только в конце

        if i < len(todo) - 1:
            time.sleep(PAUSE_BETWEEN_REQUESTS)

    save_failed(failed_set)
    print(
        f"\nГотово. Обработано в этом прогоне: {done}. "
        f"Новых отказов: {newly_failed}. Всего в failed.json: {len(failed_set)}."
    )


if __name__ == "__main__":
    main()
