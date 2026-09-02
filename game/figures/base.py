u"""Движок сюжетов режима «График»: три шага решения и КАСКАД.

Игроку показывают ЧУЖОЕ решение на графике: размеченные точки,
заштрихованная область и итоговое число. В нём может быть ошибка, и игрок
выбирает ОДИН из четырёх ответов — тот шаг, где решение впервые сломалось.

┌─ ГЛАВНОЕ ПРАВИЛО ВСЕЙ ФИЧИ ────────────────────────────────────────────┐
│ Испорчен РОВНО ОДИН шаг, а всё, что ниже по цепочке, пересчитано ОТ    │
│ ИСПОРЧЕННОГО.                                                          │
│   точки  → область строится ПО ИСПОРЧЕННЫМ точкам, число — от неё;     │
│   область → число считается ОТ ИСПОРЧЕННОЙ области, точки верны;       │
│   число  → точки и область верны, неверно только оно.                  │
│ Иначе на картинке окажется ДВЕ независимые ошибки, и «первый неверный  │
│ шаг» потеряет смысл — вопрос станет без ответа.                        │
└────────────────────────────────────────────────────────────────────────┘

Каскад держится НЕ дисциплиной автора сюжета, а устройством движка: сюжет
описывает три шага отдельными чистыми функциями (`points`, `region`,
`value`), а инжектор портит РОВНО ОДНУ из них. Нижние шаги движок
пересчитывает сам теми же функциями сюжета. Написать сюжет, ломающий
каскад, попросту нечем — если только не менять `params` из инжектора,
и ровно эта диверсия проверяется тестом на зубастость.

⚠️ Рамка чертежа (xmax/ymax) обязана считаться ТОЛЬКО из `params`. Урок
прошлой сессии: архетип строил рамку от решения, и на испорченном решении
оси разъезжались — вариант отличался поломанным рисунком, а не экономикой.
Инвариант «у эталона и у испорченного одна рамка» закреплён тестом-шлюзом.
"""
import json
from fractions import Fraction

# Три шага решения — они же три ответа «где сломалось».
STEP_POINTS = 'points'
STEP_REGION = 'region'
STEP_VALUE = 'value'
STEP_CLEAN = 'clean'
STEPS = (STEP_POINTS, STEP_REGION, STEP_VALUE)

# ⚠️ Порядок вариантов ФИКСИРОВАН и никогда не перемешивается: он и есть
# правильный порядок проверки чужого решения — сначала точки, потом
# область, потом число. Перемешать его значило бы отнять у режима то,
# ради чего он сделан.
ANSWER_OPTIONS = [
    u'Координаты точек',
    u'Заштрихованная область',
    u'Вычисление',
    u'Ошибки нет',
]
ANSWER_INDEX = {STEP_POINTS: 0, STEP_REGION: 1, STEP_VALUE: 2, STEP_CLEAN: 3}

# Формулировка вопроса одна на все сюжеты.
QUESTION_PROMPT = u'Перед тобой чужое решение. Найди ПЕРВЫЙ неверный шаг.'

QUESTION_TYPE = 'figure_audit'

MAX_SAMPLE_ATTEMPTS = 400


class SampleError(Exception):
    u"""Сюжет не собрал «красивый» набор параметров за отведённые попытки."""


class Injector(object):
    u"""Одна типовая ошибка: какой шаг портит и как.

    `apply` получает ВСЁ, что уже посчитано выше по цепочке, и возвращает
    только свой шаг. Нижние шаги пересчитает движок — инжектору их не
    отдают, чтобы он физически не мог сломать каскад.

      step=points → apply(params, points, rng) -> points
      step=region → apply(params, points, region, rng) -> region
      step=value  → apply(params, points, region, value, rng) -> value
    """

    def __init__(self, step, key, title, apply, hint=''):
        assert step in STEPS, step
        self.step = step
        self.key = key
        self.title = title        # как ошибка называется в предпросмотре
        self.apply = apply
        self.hint = hint          # одна фраза для разбора после ответа

    def __repr__(self):
        return '<Injector %s/%s>' % (self.step, self.key)


