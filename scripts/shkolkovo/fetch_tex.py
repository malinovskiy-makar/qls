# -*- coding: utf-8 -*-
r"""
Фаза 2: выгрузка исходных .tex по плоскому списку уникальных сессий
(класс запросов «static»), плюс второй проход без сети — сборка problems\<Id>.json.

Три проверки КАЖДОГО ответа до сохранения:
  1) это вообще LaTeX (\documentclass или \begin{document})?
     нет -> АВАРИЙНАЯ ОСТАНОВКА всего прогона (страница WAF).
  2) файл целый (есть И \begin{document}, И \end{document})?
     нет -> обрыв соединения, содержательный retry (до 4 попыток) -> failed.json
  3) кодировка цела (нет U+FFFD, нет кракозябр)?
     нет -> АВАРИЙНАЯ ОСТАНОВКА (это наш баг, не их).

Использование:
    python fetch_tex.py                    # скачать + собрать problems\
    python fetch_tex.py --limit 50         # пробный прогон на 50 сессиях
    python fetch_tex.py --retry-failed     # повторить только то, что в failed.json
    python fetch_tex.py --build-only       # без сети: только пересобрать problems\
                                            #   из уже скачанных .tex (с переповеркой)
    python fetch_tex.py --workers N --max-rps N   # переопределить потолки
"""
import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import (
    TEX_DIR, PROBLEMS_DIR, INDEX_FILE, DEPENDENCIES_FILE, FAILED_TEX_FILE,
    LATEX_BASE, SITE, PHASE2_STATS_FILE, ensure_dirs, atomic_write_text, atomic_write_json, read_json,
    validate_tex, extract_body,
)
from net import AdaptiveGate, RateLimiter, Stats, make_client, fetch_static, PermanentFailure, RETRY_DELAYS

START_CONCURRENCY = 3
MAX_CONCURRENCY = 8
MAX_RPS = 10
RAMP_AFTER = 500
CONTENT_RETRY_ATTEMPTS = 4
PROGRESS_EVERY_TASKS = 200

SESSION_FIELDS = [
    ("QuestionTexSessionId", "statement_tex"),
    ("SolutionTexSessionId", "solution_tex"),
    ("GradeCriteriaTexSessionId", "criteria_tex"),
]


def log(msg):
    print(msg, flush=True)


def collect_session_ids(problems):
    """Плоский список уникальных session id по всем задачам, с обратной картой id->[(qId, поле)]."""
    sid_to_uses = {}
    for q in problems:
        for field, _ in SESSION_FIELDS:
            sid = q.get(field)
            if sid:
                sid_to_uses.setdefault(sid, []).append((q["Id"], field))
        ans = q.get("Answer") or {}
        asid = ans.get("TexSessionId")
        if asid:
            sid_to_uses.setdefault(asid, []).append((q["Id"], "AnswerTexSessionId"))
    return sid_to_uses


def load_failed():
    d = read_json(FAILED_TEX_FILE, default={"failed": {}})
    return d.get("failed", {})


def save_failed(failed_map):
    atomic_write_json(FAILED_TEX_FILE, {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(failed_map),
        "failed": failed_map,
    })


class Progress:
    def __init__(self, total):
        self.total = total
        self.done = 0
        self.saved = 0
        self.skipped_existing = 0
        self.failed = 0
        self.start = time.monotonic()
        self.last_logged = 0

    def tick(self, gate):
        self.done += 1
        if self.done - self.last_logged >= PROGRESS_EVERY_TASKS or self.done == self.total:
            self.last_logged = self.done
            elapsed = time.monotonic() - self.start
            rate = self.done / elapsed if elapsed > 0 else 0
            remaining = self.total - self.done
            eta_min = (remaining / rate / 60) if rate > 0 else float("inf")
            log(
                f"[прогресс] {self.done}/{self.total} сессий, сохранено={self.saved}, "
                f"пропущено(уже было)={self.skipped_existing}, неудач={self.failed}, "
                f"{rate:.2f} сесс/с, одновременных={gate.limit}, ETA~{eta_min:.1f} мин"
            )


