"""
«Адреса» сайта (маршруты).
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.urls import include, path

from catalog import views as catalog_views
from problems.views_auth import RoleBasedLoginView

urlpatterns = [
    # Главная страница сайта: статистика, поиск, навигация.
    path('', catalog_views.home, name='home'),
    path('admin/', admin.site.urls),
    # Логин / логаут.
    path('login/', RoleBasedLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(next_page='/login/'), name='logout'),
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
]

# В режиме разработки показываем загруженные файлы (картинки, PDF).
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
