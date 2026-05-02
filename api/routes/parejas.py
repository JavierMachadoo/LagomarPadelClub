from flask import Blueprint, request, jsonify
import pandas as pd
import logging

from utils import CSVProcessor
from utils.torneo_storage import storage, ConflictError
from utils.api_helpers import (
    obtener_datos_desde_token,
    crear_respuesta_con_token_actualizado,
    sincronizar_con_storage_y_token,
    verificar_autenticacion_api,
)
from config import NUM_CANCHAS_DEFAULT
from utils.input_validation import validar_longitud, MAX_NOMBRE, MAX_TELEFONO
from services import ServiceError
from services import grupo_service

api_bp = Blueprint('api', __name__, url_prefix='/api')
logger = logging.getLogger(__name__)


@api_bp.before_request
def verificar_auth():
    authenticated, error_response = verificar_autenticacion_api(roles_permitidos=['admin'])
    if not authenticated:
        return error_response


@api_bp.route('/cargar-csv', methods=['POST'])
def cargar_csv():
    if 'archivo' not in request.files:
        return jsonify({'error': 'No se envio ningun archivo'}), 400
    file = request.files['archivo']
    if file.filename == '' or not CSVProcessor.validar_archivo(file.filename):
        return jsonify({'error': 'Archivo invalido'}), 400
    try:
        df = pd.read_csv(file)
        parejas = CSVProcessor.procesar_dataframe(df)
        datos_token = {'parejas': parejas, 'resultado_algoritmo': None}
        sincronizar_con_storage_y_token(datos_token)
        return crear_respuesta_con_token_actualizado(
            {'success': True, 'mensaje': f'{len(parejas)} parejas cargadas', 'parejas': parejas},
            datos_token,
        )
    except Exception as e:
        logger.error('Error al procesar CSV: %s', e, exc_info=True)
        return jsonify({'error': 'Error al procesar el archivo CSV'}), 500


@api_bp.route('/agregar-pareja', methods=['POST'])
def agregar_pareja():
    try:
        data = request.json
        jugador1 = data.get('jugador1', '').strip()
        jugador2 = data.get('jugador2', '').strip()
        nombre = data.get('nombre', '').strip()
        telefono = data.get('telefono', '').strip()
        categoria = data.get('categoria', 'Cuarta')
        franjas = data.get('franjas', [])
        desde_resultados = data.get('desde_resultados', False)

        if jugador1 and jugador2:
            nombre = f'{jugador1} / {jugador2}'
        elif jugador1 and not nombre:
            nombre = jugador1

        if not nombre:
            return jsonify({'error': 'El nombre es obligatorio'}), 400
        if not franjas:
            return jsonify({'error': 'Selecciona al menos una franja horaria'}), 400

        error_len = validar_longitud({'Nombre': (nombre, MAX_NOMBRE), 'Teléfono': (telefono, MAX_TELEFONO)})
        if error_len:
            return jsonify({'error': error_len}), 400

        jugador1_id = data.get('jugador1_id') or None
        jugador2_id = data.get('jugador2_id') or None

        datos_actuales = obtener_datos_desde_token()
        nueva_pareja, estadisticas = grupo_service.agregar_pareja(
            datos_actuales, jugador1, jugador2, nombre, telefono, categoria, franjas,
            desde_resultados, jugador1_id=jugador1_id, jugador2_id=jugador2_id,
        )
        sincronizar_con_storage_y_token(datos_actuales)

        response_data = {
            'success': True,
            'mensaje': 'Pareja agregada',
            'pareja': nueva_pareja,
            'desde_resultados': desde_resultados,
        }
        if desde_resultados and estadisticas:
            response_data['estadisticas'] = estadisticas
        return crear_respuesta_con_token_actualizado(response_data, datos_actuales)
    except Exception as e:
        logger.error('Error al agregar pareja: %s', e, exc_info=True)
        return jsonify({'error': 'Error al agregar la pareja'}), 500


@api_bp.route('/eliminar-pareja', methods=['POST'])
def eliminar_pareja():
    data = request.json
    pareja_id = data.get('id')
    datos_actuales = obtener_datos_desde_token()
    grupo_service.eliminar_pareja(datos_actuales, pareja_id)
    sincronizar_con_storage_y_token(datos_actuales)
    return crear_respuesta_con_token_actualizado(
        {'success': True, 'mensaje': 'Pareja eliminada correctamente'}, datos_actuales
    )


