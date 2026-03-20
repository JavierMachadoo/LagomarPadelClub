from flask import Blueprint, request, jsonify
import logging

from core import Pareja, Grupo
from utils.api_helpers import (
    obtener_datos_desde_token,
    sincronizar_con_storage_y_token,
    verificar_autenticacion_api
)
from ._helpers import (
    regenerar_fixtures_categoria,
    verificar_posiciones_completas,
)

resultados_bp = Blueprint('resultados', __name__, url_prefix='/api')
logger = logging.getLogger(__name__)


@resultados_bp.before_request
def verificar_auth():
    authenticated, error_response = verificar_autenticacion_api(roles_permitidos=['admin'])
    if not authenticated:
        return error_response


@resultados_bp.route('/asignar-posicion', methods=['POST'])
def asignar_posicion():
    """Asigna la posición final de una pareja en su grupo."""
    data = request.json
    pareja_id = data.get('pareja_id')
    posicion = data.get('posicion')  # 0 (deseleccionar), 1, 2, o 3
    categoria = data.get('categoria')

    if pareja_id is None or posicion is None or not categoria:
        return jsonify({'error': 'Faltan parámetros requeridos'}), 400

    try:
        resultado_data = obtener_datos_desde_token().get('resultado_algoritmo')
        if not resultado_data:
            return jsonify({'error': 'No hay resultados cargados'}), 400

        grupos_categoria = resultado_data['grupos_por_categoria'].get(categoria, [])
        pareja_encontrada = False
        posicion_anterior = None

        for grupo in grupos_categoria:
            for pareja in grupo['parejas']:
                if pareja['id'] == pareja_id:
                    posicion_anterior = pareja.get('posicion_grupo')
                    pareja['posicion_grupo'] = None if posicion == 0 else posicion
                    pareja_encontrada = True
                    break
            if pareja_encontrada:
                break

        if not pareja_encontrada:
            return jsonify({'error': 'Pareja no encontrada'}), 404

        datos = obtener_datos_desde_token()
        datos['resultado_algoritmo'] = resultado_data
        sincronizar_con_storage_y_token(datos)

        puede_generar = verificar_posiciones_completas(grupos_categoria)
        regenerar_fixtures_categoria(categoria, resultado_data)

        mensaje = '' if posicion == 0 else f'✓ Posición {posicion}°'

        return jsonify({
            'success': True,
            'mensaje': mensaje,
            'puede_generar_finales': puede_generar,
            'posicion': posicion,
            'posicion_anterior': posicion_anterior
        })

    except Exception as e:
        logger.error(f"Error al asignar posición: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Error al asignar posición. Por favor, intenta nuevamente.'
        }), 500


