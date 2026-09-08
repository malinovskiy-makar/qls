# -*- coding: utf-8 -*-
"""`dev_scrub` — вычистить людей с площадки dev, не тронув банк задач.

⚠️ ГЛАВНОЕ, ЧТО СТОРОЖИТ ЭТОТ НАБОР, — ПРЕДОХРАНИТЕЛЬ. База площадки
`dev.weconomics.ai` — это копия БОЕВОЙ базы, и команда, которая удаляет всех
пользователей, отличается от катастрофы ровно одной проверкой: `SITE_ENV`
обязан быть `dev`. Запуск той же команды в боевом контейнере (где `SITE_ENV`
равно `prod`) обязан ОТКАЗАТЬСЯ работать до единого удаления.

⚠️ ВТОРОЕ — ЧТО БАНК ЗАДАЧ ПЕРЕЖИВАЕТ УДАЛЕНИЕ ЛЮДЕЙ. У `Problem.owner`
стоит `SET_NULL`, но полагаться на «я посмотрел модель» нельзя: одно
изменение `on_delete` на `CASCADE` в чужой ветке — и `dev_scrub` унесёт
корпус. Поэтому число задач до и после сверяется и тестом, и самой командой.
"""
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from io import StringIO

from problems.models import (
    Assignment, CatalogAttempt, Problem, StudentGroup, User,
)
from problems.models_gamification import ParentLink
from game.models import GameResult, GameSet
from problems.models_platform import LearningEvent, UserProfile


def _данные():
    """Три человека, задача, попытка, событие, группа, домашка."""
    учитель = User.objects.create_user(
        username='real-teacher', password='x', role=User.Role.TEACHER)
    ученик = User.objects.create_user(
        username='real-student', password='x', role=User.Role.STUDENT)
    ещё = User.objects.create_user(
        username='real-student-2', password='x', role=User.Role.STUDENT)
    задача = Problem.objects.create(
        title='Задача банка', statement='Условие', owner=учитель)
    CatalogAttempt.objects.create(user=ученик, problem=задача)
    LearningEvent.objects.create(
        user=ученик, source=LearningEvent.Source.CATALOG,
        event_type=LearningEvent.EventType.SOLVED)
    группа = StudentGroup.objects.create(name='Группа', teacher=учитель)
    группа.students.add(ученик, ещё)
    Assignment.objects.create(name='Домашка', author=учитель)

    # ⚠️ АНОНИМНАЯ АКТИВНОСТЬ — БЕЗ ПОЛЬЗОВАТЕЛЯ, И ЭТО ГЛАВНОЕ В ФИКСТУРЕ.
    # 07.09.2026 первая заливка площадки оставила 48 272 события: у
    # `LearningEvent.user` стоит null=True (тренажёр работает без входа), и
    # удаление людей такие строки не трогает. Прежняя фикстура этого не
    # ловила — в ней ВСЯ активность была привязана к ученику.
    LearningEvent.objects.create(
        user=None, session_key='anon-session-key',
        source=LearningEvent.Source.GAME,
        event_type=LearningEvent.EventType.SOLVED)
    набор = GameSet.objects.create(code='devscrub1', mode='classic',
                                   author=учитель)
    # `GameResult.user` — SET_NULL: строка переживает удаление владельца и
    # остаётся в таблице рекордов без единого признака, чья она.
    GameResult.objects.create(code='res-user', game_set=набор, user=ученик,
                              mode='classic', score=10)
    GameResult.objects.create(code='res-anon', game_set=набор, user=None,
                              mode='classic', score=20)
    # ⚠️ Результат БЕЗ НАБОРА И БЕЗ ЧЕЛОВЕКА. У `game_set` стоит CASCADE, но
    # `null=True`: удаление наборов такую строку не уносит, а удаление людей
    # — тем более. Без неё проверка проходила бы «по неправильной причине»:
    # результаты исчезали бы каскадом за наборами, и забудь мы GameResult в
    # списке, никто бы этого не заметил.
    GameResult.objects.create(code='res-orphan', game_set=None, user=None,
                              mode='classic', score=30)
    return задача


