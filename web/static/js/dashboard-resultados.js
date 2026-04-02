// ==================== FUNCIONES PARA RESULTADOS DE PARTIDOS ====================

function abrirModalResultado(categoria, grupoId, pareja1Id, pareja2Id, pareja1Nombre, pareja2Nombre) {

    // Validar que tenemos IDs válidos
    if (!pareja1Id || !pareja2Id || pareja1Id === 0 || pareja2Id === 0) {
        Toast.error('Error: No se pudieron cargar los IDs de las parejas. Recarga la página.');
        return;
    }


    // Verificar que todos los elementos críticos existen
    const elementosCriticos = [
        'resultadoCategoria', 'resultadoGrupoId', 'resultadoPareja1Id', 'resultadoPareja2Id',
        'resultadoPareja1Nombre', 'resultadoPareja2Nombre',
        'formResultadoPartido', 'tiebreakCard',
        'modalResultadoPartido'
    ];

    const elementosFaltantes = elementosCriticos.filter(id => !document.getElementById(id));
    if (elementosFaltantes.length > 0) {
        Toast.error('Error: El modal no está completamente cargado. Recarga la página.');
        return;
    }


    // Guardar datos en el formulario
    document.getElementById('resultadoCategoria').value = categoria;
    document.getElementById('resultadoGrupoId').value = grupoId;
    document.getElementById('resultadoPareja1Id').value = pareja1Id;
    document.getElementById('resultadoPareja2Id').value = pareja2Id;

    // Actualizar nombres en el modal
    document.getElementById('resultadoPareja1Nombre').textContent = pareja1Nombre;
    document.getElementById('resultadoPareja2Nombre').textContent = pareja2Nombre;

    // Limpiar formulario
    document.getElementById('formResultadoPartido').reset();
    document.getElementById('tiebreakCard').style.display = 'none';

    const resumenGanador = document.getElementById('resumenGanador');
    if (resumenGanador) {
        resumenGanador.style.display = 'none';
    }

    // Cargar resultado existente si lo hay
    cargarResultadoExistente(categoria, grupoId, pareja1Id, pareja2Id);

    // Abrir modal - limpiar instancia previa y crear nueva
    const modalElement = document.getElementById('modalResultadoPartido');
    let modal = bootstrap.Modal.getInstance(modalElement);
    if (modal) {
        modal.dispose(); // Limpiar instancia anterior
    }
    modal = new bootstrap.Modal(modalElement, {
        backdrop: true,
        keyboard: true
    });

    // Agregar event listeners DESPUÉS de abrir el modal
    modalElement.addEventListener('shown.bs.modal', function agregarListeners() {

        // Event listeners para detectar cambios en los inputs
        const inputs = ['gamesSet1Pareja1', 'gamesSet1Pareja2', 'gamesSet2Pareja1', 'gamesSet2Pareja2', 'tiebreakPareja1', 'tiebreakPareja2'];
        inputs.forEach(id => {
            const input = document.getElementById(id);
            if (input) {
                // Usar onchange e oninput para asegurar detección
                input.oninput = verificarResultado;
                input.onchange = verificarResultado;
            }
        });

        // Agregar listener al botón de guardar
        const btnGuardar = document.getElementById('btnGuardarResultado');
        if (btnGuardar) {
            btnGuardar.onclick = function(e) {
                e.preventDefault();
                e.stopPropagation();
                guardarResultadoPartido();
            };
        }

        // Prevenir submit del formulario
        const form = document.getElementById('formResultadoPartido');
        if (form) {
            form.onsubmit = function(e) {
                e.preventDefault();
                return false;
            };
        }

        // Llamar a verificarResultado para revisar si hay que mostrar tie-break
        if (window.requestAnimationFrame) {
            window.requestAnimationFrame(function() {
                verificarResultado();
            });
        } else {
            setTimeout(verificarResultado, 0);
        }
    }, { once: true });

    // Limpiar al cerrar
    modalElement.addEventListener('hidden.bs.modal', function() {
        const instance = bootstrap.Modal.getInstance(modalElement);
        if (instance) {
            instance.dispose();
        }
    }, { once: true });

    modal.show();
}

