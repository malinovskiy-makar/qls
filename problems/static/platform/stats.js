/*
 * Графики экрана статистики — Chart.js с CDN, без сборки (как D3 и Math.js
 * в calc2).
 *
 * ⚠️ ЦВЕТА БЕРЁМ ИЗ ТОКЕНОВ, а не пишем hex в JS. Иначе переключатель темы
 * сайта перекрасил бы страницу, но не графики. Значения читаются из
 * вычисленного стиля документа, а на смену темы графики перерисовываются —
 * `data-theme` меняется на <html>, за ним следит MutationObserver.
 *
 * Теплокарта здесь НЕ рисуется: она SVG в шаблоне, и по той же причине —
 * её цвета идут через var(--accent) и перекрашиваются сами, без JS.
 */
(function () {
  'use strict';

  var charts = {};
  var state = JSON.parse(document.getElementById('stats-data').textContent);

  function token(name, fallback) {
    var value = getComputedStyle(document.documentElement)
      .getPropertyValue(name).trim();
    return value || fallback;
  }

  function palette() {
    return {
      accent: token('--accent', '#BE185D'),
      green: token('--green', '#1d7e45'),
      amber: token('--amber', '#b26b00'),
      error: token('--error', '#c0392b'),
      text: token('--text2', '#5b6472'),
      grid: token('--border-soft', 'rgba(0,0,0,.07)'),
      surface: token('--surface', '#fff'),
    };
  }

  function baseOptions(colors) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: colors.text, boxWidth: 12, font: { size: 11 } } },
        tooltip: { backgroundColor: colors.surface, titleColor: colors.text,
                   bodyColor: colors.text, borderColor: colors.grid,
                   borderWidth: 1 },
      },
      scales: {
        x: { ticks: { color: colors.text, font: { size: 10 } },
             grid: { color: colors.grid } },
        y: { beginAtZero: true, ticks: { color: colors.text, font: { size: 10 } },
             grid: { color: colors.grid } },
      },
    };
  }

  function make(id, config) {
    var canvas = document.getElementById(id);
    if (!canvas || typeof Chart === 'undefined') { return; }
    if (charts[id]) { charts[id].destroy(); }
    charts[id] = new Chart(canvas, config);
  }

  function drawAll() {
    var colors = palette();
    var options = baseOptions(colors);

    // Рост уровня — линия, как рейтинг на chess.com.
    if (state.levelHistory && state.levelHistory.length) {
      make('chart-level', {
        type: 'line',
        data: {
          labels: state.levelHistory.map(function (p) { return p.date; }),
          datasets: [{
            label: 'Опыт',
            data: state.levelHistory.map(function (p) { return p.xp; }),
            borderColor: colors.accent, backgroundColor: colors.accent,
            tension: 0.25, pointRadius: 0, borderWidth: 2, fill: false,
          }],
        },
        options: Object.assign({}, options, {
          plugins: Object.assign({}, options.plugins,
            { legend: { display: false } }),
        }),
      });
    }

    // Паутинка по укрупнённым разделам: по 21 теме радар нечитаем.
    make('chart-radar', {
      type: 'radar',
      data: {
        labels: state.radar.map(function (r) { return r.name; }),
        datasets: [{
          label: 'Доля верных, %',
          data: state.radar.map(function (r) { return r.accuracy; }),
          borderColor: colors.accent,
          backgroundColor: colors.accent + '33',
          pointBackgroundColor: colors.accent,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          r: {
            beginAtZero: true, max: 100,
            angleLines: { color: colors.grid },
            grid: { color: colors.grid },
            pointLabels: { color: colors.text, font: { size: 10 } },
            ticks: { color: colors.text, backdropColor: 'transparent',
                     font: { size: 9 } },
          },
        },
      },
    });

    // Кольцо верно/неверно/пропущено. Зелёный здесь в своём законном
    // смысле — «решение верно», как звёзды сложности амбером.
    make('chart-ring', {
      type: 'doughnut',
      data: {
        labels: state.ring.map(function (r) { return r.label; }),
        datasets: [{
          data: state.ring.map(function (r) { return r.value; }),
          backgroundColor: [colors.green, colors.error, colors.grid],
          borderWidth: 0,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false, cutout: '62%',
        plugins: { legend: { position: 'bottom',
                             labels: { color: colors.text, boxWidth: 12,
                                       font: { size: 11 } } } },
      },
    });

    make('chart-sources', {
      type: 'bar',
      data: {
        labels: state.sources.map(function (r) { return r.label; }),
        datasets: [
          { label: 'Верно',
            data: state.sources.map(function (r) { return r.solved; }),
            backgroundColor: colors.green, stack: 's' },
          { label: 'Мимо',
            data: state.sources.map(function (r) {
              return r.attempted - r.solved; }),
            backgroundColor: colors.error, stack: 's' },
        ],
      },
      options: Object.assign({}, options, {
        scales: {
          x: Object.assign({ stacked: true }, options.scales.x),
          y: Object.assign({ stacked: true }, options.scales.y),
        },
      }),
    });

    // ⚠️ ОБА ГРАФИКА «КОГДА ЗАНИМАЕШЬСЯ» — В МИНУТАХ, А НЕ В ПОПЫТКАХ
    // (ревью 15.08, п. 21). Числа приходят из `stats.minutes_by_*`, то
    // есть посчитаны тем же правилом, что карточка «Минут на сайте».
    // Подпись обязана называть единицу: столбик «14» без слова читается
    // как «14 задач».
    var minuteAxis = Object.assign({}, options.scales.y, {
      ticks: Object.assign({}, options.scales.y.ticks,
        { callback: function (value) { return value + ' мин'; } }),
    });
    // Подпись во всплывашке приходит ГОТОВОЙ строкой с сервера («15 минут»):
    // правило трёх русских форм живёт в питоне и второй копии на клиенте
    // не имеет. Берём её по номеру столбика.
    // ⚠️ Оформление всплывашки берём из общих настроек и ДОПОЛНЯЕМ, а не
    // заменяем: голый `{callbacks}` стёр бы цвета фона и текста, и в
    // тёмной теме подпись стала бы чёрной по чёрному.
    function minuteTipFor(rows) {
      return Object.assign({}, options.plugins.tooltip, {
        callbacks: { label: function (ctx) {
          var row = rows[ctx.dataIndex];
          return row ? row.text : ctx.formattedValue;
        } },
      });
    }

    make('chart-weekday', {
      type: 'bar',
      data: {
        labels: state.byWeekday.map(function (r) { return r.label; }),
        datasets: [{ label: 'Минуты на сайте',
                     data: state.byWeekday.map(function (r) { return r.value; }),
                     backgroundColor: colors.accent }],
      },
      options: Object.assign({}, options, {
        plugins: Object.assign({}, options.plugins,
          { legend: { display: false },
            tooltip: minuteTipFor(state.byWeekday) }),
        scales: Object.assign({}, options.scales, { y: minuteAxis }),
      }),
    });

    make('chart-hour', {
      type: 'bar',
      data: {
        labels: state.byHour.map(function (r) { return r.hour + ':00'; }),
        datasets: [{ label: 'Минуты на сайте',
                     data: state.byHour.map(function (r) { return r.value; }),
                     backgroundColor: colors.accent }],
      },
      options: Object.assign({}, options, {
        plugins: Object.assign({}, options.plugins,
          { legend: { display: false },
            tooltip: minuteTipFor(state.byHour) }),
        scales: Object.assign({}, options.scales, {
          y: minuteAxis,
          x: Object.assign({}, options.scales.x,
            { ticks: { color: colors.text, font: { size: 9 },
                       maxRotation: 0, autoSkip: true, maxTicksLimit: 8 } }),
        }),
      }),
    });
  }

  // --- Переключатель периода: меняет ВСЕ графики без перезагрузки --------
  function applyPeriod(period, button) {
    var url = new URL(window.location.href);
    url.searchParams.set('period', period);
    fetch('/profile/stats/data/?period=' + encodeURIComponent(period),
          { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.json(); })
      .then(function (payload) {
        state = payload;
        updateMetrics(payload.overview);
        var hint = document.getElementById('time-hint');
        if (hint) { hint.textContent = payload.timeHint || ''; }
        drawAll();
        document.querySelectorAll('#period-bar button').forEach(function (b) {
          b.classList.toggle('is-active', b === button);
        });
        // Адрес обновляем БЕЗ перезагрузки — чтобы обновление страницы или
        // ссылка в закладке открыли тот же период.
        window.history.replaceState({}, '', url);
      })
      .catch(function () { window.location.href = url.toString(); });
  }

  function updateMetrics(overview) {
    var texts = {
      solved: String(overview.solved),
      accuracy: overview.accuracy === null ? '—' : overview.accuracy + '%',
      minutes: overview.minutes + ' мин',
      xp: String(overview.xp),
    };
    Object.keys(texts).forEach(function (key) {
      var node = document.querySelector('[data-metric="' + key + '"]');
      if (node) { node.textContent = texts[key]; }
      var chg = document.querySelector('[data-change="' + key + '"]');
      if (!chg) { return; }
      var change = (overview.change || {})[key];
      chg.className = 'chg' + (change ? ' ' + change.direction : '');
      if (!change) { chg.innerHTML = '&nbsp;'; return; }
      var arrow = change.direction === 'up' ? '↑'
        : (change.direction === 'down' ? '↓' : '');
      chg.textContent = arrow + ' ' + change.abs_diff + ' к прошлому периоду';
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    drawAll();

    document.querySelectorAll('#period-bar button').forEach(function (button) {
      button.addEventListener('click', function () {
        applyPeriod(button.dataset.period, button);
      });
    });

    var filter = document.getElementById('achv-filter');
    if (filter) {
      filter.addEventListener('click', function (event) {
        var button = event.target.closest('button');
        if (!button) { return; }
        filter.querySelectorAll('button').forEach(function (b) {
          b.classList.toggle('is-active', b === button);
        });
        var category = button.dataset.cat;
        document.querySelectorAll('#achv-grid .achv').forEach(function (card) {
          card.hidden = category !== 'all' && card.dataset.cat !== category;
        });
      });
    }

    var edit = document.getElementById('goal-edit');
    var form = document.getElementById('goal-form');
    if (edit && form) {
      edit.addEventListener('click', function () {
        form.hidden = !form.hidden;
        if (!form.hidden) { form.querySelector('input').focus(); }
      });
    }

    // Смена темы сайта — перерисовываем: цвета живут в токенах, а Chart.js
    // копирует их в момент создания графика.
    new MutationObserver(drawAll).observe(document.documentElement,
      { attributes: true, attributeFilter: ['data-theme'] });
  });
})();
