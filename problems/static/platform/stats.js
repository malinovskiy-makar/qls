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
    // ⚠️ ПОДПИСИ ШКАЛЫ РИСУЕМ САМИ. Chart.js умеет только «строго вверх»:
    // ни угла, ни смещения у радиальных подписей в его настройках нет.
    // Плагин ставит их на биссектрису между первым и вторым лучом (там
    // свободно при любом числе разделов) и подкладывает прямоугольник
    // цвета карточки — иначе сетка просвечивает сквозь цифры.
    var radarTicks = {
      id: 'radarTicks',
      afterDatasetsDraw: function (chart, args, opts) {
        var scale = chart.scales.r;
        if (!scale) { return; }
        var count = (chart.data.labels || []).length || 1;
        var angle = Math.PI / count;
        var ctx = chart.ctx;
        ctx.save();
        ctx.font = '10px ' + getComputedStyle(document.body).fontFamily;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        (scale.ticks || []).forEach(function (tick, index) {
          if (!index) { return; }   // ноль сидит в центре, подписывать нечего
          var radius = scale.getDistanceFromCenterForValue(tick.value);
          var x = scale.xCenter + radius * Math.sin(angle);
          var y = scale.yCenter - radius * Math.cos(angle);
          var text = tick.label === undefined ? String(tick.value)
                                              : String(tick.label);
          var width = ctx.measureText(text).width;
          ctx.fillStyle = opts.backdrop;
          ctx.fillRect(x - width / 2 - 3, y - 7, width + 6, 14);
          ctx.fillStyle = opts.color;
          ctx.fillText(text, x, y);
        });
        ctx.restore();
      },
    };

    make('chart-radar', {
      type: 'radar',
      plugins: [radarTicks],
      data: {
        labels: state.radar.map(function (r) { return r.name; }),
        datasets: [{
          label: 'Доля верных, %',
          data: state.radar.map(function (r) { return r.accuracy; }),
          borderColor: colors.accent,
          backgroundColor: colors.accent + '33',
          pointBackgroundColor: colors.accent,
          // ⚠️ ТОЧКИ НА ВЕРШИНАХ (ревью 17.08, п. 4.1). Там, где заливка
          // почти сходится к центру, у многоугольника нет площади, и
          // значение раздела читать не по чему: видна только линия.
          pointRadius: 3.5,
          pointHoverRadius: 5,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false },
                   radarTicks: { color: colors.text,
                                 backdrop: colors.surface } },
        scales: {
          r: {
            beginAtZero: true, max: 100,
            angleLines: { color: colors.grid },
            grid: { color: colors.grid },
            pointLabels: { color: colors.text, font: { size: 10 } },
            // ⚠️ ВСТРОЕННЫЕ ПОДПИСИ ШКАЛЫ ВЫКЛЮЧЕНЫ (ревью 16.08, п. 5.2).
            // Chart.js рисует 20/40/60/80/100 строго вверх — там же
            // проходит линия первого раздела и сидит его точка, и цифры
            // под ними не читались вовсе. Рисуем их сами, на биссектрисе
            // между первыми двумя лучами (плагин `radarTicks` ниже).
            //
            // ⚠️ ШАГ СЕТКИ 20, А НЕ 10 (ревью 17.08, п. 4.1). По умолчанию
            // Chart.js дробит шкалу 0..100 на десять делений; на биссектрисе
            // они вставали в девяти пикселях друг от друга и слипались в
            // кашу — различалась только последняя. Пять колец читаются, и
            // сама сетка перестала быть частой рябью.
            ticks: { display: false, stepSize: 20 },
          },
        },
      },
    });

    // ── Розовая пара: насыщенный «верно», приглушённый «мимо» ─────────
    // ⚠️ РЕШЕНИЕ ВЛАДЕЛЬЦА (ревью 16.08). Зелёный и красный в этих двух
    // карточках больше не используются: они закреплены за ВЕРДИКТОМ
    // задачи («решение верно» / «неверно»), а здесь речь о распределении
    // работы, а не о приговоре ученику. Оба тона — один и тот же акцент
    // с разной плотностью, поэтому тему они переживают сами.
    var hit = colors.accent;
    var miss = colors.accent + '3d';

    // Карта сложности: высота — сколько задач взято, число сверху и
    // насыщенность — доля верных.
    make('chart-difficulty', {
      type: 'bar',
      data: {
        labels: state.difficulty.levels.map(function (r) {
          return String(r.level); }),
        datasets: [
          { label: 'Верно',
            data: state.difficulty.levels.map(function (r) {
              return r.solved; }),
            backgroundColor: hit, stack: 'd' },
          { label: 'Мимо',
            data: state.difficulty.levels.map(function (r) {
              return r.attempted - r.solved; }),
            backgroundColor: miss, stack: 'd' },
        ],
      },
      options: Object.assign({}, options, {
        plugins: Object.assign({}, options.plugins, {
          tooltip: Object.assign({}, options.plugins.tooltip, {
            callbacks: { title: function (ctx) {
              return 'Сложность ' + ctx[0].label + ' из 5';
            } },
          }),
        }),
        scales: {
          x: Object.assign({ stacked: true }, options.scales.x),
          y: Object.assign({ stacked: true }, options.scales.y),
        },
      }),
    });

    make('chart-sources', {
      type: 'bar',
      data: {
        labels: state.sources.map(function (r) { return r.label; }),
        datasets: [
          { label: 'Верно',
            data: state.sources.map(function (r) { return r.solved; }),
            backgroundColor: hit, stack: 's' },
          { label: 'Мимо',
            data: state.sources.map(function (r) {
              return r.attempted - r.solved; }),
            backgroundColor: miss, stack: 's' },
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
        // Сетку активности перерисовывает СЕРВЕР — подставляем готовую
        // разметку. Края растворения после подмены настраиваем заново.
        var block = document.getElementById('activity-block');
        if (block && payload.activityHtml) {
          block.innerHTML = payload.activityHtml;
          if (window.QLS_FADE) { window.QLS_FADE(); }
        }
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
    // ⚠️ ПУСТОЕ СОСТОЯНИЕ НАЗЫВАЕТСЯ СЛОВАМИ И ЗДЕСЬ ТОЖЕ (ревью 17.08,
    // п. 4.4). Разметку рисует шаблон, а переключатель периода —
    // этот код; разойдись они, «нет ответов» появлялось бы только при
    // загрузке страницы и пропадало при первом же переключении периода.
    var empty = overview.accuracy === null;
    var texts = {
      solved: String(overview.solved),
      accuracy: empty ? 'нет ответов' : overview.accuracy + '%',
      minutes: overview.minutes + ' мин',
      xp: String(overview.xp),
    };
    Object.keys(texts).forEach(function (key) {
      var node = document.querySelector('[data-metric="' + key + '"]');
      if (node) {
        node.textContent = texts[key];
        node.classList.toggle('is-empty', key === 'accuracy' && empty);
      }
      var chg = document.querySelector('[data-change="' + key + '"]');
      if (!chg) { return; }
      var change = (overview.change || {})[key];
      chg.className = 'chg' + (change && !(key === 'accuracy' && empty)
                               ? ' ' + change.direction : '');
      if (key === 'accuracy' && empty) {
        chg.textContent = 'за выбранный период';
        return;
      }
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
