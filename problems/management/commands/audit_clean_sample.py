"""
Аудит «чистых» задач: даём Sonnet прочитать случайную выборку задач, которые
детектор считает чистыми, и проверяем, есть ли пропущенные дефекты.
Двухфазно: без --confirm НЕ вызывает API (показ выборки + оценка). С --confirm — вызывает Sonnet.
В базу НЕ пишет. Ключ: ANTHROPIC_API_KEY или anthropic_key.txt.
"""
from typing import Optional, List, Tuple
from collections import Counter
import os
import re
import json
import time
import random

from django.core.management.base import BaseCommand
from problems.models import Problem

SONNET = "claude-sonnet-4-6"
CHARS_PER_TOKEN = 2.23
IN_RATE = 3.0    # Sonnet, полная цена (синхронно, без Batch)
OUT_RATE = 15.0
OCR_MARKERS = ["jдолл", "р.j", "\x0c", ":купа"]

FIXABLE = {"broken_latex", "ocr_corruption", "duplicated"}       # чистка починит
NEEDS_REIMPORT = {"missing_figure", "truncated"}                 # чистка НЕ починит

SYSTEM_PROMPT = """Ты — корректор банка олимпиадных задач по экономике. Тебе дают СЫРОЙ текст
одной задачи (как он лежит в базе). Определи, есть ли в нём РЕАЛЬНЫЙ дефект, который мешает
правильному отображению или чтению. Верни СТРОГО один JSON и ничего больше.

Что считать дефектом (category):
- "broken_latex": формула не отрисуется (битый \\begin{cases}/\\begin{aligned} без \\\\, незакрытые $, поехавшие команды).
- "ocr_corruption": покорёженные при сканировании символы/слова (латинские буквы внутри русских слов, двоеточия/точки внутри слов, «О» вместо нуля).
- "duplicated": задвоенные слова или фрагменты.
- "truncated": текст обрывается на полуслове, условие явно неполное.
- "missing_figure": условие ссылается на рисунок/график/таблицу/данные, которых в тексте НЕТ.
- "other": иной явный дефект (опиши в note).

Дефектом НЕ считать: корректный LaTeX (в т.ч. \\bigl((, \\item, маркеры •), намеренно длинный сюжет,
стиль, орфографические мелочи, отсутствие решения.

Формат JSON:
{"defect": true|false, "category": "ok"|"broken_latex"|"ocr_corruption"|"duplicated"|"truncated"|"missing_figure"|"other", "severity": "minor"|"major", "note": "кратко, до 12 слов"}
Если дефектов нет: {"defect": false, "category": "ok", "severity": "minor", "note": ""}."""


def get_source_name(p) -> str:
    refs = list(p.source_references.all())
    if refs and getattr(refs[0], "source", None):
        return refs[0].source.name or "—"
    return "—"


def body_text(p) -> str:
    parts = []
    if p.statement:
        parts.append(p.statement)
    for part in p.parts.all():
        st = getattr(part, "statement", "") or ""
        if st:
            parts.append(st)
    return "\n".join(parts)


def ocr_signals(text: str) -> List[str]:
    sig = []
    if re.search(r"[а-яё][a-z]{1,2}[а-яё]", text, re.IGNORECASE):
        sig.append("латиница")
    if re.search(r"[а-яё]:[а-яё]", text):
        sig.append("двоеточие в слове")
    if any(m in text for m in OCR_MARKERS):
        sig.append("OCR-обломки")
    if re.search(r"\b(\w{3,})\s+\1\b", text, re.IGNORECASE):
        sig.append("задвоенное слово")
    return sig


def cases_broken(text: str) -> bool:
    for m in re.finditer(r"\\begin\{(cases|aligned)\}(.*?)\\end\{\1\}", text, re.S):
        if "\\\\" not in m.group(2):
            return True
    return False


def read_key() -> Optional[str]:
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


def parse_json(text: str) -> dict:
    raw = (text or "").strip().replace("```json", "").replace("```", "").strip()
    a, b = raw.find("{"), raw.rfind("}")
    if a != -1 and b != -1 and b > a:
        try:
            return json.loads(raw[a:b + 1])
        except Exception:
            pass
    return {"_parse_error": True, "_raw": raw[:200]}


