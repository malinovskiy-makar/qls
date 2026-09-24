# -*- coding: utf-8 -*-
"""Формы аккаунта: регистрация, данные профиля, аватар.

⚠️ ПАРОЛЬ ЧЕРЕЗ НАШ КОД НЕ ПРОХОДИТ. Регистрация наследует
`UserCreationForm`, смена пароля — `SetPasswordForm`; своих полей пароля,
своей проверки и своего хеширования здесь нет и быть не должно. Валидаторы
(длина 10, распространённые, похожесть на логин) стоят в настройках и
применяются формами сами.
"""
import io
import re

from django import forms
from django.contrib.auth.forms import UserCreationForm
from PIL import Image, ImageOps, UnidentifiedImageError

from .models import User
from .models_platform import UserProfile

# ── Аватар: пределы ─────────────────────────────────────────────────────
#
# ⚠️ ПРОВЕРЯЕМ ДО ТОГО, КАК ОТКРЫТЬ КАРТИНКУ. Pillow разворачивает
# изображение в память: файл 100×100 после сжатия может быть «бомбой» на
# 30 000×30 000 пикселей. Поэтому сначала размер файла, потом размеры в
# пикселях, и только потом обработка.
AVATAR_MAX_BYTES = 3 * 1024 * 1024      # 3 МБ
AVATAR_MAX_SIDE = 4000                  # 4000×4000 пикселей на входе
AVATAR_SIZE = 256                       # квадрат на выходе
AVATAR_QUALITY = 85


