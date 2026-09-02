"""
Модели игры Econ Rush.

GameQuestion — денормализованный КЭШ игровых вопросов, собираемый командой
`build_game_pool` из тестовых задач (`Problem` с problem_type «тест: …»).
Контент-таблицы (`Problem`, `ProblemPart`) при пересборке не изменяются —
пул можно в любой момент снести и собрать заново.

Четыре типа вопросов (по режимам игры): boolean — данетка (Пуля),
single — один из вариантов (Блиц), multi — несколько из вариантов (Рапид),
numeric — числовой ответ вводом (Классика; извлечение появится с импортом
региональных тестов).
"""
import secrets

from django.db import models

# Алфавит кода публичной ссылки — Crockford base32: без I, L, O, U,
# чтобы код нельзя было спутать при чтении вслух или переписывании.
CODE_ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'
CODE_LENGTH = 8


def make_code():
    """Случайный короткий код: публичная страница результата и набор.

    32^8 ≈ 1,1 трлн вариантов — угадать чужой результат или набор перебором
    не выйдет, а порядковый id выдавал бы, сколько всего забегов сыграно.
    Функция ОДНА на обе сущности: копия разъехалась бы с алфавитом.
    """
    return ''.join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def normalize_code(raw):
    """Код, введённый руками: без пробелов, в верхнем регистре.

    Его переписывают с доски и диктуют вслух, поэтому регистр и пробелы
    значить не должны. Символы вне алфавита не чиним — это уже не наш код.
    """
    return ''.join((raw or '').split()).upper()


# Прежнее имя оставлено: на него ссылается default в миграции 0005, а
# исторические миграции переписывать нельзя.
make_result_code = make_code


