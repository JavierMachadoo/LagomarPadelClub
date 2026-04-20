// ==================== CALENDARIO DOMINGO (Admin) ====================
// Drag & Drop con HTML5 nativo para mover partidos entre slots horarios.

const CAT_STYLES_DOMINGO = {
    'Tercera': { border: '#fd7e14', bg: '#fff3e0', emoji: '🟠' },
    'Cuarta':  { border: '#28a745', bg: '#d4edda', emoji: '🟢' },
    'Quinta':  { border: '#ffc107', bg: '#fff3cd', emoji: '🟡' },
    'Sexta':   { border: '#17a2b8', bg: '#d1ecf1', emoji: '🔵' },
    'Séptima': { border: '#9b7fed', bg: '#e7e3ff', emoji: '🟣' },
    'Octava':  { border: '#dc3545', bg: '#fce4e6', emoji: '🔴' },
};
const DEFAULT_STYLE = { border: '#6c757d', bg: '#f8f9fa', emoji: '⚪' };

const HORAS_DOMINGO = ['10:00','11:00','12:00','13:00','14:00','15:00','16:00','17:00','18:00','19:00','20:00','21:00'];

let calendarioDomingoData = null;
let domingoInicializado = false;
let dragOrigenId = null;
let dragOrigenHora = null;
let dragOrigenCancha = null;

function inicializarCalendarioDomingo() {
    if (domingoInicializado) return;
    domingoInicializado = true;
    cargarCalendarioDomingo();
}

async function cargarCalendarioDomingo() {
    const container = document.getElementById('calendarioDomingoContainer');
    if (!container) return;
    container.innerHTML = '<div class="text-center py-5"><div class="spinner-border text-primary"></div><p class="mt-2 text-muted">Cargando calendario...</p></div>';

    try {
        const response = await fetch('/api/finales/calendario', { credentials: 'same-origin' });
        if (response.status === 401) { window.location.href = '/login'; return; }
        const data = await response.json();
        if (data.success) {
            calendarioDomingoData = data.calendario;
            renderizarGrillaCalendario(data.calendario);
        } else {
            container.innerHTML = `<div class="alert alert-warning">${data.message || 'No hay calendario disponible aún.'}</div>`;
        }
    } catch (err) {
        container.innerHTML = '<div class="alert alert-danger">Error al cargar el calendario.</div>';
    }
}

function restablecerCalendarioDomingo() {
    Confirmar.show(
        '¿Restablecer el calendario automáticamente? Se perderán los cambios manuales.',
        async () => {
            try {
                const response = await fetch('/api/finales/fixtures/regenerar', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/json' },
                });
                const data = await response.json();
                if (data.success) {
                    Toast.success('Calendario restablecido correctamente');
                    await cargarCalendarioDomingo();
                } else {
                    Toast.error(data.message || 'Error al restablecer');
                }
            } catch (err) {
                Toast.error('Error de conexión');
            }
        },
        { titulo: 'Restablecer calendario', textoOk: 'Restablecer', claseOk: 'btn-warning text-dark' }
    );
}

// ---- Renderizado ----

function renderizarGrillaCalendario(calendario) {
    const container = document.getElementById('calendarioDomingoContainer');
    if (!container) return;

    const cancha1 = calendario.cancha_1 || [];
    const cancha2 = calendario.cancha_2 || [];

    // Construir índice: hora → { cancha_1: partido|null, cancha_2: partido|null }
    const grid = {};
    HORAS_DOMINGO.forEach(h => { grid[h] = { cancha_1: null, cancha_2: null }; });
    cancha1.forEach(p => { if (grid[p.hora_inicio]) grid[p.hora_inicio].cancha_1 = p; });
    cancha2.forEach(p => { if (grid[p.hora_inicio]) grid[p.hora_inicio].cancha_2 = p; });

    const filas = HORAS_DOMINGO.map(hora => {
        const c1 = grid[hora].cancha_1;
        const c2 = grid[hora].cancha_2;
        return `
        <tr>
            <td class="text-center fw-bold text-muted align-middle" style="white-space:nowrap; width:60px;">
                ${hora}
            </td>
            <td class="p-1 droppable-cell" data-hora="${hora}" data-cancha="1"
                ondragover="onDragOver(event)" ondrop="onDrop(event)">
                ${c1 ? renderizarCardPartido(c1) : renderizarCeldaVacia()}
            </td>
            <td class="p-1 droppable-cell" data-hora="${hora}" data-cancha="2"
                ondragover="onDragOver(event)" ondrop="onDrop(event)">
                ${c2 ? renderizarCardPartido(c2) : renderizarCeldaVacia()}
            </td>
        </tr>`;
    }).join('');

    container.innerHTML = `
        <div class="table-responsive">
            <table class="table table-bordered table-sm mb-0" style="min-width:480px;">
                <thead class="table-dark">
                    <tr>
                        <th class="text-center" style="width:60px;">Hora</th>
                        <th class="text-center">
                            <i class="bi bi-1-circle-fill me-1"></i> Cancha 1
                        </th>
                        <th class="text-center">
                            <i class="bi bi-2-circle-fill me-1"></i> Cancha 2
                        </th>
                    </tr>
                </thead>
                <tbody>${filas}</tbody>
            </table>
        </div>
    `;
}