class DevScrubGuardTests(TestCase):
    """Предохранитель: без `SITE_ENV=dev` команда не делает ничего."""

    @override_settings(SITE_ENV='prod')
    def test_на_бою_команда_отказывается(self):
        _данные()
        было = User.objects.count()
        with self.assertRaises(CommandError) as ловушка:
            call_command('dev_scrub', '--yes', stdout=StringIO())
        self.assertIn('SITE_ENV', str(ловушка.exception))
        self.assertEqual(User.objects.count(), было,
                         'команда удаляла людей на боевых настройках')

    @override_settings(SITE_ENV='dev', DEV_ACCOUNTS_PASSWORD='dev-probe-2026')
    def test_без_yes_только_план(self):
        _данные()
        было = User.objects.count()
        поток = StringIO()
        call_command('dev_scrub', stdout=поток)
        self.assertEqual(User.objects.count(), было,
                         'без --yes команда всё-таки удаляла')
        вывод = поток.getvalue()
        self.assertIn('--yes', вывод, 'план не объясняет, как запустить по-настоящему')

    @override_settings(SITE_ENV='dev', DEV_ACCOUNTS_PASSWORD='')
    def test_пустой_пароль_отказ(self):
        _данные()
        было = User.objects.count()
        with self.assertRaises(CommandError) as ловушка:
            call_command('dev_scrub', '--yes', stdout=StringIO())
        self.assertIn('DEV_ACCOUNTS_PASSWORD', str(ловушка.exception))
        self.assertEqual(User.objects.count(), было)