class GameQuestion(models.Model):
    """Один игровой вопрос: текст + варианты + правильный ответ (по типу)."""

    QUESTION_TYPES = [
        ('boolean', 'Данетка'),
        ('single', 'Один из'),
        ('multi', 'Несколько из'),
        ('numeric', 'Числовой'),
        # ⚠️ figure_choice оставлен, но НЕ выдаётся ни одним режимом: слот
        # «Графика» занял аудит чужого решения (решение Notion 2026-07-26).
        # Строки этого типа в базе не трогаем — откат решения не должен
        # стоить пересборки пула.
        ('figure_choice', 'Выбор чертежа (не выдаётся)'),
        ('figure_audit', 'Аудит чужого решения'),
    ]

    # FK (не OneToOne): одна задача может дать несколько игровых вопросов —
    # задел под данетки-пачки из будущего импорта (разведка 2026-07-11
    # показала, что в текущей базе пачек нет, но формат приедет с регионами).
    # NULL — только у сгенерированных вопросов (is_generated=True): у них
    # нет задачи-источника, их math задаётся generator_key + gen_params.
    problem = models.ForeignKey(
        'problems.Problem', on_delete=models.CASCADE, null=True, blank=True,
        related_name='game_questions', verbose_name='Задача-источник')
    # Подпункт-источник — только для вопросов, извлечённых из конкретного
    # ProblemPart (разбивка пачек). Для вопросов «вся задача целиком» — NULL.
    part = models.ForeignKey(
        'problems.ProblemPart', null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='game_questions', verbose_name='Подпункт-источник')

    question_type = models.CharField(
        'Тип вопроса', max_length=16, choices=QUESTION_TYPES,
        default='single', db_index=True)
    question = models.TextField('Текст вопроса')
    # Варианты ответа — список строк (2–5 штук), порядок как в задаче.
    # Для boolean всегда ['Верно', 'Неверно']; для numeric — пустой список.
    # Для figure_choice — список из четырёх ЧЕРТЕЖЕЙ (dict по схеме
    # _figure.py): игроку нужно их видеть, это и есть варианты ответа.
    options = models.JSONField('Варианты ответа')
    # Правильный ответ — ровно одно из трёх полей по типу вопроса:
    # boolean/single → correct_index; multi → correct_indices; numeric → correct_value.
    correct_index = models.PositiveSmallIntegerField(
        'Индекс правильного (0-based)', null=True, blank=True)
    correct_indices = models.JSONField(
        'Индексы правильных (multi)', null=True, blank=True)
    correct_value = models.CharField(
        'Точный числовой ответ (numeric)', max_length=50, blank=True, default='')

    # Сложность 1–5. У большинства тестов difficulty в базе пуст —
    # тогда оценка эвристикой (см. build_game_pool), это честно записано в отчёте.
    difficulty = models.PositiveSmallIntegerField('Сложность (1–5)', default=3)
    # Темы денормализованы: список названий канонических тем (может быть пустым).
    topics = models.JSONField('Темы (названия)', default=list, blank=True)
    lang = models.CharField('Язык вопроса', max_length=2, default='ru')

    # Метаданные олимпиады (денормализация под будущий фильтр «только регион»;
    # заполнятся импортом региональных тестов, сейчас пустые).
    stage = models.CharField('Этап олимпиады', max_length=40, blank=True, default='')
    year = models.PositiveIntegerField('Год', null=True, blank=True)
    grade = models.CharField('Класс', max_length=20, blank=True, default='')
    # Единица измерения числового ответа («%», «руб.») — подсказка игроку
    # рядом с полем ввода Классики. Источник — SourceReference.note
    # («единица ответа: …»), денормализуется при пересборке пула.
    unit = models.CharField('Единица ответа', max_length=40, blank=True,
                            default='')
    # Источник вопроса — денормализован при сборке пула (как topics и
    # stage/year/grade). Нужен фильтру «источники» на стартовом экране:
    # выбор вопроса читает пул одним плоским values_list, join на
    # SourceReference там дал бы дубли строк у задач с двумя привязками.
    # Пусто — у сгенерированных (у них нет задачи-источника) и у редких
    # задач банка без SourceReference.
    source_id = models.PositiveIntegerField('ID источника', null=True,
                                            blank=True, db_index=True)
    source_group = models.CharField('Группа источников', max_length=16,
                                    blank=True, default='', db_index=True)
    # Теги задачи-источника, денормализованные списком id (как topics —
    # названиями). ⚠️ Списком, а не M2M: выбор вопроса читает пул одним
    # плоским values_list, и join на теги дал бы дубли строк у задачи с
    # тремя тегами — то есть такая задача выпадала бы чаще прочих.
    # Заполняется при пересборке пула (build_game_pool).
    tag_ids = models.JSONField('ID тегов', default=list, blank=True)

    # --- Параметрические генераторы (game/generators/) ---
    # Сгенерированные вопросы живут в том же кэше, но: build_game_pool их
    # НЕ трогает (пересобирает только is_generated=False), а полный откат —
    # команда purge_generated.
    is_generated = models.BooleanField(
        'Сгенерирован', default=False, db_index=True)
    generator_key = models.CharField(
        'Ключ генератора (архетип)', max_length=64, blank=True, default='')
    gen_params = models.JSONField(
        'Параметры генерации', null=True, blank=True)
    gen_solution = models.TextField(
        'Пошаговое решение (KaTeX)', blank=True, default='')
    # Чертёж к задаче: параметры статичного SVG (тип диаграммы + числа),
    # рисует клиент в разборе ошибок. Схема — game/generators/_figure.py.
    # NULL — у вопроса графика нет (не все архетипы графические).
    figure = models.JSONField(
        'Параметры графика', null=True, blank=True)
    # ЭТАЛОННЫЙ чертёж — только у вопросов режима «График» (figure_audit).
    # У них поле figure хранит ПОКАЗАННОЕ решение (возможно, с внедрённой
    # ошибкой), а здесь лежит то, как правильно. Разбор ошибок показывает
    # оба рядом.
    # ⚠️ Отдельное поле, а не два ключа внутри `figure`: иначе у одного поля
    # оказалось бы две формы по типу вопроса, и разбор архетипов сломался бы.
    # Пересчитывать эталон на лету из gen_params тоже нельзя — правка кода
    # сюжета разошлась бы со старыми строками.
    figure_ref = models.JSONField(
        'Эталонный чертёж (аудит)', null=True, blank=True)

    created_at = models.DateTimeField('Собран', auto_now_add=True)

    class Meta:
        verbose_name = 'Игровой вопрос'
        verbose_name_plural = 'Игровые вопросы'
        constraints = [
            models.UniqueConstraint(
                fields=['problem', 'part'], name='uniq_gq_problem_part'),
        ]
        indexes = [
            models.Index(fields=['lang', 'difficulty']),
            models.Index(fields=['lang', 'question_type']),
        ]

    def __str__(self):
        return f'GameQuestion #{self.pk} (задача #{self.problem_id})'


