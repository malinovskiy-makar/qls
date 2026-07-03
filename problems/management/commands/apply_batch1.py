"""
СЕССИЯ 3 Батча 1: применить поля обогащения к БД.
Двухфазно: без --confirm НЕ пишет в БД (показ + файлы-отчёты). С --confirm — пишет в transaction.
НЕ трогает текст условия, problem_to_text, эмбеддинги. ai_blurb — внутреннее поле.
Читает batch1_parsed.jsonl. Теги сводятся к канону через SYNONYM_MAP.
"""
from typing import Optional, Dict, List
from collections import Counter
import json
import re

from django.core.management.base import BaseCommand
from django.db import transaction, IntegrityError
from problems.models import Problem, Tag
from problems.embedding_config import CANONICAL_TAG_NAMES

NEW_TAG_MIN_FREQ = 20  # порог новых тегов из батча (согласован)

# Исходные 47 имён используются только для построения _norm-словаря канона.
# Полный итоговый канон (222 имени) живёт в embedding_config.CANONICAL_TAG_NAMES.
ORIGINAL_CANON = sorted(CANONICAL_TAG_NAMES)

# Карта склеек: вариант -> канонический тег (проверено вручную).
SYNONYM_MAP_RAW = {
    "индекс джини": "коэффициент Джини",
    "равновесие по нэшу": "равновесие Нэша",
    "асимметричная информация": "асимметрия информации",
    "информационная асимметрия": "асимметрия информации",
    "монетарная политика": "денежно-кредитная политика",
    "денежная политика": "денежно-кредитная политика",
    "денежное предложение": "денежная масса",
    "обязательные резервы": "норма обязательных резервов",
    "норма резервирования": "норма обязательных резервов",
    "резервные требования": "норма обязательных резервов",
    "мультипликатор налогов": "налоговый мультипликатор",
    "максимизация прибыли фирмы": "максимизация прибыли",
    "оптимизация потребления": "оптимальный выбор потребителя",
    "оптимизация потребителя": "оптимальный выбор потребителя",
    "чистая приведённая стоимость": "чистая приведённая стоимость (NPV)",
    "обменный курс": "валютный курс",
    "процентные ставки": "процентная ставка",
    "операции открытого рынка": "операции на открытом рынке",
    "ценовой потолок": "потолок цены",
    "импорт и экспорт": "экспорт и импорт",
    "потенциальный выпуск": "потенциальный ВВП",
    "равновесие курно": "модель Курно",
    "пространственная конкуренция": "модель Хотеллинга",
    "ставка рефинансирования": "ключевая ставка",
    "налоговая политика": "фискальная политика",
    "распределение налогового бремени": "налоговое бремя",
    "дисконтирование денежных потоков": "дисконтирование",
    "картельное соглашение": "картель",
    "межвременное потребление": "межвременной выбор",
    "государственные закупки": "государственные расходы",
    "типы безработицы": "безработица",
    "определение безработицы": "безработица",
    "измерение неравенства": "неравенство доходов",
}

# Слишком общие/мета теги — выбрасываем (группа Г).
DROP_RAW = {"финансовые расчёты", "макроэкономическая политика", "инвестиционные решения"}


def _norm(s: str) -> str:
    return (s or "").strip().lower().replace("ё", "е")


def _make_base_slug(text: str) -> str:
    """Транслит + латинская строчная для генерации slug тегов (паттерн import_ile)."""
    table = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e',
        'ё': 'e', 'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k',
        'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
        'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts',
        'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '',
        'э': 'e', 'ю': 'yu', 'я': 'ya', ' ': '-',
    }
    lowered = text.lower()
    transliterated = ''.join(table.get(ch, ch) for ch in lowered)
    slug = ''.join(c for c in transliterated if c.isalnum() or c == '-')
    return slug[:110] or 'tag'


