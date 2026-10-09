"""Списки дипломантов → строки index.jsonl. Чистые функции, без Django и сети.

⚠️ ФИО НЕ ХРАНИМ. Сайт отдаёт строку списка с полем `FullName`; сюда оно
не попадает вовсе — запись строится из белого списка полей
(`INDEX_FIELDS`), а не «весь ответ минус имя». Участник = номер работы.
"""
import re

#: Предметы по умолчанию: ключ команды → название вкладки на сайте.
#: Новый предмет добавляется без правки кода: `--subjects law=Право`.
SUBJECTS = {
    'economics': 'Экономика',
    'fingram': 'Финансовая грамотность',
    'business': 'Основы бизнеса',
}

#: Ровно эти поля и только они попадают в строку index.
INDEX_FIELDS = ('work_id', 'subject', 'season', 'grade', 'degree', 'rank',
                'score_before', 'score_after', 'score_after_listed',
                'source_url', 'listed_at')


def parse_subjects(arg):
    """`economics,fingram,law=Право` → [(slug, название на сайте)]."""
    out = []
    for piece in (arg or '').split(','):
        piece = piece.strip()
        if not piece:
            continue
        if '=' in piece:
            slug, name = (p.strip() for p in piece.split('=', 1))
        elif piece in SUBJECTS:
            slug, name = piece, SUBJECTS[piece]
        else:
            raise ValueError('Неизвестный предмет %r: известны %s, или '
                             'задайте как slug=Название' % (piece, ', '.join(SUBJECTS)))
        if not re.fullmatch(r'[a-z0-9_-]+', slug):
            raise ValueError('slug предмета — латиница, цифры, _ и -: %r' % slug)
        out.append((slug, name))
    return out


def season_label(text):
    """«2019/2020 учебный год» → «2019/2020»."""
    m = re.search(r'(\d{4})\s*/\s*(\d{4})', text or '')
    if not m:
        raise ValueError('Не вижу сезон в %r' % text)
    return '%s/%s' % m.groups()


def grade_number(text):
    """«Олимпиада 08 класс» → 8."""
    m = re.search(r'(\d{1,2})\s*класс', text or '')
    if not m:
        raise ValueError('Не вижу класс в %r' % text)
    return int(m.group(1))


def parse_score(text):
    """«74» → 74, «74,5» → 74.5, пусто → None."""
    text = (text or '').strip().replace(',', '.')
    if not text:
        return None
    value = float(text)
    return int(value) if value.is_integer() else value


def winner_record(row, *, rank, subject, season, grade, degree, source_url,
                  listed_at):
    """Строка списка с сайта → запись index. Имя не читается вовсе.

    «Балл после апелляции» сайт показывает как `AddFinalMark`, а если его
    нет — как `AddRoundMark` (так делает schoolwinners.js). Повторяем то
    же и честно помечаем, был ли `AddFinalMark` в списке.
    """
    work_id = (row.get('ID') or '').strip()
    if not work_id.isdigit():
        raise ValueError('У строки списка нет номера работы')
    before = parse_score(row.get('AddRoundMark'))
    final = parse_score(row.get('AddFinalMark'))
    record = {
        'work_id': work_id,
        'subject': subject,
        'season': season,
        'grade': grade,
        'degree': degree,
        'rank': rank,
        'score_before': before,
        'score_after': final if final is not None else before,
        'score_after_listed': final is not None,
        'source_url': source_url,
        'listed_at': listed_at,
    }
    return {k: record[k] for k in INDEX_FIELDS}


def check_index(records, expected_total=None):
    """Инварианты Фазы 2. Нарушения — список строк, а не падение."""
    problems = []
    ids = [r['work_id'] for r in records]
    dup = len(ids) - len(set(ids))
    if dup:
        problems.append('повторов work_id: %d' % dup)
    if expected_total is not None and expected_total != len(records):
        problems.append('строк %d, а по таблице объёма %d' % (len(records), expected_total))
    no_score = [r['work_id'] for r in records
                if r['score_before'] is None or r['score_after'] is None]
    if no_score:
        problems.append('без балла до/после: %d (%s)' % (len(no_score), ', '.join(no_score[:10])))
    lower = [r['work_id'] for r in records
             if r['score_before'] is not None and r['score_after'] is not None
             and r['score_after'] < r['score_before']]
    return {'rows': len(records), 'duplicates': dup, 'no_score': len(no_score),
            'after_lower': lower, 'problems': problems}
