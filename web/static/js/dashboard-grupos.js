// ==================== CONFIGURACIÓN DE CATEGORÍAS ====================
const CATEGORIA_CONFIG = {
    'Cuarta':  { clase: 'partido-cuarta',  emoji: '🟢', border: '#28a745', bg: '#d4edda' },
    'Quinta':  { clase: 'partido-quinta',  emoji: '🟡', border: '#ffc107', bg: '#fff3cd' },
    'Sexta':   { clase: 'partido-sexta',   emoji: '🔵', border: '#17a2b8', bg: '#d1ecf1' },
    'Séptima': { clase: 'partido-septima', emoji: '🟣', border: '#9b7fed', bg: '#e7e3ff' },
    'Tercera': { clase: 'partido-tercera', emoji: '🟠', border: '#fd7e14', bg: '#fff3e0' },
    'Octava':  { clase: 'partido-octava',  emoji: '🔴', border: '#dc3545', bg: '#fce4e6' },
};
const CATEGORIA_DEFAULT = { clase: '', emoji: '⚪', border: '#6c757d', bg: '#f8f9fa' };

// ==================== NAVEGACIÓN ENTRE VISTAS ====================
// Las funciones de navegación ahora se manejan con los tabs de Bootstrap

// ==================== DRAG AND DROP ====================
let draggedPareja = null;
let dragTimeout = null;

function dragStart(event) {
    // Usamos currentTarget (el div draggable con los data-attributes),
    // NO event.target (que puede ser un elemento hijo como un <span> o <i>).
    const el = event.currentTarget;
    const esNoAsignada = el.dataset.esNoAsignada === 'true';
    const categoria = el.dataset.categoria;
    const slot = el.dataset.slot;

    draggedPareja = {
        parejaId: el.dataset.parejaId,
        parejaNombre: el.dataset.parejaNombre,
        grupoOrigen: el.dataset.grupoOrigen || null,
        slotOrigen: slot ? parseInt(slot) : null,
        esNoAsignada: esNoAsignada,
        categoria: categoria
    };
    el.classList.add('dragging');
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', '');
}

function allowDropSlot(event) {
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = 'move';

    // Resaltar el slot específico
    const slot = event.currentTarget;
    if (!slot.classList.contains('drag-over-slot')) {
        slot.classList.add('drag-over-slot');
    }
}

function removeDragOverSlot(event) {
    event.currentTarget.classList.remove('drag-over-slot');
}

function dropEnSlot(event) {
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.classList.remove('drag-over-slot');

    if (!draggedPareja) return;

    const slotDestino = parseInt(event.currentTarget.dataset.slot);
    const grupoDestino = parseInt(event.currentTarget.dataset.grupoId);

    // Limpiar estado visual
    document.querySelectorAll('.dragging').forEach(el => el.classList.remove('dragging'));

    // Si es una pareja no asignada
    if (draggedPareja.esNoAsignada) {
        asignarParejaNoAsignadaASlot(draggedPareja.parejaId, grupoDestino, slotDestino, draggedPareja.categoria);
        draggedPareja = null;
        return;
    }

    // Si es intercambio entre slots
    const grupoOrigen = draggedPareja.grupoOrigen;

    // Verificar si algún grupo involucrado tiene resultados registrados
    const cardDestino = document.querySelector(`.grupo-card[data-grupo-id="${grupoDestino}"]`);
    const cardOrigen = document.querySelector(`.grupo-card[data-grupo-id="${grupoOrigen}"]`);
    if (cardDestino?.dataset.tieneResultados === 'true' || cardOrigen?.dataset.tieneResultados === 'true') {
        Toast.error('No se puede intercambiar: el grupo tiene resultados ingresados.');
        draggedPareja = null;
        return;
    }

    intercambiarParejaEnSlot(draggedPareja.parejaId, grupoOrigen, grupoDestino, slotDestino);
    draggedPareja = null;
}

function asignarParejaNoAsignadaASlot(parejaId, grupoId, slot, categoria) {
    fetch('/api/asignar-pareja-a-grupo', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            pareja_id: parseInt(parejaId),
            grupo_id: parseInt(grupoId),
            pareja_a_remover_id: null,
            categoria: categoria,
            slot_destino: slot
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Actualizar estadísticas si están disponibles
            if (data.estadisticas) {
                actualizarEstadisticas(data.estadisticas);
            }
            // Actualizar manteniendo el tab activo
            actualizarCategoria(categoria);
        } else {
        }
    })
    .catch(error => {
    });
}

function intercambiarParejaEnSlot(parejaId, grupoOrigen, grupoDestino, slotDestino) {
    fetch('/api/intercambiar-pareja', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            pareja_id: parseInt(parejaId),
            grupo_origen: parseInt(grupoOrigen),
            grupo_destino: parseInt(grupoDestino),
            slot_destino: slotDestino
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Actualizar estadísticas si están disponibles
            if (data.estadisticas) {
                actualizarEstadisticas(data.estadisticas);
            }
            // Actualizar manteniendo el tab activo
            const categoriaActual = obtenerCategoriaActual();
            actualizarCategoria(categoriaActual);
        } else {
            Toast.error(data.error || 'No se pudo intercambiar la pareja.');
        }
    })
    .catch(error => {
        Toast.error('Error de conexión al intercambiar parejas.');
    });
}

// Interceptor global: muestra un toast claro cuando el backend devuelve 409 (conflicto
// de versión de optimistic locking). Evita tener que manejar el 409 en cada fetch individual.
(function () {
    const _fetch = window.fetch;
    window.fetch = function (url, opts) {
        return _fetch.call(this, url, opts).then(function (resp) {
            if (resp.status === 409) {
                resp.clone().json()
                    .then(function (d) {
                        Toast.error(d.error || d.message || 'Otro administrador modificó los datos. Recargá la página para continuar.');
                    })
                    .catch(function () {
                        Toast.error('Otro administrador modificó los datos. Recargá la página para continuar.');
                    });
            }
            return resp;
        });
    };
})();

// Función para cargar franjas horarias en el modal
document.addEventListener('DOMContentLoaded', function() {
    inicializarDragAndDrop();

    const franjasContainer = document.getElementById('franjasModalContainer');
    const franjas = [
        "Jueves 18:00", "Jueves 20:00",
        "Viernes 18:00", "Viernes 21:00",
        "Sábado 09:00", "Sábado 12:00", "Sábado 16:00", "Sábado 19:00"
    ];

    franjas.forEach((franja, idx) => {
        const div = document.createElement('div');
        div.className = 'form-check';
        div.innerHTML = `
            <input class="form-check-input" type="checkbox" value="${franja}" id="franjaModal${idx}" name="franjas">
            <label class="form-check-label" for="franjaModal${idx}">${franja}</label>
        `;
        franjasContainer.appendChild(div);
    });

    // Cargar parejas no asignadas para cada categoría visible
    const categorias = ['Cuarta', 'Quinta', 'Sexta', 'Séptima', 'Tercera'];
    categorias.forEach(cat => cargarParejasNoAsignadas(cat));
});

// ==================== PAREJAS NO ASIGNADAS ====================

