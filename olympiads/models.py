"""Модели раздела «Олимпиады».

Раздел справочный: он рассказывает про олимпиады по экономике — что за
олимпиада, когда туры, какие льготы даёт, какие были проходные баллы и
какие комплекты заданий уже собраны.

Два правила пронизывают весь файл, и оба не про красоту:

1. **У каждого факта есть источник** (`FactSource`). Раздел читают
   школьники, которые по нему принимают решения — подавать документы или
   нет. Факт без ссылки на приказ или страницу вуза здесь не факт.
2. **Неподтверждённую дату показывать нельзя.** Если число ещё не
   объявлено, в базе лежит не «примерно 15 января», а текст «обычно
   вторая половина января». Правило закреплено в `OlympiadEvent.clean()`,
   а не только в шаблоне: шаблон легко обойти новым экраном.

Приложение НИЧЕГО не пишет в `problems`. Связь с банком задач — только на
чтение, через `problems.OlympiadRef.olympiad_slug`.
"""
from datetime import date

from django.core.exceptions import ValidationError
from django.db import models

# Месяцы в родительном падеже: «24 сентября», а не «24 сентябрь».
MONTHS_GENITIVE = (
    'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
    'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
)


# Подписи тегов и их порядок. Одно место на два экрана: полосу чипов и
# карточку — иначе список на карточке однажды разойдётся с фильтром.
TAG_LABELS = (
    ('law_bvi', 'Без экзаменов по закону'),
    ('level_1', 'I уровень'),
    ('level_23', 'II–III уровень'),
    ('registration_open', 'Идёт регистрация'),
    ('young', 'Можно с 5–8 класса'),
    ('online_qual', 'Онлайн отборочный'),
    ('online_final', 'Онлайн финал'),
    ('team', 'Командная'),
)


def current_academic_year(today=None):
    """Текущий учебный год строкой «2026/27».

    Учебный год начинается в сентябре: 3 сентября 2026 — это 2026/27,
    а 3 мая 2027 — всё ещё 2026/27.
    """
    today = today or date.today()
    start = today.year if today.month >= 9 else today.year - 1
    return '{}/{}'.format(start, str(start + 1)[-2:])


class FactSource(models.Model):
    """Источник факта: приказ, страница сайта, документ, правила приёма.

    Ядро будущего механизма обновления: фоновая проверка ходит по этим
    адресам, сравнивает `content_hash` и кладёт расхождения в
    `FactUpdateProposal`. Ничего не перезаписывается само.
    """

    class DocType(models.TextChoices):
        ORDER = 'order', 'Приказ'
        SITE = 'site', 'Страница сайта'
        PDF = 'pdf', 'Документ'
        RULES = 'rules', 'Правила приёма'

    url = models.URLField('Адрес', max_length=500, unique=True)
    title = models.CharField('Название', max_length=300, blank=True)
    doc_type = models.CharField(
        'Вид документа', max_length=20, choices=DocType.choices,
        default=DocType.SITE,
    )
    publisher = models.CharField('Кто опубликовал', max_length=200, blank=True)
    fetched_at = models.DateTimeField('Когда скачано', null=True, blank=True)
    content_hash = models.CharField('Хеш содержимого', max_length=64, blank=True)
    http_status = models.PositiveSmallIntegerField(
        'Код ответа', null=True, blank=True)
    verified_at = models.DateField('Проверено человеком', null=True, blank=True)
    note = models.TextField('Заметка', blank=True)

    class Meta:
        verbose_name = 'Источник факта'
        verbose_name_plural = 'Источники фактов'
        ordering = ['publisher', 'title']

    def __str__(self):
        return self.title or self.url


