from flask import Blueprint, request, jsonify
import pandas as pd
import logging

from core import Pareja
from utils import CSVProcessor
from utils.torneo_storage import storage, ConflictError
from utils.api_helpers import (
    obtener_datos_desde_token,
    crear_respuesta_con_token_actualizado,
    sincronizar_con_storage_y_token,
    verificar_autenticacion_api,
)
from config import NUM_CANCHAS_DEFAULT, FRANJAS_A_HORAS_MAP
from utils.input_validation import validar_longitud, MAX_NOMBRE, MAX_TELEFONO
from ._helpers import (
    recalcular_estadisticas,
    recalcular_score_grupo,
    regenerar_calendario,
)

api_bp = Blueprint("api", __name__, url_prefix="/api")
logger = logging.getLogger(__name__)


@api_bp.before_request
def verificar_auth():
    authenticated, error_response = verificar_autenticacion_api(roles_permitidos=["admin"])
    if not authenticated:
        return error_response


@api_bp.route("/cargar-csv", methods=["POST"])
def cargar_csv():
    if "archivo" not in request.files:
        return jsonify({"error": "No se envio ningun archivo"}), 400
    file = request.files["archivo"]
    if file.filename == "" or not CSVProcessor.validar_archivo(file.filename):
        return jsonify({"error": "Archivo invalido"}), 400
    try:
        df = pd.read_csv(file)
        parejas = CSVProcessor.procesar_dataframe(df)
        datos_token = {"parejas": parejas, "resultado_algoritmo": None, "num_canchas": NUM_CANCHAS_DEFAULT}
        sincronizar_con_storage_y_token(datos_token)
        return crear_respuesta_con_token_actualizado(
            {"success": True, "mensaje": f"{len(parejas)} parejas cargadas", "parejas": parejas},
            datos_token,
        )
    except Exception as e:
        logger.error("Error al procesar CSV: %s", e, exc_info=True)
        return jsonify({"error": "Error al procesar el archivo CSV"}), 500


@api_bp.route("/agregar-pareja", methods=["POST"])
def agregar_pareja():
    try:
        data = request.json
        jugador1 = data.get("jugador1", "").strip()
        jugador2 = data.get("jugador2", "").strip()
        nombre = data.get("nombre", "").strip()
        telefono = data.get("telefono", "").strip()
        categoria = data.get("categoria", "Cuarta")
        franjas = data.get("franjas", [])
        desde_resultados = data.get("desde_resultados", False)

        if jugador1 and jugador2:
            nombre = f"{jugador1} / {jugador2}"
        elif jugador1 and not nombre:
            nombre = jugador1

        if not nombre:
            return jsonify({"error": "El nombre es obligatorio"}), 400
        if not franjas:
            return jsonify({"error": "Selecciona al menos una franja horaria"}), 400

        error_len = validar_longitud({
            'Nombre':   (nombre, MAX_NOMBRE),
            'Teléfono': (telefono, MAX_TELEFONO),
        })
        if error_len:
            return jsonify({"error": error_len}), 400

        datos_actuales = obtener_datos_desde_token()
        parejas = datos_actuales.get("parejas", [])
        max_id = max([p["id"] for p in parejas], default=0)
        nueva_pareja = {
            "categoria": categoria,
            "franjas_disponibles": franjas,
            "id": max_id + 1,
            "nombre": nombre,
            "jugador1": jugador1 or nombre,
            "jugador2": jugador2,
            "telefono": telefono or "Sin telefono",
            "origen": "manual",
        }
        parejas.append(nueva_pareja)
        datos_actuales["parejas"] = parejas

        estadisticas = None
        if desde_resultados:
            resultado_data = datos_actuales.get("resultado_algoritmo")
            if resultado_data:
                resultado_data.get("parejas_sin_asignar", []).append(nueva_pareja)
                estadisticas = recalcular_estadisticas(resultado_data)
                datos_actuales["resultado_algoritmo"] = resultado_data

        sincronizar_con_storage_y_token(datos_actuales)
        response_data = {
            "success": True,
            "mensaje": f"Pareja agregada",
            "pareja": nueva_pareja,
            "desde_resultados": desde_resultados,
        }
        if desde_resultados and estadisticas:
            response_data["estadisticas"] = estadisticas
        return crear_respuesta_con_token_actualizado(response_data, datos_actuales)
    except Exception as e:
        logger.error("Error al agregar pareja: %s", e, exc_info=True)
        return jsonify({"error": "Error al agregar la pareja"}), 500


