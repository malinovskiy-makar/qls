"""
БОЕВОЙ МИНИ-ПИЛОТ ИИ-ОБОГАЩЕНИЯ (первый прогон через API).
Сравнивает Haiku vs Sonnet на ГРЯЗНЫХ задачах (фокус — чистка текста),
плюс несколько случайных для проверки формата.

НЕ пишет в базу: результат — только текстовый файл-отчёт.
Двухфазная защита: без --confirm НИ ОДНОГО обращения к API (только показывает
выборку и оценку стоимости). С --confirm — делает вызовы (это копейки).
Ключ: переменная окружения ANTHROPIC_API_KEY, иначе файл anthropic_key.txt. В коде НЕ хранится.
"""
from typing import Optional, List, Dict, Tuple
import os
import re
import json
import time
import random

from django.core.management.base import BaseCommand
from problems.models import Problem

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"
CHARS_PER_TOKEN = 2.23  # замерено на этой базе
RATES = {"haiku": {"in": 1.0, "out": 5.0}, "sonnet": {"in": 3.0, "out": 15.0}}

ALLOWED_TAGS = [
    "эластичность спроса по цене", "точечная эластичность", "постоянная эластичность",
    "линейный спрос", "рыночное равновесие", "потребительский излишек",
    "функция издержек", "предельные издержки", "кусочные издержки",
    "функция предложения фирмы", "минимизация издержек", "многозаводская фирма",
    "дискретный выпуск", "совершенная конкуренция", "монополия",
    "монополистическая конкуренция", "олигополия", "вход и выход фирм",
    "долгосрочное равновесие", "ценовая дискриминация первой степени",
    "ценовая дискриминация второй степени", "ценовая дискриминация третьей степени",
    "двухчастный тариф", "нелинейное ценообразование", "отрицательная экстерналия",
    "общественное благосостояние", "потоварный налог", "государственное регулирование",
    "прямые и косвенные налоги", "бюджетная система РФ", "обратная индукция",
    "последовательные игры", "голосование", "кривая производственных возможностей",
    "альтернативные издержки", "сравнительные преимущества", "выгоды обмена",
    "относительные цены", "совокупный спрос", "уровень цен", "темп инфляции",
    "номинальные и реальные величины", "экономический рост", "человеческий капитал",
    "качественный вопрос", "тестовый вопрос", "открытый ответ",
]

SYSTEM_PROMPT = """Ты — редактор банка олимпиадных задач по экономике. Тебе дают ОДНУ задачу.
Верни СТРОГО один JSON-объект и НИЧЕГО больше — без пояснений, без markdown-ограждений.

Поля JSON:
- "type": одно из "расчётная" | "теория" | "качественная" | "не_задача".
    "не_задача" — служебный текст/обрывок/заметка о критериях, а не условие.
- "given": для "расчётной" — строка "Дано: …" (кратко). Иначе null.
- "find": для "расчётной" — строка "Найти: …". Иначе null.
- "summary": для "теория"/"качественная" — одна строка сути. Иначе null.
- "topic_suggestion": краткое название экономической темы (свободно, как подсказка); если непонятно — "".
- "title_suggestion": короткий осмысленный заголовок (до ~8 слов), без обрывов и мусора.
- "tags": массив подтем СТРОГО из ALLOWED_TAGS (только подходящие; можно пустой).
- "new_tags": массив подходящих подтем, которых НЕТ в ALLOWED_TAGS (предложение в словарь). Можно пустой.
- "cleaned_statement": почищенный текст условия; если чистить нечего — верни исходный без изменений.
- "flags": массив из "incomplete_missing_figure" и/или "not_a_problem"; если ничего — пустой массив.

ПРАВИЛА ЧИСТКИ (cleaned_statement):
- Чини только форму: битый LaTeX (напр. \\begin{cases} без \\\\), слипшиеся $…$ и текст,
  OCR-замены (латинские буквы внутри русских слов), задвоенные скобки "(а))",
  задвоенные слова, лишние пробелы, болтающиеся обрывки вроде "$$…$$".
- НИКОГДА не меняй числа, формулы, переменные и смысл. Не добавляй и не убирай
  содержательные части. Не переводи — сохраняй язык оригинала.

КРИТИЧЕСКОЕ ПРАВИЛО — отсутствующие данные:
- Если условие ссылается на рисунок/график/таблицу/«данные», которых в тексте НЕТ
  (пустые места, обрывки осей, «приведена кривая …», «data on a survey …» без самих данных) —
  поставь flag "incomplete_missing_figure", НЕ выдумывай недостающее, НЕ дорисовывай его в
  cleaned_statement, а given/find/summary опиши только по тому, что реально есть.

Язык: given/find/summary/tags — всегда по-русски. cleaned_statement — на языке оригинала."""


def get_source_name(p):
    # type: (Problem) -> str
    refs = list(p.source_references.all())
    if refs and getattr(refs[0], "source", None):
        return refs[0].source.name or ""
    return ""