class Olympiad(models.Model):
    """Олимпиада — справочная карточка.

    «Престижность» словом нигде не хранится: порядок на главной считает
    `sort_key()` по уровню в перечне и ручному рангу. Иначе спор о том,
    кто важнее, переезжал бы в текстовое поле.
    """

    class Kind(models.TextChoices):
        VSOSH = 'vsosh', 'Всероссийская олимпиада школьников'
        PERECHEN = 'perechen', 'Из перечня РСОШ'
        INTERNATIONAL = 'international', 'Международная'
        OTHER = 'other', 'Другая'

    class DisplayGroup(models.TextChoices):
        MAIN = 'main', 'Основные по экономике'
        RELATED = 'related', 'Смежный профиль'

    slug = models.SlugField('Слаг', unique=True)
    name_full = models.CharField('Полное название', max_length=300)
    name_short = models.CharField('Короткое название', max_length=50)
    organizer = models.CharField('Организатор', max_length=300)
    official_url = models.URLField(
        'Официальный сайт', max_length=500, blank=True)
    archive_url = models.URLField('Архив заданий', max_length=500, blank=True)
    registration_url = models.URLField(
        'Страница регистрации', max_length=500, blank=True)
    logo = models.ImageField(
        'Логотип', upload_to='olympiads/logos/', blank=True, null=True)
    kind = models.CharField(
        'Тип', max_length=20, choices=Kind.choices, default=Kind.PERECHEN)
    display_group = models.CharField(
        'Группа показа', max_length=20, choices=DisplayGroup.choices,
        default=DisplayGroup.MAIN,
    )
    grade_min = models.PositiveSmallIntegerField(
        'Класс с', null=True, blank=True)
    grade_max = models.PositiveSmallIntegerField(
        'Класс по', null=True, blank=True)
    is_team = models.BooleanField('Командная', default=False)
    has_online_qualifier = models.BooleanField(
        'Отборочный онлайн', null=True, blank=True)
    has_online_final = models.BooleanField(
        'Финал онлайн', null=True, blank=True)
    language = models.CharField('Язык', max_length=50, blank=True)
    description = models.TextField('Описание', blank=True)
    manual_rank = models.IntegerField('Ручной ранг', default=0)
    is_placeholder = models.BooleanField(
        'Демонстрационные данные', default=False)
    is_published = models.BooleanField('Опубликована', default=False)
    source = models.ForeignKey(
        FactSource, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='olympiads', verbose_name='Источник',
    )

    class Meta:
        verbose_name = 'Олимпиада'
        verbose_name_plural = 'Олимпиады'
        ordering = ['display_group', '-manual_rank', 'name_short']

    def __str__(self):
        return self.name_short or self.name_full

    # ── Уровень в перечне ───────────────────────────────────────────
    def level_for(self, academic_year=None):
        """Уровень РСОШ на учебный год; None — нет уровня или нет записи.

        У ВсОШ уровня нет вовсе: она не в перечне, льгота установлена
        законом. Поэтому None здесь — законное значение, а не пробел.
        """
        academic_year = academic_year or current_academic_year()
        row = None
        # Идём по уже загруженным строкам: на списке олимпиад levels
        # приходят одним prefetch, и обращение к базе тут было бы N+1.
        for level_year in self.levels.all():
            if level_year.academic_year == academic_year:
                row = level_year
                break
        return row.level if row else None

    # ── Порядок на главной ──────────────────────────────────────────
    def sort_key(self, academic_year=None):
        """Ключ сортировки карточек. Меньше — выше.

        1. ВсОШ всегда первой;
        2. затем уровень в перечне: 1, 2, 3, потом без уровня;
        3. внутри уровня — ручной ранг по убыванию;
        4. при равенстве — число привязанных задач по убыванию.
        """
        level = self.level_for(academic_year)
        return (
            0 if self.kind == self.Kind.VSOSH else 1,
            level if level in (1, 2, 3) else 4,
            -self.manual_rank,
            -self.problem_count,
        )

    # ── Теги ────────────────────────────────────────────────────────
    @property
    def tags(self):
        """Коды активных тегов олимпиады — ими же работают чипы-фильтры."""
        codes = []
        if self.kind == self.Kind.VSOSH:
            codes.append('law_bvi')
        level = self.level_for()
        if level == 1:
            codes.append('level_1')
        elif level in (2, 3):
            codes.append('level_23')
        if self.registration_is_open:
            codes.append('registration_open')
        if self.grade_min is not None and self.grade_min <= 8:
            codes.append('young')
        if self.has_online_qualifier:
            codes.append('online_qual')
        if self.has_online_final:
            codes.append('online_final')
        if self.is_team:
            codes.append('team')
        return codes

    @property
    def registration_is_open(self):
        """Регистрация открыта: открытие уже было, дедлайн ещё не прошёл.

        Считаем только по подтверждённым датам: «примерно в октябре» не
        повод написать школьнику, что регистрация идёт.
        """
        today = date.today()
        opened = closes_later = False
        for event in self.events.all():
            if event.date_start is None:
                continue
            if event.kind == OlympiadEvent.Kind.REGISTRATION_OPEN:
                if event.date_start <= today:
                    opened = True
            elif event.kind == OlympiadEvent.Kind.REGISTRATION_CLOSE:
                if event.date_start >= today:
                    closes_later = True
        return opened and closes_later

    # ── Связь с банком задач (только чтение) ────────────────────────
    @property
    def problem_count(self):
        """Сколько задач банка привязано к этой олимпиаде.

        Привязки живут в `problems.OlympiadRef` и делаются отдельным
        конвейером; раздел олимпиад их только читает.
        """
        if getattr(self, '_problem_count', None) is not None:
            return self._problem_count
        from problems.models import OlympiadRef
        self._problem_count = (
            OlympiadRef.objects
            .filter(olympiad_slug=self.slug)
            .values('problem_id').distinct().count()
        )
        return self._problem_count

    @property
    def variant_count(self):
        return self.variants.count()

    @property
    def tag_labels(self):
        """Активные теги парами «код + подпись», в порядке полосы чипов."""
        active = set(self.tags)
        return [(code, label) for code, label in TAG_LABELS if code in active]

    @property
    def next_event(self):
        """Ближайшее событие для карточки.

        Сначала подтверждённые начиная с сегодня, потом — ориентиры. У
        ориентира числа нет, и вперёд настоящей даты он не встаёт.
        """
        today = date.today()
        confirmed = [
            e for e in self.events.all()
            if e.is_confirmed and e.date_start and e.date_start >= today
        ]
        if confirmed:
            return min(confirmed, key=lambda e: e.date_start)
        approximate = [e for e in self.events.all() if not e.is_confirmed]
        return approximate[0] if approximate else None

    @property
    def grades_label(self):
        """«9–11 классы» одной строкой; пусто, если классы не заданы."""
        if self.grade_min and self.grade_max:
            if self.grade_min == self.grade_max:
                return '{} класс'.format(self.grade_min)
            return '{}–{} классы'.format(self.grade_min, self.grade_max)
        if self.grade_min:
            return 'с {} класса'.format(self.grade_min)
        if self.grade_max:
            return 'по {} класс'.format(self.grade_max)
        return ''

    @property
    def format_label(self):
        """Формат одной строкой.

        Если отборочный и финал устроены по-разному — так и пишем, а не
        усредняем в «смешанный»: школьнику важно, куда ехать.
        """
        stages = list(self.stages.all())
        if not stages:
            return ''
        words = {'online': 'онлайн', 'offline': 'очно', 'mixed': 'смешанно'}
        formats = {stage.format for stage in stages}
        if len(formats) == 1:
            single = {'online': 'Онлайн', 'offline': 'Очно',
                      'mixed': 'Смешанный'}
            return single[formats.pop()]
        first, last = stages[0], stages[-1]
        return 'Отбор {}, финал {}'.format(words[first.format],
                                           words[last.format])

    @property
    def cities_summary(self):
        """Города всех очных этапов одной строкой, без повторов."""
        seen, out = set(), []
        for stage in self.stages.all():
            for city in (stage.cities or []):
                if city and city not in seen:
                    seen.add(city)
                    out.append(city)
        if not out:
            return ''
        if len(out) <= 3:
            return ', '.join(out)
        return '{} и ещё {}'.format(out[0], len(out) - 1)

    @property
    def registration_label(self):
        """Строка факта «Регистрация» в шапке страницы."""
        if self.registration_is_open:
            return 'Идёт'
        if self.registration_url:
            return 'Пока не открыта'
        return 'Нет данных'

    @property
    def abbr(self):
        """Две-три буквы для квадрата на месте ненайденного логотипа."""
        source = (self.name_short or self.name_full).strip()
        words = [w for w in source.replace('«', ' ').replace('»', ' ').split() if w]
        if len(words) >= 2:
            return ''.join(w[0] for w in words[:3]).upper()
        return source[:3].upper()


