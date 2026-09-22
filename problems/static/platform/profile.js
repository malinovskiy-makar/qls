/* Вкладка «Аккаунт» профиля: списки, меню аватарки, своя обрезка и просмотр фото.
 *
 * ⚠️ СКРИПТ ТОЛЬКО УЛУЧШАЕТ. Списки — это `<details>` с обычными радиокнопками
 * и галочками формы: без него страница открывается, выбирается и отправляется.
 * Закрытое состояние рисует сервер; здесь мы его лишь поддерживаем после
 * каждого выбора.
 *
 * ⚠️ ОБРЕЗКА СЧИТАЕТСЯ ЗДЕСЬ, А РЕЖЕТ СЕРВЕР. Наружу уходят три числа —
 * левый верхний угол квадрата и его сторона в пикселях исходной картинки.
 * Сервер их прижимает к границам и поворачивает картинку по EXIF сам
 * (`AvatarForm.squared_jpeg`): доверять клиенту тут нечему и незачем.
 */
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };

  // ─────────────────────────────────────────────── выпадающие списки и меню
  var dropdowns = Array.prototype.slice.call(document.querySelectorAll('.pf-dd'));
  var avatarMenu = document.querySelector('.pf-ava-menu');
  var openables = dropdowns.concat(avatarMenu ? [avatarMenu] : []);

  function closeOthers(keep) {
    openables.forEach(function (node) { if (node !== keep) node.open = false; });
  }

  /** Хватит ли места снизу: не хватает — открываем панель вверх. */
  function placePanel(dd) {
    var panel = dd.querySelector('.pf-dd-panel');
    if (!panel) return;
    dd.classList.remove('pf-dd--up');
    var below = window.innerHeight - dd.getBoundingClientRect().bottom;
    if (below < Math.min(panel.scrollHeight + 16, 300)) dd.classList.add('pf-dd--up');
  }

  /** Подпись закрытого списка — по тому, что отмечено внутри. */
  function refresh(dd) {
    var kind = dd.getAttribute('data-kind');
    var summary = dd.querySelector('.pf-dd-btn');
    var checked = Array.prototype.slice.call(
      dd.querySelectorAll('.pf-sr:checked')).filter(function (input) { return input.value; });

    dd.querySelectorAll('.pf-opt').forEach(function (option) {
      var input = option.querySelector('.pf-sr');
      option.classList.toggle('is-sel', !!(input && input.checked));
    });

    if (kind === 'multi') {
      var chips = summary.querySelector('.pf-dd-chips');
      if (chips) {
        chips.textContent = '';
        if (!checked.length) {
          var empty = document.createElement('span');
          empty.className = 'pf-dd-value pf-dd-value--empty';
          empty.textContent = 'Не выбрано';
          chips.appendChild(empty);
        } else {
          checked.forEach(function (input) {
            var chip = document.createElement('span');
            chip.className = 'pf-chip';
            // Плашка берёт КОРОТКУЮ подпись из данных варианта, если она есть:
            // в раскрытом списке подписи полные, в закрытом они не помещаются.
            chip.textContent = input.getAttribute('data-chip')
              || input.closest('.pf-opt').querySelector('.pf-opt-name').textContent.trim();
            chips.appendChild(chip);
          });
        }
      }
      var counter = dd.querySelector('[data-dd-count]');
      if (counter) counter.textContent = 'Выбрано: ' + checked.length;
      return;
    }

    var value = summary.querySelector('.pf-dd-value');
    if (!value) return;
    value.textContent = '';
    if (!checked.length) {
      value.classList.add('pf-dd-value--empty');
      value.textContent = 'Не выбрано';
      return;
    }
    value.classList.remove('pf-dd-value--empty');
    var option = checked[0].closest('.pf-opt');
    var name = option.querySelector('.pf-opt-name').textContent.trim();
    var desc = option.querySelector('.pf-opt-desc');
    if (kind === 'level' && desc) {
      var bold = document.createElement('b');
      bold.textContent = name;
      var tail = document.createElement('span');
      tail.className = 'pf-dd-desc';
      tail.textContent = ' · ' + desc.textContent.trim();
      value.appendChild(bold);
      value.appendChild(tail);
    } else {
      value.textContent = name;
    }
  }

  dropdowns.forEach(function (dd) {
    var none = dd.getAttribute('data-kind') === 'multi'
      ? dd.querySelector('.pf-opt--none .pf-sr') : null;

    dd.addEventListener('toggle', function () {
      if (dd.open) { closeOthers(dd); placePanel(dd); }
    });

    dd.addEventListener('change', function (event) {
      var input = event.target;
      if (!input.classList.contains('pf-sr')) return;
      if (none && input.checked) {
        // «Пока ни одной» и любая олимпиада — взаимно исключающие ответы.
        if (input === none) {
          dd.querySelectorAll('.pf-sr').forEach(function (other) {
            if (other !== none) other.checked = false;
          });
        } else {
          none.checked = false;
        }
      }
      refresh(dd);
      if (dd.getAttribute('data-kind') !== 'multi') dd.open = false;
    });

    var reset = dd.querySelector('[data-dd-reset]');
    if (reset) {
      reset.addEventListener('click', function () {
        dd.querySelectorAll('.pf-sr').forEach(function (input) { input.checked = false; });
        refresh(dd);
      });
    }
    var done = dd.querySelector('[data-dd-done]');
    if (done) done.addEventListener('click', function () { dd.open = false; });

    refresh(dd);
  });

  if (avatarMenu) {
    avatarMenu.addEventListener('toggle', function () {
      if (avatarMenu.open) closeOthers(avatarMenu);
    });
  }

  document.addEventListener('click', function (event) {
    openables.forEach(function (node) {
      if (node.open && !node.contains(event.target)) node.open = false;
    });
  });

  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Escape') return;
    openables.forEach(function (node) {
      if (!node.open) return;
      node.open = false;
      var summary = node.querySelector('summary');
      if (summary) summary.focus();
    });
  });

  // ─────────────────────────────────────────────────── имя пользователя
  var username = document.querySelector('.pf-user-field input');
  var warn = $('pf-user-warn');
  if (username && warn) {
    username.addEventListener('input', function () {
      warn.hidden = username.value === username.defaultValue;
    });
  }

  // ───────────────────────────────────────────────────── выбор файла
  var file = $('pf-ava-file');
  var form = $('pf-ava-form');
  var error = $('pf-ava-error');
  var MAX_BYTES = 3 * 1024 * 1024;

  function complain(text) {
    if (!error) return;
    error.textContent = text;
    error.hidden = !text;
  }

  // ───────────────────────────────────────────────────── окно обрезки
  var dialog = $('pf-crop');
  var stage = $('pf-crop-stage');
  var picture = $('pf-crop-img');
  var hole = $('pf-crop-hole');
  var zoom = $('pf-crop-zoom');
  var saveButton = $('pf-crop-save');
  var view = $('pf-view');

  var crop = { base: 1, scale: 1, tx: 0, ty: 0, W: 0, H: 0, D: 0, cx0: 0, cy0: 0 };

  function measure() {
    var box = stage.getBoundingClientRect();
    crop.W = box.width;
    crop.H = box.height;
    var circle = hole.getBoundingClientRect();
    crop.D = circle.width;
    crop.cx0 = circle.left - box.left;
    crop.cy0 = circle.top - box.top;
  }

  /** Внутри круга не должно быть пустоты — прижимаем сдвиг к границам. */
  function clamp() {
    var w = picture.naturalWidth * crop.scale;
    var h = picture.naturalHeight * crop.scale;
    crop.tx = Math.min(crop.cx0, Math.max(crop.cx0 + crop.D - w, crop.tx));
    crop.ty = Math.min(crop.cy0, Math.max(crop.cy0 + crop.D - h, crop.ty));
  }

  function draw() {
    clamp();
    picture.style.transform =
      'translate(' + crop.tx + 'px, ' + crop.ty + 'px) scale(' + crop.scale + ')';
  }

  function setZoom(factor) {
    // Масштаб меняется вокруг центра круга: точка под ним остаётся на месте.
    var cx = crop.cx0 + crop.D / 2;
    var cy = crop.cy0 + crop.D / 2;
    var before = crop.scale;
    crop.scale = crop.base * factor;
    crop.tx = cx - (cx - crop.tx) * (crop.scale / before);
    crop.ty = cy - (cy - crop.ty) * (crop.scale / before);
    draw();
  }

  function start(url) {
    picture.onload = function () {
      measure();
      crop.base = crop.D / Math.min(picture.naturalWidth, picture.naturalHeight);
      crop.scale = crop.base;
      crop.tx = (crop.W - picture.naturalWidth * crop.scale) / 2;
      crop.ty = (crop.H - picture.naturalHeight * crop.scale) / 2;
      if (zoom) zoom.value = 1;
      draw();
      dialog.showModal();
      measure();          // размеры круга известны только после показа окна
      draw();
    };
    picture.onerror = function () { complain('Это не картинка.'); };
    picture.src = url;
  }

  if (file && dialog && stage && picture) {
    file.addEventListener('change', function () {
      var chosen = file.files && file.files[0];
      if (!chosen) return;
      complain('');
      if (chosen.size > MAX_BYTES) {
        complain('Файл больше 3 МБ. Возьмите картинку поменьше.');
        file.value = '';
        return;
      }
      if (chosen.type && chosen.type.indexOf('image/') !== 0) {
        complain('Это не картинка.');
        file.value = '';
        return;
      }
      if (avatarMenu) avatarMenu.open = false;
      if (dialog.open) dialog.close();
      start(URL.createObjectURL(chosen));
    });

    if (zoom) {
      zoom.addEventListener('input', function () { setZoom(parseFloat(zoom.value) || 1); });
    }

    // Перетаскивание — Pointer Events: одна ветка для мыши, пальца и пера.
    var dragging = false;
    var last = { x: 0, y: 0 };
    stage.addEventListener('pointerdown', function (event) {
      dragging = true;
      last = { x: event.clientX, y: event.clientY };
      stage.setPointerCapture(event.pointerId);
    });
    stage.addEventListener('pointermove', function (event) {
      if (!dragging) return;
      crop.tx += event.clientX - last.x;
      crop.ty += event.clientY - last.y;
      last = { x: event.clientX, y: event.clientY };
      draw();
    });
    ['pointerup', 'pointercancel'].forEach(function (name) {
      stage.addEventListener(name, function () { dragging = false; });
    });
    stage.addEventListener('keydown', function (event) {
      var step = 10;
      var moves = { ArrowLeft: [-step, 0], ArrowRight: [step, 0],
                    ArrowUp: [0, -step], ArrowDown: [0, step] };
      var move = moves[event.key];
      if (!move) return;
      event.preventDefault();
      crop.tx += move[0];
      crop.ty += move[1];
      draw();
    });

    if (saveButton && form) {
      saveButton.addEventListener('click', function () {
        var size = Math.round(crop.D / crop.scale);
        var x = Math.round((crop.cx0 - crop.tx) / crop.scale);
        var y = Math.round((crop.cy0 - crop.ty) / crop.scale);
        $('pf-crop-size').value = Math.max(1, size);
        $('pf-crop-x').value = Math.min(Math.max(0, x), Math.max(0, picture.naturalWidth - size));
        $('pf-crop-y').value = Math.min(Math.max(0, y), Math.max(0, picture.naturalHeight - size));
        saveButton.disabled = true;
        saveButton.textContent = 'Сохраняем…';
        form.hidden = false;
        form.submit();
      });
    }
  }

  // ───────────────────────────────────────── закрытие окон и просмотр
  [dialog, view].forEach(function (node) {
    if (!node) return;
    node.addEventListener('click', function (event) {
      if (event.target === node || event.target.closest('[data-close]')) node.close();
    });
    node.addEventListener('close', function () {
      if (node === dialog && file) file.value = '';
      var summary = avatarMenu ? avatarMenu.querySelector('summary') : null;
      if (summary) summary.focus();
    });
  });

  var viewButton = document.querySelector('[data-act="view"]');
  if (viewButton && view) {
    viewButton.addEventListener('click', function () {
      if (avatarMenu) avatarMenu.open = false;
      view.showModal();
    });
  }
})();
