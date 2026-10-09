# -*- coding: utf-8 -*-
"""Тестовые пользователи для ручной проверки правового контура (локально).

Запуск (PowerShell, из корня проекта; пароль берётся из окружения и нигде не пишется):

    $env:CHECK_PASSWORD = "<пароль для тестовых аккаунтов>"
    venv313\Scripts\python.exe manage.py shell -c "exec(open('scripts/legal/make_check_user.py', encoding='utf-8').read())"

Создаёт (или обновляет) двух учеников:
  check_old – НИКАКИХ записей согласия: на первом входе экран «Правила обработки данных»;
  check_ai  – согласия на документы и на помощника даны, на первой опубликованной задаче
              есть одна реплика чата: видно, что отзыв согласия её удаляет.

⚠️ Только для локальной базы. Тестовые пароли публично известны (CLAUDE.md): перед показом
кому-либо `manage.py lockdown_dev_accounts --apply`.
"""
import os

from django.contrib.auth import get_user_model

from legal import consent
from problems.models import Problem
from problems.models_legal import ConsentRecord
from problems.models_platform import ChatTurn, UserProfile

password = os.environ.get('CHECK_PASSWORD', '')
if len(password) < 8:
    raise SystemExit('Задайте $env:CHECK_PASSWORD (не короче 8 знаков) и повторите.')

User = get_user_model()
for name in ('check_old', 'check_ai'):
    user, created = User.objects.get_or_create(username=name)
    user.set_password(password)
    user.save()
    UserProfile.objects.update_or_create(user=user, defaults={'role': 'student'})
    ConsentRecord.objects.filter(user=user).delete()
    print(name, 'создан' if created else 'обновлён')

ai_user = User.objects.get(username='check_ai')
consent.grant(ai_user, ConsentRecord.Kind.PD, ConsentRecord.Source.REGISTER)
consent.grant(ai_user, ConsentRecord.Kind.AI, ConsentRecord.Source.CHAT)
problem = Problem.objects.filter(status='published').order_by('pk').first()
ChatTurn.objects.filter(user=ai_user).delete()
ChatTurn.objects.create(user=ai_user, problem=problem, user_text='Проверка: эта реплика исчезнет после отзыва согласия')
print('check_ai: согласия pd и ai даны; реплика чата на задаче №%d' % problem.pk)
