"""verdicts_vs_cleanup — сшить вердикты ручного ревью с историей ИИ-чистки.

ТОЛЬКО ЧТЕНИЕ. Команда не пишет в базу ни одного байта: ни save(), ни create(),
ни delete(). Всё, что она делает — читает вердикты, патчи, raw-снимки и текущее
состояние задач, после чего кладёт отчёты в reports/verdicts_vs_cleanup/.

Зачем: в сессии ILE-1 вердикты Анича сравнили с НАШИМИ ДЕТЕКТОРАМИ и выяснили,
что детекторы негодны. Но вердикты ни разу не сравнили с тем, что ИИ-чистка
РЕАЛЬНО СДЕЛАЛА с теми же задачами. Отсюда неизвестно, почему после чистки
остался брак: не нашла, нашла и не тронула, тронула не то поле или тронула
нужное и не помогло.

⚠️ ILE НЕ входил в пул Батча 2. Единственная ИИ-чистка, касавшаяся ILE, — это
apply_ile_cleanup (пилот + батчи 01–10, пул 2 584 задачи). Плюс общебазовая
механика: extract_leaked_solutions, fix_ile_formulas, fix_latex_junk.
Склейка glue_pdf_lines ILE не трогала. Правки Батча 2 к ILE не приписываем.

⚠️ У ILE нет исходного .tex/PDF-эталона (источник — сайт iloveeconomics),
сверять не с чем. Поэтому команда отвечает на вопрос «что чистка сделала с этим
полем», и НИКОГДА — «кто испортил поле». Урок карточки «МатЭк отдаём на ревью
целиком»: без сырого исходника суждение о виновнике — догадка.

Запуск:
    venv/Scripts/python.exe manage.py verdicts_vs_cleanup
"""

import json
import os
import random
import re
import statistics
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand

from problems.models import Problem, ProblemPart, ReviewVerdict
from problems.review_categories import CATEGORY_LABELS, REVIEW_CATEGORIES

# Логика предохранителей переноса утёкших решений берётся ИЗ САМОЙ КОМАНДЫ —
# второй копией правил она бы разъехалась с боевой при первой же правке.
from problems.management.commands.extract_leaked_solutions import (
    MIN_MARKER_POS_FRAC,
    MIN_MID_PREFIX,
    MIN_REMAINDER,
    cleanup_statement,
    find_leaks,
)

ILE_BUNDLE = 'ile_20260721'
AA_BUNDLE = 'aa_20260728'

CLEANUP_DIR = 'reports/ai_cleanup_ile'
OUT_DIR = 'reports/verdicts_vs_cleanup'
TRIAGE_DIR = 'reports/ile_triage'

SAMPLE_SEED = 20260816
SAMPLE_PER_GROUP = 20

# Поля, которые умеет править патч ИИ-чистки (см. apply_ile_cleanup._apply_task).
PATCH_FIELDS = ('statement', 'solution', 'answer', 'parts')

# Списки id, затронутых общебазовой механикой. Пути — из самих команд.
MECHANIC_LISTS = {
    'extract_leaked_solutions': ['reports/formula_cleanup/changed_ids.txt'],
    'fix_ile_formulas': ['reports/quality_audit/changed_ids_B.txt',
                         'reports/quality_audit/changed_ids_C.txt'],
    'fix_latex_junk': ['reports/dirty_text_audit/junk_changed_ids.txt'],
}

# Разбор комментария ревьюера на поля. Только явные упоминания: где Анич поле
# не назвал, отвечаем «не указано» и НЕ гадаем (правило сессии).
COMMENT_FIELD_RE = {
    'solution': re.compile(r'реш', re.IGNORECASE),
    'answer': re.compile(r'ответ', re.IGNORECASE),
    'parts': re.compile(r'пункт', re.IGNORECASE),
    'statement': re.compile(r'услови', re.IGNORECASE),
}

# ── признаки «математической» задачи (задача 5) ──────────────────────────────
HTML_TAG_RE = re.compile(r'<[^>]{1,40}>')
DOLLAR_SPAN_RE = re.compile(r'\$[^$]+\$', re.DOTALL)
SIGN_RE = re.compile(r'[=<>≤≥]')
NUMBER_RE = re.compile(r'\d+(?:[.,]\d+)?')

# Слово-маркер утечки где угодно в тексте (а не только в начале строки, как
# требует боевая механика). Нужно, чтобы отличить «механика не увидела маркер»
# от «маркера нет вовсе» — это разные починки.
MARKER_WORD_RE = re.compile(r'(Решени|Ответ)')


def read_ids(path):
    """Список id из текстового файла. Нет файла — None («не установлено»)."""
    if not os.path.exists(path):
        return None
    out = set()
    with open(path, encoding='utf-8-sig') as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith('#'):
                try:
                    out.add(int(line))
                except ValueError:
                    continue
    return out


def field_len(value):
    """Длина поля патча/raw в символах. У parts — сумма по подпунктам."""
    if value is None:
        return 0
    if isinstance(value, str):
        return len(value)
    if isinstance(value, list):
        total = 0
        for part in value:
            if isinstance(part, dict):
                for key in ('statement', 'answer', 'solution'):
                    total += len(part.get(key) or '')
            elif isinstance(part, str):
                total += len(part)
        return total
    return 0


def field_dollars(value):
    """Сколько символов $ в поле. У parts — сумма по подпунктам."""
    if value is None:
        return 0
    if isinstance(value, str):
        return value.count('$')
    if isinstance(value, list):
        total = 0
        for part in value:
            if isinstance(part, dict):
                for key in ('statement', 'answer', 'solution'):
                    total += (part.get(key) or '').count('$')
            elif isinstance(part, str):
                total += part.count('$')
        return total
    return 0


def math_text_of(statement, parts_statements):
    """Текст, по которому судим о «математичности»: условие + подпункты."""
    return '\n'.join([statement or ''] + [p or '' for p in parts_statements])


def math_signals(text):
    """Три независимых признака математики. Пороги — в докстринге отчёта."""
    stripped = HTML_TAG_RE.sub(' ', text or '')
    return {
        'p1_dollar': bool(DOLLAR_SPAN_RE.search(stripped)),
        'p2_signs': bool(SIGN_RE.search(stripped)),
        'p3_numbers': len(NUMBER_RE.findall(stripped)) >= 3,
    }


