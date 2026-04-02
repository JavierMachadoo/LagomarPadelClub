// ==================== LLAVES / BRACKET ====================
// Wrapper para compatibilidad con las funciones de finales
function showToast(message, type = 'info') {
    if (type === 'success') Toast.success(message);
    else if (type === 'danger' || type === 'error') Toast.error(message);
    else if (type === 'warning') Toast.warning(message);
    else Toast.info(message);
}

// CAT_MAP_FINALES: mapeo local de nombres largos a códigos cortos
// CATEGORIAS_TORNEO_FINALES y CATS_ACTIVAS_FINALES se definen en el inline script del HTML
// con Jinja2 y se asumen disponibles como globales al momento de ejecutar este archivo.
const CAT_MAP_FINALES = {
    'Tercera': '3era', 'Cuarta': '4ta', 'Quinta': '5ta', 'Sexta': '6ta', 'Séptima': '7ma'
};

let currentCategoria = (typeof CATS_ACTIVAS_FINALES !== 'undefined' ? CATS_ACTIVAS_FINALES[0] : null) || '3era';
let fixtures = {};
let calendarioIndex = {};
let llavesInicializadas = false;
let pollInterval = 60000;
let pollTimer = null;
const _partidosFinalesData = {};

function iniciarPolling() {
    pollTimer = setTimeout(async () => {
        try {
            await cargarFixtures(true);
            pollInterval = 60000;
        } catch {
            pollInterval = Math.min(pollInterval * 2, 300000);
        }
        iniciarPolling();
    }, pollInterval);
}

function detenerPolling() {
    clearTimeout(pollTimer);
}

function inicializarLlaves() {
    if (llavesInicializadas) return;
    llavesInicializadas = true;
    cargarFixtures();
    cargarCalendarioIndex();
    iniciarPolling();
    const drawContainer = document.getElementById('drawContainer');
    if (drawContainer) {
        drawContainer.addEventListener('click', e => {
            const card = e.target.closest('[data-open-partido]');
            if (!card) return;
            const datos = _partidosFinalesData[card.dataset.openPartido];
            if (datos) abrirModalResultadoFinal(card.dataset.openPartido, datos.categoria, datos.p1, datos.p2);
        });
    }
}

async function cargarFixtures(silencioso = false) {
    try {
        const response = await fetch('/api/finales/fixtures', { credentials: 'same-origin' });
        const contentType = response.headers.get('content-type') || '';
        if (!contentType.includes('application/json')) {
            if (!silencioso) showToast('El servidor está iniciando, intentá de nuevo en unos segundos', 'warning');
            return;
        }
        if (response.status === 401) { window.location.href = '/login'; return; }
        const data = await response.json();
        if (data.success) {
            fixtures = {};
            if (data.fixtures['Tercera']) fixtures['3era'] = data.fixtures['Tercera'];
            if (data.fixtures['Cuarta'])  fixtures['4ta']  = data.fixtures['Cuarta'];
            if (data.fixtures['Quinta'])  fixtures['5ta']  = data.fixtures['Quinta'];
            if (data.fixtures['Sexta'])   fixtures['6ta']  = data.fixtures['Sexta'];
            if (data.fixtures['Séptima']) fixtures['7ma']  = data.fixtures['Séptima'];
            if (Object.keys(fixtures).length === 0) fixtures = data.fixtures;
            actualizarDetallesCategorias();
            cambiarCategoria(currentCategoria || CATS_ACTIVAS_FINALES[0]);
        }
    } catch (error) {
    }
}

function actualizarDetallesCategorias() {
    CATS_ACTIVAS_FINALES.forEach(cat => {
        const fixture = fixtures[cat];
        let fases = [];
        if (fixture) {
            if (fixture.octavos && fixture.octavos.length > 0) fases.push('Octavos');
            if (fixture.cuartos && fixture.cuartos.length > 0) fases.push('Cuartos');
            if (fixture.semifinales && fixture.semifinales.length > 0) fases.push('Semis');
            if (fixture.final) fases.push('Final');
        }
        const el = document.getElementById(`fases-${cat}`);
        if (el) el.textContent = fases.length > 0 ? fases.join(' • ') : 'Sin fases';
    });
}

