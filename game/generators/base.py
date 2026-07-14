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
    trivial=True — одношаговое «считывание» (сложность 1, а не 2)."""

    def __init__(self, key, nom='', acc='', gender='f', unit='',
                 kind='value', question='', claim_tpl='', class_options=None,
                 trivial=False):
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


# ---------------------------------------------------------------------------
# Грамматика вопросительных предложений
# ---------------------------------------------------------------------------

_RAVN = {'m': 'равен', 'f': 'равна', 'n': 'равно'}

# Зачины в манере ВсОШ-региона (reports/generators/style_notes.md §2).
_NUMERIC_TPLS = [
    u'Найдите {acc}{unit_p}.',
    u'Определите {acc}{unit_p}.',
    u'Чему {ravn} {nom}{unit_p}?',
]


def _unit_paren(unit):
    return u' (в {})'.format(unit) if unit else ''


def _question_sentence(rng, asked):
    """Вопросительное предложение для value-вопроса (numeric и single)."""
    tpl = rng.choice(_NUMERIC_TPLS)
    return tpl.format(acc=asked.acc, nom=asked.nom,
                      ravn=_RAVN[asked.gender], unit_p=_unit_paren(asked.unit))


def _claim_sentence(asked, value_str):
    """Утверждение для boolean-вопроса типа value: «верно ли, что X равен V»."""
    unit_sfx = u' {}'.format(asked.unit) if asked.unit else ''
    return u'Верно ли, что {} {} {}{}?'.format(
        asked.nom, _RAVN[asked.gender], value_str, unit_sfx)


# ---------------------------------------------------------------------------
# Дистракторы
# ---------------------------------------------------------------------------

def _clean_distractors(errors, answer, non_negative=True):
    """Фильтр вычисленных ошибок: уникальны, ≠ ответу, красивы,
    правдоподобны (неотрицательны). Порядок сохраняется."""
    out = []
    seen = {Fraction(answer)}
    for e in errors:
        e = Fraction(e)
        if e in seen:
            continue
        if non_negative and e < 0:
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
                arch.error_variants(params, solved, asked), answer)
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

        return {
            'question_type': question_type,
            'statement': statement,
            'options': options,
            'correct_index': correct_index,
            'correct_value': correct_value,
            'unit': unit,
            'solution_text': _numbered(steps),
            'difficulty': _difficulty(len(steps), asked.trivial),
            'topics': list(arch.topics),
            'generator_key': arch.key,
            'params': gen_params,
        }

    raise GenerationError(
        u'{}: не собрался валидный {} за {} попыток'.format(
            arch.key, question_type, MAX_SAMPLE_ATTEMPTS))


def generate_batch(arch, rng, question_type, n):
    """n УНИКАЛЬНЫХ вопросов (ключ: текст + правильный ответ). Если истощили
    попытки (комбинаторика сеток меньше n) — возвращаем сколько есть."""
    out = []
    seen = set()
    attempts = 0
    while len(out) < n and attempts < n * 60:
        attempts += 1
        try:
            q = generate_question(arch, rng, question_type)
        except GenerationError:
            break
        key = (q['statement'], q['correct_value'], q['correct_index'],
               tuple(q['options']))
        if key in seen:
            continue
        seen.add(key)
        out.append(q)
    return out