class GameSet(models.Model):
    """Набор — забег с ЗАРАНЕЕ ЗАФИКСИРОВАННЫМ списком вопросов.

    Одна сущность на три поверхности (решение Notion от 2026-07-26):
    вызов дня, набор учителя и дуэль — это один и тот же забег, у которого
    список вопросов задан заранее и одинаков у всех, кто его играет.

    ⚠️ Именно фиксированный список делает возможной доску результатов.
    Общий лидерборд по случайным забегам по-прежнему невозможен (записи
    ничьи и несравнимы), а доска набора возможна: вопросы у всех одни.

    question_ids — УПОРЯДОЧЕННЫЙ список id. Порядок часть контракта: при
    разном порядке сравнение результатов нечестно (кто-то встретил трудный
    вопрос на свежую голову, кто-то на последней жизни).
    """

    KINDS = [
        ('daily', 'Вызов дня'),
        ('custom', 'Набор учителя'),
        ('duel', 'Дуэль'),
    ]

    code = models.CharField('Код', max_length=16, unique=True,
                            default=make_code, db_index=True)
    mode = models.CharField('Режим', max_length=16)
    kind = models.CharField('Происхождение', max_length=8, choices=KINDS,
                            default='custom', db_index=True)
    title = models.CharField('Название', max_length=120, blank=True, default='')
    # NULL — у анонимного автора (дуэль без логина) и у вызова дня.
    author = models.ForeignKey('problems.User', null=True, blank=True,
                               on_delete=models.SET_NULL,
                               related_name='game_sets', verbose_name='Автор')
    created = models.DateTimeField('Создан', auto_now_add=True)

    question_ids = models.JSONField('Вопросы (по порядку)', default=list)
    # Под какой фильтр собран — показываем сопернику и «бросить вызов дальше».
    filter_snapshot = models.JSONField('Снимок фильтра', default=dict, blank=True)

    opens_at = models.DateTimeField('Открыт с', null=True, blank=True)
    closes_at = models.DateTimeField('Закрыт с', null=True, blank=True)
    attempts_allowed = models.PositiveSmallIntegerField('Попыток', default=1)

    # Дата вызова дня — по ней он и ищется. Для остальных видов пусто.
    # Пара (kind='daily', mode, day) уникальна: один вызов на режим в день.
    day = models.DateField('Дата вызова дня', null=True, blank=True,
                           db_index=True)

    class Meta:
        verbose_name = 'Набор вопросов'
        verbose_name_plural = 'Наборы вопросов'
        ordering = ['-created']
        constraints = [
            models.UniqueConstraint(
                fields=['kind', 'mode', 'day'], name='uniq_daily_set_per_mode',
                condition=models.Q(kind='daily')),
        ]

    def __str__(self):
        return f'{self.get_kind_display()} {self.code} ({self.mode})'

    @property
    def size(self):
        return len(self.question_ids or [])


class GameResult(models.Model):
    """Сохранённый результат забега — для публичной страницы `/game/r/<код>/`.

    Отдельная таблица, ничего в игре от неё не зависит: строка создаётся при
    завершении забега и живёт сама по себе. Это НЕ лидерборд — записи ничьи,
    сравнивать их между собой нельзя (авторизации у игры нет, счёт приходит
    из сессии игрока). Смысл один: у ссылки, которой делятся, должно быть
    что показать.

    Разбивки лежат JSON-полями (Django 4.2 умеет их и на SQLite, и на
    Postgres): страница read-only, запросов «по темам» к ним не будет.
    """
    code = models.CharField('Код ссылки', max_length=16, unique=True,
                            default=make_result_code, db_index=True)
    # Связь с набором: результаты одного набора и есть его доска.
    # NULL — обычный случайный забег (такие между собой несравнимы).
    game_set = models.ForeignKey(GameSet, null=True, blank=True,
                                 on_delete=models.CASCADE,
                                 related_name='results',
                                 verbose_name='Набор')
    # Кто сыграл. NULL — аноним: игра публичная, логин не требуется.
    # На доску попадают только авторизованные (у анонима нет имени, а
    # «аноним №4» ничего не значит).
    user = models.ForeignKey('problems.User', null=True, blank=True,
                             on_delete=models.SET_NULL,
                             related_name='game_results',
                             verbose_name='Игрок')
    mode = models.CharField('Режим', max_length=16)
    score = models.PositiveIntegerField('Счёт', default=0)
    correct_count = models.PositiveSmallIntegerField('Верных', default=0)
    total_count = models.PositiveSmallIntegerField('Попыток', default=0)
    max_combo = models.PositiveSmallIntegerField('Макс. множитель', default=1)
    ended_reason = models.CharField('Чем кончился', max_length=8, default='time')
    # [{topic, correct, wrong, skip, total, accuracy}, ...]
    topic_breakdown = models.JSONField('Разбивка по темам', default=list, blank=True)
    # [{key, title, total, correct}, ...]
    difficulty_breakdown = models.JSONField('Разбивка по сложности',
                                            default=list, blank=True)
    # счёт по номеру вопроса — мини-график на публичной странице
    score_curve = models.JSONField('Кривая счёта', default=list, blank=True)
    # [{question_id, number, outcome}, ...] — исход каждого вопроса.
    # Нужен доске набора («на чём посыпался класс») и полосе сравнения в
    # дуэли: журналы забегов живут в сессиях игроков и до сервера доски не
    # доходят, а результат — доходит.
    question_outcomes = models.JSONField('Исходы по вопросам',
                                         default=list, blank=True)
    created_at = models.DateTimeField('Сыгран', auto_now_add=True)

    class Meta:
        verbose_name = 'Результат забега'
        verbose_name_plural = 'Результаты забегов'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.code}: {self.score} очков ({self.mode})'

    @property
    def accuracy(self):
        return round(100 * self.correct_count / self.total_count) if self.total_count else 0


