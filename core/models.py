from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict
from enum import Enum


class PosicionGrupo(Enum):
    """Posiciones finales en el grupo"""
    PRIMERO = 1
    SEGUNDO = 2
    TERCERO = 3


@dataclass
class ResultadoPartido:
    """Representa el resultado de un partido de grupo"""
    pareja1_id: int
    pareja2_id: int
    sets_pareja1: int = 0  # Cantidad de sets ganados por pareja 1
    sets_pareja2: int = 0  # Cantidad de sets ganados por pareja 2
    games_set1_pareja1: Optional[int] = None  # Games del set 1
    games_set1_pareja2: Optional[int] = None
    games_set2_pareja1: Optional[int] = None  # Games del set 2
    games_set2_pareja2: Optional[int] = None
    tiebreak_pareja1: Optional[int] = None  # Puntos del super tie-break
    tiebreak_pareja2: Optional[int] = None
    
    def esta_completo(self) -> bool:
        """Verifica si el resultado está completo"""
        # Debe tener al menos los 2 primeros sets
        if None in [self.games_set1_pareja1, self.games_set1_pareja2, 
                    self.games_set2_pareja1, self.games_set2_pareja2]:
            return False
        
        # Si hay empate en sets (1-1), debe tener tie-break
        if self.sets_pareja1 == 1 and self.sets_pareja2 == 1:
            return self.tiebreak_pareja1 is not None and self.tiebreak_pareja2 is not None
        
        return True
    
    def calcular_ganador(self) -> Optional[int]:
        """Retorna el ID de la pareja ganadora"""
        if not self.esta_completo():
            return None
        
        # Si una pareja ganó 2 sets, es la ganadora
        if self.sets_pareja1 == 2:
            return self.pareja1_id
        if self.sets_pareja2 == 2:
            return self.pareja2_id
        
        # Si hay empate 1-1, el ganador se define por el tie-break
        if self.sets_pareja1 == 1 and self.sets_pareja2 == 1:
            if self.tiebreak_pareja1 > self.tiebreak_pareja2:
                return self.pareja1_id
            elif self.tiebreak_pareja2 > self.tiebreak_pareja1:
                return self.pareja2_id
        
        return None
    
    def total_games_pareja(self, pareja_id: int) -> int:
        """Calcula el total de games ganados por una pareja"""
        total = 0
        if pareja_id == self.pareja1_id:
            if self.games_set1_pareja1 is not None:
                total += self.games_set1_pareja1
            if self.games_set2_pareja1 is not None:
                total += self.games_set2_pareja1
        elif pareja_id == self.pareja2_id:
            if self.games_set1_pareja2 is not None:
                total += self.games_set1_pareja2
            if self.games_set2_pareja2 is not None:
                total += self.games_set2_pareja2
        return total
    
    def to_dict(self):
        return {
            'pareja1_id': self.pareja1_id,
            'pareja2_id': self.pareja2_id,
            'sets_pareja1': self.sets_pareja1,
            'sets_pareja2': self.sets_pareja2,
            'games_set1_pareja1': self.games_set1_pareja1,
            'games_set1_pareja2': self.games_set1_pareja2,
            'games_set2_pareja1': self.games_set2_pareja1,
            'games_set2_pareja2': self.games_set2_pareja2,
            'tiebreak_pareja1': self.tiebreak_pareja1,
            'tiebreak_pareja2': self.tiebreak_pareja2,
            'ganador_id': self.calcular_ganador()
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            pareja1_id=data['pareja1_id'],
            pareja2_id=data['pareja2_id'],
            sets_pareja1=data.get('sets_pareja1', 0),
            sets_pareja2=data.get('sets_pareja2', 0),
            games_set1_pareja1=data.get('games_set1_pareja1'),
            games_set1_pareja2=data.get('games_set1_pareja2'),
            games_set2_pareja1=data.get('games_set2_pareja1'),
            games_set2_pareja2=data.get('games_set2_pareja2'),
            tiebreak_pareja1=data.get('tiebreak_pareja1'),
            tiebreak_pareja2=data.get('tiebreak_pareja2')
        )


class FaseFinal(Enum):
    """Fases de las finales"""
    OCTAVOS = "Octavos de Final"
    CUARTOS = "Cuartos de Final"
    SEMIFINAL = "Semifinal"
    FINAL = "Final"


