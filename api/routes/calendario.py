from flask import Blueprint, request, jsonify
import logging

from core import Pareja, Grupo, PosicionGrupo, FixtureGenerator, FixtureFinales
from utils.torneo_storage import storage
from utils.calendario_finales_builder import CalendarioFinalesBuilder
from utils.api_helpers import (
    obtener_datos_desde_token,
    verificar_autenticacion_api
)
from ._helpers import guardar_estado_torneo

calendario_bp = Blueprint('calendario', __name__, url_prefix='/api')
logger = logging.getLogger(__name__)


@calendario_bp.before_request
def verificar_auth():
    authenticated, error_response = verificar_autenticacion_api()
    if not authenticated:
        return error_response


@calendario_bp.route('/generar-fixture/<categoria>', methods=['POST'])
def generar_fixture(categoria):
    """Genera el fixture de finales para una categoría."""
    try:
        resultado_data = obtener_datos_desde_token().get('resultado_algoritmo')
        if not resultado_data:
            return jsonify({'error': 'No hay resultados cargados'}), 400

        grupos_data = resultado_data['grupos_por_categoria'].get(categoria, [])
        if not grupos_data:
            return jsonify({'error': f'No hay grupos en categoría {categoria}'}), 404

        grupos_obj = []
        for grupo_dict in grupos_data:
            grupo = Grupo(
                id=grupo_dict['id'],
                categoria=categoria,
                franja_horaria=grupo_dict.get('franja_horaria'),
                score_compatibilidad=grupo_dict.get('score', 0.0)
            )

            for pareja_dict in grupo_dict['parejas']:
                pareja = Pareja(
                    id=pareja_dict['id'],
                    nombre=pareja_dict['nombre'],
                    telefono=pareja_dict.get('telefono', 'Sin teléfono'),
                    categoria=pareja_dict['categoria'],
                    franjas_disponibles=pareja_dict.get('franjas_disponibles', []),
                    grupo_asignado=grupo_dict['id'],
                    posicion_grupo=PosicionGrupo(pareja_dict['posicion_grupo']) if pareja_dict.get('posicion_grupo') else None
                )
                grupo.parejas.append(pareja)

            grupos_obj.append(grupo)

        generator = FixtureGenerator(grupos_obj)
        fixture = generator.generar_fixture()

        torneo = storage.cargar()
        if 'fixtures' not in torneo:
            torneo['fixtures'] = {}
        torneo['fixtures'][categoria] = fixture.to_dict()
        storage.guardar(torneo)
        guardar_estado_torneo()

        return jsonify({
            'success': True,
            'mensaje': 'Fixture generado exitosamente',
            'fixture': fixture.to_dict()
        })

    except Exception as e:
        logger.error(f"Error al generar fixture: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Error al generar el fixture. Por favor, intenta nuevamente.'
        }), 500


@calendario_bp.route('/obtener-fixture/<categoria>', methods=['GET'])
def obtener_fixture(categoria):
    """Obtiene el fixture de finales para una categoría."""
    try:
        fixtures = storage.cargar().get('fixtures', {})
        fixture = fixtures.get(categoria)

        if not fixture:
            return jsonify({'fixture': None})

        return jsonify({
            'success': True,
            'fixture': fixture
        })

    except Exception as e:
        return jsonify({
            'error': f'Error al obtener fixture: {str(e)}'
        }), 500


@calendario_bp.route('/marcar-ganador', methods=['POST'])
def marcar_ganador():
    """Marca el ganador de un partido de finales."""
    data = request.json
    categoria = data.get('categoria')
    partido_id = data.get('partido_id')
    ganador_id = data.get('ganador_id')

    if not all([categoria, partido_id, ganador_id]):
        return jsonify({'error': 'Faltan parámetros requeridos'}), 400

    try:
        torneo = storage.cargar()
        fixtures = torneo.get('fixtures', {})
        if categoria not in fixtures:
            return jsonify({'error': 'Fixture no encontrado'}), 404

        fixture_data = fixtures[categoria]

        resultado_data = obtener_datos_desde_token().get('resultado_algoritmo')
        grupos_data = resultado_data['grupos_por_categoria'].get(categoria, [])

        grupos_obj = []
        for grupo_dict in grupos_data:
            grupo = Grupo(
                id=grupo_dict['id'],
                categoria=categoria,
                franja_horaria=grupo_dict.get('franja_horaria'),
                score_compatibilidad=grupo_dict.get('score', 0.0)
            )

            for pareja_dict in grupo_dict['parejas']:
                pareja = Pareja(
                    id=pareja_dict['id'],
                    nombre=pareja_dict['nombre'],
                    telefono=pareja_dict.get('telefono', 'Sin teléfono'),
                    categoria=pareja_dict['categoria'],
                    franjas_disponibles=pareja_dict.get('franjas_disponibles', []),
                    grupo_asignado=grupo_dict['id'],
                    posicion_grupo=PosicionGrupo(pareja_dict['posicion_grupo']) if pareja_dict.get('posicion_grupo') else None
                )
                grupo.parejas.append(pareja)

            grupos_obj.append(grupo)

        # CRUCIAL: Reconstruir el fixture desde los datos guardados, no generar uno nuevo.
        # Esto preserva todos los ganadores anteriores.
        fixture = FixtureFinales.from_dict(fixture_data, grupos_obj)

        fixture = FixtureGenerator.actualizar_fixture_con_ganador(
            fixture,
            partido_id,
            ganador_id
        )

        fixtures[categoria] = fixture.to_dict()
        torneo['fixtures'] = fixtures
        storage.guardar(torneo)

        return jsonify({
            'success': True,
            'mensaje': '✓ Ganador confirmado',
            'fixture': fixture.to_dict()
        })

    except Exception as e:
        logger.error(f"Error al marcar ganador: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Error al marcar el ganador. Por favor, intenta nuevamente.'
        }), 500


@calendario_bp.route('/calendario-finales', methods=['GET'])
def obtener_calendario_finales():
    """Obtiene el calendario de finales del domingo con los partidos asignados."""
    try:
        fixtures = storage.cargar().get('fixtures', {})

        if not fixtures:
            calendario_base = CalendarioFinalesBuilder.generar_calendario_base()
            return jsonify({
                'success': True,
                'calendario': calendario_base,
                'tiene_datos': False
            })

        calendario = CalendarioFinalesBuilder.poblar_calendario_con_fixtures(fixtures)

        return jsonify({
            'success': True,
            'calendario': calendario,
            'tiene_datos': True
        })

    except Exception as e:
        logger.error(f"Error al generar calendario de finales: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Error al generar el calendario de finales. Por favor, intenta nuevamente.'
        }), 500


@calendario_bp.route('/obtener-calendario', methods=['GET'])
def obtener_calendario():
    """Devuelve el calendario general actualizado."""
    resultado_dict = obtener_datos_desde_token().get('resultado_algoritmo')
    if not resultado_dict:
        return jsonify({'error': 'No hay resultados disponibles'}), 404

    return jsonify({
        'success': True,
        'calendario': resultado_dict.get('calendario', {})
    })