class Solution(object):
    u"""Три шага чужого решения. Больше в нём ничего нет и быть не должно."""

    __slots__ = ('points', 'region', 'value', 'injected')

    def __init__(self, points, region, value, injected=None):
        self.points = points            # {имя: (x, y)} — порядок значим
        self.region = region            # [(x, y), ...] вершины
        self.value = Fraction(value)    # итоговое число
        self.injected = injected        # ключ шага или None у эталона

    def snapshot(self):
        u"""Сравнимый и печатаемый слепок — им тест-шлюз сверяет шаги."""
        return {
            'points': [[name, str(Fraction(x)), str(Fraction(y))]
                       for name, (x, y) in self.points.items()],
            'region': [[str(Fraction(x)), str(Fraction(y))]
                       for x, y in self.region],
            'value': str(self.value),
        }

    def step_key(self, step):
        return json.dumps(self.snapshot()[step], sort_keys=True)


def shoelace(region):
    u"""Площадь многоугольника по вершинам — точно, на Fraction.

    Модуль от знаковой площади: порядок обхода вершин на площадь влиять не
    должен (рисователь его тоже не различает). Именно эта функция и есть
    «шаг 3» по умолчанию: число берётся из ТОЙ САМОЙ области, которая
    нарисована, — поэтому испорченная область автоматически даёт другое
    число, без единой строчки в сюжете.
    """
    total = Fraction(0)
    n = len(region)
    for i in range(n):
        x1, y1 = region[i]
        x2, y2 = region[(i + 1) % n]
        total += Fraction(x1) * Fraction(y2) - Fraction(x2) * Fraction(y1)
    return abs(total) / 2


class Scenario(object):
    u"""Базовый сюжет. Наследник описывает четыре шага и как это нарисовать."""

    key = ''
    title = ''
    # ⚠️ Сложность задаётся ЯВНО, по экономической глубине сюжета, а НЕ по
    # числу шагов и НЕ по длине текста. Многословность ≠ сложность — урок
    # уже записан в CLAUDE.md на архетипах.
    difficulty = 3
    topics = ()

    # --- шаги решения (обязаны быть ЧИСТЫМИ функциями) ---
    def sample(self, rng):
        raise NotImplementedError

    def points(self, params):
        raise NotImplementedError

    def region(self, params, points):
        raise NotImplementedError

    def value(self, params, points, region):
        u"""По умолчанию число — это площадь нарисованной области."""
        return shoelace(region)

    # --- ошибки, чертёж, тексты ---
    def injectors(self):
        raise NotImplementedError

    def frame(self, params):
        u"""(xmax, ymax) — ТОЛЬКО из params, иначе оси поедут (см. шапку)."""
        raise NotImplementedError

    def draw(self, params, solution):
        raise NotImplementedError

    def statement(self, params):
        raise NotImplementedError

    def explain(self, params, reference, injector):
        raise NotImplementedError

    # --- движок: ниже переопределять НЕЧЕГО ---
    def solve(self, params):
        pts = self.points(params)
        reg = self.region(params, pts)
        return Solution(pts, reg, self.value(params, pts, reg))

    def inject(self, params, injector, rng):
        u"""Решение с испорченным шагом `injector` и ПЕРЕСЧИТАННЫМИ нижними."""
        if injector is None:
            sol = self.solve(params)
            sol.injected = STEP_CLEAN
            return sol
        if injector.step == STEP_POINTS:
            pts = injector.apply(params, self.points(params), rng)
            reg = self.region(params, pts)
            val = self.value(params, pts, reg)
        elif injector.step == STEP_REGION:
            pts = self.points(params)
            reg = injector.apply(params, pts, self.region(params, pts), rng)
            val = self.value(params, pts, reg)
        else:
            pts = self.points(params)
            reg = self.region(params, pts)
            val = injector.apply(params, pts, reg,
                                 self.value(params, pts, reg), rng)
        return Solution(pts, reg, val, injected=injector.step)

    def injectors_by_step(self):
        out = {step: [] for step in STEPS}
        for inj in self.injectors():
            out[inj.step].append(inj)
        return out