@api_bp.route('/remover-pareja-de-grupo', methods=['POST'])
def remover_pareja_de_grupo():
    data = request.json
    pareja_id = data.get('pareja_id')
    if not pareja_id:
        return jsonify({'error': 'Falta pareja_id'}), 400

    datos_actuales = obtener_datos_desde_token()
    resultado_data = datos_actuales.get('resultado_algoritmo')
    if not resultado_data:
        return jsonify({'error': 'No hay resultados del algoritmo'}), 404

    try:
        estadisticas = grupo_service.remover_pareja_de_grupo(
            resultado_data,
            pareja_id,
        )
    except ServiceError as e:
        return jsonify({'error': e.message}), e.status_code

    datos_actuales['resultado_algoritmo'] = resultado_data
    sincronizar_con_storage_y_token(datos_actuales)
    return crear_respuesta_con_token_actualizado(
        {'success': True, 'mensaje': 'Pareja removida del grupo', 'estadisticas': estadisticas}
    )


@api_bp.route('/obtener-parejas', methods=['GET'])
def obtener_parejas():
    datos_actuales = obtener_datos_desde_token()
    parejas = datos_actuales.get('parejas', [])
    resultado = datos_actuales.get('resultado_algoritmo')

    parejas_enriquecidas = grupo_service.enriquecer_parejas_con_asignacion(parejas, resultado)

    cats = ['Cuarta', 'Quinta', 'Sexta', 'Séptima', 'Tercera']
    stats = {
        'total': len(parejas),
        'por_categoria': {c: sum(1 for p in parejas if p.get('categoria') == c) for c in cats},
    }
    return jsonify({'success': True, 'parejas': parejas_enriquecidas, 'stats': stats})


@api_bp.route('/parejas-no-asignadas/<categoria>', methods=['GET'])
def obtener_parejas_no_asignadas(categoria):
    resultado_data = obtener_datos_desde_token().get('resultado_algoritmo')
    if not resultado_data:
        return jsonify({'error': 'No hay resultados del algoritmo'}), 404
    parejas = [p for p in resultado_data.get('parejas_sin_asignar', []) if p.get('categoria') == categoria]
    return jsonify({'success': True, 'parejas': parejas, 'total': len(parejas)})


@api_bp.route('/editar-pareja', methods=['POST'])
def editar_pareja():
    data = request.json
    pareja_id = data.get('pareja_id')
    nombre = data.get('nombre')
    telefono = data.get('telefono')
    categoria = data.get('categoria')
    franjas = data.get('franjas', [])

    if not all([pareja_id, nombre, categoria]):
        return jsonify({'error': 'Faltan parametros requeridos'}), 400
    if not franjas:
        return jsonify({'error': 'Debes seleccionar al menos una franja horaria'}), 400

    datos_actuales = obtener_datos_desde_token()
    try:
        mensaje = grupo_service.editar_pareja(
            datos_actuales, pareja_id, nombre, telefono, categoria, franjas,
        )
    except ServiceError as e:
        return jsonify({'error': e.message}), e.status_code

    sincronizar_con_storage_y_token(datos_actuales)
    return crear_respuesta_con_token_actualizado({'success': True, 'mensaje': mensaje}, datos_actuales)


@api_bp.route('/franjas-disponibles', methods=['GET'])
def obtener_franjas_disponibles():
    datos_actuales = obtener_datos_desde_token()
    resultado_data = datos_actuales.get('resultado_algoritmo')
    if not resultado_data:
        return jsonify({'error': 'No hay resultados del algoritmo'}), 404
    disponibilidad = grupo_service.obtener_franjas_disponibles(resultado_data)
    return jsonify({'success': True, 'disponibilidad': disponibilidad, 'num_canchas': NUM_CANCHAS_DEFAULT})


@api_bp.route('/cambiar-tipo-torneo', methods=['POST'])
def cambiar_tipo_torneo():
    data = request.json or {}
    tipo = data.get('tipo_torneo', 'fin1')
    if tipo not in ('fin1', 'fin2'):
        return jsonify({'error': 'Tipo de torneo invalido'}), 400
    try:
        storage.set_tipo_torneo(tipo)
    except ConflictError as e:
        return jsonify({'error': str(e)}), 409
    return jsonify({'success': True, 'tipo_torneo': tipo})


@api_bp.route('/obtener-no-asignadas/<categoria>', methods=['GET'])
def obtener_no_asignadas(categoria):
    resultado_dict = obtener_datos_desde_token().get('resultado_algoritmo')
    if not resultado_dict:
        return jsonify({'error': 'No hay resultados disponibles'}), 404
    parejas = [p for p in resultado_dict.get('parejas_sin_asignar', []) if p.get('categoria') == categoria]
    return jsonify({'success': True, 'categoria': categoria, 'parejas': parejas})
