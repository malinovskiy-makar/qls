"""
«Адреса» сайта (маршруты).
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.contrib.auth.views import LogoutView
from django.urls import include, path
from django.views.generic import RedirectView

from catalog import views as catalog_views
from problems import views_parent, views_platform, views_stats
from config.csp_report import csp_report
from config.health import health, healthz
from problems import views_auth
from problems.views_auth import RoleBasedLoginView

urlpatterns = [
    # Главная страница сайта: статистика, поиск, навигация.
    path('', catalog_views.home, name='home'),
    path('admin/', admin.site.urls),
    # Куда браузер шлёт нарушения Content-Security-Policy. Политика идёт в
    # режиме отчёта: она ничего не блокирует, но рассказывает, что заблокировал
    # бы боевой режим. См. config/security_headers.py.
    path('csp-report/', csp_report, name='csp_report'),

    # ⚠️ Наружу через nginx НЕ выставляется: сюда ходит только
    # healthcheck контейнера по внутренней сети Docker.
    path('healthz/', healthz, name='healthz'),
    # Публичная проверка живости для внешнего мониторинга — без авторизации,
    # без подробностей об ошибке. См. config/health.py.
    path('health/', health, name='health'),
    # Логин / логаут.
    path('login/', RoleBasedLoginView.as_view(), name='login'),
    path('register/', views_auth.RegisterView.as_view(), name='register'),
    # ⚠️ ВЫХОД ВЕДЁТ НА ГЛАВНУЮ, А НЕ НА ФОРМУ ВХОДА (04.09.2026). Человек
    # нажал «Выйти» — он закончил, а не собирается войти снова. Главная
    # открыта гостям. Метод только POST: так решил Django 5, и шапка шлёт
    # форму (прежняя GET-ссылка отдавала 405 — это и была «ошибка выхода»).
    path('logout/', LogoutView.as_view(next_page='/'), name='logout'),
    # Учебник — заглушка «Скоро»: раздел пишется, но пункт в шапке нужен уже
    # на бете, иначе о нём не узнают.
    path('textbook/', catalog_views.textbook, name='textbook'),
    # ⚠️ СМЕНА ПАРОЛЯ ЖИВЁТ ВО ВКЛАДКЕ «БЕЗОПАСНОСТЬ» ПРОФИЛЯ (04.09.2026,
    # ADR 0073) и спрашивает только новый пароль дважды. Отдельные страницы
    # `password/change/` и `.../done/` остаются РЕДИРЕКТАМИ ради закладок и
    # чужих ссылок: адрес, который был, отвечать не перестал.
    # Формы Django по-прежнему делают всю работу — своей формы пароля у нас
    # нет и быть не должно.
    path('password/change/', views_platform.password_change,
         name='password_change'),
    path('password/change/done/', RedirectView.as_view(
        url='/profile/?tab=security', permanent=False),
        name='password_change_done'),

    # Платформа: профиль, сохранённое, папки.
    path('profile/', views_platform.profile, name='profile'),
    # Аватар: путь к файлу — из поля модели, из запроса только номер.
    path('profile/avatar/<int:user_id>/', views_platform.avatar, name='avatar'),
    # Статистика ученика — с геймификацией. Старая страница «Прогресс»
    # ПОГЛОЩЕНА этой: /student/progress/ ведёт сюда редиректом.
    path('profile/stats/', views_stats.student_stats, name='student_stats'),
    path('profile/stats/data/', views_stats.student_stats_json,
         name='student_stats_json'),
    path('profile/stats/goal/', views_stats.set_weekly_goal,
         name='set_weekly_goal'),
    # Кабинет родителя — без геймификации и без единого показателя работы
    # репетитора (см. problems/views_parent.py).
    path('parent/', views_parent.parent_home, name='parent_home'),
    path('parent/<int:pk>/', views_parent.parent_student,
         name='parent_student'),
    path('api/saved/problem/', views_platform.api_save_problem,
         name='api_save_problem'),
    path('api/folders/create/', views_platform.api_folder_create,
         name='api_folder_create'),
    path('api/folders/rename/', views_platform.api_folder_rename,
         name='api_folder_rename'),
    path('api/saved/move/', views_platform.api_saved_move,
         name='api_saved_move'),
    path('api/saved/delete/', views_platform.api_saved_delete,
         name='api_saved_delete'),
    # Приём графика от калькулятора (Фаза 19.2 — серверная половина).
    path('api/graphs/save/', views_platform.api_graph_save,
         name='api_graph_save'),
    # Этап В1 — Кабинет ученика.
    path('student/', include('student.urls')),
    # Этап В2–В4 — Панель учителя.
    path('teacher/', include('teacher.urls')),
    # Этап Е — Собственный графический движок (D3 + Math.js), новый калькулятор.
    path('calc2/', include('calc2.urls')),
    # Этап А — Публичный каталог задач.
    path('catalog/', include('catalog.urls')),
    # Этап Е — Заглушка календаря.
    path('calendar/', include('calendar_stub.urls')),
    # Игра Econ Rush (публичная, без логина).
    path('game/', include('game.urls')),
    # Справочник олимпиад: даты туров, льготы вузов, комплекты заданий.
    path('olympiads/', include('olympiads.urls')),
]

# В режиме разработки показываем загруженные файлы (картинки, PDF).
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