@override_settings(SITE_ENV='dev', DEV_ACCOUNTS_PASSWORD='dev-probe-2026')
class DevScrubWorkTests(TestCase):
    """Боевой прогон на площадке: людей нет, банк на месте, роли заведены.

    ⚠️ ГОСТЯ СРЕДИ АККАУНТОВ НЕТ НАМЕРЕННО. Гость — это разлогиненный
    браузер, а не пятый логин: аккаунт «dev-guest» был бы вошедшим
    пользователем с пустыми правами и проверял бы не то, что нужно.
    Гостевой вид проверяется окном инкогнито.
    """

    def setUp(self):
        self.задача = _данные()
        self.задач_было = Problem.objects.count()
        call_command('dev_scrub', '--yes', stdout=StringIO())

    def test_остаются_ровно_четыре_аккаунта(self):
        логины = sorted(User.objects.values_list('username', flat=True))
        self.assertEqual(
            логины, ['dev-admin', 'dev-parent', 'dev-student', 'dev-teacher'])

    def test_у_каждого_своя_роль(self):
        """Роль профиля и подтянутая из неё роль пользователя — обе.

        Соответствие задано в `PROFILE_ROLE_TO_USER_ROLE`: tutor→teacher,
        student→student, parent→viewer. Проверяем обе стороны: шапку
        строит `User.role`, а кабинет — `UserProfile.role`, и разойтись
        они не должны.
        """
        ожидание = {
            'dev-student': (UserProfile.Role.STUDENT, User.Role.STUDENT),
            'dev-teacher': (UserProfile.Role.TUTOR, User.Role.TEACHER),
            'dev-parent': (UserProfile.Role.PARENT, User.Role.VIEWER),
        }
        for логин, (роль_профиля, роль_юзера) in ожидание.items():
            with self.subTest(логин=логин):
                человек = User.objects.get(username=логин)
                self.assertEqual(человек.profile.role, роль_профиля)
                self.assertEqual(человек.role, роль_юзера)

    def test_админ_суперпользователь_и_видит_админку(self):
        админ = User.objects.get(username='dev-admin')
        self.assertTrue(админ.is_superuser)
        self.assertTrue(админ.is_staff)
        # ⚠️ Роль админа проверяем отдельно: `sync_user_role` НЕ трогает
        # суперпользователя, поэтому она проставлена явно. Забудь мы это —
        # осталось бы значение по умолчанию `student`, и админ видел бы в
        # шапке меню ученика.
        self.assertEqual(админ.role, User.Role.TEACHER)
        self.assertTrue(self.client.login(username='dev-admin',
                                          password='dev-probe-2026'))
        ответ = self.client.get('/admin/')
        self.assertEqual(ответ.status_code, 200)

    def test_родитель_привязан_к_ученику(self):
        родитель = User.objects.get(username='dev-parent')
        ученик = User.objects.get(username='dev-student')
        self.assertTrue(
            ParentLink.objects.filter(parent=родитель, student=ученик).exists())
        # Экраны спрашивают «чьи дети» у профиля — проверяем тем же путём.
        self.assertIn(ученик, list(родитель.profile.children()))

    def test_ученик_состоит_в_группе_учителя(self):
        учитель = User.objects.get(username='dev-teacher')
        ученик = User.objects.get(username='dev-student')
        группа = StudentGroup.objects.get(teacher=учитель)
        self.assertEqual(группа.name, 'dev-группа')
        self.assertIn(ученик, list(группа.students.all()))
        # Код приглашения выдаёт сама модель — своего генератора у команды
        # быть не должно.
        self.assertRegex(группа.invite_code, r'^[A-Z2-9]{4}-[A-Z2-9]{4}$')

    def test_пароль_из_переменной_работает_у_всех(self):
        for логин in ('dev-student', 'dev-teacher', 'dev-parent', 'dev-admin'):
            with self.subTest(логин=логин):
                self.client.logout()
                self.assertTrue(self.client.login(username=логин,
                                                  password='dev-probe-2026'))

    def test_банк_задач_на_месте(self):
        self.assertEqual(Problem.objects.count(), self.задач_было)
        self.assertTrue(Problem.objects.filter(pk=self.задача.pk).exists())

    def test_личное_вычищено(self):
        self.assertEqual(CatalogAttempt.objects.count(), 0)
        self.assertEqual(LearningEvent.objects.count(), 0)
        self.assertEqual(GameResult.objects.count(), 0)
        self.assertEqual(GameSet.objects.count(), 0)
        # Осталась ровно одна группа — та, что завела сама команда.
        self.assertEqual(StudentGroup.objects.count(), 1)
        # Домашка переживает удаление автора (`author` = SET_NULL), поэтому
        # её сносит явный список команды, а не каскад. Проверка сторожит
        # именно это: забыв модель в списке, мы оставили бы на площадке
        # чужие домашние задания без единого признака владельца.
        self.assertEqual(Assignment.objects.count(), 0)

    def test_повторный_прогон_даёт_то_же_самое(self):
        """Идемпотентность: старые dev-аккаунты сносятся и заводятся заново.

        ⚠️ Это не формальность. `dev_refresh.sh` зовёт команду после каждой
        заливки дампа, а владелец может запустить её и просто так. Второй
        прогон обязан дать ТУ ЖЕ картину, а не удвоить группы и не упасть на
        занятом логине.
        """
        call_command('dev_scrub', '--yes', stdout=StringIO())
        self.assertEqual(User.objects.count(), 4)
        self.assertEqual(StudentGroup.objects.count(), 1)
        self.assertEqual(ParentLink.objects.count(), 1)
        self.assertEqual(Problem.objects.count(), self.задач_было)
        self.assertEqual(
            sorted(User.objects.values_list('username', flat=True)),
            ['dev-admin', 'dev-parent', 'dev-student', 'dev-teacher'])

    def test_анонимная_активность_тоже_вычищена(self):
        """Активность без пользователя удаление людей НЕ уносит.

        ⚠️ Проверка заведена по настоящей поломке. Первая заливка площадки
        07.09.2026 оставила 48 272 события: тренажёр и каталог работают без
        входа, такие строки хранят только ключ сессии, и каскад за
        пользователем до них не доходит. Это ровно та персональная
        активность, которой на площадке с общим паролем быть не должно.
        """
        self.assertFalse(
            LearningEvent.objects.filter(user__isnull=True).exists(),
            'на площадке остались анонимные события с ключами сессий')
        self.assertFalse(
            GameResult.objects.filter(user__isnull=True).exists(),
            'на площадке остались результаты забегов без владельца')
