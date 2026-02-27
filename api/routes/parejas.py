from flask import Blueprint, request, jsonify
import pandas as pd
import os
import logging

# Configure logging
logger = logging.getLogger(__name__)

from core import (
    Pareja, AlgoritmoGrupos, ResultadoAlgoritmo, Grupo,
    PosicionGrupo, FixtureGenerator, FixtureFinales
)
from core.fixture_finales_generator import GeneradorFixtureFinales
from utils import CSVProcessor, CalendarioBuilder
from utils.calendario_finales_builder import CalendarioFinalesBuilder
from utils.torneo_storage import storage
from utils.api_helpers import (
    obtener_datos_desde_token,
    crear_respuesta_con_token_actualizado,
    sincronizar_con_storage_y_token,
    verificar_autenticacion_api
)
from config import CATEGORIAS, NUM_CANCHAS_DEFAULT

api_bp = Blueprint('api', __name__, url_prefix='/api')
logger = logging.getLogger(__name__)


# Middleware para verificar autenticación en todas las rutas de API
@api_bp.before_request
def verificar_auth():
    """Verifica que el usuario esté autenticado antes de acceder a la API."""
    authenticated, error_response = verificar_autenticacion_api()
    if not authenticated:
        return error_response


# ==================== HELPERS ====================

def regenerar_fixtures_categoria(categoria, resultado_data):
    """Regenera los fixtures de finales para una categoría específica.
    
    Args:
        categoria: String con el nombre de la categoría (ej: '4ta')
        resultado_data: Dict con el estado del torneo
    """
    try:
        # Obtener los grupos de la categoría
        grupos_data = resultado_data.get('grupos_por_categoria', {}).get(categoria, [])
        if not grupos_data:
            logger.warning(f"No se encontraron grupos para la categoría {categoria}")
            return
        
        # Reconstruir objetos Grupo desde el dict
        grupos = []
        for grupo_data in grupos_data:
            try:
                grupo = Grupo.from_dict(grupo_data)
                grupos.append(grupo)
            except Exception as e:
                logger.error(f"Error al reconstruir grupo: {e}")
                continue
        
        if not grupos:
            logger.warning(f"No se pudieron reconstruir grupos para {categoria}")
            return
        
        # Generar fixture para esta categoría
        generador = GeneradorFixtureFinales()
        fixture = generador.generar_fixture(grupos, NUM_CANCHAS_DEFAULT)
        
        # Guardar en el torneo
        torneo = storage.cargar()
        if not torneo:
            torneo = {}
        
        if 'fixtures_finales' not in torneo:
            torneo['fixtures_finales'] = {}
        
        # Convertir fixture a dict
        if fixture:
            torneo['fixtures_finales'][categoria] = fixture.to_dict()
        else:
            torneo['fixtures_finales'][categoria] = None
        
        storage.guardar(torneo)
        logger.info(f"Fixtures regenerados exitosamente para categoría {categoria}")
        
    except Exception as e:
        logger.error(f"Error al regenerar fixtures para {categoria}: {e}")
        import traceback
        traceback.print_exc()

def recalcular_estadisticas(resultado_data):
    """Recalcula las estadísticas globales del torneo basándose en el estado actual."""
    grupos_dict = resultado_data.get('grupos_por_categoria', {})
    parejas_sin_asignar = resultado_data.get('parejas_sin_asignar', [])
    
    # Contar parejas asignadas
    parejas_asignadas = 0
    total_grupos = 0
    sum_scores = 0.0
    grupos_con_score = 0
    
    for categoria, grupos in grupos_dict.items():
        for grupo in grupos:
            total_grupos += 1
            parejas_en_grupo = len(grupo.get('parejas', []))
            parejas_asignadas += parejas_en_grupo
            
            # Sumar score de compatibilidad
            score = grupo.get('score', 0.0)
            if score > 0:
                sum_scores += score
                grupos_con_score += 1
    
    # Total de parejas (asignadas + no asignadas)
    total_parejas = parejas_asignadas + len(parejas_sin_asignar)
    
    # Calcular porcentaje de asignación
    porcentaje_asignacion = (parejas_asignadas / total_parejas * 100) if total_parejas > 0 else 0
    
    # Calcular score promedio (sobre 3.0)
    score_promedio = (sum_scores / grupos_con_score) if grupos_con_score > 0 else 0.0
    
    # Actualizar estadísticas en resultado_data
    resultado_data['estadisticas'] = {
        'parejas_asignadas': parejas_asignadas,
        'total_parejas': total_parejas,
        'parejas_sin_asignar': len(parejas_sin_asignar),
        'porcentaje_asignacion': porcentaje_asignacion,
        'total_grupos': total_grupos,
        'score_compatibilidad_promedio': score_promedio
    }
    
    return resultado_data['estadisticas']


def recalcular_score_grupo(grupo_dict):
    """Recalcula el score de compatibilidad de un grupo según sus parejas actuales."""
    parejas = grupo_dict.get('parejas', [])
    franja_asignada = grupo_dict.get('franja_horaria')
    
    # Si no hay parejas, score es 0
    if len(parejas) == 0:
        grupo_dict['score'] = 0.0
        grupo_dict['score_compatibilidad'] = 0.0
        return
    
    if not franja_asignada:
        # Si no hay franja asignada, usar algoritmo original
        parejas_obj = [Pareja.from_dict(p) for p in parejas]
        
        if len(parejas_obj) < 2:
            # Con 1 pareja, no se puede calcular compatibilidad sin franja
            score = 0.0
        elif len(parejas_obj) < 3:
            # Grupo incompleto con 2 parejas: calcular compatibilidad parcial
            franjas_p1 = set(parejas_obj[0].franjas_disponibles)
            franjas_p2 = set(parejas_obj[1].franjas_disponibles)
            franjas_comunes = franjas_p1 & franjas_p2
            score = 2.0 if franjas_comunes else 0.0
        else:
            # Usar lógica del algoritmo
            algoritmo = AlgoritmoGrupos(parejas_obj)
            score, _ = algoritmo._calcular_compatibilidad(parejas_obj)
    else:
        # Si hay franja asignada, calcular score acumulativo por pareja
        dia_asignado = franja_asignada.split(' ')[0] if ' ' in franja_asignada else ''
        score = 0.0
        
        for pareja in parejas:
            franjas_pareja = pareja.get('franjas_disponibles', [])
            
            if franja_asignada in franjas_pareja:
                # Horario exacto: suma 1.0
                score += 1.0
            elif dia_asignado:
                # Verificar si al menos tiene el mismo día
                dias_pareja = set(f.split(' ')[0] for f in franjas_pareja if ' ' in f)
                if dia_asignado in dias_pareja:
                    # Mismo día, hora diferente: suma 0.5
                    score += 0.5
                # Si no tiene el día: suma 0.0 (no suma nada)
    
    grupo_dict['score'] = score
    grupo_dict['score_compatibilidad'] = score


def regenerar_calendario(resultado_data):
    """Regenera el calendario completo y los partidos de cada grupo basándose en las parejas actuales."""
    try:
        # Deserializar resultado (esto regenera los partidos de cada grupo automáticamente)
        resultado_obj = deserializar_resultado(resultado_data)
        
        # Obtener número de canchas
        datos_actuales = obtener_datos_desde_token()
        num_canchas = datos_actuales.get('num_canchas', NUM_CANCHAS_DEFAULT)
        
        # Crear mapeo de grupo_id a cancha desde resultado_data
        canchas_por_grupo = {}
        for categoria, grupos_list in resultado_data['grupos_por_categoria'].items():
            for grupo_dict in grupos_list:
                if grupo_dict.get('cancha'):
                    canchas_por_grupo[grupo_dict['id']] = grupo_dict['cancha']
        
        # Regenerar calendario usando CalendarioBuilder
        calendario_builder = CalendarioBuilder(num_canchas)
        calendario = calendario_builder.organizar_partidos(resultado_obj, canchas_por_grupo)
        
        # Actualizar calendario en resultado_data
        resultado_data['calendario'] = calendario
        
        # Actualizar partidos de cada grupo en resultado_data con IDs
        for categoria, grupos_obj in resultado_obj.grupos_por_categoria.items():
            grupos_list = resultado_data['grupos_por_categoria'].get(categoria, [])
            for grupo_obj in grupos_obj:
                # Buscar el grupo correspondiente en resultado_data por ID
                for grupo_dict in grupos_list:
                    if grupo_dict['id'] == grupo_obj.id:
                        # Actualizar partidos CON IDs
                        grupo_dict['partidos'] = [
                            {
                                'pareja1': p1.nombre, 
                                'pareja2': p2.nombre,
                                'pareja1_id': p1.id,
                                'pareja2_id': p2.id
                            }
                            for p1, p2 in grupo_obj.partidos
                        ]
                        # Preservar resultados y estado - serializar resultados
                        grupo_dict['resultados'] = {k: v.to_dict() for k, v in grupo_obj.resultados.items()}
                        grupo_dict['resultados_completos'] = grupo_obj.todos_resultados_completos()
                        break
        
        return calendario
    except Exception as e:
        logger.error(f"Error al regenerar calendario: {e}", exc_info=True)
        return resultado_data.get('calendario', {})


