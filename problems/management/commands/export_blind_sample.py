"""export_blind_sample — собрать СЛЕПУЮ выборку для эксперимента «зрение промпта».

ТОЛЬКО ЧТЕНИЕ. Ни одной записи в базу.

Зачем: прошлая сессия установила, что из 482 дефектных задач ILE чистка не
тронула 332, хотя все они были отправлены модели. То есть модель их читала и
решила, что чинить нечего. Вопрос: лечится ли эта слепота промптом? Проверяем
экспериментом, в котором модель НЕ ПРАВИТ тексты, а только говорит «дефект
есть / дефекта нет». Тестируем зрение, а не руки.

⚠️ ГЛАВНОЕ: команда печатает ТОЛЬКО итоговые числа. Она НИКОГДА не выводит,
какая задача в какой группе, — иначе разметка перестанет быть слепой прямо в
момент сборки выборки. Соответствие «id → группа» уходит в отдельный файл
sample_key.json, который до конца разметки не открывают.

Две группы:
  А — 100 задач: человек пометил ДЕФЕКТНОЙ и чистка её не трогала (группа Г1).
  Б — 30 задач: человек пометил ИДЕАЛЬНОЙ и чистка её тоже не трогала.

Группа Б обязательна: без неё результат нельзя истолковать. Если новый промпт
начнёт находить дефекты и в идеальных задачах, значит он не стал зорче, а стал
шумным, и это провал, а не успех. Б меряет ложные срабатывания.

Запуск:
    venv\\Scripts\\python manage.py export_blind_sample
"""

import json
import os
import random

from django.core.management.base import BaseCommand

from problems.models import Problem, ReviewVerdict

# Правило «чистка трогала задачу» берётся ИЗ КОМАНДЫ ПРОШЛОЙ СЕССИИ — второй
# копией оно разъехалось бы с первой при первой же правке форматов патчей.
from problems.management.commands.verdicts_vs_cleanup import Command as VvcCommand

ILE_BUNDLE = 'ile_20260721'
OUT_DIR = 'reports/blind_experiment'
TRIAGE_FILE = 'reports/ile_triage/recheck_ids.txt'

SEED = 20260818
N_GROUP_A = 100   # человек: дефект, чистка не трогала
N_GROUP_B = 30    # человек: идеально, чистка не трогала


class Command(BaseCommand):
    help = ('Собрать слепую выборку 130 задач ILE для эксперимента о зрении '
            'промпта. Только чтение.')

    def handle(self, *args, **options):
        os.makedirs(OUT_DIR, exist_ok=True)

        # ── вердикты человека (нужны, чтобы построить группы) ─────────────
        verdicts = {}
        for row in (ReviewVerdict.objects.filter(bundle=ILE_BUNDLE)
                    .order_by('problem_id', 'category')
                    .values('problem_id', 'category')):
            verdicts.setdefault(row['problem_id'], set()).add(row['category'])

        # ── семь вердиктов «тест» ────────────────────────────────────────
        # ⚠️ Исключены ТОЛЬКО ради воспроизводимости уже проведённого слепого
        # эксперимента: выборка семенится по отфильтрованному списку, и снятие
        # исключения дало бы ДРУГИЕ 130 задач, а отчёт перестал бы совпадать.
        # Прежнее объяснение «ревьюер пробовал оболочку» ОШИБОЧНО (2026-08-19):
        # «тест» означает тип задачи. На `human_review` эти вердикты влияют.
        test_ids = set()
        if os.path.exists(TRIAGE_FILE):
            with open(TRIAGE_FILE, encoding='utf-8-sig') as fh:
                for line in fh:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        test_ids.add(int(line))

        # ── какие задачи чистка трогала ──────────────────────────────────
        helper = VvcCommand()
        patches, _hide, _sver, _skipped, used_files = helper.load_patches()
        touched = set(patches)

        pool_a, pool_b = [], []
        for pid, cats in verdicts.items():
            if pid in test_ids or pid in touched:
                continue
            if cats == {'perfect'}:
                pool_b.append(pid)
            elif any(c != 'perfect' for c in cats):
                pool_a.append(pid)
        pool_a.sort()
        pool_b.sort()

        rnd = random.Random(SEED)
        picked_a = sorted(rnd.sample(pool_a, min(N_GROUP_A, len(pool_a))))
        picked_b = sorted(rnd.sample(pool_b, min(N_GROUP_B, len(pool_b))))

        combined = [(pid, 'A') for pid in picked_a] + [(pid, 'B') for pid in picked_b]
        rnd.shuffle(combined)

        # ── тексты задач (текущее состояние базы) ────────────────────────
        ids = [pid for pid, _ in combined]
        problems = {p.id: p for p in
                    Problem.objects.filter(id__in=ids).prefetch_related('parts')}

        blind = []
        for pid, _group in combined:
            p = problems.get(pid)
            if p is None:
                continue
            blind.append({
                'id': pid,
                'statement': p.statement or '',
                'parts': [{'label': x.label, 'statement': x.statement or '',
                           'answer': x.answer or ''}
                          for x in p.parts.order_by('order', 'label')],
                'solution': p.solution or '',
                'answer': p.answer or '',
            })

        # ⚠️ В sample_blind.json НЕТ ни вердикта, ни группы, ни порядка групп:
        # список уже перемешан, ключи записи одни и те же у А и Б.
        with open(os.path.join(OUT_DIR, 'sample_blind.json'), 'w',
                  encoding='utf-8') as fh:
            json.dump(blind, fh, ensure_ascii=False, indent=1)

        with open(os.path.join(OUT_DIR, 'sample_key.json'), 'w',
                  encoding='utf-8') as fh:
            json.dump({'seed': SEED,
                       'groups': {str(pid): group for pid, group in
                                  sorted(combined)}},
                      fh, ensure_ascii=False, indent=1)

        # ── контрольные числа (и ТОЛЬКО они) ─────────────────────────────
        out = [
            '=== СЛЕПАЯ ВЫБОРКА ===',
            f'патч-файлов прочитано: {len(used_files)}',
            f'вердиктов ILE: {len(verdicts)}; исключено «тест»: '
            f'{len(test_ids & set(verdicts))}',
            '',
            f'пул А (дефект + чистка не трогала): {len(pool_a)}',
            f'пул Б (идеально + чистка не трогала): {len(pool_b)}',
            '',
            f'взято в А: {len(picked_a)} из {len(pool_a)}',
            f'взято в Б: {len(picked_b)} из {len(pool_b)}',
            f'всего в файле: {len(blind)} (ожидалось {N_GROUP_A + N_GROUP_B})',
            f'seed: {SEED}',
            '',
            'Списки id по группам НЕ печатаются намеренно: разметка слепая.',
        ]
        for line in out:
            try:
                self.stdout.write(line)
            except UnicodeEncodeError:
                self.stdout.write(line.encode('ascii', 'replace').decode())
        with open(os.path.join(OUT_DIR, 'sample_build_log.txt'), 'w',
                  encoding='utf-8') as fh:
            fh.write('\n'.join(out) + '\n')
