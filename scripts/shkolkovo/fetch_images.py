# -*- coding: utf-8 -*-
r"""
Фаза 3: картинки (класс запросов «static»).

Собирает \includegraphics[...]{ИМЯ} из всех скачанных .tex, качает файл
из КОРНЯ сессии (не из images/ — там 404, см. разведку). Расширение в LaTeX
можно опустить ({54} валидно, файл на диске 54.png) — тогда берём листинг
папки сессии и ищем файл с такой основой имени.

Проверка: Content-Type начинается с image/ И размер > 0.
Не image/ -> АВАРИЙНАЯ ОСТАНОВКА (тот же WAF, что и в Фазе 2).
Не нашлось даже после листинга -> failed_images.json, продолжаем.

Инвариант: каждая УНИКАЛЬНАЯ пара (sessionId, имя-как-в-tex) должна попасть
РОВНО в один из двух: image_map.json или failed_images.json.
"""
import argparse
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import (
    TEX_DIR, IMAGES_DIR, IMAGE_MAP_FILE, FAILED_IMAGES_FILE, LATEX_BASE, PHASE3_STATS_FILE,
    ensure_dirs, atomic_write_bytes, atomic_write_json, read_json,
)
from net import AdaptiveGate, RateLimiter, Stats, make_client, fetch_static, PermanentFailure

START_CONCURRENCY = 3
MAX_CONCURRENCY = 8
MAX_RPS = 10
RAMP_AFTER = 500
PROGRESS_EVERY = 100

INCLUDEGRAPHICS_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
LISTING_HREF_RE = re.compile(r'<a href="([^"]+)">')
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf", ".bmp", ".webp")

# "#1", "#2" и т.п. — не имя файла, а неразвёрнутый параметр макроса
# (встречается в определении \newcommand{\pict}[2][1]{...\includegraphics{#2}...},
# который сам нигде не вызывается — проверено на всём корпусе, см. отчёт сессии).
MACRO_PLACEHOLDER_RE = re.compile(r"^#\d+$")


def log(msg):
    print(msg, flush=True)


def scan_tex_files():
    """Возвращает (occurrences_count, unique_pairs) — occurrences считает КАЖДОЕ вхождение.
    Вхождения вида {#1}/{#2} (неразвёрнутый параметр макроса, не имя файла) исключаются —
    см. MACRO_PLACEHOLDER_RE."""
    occurrences = 0
    skipped_placeholders = 0
    pairs = {}  # (sid, name) -> count
    for path in TEX_DIR.glob("*.tex"):
        sid = path.stem
        raw = path.read_text(encoding="utf-8")
        for m in INCLUDEGRAPHICS_RE.finditer(raw):
            name = m.group(1).strip()
            if MACRO_PLACEHOLDER_RE.match(name):
                skipped_placeholders += 1
                continue
            occurrences += 1
            pairs[(sid, name)] = pairs.get((sid, name), 0) + 1
    if skipped_placeholders:
        log(f"Пропущено вхождений вида {{#N}} (параметр макроса, не файл): {skipped_placeholders}")
    return occurrences, pairs


async def get_listing(client, gate, limiter, stats, sid, listing_cache, listing_locks):
    if sid in listing_cache:
        return listing_cache[sid]
    lock = listing_locks.setdefault(sid, asyncio.Lock())
    async with lock:
        if sid in listing_cache:
            return listing_cache[sid]
        url = f"{LATEX_BASE}/{sid}/"
        try:
            resp = await fetch_static(client, gate, limiter, stats, url, log=log)
        except PermanentFailure:
            listing_cache[sid] = []
            return []
        if resp.status_code != 200:
            listing_cache[sid] = []
            return []
        files = LISTING_HREF_RE.findall(resp.text)
        listing_cache[sid] = files
        return files


def resolve_from_listing(name, files):
    """Ищет в листинге файл с основой имени == name, среди 'настоящих' файлов-картинок
    (исключая автосгенерированные index-<hash>.ext превью формул)."""
    candidates = []
    for fn in files:
        if fn.startswith("index-") or fn in ("index.tex", "index.css", "version.txt"):
            continue
        stem = fn.rsplit(".", 1)[0] if "." in fn else fn
        if stem == name:
            candidates.append(fn)
    return candidates