def guardar_estado_torneo():
    """
    DEPRECATED: Con JWT, los datos se sincronizan automáticamente.
    Mantenida para compatibilidad temporal.
    """
    # Los datos ya se guardan con sincronizar_con_storage_y_token()
    pass


def guardar_estado_torneo_legacy():
    """Versión legacy - Guarda el estado actual del torneo en el almacenamiento JSON."""
    torneo = storage.cargar()
    
    # Actualizar datos del torneo desde datos actuales
    datos = obtener_datos_desde_token()
    torneo['parejas'] = datos.get('parejas', [])
    torneo['resultado_algoritmo'] = datos.get('resultado_algoritmo')
    torneo['num_canchas'] = datos.get('num_canchas', NUM_CANCHAS_DEFAULT)
    
    # Determinar estado según el progreso
    if torneo['resultado_algoritmo']:
        torneo['estado'] = 'grupos_generados'
    elif torneo['parejas']:
        torneo['estado'] = 'creando'
    else:
        torneo['estado'] = 'creando'
    
    storage.guardar(torneo)


# ==================== CARGA DE DATOS ====================

@api_bp.route('/cargar-csv', methods=['POST'])
def cargar_csv():
    """Carga parejas desde un archivo CSV."""
    if 'archivo' not in request.files:
        return jsonify({'error': 'No se envió ningún archivo'}), 400
    
    file = request.files['archivo']
    
    if file.filename == '' or not CSVProcessor.validar_archivo(file.filename):
        return jsonify({'error': 'Archivo inválido'}), 400
    
    try:
        df = pd.read_csv(file)
        parejas = CSVProcessor.procesar_dataframe(df)
        
        datos_token = {
            'parejas': parejas,
            'resultado_algoritmo': None,
            'num_canchas': NUM_CANCHAS_DEFAULT
        }
        sincronizar_con_storage_y_token(datos_token)
        
        return crear_respuesta_con_token_actualizado({
            'success': True,
            'mensaje': f'✅ {len(parejas)} parejas cargadas correctamente',
            'parejas': parejas
        }, datos_token)
    except Exception as e:
        return jsonify({'error': f'Error al procesar CSV: {str(e)}'}), 500


@api_bp.route('/agregar-pareja', methods=['POST'])
def agregar_pareja():
    """Agrega una pareja manualmente al torneo."""
    try:
        data = request.json

        jugador1 = data.get('jugador1', '').strip()
        jugador2 = data.get('jugador2', '').strip()
        nombre = data.get('nombre', '').strip()
        telefono = data.get('telefono', '').strip()
        categoria = data.get('categoria', 'Cuarta')
        franjas = data.get('franjas', [])
        desde_resultados = data.get('desde_resultados', False)

        # Construir nombre combinado desde jugador1/jugador2 si se proveen
        if jugador1 and jugador2:
            nombre = f"{jugador1} / {jugador2}"
        elif jugador1 and not nombre:
            nombre = jugador1

        if not nombre:
            return jsonify({'error': 'El nombre es obligatorio'}), 400

        if not franjas:
            return jsonify({'error': 'Selecciona al menos una franja horaria'}), 400
        
        datos_actuales = obtener_datos_desde_token()
        parejas = datos_actuales.get('parejas', [])
        
        # Generar nuevo ID único
        max_id = max([p['id'] for p in parejas], default=0)
        nueva_pareja = {
            'categoria': categoria,
            'franjas_disponibles': franjas,
            'id': max_id + 1,
            'nombre': nombre,
            'jugador1': jugador1 if jugador1 else nombre,
            'jugador2': jugador2,
            'telefono': telefono or 'Sin teléfono'
        }
        
        parejas.append(nueva_pareja)
        datos_actuales['parejas'] = parejas
        
        # Si estamos en resultados y hay algoritmo ejecutado, agregar a no asignadas
        estadisticas = None
        if desde_resultados:
            resultado_data = datos_actuales.get('resultado_algoritmo')
            if resultado_data:
                # Agregar a parejas no asignadas
                parejas_sin_asignar = resultado_data.get('parejas_sin_asignar', [])
                parejas_sin_asignar.append(nueva_pareja)
                resultado_data['parejas_sin_asignar'] = parejas_sin_asignar
                
                # Recalcular estadísticas globales
                estadisticas = recalcular_estadisticas(resultado_data)
                datos_actuales['resultado_algoritmo'] = resultado_data
        
        sincronizar_con_storage_y_token(datos_actuales)
        
        response_data = {
            'success': True,
            'mensaje': f'Pareja "{nombre}" agregada correctamente',
            'pareja': nueva_pareja,
            'desde_resultados': desde_resultados
        }
        
        # Incluir estadísticas si estamos en resultados
        if desde_resultados and estadisticas:
            response_data['estadisticas'] = estadisticas
        
        logger.info(f"Pareja agregada exitosamente: {nombre}")
        return crear_respuesta_con_token_actualizado(response_data, datos_actuales)
    
    except Exception as e:
        logger.error(f"Error al agregar pareja: {str(e)}", exc_info=True)
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Error al agregar pareja: {str(e)}'}), 500


@api_bp.route('/eliminar-pareja', methods=['POST'])
def eliminar_pareja():
    """Elimina una pareja del torneo completamente."""
    data = request.json
    pareja_id = data.get('id')
    
    datos_actuales = obtener_datos_desde_token()
    
    # 1. Eliminar de la lista base de parejas
    parejas = datos_actuales.get('parejas', [])
    parejas = [p for p in parejas if p['id'] != pareja_id]
    datos_actuales['parejas'] = parejas
    
    # 2. Si hay resultado del algoritmo, eliminar de grupos y no asignadas
    resultado_data = datos_actuales.get('resultado_algoritmo')
    if resultado_data:
        # Eliminar de grupos
        grupos_dict = resultado_data['grupos_por_categoria']
        for cat, grupos in grupos_dict.items():
            for grupo in grupos:
                parejas_grupo = grupo.get('parejas', [])
                grupo['parejas'] = [p for p in parejas_grupo if p.get('id') != pareja_id]
                # Recalcular score si se eliminó del grupo
                if len(grupo['parejas']) != len(parejas_grupo):
                    recalcular_score_grupo(grupo)
        
        # Eliminar de no asignadas
        parejas_sin_asignar = resultado_data.get('parejas_sin_asignar', [])
        resultado_data['parejas_sin_asignar'] = [p for p in parejas_sin_asignar if p.get('id') != pareja_id]
        
        # Regenerar calendario y estadísticas
        regenerar_calendario(resultado_data)
        resultado_data['estadisticas'] = recalcular_estadisticas(resultado_data)
        datos_actuales['resultado_algoritmo'] = resultado_data
    
    sincronizar_con_storage_y_token(datos_actuales)
    guardar_estado_torneo()
    
    return crear_respuesta_con_token_actualizado({
        'success': True,
        'mensaje': 'Pareja eliminada correctamente'
    }, datos_actuales)


