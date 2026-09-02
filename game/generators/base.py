"""
Движок параметрических генераторов вопросов Econ Rush («архетипов»).

Принцип «обратного хода»: сначала сэмплируется КРАСИВЫЙ ответ (целое или
простая дробь) и опорные величины из красивых сеток, затем коэффициенты
условия вычисляются обратным ходом — ответ верен по построению, вся
математика точная (fractions.Fraction), никакого ИИ и никаких float.

Каждый архетип (файл в game/generators/) реализует ТОЛЬКО экономику:
  sample(rng)  -> params            — обратный ход от красивого ответа;
  solve(params) -> dict Fraction'ов — промежуточные и итоговые величины;
  asked_values(params) -> [Asked]   — какие величины можно спрашивать;
  error_variants(params, solved, asked) -> [Fraction] — ВЫЧИСЛЕННЫЕ
      типовые ошибки (дистракторы не выдумываются);
  wrappers() -> [Wrapper]           — сюжетные обёртки (полная форма для
      numeric ≤700 симв., краткая для single/boolean ≤300);
  solution(params, solved, asked) -> [str] — шаги решения (KaTeX).

Преобразования типов — ЗДЕСЬ ОДИН РАЗ (generate_question):
  numeric — «найдите X», correct_value (целое / десятичная / дробь a/b);
  single  — правильный + 3 случайных дистрактора из error_variants;
  boolean — «верно ли, что X равен V», V = ответ или дистрактор (50/50).

params обязаны быть JSON-сериализуемыми (int / str) — они пишутся в
GameQuestion.gen_params, и тесты пересчитывают ответ заново через solve().
"""
import json
from fractions import Fraction
from typing import Any, Callable, Dict, List, Optional

# «Красивый» ответ: целое, либо дробь со знаменателем ≤ 10
# (десятичная с одним знаком — частный случай: знаменатель 2, 5, 10).
NICE_MAX_DENOMINATOR = 10

LIMIT_FULL = 700    # лимит условия numeric (Классика) — как в build_game_pool
LIMIT_SHORT = 300   # лимит условия single/boolean (Блиц/Пуля)

MAX_SAMPLE_ATTEMPTS = 300   # лимит пересэмплирований на один вопрос
MIN_DISTRACTORS = 3         # меньше трёх красивых дистракторов → пересэмплировать


class GenerationError(Exception):
    """Не удалось собрать валидный вопрос за MAX_SAMPLE_ATTEMPTS попыток."""


def F(v):
    """Приводит значение params (int или строка '1/2', '0,5') к Fraction."""
    if isinstance(v, Fraction):
        return v
    return Fraction(str(v).replace(',', '.'))


def is_nice(x):
    """Красивое число: целое или дробь со знаменателем ≤ NICE_MAX_DENOMINATOR."""
    return Fraction(x).denominator <= NICE_MAX_DENOMINATOR


def fmt_num(x, latex=False):
    """Fraction → строка в русской записи.

    Целое → '50'; конечная десятичная с ≤2 знаками → '0,5' (в LaTeX '0{,}5' —
    иначе KaTeX ставит пробел после запятой); прочее → 'a/b' (в LaTeX \\frac).
    Этой же функцией формируется correct_value — parse_exact_number
    (game/views.py) понимает все три формы."""
    x = Fraction(x)
    sign = '-' if x < 0 else ''
    ax = abs(x)
    if ax.denominator == 1:
        return sign + str(ax.numerator)
    for digits in (1, 2):
        mult = 10 ** digits
        scaled = ax * mult
        if scaled.denominator == 1:
            ip, fp = divmod(scaled.numerator, mult)
            comma = '{,}' if latex else ','
            return '{}{}{}{}'.format(sign, ip, comma, str(fp).rjust(digits, '0'))
    if latex:
        return '{}\\frac{{{}}}{{{}}}'.format(sign, ax.numerator, ax.denominator)
    return '{}{}/{}'.format(sign, ax.numerator, ax.denominator)


def fmt_coef(x):
    """Коэффициент при переменной в формуле: 1 → '', 0,5 → '0{,}5', 2 → '2'."""
    ax = abs(Fraction(x))
    return '' if ax == 1 else fmt_num(ax, latex=True)


def linear_rhs(intercept, coef, var='P'):
    """Правая часть 'a + b·var' с чисткой нулей и единиц: '100 - 2P', 'P'."""
    a, b = Fraction(intercept), Fraction(coef)
    parts = ''
    if a != 0 or b == 0:
        parts = fmt_num(a, latex=True)
    if b != 0:
        term = fmt_coef(b) + var
        if parts:
            parts += (' + ' if b > 0 else ' - ') + term
        else:
            parts = ('-' if b < 0 else '') + term
    return parts


