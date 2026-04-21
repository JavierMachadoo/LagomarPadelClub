window.Lightbox = (function () {
  'use strict';

  var $root, $img, $caption, $counter, $prev, $next;
  var fotos = [];
  var idx = 0;
  var touchStartX = 0;

  function ensureDOM() {
    if ($root) return;
    var el = document.createElement('div');
    el.innerHTML = [
      '<div class="lb-overlay" id="lb-root" hidden>',
      '  <button class="lb-close" aria-label="Cerrar">&times;</button>',
      '  <button class="lb-prev" aria-label="Anterior">&#10094;</button>',
      '  <div class="lb-stage">',
      '    <img class="lb-img" alt="">',
      '    <div class="lb-caption"></div>',
      '    <div class="lb-counter"></div>',
      '  </div>',
      '  <button class="lb-next" aria-label="Siguiente">&#10095;</button>',
      '</div>',
    ].join('');
    document.body.appendChild(el.firstElementChild);
    $root    = document.getElementById('lb-root');
    $img     = $root.querySelector('.lb-img');
    $caption = $root.querySelector('.lb-caption');
    $counter = $root.querySelector('.lb-counter');
    $prev    = $root.querySelector('.lb-prev');
    $next    = $root.querySelector('.lb-next');

    $root.querySelector('.lb-close').addEventListener('click', cerrar);
    $prev.addEventListener('click', prev);
    $next.addEventListener('click', next);
    $root.addEventListener('click', function (e) { if (e.target === $root) cerrar(); });
    $root.addEventListener('touchstart', function (e) {
      touchStartX = e.changedTouches[0].clientX;
    }, { passive: true });
    $root.addEventListener('touchend', function (e) {
      var dx = e.changedTouches[0].clientX - touchStartX;
      if (Math.abs(dx) > 50) { dx > 0 ? prev() : next(); }
    });
    document.addEventListener('keydown', function (e) {
      if (!$root || $root.hidden) return;
      if (e.key === 'Escape')     cerrar();
      if (e.key === 'ArrowLeft')  prev();
      if (e.key === 'ArrowRight') next();
    });
  }

  function render() {
    var f = fotos[idx];
    $img.src = f.full_url;
    $img.alt = f.nombre;
    $caption.textContent = f.nombre;
    $counter.textContent = (idx + 1) + ' / ' + fotos.length;
    $prev.disabled = idx === 0;
    $next.disabled = idx === fotos.length - 1;
  }

  function abrir(i) {
    idx = i;
    render();
    $root.hidden = false;
    document.body.style.overflow = 'hidden';
  }

  function cerrar() {
    $root.hidden = true;
    document.body.style.overflow = '';
  }

  function prev() { if (idx > 0)                { idx--; render(); } }
  function next() { if (idx < fotos.length - 1)  { idx++; render(); } }

  function attach(containerEl) {
    ensureDOM();
    var thumbs = Array.from(containerEl.querySelectorAll('.foto-thumb'));
    fotos = thumbs.map(function (t) {
      return { full_url: t.dataset.full, nombre: t.dataset.nombre || '' };
    });
    thumbs.forEach(function (t, i) {
      t.addEventListener('click', function () { abrir(i); });
    });
  }

  return { attach: attach };
})();
