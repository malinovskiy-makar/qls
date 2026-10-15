/* Окно cookie (Правовой контур, часть Б, 09.10.2026; Политика cookie, разделы 1, 2, 4).
 *
 * Выбор человека пишется в куку weco_consent (all / necessary) на год: её читает
 * и скрипт (показывать ли окно), и сервер (выводить ли Метрику, ставить ли weco_src).
 *
 * «Разрешить»: кука, окно закрывается, счётчик подгружается файлом /legal/metrika.js
 *   БЕЗ перезагрузки страницы (сервер отдаёт код только при куке all).
 * «Только необходимые»: кука, окно закрывается, куки _ym* на домене сайта стираются,
 *   счётчик на странице отключается; weco_src (HttpOnly) стирает сервер на
 *   следующем запросе (problems/signup_source.py).
 * Ссылка «Настройки cookie» в футере (любой элемент с data-cookie-settings) открывает
 *   окно заново.
 *
 * Номер счётчика приходит в data-metrika-id окна: адреса Яндекса в HTML страницы
 * без согласия не попадают.
 */
(function () {
  'use strict';
  var bar = document.getElementById('cookie-bar');
  if (!bar) return;
  var NAME = 'weco_consent';
  var YEAR = 365 * 24 * 60 * 60;
  var root = document.documentElement;

  function readChoice() {
    var m = document.cookie.match(new RegExp('(?:^|;\\s*)' + NAME + '=(all|necessary)(?:;|$)'));
    return m ? m[1] : null;
  }

  function writeChoice(value) {
    var secure = location.protocol === 'https:' ? '; Secure' : '';
    document.cookie = NAME + '=' + value + '; max-age=' + YEAR + '; path=/; SameSite=Lax' + secure;
  }

  /* Высота окна нужна стилям: футер, кружок Telegram и низ экрана поднимаются на неё. */
  function measure() {
    if (bar.hidden) { root.style.removeProperty('--ck-h'); return; }
    root.style.setProperty('--ck-h', bar.offsetHeight + 'px');
  }
  if (typeof ResizeObserver === 'function') new ResizeObserver(measure).observe(bar);
  window.addEventListener('resize', measure);
  /* Первый замер мог пройти до раскладки страницы (скрытая вкладка, медленные стили). */
  window.addEventListener('load', measure);
  if (typeof requestAnimationFrame === 'function') requestAnimationFrame(measure);

  function show() { bar.hidden = false; measure(); }
  function hide() { bar.hidden = true; measure(); }

  function loadMetrika() {
    var id = bar.getAttribute('data-metrika-id');
    if (!id) return;
    var weco = window.weco = window.weco || {};
    if (weco.metrikaReady || weco.metrikaLoading) return;
    weco.metrikaLoading = true;
    var s = document.createElement('script');
    s.async = true;
    s.src = '/legal/metrika.js' + (bar.getAttribute('data-private') ? '?private=1' : '');
    document.head.appendChild(s);
  }

  /* Куки _ym*: ставятся на домен сайта и, бывает, на родительский. Стираем под
     каждым вариантом домена, иначе одна из копий пережила бы отказ. */
  function dropMetrikaCookies() {
    var host = location.hostname;
    var parts = host.split('.');
    var domains = [null, host, '.' + host];
    for (var i = 1; i < parts.length - 1; i++) domains.push('.' + parts.slice(i).join('.'));
    document.cookie.split(';').forEach(function (pair) {
      var name = pair.split('=')[0].replace(/^\s+/, '');
      if (name.indexOf('_ym') !== 0) return;
      domains.forEach(function (d) {
        document.cookie = name + '=; max-age=0; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/' +
          (d ? '; domain=' + d : '');
      });
    });
    try {
      Object.keys(window.localStorage).forEach(function (key) {
        if (key.indexOf('_ym') === 0) window.localStorage.removeItem(key);
      });
    } catch (e) { /* хранилище закрыто: чистить нечего */ }
    var id = bar.getAttribute('data-metrika-id');
    /* Справка Метрики: этот флаг отключает уже загруженный счётчик до перезагрузки. */
    if (id) window['disableYaCounter' + id] = true;
  }

  function choose(value) {
    writeChoice(value);
    hide();
    if (value === 'all') loadMetrika(); else dropMetrikaCookies();
  }

  bar.addEventListener('click', function (e) {
    var btn = e.target.closest ? e.target.closest('[data-cookie-choice]') : null;
    if (btn) choose(btn.getAttribute('data-cookie-choice'));
  });

  document.addEventListener('click', function (e) {
    var opener = e.target.closest ? e.target.closest('[data-cookie-settings]') : null;
    if (!opener) return;
    e.preventDefault();
    show();
    var first = bar.querySelector('[data-cookie-choice]');
    if (first) first.focus();
  });

  /* Кука стёрта в самом браузере, пока страница открыта, окно не оживит; на следующей
     странице сервер выведет его сам. Здесь только согласуем начальное состояние. */
  if (!readChoice() && bar.hidden) show();
  measure();
})();