def linear_eq(head, intercept, coef, var='P'):
    """'$Q_d = 100 - 2P$' — готовая инлайн-формула с долларами.
    coef может быть отрицательным (спрос)."""
    return '${} = {}$'.format(head, linear_rhs(intercept, coef, var))


class Asked(object):
    """Величина, которую можно спросить у игрока.

    kind='value' — числовая: nom/acc/gender для грамматики вопроса, unit —
    единица ответа («ден. ед.», «шт.», «%», '' — безразмерная).
    kind='class' — качественная (классификация): question — готовый вопрос
    для single, claim_tpl — шаблон утверждения для boolean с {V},
    class_options — метки вариантов; solved[key] обязан быть одной из меток.
    trivial=True — одношаговое «считывание» (сложность 1, а не 2).
    difficulty=N — сложность 1–5 ЯВНО, по экономической глубине вопроса.
    Без неё сложность выводится из числа шагов решения (старое поведение),
    а это неверно для развёрнутых решений: подробный разбор «почему так»
    длиннее не потому, что задача труднее. Многословность ≠ сложность."""

    def __init__(self, key, nom='', acc='', gender='f', unit='',
                 kind='value', question='', claim_tpl='', class_options=None,
                 trivial=False, max_value=None, difficulty=None):
        self.key = key
        self.nom = nom
        self.acc = acc
        self.gender = gender
        self.unit = unit
        self.kind = kind
        self.question = question
        self.claim_tpl = claim_tpl
        self.class_options = class_options or []
        self.trivial = trivial
        self.max_value = max_value  # потолок правдоподобия дистракторов (доля ≤ 100 %)
        self.difficulty = difficulty


class Wrapper(object):
    """Сюжетная обёртка: full(params, solved) — развёрнутая декорация + данные
    (для numeric), short(params, solved) — сжатая (для single/boolean).
    Обе возвращают ТОЛЬКО завязку и данные; вопрос дописывает движок."""

    def __init__(self, key, full, short):
        self.key = key
        self.full = full
        self.short = short


class Archetype(object):
    """Базовый класс архетипа. Подклассы задают key/title/block/topics
    и реализуют пять методов (см. докстринг модуля)."""

    key = ''
    title = ''
    block = ''
    topics = []  # КАНОНИЧЕСКИЕ названия тем (apply_topic_mapping)

    def sample(self, rng):
        raise NotImplementedError

    def solve(self, params):
        raise NotImplementedError

    def asked_values(self, params):
        raise NotImplementedError

    def error_variants(self, params, solved, asked):
        raise NotImplementedError

    def wrappers(self):
        raise NotImplementedError

    def solution(self, params, solved, asked):
        raise NotImplementedError

    def figure(self, params, solved, asked):
        """Чертёж к задаче — dict по схеме _figure.py или None.

        Необязателен: график есть только у графических архетипов (монополия,
        равновесие, налог/субсидия, КПВ). Показывается в РАЗБОРЕ ошибок, не
        в карточке во время забега — на скорость забега он не влияет."""
        return None


# ---------------------------------------------------------------------------
# Грамматика вопросительных предложений
# ---------------------------------------------------------------------------

_RAVN = {'m': u'равен', 'f': u'равна', 'n': u'равно', 'p': u'равны'}

# Зачины в манере ВсОШ-региона (reports/generators/style_notes.md §2).
_NUMERIC_TPLS = [
    u'Найдите {acc}{unit_p}.',
    u'Определите {acc}{unit_p}.',
    u'Чему {ravn} {nom}{unit_p}?',
]


def _unit_paren(unit):
    return u' (в {})'.format(unit) if unit else ''


def _question_sentence(rng, asked):
    """Вопросительное предложение для value-вопроса (numeric и single).
    Если у Asked задан собственный question — он главнее шаблонов
    (нужно для вопросов об изменениях: «На сколько … вырастет цена?»)."""
    if asked.question:
        return asked.question
    tpl = rng.choice(_NUMERIC_TPLS)
    return tpl.format(acc=asked.acc, nom=asked.nom,
                      ravn=_RAVN[asked.gender], unit_p=_unit_paren(asked.unit))


