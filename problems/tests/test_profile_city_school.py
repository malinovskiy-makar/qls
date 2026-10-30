# -*- coding: utf-8 -*-
"""Профиль `/profile/?tab=data`: город перед школой, подсказки анкеты, ответы анкеты в профиле
(решение владельца 30.10.2026).

* «Класс | Город», под ним «Школа» на всю ширину — и в разметке, и в порядке полей формы.
* Подсказки — тот же скрипт и те же адреса, что на шагах «Город» и «Школа» анкеты: один
  `static/onboarding/suggest.js`, второй реализации ни в профиле, ни в `onboarding.js` нет.
* Анкета пишет в `profile.city` / `profile.school` ТЕКСТ — профиль читает и пишет тот же текст.
* Цели и «Другое» в профиль не добавляются: по документам ред. 3 они меняются по запросу.
"""
import re
from pathlib import Path

from django.conf import settings

from problems.forms_accounts import ProfileForm
from problems.tests.test_onboarding import OnboardingBase, main_html

ROOT = Path(settings.BASE_DIR)


def checked_values(html, name):
    """Значения отмеченных радиокнопок `name` в разметке страницы."""
    values = set()
    for tag in re.findall(r'<input\b[^>]*>', html):
        if 'name="%s"' % name in tag and ' checked' in tag:
            values.add(re.search(r'value="([^"]*)"', tag).group(1))
    return values


class ProfileCitySchoolBase(OnboardingBase):
    def profile_page(self):
        response = self.client.get('/profile/?tab=data')
        self.assertEqual(response.status_code, 200)
        return response

    def payload(self, response, **changes):
        """Полная форма так, как её отправит браузер: значения из самой страницы."""
        form = response.context['form']
        data = {}
        for name in form.fields:
            value = form[name].value()
            data[name] = [] if value is None else value
        data.update(action='data', **changes)
        return data


class OrderTests(ProfileCitySchoolBase):
    def test_city_goes_before_school_in_the_html(self):
        html = self.profile_page().content.decode()
        self.assertLess(html.index('for="id_city"'), html.index('for="id_school"'))
        self.assertLess(html.index('name="city"'), html.index('name="school"'))
        # Класс и город — одним рядом (в одной сетке), школа — отдельным полем под ним.
        self.assertLess(html.index('name="grade"'), html.index('name="city"'))
        self.assertLess(html.index('name="city"'), html.index('data-pf-school'))
        self.assertLess(html.index('data-pf-school'), html.index('name="school"'))

    def test_form_fields_follow_the_same_order(self):
        names = list(ProfileForm.Meta.fields)
        self.assertLess(names.index('city'), names.index('school'))


class SharedSuggestTests(ProfileCitySchoolBase):
    def test_profile_wires_the_same_component_as_the_onboarding(self):
        html = self.profile_page().content.decode()
        self.assertIn('onboarding/suggest.js', html)
        self.assertIn('onboarding/suggest.css', html)
        self.assertIn('data-ac="/welcome/api/cities/"', html)
        self.assertIn('data-ac="/welcome/api/schools/"', html)
        # Школа спрашивает город из соседнего поля; от города подсказки не зависят.
        self.assertIn('data-ac-city="id_city"', html)
        # Никакого инлайн-JS с подсказками: код только в статическом файле.
        self.assertNotIn('initSuggest', html)
        self.assertNotIn('/welcome/api/', re.sub(r'data-ac="[^"]*"', '', html))

    def test_onboarding_school_step_uses_the_same_script_and_urls(self):
        self.pass_student()
        html = self.client.get('/welcome/school/').content.decode()
        self.assertIn('onboarding/suggest.js', html)
        self.assertIn('onboarding/suggest.css', html)
        self.assertIn('data-ac="/welcome/api/cities/"', main_html_of(html))
        self.assertIn('data-ac="/welcome/api/schools/"', main_html_of(html))

    def test_there_is_one_implementation(self):
        suggest = (ROOT / 'static/onboarding/suggest.js').read_text(encoding='utf-8')
        onboarding = (ROOT / 'static/onboarding/onboarding.js').read_text(encoding='utf-8')
        self.assertIn('function initSuggest', suggest)
        self.assertIn("closest('.ob-field, .pf-field')", suggest)
        self.assertNotIn('initSuggest', onboarding)
        self.assertIn('WecoSuggest', onboarding)
        css = (ROOT / 'static/onboarding/suggest.css').read_text(encoding='utf-8')
        self.assertIn('.pf-field.is-ac-open', css)
        self.assertNotIn('.ob-dd', (ROOT / 'static/onboarding/onboarding.css').read_text(encoding='utf-8'))

    def test_suggestion_urls_answer_a_logged_in_profile_owner(self):
        self.pass_student()
        self.assertEqual(self.client.get('/welcome/api/cities/?q=каз').status_code, 200)
        self.assertEqual(self.client.get('/welcome/api/schools/?q=лицей').status_code, 200)

    def test_suggest_widgets_are_not_covered_by_browser_autofill(self):
        form = ProfileForm(instance=self.profile)
        self.assertEqual(form.fields['city'].widget.attrs['autocomplete'], 'off')
        self.assertEqual(form.fields['school'].widget.attrs['autocomplete'], 'off')


def main_html_of(html):
    found = re.search(r'<main class="ob-main"[^>]*>(.*?)</main>', html, re.S)
    return found.group(1) if found else ''


class SavingTests(ProfileCitySchoolBase):
    def test_city_and_school_saved_through_the_profile_are_shown_next_time(self):
        self.pass_student()
        response = self.profile_page()
        saved = self.client.post('/profile/?tab=data',
                                 self.payload(response, city='Екатеринбург',
                                              school='Лицей № 110'))
        self.assertEqual(saved.status_code, 302)
        profile = self.reload()
        self.assertEqual((profile.city, profile.school), ('Екатеринбург', 'Лицей № 110'))
        html = self.profile_page().content.decode()
        self.assertIn('value="Екатеринбург"', html)
        self.assertIn('value="Лицей № 110"', html)
        # Остальные ответы анкеты при этом не пострадали.
        self.assertEqual((profile.grade, profile.level, profile.source_channel),
                         ('10', 'basic', 'vk'))


class OnboardingAnswersInProfileTests(ProfileCitySchoolBase):
    def test_answers_of_the_form_are_filled_in_the_profile(self):
        self.pass_student(grade='10', source='vk')
        response = self.profile_page()
        form = response.context['form']
        self.assertEqual(form['grade'].value(), '10')
        self.assertEqual(form['level'].value(), 'basic')
        self.assertEqual(form['city'].value(), 'Казань')
        self.assertEqual(form['school'].value(), 'Лицей 131')
        self.assertEqual(form['source_channel'].value(), 'vk')
        html = response.content.decode()
        self.assertIn('value="Казань"', html)
        self.assertIn('value="Лицей 131"', html)
        # Не только значения формы: радиокнопки в самой разметке отмечены.
        self.assertEqual(checked_values(html, 'grade'), {'10'})
        self.assertEqual(checked_values(html, 'level'), {'basic'})
        self.assertEqual(checked_values(html, 'source_channel'), {'vk'})

    def test_goals_and_other_text_are_not_in_the_profile(self):
        self.pass_student(goals=('vsosh', 'listed'))
        form = self.profile_page().context['form']
        self.assertNotIn('goals', form.fields)
        self.assertNotIn('source_other', form.fields)
        self.assertEqual(self.reload().goals, ['vsosh', 'listed'])
