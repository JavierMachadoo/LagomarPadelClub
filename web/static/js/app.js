const TorneoApp = (() => {
    const mostrarAlerta = (mensaje, tipo = 'info') => {
        const container = document.getElementById('flash-messages');
        if (!container) return;

        const iconos = {
            success: 'check-circle-fill',
            danger: 'exclamation-triangle-fill',
            warning: 'exclamation-triangle-fill',
            info: 'info-circle-fill'
        };

        const alerta = document.createElement('div');
        alerta.className = `alert alert-${tipo} alert-dismissible fade show fade-in`;
        alerta.setAttribute('role', 'alert');
        alerta.innerHTML = `
            <i class="bi bi-${iconos[tipo]} me-2"></i>
            ${mensaje}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;

        container.appendChild(alerta);
        setTimeout(() => {
            alerta.classList.remove('show');
            setTimeout(() => alerta.remove(), 300);
        }, 5000);
    };

    const validarTelefono = (telefono) => {
        const patron = /^[\d\s\-\(\)\+]+$/;
        return patron.test(telefono) && telefono.replace(/\D/g, '').length >= 10;
    };

    const formatearTelefono = (telefono) => {
        const numeros = telefono.replace(/\D/g, '');
        if (numeros.length === 10) {
            return `(${numeros.substring(0, 3)}) ${numeros.substring(3, 6)}-${numeros.substring(6)}`;
        }
        return telefono;
    };

    const validarFormularioAgregarPareja = (form) => {
        const nombre = form.querySelector('[name="nombre"]').value.trim();
        const telefono = form.querySelector('[name="telefono"]').value.trim();
        const categoria = form.querySelector('[name="categoria"]').value;
        const franjas = form.querySelectorAll('[name="franjas[]"]:checked');

        if (!nombre) {
            mostrarAlerta('Por favor ingrese el nombre de la pareja', 'warning');
            return false;
        }

        if (telefono && !validarTelefono(telefono)) {
            mostrarAlerta('El teléfono debe tener al menos 10 dígitos', 'warning');
            return false;
        }

        if (!categoria) {
            mostrarAlerta('Por favor seleccione una categoría', 'warning');
            return false;
        }

        if (franjas.length === 0) {
            mostrarAlerta('Por favor seleccione al menos un horario', 'warning');
            return false;
        }

        return true;
    };

    const confirmarEliminacion = (mensaje, onConfirm) => {
        Confirmar.show(mensaje || '¿Está seguro de eliminar este elemento?', onConfirm, { titulo: 'Eliminar', textoOk: 'Eliminar' });
    };

    const actualizarContadorFranjas = () => {
        const checkboxes = document.querySelectorAll('[name="franjas[]"]');
        const contador = document.getElementById('contador-franjas');
        
        if (contador) {
            const seleccionadas = Array.from(checkboxes).filter(cb => cb.checked).length;
            contador.textContent = `${seleccionadas} franja${seleccionadas !== 1 ? 's' : ''} seleccionada${seleccionadas !== 1 ? 's' : ''}`;
        }
    };

    const copiarAlPortapapeles = (texto) => {
        navigator.clipboard.writeText(texto).then(() => {
            mostrarAlerta('Copiado al portapapeles', 'success');
        }).catch(() => {
            mostrarAlerta('Error al copiar', 'danger');
        });
    };

    const exportarTablaCSV = (tablaId, nombreArchivo = 'datos.csv') => {
        const tabla = document.getElementById(tablaId);
        if (!tabla) return;

        const csv = [];
        const filas = tabla.querySelectorAll('tr');

        filas.forEach(fila => {
            const cols = fila.querySelectorAll('td, th');
            const row = Array.from(cols).map(col => col.textContent);
            csv.push(row.join(','));
        });

        const csvString = csv.join('\n');
        const blob = new Blob([csvString], { type: 'text/csv' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = nombreArchivo;
        a.click();
        window.URL.revokeObjectURL(url);

        mostrarAlerta('Archivo CSV descargado', 'success');
    };

    const imprimirSeccion = (seccionId) => {
        const seccion = document.getElementById(seccionId);
        if (!seccion) return;

        const ventana = window.open('', '', 'height=600,width=800');
        ventana.document.write('<html><head><title>Imprimir</title>');
        ventana.document.write('<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">');
        ventana.document.write('</head><body>');
        ventana.document.write(seccion.innerHTML);
        ventana.document.write('</body></html>');
        ventana.document.close();
        ventana.print();
    };

    const toggleBotonCargando = (boton, cargando = true) => {
        if (cargando) {
            boton.disabled = true;
            boton.dataset.originalText = boton.innerHTML;
            boton.innerHTML = `
                <span class="spinner-border spinner-border-sm me-2" role="status"></span>
                Cargando...
            `;
        } else {
            boton.disabled = false;
            boton.innerHTML = boton.dataset.originalText || boton.innerHTML;
        }
    };

    const scrollSuaveA = (elementoId) => {
        const elemento = document.getElementById(elementoId);
        if (elemento) {
            elemento.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    };

    const filtrarTabla = (inputId, tablaId) => {
        const input = document.getElementById(inputId);
        const tabla = document.getElementById(tablaId);
        
        if (!input || !tabla) return;

        input.addEventListener('keyup', function() {
            const filtro = this.value.toLowerCase();
            const filas = tabla.getElementsByTagName('tr');

            for (let i = 1; i < filas.length; i++) {
                const celdas = filas[i].getElementsByTagName('td');
                let encontrado = false;

                for (let j = 0; j < celdas.length; j++) {
                    if (celdas[j].textContent.toLowerCase().indexOf(filtro) > -1) {
                        encontrado = true;
                        break;
                    }
                }

                filas[i].style.display = encontrado ? '' : 'none';
            }
        });
    };

    const inicializar = () => {
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(el => new bootstrap.Tooltip(el));

        const alertas = document.querySelectorAll('.alert:not(.alert-permanent)');
        alertas.forEach(alerta => {
            setTimeout(() => {
                alerta.classList.remove('show');
                setTimeout(() => alerta.remove(), 300);
            }, 5000);
        });

        const cards = document.querySelectorAll('.card');
        cards.forEach((card, index) => {
            setTimeout(() => card.classList.add('fade-in'), index * 100);
        });

        const checkboxesFranjas = document.querySelectorAll('[name="franjas[]"]');
        checkboxesFranjas.forEach(cb => {
            cb.addEventListener('change', actualizarContadorFranjas);
        });
    };

    return {
        mostrarAlerta,
        validarTelefono,
        formatearTelefono,
        validarFormularioAgregarPareja,
        confirmarEliminacion,
        actualizarContadorFranjas,
        copiarAlPortapapeles,
        exportarTablaCSV,
        imprimirSeccion,
        toggleBotonCargando,
        scrollSuaveA,
        filtrarTabla,
        inicializar
    };
})();

document.addEventListener('DOMContentLoaded', TorneoApp.inicializar);

window.torneoUtils = TorneoApp;
