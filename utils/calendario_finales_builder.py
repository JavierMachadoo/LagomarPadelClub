"""
Módulo para generar el calendario de finales del domingo.
Organiza todos los partidos de finales respetando las restricciones horarias.

Algoritmo principal: "Pipeline por categoría"
- Trabaja hacia atrás desde las 20:00 (hora de las finales)
- Cada categoría tiene su propio pipeline de fases que se ejecutan en orden
- Las categorías se interleavan en las 2 canchas disponibles
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


def _get_nombre(pareja: Optional[dict]) -> Optional[str]:
    """Extrae el nombre de una pareja serializada."""
    if not pareja:
        return None
    return pareja.get('nombre')


@dataclass
class BloqueHorario:
    """Representa un bloque horario disponible"""
    inicio: str  # formato "HH:MM"
    fin: str     # formato "HH:MM"
    cancha: int  # 1 o 2

    def duracion_minutos(self) -> int:
        h_inicio, m_inicio = map(int, self.inicio.split(':'))
        h_fin, m_fin = map(int, self.fin.split(':'))
        return (h_fin * 60 + m_fin) - (h_inicio * 60 + m_inicio)


@dataclass
class PartidoCalendarizado:
    """Representa un partido con su horario asignado"""
    partido_id: str
    categoria: str
    fase: str
    numero_partido: int
    pareja1: Optional[str]
    pareja2: Optional[str]
    hora_inicio: str
    hora_fin: str
    cancha: int

    def to_dict(self):
        return {
            'partido_id': self.partido_id,
            'categoria': self.categoria,
            'fase': self.fase,
            'numero_partido': self.numero_partido,
            'pareja1': self.pareja1,
            'pareja2': self.pareja2,
            'hora_inicio': self.hora_inicio,
            'hora_fin': self.hora_fin,
            'cancha': self.cancha
        }


class GeneradorCalendarioFinales:
    """
    Genera el calendario del domingo para todos los partidos de finales.

    Algoritmo principal: "Pipeline por categoría"
    - Cada categoría tiene un pipeline de fases (octavos → cuartos → semis → final)
    - Las finales se asignan a las 20:00 (o antes si hay más de 2 categorías)
    - Las fases anteriores se asignan hacia atrás desde la final de su categoría
    - Distintas categorías pueden interleavar en las 2 canchas disponibles
    """

    # Horario del domingo
    HORA_INICIO = 10  # primera franja: 10:00
    HORA_FIN = 22     # hasta 22:00 máximo

    # Orden de categorías: la peor categoría juega primero
    ORDEN_CATEGORIAS = ["Séptima", "Sexta", "Quinta", "Cuarta", "Tercera"]

    # Orden de fases en que se programan los partidos
    ORDEN_FASES_PROGRAMACION = ["octavos", "cuartos", "semifinales", "final"]

    # Nombres display de las fases (coinciden con FaseFinal.value)
    FASE_DISPLAY = {
        'octavos': 'Octavos de Final',
        'cuartos': 'Cuartos de Final',
        'semifinales': 'Semifinal',
        'final': 'Final'
    }

    # Para compatibilidad con código legacy que usa ORDEN_FASES
    ORDEN_FASES = {
        "Octavos de Final": 1,
        "Cuartos de Final": 2,
        "Semifinal": 3,
        "Final": 4
    }

    @staticmethod
    def _extraer_fases(fixture: dict) -> dict:
        """
        Extrae los partidos de un fixture agrupados por fase_key.
        Incluye partidos sin parejas (para mostrar 'Por definir').
        Excluye solo partidos placeholder vacíos (slot1_info == 'Vacío').

        Returns: {'octavos': [...], 'cuartos': [...], 'semifinales': [...], 'final': [...]}
        """
        def _es_valido(p):
            if not p or not p.get('id'):
                return False
            # Excluir placeholders vacíos del bracket viejo
            if p.get('slot1_info') == 'Vacío' and not p.get('pareja1') and not p.get('pareja2'):
                return False
            return True

        result = {}

        octavos = [p for p in fixture.get('octavos', []) if _es_valido(p)]
        if octavos:
            result['octavos'] = octavos

        cuartos = [p for p in fixture.get('cuartos', []) if _es_valido(p)]
        if cuartos:
            result['cuartos'] = cuartos

        semis = [p for p in fixture.get('semifinales', []) if _es_valido(p)]
        if semis:
            result['semifinales'] = semis

        if _es_valido(fixture.get('final')):
            result['final'] = [fixture['final']]

        return result

    @staticmethod
    def generar_plantilla_calendario(fixtures: Dict[str, dict]) -> Dict:
        """
        Genera el calendario del domingo para todos los partidos de finales.

        Algoritmo forward desde las 10:00:
          - Fases en orden: octavos → cuartos → semifinales → final
          - Dentro de cada fase, categorías de peor a mejor (Séptima primero)
          - Cada partido ocupa el primer slot libre (hora más temprana, cancha 1 primero)

        Funciona con fixtures sin clasificados aún (pareja = None → 'Por definir').

        Args:
            fixtures: {categoria: fixture_dict} — fixtures_finales del torneo

        Returns:
            {'cancha_1': [...], 'cancha_2': [...], 'sin_asignar': []}
        """
        if not fixtures:
            return {'cancha_1': [], 'cancha_2': [], 'sin_asignar': []}

        HORA_INICIO = GeneradorCalendarioFinales.HORA_INICIO
        HORA_FIN = GeneradorCalendarioFinales.HORA_FIN

        # 1. Extraer fases por categoría
        cat_fases: Dict[str, dict] = {}
        for cat, fixture in fixtures.items():
            fases = GeneradorCalendarioFinales._extraer_fases(fixture)
            if fases:
                cat_fases[cat] = fases

        if not cat_fases:
            return {'cancha_1': [], 'cancha_2': [], 'sin_asignar': []}

        # 2. Inicializar grilla: hora (int) → cancha (1|2) → entrada | None
        grid = {h: {1: None, 2: None} for h in range(HORA_INICIO, HORA_FIN)}

        def _siguiente_slot(desde_hora: int) -> Optional[Tuple[int, int]]:
            """Devuelve (hora, cancha) del primer slot libre desde desde_hora."""
            for h in range(desde_hora, HORA_FIN):
                for c in [1, 2]:
                    if grid[h][c] is None:
                        return (h, c)
            return None

        orden_cats = GeneradorCalendarioFinales.ORDEN_CATEGORIAS
        orden_fases = GeneradorCalendarioFinales.ORDEN_FASES_PROGRAMACION

        # 3. Programar fase a fase, de peor a mejor categoría dentro de cada fase
        hora_cursor = HORA_INICIO

        for fase_key in orden_fases:
            # Categorías presentes en esta fase, ordenadas peor→mejor
            cats_en_fase = [
                c for c in orden_cats
                if c in cat_fases and fase_key in cat_fases[c]
            ]

            for cat in cats_en_fase:
                partidos = cat_fases[cat][fase_key]
                for partido in partidos:
                    slot = _siguiente_slot(hora_cursor)
                    if slot is None:
                        logger.warning(
                            f"Sin slot para {cat} {fase_key} {partido.get('id')}"
                        )
                        continue

                    hora, cancha = slot
                    grid[hora][cancha] = {
                        'partido_id': partido.get('id'),
                        'categoria': cat,
                        'fase': GeneradorCalendarioFinales.FASE_DISPLAY.get(fase_key, fase_key),
                        'numero_partido': partido.get('numero_partido', 1),
                        'pareja1': _get_nombre(partido.get('pareja1')),
                        'pareja2': _get_nombre(partido.get('pareja2')),
                        'hora_inicio': f"{hora:02d}:00",
                        'hora_fin': f"{hora + 1:02d}:00",
                        'cancha': cancha,
                    }
                    logger.debug(f"{cat} {fase_key} {partido.get('id')} → {hora:02d}:00 C{cancha}")

                    # Si la otra cancha de esa hora también está ocupada, avanzar el cursor
                    otra = 2 if cancha == 1 else 1
                    if grid[hora][otra] is not None:
                        hora_cursor = hora + 1
                    else:
                        hora_cursor = hora  # puede haber otro partido en la misma hora

        # 4. Convertir grilla a formato de salida
        calendario: Dict[str, list] = {'cancha_1': [], 'cancha_2': [], 'sin_asignar': []}

        for h in range(HORA_INICIO, HORA_FIN):
            for court in [1, 2]:
                if grid[h][court] is not None:
                    key = 'cancha_1' if court == 1 else 'cancha_2'
                    calendario[key].append(grid[h][court])

        logger.info(
            f"Calendario generado: Cancha 1: {len(calendario['cancha_1'])} partidos, "
            f"Cancha 2: {len(calendario['cancha_2'])} partidos"
        )
        return calendario

    @staticmethod
    def sincronizar_parejas(calendario: Dict, fixtures: Dict[str, dict]) -> Dict:
        """
        Actualiza los nombres de parejas en el calendario a partir de los fixtures actuales.

        Útil cuando se completan grupos y los clasificados se conocen: el calendario
        mantiene los horarios/courts asignados pero actualiza los nombres de parejas.

        Args:
            calendario: calendario_finales existente (cancha_1, cancha_2, sin_asignar)
            fixtures: fixtures_finales actualizados con parejas

        Returns:
            El mismo objeto calendario actualizado in-place
        """
        if not calendario or not fixtures:
            return calendario

        # Construir índice: partido_id → pareja1, pareja2
        partido_index = {}
        for cat, fixture in fixtures.items():
            for fase_key in ['octavos', 'cuartos', 'semifinales']:
                for partido in fixture.get(fase_key, []):
                    if partido and partido.get('id'):
                        partido_index[partido['id']] = partido
            final = fixture.get('final')
            if final and final.get('id'):
                partido_index[final['id']] = final

        # Actualizar entradas
        for cancha_key in ['cancha_1', 'cancha_2']:
            for entry in calendario.get(cancha_key, []):
                pid = entry.get('partido_id')
                if pid and pid in partido_index:
                    partido = partido_index[pid]
                    entry['pareja1'] = _get_nombre(partido.get('pareja1'))
                    entry['pareja2'] = _get_nombre(partido.get('pareja2'))

        return calendario

    @staticmethod
    def asignar_horarios(fixtures: Dict[str, dict]) -> Dict:
        """
        Alias de generar_plantilla_calendario para compatibilidad con código existente.
        """
        return GeneradorCalendarioFinales.generar_plantilla_calendario(fixtures)

    @staticmethod
    def generar_resumen_horarios() -> List[str]:
        """Genera un resumen de los horarios disponibles"""
        return [
            "🌅 Mañana: desde 09:00 (Octavos / Cuartos)",
            "🏆 Tarde: Semifinales y Cuartos",
            "🥇 Noche: Finales a las 20:00"
        ]


# LEGACY CODE BELOW - Mantener por compatibilidad con api/routes/calendario.py
class CalendarioFinalesBuilder:
    """DEPRECATED: Usar GeneradorCalendarioFinales en su lugar"""

    @dataclass
    class SlotFinal:
        """Representa un slot de partido en el calendario de finales"""
        categoria: str
        fase: str
        numero_partido: int

    HORARIOS_DOMINGO = [
        "09:00", "10:00", "11:00", "12:00", "13:00", "14:00",
        "15:00", "16:00", "17:00", "18:00", "19:00", "20:00", "21:00", "22:00"
    ]

    ESTRUCTURA_CALENDARIO = {
        "13:00": (
            SlotFinal("Quinta", "Semifinal", 1),
            SlotFinal("Sexta", "Cuartos", 1)
        ),
        "14:00": (
            SlotFinal("Séptima", "Semifinal", 1),
            SlotFinal("Sexta", "Cuartos", 2)
        ),
        "15:00": (
            SlotFinal("Quinta", "Semifinal", 2),
            SlotFinal("Sexta", "Cuartos", 3)
        ),
        "16:00": (
            SlotFinal("Séptima", "Semifinal", 2),
            SlotFinal("Sexta", "Cuartos", 4)
        ),
        "17:00": (
            SlotFinal("Cuarta", "Cuartos", 1),
            SlotFinal("Cuarta", "Cuartos", 2)
        ),
        "18:00": (
            SlotFinal("Cuarta", "Cuartos", 3),
            SlotFinal("Cuarta", "Cuartos", 4)
        ),
        "19:00": (
            SlotFinal("Sexta", "Semifinal", 1),
            SlotFinal("Sexta", "Semifinal", 2)
        ),
        "20:00": (
            SlotFinal("Cuarta", "Semifinal", 1),
            SlotFinal("Cuarta", "Semifinal", 2)
        ),
        "21:00": (
            SlotFinal("Quinta", "Final", 1),
            SlotFinal("Séptima", "Final", 1)
        ),
        "22:00": (
            SlotFinal("Cuarta", "Final", 1),
            SlotFinal("Sexta", "Final", 1)
        ),
    }

    @staticmethod
    def generar_calendario_base() -> Dict:
        calendario = {}
        for hora, (slot_cancha1, slot_cancha2) in CalendarioFinalesBuilder.ESTRUCTURA_CALENDARIO.items():
            calendario[hora] = {1: slot_cancha1, 2: slot_cancha2}
        return calendario

    @staticmethod
    def obtener_slot_para_partido(categoria: str, fase: str, numero_partido: int):
        for hora, (slot_cancha1, slot_cancha2) in CalendarioFinalesBuilder.ESTRUCTURA_CALENDARIO.items():
            if (slot_cancha1.categoria == categoria and
                    slot_cancha1.fase == fase and
                    slot_cancha1.numero_partido == numero_partido):
                return (hora, 1)
            if (slot_cancha2.categoria == categoria and
                    slot_cancha2.fase == fase and
                    slot_cancha2.numero_partido == numero_partido):
                return (hora, 2)
        return None

    @staticmethod
    def poblar_calendario_con_fixtures(fixtures_dict: dict) -> Dict:
        calendario = {}
        for hora in CalendarioFinalesBuilder.HORARIOS_DOMINGO:
            calendario[hora] = {1: None, 2: None}

        categoria_map = {"Cuarta": "Cuarta", "Quinta": "Quinta",
                         "Sexta": "Sexta", "Séptima": "Séptima"}

        for categoria_key, fixture_data in fixtures_dict.items():
            if not fixture_data:
                continue
            categoria_nombre = categoria_map.get(categoria_key, categoria_key)

            for idx, partido in enumerate(fixture_data.get('cuartos', []), 1):
                slot_info = CalendarioFinalesBuilder.obtener_slot_para_partido(
                    categoria_nombre, "Cuartos", idx)
                if slot_info:
                    hora, cancha = slot_info
                    calendario[hora][cancha] = {
                        'categoria': categoria_key, 'fase': 'Cuartos',
                        'numero_partido': idx, 'partido_id': partido.get('id'),
                        'pareja1': partido.get('pareja1', {}).get('nombre') if partido.get('pareja1') else 'Por definir',
                        'pareja2': partido.get('pareja2', {}).get('nombre') if partido.get('pareja2') else 'Por definir',
                        'tiene_ganador': partido.get('tiene_ganador', False),
                        'ganador': partido.get('ganador', {}).get('nombre') if partido.get('ganador') else None
                    }

            for idx, partido in enumerate(fixture_data.get('semifinales', []), 1):
                slot_info = CalendarioFinalesBuilder.obtener_slot_para_partido(
                    categoria_nombre, "Semifinal", idx)
                if slot_info:
                    hora, cancha = slot_info
                    calendario[hora][cancha] = {
                        'categoria': categoria_key, 'fase': 'Semifinal',
                        'numero_partido': idx, 'partido_id': partido.get('id'),
                        'pareja1': partido.get('pareja1', {}).get('nombre') if partido.get('pareja1') else 'Por definir',
                        'pareja2': partido.get('pareja2', {}).get('nombre') if partido.get('pareja2') else 'Por definir',
                        'tiene_ganador': partido.get('tiene_ganador', False),
                        'ganador': partido.get('ganador', {}).get('nombre') if partido.get('ganador') else None
                    }

            if fixture_data.get('final'):
                partido = fixture_data['final']
                slot_info = CalendarioFinalesBuilder.obtener_slot_para_partido(
                    categoria_nombre, "Final", 1)
                if slot_info:
                    hora, cancha = slot_info
                    calendario[hora][cancha] = {
                        'categoria': categoria_key, 'fase': 'Final',
                        'numero_partido': 1, 'partido_id': partido.get('id'),
                        'pareja1': partido.get('pareja1', {}).get('nombre') if partido.get('pareja1') else 'Por definir',
                        'pareja2': partido.get('pareja2', {}).get('nombre') if partido.get('pareja2') else 'Por definir',
                        'tiene_ganador': partido.get('tiene_ganador', False),
                        'ganador': partido.get('ganador', {}).get('nombre') if partido.get('ganador') else None
                    }

        return calendario
