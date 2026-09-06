# -*- coding: utf-8 -*-
"""Формы аккаунта: регистрация, данные профиля, аватар.

⚠️ ПАРОЛЬ ЧЕРЕЗ НАШ КОД НЕ ПРОХОДИТ. Регистрация наследует
`UserCreationForm`, смена пароля — `SetPasswordForm`; своих полей пароля,
своей проверки и своего хеширования здесь нет и быть не должно. Валидаторы
(длина 10, распространённые, похожесть на логин) стоят в настройках и
применяются формами сами.
"""
import io

from django import forms
from django.contrib.auth.forms import UserCreationForm
from PIL import Image, UnidentifiedImageError

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


class ProfileForm(forms.ModelForm):
    """Данные профиля. Роль здесь не меняется — она про права."""

    first_name = forms.CharField(label='Имя', max_length=150, required=False)
    last_name = forms.CharField(label='Фамилия', max_length=150, required=False)
    username = forms.CharField(label='Логин', max_length=150)
    email = forms.EmailField(
        label='Почта', required=False,
        help_text='Необязательно, не подтверждается, нужно только для связи.')

    class Meta:
        model = UserProfile
        fields = ('grade', 'school', 'level', 'phone')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = self.instance.user
        self.fields['first_name'].initial = user.first_name
        self.fields['last_name'].initial = user.last_name
        self.fields['username'].initial = user.username
        self.fields['email'].initial = user.email
        self.fields['grade'].required = False
        self.fields['school'].required = False

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

    def squared_jpeg(self):
        """Квадрат 256×256 с обрезкой по центру, JPEG без метаданных."""
        uploaded = self.cleaned_data['avatar']
        uploaded.seek(0)
        image = Image.open(uploaded)
        image = image.convert('RGB')

        side = min(image.width, image.height)
        left = (image.width - side) // 2
        top = (image.height - side) // 2
        image = image.crop((left, top, left + side, top + side))
        image = image.resize((AVATAR_SIZE, AVATAR_SIZE), Image.LANCZOS)

        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=AVATAR_QUALITY, optimize=True)
        buffer.seek(0)
        return buffer