function cambiarCategoria(categoria, event = null) {
    currentCategoria = categoria;
    document.querySelectorAll('.categoria-btn').forEach(btn => btn.classList.remove('active'));
    if (event && event.target) {
        event.target.closest('.categoria-btn').classList.add('active');
    } else {
        const button = Array.from(document.querySelectorAll('.categoria-btn')).find(
            btn => btn.textContent.includes(categoria)
        );
        if (button) button.classList.add('active');
    }
    renderizarFixture(categoria);
}

function renderizarFixture(categoria) {
    const container = document.getElementById('drawContainer');
    if (!container) return;
    const fixture = fixtures[categoria];
    if (!fixture) { container.innerHTML = crearPartidosVacios(categoria); return; }
    let hasAnyRound = false;
    let columns = [];
    if (fixture.octavos && fixture.octavos.length > 0) { hasAnyRound = true; columns.push(renderizarColumnaITF('Octavos de Final', fixture.octavos, categoria, true)); }
    if (fixture.cuartos && fixture.cuartos.length > 0) { hasAnyRound = true; columns.push(renderizarColumnaITF('Cuartos de Final', fixture.cuartos, categoria, true)); }
    if (fixture.semifinales && fixture.semifinales.length > 0) { hasAnyRound = true; columns.push(renderizarColumnaITF('Semifinales', fixture.semifinales, categoria, true)); }
    if (fixture.final) { hasAnyRound = true; columns.push(renderizarColumnaITF('Final', [fixture.final], categoria, false)); }
    if (!hasAnyRound) {
        container.innerHTML = crearPartidosVacios(categoria);
    } else {
        container.innerHTML = `<div class="draw-grid">${columns.join('')}</div>`;
        setTimeout(() => dibujarLineasConectoras(), 100);
    }
}

function crearPartidosVacios(categoria) {
    const html = `
        <div class="draw-grid">
            <div class="round-column">
                <div class="round-header-itf">Cuartos de Final<div class="position-badges"><small style="opacity:.85;font-size:.7rem;">Perdedores: 5° - 8° Lugar</small></div></div>
                <div class="matches-column">${renderizarPartidoVacioITF()}${renderizarPartidoVacioITF()}${renderizarPartidoVacioITF()}${renderizarPartidoVacioITF()}</div>
            </div>
            <div class="round-column">
                <div class="round-header-itf">Semifinales<div class="position-badges"><small style="opacity:.85;font-size:.7rem;">Perdedores: 3° - 4° Lugar</small></div></div>
                <div class="matches-column">${renderizarPartidoVacioITF()}${renderizarPartidoVacioITF()}</div>
            </div>
            <div class="round-column">
                <div class="round-header-itf">Final<div class="position-badges"><span class="badge bg-warning text-dark">🥇 1° Lugar</span><span class="badge bg-secondary">🥈 2° Lugar</span></div></div>
                <div class="matches-column">${renderizarPartidoVacioITF()}</div>
            </div>
        </div>`;
    setTimeout(() => dibujarLineasConectoras(), 100);
    return html;
}

function renderizarPartidoVacioITF() {
    return `<div class="match-wrapper"><div class="match-card-itf" style="cursor:default;"><div class="player-row-itf por-definir"><span class="player-name-itf">— Por definir —</span><span></span><div class="player-scores"></div></div><div class="player-row-itf por-definir"><span class="player-name-itf">— Por definir —</span><span></span><div class="player-scores"></div></div></div></div>`;
}

function renderizarColumnaITF(titulo, partidos, categoria, tieneSiguienteRonda = false) {
    const hasNextClass = tieneSiguienteRonda ? 'has-next' : '';
    let headerExtra = '';
    if (titulo === 'Cuartos de Final') headerExtra = `<div class="position-badges"><small style="opacity:.85;font-size:.7rem;">Perdedores: 5° - 8° Lugar</small></div>`;
    else if (titulo === 'Semifinales') headerExtra = `<div class="position-badges"><small style="opacity:.9;font-size:.7rem;">Perdedores: 3° - 4° Lugar</small></div>`;
    else if (titulo === 'Final') headerExtra = `<div class="position-badges"><span class="badge bg-warning text-dark">🥇 1° Lugar</span><span class="badge bg-secondary">🥈 2° Lugar</span></div>`;
    let html = `<div class="round-column ${hasNextClass}"><div class="round-header-itf">${titulo}${headerExtra}</div><div class="matches-column">`;
    partidos.forEach((partido, idx) => { html += renderizarPartidoITF(partido, categoria, tieneSiguienteRonda, idx); });
    html += `</div></div>`;
    return html;
}

