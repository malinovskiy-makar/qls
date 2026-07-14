"""
СЕССИЯ 2 Батча 1: забрать результаты из Batch API, разобрать, собрать сводку.
В базу НЕ пишет. Читает id из batch1_ids.txt. Ключ: ANTHROPIC_API_KEY или anthropic_key.txt.
Запускать можно сколько угодно раз: пока батч не готов — просто скажет статус.
"""
from typing import Optional, List, Dict
from collections import defaultdict, Counter
import os
import json

from django.core.management.base import BaseCommand

ALLOWED_FLAGS = {"incomplete_missing_figure", "not_a_problem", "multiple_problems"}


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


def read_ids(path: str) -> List[str]:
    ids = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    ids.append(line)
    except FileNotFoundError:
        pass
    return ids


def extract_text(message) -> str:
    """Собрать текст из message.content (список блоков)."""
    out = []
    content = getattr(message, "content", None) or []
    for block in content:
        t = getattr(block, "text", None)
        if t:
            out.append(t)
    return "".join(out)


def parse_json(text: str) -> Dict:
    raw = (text or "").strip().replace("```json", "").replace("```", "").strip()
    a, b = raw.find("{"), raw.rfind("}")
    if a != -1 and b != -1 and b > a:
        try:
            return json.loads(raw[a:b + 1])
        except Exception:
            pass
    return {"_parse_error": True, "_raw": raw[:400]}


class Command(BaseCommand):
    help = "СЕССИЯ 2 Батча 1: забрать результаты Batch API и собрать сводку. В базу не пишет."

    def add_arguments(self, parser):
        parser.add_argument("--ids-file", type=str, default="batch1_ids.txt")
        parser.add_argument("--out", type=str, default="batch1_parsed.jsonl")
        parser.add_argument("--errors", type=str, default="batch1_errors.txt")

    def handle(self, *args, **opts):
        ids = read_ids(opts["ids_file"])
        if not ids:
            self.stdout.write(f"❌ Не нашёл id батча в {opts['ids_file']}. Отмена.")
            return
        key = read_key()
        if not key:
            self.stdout.write("❌ Ключ не найден (anthropic_key.txt или ANTHROPIC_API_KEY). Отмена.")
            return

        from anthropic import Anthropic
        client = Anthropic(api_key=key)

        # 1) Проверяем готовность всех батчей.
        all_ended = True
        for bid in ids:
            mb = client.messages.batches.retrieve(bid)
            rc = mb.request_counts
            self.stdout.write(f"Батч {bid}: статус {mb.processing_status} | "
                              f"готово {rc.succeeded:,}, ошибок {rc.errored:,}, "
                              f"в работе {rc.processing:,}, истекло {rc.expired:,}, отменено {rc.canceled:,}")
            if mb.processing_status != "ended":
                all_ended = False

        if not all_ended:
            self.stdout.write("")
            self.stdout.write("⏳ Батч ещё обрабатывается. Закрой и запусти эту же команду позже — "
                              "обычно готово меньше чем за час, максимум 24 ч.")
            return

        # 2) Забираем и разбираем результаты.
        type_counts = Counter()
        flag_counts = Counter()
        new_tags_counter = Counter()
        tag_counts = Counter()
        n_ok = n_err = n_parse_err = 0
        n_given = n_summary = n_title = n_topic = 0
        errors: List[str] = []

        with open(opts["out"], "w", encoding="utf-8") as fout:
            for bid in ids:
                for entry in client.messages.batches.results(bid):
                    cid = entry.custom_id
                    res = entry.result
                    if res.type != "succeeded":
                        n_err += 1
                        errors.append(f"{cid}\t{res.type}")
                        continue
                    n_ok += 1
                    text = extract_text(res.message)
                    data = parse_json(text)
                    if data.get("_parse_error"):
                        n_parse_err += 1
                        errors.append(f"{cid}\tparse_error\t{data.get('_raw','')[:200]}")
                        # всё равно пишем строку, чтобы ничего не потерять
                    # Статистика
                    t = data.get("type", "—")
                    type_counts[t] += 1
                    for fl in (data.get("flags") or []):
                        flag_counts[fl] += 1
                    for tg in (data.get("tags") or []):
                        tag_counts[tg] += 1
                    for tg in (data.get("new_tags") or []):
                        new_tags_counter[tg] += 1
                    if (data.get("given") or "").strip():
                        n_given += 1
                    if (data.get("summary") or "").strip():
                        n_summary += 1
                    if (data.get("title_suggestion") or "").strip():
                        n_title += 1
                    if (data.get("topic_suggestion") or "").strip():
                        n_topic += 1
                    # Пишем по строке на задачу: custom_id + разобранные поля
                    fout.write(json.dumps({"custom_id": cid, "data": data}, ensure_ascii=False) + "\n")

        if errors:
            with open(opts["errors"], "w", encoding="utf-8") as fe:
                fe.write("\n".join(errors))

        # 3) Сводка.
        total = n_ok + n_err
        self.stdout.write("")
        self.stdout.write("=" * 60)
        self.stdout.write(f"ЗАБРАНО результатов: {total:,}  (успешно {n_ok:,}, с ошибкой {n_err:,})")
        self.stdout.write(f"Ошибок парсинга JSON среди успешных: {n_parse_err:,}")
        self.stdout.write(f"Разобранные строки записаны в: {opts['out']}")
        if errors:
            self.stdout.write(f"Список ошибок: {opts['errors']}")
        self.stdout.write("")
        self.stdout.write("=== ТИПЫ ЗАДАЧ ===")
        for t, c in type_counts.most_common():
            self.stdout.write(f"  {t:<14} {c:>7,}")
        self.stdout.write("")
        self.stdout.write("=== ФЛАГИ ===")
        for fl, c in flag_counts.most_common():
            mark = "" if fl in ALLOWED_FLAGS else "  ⚠️ неизвестный флаг"
            self.stdout.write(f"  {fl:<26} {c:>7,}{mark}")
        self.stdout.write("")
        self.stdout.write("=== ЗАПОЛНЕННОСТЬ ПОЛЕЙ ===")
        self.stdout.write(f"  с дано/найти (given):   {n_given:>7,}")
        self.stdout.write(f"  с сутью (summary):      {n_summary:>7,}")
        self.stdout.write(f"  с заголовком:           {n_title:>7,}")
        self.stdout.write(f"  с темой-подсказкой:     {n_topic:>7,}")
        self.stdout.write("")
        self.stdout.write(f"=== ТОП-30 ТЕГОВ (из разрешённого списка), всего разных {len(tag_counts)} ===")
        for tg, c in tag_counts.most_common(30):
            self.stdout.write(f"  {c:>6,}  {tg}")
        self.stdout.write("")
        self.stdout.write(f"=== ПРЕДЛОЖЕННЫЕ НОВЫЕ ТЕГИ (вне списка), всего разных {len(new_tags_counter)} ===")
        self.stdout.write("(топ-40 по частоте — кандидаты в словарь)")
        for tg, c in new_tags_counter.most_common(40):
            self.stdout.write(f"  {c:>6,}  {tg}")
