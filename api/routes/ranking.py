"""
Blueprint de ranking anual por jugador.

Rutas:
  GET /api/ranking?year=YYYY           → JSON con ranking por categoría
  GET /ranking                         → Vista pública del ranking
"""

import logging
from collections import defaultdict

from flask import Blueprint, jsonify, render_template



from config.settings import CATEGORIAS, COLORES_CATEGORIA, EMOJI_CATEGORIA

logger = logging.getLogger(__name__)

ranking_bp = Blueprint('ranking', __name__)


def _sb():
    from utils.supabase_client import get_supabase_admin
    return get_supabase_admin()


def _use_supabase() -> bool:
    from config.settings import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


def _calcular_ranking() -> dict:
    """Devuelve ranking agrupado por categoría (todos los torneos finalizados).

    Estructura de retorno:
    {
      "Tercera": [
        {"posicion": 1, "nombre": "Juan", "apellido": "García",
         "jugador_id": "uuid", "puntos": 250, "torneos": 2,
         "mejor_resultado": "campeon"},
        ...
      ],
      ...
    }
    """
    if not _use_supabase():
        return {}

    sb = _sb()

    # 1. Todos los torneos finalizados
    torneos_resp = (
        sb.table('torneos')
        .select('id')
        .eq('estado', 'finalizado')
        .execute()
    )
    torneos_finalizados = torneos_resp.data or []
    if not torneos_finalizados:
        return {}

    torneo_ids = [t['id'] for t in torneos_finalizados]

    # 2. Puntos de esos torneos
    puntos_resp = (
        sb.table('puntos_jugador')
        .select('jugador_id, torneo_id, categoria, puntos, concepto')
        .in_('torneo_id', torneo_ids)
        .execute()
    )
    filas = puntos_resp.data or []
    if not filas:
        return {}

    # 3. Jugadores involucrados
    jugador_ids = list({f['jugador_id'] for f in filas})
    jugadores_resp = (
        sb.table('jugadores')
        .select('id, nombre, apellido')
        .in_('id', jugador_ids)
        .execute()
    )
    jugadores_map = {j['id']: j for j in (jugadores_resp.data or [])}

    # 4. Agregar en Python: sum(puntos), count(torneos), mejor concepto por jugador+categoría
    _ORDEN_CONCEPTO = ['serie', 'octavos', 'cuartos', 'semifinal', 'vicecampeon', 'campeon']

    acum: dict[str, dict] = {}  # key: "jugador_id|categoria"
    for fila in filas:
        key = f"{fila['jugador_id']}|{fila['categoria']}"
        if key not in acum:
            acum[key] = {
                'jugador_id':      fila['jugador_id'],
                'categoria':       fila['categoria'],
                'puntos':          0,
                'torneos':         0,
                'mejor_resultado': 'serie',
            }
        acum[key]['puntos'] += fila['puntos']
        acum[key]['torneos'] += 1
        concepto_actual = acum[key]['mejor_resultado']
        concepto_nuevo = fila['concepto']
        if _ORDEN_CONCEPTO.index(concepto_nuevo) > _ORDEN_CONCEPTO.index(concepto_actual):
            acum[key]['mejor_resultado'] = concepto_nuevo

    # 5. Agrupar por categoría y ordenar
    ranking: dict[str, list] = defaultdict(list)
    for entry in acum.values():
        jugador = jugadores_map.get(entry['jugador_id'], {})
        ranking[entry['categoria']].append({
            'jugador_id':      entry['jugador_id'],
            'nombre':          jugador.get('nombre', ''),
            'apellido':        jugador.get('apellido', ''),
            'puntos':          entry['puntos'],
            'torneos':         entry['torneos'],
            'mejor_resultado': entry['mejor_resultado'],
        })

    for cat in ranking:
        ranking[cat].sort(key=lambda x: -x['puntos'])
        for i, row in enumerate(ranking[cat], start=1):
            row['posicion'] = i

    # Respetar orden canónico de categorías
    return {cat: ranking[cat] for cat in CATEGORIAS if cat in ranking}


@ranking_bp.route('/api/ranking')
def api_ranking():
    try:
        data = _calcular_ranking()
        return jsonify({'ranking': data})
    except Exception:
        logger.exception('Error al calcular ranking')
        return jsonify({'error': 'Error al calcular el ranking'}), 500


@ranking_bp.route('/ranking')
def ranking_publico():
    try:
        ranking = _calcular_ranking()
    except Exception:
        logger.exception('Error al renderizar ranking')
        ranking = {}

    return render_template(
        'ranking.html',
        ranking=ranking,
        colores=COLORES_CATEGORIA,
        emojis=EMOJI_CATEGORIA,
    )