@api_bp.route("/eliminar-pareja", methods=["POST"])
def eliminar_pareja():
    data = request.json
    pareja_id = data.get("id")
    datos_actuales = obtener_datos_desde_token()
    datos_actuales["parejas"] = [p for p in datos_actuales.get("parejas", []) if p["id"] != pareja_id]
    resultado_data = datos_actuales.get("resultado_algoritmo")
    if resultado_data:
        for cat, grupos in resultado_data["grupos_por_categoria"].items():
            for grupo in grupos:
                prev = len(grupo.get("parejas", []))
                grupo["parejas"] = [p for p in grupo["parejas"] if p.get("id") != pareja_id]
                if len(grupo["parejas"]) != prev:
                    recalcular_score_grupo(grupo)
        resultado_data["parejas_sin_asignar"] = [
            p for p in resultado_data.get("parejas_sin_asignar", []) if p.get("id") != pareja_id
        ]
        regenerar_calendario(resultado_data)
        resultado_data["estadisticas"] = recalcular_estadisticas(resultado_data)
        datos_actuales["resultado_algoritmo"] = resultado_data
    sincronizar_con_storage_y_token(datos_actuales)
    return crear_respuesta_con_token_actualizado(
        {"success": True, "mensaje": "Pareja eliminada correctamente"}, datos_actuales
    )


@api_bp.route("/remover-pareja-de-grupo", methods=["POST"])
def remover_pareja_de_grupo():
    data = request.json
    pareja_id = data.get("pareja_id")
    if not pareja_id:
        return jsonify({"error": "Falta pareja_id"}), 400
    datos_actuales = obtener_datos_desde_token()
    resultado_data = datos_actuales.get("resultado_algoritmo")
    if not resultado_data:
        return jsonify({"error": "No hay resultados del algoritmo"}), 404
    grupos_dict = resultado_data["grupos_por_categoria"]
    parejas_sin_asignar = resultado_data.get("parejas_sin_asignar", [])
    pareja_encontrada = None
    grupo_contenedor = None
    for cat, grupos in grupos_dict.items():
        for grupo in grupos:
            for idx, pareja in enumerate(grupo.get("parejas", [])):
                if pareja.get("id") == pareja_id:
                    pareja_encontrada = grupo["parejas"].pop(idx)
                    grupo_contenedor = grupo
                    break
            if pareja_encontrada:
                break
        if pareja_encontrada:
            break
    if not pareja_encontrada:
        return jsonify({"error": "Pareja no encontrada en ningun grupo"}), 404
    pareja_encontrada["posicion_grupo"] = None
    parejas_sin_asignar.append(pareja_encontrada)
    recalcular_score_grupo(grupo_contenedor)
    regenerar_calendario(resultado_data)
    estadisticas = recalcular_estadisticas(resultado_data)
    datos_actuales["resultado_algoritmo"] = resultado_data
    sincronizar_con_storage_y_token(datos_actuales)
    return crear_respuesta_con_token_actualizado(
        {"success": True, "mensaje": "Pareja removida del grupo", "estadisticas": estadisticas}
    )


