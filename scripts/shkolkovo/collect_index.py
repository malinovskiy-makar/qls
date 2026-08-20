# -*- coding: utf-8 -*-
r"""
Фаза 1: перечисление каталога Школково через Playwright (класс запросов «app»).

Один браузерный контекст на весь прогон, 3 одновременных вкладки (по разделам),
внутри раздела страницы читаются последовательно (число страниц известно
только после первой). Параметр пагинации регистрозависим: ?Page=N.

Пишет:
  raw\theme_<id>_page_<n>.json   — questionList целиком, как пришло, без правок
  themes.json                    — по разделу: Id, Name, ParentId, TotalRecords, TotalPages
  index.json                     — по задаче, дедуплицировано по Id,
                                    с накопленным списком членств в разделах
  dependencies_global.json       — смёрженные словари-справочники (для удобства;
                                    источник истины всё равно raw\)

Инвариант фазы: сумма pagination.TotalRecords по всем разделам должна СОВПАСТЬ
с суммарным числом строк вопросов, реально собранных со всех страниц. Если нет —
аварийная остановка с разбивкой по разделам.
"""
import argparse
import asyncio
import json
import sys
import time

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from common import (
    RAW_DIR, INDEX_FILE, THEMES_FILE, DEPENDENCIES_FILE, PHASE1_STATS_FILE,
    BROWSER_USER_AGENT, SITE, ensure_dirs, atomic_write_json, read_json,
)

ROOT_URL = f"{SITE}/catalog?SubjectId=16"
CATALOG_BASE = f"{SITE}/catalog"
CONCURRENCY = 3
MAX_RETRIES = 3
HYDRATION_TIMEOUT_S = 15


class FatalStop(Exception):
    pass


def log(msg):
    print(msg, flush=True)


async def wait_for_props(page, timeout_s=HYDRATION_TIMEOUT_S):
    """Ждёт window.__NEXT_DATA__.props.pageProps, возвращает его как dict, либо None по таймауту."""
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            result = await page.evaluate(
                "() => window.__NEXT_DATA__ && window.__NEXT_DATA__.props "
                "? JSON.stringify(window.__NEXT_DATA__.props.pageProps) : null"
            )
        except Exception:
            result = None
        if result and result != "null":
            return json.loads(result)
        await asyncio.sleep(0.3)
    return None


async def goto_with_retries(page, url, retries=MAX_RETRIES, need_nonempty_questions=True):
    """Возвращает pageProps. Бросает FatalStop после `retries` неудач подряд."""
    last_html_snippet = None
    last_reason = None
    for attempt in range(1, retries + 1):
        try:
            await page.goto(url, wait_until="load", timeout=30000)
        except Exception as e:
            last_reason = f"goto exception: {e}"
            await asyncio.sleep(2)
            continue

        pp = await wait_for_props(page)
        if pp is None:
            last_reason = "нет __NEXT_DATA__.props (челлендж или ошибка страницы)"
            try:
                last_html_snippet = (await page.content())[:300]
            except Exception:
                last_html_snippet = None
            log(f"    [retry {attempt}/{retries}] {url}: {last_reason}")
            await asyncio.sleep(2)
            continue

        if need_nonempty_questions:
            ql = pp.get("questionList") or {}
            questions = ql.get("questions")
            pagination = pp.get("pagination") or {}
            declared_total = pagination.get("TotalRecords")
            # Пустой questions — норма, когда пагинация САМА заявляет 0 записей
            # (реально пустой раздел). Подозрительно только когда заявлено >0,
            # а строк не пришло — вот это похоже на порчу/челлендж и стоит повторить.
            if not questions and declared_total:
                last_reason = f"questionList.questions пуст, но pagination.TotalRecords={declared_total}"
                log(f"    [retry {attempt}/{retries}] {url}: {last_reason}")
                await asyncio.sleep(2)
                continue

        return pp

    raise FatalStop(
        f"3 неудачи подряд на {url}. Причина последней: {last_reason}. "
        f"Начало HTML последнего ответа: {last_html_snippet!r}"
    )


async def discover_theme_ids(page):
    pp = None
    for attempt in range(1, MAX_RETRIES + 1):
        await page.goto(ROOT_URL, wait_until="load", timeout=30000)
        pp = await wait_for_props(page)
        if pp is not None:
            break
        log(f"    [retry {attempt}/{MAX_RETRIES}] корневая страница: нет __NEXT_DATA__.props (челлендж?)")
        await asyncio.sleep(2)
    if pp is None:
        raise FatalStop(f"3 неудачи подряд на корневой странице каталога: {ROOT_URL}")
    ids_json = await page.evaluate(
        """() => {
            const links = Array.from(document.querySelectorAll('a[href^="/catalog/"]'));
            const ids = new Set();
            links.forEach(a => {
                const href = a.getAttribute('href');
                const m = href.match(/^\\/catalog\\/(\\d+)$/);
                if (m) ids.add(m[1]);
            });
            return JSON.stringify(Array.from(ids));
        }"""
    )
    ids = sorted(set(int(x) for x in json.loads(ids_json)))
    return ids