function cargarResultadoExistente(categoria, grupoId, pareja1Id, pareja2Id) {
    // Obtener resultado desde los datos de session/backend si existe
    fetch(`/api/resultado_algoritmo`)
        .then(response => {
            if (!response.ok) {
                throw new Error('No se pudieron cargar los datos');
            }
            return response.json();
        })
        .then(data => {
            const grupos = data.grupos_por_categoria[categoria] || [];
            const grupo = grupos.find(g => g.id === grupoId);

            if (grupo && grupo.resultados) {
                const ids = [pareja1Id, pareja2Id].sort();
                const key = `${ids[0]}-${ids[1]}`;
                const resultado = grupo.resultados[key];

                if (resultado) {
                    // Llenar el formulario con el resultado existente
                    document.getElementById('gamesSet1Pareja1').value = resultado.games_set1_pareja1 || '';
                    document.getElementById('gamesSet1Pareja2').value = resultado.games_set1_pareja2 || '';
                    document.getElementById('gamesSet2Pareja1').value = resultado.games_set2_pareja1 || '';
                    document.getElementById('gamesSet2Pareja2').value = resultado.games_set2_pareja2 || '';

                    if (resultado.tiebreak_pareja1 !== null && resultado.tiebreak_pareja1 !== undefined) {
                        document.getElementById('tiebreakPareja1').value = resultado.tiebreak_pareja1;
                        document.getElementById('tiebreakPareja2').value = resultado.tiebreak_pareja2;
                        document.getElementById('tiebreakCard').style.display = 'block';
                    }

                    // Verificar y mostrar resumen
                    verificarResultado();
                }
            }
        })
        .catch(error => {
            // No mostramos error al usuario porque puede ser normal que no haya resultado previo
        });
}

function verificarResultado() {

    const set1P1 = parseInt(document.getElementById('gamesSet1Pareja1').value) || 0;
    const set1P2 = parseInt(document.getElementById('gamesSet1Pareja2').value) || 0;
    const set2P1 = parseInt(document.getElementById('gamesSet2Pareja1').value) || 0;
    const set2P2 = parseInt(document.getElementById('gamesSet2Pareja2').value) || 0;


    const tiebreakCard = document.getElementById('tiebreakCard');
    const resumenGanador = document.getElementById('resumenGanador');

    // Si el elemento tiebreakCard no existe, salir
    if (!tiebreakCard) {
        return;
    }

    // Verificar si ambos sets están ingresados
    if (set1P1 === 0 && set1P2 === 0 && set2P1 === 0 && set2P2 === 0) {
        tiebreakCard.style.display = 'none';
        if (resumenGanador) resumenGanador.style.display = 'none';
        return;
    }

    // Calcular sets ganados
    let setsP1 = 0;
    let setsP2 = 0;

    if (set1P1 > set1P2) setsP1++;
    else if (set1P2 > set1P1) setsP2++;

    if (set2P1 > set2P2) setsP1++;
    else if (set2P2 > set2P1) setsP2++;


    // Mostrar/ocultar tie-break
    if (setsP1 === 1 && setsP2 === 1) {
        tiebreakCard.style.display = 'block';
        if (resumenGanador) resumenGanador.style.display = 'none';

        // Ver si hay ganador por tie-break
        const tbP1 = parseInt(document.getElementById('tiebreakPareja1').value) || 0;
        const tbP2 = parseInt(document.getElementById('tiebreakPareja2').value) || 0;

        if (tbP1 > 0 || tbP2 > 0) {
            mostrarResumenGanador(setsP1, setsP2, tbP1, tbP2);
        } else {
            if (resumenGanador) resumenGanador.style.display = 'none';
        }
    } else {
        tiebreakCard.style.display = 'none';
        document.getElementById('tiebreakPareja1').value = '';
        document.getElementById('tiebreakPareja2').value = '';

        if (setsP1 > 0 || setsP2 > 0) {
            mostrarResumenGanador(setsP1, setsP2, 0, 0);
        } else {
            if (resumenGanador) resumenGanador.style.display = 'none';
        }
    }
}