class OlympiadLevelYear(models.Model):
    """Уровень в перечне РСОШ на конкретный учебный год.

    Отдельной моделью, потому что уровень пересматривают каждый год: он
    свойство пары «олимпиада + год», а не самой олимпиады. У ВсОШ уровня
    нет вовсе — тогда `level` пустой.
    """

    class ApprovalStatus(models.TextChoices):
        DRAFT = 'draft', 'Проект приказа'
        APPROVED = 'approved', 'Утверждён'

    olympiad = models.ForeignKey(
        Olympiad, on_delete=models.CASCADE, related_name='levels',
        verbose_name='Олимпиада',
    )
    academic_year = models.CharField('Учебный год', max_length=10)
    level = models.PositiveSmallIntegerField(
        'Уровень', null=True, blank=True,
        help_text='1, 2 или 3; пусто — олимпиады нет в перечне',
    )
    order_number = models.PositiveSmallIntegerField(
        'Номер в перечне', null=True, blank=True)
    approval_status = models.CharField(
        'Статус приказа', max_length=20, choices=ApprovalStatus.choices,
        default=ApprovalStatus.DRAFT,
    )
    source = models.ForeignKey(
        FactSource, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='levels', verbose_name='Источник',
    )

    class Meta:
        verbose_name = 'Уровень по годам'
        verbose_name_plural = 'Уровни по годам'
        unique_together = ('olympiad', 'academic_year')
        ordering = ['-academic_year', 'level']

    def __str__(self):
        level = self.level if self.level else 'без уровня'
        return '{} · {} · {}'.format(self.olympiad, self.academic_year, level)


