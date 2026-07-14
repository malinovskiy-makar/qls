"""
БАТЧ 2, сессия 1 — чистка формы + вынос решений на Sonnet через Batch API.
Обрабатываем И основное условие, И подпункты (в подпунктах сидит большинство решений).
НЕ пишет в базу, НЕ трогает эмбеддинги. Двухфазно: без --submit НИ ОДНОГО вызова API.
С --submit — создаёт батч(и) и пишет id в batch2_ids.txt СРАЗУ по мере создания.
Ключ: ANTHROPIC_API_KEY или anthropic_key.txt. В коде НЕ хранится.
"""
from typing import Optional, List
import os

from django.core.management.base import BaseCommand
from problems.models import Problem

SONNET = "claude-sonnet-4-6"
MAX_TOKENS = 16000          # потолок вывода; платим за факт; крупные задачи не обрезаем
IN_RATE_BATCH = 1.50        # Sonnet 4.6, Batch (-50%): ввод $3/млн -> $1.50
OUT_RATE_BATCH = 7.50       #                            вывод $15/млн -> $7.50

SYSTEM_PROMPT = """Ты — редактор банка олимпиадных задач по экономике. Тебе дают СЫРОЙ текст одной
задачи: заголовок, основное УСЛОВИЕ и ПОДПУНКТЫ (каждый со своей меткой в квадратных скобках, напр. [а]).
Верни СТРОГО один JSON и НИЧЕГО больше (без пояснений, без markdown, без тройных кавычек).

Три задачи. Они касаются И основного УСЛОВИЯ, И КАЖДОГО ПОДПУНКТА:

1) ПОЧИНИТЬ ФОРМУ, не трогая смысл. Чини: битый LaTeX (\\begin{cases}/\\begin{aligned} без \\\\,
   незакрытые $, поехавшие команды), OCR-порчу (латинские буквы внутри русских слов, двоеточия/точки
   внутри слов, «О» вместо нуля), задвоенные слова/фрагменты, лишние артефакты.
   НИКОГДА не меняй числа, формулы, переменные, значения, смысл. Не добавляй и не убирай
   содержательные части. НЕ переводи — сохраняй язык оригинала. Значки списков (•), \\item и корректный
   LaTeX — это НЕ порча, не трогай.
2) ВЫНЕСТИ РЕШЕНИЕ. Если в тексте условия ИЛИ подпунктов запечён разбор/решение/критерии
   оценивания — вынеси его ОТДЕЛЬНО, а в очищенном тексте оставь ТОЛЬКО саму задачу (без решения).
   Решение из всех мест собери в ОДНУ строку, помечая источник меткой: сначала общее (если есть),
   потом по подпунктам, напр.: "(а) <решение а> (б) <решение б>". Если решения нигде нет — пусто.
3) ПОМЕТИТЬ НЕПОЛНОЕ. Если условие/подпункты ссылаются на рисунок/график/таблицу/данные, которых
   в тексте НЕТ, ИЛИ текст обрывается на полуслове — НЕ выдумывай недостающее, поставь флаг.

Формат JSON:
{
 "dirty": true|false,                       // менял ли ты форму хоть где-то (условие или подпункты)
 "cleaned_statement": "<если основное условие правил — очищенное условие БЕЗ решения; иначе ПУСТАЯ строка>",
 "cleaned_parts": {"<метка>": "<очищенный подпункт БЕЗ решения>", ...},  // ТОЛЬКО те подпункты, что реально правил; иначе {}
 "has_solution": true|false,
 "extracted_solution": "<единой строкой, по меткам; иначе пустая строка>",
 "flags": []                                // из "missing_figure" и/или "truncated"; иначе []
}

ВАЖНО: cleaned_statement и cleaned_parts заполняй ТОЛЬКО там, где реально что-то исправил.
Не копируй нетронутый текст — исходник у нас уже есть. Если ничего не правил — "" и {}.
Метки подпунктов в cleaned_parts бери РОВНО те, что даны во входе в квадратных скобках.
Сохраняй язык оригинала. Ничего, кроме JSON, не выводи."""