@resultados_bp.route('/guardar-resultado-partido', methods=['POST'])
def guardar_resultado_partido():
    """Guarda o actualiza el resultado de un partido de grupo."""
    from core.models import ResultadoPartido
    from core.clasificacion import CalculadorClasificacion
    from core.fixture_finales_generator import GeneradorFixtureFinales

    data = request.json
    categoria = data.get('categoria')
    grupo_id = data.get('grupo_id')
    pareja1_id = data.get('pareja1_id')
    pareja2_id = data.get('pareja2_id')

    games_set1_p1 = data.get('games_set1_pareja1')
    games_set1_p2 = data.get('games_set1_pareja2')
    games_set2_p1 = data.get('games_set2_pareja1')
    games_set2_p2 = data.get('games_set2_pareja2')
    tiebreak_p1 = data.get('tiebreak_pareja1')
    tiebreak_p2 = data.get('tiebreak_pareja2')

    if not all([categoria, grupo_id is not None, pareja1_id is not None, pareja2_id is not None]):
        return jsonify({'error': 'Faltan parámetros requeridos'}), 400

    try:
        resultado_data = obtener_datos_desde_token().get('resultado_algoritmo')
        if not resultado_data:
            return jsonify({'error': 'No hay resultados cargados'}), 400

        grupos_categoria = resultado_data['grupos_por_categoria'].get(categoria, [])
        grupo_encontrado = None

        for grupo in grupos_categoria:
            if grupo['id'] == grupo_id:
                grupo_encontrado = grupo
                break

        if not grupo_encontrado:
            return jsonify({'error': 'Grupo no encontrado'}), 404

        sets_p1 = 0
        sets_p2 = 0

        if games_set1_p1 is not None and games_set1_p2 is not None:
            if games_set1_p1 > games_set1_p2:
                sets_p1 += 1
            else:
                sets_p2 += 1

        if games_set2_p1 is not None and games_set2_p2 is not None:
            if games_set2_p1 > games_set2_p2:
                sets_p1 += 1
            else:
                sets_p2 += 1

        resultado = ResultadoPartido(
            pareja1_id=pareja1_id,
            pareja2_id=pareja2_id,
            sets_pareja1=sets_p1,
            sets_pareja2=sets_p2,
            games_set1_pareja1=games_set1_p1,
            games_set1_pareja2=games_set1_p2,
            games_set2_pareja1=games_set2_p1,
            games_set2_pareja2=games_set2_p2,
            tiebreak_pareja1=tiebreak_p1,
            tiebreak_pareja2=tiebreak_p2
        )

        resultado_dict = resultado.to_dict()

        if 'resultados' not in grupo_encontrado:
            grupo_encontrado['resultados'] = {}

        ids_ordenados = sorted([pareja1_id, pareja2_id])
        key = f"{ids_ordenados[0]}-{ids_ordenados[1]}"
        grupo_encontrado['resultados'][key] = resultado_dict

        grupo_encontrado['resultados_completos'] = False
        if len(grupo_encontrado.get('parejas', [])) == 3:
            resultados = grupo_encontrado.get('resultados', {})
            resultados_completos = sum(
                1 for r in resultados.values()
                if ResultadoPartido.from_dict(r).esta_completo()
            )
            grupo_encontrado['resultados_completos'] = (resultados_completos == 3)

        if grupo_encontrado.get('resultados_completos', False):
            grupo_obj = Grupo(
                id=grupo_encontrado['id'],
                categoria=categoria,
                franja_horaria=grupo_encontrado.get('franja_horaria')
            )

            for pareja_dict in grupo_encontrado['parejas']:
                pareja = Pareja(
                    id=pareja_dict['id'],
                    nombre=pareja_dict['nombre'],
                    telefono=pareja_dict.get('telefono', 'Sin teléfono'),
                    categoria=pareja_dict['categoria'],
                    franjas_disponibles=pareja_dict.get('franjas_disponibles', []),
                    grupo_asignado=grupo_encontrado['id']
                )
                grupo_obj.parejas.append(pareja)

            for k, rd in grupo_encontrado['resultados'].items():
                grupo_obj.resultados[k] = ResultadoPartido.from_dict(rd)

            posiciones = CalculadorClasificacion.asignar_posiciones(grupo_obj)

            for pareja_dict in grupo_encontrado['parejas']:
                pid = pareja_dict['id']
                if pid in posiciones:
                    pareja_dict['posicion_grupo'] = posiciones[pid].value

        datos = obtener_datos_desde_token()
        datos['resultado_algoritmo'] = resultado_data

        if grupo_encontrado.get('resultados_completos', False):
            try:
                grupos_data = resultado_data['grupos_por_categoria'].get(categoria, [])
                grupos_obj = [Grupo.from_dict(g) for g in grupos_data]

                fixture = GeneradorFixtureFinales.generar_fixture(categoria, grupos_obj)

                if fixture:
                    if 'fixtures_finales' not in datos:
                        datos['fixtures_finales'] = {}
                    datos['fixtures_finales'][categoria] = fixture.to_dict()
                    logger.info(f"Fixtures de finales regenerados automáticamente para {categoria}")
            except Exception as e:
                logger.error(f"Error al regenerar fixtures: {str(e)}")

        sincronizar_con_storage_y_token(datos)

        return jsonify({
            'success': True,
            'mensaje': '✓ Resultado guardado',
            'resultado': resultado.to_dict(),
            'resultados_completos': grupo_encontrado.get('resultados_completos', False)
        })

    except Exception as e:
        logger.error(f"Error al guardar resultado: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Error al guardar el resultado. Por favor, intenta nuevamente.'
        }), 500


@resultados_bp.route('/obtener-tabla-posiciones/<categoria>/<int:grupo_id>', methods=['GET'])
def obtener_tabla_posiciones(categoria, grupo_id):
    """Obtiene la tabla de posiciones de un grupo."""
    from core.models import ResultadoPartido
    from core.clasificacion import CalculadorClasificacion

    try:
        resultado_data = obtener_datos_desde_token().get('resultado_algoritmo')
        if not resultado_data:
            return jsonify({'error': 'No hay resultados cargados'}), 400

        grupos_categoria = resultado_data['grupos_por_categoria'].get(categoria, [])
        grupo_encontrado = None

        for grupo in grupos_categoria:
            if grupo['id'] == grupo_id:
                grupo_encontrado = grupo
                break

        if not grupo_encontrado:
            return jsonify({'error': 'Grupo no encontrado'}), 404

        grupo_obj = Grupo(
            id=grupo_encontrado['id'],
            categoria=categoria,
            franja_horaria=grupo_encontrado.get('franja_horaria')
        )

        for pareja_dict in grupo_encontrado['parejas']:
            pareja = Pareja(
                id=pareja_dict['id'],
                nombre=pareja_dict['nombre'],
                telefono=pareja_dict.get('telefono', 'Sin teléfono'),
                categoria=pareja_dict['categoria'],
                franjas_disponibles=pareja_dict.get('franjas_disponibles', []),
                grupo_asignado=grupo_encontrado['id']
            )
            grupo_obj.parejas.append(pareja)

        for k, rd in grupo_encontrado.get('resultados', {}).items():
            grupo_obj.resultados[k] = ResultadoPartido.from_dict(rd)

        tabla = CalculadorClasificacion.calcular_tabla_posiciones(grupo_obj)

        return jsonify({
            'success': True,
            'tabla': tabla,
            'resultados_completos': grupo_encontrado.get('resultados_completos', False)
        })

    except Exception as e:
        logger.error(f"Error al obtener tabla: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Error al obtener la tabla de posiciones. Por favor, intenta nuevamente.'
        }), 500