@api_bp.route('/remover-pareja-de-grupo', methods=['POST'])
def remover_pareja_de_grupo():
    """Remueve una pareja de un grupo y la devuelve a parejas no asignadas."""
    data = request.json
    pareja_id = data.get('pareja_id')
    
    if not pareja_id:
        return jsonify({'error': 'Falta pareja_id'}), 400
    
    datos_actuales = obtener_datos_desde_token()
    resultado_data = datos_actuales.get('resultado_algoritmo')
    if not resultado_data:
        return jsonify({'error': 'No hay resultados del algoritmo'}), 404
    
    grupos_dict = resultado_data['grupos_por_categoria']
    parejas_sin_asignar = resultado_data.get('parejas_sin_asignar', [])
    
    # Buscar la pareja en los grupos
    pareja_encontrada = None
    grupo_contenedor = None
    
    for cat, grupos in grupos_dict.items():
        for grupo in grupos:
            for idx, pareja in enumerate(grupo.get('parejas', [])):
                if pareja.get('id') == pareja_id:
                    pareja_encontrada = grupo['parejas'].pop(idx)
                    grupo_contenedor = grupo
                    break
            if pareja_encontrada:
                break
        if pareja_encontrada:
            break
    
    if not pareja_encontrada:
        return jsonify({'error': 'Pareja no encontrada en ningún grupo'}), 404
    
    # Limpiar la posición de grupo antes de agregar a no asignadas
    pareja_encontrada['posicion_grupo'] = None
    
    # Agregar a parejas no asignadas
    parejas_sin_asignar.append(pareja_encontrada)
    
    # Recalcular score del grupo afectado
    recalcular_score_grupo(grupo_contenedor)
    
    # Regenerar calendario completo
    regenerar_calendario(resultado_data)
    
    # Recalcular estadísticas globales
    estadisticas = recalcular_estadisticas(resultado_data)
    
    # Actualizar datos
    datos_actuales['resultado_algoritmo'] = resultado_data
    sincronizar_con_storage_y_token(datos_actuales)
    guardar_estado_torneo()
    
    return crear_respuesta_con_token_actualizado({
        'success': True,
        'mensaje': f'✓ Pareja removida del grupo y devuelta a no asignadas',
        'estadisticas': estadisticas
    })


@api_bp.route('/limpiar-datos', methods=['POST'])
def limpiar_datos():
    """Limpia todos los datos del torneo actual, preservando el tipo de torneo."""
    storage.limpiar()

    # Crear token con datos vacíos
    datos_limpios = {
        'parejas': [],
        'resultado_algoritmo': None,
        'num_canchas': NUM_CANCHAS_DEFAULT
    }
    
    return crear_respuesta_con_token_actualizado({
        'success': True,
        'mensaje': 'Datos limpiados correctamente'
    }, datos_limpios)


@api_bp.route('/cambiar-tipo-torneo', methods=['POST'])
def cambiar_tipo_torneo():
    """Cambia el tipo de torneo activo sin borrar datos."""
    data = request.json or {}
    tipo = data.get('tipo_torneo', 'fin1')
    if tipo not in ('fin1', 'fin2'):
        return jsonify({'error': 'Tipo de torneo inválido'}), 400
    storage.set_tipo_torneo(tipo)
    return jsonify({'success': True, 'tipo_torneo': tipo})


@api_bp.route('/obtener-parejas', methods=['GET'])
def obtener_parejas():
    """Obtiene la lista actualizada de parejas con estadísticas y estado de asignación."""
    datos_actuales = obtener_datos_desde_token()
    parejas = datos_actuales.get('parejas', [])
    resultado = datos_actuales.get('resultado_algoritmo')
    
    # Enriquecer parejas con información de asignación
    parejas_enriquecidas = []
    for pareja in parejas:
        pareja_info = pareja.copy()
        pareja_info['grupo_asignado'] = None
        pareja_info['franja_asignada'] = None
        pareja_info['esta_asignada'] = False
        pareja_info['fuera_de_horario'] = False
        
        # Si hay resultado del algoritmo, buscar asignación
        if resultado:
            # Buscar en grupos
            for categoria, grupos in resultado.get('grupos_por_categoria', {}).items():
                for grupo in grupos:
                    for p in grupo.get('parejas', []):
                        if p['id'] == pareja['id']:
                            pareja_info['grupo_asignado'] = grupo['id']
                            pareja_info['franja_asignada'] = grupo.get('franja_horaria')
                            pareja_info['esta_asignada'] = True
                            
                            # Verificar si está fuera de horario
                            franja_asignada = grupo.get('franja_horaria')
                            if franja_asignada:
                                franjas_disponibles = pareja.get('franjas_disponibles', [])
                                if franja_asignada not in franjas_disponibles:
                                    pareja_info['fuera_de_horario'] = True
                            break
                    if pareja_info['esta_asignada']:
                        break
                if pareja_info['esta_asignada']:
                    break
        
        parejas_enriquecidas.append(pareja_info)
    
    # Calcular estadísticas
    stats = {
        'total': len(parejas),
        'por_categoria': {
            'Cuarta': sum(1 for p in parejas if p.get('categoria') == 'Cuarta'),
            'Quinta': sum(1 for p in parejas if p.get('categoria') == 'Quinta'),
            'Sexta': sum(1 for p in parejas if p.get('categoria') == 'Sexta'),
            'Séptima': sum(1 for p in parejas if p.get('categoria') == 'Séptima'),
            'Tercera': sum(1 for p in parejas if p.get('categoria') == 'Tercera')
        }
    }
    
    return jsonify({
        'success': True,
        'parejas': parejas_enriquecidas,
        'stats': stats
    })


@api_bp.route('/resultado_algoritmo', methods=['GET'])
def obtener_resultado_algoritmo():
    """Obtiene el resultado completo del algoritmo con grupos y parejas."""
    datos_actuales = obtener_datos_desde_token()
    resultado_data = datos_actuales.get('resultado_algoritmo')
    
    if not resultado_data:
        return jsonify({'error': 'No hay resultados del algoritmo'}), 404
    
    return jsonify(resultado_data)


@api_bp.route('/intercambiar-pareja', methods=['POST'])
def intercambiar_pareja():
    """Intercambia parejas entre slots específicos de grupos."""
    data = request.json
    pareja_id = data.get('pareja_id')
    grupo_origen_id = data.get('grupo_origen')
    grupo_destino_id = data.get('grupo_destino')
    slot_destino = data.get('slot_destino')  # 0, 1, o 2
    
    datos_actuales = obtener_datos_desde_token()
    resultado = datos_actuales.get('resultado_algoritmo')
    if not resultado:
        return jsonify({'error': 'No hay resultados cargados'}), 400
    
    try:
        pareja_movida = None
        grupo_origen_obj = None
        grupo_destino_obj = None
        categoria_actual = None
        
        # Buscar la pareja que se está moviendo y los grupos
        for categoria, grupos in resultado['grupos_por_categoria'].items():
            for grupo in grupos:
                if grupo['id'] == grupo_origen_id:
                    categoria_actual = categoria
                    grupo_origen_obj = grupo
                    for i, pareja in enumerate(grupo['parejas']):
                        if pareja['id'] == pareja_id:
                            pareja_movida = grupo['parejas'].pop(i)
                            break
                
                if grupo['id'] == grupo_destino_id:
                    grupo_destino_obj = grupo
        
        if not pareja_movida or not grupo_destino_obj:
            return jsonify({'error': 'No se encontró la pareja o el grupo'}), 400
        
        # Verificar si hay una pareja en el slot destino
        pareja_en_slot = None
        if slot_destino < len(grupo_destino_obj['parejas']):
            pareja_en_slot = grupo_destino_obj['parejas'][slot_destino]
        
        # Intercambio
        if pareja_en_slot:
            # Hay una pareja en el slot destino, intercambiarlas
            grupo_destino_obj['parejas'][slot_destino] = pareja_movida
            grupo_origen_obj['parejas'].append(pareja_en_slot)
            mensaje = f"Intercambio exitoso: {pareja_movida['nombre']} ↔ {pareja_en_slot['nombre']}"
        else:
            # El slot está vacío, solo mover la pareja
            # Insertar en el slot específico o al final si el grupo no tiene suficientes parejas
            if slot_destino <= len(grupo_destino_obj['parejas']):
                grupo_destino_obj['parejas'].insert(slot_destino, pareja_movida)
            else:
                grupo_destino_obj['parejas'].append(pareja_movida)
            mensaje = f"Pareja {pareja_movida['nombre']} movida al slot {slot_destino + 1}"
        
        # Recalcular scores de ambos grupos
        recalcular_score_grupo(grupo_origen_obj)
        recalcular_score_grupo(grupo_destino_obj)
        
        # Regenerar calendario completo
        regenerar_calendario(resultado)
        
        # Recalcular estadísticas globales
        estadisticas = recalcular_estadisticas(resultado)
        
        datos_actuales['resultado_algoritmo'] = resultado
        sincronizar_con_storage_y_token(datos_actuales)
        guardar_estado_torneo()  # Auto-guardar
        
        return crear_respuesta_con_token_actualizado({
            'success': True,
            'mensaje': mensaje,
            'estadisticas': estadisticas
        }, datos_actuales)
    except Exception as e:
        logger.error(f"Error al intercambiar: {str(e)}", exc_info=True)
        return jsonify({'error': 'Error al intercambiar parejas. Por favor, intenta nuevamente.'}), 500