@api_bp.route("/obtener-parejas", methods=["GET"])
def obtener_parejas():
    datos_actuales = obtener_datos_desde_token()
    parejas = datos_actuales.get("parejas", [])
    resultado = datos_actuales.get("resultado_algoritmo")
    parejas_enriquecidas = []
    for pareja in parejas:
        info = pareja.copy()
        info.update({"grupo_asignado": None, "franja_asignada": None, "esta_asignada": False, "fuera_de_horario": False})
        if resultado:
            for cat, grupos in resultado.get("grupos_por_categoria", {}).items():
                for grupo in grupos:
                    for p in grupo.get("parejas", []):
                        if p["id"] == pareja["id"]:
                            info["grupo_asignado"] = grupo["id"]
                            info["franja_asignada"] = grupo.get("franja_horaria")
                            info["esta_asignada"] = True
                            if grupo.get("franja_horaria") and grupo["franja_horaria"] not in pareja.get("franjas_disponibles", []):
                                info["fuera_de_horario"] = True
                            break
                    if info["esta_asignada"]:
                        break
                if info["esta_asignada"]:
                    break
        parejas_enriquecidas.append(info)
    cats = ["Cuarta", "Quinta", "Sexta", "Séptima", "Tercera"]
    stats = {
        "total": len(parejas),
        "por_categoria": {c: sum(1 for p in parejas if p.get("categoria") == c) for c in cats},
    }
    return jsonify({"success": True, "parejas": parejas_enriquecidas, "stats": stats})


@api_bp.route("/parejas-no-asignadas/<categoria>", methods=["GET"])
def obtener_parejas_no_asignadas(categoria):
    resultado_data = obtener_datos_desde_token().get("resultado_algoritmo")
    if not resultado_data:
        return jsonify({"error": "No hay resultados del algoritmo"}), 404
    parejas = [p for p in resultado_data.get("parejas_sin_asignar", []) if p.get("categoria") == categoria]
    return jsonify({"success": True, "parejas": parejas, "total": len(parejas)})


@api_bp.route("/editar-pareja", methods=["POST"])
def editar_pareja():
    data = request.json
    pareja_id = data.get("pareja_id")
    nombre = data.get("nombre")
    telefono = data.get("telefono")
    categoria = data.get("categoria")
    franjas = data.get("franjas", [])
    if not all([pareja_id, nombre, categoria]):
        return jsonify({"error": "Faltan parametros requeridos"}), 400
    if not franjas:
        return jsonify({"error": "Debes seleccionar al menos una franja horaria"}), 400
    datos_actuales = obtener_datos_desde_token()
    resultado_data = datos_actuales.get("resultado_algoritmo")
    if not resultado_data:
        return jsonify({"error": "No hay resultados del algoritmo"}), 404
    grupos_dict = resultado_data["grupos_por_categoria"]
    parejas_sin_asignar = resultado_data.get("parejas_sin_asignar", [])
    pareja_encontrada = None
    grupo_contenedor = None
    categoria_original = None
    for cat, grupos in grupos_dict.items():
        for grupo in grupos:
            for pareja in grupo.get("parejas", []):
                if pareja.get("id") == pareja_id:
                    pareja_encontrada = pareja
                    grupo_contenedor = grupo
                    categoria_original = cat
                    break
            if pareja_encontrada:
                break
        if pareja_encontrada:
            break
    if not pareja_encontrada:
        for pareja in parejas_sin_asignar:
            if pareja.get("id") == pareja_id:
                pareja_encontrada = pareja
                categoria_original = pareja.get("categoria")
                break
    if not pareja_encontrada:
        return jsonify({"error": "Pareja no encontrada"}), 404
    cambio_categoria = categoria != categoria_original
    if cambio_categoria and grupo_contenedor:
        grupo_contenedor["parejas"].remove(pareja_encontrada)
        recalcular_score_grupo(grupo_contenedor)
        pareja_encontrada["categoria"] = categoria
        parejas_sin_asignar.append(pareja_encontrada)
    pareja_encontrada.update({"nombre": nombre, "telefono": telefono, "categoria": categoria, "franjas_disponibles": franjas})
    parejas_base = datos_actuales.get("parejas", [])
    updated = False
    for pb in parejas_base:
        if pb["id"] == pareja_id:
            pb.update({"nombre": nombre, "telefono": telefono, "categoria": categoria, "franjas_disponibles": franjas})
            updated = True
            break
    if not updated:
        parejas_base.append({"id": pareja_id, "nombre": nombre, "telefono": telefono, "categoria": categoria, "franjas_disponibles": franjas})
    datos_actuales["parejas"] = parejas_base
    if grupo_contenedor and not cambio_categoria:
        recalcular_score_grupo(grupo_contenedor)
    regenerar_calendario(resultado_data)
    datos_actuales["resultado_algoritmo"] = resultado_data
    sincronizar_con_storage_y_token(datos_actuales)
    mensaje = "Pareja actualizada"
    if cambio_categoria:
        mensaje += " (movida a no asignadas por cambio de categoria)"
    return crear_respuesta_con_token_actualizado({"success": True, "mensaje": mensaje}, datos_actuales)