function cargarParejasNoAsignadas(categoria) {
    fetch(`/api/parejas-no-asignadas/${categoria}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                renderizarParejasNoAsignadas(categoria, data.parejas);
            }
        })
        .catch(error => {
        });
}

function renderizarParejasNoAsignadas(categoria, parejas) {
    const container = document.getElementById(`parejas-no-asignadas-${categoria}`);
    // El contenedor solo existe si la categoría tiene grupos renderizados.
    if (!container) return;

    if (!parejas || parejas.length === 0) {
        container.innerHTML = '';
        return;
    }

    const color = CATEGORIA_CONFIG[categoria] || CATEGORIA_DEFAULT;

    let html = `
        <div class="parejas-no-asignadas-container">
            <h5 class="mb-3">
                <i class="bi bi-exclamation-triangle-fill text-warning"></i>
                Parejas No Asignadas (${parejas.length})
            </h5>
            <p class="text-muted small mb-3">
                <i class="bi bi-info-circle"></i>
                Arrastra estas parejas a los grupos o usa el botón "Asignar" para elegir manualmente
            </p>
            <div class="row g-2">
    `;

    parejas.forEach(pareja => {
        html += `
            <div class="col-md-4">
                <div class="pareja-no-asignada"
                     draggable="true"
                     data-pareja-id="${pareja.id}"
                     data-pareja-nombre="${pareja.nombre}"
                     data-categoria="${categoria}"
                     data-es-no-asignada="true">
                    <div class="d-flex justify-content-between align-items-start mb-2">
                        <div class="flex-grow-1">
                            <div class="fw-bold text-truncate" title="${pareja.nombre}">
                                ${color.emoji} ${pareja.nombre}
                            </div>
                        </div>
                        <div class="d-flex gap-1">
                            <button class="btn btn-sm btn-outline-primary btn-asignar-manual"
                                    draggable="false"
                                    onmousedown="event.stopPropagation();"
                                    onclick="abrirModalAsignarManual(${pareja.id}, '${pareja.nombre}', '${categoria}')"
                                    title="Asignar manualmente">
                                <i class="bi bi-plus-circle"></i>
                            </button>
                        </div>
                    </div>
                    <small class="text-muted d-block">
                        <i class="bi bi-clock"></i> ${pareja.franjas_disponibles ? pareja.franjas_disponibles.join(', ') : 'Sin horarios'}
                    </small>
                    <small class="text-muted d-block">
                        <i class="bi bi-telephone"></i> ${pareja.telefono || 'Sin teléfono'}
                    </small>
                </div>
            </div>
        `;
    });

    html += `
            </div>
        </div>
    `;

    container.innerHTML = html;
}

function abrirModalAsignarManual(parejaId, parejaNombre, categoria) {
    // Crear modal dinámico
    const modalHtml = `
        <div class="modal fade" id="modalAsignarManual" tabindex="-1">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header bg-primary text-white">
                        <h5 class="modal-title">
                            <i class="bi bi-arrow-right-circle"></i> Asignar Pareja a Grupo
                        </h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <p><strong>Pareja:</strong> ${parejaNombre}</p>
                        <div class="mb-3">
                            <label for="selectGrupo" class="form-label">Grupo de destino *</label>
                            <select class="form-select" id="selectGrupo" required>
                                <option value="">-- Selecciona un grupo --</option>
                            </select>
                        </div>
                        <div class="mb-3" id="selectParejaRemoverContainer" style="display: none;">
                            <label for="selectParejaRemover" class="form-label">Reemplazar pareja (opcional)</label>
                            <select class="form-select" id="selectParejaRemover">
                                <option value="">-- No reemplazar, solo agregar --</option>
                            </select>
                            <small class="text-muted">
                                Si el grupo ya tiene 3 parejas, debes seleccionar una para reemplazar
                            </small>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
                        <button type="button" class="btn btn-primary" onclick="confirmarAsignacionManual(${parejaId}, '${categoria}')">
                            <i class="bi bi-check-circle"></i> Asignar
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;

    // Remover modal anterior si existe
    const modalAnterior = document.getElementById('modalAsignarManual');
    if (modalAnterior) {
        modalAnterior.remove();
    }

    // Agregar nuevo modal
    document.body.insertAdjacentHTML('beforeend', modalHtml);

    // Cargar grupos disponibles
    cargarGruposDisponibles(categoria);

    // Mostrar modal
    const modal = new bootstrap.Modal(document.getElementById('modalAsignarManual'));
    modal.show();
}

function cargarGruposDisponibles(categoria) {
    // Obtener todos los grupos de la categoría del DOM
    const gruposCards = document.querySelectorAll(`[data-categoria="${categoria}"].grupo-card`);
    const selectGrupo = document.getElementById('selectGrupo');

    gruposCards.forEach((card, index) => {
        const grupoId = card.dataset.grupoId;
        const letra = ['A', 'B', 'C', 'D'][index] || index + 1;
        // Contar solo slots que tienen parejas (tienen data-pareja-id válido)
        const parejas = card.querySelectorAll('.pareja-slot[data-pareja-id]');
        const numParejas = parejas.length;

        const option = document.createElement('option');
        option.value = grupoId;
        option.textContent = `Grupo ${letra} (${numParejas}/3 parejas)`;
        option.dataset.numParejas = numParejas;
        selectGrupo.appendChild(option);
    });

    // Evento para mostrar selector de pareja a remover si el grupo está lleno
    selectGrupo.addEventListener('change', function() {
        const selectedOption = this.options[this.selectedIndex];
        const numParejas = parseInt(selectedOption.dataset.numParejas || 0);
        const grupoId = this.value;

        const container = document.getElementById('selectParejaRemoverContainer');
        const selectPareja = document.getElementById('selectParejaRemover');

        if (numParejas >= 3 && grupoId) {
            // Mostrar selector y cargar parejas del grupo
            container.style.display = 'block';
            selectPareja.innerHTML = '<option value="">-- Selecciona pareja a reemplazar --</option>';

            // Buscar parejas del grupo (solo las que tienen data-pareja-id)
            const grupoCard = document.querySelector(`[data-grupo-id="${grupoId}"]`);
            const parejas = grupoCard.querySelectorAll('.pareja-slot[data-pareja-id]');

            parejas.forEach(pareja => {
                const option = document.createElement('option');
                option.value = pareja.dataset.parejaId;
                option.textContent = pareja.dataset.parejaNombre;
                selectPareja.appendChild(option);
            });

            selectPareja.required = true;
        } else {
            container.style.display = 'none';
            selectPareja.required = false;
        }
    });
}

function confirmarAsignacionManual(parejaId, categoria) {
    const grupoId = document.getElementById('selectGrupo').value;
    const parejaRemoverId = document.getElementById('selectParejaRemover').value;

    if (!grupoId) {
        Toast.error('Debes seleccionar un grupo');
        return;
    }

    // Verificar si el grupo está lleno y no se seleccionó pareja a remover
    const selectedOption = document.getElementById('selectGrupo').options[document.getElementById('selectGrupo').selectedIndex];
    const numParejas = parseInt(selectedOption.dataset.numParejas || 0);

    if (numParejas >= 3 && !parejaRemoverId) {
        Toast.error('El grupo está lleno. Debes seleccionar una pareja para reemplazar');
        return;
    }

    fetch('/api/asignar-pareja-a-grupo', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            pareja_id: parseInt(parejaId),
            grupo_id: parseInt(grupoId),
            pareja_a_remover_id: parejaRemoverId ? parseInt(parejaRemoverId) : null,
            categoria: categoria
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            Toast.success(data.mensaje);

            // Cerrar modal y actualizar solo la categoría
            const modal = bootstrap.Modal.getInstance(document.getElementById('modalAsignarManual'));
            modal.hide();

            actualizarCategoria(categoria);
        } else {
            Toast.error('Error: ' + data.error);
        }
    })
    .catch(error => {
        Toast.error('Error al asignar pareja');
    });
}

function agregarParejaDesdeModal() {
    const form = document.getElementById('formAgregarParejaModal');
    const nombre = document.getElementById('nombreModal').value.trim();
    const telefono = document.getElementById('telefonoModal').value.trim();
    const categoria = document.getElementById('categoriaModal').value;

    const franjasChecked = Array.from(document.querySelectorAll('#franjasModalContainer input[type="checkbox"]:checked'))
        .map(cb => cb.value);

    if (!nombre) {
        Toast.error('El nombre es obligatorio');
        return;
    }

    if (franjasChecked.length === 0) {
        Toast.error('Selecciona al menos una franja horaria');
        return;
    }

    fetch('/api/agregar-pareja', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            nombre: nombre,
            telefono: telefono || 'Sin teléfono',
            categoria: categoria,
            franjas: franjasChecked,
            desde_resultados: true
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            Toast.success(data.mensaje + ' - Agregada a parejas no asignadas');

            // Actualizar estadísticas si están disponibles
            if (data.estadisticas) {
                actualizarEstadisticas(data.estadisticas);
            }

            // Cerrar modal
            const modal = bootstrap.Modal.getInstance(document.getElementById('modalAgregarPareja'));
            modal.hide();

            // Limpiar formulario
            form.reset();

            // Actualizar la categoría correspondiente para reflejar la nueva pareja
            if (data.desde_resultados) {
                actualizarCategoria(categoria);
            } else {
                // Si no hay resultados, redirigir a datos
                Toast.info('Redirigiendo para re-ejecutar el algoritmo...');
                setTimeout(() => {
                    window.location.href = '/datos';
                }, 1000);
            }
        } else {
            Toast.error('Error: ' + data.error);
        }
    })
    .catch(error => {
        Toast.error('Error al agregar pareja');
    });
}

// ==================== CREAR Y EDITAR GRUPOS ====================

// Variable global para almacenar disponibilidad
let disponibilidadGlobal = null;

function abrirModalCrearGrupo(categoria) {
    document.getElementById('crearGrupoCategoria').value = categoria;
    document.getElementById('crearGrupoFranja').value = '';
    document.getElementById('crearGrupoCancha').value = '';

    // Ocultar el card de disponibilidad inicialmente
    document.getElementById('disponibilidadCard').style.display = 'none';

    // Cargar disponibilidad
    cargarDisponibilidad();

    const modal = new bootstrap.Modal(document.getElementById('modalCrearGrupo'));
    modal.show();
}

function cargarDisponibilidad() {
    fetch('/api/franjas-disponibles')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                disponibilidadGlobal = data.disponibilidad;
                // Agregar event listeners a los selects
                document.getElementById('crearGrupoFranja').addEventListener('change', actualizarDisponibilidad);
                document.getElementById('crearGrupoCancha').addEventListener('change', actualizarDisponibilidad);
            }
        })
        .catch(() => {});
}