def _claim_sentence(asked, value_str):
    """Утверждение для boolean-вопроса типа value: «верно ли, что X равен V».
    Если задан claim_tpl — берём его (с подстановкой {V})."""
    if asked.claim_tpl:
        return u'Верно ли, что {}?'.format(asked.claim_tpl.format(V=value_str))
    unit_sfx = u' {}'.format(asked.unit) if asked.unit else ''
    return u'Верно ли, что {} {} {}{}?'.format(
        asked.nom, _RAVN[asked.gender], value_str, unit_sfx)


# ---------------------------------------------------------------------------
# Дистракторы
# ---------------------------------------------------------------------------

def _clean_distractors(errors, answer, max_value=None):
    """Фильтр вычисленных ошибок: уникальны, ≠ ответу, красивы,
    правдоподобны (строго положительны — ноль как вариант ответа выглядит
    подсказкой «не тот»; не выше max_value, если задан). Порядок сохраняется."""
    out = []
    seen = {Fraction(answer)}
    for e in errors:
        e = Fraction(e)
        if e in seen:
            continue
        if e <= 0:
            continue
        if max_value is not None and e > max_value:
            continue
        if not is_nice(e):
            continue
        seen.add(e)
        out.append(e)
    return out


# ---------------------------------------------------------------------------
# Сложность из числа шагов решения
# ---------------------------------------------------------------------------

def _difficulty(n_steps, trivial):
    """1 шаг → 1–2 (1 только для тривиального считывания), 2 → 3, 3 → 4, 4+ → 5."""
    if n_steps <= 1:
        return 1 if trivial else 2
    return {2: 3, 3: 4}.get(n_steps, 5)


def _numbered(steps):
    return '\n'.join(u'{}. {}'.format(i + 1, s) for i, s in enumerate(steps))


# ---------------------------------------------------------------------------
# Сборка вопроса (преобразование типов — только здесь)
# ---------------------------------------------------------------------------

def generate_question(arch, rng, question_type):
    """Собирает один GeneratedQuestion (dict) типа question_type.

    Пересэмплирует параметры, пока ответ не красив, дистракторов не меньше
    трёх и условие не влезает в лимит длины. Все проверки валидности
    экономики — внутри sample()/solve() архетипа."""
    assert question_type in ('numeric', 'single', 'boolean')
    limit = LIMIT_FULL if question_type == 'numeric' else LIMIT_SHORT

    for _ in range(MAX_SAMPLE_ATTEMPTS):
        params = arch.sample(rng)
        solved = arch.solve(params)

        candidates = []
        for a in arch.asked_values(params):
            if a.kind == 'value':
                if is_nice(solved[a.key]):
                    candidates.append(a)
            elif question_type != 'numeric':
                candidates.append(a)  # class-вопросы не бывают числовыми
        if not candidates:
            continue
        asked = rng.choice(candidates)

        # --- содержимое по типу ---
        options = []
        correct_index = None
        correct_value = ''
        unit = ''
        claim_value = None

        if asked.kind == 'class':
            labels = list(asked.class_options)
            correct_label = solved[asked.key]
            if question_type == 'single':
                # ⚠️ Тасуем, как и числовые варианты: без этого правильный
                # ответ стоит там, куда его поставило объявление
                # class_options, и запоминается позицией, а не смыслом.
                rng.shuffle(labels)
                options = labels
                correct_index = labels.index(correct_label)
                q_sentence = asked.question
            else:  # boolean
                if rng.random() < 0.5:
                    shown = correct_label
                else:
                    shown = rng.choice([l for l in labels if l != correct_label])
                claim_value = shown
                options = [u'Верно', u'Неверно']
                correct_index = 0 if shown == correct_label else 1
                q_sentence = u'Верно ли, что {}?'.format(
                    asked.claim_tpl.format(V=shown))
        else:
            answer = Fraction(solved[asked.key])
            distractors = _clean_distractors(
                arch.error_variants(params, solved, asked), answer,
                max_value=asked.max_value)
            if question_type != 'numeric' and len(distractors) < MIN_DISTRACTORS:
                continue  # мало красивых дистракторов — пересэмплировать

            if question_type == 'numeric':
                correct_value = fmt_num(answer)
                unit = asked.unit
                q_sentence = _question_sentence(rng, asked)
            elif question_type == 'single':
                chosen = rng.sample(distractors, MIN_DISTRACTORS)
                values = chosen + [answer]
                rng.shuffle(values)
                options = [fmt_num(v) for v in values]
                correct_index = values.index(answer)
                q_sentence = _question_sentence(rng, asked)
            else:  # boolean
                if rng.random() < 0.5:
                    shown = answer
                else:
                    shown = rng.choice(distractors)
                claim_value = fmt_num(shown)
                options = [u'Верно', u'Неверно']
                correct_index = 0 if shown == answer else 1
                q_sentence = _claim_sentence(asked, fmt_num(shown))

        # --- обёртка и лимит длины ---
        wrappers = list(arch.wrappers())
        rng.shuffle(wrappers)
        statement = None
        used_wrapper = None
        for w in wrappers:
            setup = w.full(params, solved) if question_type == 'numeric' \
                else w.short(params, solved)
            text = setup.strip() + ' ' + q_sentence
            if len(text) <= limit:
                statement = text
                used_wrapper = w
                break
        if statement is None:
            continue  # ни одна обёртка не влезла — пересэмплировать

        steps = arch.solution(params, solved, asked)
        gen_params = dict(params)
        gen_params['_asked'] = asked.key
        gen_params['_wrapper'] = used_wrapper.key
        if claim_value is not None:
            gen_params['_claim'] = str(claim_value)
        json.dumps(gen_params)  # гарантия JSON-сериализуемости (упадёт тут, не в БД)

        # Сложность: явная у Asked (экономическая глубина), иначе — старая
        # оценка по числу шагов. Развёрнутое решение НЕ делает вопрос труднее.
        difficulty = asked.difficulty if asked.difficulty is not None \
            else _difficulty(len(steps), asked.trivial)

        # График — только к развёрнутому numeric: его смотрят в разборе,
        # где есть место. У Блица/Пули карточка короткая, чертёж там лишний.
        figure = arch.figure(params, solved, asked) \
            if question_type == 'numeric' else None

        return {
            'question_type': question_type,
            'statement': statement,
            'options': options,
            'correct_index': correct_index,
            'correct_value': correct_value,
            'unit': unit,
            'solution_text': _numbered(steps),
            'difficulty': difficulty,
            'topics': list(arch.topics),
            'generator_key': arch.key,
            'params': gen_params,
            'figure': figure,
        }

    raise GenerationError(
        u'{}: не собрался валидный {} за {} попыток'.format(
            arch.key, question_type, MAX_SAMPLE_ATTEMPTS))


