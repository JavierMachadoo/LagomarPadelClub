const Toast = (() => {
    const container = document.getElementById('toastContainer');
    let toastCounter = 0;

    const icons = {
        success: 'check-circle-fill',
        error: 'exclamation-triangle-fill',
        warning: 'exclamation-triangle-fill',
        info: 'info-circle-fill'
    };

    const colors = {
        success: 'text-bg-success',
        error: 'text-bg-danger',
        warning: 'text-bg-warning',
        info: 'text-bg-info'
    };

    function show(message, type = 'info', duration = 3000) {
        const toastId = `toast-${++toastCounter}`;
        const icon = icons[type] || icons.info;
        const color = colors[type] || colors.info;

        const toastHtml = `
            <div id="${toastId}" class="toast toast-custom ${color}" role="alert">
                <div class="toast-header ${color}">
                    <i class="bi bi-${icon} me-2"></i>
                    <strong class="me-auto">Notificación</strong>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast"></button>
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