function actualizarDisponibilidad() {
    const franja = document.getElementById('crearGrupoFranja').value;
    const canchaSeleccionada = document.getElementById('crearGrupoCancha').value;
    const disponibilidadCard = document.getElementById('disponibilidadCard');
    const disponibilidadInfo = document.getElementById('disponibilidadInfo');

    if (!franja && !canchaSeleccionada) {
        disponibilidadCard.style.display = 'none';
        return;
    }

    disponibilidadCard.style.display = 'block';
    disponibilidadInfo.innerHTML = '';

    if (!disponibilidadGlobal) {
        disponibilidadInfo.innerHTML = '<div class="col-12 text-center">Cargando...</div>';
        return;
    }

    // Si hay franja seleccionada, mostrar disponibilidad de canchas para esa franja
    if (franja && disponibilidadGlobal[franja]) {
        disponibilidadInfo.innerHTML = '<div class="col-12"><h6 class="mb-2">Canchas para ' + franja + ':</h6></div>';

        Object.keys(disponibilidadGlobal[franja]).forEach(cancha => {
            const info = disponibilidadGlobal[franja][cancha];
            const disponible = info.disponible;
            const solapamiento = info.solapamiento;

            let colorClass, icono, texto;

            if (disponible && !solapamiento) {
                // Completamente disponible
                colorClass = 'success';
                icono = '✓';
                texto = 'Disponible';
            } else if (disponible && solapamiento) {
                // Disponible pero con solapamiento
                colorClass = 'warning';
                icono = '⚠';
                const horas = solapamiento.horas_conflicto.join(', ');
                texto = `Parcialmente ocupada: ${solapamiento.franja} (${solapamiento.categoria}) solapa en ${horas}`;
            } else {
                // Ocupada
                colorClass = 'danger';
                icono = '✗';
                texto = `Ocupada (${info.ocupada_por})`;
            }

            disponibilidadInfo.innerHTML += `
                <div class="col-12">
                    <div class="alert alert-${colorClass} mb-2 py-2 px-3">
                        <strong>${icono} Cancha ${cancha}:</strong> ${texto}
                    </div>
                </div>
            `;
        });
    }
    // Si hay cancha seleccionada, mostrar franjas disponibles para esa cancha
    else if (canchaSeleccionada) {
        disponibilidadInfo.innerHTML = '<div class="col-12"><h6 class="mb-2">Franjas para Cancha ' + canchaSeleccionada + ':</h6></div>';

        Object.keys(disponibilidadGlobal).forEach(franja => {
            const info = disponibilidadGlobal[franja][canchaSeleccionada];
            if (info) {
                const disponible = info.disponible;
                const solapamiento = info.solapamiento;

                let colorClass, icono, texto;

                if (disponible && !solapamiento) {
                    colorClass = 'success';
                    icono = '✓';
                    texto = franja;
                } else if (disponible && solapamiento) {
                    colorClass = 'warning';
                    icono = '⚠';
                    const horas = solapamiento.horas_conflicto.join(', ');
                    texto = `${franja} - Solapamiento con ${solapamiento.franja} en ${horas}`;
                } else {
                    // No mostrar las ocupadas en esta vista
                    return;
                }

                disponibilidadInfo.innerHTML += `
                    <div class="col-12 col-md-6">
                        <div class="alert alert-${colorClass} mb-2 py-2 px-3">
                            ${icono} <strong>${texto}</strong>
                        </div>
                    </div>
                `;
            }
        });
    }
    // Si no hay nada seleccionado, mostrar resumen general
    else {
        disponibilidadInfo.innerHTML = '<div class="col-12"><h6 class="mb-2">Resumen General:</h6></div>';

        Object.keys(disponibilidadGlobal).forEach(franja => {
            const canchas = disponibilidadGlobal[franja];
            const disponibles = Object.values(canchas).filter(c => c.disponible && !c.solapamiento).length;
            const conSolapamiento = Object.values(canchas).filter(c => c.disponible && c.solapamiento).length;
            const total = Object.keys(canchas).length;

            if (disponibles > 0 || conSolapamiento > 0) {
                let texto = `${disponibles}/${total} canchas libres`;
                if (conSolapamiento > 0) {
                    texto += ` (${conSolapamiento} con solapamiento)`;
                }

                disponibilidadInfo.innerHTML += `
                    <div class="col-12 col-md-6">
                        <div class="alert alert-info mb-2 py-2 px-3">
                            <strong>${franja}:</strong> ${texto}
                        </div>
                    </div>
                `;
            }
        });
    }
}

function confirmarCrearGrupo() {
    const categoria = document.getElementById('crearGrupoCategoria').value;
    const franja = document.getElementById('crearGrupoFranja').value;
    const cancha = document.getElementById('crearGrupoCancha').value;

    if (!franja || !cancha) {
        Toast.error('Debes completar todos los campos');
        return;
    }

    fetch('/api/crear-grupo-manual', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            categoria: categoria,
            franja_horaria: franja,
            cancha: cancha
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            Toast.success(data.mensaje);

            // Cerrar modal
            const modal = bootstrap.Modal.getInstance(document.getElementById('modalCrearGrupo'));
            modal.hide();

            // Para crear grupo necesitamos reload porque es un elemento nuevo en el DOM
            sessionStorage.setItem('tabPrincipal', 'series-main');
            sessionStorage.setItem('tabCategoria', `series-${categoria.toLowerCase()}`);
            const scrollPos = window.pageYOffset || document.documentElement.scrollTop;
            sessionStorage.setItem('scrollPos', scrollPos);

            setTimeout(() => {
                window.location.reload();
            }, 300); // Pequeño delay para que se cierre el modal
        } else {
            Toast.error('Error: ' + data.error);
        }
    })
    .catch(error => {
        Toast.error('Error al crear grupo');
    });
}

function abrirModalEditarGrupo(button) {
    const grupoId = button.getAttribute('data-grupo-id');
    const categoria = button.getAttribute('data-categoria');
    const franjaActual = button.getAttribute('data-franja');
    const canchaActual = button.getAttribute('data-cancha');

    document.getElementById('editarGrupoId').value = grupoId;
    document.getElementById('editarGrupoCategoria').value = categoria;
    document.getElementById('editarGrupoFranja').value = franjaActual;
    document.getElementById('editarGrupoCancha').value = canchaActual;

    // Obtener datos frescos del grupo desde el servidor
    fetch(`/api/obtener-grupo/${categoria}/${grupoId}`)
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                Toast.error(data.error);
                return;
            }

            const grupo = data.grupo;
            const parejas = grupo.parejas || [];

            // Mostrar las parejas del grupo
            const contenedorParejas = document.getElementById('parejasDelGrupo');
            if (parejas && parejas.length > 0) {
                let html = '<div class="table-responsive"><table class="table table-sm table-hover mb-0">';
                html += '<thead class="table-light"><tr>';
                html += '<th width="5%">#</th>';
                html += '<th width="55%">Nombre</th>';
                html += '<th width="30%">Teléfono</th>';
                html += '<th width="10%">Acción</th>';
                html += '</tr></thead><tbody>';

                parejas.forEach((pareja, index) => {
                    html += `<tr>
                        <td>${index + 1}</td>
                        <td class="fw-bold">${pareja.nombre}</td>
                        <td><small><i class="bi bi-telephone"></i> ${pareja.telefono || 'N/A'}</small></td>
                        <td>
                            <button class="btn btn-sm btn-primary me-1"
                                    data-pareja-id="${pareja.id}"
                                    data-pareja-nombre="${pareja.nombre}"
                                    data-pareja-telefono="${pareja.telefono || ''}"
                                    data-pareja-categoria="${pareja.categoria}"
                                    data-pareja-franjas='${JSON.stringify(pareja.franjas_disponibles)}'
                                    onclick="editarParejaDesdeGrupo(this)"
                                    title="Editar">
                                <i class="bi bi-pencil-fill"></i>
                            </button>
                            <button class="btn btn-sm btn-danger"
                                    onclick="eliminarParejaGrupo(${pareja.id})"
                                    title="Eliminar">
                                <i class="bi bi-trash-fill"></i>
                            </button>
                        </td>
                    </tr>`;
                });

                html += '</tbody></table></div>';
                contenedorParejas.innerHTML = html;
            } else {
                contenedorParejas.innerHTML = '<div class="alert alert-warning mb-0"><i class="bi bi-exclamation-triangle"></i> No hay parejas en este grupo</div>';
            }

            const modal = new bootstrap.Modal(document.getElementById('modalEditarGrupo'));
            modal.show();
        })
        .catch(error => {
            Toast.error('Error al cargar los datos del grupo');
        });
}

// Nueva función para editar pareja desde el modal de grupo
function editarParejaDesdeGrupo(button) {
    const id = button.getAttribute('data-pareja-id');
    const nombre = button.getAttribute('data-pareja-nombre');
    const telefono = button.getAttribute('data-pareja-telefono');
    const categoria = button.getAttribute('data-pareja-categoria');
    const franjas = JSON.parse(button.getAttribute('data-pareja-franjas'));

    document.getElementById('editarParejaId').value = id;
    document.getElementById('editarParejaNombre').value = nombre;
    document.getElementById('editarParejaTelefono').value = telefono;
    document.getElementById('editarParejaCategoria').value = categoria;

    // Limpiar checkboxes
    document.querySelectorAll('#modalEditarPareja input[type="checkbox"]').forEach(cb => cb.checked = false);

    // Marcar franjas actuales
    franjas.forEach(franja => {
        const checkbox = Array.from(document.querySelectorAll('#modalEditarPareja input[type="checkbox"]'))
            .find(cb => cb.value === franja);
        if (checkbox) checkbox.checked = true;
    });

    // Cerrar modal de editar grupo y abrir modal de editar pareja
    const modalGrupo = bootstrap.Modal.getInstance(document.getElementById('modalEditarGrupo'));
    if (modalGrupo) modalGrupo.hide();

    const modalPareja = new bootstrap.Modal(document.getElementById('modalEditarPareja'));
    modalPareja.show();
}

