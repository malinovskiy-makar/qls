"""
Management command: import_akimova

Импортирует задачи из пары «задачник + решебник» Акимова/Дичева/Щукина
«Задания по экономике: от простых до олимпиадных» (Вита-Пресс):
  ЗАДАЧНИК (условия + краткие ответы):
      materials/akimova               (PDF без расширения, 324 стр.)
  РЕШЕБНИК (полные решения):
      materials/attachments/задачник акимова (очень много задач разной сложности).pdf

Оба файла имеют одинаковую структуру: 17 глав, расчётные задачи нумеруются
с 1 в каждой главе. Совмещение «условие N главы X» ↔ «решение N главы X» ↔
«краткий ответ N главы X» — по номеру главы + номеру задачи.

Где что:
  - Глава: страница, чьи первые строки «Глава N» + НАЗВАНИЕ ЗАГЛАВНЫМИ.
  - Условия: в задачнике после маркера «ЗАДАЧИ И УПРАЖНЕНИЯ» до след. главы.
  - Решения: в решебнике от заголовка главы, маркер «N.», конец — «Ответ(ы):».
  - Краткие ответы: в задачнике раздел «ОТВЕТЫ» (стр. ~272+), подсекция
    «Задачи и упражнения» каждой главы. → Problem.answer.

Текст нативный (PyMuPDF) с OCR-шумом; чистится от колонтитулов и переносов.
Нумерация в решебнике/ответах с пропусками — матчим строго по номеру,
не предполагая сплошной нумерации.

status=draft. Тема = название главы → Topic. Источник «Акимова — Задания по
экономике». Дедупликация по content_hash (md5 условия).

Запуск:
    python manage.py import_akimova
    python manage.py import_akimova --dry-run
"""
import hashlib
import re
from pathlib import Path
from typing import Optional

import fitz  # pymupdf

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from problems.models import Job, Problem, ProblemPart, Source, SourceReference, Topic


ZAD_PATH = Path(settings.BASE_DIR) / 'materials' / 'akimova'
RESH_PATH = (Path(settings.BASE_DIR) / 'materials' / 'attachments'
             / 'задачник акимова (очень много задач разной сложности).pdf')
SOURCE_NAME = 'Акимова — Задания по экономике'

CHAPTER_NAMES = {
    1: 'Введение в экономическую теорию. Альтернативные издержки',
    2: 'КПВ. Абсолютные и сравнительные преимущества. Выгоды обмена',
    3: 'Спрос и предложение. Рыночное равновесие',
    4: 'Эластичность',
    5: 'Производство и издержки. Выручка. Прибыль',
    6: 'Рыночные структуры',
    7: 'Рынок труда. Рынок капитала',
    8: 'Неравенство доходов. Внешние эффекты. Общественные блага',
    9: 'Система национальных счетов',
    10: 'Совокупный спрос и совокупное предложение',
    11: 'Экономический рост. Экономический цикл',
    12: 'Безработица',
    13: 'Инфляция',
    14: 'Деньги и банки',
    15: 'Денежный рынок. Кредитно-денежная политика',
    16: 'Государственный бюджет и бюджетно-налоговая политика',
    17: 'Международная экономика',
}

_TRANSLIT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
}

TASK_SPLIT_RE = re.compile(r'(?m)^\s*(\d+)\.(?:\s|$)')
ZADACHI_RE = re.compile(r'ЗАДАЧИ\s+И\s+УПРАЖНЕНИЯ')
OTV_CH_RE = re.compile(r'(?m)^\s*Глава\s+(\d+)\.')
SUB_RE = re.compile(r'(?m)^\s*([абвгдеёжзaА-Яa-z])\)\s')


def md5(text: str) -> str:
    return hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()


def make_slug(name: str) -> str:
    chars = [_TRANSLIT.get(c, c) for c in name.lower()]
    return (re.sub(r'[^a-z0-9]+', '-', ''.join(chars)).strip('-')[:110]) or 'topic'


def get_or_create_topic(name, cache, dry_run) -> Optional[Topic]:
    if name in cache:
        return cache[name]
    try:
        t = Topic.objects.get(name=name)
        cache[name] = t
        return t
    except Topic.DoesNotExist:
        pass
    if dry_run:
        return None
    base = make_slug(name)
    slug = base
    i = 1
    while Topic.objects.filter(slug=slug).exists():
        slug = f'{base}-{i}'
        i += 1
    t = Topic.objects.create(name=name, slug=slug)
    cache[name] = t
    return t


