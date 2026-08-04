"""
«Адреса» сайта (маршруты).
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.contrib.auth.views import LogoutView
from django.urls import include, path

from catalog import views as catalog_views
from problems import views_platform
from problems.views_auth import RoleBasedLoginView

urlpatterns = [
    # Главная страница сайта: статистика, поиск, навигация.
    path('', catalog_views.home, name='home'),
    path('admin/', admin.site.urls),
    # Логин / логаут.
    path('login/', RoleBasedLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(next_page='/login/'), name='logout'),
    # Смена пароля — штатными формами Django. Свою форму не пишем: пароль
    # не должен проходить через наш код ни в каком виде.
    path('password/change/', auth_views.PasswordChangeView.as_view(
        success_url='/password/change/done/'), name='password_change'),
    path('password/change/done/', auth_views.PasswordChangeDoneView.as_view(),
         name='password_change_done'),

    # Платформа: профиль, сохранённое, папки.
    path('profile/', views_platform.profile, name='profile'),
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
    # Этап 6а — Графический калькулятор Desmos.
    path('desmos/', include('graphs.urls')),
    # Этап Е — Собственный графический движок (D3 + Math.js), новый калькулятор.
    path('calc2/', include('calc2.urls')),
    # Этап А — Публичный каталог задач.
    path('catalog/', include('catalog.urls')),
    # Этап Е — Заглушка календаря.
    path('calendar/', include('calendar_stub.urls')),
    # Игра Econ Rush (публичная, без логина).
    path('game/', include('game.urls')),
]

# В режиме разработки показываем загруженные файлы (картинки, PDF).
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