// Nueva función para eliminar pareja desde el modal de grupo
function eliminarParejaGrupo(parejaId) {
    if (!confirm('¿Estás seguro de eliminar esta pareja? Se quitará del grupo y volverá a la lista de no asignadas.')) {
        return;
    }

    fetch('/api/remover-pareja-de-grupo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pareja_id: parejaId })
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            Toast.error(data.error);
        } else {
            Toast.success(data.mensaje);

            // Actualizar estadísticas si están disponibles
            if (data.estadisticas) {
                actualizarEstadisticas(data.estadisticas);
            }

            const modalGrupo = bootstrap.Modal.getInstance(document.getElementById('modalEditarGrupo'));
            if (modalGrupo) modalGrupo.hide();

            // Actualizar solo la categoría del grupo
            const categoriaActual = obtenerCategoriaActual();
            actualizarCategoria(categoriaActual);
        }
    })
    .catch(error => {
        Toast.error('Error al eliminar la pareja');
    });
}

function confirmarEditarGrupo() {
    const grupoId = document.getElementById('editarGrupoId').value;
    const categoria = document.getElementById('editarGrupoCategoria').value;
    const franja = document.getElementById('editarGrupoFranja').value;
    const cancha = document.getElementById('editarGrupoCancha').value;

    if (!franja || !cancha) {
        Toast.error('Debes completar todos los campos');
        return;
    }

    fetch('/api/editar-grupo', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            grupo_id: parseInt(grupoId),
            categoria: categoria,
            franja_horaria: franja,
            cancha: cancha
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            Toast.success(data.mensaje);

            // Cerrar modal y actualizar categoría
            const modal = bootstrap.Modal.getInstance(document.getElementById('modalEditarGrupo'));
            modal.hide();

            actualizarCategoria(categoria);
        } else {
            Toast.error('Error: ' + data.error);
        }
    })
    .catch(error => {
        Toast.error('Error al editar grupo');
    });
}

// ==================== EDITAR PAREJA ====================

function abrirModalEditarPareja(parejaId, nombre, telefono, categoria, franjas) {
    document.getElementById('editarParejaId').value = parejaId;
    document.getElementById('editarParejaNombre').value = nombre;
    document.getElementById('editarParejaTelefono').value = telefono || '';
    document.getElementById('editarParejaCategoria').value = categoria;

    // Limpiar checkboxes
    document.querySelectorAll('#editarParejaFranjasContainer input[type="checkbox"]').forEach(cb => {
        cb.checked = false;
    });

    // Marcar las franjas actuales
    if (franjas && Array.isArray(franjas)) {
        franjas.forEach(franja => {
            const checkbox = document.querySelector(`#editarParejaFranjasContainer input[value="${franja}"]`);
            if (checkbox) {
                checkbox.checked = true;
            }
        });
    }

    const modal = new bootstrap.Modal(document.getElementById('modalEditarPareja'));
    modal.show();
}

function confirmarEditarPareja() {
    const parejaId = document.getElementById('editarParejaId').value;
    const nombre = document.getElementById('editarParejaNombre').value.trim();
    const telefono = document.getElementById('editarParejaTelefono').value.trim();
    const categoria = document.getElementById('editarParejaCategoria').value;

    const franjasChecked = Array.from(document.querySelectorAll('#editarParejaFranjasContainer input[type="checkbox"]:checked'))
        .map(cb => cb.value);

    if (!nombre) {
        Toast.error('El nombre es obligatorio');
        return;
    }

    if (franjasChecked.length === 0) {
        Toast.error('Selecciona al menos una franja horaria');
        return;
    }

    fetch('/api/editar-pareja', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            pareja_id: parseInt(parejaId),
            nombre: nombre,
            telefono: telefono || 'Sin teléfono',
            categoria: categoria,
            franjas: franjasChecked
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            Toast.success(data.mensaje);

            // Cerrar modal
            const modal = bootstrap.Modal.getInstance(document.getElementById('modalEditarPareja'));
            modal.hide();

            // Guardar estado antes de recargar
            sessionStorage.setItem('tabPrincipal', 'series-main');
            const categoriaActual = obtenerCategoriaActual();
            sessionStorage.setItem('tabCategoria', `series-${categoriaActual.toLowerCase()}`);
            const scrollPos = window.pageYOffset || document.documentElement.scrollTop;
            sessionStorage.setItem('scrollPos', scrollPos);

            // Recargar para actualizar marcadores y prevenir inconsistencias
            setTimeout(() => {
                window.location.reload();
            }, 300);
        } else {
            Toast.error('Error: ' + data.error);
        }
    })
    .catch(error => {
        Toast.error('Error al editar pareja');
    });
}

// ==================== FUNCIONES PARA FINALES ====================

function asignarPosicion(parejaId, posicion, categoria, grupoId) {
    // Obtener el elemento de la pareja actual
    const parejaElement = document.querySelector(`[data-pareja-id="${parejaId}"][data-grupo-id="${grupoId}"]`);
    const posicionActual = parejaElement ? parseInt(parejaElement.dataset.posicion) : null;

    // Si ya tiene esta posición, deseleccionar
    if (posicionActual === posicion) {
        posicion = 0; // 0 significa deseleccionar
    } else {
        // Validar que no exista otra pareja con la misma posición en el mismo grupo
        const parejasDelGrupo = document.querySelectorAll(`[data-grupo-id="${grupoId}"]`);

        for (let pareja of parejasDelGrupo) {
            const parejaIdActual = parseInt(pareja.dataset.parejaId);
            const posicionOtra = parseInt(pareja.dataset.posicion);

            // Si es otra pareja (no la misma) y tiene la misma posición
            if (parejaIdActual !== parejaId && posicionOtra === posicion) {
                Toast.error(`Ya existe una pareja con la posición ${posicion}° en este grupo. Debes asignar posiciones diferentes (1°, 2° y 3°).`);
                return;
            }
        }
    }

    fetch('/api/asignar-posicion', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            pareja_id: parejaId,
            posicion: posicion,
            categoria: categoria
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Solo mostrar mensaje si hay texto (no cuando se deselecciona)
            if (data.mensaje) {
                // No mostrar notificación, solo actualizar UI silenciosamente
            }
            // Actualizar solo los badges de posición sin recargar la página
            actualizarBadgesPosicion(parejaId, posicion, grupoId);
        } else {
            Toast.error('Error: ' + data.error);
        }
    })
    .catch(error => {
        Toast.error('Error al asignar posición');
    });
}

function actualizarBadgesPosicion(parejaId, posicion, grupoId) {
    // Encontrar el elemento de la pareja
    const parejaElement = document.querySelector(`[data-pareja-id="${parejaId}"][data-grupo-id="${grupoId}"]`);

    if (!parejaElement) return;

    // Actualizar el data-posicion
    parejaElement.dataset.posicion = posicion;

    // Remover clases de posición de todos los badges de esta pareja
    const badges = parejaElement.querySelectorAll('.posicion-badge');
    badges.forEach(badge => {
        badge.classList.remove('posicion-primero', 'posicion-segundo', 'posicion-tercero');
    });

    // Si posicion es 0 o null, solo limpiar (deseleccionar)
    if (posicion === 0 || posicion === null) {
        return;
    }

    // Agregar clase solo al badge correspondiente
    const badgeIndex = posicion - 1; // 0, 1, 2
    if (badges[badgeIndex]) {
        if (posicion === 1) {
            badges[badgeIndex].classList.add('posicion-primero');
        } else if (posicion === 2) {
            badges[badgeIndex].classList.add('posicion-segundo');
        } else if (posicion === 3) {
            badges[badgeIndex].classList.add('posicion-tercero');
        }
    }
}

function generarFinales(categoria) {
    // Función obsoleta - redirigir a página de finales
    window.location.href = '/finales';
}

function cargarFixture(categoria) {
    // Función obsoleta - redirigir a página de finales
    window.location.href = '/finales';
}


