"""
Blueprint para historial de torneos archivados.

Rutas:
  POST /api/admin/terminar-torneo  → archivar torneo actual y resetear
  GET  /torneos                    → lista de torneos archivados
  GET  /torneos/<torneo_id>        → detalle del torneo archivado
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request

from api.routes._helpers import deserializar_resultado
from core.clasificacion import CalculadorClasificacion
from utils.api_helpers import verificar_autenticacion_api
from utils.torneo_storage import storage

logger = logging.getLogger(__name__)

historial_bp = Blueprint('historial', __name__)

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_HISTORIAL_FILE = _BASE_DIR / 'data' / 'torneos' / 'historial.json'


def _use_supabase() -> bool:
    from config.settings import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


def _sb_admin():
    from config.settings import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


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


@historial_bp.route('/api/admin/terminar-torneo', methods=['POST'])
def terminar_torneo():
    """Archiva el torneo actual con sus datos y lo resetea completamente."""
    autenticado, error = verificar_autenticacion_api(roles_permitidos=['admin'])
    if not autenticado:
        return error

    data = request.get_json(silent=True) or {}
    nombre = (data.get('nombre') or '').strip()
    if not nombre:
        return jsonify({'error': 'El nombre del torneo es obligatorio'}), 400

    torneo = storage.cargar()
    torneo_id = torneo.get('torneo_id')
    tipo = torneo.get('tipo_torneo', 'fin1')

    datos_blob = {
        'resultado_algoritmo': torneo.get('resultado_algoritmo'),
        'fixtures_finales': torneo.get('fixtures_finales', {}),
        'tipo_torneo': tipo,
    }

    if _use_supabase():
        try:
            _sb_admin().table('torneos').upsert({
                'id': torneo_id,
                'nombre': nombre,
                'tipo': tipo,
                'estado': 'finalizado',
                'datos_blob': datos_blob,
            }, on_conflict='id').execute()
        except Exception as e:
            logger.error('Error al archivar torneo en Supabase: %s', e)
            return jsonify({'error': 'Error al archivar el torneo'}), 500
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

    storage.limpiar()
    logger.info('Torneo "%s" (%s) archivado y reseteado', nombre, torneo_id)
    return jsonify({'ok': True})


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

    return render_template(
        'torneo_detalle.html',
        torneo=torneo,
        grupos_por_categoria=grupos_por_categoria,
        standings_por_categoria=standings_por_categoria,
        fixtures_finales=fixtures_finales,
    )