class QuestionStatBase(models.Model):
    """Общие счётчики статистики вопроса.

    ⚠️ Почему статистика НЕ лежит на GameQuestion: пул — это КЭШ, команда
    `build_game_pool` сносит все несгенерированные строки и создаёт их
    заново с новыми id. Счётчики, положенные на строку кэша, умерли бы при
    первой же пересборке. Поэтому они привязаны к устойчивым сущностям:
    задаче банка (Problem + ProblemPart) либо ключу архетипа.

    Доля верных считается от ПОПЫТОК (correct + wrong) — тот же принцип,
    что в build_summary: пропуск не ответ и портить им долю нечестно.
    """
    shown = models.PositiveIntegerField('Показов', default=0)
    correct = models.PositiveIntegerField('Верных', default=0)
    wrong = models.PositiveIntegerField('Неверных', default=0)
    skipped = models.PositiveIntegerField('Пропусков', default=0)
    # Сумма времени ответов. Медиану по сумме не восстановить — служебная
    # страница честно показывает СРЕДНЕЕ и так и подписана.
    total_ms = models.BigIntegerField('Сумма времени ответов (мс)', default=0)
    updated = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        abstract = True

    @property
    def attempts(self):
        return self.correct + self.wrong

    @property
    def p_correct(self):
        """Доля верных 0..1 или None, если попыток ещё нет."""
        return (self.correct / self.attempts) if self.attempts else None

    @property
    def avg_ms(self):
        """Среднее время ответа. Именно среднее, не медиана: по сумме
        медиану не восстановить, а хранить каждый ответ ради неё дорого."""
        return round(self.total_ms / self.shown) if self.shown else 0


class BankQuestionStat(QuestionStatBase):
    """Статистика вопроса из банка: ключ — задача (+ подпункт, если вопрос
    извлечён из него). Переживает любую пересборку пула."""

    problem = models.ForeignKey(
        'problems.Problem', on_delete=models.CASCADE,
        related_name='game_stats', verbose_name='Задача')
    part = models.ForeignKey(
        'problems.ProblemPart', null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='game_stats', verbose_name='Подпункт')

    class Meta:
        verbose_name = 'Статистика вопроса банка'
        verbose_name_plural = 'Статистика вопросов банка'
        constraints = [
            models.UniqueConstraint(fields=['problem', 'part'],
                                    name='uniq_bank_stat_problem_part'),
        ]

    def __str__(self):
        return f'stat задачи #{self.problem_id}: {self.correct}/{self.attempts}'


class ArchetypeStat(QuestionStatBase):
    """Статистика сгенерированного вопроса — по АРХЕТИПУ, не по вопросу.

    У сгенерированного вопроса параметры каждый раз новые: «монополия
    с ценой 40» и «монополия с ценой 60» — разные строки кэша, но одна и та
    же задача по сути. Считать долю верных по конкретной строке значит
    делить выборку на песчинки; по архетипу — осмысленно.
    """
    generator_key = models.CharField('Ключ архетипа', max_length=64,
                                     unique=True, db_index=True)

    class Meta:
        verbose_name = 'Статистика архетипа'
        verbose_name_plural = 'Статистика архетипов'

    def __str__(self):
        return f'stat архетипа {self.generator_key}: {self.correct}/{self.attempts}'