@api_bp.route('/ejecutar-algoritmo', methods=['POST'])
def ejecutar_algoritmo():
    """Ejecuta el algoritmo de generación de grupos para el torneo."""
    datos_actuales = obtener_datos_desde_token()
    parejas_data = datos_actuales.get('parejas', [])
    
    if not parejas_data:
        return jsonify({'error': 'No hay parejas cargadas'}), 400
    
    try:
        parejas_obj = [Pareja.from_dict(p) for p in parejas_data]
        
        algoritmo = AlgoritmoGrupos(parejas=parejas_obj, num_canchas=NUM_CANCHAS_DEFAULT)
        resultado_obj = algoritmo.ejecutar()
        
        resultado = serializar_resultado(resultado_obj, NUM_CANCHAS_DEFAULT)
        
        datos_actuales['resultado_algoritmo'] = resultado
        datos_actuales['num_canchas'] = NUM_CANCHAS_DEFAULT
        sincronizar_con_storage_y_token(datos_actuales)
        guardar_estado_torneo()  # Auto-guardar
        
        return crear_respuesta_con_token_actualizado({
            'success': True,
            'mensaje': f'✅ {len(parejas_data)} parejas cargadas y grupos generados exitosamente',
            'resultado': resultado
        }, datos_actuales)
    except Exception as e:
        logger.error(f"Error al ejecutar algoritmo: {str(e)}", exc_info=True)
        return jsonify({
            'error': 'Error al ejecutar el algoritmo. Por favor, verifica los datos e intenta nuevamente.'
        }), 500


def serializar_resultado(resultado, num_canchas):
    """Convierte el resultado del algoritmo a formato JSON serializable."""
    grupos_dict = {}
    canchas_por_grupo = {}  # Mapeo de grupo_id a cancha
    
    # Obtener las asignaciones de cancha del calendario del algoritmo
    # El calendario ya tiene las canchas asignadas correctamente sin solapamientos
    for franja, partidos_franja in resultado.calendario.items():
        for partido in partidos_franja:
            grupo_id = partido.get('grupo_id')
            cancha = partido.get('cancha')
            if grupo_id and cancha:
                canchas_por_grupo[grupo_id] = cancha
    
    for categoria, grupos in resultado.grupos_por_categoria.items():
        grupos_dict[categoria] = []
        
        for grupo in grupos:
            # Usar la cancha asignada por el algoritmo
            cancha_num = canchas_por_grupo.get(grupo.id)
            
            grupos_dict[categoria].append({
                'id': grupo.id,
                'parejas': [p.to_dict() for p in grupo.parejas],
                'partidos': [
                    {
                        'pareja1': p1.nombre, 
                        'pareja2': p2.nombre,
                        'pareja1_id': p1.id,
                        'pareja2_id': p2.id
                    }
                    for p1, p2 in grupo.partidos
                ],
                'resultados': {},  # Inicializar diccionario de resultados vacío
                'franja_horaria': grupo.franja_horaria,
                'cancha': cancha_num,
                'score': grupo.score_compatibilidad,
                'resultados_completos': False
            })
    
    calendario_builder = CalendarioBuilder(num_canchas)
    calendario = calendario_builder.organizar_partidos(resultado, canchas_por_grupo)
    
    return {
        'grupos_por_categoria': grupos_dict,
        'estadisticas': resultado.estadisticas,
        'parejas_sin_asignar': [p.to_dict() for p in resultado.parejas_sin_asignar],
        'calendario': calendario
    }


@api_bp.route('/parejas-no-asignadas/<categoria>', methods=['GET'])
def obtener_parejas_no_asignadas(categoria):
    """Obtiene las parejas no asignadas de una categoría específica."""
    datos_actuales = obtener_datos_desde_token()
    resultado_data = datos_actuales.get('resultado_algoritmo')
    if not resultado_data:
        return jsonify({'error': 'No hay resultados del algoritmo'}), 404
    
    parejas_no_asignadas = resultado_data.get('parejas_sin_asignar', [])
    
    # Filtrar por categoría
    parejas_categoria = [
        pareja for pareja in parejas_no_asignadas 
        if pareja.get('categoria') == categoria
    ]
    
    return jsonify({
        'success': True,
        'parejas': parejas_categoria,
        'total': len(parejas_categoria)
    })


@api_bp.route('/asignar-pareja-a-grupo', methods=['POST'])
def asignar_pareja_a_grupo():
    """Asigna una pareja no asignada a un grupo, opcionalmente en un slot específico."""
    data = request.json
    pareja_id = data.get('pareja_id')
    grupo_id = data.get('grupo_id')
    pareja_a_remover_id = data.get('pareja_a_remover_id')  # Opcional
    categoria = data.get('categoria')
    slot_destino = data.get('slot_destino')  # Opcional: 0, 1, o 2
    
    if not all([pareja_id, grupo_id, categoria]):
        return jsonify({'error': 'Faltan parámetros requeridos'}), 400
    
    resultado_data = obtener_datos_desde_token().get('resultado_algoritmo')
    if not resultado_data:
        return jsonify({'error': 'No hay resultados del algoritmo'}), 404
    
    grupos_dict = resultado_data['grupos_por_categoria']
    parejas_sin_asignar = resultado_data.get('parejas_sin_asignar', [])
    
    # Buscar la pareja no asignada
    pareja_a_asignar = None
    for idx, p in enumerate(parejas_sin_asignar):
        if p.get('id') == pareja_id:
            pareja_a_asignar = parejas_sin_asignar.pop(idx)
            break
    
    if not pareja_a_asignar:
        return jsonify({'error': 'Pareja no encontrada en no asignadas'}), 404
    
    # Buscar el grupo
    grupo_encontrado = None
    for grupo in grupos_dict.get(categoria, []):
        if grupo['id'] == grupo_id:
            grupo_encontrado = grupo
            break
    
    if not grupo_encontrado:
        return jsonify({'error': 'Grupo no encontrado'}), 404
    
    # Si hay pareja a remover, quitarla del grupo y agregarla a no asignadas
    if pareja_a_remover_id:
        pareja_removida = None
        for idx, p in enumerate(grupo_encontrado['parejas']):
            if p.get('id') == pareja_a_remover_id:
                pareja_removida = grupo_encontrado['parejas'].pop(idx)
                break
        
        if pareja_removida:
            # Limpiar la posición de grupo antes de agregar a no asignadas
            pareja_removida['posicion_grupo'] = None
            parejas_sin_asignar.append(pareja_removida)
    
    # Si el grupo ya tiene 3 parejas y no se especificó a quién remover
    if len(grupo_encontrado['parejas']) >= 3 and not pareja_a_remover_id:
        # Devolver la pareja a no asignadas
        parejas_sin_asignar.append(pareja_a_asignar)
        return jsonify({
            'error': 'El grupo ya tiene 3 parejas. Debes especificar cuál reemplazar.',
            'grupo_lleno': True,
            'parejas_grupo': grupo_encontrado['parejas']
        }), 400
    
    # Agregar la pareja al grupo en el slot específico si se provee
    if slot_destino is not None and slot_destino < len(grupo_encontrado['parejas']):
        grupo_encontrado['parejas'].insert(slot_destino, pareja_a_asignar)
    else:
        grupo_encontrado['parejas'].append(pareja_a_asignar)
    
    # Recalcular score del grupo
    recalcular_score_grupo(grupo_encontrado)
    
    # Regenerar calendario completo
    regenerar_calendario(resultado_data)
    
    # Recalcular estadísticas globales
    estadisticas = recalcular_estadisticas(resultado_data)
    
    # Actualizar datos
    datos_actuales = obtener_datos_desde_token()
    datos_actuales['resultado_algoritmo'] = resultado_data
    sincronizar_con_storage_y_token(datos_actuales)
    guardar_estado_torneo()  # Auto-guardar
    
    return crear_respuesta_con_token_actualizado({
        'success': True,
        'mensaje': f'✓ Pareja asignada al grupo correctamente',
        'estadisticas': estadisticas
    }, datos_actuales)