@dataclass
class Pareja:
    id: int
    nombre: str
    telefono: str
    categoria: str
    franjas_disponibles: List[str]
    grupo_asignado: Optional[int] = None
    posicion_grupo: Optional[PosicionGrupo] = None  # Nueva: posición final en el grupo
    jugador1: str = ""
    jugador2: str = ""
    
    def __hash__(self):
        return hash(self.id)
    
    def __eq__(self, other):
        if isinstance(other, Pareja):
            return self.id == other.id
        return False
    
    def to_dict(self):
        return {
            'categoria': self.categoria,
            'franjas_disponibles': self.franjas_disponibles,
            'id': self.id,
            'nombre': self.nombre,
            'jugador1': self.jugador1,
            'jugador2': self.jugador2,
            'telefono': self.telefono,
            'grupo_asignado': self.grupo_asignado,
            'posicion_grupo': self.posicion_grupo.value if self.posicion_grupo else None
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        posicion = data.get('posicion_grupo')
        # Normalizar franjas_disponibles: puede venir como string vacío o lista
        franjas_raw = data.get('franjas_disponibles', [])
        if isinstance(franjas_raw, str):
            # Convertir string a lista; string vacío → lista vacía
            franjas_raw = [f.strip() for f in franjas_raw.split(',') if f.strip()] if franjas_raw else []
        return cls(
            id=data['id'],
            nombre=data['nombre'],
            telefono=data.get('telefono', 'Sin teléfono'),
            categoria=data['categoria'],
            franjas_disponibles=franjas_raw,
            grupo_asignado=data.get('grupo_asignado'),
            posicion_grupo=PosicionGrupo(posicion) if posicion else None,
            jugador1=data.get('jugador1', ''),
            jugador2=data.get('jugador2', '')
        )


@dataclass
class Grupo:
    id: int
    categoria: str
    parejas: List[Pareja] = field(default_factory=list)
    franja_horaria: Optional[str] = None
    partidos: List[Tuple[Pareja, Pareja]] = field(default_factory=list)
    resultados: Dict[str, ResultadoPartido] = field(default_factory=dict)  # key: "pareja1_id-pareja2_id"
    score_compatibilidad: float = 0.0
    
    def agregar_pareja(self, pareja: Pareja):
        if len(self.parejas) < 3:
            self.parejas.append(pareja)
            pareja.grupo_asignado = self.id
    
    def esta_completo(self) -> bool:
        return len(self.parejas) == 3
    
    def generar_partidos(self):
        if self.esta_completo():
            self.partidos = [
                (self.parejas[0], self.parejas[1]),
                (self.parejas[0], self.parejas[2]),
                (self.parejas[1], self.parejas[2])
            ]
    
    def get_resultado_key(self, pareja1_id: int, pareja2_id: int) -> str:
        """Genera la clave para buscar un resultado en el diccionario"""
        ids = sorted([pareja1_id, pareja2_id])
        return f"{ids[0]}-{ids[1]}"
    
    def agregar_resultado(self, resultado: ResultadoPartido):
        """Agrega o actualiza el resultado de un partido"""
        key = self.get_resultado_key(resultado.pareja1_id, resultado.pareja2_id)
        self.resultados[key] = resultado
    
    def todos_resultados_completos(self) -> bool:
        """Verifica si todos los partidos del grupo tienen resultados completos"""
        if not self.esta_completo():
            return False
        
        # Debe haber 3 partidos con resultados completos
        partidos_esperados = 3
        resultados_completos = sum(1 for r in self.resultados.values() if r.esta_completo())
        return resultados_completos == partidos_esperados
    
    def to_dict(self):
        return {
            'id': self.id,
            'categoria': self.categoria,
            'parejas': [p.to_dict() for p in self.parejas],
            'franja_horaria': self.franja_horaria,
            'partidos': [
                {
                    'pareja1': p1.nombre, 
                    'pareja2': p2.nombre,
                    'pareja1_id': p1.id,
                    'pareja2_id': p2.id
                }
                for p1, p2 in self.partidos
            ],
            'resultados': {k: v.to_dict() for k, v in self.resultados.items()},
            'score_compatibilidad': self.score_compatibilidad,
            'resultados_completos': self.todos_resultados_completos()
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        """Reconstruye un Grupo desde un diccionario"""
        # Si no tiene categoria directa, intentar obtenerla de la primera pareja
        categoria = data.get('categoria')
        if not categoria and data.get('parejas'):
            categoria = data['parejas'][0].get('categoria', 'Sin categoría')
        
        grupo = cls(
            id=data['id'],
            categoria=categoria or 'Sin categoría',
            franja_horaria=data.get('franja_horaria'),
            score_compatibilidad=data.get('score_compatibilidad', 0.0)
        )
        
        # Reconstruir parejas
        for pareja_dict in data.get('parejas', []):
            pareja = Pareja.from_dict(pareja_dict)
            grupo.parejas.append(pareja)
        
        # Reconstruir partidos
        if grupo.esta_completo():
            grupo.generar_partidos()
        
        # Reconstruir resultados
        for key, resultado_dict in data.get('resultados', {}).items():
            resultado = ResultadoPartido.from_dict(resultado_dict)
            grupo.resultados[key] = resultado
        
        return grupo


@dataclass
class ResultadoAlgoritmo:
    grupos_por_categoria: dict
    parejas_sin_asignar: List[Pareja]
    calendario: dict
    estadisticas: dict


@dataclass
class PartidoFinal:
    """Representa un partido en la fase final"""
    id: str  # Ej: "cuartos_1", "semi_1", "final"
    fase: FaseFinal
    pareja1: Optional[Pareja] = None
    pareja2: Optional[Pareja] = None
    ganador: Optional[Pareja] = None
    numero_partido: int = 1  # Número del partido dentro de la fase
    slot1_info: Optional[str] = None  # Ej: "1° Grupo A"
    slot2_info: Optional[str] = None  # Ej: "2° Grupo B"
    
    def to_dict(self):
        return {
            'id': self.id,
            'fase': self.fase.value,
            'pareja1': self.pareja1.to_dict() if self.pareja1 else None,
            'pareja2': self.pareja2.to_dict() if self.pareja2 else None,
            'ganador': self.ganador.to_dict() if self.ganador else None,
            'numero_partido': self.numero_partido,
            'slot1_info': self.slot1_info,
            'slot2_info': self.slot2_info,
            'esta_completo': self.pareja1 is not None and self.pareja2 is not None,
            'tiene_ganador': self.ganador is not None
        }
    
    @staticmethod
    def from_dict(data: dict, grupos: List['Grupo']) -> 'PartidoFinal':
        """Reconstruye un PartidoFinal desde un diccionario"""
        # Crear un mapa de parejas por ID para búsqueda rápida
        parejas_map = {}
        for grupo in grupos:
            for pareja in grupo.parejas:
                parejas_map[pareja.id] = pareja
        
        def encontrar_pareja(pareja_dict):
            if not pareja_dict:
                return None
            pareja_id = pareja_dict.get('id')
            return parejas_map.get(pareja_id)
        
        return PartidoFinal(
            id=data['id'],
            fase=FaseFinal(data['fase']),
            pareja1=encontrar_pareja(data.get('pareja1')),
            pareja2=encontrar_pareja(data.get('pareja2')),
            ganador=encontrar_pareja(data.get('ganador')),
            numero_partido=data.get('numero_partido', 1),
            slot1_info=data.get('slot1_info'),
            slot2_info=data.get('slot2_info')
        )


@dataclass
class FixtureFinales:
    """Fixture completo de finales para una categoría"""
    categoria: str
    octavos: List[PartidoFinal] = field(default_factory=list)
    cuartos: List[PartidoFinal] = field(default_factory=list)
    semifinales: List[PartidoFinal] = field(default_factory=list)
    final: Optional[PartidoFinal] = None
    
    def to_dict(self):
        return {
            'categoria': self.categoria,
            'octavos': [p.to_dict() for p in self.octavos],
            'cuartos': [p.to_dict() for p in self.cuartos],
            'semifinales': [p.to_dict() for p in self.semifinales],
            'final': self.final.to_dict() if self.final else None
        }
    
    @staticmethod
    def from_dict(data: dict, grupos: List['Grupo']) -> 'FixtureFinales':
        """Reconstruye un FixtureFinales desde un diccionario"""
        fixture = FixtureFinales(categoria=data['categoria'])
        
        # Reconstruir cada lista de partidos
        fixture.octavos = [
            PartidoFinal.from_dict(p, grupos) for p in data.get('octavos', [])
        ]
        fixture.cuartos = [
            PartidoFinal.from_dict(p, grupos) for p in data.get('cuartos', [])
        ]
        fixture.semifinales = [
            PartidoFinal.from_dict(p, grupos) for p in data.get('semifinales', [])
        ]
        
        if data.get('final'):
            fixture.final = PartidoFinal.from_dict(data['final'], grupos)
        
        return fixture