def clean(text: str) -> str:
    text = text.replace('\xad', '')
    # переносы «сло-\nво» → «слово»
    text = re.sub(r'(\w)-\n(\S)', r'\1\2', text)
    # колонтитулы: «14 \nГлава 1» и «Глава 1 \n14»
    text = re.sub(r'(?m)^\s*\d{1,3}\s*\n\s*Глава\s+\d+[^\n]*$', '', text)
    text = re.sub(r'(?m)^\s*Глава\s+\d+[^\n]*\n\s*\d{1,3}\s*$', '', text)
    text = re.sub(r'(?m)^\s*Глава\s+\d+\s*$', '', text)
    return text


def pages_text(doc, a, b) -> str:
    return '\n'.join(doc[i].get_text() for i in range(a, min(b, len(doc))))


def detect_chapters(doc) -> dict:
    """{номер_главы: индекс_страницы} по заголовку «Глава N» + строка ЗАГЛАВНЫМИ."""
    res = {}
    for i in range(len(doc)):
        lines = [l for l in doc[i].get_text().split('\n') if l.strip()]
        if not lines:
            continue
        m = re.match(r'^Глава\s+(\d+)\s*$', lines[0].strip())
        if m and len(lines) > 1:
            nxt = lines[1].strip()
            up = sum(1 for c in nxt if c.isupper())
            low = sum(1 for c in nxt if c.islower())
            if len(nxt) > 4 and up > low:
                res.setdefault(int(m.group(1)), i)
    return res


def detect_otvety_page(doc) -> int:
    for i in range(len(doc) - 1, 0, -1):
        first = next((l for l in doc[i].get_text().split('\n') if l.strip()), '')
        if re.match(r'^\s*ОТВЕТЫ\s*$', first):
            return i
    return len(doc)


def parse_numbered(region: str):
    """Список (num, text) по маркерам «N.»."""
    out = []
    ms = list(TASK_SPLIT_RE.finditer(region))
    for i, m in enumerate(ms):
        s = m.end()
        e = ms[i + 1].start() if i + 1 < len(ms) else len(region)
        out.append((int(m.group(1)), region[s:e].strip()))
    return out


def parse_subparts(text: str):
    """(statement, [(label, sub_text)]) по подпунктам «а)/b)…»."""
    pos = list(SUB_RE.finditer(text))
    # оставляем только реально похожее на список подпунктов (>=2)
    if len(pos) < 2:
        return text.strip(), []
    statement = text[:pos[0].start()].strip()
    parts = []
    for i, m in enumerate(pos):
        s = m.end()
        e = pos[i + 1].start() if i + 1 < len(pos) else len(text)
        parts.append((m.group(1), text[s:e].strip()))
    return statement, parts


def parse_otvety(otv_text: str) -> dict:
    """{(глава, номер): краткий_ответ} с детекцией сброса нумерации."""
    ans = {}
    cms = list(OTV_CH_RE.finditer(otv_text))
    for i, cm in enumerate(cms):
        c = int(cm.group(1))
        s = cm.end()
        e = cms[i + 1].start() if i + 1 < len(cms) else len(otv_text)
        block = otv_text[s:e]
        nxt = int(cms[i + 1].group(1)) if i + 1 < len(cms) else c + 1
        gapped = (nxt != c + 1)
        zm = re.search(r'Задачи\s+и\s+упражнения', block)
        region = block[zm.end():] if zm else block
        last = 0
        for num, atext in parse_numbered(region):
            if gapped and num <= last and last > 0:
                break   # сброс → ответы следующей (пропущенной) главы — не берём
            if 0 < len(atext) < 250:
                ans[(c, num)] = atext
            last = num
    return ans