function renderizarPartidoITF(partido, categoria, tieneSiguienteRonda = false, idx = 0) {
    const sets = partido.sets || [];
    const tieneResultado = sets.length > 0;
    let pareja1Text = '', pareja2Text = '';
    if (partido.pareja1) {
        if (tieneResultado) { pareja1Text = `<span class="player-name-itf">${partido.pareja1.nombre}</span>`; }
        else if (partido.slot1_info && partido.slot1_info !== 'Vacío') { pareja1Text = `<span class="player-name-itf">${partido.pareja1.nombre}</span><small style="display:block;opacity:.7;font-size:.7rem;margin-top:2px;">${partido.slot1_info}</small>`; }
        else { pareja1Text = `<span class="player-name-itf">${partido.pareja1.nombre}</span>`; }
    } else { pareja1Text = partido.slot1_info || '— Por definir —'; }
    if (partido.pareja2) {
        if (tieneResultado) { pareja2Text = `<span class="player-name-itf">${partido.pareja2.nombre}</span>`; }
        else if (partido.slot2_info && partido.slot2_info !== 'Vacío') { pareja2Text = `<span class="player-name-itf">${partido.pareja2.nombre}</span><small style="display:block;opacity:.7;font-size:.7rem;margin-top:2px;">${partido.slot2_info}</small>`; }
        else { pareja2Text = `<span class="player-name-itf">${partido.pareja2.nombre}</span>`; }
    } else { pareja2Text = partido.slot2_info || '— Por definir —'; }
    const ganador = partido.ganador ? partido.ganador.id : null;
    const pareja1Id = partido.pareja1 ? partido.pareja1.id : null;
    const pareja2Id = partido.pareja2 ? partido.pareja2.id : null;
    const pareja1Class = ganador === pareja1Id ? 'winner' : '';
    const pareja2Class = ganador === pareja2Id ? 'winner' : '';
    const porDefinir1 = !partido.pareja1 ? 'por-definir' : '';
    const porDefinir2 = !partido.pareja2 ? 'por-definir' : '';
    let setsHTML1 = '', setsHTML2 = '';
    if (tieneResultado) {
        sets.forEach(set => {
            setsHTML1 += `<div class="score-set">${set.pareja1 || '-'}</div>`;
            setsHTML2 += `<div class="score-set">${set.pareja2 || '-'}</div>`;
        });
    }
    const pareja1Nombre = partido.pareja1 ? partido.pareja1.nombre : (partido.slot1_info || 'Por definir');
    const pareja2Nombre = partido.pareja2 ? partido.pareja2.nombre : (partido.slot2_info || 'Por definir');
    let clickHandler = '';
    if (partido.pareja1 && partido.pareja2 && !ganador) {
        _partidosFinalesData[partido.id] = { categoria, p1: pareja1Nombre, p2: pareja2Nombre };
        clickHandler = `data-open-partido="${partido.id}"`;
    }
    const cursorStyle = partido.pareja1 && partido.pareja2 && !ganador ? 'cursor:pointer;' : 'cursor:default;';
    const horarioInfo = calendarioIndex[partido.id]
        ? `<div class="match-schedule-info"><span class="match-schedule-cancha"><i class="bi bi-geo-alt-fill"></i> Cancha ${calendarioIndex[partido.id].cancha}</span><span>·</span><span><i class="bi bi-clock"></i> ${calendarioIndex[partido.id].hora_inicio}</span></div>` : '';
    return `<div class="match-wrapper">${horarioInfo}<div class="match-card-itf" ${clickHandler} style="${cursorStyle}"><div class="player-row-itf ${pareja1Class} ${porDefinir1}">${pareja1Text}${(partido.pareja1 && ganador === pareja1Id) ? '<i class="bi bi-check-circle-fill player-check"></i>' : ''}<div class="player-scores">${setsHTML1}</div></div><div class="player-row-itf ${pareja2Class} ${porDefinir2}">${pareja2Text}${(partido.pareja2 && ganador === pareja2Id) ? '<i class="bi bi-check-circle-fill player-check"></i>' : ''}<div class="player-scores">${setsHTML2}</div></div></div></div>`;
}

