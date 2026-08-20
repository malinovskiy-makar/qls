# -*- coding: utf-8 -*-
r"""
Фаза 4: проверка математических вставок настоящим KaTeX (тем же, что на сайте).

    python check_katex.py --katex-dir <папка с npm i katex, вне репозитория>

Пишет katex_report.txt рядом с данными (DATA_DIR).
Не чинит формулы — только считает и перечисляет, что падает.
"""
import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import PROBLEMS_DIR, DATA_DIR, read_json, atomic_write_text

FIELDS = ["statement_tex", "solution_tex", "answer_tex", "criteria_tex"]

DISPLAY_DOLLAR_RE = re.compile(r"\$\$(.*?)\$\$", re.S)
BRACKET_RE = re.compile(r"\\\[(.*?)\\\]", re.S)
PAREN_RE = re.compile(r"\\\((.*?)\\\)", re.S)
ENV_RE = re.compile(r"\\begin\{(equation\*?|align\*?|gather\*?|cases\*?)\}.*?\\end\{\1\}", re.S)
INLINE_DOLLAR_RE = re.compile(r"\$(.*?)\$", re.S)

KATEX_REPORT = DATA_DIR / "katex_report.txt"
KATEX_FAILING_IDS_FILE = DATA_DIR / "katex_failing_ids.json"
NODE_SCRIPT = Path(__file__).parent / "katex_check.js"


def extract_math_spans(text):
    if not text:
        return []
    masked = list(text)
    spans = []

    def blank(s, e):
        for i in range(s, e):
            masked[i] = " "

    def scan(pattern, kind, display, whole=False):
        working = "".join(masked)
        for m in pattern.finditer(working):
            content = m.group(0) if whole else m.group(1)
            if not content.strip():
                continue
            spans.append({"kind": kind, "display": display, "tex": content})
            blank(m.start(), m.end())

    scan(DISPLAY_DOLLAR_RE, "$$...$$", True)
    scan(BRACKET_RE, r"\[...\]", True)
    scan(PAREN_RE, r"\(...\)", False)
    scan(ENV_RE, "environment", True, whole=True)
    scan(INLINE_DOLLAR_RE, "$...$", False)

    return spans


def gather_all_spans(problems):
    items, meta = [], []
    idx = 0
    for p in problems:
        for field in FIELDS:
            text = p.get(field)
            for sp in extract_math_spans(text):
                items.append({"id": idx, "displayMode": sp["display"], "tex": sp["tex"]})
                meta.append({"problemId": p["Id"], "field": field, "kind": sp["kind"], "tex": sp["tex"]})
                idx += 1
    return items, meta


def normalize_error(msg):
    m = re.match(r"^(.*?)\s+at position \d+", msg)
    base = m.group(1).strip() if m else msg.strip()
    return base


def run_node_check(items, katex_dir, tmp_dir):
    in_path = tmp_dir / "katex_input.json"
    out_path = tmp_dir / "katex_output.json"
    with open(in_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False)
    result = subprocess.run(
        ["node", str(NODE_SCRIPT), str(in_path), str(out_path), str(katex_dir)],
        capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode != 0:
        print("node stdout:", result.stdout)
        print("node stderr:", result.stderr)
        raise RuntimeError("katex_check.js завершился с ошибкой")
    with open(out_path, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--katex-dir", required=True, help="папка вне репозитория с npm i katex")
    ap.add_argument("--chunk-size", type=int, default=5000)
    args = ap.parse_args()

    katex_dir = Path(args.katex_dir)
    if not (katex_dir / "node_modules" / "katex").exists():
        print(f"Не найден katex в {katex_dir}\\node_modules\\katex — сначала npm i katex там")
        sys.exit(1)

    problem_files = sorted(PROBLEMS_DIR.glob("*.json"))
    problems = [read_json(p) for p in problem_files]
    print(f"Задач: {len(problems)}")

    items, meta = gather_all_spans(problems)
    print(f"Математических вставок найдено: {len(items)}")

    if not items:
        print("Вставок нет — нечего проверять.")
        return

    tmp_dir = DATA_DIR / "_katex_tmp_io"
    tmp_dir.mkdir(exist_ok=True)

    all_results = []
    for i in range(0, len(items), args.chunk_size):
        chunk = items[i:i + args.chunk_size]
        print(f"  прогоняю через katex: {i}..{i+len(chunk)} из {len(items)}")
        res = run_node_check(chunk, katex_dir, tmp_dir)
        all_results.extend(res)

    assert len(all_results) == len(items) == len(meta)

    n_ok = sum(1 for r in all_results if r["ok"])
    n_fail = len(all_results) - n_ok
    pct_ok = n_ok / len(all_results) * 100

    error_groups = defaultdict(list)
    failing_problem_ids = set()
    for r, m in zip(all_results, meta):
        if not r["ok"]:
            norm = normalize_error(r["error"])
            error_groups[norm].append({**m, "raw_error": r["error"]})
            failing_problem_ids.add(m["problemId"])

    sorted_groups = sorted(error_groups.items(), key=lambda kv: -len(kv[1]))

    lines = []
    lines.append("=== ОТЧЁТ ПО ПРОВЕРКЕ ФОРМУЛ НАСТОЯЩИМ KaTeX ===\n")
    lines.append(f"Всего математических вставок: {len(all_results)}")
    lines.append(f"Отрендерилось без ошибки: {n_ok} ({pct_ok:.2f}%)")
    lines.append(f"Упало с ошибкой: {n_fail} ({100 - pct_ok:.2f}%)")
    if pct_ok >= 99:
        verdict = "ОТЛИЧНО (>=99%) — чинить точечно на импорте"
    elif pct_ok >= 95:
        verdict = "НОРМАЛЬНО (95-99%) — список причин нужно разобрать с Макаром"
    else:
        verdict = "СИСТЕМНАЯ ПРОБЛЕМА (<95%) — разбираться до импорта"
    lines.append(f"Вердикт по порогу: {verdict}\n")

    lines.append(f"Задач хотя бы с одной падающей формулой: {len(failing_problem_ids)} из {len(problems)}\n")

    lines.append("=== УНИКАЛЬНЫЕ ПРИЧИНЫ ОШИБОК (по убыванию частоты) ===\n")
    for norm, occurrences in sorted_groups:
        lines.append(f"[{len(occurrences)} случаев] {norm}")
        for ex in occurrences[:3]:
            snippet = ex["tex"]
            if len(snippet) > 150:
                snippet = snippet[:150] + "..."
            lines.append(f"    пример: Id={ex['problemId']}, поле={ex['field']}, вид={ex['kind']}")
            lines.append(f"      вставка: {snippet!r}")
        lines.append("")

    lines.append("=== ID ЗАДАЧ С ХОТЯ БЫ ОДНОЙ ПАДАЮЩЕЙ ФОРМУЛОЙ ===")
    lines.append(", ".join(str(i) for i in sorted(failing_problem_ids)))

    atomic_write_text(KATEX_REPORT, "\n".join(lines))

    from common import atomic_write_json
    atomic_write_json(KATEX_FAILING_IDS_FILE, sorted(failing_problem_ids))

    print(f"\nЗаписано: {KATEX_REPORT}")
    print(f"Записано: {KATEX_FAILING_IDS_FILE} ({len(failing_problem_ids)} задач)")
    print(f"Успех: {n_ok}/{len(all_results)} ({pct_ok:.2f}%)")


if __name__ == "__main__":
    main()