def _ensure_tag(name: str, cache: Dict[str, Tag]) -> Tag:
    """Находит или создаёт Tag; генерирует уникальный slug (паттерн import_ile)."""
    if name in cache:
        return cache[name]
    try:
        tag = Tag.objects.get(name=name)
        cache[name] = tag
        return tag
    except Tag.DoesNotExist:
        pass
    base_slug = _make_base_slug(name)
    slug = base_slug
    for attempt in range(1, 300):
        try:
            with transaction.atomic():
                tag = Tag.objects.create(name=name[:99], slug=slug[:119])
            cache[name] = tag
            return tag
        except IntegrityError:
            slug = '{}-{}'.format(base_slug, attempt)[:119]
    raise RuntimeError('Не удалось создать тег «{}»: все варианты slug заняты'.format(name))


class Command(BaseCommand):
    help = 'СЕССИЯ 3 Батча 1: применить поля к БД. Без --confirm не пишет.'

    def add_arguments(self, parser):
        parser.add_argument('--file', type=str, default='batch1_parsed.jsonl')
        parser.add_argument('--confirm', action='store_true',
                            help='Без этого флага в БД НЕ пишем (только показ и отчёты).')

    # ------------------------------------------------------------------
    # Построение канона тегов
    # ------------------------------------------------------------------

    def _build_canon(self, records):
        # type: (Dict[int, dict]) -> tuple
        """Возвращает (syn, drop, canon_norm_to_disp)."""
        syn = {_norm(k): v for k, v in SYNONYM_MAP_RAW.items()}
        drop = {_norm(x) for x in DROP_RAW}
        orig_norm = {_norm(t): t for t in ORIGINAL_CANON}

        freq = Counter()  # type: Counter
        first_seen = {}   # type: Dict[str, str]
        for data in records.values():
            for tg in (data.get('new_tags') or []):
                n = _norm(tg)
                if n and n not in orig_norm:
                    freq[n] += 1
                    if n not in first_seen:
                        first_seen[n] = tg.strip()

        new_canon = {}  # type: Dict[str, str]
        for n, c in freq.items():
            if c >= NEW_TAG_MIN_FREQ and n not in syn and n not in drop:
                new_canon[n] = first_seen.get(n, n)

        canon_norm_to_disp = dict(orig_norm)
        canon_norm_to_disp.update(new_canon)
        return syn, drop, canon_norm_to_disp

    def _resolve(self, tag, syn, canon_norm_to_disp):
        # type: (str, dict, dict) -> Optional[str]
        """Возвращает каноническое отображение или None (хвост / выброс)."""
        n = _norm(tag)
        if n in syn:
            return syn[n]
        if n in canon_norm_to_disp:
            return canon_norm_to_disp[n]
        return None

    # ------------------------------------------------------------------
    # Вспомогательные
    # ------------------------------------------------------------------

    @staticmethod
    def _make_blurb(data):
        # type: (dict) -> str
        given = (data.get('given') or '').strip()
        find = (data.get('find') or '').strip()
        if given or find:
            return '\n'.join(x for x in (given, find) if x)
        summ = (data.get('summary') or '').strip()
        if summ:
            return summ if summ.lower().startswith('суть') else 'Суть: ' + summ
        return ''

    @staticmethod
    def _is_multi(data):
        # type: (dict) -> bool
        if 'multiple_problems' in (data.get('flags') or []):
            return True
        return 'multiple_problems' in (data.get('type') or '')

    @staticmethod
    def _is_not_problem(data):
        # type: (dict) -> bool
        return (
            'not_a_problem' in (data.get('flags') or [])
            or (data.get('type') or '') == 'не_задача'
        )

    @staticmethod
    def _title_is_junk(title, statement):
        # type: (str, str) -> bool
        t = (title or '').strip()
        if t in ('', '—', '-', '–'):
            return True
        if re.match(r'^Разное\s*\d*$', t):
            return True
        first_line = (statement or '').strip().split('\n', 1)[0].strip()
        if t and first_line and t == first_line:
            return True
        return False

    # ------------------------------------------------------------------
    # Основной метод
    # ------------------------------------------------------------------

    def handle(self, *args, **opts):
        path = opts['file']
        records = {}   # type: Dict[int, dict]
        parse_errors = 0

        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                cid = rec.get('custom_id', '')
                data = rec.get('data') or {}
                if not cid.startswith('p'):
                    continue
                try:
                    pid = int(cid[1:])
                except ValueError:
                    continue
                if data.get('_parse_error'):
                    parse_errors += 1
                    continue
                records[pid] = data

        self.stdout.write(
            'Записей в файле (валидных): {:,} (нечитаемых/с ошибкой пропущено: {:,})'.format(
                len(records), parse_errors)
        )
        if not records:
            return

        syn, drop, canon = self._build_canon(records)
        self.stdout.write(
            'Канонических тегов всего: {} (исходных {} + новых {})'.format(
                len(canon), len(ORIGINAL_CANON), len(canon) - len(ORIGINAL_CANON))
        )

        # Грузим задачи разом (только нужные поля + prefetch для тем).
        probs = Problem.objects.in_bulk(list(records.keys()))

        # ---------- планирование (без записи) ----------
        plan_blurb = 0
        plan_title = 0
        title_samples = []   # type: List[tuple]
        used_tags = Counter()
        n_multi = n_notprob = n_missfig = n_topic = 0
        reimport_rows = []   # type: List[str]
        notprob_rows = []    # type: List[str]
        missfig_rows = []    # type: List[str]
        topic_rows = []      # type: List[str]

        for pid, data in records.items():
            p = probs.get(pid)
            if p is None:
                continue

            topic_sug = (data.get('topic_suggestion') or '').strip()
            if topic_sug:
                n_topic += 1
                topic_rows.append('{}\t{}'.format(pid, topic_sug))

            if self._is_multi(data):
                n_multi += 1
                reimport_rows.append(str(pid))
                continue  # склейкам обогащение НЕ применяем

            if self._is_not_problem(data):
                n_notprob += 1
                notprob_rows.append('{}\t{}'.format(pid, (p.title or '')[:80]))
            if 'incomplete_missing_figure' in (data.get('flags') or []):
                n_missfig += 1
                missfig_rows.append('{}\t{}'.format(pid, (p.title or '')[:80]))

            if self._make_blurb(data):
                plan_blurb += 1

            for tg in list(data.get('tags') or []) + list(data.get('new_tags') or []):
                c = self._resolve(tg, syn, canon)
                if c:
                    used_tags[c] += 1

            sug = (data.get('title_suggestion') or '').strip()
            if sug and sug != (p.title or '').strip() and self._title_is_junk(p.title, p.statement):
                plan_title += 1
                if len(title_samples) < 40:
                    title_samples.append((pid, (p.title or '').strip(), sug))

        # ---------- файлы-отчёты (БД не трогаем) ----------
        def _dump(name, header, rows):
            with open(name, 'w', encoding='utf-8') as fo:
                fo.write(header + '\n')
                fo.write('\n'.join(rows))

        _dump('batch1_topic_review.csv',
              'id\tпредложенная_тема',
              topic_rows)
        _dump('batch1_reimport_queue.txt',
              '# id задач-склеек, требующих переимпорта',
              reimport_rows)
        _dump('batch1_not_a_problem.txt',
              'id\tзаголовок',
              notprob_rows)
        _dump('batch1_missing_figure.txt',
              'id\tзаголовок',
              missfig_rows)

        # ---------- сводка ----------
        self.stdout.write('')
        self.stdout.write('=== ЧТО БУДЕТ ПРИМЕНЕНО ===')
        self.stdout.write('  дано/найти/суть (ai_blurb):         {:,} задач'.format(plan_blurb))
        self.stdout.write('  разных канонических тегов в данных: {:,}'.format(len(used_tags)))
        self.stdout.write('  замена мусорных заголовков:         {:,}'.format(plan_title))
        self.stdout.write('')
        self.stdout.write('=== ВЫНЕСЕНО В ОТЧЁТЫ (в БД НЕ применяется) ===')
        self.stdout.write(
            '  склейки (multiple_problems) → batch1_reimport_queue.txt:  {:,}  (флаг multiple_problems будет поставлен)'.format(n_multi))
        self.stdout.write(
            '  не_задача → batch1_not_a_problem.txt:                     {:,}  (обогащение применяем, удаление НЕ делаем)'.format(n_notprob))
        self.stdout.write(
            '  потерян рисунок → batch1_missing_figure.txt:              {:,}  (обогащение применяем)'.format(n_missfig))
        self.stdout.write(
            '  темы-подсказки → batch1_topic_review.csv:                 {:,}  (НЕ применяем вслепую)'.format(n_topic))
        self.stdout.write('')
        self.stdout.write('=== ПРИМЕРЫ ЗАМЕНЫ ЗАГОЛОВКОВ (было → станет), до 40 ===')
        for pid, old, new in title_samples:
            self.stdout.write('  #{}: «{}» → «{}»'.format(pid, old, new))
        self.stdout.write('')
        self.stdout.write('=== ПОЛНЫЙ СПИСОК КАНОНИЧЕСКИХ ТЕГОВ ({}) — проверь глазами ==='.format(len(canon)))
        for disp in sorted(set(canon.values())):
            self.stdout.write('  {}'.format(disp))

        if not opts['confirm']:
            self.stdout.write('')
            self.stdout.write('⏸  ФАЗА ПОКАЗА: в БД ничего не записано. Отчёты записаны на диск.')
            self.stdout.write('Если всё ок — запусти ту же команду с флагом --confirm.')
            return

        # ------------------------------------------------------------------
        # ЗАПИСЬ В БД
        # ------------------------------------------------------------------
        self.stdout.write('')
        self.stdout.write('▶  ЗАПИСЬ В БД…')

        with transaction.atomic():
            # Гарантируем, что все канонические теги существуют в БД.
            tag_cache = {}   # type: Dict[str, Tag]
            for disp in set(canon.values()):
                _ensure_tag(disp, tag_cache)

            written_blurb = 0
            written_title = 0
            written_multi = 0

            for pid, data in records.items():
                p = probs.get(pid)
                if p is None:
                    continue

                if self._is_multi(data):
                    if not p.multiple_problems:
                        p.multiple_problems = True
                        p.save(update_fields=['multiple_problems'])
                        written_multi += 1
                    continue

                changed = []   # type: List[str]

                blurb = self._make_blurb(data)
                if blurb and p.ai_blurb != blurb:
                    p.ai_blurb = blurb
                    changed.append('ai_blurb')
                    written_blurb += 1

                sug = (data.get('title_suggestion') or '').strip()
                if sug and sug != (p.title or '').strip() and self._title_is_junk(p.title, p.statement):
                    p.title = sug
                    changed.append('title')
                    written_title += 1

                if changed:
                    p.save(update_fields=changed)

                # Теги: добавляем к существующим (не заменяем).
                tags_for_p = set()
                for tg in list(data.get('tags') or []) + list(data.get('new_tags') or []):
                    resolved = self._resolve(tg, syn, canon)
                    if resolved and resolved in tag_cache:
                        tags_for_p.add(tag_cache[resolved])
                if tags_for_p:
                    p.tags.add(*tags_for_p)

        self.stdout.write('')
        self.stdout.write(
            '✅ Записано: ai_blurb у {:,}, заголовков заменено {:,}, '
            'склеек помечено {:,}. Теги связаны.'.format(
                written_blurb, written_title, written_multi)
        )
        self.stdout.write('Темы НЕ применялись (см. batch1_topic_review.csv). Эмбеддинги НЕ пересчитывались.')
