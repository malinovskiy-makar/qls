"""
БАТЧ 2, сессия 2: забрать результаты из Batch API, разобрать, собрать сводку.
В базу НЕ пишет. Читает ВСЕ id из batch2_ids.txt. Ключ: ANTHROPIC_API_KEY или anthropic_key.txt.
Запускать можно сколько угодно раз: пока хоть один батч не готов — просто покажет статус.
"""
from typing import Optional, List, Dict
from collections import Counter
import os
import json

from django.core.management.base import BaseCommand

ALLOWED_FLAGS = {"missing_figure", "truncated"}


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
    out = []
    for block in (getattr(message, "content", None) or []):
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
    return {"_parse_error": True, "_raw": raw[:300]}


class Command(BaseCommand):
    help = "БАТЧ 2 сессия 2: забрать результаты Batch API и собрать сводку. В базу не пишет."

    def add_arguments(self, parser):
        parser.add_argument("--ids-file", type=str, default="batch2_ids.txt")
        parser.add_argument("--out", type=str, default="batch2_parsed.jsonl")
        parser.add_argument("--errors", type=str, default="batch2_errors.txt")

    def handle(self, *args, **opts):
        ids = read_ids(opts["ids_file"])
        if not ids:
            self.stdout.write("❌ Не нашёл id батчей в {}. Отмена.".format(opts["ids_file"]))
            return
        key = read_key()
        if not key:
            self.stdout.write("❌ Ключ не найден (anthropic_key.txt или ANTHROPIC_API_KEY). Отмена.")
            return

        from anthropic import Anthropic
        client = Anthropic(api_key=key)

        # 1) Проверяем готовность ВСЕХ батчей.
        all_ended = True
        for bid in ids:
            mb = client.messages.batches.retrieve(bid)
            rc = mb.request_counts
            self.stdout.write(
                "Батч {}: {} | готово {:,}, ошибок {:,}, в работе {:,}, "
                "истекло {:,}, отменено {:,}".format(
                    bid, mb.processing_status,
                    rc.succeeded, rc.errored, rc.processing,
                    rc.expired, rc.canceled,
                )
            )
            if mb.processing_status != "ended":
                all_ended = False

        if not all_ended:
            self.stdout.write("")
            self.stdout.write(
                "⏳ Не все батчи готовы. Запусти эту же команду позже "
                "(обычно <1 ч, максимум 24 ч). ВПН на время забора нужен."
            )
            return

        # 2) Забираем и разбираем.
        n_ok = n_err = n_parse_err = 0
        n_dirty = n_solution = 0
        flag_counts = Counter()
        rewritten_parts_total = 0
        errors: List[str] = []

        with open(opts["out"], "w", encoding="utf-8") as fout:
            for bid in ids:
                for entry in client.messages.batches.results(bid):
                    cid = entry.custom_id
                    res = entry.result
                    if res.type != "succeeded":
                        n_err += 1
                        errors.append("{}\t{}".format(cid, res.type))
                        continue
                    n_ok += 1
                    data = parse_json(extract_text(res.message))
                    if data.get("_parse_error"):
                        n_parse_err += 1
                        errors.append("{}\tparse_error\t{}".format(
                            cid, data.get("_raw", "")[:200]))
                    if data.get("dirty"):
                        n_dirty += 1
                    if data.get("has_solution"):
                        n_solution += 1
                    cp = data.get("cleaned_parts") or {}
                    if isinstance(cp, dict):
                        rewritten_parts_total += len(cp)
                    for fl in (data.get("flags") or []):
                        flag_counts[fl] += 1
                    fout.write(json.dumps({"custom_id": cid, "data": data},
                                         ensure_ascii=False) + "\n")

        if errors:
            with open(opts["errors"], "w", encoding="utf-8") as fe:
                fe.write("\n".join(errors))

        # 3) Сводка.
        total = n_ok + n_err
        self.stdout.write("")
        self.stdout.write("=" * 60)
        self.stdout.write("ЗАБРАНО: {:,} (успешно {:,}, с ошибкой {:,})".format(
            total, n_ok, n_err))
        self.stdout.write("Ошибок парсинга JSON среди успешных: {:,}".format(n_parse_err))
        self.stdout.write("Разобранные строки: {}".format(opts["out"]))
        if errors:
            self.stdout.write("Ошибки: {}".format(opts["errors"]))
        self.stdout.write("")
        self.stdout.write("=== ЧТО НАШЛА ЧИСТКА (по всей базе) ===")
        self.stdout.write("  задач с реально исправленным текстом (dirty):   {:,}".format(n_dirty))
        self.stdout.write("  задач с вынесенным решением (has_solution):     {:,}".format(n_solution))
        self.stdout.write("  всего переписанных подпунктов:                  {:,}".format(
            rewritten_parts_total))
        self.stdout.write("")
        self.stdout.write("=== ФЛАГИ (в очередь на пере-импорт, НЕ чистятся) ===")
        if flag_counts:
            for fl, c in flag_counts.most_common():
                mark = "" if fl in ALLOWED_FLAGS else "  ⚠️ неизвестный флаг"
                self.stdout.write("  {:<16} {:>6,}{}".format(fl, c, mark))
        else:
            self.stdout.write("  (флагов нет)")