# ---------------------------------------------------------------------------
# Режим «График»: выбор верного чертежа из четырёх
# ---------------------------------------------------------------------------

FIGURE_CHOICE_OPTIONS = 4     # один верный + три неверных


def _figure_axes(fig):
    return Fraction(str(fig['xmax'])), Fraction(str(fig['ymax']))


def _spoil_figure(fig, v_true, v_err):
    """Чертёж, на котором ИСКОМАЯ величина отмечена НЕВЕРНО.

    Кривые, оси и заливки остаются как есть — двигаются только точки,
    засечки и пунктирные выноски, стоявшие на верном значении.

    ⚠️ Почему не «пересчитать figure() на испорченном solved»: архетип
    строит рамку от решения (axis_max(q_star·2)) и обрезает кривые по ней
    (clip_linear). Испорченное значение меняет рамку, и после подгонки к
    общей от кривых остаются обрубки — вариант отличается не экономикой,
    а поломанным рисунком. Ровно это и вышло на первом прогоне (видно на
    скриншоте p7 первой версии). Здесь же меняется только то, что игрок
    и должен сравнивать: где отмечен оптимум.

    Возвращает None, если ничего не сдвинулось (вариант неотличим) или
    неверное значение вышло за рамку чертежа.
    """
    xmax, ymax = Fraction(str(fig['xmax'])), Fraction(str(fig['ymax']))
    if not (0 < v_err <= max(xmax, ymax)):
        return None
    import copy
    out = copy.deepcopy(fig)
    changed = [False]

    def swap(value, limit):
        if Fraction(str(value)) != v_true:
            return value
        if v_err > limit:
            return value
        changed[0] = True
        f = Fraction(v_err)
        return int(f) if f.denominator == 1 else round(float(f), 6)

    for p in out.get('points', []):
        p['x'] = swap(p['x'], xmax)
        p['y'] = swap(p['y'], ymax)
    for mk in out.get('marks', []):
        mk['at'] = swap(mk['at'], xmax if mk['axis'] == 'x' else ymax)
    for ln in out.get('lines', []):
        if not ln.get('dash'):
            continue          # сплошные — это сами кривые, их не трогаем
        ln['from'] = [swap(ln['from'][0], xmax), swap(ln['from'][1], ymax)]
        ln['to'] = [swap(ln['to'][0], xmax), swap(ln['to'][1], ymax)]
    return out if changed[0] else None