class RegisterForm(UserCreationForm):
    """Регистрация: логин, пароль дважды, роль и согласие.

    Почты нет намеренно (решение владельца 04.09.2026): подтверждать её
    нечем — рассылки у платформы нет, а непроверенная почта в базе создаёт
    ложное чувство, что человека можно найти.
    """

    ROLE_CHOICES = (
        ('student', 'Я ученик'),
        ('tutor', 'Я преподаватель'),
    )

    role = forms.ChoiceField(
        label='Кто вы',
        choices=ROLE_CHOICES,
        initial='student',
        widget=forms.RadioSelect,
    )
    consent = forms.BooleanField(
        label='Согласен на обработку персональных данных',
        required=True,
        error_messages={'required': 'Без согласия зарегистрировать нельзя.'},
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'Логин'
        self.fields['username'].help_text = (
            'Им вы входите, и он же виден на сайте, пока не заполнено имя.')
        self.fields['password1'].label = 'Пароль'
        self.fields['password2'].label = 'Пароль ещё раз'
        for field in self.fields.values():
            field.widget.attrs.setdefault('autocomplete', 'off')

    def clean_username(self):
        """⚠️ ЗАНЯТЫЙ ЛОГИН НАЗЫВАЕТСЯ ЧЕСТНО, И ЭТО НЕ ОПЛОШНОСТЬ.

        На ВХОДЕ мы намеренно не говорим, существует ли аккаунт: там это
        подсказка подбирающему. На РЕГИСТРАЦИИ молчать нельзя — человеку
        надо знать, почему не получилось. Занятость логина всё равно
        выясняется за одну попытку регистрации, так что скрывать нечего.
        """
        username = self.cleaned_data['username']
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('Этот логин занят. Придумайте другой.')
        return username


class KnownCodesField(forms.MultipleChoiceField):
    """Галочки списком кодов; неизвестный код молча отбрасывается.

    Штатное поле на чужой код валит ВСЮ форму — человек теряет имя и класс
    из-за устаревшей галочки в кэше страницы. Необязательный самоотчёт
    того не стоит.
    """

    def clean(self, value):
        known = {code for code, _ in self.choices}
        return [v for v in dict.fromkeys(self.to_python(value)) if v in known]


class ProfileForm(forms.ModelForm):
    """Данные профиля. Роль здесь не меняется — она про права.

    ⚠️ ТЕЛЕФОНА В ФОРМЕ НЕТ С 22.09.2026 (решение владельца): поле модели
    осталось, уже собранные номера лежат, но ни собрать, ни показать их эта
    форма не может. Возвращать `'phone'` в `Meta.fields` нельзя.
    """

    first_name = forms.CharField(label='Имя', max_length=150, required=False)
    last_name = forms.CharField(label='Фамилия', max_length=150, required=False)
    # Прежний «Логин»: имя осталось тем же, подпись стала человеческой.
    # ⚠️ `form="pf-data-form"`: на странице поле стоит рядом с аватаркой, ВНЕ
    # формы данных, и без атрибута браузер его не отправляет (24.09.2026).
    username = forms.CharField(
        label='Имя пользователя', max_length=150,
        widget=forms.TextInput(attrs={'form': 'pf-data-form'}))
    email = forms.EmailField(
        label='Почта', required=False,
        help_text='Необязательно, не подтверждается, нужно только для связи.')
    telegram = forms.CharField(
        label='Telegram', required=False, max_length=64,
        widget=forms.TextInput(attrs={'placeholder': '@username'}))

    # Множественный выбор — списком кодов. Варианты живут в модели, форма
    # их только читает.
    prep_mode = KnownCodesField(
        label='Способ подготовки', choices=UserProfile.PREP_MODES,
        widget=forms.CheckboxSelectMultiple, required=False)
    olympiad_history = KnownCodesField(
        label='Какие олимпиады уже писал', choices=UserProfile.OLYMPIAD_HISTORY,
        widget=forms.CheckboxSelectMultiple, required=False)

    class Meta:
        model = UserProfile
        fields = ('grade', 'school', 'city', 'level', 'goal', 'prep_mode',
                  'hours_week', 'source_channel', 'olympiad_history', 'telegram')

    #: Подписи полей на вкладке «Аккаунт» (ТЗ владельца 22.09.2026).
    #: ⚠️ Меняются ТОЛЬКО в форме: `verbose_name` модели — имя поля в админке
    #: и в выгрузке, и переписывать его ради экрана нельзя.
    LABELS = {
        'olympiad_history': 'Какие олимпиады уже писал',
        'source_channel': 'Откуда вы узнали о Weconomics',
        'goal': 'Цель на ближайший учебный год',
        'hours_week': 'Часов в неделю на олимпиадную экономику',
        'level': 'Уровень подготовки',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = self.instance.user
        self.fields['first_name'].initial = user.first_name
        self.fields['last_name'].initial = user.last_name
        self.fields['username'].initial = user.username
        self.fields['email'].initial = user.email
        self.fields['grade'].required = False
        self.fields['school'].required = False
        self.fields['goal'].widget.attrs.setdefault(
            'placeholder', 'Например: призёр регионального этапа')
        for name, label in self.LABELS.items():
            self.fields[name].label = label
        # Одиночный выбор — радиокнопками внутри своего выпадающего списка:
        # закрытое состояние рисует сервер, а форма остаётся обычной формой.
        # Пустой вариант — «Не выбрано», а не прочерк Django.
        for name in ('grade', 'hours_week', 'source_channel'):
            self.fields[name].choices = [('', 'Не выбрано')] + [
                c for c in self.fields[name].choices if c[0]]
            self.fields[name].widget = forms.RadioSelect(
                choices=self.fields[name].choices)
        self.fields['level'].choices = [('', 'Не выбрано')] + list(
            UserProfile.Level.choices)
        self.fields['level'].widget = forms.RadioSelect(
            choices=self.fields['level'].choices)
        if self.instance.telegram:
            self.initial['telegram'] = '@' + self.instance.telegram

    @staticmethod
    def _known_codes(values, choices):
        known = {code for code, _ in choices}
        return [v for v in values if v in known]

    def clean_prep_mode(self):
        return self._known_codes(self.cleaned_data.get('prep_mode') or [],
                                 UserProfile.PREP_MODES)

    def clean_olympiad_history(self):
        return self._known_codes(self.cleaned_data.get('olympiad_history') or [],
                                 UserProfile.OLYMPIAD_HISTORY)

    #: Что люди приносят вместо ника: адрес канала, ссылка, собачка, пробелы.
    _TELEGRAM_PREFIXES = ('https://', 'http://', 'www.', 't.me/', 'telegram.me/')
    _TELEGRAM_RE = re.compile(r'^[A-Za-z0-9_]{5,32}$')

    def clean_telegram(self):
        """Ник без «@» и без адреса: хранится голым, показывается с собачкой.

        Нормализуем, а не отбраковываем: человек копирует из Telegram ссылку
        целиком, и отказ «неверный формат» был бы придиркой.
        """
        value = (self.cleaned_data.get('telegram') or '').strip()
        changed = True
        while changed and value:
            changed = False
            for prefix in self._TELEGRAM_PREFIXES:
                if value.lower().startswith(prefix):
                    value = value[len(prefix):]
                    changed = True
            if value.startswith('@'):
                value = value.lstrip('@')
                changed = True
        value = value.strip().rstrip('/')
        if not value:
            return ''
        if not self._TELEGRAM_RE.match(value):
            raise forms.ValidationError(
                'Ник в Telegram: 5–32 символа, латинские буквы, цифры и подчёркивание.')
        return value

    def clean_username(self):
        """Логин можно менять, но он остаётся уникальным."""
        username = self.cleaned_data['username'].strip()
        User._meta.get_field('username').run_validators(username)
        clash = (User.objects.filter(username__iexact=username)
                 .exclude(pk=self.instance.user_id).exists())
        if clash:
            raise forms.ValidationError('Этот логин занят. Придумайте другой.')
        return username

    def save(self, commit=True):
        profile = super().save(commit=commit)
        user = profile.user
        user.first_name = self.cleaned_data['first_name'].strip()
        user.last_name = self.cleaned_data['last_name'].strip()
        user.username = self.cleaned_data['username']
        user.email = self.cleaned_data['email']
        if commit:
            user.save(update_fields=['first_name', 'last_name', 'username',
                                     'email'])
        return profile


class AvatarForm(forms.Form):
    """Загрузка аватара. Пересжимает и переименовывает — всегда.

    ⚠️ ИЗ ЗАГРУЖЕННОГО ФАЙЛА НЕ БЕРЁТСЯ НИЧЕГО: ни имя, ни тип, ни
    метаданные. На диск попадает наш собственный JPEG 256×256 под именем
    `avatars/<id пользователя>.jpg`. Так у загрузчика нет способа ни
    подсунуть путь, ни оставить в файле что-то исполняемое, ни спрятать в
    EXIF геометку — пересохранение её стирает.
    """

    avatar = forms.ImageField(label='Аватар')
    # Квадрат, который человек выбрал сам в окне обрезки, в пикселях
    # ИСХОДНОЙ картинки (после поворота по EXIF — так её видит браузер).
    # Не пришли или пришли не все три — режем по центру, как раньше.
    crop_x = forms.IntegerField(required=False, min_value=0)
    crop_y = forms.IntegerField(required=False, min_value=0)
    crop_size = forms.IntegerField(required=False, min_value=0)

    def clean_avatar(self):
        uploaded = self.cleaned_data['avatar']
        if uploaded.size > AVATAR_MAX_BYTES:
            raise forms.ValidationError(
                'Файл больше 3 МБ. Возьмите картинку поменьше.')
        try:
            probe = Image.open(uploaded)
            probe.verify()          # только проверка целостности
        except (UnidentifiedImageError, OSError, ValueError):
            raise forms.ValidationError('Это не картинка.')
        # ⚠️ ПОСЛЕ verify() ФАЙЛ ЧИТАТЬ НЕЛЬЗЯ — Pillow требует открыть заново.
        uploaded.seek(0)
        image = Image.open(uploaded)
        if image.width > AVATAR_MAX_SIDE or image.height > AVATAR_MAX_SIDE:
            raise forms.ValidationError(
                'Картинка больше 4000×4000. Возьмите поменьше.')
        uploaded.seek(0)
        return uploaded

    #: Меньше этого квадрат не бывает: из 5×5 пикселей аватарки не выйдет.
    CROP_MIN_SIDE = 32

    def _crop_box(self, width, height):
        """Квадрат обрезки: выбранный человеком или по центру.

        ⚠️ КООРДИНАТЫ ПРИХОДЯТ ОТ КЛИЕНТА, И ЭТО НОРМАЛЬНО: они ничего не
        открывают, а только выбирают кусок уже загруженной картинки. Поэтому
        их не отвергаем, а ПРИЖИМАЕМ к границам — кривое число даёт не 500, а
        край картинки (docs/SECURITY.md).
        """
        left = self.cleaned_data.get('crop_x')
        top = self.cleaned_data.get('crop_y')
        size = self.cleaned_data.get('crop_size')
        if left is None or top is None or size is None:
            side = min(width, height)
            return (width - side) // 2, (height - side) // 2, side
        side = max(self.CROP_MIN_SIDE, min(size, width, height))
        left = min(max(0, left), width - side)
        top = min(max(0, top), height - side)
        return left, top, side

    def squared_jpeg(self):
        """Квадрат 256×256: выбранный человеком или по центру, JPEG без метаданных."""
        uploaded = self.cleaned_data['avatar']
        uploaded.seek(0)
        # ⚠️ ПОВОРОТ ПО EXIF — ДО ОБРЕЗКИ И ОБЯЗАТЕЛЬНО. Снимки с телефона
        # хранят поворот в EXIF: браузер показывает их уже повёрнутыми, и
        # координаты квадрата приходят в повёрнутой системе. Без поворота на
        # сервере квадрат вырезался бы не там — а заодно чинятся «лежащие»
        # аватарки с телефона.
        image = ImageOps.exif_transpose(Image.open(uploaded)).convert('RGB')

        left, top, side = self._crop_box(image.width, image.height)
        image = image.crop((left, top, left + side, top + side))
        image = image.resize((AVATAR_SIZE, AVATAR_SIZE), Image.LANCZOS)

        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=AVATAR_QUALITY, optimize=True)
        buffer.seek(0)
        return buffer