class Command(BaseCommand):
    help = "Аудит чистых задач через Sonnet. Без --confirm не вызывает API."

    def add_arguments(self, parser):
        parser.add_argument("--sample", type=int, default=150)
        parser.add_argument("--confirm", action="store_true",
                            help="Без него API НЕ вызывается (только показ и оценка).")
        parser.add_argument("--out", type=str, default="clean_audit.txt")
        parser.add_argument("--seed", type=int, default=2026)

    def handle(self, *args, **opts):
        random.seed(opts["seed"])
        qs = (Problem.objects.filter(status="published", multiple_problems=False)
              .prefetch_related("parts", "source_references__source"))

        clean_ids: List[int] = []
        for p in qs.iterator(chunk_size=300):
            src = get_source_name(p)
            if "ile" in src.lower() or "iloveeconomics" in src.lower():
                continue
            body = body_text(p)
            if ocr_signals(body) or cases_broken(body):
                continue  # это НЕ «чистая» — детектор её поймал
            clean_ids.append(p.id)

        self.stdout.write(f"«Чистых» задач (детектор ничего не нашёл): {len(clean_ids):,}")
        if not clean_ids:
            return

        k = min(opts["sample"], len(clean_ids))
        sample_ids = random.sample(clean_ids, k)
        objs = {p.id: p for p in Problem.objects.filter(id__in=sample_ids)
                .prefetch_related("parts", "source_references__source")}

        # Оценка стоимости.
        sys_chars = len(SYSTEM_PROMPT)
        in_tok = out_tok = 0.0
        for pid in sample_ids:
            body = body_text(objs[pid])
            in_tok += (sys_chars + len(body)) / CHARS_PER_TOKEN
            out_tok += 60
        cost = in_tok / 1e6 * IN_RATE + out_tok / 1e6 * OUT_RATE
        self.stdout.write("")
        self.stdout.write(f"Выборка для аудита: {k} случайных «чистых» задач.")
        self.stdout.write(f"Оценка стоимости (Sonnet, синхронно): ~${cost:.2f}. Вызовов к API: {k}.")

        if not opts["confirm"]:
            self.stdout.write("")
            self.stdout.write("ФАЗА ПОКАЗА: API не вызывался, денег не потрачено.")
            self.stdout.write("Если ок — запусти ту же команду с флагом --confirm.")
            return

        key = read_key()
        if not key:
            self.stdout.write("Ключ не найден (anthropic_key.txt или ANTHROPIC_API_KEY). Отмена.")
            return
        from anthropic import Anthropic
        client = Anthropic(api_key=key)

        self.stdout.write("")
        self.stdout.write(f"ПРОГОН: {k} вызовов Sonnet...")
        cat_counter = Counter()
        sev_counter = Counter()
        n_defect = n_ok = n_err = 0
        rows = []

        for i, pid in enumerate(sample_ids, 1):
            p = objs[pid]
            body = body_text(p)
            verdict = None
            for attempt in range(3):
                try:
                    resp = client.messages.create(
                        model=SONNET, max_tokens=300, system=SYSTEM_PROMPT,
                        messages=[{"role": "user", "content": body[:8000]}])
                    txt = "".join(getattr(b, "text", "") for b in resp.content
                                  if getattr(b, "type", None) == "text")
                    verdict = parse_json(txt)
                    break
                except Exception as e:
                    if attempt < 2:
                        time.sleep(3 * (attempt + 1))
                        continue
                    verdict = {"_error": str(e)}
            if verdict.get("_error"):
                n_err += 1
                continue
            if verdict.get("_parse_error"):
                n_err += 1
                rows.append((pid, get_source_name(p), "parse_error", "", verdict.get("_raw", ""), body))
                continue
            cat = verdict.get("category", "ok")
            sev = verdict.get("severity", "minor")
            note = verdict.get("note", "")
            defect = bool(verdict.get("defect"))
            cat_counter[cat] += 1
            if defect and cat != "ok":
                n_defect += 1
                sev_counter[sev] += 1
                rows.append((pid, get_source_name(p), cat, sev, note, body))
            else:
                n_ok += 1
            if i % 25 == 0:
                self.stdout.write(f"  {i}/{k}...")

        # Файл-отчёт: все найденные дефекты.
        lines = [f"Дефекты, найденные Sonnet в выборке «чистых» ({n_defect} из {k}). "
                 f"Проверь глазами несколько — не преувеличивает ли Sonnet.", ""]
        for pid, src, cat, sev, note, body in rows:
            lines.append("=" * 80)
            lines.append(f"ЗАДАЧА #{pid} | {src} | {cat}/{sev} | {note}")
            lines.append("-" * 80)
            lines.append(body.strip()[:2000])
            lines.append("")
        with open(opts["out"], "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        # Сводка.
        checked = n_defect + n_ok
        fixable = sum(cat_counter[c] for c in FIXABLE)
        reimport = sum(cat_counter[c] for c in NEEDS_REIMPORT)
        rate = 100.0 * n_defect / checked if checked else 0
        self.stdout.write("")
        self.stdout.write("=" * 60)
        self.stdout.write(f"Проверено успешно: {checked} (ошибок API/парсинга: {n_err})")
        self.stdout.write(f"С дефектом: {n_defect}  ({rate:.0f}% выборки «чистых»)")
        self.stdout.write("")
        self.stdout.write("=== ПО ТИПАМ ДЕФЕКТА ===")
        for cat, c in cat_counter.most_common():
            self.stdout.write(f"  {cat:<16} {c:>4}")
        self.stdout.write("")
        self.stdout.write("=== ЧТО ИЗ ЭТОГО ЧИНИТ ЧИСТКА ===")
        self.stdout.write(f"  чистка Sonnet ПОЧИНИТ (broken_latex/ocr/duplicated): {fixable}")
        self.stdout.write(f"  чистка НЕ поможет (missing_figure/truncated -> пере-импорт): {reimport}")
        self.stdout.write("")
        exp = int(rate / 100.0 * len(clean_ids))
        self.stdout.write(f"ЭКСТРАПОЛЯЦИЯ на все «чистые» ({len(clean_ids):,}): "
                          f"примерно {exp:,} задач с каким-то дефектом.")
        self.stdout.write(f"Файл с найденными дефектами: {opts['out']} — проверь несколько вердиктов глазами.")
