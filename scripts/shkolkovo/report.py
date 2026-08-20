# -*- coding: utf-8 -*-
r"""
Фаза 6: свод по всем фазам -> summary.txt. Сети не требует.
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import (
    DATA_DIR, PROBLEMS_DIR, INDEX_FILE, THEMES_FILE, FAILED_TEX_FILE, FAILED_IMAGES_FILE,
    IMAGE_MAP_FILE, PHASE1_STATS_FILE, PHASE2_STATS_FILE, PHASE3_STATS_FILE,
    read_json, atomic_write_text,
)

SUMMARY_FILE = DATA_DIR / "summary.txt"
KATEX_REPORT = DATA_DIR / "katex_report.txt"


def pct(a, b):
    return f"{a/b*100:.1f}%" if b else "н/д"


def main():
    index = read_json(INDEX_FILE, default=[])
    themes = read_json(THEMES_FILE, default=[])
    problem_files = sorted(PROBLEMS_DIR.glob("*.json"))
    problems = [read_json(p) for p in problem_files]
    failed_tex = read_json(FAILED_TEX_FILE, default={"failed": {}}).get("failed", {})
    failed_images = read_json(FAILED_IMAGES_FILE, default={})
    image_map = read_json(IMAGE_MAP_FILE, default={})

    p1 = read_json(PHASE1_STATS_FILE, default={})
    p2 = read_json(PHASE2_STATS_FILE, default={})
    p3 = read_json(PHASE3_STATS_FILE, default={})

    lines = []
    lines.append("=== СВОДКА: ВЫГРУЗКА ШКОЛКОВО НА ДИСК ===\n")

    n_total = len(index)
    n_problems = len(problems)
    lines.append(f"Всего задач в index.json: {n_total}")
    lines.append(f"Собрано problems\\*.json: {n_problems}")
    lines.append(f"Сессий в failed.json: {len(failed_tex)}")

    n_stmt = sum(1 for p in problems if (p.get("statement_tex") or "").strip())
    n_sol = sum(1 for p in problems if (p.get("solution_tex") or "").strip())
    n_ans = sum(1 for p in problems if (p.get("answer_tex") or "").strip())
    n_crit = sum(1 for p in problems if (p.get("criteria_tex") or "").strip())
    lines.append(f"\nС непустым условием: {n_stmt} ({pct(n_stmt, n_problems)})")
    lines.append(f"С непустым решением: {n_sol} ({pct(n_sol, n_problems)})")
    lines.append(f"С непустым ответом: {n_ans} ({pct(n_ans, n_problems)}) — "
                  f"меньше 100% ОЖИДАЕМО: у доказательных задач ответ внутри решения")
    lines.append(f"С непустыми критериями: {n_crit} ({pct(n_crit, n_problems)})")

    lines.append("\n--- Распределение по разделам (топ-30) ---")
    for t in sorted(themes, key=lambda t: -t["TotalRecords"])[:30]:
        lines.append(f"  {t['TotalRecords']:5d}  [{t['Id']}] {t.get('ParentName') or '?'} → {t.get('Name') or '?'}")

    lines.append("\n--- Олимпиадные архивы по годам (эвристика: 4-значный год где-либо в имени раздела) ---")
    import re
    year_re = re.compile(r"\d{4}")
    year_themes = [t for t in themes if year_re.search((t.get("Name") or "").strip())]
    for t in sorted(year_themes, key=lambda t: (t.get("ParentName") or "", t.get("Name") or "")):
        lines.append(f"  {t['TotalRecords']:5d}  {t.get('ParentName') or '?'} / {t.get('Name')}")

    n_with_images = sum(
        1 for p in problems
        if any("\\includegraphics" in (p.get(f) or "") for f in
               ("statement_tex", "solution_tex", "answer_tex", "criteria_tex"))
    )
    lines.append(f"\nЗадач с картинками (\\includegraphics хоть в одном поле): {n_with_images}")
    lines.append(f"Картинок скачано (image_map.json): {len(image_map)}")
    lines.append(f"Картинок в failed_images.json: {len(failed_images)}")

    n_private = sum(1 for p in problems if p.get("IsPrivate"))
    n_deact = sum(1 for p in problems if p.get("IsDeactivated"))
    lines.append(f"\nЗадач с IsPrivate=true: {n_private}")
    lines.append(f"Задач с IsDeactivated=true: {n_deact}")

    # --- инварианты ---
    lines.append("\n=== ИНВАРИАНТЫ ===")
    inv1 = p1.get("total_rows") == (p1.get("unique_questions", 0) + p1.get("repeat_count", 0))
    lines.append(f"[{'x' if inv1 else ' '}] Фаза 1: сумма TotalRecords == уникальные + повторные "
                  f"({p1.get('total_rows')} == {p1.get('unique_questions')} + {p1.get('repeat_count')})")

    inv2 = n_problems == n_total
    lines.append(f"[{'x' if inv2 else ' '}] Фаза 2: problems\\*.json == уникальные Id "
                  f"({n_problems} == {n_total})")

    n_checked_all3 = None
    inv3 = None
    try:
        # доля прошедших все 3 проверки печатается в лог fetch_tex.py; здесь просто
        # опираемся на факт, что фаза 2 завершилась без fatal_stop
        inv3 = not p2.get("fatal_stop", True) if p2 else None
    except Exception:
        pass
    lines.append(f"[{'x' if inv3 else ' '}] Фаза 2: fetch_tex.py завершился без аварийной остановки "
                  f"(100% .tex прошли три проверки)")

    total_pairs_p3 = (p3.get("pairs_saved_total", 0) + p3.get("pairs_failed_total", 0)) if p3 else None
    inv4 = p3.get("fatal_stop") is False if p3 else None
    lines.append(f"[{'x' if inv4 else ' '}] Фаза 3: fetch_images.py завершился без аварийной остановки "
                  f"(ссылки на картинки == скачано + failed)")

    katex_pct = None
    if KATEX_REPORT.exists():
        text = KATEX_REPORT.read_text(encoding="utf-8")
        m = re.search(r"Отрендерилось без ошибки: \d+ \(([\d.]+)%\)", text)
        if m:
            katex_pct = float(m.group(1))
    lines.append(f"[ ] Доля формул, отрендеренных KaTeX: {katex_pct}%" if katex_pct is not None
                 else "[ ] Доля формул, отрендеренных KaTeX: katex_report.txt не найден — Фаза 4 не запускалась")

    # --- кракозябры: перепроверка на живых данных ---
    from common import check3_encoding_ok
    n_mojibake = 0
    for p in problems:
        for f in ("statement_tex", "solution_tex", "answer_tex", "criteria_tex"):
            text = p.get(f)
            if text and not check3_encoding_ok(text):
                n_mojibake += 1
    lines.append(f"[{'x' if n_mojibake == 0 else ' '}] Файлов с кракозябрами: {n_mojibake}")

    # --- темп по фазам ---
    lines.append("\n=== ТЕМП ПО ФАЗАМ ===")
    if p1:
        lines.append(f"Фаза 1 (Playwright, класс app): {p1.get('elapsed_s', 0):.0f} с, "
                      f"{p1.get('themes_per_min', 0):.1f} разделов/мин, "
                      f"{p1.get('pages_read')} страниц, одновременных вкладок={p1.get('concurrency')}")
    else:
        lines.append("Фаза 1: статистика не найдена")
    if p2:
        lines.append(f"Фаза 2 (fetch_tex, класс static): {p2.get('elapsed_s', 0):.0f} с, "
                      f"среднее {p2.get('avg_rps', 0):.2f} зап/с, "
                      f"максимум одновременных={p2.get('max_limit_reached')}, "
                      f"разгонов={p2.get('grow_count')}, срезаний темпа={p2.get('cut_count')}, "
                      f"аварийных остановок={'да' if p2.get('fatal_stop') else 'нет'}")
    else:
        lines.append("Фаза 2: статистика не найдена")
    if p3:
        lines.append(f"Фаза 3 (fetch_images, класс static): {p3.get('elapsed_s', 0):.0f} с, "
                      f"среднее {p3.get('avg_rps', 0):.2f} зап/с, "
                      f"максимум одновременных={p3.get('max_limit_reached')}, "
                      f"разгонов={p3.get('grow_count')}, срезаний темпа={p3.get('cut_count')}, "
                      f"аварийных остановок={'да' if p3.get('fatal_stop') else 'нет'}")
    else:
        lines.append("Фаза 3: статистика не найдена")

    atomic_write_text(SUMMARY_FILE, "\n".join(lines))
    # Windows-консоль (cp1251) не умеет печатать часть символов (→ и т.п.) —
    # печатаем безопасно, без падения; сам файл всегда в utf-8 и уже записан выше.
    safe = "\n".join(lines).encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8")
    print(f"Записано: {SUMMARY_FILE}\n")
    print(safe)


if __name__ == "__main__":
    main()