def build_parts(p):
    # type: (Problem) -> str
    out = []
    for part in p.parts.all():
        label = getattr(part, "label", "") or ""
        st = (getattr(part, "statement", "") or "").strip()
        if st:
            out.append("({}) {}".format(label, st) if label else st)
    return "\n".join(out)


def dirtiness(statement, parts):
    # type: (str, str) -> Tuple[int, List[str]]
    full = (statement or "") + "\n" + (parts or "")
    score, sig = 0, []
    if full.count("$") % 2 == 1:
        score += 2; sig.append("непарные $")
    if "\\begin{cases}" in full and "\\\\" not in full:
        score += 2; sig.append("битый cases")
    if "((" in full or "))" in full:
        score += 1; sig.append("задвоенные скобки")
    if re.search(r"[а-яё][a-z][а-яё]", full, re.IGNORECASE):
        score += 2; sig.append("латиница в слове (OCR)")
    if re.search(r"\b(\w{3,})\s+\1\b", full, re.IGNORECASE):
        score += 1; sig.append("задвоенное слово")
    fig_words = ["таблиц", "график", "рисун", "приведена крив", "на рисунке",
                 "figure", "the data", "data on", "survey"]
    has_fig = any(w in full.lower() for w in fig_words)
    gappy = bool(re.search(r"\n\s*\n\s*\n", full))
    if has_fig and (len((statement or "").strip()) < 220 or gappy):
        score += 2; sig.append("возможен потерянный рисунок/таблица")
    if gappy:
        score += 1; sig.append("разрыв (пустые строки)")
    return score, sig


def read_key():
    # type: () -> Optional[str]
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key.strip()
    try:
        with open("anthropic_key.txt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    return line
    except FileNotFoundError:
        return None
    return None


def parse_json(text):
    # type: (str) -> Dict
    raw = (text or "").strip()
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(cleaned[start:end + 1])
        except Exception:
            pass
    return {"_parse_error": True, "_raw": raw}


def call_model(client, model, user):
    # type: (object, str, str) -> Dict
    for attempt in range(3):
        try:
            resp = client.messages.create(
                model=model, max_tokens=3000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user}],
            )
            text = "".join(getattr(b, "text", "") for b in resp.content
                           if getattr(b, "type", None) == "text")
            return parse_json(text)
        except Exception as e:
            if attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            return {"_error": str(e)}
    return {"_error": "unknown"}


def fmt_block(label, d):
    # type: (str, Dict) -> List[str]
    L = ["---- {} ----".format(label)]
    if "_error" in d:
        L.append("ОШИБКА API: {}".format(d["_error"]))
        return L
    if d.get("_parse_error"):
        L.append("JSON не распарсился. Сырой ответ:")
        L.append(d.get("_raw", ""))
        return L
    L.append("тип: {}   флаги: {}".format(d.get("type", "—"), d.get("flags", [])))
    if d.get("given") or d.get("find"):
        L.append(d.get("given") or "Дано: —")
        L.append(d.get("find") or "Найти: —")
    if d.get("summary"):
        L.append("Суть: {}".format(d["summary"]))
    L.append("тема (подсказка): {}".format(d.get("topic_suggestion", "")))
    L.append("заголовок (подсказка): {}".format(d.get("title_suggestion", "")))
    L.append("теги: {}".format(d.get("tags", [])))
    L.append("новые теги: {}".format(d.get("new_tags", [])))
    L.append("ЧИСТКА:")
    L.append(d.get("cleaned_statement", "—"))
    return L