def generate_figure_choice(arch, rng):
    """Вопрос режима «График»: четыре чертежа, верен ровно один.

    Неверные варианты — НЕ выдуманные картинки: это чертёж того же
    архетипа, посчитанный на его ТИПОВОЙ ОШИБКЕ (error_variants уже умеет
    их вычислять для дистракторов). Налог сдвинул не ту кривую, оптимум
    отмечен не там — ошибка настоящая, экономическая, а новой математики
    писать не пришлось.

    Архетип без чертежа сюда не попадает (figure() вернёт None →
    пересэмплирование → GenerationError).
    """
    for _ in range(MAX_SAMPLE_ATTEMPTS):
        params = arch.sample(rng)
        solved = arch.solve(params)

        candidates = [a for a in arch.asked_values(params)
                      if a.kind == 'value' and is_nice(solved[a.key])]
        if not candidates:
            continue
        asked = rng.choice(candidates)

        correct = arch.figure(params, solved, asked)
        if not correct:
            continue

        answer = Fraction(solved[asked.key])
        errors = _clean_distractors(
            arch.error_variants(params, solved, asked), answer,
            max_value=asked.max_value)
        answer_f = Fraction(solved[asked.key])
        variants, seen = [], {json.dumps(correct, sort_keys=True)}
        for err in errors:
            # Ошибка обязана быть ЦЕЛЫМ числом: её значение попадает
            # засечкой на ось чертежа, и «86,6666» там налезает на соседей.
            if Fraction(err).denominator != 1:
                continue
            fig = _spoil_figure(correct, answer_f, Fraction(err))
            if not fig:
                continue
            key = json.dumps(fig, sort_keys=True)
            if key in seen:     # чертёж не отличается от верного — не вариант
                continue
            seen.add(key)
            variants.append(fig)
            if len(variants) >= FIGURE_CHOICE_OPTIONS - 1:
                break
        if len(variants) < FIGURE_CHOICE_OPTIONS - 1:
            continue            # меньше трёх дистракторов — пересэмплировать

        figs = [correct] + variants
        correct_fig = correct
        options = list(figs)
        rng.shuffle(options)
        correct_index = options.index(correct_fig)

        # Короткий вопрос текстом: завязка сюжета + «какой чертёж?».
        wrappers = list(arch.wrappers())
        rng.shuffle(wrappers)
        statement = None
        used_wrapper = None
        tail = u'На каком чертеже эта ситуация показана верно?'
        for w in wrappers:
            text = w.short(params, solved).strip() + ' ' + tail
            if len(text) <= LIMIT_SHORT:
                statement = text
                used_wrapper = w
                break
        if statement is None:
            continue

        steps = arch.solution(params, solved, asked)
        gen_params = dict(params)
        gen_params['_asked'] = asked.key
        gen_params['_wrapper'] = used_wrapper.key
        json.dumps(gen_params)

        difficulty = asked.difficulty if asked.difficulty is not None \
            else _difficulty(len(steps), asked.trivial)

        return {
            'question_type': 'figure_choice',
            'statement': statement,
            # options — САМИ ЧЕРТЕЖИ: игроку нужно их видеть, это и есть
            # варианты ответа. Правильный индекс сюда не входит.
            'options': options,
            'correct_index': correct_index,
            'correct_value': '',
            'unit': '',
            'solution_text': _numbered(steps),
            'difficulty': difficulty,
            'topics': list(arch.topics),
            'generator_key': arch.key,
            'params': gen_params,
            'figure': correct_fig,     # для разбора после ответа
        }

    raise GenerationError(
        u'{}: не собрался валидный figure_choice за {} попыток'.format(
            arch.key, MAX_SAMPLE_ATTEMPTS))


def generate_batch(arch, rng, question_type, n):
    """n УНИКАЛЬНЫХ вопросов (ключ: текст + правильный ответ). Если истощили
    попытки (комбинаторика сеток меньше n) — возвращаем сколько есть."""
    out = []
    seen = set()
    attempts = 0
    while len(out) < n and attempts < n * 60:
        attempts += 1
        try:
            q = (generate_figure_choice(arch, rng)
                 if question_type == 'figure_choice'
                 else generate_question(arch, rng, question_type))
        except GenerationError:
            break
        key = (q['statement'], q['correct_value'], q['correct_index'],
               json.dumps(q['options'], sort_keys=True))
        if key in seen:
            continue
        seen.add(key)
        out.append(q)
    return out