class Command(BaseCommand):
    help = 'Импортирует задачник+решебник Акимова (совмещение условие/решение/ответ)'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        for p in (ZAD_PATH, RESH_PATH):
            if not p.exists():
                self.stderr.write(self.style.ERROR(f'Нет файла: {p}'))
                return

        zad = fitz.open(str(ZAD_PATH))
        resh = fitz.open(str(RESH_PATH))
        try:
            zad_ch = detect_chapters(zad)
            resh_ch = detect_chapters(resh)
            otv_page = detect_otvety_page(zad)
            self.stdout.write(
                f'Глав: задачник {len(zad_ch)}, решебник {len(resh_ch)}; '
                f'ОТВЕТЫ на стр. {otv_page}')

            # ── условия (задачник) ───────────────────────────────────────
            conditions = {}   # (c, n) -> текст
            for c in range(1, 18):
                if c not in zad_ch:
                    continue
                start = zad_ch[c]
                end = zad_ch.get(c + 1, otv_page)
                txt = clean(pages_text(zad, start, end))
                zm = ZADACHI_RE.search(txt)
                if not zm:
                    continue
                for num, body in parse_numbered(txt[zm.end():]):
                    if len(body) >= 15 and (c, num) not in conditions:
                        conditions[(c, num)] = body

            # ── решения (решебник) ───────────────────────────────────────
            solutions = {}
            for c in range(1, 18):
                if c not in resh_ch:
                    continue
                start = resh_ch[c]
                end = resh_ch.get(c + 1, len(resh))
                txt = clean(pages_text(resh, start, end))
                for num, body in parse_numbered(txt):
                    if len(body) >= 10:
                        solutions[(c, num)] = body

            # ── краткие ответы (задачник, раздел ОТВЕТЫ) ────────────────
            answers = parse_otvety(clean(pages_text(zad, otv_page, len(zad))))
        finally:
            zad.close()
            resh.close()

        self.stdout.write(
            f'Условий: {len(conditions)}, решений: {len(solutions)}, '
            f'кратких ответов: {len(answers)}')
        if dry_run:
            self.stdout.write(self.style.WARNING('Режим --dry-run.'))

        existing_hashes = set(
            Problem.objects.exclude(content_hash='').values_list('content_hash', flat=True)
        )
        topic_cache = {}
        source = job = None
        if not dry_run:
            source, _ = Source.objects.get_or_create(
                name=SOURCE_NAME,
                defaults={'kind': 'сборник задач',
                          'note': 'Акимов Д.В., Дичева О.В., Щукина Л.Б., Вита-Пресс'})
            job = Job.objects.create(kind='import', status='running',
                                     params={'source': SOURCE_NAME})

        created = skipped = errors = 0
        with_sol = with_ans = 0

        for (c, n) in sorted(conditions):
            condition = conditions[(c, n)]
            try:
                h = md5(condition)
                if h in existing_hashes:
                    skipped += 1
                    continue
                solution = solutions.get((c, n), '')
                answer = answers.get((c, n), '')
                if solution:
                    with_sol += 1
                if answer:
                    with_ans += 1
                if dry_run:
                    created += 1
                    existing_hashes.add(h)
                    continue
                statement, parts = parse_subparts(condition)
                topic = get_or_create_topic(CHAPTER_NAMES.get(c, f'Глава {c}'),
                                            topic_cache, dry_run)
                with transaction.atomic():
                    title = statement.split('\n')[0].strip()[:80] or f'Глава {c}, Задача {n}'
                    problem = Problem.objects.create(
                        title=title, statement=statement, solution=solution,
                        answer=answer, status=Problem.Status.DRAFT, content_hash=h)
                    if topic:
                        problem.topics.add(topic)
                    SourceReference.objects.create(
                        problem=problem, source=source,
                        note=f'Глава {c}, Задача {n}')
                    for order, (label, sub_text) in enumerate(parts):
                        ProblemPart.objects.create(
                            problem=problem, label=label, statement=sub_text,
                            answer='', order=order)
                created += 1
                existing_hashes.add(h)
            except Exception as exc:
                self.stderr.write(f'  Ошибка Глава {c} Задача {n}: {exc}')
                errors += 1

        if not dry_run and job:
            job.status = 'done' if errors == 0 else 'failed'
            job.progress = 100
            job.finished_at = timezone.now()
            job.result = {'created': created, 'skipped': skipped, 'errors': errors,
                          'with_solution': with_sol, 'with_answer': with_ans}
            job.save(update_fields=['status', 'progress', 'finished_at', 'result'])

        self.stdout.write(self.style.SUCCESS(
            f'\nИтог Акимова: создано {created}, пропущено {skipped}, ошибок {errors}\n'
            f'  с решением {with_sol}, с кратким ответом {with_ans}'))