function dibujarLineasConectoras() {
    const drawGrid = document.querySelector('.draw-grid');
    if (!drawGrid) return;
    const existingSvg = drawGrid.querySelector('.bracket-connections');
    if (existingSvg) existingSvg.remove();
    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute('class', 'bracket-connections');
    svg.style.cssText = 'position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:0;';
    const columns = Array.from(drawGrid.querySelectorAll('.round-column'));
    for (let i = 0; i < columns.length - 1; i++) {
        const currentMatches = Array.from(columns[i].querySelectorAll('.match-wrapper'));
        const nextMatches = Array.from(columns[i + 1].querySelectorAll('.match-wrapper'));
        for (let j = 0; j < nextMatches.length; j++) {
            const match1 = currentMatches[j * 2];
            const match2 = currentMatches[j * 2 + 1];
            const nextMatch = nextMatches[j];
            if (match1 && match2 && nextMatch) dibujarConexionBracket(svg, match1, match2, nextMatch, drawGrid);
        }
    }
    drawGrid.appendChild(svg);
}

function dibujarConexionBracket(svg, match1, match2, nextMatch, container) {
    const svgNS = "http://www.w3.org/2000/svg";
    const containerRect = container.getBoundingClientRect();
    const rect1 = match1.getBoundingClientRect();
    const rect2 = match2.getBoundingClientRect();
    const rectNext = nextMatch.getBoundingClientRect();
    const x1 = rect1.right - containerRect.left, y1 = rect1.top + rect1.height / 2 - containerRect.top;
    const x2 = rect2.right - containerRect.left, y2 = rect2.top + rect2.height / 2 - containerRect.top;
    const xNext = rectNext.left - containerRect.left, yNext = rectNext.top + rectNext.height / 2 - containerRect.top;
    const xMid = x1 + (xNext - x1) / 2;
    const path = document.createElementNS(svgNS, "path");
    path.setAttribute('d', `M ${x1} ${y1} L ${xMid} ${y1} L ${xMid} ${yNext} M ${x2} ${y2} L ${xMid} ${y2} L ${xMid} ${yNext} M ${xMid} ${yNext} L ${xNext} ${yNext}`);
    path.setAttribute('class', 'bracket-line');
    svg.appendChild(path);
}

window.addEventListener('resize', () => { if (document.querySelector('.draw-grid')) dibujarLineasConectoras(); });

function limitarGamesInput(input, maxValue = 6) {
    let value = parseInt(input.value);
    if (isNaN(value) || value < 0) input.value = '';
    else if (value > maxValue) input.value = maxValue;
}

function verificarNecesidadTiebreak() {
    const s1p1 = parseInt(document.getElementById('gamesSet1P1').value) || 0;
    const s1p2 = parseInt(document.getElementById('gamesSet1P2').value) || 0;
    const s2p1 = parseInt(document.getElementById('gamesSet2P1').value) || 0;
    const s2p2 = parseInt(document.getElementById('gamesSet2P2').value) || 0;
    if (s1p1 === 0 && s1p2 === 0 && s2p1 === 0 && s2p2 === 0) { document.getElementById('tiebreakCardFinal').style.display = 'none'; return; }
    const sP1 = (s1p1 > s1p2 ? 1 : 0) + (s2p1 > s2p2 ? 1 : 0);
    const sP2 = (s1p2 > s1p1 ? 1 : 0) + (s2p2 > s2p1 ? 1 : 0);
    document.getElementById('tiebreakCardFinal').style.display = (sP1 === 1 && sP2 === 1) ? 'block' : 'none';
}

