"""
Módulo para calcular automáticamente las posiciones en los grupos
basándose en los resultados de los partidos.
"""

from typing import List, Dict
from dataclasses import dataclass
from core.models import Grupo, PosicionGrupo


@dataclass
class EstadisticasPareja:
    """Estadísticas de una pareja en su grupo"""
    pareja_id: int
    pareja_nombre: str
    partidos_jugados: int = 0
    partidos_ganados: int = 0
    partidos_perdidos: int = 0
    sets_ganados: int = 0
    sets_perdidos: int = 0
    games_ganados: int = 0
    games_perdidos: int = 0
    
    @property
    def diferencia_sets(self) -> int:
        return self.sets_ganados - self.sets_perdidos
    
    @property
    def diferencia_games(self) -> int:
        return self.games_ganados - self.games_perdidos


class CalculadorClasificacion:
    """Calcula las posiciones finales en un grupo basándose en los resultados"""
    
    @staticmethod
    def calcular_estadisticas_grupo(grupo: Grupo) -> List[EstadisticasPareja]:
        """Calcula las estadísticas de todas las parejas en un grupo"""
        estadisticas_dict = {}
        
        # Inicializar estadísticas para cada pareja
        for pareja in grupo.parejas:
            estadisticas_dict[pareja.id] = EstadisticasPareja(
                pareja_id=pareja.id,
                pareja_nombre=pareja.nombre
            )
        
        # Procesar cada resultado
        for resultado in grupo.resultados.values():
            if not resultado.esta_completo():
                continue
            
            p1_id = resultado.pareja1_id
            p2_id = resultado.pareja2_id
            ganador_id = resultado.calcular_ganador()
            
            if ganador_id is None:
                continue
            
            perdedor_id = p2_id if ganador_id == p1_id else p1_id
            
            # Actualizar partidos ganados/perdidos
            estadisticas_dict[ganador_id].partidos_jugados += 1
            estadisticas_dict[ganador_id].partidos_ganados += 1
            estadisticas_dict[perdedor_id].partidos_jugados += 1
            estadisticas_dict[perdedor_id].partidos_perdidos += 1
            
            # Actualizar sets
            estadisticas_dict[p1_id].sets_ganados += resultado.sets_pareja1
            estadisticas_dict[p1_id].sets_perdidos += resultado.sets_pareja2
            estadisticas_dict[p2_id].sets_ganados += resultado.sets_pareja2
            estadisticas_dict[p2_id].sets_perdidos += resultado.sets_pareja1

            # Super tiebreak: cuenta como set extra para el ganador, no suma games
            if resultado.tiebreak_pareja1 is not None and resultado.tiebreak_pareja2 is not None:
                if resultado.tiebreak_pareja1 > resultado.tiebreak_pareja2:
                    estadisticas_dict[p1_id].sets_ganados += 1
                    estadisticas_dict[p2_id].sets_perdidos += 1
                else:
                    estadisticas_dict[p2_id].sets_ganados += 1
                    estadisticas_dict[p1_id].sets_perdidos += 1

            # Actualizar games
            games_p1 = resultado.total_games_pareja(p1_id)
            games_p2 = resultado.total_games_pareja(p2_id)
            estadisticas_dict[p1_id].games_ganados += games_p1
            estadisticas_dict[p1_id].games_perdidos += games_p2
            estadisticas_dict[p2_id].games_ganados += games_p2
            estadisticas_dict[p2_id].games_perdidos += games_p1
        
        return list(estadisticas_dict.values())
    
    @staticmethod
    def ordenar_parejas(estadisticas: List[EstadisticasPareja]) -> List[EstadisticasPareja]:
        """
        Ordena las parejas según las reglas del torneo:
        1. Más partidos ganados
        2. En caso de empate, más sets ganados (NO cuenta tie-break como set)
        3. En caso de empate, más games ganados
        """
        return sorted(
            estadisticas,
            key=lambda e: (
                e.partidos_ganados,      # 1° criterio: partidos ganados
                e.diferencia_sets,       # 2° criterio: diferencia de sets
                e.diferencia_games       # 3° criterio: diferencia de games
            ),
            reverse=True
        )
    
    @staticmethod
    def asignar_posiciones(grupo: Grupo) -> Dict[int, PosicionGrupo]:
        """
        Calcula y asigna las posiciones automáticamente.
        Retorna un diccionario: {pareja_id: PosicionGrupo}
        """
        # Verificar que todos los resultados estén completos
        if not grupo.todos_resultados_completos():
            return {}
        
        # Calcular estadísticas
        estadisticas = CalculadorClasificacion.calcular_estadisticas_grupo(grupo)
        
        # Ordenar parejas
        estadisticas_ordenadas = CalculadorClasificacion.ordenar_parejas(estadisticas)
        
        # Asignar posiciones
        posiciones = {}
        posiciones_enum = [PosicionGrupo.PRIMERO, PosicionGrupo.SEGUNDO, PosicionGrupo.TERCERO]
        
        for i, estadistica in enumerate(estadisticas_ordenadas):
            if i < len(posiciones_enum):
                posiciones[estadistica.pareja_id] = posiciones_enum[i]
        
        return posiciones
    
    @staticmethod
    def rankear_clasificados(clasificados: List[dict]) -> List[dict]:
        """
        Rankea parejas de distintos grupos usando los mismos criterios de clasificación.

        Recibe lista de dicts con keys: 'pareja', 'grupo_id', 'estadisticas' (EstadisticasPareja).
        Retorna la lista ordenada de mejor a peor:
          1° partidos_ganados, 2° sets_ganados, 3° games_ganados
        """
        return sorted(
            clasificados,
            key=lambda c: (
                c['estadisticas'].partidos_ganados,
                c['estadisticas'].diferencia_sets,
                c['estadisticas'].diferencia_games,
            ),
            reverse=True,
        )

    @staticmethod
    def calcular_tabla_posiciones(grupo: Grupo) -> List[Dict]:
        """
        Genera una tabla de posiciones formateada para mostrar en el frontend
        """
        estadisticas = CalculadorClasificacion.calcular_estadisticas_grupo(grupo)
        estadisticas_ordenadas = CalculadorClasificacion.ordenar_parejas(estadisticas)
        
        tabla = []
        posiciones_enum = [1, 2, 3]
        
        for i, est in enumerate(estadisticas_ordenadas):
            tabla.append({
                'posicion': posiciones_enum[i] if i < len(posiciones_enum) else None,
                'pareja_id': est.pareja_id,
                'pareja_nombre': est.pareja_nombre,
                'partidos_jugados': est.partidos_jugados,
                'partidos_ganados': est.partidos_ganados,
                'partidos_perdidos': est.partidos_perdidos,
                'sets_ganados': est.sets_ganados,
                'sets_perdidos': est.sets_perdidos,
                'diferencia_sets': est.diferencia_sets,
                'games_ganados': est.games_ganados,
                'games_perdidos': est.games_perdidos,
                'diferencia_games': est.diferencia_games
            })
        
        return tabla
