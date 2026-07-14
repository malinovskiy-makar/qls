"""
БАТЧ 1 — поля обогащения (дано/найти + темы + теги + заголовки) на Haiku через Batch API.
НЕ трогает текст условия (это Батч 2 на Sonnet). НЕ пишет в базу (применение — отдельная сессия).
Двухфазно: без --submit НИ ОДНОГО обращения к API (только счёт задач, оценка стоимости, 3 примера).
С --submit — создаёт батч(и) на Anthropic и сохраняет id в batch1_ids.txt.
Ключ: ANTHROPIC_API_KEY или anthropic_key.txt. В коде НЕ хранится.
"""
from typing import Optional, List
import os

from django.core.management.base import BaseCommand
from problems.models import Problem

HAIKU = "claude-haiku-4-5-20251001"
CHARS_PER_TOKEN = 2.23          # замерено на этой базе
OUT_TOKENS_EST = 180           # поля — короткий вывод
IN_RATE_BATCH = 0.50           # Haiku, Batch (-50%): $/млн ввода
OUT_RATE_BATCH = 2.50          # Haiku, Batch (-50%): $/млн вывода
MAX_TOKENS = 1500              # потолок вывода (платится фактический, не потолок)

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

BASE_SYSTEM = """Ты — редактор банка олимпиадных задач по экономике. Тебе дают ОДНУ задачу.
Извлеки структурные поля. НЕ переписывай и НЕ исправляй текст условия — этим займётся отдельный этап.
Верни СТРОГО один JSON-объект и НИЧЕГО больше (без пояснений, без markdown-ограждений).

Поля JSON:
- "type": "расчётная" | "теория" | "качественная" | "тестовый" | "не_задача".
    "не_задача" — служебный текст/обрывок/заметка о баллах, а не условие.
- "given": для "расчётной" — строка "Дано: …" (кратко, только то, что реально дано). Иначе null.
- "find": для "расчётной" — строка "Найти: …". Иначе null.
- "summary": для "теория"/"качественная"/"тестовый" — одна строка сути. Иначе null.
- "topic_suggestion": краткое каноническое название темы (как подсказка); если непонятно — "".
- "title_suggestion": короткий осмысленный заголовок (до ~8 слов), без обрывов и мусора.
- "tags": массив подтем СТРОГО из ALLOWED_TAGS (только подходящие; можно пустой).
- "new_tags": подходящие подтемы, которых НЕТ в ALLOWED_TAGS (предложение в словарь). Можно пустой.
- "flags": массив из "incomplete_missing_figure", "not_a_problem" и/или "multiple_problems";
    если ничего — пустой массив.

КРИТИЧЕСКОЕ ПРАВИЛО — отсутствующие данные:
Если условие ссылается на рисунок/график/таблицу/«данные», которых в тексте НЕТ (пустые места,
обрывки осей, «приведена кривая …» без самих данных) — поставь flag "incomplete_missing_figure",
НЕ выдумывай недостающее, а given/find/summary опиши только по тому, что реально есть.

ВАЖНО про решения: в условии может быть запечён разбор/решение и критерии оценивания. Игнорируй
их при извлечении полей — описывай саму задачу, а не её решение. Текст условия НЕ трогай.

ВАЖНО про склейки: иногда в одну запись по ошибке импорта слиты НЕСКОЛЬКО разных задач подряд
(признаки: несколько независимых условий, номера страниц/колонтитулы внутри текста, нумерация
вроде «6&», «9*.», «10:»). Если это так — поставь flag "multiple_problems". given/find/summary
для такой записи заполнять не нужно (можно null) — она пойдёт на ручной разбор.

Язык: given/find/summary/tags/topic_suggestion — всегда по-русски."""

SYSTEM_PROMPT = BASE_SYSTEM + "\n\nALLOWED_TAGS: " + ", ".join(ALLOWED_TAGS)


def get_source_name(p) -> str:
    refs = list(p.source_references.all())
    if refs and getattr(refs[0], "source", None):
        return refs[0].source.name or ""
    return ""


def build_parts(p) -> str:
    out = []
    for part in p.parts.all():
        label = getattr(part, "label", "") or ""
        st = (getattr(part, "statement", "") or "").strip()
        if st:
            out.append(f"({label}) {st}" if label else st)
    return "\n".join(out)