def is_ile(p) -> bool:
    for ref in p.source_references.all():
        name = (getattr(getattr(ref, "source", None), "name", "") or "").lower()
        if "ile" in name or "iloveeconomics" in name:
            return True
    return False


def part_label(part, idx: int) -> str:
    lbl = (getattr(part, "label", "") or "").strip()
    return lbl if lbl else str(idx)


def build_body(p) -> str:
    parts = []
    if p.title:
        parts.append("ЗАГОЛОВОК: " + p.title)
    if p.statement:
        parts.append("УСЛОВИЕ:\n" + p.statement)
    subs = []
    for idx, part in enumerate(p.parts.all(), 1):
        st = (getattr(part, "statement", "") or "").strip()
        if st:
            subs.append("[{}] {}".format(part_label(part, idx), st))
    if subs:
        parts.append("ПОДПУНКТЫ (каждый чинить и выносить из него решение):\n" + "\n".join(subs))
    return "\n".join(parts)


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


def chunked(seq: list, size: int):
    if size <= 0:
        yield seq
        return
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


class Command(BaseCommand):
    help = "БАТЧ 2 сессия 1: отправка чистки+выноса решений (условие+подпункты) на Sonnet. Без --submit не тратит."

    def add_arguments(self, parser):
        parser.add_argument("--submit", action="store_true",
                            help="Без него API НЕ вызывается (только счёт и оценка).")
        parser.add_argument("--chunk-size", type=int, default=6000,
                            help="Размер чанка батча (0 = один батч).")
        parser.add_argument("--ids-file", type=str, default="batch2_ids.txt")
        parser.add_argument("--sample-file", type=str, default="batch2_sample.txt")

    def handle(self, *args, **opts):
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
        except Exception:
            enc = None

        def ntok(text: str) -> int:
            if not text:
                return 0
            return len(enc.encode(text)) if enc else int(len(text) / 2.23)

        sys_tok = ntok(SYSTEM_PROMPT)

        qs = (Problem.objects.filter(status="published", multiple_problems=False)
              .prefetch_related("parts", "source_references__source"))

        requests: List[dict] = []
        in_tok_total = 0
        # переписываемый объём = условие + подпункты (то, что реально может вернуться в выводе)
        rewritable_tok_total = 0
        skipped_ile = 0

        for p in qs.iterator(chunk_size=300):
            if is_ile(p):
                skipped_ile += 1
                continue
            body = build_body(p)
            bt = ntok(body)
            in_tok_total += sys_tok + bt
            rw = ntok(p.statement or "")
            for part in p.parts.all():
                rw += ntok(getattr(part, "statement", "") or "")
            rewritable_tok_total += rw
            requests.append({
                "custom_id": "p{}".format(p.id),
                "params": {
                    "model": SONNET,
                    "max_tokens": MAX_TOKENS,
                    "system": [{"type": "text", "text": SYSTEM_PROMPT,
                                "cache_control": {"type": "ephemeral"}}],
                    "messages": [{"role": "user", "content": body}],
                },
            })

        n = len(requests)
        self.stdout.write("Пул (published, без ILE и склеек): {:,}. Исключено ILE: {:,}.".format(n, skipped_ile))
        if not enc:
            self.stdout.write("⚠️ tiktoken недоступен — оценка приблизительная (2.23 симв/токен).")
        if n == 0:
            return

        # Вывод = маленький JSON-вердикт на КАЖДУЮ задачу
        #       + переписанный текст (условие+подпункты) ТОЛЬКО для грязных
        #       + вынесенные решения там, где они есть (≈60% переписываемого объёма у задач с решением).
        verdict = 110 * n

        def cost(dirty, sol):
            out = verdict + dirty * rewritable_tok_total + sol * rewritable_tok_total * 0.60
            return in_tok_total / 1e6 * IN_RATE_BATCH + out / 1e6 * OUT_RATE_BATCH

        self.stdout.write("")
        self.stdout.write("ВВОД (≈, tiktoken — не токенизатор Anthropic): {:.2f} млн токенов.".format(
            in_tok_total / 1e6))
        self.stdout.write("Переписываемый объём (условие+подпункты): {:.2f} млн токенов.".format(
            rewritable_tok_total / 1e6))
        self.stdout.write("Оценка стоимости (Sonnet 4.6 + Batch), по сценариям вывода:")
        self.stdout.write("  грязь 5%,  решения 5%:   ~${:.0f}".format(cost(0.05, 0.05)))
        self.stdout.write("  грязь 10%, решения 10%:  ~${:.0f}  (опорная)".format(cost(0.10, 0.10)))
        self.stdout.write("  грязь 15%, решения 20%:  ~${:.0f}".format(cost(0.15, 0.20)))

        # Приблизительная оценка С КЭШИРОВАНИЕМ инструкции (best-effort, ~70% попаданий).
        sys_input = sys_tok * n
        body_input = in_tok_total - sys_input
        cache_mult = 0.70 * 0.1 + 0.30 * 1.25   # попадания по 0.1x, промахи+запись ~1.25x
        cached_in_cost = (body_input + sys_input * cache_mult) / 1e6 * IN_RATE_BATCH
        out_mid = verdict + 0.10 * rewritable_tok_total + 0.10 * rewritable_tok_total * 0.60
        cached_total = cached_in_cost + out_mid / 1e6 * OUT_RATE_BATCH
        self.stdout.write("  С КЭШИРОВАНИЕМ инструкции (≈, опорная): ~${:.0f} "
                          "(реальный счёт, скорее всего, ближе к этому)".format(cached_total))

        with open(opts["sample_file"], "w", encoding="utf-8") as f:
            for r in requests[:3]:
                f.write("=" * 80 + "\n")
                f.write("custom_id: {}\n".format(r["custom_id"]))
                f.write("USER:\n" + r["params"]["messages"][0]["content"] + "\n\n")
        self.stdout.write("3 примера запроса записаны в {}.".format(opts["sample_file"]))

        if not opts["submit"]:
            self.stdout.write("")
            self.stdout.write("⏸  ФАЗА ПОКАЗА: API не вызывался, денег не потрачено.")
            self.stdout.write("Если всё ок — запусти ту же команду с флагом --submit.")
            return

        if os.path.exists(opts["ids_file"]):
            self.stdout.write("❌ Файл {} уже существует — похоже, батч уже отправлен. "
                              "Если правда нужно заново — удали файл вручную. Отмена.".format(opts["ids_file"]))
            return
        key = read_key()
        if not key:
            self.stdout.write("❌ Ключ не найден (ANTHROPIC_API_KEY или anthropic_key.txt). Отмена.")
            return

        from anthropic import Anthropic
        client = Anthropic(api_key=key)
        chunks = list(chunked(requests, opts["chunk_size"]))
        self.stdout.write("")
        self.stdout.write("▶  ОТПРАВКА: {:,} запросов в {} батч(ей)…".format(n, len(chunks)))
        batch_ids = []
        for i, chunk in enumerate(chunks, 1):
            mb = client.messages.batches.create(requests=chunk)
            with open(opts["ids_file"], "a", encoding="utf-8") as f:
                f.write(mb.id + "\n")
            batch_ids.append(mb.id)
            self.stdout.write("  батч {}/{}: {} ({:,} запросов, {})".format(
                i, len(chunks), mb.id, len(chunk), mb.processing_status))

        self.stdout.write("")
        self.stdout.write("✅ Отправлено. id батча(ей) в {}:".format(opts["ids_file"]))
        for bid in batch_ids:
            self.stdout.write("   {}".format(bid))
        self.stdout.write("Обработка на стороне Anthropic (обычно <1 ч, максимум 24 ч). Забор — отдельной сессией.")