async def process_pair(sid, name, client, gate, limiter, stats, state, listing_cache, listing_locks, fatal):
    if fatal["event"].is_set():
        return

    tried_urls = []
    resolved_name = None

    has_ext = "." in name and name.rsplit(".", 1)[-1].lower() in (e[1:] for e in IMAGE_EXTS)
    if has_ext:
        resolved_name = name
        tried_urls.append(name)
    else:
        files = await get_listing(client, gate, limiter, stats, sid, listing_cache, listing_locks)
        candidates = resolve_from_listing(name, files)
        if candidates:
            resolved_name = candidates[0]
            if len(candidates) > 1:
                log(f"    сессия {sid}, имя {name!r}: неоднозначно ({candidates}), беру {resolved_name!r}")
        else:
            state["failed"][f"{sid}|{name}"] = f"не найдено в листинге сессии (файлов в листинге: {len(files)})"
            state["done"] += 1
            maybe_progress(state, gate)
            return

    url = f"{LATEX_BASE}/{sid}/{resolved_name}"
    try:
        resp = await fetch_static(client, gate, limiter, stats, url, log=log)
    except PermanentFailure as e:
        state["failed"][f"{sid}|{name}"] = f"сетевой отказ после всех повторов: {e}"
        state["done"] += 1
        maybe_progress(state, gate)
        return

    if resp.status_code == 404:
        # именование без расширения, но точное совпадение не нашли и листинг не помог —
        # уже покрыто веткой has_ext=False выше; сюда попадаем, когда имя БЫЛО с расширением,
        # но и оно не подтвердилось — пробуем листинг как последний шанс.
        files = await get_listing(client, gate, limiter, stats, sid, listing_cache, listing_locks)
        candidates = resolve_from_listing(name.rsplit(".", 1)[0], files)
        if candidates:
            resolved_name = candidates[0]
            url = f"{LATEX_BASE}/{sid}/{resolved_name}"
            try:
                resp = await fetch_static(client, gate, limiter, stats, url, log=log)
            except PermanentFailure as e:
                state["failed"][f"{sid}|{name}"] = f"сетевой отказ после всех повторов: {e}"
                state["done"] += 1
                maybe_progress(state, gate)
                return
        if resp.status_code == 404:
            state["failed"][f"{sid}|{name}"] = "404 даже после листинга"
            state["done"] += 1
            maybe_progress(state, gate)
            return

    content_type = resp.headers.get("Content-Type", "")
    if not content_type.startswith("image/"):
        fatal["message"] = (
            f"Сессия {sid}, файл {resolved_name!r}: Content-Type={content_type!r}, не image/* — "
            f"похоже на страницу WAF, не картинку. Успешно скачано к этому моменту: {state['saved']}."
        )
        fatal["event"].set()
        return

    data = resp.content
    if len(data) == 0:
        state["failed"][f"{sid}|{name}"] = "скачался с нулевым размером"
        state["done"] += 1
        maybe_progress(state, gate)
        return

    local_name = f"{sid}_{resolved_name}"
    atomic_write_bytes(IMAGES_DIR / local_name, data)
    state["image_map"][f"{sid}|{name}"] = local_name
    state["saved"] += 1
    state["done"] += 1
    maybe_progress(state, gate)


def maybe_progress(state, gate):
    if state["done"] - state["last_logged"] >= PROGRESS_EVERY or state["done"] == state["total"]:
        state["last_logged"] = state["done"]
        log(
            f"[прогресс] {state['done']}/{state['total']} пар, сохранено={state['saved']}, "
            f"неудач={len(state['failed'])}, одновременных={gate.limit}"
        )