function renderizarCardPartido(partido) {
    const style = CAT_STYLES_DOMINGO[partido.categoria] || DEFAULT_STYLE;
    const p1 = partido.pareja1 || 'Por definir';
    const p2 = partido.pareja2 || 'Por definir';
    const faseCorta = partido.fase
        .replace('Octavos de Final', 'Octavos')
        .replace('Cuartos de Final', 'Cuartos')
        .replace('Semifinal', 'Semis');

    const parts = partido.partido_id ? partido.partido_id.split('_') : [];
    const lastPart = parts[parts.length - 1];
    const numPartido = (!isNaN(lastPart) && lastPart !== '') ? ` ${lastPart}` : '';
    const faseConNumero = `${faseCorta}${numPartido}`;

    return `
        <div class="partido-card-domingo"
             draggable="true"
             data-partido-id="${partido.partido_id}"
             data-hora="${partido.hora_inicio}"
             data-cancha="${partido.cancha}"
             ondragstart="onDragStart(event)"
             ondragend="onDragEnd(event)"
             style="border-left: 4px solid ${style.border}; background: ${style.bg}; border-radius: 8px; padding: 0.5rem 0.75rem; cursor: grab; user-select: none;">
            <div class="d-flex justify-content-between align-items-center mb-1">
                <span style="font-size:0.75rem; font-weight:600; color:${style.border};">
                    ${style.emoji} ${partido.categoria} — ${faseConNumero}
                </span>
                <i class="bi bi-grip-vertical text-muted" style="font-size:0.85rem;"></i>
            </div>
            <div style="font-size:0.8rem; line-height:1.3;">
                <div class="fw-semibold">${p1}</div>
                <div class="text-muted" style="font-size:0.7rem;">vs</div>
                <div class="fw-semibold">${p2}</div>
            </div>
        </div>`;
}

function renderizarCeldaVacia() {
    return `<div class="celda-vacia-domingo" style="min-height:80px; border: 2px dashed #dee2e6; border-radius:8px; display:flex; align-items:center; justify-content:center; color:#adb5bd; font-size:0.8rem;">
        <i class="bi bi-plus-circle me-1"></i> libre
    </div>`;
}

// ---- Drag & Drop ----

function onDragStart(event) {
    const card = event.currentTarget;
    dragOrigenId = card.dataset.partidoId;
    dragOrigenHora = card.dataset.hora;
    dragOrigenCancha = parseInt(card.dataset.cancha);

    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', dragOrigenId);
    card.style.opacity = '0.4';
}

function onDragEnd(event) {
    event.currentTarget.style.opacity = '';
    document.querySelectorAll('.droppable-cell').forEach(c => c.classList.remove('drag-over-domingo'));
}

function onDragOver(event) {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
    const cell = event.currentTarget;
    document.querySelectorAll('.droppable-cell').forEach(c => c.classList.remove('drag-over-domingo'));
    cell.classList.add('drag-over-domingo');
}

async function onDrop(event) {
    event.preventDefault();
    document.querySelectorAll('.droppable-cell').forEach(c => c.classList.remove('drag-over-domingo'));

    const cell = event.currentTarget;
    const nuevaHora = cell.dataset.hora;
    const nuevaCancha = parseInt(cell.dataset.cancha);

    // Ignorar si se suelta en el mismo slot
    if (nuevaHora === dragOrigenHora && nuevaCancha === dragOrigenCancha) return;

    await moverPartidoCalendario(dragOrigenId, nuevaHora, nuevaCancha);
}

async function moverPartidoCalendario(partidoId, nuevaHora, nuevaCancha) {
    try {
        const response = await fetch(`/api/finales/calendario/partido/${encodeURIComponent(partidoId)}`, {
            method: 'PUT',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ nueva_hora: nuevaHora, nueva_cancha: nuevaCancha }),
        });
        const data = await response.json();
        if (data.success) {
            calendarioDomingoData = data.calendario;
            renderizarGrillaCalendario(data.calendario);
        } else {
            Toast.error(data.message || 'Error al mover el partido');
        }
    } catch (err) {
        Toast.error('Error de conexión');
    }
}
