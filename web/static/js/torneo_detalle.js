(function () {
  'use strict';

  var TORNEO_ID  = window.TORNEO_DATA && window.TORNEO_DATA.id;
  var ES_ADMIN   = !!(window.TORNEO_DATA && window.TORNEO_DATA.esAdmin);
  var fotosLoaded = false;

  var $panel    = document.getElementById('fotos-panel');
  var $skeleton = document.getElementById('fotos-skeleton');
  var $content  = document.getElementById('fotos-content');
  var $empty    = document.getElementById('fotos-empty');
  var $btnVer   = document.getElementById('btn-ver-fotos');
  var $btnCerrar = document.getElementById('btn-cerrar-fotos');

  if (!TORNEO_ID || !$panel) return;

  // defer garantiza que el DOM ya está listo — llamamos init directamente
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  function init() {
    // Mostrar botón hero si hay carpeta configurada o es admin
    var tieneFolderOAdmin = !!(window.TORNEO_DATA.driveFolderId || ES_ADMIN);
    if ($btnVer && tieneFolderOAdmin) $btnVer.hidden = false;

    if ($btnVer) $btnVer.addEventListener('click', abrirPanel);
    if ($btnCerrar) $btnCerrar.addEventListener('click', cerrarPanel);

    // Cerrar con Escape — cede el evento al lightbox si está abierto
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && $panel.classList.contains('is-open')) {
        var lb = document.getElementById('lb-root');
        if (lb && !lb.hidden) return;
        cerrarPanel();
      }
    });

    if (ES_ADMIN) configurarAdmin();
  }

  function lockScroll() {
    var n = (parseInt(document.body.dataset.scrollLocks, 10) || 0) + 1;
    document.body.dataset.scrollLocks = n;
    document.body.style.overflow = 'hidden';
  }

  function unlockScroll() {
    var n = Math.max(0, (parseInt(document.body.dataset.scrollLocks, 10) || 0) - 1);
    document.body.dataset.scrollLocks = n;
    if (n === 0) document.body.style.overflow = '';
  }

  function abrirPanel() {
    $panel.classList.add('is-open');
    lockScroll();
    if (!fotosLoaded) cargarFotos();
  }

  function cerrarPanel() {
    $panel.classList.remove('is-open');
    unlockScroll();
  }

  function cargarFotos() {
    fetch('/api/torneos/' + TORNEO_ID + '/fotos')
      .then(function (r) { return r.json(); })
      .then(function (data) { fotosLoaded = true; renderGaleria(data); })
      .catch(function (e) {
        console.warn('Error cargando galería:', e);
        fotosLoaded = true;
        mostrarEmpty();
      });
  }

  function renderGaleria(data) {
    $skeleton.hidden = true;
    var subcarpetas = data.subcarpetas || [];
    if (!subcarpetas.length) { mostrarEmpty(); return; }
    $content.hidden = false;
    $content.innerHTML = subcarpetas.map(renderSubcarpeta).join('');
    if (window.Lightbox) window.Lightbox.attach($content);
  }

  function renderSubcarpeta(sub) {
    var fotos = (sub.fotos || []).map(function (f) {
      return '<button class="foto-thumb" type="button"' +
             ' data-full="' + f.full_url + '"' +
             ' data-nombre="' + escapeHtml(f.nombre) + '"' +
             ' data-download="' + f.download_url + '">' +
             '<img src="' + f.thumbnail_url + '" alt="' + escapeHtml(f.nombre) + '" loading="lazy">' +
             '</button>';
    }).join('');
    return '<div class="fotos-subcarpeta">' +
           '<h3 class="fotos-subcarpeta-title">' + escapeHtml(sub.nombre) + '</h3>' +
           '<div class="fotos-grid">' + fotos + '</div>' +
           '</div>';
  }

  function mostrarEmpty() {
    $skeleton.hidden = true;
    $content.hidden = true;
    $empty.hidden = false;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  }

  // ── Admin modal ──────────────────────────────────────────────
  function configurarAdmin() {
    var $btn      = document.getElementById('btn-abrir-modal-drive');
    var $modal    = document.getElementById('modal-drive');
    var $form     = document.getElementById('form-drive');
    var $input    = document.getElementById('drive-folder-input');
    var $errEl    = document.getElementById('drive-error');

    if (!$btn || !$modal) return;

    $btn.hidden = false;
    $btn.addEventListener('click', function () {
      if ($errEl) $errEl.textContent = '';
      if ($input) $input.value = '';
      $modal.classList.add('is-open');
      if ($input) $input.focus();
    });

    $modal.querySelectorAll('[data-close]').forEach(function (el) {
      el.addEventListener('click', function () { $modal.classList.remove('is-open'); });
    });

    if ($form) $form.addEventListener('submit', function (e) {
      e.preventDefault();
      if ($errEl) $errEl.textContent = '';
      var folder_url = $input ? $input.value.trim() : '';
      if (!folder_url) {
        if ($errEl) $errEl.textContent = 'Ingresá una URL o ID de Google Drive.';
        return;
      }
      fetch('/api/admin/torneos/' + TORNEO_ID + '/drive-folder', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ folder_url: folder_url }),
      })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
        .then(function (res) {
          if (!res.ok) {
            if ($errEl) $errEl.textContent = res.data.error || 'Error al guardar.';
            return;
          }
          if (window.Toast) window.Toast.success('Carpeta de fotos vinculada correctamente');
          $modal.classList.remove('is-open');
          $skeleton.hidden = false;
          $content.hidden  = true;
          $empty.hidden    = true;
          fotosLoaded = false;
          if ($btnVer) $btnVer.hidden = false;
          fetch('/api/torneos/' + TORNEO_ID + '/fotos')
            .then(function (r) { return r.json(); })
            .then(function (data) { fotosLoaded = true; renderGaleria(data); })
            .catch(mostrarEmpty);
        })
        .catch(function () {
          if ($errEl) $errEl.textContent = 'Error de red. Intentá de nuevo.';
        });
    });
  }
})();