class OlympiadStage(models.Model):
    """Устройство этапа — БЕЗ дат. Даты живут только в `OlympiadEvent`.

    Разделено намеренно: устройство этапа («региональный, 235 минут,
    очно») меняется раз в несколько лет, а даты — каждый сезон.
    """

    class Format(models.TextChoices):
        ONLINE = 'online', 'Онлайн'
        OFFLINE = 'offline', 'Очно'
        MIXED = 'mixed', 'Смешанный'

    olympiad = models.ForeignKey(
        Olympiad, on_delete=models.CASCADE, related_name='stages',
        verbose_name='Олимпиада',
    )
    code = models.CharField('Код этапа', max_length=20)
    name = models.CharField('Название', max_length=100)
    order = models.PositiveSmallIntegerField('Порядок', default=0)
    format = models.CharField(
        'Формат', max_length=20, choices=Format.choices,
        default=Format.OFFLINE,
    )
    cities = models.JSONField('Города', default=list, blank=True)
    duration_minutes = models.PositiveIntegerField(
        'Длительность, минут', null=True, blank=True)
    max_score = models.PositiveIntegerField(
        'Максимум баллов', null=True, blank=True)
    has_test_part = models.BooleanField(
        'Есть тестовая часть', null=True, blank=True)
    how_to_qualify = models.TextField('Как попасть', blank=True)
    top_topic = models.CharField(
        'Самая частая тема', max_length=200, blank=True)
    top_topic_share = models.FloatField(
        'Доля самой частой темы', null=True, blank=True)
    topic_histogram = models.JSONField(
        'Распределение тем', default=list, blank=True,
        help_text='[{"topic": "...", "share": 0.18}] — заполнит прогон обогащения',
    )

    class Meta:
        verbose_name = 'Этап олимпиады'
        verbose_name_plural = 'Этапы олимпиад'
        unique_together = ('olympiad', 'code')
        ordering = ['olympiad', 'order']

    def __str__(self):
        return '{} · {}'.format(self.olympiad, self.name)

    @property
    def cities_label(self):
        """Где проходит: «Онлайн», список до трёх городов или «Москва и ещё N»."""
        if self.format == self.Format.ONLINE:
            return 'Онлайн'
        cities = [c for c in (self.cities or []) if c]
        if not cities:
            return ''
        if len(cities) <= 3:
            return ', '.join(cities)
        return '{} и ещё {}'.format(cities[0], len(cities) - 1)

    @property
    def cities_overflow(self):
        """Полный список городов — его показывает подсказка при наведении."""
        cities = [c for c in (self.cities or []) if c]
        return cities if len(cities) > 3 else []