def build_user(p) -> str:
    cur_topic = ", ".join(t.name for t in p.topics.all()) or "—"
    parts = build_parts(p)
    return (f"Задача (id {p.id}; текущая тема в базе: «{cur_topic}»):\n"
            f"ЗАГОЛОВОК: {p.title or '—'}\n"
            f"УСЛОВИЕ:\n{(p.statement or '—').strip()}\n"
            f"ПОДПУНКТЫ:\n{parts or '—'}")


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
    help = "БАТЧ 1: отправка полей обогащения на Haiku через Batch API. НЕ пишет в базу."

    def add_arguments(self, parser):
        parser.add_argument("--submit", action="store_true",
                            help="Без него API НЕ вызывается (только счёт и оценка стоимости).")
        parser.add_argument("--chunk-size", type=int, default=0,
                            help="Размер чанка батча (0 = один батч на всё). Для надёжности можно 5000.")
        parser.add_argument("--ids-file", type=str, default="batch1_ids.txt")
        parser.add_argument("--sample-file", type=str, default="batch1_sample.txt")

    def handle(self, *args, **opts):
        # Те же опубликованные без ILE, что и в pilot_enrich / export_preview_sample.
        qs = (Problem.objects.filter(status="published")
              .prefetch_related("parts", "topics", "source_references__source"))

        requests: List[dict] = []
        body_chars: List[int] = []
        skipped_ile = 0
        for p in qs.iterator(chunk_size=300):
            name = get_source_name(p).lower()
            if "ile" in name or "iloveeconomics" in name:
                skipped_ile += 1
                continue
            user = build_user(p)
            body_chars.append(len(user))
            requests.append({
                "custom_id": f"p{p.id}",
                "params": {
                    "model": HAIKU,
                    "max_tokens": MAX_TOKENS,
                    "system": SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": user}],
                },
            })

        n = len(requests)
        self.stdout.write(f"Опубликованных без ILE: {n:,}. Исключено ILE: {skipped_ile:,}.")
        if n == 0:
            self.stdout.write("Нет задач — нечего отправлять.")
            return

        # Оценка стоимости (без API). Консервативно, без учёта возможного кэширования.
        sys_chars = len(SYSTEM_PROMPT)
        in_tok = sum((sys_chars + b) / CHARS_PER_TOKEN for b in body_chars)
        out_tok = OUT_TOKENS_EST * n
        cost = in_tok / 1e6 * IN_RATE_BATCH + out_tok / 1e6 * OUT_RATE_BATCH
        self.stdout.write("")
        self.stdout.write(f"Токены (оценка): ввод ~{in_tok/1e6:.1f} млн, вывод ~{out_tok/1e6:.1f} млн")
        self.stdout.write(f"Оценка стоимости (Haiku + Batch): ~${cost:.2f}  "
                          f"(это потолок без кэширования; по факту может выйти дешевле)")

        # 3 примера запроса в файл — для глазной проверки.
        with open(opts["sample_file"], "w", encoding="utf-8") as f:
            for r in requests[:3]:
                f.write("=" * 80 + "\n")
                f.write(f"custom_id: {r['custom_id']}\n")
                f.write(f"model: {r['params']['model']}  max_tokens: {r['params']['max_tokens']}\n")
                f.write("USER:\n" + r["params"]["messages"][0]["content"] + "\n\n")
        self.stdout.write(f"3 примера запроса записаны в {opts['sample_file']}.")

        if not opts["submit"]:
            self.stdout.write("")
            self.stdout.write("⏸  ФАЗА ПОКАЗА: API не вызывался, денег не потрачено.")
            self.stdout.write("Если всё ок — запусти ту же команду с флагом --submit.")
            return

        # ---- Фаза отправки ----
        if os.path.exists(opts["ids_file"]):
            self.stdout.write(f"❌ Файл {opts['ids_file']} уже существует — похоже, батч уже отправлен. "
                              f"Если правда нужно отправить заново, удали этот файл вручную. Отмена.")
            return

        key = read_key()
        if not key:
            self.stdout.write("❌ Ключ не найден. Вставь его в anthropic_key.txt (одной строкой, без #) "
                              "или задай ANTHROPIC_API_KEY. Отмена.")
            return

        from anthropic import Anthropic
        client = Anthropic(api_key=key)

        batch_ids: List[str] = []
        chunks = list(chunked(requests, opts["chunk_size"]))
        self.stdout.write("")
        self.stdout.write(f"▶  ОТПРАВКА: {n:,} запросов в {len(chunks)} батч(ей)…")
        for i, chunk in enumerate(chunks, 1):
            mb = client.messages.batches.create(requests=chunk)
            batch_ids.append(mb.id)
            self.stdout.write(f"  батч {i}/{len(chunks)}: {mb.id}  "
                              f"({len(chunk):,} запросов, статус {mb.processing_status})")

        with open(opts["ids_file"], "w", encoding="utf-8") as f:
            for bid in batch_ids:
                f.write(bid + "\n")

        self.stdout.write("")
        self.stdout.write(f"✅ Отправлено. id батча(ей) сохранены в {opts['ids_file']}:")
        for bid in batch_ids:
            self.stdout.write(f"   {bid}")
        self.stdout.write("Обработка идёт на стороне Anthropic (обычно меньше часа, максимум 24 ч). "
                          "Забор результатов — отдельной командой в следующей сессии.")