@api_bp.route('/franjas-disponibles', methods=['GET'])
def obtener_franjas_disponibles():
    """Obtiene las franjas disponibles para cada cancha."""
    from config.settings import FRANJAS_HORARIAS
    
    resultado_data = obtener_datos_desde_token().get('resultado_algoritmo')
    if not resultado_data:
        return jsonify({'error': 'No hay resultados del algoritmo'}), 404
    
    grupos_dict = resultado_data['grupos_por_categoria']
    num_canchas = obtener_datos_desde_token().get('num_canchas', 2)
    
    # Mapeo de franjas a horas que ocupan (incluye día para detectar solapamientos correctamente)
    franjas_a_horas_mapa = {
        'Jueves 18:00': ['Jueves 18:00', 'Jueves 19:00', 'Jueves 20:00'],
        'Jueves 20:00': ['Jueves 20:00', 'Jueves 21:00', 'Jueves 22:00'],
        'Viernes 18:00': ['Viernes 18:00', 'Viernes 19:00', 'Viernes 20:00'],
        'Viernes 21:00': ['Viernes 21:00', 'Viernes 22:00', 'Viernes 23:00'],
        'Sábado 09:00': ['Sábado 09:00', 'Sábado 10:00', 'Sábado 11:00'],
        'Sábado 12:00': ['Sábado 12:00', 'Sábado 13:00', 'Sábado 14:00'],
        'Sábado 16:00': ['Sábado 16:00', 'Sábado 17:00', 'Sábado 18:00'],
        'Sábado 19:00': ['Sábado 19:00', 'Sábado 20:00', 'Sábado 21:00'],
    }
    
    # Crear un diccionario de franjas ocupadas por cancha con info detallada
    franjas_ocupadas = {}
    for cat, grupos in grupos_dict.items():
        for grupo in grupos:
            franja = grupo.get('franja_horaria')
            cancha = str(grupo.get('cancha'))
            if franja and cancha:
                if franja not in franjas_ocupadas:
                    franjas_ocupadas[franja] = {}
                franjas_ocupadas[franja][cancha] = cat
    
    # Construir la respuesta con disponibilidad por franja y cancha
    disponibilidad = {}
    for franja in FRANJAS_HORARIAS:
        disponibilidad[franja] = {}
        for cancha_num in range(1, num_canchas + 1):
            cancha_str = str(cancha_num)
            
            # Verificar si está ocupada directamente
            ocupada_directa = franja in franjas_ocupadas and cancha_str in franjas_ocupadas[franja]
            categoria_ocupante = franjas_ocupadas.get(franja, {}).get(cancha_str)
            
            # Verificar solapamientos (especialmente Jueves 18:00 y 20:00)
            solapamiento = None
            horas_franja = franjas_a_horas_mapa.get(franja, [])
            
            for otra_franja, cat_por_cancha in franjas_ocupadas.items():
                if otra_franja != franja and cancha_str in cat_por_cancha:
                    horas_otra = franjas_a_horas_mapa.get(otra_franja, [])
                    horas_comunes = set(horas_franja) & set(horas_otra)
                    if horas_comunes:
                        solapamiento = {
                            'franja': otra_franja,
                            'categoria': cat_por_cancha[cancha_str],
                            'horas_conflicto': sorted(list(horas_comunes))
                        }
                        break
            
            disponibilidad[franja][cancha_str] = {
                'disponible': not ocupada_directa,
                'ocupada_por': categoria_ocupante,
                'solapamiento': solapamiento
            }
    
    return jsonify({
        'success': True,
        'disponibilidad': disponibilidad,
        'num_canchas': num_canchas
    })


@api_bp.route('/crear-grupo-manual', methods=['POST'])
def crear_grupo_manual():
    """Crea un nuevo grupo manualmente para una categoría."""
    data = request.json
    categoria = data.get('categoria')
    franja_horaria = data.get('franja_horaria')
    cancha = data.get('cancha')
    
    if not all([categoria, franja_horaria, cancha]):
        return jsonify({'error': 'Faltan parámetros requeridos'}), 400
    
    resultado_data = obtener_datos_desde_token().get('resultado_algoritmo')
    if not resultado_data:
        return jsonify({'error': 'No hay resultados del algoritmo'}), 404
    
    grupos_dict = resultado_data['grupos_por_categoria']
    
    # Mapeo de franjas a horas (incluye día para detectar solapamientos correctamente)
    franjas_a_horas_mapa = {
        'Jueves 18:00': ['Jueves 18:00', 'Jueves 19:00', 'Jueves 20:00'],
        'Jueves 20:00': ['Jueves 20:00', 'Jueves 21:00', 'Jueves 22:00'],
        'Viernes 18:00': ['Viernes 18:00', 'Viernes 19:00', 'Viernes 20:00'],
        'Viernes 21:00': ['Viernes 21:00', 'Viernes 22:00', 'Viernes 23:00'],
        'Sábado 09:00': ['Sábado 09:00', 'Sábado 10:00', 'Sábado 11:00'],
        'Sábado 12:00': ['Sábado 12:00', 'Sábado 13:00', 'Sábado 14:00'],
        'Sábado 16:00': ['Sábado 16:00', 'Sábado 17:00', 'Sábado 18:00'],
        'Sábado 19:00': ['Sábado 19:00', 'Sábado 20:00', 'Sábado 21:00'],
    }
    
    # Validar que la cancha no esté ocupada directamente
    for cat, grupos in grupos_dict.items():
        for grupo in grupos:
            if grupo.get('franja_horaria') == franja_horaria and str(grupo.get('cancha')) == str(cancha):
                return jsonify({
                    'error': f'La Cancha {cancha} ya está ocupada en {franja_horaria} por un grupo de {cat}'
                }), 400
    
    # Validar solapamientos horarios
    horas_nueva_franja = franjas_a_horas_mapa.get(franja_horaria, [])
    for cat, grupos in grupos_dict.items():
        for grupo in grupos:
            if str(grupo.get('cancha')) == str(cancha):
                franja_existente = grupo.get('franja_horaria')
                horas_existente = franjas_a_horas_mapa.get(franja_existente, [])
                horas_conflicto = set(horas_nueva_franja) & set(horas_existente)
                
                if horas_conflicto:
                    return jsonify({
                        'error': f'Conflicto: La Cancha {cancha} tiene un solapamiento horario con {franja_existente} (grupo de {cat}) en las horas: {", ".join(sorted(horas_conflicto))}'
                    }), 400
    
    # Asegurar que existe la categoría
    if categoria not in grupos_dict:
        grupos_dict[categoria] = []
    
    # Generar nuevo ID único para el grupo
    max_id = 0
    for cat_grupos in grupos_dict.values():
        for grupo in cat_grupos:
            if grupo.get('id', 0) > max_id:
                max_id = grupo['id']
    
    nuevo_id = max_id + 1
    
    # Crear el nuevo grupo con todos los atributos necesarios
    nuevo_grupo = {
        'id': nuevo_id,
        'franja_horaria': franja_horaria,
        'cancha': cancha,
        'score': 0.0,  # Score de calidad del grupo
        'score_compatibilidad': 0.0,
        'parejas': [],
        'partidos': [],
        'resultados': {},  # Inicializar diccionario de resultados vacío
        'resultados_completos': False
    }
    
    grupos_dict[categoria].append(nuevo_grupo)
    
    # Regenerar calendario completo
    regenerar_calendario(resultado_data)
    
    # Actualizar datos
    datos_actuales = obtener_datos_desde_token()
    datos_actuales['resultado_algoritmo'] = resultado_data
    sincronizar_con_storage_y_token(datos_actuales)
    guardar_estado_torneo()  # Auto-guardar
    
    return crear_respuesta_con_token_actualizado({
        'success': True,
        'mensaje': '✓ Grupo creado correctamente',
        'grupo': nuevo_grupo
    }, datos_actuales)