function renderizarPartido(partido, categoria) {
    if (!partido.pareja1 && !partido.pareja2) {
        return `
            <div class="partido-final">
                <div class="text-center text-muted">
                    <i class="bi bi-hourglass-split"></i> Esperando resultados anteriores...
                </div>
            </div>
        `;
    }

    const p1 = partido.pareja1;
    const p2 = partido.pareja2;
    const ganadorId = partido.ganador ? partido.ganador.id : null;
    const tieneGanador = partido.tiene_ganador;

    return `
        <div class="partido-final ${tieneGanador ? 'tiene-ganador' : ''}" data-partido-id="${partido.id}">
            <div class="mb-3 text-center">
                <span class="badge bg-secondary">${partido.fase}</span>
            </div>

            <!-- Pareja 1 -->
            <div class="d-flex justify-content-between align-items-center mb-2 p-2 rounded ${ganadorId === (p1 ? p1.id : null) ? 'bg-success text-white' : 'bg-light'}">
                <div class="flex-grow-1">
                    <strong>${p1 ? p1.nombre : 'Por definir'}</strong>
                </div>
                ${p1 && p2 ? `
                    <button class="btn btn-sm btn-success btn-ganador ${ganadorId === p1.id ? 'activo' : ''}"
                            onclick="confirmarGanador('${categoria}', '${partido.id}', ${p1.id}, '${p1.nombre}')"
                            title="Marcar como ganador">
                        <i class="bi bi-check-circle-fill"></i>
                    </button>
                ` : ''}
                ${ganadorId === (p1 ? p1.id : null) ? '<i class="bi bi-trophy-fill text-warning ms-2"></i>' : ''}
            </div>

            <div class="text-center my-2">
                <strong class="text-muted">VS</strong>
            </div>

            <!-- Pareja 2 -->
            <div class="d-flex justify-content-between align-items-center p-2 rounded ${ganadorId === (p2 ? p2.id : null) ? 'bg-success text-white' : 'bg-light'}">
                <div class="flex-grow-1">
                    <strong>${p2 ? p2.nombre : 'Por definir'}</strong>
                </div>
                ${p1 && p2 ? `
                    <button class="btn btn-sm btn-success btn-ganador ${ganadorId === p2.id ? 'activo' : ''}"
                            onclick="confirmarGanador('${categoria}', '${partido.id}', ${p2.id}, '${p2.nombre}')"
                            title="Marcar como ganador">
                        <i class="bi bi-check-circle-fill"></i>
                    </button>
                ` : ''}
                ${ganadorId === (p2 ? p2.id : null) ? '<i class="bi bi-trophy-fill text-warning ms-2"></i>' : ''}
            </div>
        </div>
    `;
}

function confirmarGanador(categoria, partidoId, ganadorId, nombreGanador) {
    // Configurar el modal de confirmación
    document.getElementById('mensajeConfirmacion').innerHTML = `<strong>"${nombreGanador}"</strong> ganó este partido`;
    document.getElementById('detalleConfirmacion').textContent = 'Esta acción actualizará el fixture y avanzará al ganador a la siguiente ronda.';

    // Configurar el botón de confirmar
    const btnConfirmar = document.getElementById('btnConfirmarGanador');
    btnConfirmar.onclick = function() {
        // Cerrar modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('modalConfirmarGanador'));
        modal.hide();

        // Marcar ganador
        marcarGanador(categoria, partidoId, ganadorId);
    };

    // Mostrar modal
    const modal = new bootstrap.Modal(document.getElementById('modalConfirmarGanador'));
    modal.show();
}

function marcarGanador(categoria, partidoId, ganadorId) {
    fetch('/api/marcar-ganador', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            categoria: categoria,
            partido_id: partidoId,
            ganador_id: ganadorId
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            Toast.success(data.mensaje);
            // Recargar solo el fixture sin refrescar toda la página
            cargarFixture(categoria);
            // Si estamos en el tab de finales, recargar el calendario también
            if (document.getElementById('finales-tab').classList.contains('active')) {
                cargarCalendarioFinales();
            }
        } else {
            Toast.error('Error: ' + data.error);
        }
    })
    .catch(error => {
        Toast.error('Error al marcar ganador');
    });
}

// ==================== CALENDARIO DE FINALES ====================

function cargarCalendarioFinales() {
    const container = document.getElementById('calendario-finales-container');

    // Mostrar loading
    container.innerHTML = `
        <div class="text-center py-5">
            <div class="spinner-border text-warning" role="status">
                <span class="visually-hidden">Cargando...</span>
            </div>
            <p class="mt-3 text-muted">Cargando calendario de finales...</p>
        </div>
    `;

    fetch('/api/calendario-finales')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                renderizarCalendarioFinales(data.calendario, data.tiene_datos);
            } else {
                container.innerHTML = `
                    <div class="alert alert-danger">
                        <i class="bi bi-x-circle"></i> Error al cargar calendario de finales
                    </div>
                `;
            }
        })
        .catch(error => {
            container.innerHTML = `
                <div class="alert alert-danger">
                    <i class="bi bi-x-circle"></i> Error al cargar calendario de finales
                </div>
            `;
        });
}

function renderizarCalendarioFinales(calendario, tieneDatos) {
    const container = document.getElementById('calendario-finales-container');

    if (!tieneDatos) {
        container.innerHTML = `
            <div class="alert alert-info">
                <h5><i class="bi bi-info-circle"></i> Calendario de finales no disponible</h5>
                <p>Debes generar los fixtures de finales primero en cada categoría.</p>
            </div>
        `;
        return;
    }


    let html = `
        <h3 class="fw-bold text-warning mb-3">📆 DOMINGO</h3>
        <div class="table-responsive">
            <table class="table table-bordered table-hover">
                <thead class="table-dark">
                    <tr>
                        <th width="10%" class="text-center">HORA</th>
                        <th width="45%"> CANCHA 1</th>
                        <th width="45%"> CANCHA 2</th>
                    </tr>
                </thead>
                <tbody>
    `;

    const horarios = Object.keys(calendario).sort();

    for (const hora of horarios) {
        const canchas = calendario[hora];

        html += `<tr>`;
        html += `<td class="fw-bold text-center align-middle bg-light">${hora}</td>`;

        // Cancha 1
        html += `<td class="p-2">`;
        if (canchas[1]) {
            const partido = canchas[1];
            const catCfg = CATEGORIA_CONFIG[partido.categoria] || CATEGORIA_DEFAULT;
            const colorFondo = catCfg.bg;
            const colorBorde = catCfg.border;
            const emoji = catCfg.emoji;

            html += `
                <div class="p-2 rounded" style="background-color: ${colorFondo}; border-left: 4px solid ${colorBorde};">
                    <div class="mb-2">
                        <span class="badge" style="background-color: ${colorBorde};">
                            ${emoji} ${partido.categoria} - ${partido.fase} ${partido.numero_partido}
                        </span>
                    </div>
                    <div class="row align-items-center g-0">
                        <div class="col-5 text-end pe-2">
                            <strong>${partido.pareja1}</strong>
                        </div>
                        <div class="col-2 text-center">
                            <strong class="text-muted">VS</strong>
                        </div>
                        <div class="col-5 text-start ps-2">
                            <strong>${partido.pareja2}</strong>
                        </div>
                    </div>
                    ${partido.tiene_ganador ? `
                        <div class="mt-2 text-center">
                            <i class="bi bi-trophy-fill text-warning"></i>
                            <small class="text-success fw-bold">Ganador: ${partido.ganador}</small>
                        </div>
                    ` : ''}
                </div>
            `;
        } else {
            html += `<span class="text-muted">Libre</span>`;
        }
        html += `</td>`;

        // Cancha 2
        html += `<td class="p-2">`;
        if (canchas[2]) {
            const partido = canchas[2];
            const catCfg = CATEGORIA_CONFIG[partido.categoria] || CATEGORIA_DEFAULT;
            const colorFondo = catCfg.bg;
            const colorBorde = catCfg.border;
            const emoji = catCfg.emoji;

            html += `
                <div class="p-2 rounded" style="background-color: ${colorFondo}; border-left: 4px solid ${colorBorde};">
                    <div class="mb-2">
                        <span class="badge" style="background-color: ${colorBorde};">
                            ${emoji} ${partido.categoria} - ${partido.fase} ${partido.numero_partido}
                        </span>
                    </div>
                    <div class="row align-items-center g-0">
                        <div class="col-5 text-end pe-2">
                            <strong>${partido.pareja1}</strong>
                        </div>
                        <div class="col-2 text-center">
                            <strong class="text-muted">VS</strong>
                        </div>
                        <div class="col-5 text-start ps-2">
                            <strong>${partido.pareja2}</strong>
                        </div>
                    </div>
                    ${partido.tiene_ganador ? `
                        <div class="mt-2 text-center">
                            <i class="bi bi-trophy-fill text-warning"></i>
                            <small class="text-success fw-bold">Ganador: ${partido.ganador}</small>
                        </div>
                    ` : ''}
                </div>
            `;
        } else {
            html += `<span class="text-muted">Libre</span>`;
        }
        html += `</td>`;

        html += `</tr>`;
    }

    html += `
                </tbody>
            </table>
        </div>
    `;

    container.innerHTML = html;
}

// ==========================================
// SISTEMA DE ACTUALIZACIÓN SELECTIVA SIN RECARGAR
// ==========================================

