# -*- coding: utf-8 -*-
r"""
Фаза 5а: инвентаризация разметки — что реально встречается в скачанных задачах.
Сети не требует. Пишет inventory.txt и папку samples\ (по одному примеру на окружение).
"""
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import PROBLEMS_DIR, DEPENDENCIES_FILE, DATA_DIR, SAMPLES_DIR, read_json, atomic_write_text

FIELDS = ["statement_tex", "solution_tex", "answer_tex", "criteria_tex"]
INVENTORY_FILE = DATA_DIR / "inventory.txt"

CMD_RE = re.compile(r"\\([A-Za-z]+)")
ENV_BEGIN_RE = re.compile(r"\\begin\{([^}]+)\}")
UNESCAPED_PERCENT_RE = re.compile(r"(?<!\\)%")
UNESCAPED_DOLLAR_RE = re.compile(r"(?<!\\)\$")

_ENV_MASK_RE = re.compile(r"\\begin\{(equation\*?|align\*?|gather\*?|cases\*?)\}.*?\\end\{\1\}", re.S)
_DISPLAY_MASK_RE = re.compile(r"\$\$.*?\$\$", re.S)
_BRACKET_MASK_RE = re.compile(r"\\\[.*?\\\]", re.S)
_PAREN_MASK_RE = re.compile(r"\\\(.*?\\\)", re.S)
_INLINE_MASK_RE = re.compile(r"\$.*?\$", re.S)

CYRILLIC_RANGE = (0x0400, 0x04FF)


def build_math_mask(text):
    n = len(text)
    mask = bytearray(n)
    masked = list(text)

    def consume(pattern):
        working = "".join(masked)
        for m in pattern.finditer(working):
            s, e = m.start(), m.end()
            for i in range(s, e):
                mask[i] = 1
                masked[i] = " "

    consume(_DISPLAY_MASK_RE)
    consume(_BRACKET_MASK_RE)
    consume(_PAREN_MASK_RE)
    consume(_ENV_MASK_RE)
    consume(_INLINE_MASK_RE)
    return mask