def save_raw_page(theme_id, page_n, question_list_obj):
    path = RAW_DIR / f"theme_{theme_id}_page_{page_n}.json"
    if path.exists():
        return  # уже есть — не перезаписываем сырьё без необходимости
    atomic_write_json(path, question_list_obj)


def load_raw_page(theme_id, page_n):
    path = RAW_DIR / f"theme_{theme_id}_page_{page_n}.json"
    if not path.exists():
        return None
    return read_json(path)


def merge_dependencies(global_deps, deps):
    for key, val in (deps or {}).items():
        if isinstance(val, dict):
            global_deps.setdefault(key, {}).update(val)
        else:
            global_deps.setdefault(key, val)


async def process_theme(page, theme_id, state):
    theme_url = f"{CATALOG_BASE}/{theme_id}"

    cached_p1 = load_raw_page(theme_id, 1)
    if cached_p1 is not None:
        ql1 = cached_p1
        # для метаданных темы (currentTheme/parentTheme/pagination) нужен полный pageProps —
        # он не сохраняется отдельно, поэтому при наличии кэша страницы 1 всё равно
        # делаем один живой запрос, чтобы получить currentTheme/parentTheme/pagination.
        # (сам questionList при этом не перезаписывается, см. save_raw_page.)
        pp1 = await goto_with_retries(page, theme_url)
    else:
        pp1 = await goto_with_retries(page, theme_url)
        ql1 = pp1["questionList"]
        save_raw_page(theme_id, 1, ql1)

    pagination = pp1["pagination"]
    current_theme = pp1.get("currentTheme") or {}
    parent_theme = pp1.get("parentTheme") or {}
    total_pages = pagination["TotalPages"]
    total_records = pagination["TotalRecords"]

    all_rows = list(ql1["questions"])
    merge_dependencies(state["global_deps"], ql1.get("dependencies"))

    for pg in range(2, total_pages + 1):
        cached = load_raw_page(theme_id, pg)
        if cached is not None:
            ql = cached
        else:
            pp = await goto_with_retries(page, f"{theme_url}?Page={pg}")
            ql = pp["questionList"]
            save_raw_page(theme_id, pg, ql)
        all_rows.extend(ql["questions"])
        merge_dependencies(state["global_deps"], ql.get("dependencies"))

    theme_name = current_theme.get("Name")
    parent_name = parent_theme.get("Name")

    state["themes"].append({
        "Id": theme_id,
        "Name": theme_name,
        "ParentId": current_theme.get("ParentId"),
        "ParentName": parent_name,
        "SubjectId": current_theme.get("SubjectId"),
        "TotalRecords": total_records,
        "TotalPages": total_pages,
        "ActualRowsCollected": len(all_rows),
    })

    if len(all_rows) != total_records:
        state["theme_mismatches"].append({
            "themeId": theme_id, "themeName": theme_name,
            "declared_TotalRecords": total_records, "actual_rows": len(all_rows),
        })

    for row in all_rows:
        qid = row["Id"]
        membership = {"themeId": theme_id, "themeName": theme_name, "parentThemeName": parent_name}
        if qid not in state["results"]:
            entry = dict(row)
            entry["theme_memberships"] = [membership]
            state["results"][qid] = entry
        else:
            state["results"][qid]["theme_memberships"].append(membership)

    state["total_rows_collected"] += len(all_rows)
    state["sum_total_records"] += total_records
    state["themes_done"] += 1
    log(
        f"  [{state['themes_done']}/{state['themes_total']}] раздел {theme_id} "
        f"({theme_name!r}): {total_records} задач, {total_pages} стр. — ok"
    )


async def worker(worker_id, page, queue, state, abort_event):
    while not abort_event.is_set():
        try:
            theme_id = queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        try:
            await process_theme(page, theme_id, state)
        except FatalStop as e:
            state["fatal_error"] = str(e)
            abort_event.set()
            return
        except Exception as e:
            state["fatal_error"] = f"раздел {theme_id}: неожиданная ошибка: {type(e).__name__}: {e}"
            abort_event.set()
            return
        finally:
            queue.task_done()


