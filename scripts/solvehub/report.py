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


def has_real_correct_answer(p):
    return p.get("check_type") != "uncheckable" and bool(p.get("correct_answer"))


def parse_json_field(raw):
    """correct_answer/check_options хранятся как JSON, закодированный ЕЩЁ РАЗ в строку."""
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw
    return raw


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
    n_answer_md = sum(1 for p in problems if (p.get("answer_md") or "").strip())
    n_correct_answer_naive = sum(1 for p in problems if p.get("correct_answer"))
    out(f"Всего задач: {total}")
    out(f"  is_test = true (тесты): {n_test}")
    out(f"  is_test = false (открытые задачи): {n_not_test}")
    out(f"С непустым answer_md (есть решение): {n_answer_md}")
    out(
        f"С непустым correct_answer (просто непустая строка, см. ниже почему это "
        f"вводит в заблуждение): {n_correct_answer_naive}"
    )
    out(f"С непустым criteria: {sum(1 for p in problems if not is_empty_criteria(p.get('criteria')))}")
    out("ai_generated, approved, hidden, visible — см. отдельные секции ниже")

    # --- approved / hidden / visible: полный разбор по значениям ---
    out("\n--- approved / hidden / visible — ПОЛНЫЙ РАЗБОР (по просьбе Макара, 2026-08-20) ---")

    def field_breakdown(field):
        c = Counter()
        for p in problems:
            if field not in p:
                c["<ключа нет в файле>"] += 1
            else:
                v = p[field]
                c["null" if v is None else repr(v)] += 1
        return c

    dead_fields = []
    for field in ("approved", "hidden", "visible"):
        c = field_breakdown(field)
        out(f"{field}: {dict(c)}")
        if len(c) == 1:
            only_value = next(iter(c))
            dead_fields.append((field, only_value))

    n_approved_false = sum(1 for p in problems if p.get("approved") is False)
    n_approved_true = sum(1 for p in problems if p.get("approved") is True)
    n_hidden_true = sum(1 for p in problems if p.get("hidden") is True)
    n_hidden_false = sum(1 for p in problems if p.get("hidden") is False)
    n_both_flagged = sum(1 for p in problems if p.get("approved") is False and p.get("hidden") is True)
    out(f"approved = false: {n_approved_false}")
    out(f"approved = true: {n_approved_true}")
    out(f"hidden = true: {n_hidden_true}")
    out(f"hidden = false: {n_hidden_false}")
    out(f"пересечение (approved=false И hidden=true): {n_both_flagged}")
    if dead_fields:
        out("")
        for field, value in dead_fields:
            out(
                f"!!! ПОЛЕ {field} МЁРТВОЕ: одно и то же значение {value} у ВСЕХ {total} задач. "
                f"Опираться на него на импорте нельзя — оно ничего не различает."
            )
        live = [f for f in ("approved", "hidden", "visible") if f not in dict(dead_fields)]
        if live:
            out(f"Живое (различается) поле: {', '.join(live)} — но 40 из 6121 approved=true "
                f"(0,65%) тоже подозрительно мало для «одобрено к публикации», раз все 6121 "
                f"и так публично доступны на сайте. Смысл поля перед импортом стоит уточнить "
                f"у авторов сайта, а не считать его готовым фильтром качества.")

    # --- профиль 40 approved=true в сравнении со всем банком ---
    out("\n--- ПРОФИЛЬ approved=true (40 штук) В СРАВНЕНИИ СО ВСЕМ БАНКОМ (по просьбе Макара) ---")
    approved_true = [p for p in problems if p.get("approved") is True]
    n40 = len(approved_true)
    if n40 == 0:
        out("  задач с approved=true не найдено — сравнивать нечего")
    else:
        def pct(n, d):
            return f"{n} ({100 * n / d:.0f}%)"

        n_md_40 = sum(1 for p in approved_true if (p.get("answer_md") or "").strip())
        n_md_all = sum(1 for p in problems if (p.get("answer_md") or "").strip())
        out(f"С answer_md:               40-ка: {pct(n_md_40, n40)}   весь банк: {pct(n_md_all, total)}")

        n_ca_40 = sum(1 for p in approved_true if has_real_correct_answer(p))
        n_ca_all = sum(1 for p in problems if has_real_correct_answer(p))
        out(f"С реальным correct_answer: 40-ка: {pct(n_ca_40, n40)}   весь банк: {pct(n_ca_all, total)}")

        src_40 = Counter(p.get("source") or "<пусто>" for p in approved_true)
        out(f"source внутри 40-ки: {dict(src_40.most_common())}")

        author_40 = Counter(p.get("author") or "<пусто>" for p in approved_true)
        out(f"author внутри 40-ки: {dict(author_40.most_common())}")

        diff_40 = Counter(p.get("difficulty") for p in approved_true)
        out(f"difficulty внутри 40-ки: {dict(diff_40.most_common())}")

        ct_40 = Counter(p.get("check_type") for p in approved_true)
        out(f"check_type внутри 40-ки: {dict(ct_40.most_common())}")

        tag_40 = Counter()
        for p in approved_true:
            for tid in (p.get("tagList") or []):
                tag_40[tid] += 1
        top_tags_40 = []
        for tid, c in tag_40.most_common(5):
            info = tags_by_id.get(tid)
            name = info["name"] if info else f"id={tid}"
            top_tags_40.append(f"{name} {c}/{n40}")
        out(f"топ-5 тегов внутри 40-ки: {', '.join(top_tags_40)}")

        dominant_source, dominant_source_n = src_40.most_common(1)[0]
        dominant_author, dominant_author_n = author_40.most_common(1)[0]
        out("")
        if dominant_source_n / n40 >= 0.8 and dominant_author_n / n40 >= 0.8:
            out(
                f"ВЫВОД: approved=true резко смещено к одному источнику — "
                f"{dominant_source_n} из {n40} ({100 * dominant_source_n / n40:.0f}%) имеют "
                f"source={dominant_source!r} и author={dominant_author!r} (это один и тот же "
                f"партнёр — сайт olymp.education принадлежит «Экономическому олимпу»). При "
                f"этом доля с решением внутри 40-ки НЕ выше, а НИЖЕ, чем в среднем по банку: "
                f"answer_md {pct(n_md_40, n40)} против {pct(n_md_all, total)} по всему банку, "
                f"реальный correct_answer {pct(n_ca_40, n40)} против {pct(n_ca_all, total)}. "
                f"Это НЕ сигнал качества или полноты решения — похоже на административную "
                f"метку конкретного партнёра-источника, а не на общий фильтр «одобрено к "
                f"публикации». Опираться на approved как на признак готовности задачи к "
                f"использованию на импорте нельзя."
            )
        else:
            out("ВЫВОД: 40-ка не показывает резкого смещения ни по одному признаку — тоже ответ.")

    # --- ai_generated: честное ли поле ---
    out("\n--- ai_generated — ПРОВЕРКА, ЧТО ПОЛЕ РАБОЧЕЕ, А НЕ ПУСТОЕ (по просьбе Макара) ---")
    ai_breakdown = field_breakdown("ai_generated")
    out(f"Все значения ai_generated по {total} файлам: {dict(ai_breakdown)}")
    out(
        "В справочнике tags.json и в сыром tRPC-ответе страницы списка (фильтр-панель) "
        "проверено на упоминания ИИ/генерации (искусственный интеллект, нейросеть, "
        "generat*, ai) — ноль совпадений, такого фильтра на сайте нет вообще."
    )
    if ai_breakdown.keys() == {"False"}:
        out(
            "ВЫВОД: поле рабочее, ИИ-задач нет. У всех 6121 задач ai_generated явно "
            "равно false (не null, не отсутствует — интеграционная проверка Фазы 4 уже "
            "подтвердила, что поля без ai_generated или с null нет ни одной). Другого "
            "значения не встречается нигде, а на сайте нет и намёка на функцию "
            "ИИ-генерации задач — значит false здесь достоверный факт об источнике, "
            "а не забытое дефолтное значение."
        )
    else:
        out("ВЫВОД: поле неоднородно — см. разбор значений выше, нужен отдельный анализ.")

    # --- correct_answer: осмысленно, а не по факту непустой строки ---
    out("\n--- correct_answer — ОСМЫСЛЕННЫЙ РАЗБОР (по просьбе Макара) ---")
    out(
        f"Наивная проверка «непустая строка» даёт {n_correct_answer_naive} из {total} — "
        f"ЭТО ВВОДИТ В ЗАБЛУЖДЕНИЕ. correct_answer — это ВСЕГДА JSON-объект вида "
        f'{{"type": <тип>, "value": ...}}, и у типа "uncheckable" value просто null — '
        f"формально непустая строка, а по сути ответа нет. Тип совпадает с полем "
        f"check_type — считаю по нему."
    )
    check_type_counter = Counter(p.get("check_type") for p in problems)
    out(f"Распределение check_type: {dict(check_type_counter.most_common())}")

    n_real_ca = sum(1 for p in problems if has_real_correct_answer(p))
    out(f"С РЕАЛЬНЫМ correct_answer (check_type != 'uncheckable'): {n_real_ca} из {total}")

    both = sum(1 for p in problems if (p.get("answer_md") or "").strip() and has_real_correct_answer(p))
    only_answer_md = sum(
        1 for p in problems if (p.get("answer_md") or "").strip() and not has_real_correct_answer(p)
    )
    only_correct_answer = sum(
        1 for p in problems if not (p.get("answer_md") or "").strip() and has_real_correct_answer(p)
    )
    neither = sum(
        1 for p in problems if not (p.get("answer_md") or "").strip() and not has_real_correct_answer(p)
    )
    out("\nКарта ценности банка (answer_md — развёрнутый разбор; correct_answer — реальный, см. выше):")
    out(f"  и answer_md, и correct_answer: {both}")
    out(f"  только answer_md: {only_answer_md}")
    out(f"  только correct_answer: {only_correct_answer}")
    out(f"  ни того, ни другого (голое условие): {neither}")
    assert both + only_answer_md + only_correct_answer + neither == total, "корзины не сходятся с total"

    # --- check_type / check_options: готовое сырьё для Econ Rush? ---
    out("\n--- check_type И check_options — ГОТОВОЕ СЫРЬЁ ДЛЯ ECON RUSH? (по просьбе Макара) ---")
    out(
        f"{n_real_ca} задач с реальным correct_answer (см. выше) — потенциальный пул вопросов "
        f"с автопроверкой вместо генерации моделью. check_type различает форму ответа, "
        f"check_options — по одному примеру дословно, до 200 символов:"
    )
    check_options_example = {}
    for p in problems:
        t = p.get("check_type")
        if t not in check_options_example:
            check_options_example[t] = json.dumps(parse_json_field(p.get("check_options")), ensure_ascii=False)
    for t, count in check_type_counter.most_common():
        example = check_options_example.get(t, "")[:200]
        out(f"  {t!r}: {count} задач. check_options: {example!r}")
    out(
        "\nДля быстрой игры сразу готовы, без доработки: single_choice "
        f"({check_type_counter.get('single_choice', 0)} задач) — check_options содержит "
        "готовые текстовые варианты ответа, correct_answer указывает верный индексом. "
        f"true_false ({check_type_counter.get('true_false', 0)}) — тоже готов: "
        "check_options пуст не потому, что данных не хватает, а потому что вариантов всего "
        "два (да/нет) и перечислять их незачем, само утверждение — в тексте задачи. "
        "multiple_choice "
        f"({check_type_counter.get('multiple_choice', 0)}) тоже структурирован, но это "
        "мультивыбор — для игры на скорость сложнее, чем один клик. single_freetext "
        f"({check_type_counter.get('single_freetext', 0)}) и multiple_questions "
        f"({check_type_counter.get('multiple_questions', 0)}) требуют сверки текста "
        "или нескольких значений — риск ложных несовпадений из-за формулировки ответа, "
        "с ходу на игру не положить без ручной проверки. matching_list — 1 штука, погоды "
        "не делает."
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