function abrirModalResultadoFinal(partidoId, categoria, pareja1Nombre, pareja2Nombre) {
    document.getElementById('resultadoPartidoId').value = partidoId;
    document.getElementById('resultadoCategoria').value = categoria;
    document.getElementById('resultadoFinalPareja1').textContent = pareja1Nombre;
    document.getElementById('resultadoFinalPareja2').textContent = pareja2Nombre;
    ['gamesSet1P1','gamesSet1P2','gamesSet2P1','gamesSet2P2','tiebreakP1','tiebreakP2'].forEach(id => { document.getElementById(id).value = ''; });
    document.getElementById('tiebreakCardFinal').style.display = 'none';
    const setInputs = ['gamesSet1P1','gamesSet1P2','gamesSet2P1','gamesSet2P2'];
    setInputs.forEach(id => {
        const input = document.getElementById(id);
        input.removeEventListener('input', verificarNecesidadTiebreak);
        input.addEventListener('input', () => { limitarGamesInput(input, 6); verificarNecesidadTiebreak(); });
        input.addEventListener('blur', () => limitarGamesInput(input, 6));
    });
    new bootstrap.Modal(document.getElementById('modalResultadoFinal')).show();
}

async function guardarResultadoFinal() {
    const partidoId = document.getElementById('resultadoPartidoId').value;
    const s1p1 = parseInt(document.getElementById('gamesSet1P1').value) || 0;
    const s1p2 = parseInt(document.getElementById('gamesSet1P2').value) || 0;
    const s2p1 = parseInt(document.getElementById('gamesSet2P1').value) || 0;
    const s2p2 = parseInt(document.getElementById('gamesSet2P2').value) || 0;
    function esSetValido(a, b) {
        return (a === 6 && b >= 0 && b <= 5) || (b === 6 && a >= 0 && a <= 5);
    }
    if (!esSetValido(s1p1, s1p2)) { showToast('Set 1 inválido: el ganador debe tener exactamente 6 games y el perdedor entre 0 y 5 (ej: 6-4). No puede haber 6-6.', 'warning'); return; }
    if (!esSetValido(s2p1, s2p2)) { showToast('Set 2 inválido: el ganador debe tener exactamente 6 games y el perdedor entre 0 y 5 (ej: 6-3). No puede haber 6-6.', 'warning'); return; }
    const sets = [{ pareja1: s1p1, pareja2: s1p2 }, { pareja1: s2p1, pareja2: s2p2 }];
    const sP1 = (s1p1 > s1p2 ? 1 : 0) + (s2p1 > s2p2 ? 1 : 0);
    const sP2 = (s1p2 > s1p1 ? 1 : 0) + (s2p2 > s2p1 ? 1 : 0);
    if (sP1 === 1 && sP2 === 1) {
        const tP1 = parseInt(document.getElementById('tiebreakP1').value);
        const tP2 = parseInt(document.getElementById('tiebreakP2').value);
        if (isNaN(tP1) || isNaN(tP2)) { showToast('Debes ingresar el resultado del super tie-break', 'warning'); document.getElementById('tiebreakCardFinal').style.display = 'block'; return; }
        if (tP1 === tP2) { showToast('El super tie-break no puede quedar empatado', 'warning'); return; }
        const tbGanador = Math.max(tP1, tP2);
        const tbPerdedor = Math.min(tP1, tP2);
        if (tbGanador < 11) { showToast('El ganador del super tie-break debe llegar mínimo a 11 puntos', 'warning'); return; }
        if (tbGanador - tbPerdedor < 2) { showToast('El super tie-break se gana por al menos 2 puntos de diferencia (ej: 11-9, 12-10)', 'warning'); return; }
        sets.push({ pareja1: tP1, pareja2: tP2 });
    }
    try {
        const response = await fetch(`/api/finales/partido/${partidoId}/resultado`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sets }) });
        const data = await response.json();
        if (data.success) {
            showToast('Resultado guardado correctamente', 'success');
            bootstrap.Modal.getInstance(document.getElementById('modalResultadoFinal')).hide();
            await cargarFixtures();
        } else { showToast('Error al guardar resultado: ' + data.message, 'danger'); }
    } catch (error) { showToast('Error de conexión', 'danger'); }
}

async function cargarCalendarioIndex() {
    try {
        const response = await fetch('/api/finales/calendario', { credentials: 'same-origin' });
        if (!response.ok) return;
        const data = await response.json();
        if (!data.success) return;
        const nuevoIndex = {};
        [data.calendario.cancha_1 || [], data.calendario.cancha_2 || []].forEach(lista => {
            lista.forEach(p => { nuevoIndex[p.partido_id] = { cancha: p.cancha, hora_inicio: p.hora_inicio }; });
        });
        calendarioIndex = nuevoIndex;
        if (currentCategoria) renderizarFixture(currentCategoria);
    } catch (_) {}
}
