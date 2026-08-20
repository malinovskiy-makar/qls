# -*- coding: utf-8 -*-
"""
Фаза 4: сводка по выгруженному — что мы вообще выкачали, до того как это
поедет в базу.

Обычный скрипт, НЕ management command — Django и база не участвуют. Читает
уже скачанные problems/*.json (Фаза 2) и tags.json — справочник тегов
(Фаза 0, Проверка B); без справочника теги и бинарные теги печатаются
голыми id.

Запуск:
    python scripts/solvehub/report.py
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

# Чужой текст (заголовки, условия) может содержать символ вне кодовой страницы
# консоли — пусть скрипт заменит его точкой, а не упадёт на 6000-й задаче.
sys.stdout.reconfigure(errors="replace")

DATA_DIR = Path(r"C:\Users\shipu\weconomics-data\solvehub")
PROBLEMS_DIR = DATA_DIR / "problems"
TAGS_FILE = DATA_DIR / "tags.json"
SUMMARY_FILE = DATA_DIR / "summary.txt"

IMAGE_URL_RE = re.compile(r'https?://api\.solvehub\.app/uploads/[^\s)"\']+')
LATEX_RE = re.compile(r"\\[a-zA-Z]+")


def load_problems():
    problems = []
    for path in sorted(PROBLEMS_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            problems.append(json.load(f))
    return problems


def load_tags():
    if not TAGS_FILE.exists():
        return {}, {}
    with open(TAGS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    tags_by_id = {t["id"]: t for t in data.get("tags", [])}
    binary_tags_by_id = {t["id"]: t for t in data.get("binaryTags", [])}
    return tags_by_id, binary_tags_by_id


def is_empty_criteria(val):
    if val in (None, "", "[]", []):
        return True
    if isinstance(val, str) and val.strip() in ("", "[]"):
        return True
    return False


def main():
    if not PROBLEMS_DIR.exists() or not any(PROBLEMS_DIR.glob("*.json")):
        print(f"В {PROBLEMS_DIR} нет скачанных задач — сначала запусти fetch_problems.py")
        raise SystemExit(1)

    problems = load_problems()
    tags_by_id, binary_tags_by_id = load_tags()
    if not tags_by_id:
        print("!!! ВНИМАНИЕ: tags.json не найден или пуст — теги будут показаны голыми id.")

    lines = []

    def out(s=""):
        lines.append(s)

    total = len(problems)
    out(f"Сводка по выгрузке SolveHub — всего файлов: {total}")
    out("=" * 70)

    # --- Целостность: обе проверки должны дать 0 ---
    out("\n--- ПРОВЕРКИ ЦЕЛОСТНОСТИ (должны дать 0) ---")
    no_source_url = [p.get("hash") for p in problems if not p.get("_source_url")]
    no_ai_generated = [p.get("hash") for p in problems if p.get("ai_generated") is None or "ai_generated" not in p]
    out(f"Файлов БЕЗ _source_url: {len(no_source_url)}")
    if no_source_url:
        out(f"  ПЕРВЫЕ 20: {no_source_url[:20]}")
    out(f"Файлов, где ai_generated отсутствует/null: {len(no_ai_generated)}")
    if no_ai_generated:
        out(f"  ПЕРВЫЕ 20: {no_ai_generated[:20]}")
    integrity_ok = not no_source_url and not no_ai_generated
    out(f"\n{'ЦЕЛОСТНОСТЬ: OK' if integrity_ok else '!!! ЕСТЬ ОШИБКИ ЦЕЛОСТНОСТИ — СМ. ВЫШЕ !!!'}")

    # --- Основная статистика ---
    out("\n--- ОСНОВНАЯ СТАТИСТИКА ---")
    n_test = sum(1 for p in problems if p.get("is_test") is True)
    n_not_test = sum(1 for p in problems if p.get("is_test") is False)
    out(f"Всего задач: {total}")
    out(f"  is_test = true (тесты): {n_test}")
    out(f"  is_test = false (открытые задачи): {n_not_test}")
    out(f"С непустым answer_md (есть решение): {sum(1 for p in problems if (p.get('answer_md') or '').strip())}")
    out(f"С непустым correct_answer: {sum(1 for p in problems if p.get('correct_answer'))}")
    out(f"С непустым criteria: {sum(1 for p in problems if not is_empty_criteria(p.get('criteria')))}")
    out(f"ai_generated = true: {sum(1 for p in problems if p.get('ai_generated') is True)}")
    out(
        "approved = false ИЛИ hidden = true: "
        f"{sum(1 for p in problems if p.get('approved') is False or p.get('hidden') is True)}"
    )

    # --- difficulty (дословно) ---
    out("\n--- РАСПРЕДЕЛЕНИЕ ПО difficulty (значения дословно) ---")
    diff_counter = Counter(p.get("difficulty") for p in problems)
    for value, count in diff_counter.most_common():
        out(f"  {value!r}: {count}")

    # --- топ-40 тегов ---
    out("\n--- ТОП-40 ТЕГОВ из tagList (название дословно, если есть в справочнике) ---")
    tag_counter = Counter()
    for p in problems:
        for tid in (p.get("tagList") or []):
            tag_counter[tid] += 1
    for tid, count in tag_counter.most_common(40):
        info = tags_by_id.get(tid)
        label = f'{info["name"]!r} (is_topic={info["is_topic"]})' if info else "(нет в справочнике)"
        out(f"  id={tid} {label}: {count}")

    # --- все значения binaryTagList ---
    out("\n--- ВСЕ ЗНАЧЕНИЯ binaryTagList (расшифровка по справочнику) ---")
    btag_counter = Counter()
    for p in problems:
        for bt in (p.get("binaryTagList") or []):
            btag_counter[(bt.get("id"), bt.get("value"))] += 1
    for (bid, value), count in btag_counter.most_common():
        info = binary_tags_by_id.get(bid)
        label = f'{info["filter_title"]}: {info["name_1"] if value else info["name_0"]}' if info else "(нет в справочнике)"
        out(f"  id={bid} value={value} {label!r}: {count}")

    # --- бинарный тег «Язык» отдельно (решение Макара про английские задачи) ---
    out("\n--- БИНАРНЫЙ ТЕГ «Язык» ОТДЕЛЬНО ---")
    lang_tag_id = next((tid for tid, info in binary_tags_by_id.items() if info.get("filter_title") == "Язык"), None)
    if lang_tag_id is None:
        out("  тег «Язык» не найден в tags.json — не могу посчитать")
    else:
        info = binary_tags_by_id[lang_tag_id]
        for value in (False, True):
            count = btag_counter.get((lang_tag_id, value), 0)
            label = info["name_1"] if value else info["name_0"]
            out(f"  {label}: {count}")
        with_tag = sum(btag_counter.get((lang_tag_id, v), 0) for v in (False, True))
        out(f"  без этого тега вообще (язык не указан): {total - with_tag}")

    # --- источники ---
    out("\n--- ТОП-30 ЗНАЧЕНИЙ source (олимпиада-источник) ---")
    source_counter = Counter((p.get("source") or "").strip() for p in problems)
    for value, count in source_counter.most_common(30):
        out(f"  {value!r}: {count}")

    # --- картинки ---
    out("\n--- КАРТИНКИ ---")
    n_with_images = 0
    n_refs_total = 0
    unique_image_urls = set()
    for p in problems:
        urls = set()
        for field in ("md", "answer_md"):
            urls.update(IMAGE_URL_RE.findall(p.get(field) or ""))
        if urls:
            n_with_images += 1
        n_refs_total += len(urls)
        unique_image_urls.update(urls)
    out(f"Задач с картинками: {n_with_images}")
    out(f"Всего ссылок на картинки (с повторами по задачам): {n_refs_total}")
    out(f"Из них уникальных файлов: {len(unique_image_urls)}")

    # --- LaTeX ---
    out("\n--- LaTeX ---")
    n_latex = sum(1 for p in problems if LATEX_RE.search(p.get("md") or ""))
    out(f"Задач с LaTeX-командами (\\ + буква) в md: {n_latex}")

    # --- длина условий ---
    out("\n--- ДЛИНА УСЛОВИЙ (md) — ловим мусор и обрывки ---")
    with_len = sorted(
        ((len(p.get("md") or ""), p.get("hash"), (p.get("title") or "")[:60]) for p in problems)
    )
    out("10 самых коротких:")
    for length, h, title in with_len[:10]:
        out(f"  {length} символов, {h}: {title!r}")
    out("10 самых длинных:")
    for length, h, title in with_len[-10:][::-1]:
        out(f"  {length} символов, {h}: {title!r}")

    # --- флаги-не-темы (is_topic=false) ---
    out("\n--- ФЛАГИ-НЕ-ТЕМЫ (is_topic=false) — сколько задач помечено каждым ---")
    non_topic_tags = [t for t in tags_by_id.values() if not t.get("is_topic")]
    if not non_topic_tags:
        out("  справочник тегов недоступен — не могу посчитать")
    else:
        for t in sorted(non_topic_tags, key=lambda t: -tag_counter.get(t["id"], 0)):
            out(f"  {t['name']!r} (id={t['id']}): {tag_counter.get(t['id'], 0)}")

    # --- задачи вовсе без темы ---
    out("\n--- ЗАДАЧИ БЕЗ ЕДИНОЙ ТЕМЫ (is_topic=true) ---")
    topic_ids = {tid for tid, t in tags_by_id.items() if t.get("is_topic")}
    if not topic_ids:
        out("  справочник тегов недоступен — не могу посчитать")
    else:
        n_no_topic = sum(1 for p in problems if not (set(p.get("tagList") or []) & topic_ids))
        out(f"Задач без единой темы (придётся размечать самим): {n_no_topic}")

    report = "\n".join(lines)
    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        f.write(report)
    print(report)
    print(f"\n(сохранено также в {SUMMARY_FILE})")


if __name__ == "__main__":
    main()