@api_bp.route('/editar-grupo', methods=['POST'])
def editar_grupo():
    """Edita la franja horaria y cancha de un grupo."""
    data = request.json
    grupo_id = data.get('grupo_id')
    categoria = data.get('categoria')
    franja_horaria = data.get('franja_horaria')
    cancha = data.get('cancha')
    
    if not all([grupo_id, categoria, franja_horaria, cancha]):
        return jsonify({'error': 'Faltan parámetros requeridos'}), 400
    
    resultado_data = obtener_datos_desde_token().get('resultado_algoritmo')
    if not resultado_data:
        return jsonify({'error': 'No hay resultados del algoritmo'}), 404
    
    grupos_dict = resultado_data['grupos_por_categoria']
    
    # Buscar el grupo
    grupo_encontrado = None
    for grupo in grupos_dict.get(categoria, []):
        if grupo['id'] == grupo_id:
            grupo_encontrado = grupo
            break
    
    if not grupo_encontrado:
        return jsonify({'error': 'Grupo no encontrado'}), 404
    
    # Validar que la combinación franja + cancha esté disponible
    # (no debe estar ocupada por otro grupo)
    for cat, grupos in grupos_dict.items():
        for grupo in grupos:
            # Saltar el grupo que estamos editando
            if grupo['id'] == grupo_id:
                continue
            
            # Verificar si ya existe un grupo con la misma franja y cancha
            if grupo.get('franja_horaria') == franja_horaria and str(grupo.get('cancha')) == str(cancha):
                return jsonify({
                    'error': f'La Cancha {cancha} ya está ocupada en {franja_horaria} por otro grupo ({cat})'
                }), 400
    
    # Actualizar datos del grupo
    grupo_encontrado['franja_horaria'] = franja_horaria
    grupo_encontrado['cancha'] = cancha
    
    # Recalcular score de compatibilidad del grupo
    recalcular_score_grupo(grupo_encontrado)
    
    # Regenerar calendario completo
    regenerar_calendario(resultado_data)
    
    # Actualizar datos
    datos_actuales = obtener_datos_desde_token()
    datos_actuales['resultado_algoritmo'] = resultado_data
    sincronizar_con_storage_y_token(datos_actuales)
    guardar_estado_torneo()  # Auto-guardar
    
    return crear_respuesta_con_token_actualizado({
        'success': True,
        'mensaje': '✓ Grupo actualizado correctamente'
    }, datos_actuales)


@api_bp.route('/editar-pareja', methods=['POST'])
def editar_pareja():
    """Edita los datos de una pareja (nombre, teléfono, categoría, franjas)."""
    data = request.json
    pareja_id = data.get('pareja_id')
    nombre = data.get('nombre')
    telefono = data.get('telefono')
    categoria = data.get('categoria')
    franjas = data.get('franjas', [])
    
    if not all([pareja_id, nombre, categoria]):
        return jsonify({'error': 'Faltan parámetros requeridos'}), 400
    
    if not franjas or len(franjas) == 0:
        return jsonify({'error': 'Debes seleccionar al menos una franja horaria'}), 400
    
    datos_actuales = obtener_datos_desde_token()
    resultado_data = datos_actuales.get('resultado_algoritmo')
    if not resultado_data:
        return jsonify({'error': 'No hay resultados del algoritmo'}), 404
    
    grupos_dict = resultado_data['grupos_por_categoria']
    parejas_sin_asignar = resultado_data.get('parejas_sin_asignar', [])
    
    # Buscar la pareja en grupos o en no asignadas
    pareja_encontrada = None
    grupo_contenedor = None
    categoria_original = None
    en_no_asignadas = False
    
    # Buscar en grupos
    for cat, grupos in grupos_dict.items():
        for grupo in grupos:
            for pareja in grupo.get('parejas', []):
                if pareja.get('id') == pareja_id:
                    pareja_encontrada = pareja
                    grupo_contenedor = grupo
                    categoria_original = cat
                    break
            if pareja_encontrada:
                break
        if pareja_encontrada:
            break
    
    # Si no está en grupos, buscar en no asignadas
    if not pareja_encontrada:
        for pareja in parejas_sin_asignar:
            if pareja.get('id') == pareja_id:
                pareja_encontrada = pareja
                categoria_original = pareja.get('categoria')
                en_no_asignadas = True
                break
    
    if not pareja_encontrada:
        return jsonify({'error': 'Pareja no encontrada'}), 404
    
    # Si cambió de categoría, mover a parejas no asignadas de la nueva categoría
    cambio_categoria = categoria != categoria_original
    
    if cambio_categoria and grupo_contenedor:
        # Remover del grupo actual
        grupo_contenedor['parejas'].remove(pareja_encontrada)
        # Recalcular score del grupo afectado
        recalcular_score_grupo(grupo_contenedor)
        # Actualizar categoría
        pareja_encontrada['categoria'] = categoria
        # Agregar a no asignadas
        parejas_sin_asignar.append(pareja_encontrada)
    
    # Actualizar datos de la pareja
    pareja_encontrada['nombre'] = nombre
    pareja_encontrada['telefono'] = telefono
    pareja_encontrada['categoria'] = categoria
    pareja_encontrada['franjas_disponibles'] = franjas
    
    # IMPORTANTE: También actualizar en la lista base de parejas
    parejas_base = datos_actuales.get('parejas', [])
    pareja_actualizada_en_base = False
    for pareja_base in parejas_base:
        if pareja_base['id'] == pareja_id:
            pareja_base['nombre'] = nombre
            pareja_base['telefono'] = telefono
            pareja_base['categoria'] = categoria
            pareja_base['franjas_disponibles'] = franjas
            pareja_actualizada_en_base = True
            break
    
    # Si no existe en la lista base, agregarla (prevenir inconsistencias)
    if not pareja_actualizada_en_base:
        parejas_base.append({
            'id': pareja_id,
            'nombre': nombre,
            'telefono': telefono,
            'categoria': categoria,
            'franjas_disponibles': franjas
        })
    
    datos_actuales['parejas'] = parejas_base
    
    # Si la pareja está en un grupo y cambiaron las franjas, recalcular score
    if grupo_contenedor and not cambio_categoria:
        recalcular_score_grupo(grupo_contenedor)
    
    # Regenerar calendario completo
    regenerar_calendario(resultado_data)
    
    # Actualizar datos
    datos_actuales['resultado_algoritmo'] = resultado_data
    sincronizar_con_storage_y_token(datos_actuales)
    guardar_estado_torneo()  # Auto-guardar
    
    mensaje = '✓ Pareja actualizada correctamente'
    if cambio_categoria:
        mensaje += ' (movida a parejas no asignadas por cambio de categoría)'
    
    return crear_respuesta_con_token_actualizado({
        'success': True,
        'mensaje': mensaje
    }, datos_actuales)


