"""
Статистика по вопросам Econ Rush: сколько раз показан, как отвечали,
сколько думали.

Зачем: у большинства тестов в банке поле difficulty пусто, и сложность в
пуле — эвристика по длине и числу шагов. Живая доля верных ответов знает о
сложности больше любой эвристики; заодно она вылавливает сломанные вопросы
(доля близка к нулю — почти наверняка не тот ключ ответа или потерялась
формула) и тривиальные (доля близка к единице — вопрос только разбавляет
пул).

Три правила, из которых всё остальное следует:

1. **Статистика не живёт на GameQuestion.** Пул — кэш, `build_game_pool`
   сносит его целиком и создаёт заново с новыми id. Ключ статистики —
   устойчивая сущность: `Problem` (+ `ProblemPart`) для банка,
   строка-ключ архетипа для сгенерированных.
2. **Считаем только ПЕРВУЮ встречу вопроса игроком.** Второй раз тот же
   человек отвечает уже зная ответ; складывать это с чужими первыми
   ответами — портить выборку. Флаг первой встречи ставится при ВЫДАЧЕ
   вопроса (сверяясь со списком виданных между забегами) и лежит в
   состоянии забега.
3. **Доля верных считается от попыток** (correct + wrong). Пропуск идёт в
   свой счётчик и долю не портит — тот же принцип, что в `build_summary`.
"""
from typing import Optional

from django.db import transaction
from django.db.models import F

from . import config
from .models import ArchetypeStat, BankQuestionStat


def _bank_key(gq):
    """(problem_id, part_id) вопроса банка или None, если это не банк."""
    if gq.is_generated or gq.problem_id is None:
        return None
    return gq.problem_id, gq.part_id


def get_stat(gq):
    """Строка статистики вопроса — или None, если её ещё нет.

    Ничего не создаёт: читающие поверхности (карточка ответа, каталог,
    выбор вопроса) не должны плодить пустые строки на каждый показ.
    """
    key = _bank_key(gq)
    if key is not None:
        return BankQuestionStat.objects.filter(
            problem_id=key[0], part_id=key[1]).first()
    if gq.generator_key:
        return ArchetypeStat.objects.filter(
            generator_key=gq.generator_key).first()
    return None


def record_answer(gq, outcome, elapsed_ms=0):
    """Учесть один сыгранный вопрос. Возвращает обновлённую строку (или None).

    Вызывается РОВНО в той же точке, где дописывается журнал забега, и в
    той же транзакции: журнал и счётчики обязаны рассказывать одно и то же.
    Инкременты — через F(), чтобы параллельные забеги не затирали друг
    друга (read-modify-write потерял бы ответы).

    outcome: 'correct' | 'wrong' | 'skip'.
    """
    if outcome not in ('correct', 'wrong', 'skip'):
        return None
    elapsed_ms = max(0, int(elapsed_ms or 0))

    key = _bank_key(gq)
    if key is not None:
        model, lookup = BankQuestionStat, {'problem_id': key[0],
                                           'part_id': key[1]}
    elif gq.generator_key:
        model, lookup = ArchetypeStat, {'generator_key': gq.generator_key}
    else:
        return None   # сгенерированный вопрос без ключа архетипа — считать нечего

    field = {'correct': 'correct', 'wrong': 'wrong', 'skip': 'skipped'}[outcome]
    with transaction.atomic():
        model.objects.get_or_create(**lookup)
        model.objects.filter(**lookup).update(
            shown=F('shown') + 1,
            total_ms=F('total_ms') + elapsed_ms,
            **{field: F(field) + 1})
    return model.objects.filter(**lookup).first()


# Разделитель ключа «сюжет | вид внедрённой ошибки». Вертикальная черта в
# ключах сюжетов и архетипов не встречается, поэтому разбор ключа обратим.
VARIANT_SEP = '|'


def variant_key(gq):
    u"""Ключ статистики «сюжет + вид внедрённой ошибки» или None.

    Только для режима «График»: у его вопросов параметры каждый раз новые,
    зато вид ошибки — устойчивая величина, и знать, какая из них чаще
    обманывает игроков, полезнее, чем средняя доля по сюжету.
    """
    if not gq.generator_key or gq.question_type != 'figure_audit':
        return None
    inject = (gq.gen_params or {}).get('_inject')
    if not inject:
        return None
    return '%s%s%s' % (gq.generator_key, VARIANT_SEP, inject)