class OlympiadEvent(models.Model):
    """Событие с датой: открытие регистрации, дедлайн, тур, результаты.

    ЕДИНСТВЕННЫЙ источник дат в разделе. И лента «Ближайшие даты», и
    календарь читают только отсюда — иначе две ленты рано или поздно
    разойдутся и школьник поверит той, что старее.
    """

    class Kind(models.TextChoices):
        REGISTRATION_OPEN = 'registration_open', 'Открытие регистрации'
        REGISTRATION_CLOSE = 'registration_close', 'Дедлайн регистрации'
        STAGE = 'stage', 'Тур'
        RESULTS = 'results', 'Объявление результатов'

    class DateStatus(models.TextChoices):
        CONFIRMED = 'confirmed', 'Дата подтверждена'
        APPROX_LAST_YEAR = 'approx_last_year', 'Ориентировочно по прошлому году'
        AWAITING = 'awaiting', 'Ждём объявления'

    olympiad = models.ForeignKey(
        Olympiad, on_delete=models.CASCADE, related_name='events',
        verbose_name='Олимпиада',
    )
    stage = models.ForeignKey(
        OlympiadStage, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='events', verbose_name='Этап',
    )
    academic_year = models.CharField('Учебный год', max_length=10)
    kind = models.CharField(
        'Что за событие', max_length=30, choices=Kind.choices,
        default=Kind.STAGE,
    )
    date_start = models.DateField('Дата начала', null=True, blank=True)
    date_end = models.DateField('Дата конца', null=True, blank=True)
    approx_text = models.CharField(
        'Ориентир словами', max_length=200, blank=True)
    date_status = models.CharField(
        'Статус даты', max_length=20, choices=DateStatus.choices,
        default=DateStatus.AWAITING,
    )
    region = models.CharField('Регион', max_length=200, blank=True)
    source = models.ForeignKey(
        FactSource, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='events', verbose_name='Источник',
    )

    class Meta:
        verbose_name = 'Событие олимпиады'
        verbose_name_plural = 'События олимпиад'
        ordering = ['date_start', 'olympiad']

    def __str__(self):
        return '{} · {} · {}'.format(
            self.olympiad, self.get_kind_display(), self.display_date)

    def clean(self):
        """Неподтверждённая дата не имеет права быть конкретной.

        Школьник читает число как факт и планирует по нему регистрацию.
        Поэтому правило стоит в модели, а не только в шаблоне: новый
        экран шаблон обойдёт, а `full_clean()` — нет.
        """
        if self.date_status == self.DateStatus.CONFIRMED:
            if self.date_start is None:
                raise ValidationError({
                    'date_start': 'Дата подтверждена — значит, число обязано быть.',
                })
        else:
            if self.date_start is not None:
                raise ValidationError({
                    'date_start': 'Дата не подтверждена — конкретное число '
                                  'показывать нельзя, напишите ориентир словами.',
                })
            if not self.approx_text.strip():
                raise ValidationError({
                    'approx_text': 'Дата не подтверждена — нужен ориентир словами.',
                })

    @property
    def display_date(self):
        """Как показать дату: «24 сентября, 2026» или ориентир словами."""
        if self.date_status == self.DateStatus.CONFIRMED and self.date_start:
            day = self.date_start
            return '{} {}, {}'.format(
                day.day, MONTHS_GENITIVE[day.month - 1], day.year)
        return self.approx_text

    @property
    def chip_label(self):
        """Подпись чипа типа события в ленте ближайших дат."""
        if self.kind == self.Kind.REGISTRATION_OPEN:
            return 'Регистрация'
        if self.kind == self.Kind.REGISTRATION_CLOSE:
            return 'До какого числа'
        if self.kind == self.Kind.RESULTS:
            return 'Результаты'
        return 'Тур'

    @property
    def is_confirmed(self):
        return self.date_status == self.DateStatus.CONFIRMED

    @property
    def status_word(self):
        """Короткая подпись статуса рядом с точкой: она стоит в карточке
        события, где длинное «Ориентировочно по прошлому году» не помещается.
        """
        if self.date_status == self.DateStatus.CONFIRMED:
            return 'дата подтверждена'
        if self.date_status == self.DateStatus.APPROX_LAST_YEAR:
            return 'ориентировочно'
        return 'ждём объявления'

    @property
    def day_number(self):
        """Крупное число дня — только у подтверждённой даты."""
        return self.date_start.day if self.is_confirmed and self.date_start else None

    @property
    def month_word(self):
        if self.is_confirmed and self.date_start:
            return MONTHS_GENITIVE[self.date_start.month - 1]
        return ''


