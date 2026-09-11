# -*- coding: utf-8 -*-
"""Проверка результата пробного прогона поимённо, по `dry_run_groups.json`.

Отвечает на вопросы, которые нельзя закрыть сводными числами:
известная НЕ-пара `51615`/`51609` осталась врозь? старая ложная группа из
30 тестовых заданий с общей шапкой рассыпалась? где живут группы из трёх
и более? сколько approved внутри каждой группы?

Только чтение.
"""
import argparse
import io
import json
import sqlite3
import sys
from collections import Counter

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8',
                                  errors='replace')

#: Пара разных задач одного сюжета («три и четыре» против «двух и трёх»),
#: косинус v1 = 0,9885. Числовой гейт обязан держать их врозь.
НЕ_ПАРА = (51615, 51609)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--groups', required=True)
    ap.add_argument('--db', default='db.sqlite3')
    args = ap.parse_args()

    группы = json.load(open(args.groups, encoding='utf-8'))
    членство = {}
    for gid, g in группы.items():
        for pid in g['члены']:
            членство[pid] = gid

    con = sqlite3.connect('file:%s?mode=ro' % args.db.replace('\\', '/'),
                          uri=True)

    a, b = НЕ_ПАРА
    вместе = членство.get(a) and членство.get(a) == членство.get(b)
    print('НЕ-пара %d/%d: %s (группы: %s и %s)'
          % (a, b, 'СКЛЕЕНА — ПЛОХО' if вместе else 'врозь ✔',
             членство.get(a), членство.get(b)))

    # Старая ложная группа content_hash из 30 — берём самый населённый хеш.
    хеши = Counter()
    for (h,) in con.execute("SELECT content_hash FROM problems_problem "
                            "WHERE content_hash <> ''"):
        хеши[h] += 1
    топ_хеш, размер = хеши.most_common(1)[0]
    члены_хеша = [r[0] for r in con.execute(
        "SELECT id FROM problems_problem WHERE content_hash = ?", (топ_хеш,))]
    их_группы = {членство.get(pid) for pid in члены_хеша} - {None}
    самая_большая = max(
        (len(группы[g]['члены']) for g in их_группы), default=0)
    print('Самая большая группа content_hash: %d задач, хеш %s' % (размер, топ_хеш[:12]))
    print('  после гейта они разошлись максимум по группе из %d '
          '(в группах вообще: %d из %d) %s'
          % (самая_большая, sum(1 for p in члены_хеша if p in членство),
             размер, '✔' if самая_большая < размер else '— ПЛОХО'))

    размеры = Counter(len(g['члены']) for g in группы.values())
    print('Размеры групп:', dict(sorted(размеры.items())))
    print('Групп из трёх и более: %d'
          % sum(v for k, v in размеры.items() if k >= 3))

    approved = {r[0] for r in con.execute(
        "SELECT id FROM problems_problem WHERE human_review='approved'")}
    внутри = Counter()
    for g in группы.values():
        внутри[sum(1 for pid in g['члены'] if pid in approved)] += 1
    print('approved внутри группы (штук -> групп):', dict(sorted(внутри.items())))

    правила = Counter(g['правило'] for g in группы.values())
    фаворитов = sum(1 for g in группы.values() if g['фаворит'] is not None)
    print('Правила:', dict(правила))
    print('Групп с назначенным фаворитом: %d' % фаворитов)
    без = [gid for gid, g in группы.items()
           if g['фаворит'] is None
           and g['правило'] in ('approved', 'completeness_margin')]
    print('Уверенных групп БЕЗ фаворита (обязан быть 0): %d' % len(без))
    лишние = [gid for gid, g in группы.items()
              if g['фаворит'] is not None
              and g['правило'] not in ('approved', 'completeness_margin')]
    print('Групп на разбор С фаворитом (обязан быть 0): %d' % len(лишние))

    беднее(con, группы)
    con.close()


def беднее(con, группы):
    """Сколько раз approved-фаворит БЕДНЕЕ своего двойника.

    Правило владельца ставит approved выше полноты намеренно: одобренная
    человеком версия — это решение человека, а полнота — машинная оценка.
    Но владелец должен видеть цену этого правила числом: разведка 11.09
    нашла 858 пар (порог 0,95), где у approved нет ответа, а у двойника есть.
    """
    нужны = {pid for g in группы.values() for pid in g['члены']}
    поля = {}
    for pid, ans, sol, fmt in con.execute(
            "SELECT id, COALESCE(answer,''), COALESCE(solution,''), "
            "content_format FROM problems_problem"):
        if pid in нужны:
            поля[pid] = (ans.strip(), sol.strip(), fmt)
    фигуры = {r[0] for r in con.execute(
        "SELECT DISTINCT problem_id FROM problems_problemfigure")}
    подпункты = {r[0] for r in con.execute(
        "SELECT DISTINCT problem_id FROM problems_problempart")}

    def балл(pid):
        ans, sol, fmt = поля.get(pid, ('', '', 'plain'))
        return (int(pid in подпункты) + int(bool(sol)) + int(pid in фигуры)
                + int(fmt == 'markdown'))

    беднее_полнотой = 0
    без_ответа_у_фаворита = 0
    for g in группы.values():
        if g['правило'] != 'approved' or g['фаворит'] is None:
            continue
        ф = g['фаворит']
        прочие = [p for p in g['члены'] if p != ф]
        if any(балл(p) > балл(ф) for p in прочие):
            беднее_полнотой += 1
        if not поля.get(ф, ('',))[0] and any(поля.get(p, ('',))[0]
                                             for p in прочие):
            без_ответа_у_фаворита += 1
    print('Групп «approved-фаворит беднее двойника по полноте»: %d'
          % беднее_полнотой)
    print('Групп «у approved ответа нет, у двойника есть»: %d'
          % без_ответа_у_фаворита)


if __name__ == '__main__':
    main()
