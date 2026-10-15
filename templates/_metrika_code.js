{% comment %}
Код счётчика Яндекс Метрики БЕЗ обёртки <script> (часть Б, 09.10.2026). Один
источник для двух путей:
- `_metrika.html` вставляет его в страницу, когда кука `weco_consent` = `all`;
- `legal.views.metrika_boot` отдаёт его отдельным файлом `/legal/metrika.js`,
  который окно cookie подгружает, когда человек нажал «Разрешить» (без
  перезагрузки страницы).
Контекст: `metrika_id`, `metrika_private`, `user`, `goal`.
{% endcomment %}(function(m,e,t,r,i,k,a){m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
m[i].l=1*new Date();k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)})
(window, document, "script", "https://mc.yandex.ru/metrika/tag.js", "ym");
ym({{ metrika_id }}, "init", {clickmap: true, trackLinks: true, accurateTrackBounce: true, {% if metrika_private %}webvisor: false, sendTitle: false{% elif user.is_authenticated %}webvisor: false{% else %}webvisor: true{% endif %}});
(function () {
  var ID = {{ metrika_id }};
  var weco = window.weco = window.weco || {};
  /* Любой вызов Метрики — только если `ym` есть: блокировщик может вырезать
     счётчик целиком, и страница от этого ломаться не должна. */
  function send(args) {
    if (typeof window.ym !== 'function') return;
    try { window.ym.apply(window, [ID].concat(args)); } catch (e) { /* счётчик не роняет страницу */ }
  }
  weco.metrikaReady = true;
  weco.reachGoal = function (name) { send(['reachGoal', name]); };
  weco.reachGoalOnce = function (name, token) {
    var key = 'weco_goal_' + token;
    try {
      if (window.localStorage.getItem(key)) return;
      window.localStorage.setItem(key, '1');
    } catch (e) { /* хранилище закрыто: цель всё равно выдана сервером один раз */ }
    weco.reachGoal(name);
  };
  var last = location.href;
  weco.metrikaHit = function () {
    var url = location.href;
    if (url === last) return;
    var options = {referer: last};{% if not metrika_private %}
    options.title = document.title;{% endif %}
    last = url;
    send(['hit', url, options]);
  };{% if goal %}
  weco.reachGoalOnce('{{ goal.name }}', '{{ goal.token }}');{% endif %}
})();