// Función para obtener la categoría del tab actual
function obtenerCategoriaActual() {
    // Obtener del sessionStorage la categoría activa
    const tabCategoria = sessionStorage.getItem('tabCategoria') || 'series-cuarta';
    // Extraer solo la categoría (sin el prefijo 'series-')
    const categoria = tabCategoria.replace('series-', '');

    // Mapeo correcto de nombres (considerando acentos)
    const mapeoNombres = {
        'cuarta': 'Cuarta',
        'quinta': 'Quinta',
        'sexta': 'Sexta',
        'septima': 'Séptima'  // Importante: con acento
    };

    return mapeoNombres[categoria] || categoria.charAt(0).toUpperCase() + categoria.slice(1);
}

// Función para actualizar solo el contenido de una categoría específica
function actualizarCategoria(categoria) {
    // NO hacer reload - actualizar dinámicamente SIN flash
    const categoriaNormalizada = categoria.charAt(0).toUpperCase() + categoria.slice(1);

    // Obtener datos actualizados del servidor
    fetch(`/api/obtener-datos-categoria/${categoriaNormalizada}`)
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // 1. Actualizar parejas no asignadas
            actualizarParejasNoAsignadas(categoriaNormalizada, data.parejas_no_asignadas);

            // 2. Actualizar grupos (parejas dentro de cada grupo)
            actualizarGrupos(categoriaNormalizada, data.grupos);

            // 3. Actualizar partidos (pasando los grupos completos)
            actualizarPartidos(categoriaNormalizada, data.grupos);

            // 4. Actualizar calendario general
            actualizarCalendarioGeneral();

            // 5. Actualizar estadísticas globales
            actualizarEstadisticasDesdeServidor();
        } else {
        }
    })
    .catch(error => {
    });
}

// Función auxiliar para actualizar parejas no asignadas
function actualizarParejasNoAsignadas(categoria, parejas) {
    // Usar la función existente renderizarParejasNoAsignadas
    renderizarParejasNoAsignadas(categoria, parejas);
}

// Función auxiliar para actualizar grupos
function actualizarGrupos(categoria, grupos) {
    grupos.forEach((grupo, index) => {
        const grupoCard = document.querySelector(`[data-grupo-id="${grupo.id}"][data-categoria="${categoria}"]`);
        if (!grupoCard) return;

        const cardBody = grupoCard.querySelector('.card-body');
        if (!cardBody) return;

        // Actualizar el botón de editar con los datos frescos del grupo
        const editButton = grupoCard.querySelector('.card-header button[onclick*="abrirModalEditarGrupo"]');
        if (editButton) {
            editButton.setAttribute('data-grupo-id', grupo.id);
            editButton.setAttribute('data-categoria', categoria);
            editButton.setAttribute('data-franja', grupo.franja_horaria || '');
            editButton.setAttribute('data-cancha', grupo.cancha || '');
            // Ya no necesitamos data-parejas porque ahora se obtienen del servidor
        }

        // Actualizar info de franja y cancha
        const alertInfo = cardBody.querySelector('.alert-light');
        if (alertInfo) {
            alertInfo.innerHTML = `
                <small class="d-block">
                    <i class="bi bi-clock-fill"></i> <strong>${grupo.franja_horaria || 'Por coordinar'}</strong>
                </small>
                <small class="d-block">
                    <i class="bi bi-geo-alt-fill"></i> <strong>Cancha ${grupo.cancha || 'Por asignar'}</strong>
                </small>
            `;
        }

        // Actualizar parejas (slots)
        const parejasContainer = cardBody.querySelector('h6.fw-bold').nextElementSibling;
        if (!parejasContainer) return;

        let parejasHtml = '';
        for (let slot = 0; slot < 3; slot++) {
            const pareja = grupo.parejas[slot];

            if (pareja) {
                const franjaAsignada = grupo.franja_horaria;
                const franjasPareja = pareja.franjas_disponibles || [];
                const compatibleExacto = franjaAsignada && franjasPareja.includes(franjaAsignada);

                let compatibleParcial = false;
                if (franjaAsignada && !compatibleExacto && franjasPareja.length > 0) {
                    const diaAsignado = franjaAsignada.split(' ')[0];
                    compatibleParcial = franjasPareja.some(f => f.split(' ')[0] === diaAsignado);
                }

                const borderClass = compatibleExacto ? '' : (compatibleParcial ? 'border-warning border-2' : 'border-danger border-2');
                const textClass = compatibleExacto ? '' : (compatibleParcial ? 'text-warning' : 'text-danger');
                const tooltip = compatibleExacto ? '' : (compatibleParcial ? 'Esta pareja eligió este día pero en otro horario' : 'Esta pareja no eligió este día');

                parejasHtml += `
                    <div class="pareja-slot mb-2 p-2 bg-white rounded border ${borderClass}"
                         draggable="true"
                         data-pareja-id="${pareja.id}"
                         data-pareja-nombre="${pareja.nombre}"
                         data-grupo-origen="${grupo.id}"
                         data-grupo-id="${grupo.id}"
                         data-slot="${slot}"
                         data-posicion="${pareja.posicion_grupo || ''}"
                         ${tooltip ? `title="${tooltip}"` : ''}>
                        <div class="d-flex justify-content-between align-items-start">
                            <div class="flex-grow-1">
                                <div class="fw-bold text-truncate ${textClass}" title="${pareja.nombre}">
                                    ${slot + 1}. ${pareja.nombre}
                                </div>
                                <small class="text-muted d-block mt-1">
                                    <i class="bi bi-clock"></i> ${franjasPareja.join(', ') || 'Sin horarios'}
                                </small>
                                <small class="text-muted d-block">
                                    <i class="bi bi-telephone"></i> ${pareja.telefono}
                                </small>
                            </div>
                            ${pareja.posicion_grupo ? `
                                <div class="ms-2">
                                    ${pareja.posicion_grupo === 1 ? '<span class="badge text-dark" style="background: linear-gradient(135deg, #FFD700 0%, #FFA500 100%);" title="1° Puesto (Automático)">1°</span>' : ''}
                                    ${pareja.posicion_grupo === 2 ? '<span class="badge text-dark" style="background: linear-gradient(135deg, #C0C0C0 0%, #A8A8A8 100%);" title="2° Puesto (Automático)">2°</span>' : ''}
                                    ${pareja.posicion_grupo === 3 ? '<span class="badge text-white" style="background: linear-gradient(135deg, #CD7F32 0%, #A0522D 100%);" title="3° Puesto (Automático)">3°</span>' : ''}
                                </div>
                            ` : ''}
                        </div>
                    </div>
                `;
            } else {
                parejasHtml += `
                    <div class="pareja-slot pareja-slot-vacio mb-2 p-2 bg-light rounded border border-dashed"
                         data-grupo-id="${grupo.id}"
                         data-slot="${slot}"
                         style="min-height: 80px; display: flex; align-items: center; justify-content: center; border-style: dashed !important;">
                        <div class="text-muted text-center">
                            <i class="bi bi-plus-circle"></i>
                            <small class="d-block">Slot ${slot + 1} vacío</small>
                            <small class="d-block" style="font-size: 0.7rem;">Arrastra una pareja aquí</small>
                        </div>
                    </div>
                `;
            }
        }

        // Reemplazar el contenido de parejas
        const h6 = cardBody.querySelector('h6.fw-bold');
        if (h6) {
            // Eliminar todos los divs de pareja-slot existentes
            const existingSlots = cardBody.querySelectorAll('.pareja-slot, .pareja-slot-vacio');
            existingSlots.forEach(slot => slot.remove());

            // Insertar el nuevo HTML después del h6
            h6.insertAdjacentHTML('afterend', parejasHtml);
        }

        // Actualizar score en el footer
        const footer = grupoCard.querySelector('.card-footer');
        if (footer) {
            const score = grupo.score || 0.0;
            let badgeHtml = '';
            if (score === 3.0) {
                badgeHtml = `<span class="badge bg-success">✅ Perfecto: ${score.toFixed(1)}/3.0</span>`;
            } else if (score >= 2.5) {
                badgeHtml = `<span class="badge bg-success">✅ Calidad: ${score.toFixed(1)}/3.0</span>`;
            } else if (score >= 2.0) {
                badgeHtml = `<span class="badge bg-warning text-dark">⚠️ Calidad: ${score.toFixed(1)}/3.0</span>`;
            } else if (score >= 1.0) {
                badgeHtml = `<span class="badge bg-info text-white">📅 Calidad: ${score.toFixed(1)}/3.0</span>`;
            } else if (score > 0.0) {
                badgeHtml = `<span class="badge bg-warning text-dark">⚠️ Calidad: ${score.toFixed(1)}/3.0</span>`;
            } else {
                badgeHtml = `<span class="badge bg-danger">❌ Calidad: ${score.toFixed(1)}/3.0</span>`;
            }
            footer.innerHTML = badgeHtml;
        }
    });
}

