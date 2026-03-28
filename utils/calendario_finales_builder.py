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
    HORA_INICIO = 9   # primera franja: 09:00
    HORA_FINALES = 20 # hora reservada para las finales

    # Orden de categorías para el calendario (Séptima juega antes que Tercera)
    ORDEN_CATEGORIAS = ["Séptima", "Sexta", "Quinta", "Cuarta", "Tercera"]

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
    def _extraer_fases(fixture: dict) -> List[Tuple[str, List[dict]]]:
        """
        Extrae las fases de un fixture como lista ordenada de (fase_key, [partidos]).
        Filtra partidos 'Vacío' que no tienen pareja real asignada.
        """
        fases = []

        octavos = [p for p in fixture.get('octavos', [])
                   if p and p.get('id') and p.get('slot1_info') != 'Vacío']
        if octavos:
            fases.append(('octavos', octavos))

        cuartos = [p for p in fixture.get('cuartos', [])
                   if p and p.get('id') and p.get('slot1_info') != 'Vacío']
        if cuartos:
            fases.append(('cuartos', cuartos))

        semis = [p for p in fixture.get('semifinales', []) if p and p.get('id')]
        if semis:
            fases.append(('semifinales', semis))

        if fixture.get('final') and fixture['final'].get('id'):
            fases.append(('final', [fixture['final']]))

        return fases

    @staticmethod
    def generar_plantilla_calendario(fixtures: Dict[str, dict]) -> Dict:
        """
        Genera el calendario del domingo para todos los partidos de finales.

        Funciona con fixtures sin clasificados aún (parejas='Por definir') o con
        clasificados parciales/completos. Los nombres de parejas se toman del fixture
        en el momento de la generación.

        Args:
            fixtures: {categoria: fixture_dict} — fixtures_finales del torneo

        Returns:
            {
                'cancha_1': [{partido_id, categoria, fase, numero_partido,
                              pareja1, pareja2, hora_inicio, hora_fin, cancha}, ...],
                'cancha_2': [...],
                'sin_asignar': []
            }
        """
        if not fixtures:
            return {'cancha_1': [], 'cancha_2': [], 'sin_asignar': []}

        HORA_INICIO = GeneradorCalendarioFinales.HORA_INICIO
        HORA_FIN = GeneradorCalendarioFinales.HORA_FINALES + 1  # slot 20:00-21:00 incluido

        # 1. Extraer fases por categoría
        cat_fases = {}
        for cat, fixture in fixtures.items():
            fases = GeneradorCalendarioFinales._extraer_fases(fixture)
            if fases:
                cat_fases[cat] = fases

        if not cat_fases:
            return {'cancha_1': [], 'cancha_2': [], 'sin_asignar': []}

        # 2. Ordenar categorías: más fases primero → comienzan antes
        orden_base = GeneradorCalendarioFinales.ORDEN_CATEGORIAS
        cats_sorted = sorted(
            cat_fases.keys(),
            key=lambda c: (
                -len(cat_fases[c]),
                orden_base.index(c) if c in orden_base else 99
            )
        )

        # 3. Inicializar grilla de horarios: hora → cancha → entrada
        grid = {h: {1: None, 2: None} for h in range(HORA_INICIO, HORA_FIN)}

        # 4. Asignar finales empezando en 20:00 hacia atrás (2 por hora con 2 canchas)
        hora_finales_actual = GeneradorCalendarioFinales.HORA_FINALES
        cat_final_hora = {}

        for i, cat in enumerate(cats_sorted):
            fases = cat_fases[cat]
            if not fases or fases[-1][0] != 'final':
                continue

            court = (i % 2) + 1
            # Cada 2 categorías bajar una hora (ya que hay 2 canchas por hora)
            if i > 0 and i % 2 == 0:
                hora_finales_actual -= 1

            # Buscar slot disponible en la hora objetivo
            hora_asignada = hora_finales_actual
            while hora_asignada >= HORA_INICIO:
                if grid[hora_asignada][court] is None:
                    break
                hora_asignada -= 1

            if hora_asignada < HORA_INICIO:
                logger.warning(f"Sin slot para final de {cat}")
                continue

            partido = fases[-1][1][0]
            grid[hora_asignada][court] = {
                'partido_id': partido.get('id'),
                'categoria': cat,
                'fase': GeneradorCalendarioFinales.FASE_DISPLAY['final'],
                'numero_partido': partido.get('numero_partido', 1),
                'pareja1': _get_nombre(partido.get('pareja1')),
                'pareja2': _get_nombre(partido.get('pareja2')),
                'hora_inicio': f"{hora_asignada:02d}:00",
                'hora_fin': f"{hora_asignada + 1:02d}:00",
                'cancha': court
            }
            cat_final_hora[cat] = hora_asignada
            logger.debug(f"Final {cat} → {hora_asignada:02d}:00 Cancha {court}")

        # 5. Para cada categoría, asignar fases anteriores hacia atrás desde su final
        for cat in cats_sorted:
            if cat not in cat_final_hora:
                continue

            fases = cat_fases[cat]
            max_hora = cat_final_hora[cat] - 1  # debe ser ANTES de la final

            # Procesar fases en orden inverso: semis → cuartos → octavos
            for fase_key, partidos in reversed(fases[:-1]):
                hora_actual = max_hora
                min_hora_usada = max_hora + 1  # track earliest hour used in this phase

                for partido in partidos:
                    # Buscar siguiente slot disponible
                    while hora_actual >= HORA_INICIO:
                        court = None
                        for c in [1, 2]:
                            if grid[hora_actual][c] is None:
                                court = c
                                break
                        if court is not None:
                            break
                        hora_actual -= 1

                    if hora_actual < HORA_INICIO:
                        logger.warning(
                            f"Sin slot para {cat} {fase_key} partido {partido.get('id')}"
                        )
                        break

                    grid[hora_actual][court] = {
                        'partido_id': partido.get('id'),
                        'categoria': cat,
                        'fase': GeneradorCalendarioFinales.FASE_DISPLAY[fase_key],
                        'numero_partido': partido.get('numero_partido', 1),
                        'pareja1': _get_nombre(partido.get('pareja1')),
                        'pareja2': _get_nombre(partido.get('pareja2')),
                        'hora_inicio': f"{hora_actual:02d}:00",
                        'hora_fin': f"{hora_actual + 1:02d}:00",
                        'cancha': court
                    }
                    min_hora_usada = min(min_hora_usada, hora_actual)
                    logger.debug(
                        f"{cat} {fase_key} {partido.get('id')} → {hora_actual:02d}:00 C{court}"
                    )

                    # Si la otra cancha también está ocupada en esta hora, avanzar
                    other_court = 2 if court == 1 else 1
                    if grid[hora_actual][other_court] is not None:
                        hora_actual -= 1

                # La próxima fase debe terminar ANTES de la hora más temprana de esta fase
                max_hora = min_hora_usada - 1

        # 6. Convertir grilla a formato de calendario
        calendario = {'cancha_1': [], 'cancha_2': [], 'sin_asignar': []}

        for h in range(HORA_INICIO, HORA_FIN):
            for court in [1, 2]:
                if grid[h][court] is not None:
                    entry = grid[h][court]
                    if court == 1:
                        calendario['cancha_1'].append(entry)
                    else:
                        calendario['cancha_2'].append(entry)

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