function mostrarResumenGanador(setsP1, setsP2, tbP1, tbP2) {
    const resumenGanador = document.getElementById('resumenGanador');
    const nombreGanador = document.getElementById('nombreGanador');
    const detalleResultado = document.getElementById('detalleResultado');

    // Si los elementos no existen, salir
    if (!resumenGanador || !nombreGanador || !detalleResultado) {
        return;
    }

    const pareja1Nombre = document.getElementById('resultadoPareja1Nombre').textContent;
    const pareja2Nombre = document.getElementById('resultadoPareja2Nombre').textContent;

    const set1P1 = document.getElementById('gamesSet1Pareja1').value;
    const set1P2 = document.getElementById('gamesSet1Pareja2').value;
    const set2P1 = document.getElementById('gamesSet2Pareja1').value;
    const set2P2 = document.getElementById('gamesSet2Pareja2').value;

    let ganador = '';
    let detalle = '';

    if (setsP1 === 2) {
        ganador = pareja1Nombre;
        detalle = `${set1P1}-${set1P2}, ${set2P1}-${set2P2}`;
    } else if (setsP2 === 2) {
        ganador = pareja2Nombre;
        detalle = `${set1P2}-${set1P1}, ${set2P2}-${set2P1}`;
    } else if (setsP1 === 1 && setsP2 === 1) {
        if (tbP1 > tbP2 && tbP1 > 0) {
            ganador = pareja1Nombre;
            detalle = `${set1P1}-${set1P2}, ${set2P1}-${set2P2}, TB: ${tbP1}-${tbP2}`;
        } else if (tbP2 > tbP1 && tbP2 > 0) {
            ganador = pareja2Nombre;
            detalle = `${set1P2}-${set1P1}, ${set2P2}-${set2P1}, TB: ${tbP2}-${tbP1}`;
        } else {
            resumenGanador.style.display = 'none';
            return;
        }
    } else {
        resumenGanador.style.display = 'none';
        return;
    }

    nombreGanador.textContent = ganador;
    detalleResultado.textContent = detalle;
    resumenGanador.style.display = 'block';
}

function guardarResultadoPartido() {

    const categoria = document.getElementById('resultadoCategoria').value;
    const grupoId = parseInt(document.getElementById('resultadoGrupoId').value);
    const pareja1Id = parseInt(document.getElementById('resultadoPareja1Id').value);
    const pareja2Id = parseInt(document.getElementById('resultadoPareja2Id').value);


    const gamesSet1P1 = parseInt(document.getElementById('gamesSet1Pareja1').value);
    const gamesSet1P2 = parseInt(document.getElementById('gamesSet1Pareja2').value);
    const gamesSet2P1 = parseInt(document.getElementById('gamesSet2Pareja1').value);
    const gamesSet2P2 = parseInt(document.getElementById('gamesSet2Pareja2').value);


    let tiebreakP1 = document.getElementById('tiebreakPareja1').value;
    let tiebreakP2 = document.getElementById('tiebreakPareja2').value;


    // Validaciones
    if (isNaN(gamesSet1P1) || isNaN(gamesSet1P2) || isNaN(gamesSet2P1) || isNaN(gamesSet2P2)) {
        Toast.error('Debes ingresar los resultados de ambos sets');
        return;
    }

    // Calcular sets
    let setsP1 = 0;
    let setsP2 = 0;
    if (gamesSet1P1 > gamesSet1P2) setsP1++;
    else setsP2++;
    if (gamesSet2P1 > gamesSet2P2) setsP1++;
    else setsP2++;

    // Si hay empate en sets, validar tie-break
    if (setsP1 === 1 && setsP2 === 1) {
        tiebreakP1 = parseInt(tiebreakP1);
        tiebreakP2 = parseInt(tiebreakP2);

        if (isNaN(tiebreakP1) || isNaN(tiebreakP2)) {
            Toast.error('Debes ingresar el resultado del super tie-break');
            return;
        }

        if (tiebreakP1 === tiebreakP2) {
            Toast.error('El tie-break no puede quedar empatado');
            return;
        }
    } else {
        tiebreakP1 = null;
        tiebreakP2 = null;
    }

    // Preparar datos
    const data = {
        categoria: categoria,
        grupo_id: grupoId,
        pareja1_id: pareja1Id,
        pareja2_id: pareja2Id,
        games_set1_pareja1: gamesSet1P1,
        games_set1_pareja2: gamesSet1P2,
        games_set2_pareja1: gamesSet2P1,
        games_set2_pareja2: gamesSet2P2,
        tiebreak_pareja1: tiebreakP1,
        tiebreak_pareja2: tiebreakP2
    };


    // Enviar al backend
    fetch('/api/guardar-resultado-partido', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    })
    .then(response => {
        return response.json();
    })
    .then(data => {
        if (data.success) {
            Toast.success(data.mensaje);

            // Cerrar modal
            const modalElement = document.getElementById('modalResultadoPartido');
            const modal = bootstrap.Modal.getInstance(modalElement);
            if (modal) {
                modal.hide();
            }

            // Guardar la pestaña activa antes del reload
            const activeTab = document.querySelector('#mainTabs .nav-link.active');
            if (activeTab) {
                sessionStorage.setItem('activeTab', activeTab.id);
            }

            // Recargar la página para mostrar los cambios
            setTimeout(() => {
                location.reload();
            }, 300);
        } else {
            Toast.error('Error: ' + data.error);
        }
    })
    .catch(error => {
        Toast.error('Error al guardar resultado: ' + error.message);
    });
}