async def process_session(sid, client, gate, limiter, stats, progress, failed_map, fatal):
    if fatal["event"].is_set():
        return
    out_path = TEX_DIR / f"{sid}.tex"
    if out_path.exists():
        progress.skipped_existing += 1
        progress.tick(gate)
        return

    url = f"{LATEX_BASE}/{sid}/index.tex"
    last_raw = None
    for content_attempt in range(1, CONTENT_RETRY_ATTEMPTS + 1):
        if fatal["event"].is_set():
            return
        if content_attempt > 1:
            await asyncio.sleep(RETRY_DELAYS[min(content_attempt - 2, len(RETRY_DELAYS) - 1)])
        try:
            resp = await fetch_static(client, gate, limiter, stats, url, log=log)
        except PermanentFailure as e:
            failed_map[str(sid)] = f"сетевой отказ после всех повторов: {e}"
            progress.failed += 1
            progress.tick(gate)
            return

        if resp.status_code == 404:
            failed_map[str(sid)] = "HTTP 404 — сессия не найдена (неожиданно для валидного id из каталога)"
            progress.failed += 1
            progress.tick(gate)
            return

        raw = resp.content.decode("utf-8", errors="replace")
        last_raw = raw
        ok1, ok2, ok3 = validate_tex(raw)

        if not ok1:
            fatal["message"] = (
                f"Сессия {sid}: ответ НЕ похож на LaTeX (нет \\documentclass и нет \\begin{{document}}) — "
                f"похоже на страницу WAF. Успешно скачано к этому моменту: {progress.saved}. "
                f"Первые 300 символов ответа:\n{raw[:300]!r}"
            )
            fatal["event"].set()
            return
        if not ok3:
            fatal["message"] = (
                f"Сессия {sid}: повреждена кодировка (U+FFFD или кракозябры) — это наш баг записи/чтения, "
                f"не их. Успешно скачано к этому моменту: {progress.saved}."
            )
            fatal["event"].set()
            return
        if ok2:
            atomic_write_text(out_path, raw)
            progress.saved += 1
            progress.tick(gate)
            return

        log(f"    сессия {sid}: файл оборван (нет \\end{{document}}), попытка {content_attempt}/{CONTENT_RETRY_ATTEMPTS}")

    failed_map[str(sid)] = f"после {CONTENT_RETRY_ATTEMPTS} попыток файл всё ещё обрывается (нет \\end{{document}})"
    progress.failed += 1
    progress.tick(gate)


async def run_download(problems, args):
    ensure_dirs()
    sid_to_uses = collect_session_ids(problems)
    all_sids = sorted(sid_to_uses.keys())
    log(f"Уникальных сессий во всех задачах: {len(all_sids)}")

    failed_map = load_failed()
    if args.retry_failed:
        todo = [s for s in all_sids if str(s) in failed_map]
        log(f"Режим --retry-failed: к повтору {len(todo)} сессий из failed.json")
        for s in todo:
            failed_map.pop(str(s), None)
    else:
        todo = [s for s in all_sids if not (TEX_DIR / f"{s}.tex").exists()]
        log(f"Уже на диске: {len(all_sids) - len(todo)}. К выгрузке: {len(todo)}")

    if args.limit:
        todo = todo[: args.limit]
        log(f"--limit {args.limit}: ограничиваю прогон {len(todo)} сессиями")

    if not todo:
        log("Нечего скачивать.")
        return

    max_n = args.workers or MAX_CONCURRENCY
    start_n = min(START_CONCURRENCY, max_n)
    max_rps = args.max_rps or MAX_RPS

    gate = AdaptiveGate(start=start_n, max_n=max_n)
    limiter = RateLimiter(max_rps)
    stats = Stats(ramp_after=RAMP_AFTER)
    progress = Progress(len(todo))
    fatal = {"event": asyncio.Event(), "message": None}

    log(f"Старт: одновременных={start_n}, максимум={max_n}, потолок={max_rps} зап/с, разгон после {RAMP_AFTER}")

    async with make_client() as client:
        await asyncio.gather(*[
            process_session(sid, client, gate, limiter, stats, progress, failed_map, fatal)
            for sid in todo
        ])

    save_failed(failed_map)

    gate_stats = gate.stats()
    s = stats.summary()
    atomic_write_json(PHASE2_STATS_FILE, {
        **s, **gate_stats,
        "sessions_done": progress.done, "sessions_saved": progress.saved,
        "sessions_skipped_existing": progress.skipped_existing, "sessions_failed": progress.failed,
        "fatal_stop": fatal["event"].is_set(),
    })

    if fatal["event"].is_set():
        log("\n=== АВАРИЙНАЯ ОСТАНОВКА ФАЗЫ 2 ===")
        log(fatal["message"])
        sys.exit(1)

    log(
        f"\nЗагрузка завершена. Обработано сессий: {progress.done}. Сохранено: {progress.saved}. "
        f"Пропущено (уже было): {progress.skipped_existing}. Неудач: {progress.failed}."
    )
    log(
        f"HTTP-запросов всего: {s['total']}, ok={s['ok']}, 404={s['not_found']}, "
        f"отказов темпа={s['rate_incidents']}, окончательных неудач={s['failed_permanent']}, "
        f"среднее {s['avg_rps']:.2f} зап/с за {s['elapsed_s']:.0f} с"
    )
    log(
        f"Темп: максимум одновременных достигнут={gate_stats['max_limit_reached']}, "
        f"разгонов={gate_stats['grow_count']}, срезаний={gate_stats['cut_count']}"
    )