class UniversityProgram(models.Model):
    """Программа вуза — строка в таблице льгот."""

    university_name = models.CharField('Вуз', max_length=200)
    university_short = models.CharField('Вуз кратко', max_length=50)
    university_logo = models.ImageField(
        'Логотип вуза', upload_to='olympiads/unilogos/', blank=True, null=True)
    program_name = models.CharField('Программа', max_length=300)
    city = models.CharField('Город', max_length=100, blank=True)
    admission_rules_url = models.URLField(
        'Правила приёма', max_length=500, blank=True)
    order = models.PositiveSmallIntegerField('Порядок', default=0)

    class Meta:
        verbose_name = 'Программа вуза'
        verbose_name_plural = 'Программы вузов'
        ordering = ['order', 'university_short']

    def __str__(self):
        return '{} — {}'.format(self.university_short, self.program_name)

    @property
    def abbr(self):
        source = (self.university_short or self.university_name).strip()
        return source[:4].upper()


class OlympiadBenefit(models.Model):
    """Льгота при поступлении: что даёт эта олимпиада на этой программе.

    `benefit_type='none'` — тоже запись, а не пробел: «здесь льготы нет» —
    это ответ на вопрос школьника, и молчание вместо него хуже.
    """

    class BenefitType(models.TextChoices):
        BVI = 'bvi', 'Без вступительных испытаний'
        SCORE_100 = 'score_100', '100 баллов за предмет'
        NONE = 'none', 'Льготы нет'

    olympiad = models.ForeignKey(
        Olympiad, on_delete=models.CASCADE, related_name='benefits',
        verbose_name='Олимпиада',
    )
    program = models.ForeignKey(
        UniversityProgram, on_delete=models.CASCADE, related_name='benefits',
        verbose_name='Программа',
    )
    admission_year = models.PositiveSmallIntegerField('Год поступления')
    benefit_type = models.CharField(
        'Что даёт', max_length=20, choices=BenefitType.choices,
        default=BenefitType.NONE,
    )
    score_100_subject = models.CharField(
        'Предмет для 100 баллов', max_length=100, blank=True)
    confirm_subject = models.CharField(
        'Предмет подтверждения ЕГЭ', max_length=100, blank=True)
    confirm_min_score = models.PositiveSmallIntegerField(
        'Минимум ЕГЭ', null=True, blank=True)
    required_level = models.PositiveSmallIntegerField(
        'Требуемый уровень', null=True, blank=True)
    grades_note = models.CharField('Классы', max_length=100, blank=True)
    source = models.ForeignKey(
        FactSource, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='benefits', verbose_name='Источник',
    )

    class Meta:
        verbose_name = 'Льгота'
        verbose_name_plural = 'Льготы'
        unique_together = ('olympiad', 'program', 'admission_year')
        ordering = ['program__order', 'olympiad']

    def __str__(self):
        return '{} · {} · {}'.format(
            self.olympiad, self.program, self.get_benefit_type_display())

    @property
    def gives_label(self):
        """Колонка «Что даёт» — человеческой строкой."""
        if self.benefit_type == self.BenefitType.BVI:
            return 'Без вступительных испытаний'
        if self.benefit_type == self.BenefitType.SCORE_100:
            subject = self.score_100_subject or 'профильному предмету'
            return '100 баллов по предмету «{}»'.format(subject)
        return 'Льготы нет'

    @property
    def confirm_label(self):
        """Колонка «Подтверждение ЕГЭ».

        У ВсОШ подтверждать не нужно — и это важное отличие, ради
        которого колонка и заведена.
        """
        if self.benefit_type == self.BenefitType.NONE:
            return '—'
        if not self.confirm_subject and self.confirm_min_score is None:
            return 'Не требуется'
        subject = self.confirm_subject or 'профильный предмет'
        if self.confirm_min_score is None:
            return subject
        return '{}, не ниже {}'.format(subject, self.confirm_min_score)


