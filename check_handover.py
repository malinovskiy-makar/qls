"""Проверка: доехала ли база ровно такой, какой её отправили.

Запускается ЛЮБЫМ Python 3 — никаких библиотек ставить не надо,
Django тоже не нужен. Можно запускать сразу после распаковки.

Windows:  python check_handover.py
Mac:      python3 check_handover.py

Скрипт открывает базу ТОЛЬКО НА ЧТЕНИЕ и ничего в ней не меняет.

Внимание: в тексте намеренно нет значков-стрелок и галочек — в старых
консолях Windows они вызывают ошибку вывода. Только буквы и скобки.
"""

import hashlib
import os
import sqlite3
import sys

# --- Чего мы ждём. Числа взяты из HANDOVER.md, менять их не нужно. ---
EXPECTED = {
    'md5': '7aff67d9eb4a14e68f6ffa74d142c7bd',
    'total': 31694,
    'published': 21271,
    'flagged': 3518,
    'solution': 6662,
    'answer': 5666,
    'parts': 63100,
}
EXPECTED_VERDICTS = {
    'ile_20260721': 2401,
}

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'db.sqlite3')


def human(number):
    """31694 -> '31 694' (пробел между тысячами, так читается легче)."""
    return '{:,}'.format(number).replace(',', ' ')


def main():
    if not os.path.exists(DB):
        print('НЕ НАЙДЕН файл базы: %s' % DB)
        print('')
        print('Положите check_handover.py рядом с db.sqlite3 — в корень')
        print('папки проекта — и запустите ещё раз.')
        return 2

    problems = []

    # --- 1. Отпечаток файла ---
    print('=' * 60)
    print('ПРОВЕРКА ПЕРЕЕЗДА')
    print('=' * 60)
    print('')
    print('Файл базы: %s' % DB)
    print('Размер   : %s байт' % human(os.path.getsize(DB)))
    print('Считаю отпечаток (MD5), это занимает секунд десять...')

    digest = hashlib.md5()
    with open(DB, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    md5 = digest.hexdigest()

    if md5 == EXPECTED['md5']:
        print('MD5      : %s  [СОВПАЛ]' % md5)
    else:
        print('MD5      : %s  [НЕ СОВПАЛ!]' % md5)
        print('           ожидался: %s' % EXPECTED['md5'])
        problems.append('отпечаток файла базы не совпал')

    # --- 2. Числа внутри базы ---
    # mode=ro означает "только чтение" — испортить базу невозможно физически.
    con = sqlite3.connect('file:%s?mode=ro' % DB.replace('\\', '/'), uri=True)
    cur = con.cursor()

    def count(sql):
        cur.execute(sql)
        return cur.fetchone()[0]

    checks = [
        ('Всего задач', 'total',
         "SELECT COUNT(*) FROM problems_problem"),
        ('Со статусом published', 'published',
         "SELECT COUNT(*) FROM problems_problem WHERE status='published'"),
        ('С флагом needs_quality_review', 'flagged',
         "SELECT COUNT(*) FROM problems_problem WHERE needs_quality_review=1"),
        ('С непустым решением', 'solution',
         "SELECT COUNT(*) FROM problems_problem "
         "WHERE solution IS NOT NULL AND TRIM(solution)<>''"),
        ('С непустым ответом', 'answer',
         "SELECT COUNT(*) FROM problems_problem "
         "WHERE answer IS NOT NULL AND TRIM(answer)<>''"),
        ('Подпунктов (ProblemPart)', 'parts',
         "SELECT COUNT(*) FROM problems_problempart"),
    ]

    print('')
    print('-' * 60)
    print('ЧИСЛА В БАЗЕ')
    print('-' * 60)
    for title, key, sql in checks:
        got = count(sql)
        want = EXPECTED[key]
        mark = '[OK]' if got == want else '[!! НЕ СОВПАЛО, ждали %s]' % human(want)
        if got != want:
            problems.append('%s: %s вместо %s' % (title, human(got), human(want)))
        print('%-32s %10s  %s' % (title, human(got), mark))

    # --- 3. Вердикты ручного ревью ---
    print('')
    print('-' * 60)
    print('ВЕРДИКТЫ РУЧНОГО РЕВЬЮ (по пакетам)')
    print('-' * 60)
    cur.execute("SELECT bundle, COUNT(*) FROM problems_reviewverdict "
                "GROUP BY bundle ORDER BY bundle")
    got_verdicts = dict(cur.fetchall())
    if not got_verdicts:
        print('  ни одного вердикта в базе')
        problems.append('вердиктов нет вообще')
    for bundle, number in sorted(got_verdicts.items()):
        want = EXPECTED_VERDICTS.get(bundle)
        if want is None:
            mark = '[лишний пакет, ждали только ile_20260721]'
            problems.append('неожиданный пакет вердиктов: %s' % bundle)
        elif want == number:
            mark = '[OK]'
        else:
            mark = '[!! НЕ СОВПАЛО, ждали %s]' % human(want)
            problems.append('вердиктов %s: %s вместо %s'
                            % (bundle, human(number), human(want)))
        print('%-32s %10s  %s' % (bundle, human(number), mark))

    for bundle, want in EXPECTED_VERDICTS.items():
        if bundle not in got_verdicts:
            print('%-32s %10s  [!! ПАКЕТ ПРОПАЛ]' % (bundle, '0'))
            problems.append('пропал пакет вердиктов %s' % bundle)

    print('')
    print('  Напоминание: пакеты aa_20260728, ap_homeworks_20260728 и')
    print('  matek_20260808 собраны, но ещё НЕ пройдены — вердиктов по ним')
    print('  ноль, и это правильно. Это и есть работа, которая переезжает.')

    con.close()

    # --- Итог ---
    print('')
    print('=' * 60)
    if problems:
        print('ЕСТЬ РАСХОЖДЕНИЯ (%d). ЧИСТКУ НЕ НАЧИНАТЬ.' % len(problems))
        print('Напишите Макару и покажите этот список:')
        for line in problems:
            print('   - %s' % line)
        print('=' * 60)
        return 1

    print('ВСЁ СОШЛОСЬ. База доехала целой, можно работать.')
    print('=' * 60)
    return 0


if __name__ == '__main__':
    sys.exit(main())