def build_problems(problems, dependencies):
    ensure_dirs()
    log("\n--- Второй проход: сборка problems\\<Id>.json (без сети) ---")

    sources_map = (dependencies or {}).get("QuestionSources") or {}

    n_total = len(problems)
    n_check1_fail = 0
    n_check2_fail = 0
    n_check3_fail = 0
    n_all_pass_files = 0
    n_files_checked = 0
    n_source_resolved = 0
    n_written = 0
    fatal_msg = None

    tex_cache = {}

    def load_and_validate(sid):
        nonlocal n_check1_fail, n_check2_fail, n_check3_fail, n_all_pass_files, n_files_checked, fatal_msg
        if not sid:
            return None
        if sid in tex_cache:
            return tex_cache[sid]
        path = TEX_DIR / f"{sid}.tex"
        if not path.exists():
            tex_cache[sid] = None
            return None
        raw = path.read_text(encoding="utf-8")
        n_files_checked += 1
        ok1, ok2, ok3 = validate_tex(raw)
        if not ok1:
            n_check1_fail += 1
            fatal_msg = (
                f"Переповерка: tex\\{sid}.tex НЕ похож на LaTeX (нет \\documentclass/\\begin{{document}}). "
                f"Файл лежал на диске нераспознанным — аварийная остановка второго прохода."
            )
            return None
        if not ok3:
            n_check3_fail += 1
            fatal_msg = f"Переповерка: tex\\{sid}.tex — повреждена кодировка. Аварийная остановка."
            return None
        if not ok2:
            n_check2_fail += 1
            tex_cache[sid] = None
            return None
        n_all_pass_files += 1
        body = extract_body(raw)
        tex_cache[sid] = body
        return body

    written_ids = set()
    for q in problems:
        qid = q["Id"]
        entry = dict(q)

        entry["statement_tex"] = load_and_validate(q.get("QuestionTexSessionId"))
        if fatal_msg:
            return fatal_msg
        entry["solution_tex"] = load_and_validate(q.get("SolutionTexSessionId"))
        if fatal_msg:
            return fatal_msg
        entry["criteria_tex"] = load_and_validate(q.get("GradeCriteriaTexSessionId"))
        if fatal_msg:
            return fatal_msg
        ans = q.get("Answer") or {}
        entry["answer_tex"] = load_and_validate(ans.get("TexSessionId"))
        if fatal_msg:
            return fatal_msg

        source_ids = q.get("Sources") or []
        names = [sources_map[str(sid)]["Source"] for sid in source_ids if str(sid) in sources_map]
        entry["source_names"] = names
        entry["source_name"] = "; ".join(names) if names else None
        if names:
            n_source_resolved += 1

        memberships = q.get("theme_memberships") or []
        first_theme_id = memberships[0]["themeId"] if memberships else None
        entry["_source_url"] = (
            f"{SITE}/catalog/{first_theme_id}/{qid}" if first_theme_id else f"{SITE}/catalog/{qid}"
        )
        entry["_fetched_at"] = datetime.now(timezone.utc).isoformat()

        atomic_write_json(PROBLEMS_DIR / f"{qid}.json", entry)
        written_ids.add(qid)
        n_written += 1

    log(f"problems\\*.json записано: {n_written} (уникальных Id в index.json: {n_total})")
    log(f".tex файлов переповерено: {n_files_checked}")
    log(f"  прошли все 3 проверки: {n_all_pass_files}")
    log(f"  провалили проверку 1 (не LaTeX): {n_check1_fail}")
    log(f"  провалили проверку 2 (оборван): {n_check2_fail}")
    log(f"  провалили проверку 3 (кодировка): {n_check3_fail}")
    pct = (n_all_pass_files / n_files_checked * 100) if n_files_checked else 0.0
    log(f"  доля прошедших все 3 проверки: {pct:.2f}%")
    log(f"Задач с непустым source_name: {n_source_resolved} из {n_total} "
        f"({n_source_resolved/n_total*100:.1f}%)")

    if n_written != n_total:
        log(f"!!! ИНВАРИАНТ НЕ СОШЁЛСЯ: problems\\*.json ({n_written}) != уникальные Id ({n_total})")
        return f"problems\\*.json ({n_written}) != уникальные Id из index.json ({n_total})"

    if n_check1_fail or n_check3_fail:
        return f"переповерка нашла {n_check1_fail} файлов не-LaTeX и {n_check3_fail} с битой кодировкой"

    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--retry-failed", action="store_true")
    ap.add_argument("--build-only", action="store_true", help="без сети, только пересобрать problems\\")
    ap.add_argument("--workers", type=int, default=None, help="переопределить максимум одновременных")
    ap.add_argument("--max-rps", type=float, default=None)
    args = ap.parse_args()

    problems = read_json(INDEX_FILE)
    if not problems:
        log(f"Не найден или пуст {INDEX_FILE} — сначала запусти collect_index.py")
        sys.exit(1)
    dependencies = read_json(DEPENDENCIES_FILE, default={})

    if not args.build_only:
        asyncio.run(run_download(problems, args))

    err = build_problems(problems, dependencies)
    if err:
        log("\n=== АВАРИЙНАЯ ОСТАНОВКА (сборка problems\\) ===")
        log(err)
        sys.exit(1)

    log("\nФаза 2 завершена без расхождений.")


if __name__ == "__main__":
    main()