function cargarTablaPosiciones(categoria, grupoId) {
    fetch(`/api/obtener-tabla-posiciones/${categoria}/${grupoId}`)
        .then(response => response.json())
        .then(data => {
            if (data.success && data.tabla) {
                renderizarTablaPosiciones(categoria, grupoId, data.tabla);
            } else if (data.error) {
            }
        })
        .catch(error => {
        });
}

function renderizarTablaPosiciones(categoria, grupoId, tabla) {
    const tbody = document.getElementById(`tbody-posiciones-${categoria}-${grupoId}`);

    if (!tbody) {
        return;
    }

    if (tabla.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="text-center text-muted">
                    <small>Ingresa los resultados de los partidos para ver la tabla</small>
                </td>
            </tr>
        `;
        return;
    }

    let html = '';
    tabla.forEach((fila, index) => {
        const medallas = ['🥇', '🥈', '🥉'];
        const medal = medallas[index] || '';
        const bgClass = index === 0 ? 'table-success' : index === 1 ? 'table-warning' : index === 2 ? 'table-info' : '';

        html += `
            <tr class="${bgClass}">
                <td class="text-center fw-bold">${medal} ${fila.posicion || '-'}</td>
                <td class="fw-bold">${fila.pareja_nombre}</td>
                <td class="text-center">${fila.partidos_jugados}</td>
                <td class="text-center fw-bold text-success">${fila.partidos_ganados}</td>
                <td class="text-center">
                    <small>${fila.sets_ganados}-${fila.sets_perdidos}</small>
                    <br>
                    <small class="text-muted">(${fila.diferencia_sets >= 0 ? '+' : ''}${fila.diferencia_sets})</small>
                </td>
                <td class="text-center">
                    <small>${fila.games_ganados}-${fila.games_perdidos}</small>
                    <br>
                    <small class="text-muted">(${fila.diferencia_games >= 0 ? '+' : ''}${fila.diferencia_games})</small>
                </td>
            </tr>
        `;
    });

    tbody.innerHTML = html;
}

// Función simplificada que obtiene los nombres del DOM
function abrirModalPorIds(categoria, grupoId, pareja1Id, pareja2Id) {

    // Validar IDs de parejas antes de realizar la petición
    const pareja1Num = Number(pareja1Id);
    const pareja2Num = Number(pareja2Id);
    if (!Number.isFinite(pareja1Num) || pareja1Num <= 0 ||
        !Number.isFinite(pareja2Num) || pareja2Num <= 0) {
        Toast.error('Identificadores de pareja inválidos');
        return;
    }

    // Buscar los nombres en los datos del resultado
    fetch('/api/resultado_algoritmo')
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            const grupos = data.grupos_por_categoria[categoria] || [];
            const grupo = grupos.find(g => g.id === grupoId);

            if (!grupo) {
                Toast.error('Grupo no encontrado');
                return;
            }

            // Buscar las parejas por ID
            const pareja1 = grupo.parejas.find(p => p.id === pareja1Id);
            const pareja2 = grupo.parejas.find(p => p.id === pareja2Id);

            if (!pareja1 || !pareja2) {
                Toast.error('Parejas no encontradas');
                return;
            }

            abrirModalResultado(categoria, grupoId, pareja1Id, pareja2Id, pareja1.nombre, pareja2.nombre);
        })
        .catch(error => {
            Toast.error('Error al cargar datos: ' + error.message);
        });
}

// Cargar todas las tablas de posiciones al iniciar la página
document.addEventListener('DOMContentLoaded', function() {
    // Restaurar la pestaña activa después del reload
    const savedTab = sessionStorage.getItem('activeTab');
    if (savedTab) {
        const tabButton = document.getElementById(savedTab);
        if (tabButton) {
            const tab = new bootstrap.Tab(tabButton);
            tab.show();
        }
        sessionStorage.removeItem('activeTab');
    }

    // Cargar tablas para cada categoría (dinámico: se basa en las categorías reales del torneo)
    fetch('/api/resultado_algoritmo')
        .then(response => response.json())
        .then(data => {
            if (!data.grupos_por_categoria) return;
            const categorias = Object.keys(data.grupos_por_categoria);
            categorias.forEach(categoria => {
                const grupos = data.grupos_por_categoria[categoria] || [];
                grupos.forEach(grupo => {
                    if (grupo.resultados && Object.keys(grupo.resultados).length > 0) {
                        cargarTablaPosiciones(categoria, grupo.id);
                    }
                });
            });
        })
        .catch(error => {
            Toast.error('Error al cargar tablas: ' + (error && error.message ? error.message : 'Error desconocido'));
        });
});