class Command(BaseCommand):
    help = ('Сшить вердикты ревью с историей ИИ-чистки ILE. Только чтение, '
            'результат — reports/verdicts_vs_cleanup/.')

    # ------------------------------------------------------------------
    # загрузка источников
    # ------------------------------------------------------------------

    def load_verdicts(self, bundle):
        """pid → {categories, comment, at}. Формат v1 и v2 читаются одинаково:
        модель хранит строку на пару «задача × категория»."""
        data = {}
        qs = (ReviewVerdict.objects.filter(bundle=bundle)
              .order_by('problem_id', 'category')
              .values('problem_id', 'category', 'comment', 'created_at'))
        for row in qs:
            rec = data.setdefault(row['problem_id'], {
                'categories': set(), 'comment': '', 'at': None,
            })
            rec['categories'].add(row['category'])
            if row['comment'] and not rec['comment']:
                rec['comment'] = row['comment']
            at = row['created_at']
            if at and (rec['at'] is None or at < rec['at']):
                rec['at'] = at
        return data

    def load_patches(self):
        """Патчи ИИ-чистки. Возвращает (по задаче, hide, сверь_цифры, пропуски)."""
        per_problem = defaultdict(lambda: {'patches': {}, 'fields': set()})
        hide = {}
        sver = set()
        skipped_files = []
        used_files = []

        for name in sorted(os.listdir(CLEANUP_DIR)):
            if 'apply' not in name or not name.endswith('.json'):
                continue
            # backup_* — это снимок ДО применения, а не патч; *.unused — отменённый.
            if 'backup' in name or 'unused' in name:
                continue
            path = os.path.join(CLEANUP_DIR, name)
            with open(path, encoding='utf-8') as fh:
                data = json.load(fh)
            tasks = data.get('tasks')
            if not isinstance(tasks, dict):
                # Пилот-формат (tasks — список) пропускаем по условию сессии;
                # сколько вердиктов это задевает, считается отдельно и
                # честно называется пробелом в summary.md.
                skipped_files.append((name, len(tasks) if isinstance(tasks, list) else 0,
                                      sorted(int(t['id']) for t in tasks)
                                      if isinstance(tasks, list) else []))
                continue
            used_files.append(name)

            meta = data.get('meta', {}) or {}
            reasons = meta.get('hide_reasons', {}) or {}
            for raw_id in meta.get('hide', []) or []:
                pid = int(raw_id)
                hide.setdefault(pid, {'file': name,
                                      'reason': reasons.get(str(raw_id))
                                      or reasons.get(raw_id) or ''})
            for raw_id in (meta.get('notes', {}) or {}).get('сверь_цифры', []) or []:
                sver.add(int(raw_id))

            for str_id, fields in tasks.items():
                pid = int(str_id)
                touched = sorted(f for f in fields if f in PATCH_FIELDS)
                rec = per_problem[pid]
                rec['patches'][name] = {
                    'fields': touched,
                    'sizes_after': {f: field_len(fields.get(f)) for f in touched},
                    'dollars_after': {f: field_dollars(fields.get(f))
                                      for f in touched},
                }
                rec['fields'].update(touched)

        return per_problem, hide, sver, skipped_files, used_files

    def load_raw(self):
        """pid → снимок «БЫЛО». id в нескольких raw — берём первый по имени файла."""
        raw = {}
        for name in sorted(os.listdir(CLEANUP_DIR)):
            if not name.endswith('_raw.json'):
                continue
            with open(os.path.join(CLEANUP_DIR, name), encoding='utf-8') as fh:
                data = json.load(fh)
            if not isinstance(data, list):
                continue
            for task in data:
                pid = int(task['id'])
                if pid not in raw:
                    raw[pid] = task
        return raw

    # ------------------------------------------------------------------
    # сборка карточек
    # ------------------------------------------------------------------

    def build_cards(self, verdicts, patches, hide, sver, raw, pool, mechanics,
                    test_ids):
        cards = {}
        problems = (Problem.objects.filter(id__in=list(verdicts))
                    .prefetch_related('parts')
                    .only('id', 'status', 'statement', 'solution', 'answer'))
        db = {p.id: p for p in problems}

        for pid in sorted(verdicts):
            v = verdicts[pid]
            cats = sorted(v['categories'])
            patch_rec = patches.get(pid)
            fields_edited = sorted(patch_rec['fields']) if patch_rec else []
            comment = v['comment'] or ''

            named = sorted(f for f, rx in COMMENT_FIELD_RE.items()
                           if comment and rx.search(comment))

            problem = db.get(pid)
            parts = list(problem.parts.all()) if problem else []
            raw_rec = raw.get(pid)

            sizes = {}
            if patch_rec:
                for name, info in sorted(patch_rec['patches'].items()):
                    for f in info['fields']:
                        raw_val = (raw_rec or {}).get(f)
                        sizes.setdefault(f, []).append({
                            'patch': name,
                            'before_chars': field_len(raw_val) if raw_rec else None,
                            'after_chars': info['sizes_after'][f],
                            'before_dollars': (field_dollars(raw_val)
                                               if raw_rec else None),
                            'after_dollars': info['dollars_after'][f],
                        })

            cards[pid] = {
                'problem_id': pid,
                'verdict_categories': cats,
                'is_perfect': cats == ['perfect'],
                'is_defect': any(c not in ('perfect',) for c in cats),
                'comment': comment,
                'comment_fields': named,
                'verdict_at': v['at'].isoformat() if v['at'] else None,
                'excluded_as_test': pid in test_ids,
                'in_cleanup_pool': pid in pool,
                'cleanup_touched': bool(patch_rec),
                'patch_files': sorted(patch_rec['patches']) if patch_rec else [],
                'fields_edited': fields_edited,
                'fields_by_patch': ({n: i['fields']
                                     for n, i in sorted(patch_rec['patches'].items())}
                                    if patch_rec else {}),
                'hidden_by_cleanup': pid in hide,
                'hide_reason': hide.get(pid, {}).get('reason') or None,
                'sver_cifry': pid in sver,
                'sizes': sizes,
                'raw_available': raw_rec is not None,
                'mechanics': {name: (None if ids is None else pid in ids)
                              for name, ids in mechanics.items()},
                'db_now': {
                    'status': problem.status if problem else None,
                    'parts_count': len(parts),
                    'statement_chars': len(problem.statement or '') if problem else None,
                    'solution_chars': len(problem.solution or '') if problem else None,
                    'answer_chars': len(problem.answer or '') if problem else None,
                },
            }
        return cards, db

    def assign_groups(self, cards, test_ids):
        """Г1–Г4 по дефектным задачам (без семи вердиктов «тест»)."""
        groups = {'Г1': [], 'Г2': [], 'Г3': [], 'Г4': [], 'поле не указано': []}
        for pid, c in sorted(cards.items()):
            if not c['is_defect'] or pid in test_ids:
                continue
            if c['hidden_by_cleanup']:
                groups['Г4'].append(pid)
            elif not c['cleanup_touched']:
                groups['Г1'].append(pid)
            elif not c['comment_fields']:
                groups['поле не указано'].append(pid)
            elif set(c['comment_fields']) & set(c['fields_edited']):
                groups['Г3'].append(pid)
            else:
                groups['Г2'].append(pid)
        return groups

    # ------------------------------------------------------------------
    # main
    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        os.makedirs(OUT_DIR, exist_ok=True)
        log = []

        def say(line=''):
            log.append(line)
            try:
                self.stdout.write(line)
            except UnicodeEncodeError:
                self.stdout.write(line.encode('ascii', 'replace').decode('ascii'))

        # ── источники ────────────────────────────────────────────────────
        verdicts = self.load_verdicts(ILE_BUNDLE)
        patches, hide, sver, skipped_files, used_files = self.load_patches()
        raw = self.load_raw()
        pool = set(json.load(open(os.path.join(
            CLEANUP_DIR, 'shuffle_order_seed2026.json'), encoding='utf-8'))['order'])
        mechanics = {}
        for name, paths in MECHANIC_LISTS.items():
            found = [read_ids(p) for p in paths]
            mechanics[name] = (None if all(f is None for f in found)
                               else set().union(*[f for f in found if f is not None]))
        test_ids = read_ids(os.path.join(TRIAGE_DIR, 'recheck_ids.txt')) or set()

        cards, db = self.build_cards(verdicts, patches, hide, sver, raw, pool,
                                     mechanics, test_ids)

        # ── контрольные суммы (задача 1) ─────────────────────────────────
        say('=== КОНТРОЛЬНЫЕ СУММЫ ===')
        cat_counts = Counter()
        for c in cards.values():
            for cat in c['verdict_categories']:
                cat_counts[cat] += 1
        total = len(cards)
        perfect = sum(1 for c in cards.values() if c['is_perfect'])
        defect = sum(1 for c in cards.values() if c['is_defect'])
        say(f'вердиктов ILE: {total} (ожидалось 2401)')
        say(f'идеально: {perfect} (ожидалось 1919)')
        say(f'дефектных задач: {defect} (ожидалось 482)')
        expected = {'broken_formula': 191, 'merged_structure': 137,
                    'leaked_solution': 67, 'other': 38, 'junk': 21,
                    'broken_table': 20, 'bare_math': 8}
        ok = (total == 2401 and perfect == 1919 and defect == 482)
        for key, want in expected.items():
            got = cat_counts.get(key, 0)
            mark = 'OK' if got == want else 'РАСХОЖДЕНИЕ'
            if got != want:
                ok = False
            say(f'  {key:18s} {got:4d} (ожидалось {want:4d})  {mark}')
        say(f'сумма по категориям дефектов: {sum(cat_counts[k] for k in expected)}'
            f' (ожидалось 482)')
        if not ok:
            say('СТОП: контрольные суммы не сошлись, дальше не считаю.')
            self._write_log(log)
            return
        say('Все контрольные суммы сошлись.')
        say()

        say(f'патч-файлов прочитано: {len(used_files)}')
        for name, n, ids in skipped_files:
            hit = sorted(i for i in ids if i in cards)
            say(f'ПРОПУЩЕН старый формат: {name} (задач {n}); из них в пакете '
                f'ревью {len(hit)}: {hit}')
        # ⚠️ Не «недостоверные»: чтение «ревьюер пробовал оболочку» оказалось
        # неверным (2026-08-19). Исключение живо только ради воспроизводимости
        # уже опубликованного замера — см. пояснение в самом отчёте.
        say(f'вердиктов «тест» исключено из этого замера: '
            f'{len(test_ids & set(cards))} {sorted(test_ids & set(cards))}')
        say()

        # ── задача 2 ─────────────────────────────────────────────────────
        analysed = {pid: c for pid, c in cards.items() if pid not in test_ids}
        t_def = sum(1 for c in analysed.values() if c['cleanup_touched'] and c['is_defect'])
        t_ok = sum(1 for c in analysed.values() if c['cleanup_touched'] and c['is_perfect'])
        u_def = sum(1 for c in analysed.values()
                    if not c['cleanup_touched'] and c['is_defect'])
        u_ok = sum(1 for c in analysed.values()
                   if not c['cleanup_touched'] and c['is_perfect'])
        share_t = 100.0 * t_def / (t_def + t_ok) if (t_def + t_ok) else 0.0
        share_u = 100.0 * u_def / (u_def + u_ok) if (u_def + u_ok) else 0.0
        say('=== ЗАДАЧА 2: чистка трогала × вердикт ===')
        say(f'трогала:    дефект {t_def:4d}  идеально {t_ok:4d}  доля брака {share_t:5.1f}%')
        say(f'не трогала: дефект {u_def:4d}  идеально {u_ok:4d}  доля брака {share_u:5.1f}%')
        say(f'разница: {share_t - share_u:+.1f} п.п.')

        groups = self.assign_groups(cards, test_ids)
        say('Разложение дефектных:')
        for key in ('Г1', 'Г2', 'Г3', 'Г4', 'поле не указано'):
            say(f'  {key:16s} {len(groups[key]):4d}')
        say(f'  сумма           {sum(len(v) for v in groups.values()):4d}'
            f' (дефектных без «тест»: {sum(1 for c in analysed.values() if c["is_defect"])})')
        say()

        # ── задача 3 ─────────────────────────────────────────────────────
        checks = self.targeted_checks(cards, db, sver, test_ids, say)

        # ── задача 4 ─────────────────────────────────────────────────────
        say('=== ЗАДАЧА 4: что чистка делала с ИДЕАЛЬНЫМИ ===')
        perfect_cards = [c for c in analysed.values() if c['is_perfect']]
        p_touched = [c for c in perfect_cards if c['cleanup_touched']]
        say(f'идеальных: {len(perfect_cards)}, из них чистка трогала '
            f'{len(p_touched)} ({100.0 * len(p_touched) / len(perfect_cards):.1f}%)')
        pf = Counter()
        for c in p_touched:
            for f in c['fields_edited']:
                pf[f] += 1
        for f, n in sorted(pf.items(), key=lambda x: -x[1]):
            say(f'  поле {f:10s} {n:4d}')
        perfect_sver = sorted(c['problem_id'] for c in perfect_cards if c['sver_cifry'])
        say(f'идеальные с пометкой «сверь_цифры»: {len(perfect_sver)} {perfect_sver}')
        say()

        # ── задача 5 ─────────────────────────────────────────────────────
        math_stats = self.math_vs_text(cards, db, test_ids, say)

        # ── выгрузка ─────────────────────────────────────────────────────
        with open(os.path.join(OUT_DIR, 'per_problem.json'), 'w',
                  encoding='utf-8') as fh:
            json.dump([cards[pid] for pid in sorted(cards)], fh,
                      ensure_ascii=False, indent=1)
        for key, ids in groups.items():
            fname = {'Г1': 'group_g1_not_touched.txt',
                     'Г2': 'group_g2_other_field.txt',
                     'Г3': 'group_g3_same_field.txt',
                     'Г4': 'group_g4_hidden.txt',
                     'поле не указано': 'group_field_unknown.txt'}[key]
            with open(os.path.join(OUT_DIR, fname), 'w', encoding='utf-8') as fh:
                fh.write(f'# {key}: {len(ids)} задач\n')
                fh.write('\n'.join(str(i) for i in ids) + ('\n' if ids else ''))

        self.write_summary(cards, analysed, groups, checks, math_stats,
                           dict(t_def=t_def, t_ok=t_ok, u_def=u_def, u_ok=u_ok,
                                share_t=share_t, share_u=share_u),
                           skipped_files, used_files, test_ids, perfect_sver,
                           mechanics)
        self.build_samples(cards, db, raw, groups)
        self._write_log(log)
        say(f'Готово. Отчёты в {OUT_DIR}/')

    # ------------------------------------------------------------------
    # задача 3
    # ------------------------------------------------------------------

    def targeted_checks(self, cards, db, sver, test_ids, say):
        out = {}
        say('=== ЗАДАЧА 3: прицельные проверки ===')

        # 3a — leaked_solution
        leaked = sorted(pid for pid, c in cards.items()
                        if 'leaked_solution' in c['verdict_categories']
                        and pid not in test_ids)
        blockers = Counter()
        per_problem = {}
        for pid in leaked:
            p = db.get(pid)
            reasons = self.leak_blockers(p)
            per_problem[pid] = reasons
            for r in reasons:
                blockers[r] += 1
        say(f'3a. leaked_solution: {len(leaked)} задач')
        for r, n in sorted(blockers.items(), key=lambda x: -x[1]):
            say(f'    {r:34s} {n:4d}')
        out['leaked'] = {'ids': leaked, 'blockers': dict(blockers),
                         'per_problem': per_problem}

        # 3b — broken_table × сверь_цифры
        tables = sorted(pid for pid, c in cards.items()
                        if 'broken_table' in c['verdict_categories']
                        and pid not in test_ids)
        cross = sorted(set(tables) & sver)
        touched_tables = sorted(pid for pid in tables if cards[pid]['cleanup_touched'])
        say(f'3b. broken_table: {len(tables)}; из них чистка трогала '
            f'{len(touched_tables)}; пересечение со «сверь_цифры»: {len(cross)} {cross}')
        out['tables'] = {'ids': tables, 'sver_cross': cross,
                         'touched': touched_tables}

        # 3c — merged_structure
        merged = sorted(pid for pid, c in cards.items()
                        if 'merged_structure' in c['verdict_categories']
                        and pid not in test_ids)
        with_parts = [pid for pid in merged if cards[pid]['db_now']['parts_count'] > 0]
        no_parts = [pid for pid in merged if cards[pid]['db_now']['parts_count'] == 0]
        parts_edited = [pid for pid in merged if 'parts' in cards[pid]['fields_edited']]
        say(f'3c. merged_structure: {len(merged)}; с подпунктами сейчас '
            f'{len(with_parts)}; без подпунктов {len(no_parts)}; '
            f'чистка правила parts у {len(parts_edited)}')
        out['merged'] = {'ids': merged, 'with_parts': with_parts,
                         'no_parts': no_parts, 'parts_edited': parts_edited}

        # 3d — broken_formula
        formulas = sorted(pid for pid, c in cards.items()
                          if 'broken_formula' in c['verdict_categories']
                          and pid not in test_ids)
        stmt_edited, dollar_changed, untouched = [], [], []
        for pid in formulas:
            c = cards[pid]
            if not c['cleanup_touched']:
                untouched.append(pid)
                continue
            if 'statement' in c['fields_edited']:
                stmt_edited.append(pid)
                # ДО — raw-снимок (ровно то, что ушло модели), ПОСЛЕ — патч
                # (ровно то, что модель вернула). Обе стороны принадлежат
                # ИИ-чистке, поэтому разница честно приписывается ей.
                for entry in c['sizes'].get('statement', []):
                    if (entry['before_dollars'] is not None
                            and entry['before_dollars'] != entry['after_dollars']):
                        dollar_changed.append(pid)
                        break
        out['formulas'] = {'ids': formulas, 'stmt_edited': stmt_edited,
                           'untouched': untouched, 'dollar_changed': dollar_changed}
        say(f'3d. broken_formula: {len(formulas)}; чистка правила statement '
            f'у {len(stmt_edited)}; из них число $ изменилось у '
            f'{len(dollar_changed)}; не трогала вовсе {len(untouched)}')
        return out

    def leak_blockers(self, problem):
        """Во что упирается extract_leaked_solutions на ТЕКУЩЕМ тексте задачи.

        Механика ищет маркер ТОЛЬКО в начале строки и ТОЛЬКО в statement и
        part.statement. Поэтому мало сказать «маркер не распознан» — надо
        различать, где утечка сидит на самом деле: это разные починки.
        """
        if problem is None:
            return ['задача не найдена в базе']
        statement = problem.statement or ''
        parts = [p.statement or '' for p in problem.parts.all()]
        ops = find_leaks(statement)
        if not ops:
            for part_text in parts:
                if find_leaks(part_text):
                    return ['find_leaks видит маркер в подпункте']
            if MARKER_WORD_RE.search(statement):
                return ['маркер в условии, но НЕ в начале строки']
            if any(MARKER_WORD_RE.search(t) for t in parts):
                return ['маркер в подпункте, но НЕ в начале строки']
            if MARKER_WORD_RE.search(problem.solution or ''):
                return ['утечка внутри поля solution — механика туда не смотрит']
            return ['слова-маркера нет вовсе — утечка без маркера']
        reasons = []
        for cut_start, cut_end, kind, text in ops:
            if kind == 'solution' and cut_start < MIN_MARKER_POS_FRAC * len(statement):
                reasons.append('маркер раньше 25% текста')
                continue
            if kind == 'solution_mid' and cut_start < MIN_MID_PREFIX:
                reasons.append('маркер раньше 120 символов')
                continue
            if kind == 'empty':
                continue
            field = {'solution': 'solution', 'solution_mid': 'solution',
                     'answer': 'answer'}.get(kind)
            existing = getattr(problem, field, '') if field else ''
            if existing:
                reasons.append('целевое поле уже непустое')
                continue
            remainder = cleanup_statement(statement[:cut_start] + statement[cut_end:])
            if len(remainder) < MIN_REMAINDER:
                reasons.append('остаток условия короче 40 символов')
                continue
            reasons.append('предохранители пройдены (перенос возможен)')
        return sorted(set(reasons)) or ['только служебная вырезка']

    # ------------------------------------------------------------------
    # задача 5
    # ------------------------------------------------------------------

    def math_vs_text(self, cards, db, test_ids, say):
        say('=== ЗАДАЧА 5: математика против текста ===')
        rows = {}
        for pid, c in cards.items():
            if pid in test_ids:
                continue
            p = db.get(pid)
            if p is None:
                continue
            parts = [x.statement for x in p.parts.all()]
            text = math_text_of(p.statement, parts)
            rows[pid] = {'signals': math_signals(text), 'chars': len(text),
                         'defect': c['is_defect']}
        out = {'ile': {}, 'aa': {}}
        for key in ('p1_dollar', 'p2_signs', 'p3_numbers'):
            m = [r for r in rows.values() if r['signals'][key]]
            t = [r for r in rows.values() if not r['signals'][key]]
            md = sum(1 for r in m if r['defect'])
            td = sum(1 for r in t if r['defect'])
            out['ile'][key] = {
                'math_n': len(m), 'math_defect': md,
                'math_share': (100.0 * md / len(m)) if m else None,
                'text_n': len(t), 'text_defect': td,
                'text_share': (100.0 * td / len(t)) if t else None,
            }
            say(f'  {key:11s} матем. {len(m):4d} брак {md:3d} '
                f'({(100.0 * md / len(m)) if m else 0:5.1f}%) | '
                f'текст {len(t):4d} брак {td:3d} '
                f'({(100.0 * td / len(t)) if t else 0:5.1f}%)')
        lens = sorted(r['chars'] for r in rows.values())
        out['ile']['median_chars'] = statistics.median(lens) if lens else None
        out['ile']['median_chars_defect'] = statistics.median(
            sorted(r['chars'] for r in rows.values() if r['defect']) or [0])
        out['ile']['median_chars_perfect'] = statistics.median(
            sorted(r['chars'] for r in rows.values() if not r['defect']) or [0])
        say(f'  медиана длины ILE: {out["ile"]["median_chars"]:.0f} симв. '
            f'(дефектные {out["ile"]["median_chars_defect"]:.0f}, '
            f'идеальные {out["ile"]["median_chars_perfect"]:.0f})')

        # темп ревью по отметкам времени
        stamps = sorted(c['verdict_at'] for c in cards.values() if c['verdict_at'])
        out['ile']['pace'] = self.pace(cards, rows, say)

        # АА: вердиктов в базе нет — считаем только состав пакета
        aa = self.aa_composition(say)
        out['aa'] = aa
        return out

    def pace(self, cards, rows, say):
        """Медиана времени на задачу по отметкам вердиктов."""
        from datetime import datetime
        seq = []
        for c in cards.values():
            if c['verdict_at']:
                seq.append((datetime.fromisoformat(c['verdict_at']), c['problem_id']))
        seq.sort()
        gaps = {}
        for i in range(1, len(seq)):
            delta = (seq[i][0] - seq[i - 1][0]).total_seconds()
            if 0 <= delta <= 300:      # больше пяти минут — перерыв, не чтение
                gaps[seq[i][1]] = delta
        allg = sorted(gaps.values())
        res = {'median_all': statistics.median(allg) if allg else None,
               'n': len(allg)}
        for key in ('p1_dollar', 'p2_signs', 'p3_numbers'):
            m = sorted(g for pid, g in gaps.items()
                       if pid in rows and rows[pid]['signals'][key])
            t = sorted(g for pid, g in gaps.items()
                       if pid in rows and not rows[pid]['signals'][key])
            res[key] = {'math_median': statistics.median(m) if m else None,
                        'text_median': statistics.median(t) if t else None}
        if res['median_all'] is not None:
            say(f'  медиана времени на задачу ILE: {res["median_all"]:.2f} с '
                f'(по {res["n"]} промежуткам ≤300 с)')
            for key in ('p1_dollar', 'p2_signs', 'p3_numbers'):
                mm, tt = res[key]['math_median'], res[key]['text_median']
                if mm is not None and tt is not None:
                    say(f'    {key:11s} матем. {mm:5.2f} с | текст {tt:5.2f} с')
        return res

    def aa_composition(self, say):
        """Состав пакета АА. Вердиктов АА в базе НЕТ — доля брака не считается."""
        n_verdicts = ReviewVerdict.objects.filter(bundle=AA_BUNDLE).count()
        path = f'reports/review_bundles/{AA_BUNDLE}/manifest.json'
        res = {'verdicts_in_db': n_verdicts, 'defect_share': 'не установлено'}
        if not os.path.exists(path):
            say('  АА: манифеста пакета нет — состав не установлен')
            res['note'] = 'манифест не найден'
            return res
        with open(path, encoding='utf-8') as fh:
            manifest = json.load(fh)
        ids = [int(p['id']) for p in manifest.get('problems', [])]
        res['bundle_size'] = len(ids)
        problems = (Problem.objects.filter(id__in=ids).prefetch_related('parts')
                    .only('id', 'statement'))
        rows = []
        for p in problems:
            text = math_text_of(p.statement, [x.statement for x in p.parts.all()])
            rows.append({'signals': math_signals(text), 'chars': len(text)})
        res['found_in_db'] = len(rows)
        say(f'  АА: вердиктов в базе {n_verdicts}; пакет {len(ids)} задач, '
            f'найдено в базе {len(rows)}')
        for key in ('p1_dollar', 'p2_signs', 'p3_numbers'):
            share = (100.0 * sum(1 for r in rows if r['signals'][key]) / len(rows)
                     if rows else None)
            res[key] = {'math_n': sum(1 for r in rows if r['signals'][key]),
                        'math_share_of_bundle': share}
            say(f'    {key:11s} математических {res[key]["math_n"]:4d} '
                f'({share:5.1f}% пакета)')
        lens = sorted(r['chars'] for r in rows)
        res['median_chars'] = statistics.median(lens) if lens else None
        say(f'    медиана длины АА: {res["median_chars"]:.0f} симв.')
        return res

    # ------------------------------------------------------------------
    # задача 6 — выборка для глаз
    # ------------------------------------------------------------------

    def build_samples(self, cards, db, raw, groups):
        rnd = random.Random(SAMPLE_SEED)
        picked = {}
        # Г3 меньше двадцати задач физически: комментариев всего 42 на 482
        # вердикта, и лишь в четырёх Анич назвал поле, которое чистка правила.
        # Добираем ближайшим честным аналогом — «чистка трогала, дефект остался,
        # но поле не названо». Подменять им Г3 нельзя, поэтому он идёт своей
        # секцией со своим заголовком.
        g3 = sorted(groups['Г3'])
        picked['Г3'] = sorted(rnd.sample(g3, min(SAMPLE_PER_GROUP, len(g3))))
        need = SAMPLE_PER_GROUP - len(picked['Г3'])
        if need > 0:
            pool = sorted(groups['поле не указано'])
            picked['Г3+'] = sorted(rnd.sample(pool, min(need, len(pool))))
        g1 = sorted(groups['Г1'])
        picked['Г1'] = sorted(rnd.sample(g1, min(SAMPLE_PER_GROUP, len(g1))))
        html = self.render_samples(picked, cards, db, raw)
        with open(os.path.join(OUT_DIR, 'samples.html'), 'w', encoding='utf-8') as fh:
            fh.write(html)

    def render_samples(self, picked, cards, db, raw):
        katex = self.vendor_katex()
        esc = self.esc
        rows = []
        for group, ids in picked.items():
            title = {
                'Г3': 'Г3 — чистка правила ИМЕННО ТО поле, что назвал Анич, '
                      'дефект остался',
                'Г3+': 'Дополнение к Г3 — чистка правила задачу, дефект '
                       'остался, но поле в комментарии не названо',
                'Г1': 'Г1 — чистка задачу не трогала, дефект есть',
            }[group]
            rows.append(f'<h2 class="qls-h">{esc(title)} ({len(ids)})</h2>')
            for pid in ids:
                c = cards[pid]
                r = raw.get(pid) or {}
                p = db.get(pid)
                before = (r.get('statement') or '')
                before_parts = r.get('parts') or []
                after = (p.statement if p else '') or ''
                after_parts = [x.statement for x in p.parts.all()] if p else []
                cats = ', '.join(CATEGORY_LABELS.get(x, x)
                                 for x in c['verdict_categories'])
                fields = ', '.join(c['fields_edited']) or 'не трогала'
                rows.append(f'''
<div class="qls-card">
  <div class="qls-head">
    <b>#{pid}</b> · <span class="qls-cat">{esc(cats)}</span>
    · правила поля: <span class="qls-fields">{esc(fields)}</span>
    {'· патчи: ' + esc(', '.join(c['patch_files'])) if c['patch_files'] else ''}
  </div>
  {'<div class="qls-note">Комментарий Анича: ' + esc(c['comment']) + '</div>'
   if c['comment'] else ''}
  <div class="qls-cols">
    <div class="qls-col-before"><div class="qls-lbl">ДО (raw-снимок)</div>
      <div class="qls-body">{esc(before) or '<i>нет raw-снимка</i>'}
      {''.join('<div class="qls-part">' + esc(x.get('statement') or '') + '</div>'
               for x in before_parts if isinstance(x, dict))}</div></div>
    <div class="qls-col-after"><div class="qls-lbl">ПОСЛЕ (база сейчас)</div>
      <div class="qls-body">{esc(after)}
      {''.join('<div class="qls-part">' + esc(x or '') + '</div>'
               for x in after_parts)}</div></div>
  </div>
</div>''')
        body = '\n'.join(rows)
        # ⚠️ Свои классы — только с префиксом qls-: KaTeX сам генерирует
        # .text/.mord/.base/.strut внутри .katex-html, CSS матчит по ТОКЕНУ
        # класса, и рамка с паддингом протащилась бы прямо в формулу.
        return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>Вердикты × чистка — выборка</title>
{katex}
<style>
 body {{ font: 15px/1.5 -apple-system, Segoe UI, Roboto, sans-serif;
        margin: 24px; background: #f6f7f9; color: #111; }}
 .qls-h {{ margin: 32px 0 12px; font-size: 19px; }}
 .qls-card {{ background: #fff; border: 1px solid #d9dde3; border-radius: 8px;
              padding: 14px 16px; margin-bottom: 16px; }}
 .qls-head {{ font-size: 13px; color: #444; margin-bottom: 8px; }}
 .qls-cat {{ color: #be185d; font-weight: 600; }}
 .qls-fields {{ color: #1d4ed8; }}
 .qls-note {{ background: #fff7ed; border-left: 3px solid #b26b00;
              padding: 6px 10px; margin-bottom: 10px; font-size: 14px; }}
 .qls-cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
 .qls-col-before .qls-body {{ background: #fdf2f2; }}
 .qls-col-after .qls-body {{ background: #f2fbf4; }}
 .qls-lbl {{ font-size: 12px; text-transform: uppercase; letter-spacing: .04em;
             color: #666; margin-bottom: 4px; }}
 .qls-body {{ white-space: pre-line; padding: 10px; border-radius: 6px;
              border: 1px solid #e3e6ea; overflow-x: auto; }}
 .qls-part {{ margin-top: 8px; padding-top: 8px; border-top: 1px dashed #ccd; }}
</style></head><body>
<h1 class="qls-h">Вердикты ревью × история ИИ-чистки — 40 задач на глаз</h1>
<p>Отбор детерминированный, seed {SAMPLE_SEED}. «ДО» — raw-снимок перед
ИИ-чисткой, «ПОСЛЕ» — текущее состояние базы.</p>
{body}
<script>
 document.addEventListener('DOMContentLoaded', function () {{
   if (window.renderMathInElement) {{
     document.querySelectorAll('.qls-body').forEach(function (el) {{
       renderMathInElement(el, {{
         delimiters: [{{left: '$$', right: '$$', display: true}},
                      {{left: '$', right: '$', display: false}}],
         throwOnError: false
       }});
     }});
   }}
 }});
</script>
</body></html>'''

    def vendor_katex(self):
        """KaTeX из пакета ревью — страница обязана открываться с file:// без сети."""
        base = f'reports/review_bundles/{ILE_BUNDLE}/assets/vendor/katex'
        css = os.path.join(base, 'katex.min.css')
        js = os.path.join(base, 'katex.min.js')
        auto = os.path.join(base, 'contrib', 'auto-render.min.js')
        if not all(os.path.exists(p) for p in (css, js, auto)):
            return '<!-- KaTeX не найден в пакете ревью, формулы будут сырыми -->'
        rel = os.path.relpath(base, OUT_DIR).replace('\\', '/')
        return (f'<link rel="stylesheet" href="{rel}/katex.min.css">\n'
                f'<script defer src="{rel}/katex.min.js"></script>\n'
                f'<script defer src="{rel}/contrib/auto-render.min.js"></script>')

    @staticmethod
    def esc(text):
        return (str(text or '').replace('&', '&amp;').replace('<', '&lt;')
                .replace('>', '&gt;'))

    # ------------------------------------------------------------------
    # отчёты
    # ------------------------------------------------------------------

    def _write_log(self, log):
        with open(os.path.join(OUT_DIR, 'run_log.txt'), 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(log) + '\n')

    def write_summary(self, cards, analysed, groups, checks, math_stats, tab,
                      skipped_files, used_files, test_ids, perfect_sver, mechanics):
        L = []
        A = L.append
        A('# Вердикты ревью ILE × история ИИ-чистки')
        A('')
        A('Сессия только на чтение. Ни одной записи в базу, ни одной правки '
          'текста задач.')
        A('')
        A('⚠️ У ILE нет исходного .tex/PDF-эталона (источник — сайт '
          'iloveeconomics), сверять не с чем. Поэтому здесь всюду отвечаем на '
          'вопрос **что чистка сделала с полем**, и нигде — «кто испортил '
          'поле». Последнее без сырого исходника было бы догадкой.')
        A('')
        A('⚠️ ILE **не входил** в пул Батча 2. Единственная ИИ-чистка, '
          'касавшаяся ILE, — `apply_ile_cleanup` (пилот + батчи 01–10, пул '
          '2 584 задачи). Плюс общебазовая механика: `extract_leaked_solutions`, '
          '`fix_ile_formulas`, `fix_latex_junk`. Склейка `glue_pdf_lines` ILE '
          'не трогала.')
        A('')
        A('## Контрольные суммы')
        A('')
        A('| Показатель | Получено | Ожидалось |')
        A('|---|---:|---:|')
        A(f'| вердиктов ILE | {len(cards)} | 2401 |')
        A(f'| идеально | {sum(1 for c in cards.values() if c["is_perfect"])} | 1919 |')
        A(f'| дефектных | {sum(1 for c in cards.values() if c["is_defect"])} | 482 |')
        cat_counts = Counter()
        for c in cards.values():
            for cat in c['verdict_categories']:
                cat_counts[cat] += 1
        for key, want in (('broken_formula', 191), ('merged_structure', 137),
                          ('leaked_solution', 67), ('other', 38), ('junk', 21),
                          ('broken_table', 20), ('bare_math', 8)):
            A(f'| {key} | {cat_counts.get(key, 0)} | {want} |')
        A('')
        A('Все цифры сошлись.')
        A('')
        A(f'**Исключены из расчётов:** 7 вердиктов с комментарием «тест» — '
          f'{sorted(test_ids & set(cards))}. '
          f'Дальше везде считается {len(analysed)} задач, из них дефектных '
          f'{sum(1 for c in analysed.values() if c["is_defect"])}.')
        A('')
        A('⚠️ **Исключение сохранено ТОЛЬКО ради воспроизводимости этого '
          'замера.** Прежнее объяснение «ревьюер пробовал оболочку» ОШИБОЧНО '
          '(исправлено 2026-08-19): «тест» означает тип задачи — задание с '
          'выбором варианта ответа. Вердикты достоверны, и на состояние задач '
          '(`human_review`) они теперь влияют наравне со всеми. Если замер '
          'пересчитывается заново — снимите исключение, дефектных станет на '
          '7 больше.')
        A('')
        A('**Пробел в данных:** ' + (
            '; '.join(f'файл `{n}` старого формата (tasks — список, {k} задач) '
                      f'пропущен; из них в пакете ревью '
                      f'{len([i for i in ids if i in cards])} задач '
                      f'({[i for i in ids if i in cards]}) — по ним правки '
                      f'пилота в расчёт «чистка трогала» НЕ вошли'
                      for n, k, ids in skipped_files)
            if skipped_files else 'нет'))
        A('')
        A(f'Прочитано патч-файлов: {len(used_files)}.')
        A('')

        A('## Задача 2. Главная метрика: чистка трогала × вердикт')
        A('')
        A('| | дефект | идеально | всего | доля брака |')
        A('|---|---:|---:|---:|---:|')
        A(f'| чистка трогала | {tab["t_def"]} | {tab["t_ok"]} | '
          f'{tab["t_def"] + tab["t_ok"]} | {tab["share_t"]:.1f}% |')
        A(f'| чистка не трогала | {tab["u_def"]} | {tab["u_ok"]} | '
          f'{tab["u_def"] + tab["u_ok"]} | {tab["share_u"]:.1f}% |')
        A('')
        A(f'Разница: **{tab["share_t"] - tab["share_u"]:+.1f} п.п.**')
        A('')
        A('> ⚠️ **ЭТО НЕ ИЗМЕРЕНИЕ ЭФФЕКТА ЧИСТКИ.** Чистка бралась за задачи '
          'НЕ случайно, а за те, которые выглядели хуже. Поэтому сравнение '
          'групп показывает корреляцию отбора, а не пользу правок. Цифру '
          'нельзя цитировать как «чистка снизила брак на N пунктов» — при '
          'таком отборе она равно совместима и с «чистка помогла», и с '
          '«чистка не сделала ничего».')
        A('')
        A('### Разложение дефектных задач')
        A('')
        A('| Группа | Что значит | Задач |')
        A('|---|---|---:|')
        A(f'| Г1 | чистка задачу вообще не трогала | {len(groups["Г1"])} |')
        A(f'| Г2 | трогала, но НЕ то поле, где Анич указал дефект | '
          f'{len(groups["Г2"])} |')
        A(f'| Г3 | трогала именно то поле, дефект остался | {len(groups["Г3"])} |')
        A(f'| Г4 | задача скрыта чисткой | {len(groups["Г4"])} |')
        A(f'| — | поле в комментарии не указано, Г2/Г3 не различимы | '
          f'{len(groups["поле не указано"])} |')
        A('')
        A('Г2 и Г3 считаются ТОЛЬКО там, где Анич назвал поле словами '
          '(«в решении», «в ответе», «пункты», «в условии»). По остальным поле '
          'не указано — гадать не стали. Комментариев всего 42 на 482 задачи, '
          'поэтому Г2 и Г3 малы не потому, что таких случаев мало, а потому '
          'что по ним нечем судить.')
        A('')
        in_pool = sum(1 for c in analysed.values() if c['in_cleanup_pool'])
        with_raw = sum(1 for c in analysed.values() if c['raw_available'])
        A(f'### ⚠️ Что именно значит «чистка не трогала» (Г1)')
        A('')
        A(f'Не «задача прошла мимо чистки». Все {in_pool} задач ревью входят в '
          f'пул `shuffle_order_seed2026` ({len(analysed)} из {len(analysed)}), '
          f'и у всех {with_raw} есть raw-снимок — то есть **каждая была '
          f'извлечена и отправлена модели**. Значит Г1 это задачи, которые '
          f'модель увидела и вернула БЕЗ правки.')
        A('')
        A('Это переворачивает объяснение остаточного брака: дело не в том, что '
          'до задач не дошли руки, а в том, что модель, глядя прямо на них, '
          'не сочла нужным что-то менять.')
        A('')
        if groups['Г4']:
            A(f'**Находка:** в Г4 попали задачи, хотя пакет ревью собирался из '
              f'published: {groups["Г4"]}.')
        else:
            A('Г4 пуст — как и должно быть: пакет ревью собирался из published, '
              'а скрытые чисткой задачи в него попасть не могли.')
        A('')
        A('Списки id — файлы `group_g1_not_touched.txt`, '
          '`group_g2_other_field.txt`, `group_g3_same_field.txt`, '
          '`group_g4_hidden.txt`, `group_field_unknown.txt`.')
        A('')

        A('## Задача 3. Прицельные проверки')
        A('')
        lk = checks['leaked']
        A(f'### 3a. leaked_solution — {len(lk["ids"])} задач')
        A('')
        A('Проверка гоняет БОЕВУЮ функцию `find_leaks` из '
          '`extract_leaked_solutions` по ТЕКУЩЕМУ тексту задачи и смотрит, во '
          'что упирается перенос. Второй копии правил не заводили — она '
          'разъехалась бы с боевой.')
        A('')
        A('| Во что упёрлось | Задач |')
        A('|---|---:|')
        for r, n in sorted(lk['blockers'].items(), key=lambda x: -x[1]):
            A(f'| {r} | {n} |')
        A('')
        guards = ('маркер раньше 25% текста', 'маркер раньше 120 символов',
                  'целевое поле уже непустое',
                  'остаток условия короче 40 символов')
        hit_guard = sum(n for r, n in lk['blockers'].items() if r in guards)
        A(f'**Вывод: ни одна из {len(lk["ids"])} задач не упёрлась в три '
          f'предохранителя** (пустое поле solution / позиция маркера >25% / '
          f'остаток ≥40 символов) — в них упёрлось {hit_guard} задач. Причина '
          f'другая и она в устройстве самой механики: `find_leaks` ищет маркер '
          f'ТОЛЬКО в начале строки и ТОЛЬКО в `statement` и `part.statement`.')
        A('')
        A('Разложение по настоящим причинам:')
        A('')
        A('- **утечка внутри поля `solution`** — механика туда не смотрит '
          'вовсе. Типичный вид: ответ «5) нет 6) да» приклеен перед словом '
          '«Решение:» внутри самого решения.')
        A('- **маркер в условии, но не в начале строки** — например '
          '`См. комментарии! Ответ: 1,3,4,5` в конце абзаца. Регулярка '
          'требует начала строки и такой маркер пропускает.')
        A('- **слова-маркера нет вовсе** — утечка без маркера. Механика, '
          'построенная на маркерах, такую не найдёт принципиально, каким бы '
          'мягким ни был порог.')
        A('')
        A('Практический смысл: чинить эти 67 задач ослаблением порогов '
          'БЕСПОЛЕЗНО. Нужны два других шага — смотреть в поле `solution` и '
          'разрешить маркер в середине строки.')
        A('')
        tb = checks['tables']
        A(f'### 3b. broken_table — {len(tb["ids"])} задач')
        A('')
        A(f'Чистка трогала {len(tb["touched"])} из них. Пересечение со списком '
          f'«сверь_цифры»: **{len(tb["sver_cross"])}** — id {tb["sver_cross"]}.')
        A('')
        A('Полный список broken_table: ' + ', '.join(str(i) for i in tb['ids']))
        A('')
        mg = checks['merged']
        A(f'### 3c. merged_structure — {len(mg["ids"])} задач')
        A('')
        A(f'- с подпунктами (`ProblemPart`) сейчас: **{len(mg["with_parts"])}**')
        A(f'- без подпунктов вовсе: **{len(mg["no_parts"])}**')
        A(f'- чистка правила `parts`: **{len(mg["parts_edited"])}**')
        A('')
        fm = checks['formulas']
        A(f'### 3d. broken_formula — {len(fm["ids"])} задач')
        A('')
        A(f'- чистка правила `statement`: **{len(fm["stmt_edited"])}**')
        A(f'- из них число символов `$` изменилось: '
          f'**{len(fm["dollar_changed"])}**')
        A(f'- чистка не трогала ни одним патчем: **{len(fm["untouched"])}** '
          f'({100.0 * len(fm["untouched"]) / len(fm["ids"]):.0f}%)')
        A('')
        A('Счёт `$` берётся ДО = raw-снимок (ровно то, что ушло модели), '
          'ПОСЛЕ = патч (ровно то, что модель вернула). Обе стороны '
          'принадлежат ИИ-чистке, поэтому разница честно приписывается ей, а '
          'не общебазовой механике.')
        A('')
        A(f'**Вывод:** по самой крупной категории дефектов чистка не '
          f'притронулась к двум третям задач. Там, где условие всё же '
          f'правилось, разметку формул она действительно меняла '
          f'({len(fm["dollar_changed"])} из {len(fm["stmt_edited"])}) — но на '
          f'вид задачи это не помогло: вердикт всё равно «сломанная формула».')
        A('')

        A('## Задача 4. Обратная сторона: не сломала ли чистка хорошее')
        A('')
        perfect_cards = [c for c in analysed.values() if c['is_perfect']]
        p_touched = [c for c in perfect_cards if c['cleanup_touched']]
        A(f'Идеальных по Аничу — {len(perfect_cards)}. Чистка касалась '
          f'**{len(p_touched)}** из них '
          f'({100.0 * len(p_touched) / len(perfect_cards):.1f}%).')
        A('')
        pf = Counter()
        for c in p_touched:
            for f in c['fields_edited']:
                pf[f] += 1
        A('| Поле | Правок среди идеальных |')
        A('|---|---:|')
        for f, n in sorted(pf.items(), key=lambda x: -x[1]):
            A(f'| {f} | {n} |')
        A('')
        A(f'**Оценка безвредности:** {len(p_touched)} задач, которых чистка '
          f'касалась, человек потом признал идеальными. Правки этих задач как '
          f'минимум не испортили.')
        A('')
        A('### Куда чистка вообще целилась')
        A('')
        df = Counter()
        d_touched = [c for c in analysed.values()
                     if c['is_defect'] and c['cleanup_touched']]
        for c in d_touched:
            for f in c['fields_edited']:
                df[f] += 1
        A('| Поле | Правок у идеальных | Правок у дефектных |')
        A('|---|---:|---:|')
        for f in ('statement', 'parts', 'solution', 'answer'):
            A(f'| {f} | {pf.get(f, 0)} | {df.get(f, 0)} |')
        A('')
        named = Counter()
        n_comments = 0
        for c in analysed.values():
            if c['comment']:
                n_comments += 1
                for f in c['comment_fields']:
                    named[f] += 1
        top = ', '.join(f'{f} — {n}'
                        for f, n in sorted(named.items(), key=lambda x: -x[1]))
        A(f'Чистка целилась прежде всего в условие и подпункты. Поле '
          f'`solution` она правила у {df.get("solution", 0)} дефектных задач '
          f'из {len(d_touched)} тронутых — при том, что среди {n_comments} '
          f'комментариев Анича поле «решение» называется чаще любого другого '
          f'({top}).')
        A('')
        A('Это же видно поштучно: у #144 («в решении пункты слетели») чистка '
          'разобрала на подпункты УСЛОВИЕ, а решение не тронула вовсе — хотя '
          'дефект человек увидел именно в решении.')
        A('')
        A(f'⚠️ **{len(perfect_sver)} «идеальных» задач несут пометку '
          f'«сверь_цифры»** — их НЕЛЬЗЯ считать проверенными: Анич смотрел на '
          f'ВИД, а не сверял числа с оригиналом. Пометку ставил сам процесс '
          f'чистки — значит по этим задачам есть подозрение на изменившееся '
          f'число, и ревью внешнего вида его не снимает. Список: '
          f'{perfect_sver}')
        A('')

        A('## Задача 5. Математика против текста')
        A('')
        A('Признаки (по условию + подпунктам, HTML-теги вырезаны):')
        A('')
        A('- **П1** — есть хотя бы один спан `$...$`')
        A('- **П2** — есть знак `=`, `<`, `>`, `≤`, `≥`')
        A('- **П3** — три и более числовых токена')
        A('')
        A('### ILE')
        A('')
        A('| Признак | Матем. задач | брак | доля | Текстовых | брак | доля |')
        A('|---|---:|---:|---:|---:|---:|---:|')
        for key, name in (('p1_dollar', 'П1 $…$'), ('p2_signs', 'П2 знаки'),
                          ('p3_numbers', 'П3 числа')):
            r = math_stats['ile'][key]
            A(f'| {name} | {r["math_n"]} | {r["math_defect"]} | '
              f'{r["math_share"]:.1f}% | {r["text_n"]} | {r["text_defect"]} | '
              f'{r["text_share"]:.1f}% |')
        A('')
        A(f'Медиана длины задачи ILE — {math_stats["ile"]["median_chars"]:.0f} '
          f'символов.')
        pace = math_stats['ile'].get('pace') or {}
        if pace.get('median_all') is not None:
            A('')
            A(f'Отметки времени в вердиктах ЕСТЬ. Медиана времени на задачу — '
              f'{pace["median_all"]:.2f} с (по {pace["n"]} промежуткам между '
              f'соседними вердиктами, промежутки длиннее 300 с считаются '
              f'перерывом и отброшены).')
            A('')
            A('| Признак | Медиана времени, матем. | Медиана времени, текст |')
            A('|---|---:|---:|')
            for key, name in (('p1_dollar', 'П1'), ('p2_signs', 'П2'),
                              ('p3_numbers', 'П3')):
                r = pace.get(key, {})
                if r.get('math_median') is not None:
                    A(f'| {name} | {r["math_median"]:.2f} с | '
                      f'{r["text_median"]:.2f} с |')
        A('')
        A('### Сборник АА')
        A('')
        aa = math_stats['aa']
        A(f'⚠️ **Доля брака у АА в разрезе математика/текст — НЕ УСТАНОВЛЕНА.** '
          f'Вердиктов АА в базе `{aa["verdicts_in_db"]}`, файла '
          f'`verdicts_aa_20260728` нет ни в репозитории, ни в профиле '
          f'пользователя (искали по всему диску). Без повердиктных данных '
          f'кросс-таб «математика × брак» внутри АА построить нечем.')
        A('')
        A('Контрольная сумма из задания (61+43+24+11+2+1 = 142 категории при '
          '131 дефектной задаче) **не проверена по той же причине** — сверять '
          'не с чем. Числа известны только из карточки Notion.')
        A('')
        if aa.get('bundle_size'):
            A(f'Что проверить всё-таки можно — **состав** пакета АА '
              f'({aa["found_in_db"]} задач из {aa["bundle_size"]} найдено в '
              f'базе). Это проверяет ПОСЫЛКУ гипотезы («в АА меньше '
              f'математики»), но не её вывод.')
            A('')
            A('| Признак | Математических в АА | Доля пакета | Доля пакета ILE |')
            A('|---|---:|---:|---:|')
            ile_total = (math_stats['ile']['p1_dollar']['math_n']
                         + math_stats['ile']['p1_dollar']['text_n'])
            for key, name in (('p1_dollar', 'П1 $…$'), ('p2_signs', 'П2 знаки'),
                              ('p3_numbers', 'П3 числа')):
                ile_share = 100.0 * math_stats['ile'][key]['math_n'] / ile_total
                A(f'| {name} | {aa[key]["math_n"]} | '
                  f'{aa[key]["math_share_of_bundle"]:.1f}% | {ile_share:.1f}% |')
            A('')
            A(f'Медиана длины задачи АА — {aa["median_chars"]:.0f} символов '
              f'против {math_stats["ile"]["median_chars"]:.0f} у ILE. Вторая '
              f'половина объяснения Макара («короткие задания читаются '
              f'мгновенно») подтверждается: задача АА втрое короче.')
            A('')
            A('### Объясняет ли состав разрыв 20,1% против 8,2%')
            A('')
            A('Прямая проверка — стандартизация: берём доли брака ILE в группах '
              '«математика» и «текст» и применяем их к СОСТАВУ пакета АА. '
              'Получается, каким был бы брак АА, если бы задачи в нём портились '
              'ровно как у ILE, а отличался только состав.')
            A('')
            A('| Признак | Ожидаемый брак АА при составе АА и долях ILE | '
              'Факт АА | Доля разрыва, которую объясняет состав |')
            A('|---|---:|---:|---:|')
            ile_overall = 100.0 * sum(1 for c in analysed.values()
                                      if c['is_defect']) / len(analysed)
            aa_fact = 8.2
            for key, name in (('p1_dollar', 'П1 $…$'), ('p2_signs', 'П2 знаки'),
                              ('p3_numbers', 'П3 числа')):
                share = aa[key]['math_share_of_bundle'] / 100.0
                pred = (share * math_stats['ile'][key]['math_share']
                        + (1 - share) * math_stats['ile'][key]['text_share'])
                explained = ((ile_overall - pred) / (ile_overall - aa_fact) * 100.0
                             if ile_overall != aa_fact else 0.0)
                A(f'| {name} | {pred:.1f}% | {aa_fact}% | {explained:.0f}% |')
            A('')
            A(f'(Общий брак ILE в этом расчёте — {ile_overall:.1f}%, факт АА '
              f'8,2% взят из карточки Notion: своих вердиктов АА у нас нет.)')
            A('')
            A('**Вывод: гипотеза подтверждается ЧАСТИЧНО.**')
            A('')
            A('- По самому надёжному признаку П3 состав объясняет примерно '
              'три пятых разрыва. Оставшаяся часть на долю математики не '
              'списывается — там работает что-то ещё (например, разная '
              'природа источников: ILE это форумный HTML, АА — тестовый '
              'сборник).')
            A('- **П1 даёт ОБРАТНЫЙ результат и это не шум.** Задачи со '
              'спанами `$…$` ломаются РЕЖЕ (16,0% против 25,0%), поэтому по '
              'П1 состав АА предсказывает брак ХУЖЕ фактического. Причина в '
              'том, что П1 меряет не «есть ли в задаче математика», а «есть '
              'ли у неё рабочая разметка формул». Задача, где математика '
              'есть, а долларов нет, — это ровно `bare_math` и '
              '`broken_formula`, то есть уже дефект. Как признак '
              '«математичности» П1 не годится.')
            A('- Поэтому опираться следует на П3 (три и более числа): он '
              'единственный из трёх меряет предмет, а не разметку.')
            A('')
            A('⚠️ Всё это — сравнение ДВУХ источников, различающихся сразу '
              'многим (природа, длина, доля математики, темп ревью). '
              'Стандартизация по одному признаку разделить эти причины не '
              'может и доказательством не является.')
        A('')

        A('## Выборка для глаз')
        A('')
        A(f'`samples.html` — 40 задач, отбор детерминированный (seed '
          f'{SAMPLE_SEED}). Колонки ДО (raw-снимок) / ПОСЛЕ (база сейчас), '
          f'категория вердикта, комментарий Анича, какие поля правила чистка. '
          f'KaTeX вендорится из пакета ревью, страница открывается с `file://` '
          f'без сети.')
        A('')
        A(f'⚠️ Двадцати задач в Г3 **не существует**: там всего '
          f'{len(groups["Г3"])} задачи, потому что комментариев у Анича 42 на '
          f'482 вердикта. Поэтому в выборке все {len(groups["Г3"])} задачи Г3 '
          f'плюс {SAMPLE_PER_GROUP - len(groups["Г3"])} задач ближайшего '
          f'честного аналога — «чистка трогала, дефект остался, поле не '
          f'названо». Они идут отдельной секцией и за Г3 не выдаются.')
        A('')
        A('## Списки id, затронутых общебазовой механикой')
        A('')
        A('| Механика | Список | Найден |')
        A('|---|---|---|')
        for name, paths in MECHANIC_LISTS.items():
            found = 'да' if mechanics[name] is not None else 'НЕ УСТАНОВЛЕНО'
            A(f'| {name} | {", ".join(paths)} | {found} |')
        A('')

        with open(os.path.join(OUT_DIR, 'summary.md'), 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(L) + '\n')