def main():
    problem_files = sorted(PROBLEMS_DIR.glob("*.json"))
    problems = [read_json(p) for p in problem_files]
    n_total = len(problems)
    print(f"Задач: {n_total}")

    dependencies = read_json(DEPENDENCIES_FILE, default={})
    tags_map = dependencies.get("Tags") or {}

    cmd_math = Counter()
    cmd_nonmath = Counter()
    env_counter = Counter()
    env_examples = {}  # env_name -> (problemId, field, excerpt)

    n_with_table = 0
    n_with_list = 0
    n_with_image = 0
    n_with_textbf = 0
    n_with_emph = 0
    n_with_footnote = 0
    n_with_color = 0
    n_with_hrule_vrule = 0

    n_unclosed_dollar = 0
    n_unescaped_percent = 0
    n_verb = 0
    n_input_include = 0

    nonascii_noncyr = Counter()

    n_display_dollar = 0
    n_bracket = 0
    n_paren = 0
    n_inline_dollar_pairs = 0
    n_env_math = 0

    n_empty_statement = 0
    n_empty_solution = 0
    n_empty_criteria = 0

    answer_type_counter = Counter()
    tag_counter = Counter()
    source_name_counter = Counter()

    statement_lengths = []  # (len, Id)

    for p in problems:
        pid = p["Id"]

        stmt = p.get("statement_tex") or ""
        if not stmt.strip():
            n_empty_statement += 1
        statement_lengths.append((len(stmt), pid))

        if not (p.get("solution_tex") or "").strip():
            n_empty_solution += 1
        if not (p.get("criteria_tex") or "").strip():
            n_empty_criteria += 1

        answer_type_counter[p.get("AnswerTypeId")] += 1

        for tag_id in (p.get("Tags") or []):
            tag_entry = tags_map.get(str(tag_id))
            if tag_entry:
                tag_counter[tag_entry["Name"]] += 1

        source_name_counter[p.get("source_name")] += 1

        has_table = has_list = has_image = has_textbf = has_emph = False
        has_footnote = has_color = has_rule = False

        for field in FIELDS:
            text = p.get(field) or ""
            if not text:
                continue

            mask = build_math_mask(text)
            for m in CMD_RE.finditer(text):
                name = m.group(1)
                (cmd_math if mask[m.start()] else cmd_nonmath)[name] += 1

            for m in ENV_BEGIN_RE.finditer(text):
                name = m.group(1)
                env_counter[name] += 1
                if name not in env_examples:
                    start = max(0, m.start() - 20)
                    end = min(len(text), m.start() + 400)
                    env_examples[name] = (pid, field, text[start:end])

            if "tabular" in text or "\\begin{array}" in text:
                has_table = True
            if "\\begin{itemize}" in text or "\\begin{enumerate}" in text:
                has_list = True
            if "\\includegraphics" in text:
                has_image = True
            if "\\textbf" in text:
                has_textbf = True
            if "\\emph" in text or "\\textit" in text:
                has_emph = True
            if "\\footnote" in text:
                has_footnote = True
            if "\\color" in text or "\\textcolor" in text:
                has_color = True
            if "\\hline" in text or "\\vline" in text or "\\cline" in text:
                has_rule = True

            dollars = UNESCAPED_DOLLAR_RE.findall(text)
            if len(dollars) % 2 != 0:
                n_unclosed_dollar += 1

            n_unescaped_percent += len(UNESCAPED_PERCENT_RE.findall(text))
            if "\\verb" in text:
                n_verb += 1
            if "\\input" in text or "\\include{" in text or "\\include " in text:
                n_input_include += 1

            n_display_dollar += len(_DISPLAY_MASK_RE.findall(text))
            n_bracket += len(_BRACKET_MASK_RE.findall(text))
            n_paren += len(_PAREN_MASK_RE.findall(text))
            n_env_math += len(_ENV_MASK_RE.findall(text))
            n_inline_dollar_pairs += len(_INLINE_MASK_RE.findall(_DISPLAY_MASK_RE.sub("", text)))

            for ch in text:
                if ord(ch) > 127:
                    cp = ord(ch)
                    if not (CYRILLIC_RANGE[0] <= cp <= CYRILLIC_RANGE[1]):
                        nonascii_noncyr[ch] += 1

        if has_table:
            n_with_table += 1
        if has_list:
            n_with_list += 1
        if has_image:
            n_with_image += 1
        if has_textbf:
            n_with_textbf += 1
        if has_emph:
            n_with_emph += 1
        if has_footnote:
            n_with_footnote += 1
        if has_color:
            n_with_color += 1
        if has_rule:
            n_with_hrule_vrule += 1

    statement_lengths.sort()
    shortest_15 = statement_lengths[:15]
    longest_15 = statement_lengths[-15:][::-1]

    # --- samples\: по одному примеру на окружение ---
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    for env_name, (pid, field, excerpt) in env_examples.items():
        safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", env_name)
        atomic_write_text(
            SAMPLES_DIR / f"env_{safe_name}.txt",
            f"Id={pid} field={field} env={env_name}\n\n{excerpt}",
        )

    # --- запись inventory.txt ---
    lines = []
    lines.append("=== ИНВЕНТАРИЗАЦИЯ РАЗМЕТКИ ШКОЛКОВО ===\n")
    lines.append(f"Всего задач: {n_total}\n")

    lines.append("--- 1. Команды \\имя — ВНУТРИ математики (топ-80) ---")
    for name, cnt in cmd_math.most_common(80):
        lines.append(f"  {cnt:6d}  \\{name}")
    lines.append(f"\n--- 1. Команды \\имя — ВНЕ математики (топ-80) ---")
    for name, cnt in cmd_nonmath.most_common(80):
        lines.append(f"  {cnt:6d}  \\{name}")

    lines.append("\n--- 2. Окружения \\begin{X} (все, по убыванию) ---")
    for name, cnt in env_counter.most_common():
        lines.append(f"  {cnt:6d}  {name}")

    lines.append("\n--- 3. Задачи, содержащие ---")
    lines.append(f"  таблицу (tabular/array): {n_with_table} ({n_with_table/n_total*100:.1f}%)")
    lines.append(f"  список (itemize/enumerate): {n_with_list} ({n_with_list/n_total*100:.1f}%)")
    lines.append(f"  картинку (\\includegraphics): {n_with_image} ({n_with_image/n_total*100:.1f}%)")
    lines.append(f"  \\textbf: {n_with_textbf} ({n_with_textbf/n_total*100:.1f}%)")
    lines.append(f"  \\emph/\\textit: {n_with_emph}")
    lines.append(f"  сноску (\\footnote): {n_with_footnote}")
    lines.append(f"  цвет (\\color/\\textcolor): {n_with_color}")
    lines.append(f"  линейку (\\hline/\\vline/\\cline): {n_with_hrule_vrule}")

    lines.append("\n--- 4. Виды математических вставок (по всем полям, по всем задачам) ---")
    lines.append(f"  $$...$$: {n_display_dollar}")
    lines.append(f"  \\[...\\]: {n_bracket}")
    lines.append(f"  \\(...\\): {n_paren}")
    lines.append(f"  окружения equation/align/gather/cases (и *): {n_env_math}")
    lines.append(f"  $...$ (после исключения $$...$$): {n_inline_dollar_pairs}")

    lines.append("\n--- 5. Небезопасные места ---")
    lines.append(f"  полей с нечётным числом $ (незакрытые): {n_unclosed_dollar}")
    lines.append(f"  неэкранированных % (всего вхождений): {n_unescaped_percent}")
    lines.append(f"  задач/полей с \\verb: {n_verb}")
    lines.append(f"  задач/полей с \\input или \\include: {n_input_include}")

    lines.append("\n--- 6. Символы вне ASCII и кириллицы (уникальные, с частотой) ---")
    for ch, cnt in nonascii_noncyr.most_common():
        name = unicodedata.name(ch, "?")
        lines.append(f"  {cnt:6d}  {ch!r}  U+{ord(ch):04X}  {name}")

    lines.append("\n--- 7. 15 самых ДЛИННЫХ условий ---")
    for length, pid in longest_15:
        lines.append(f"  {length:6d} символов  Id={pid}")
    lines.append("\n--- 7. 15 самых КОРОТКИХ условий ---")
    for length, pid in shortest_15:
        lines.append(f"  {length:6d} символов  Id={pid}")

    lines.append("\n--- 8. Пустые поля ---")
    lines.append(f"  пустых условий: {n_empty_statement}")
    lines.append(f"  пустых решений: {n_empty_solution}")
    lines.append(f"  пустых критериев: {n_empty_criteria}")

    lines.append("\n--- 9. AnswerTypeId ---")
    for atype, cnt in sorted(answer_type_counter.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {cnt:6d}  AnswerTypeId={atype}")

    lines.append("\n--- 10. Топ-50 тегов ---")
    for name, cnt in tag_counter.most_common(50):
        lines.append(f"  {cnt:6d}  {name}")

    lines.append("\n--- 10. Все значения source_name ---")
    for name, cnt in source_name_counter.most_common():
        lines.append(f"  {cnt:6d}  {name}")

    atomic_write_text(INVENTORY_FILE, "\n".join(lines))
    print(f"Записано: {INVENTORY_FILE}")
    print(f"Примеров окружений в samples\\: {len(env_examples)}")


if __name__ == "__main__":
    main()