// Función auxiliar para actualizar partidos
function actualizarPartidos(categoria, grupos) {

    grupos.forEach(grupo => {
        const container = document.querySelector(`#partidos-grupo-${grupo.id}`);
        if (!container) {
            return;
        }

        const franjaHoraria = grupo.franja_horaria || 'Por coordinar';
        const cancha = grupo.cancha || 'Por asignar';
        const partidos = grupo.partidos || [];
        const resultados = grupo.resultados || {};


        // Extraer hora base para los partidos
        let horaInicio = 20;
        if (franjaHoraria && franjaHoraria.includes(' ')) {
            const partes = franjaHoraria.split(' ')[1].split(':');
            horaInicio = parseInt(partes[0]);
        }

        let html = `
            <div class="mb-3 p-2 bg-white rounded border">
                <small class="text-muted d-block">
                    <i class="bi bi-calendar3"></i> <strong>${franjaHoraria}</strong>
                </small>
                <small class="text-muted d-block">
                    <i class="bi bi-geo-alt-fill"></i> <strong>Cancha ${cancha}</strong>
                </small>
            </div>
        `;

        if (partidos.length > 0) {
            partidos.forEach((partido, idx) => {
                const horaPartido = (horaInicio + idx) % 24;
                const horaStr = String(horaPartido).padStart(2, '0') + ':00';

                // Obtener IDs y resultado
                const p1_id = partido.pareja1_id || 0;
                const p2_id = partido.pareja2_id || 0;
                const puede_ingresar = p1_id > 0 && p2_id > 0;

                // Buscar resultado - IMPORTANTE: ordenar numéricamente
                const ids = [p1_id, p2_id].sort((a, b) => a - b);
                const resultado_key = ids.join('-');
                const resultado = resultados[resultado_key] || {};
                const tiene_resultado = resultado.ganador_id !== undefined && resultado.ganador_id !== null;

                const borderClass = tiene_resultado ? 'border-success border-2' : (puede_ingresar ? '' : 'border-danger');
                const cursor = puede_ingresar ? 'pointer' : 'not-allowed';
                const opacity = puede_ingresar ? '' : 'opacity: 0.6;';

                html += `
                    <div class="partido-card mb-3 p-3 bg-white rounded border shadow-sm ${borderClass}"
                         style="cursor: ${cursor}; transition: all 0.2s; ${opacity}"
                         ${puede_ingresar ? `
                             onclick="abrirModalPorIds('${categoria}', ${grupo.id}, ${p1_id}, ${p2_id})"
                             onmouseenter="this.style.transform='translateY(-2px)'; this.style.boxShadow='0 4px 12px rgba(0,0,0,0.15)';"
                             onmouseleave="this.style.transform=''; this.style.boxShadow='';"
                         ` : `
                             title="Recarga la página para actualizar los datos del partido"
                         `}>
                        <div class="d-flex align-items-center mb-2">
                            <div class="me-2">
                                <span class="badge bg-primary">
                                    <i class="bi bi-clock-fill"></i> ${horaStr}
                                </span>
                            </div>
                            <div class="flex-grow-1">
                                <small class="text-muted">Partido ${idx + 1}</small>
                            </div>
                            ${tiene_resultado ? `
                                <div class="ms-2">
                                    <span class="badge bg-success">
                                        <i class="bi bi-check-circle-fill"></i> Completado
                                    </span>
                                </div>
                            ` : `
                                <div class="ms-2">
                                    <span class="badge bg-secondary">
                                        <i class="bi bi-pencil-fill"></i> Pendiente
                                    </span>
                                </div>
                            `}
                        </div>
                        <div class="row g-0 align-items-center">
                            <div class="col-5">
                                <div class="text-end pe-2">
                                    <div class="fw-bold text-truncate ${resultado.ganador_id === p1_id ? 'text-success' : ''}" style="font-size: 0.95rem;" title="${partido.pareja1}">
                                        ${resultado.ganador_id === p1_id ? '<i class="bi bi-trophy-fill text-warning"></i> ' : ''}${partido.pareja1}
                                    </div>
                                    ${tiene_resultado ? `
                                        <small class="text-muted">
                                            ${resultado.games_set1_pareja1 || '-'}-${resultado.games_set1_pareja2 || '-'},
                                            ${resultado.games_set2_pareja1 || '-'}-${resultado.games_set2_pareja2 || '-'}
                                            ${resultado.tiebreak_pareja1 !== null && resultado.tiebreak_pareja1 !== undefined ?
                                                `, TB: ${resultado.tiebreak_pareja1}-${resultado.tiebreak_pareja2}` : ''}
                                        </small>
                                    ` : ''}
                                </div>
                            </div>
                            <div class="col-2">
                                <div class="text-center">
                                    <span class="badge bg-secondary">VS</span>
                                </div>
                            </div>
                            <div class="col-5">
                                <div class="ps-2">
                                    <div class="fw-bold text-truncate ${resultado.ganador_id === p2_id ? 'text-success' : ''}" style="font-size: 0.95rem;" title="${partido.pareja2}">
                                        ${partido.pareja2}${resultado.ganador_id === p2_id ? ' <i class="bi bi-trophy-fill text-warning"></i>' : ''}
                                    </div>
                                </div>
                            </div>
                        </div>
                        ${!tiene_resultado ? `
                            <div class="text-center mt-2">
                                ${puede_ingresar ? `
                                    <small class="text-muted">
                                        <i class="bi bi-hand-index"></i> Click para ingresar resultado
                                    </small>
                                ` : `
                                    <small class="text-danger">
                                        <i class="bi bi-exclamation-triangle"></i> Recarga la página para ingresar resultado
                                    </small>
                                `}
                            </div>
                        ` : ''}
                    </div>
                `;
            });
        } else {
            html += `
                <div class="alert alert-light mb-0">
                    <i class="bi bi-info-circle"></i> No hay partidos generados aún
                </div>
            `;
        }

        container.innerHTML = html;
        container.setAttribute('data-franja', franjaHoraria);
    });
}

// Función para actualizar el calendario general
function actualizarCalendarioGeneral() {
    fetch('/api/obtener-calendario')
    .then(response => response.json())
    .then(data => {
        if (data.success && data.calendario) {
            renderizarCalendario(data.calendario);
        }
    })
    .catch(error => {
    });
}

// Función para renderizar el calendario completo
function renderizarCalendario(calendario) {
    // Función auxiliar para renderizar un partido
    function renderPartido(partido) {
        if (!partido) return '';

        const catCfg = CATEGORIA_CONFIG[partido.categoria] || CATEGORIA_DEFAULT;
        const claseCategoria = catCfg.clase;
        const emoji = catCfg.emoji;

        return `
            <div class="partido-bloque-simple ${claseCategoria}">
                <div class="mb-2 text-center">
                    <span class="badge-categoria">${emoji} ${partido.categoria}</span>
                    <span class="badge-grupo">Grupo ${partido.grupo_letra || 'A'}</span>
                </div>
                <div class="row align-items-center g-0">
                    <div class="col-5 text-end pe-2">
                        <div class="fw-bold">${partido.pareja1}</div>
                    </div>
                    <div class="col-2 text-center">
                        <strong class="text-muted">VS</strong>
                    </div>
                    <div class="col-5 text-start ps-2">
                        <div class="fw-bold">${partido.pareja2}</div>
                    </div>
                </div>
            </div>
        `;
    }

    // Actualizar Jueves
    const juevesBody = document.getElementById('calendario-jueves');
    if (juevesBody && calendario.Jueves) {
        const horasJueves = ['18:00', '19:00', '20:00', '21:00', '22:00'];
        let htmlJueves = '';

        horasJueves.forEach(hora => {
            if (calendario.Jueves[hora]) {
                const cancha1 = calendario.Jueves[hora][0];
                const cancha2 = calendario.Jueves[hora][1];

                htmlJueves += `
                    <tr>
                        <td class="text-center align-middle bg-light fw-bold">${hora}</td>
                        <td class="calendario-celda">${renderPartido(cancha1)}</td>
                        <td class="calendario-celda">${renderPartido(cancha2)}</td>
                    </tr>
                `;
            }
        });

        juevesBody.innerHTML = htmlJueves;
    }

    // Actualizar Viernes
    const viernesBody = document.getElementById('calendario-viernes');
    if (viernesBody && calendario.Viernes) {
        const horasViernes = ['18:00', '19:00', '20:00', '21:00', '22:00', '23:00'];
        let htmlViernes = '';

        horasViernes.forEach(hora => {
            if (calendario.Viernes[hora]) {
                const cancha1 = calendario.Viernes[hora][0];
                const cancha2 = calendario.Viernes[hora][1];

                htmlViernes += `
                    <tr>
                        <td class="text-center align-middle bg-light fw-bold">${hora}</td>
                        <td class="calendario-celda">${renderPartido(cancha1)}</td>
                        <td class="calendario-celda">${renderPartido(cancha2)}</td>
                    </tr>
                `;
            }
        });

        viernesBody.innerHTML = htmlViernes;
    }

    // Actualizar Sábado
    const sabadoBody = document.getElementById('calendario-sabado');
    if (sabadoBody && calendario['Sábado']) {
        const horasSabado = ['09:00', '10:00', '11:00', '12:00', '13:00', '14:00', '16:00', '17:00', '18:00', '19:00', '20:00', '21:00'];
        let htmlSabado = '';

        horasSabado.forEach(hora => {
            if (calendario['Sábado'][hora]) {
                const cancha1 = calendario['Sábado'][hora][0];
                const cancha2 = calendario['Sábado'][hora][1];

                htmlSabado += `
                    <tr>
                        <td class="text-center align-middle bg-light fw-bold">${hora}</td>
                        <td class="calendario-celda">${renderPartido(cancha1)}</td>
                        <td class="calendario-celda">${renderPartido(cancha2)}</td>
                    </tr>
                `;
            }
        });

        sabadoBody.innerHTML = htmlSabado;
    }
}