def deserializar_resultado(resultado_data):
    """Reconstruye el objeto ResultadoAlgoritmo desde datos de sesión."""
    grupos_por_categoria = {}
    
    for categoria, grupos_list in resultado_data['grupos_por_categoria'].items():
        grupos_por_categoria[categoria] = []
        for grupo_dict in grupos_list:
            grupo = Grupo(
                id=grupo_dict['id'],
                categoria=categoria
            )
            grupo.franja_horaria = grupo_dict.get('franja_horaria')
            grupo.score_compatibilidad = grupo_dict.get('score', 0.0)
            
            # Cargar resultados guardados — reconstruir como objetos ResultadoPartido
            from core.models import ResultadoPartido
            resultados_raw = grupo_dict.get('resultados', {})
            for key, r_data in resultados_raw.items():
                if isinstance(r_data, dict):
                    grupo.resultados[key] = ResultadoPartido.from_dict(r_data)
                else:
                    grupo.resultados[key] = r_data
            grupo.resultados_completos = grupo_dict.get('resultados_completos', False)
            
            for pareja_dict in grupo_dict['parejas']:
                pareja = Pareja(
                    id=pareja_dict['id'],
                    nombre=pareja_dict['nombre'],
                    telefono=pareja_dict.get('telefono', 'Sin teléfono'),
                    categoria=pareja_dict['categoria'],
                    franjas_disponibles=pareja_dict.get('franjas_disponibles', [])
                )
                grupo.parejas.append(pareja)
            
            grupo.generar_partidos()
            grupos_por_categoria[categoria].append(grupo)
    
    parejas_sin_asignar = []
    for p in resultado_data.get('parejas_sin_asignar', []):
        pareja = Pareja(
            id=p['id'],
            nombre=p['nombre'],
            telefono=p.get('telefono', 'Sin teléfono'),
            categoria=p['categoria'],
            franjas_disponibles=p.get('franjas_disponibles', [])
        )
        parejas_sin_asignar.append(pareja)
    
    resultado = ResultadoAlgoritmo(
        grupos_por_categoria=grupos_por_categoria,
        parejas_sin_asignar=parejas_sin_asignar,
        calendario=resultado_data.get('calendario', {}),
        estadisticas=resultado_data.get('estadisticas', {})
    )
    
    return resultado


@api_bp.route('/asignar-posicion', methods=['POST'])
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
        
        # Buscar la pareja en los grupos de la categoría
        grupos_categoria = resultado_data['grupos_por_categoria'].get(categoria, [])
        pareja_encontrada = False
        grupo_id = None
        posicion_anterior = None
        
        for grupo in grupos_categoria:
            for pareja in grupo['parejas']:
                if pareja['id'] == pareja_id:
                    posicion_anterior = pareja.get('posicion_grupo')
                    # Si posicion es 0 o None, deseleccionar
                    if posicion == 0:
                        pareja['posicion_grupo'] = None
                    else:
                        pareja['posicion_grupo'] = posicion
                    pareja_encontrada = True
                    grupo_id = grupo['id']
                    break
            if pareja_encontrada:
                break
        
        if not pareja_encontrada:
            return jsonify({'error': 'Pareja no encontrada'}), 404
        
        # Guardar cambios en storage
        datos = obtener_datos_desde_token()
        datos['resultado_algoritmo'] = resultado_data
        sincronizar_con_storage_y_token(datos)
        
        # Verificar si ya se pueden generar las finales
        puede_generar = verificar_posiciones_completas(grupos_categoria)
        
        # REGENERAR FIXTURES cuando se asignan posiciones
        regenerar_fixtures_categoria(categoria, resultado_data)
        
        # Preparar mensaje según la acción
        if posicion == 0:
            mensaje = ''
        else:
            mensaje = f'✓ Posición {posicion}°'
        
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


# ==================== ENDPOINTS PARA RESULTADOS DE PARTIDOS ====================

@api_bp.route('/guardar-resultado-partido', methods=['POST'])
def guardar_resultado_partido():
    """Guarda o actualiza el resultado de un partido de grupo"""
    from core.models import ResultadoPartido
    from core.clasificacion import CalculadorClasificacion
    
    data = request.json
    categoria = data.get('categoria')
    grupo_id = data.get('grupo_id')
    pareja1_id = data.get('pareja1_id')
    pareja2_id = data.get('pareja2_id')
    
    # Datos del resultado
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
        
        # Buscar el grupo
        grupos_categoria = resultado_data['grupos_por_categoria'].get(categoria, [])
        grupo_encontrado = None
        
        for grupo in grupos_categoria:
            if grupo['id'] == grupo_id:
                grupo_encontrado = grupo
                break
        
        if not grupo_encontrado:
            return jsonify({'error': 'Grupo no encontrado'}), 404
        
        # Calcular sets ganados
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
        
        # Crear objeto resultado
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
        
        # Guardar resultado en el grupo
        if 'resultados' not in grupo_encontrado:
            grupo_encontrado['resultados'] = {}
        
        ids_ordenados = sorted([pareja1_id, pareja2_id])
        key = f"{ids_ordenados[0]}-{ids_ordenados[1]}"
        grupo_encontrado['resultados'][key] = resultado_dict
        
        # Verificar si todos los resultados están completos
        grupo_encontrado['resultados_completos'] = False
        if len(grupo_encontrado.get('parejas', [])) == 3:
            resultados = grupo_encontrado.get('resultados', {})
            resultados_completos = sum(
                1 for r in resultados.values() 
                if ResultadoPartido.from_dict(r).esta_completo()
            )
            grupo_encontrado['resultados_completos'] = (resultados_completos == 3)
        
        # Si todos los resultados están completos, calcular posiciones automáticamente
        if grupo_encontrado.get('resultados_completos', False):
            # Reconstruir objeto Grupo para usar el calculador
            grupo_obj = Grupo(
                id=grupo_encontrado['id'],
                categoria=categoria,
                franja_horaria=grupo_encontrado.get('franja_horaria')
            )
            
            # Agregar parejas
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
            
            # Agregar resultados
            for key, resultado_dict in grupo_encontrado['resultados'].items():
                grupo_obj.resultados[key] = ResultadoPartido.from_dict(resultado_dict)
            
            # Calcular posiciones
            posiciones = CalculadorClasificacion.asignar_posiciones(grupo_obj)
            
            # Asignar posiciones a las parejas
            for pareja_dict in grupo_encontrado['parejas']:
                pareja_id = pareja_dict['id']
                if pareja_id in posiciones:
                    pareja_dict['posicion_grupo'] = posiciones[pareja_id].value
        
        # Guardar en storage
        datos = obtener_datos_desde_token()
        datos['resultado_algoritmo'] = resultado_data
        
        # Si los resultados del grupo están completos, regenerar fixtures de finales
        if grupo_encontrado.get('resultados_completos', False):
            from core.fixture_finales_generator import GeneradorFixtureFinales
            try:
                # Obtener todos los grupos de la categoría
                grupos_data = resultado_data['grupos_por_categoria'].get(categoria, [])
                grupos_obj = [Grupo.from_dict(g) for g in grupos_data]
                
                # Regenerar fixture para esta categoría
                fixture = GeneradorFixtureFinales.generar_fixture(categoria, grupos_obj)
                
                if fixture:
                    # Actualizar fixtures guardados
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


@api_bp.route('/obtener-tabla-posiciones/<categoria>/<int:grupo_id>', methods=['GET'])
def obtener_tabla_posiciones(categoria, grupo_id):
    """Obtiene la tabla de posiciones de un grupo"""
    from core.models import ResultadoPartido
    from core.clasificacion import CalculadorClasificacion
    
    try:
        resultado_data = obtener_datos_desde_token().get('resultado_algoritmo')
        if not resultado_data:
            return jsonify({'error': 'No hay resultados cargados'}), 400
        
        # Buscar el grupo
        grupos_categoria = resultado_data['grupos_por_categoria'].get(categoria, [])
        grupo_encontrado = None
        
        for grupo in grupos_categoria:
            if grupo['id'] == grupo_id:
                grupo_encontrado = grupo
                break
        
        if not grupo_encontrado:
            return jsonify({'error': 'Grupo no encontrado'}), 404
        
        # Reconstruir objeto Grupo
        grupo_obj = Grupo(
            id=grupo_encontrado['id'],
            categoria=categoria,
            franja_horaria=grupo_encontrado.get('franja_horaria')
        )
        
        # Agregar parejas
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
        
        # Agregar resultados
        resultados_dict = grupo_encontrado.get('resultados', {})
        for key, resultado_dict in resultados_dict.items():
            grupo_obj.resultados[key] = ResultadoPartido.from_dict(resultado_dict)
        
        # Calcular tabla de posiciones
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