class OlympiadScore(models.Model):
    """Проходной или граничный балл за конкретный год и класс."""

    class ScoreType(models.TextChoices):
        PASS_TO_FINAL = 'pass_to_final', 'Проход на заключительный этап'
        WINNER = 'winner', 'На победителя'
        PRIZE = 'prize', 'На призёра'

    class Scope(models.TextChoices):
        FEDERAL = 'federal', 'Единый по стране'
        REGION = 'region', 'Региональный'

    olympiad = models.ForeignKey(
        Olympiad, on_delete=models.CASCADE, related_name='scores',
        verbose_name='Олимпиада',
    )
    stage = models.ForeignKey(
        OlympiadStage, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='scores', verbose_name='Этап',
    )
    year = models.PositiveSmallIntegerField('Год')
    grade = models.PositiveSmallIntegerField('Класс', null=True, blank=True)
    score_type = models.CharField(
        'Что за балл', max_length=20, choices=ScoreType.choices,
        default=ScoreType.PASS_TO_FINAL,
    )
    value = models.PositiveIntegerField('Балл')
    max_value = models.PositiveIntegerField(
        'Максимум', null=True, blank=True)
    scope = models.CharField(
        'Охват', max_length=20, choices=Scope.choices, default=Scope.FEDERAL)
    region = models.CharField('Регион', max_length=200, blank=True)
    source = models.ForeignKey(
        FactSource, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='scores', verbose_name='Источник',
    )

    class Meta:
        verbose_name = 'Проходной балл'
        verbose_name_plural = 'Проходные баллы'
        ordering = ['olympiad', 'grade', 'year']

    def __str__(self):
        return '{} · {} · {} класс · {}'.format(
            self.olympiad, self.year, self.grade, self.value)

    @property
    def share(self):
        """Доля от максимума — длина полоски в блоке анализа баллов."""
        if not self.max_value:
            return None
        return min(1.0, self.value / self.max_value)