def verdict(injector):
    u"""Вторая половина разбора: что именно сломано и почему это ПЕРВЫЙ шаг.

    Текст один на все сюжеты — он объясняет не экономику, а КАСКАД, а каскад
    у всех сюжетов один. Разъехавшись по сюжетам, эти шесть абзацев начали бы
    противоречить друг другу.
    """
    if injector is None:
        return (u'В показанном решении ошибки нет: и точки, и область, '
                u'и число верны.')
    if injector.step == STEP_POINTS:
        return (u'В показанном решении сломан ПЕРВЫЙ шаг, координаты точек: '
                u'%s. Дальше всё построено от них, поэтому и область, и число '
                u'тоже разошлись, но виноват именно первый шаг: %s.'
                % (injector.title, injector.hint))
    if injector.step == STEP_REGION:
        return (u'Точки сняты верно, а вот область нет: %s. Число посчитано '
                u'от неверной области, поэтому первый неверный шаг именно '
                u'она: %s.' % (injector.title, injector.hint))
    return (u'Точки и область верны, ошибка только в вычислении: %s (%s).'
            % (injector.title, injector.hint))


def params_json(params):
    u"""Параметры в JSON: Fraction → строка ('3/2'), остальное как есть.

    Хранить сами Fraction нельзя (JSONField их не примет), а float ронял бы
    точность — а точность здесь и есть весь смысл: числа сравниваются на
    равенство.
    """
    out = {}
    for k, v in params.items():
        if isinstance(v, Fraction):
            out[k] = str(v)
        elif isinstance(v, (list, tuple)):
            out[k] = [str(x) if isinstance(x, Fraction) else x for x in v]
        else:
            out[k] = v
    json.dumps(out, ensure_ascii=False)     # падать здесь, а не при записи
    return out


def pick_injector(scenario, rng, clean_share):
    u"""Что портим в этом экземпляре — или не портим ничего.

    Сначала решаем, будет ли ошибка вообще (доля `clean_share`), и только
    потом — какого она ВИДА, поровну между тремя. Иначе сюжет с четырьмя
    ошибками области и одной ошибкой счёта выдавал бы «область» вчетверо
    чаще, и игрок выучил бы не экономику, а перекос генератора.
    """
    if rng.random() < clean_share:
        return None
    by_step = scenario.injectors_by_step()
    step = rng.choice(list(STEPS))
    pool = by_step.get(step) or []
    if not pool:
        # У всех сюжетов должны быть все три вида (это проверяется тестом).
        pool = [i for i in scenario.injectors()]
        if not pool:
            return None
    return pool[rng.randrange(len(pool))]


def build_question(scenario, rng, clean_share):
    u"""Готовый вопрос режима «График» — словарём, как у генераторов.

    ⚠️ Верный ответ и вид внедрённой ошибки здесь ЕСТЬ, но в payload вопроса
    они не попадают никогда: их кладут в GameQuestion.correct_index и
    gen_params, а выдача (`_question_payload`) отдаёт только показанный
    чертёж и подписи вариантов.
    """
    params = scenario.sample(rng)
    reference = scenario.solve(params)
    injector = pick_injector(scenario, rng, clean_share)
    shown = scenario.inject(params, injector, rng)

    step = injector.step if injector else STEP_CLEAN
    stored = params_json(params)
    stored['_inject'] = injector.key if injector else 'clean'
    stored['_step'] = step

    return {
        'question_type': QUESTION_TYPE,
        'statement': scenario.statement(params),
        'options': list(ANSWER_OPTIONS),
        'correct_index': ANSWER_INDEX[step],
        'correct_value': '',
        'unit': '',
        'figure': scenario.draw(params, shown),
        'figure_ref': scenario.draw(params, reference),
        'solution_text': scenario.explain(params, reference, injector),
        'difficulty': scenario.difficulty,
        'topics': list(scenario.topics),
        'generator_key': scenario.key,
        'params': stored,
    }