// Función para actualizar todas las categorías (más rápido que reload completo)
function actualizarTodasCategorias() {
    return Promise.all(CATEGORIAS_TORNEO_FINALES.map(cat => actualizarCategoria(cat)));
}

// Función para actualizar solo un grupo específico
function actualizarGrupo(categoria, grupoId) {
    return fetch(`/api/obtener-grupo/${categoria}/${grupoId}`)
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                throw new Error(data.error);
            }

            // Actualizar el grupo específico en el DOM
            const grupoCard = document.querySelector(`[data-grupo-id="${grupoId}"][data-categoria="${categoria}"]`);
            if (grupoCard && data.html) {
                grupoCard.outerHTML = data.html;
            }

            return data;
        });
}

// Función para actualizar la lista de parejas no asignadas de una categoría
function actualizarParejaNoAsignadas(categoria) {
    return fetch(`/api/obtener-no-asignadas/${categoria}`)
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                throw new Error(data.error);
            }

            const contenedor = document.querySelector(`#${categoria.toLowerCase()} .parejas-no-asignadas-container`);
            if (contenedor && data.html) {
                contenedor.outerHTML = data.html;
            }

            return data;
        });
}

// Delegación de eventos para drag & drop — funciona en DOM dinámico
function inicializarDragAndDrop() {
    document.addEventListener('dragstart', (e) => {
        const el = e.target.closest('[draggable="true"][data-pareja-id]');
        if (!el) return;
        const slot = el.dataset.slot;
        draggedPareja = {
            parejaId:     el.dataset.parejaId,
            parejaNombre: el.dataset.parejaNombre,
            grupoOrigen:  el.dataset.grupoOrigen || null,
            slotOrigen:   slot ? parseInt(slot) : null,
            esNoAsignada: el.dataset.esNoAsignada === 'true',
            categoria:    el.dataset.categoria,
        };
        el.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', '');
    });

    document.addEventListener('dragover', (e) => {
        const slot = e.target.closest('[data-slot][data-grupo-id]');
        if (!slot) return;
        e.preventDefault();
        e.stopPropagation();
        e.dataTransfer.dropEffect = 'move';
        if (!slot.classList.contains('drag-over-slot')) {
            slot.classList.add('drag-over-slot');
        }
    });

    document.addEventListener('dragleave', (e) => {
        const slot = e.target.closest('[data-slot][data-grupo-id]');
        if (!slot || slot.contains(e.relatedTarget)) return;
        slot.classList.remove('drag-over-slot');
    });

    document.addEventListener('drop', (e) => {
        const slot = e.target.closest('[data-slot][data-grupo-id]');
        if (!slot) return;
        e.preventDefault();
        e.stopPropagation();
        slot.classList.remove('drag-over-slot');
        if (!draggedPareja) return;
        const slotDestino  = parseInt(slot.dataset.slot);
        const grupoDestino = parseInt(slot.dataset.grupoId);
        document.querySelectorAll('.dragging').forEach(el => el.classList.remove('dragging'));
        if (draggedPareja.esNoAsignada) {
            asignarParejaNoAsignadaASlot(draggedPareja.parejaId, grupoDestino, slotDestino, draggedPareja.categoria);
        } else {
            intercambiarParejaEnSlot(draggedPareja.parejaId, draggedPareja.grupoOrigen, grupoDestino, slotDestino);
        }
        draggedPareja = null;
    });
}

// Función auxiliar para cerrar modal y actualizar
function cerrarModalYActualizar(modalId, callback) {
    const modalElement = document.getElementById(modalId);
    const modal = bootstrap.Modal.getInstance(modalElement);
    if (modal) {
        modal.hide();
    }

    // Esperar a que el modal se cierre antes de actualizar
    if (modalElement) {
        modalElement.addEventListener('hidden.bs.modal', function handler() {
            modalElement.removeEventListener('hidden.bs.modal', handler);
            if (callback) callback();
        }, { once: true });
    } else if (callback) {
        callback();
    }
}

// Función para actualizar estadísticas en tiempo real
function actualizarEstadisticas(estadisticas) {
    if (!estadisticas) return;

    // Actualizar Parejas Asignadas
    const parejasAsignadasEl = document.querySelector('.stat-card:nth-child(1) .stat-number');
    if (parejasAsignadasEl) {
        parejasAsignadasEl.textContent = `${estadisticas.parejas_asignadas}/${estadisticas.total_parejas}`;
        parejasAsignadasEl.classList.add('stat-updated');
        setTimeout(() => parejasAsignadasEl.classList.remove('stat-updated'), 600);
    }

    // Actualizar Tasa de Asignación
    const tasaAsignacionEl = document.querySelector('.stat-card:nth-child(2) .stat-number');
    if (tasaAsignacionEl) {
        tasaAsignacionEl.textContent = `${Math.round(estadisticas.porcentaje_asignacion)}%`;
        tasaAsignacionEl.classList.add('stat-updated');
        setTimeout(() => tasaAsignacionEl.classList.remove('stat-updated'), 600);
    }

    // Actualizar Grupos Formados
    const gruposFormadosEl = document.querySelector('.stat-card:nth-child(3) .stat-number');
    if (gruposFormadosEl) {
        gruposFormadosEl.textContent = estadisticas.total_grupos;
        gruposFormadosEl.classList.add('stat-updated');
        setTimeout(() => gruposFormadosEl.classList.remove('stat-updated'), 600);
    }

    // Actualizar Calidad Promedio
    const calidadPromedioEl = document.querySelector('.stat-card:nth-child(4) .stat-number');
    if (calidadPromedioEl) {
        calidadPromedioEl.textContent = `${estadisticas.score_compatibilidad_promedio.toFixed(2)}/3.0`;
        calidadPromedioEl.classList.add('stat-updated');
        setTimeout(() => calidadPromedioEl.classList.remove('stat-updated'), 600);
    }
}

// Función para obtener estadísticas del servidor y actualizarlas
function actualizarEstadisticasDesdeServidor() {
    fetch('/api/estadisticas')
        .then(response => response.json())
        .then(data => {
            if (data.success && data.estadisticas) {
                actualizarEstadisticas(data.estadisticas);
            }
        })
        .catch(error => {
        });
}

// Detectar cambios de tab
document.addEventListener('DOMContentLoaded', function() {
    // PRIMERO: Restaurar tabs INMEDIATAMENTE (sin esperas)
    const tabPrincipalGuardado = sessionStorage.getItem('tabPrincipal');
    const tabCategoriaGuardado = sessionStorage.getItem('tabCategoria');

    // 1. Restaurar tab principal (SERIES) - INMEDIATO
    if (tabPrincipalGuardado === 'series-main') {
        const mainTabButton = document.querySelector('[data-bs-target="#series-main"]');
        if (mainTabButton) {
            const tab = new bootstrap.Tab(mainTabButton);
            tab.show();
        }
    }

    // 2. Restaurar tab de categoría (ej: series-quinta) - INMEDIATO SIN TIMEOUT
    if (tabCategoriaGuardado) {
        const tabButton = document.querySelector(`[data-bs-target="#${tabCategoriaGuardado}"]`);
        if (tabButton) {
            const tab = new bootstrap.Tab(tabButton);
            tab.show();

            // 3. Extraer la categoría para restaurar sub-tab de SERIE
            const categoria = tabCategoriaGuardado.replace('series-', '');
            const serieButton = document.querySelector(`#serie-${categoria}-tab`);
            if (serieButton && !serieButton.classList.contains('active')) {
                const serieTab = new bootstrap.Tab(serieButton);
                serieTab.show();
            }
        }
    }

    // DESPUÉS: Configurar listeners para futuros cambios
    const tabs = document.querySelectorAll('[data-bs-toggle="tab"]');
    tabs.forEach(tab => {
        tab.addEventListener('shown.bs.tab', function(e) {
            // Extraer el ID del tab desde data-bs-target
            const target = e.target.getAttribute('data-bs-target');
            if (target) {
                const targetId = target.replace('#', '');

                // Guardar tabs principales (fixture-main, series-main, finales-main)
                if (['fixture-main', 'series-main', 'finales-main'].includes(targetId)) {
                    sessionStorage.setItem('tabPrincipal', targetId);
                }

                // Guardar tabs de categoría en SERIES (series-cuarta, series-quinta, etc.)
                if (targetId.startsWith('series-')) {
                    sessionStorage.setItem('tabCategoria', targetId);
                }
            }
        });
    });

    // Restaurar posición del scroll
    const scrollPos = sessionStorage.getItem('scrollPos');
    if (scrollPos) {
        // Usar setTimeout para asegurar que el DOM esté completamente renderizado
        setTimeout(() => {
            window.scrollTo(0, parseInt(scrollPos));
            sessionStorage.removeItem('scrollPos');
        }, 150);
    }
});