class OlympiadVariant(models.Model):
    """Комплект заданий одного тура: год, этап, класс, ссылка на оригинал."""

    class OriginalSource(models.TextChoices):
        OFFICIAL = 'official', 'Официальный сайт'
        AGGREGATOR = 'aggregator', 'Агрегатор'
        NONE = 'none', 'Нет'

    olympiad = models.ForeignKey(
        Olympiad, on_delete=models.CASCADE, related_name='variants',
        verbose_name='Олимпиада',
    )
    stage = models.ForeignKey(
        OlympiadStage, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='variants', verbose_name='Этап',
    )
    year = models.PositiveSmallIntegerField('Год')
    grade = models.PositiveSmallIntegerField('Класс', null=True, blank=True)
    variant_label = models.CharField('Вариант', max_length=100, blank=True)
    problem_count = models.PositiveSmallIntegerField(
        'Заданий', null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(
        'Минут', null=True, blank=True)
    max_score = models.PositiveIntegerField(
        'Максимум баллов', null=True, blank=True)
    has_solutions = models.BooleanField('Есть разборы', default=False)
    original_url = models.URLField(
        'Ссылка на оригинал', max_length=800, blank=True)
    original_source = models.CharField(
        'Откуда оригинал', max_length=20, choices=OriginalSource.choices,
        default=OriginalSource.NONE,
    )
    ref_event_id = models.CharField(
        'ID тура в банке', max_length=200, blank=True,
        help_text='Соответствует problems.OlympiadRef.event_id',
    )
    source = models.ForeignKey(
        FactSource, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='variants', verbose_name='Источник',
    )

    class Meta:
        verbose_name = 'Комплект заданий'
        verbose_name_plural = 'Комплекты заданий'
        ordering = ['-year', 'olympiad', 'grade']

    def __str__(self):
        return '{} · {} · {}'.format(self.olympiad, self.year, self.stage or '')

    @property
    def has_original(self):
        return bool(self.original_url) and self.original_source != self.OriginalSource.NONE

    @property
    def grade_label(self):
        return '{} класс'.format(self.grade) if self.grade else 'все классы'


class RegionalCoordinator(models.Model):
    """Региональный организатор ВсОШ.

    Школьный и муниципальный этапы назначает регион своим приказом —
    единой даты по стране не существует, и адрес организатора для
    школьника важнее любого нашего текста.
    """

    region_name = models.CharField('Регион', max_length=200, unique=True)
    region_code = models.CharField('Код региона', max_length=10, blank=True)
    url = models.URLField('Страница организатора', max_length=800, blank=True)
    url_status = models.PositiveSmallIntegerField(
        'Код ответа', null=True, blank=True)
    url_checked_at = models.DateTimeField(
        'Ссылка проверена', null=True, blank=True)
    contact_note = models.TextField('Контакты', blank=True)
    is_verified = models.BooleanField('Проверено', default=False)

    class Meta:
        verbose_name = 'Региональный организатор'
        verbose_name_plural = 'Региональные организаторы'
        ordering = ['region_name']

    def __str__(self):
        return self.region_name


class FactUpdateProposal(models.Model):
    """Очередь изменений на подтверждение человеком.

    Фоновая проверка источников НИЧЕГО не перезаписывает сама: она кладёт
    расхождение сюда, а человек в админке принимает или отклоняет. Иначе
    одна опечатка на чужом сайте молча растеклась бы по разделу.
    """

    class Status(models.TextChoices):
        PENDING = 'pending', 'Ждёт решения'
        ACCEPTED = 'accepted', 'Принято'
        REJECTED = 'rejected', 'Отклонено'

    target_app = models.CharField('Приложение', max_length=50)
    target_model = models.CharField('Модель', max_length=50)
    target_pk = models.PositiveIntegerField('Ключ записи')
    field_name = models.CharField('Поле', max_length=100)
    old_value = models.TextField('Было', blank=True)
    new_value = models.TextField('Стало', blank=True)
    source = models.ForeignKey(
        FactSource, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='proposals', verbose_name='Источник',
    )
    status = models.CharField(
        'Статус', max_length=20, choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    reviewed_at = models.DateTimeField('Рассмотрено', null=True, blank=True)

    class Meta:
        verbose_name = 'Предложение правки факта'
        verbose_name_plural = 'Предложения правок фактов'
        ordering = ['status', '-created_at']

    def __str__(self):
        return '{}.{} #{} · {}'.format(
            self.target_app, self.target_model, self.target_pk, self.field_name)