@api_bp.route('/generar-fixture/<categoria>', methods=['POST'])
def generar_fixture(categoria):
    """Genera el fixture de finales para una categoría."""
    try:
        resultado_data = obtener_datos_desde_token().get('resultado_algoritmo')
        if not resultado_data:
            return jsonify({'error': 'No hay resultados cargados'}), 400
        
        # Reconstruir grupos con posiciones
        grupos_data = resultado_data['grupos_por_categoria'].get(categoria, [])
        if not grupos_data:
            return jsonify({'error': f'No hay grupos en categoría {categoria}'}), 404
        
        # Reconstruir objetos Grupo
        grupos_obj = []
        for grupo_dict in grupos_data:
            grupo = Grupo(
                id=grupo_dict['id'],
                categoria=categoria,
                franja_horaria=grupo_dict.get('franja_horaria'),
                score_compatibilidad=grupo_dict.get('score', 0.0)
            )
            
            # Reconstruir parejas con posiciones
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
        
        # Generar fixture
        generator = FixtureGenerator(grupos_obj)
        fixture = generator.generar_fixture()
        
        # Guardar fixture en storage (no en session)
        torneo = storage.cargar()
        if 'fixtures' not in torneo:
            torneo['fixtures'] = {}
        torneo['fixtures'][categoria] = fixture.to_dict()
        storage.guardar(torneo)
        guardar_estado_torneo()  # Auto-guardar
        
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


@api_bp.route('/obtener-fixture/<categoria>', methods=['GET'])
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


@api_bp.route('/marcar-ganador', methods=['POST'])
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
        
        # Reconstruir objetos para usar el método de actualización
        resultado_data = obtener_datos_desde_token().get('resultado_algoritmo')
        grupos_data = resultado_data['grupos_por_categoria'].get(categoria, [])
        
        # Reconstruir grupos
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
        
        # CRUCIAL: Reconstruir el fixture DESDE LOS DATOS GUARDADOS, no generar uno nuevo
        # Esto preserva todos los ganadores anteriores
        fixture = FixtureFinales.from_dict(fixture_data, grupos_obj)
        
        # Actualizar con el ganador NUEVO
        fixture = FixtureGenerator.actualizar_fixture_con_ganador(
            fixture,
            partido_id,
            ganador_id
        )
        
        # Guardar en storage
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


@api_bp.route('/calendario-finales', methods=['GET'])
def obtener_calendario_finales():
    """Obtiene el calendario de finales del domingo con los partidos asignados."""
    try:
        fixtures = storage.cargar().get('fixtures', {})
        
        if not fixtures:
            # Si no hay fixtures, devolver calendario vacío con estructura
            calendario_base = CalendarioFinalesBuilder.generar_calendario_base()
            return jsonify({
                'success': True,
                'calendario': calendario_base,
                'tiene_datos': False
            })
        
        # Poblar calendario con los fixtures actuales
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


def verificar_posiciones_completas(grupos: list) -> bool:
    """Verifica si todas las parejas tienen posiciones asignadas."""
    for grupo in grupos:
        for pareja in grupo['parejas']:
            if not pareja.get('posicion_grupo'):
                return False
    return True


# ==========================================
# ENDPOINTS PARA ACTUALIZACIÓN SELECTIVA
# ==========================================

@api_bp.route('/estadisticas', methods=['GET'])
def obtener_estadisticas():
    """Obtiene las estadísticas actualizadas del torneo."""
    resultado_data = obtener_datos_desde_token().get('resultado_algoritmo')
    if not resultado_data:
        return jsonify({'error': 'No hay resultados disponibles'}), 404
    
    # Recalcular estadísticas para asegurar que están actualizadas
    estadisticas = recalcular_estadisticas(resultado_data)
    
    return jsonify({
        'success': True,
        'estadisticas': estadisticas
    })


@api_bp.route('/obtener-categoria/<categoria>', methods=['GET'])
def obtener_categoria(categoria):
    """Devuelve solo el HTML de una categoría específica para actualización parcial."""
    from flask import render_template_string
    
    resultado_dict = obtener_datos_desde_token().get('resultado_algoritmo')
    if not resultado_dict:
        return jsonify({'error': 'No hay resultados disponibles'}), 404
    
    # Verificar que la categoría existe
    if categoria not in resultado_dict.get('grupos_por_categoria', {}):
        return jsonify({'error': f'Categoría {categoria} no encontrada'}), 404
    
    # Devolver datos de la categoría
    return jsonify({
        'success': True,
        'categoria': categoria,
        'grupos': resultado_dict['grupos_por_categoria'][categoria],
        'parejas_sin_asignar': [p for p in resultado_dict.get('parejas_sin_asignar', []) if p.get('categoria') == categoria]
    })


@api_bp.route('/obtener-grupo/<categoria>/<int:grupo_id>', methods=['GET'])
def obtener_grupo(categoria, grupo_id):
    """Devuelve el HTML de un grupo específico."""
    resultado_dict = obtener_datos_desde_token().get('resultado_algoritmo')
    if not resultado_dict:
        return jsonify({'error': 'No hay resultados disponibles'}), 404
    
    grupos = resultado_dict.get('grupos_por_categoria', {}).get(categoria, [])
    
    # Buscar el grupo
    grupo = next((g for g in grupos if g['id'] == grupo_id), None)
    
    if not grupo:
        return jsonify({'error': 'Grupo no encontrado'}), 404
    
    return jsonify({
        'success': True,
        'grupo': grupo
    })


@api_bp.route('/obtener-no-asignadas/<categoria>', methods=['GET'])
def obtener_no_asignadas(categoria):
    """Devuelve las parejas no asignadas de una categoría."""
    resultado_dict = obtener_datos_desde_token().get('resultado_algoritmo')
    if not resultado_dict:
        return jsonify({'error': 'No hay resultados disponibles'}), 404
    
    parejas_sin_asignar = resultado_dict.get('parejas_sin_asignar', [])
    parejas_categoria = [p for p in parejas_sin_asignar if p.get('categoria') == categoria]
    
    return jsonify({
        'success': True,
        'categoria': categoria,
        'parejas': parejas_categoria
    })


@api_bp.route('/obtener-datos-categoria/<categoria>', methods=['GET'])
def obtener_datos_categoria(categoria):
    """Devuelve todos los datos actualizados de una categoría para actualización dinámica."""
    resultado_dict = obtener_datos_desde_token().get('resultado_algoritmo')
    if not resultado_dict:
        return jsonify({'error': 'No hay resultados disponibles'}), 404
    
    # Obtener grupos de la categoría
    grupos = resultado_dict.get('grupos_por_categoria', {}).get(categoria, [])
    
    # Obtener parejas no asignadas
    parejas_sin_asignar = resultado_dict.get('parejas_sin_asignar', [])
    parejas_no_asignadas = [p for p in parejas_sin_asignar if p.get('categoria') == categoria]
    
    # Obtener partidos de esta categoría
    partidos_por_grupo = resultado_dict.get('partidos_por_grupo', {})
    partidos_categoria = {}
    for grupo in grupos:
        grupo_id = str(grupo.get('id'))
        if grupo_id in partidos_por_grupo:
            partidos_categoria[grupo_id] = partidos_por_grupo[grupo_id]
    
    return jsonify({
        'success': True,
        'categoria': categoria,
        'grupos': grupos,
        'parejas_no_asignadas': parejas_no_asignadas,
        'partidos': partidos_categoria
    })


@api_bp.route('/obtener-calendario', methods=['GET'])
def obtener_calendario():
    """Devuelve el calendario general actualizado."""
    resultado_dict = obtener_datos_desde_token().get('resultado_algoritmo')
    if not resultado_dict:
        return jsonify({'error': 'No hay resultados disponibles'}), 404
    
    calendario = resultado_dict.get('calendario', {})
    
    return jsonify({
        'success': True,
        'calendario': calendario
    })