@api_bp.route("/franjas-disponibles", methods=["GET"])
def obtener_franjas_disponibles():
    from config.settings import FRANJAS_HORARIAS
    datos_actuales = obtener_datos_desde_token()
    resultado_data = datos_actuales.get("resultado_algoritmo")
    if not resultado_data:
        return jsonify({"error": "No hay resultados del algoritmo"}), 404
    grupos_dict = resultado_data["grupos_por_categoria"]
    num_canchas = datos_actuales.get("num_canchas", 2)
    franjas_ocupadas = {}
    for cat, grupos in grupos_dict.items():
        for grupo in grupos:
            franja = grupo.get("franja_horaria")
            cancha = str(grupo.get("cancha"))
            if franja and cancha:
                franjas_ocupadas.setdefault(franja, {})[cancha] = cat
    disponibilidad = {}
    for franja in FRANJAS_HORARIAS:
        disponibilidad[franja] = {}
        for cn in range(1, num_canchas + 1):
            cs = str(cn)
            ocupada = franja in franjas_ocupadas and cs in franjas_ocupadas[franja]
            solapamiento = None
            horas_f = FRANJAS_A_HORAS_MAP.get(franja, [])
            for otra, cat_cn in franjas_ocupadas.items():
                if otra != franja and cs in cat_cn:
                    horas_o = FRANJAS_A_HORAS_MAP.get(otra, [])
                    horas_c = set(horas_f) & set(horas_o)
                    if horas_c:
                        solapamiento = {"franja": otra, "categoria": cat_cn[cs], "horas_conflicto": sorted(horas_c)}
                        break
            disponibilidad[franja][cs] = {
                "disponible": not ocupada,
                "ocupada_por": franjas_ocupadas.get(franja, {}).get(cs),
                "solapamiento": solapamiento,
            }
    return jsonify({"success": True, "disponibilidad": disponibilidad, "num_canchas": num_canchas})


@api_bp.route("/limpiar-datos", methods=["POST"])
def limpiar_datos():
    try:
        torneo = storage.cargar()
        parejas_actuales = torneo.get('parejas', [])
        parejas_a_mantener = [p for p in parejas_actuales if p.get('inscripcion_id')]
        torneo['parejas'] = parejas_a_mantener
        torneo['resultado_algoritmo'] = None
        torneo['fixtures_finales'] = {}
        storage.guardar_con_version(torneo)
    except ConflictError as e:
        return jsonify({"error": str(e)}), 409
    datos_limpios = {"parejas": parejas_a_mantener, "resultado_algoritmo": None, "num_canchas": NUM_CANCHAS_DEFAULT}
    return crear_respuesta_con_token_actualizado({"success": True, "mensaje": "Datos CSV limpiados"}, datos_limpios)


@api_bp.route("/cambiar-tipo-torneo", methods=["POST"])
def cambiar_tipo_torneo():
    data = request.json or {}
    tipo = data.get("tipo_torneo", "fin1")
    if tipo not in ("fin1", "fin2"):
        return jsonify({"error": "Tipo de torneo invalido"}), 400
    try:
        storage.set_tipo_torneo(tipo)
    except ConflictError as e:
        return jsonify({"error": str(e)}), 409
    return jsonify({"success": True, "tipo_torneo": tipo})


@api_bp.route("/obtener-no-asignadas/<categoria>", methods=["GET"])
def obtener_no_asignadas(categoria):
    resultado_dict = obtener_datos_desde_token().get("resultado_algoritmo")
    if not resultado_dict:
        return jsonify({"error": "No hay resultados disponibles"}), 404
    parejas = [p for p in resultado_dict.get("parejas_sin_asignar", []) if p.get("categoria") == categoria]
    return jsonify({"success": True, "categoria": categoria, "parejas": parejas})
