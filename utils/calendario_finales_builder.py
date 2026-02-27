"""
Módulo para generar el calendario de finales del domingo.
Organiza todos los partidos de finales respetando las restricciones horarias.
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class BloqueHorario:
    """Representa un bloque horario disponible"""
    inicio: str  # formato "HH:MM"
    fin: str     # formato "HH:MM"
    cancha: int  # 1 o 2
    
    def duracion_minutos(self) -> int:
        """Calcula la duración del bloque en minutos"""
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
    """Genera el calendario del domingo para todos los partidos de finales"""
    
    # Configuración de horarios
    HORARIOS_DISPONIBLES = [
        # Mañana/Tarde
        ("09:00", "15:00"),
        # Tarde/Noche (después del break)
        ("16:00", "22:00")
    ]
    
    DURACION_PARTIDO = 60  # minutos por partido
    TIEMPO_CAMBIO = 10     # minutos entre partidos
    
    # Orden de prioridad de categorías (empezar por Séptima, terminar por Tercera)
    ORDEN_CATEGORIAS = ["Séptima", "Sexta", "Quinta", "Cuarta", "Tercera"]
    
    # Orden de fases (de menor a mayor importancia)
    ORDEN_FASES = {
        "Octavos de Final": 1,
        "Cuartos de Final": 2,
        "Semifinal": 3,
        "Final": 4
    }
    
    @staticmethod
    def generar_bloques_horarios() -> List[BloqueHorario]:
        """Genera todos los bloques horarios disponibles para ambas canchas"""
        bloques = []
        
        for cancha in [1, 2]:
            for inicio, fin in GeneradorCalendarioFinales.HORARIOS_DISPONIBLES:
                # Calcular cuántos partidos caben en este bloque
                h_inicio, m_inicio = map(int, inicio.split(':'))
                h_fin, m_fin = map(int, fin.split(':'))
                
                tiempo_disponible = (h_fin * 60 + m_fin) - (h_inicio * 60 + m_inicio)
                tiempo_por_partido = GeneradorCalendarioFinales.DURACION_PARTIDO + GeneradorCalendarioFinales.TIEMPO_CAMBIO
                
                # Crear bloques individuales para cada partido posible
                num_partidos = tiempo_disponible // tiempo_por_partido
                
                for i in range(num_partidos):
                    minutos_inicio = h_inicio * 60 + m_inicio + (i * tiempo_por_partido)
                    minutos_fin = minutos_inicio + GeneradorCalendarioFinales.DURACION_PARTIDO
                    
                    hora_inicio = f"{minutos_inicio // 60:02d}:{minutos_inicio % 60:02d}"
                    hora_fin = f"{minutos_fin // 60:02d}:{minutos_fin % 60:02d}"
                    
                    bloques.append(BloqueHorario(
                        inicio=hora_inicio,
                        fin=hora_fin,
                        cancha=cancha
                    ))
        
        return bloques
    
    @staticmethod
    def obtener_partidos_para_calendarizar(fixtures: Dict[str, dict]) -> List[Dict]:
        """
        Obtiene todos los partidos de finales que deben calendarizarse.
        Retorna lista ordenada por prioridad (categoría y fase).
        """
        partidos = []
        
        for categoria in GeneradorCalendarioFinales.ORDEN_CATEGORIAS:
            if categoria not in fixtures:
                continue
            
            fixture = fixtures[categoria]
            
            # Agregar partidos de cada fase
            for fase_key, fase_nombre in [('octavos', 'Octavos de Final'), 
                                          ('cuartos', 'Cuartos de Final'),
                                          ('semifinales', 'Semifinal')]:
                if fase_key in fixture:
                    for partido in fixture[fase_key]:
                        if partido:  # Verificar que el partido existe
                            partidos.append({
                                'partido_id': partido.get('id'),
                                'categoria': categoria,
                                'fase': fase_nombre,
                                'numero_partido': partido.get('numero_partido', 1),
                                'pareja1': partido.get('pareja1', {}).get('nombre') if partido.get('pareja1') else None,
                                'pareja2': partido.get('pareja2', {}).get('nombre') if partido.get('pareja2') else None,
                                'prioridad_categoria': GeneradorCalendarioFinales.ORDEN_CATEGORIAS.index(categoria),
                                'prioridad_fase': GeneradorCalendarioFinales.ORDEN_FASES.get(fase_nombre, 0)
                            })
            
            # Agregar final
            if fixture.get('final'):
                final = fixture['final']
                partidos.append({
                    'partido_id': final.get('id'),
                    'categoria': categoria,
                    'fase': 'Final',
                    'numero_partido': 1,
                    'pareja1': final.get('pareja1', {}).get('nombre') if final.get('pareja1') else None,
                    'pareja2': final.get('pareja2', {}).get('nombre') if final.get('pareja2') else None,
                    'prioridad_categoria': GeneradorCalendarioFinales.ORDEN_CATEGORIAS.index(categoria),
                    'prioridad_fase': GeneradorCalendarioFinales.ORDEN_FASES.get('Final', 0)
                })
        
        # Ordenar: primero por fase (octavos antes que finales), luego por categoría
        # Esto hace que las fases tempranas de todas las categorías se jueguen primero
        partidos.sort(key=lambda p: (p['prioridad_fase'], p['prioridad_categoria']))
        
        return partidos
    
    @staticmethod
    def asignar_horarios(fixtures: Dict[str, dict]) -> Dict:
        """
        Asigna horarios a todos los partidos de finales.
        Retorna calendario organizado por cancha y horario.
        """
        bloques = GeneradorCalendarioFinales.generar_bloques_horarios()
        partidos = GeneradorCalendarioFinales.obtener_partidos_para_calendarizar(fixtures)
        
        calendario = {
            'cancha_1': [],
            'cancha_2': [],
            'sin_asignar': []
        }
        
        logger.info(f"Asignando {len(partidos)} partidos a {len(bloques)} bloques horarios")
        
        # Asignar cada partido a un bloque
        idx_bloque = 0
        for partido in partidos:
            if idx_bloque >= len(bloques):
                # No hay más bloques disponibles
                calendario['sin_asignar'].append(partido)
                logger.warning(f"No hay bloques disponibles para {partido['partido_id']}")
                continue
            
            bloque = bloques[idx_bloque]
            
            partido_calendarizado = PartidoCalendarizado(
                partido_id=partido['partido_id'],
                categoria=partido['categoria'],
                fase=partido['fase'],
                numero_partido=partido['numero_partido'],
                pareja1=partido['pareja1'],
                pareja2=partido['pareja2'],
                hora_inicio=bloque.inicio,
                hora_fin=bloque.fin,
                cancha=bloque.cancha
            )
            
            # Agregar al calendario
            if bloque.cancha == 1:
                calendario['cancha_1'].append(partido_calendarizado.to_dict())
            else:
                calendario['cancha_2'].append(partido_calendarizado.to_dict())
            
            idx_bloque += 1
        
        # Ordenar por hora de inicio
        calendario['cancha_1'].sort(key=lambda p: p['hora_inicio'])
        calendario['cancha_2'].sort(key=lambda p: p['hora_inicio'])
        
        logger.info(f"Calendario generado: Cancha 1: {len(calendario['cancha_1'])} partidos, "
                   f"Cancha 2: {len(calendario['cancha_2'])} partidos, "
                   f"Sin asignar: {len(calendario['sin_asignar'])} partidos")
        
        return calendario
    
    @staticmethod
    def generar_resumen_horarios() -> List[str]:
        """Genera un resumen de los horarios disponibles"""
        return [
            "🌅 Mañana/Tarde: 09:00 - 15:00 (ambas canchas)",
            "⏸️  Pausa: 15:00 - 16:00",
            "🌆 Tarde/Noche: 16:00 - 22:00 (ambas canchas)"
        ]


# LEGACY CODE BELOW - Mantener por compatibilidad
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
        # Mediodía: Semifinales y más Cuartos
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
        
        # Tarde: Más Semifinales y Cuartos de 4ta
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
        
        # Noche: Semifinales de 4ta y 6ta
        "19:00": (
            SlotFinal("Sexta", "Semifinal", 1),
            SlotFinal("Sexta", "Semifinal", 2)
        ),
        "20:00": (
            SlotFinal("Cuarta", "Semifinal", 1),
            SlotFinal("Cuarta", "Semifinal", 2)
        ),
        
        # Finales
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
    def generar_calendario_base() -> Dict[str, Dict[int, SlotFinal]]:
        """
        Genera la estructura base del calendario de finales.
        
        Returns:
            Dict con estructura: {"09:00": {1: SlotFinal, 2: SlotFinal}, ...}
        """
        calendario = {}
        
        for hora, (slot_cancha1, slot_cancha2) in CalendarioFinalesBuilder.ESTRUCTURA_CALENDARIO.items():
            calendario[hora] = {
                1: slot_cancha1,
                2: slot_cancha2
            }
        
        return calendario
    
    @staticmethod
    def obtener_slot_para_partido(categoria: str, fase: str, numero_partido: int) -> Tuple[str, int]:
        """
        Encuentra el horario y cancha asignados a un partido específico.
        
        Args:
            categoria: "Cuarta", "Quinta", "Sexta", "Séptima"
            fase: "Cuartos", "Semifinal", "Final"
            numero_partido: 1, 2, 3, 4
        
        Returns:
            Tupla (hora, cancha) ej: ("09:00", 1)
        """
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
    def poblar_calendario_con_fixtures(fixtures_dict: dict) -> Dict[str, Dict[int, dict]]:
        """
        Puebla el calendario base con los partidos reales de los fixtures.
        
        Args:
            fixtures_dict: Diccionario con fixtures por categoría
                          {"Cuarta": fixture_dict, "Quinta": fixture_dict, ...}
        
        Returns:
            Calendario poblado con información de partidos
        """
        calendario = {}
        
        # Inicializar calendario vacío
        for hora in CalendarioFinalesBuilder.HORARIOS_DOMINGO:
            calendario[hora] = {1: None, 2: None}
        
        # Mapeo de nombres de categoría
        categoria_map = {
            "Cuarta": "Cuarta",
            "Quinta": "Quinta",
            "Sexta": "Sexta",
            "Séptima": "Séptima"
        }
        
        # Mapeo de fases
        fase_map = {
            "CUARTOS": "Cuartos",
            "SEMIFINAL": "Semifinal",
            "FINAL": "Final"
        }
        
        # Procesar cada categoría
        for categoria_key, fixture_data in fixtures_dict.items():
            if not fixture_data:
                continue
            
            categoria_nombre = categoria_map.get(categoria_key, categoria_key)
            
            # Procesar cuartos
            for idx, partido in enumerate(fixture_data.get('cuartos', []), 1):
                slot_info = CalendarioFinalesBuilder.obtener_slot_para_partido(
                    categoria_nombre, "Cuartos", idx
                )
                if slot_info:
                    hora, cancha = slot_info
                    calendario[hora][cancha] = {
                        'categoria': categoria_key,
                        'fase': 'Cuartos',
                        'numero_partido': idx,
                        'partido_id': partido.get('id'),
                        'pareja1': partido.get('pareja1', {}).get('nombre') if partido.get('pareja1') else 'Por definir',
                        'pareja2': partido.get('pareja2', {}).get('nombre') if partido.get('pareja2') else 'Por definir',
                        'tiene_ganador': partido.get('tiene_ganador', False),
                        'ganador': partido.get('ganador', {}).get('nombre') if partido.get('ganador') else None
                    }
            
            # Procesar semifinales
            for idx, partido in enumerate(fixture_data.get('semifinales', []), 1):
                slot_info = CalendarioFinalesBuilder.obtener_slot_para_partido(
                    categoria_nombre, "Semifinal", idx
                )
                if slot_info:
                    hora, cancha = slot_info
                    calendario[hora][cancha] = {
                        'categoria': categoria_key,
                        'fase': 'Semifinal',
                        'numero_partido': idx,
                        'partido_id': partido.get('id'),
                        'pareja1': partido.get('pareja1', {}).get('nombre') if partido.get('pareja1') else 'Por definir',
                        'pareja2': partido.get('pareja2', {}).get('nombre') if partido.get('pareja2') else 'Por definir',
                        'tiene_ganador': partido.get('tiene_ganador', False),
                        'ganador': partido.get('ganador', {}).get('nombre') if partido.get('ganador') else None
                    }
            
            # Procesar final
            if fixture_data.get('final'):
                partido = fixture_data['final']
                slot_info = CalendarioFinalesBuilder.obtener_slot_para_partido(
                    categoria_nombre, "Final", 1
                )
                if slot_info:
                    hora, cancha = slot_info
                    calendario[hora][cancha] = {
                        'categoria': categoria_key,
                        'fase': 'Final',
                        'numero_partido': 1,
                        'partido_id': partido.get('id'),
                        'pareja1': partido.get('pareja1', {}).get('nombre') if partido.get('pareja1') else 'Por definir',
                        'pareja2': partido.get('pareja2', {}).get('nombre') if partido.get('pareja2') else 'Por definir',
                        'tiene_ganador': partido.get('tiene_ganador', False),
                        'ganador': partido.get('ganador', {}).get('nombre') if partido.get('ganador') else None
                    }
        
        return calendario
