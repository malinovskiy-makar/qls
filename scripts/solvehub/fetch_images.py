# -*- coding: utf-8 -*-
"""
Фаза 3: скачать все картинки, на которые ссылаются условия и решения задач.

Обычный скрипт, НЕ management command — Django и база не участвуют. Работает
по уже скачанным problems/*.json (Фаза 2); сеть нужна только для картинок.

Запуск:
    python scripts/solvehub/fetch_images.py
"""
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

# Все данные — вне репозитория. Меняется в одном месте.
DATA_DIR = Path(r"C:\Users\shipu\weconomics-data\solvehub")
PROBLEMS_DIR = DATA_DIR / "problems"
IMAGES_DIR = DATA_DIR / "images"
IMAGE_MAP_FILE = DATA_DIR / "image_map.json"

HEADERS = {
    "User-Agent": "Weconomics-import/1.0 (+https://t.me/lengler)",
}
REQUEST_TIMEOUT = 40  # секунд с запасом — сеть у нас самих временами медленная, это не отказ
PAUSE_BETWEEN_REQUESTS = 1.0  # секунда, вежливость — сервер слабый
RETRY_DELAYS = [5, 15, 45, 120]  # секунд, при 503/429/таймауте/обрыве соединения
PROGRESS_EVERY = 50
MAX_CONSECUTIVE_FAILURES = 20  # если сервер лёг совсем — сдаться честно, а не молотить впустую

IMAGE_URL_RE = re.compile(r'https?://api\.solvehub\.app/uploads/[^\s)"\']+')


def collect_image_urls():
    """Проходит все problems/*.json, собирает уникальные адреса картинок из md и answer_md."""
    urls = set()
    files = sorted(PROBLEMS_DIR.glob("*.json"))
    for path in files:
        with open(path, encoding="utf-8") as f:
            problem = json.load(f)
        for field in ("md", "answer_md"):
            text = problem.get(field) or ""
            urls.update(IMAGE_URL_RE.findall(text))
    return files, sorted(urls)


def local_filename(url):
    return urlparse(url).path.rsplit("/", 1)[-1]


def download_image(url):
    """Скачивает картинку, возвращает сырые байты. Бросает исключение, если все попытки исчерпаны."""
    last_exc = None
    for attempt, delay in enumerate([0] + RETRY_DELAYS):
        if delay:
            print(f"    {url}: попытка {attempt + 1}/5 через {delay} с...")
            time.sleep(delay)
        try:
            r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        except (requests.ConnectionError, requests.Timeout) as e:
            last_exc = e
            continue
        if r.status_code in (503, 429):
            last_exc = RuntimeError(f"HTTP {r.status_code}")
            continue
        r.raise_for_status()
        return r.content
    raise last_exc or RuntimeError("не удалось скачать")


def load_image_map():
    if not IMAGE_MAP_FILE.exists():
        return {}
    with open(IMAGE_MAP_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_image_map(m):
    with open(IMAGE_MAP_FILE, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)


def main():
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    if not PROBLEMS_DIR.exists() or not any(PROBLEMS_DIR.glob("*.json")):
        print(f"В {PROBLEMS_DIR} нет скачанных задач — сначала запусти fetch_problems.py")
        raise SystemExit(1)

    print("Собираю адреса картинок из скачанных задач...")
    files, all_urls = collect_image_urls()
    print(f"Просмотрено задач: {len(files)}. Уникальных адресов картинок: {len(all_urls)}")

    # сверка имён файлов на коллизии: разные URL -> одно и то же имя файла
    seen_names = {}
    collisions = []
    for url in all_urls:
        name = local_filename(url)
        if name in seen_names and seen_names[name] != url:
            collisions.append((name, seen_names[name], url))
        seen_names[name] = url
    if collisions:
        print(f"!!! ВНИМАНИЕ: {len(collisions)} коллизий имён файлов у разных адресов:")
        for name, u1, u2 in collisions[:10]:
            print(f"    {name}: {u1}  vs  {u2}")

    image_map = load_image_map()
    todo = [u for u in all_urls if u not in image_map or not (IMAGES_DIR / image_map[u]).exists()]
    already_done = len(all_urls) - len(todo)
    print(f"Уже скачано: {already_done}. К выгрузке: {len(todo)}")

    if not todo:
        print("Нечего скачивать.")
        return

    total = len(todo)
    start_time = time.time()
    done = 0
    newly_failed = 0
    consecutive_failures = 0
    failures = []

    for i, url in enumerate(todo):
        name = local_filename(url)
        try:
            content = download_image(url)
            with open(IMAGES_DIR / name, "wb") as f:
                f.write(content)
            image_map[url] = name
            consecutive_failures = 0
        except Exception as e:
            print(f"    {url}: ОТКАЗ после всех попыток — {e}")
            failures.append(url)
            newly_failed += 1
            consecutive_failures += 1

        done += 1

        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            save_image_map(image_map)
            print(
                f"\nСервер похоже недоступен: {consecutive_failures} картинок подряд ушли "
                f"в отказ. Остановился на {done} из {total}. Запусти скрипт снова позже — "
                f"уже скачанное сохранено, продолжится с места остановки."
            )
            return

        if done % PROGRESS_EVERY == 0 or done == total:
            elapsed = time.time() - start_time
            rate = elapsed / done
            remaining = total - done
            eta_min = remaining * rate / 60
            print(f"[{done}/{total}] отказов в этом прогоне: {newly_failed}, осталось ~{eta_min:.0f} мин")
            save_image_map(image_map)

        if i < len(todo) - 1:
            time.sleep(PAUSE_BETWEEN_REQUESTS)

    save_image_map(image_map)
    print(f"\nГотово. Скачано в этом прогоне: {done - newly_failed}. Отказов: {newly_failed}.")
    if failures:
        print("Не удалось скачать (проверь вручную, они не попали в image_map.json):")
        for u in failures:
            print(f"  {u}")


if __name__ == "__main__":
    main()