class Command(BaseCommand):
    help = "Боевой мини-пилот обогащения: Haiku vs Sonnet на грязных задачах. НЕ пишет в базу."

    def add_arguments(self, parser):
        parser.add_argument("--dirty", type=int, default=24)
        parser.add_argument("--random", type=int, default=6)
        parser.add_argument("--confirm", action="store_true",
                            help="Без него API НЕ вызывается (только показ выборки и оценка).")
        parser.add_argument("--out", type=str, default="pilot_results.txt")
        parser.add_argument("--seed", type=int, default=None)

    def handle(self, *args, **opts):
        if opts["seed"] is not None:
            random.seed(opts["seed"])

        # Пасс 1 — потоково считаем грязь, держим только лёгкие кортежи.
        qs = (Problem.objects.filter(status="published")
              .prefetch_related("parts", "source_references__source"))
        # (score, id, sig, char_len)
        scored = []
        skipped_ile = 0
        for p in qs.iterator(chunk_size=300):
            name = get_source_name(p).lower()
            if "ile" in name or "iloveeconomics" in name:
                skipped_ile += 1
                continue
            statement = p.statement or ""
            parts = build_parts(p)
            sc, sig = dirtiness(statement, parts)
            scored.append((sc, p.id, sig, len(statement) + len(parts)))

        self.stdout.write("Опубликованных (без ILE): {:,}. Исключено ILE: {:,}.".format(
            len(scored), skipped_ile))

        scored.sort(key=lambda t: -t[0])
        dirty = [t for t in scored if t[0] > 0][:opts["dirty"]]
        dirty_set = set(id(t) for t in dirty)
        rest = [t for t in scored if id(t) not in dirty_set]
        rnd = random.sample(rest, min(opts["random"], len(rest))) if rest else []
        chosen = dirty + rnd
        chosen_ids = [t[1] for t in chosen]
        sig_by_id = {t[1]: t[2] for t in chosen}

        # Догружаем выбранные целиком.
        objs = {p.id: p for p in Problem.objects.filter(id__in=chosen_ids)
                .prefetch_related("parts", "source_references__source", "topics")}
        ordered = [objs[i] for i in chosen_ids if i in objs]

        # Оценка стоимости (без API).
        in_tok = out_tok = 0.0
        sys_len = len(SYSTEM_PROMPT) + len(", ".join(ALLOWED_TAGS))
        for p in ordered:
            body = len((p.statement or "") + build_parts(p))
            in_tok += (sys_len + body + 200) / CHARS_PER_TOKEN
            out_tok += body / CHARS_PER_TOKEN + 150
        cost = {}
        for m in ("haiku", "sonnet"):
            cost[m] = in_tok / 1e6 * RATES[m]["in"] + out_tok / 1e6 * RATES[m]["out"]
        total = cost["haiku"] + cost["sonnet"]

        self.stdout.write("")
        self.stdout.write("=== ВЫБРАНО {} задач (грязных {} + случайных {}) ===".format(
            len(ordered), len(dirty), len(rnd)))
        for t in chosen:
            self.stdout.write("  #{:<6} грязь={}  {}".format(
                t[1], t[0], ", ".join(t[2]) or "—"))
        self.stdout.write("")
        self.stdout.write(
            "Оценка стоимости обоих прогонов: ~${:.2f} "
            "(Haiku ~${:.2f} + Sonnet ~${:.2f}). "
            "Вызовов к API: {}.".format(
                total, cost["haiku"], cost["sonnet"], len(ordered) * 2))

        if not opts["confirm"]:
            self.stdout.write("")
            self.stdout.write("ФАЗА ПОКАЗА: API НЕ вызывался, денег не потрачено.")
            self.stdout.write("Если выборка ок — запусти ту же команду с флагом --confirm.")
            return

        key = read_key()
        if not key:
            self.stdout.write("Ключ не найден. Вставь его в anthropic_key.txt "
                              "(одной строкой) или задай ANTHROPIC_API_KEY. Отмена.")
            return

        from anthropic import Anthropic
        client = Anthropic(api_key=key)

        self.stdout.write("")
        self.stdout.write("ФАЗА ПРОГОНА: {} вызовов…".format(len(ordered) * 2))
        tags_line = ", ".join(ALLOWED_TAGS)
        report = []
        stats = {"flag_fig": 0, "flag_notprob": 0, "parse_err": 0, "api_err": 0}

        for n, p in enumerate(ordered, 1):
            parts = build_parts(p)
            cur_topic = ", ".join(t.name for t in p.topics.all()) or "—"
            user = (
                "ALLOWED_TAGS: {}\n\n"
                "Задача (id {}; текущая тема в базе: «{}»):\n"
                "ЗАГОЛОВОК: {}\n"
                "УСЛОВИЕ:\n{}\n"
                "ПОДПУНКТЫ:\n{}"
            ).format(
                tags_line, p.id, cur_topic,
                p.title or "—",
                (p.statement or "—").strip(),
                parts or "—",
            )

            h = call_model(client, HAIKU, user)
            s = call_model(client, SONNET, user)
            for d in (h, s):
                if "_error" in d:
                    stats["api_err"] += 1
                elif d.get("_parse_error"):
                    stats["parse_err"] += 1
                else:
                    fl = d.get("flags", [])
                    if "incomplete_missing_figure" in fl:
                        stats["flag_fig"] += 1
                    if "not_a_problem" in fl:
                        stats["flag_notprob"] += 1

            report.append("=" * 80)
            report.append("ЗАДАЧА #{} | {} | тема в базе: {}".format(
                p.id, get_source_name(p), cur_topic))
            report.append("dirtiness-сигналы: {}".format(
                ", ".join(sig_by_id.get(p.id, [])) or "—"))
            report.append("[ИСХОДНЫЙ ЗАГОЛОВОК] {}".format(p.title or "—"))
            report.append("[ИСХОДНОЕ УСЛОВИЕ]")
            report.append((p.statement or "—").strip())
            if parts:
                report.append("[ПОДПУНКТЫ]")
                report.append(parts)
            report.append("")
            report.extend(fmt_block("HAIKU", h))
            report.append("")
            report.extend(fmt_block("SONNET", s))
            report.append("")
            self.stdout.write("  [{}/{}] #{} готово".format(n, len(ordered), p.id))

        with open(opts["out"], "w", encoding="utf-8") as f:
            f.write("\n".join(report))

        self.stdout.write("")
        self.stdout.write("Отчёт: {}".format(opts["out"]))
        self.stdout.write(
            "Помечено «потерян рисунок/таблица»: {}; "
            "«не задача»: {}; "
            "ошибок парсинга: {}; ошибок API: {}.".format(
                stats["flag_fig"], stats["flag_notprob"],
                stats["parse_err"], stats["api_err"]))
