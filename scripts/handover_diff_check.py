"""Прямое доказательство для двух вопросов Макара.

Сравнивает ТЕКУЩУЮ базу со снимком от 12.08.2026
(backups/db_before_merge_topics_20260813.sqlite3) — он снят ДО передачи
пакета 18.08, поэтому закрывает весь спорный промежуток разом.

Обе базы открываются в режиме ТОЛЬКО ЧТЕНИЕ (mode=ro). Скрипт ничего не пишет.

Почему не хватает updated_at: у Problem это auto_now, он срабатывает только
на model.save(). Команды разметки (human_review_mark, pending_review_gate)
пишут через queryset.update(), который auto_now НЕ трогает. Значит массовая
подмена текста тем же .update() тоже осталась бы невидимой для updated_at,
и косвенным признаком тут обойтись нельзя.
"""
import json
import sqlite3
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CUR = ROOT / 'db.sqlite3'
OLD = ROOT / 'backups' / 'db_before_merge_topics_20260813.sqlite3'
OUT = ROOT / 'reports' / 'handover_back_20260820'
OUT.mkdir(parents=True, exist_ok=True)

sys.stdout.reconfigure(encoding='utf-8')


def ro(path):
    return 'file:{}?mode=ro'.format(str(path).replace('\\', '/'))


con = sqlite3.connect(ro(CUR), uri=True)
con.execute("ATTACH DATABASE ? AS old", (ro(OLD),))
cur = con.cursor()

result = OrderedDict()
result['baseline_snapshot'] = OLD.name
result['baseline_note'] = 'снят 12.08.2026, до передачи пакета 18.08'

# --- сколько строк в обеих --------------------------------------------------
cur.execute('SELECT COUNT(*) FROM main.problems_problem')
now_n = cur.fetchone()[0]
cur.execute('SELECT COUNT(*) FROM old.problems_problem')
old_n = cur.fetchone()[0]
result['problem_count_now'] = now_n
result['problem_count_baseline'] = old_n
result['problems_added_since_baseline'] = now_n - old_n

cur.execute('SELECT COUNT(*) FROM main.problems_problem a '
            'LEFT JOIN old.problems_problem b ON a.id=b.id WHERE b.id IS NULL')
result['problem_ids_only_in_now'] = cur.fetchone()[0]
cur.execute('SELECT COUNT(*) FROM old.problems_problem b '
            'LEFT JOIN main.problems_problem a ON a.id=b.id WHERE a.id IS NULL')
result['problem_ids_only_in_baseline'] = cur.fetchone()[0]

# --- ВОПРОС А: тексты -------------------------------------------------------
text_fields = ['title', 'statement', 'answer', 'solution']
texts = OrderedDict()
for f in text_fields:
    cur.execute(
        'SELECT COUNT(*) FROM main.problems_problem a '
        'JOIN old.problems_problem b ON a.id=b.id '
        'WHERE IFNULL(a.{f},"") <> IFNULL(b.{f},"")'.format(f=f))
    texts['problem.' + f] = cur.fetchone()[0]

cur.execute('SELECT COUNT(*) FROM main.problems_problempart')
result['problempart_count_now'] = cur.fetchone()[0]
cur.execute('SELECT COUNT(*) FROM old.problems_problempart')
result['problempart_count_baseline'] = cur.fetchone()[0]

for f in ['label', 'statement', 'answer', 'solution']:
    cur.execute(
        'SELECT COUNT(*) FROM main.problems_problempart a '
        'JOIN old.problems_problempart b ON a.id=b.id '
        'WHERE IFNULL(a.{f},"") <> IFNULL(b.{f},"")'.format(f=f))
    texts['problempart.' + f] = cur.fetchone()[0]

result['question_a_text_diffs'] = texts
result['question_a_answer'] = ('НЕТ' if sum(texts.values()) == 0
                               and result['problems_added_since_baseline'] == 0
                               else 'ДА — см. числа выше')

# --- ВОПРОС Б: признаки -----------------------------------------------------
flag_fields = ['status', 'needs_quality_review', 'duplicate_of_id']
flags = OrderedDict()
for f in flag_fields:
    cur.execute(
        'SELECT COUNT(*) FROM main.problems_problem a '
        'JOIN old.problems_problem b ON a.id=b.id '
        'WHERE IFNULL(a.{f},-1) <> IFNULL(b.{f},-1)'.format(f=f))
    flags['problem.' + f] = cur.fetchone()[0]

result['question_b_flag_diffs'] = flags
result['question_b_answer'] = 'НЕТ' if sum(flags.values()) == 0 else 'ДА — см. числа выше'

# --- Контроль: что ИЗМЕНИТЬСЯ ДОЛЖНО БЫЛО (разметка 19.08) ------------------
# Если и эти нули — значит сравнение вообще ничего не видит, и первым двум
# ответам грош цена. Это проверка на зубастость самой проверки.
control = OrderedDict()

# Схема: колонок human_review / hidden_pending_review в снимке 12.08 НЕТ вовсе.
# Это отдельное доказательство: миграции 0040+ применены после снимка.
cur.execute('PRAGMA old.table_info(problems_problem)')
old_cols = {r[1] for r in cur.fetchall()}
cur.execute('PRAGMA main.table_info(problems_problem)')
new_cols = {r[1] for r in cur.fetchall()}
control['колонки_добавленные_после_снимка'] = sorted(new_cols - old_cols)
control['колонки_пропавшие_после_снимка'] = sorted(old_cols - new_cols)

# Зубастость: merge_topics (13.08) перевесил темы у 133 задач. Если сравнение
# не видит и этого, значит оно слепо, и первым двум ответам грош цена.
cur.execute('SELECT COUNT(*) FROM ('
            '  SELECT problem_id FROM main.problems_problem_topics'
            '  EXCEPT SELECT problem_id FROM old.problems_problem_topics'
            '  UNION'
            '  SELECT problem_id FROM old.problems_problem_topics'
            '  EXCEPT SELECT problem_id FROM main.problems_problem_topics)')
cur.execute(
    'SELECT COUNT(DISTINCT problem_id) FROM ('
    '  SELECT problem_id, topic_id FROM main.problems_problem_topics'
    '  EXCEPT SELECT problem_id, topic_id FROM old.problems_problem_topics'
    '  UNION ALL'
    '  SELECT problem_id, topic_id FROM old.problems_problem_topics'
    '  EXCEPT SELECT problem_id, topic_id FROM main.problems_problem_topics)')
control['задач_с_изменившимися_темами'] = cur.fetchone()[0]

result['control_expected_to_differ'] = control
sharp = control['задач_с_изменившимися_темами'] > 0 and control['колонки_добавленные_после_снимка']
result['control_verdict'] = ('проверка зубаста: правки после снимка она видит'
                             if sharp
                             else 'ВНИМАНИЕ: проверка слепа, ответам верить нельзя')

# --- Заодно: статусы в обеих базах ------------------------------------------
for tag, db in (('now', 'main'), ('baseline', 'old')):
    cur.execute('SELECT status, COUNT(*) FROM {}.problems_problem '
                'GROUP BY status ORDER BY 2 DESC'.format(db))
    result['status_' + tag] = OrderedDict(cur.fetchall())

con.close()

with open(OUT / 'diff_vs_baseline.json', 'w', encoding='utf-8') as fh:
    json.dump(result, fh, ensure_ascii=False, indent=2)

for k, v in result.items():
    if isinstance(v, dict):
        print(k + ':')
        for kk, vv in v.items():
            print('   {:<34} {}'.format(kk, vv))
    else:
        print('{:<38} {}'.format(k, v))
