const Toast = (() => {
    const container = document.getElementById('toastContainer');
    let toastCounter = 0;

    const icons = {
        success: 'check-circle-fill',
        error: 'exclamation-triangle-fill',
        warning: 'exclamation-triangle-fill',
        info: 'info-circle-fill'
    };

    const styles = {
        success: {
            outer: 'background:#111111; color:#fff; border:1px solid rgba(34,197,94,0.4);',
            header: 'background:#111111; color:#fff; border-bottom:1px solid rgba(34,197,94,0.2);',
            icon:   'color:#22c55e;',
            close:  'btn-close-white'
        },
        error: {
            outer: 'background:#1a0000; color:#fff; border:1px solid rgba(239,68,68,0.4);',
            header: 'background:#1a0000; color:#fff; border-bottom:1px solid rgba(239,68,68,0.2);',
            icon:   'color:#f87171;',
            close:  'btn-close-white'
        },
        warning: {
            outer: 'background:#1a1200; color:#fff; border:1px solid rgba(234,179,8,0.4);',
            header: 'background:#1a1200; color:#fff; border-bottom:1px solid rgba(234,179,8,0.2);',
            icon:   'color:#facc15;',
            close:  'btn-close-white'
        },
        info: {
            outer: 'background:#001a1a; color:#fff; border:1px solid rgba(56,189,248,0.4);',
            header: 'background:#001a1a; color:#fff; border-bottom:1px solid rgba(56,189,248,0.2);',
            icon:   'color:#38bdf8;',
            close:  'btn-close-white'
        }
    };

    function show(message, type = 'info', duration = 3000) {
        const toastId = `toast-${++toastCounter}`;
        const icon = icons[type] || icons.info;
        const s = styles[type] || styles.info;

        const toastHtml = `
            <div id="${toastId}" class="toast toast-custom" role="alert" style="${s.outer} border-radius:12px; overflow:hidden;">
                <div class="toast-header" style="${s.header}">
                    <i class="bi bi-${icon} me-2" style="${s.icon}"></i>
                    <strong class="me-auto">Notificación</strong>
                    <button type="button" class="btn-close ${s.close}" data-bs-dismiss="toast"></button>
                </div>
                <div class="toast-body">
                    ${message}
                </div>
            </div>
        `;

        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = toastHtml;
        const toastElement = tempDiv.firstElementChild;
        
        container.appendChild(toastElement);

        const bsToast = new bootstrap.Toast(toastElement, {
            autohide: true,
            delay: duration
        });

        bsToast.show();

        toastElement.addEventListener('hidden.bs.toast', () => {
            toastElement.remove();
        });
    }

    return {
        success: (msg) => show(msg, 'success', 3000),
        error: (msg) => show(msg, 'error', 5000),
        warning: (msg) => show(msg, 'warning', 4000),
        info: (msg) => show(msg, 'info', 3000)
    };
})();

window.Toast = Toast;