async def main_async(args):
    ensure_dirs()
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=BROWSER_USER_AGENT)

        seed_page = await context.new_page()
        log("Захожу на корень каталога, собираю список разделов...")
        theme_ids = await discover_theme_ids(seed_page)
        log(f"Найдено уникальных разделов: {len(theme_ids)}")

        if args.limit:
            theme_ids = theme_ids[: args.limit]
            log(f"--limit {args.limit}: ограничиваю прогон {len(theme_ids)} разделами")

        queue = asyncio.Queue()
        for tid in theme_ids:
            queue.put_nowait(tid)

        state = {
            "themes": [],
            "results": {},
            "global_deps": {},
            "theme_mismatches": [],
            "total_rows_collected": 0,
            "sum_total_records": 0,
            "themes_done": 0,
            "themes_total": len(theme_ids),
            "fatal_error": None,
        }
        abort_event = asyncio.Event()

        pages = [seed_page] + [await context.new_page() for _ in range(CONCURRENCY - 1)]
        t0 = time.time()
        await asyncio.gather(*[
            worker(i, pages[i], queue, state, abort_event) for i in range(CONCURRENCY)
        ])
        elapsed = time.time() - t0

        await context.close()
        await browser.close()

    if state["fatal_error"]:
        log("\n=== АВАРИЙНАЯ ОСТАНОВКА ФАЗЫ 1 ===")
        log(state["fatal_error"])
        log(f"Успели обработать разделов: {state['themes_done']} из {state['themes_total']}")
        sys.exit(1)

    # --- инвариант фазы ---
    unique_count = len(state["results"])
    total_rows = state["total_rows_collected"]
    repeat_count = total_rows - unique_count
    sum_total_records = state["sum_total_records"]

    log("\n=== ПОДСЧЁТ (Фаза 1) ===")
    log(f"Разделов обойдено: {state['themes_done']}")
    log(f"Страниц прочитано: {sum(t['TotalPages'] for t in state['themes'])}")
    log(f"Сумма pagination.TotalRecords по всем разделам: {sum_total_records}")
    log(f"Всего строк вопросов собрано (с повторами): {total_rows}")
    log(f"Уникальных Id: {unique_count}")
    log(f"Повторных вхождений (задача в >1 разделе): {repeat_count}")
    log(f"уникальные + повторные = {unique_count + repeat_count}")

    multi_theme = sum(1 for r in state["results"].values() if len(r["theme_memberships"]) > 1)
    log(f"Задач, состоящих более чем в одном разделе: {multi_theme}")

    if sum_total_records != total_rows or state["theme_mismatches"]:
        log("\n=== ИНВАРИАНТ НЕ СОШЁЛСЯ — АВАРИЙНАЯ ОСТАНОВКА ===")
        log(f"sum(TotalRecords)={sum_total_records} != собрано строк={total_rows}")
        log(f"Разделов с расхождением: {len(state['theme_mismatches'])}")
        for m in state["theme_mismatches"]:
            log(f"  раздел {m['themeId']} ({m['themeName']!r}): "
                f"заявлено {m['declared_TotalRecords']}, реально собрано {m['actual_rows']}")
        # сохраняем то, что есть, под отдельным именем — для разбора, не как готовый результат
        atomic_write_json(RAW_DIR.parent / "index_MISMATCH_DEBUG.json", {
            "themes": state["themes"], "mismatches": state["theme_mismatches"],
        })
        sys.exit(1)

    log("\nИНВАРИАНТ СОШЁЛСЯ ТОЧНО.")

    # финальная запись
    atomic_write_json(THEMES_FILE, state["themes"])
    atomic_write_json(INDEX_FILE, list(state["results"].values()))
    atomic_write_json(DEPENDENCIES_FILE, state["global_deps"])

    log(f"\nЗаписано: {THEMES_FILE}")
    log(f"Записано: {INDEX_FILE} ({unique_count} задач)")
    log(f"Записано: {DEPENDENCIES_FILE}")
    log(f"Время фазы: {elapsed:.1f} с, разделов: {state['themes_total']}, "
        f"{state['themes_total']/elapsed*60:.1f} разделов/мин")

    atomic_write_json(PHASE1_STATS_FILE, {
        "elapsed_s": elapsed, "themes_total": state["themes_total"],
        "themes_per_min": state["themes_total"] / elapsed * 60 if elapsed else 0,
        "pages_read": sum(t["TotalPages"] for t in state["themes"]),
        "unique_questions": unique_count, "total_rows": total_rows,
        "repeat_count": repeat_count, "multi_theme_questions": multi_theme,
        "concurrency": CONCURRENCY,
    })


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="ограничить число разделов (пробный прогон)")
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
