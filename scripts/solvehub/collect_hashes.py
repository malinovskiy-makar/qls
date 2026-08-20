# -*- coding: utf-8 -*-
"""
Фаза 1: собрать список хэшей всех задач раздела «Экономика» на solvehub.app.

Обычный скрипт, НЕ management command — Django и база в этой сессии не участвуют
вообще (см. CLAUDE.md сессии: в базу данных не пишем ничего).

Способ — tRPC JSON API сайта: GET .../trpc/problems.getByFilter?input={"page":N}.
Найден и провалидирован в Фазе 0 (сверка с альтернативным способом — в
rsc_reserve.py и в отчёте сессии). У ответа есть авторитетное поле "count" —
общее число задач по мнению сервера, используется здесь для контроля полноты.

Запуск:
    python scripts/solvehub/collect_hashes.py
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# Все данные — вне репозитория. Меняется в одном месте.
DATA_DIR = Path(r"C:\Users\shipu\weconomics-data\solvehub")
HASHES_FILE = DATA_DIR / "hashes.json"

API = "https://api.prod.solvehub.app/trpc"
HEADERS = {
    "User-Agent": "Weconomics-import/1.0 (+https://t.me/lengler)",
    "x-subject-label": "econ",
    "Accept": "*/*",
}
REQUEST_TIMEOUT = 40  # секунд с запасом — сеть у нас самих временами медленная, это не отказ
PAUSE_BETWEEN_PAGES = 1.5  # секунд, вежливость — сервер слабый
RETRY_DELAYS = [5, 15, 45, 120]  # секунд, при 503/429/таймауте/обрыве соединения


def fetch_page(page):
    """Возвращает распакованный json-объект ответа ({"problems": [...], "count": N})."""
    input_obj = {"0": {"json": {"page": page}}}
    params = {"batch": "1", "input": json.dumps(input_obj, separators=(",", ":"))}
    url = f"{API}/problems.getByFilter"

    last_exc = None
    for attempt, delay in enumerate([0] + RETRY_DELAYS):
        if delay:
            print(f"  страница {page}: попытка {attempt + 1}/5 через {delay} с...")
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
        return data[0]["result"]["data"]["json"]
    raise last_exc or RuntimeError(f"страница {page}: не удалось получить данные")


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    all_hashes = []
    page = 1
    expected_count = None

    while True:
        j = fetch_page(page)
        problems = j.get("problems") or []
        if expected_count is None:
            expected_count = j.get("count")
            print(f"Сервер сообщает: всего задач в разделе — {expected_count}")

        if not problems:
            print(f"Страница {page}: пусто — список закончился.")
            break

        page_hashes = [p["hash"] for p in problems]
        all_hashes.extend(page_hashes)
        print(f"Страница {page}: {len(page_hashes)} задач, собрано всего {len(all_hashes)}")

        page += 1
        time.sleep(PAUSE_BETWEEN_PAGES)

    unique_hashes = sorted(set(all_hashes))
    n_dupes = len(all_hashes) - len(unique_hashes)

    print(f"\nПройдено страниц: {page - 1}")
    print(f"Собрано хэшей (со страниц, с учётом дублей): {len(all_hashes)}")
    print(f"Уникальных: {len(unique_hashes)}")
    print(f"Дублей отброшено: {n_dupes}")
    if expected_count is not None:
        print(f"Сервер заявлял (поле count): {expected_count}")
        if len(unique_hashes) < expected_count * 0.9:
            print(
                "!!! ВНИМАНИЕ: уникальных хэшей СИЛЬНО меньше, чем заявляет сервер. "
                "Не запускай Фазу 2 (fetch_problems.py) — сначала разберись, "
                "куда делись задачи, и доложи."
            )

    with open(HASHES_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "total": len(unique_hashes),
                "hashes": unique_hashes,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\nСохранено в {HASHES_FILE}")


if __name__ == "__main__":
    main()