def record_variant(gq, outcome, elapsed_ms=0):
    u"""Второй счётчик — по виду внедрённой ошибки. Первый (по сюжету)
    ставит `record_answer`, и его трогать нельзя: на нём стоит измеренная
    сложность, а она обязана считаться по сюжету целиком."""
    key = variant_key(gq)
    if key is None or outcome not in ('correct', 'wrong', 'skip'):
        return None
    field = {'correct': 'correct', 'wrong': 'wrong', 'skip': 'skipped'}[outcome]
    lookup = {'generator_key': key}
    with transaction.atomic():
        ArchetypeStat.objects.get_or_create(**lookup)
        ArchetypeStat.objects.filter(**lookup).update(
            shown=F('shown') + 1,
            total_ms=F('total_ms') + max(0, int(elapsed_ms or 0)),
            **{field: F(field) + 1})
    return ArchetypeStat.objects.filter(**lookup).first()


def public_stat(stat):
    """Что можно показать человеку: {'p_correct': 0.53, 'attempts': 1240}.

    None, если попыток меньше порога — процент на пяти ответах врёт, и
    честнее не показывать ничего, чем показывать шум.
    """
    if stat is None:
        return None
    attempts = stat.attempts
    if attempts < config.STATS_MIN_ATTEMPTS:
        return None
    return {'p_correct': round(stat.correct / attempts, 4),
            'attempts': attempts}


def measured_difficulty(p_correct):
    # type: (float) -> int
    """Доля верных → сложность 1–5 по шкале из config.MEASURED_DIFFICULTY_SCALE."""
    for lo, level in config.MEASURED_DIFFICULTY_SCALE:
        if p_correct >= lo:
            return level
    return 5


def effective_difficulty(gq, stat=None):
    # type: (object, Optional[object]) -> int
    """Сложность вопроса: ИЗМЕРЕННАЯ, если попыток хватает, иначе хранимая
    эвристика `GameQuestion.difficulty`.

    Единственный вход в «сложность» для всей остальной игры (эскалация,
    служебная страница, будущие очки по сложности). Сегодня почти везде
    вернёт эвристику — данных ещё нет; завтра, когда наберутся попытки,
    та же функция начнёт возвращать измеренное, и переписывать вызывающий
    код не придётся.

    stat можно передать заранее прочитанным — чтобы не ходить в базу по
    строке на каждый вопрос при массовом расчёте.
    """
    if stat is None:
        stat = get_stat(gq)
    pub = public_stat(stat)
    if pub is None:
        return gq.difficulty
    return measured_difficulty(pub['p_correct'])


def difficulty_overrides():
    """Карты измеренной сложности для быстрой фильтрации пула.

    Возвращает (bank, arch): {(problem_id, part_id): 1..5} и
    {generator_key: 1..5} — только для вопросов, где попыток набралось
    достаточно. Два запроса вместо запроса на вопрос: выбор очередного
    вопроса читает пул плоским списком и не может позволить себе N+1.
    """
    thr = config.STATS_MIN_ATTEMPTS
    bank, arch = {}, {}
    rows = (BankQuestionStat.objects
            .annotate(att=F('correct') + F('wrong'))
            .filter(att__gte=thr)
            .values_list('problem_id', 'part_id', 'correct', 'att'))
    for problem_id, part_id, correct, att in rows:
        bank[(problem_id, part_id)] = measured_difficulty(correct / att)
    rows = (ArchetypeStat.objects
            .annotate(att=F('correct') + F('wrong'))
            .filter(att__gte=thr)
            .values_list('generator_key', 'correct', 'att'))
    for key, correct, att in rows:
        arch[key] = measured_difficulty(correct / att)
    return bank, arch


def bulk_stats(questions):
    """Словарь id вопроса → строка статистики. Один запрос на банк и один
    на архетипы вместо запроса на вопрос: служебная страница показывает
    тысячи строк разом."""
    bank_keys = {}
    arch_keys = {}
    for gq in questions:
        key = _bank_key(gq)
        if key is not None:
            bank_keys.setdefault(key, []).append(gq.id)
        elif gq.generator_key:
            arch_keys.setdefault(gq.generator_key, []).append(gq.id)

    out = {}
    if bank_keys:
        problem_ids = {k[0] for k in bank_keys}
        for st in BankQuestionStat.objects.filter(problem_id__in=problem_ids):
            for qid in bank_keys.get((st.problem_id, st.part_id), []):
                out[qid] = st
    if arch_keys:
        for st in ArchetypeStat.objects.filter(
                generator_key__in=list(arch_keys)):
            for qid in arch_keys.get(st.generator_key, []):
                out[qid] = st
    return out


def problem_stat_summary(problem_id):
    """Сводная статистика задачи для страницы каталога.

    Задача может дать несколько игровых вопросов (подпункты) — складываем
    их: читателю каталога интересна задача целиком, а не то, на какой
    подпункт пришлось больше попыток.

    None, если попыток меньше порога.
    """
    rows = list(BankQuestionStat.objects.filter(problem_id=problem_id))
    if not rows:
        return None
    correct = sum(r.correct for r in rows)
    attempts = sum(r.attempts for r in rows)
    if attempts < config.STATS_MIN_ATTEMPTS:
        return None
    return {'percent': round(100 * correct / attempts),
            'attempts': attempts}
