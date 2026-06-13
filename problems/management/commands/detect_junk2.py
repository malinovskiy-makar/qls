"""
detect_junk2.py — сессия H, этап 4. Три детектора, НИЧЕГО не правят —
только списки id для качественного шлюза (reports/quality_audit/*.txt).

1. bad_glyph — битые глифы в statement/solution/answer задачи или подпунктов:
   U+FFFD (�), U+25A0–U+25FF (геометрические фигуры ■▤▥ — чёрные квадраты
   Фридмана #17), U+2580–U+259F (блоки), U+E000–U+F8FF (Private Use Area),
   + U+239B–U+23B3 (куски скобок ⎧⎪⎨⎩ из PDF — улика #5174: рассыпанная
   система в answer). БЕЗ предохранителя — это всегда мусор.
   → bad_glyph_ids.txt

2. midword — условие начинается с середины слова: Problem.statement после
   strip начинается со строчной кириллической буквы (маркеры «а)», «б).»
   исключены), ЛИБО с обрезка «YYYY)» (улика #6926 «2007)...»).
   Улики: #47590 «личину спроса...», #47557 «левства...».
   → midword_ids.txt

3. not_a_problem — не-задачи MRU-типа: statement < 300 симв. И содержит
   «приложи скриншот» / «добавь скриншот» / «на сайте Marginal Revolution» /
   «выполни задание по ссылке». Улика: #7667.
   → not_a_problem_ids.txt

Запуск:
    ./venv/bin/python manage.py detect_junk2            # печать + файлы
    ./venv/bin/python manage.py detect_junk2 --dry-run  # только печать
"""

import os
import re
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand

from problems.models import Problem

REPORT_DIR = 'reports/quality_audit'

# \u25CF(●) \u25CB(○) \u25E6(◦) исключены: легитимные буллеты списков
# (IEO #7 — 11 задач, где других «плохих» глифов нет)
BAD_GLYPH_RE = re.compile(
    '[\ufffd'                 # �
    '\u25a0-\u25ca'           # геом. фигуры до ○ (○)
    '\u25cc-\u25ce'           # ◌◍◎ (○ U+25CB и ● U+25CF исключены)
    '\u25d0-\u25e5'           # ◐-◥
    '\u25e7-\u25ff'           # ◧-◿ (◦ U+25E6 исключён)
    '\u2580-\u259f'           # блоки
    '\ue000-\uf8ff'           # Private Use Area
    '\u239b-\u23b3]'          # куски скобок ⎧⎪⎨⎩ (улика #5174)
)

# строчная кириллическая в начале, но не маркер подпункта «а)» / «б.»
MIDWORD_RE = re.compile(r'^[а-яё](?![).\s])')
YEAR_STUB_RE = re.compile(r'^\d{4}\)')

NOT_A_PROBLEM_PATTERNS = [
    'приложи скриншот',
    'добавь скриншот',
    'на сайте marginal revolution',
    'выполни задание по ссылке',
]
NOT_A_PROBLEM_MAXLEN = 300


class Command(BaseCommand):
    help = 'Детекторы сессии H: битые глифы, обрезанные условия, не-задачи (только списки)'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', default=False,
                            help='Только печать, файлы не писать')

    def handle(self, *args, **options):
        os.makedirs(REPORT_DIR, exist_ok=True)

        bad_glyph = []
        midword = []
        not_a_problem = []
        glyph_counter = Counter()
        by_source = defaultdict(Counter)

        qs = Problem.objects.all().prefetch_related('parts').order_by('id')
        for p in qs.iterator(chunk_size=500):
            sid = None
            texts = [p.statement or '', p.solution or '', p.answer or '']
            for part in p.parts.all():
                texts.append(part.statement or '')
                texts.append(part.answer or '')

            hits = [ch for t in texts for ch in BAD_GLYPH_RE.findall(t)]
            if hits:
                bad_glyph.append(p.id)
                glyph_counter.update(hits)
                sid = sid or self._sid(p)
                by_source[sid]['bad_glyph'] += 1

            st = (p.statement or '').strip()
            if st and (MIDWORD_RE.match(st) or YEAR_STUB_RE.match(st)):
                midword.append(p.id)
                sid = sid or self._sid(p)
                by_source[sid]['midword'] += 1

            if st and len(st) < NOT_A_PROBLEM_MAXLEN:
                low = st.lower()
                if any(pat in low for pat in NOT_A_PROBLEM_PATTERNS):
                    not_a_problem.append(p.id)
                    sid = sid or self._sid(p)
                    by_source[sid]['not_a_problem'] += 1

        self.stdout.write(f'bad_glyph: {len(bad_glyph)} задач')
        self.stdout.write('  топ глифов: ' + ', '.join(
            f'{ch!r}(U+{ord(ch):04X})×{n}' for ch, n in glyph_counter.most_common(12)))
        self.stdout.write(f'midword: {len(midword)} задач')
        self.stdout.write(f'not_a_problem: {len(not_a_problem)} задач')
        self.stdout.write('По источникам:')
        for sid in sorted(by_source, key=lambda s: (s is None, s)):
            self.stdout.write(f'  src #{sid}: {dict(by_source[sid])}')

        if options['dry_run']:
            self.stdout.write('DRY-RUN: файлы не записаны.')
            return

        for fname, ids in (('bad_glyph_ids.txt', bad_glyph),
                           ('midword_ids.txt', midword),
                           ('not_a_problem_ids.txt', not_a_problem)):
            path = os.path.join(REPORT_DIR, fname)
            with open(path, 'w') as f:
                f.write('\n'.join(map(str, sorted(ids))) + ('\n' if ids else ''))
            self.stdout.write(self.style.SUCCESS(f'{path}: {len(ids)} id'))

    @staticmethod
    def _sid(p):
        ref = p.source_references.values_list('source_id', flat=True).first()
        return ref