async def main_async(args):
    ensure_dirs()
    occurrences, pairs = scan_tex_files()
    unique_pairs = list(pairs.keys())
    log(f"Найдено вхождений \\includegraphics во всех .tex: {occurrences}")
    log(f"Уникальных пар (sessionId, имя): {len(unique_pairs)}")

    existing_map = read_json(IMAGE_MAP_FILE, default={})
    existing_failed = read_json(FAILED_IMAGES_FILE, default={})

    todo = []
    for sid, name in unique_pairs:
        key = f"{sid}|{name}"
        if key in existing_map or key in existing_failed:
            continue
        todo.append((sid, name))

    log(f"Уже обработано ранее: {len(unique_pairs) - len(todo)}. К обработке: {len(todo)}")

    if args.limit:
        todo = todo[: args.limit]
        log(f"--limit {args.limit}: ограничиваю прогон {len(todo)} парами")

    if not todo:
        log("Нечего качать.")
        state_image_map, state_failed = existing_map, existing_failed
    else:
        max_n = args.workers or MAX_CONCURRENCY
        start_n = min(START_CONCURRENCY, max_n)
        max_rps = args.max_rps or MAX_RPS

        gate = AdaptiveGate(start=start_n, max_n=max_n)
        limiter = RateLimiter(max_rps)
        stats = Stats(ramp_after=RAMP_AFTER)
        fatal = {"event": asyncio.Event(), "message": None}
        state = {
            "image_map": dict(existing_map), "failed": dict(existing_failed),
            "saved": 0, "done": 0, "last_logged": 0, "total": len(todo),
        }
        listing_cache = {}
        listing_locks = {}

        log(f"Старт: одновременных={start_n}, максимум={max_n}, потолок={max_rps} зап/с")

        async with make_client() as client:
            await asyncio.gather(*[
                process_pair(sid, name, client, gate, limiter, stats, state, listing_cache, listing_locks, fatal)
                for sid, name in todo
            ])

        atomic_write_json(IMAGE_MAP_FILE, state["image_map"])
        atomic_write_json(FAILED_IMAGES_FILE, state["failed"])

        gate_stats = gate.stats()
        s = stats.summary()
        atomic_write_json(PHASE3_STATS_FILE, {
            **s, **gate_stats,
            "pairs_saved_total": len(state["image_map"]), "pairs_failed_total": len(state["failed"]),
            "fatal_stop": fatal["event"].is_set(),
        })

        if fatal["event"].is_set():
            log("\n=== АВАРИЙНАЯ ОСТАНОВКА ФАЗЫ 3 ===")
            log(fatal["message"])
            sys.exit(1)

        log(f"\nСохранено в этом прогоне: {state['saved']}. Неудач в этом прогоне: {len(state['failed']) - len(existing_failed)}.")
        log(f"HTTP-запросов: {s['total']}, {s['avg_rps']:.2f} зап/с за {s['elapsed_s']:.0f} с")
        log(f"Темп: максимум одновременных={gate_stats['max_limit_reached']}, "
            f"разгонов={gate_stats['grow_count']}, срезаний={gate_stats['cut_count']}")
        state_image_map, state_failed = state["image_map"], state["failed"]

    if args.limit:
        log(f"\n--limit {args.limit}: пробный прогон, инвариант полноты не проверяется "
            f"(заведомо обработана не вся выгрузка)")
        return

    # --- инвариант фазы ---
    total_accounted = len(state_image_map) + len(state_failed)
    log(f"\n=== ИНВАРИАНТ ФАЗЫ 3 ===")
    log(f"Уникальных пар (sessionId,имя): {len(unique_pairs)}")
    log(f"В image_map.json: {len(state_image_map)}")
    log(f"В failed_images.json: {len(state_failed)}")
    log(f"Сумма: {total_accounted}")

    if total_accounted != len(unique_pairs):
        unaccounted = set(unique_pairs) - {tuple(k.split("|", 1)) for k in state_image_map} - {tuple(k.split("|", 1)) for k in state_failed}
        log("!!! ИНВАРИАНТ НЕ СОШЁЛСЯ !!!")
        log(f"Не учтено пар: {len(unaccounted)}")
        for sid, name in list(unaccounted)[:20]:
            log(f"  {sid} | {name}")
        sys.exit(1)

    log("ИНВАРИАНТ СОШЁЛСЯ ТОЧНО.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--max-rps", type=float, default=None)
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
