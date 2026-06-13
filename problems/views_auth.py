"""
Кастомный логин-view: после входа учеников редиректит на /student/,
преподавателей и администраторов — в /admin/.
"""
from django.contrib.auth.views import LoginView, LogoutView


class RoleBasedLoginView(LoginView):
    template_name = 'registration/login.html'

    def get_success_url(self):
        user = self.request.user
        if user.role == 'student':
            return '/student/'
        if user.role == 'teacher':
            return '/teacher/'
        return '/admin/'
