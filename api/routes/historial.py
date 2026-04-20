"""
Blueprint para historial de torneos archivados.

Rutas:
  POST /api/admin/terminar-torneo  → archivar torneo actual y resetear
  GET  /torneos                    → lista de torneos archivados
  GET  /torneos/<torneo_id>        → detalle del torneo archivado
"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request

from api.routes._helpers import deserializar_resultado
from config.settings import COLORES_CATEGORIA, EMOJI_CATEGORIA, TIPOS_TORNEO
from core.clasificacion import CalculadorClasificacion
from utils.api_helpers import verificar_autenticacion_api
from utils.torneo_storage import storage, ConflictError

logger = logging.getLogger(__name__)

historial_bp = Blueprint('historial', __name__)

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_HISTORIAL_FILE = _BASE_DIR / 'data' / 'torneos' / 'historial.json'


def _use_supabase() -> bool:
    from config.settings import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


def _sb_admin():
    from utils.supabase_client import get_supabase_admin
    return get_supabase_admin()


def _listar_archivados():
    """Devuelve lista de torneos archivados, más recientes primero."""
    if _use_supabase():
        try:
            resp = _sb_admin().table('torneos') \
                .select('id, nombre, tipo, estado, created_at') \
                .eq('estado', 'finalizado') \
                .order('created_at', desc=True) \
                .execute()
            return resp.data or []
        except Exception as e:
            logger.error('Error al listar torneos archivados: %s', e)
            return []
    else:
        try:
            if _HISTORIAL_FILE.exists():
                with open(_HISTORIAL_FILE, encoding='utf-8') as f:
                    torneos = json.load(f)
                return [
                    {'id': t['id'], 'nombre': t['nombre'], 'tipo': t['tipo'],
                     'estado': t.get('estado', 'finalizado'), 'created_at': t.get('created_at')}
                    for t in torneos
                ]
        except Exception as e:
            logger.error('Error al leer historial local: %s', e)
        return []


def _cargar_archivado(torneo_id: str):
    """Devuelve el torneo archivado completo (con datos_blob)."""
    if _use_supabase():
        try:
            resp = _sb_admin().table('torneos').select('*').eq('id', torneo_id).execute()
            return resp.data[0] if resp.data else None
        except Exception as e:
            logger.error('Error al cargar torneo archivado %s: %s', torneo_id, e)
            return None
    else:
        try:
            if _HISTORIAL_FILE.exists():
                with open(_HISTORIAL_FILE, encoding='utf-8') as f:
                    torneos = json.load(f)
                return next((t for t in torneos if t['id'] == torneo_id), None)
        except Exception as e:
            logger.error('Error al leer historial local: %s', e)
        return None


def _poblar_tablas_relacionales(sb, torneo_id: str, datos_blob: dict) -> None:
    """Popula las 4 tablas relacionales desde el blob al archivar un torneo.

    - UUIDs generados en Python → batch inserts (~6 calls en vez de ~N calls).
    - DELETE antes de INSERT → idempotente ante reintentos.
    - ON DELETE CASCADE en grupos elimina automáticamente parejas_grupo y partidos.
    """
    resultado = datos_blob.get('resultado_algoritmo') or {}
    grupos_por_categoria = resultado.get('grupos_por_categoria') or {}
    fixtures_finales = datos_blob.get('fixtures_finales') or {}

    # 1. Limpiar datos previos para garantizar idempotencia
    # La cascada ON DELETE CASCADE elimina parejas_grupo y partidos automáticamente
    sb.table('grupos').delete().eq('torneo_id', torneo_id).execute()
    sb.table('partidos_finales').delete().eq('torneo_id', torneo_id).execute()

    # 2. Construir todos los lotes en memoria antes de ir a la red
    grupos_rows = []
    parejas_rows = []
    partidos_rows = []
    finales_rows = []

    for categoria, grupos_lista in grupos_por_categoria.items():
        for grupo_dict in grupos_lista:
            grupo_uuid = str(uuid.uuid4())
            grupos_rows.append({
                'id':        grupo_uuid,
                'torneo_id': torneo_id,
                'categoria': categoria,
                'franja':    grupo_dict.get('franja_horaria'),
                'cancha':    grupo_dict.get('cancha'),
            })

            # Mapa id_entero → nombre para resolver los IDs del resultado
            nombre_map = {p.get('id'): p.get('nombre', '') for p in grupo_dict.get('parejas', [])}

            for pareja_dict in grupo_dict.get('parejas', []):
                parejas_rows.append({
                    'grupo_id': grupo_uuid,
                    'nombre':   pareja_dict.get('nombre', ''),
                    'posicion': pareja_dict.get('posicion_grupo'),  # puede ser None
                })

            for resultado_dict in grupo_dict.get('resultados', {}).values():
                partidos_rows.append({
                    'id':        str(uuid.uuid4()),
                    'grupo_id':  grupo_uuid,
                    'pareja1':   nombre_map.get(resultado_dict.get('pareja1_id'), ''),
                    'pareja2':   nombre_map.get(resultado_dict.get('pareja2_id'), ''),
                    'resultado': resultado_dict,
                })

    for categoria, fixture_dict in fixtures_finales.items():
        if not isinstance(fixture_dict, dict):
            continue
        # octavos, cuartos y semifinales son listas de partidos
        for fase_key in ('octavos', 'cuartos', 'semifinales'):
            for partido_dict in fixture_dict.get(fase_key, []):
                if not isinstance(partido_dict, dict):
                    continue
                finales_rows.append({
                    'id':        str(uuid.uuid4()),
                    'torneo_id': torneo_id,
                    'categoria': categoria,
                    'fase':      partido_dict.get('fase', fase_key),
                    'pareja1':   (partido_dict.get('pareja1') or {}).get('nombre'),
                    'pareja2':   (partido_dict.get('pareja2') or {}).get('nombre'),
                    'ganador':   (partido_dict.get('ganador') or {}).get('nombre'),
                })
        # 'final' es un dict único, no una lista como las otras fases
        final_dict = fixture_dict.get('final')
        if final_dict and isinstance(final_dict, dict):
            finales_rows.append({
                'id':        str(uuid.uuid4()),
                'torneo_id': torneo_id,
                'categoria': categoria,
                'fase':      final_dict.get('fase', 'Final'),
                'pareja1':   (final_dict.get('pareja1') or {}).get('nombre'),
                'pareja2':   (final_dict.get('pareja2') or {}).get('nombre'),
                'ganador':   (final_dict.get('ganador') or {}).get('nombre'),
            })

    # 3. Batch inserts — orden obligatorio: grupos antes que sus hijos (FK constraint)
    if grupos_rows:
        sb.table('grupos').insert(grupos_rows).execute()
    if parejas_rows:
        sb.table('parejas_grupo').insert(parejas_rows).execute()
    if partidos_rows:
        sb.table('partidos').insert(partidos_rows).execute()
    if finales_rows:
        sb.table('partidos_finales').insert(finales_rows).execute()

    logger.info(
        'Tablas relacionales pobladas para torneo %s: %d grupos, %d parejas, '
        '%d partidos grupo, %d partidos finales',
        torneo_id, len(grupos_rows), len(parejas_rows), len(partidos_rows), len(finales_rows),
    )


@historial_bp.route('/api/admin/terminar-torneo', methods=['POST'])
def terminar_torneo():
    """Archiva el torneo actual con sus datos y lo resetea completamente.

    El nombre ya fue asignado al configurar el próximo torneo en estado espera,
    por lo que se toma del blob directamente (no se pide en el request).
    """
    autenticado, error = verificar_autenticacion_api(roles_permitidos=['admin'])
    if not autenticado:
        return error

    torneo = storage.cargar()
    torneo_id = storage.get_torneo_id()
    tipo = torneo.get('tipo_torneo', 'fin1')
    nombre = torneo.get('nombre', '').strip() or f"Torneo {datetime.now().strftime('%d/%m/%Y')}"

    datos_blob = {
        'resultado_algoritmo': torneo.get('resultado_algoritmo'),
        'fixtures_finales': torneo.get('fixtures_finales', {}),
        'calendario_finales': torneo.get('calendario_finales', {}),
        'tipo_torneo': tipo,
    }
    if _use_supabase():
        sb = _sb_admin()  # Una sola instancia para todo el bloque
        try:
            sb.table('torneos').upsert({
                'id': torneo_id,
                'nombre': nombre,
                'tipo': tipo,
                'estado': 'finalizado',
                'datos_blob': datos_blob,
            }, on_conflict='id').execute()
        except Exception as e:
            logger.error('Error al archivar torneo en Supabase: %s', e)
            return jsonify({'error': 'Error al archivar el torneo'}), 500

        # Poblar tablas relacionales (best-effort: el blob ya está guardado)
        try:
            _poblar_tablas_relacionales(sb, torneo_id, datos_blob)
        except Exception as e:
            logger.error('Error al poblar tablas relacionales para torneo %s: %s', torneo_id, e)
    else:
        torneos = []
        if _HISTORIAL_FILE.exists():
            try:
                with open(_HISTORIAL_FILE, encoding='utf-8') as f:
                    torneos = json.load(f)
            except Exception:
                pass
        torneos.insert(0, {
            'id': torneo_id,
            'nombre': nombre,
            'tipo': tipo,
            'estado': 'finalizado',
            'datos_blob': datos_blob,
            'created_at': datetime.now().isoformat(),
        })
        _HISTORIAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_HISTORIAL_FILE, 'w', encoding='utf-8') as f:
            json.dump(torneos, f, indent=2, ensure_ascii=False)

    try:
        storage.transicion_a_espera(torneo_id)
    except ConflictError as e:
        return jsonify({'error': str(e)}), 409
    logger.info('Torneo "%s" (%s) archivado → estado espera', nombre, torneo_id)
    return jsonify({'ok': True})


@historial_bp.route('/api/admin/abrir-inscripciones', methods=['POST'])
def abrir_inscripciones():
    """Transiciona de estado 'espera' a 'inscripcion'.

    Requiere que el próximo torneo haya sido configurado (nombre y fecha).
    El nombre y tipo_torneo ya están en el blob y se preservan en limpiar().
    """
    autenticado, error = verificar_autenticacion_api(roles_permitidos=['admin'])
    if not autenticado:
        return error

    fase_actual = storage.get_fase()
    if fase_actual != 'espera':
        return jsonify({'error': f'Solo se puede abrir inscripciones desde estado espera (actual: {fase_actual})'}), 400

    proximo = storage.get_proximo_torneo()
    if not proximo or not proximo.get('nombre') or not proximo.get('fecha'):
        return jsonify({'error': 'Debes configurar el nombre y la fecha del próximo torneo antes de abrir inscripciones'}), 400

    try:
        storage.limpiar()
    except ConflictError as e:
        return jsonify({'error': str(e)}), 409
    logger.info('Inscripciones abiertas — transición espera → inscripcion')
    return jsonify({'ok': True, 'fase': 'inscripcion'})


@historial_bp.route('/api/admin/proximo-torneo', methods=['POST'])
def configurar_proximo_torneo():
    """Guarda nombre, fecha y tipo del próximo torneo (solo durante estado 'espera').

    El nombre y tipo_torneo se aplican directamente al blob activo para que
    sobrevivan la transición a inscripcion.
    """
    autenticado, error = verificar_autenticacion_api(roles_permitidos=['admin'])
    if not autenticado:
        return error

    fase_actual = storage.get_fase()
    if fase_actual != 'espera':
        return jsonify({'error': 'Solo se puede configurar el próximo torneo en estado espera'}), 400

    data = request.get_json(silent=True) or {}
    nombre = (data.get('nombre') or '').strip()
    fecha = (data.get('fecha') or '').strip()
    tipo_torneo = (data.get('tipo_torneo') or 'fin1').strip()
    descripcion = (data.get('descripcion') or '').strip()

    if not nombre:
        return jsonify({'error': 'El nombre es obligatorio'}), 400
    if not fecha:
        return jsonify({'error': 'La fecha es obligatoria'}), 400
    if tipo_torneo not in ('fin1', 'fin2'):
        return jsonify({'error': 'El tipo de torneo debe ser fin1 o fin2'}), 400

    try:
        storage.set_proximo_torneo(fecha=fecha, nombre=nombre, tipo_torneo=tipo_torneo, descripcion=descripcion)
    except ConflictError as e:
        return jsonify({'error': str(e)}), 409
    logger.info('Próximo torneo configurado: "%s" — %s (%s)', nombre, fecha, tipo_torneo)
    return jsonify({'ok': True, 'proximo_torneo': storage.get_proximo_torneo()})


@historial_bp.route('/api/proximo-torneo', methods=['GET'])
def obtener_proximo_torneo():
    """Devuelve la info del próximo torneo (endpoint público)."""
    proximo = storage.get_proximo_torneo()
    if not proximo:
        return jsonify({'proximo_torneo': None})
    return jsonify({'proximo_torneo': proximo})


@historial_bp.route('/torneos')
def lista_torneos():
    """Lista de todos los torneos archivados."""
    torneos = _listar_archivados()
    return render_template('torneos.html', torneos=torneos)


@historial_bp.route('/torneos/<torneo_id>')
def detalle_torneo(torneo_id):
    """Detalle de un torneo archivado: grupos con posiciones y cuadros de finales."""
    torneo = _cargar_archivado(torneo_id)
    if not torneo:
        from flask import abort
        abort(404)

    datos_blob = torneo.get('datos_blob') or {}
    resultado_data = datos_blob.get('resultado_algoritmo')
    fixtures_finales = datos_blob.get('fixtures_finales') or {}

    grupos_por_categoria = {}
    standings_por_categoria = {}

    if resultado_data:
        try:
            resultado_obj = deserializar_resultado(resultado_data)
            grupos_por_categoria = resultado_data.get('grupos_por_categoria', {})
            for cat, grupos in resultado_obj.grupos_por_categoria.items():
                standings_por_categoria[cat] = {}
                for grupo in grupos:
                    stats = CalculadorClasificacion.calcular_estadisticas_grupo(grupo)
                    stats_sorted = sorted(
                        stats,
                        key=lambda s: (-s.partidos_ganados, -s.diferencia_sets, -s.diferencia_games)
                    )
                    standings_por_categoria[cat][grupo.id] = stats_sorted
        except Exception as e:
            logger.error('Error al calcular clasificación para historial %s: %s', torneo_id, e)

    tipo = torneo.get('tipo', '')
    categorias_ordenadas = TIPOS_TORNEO.get(tipo, list(grupos_por_categoria.keys()))

    return render_template(
        'torneo_detalle.html',
        torneo=torneo,
        grupos_por_categoria=grupos_por_categoria,
        standings_por_categoria=standings_por_categoria,
        fixtures_finales=fixtures_finales,
        categorias=categorias_ordenadas,
        colores=COLORES_CATEGORIA,
        emojis=EMOJI_CATEGORIA,
    )
