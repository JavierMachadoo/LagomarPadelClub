from typing import List, Dict, Set, Tuple, Optional
from collections import defaultdict
import itertools

from core.models import Pareja, Grupo, ResultadoAlgoritmo
from config import CATEGORIAS, EMOJI_CATEGORIA


class AlgoritmoGrupos:
    def __init__(self, parejas: List[Pareja], num_canchas: int = 2):
        self.parejas = parejas
        self.num_canchas = num_canchas
        self.contador_grupos = 0
    
    def ejecutar(self) -> ResultadoAlgoritmo:
        parejas_por_categoria = self._separar_por_categoria()
        grupos_por_categoria = {}
        parejas_sin_asignar_total = []
        
        for categoria, parejas_cat in parejas_por_categoria.items():
            grupos, sin_asignar = self._formar_grupos_categoria(parejas_cat, categoria)
            grupos_por_categoria[categoria] = grupos
            parejas_sin_asignar_total.extend(sin_asignar)
        
        calendario = self._generar_calendario(grupos_por_categoria)
        estadisticas = self._calcular_estadisticas(grupos_por_categoria, parejas_sin_asignar_total)
        
        return ResultadoAlgoritmo(
            grupos_por_categoria=grupos_por_categoria,
            parejas_sin_asignar=parejas_sin_asignar_total,
            calendario=calendario,
            estadisticas=estadisticas
        )
    
    def _separar_por_categoria(self) -> Dict[str, List[Pareja]]:
        parejas_por_cat = defaultdict(list)
        for pareja in self.parejas:
            if pareja.categoria in CATEGORIAS:
                parejas_por_cat[pareja.categoria].append(pareja)
        return dict(parejas_por_cat)
    
    def _formar_grupos_categoria(self, parejas: List[Pareja], categoria: str) -> Tuple[List[Grupo], List[Pareja]]:
        if len(parejas) < 3:
            return [], list(parejas)
        
        # Intentar optimización global si hay suficientes parejas pero no demasiadas
        num_grupos_posibles = len(parejas) // 3
        
        # Solo optimizar si podemos formar entre 2 y 6 grupos (para mantener eficiencia)
        if 2 <= num_grupos_posibles <= 6:
            mejor_distribucion = self._buscar_distribucion_optima(list(parejas), categoria)
            if mejor_distribucion:
                grupos_formados, parejas_sin_asignar = mejor_distribucion
                return grupos_formados, parejas_sin_asignar
        
        # Si hay muy pocas o demasiadas parejas, usar algoritmo greedy original
        grupos_formados = []
        parejas_disponibles = set(parejas)
        
        while len(parejas_disponibles) >= 3:
            mejor_grupo = None
            mejor_score = -1
            mejor_franja = None
            
            for combo in itertools.combinations(parejas_disponibles, 3):
                score, franja = self._calcular_compatibilidad(list(combo))
                
                if score > mejor_score:
                    mejor_score = score
                    mejor_grupo = combo
                    mejor_franja = franja
            
            if mejor_grupo and mejor_score > 0:
                grupo = self._crear_grupo(list(mejor_grupo), categoria, mejor_franja, mejor_score)
                grupos_formados.append(grupo)
                
                for pareja in mejor_grupo:
                    parejas_disponibles.remove(pareja)
            else:
                break
        
        parejas_sin_asignar = list(parejas_disponibles)
        return grupos_formados, parejas_sin_asignar
    
    def _buscar_distribucion_optima(self, parejas: List[Pareja], categoria: str) -> Optional[Tuple[List[Grupo], List[Pareja]]]:
        """
        Busca la distribución óptima de grupos que maximiza el score total.
        Usa backtracking con poda para explorar combinaciones eficientemente.
        """
        mejor_score_total = -1
        mejor_grupos = None
        mejor_sin_asignar = None
        
        num_parejas = len(parejas)
        num_grupos_max = num_parejas // 3
        
        def backtrack(parejas_restantes: List[Pareja], grupos_actuales: List[Grupo], 
                     score_acumulado: float, grupos_formados: int):
            nonlocal mejor_score_total, mejor_grupos, mejor_sin_asignar
            
            # Si ya no podemos formar más grupos de 3
            if len(parejas_restantes) < 3:
                # Evaluar si esta solución es mejor
                if score_acumulado > mejor_score_total:
                    mejor_score_total = score_acumulado
                    mejor_grupos = grupos_actuales.copy()
                    mejor_sin_asignar = parejas_restantes.copy()
                return
            
            # Si ya formamos el máximo de grupos posibles
            if grupos_formados >= num_grupos_max:
                if score_acumulado > mejor_score_total:
                    mejor_score_total = score_acumulado
                    mejor_grupos = grupos_actuales.copy()
                    mejor_sin_asignar = parejas_restantes.copy()
                return
            
            # Poda: si incluso con score perfecto no superamos el mejor, no continuar
            parejas_por_asignar = len(parejas_restantes)
            grupos_restantes = parejas_por_asignar // 3
            score_maximo_posible = score_acumulado + (grupos_restantes * 3.0)
            
            if score_maximo_posible <= mejor_score_total:
                return
            
            # Probar combinaciones de 3 parejas
            combinaciones_scores = []
            for combo in itertools.combinations(parejas_restantes, 3):
                score, franja = self._calcular_compatibilidad(list(combo))
                if score > 0:  # Solo considerar grupos con alguna compatibilidad
                    combinaciones_scores.append((score, franja, combo))
            
            # Ordenar por score descendente
            combinaciones_scores.sort(reverse=True, key=lambda x: x[0])
            
            # Limitar basado en el número de parejas restantes para balance eficiencia/precisión
            # - Pocas parejas (≤9): explorar todas las combinaciones válidas
            # - Más parejas: limitar progresivamente para evitar explosión combinatoria
            if len(parejas_restantes) <= 9:
                # Con 9 parejas o menos (≤3 grupos), explorar todo
                max_combos = len(combinaciones_scores)
            elif len(parejas_restantes) <= 12:
                # Con 12 parejas (4 grupos), explorar las mejores 20
                max_combos = min(20, len(combinaciones_scores))
            else:
                # Con más parejas, limitar a 15
                max_combos = min(15, len(combinaciones_scores))
            
            for score, franja, combo in combinaciones_scores[:max_combos]:
                # Crear grupo temporal
                grupo = self._crear_grupo(list(combo), categoria, franja, score)
                
                # Quitar parejas de la lista restante
                nuevas_restantes = [p for p in parejas_restantes if p not in combo]
                
                # Continuar backtracking
                grupos_actuales.append(grupo)
                backtrack(nuevas_restantes, grupos_actuales, score_acumulado + score, grupos_formados + 1)
                grupos_actuales.pop()
        
        # Iniciar búsqueda
        backtrack(parejas, [], 0.0, 0)
        
        if mejor_grupos is not None:
            return mejor_grupos, mejor_sin_asignar
        
        return None
    
    def _calcular_compatibilidad(self, parejas: List[Pareja]) -> Tuple[float, Optional[str]]:
        if len(parejas) != 3:
            return 0.0, None
        
        franjas_p1 = set(parejas[0].franjas_disponibles)
        franjas_p2 = set(parejas[1].franjas_disponibles)
        franjas_p3 = set(parejas[2].franjas_disponibles)
        
        # Primero intentar encontrar una franja común a las 3 parejas
        franjas_comunes_todas = franjas_p1 & franjas_p2 & franjas_p3
        
        if franjas_comunes_todas:
            return 3.0, list(franjas_comunes_todas)[0]
        
        # Buscar la mejor franja evaluando todas las posibilidades
        mejor_franja = None
        mejor_score = 0.0
        
        # Obtener todas las franjas únicas de las 3 parejas
        todas_franjas = franjas_p1 | franjas_p2 | franjas_p3
        
        for franja_candidata in todas_franjas:
            dia_candidato = franja_candidata.split(' ')[0] if ' ' in franja_candidata else ''
            score = 0.0
            
            # Calcular score para cada pareja con esta franja
            for franjas_pareja in [franjas_p1, franjas_p2, franjas_p3]:
                if franja_candidata in franjas_pareja:
                    # Horario exacto: 1.0 punto
                    score += 1.0
                else:
                    # Verificar si al menos tiene el mismo día
                    dias_pareja = set(f.split(' ')[0] for f in franjas_pareja if ' ' in f)
                    if dia_candidato and dia_candidato in dias_pareja:
                        # Mismo día, hora diferente: 0.5 puntos
                        score += 0.5
                    # Si no tiene el día, suma 0.0 (no suma nada)
            
            if score > mejor_score:
                mejor_score = score
                mejor_franja = franja_candidata
        
        return mejor_score, mejor_franja
    
    def _crear_grupo(self, parejas: List[Pareja], categoria: str, 
                     franja: Optional[str], score: float) -> Grupo:
        self.contador_grupos += 1
        grupo = Grupo(
            id=self.contador_grupos,
            categoria=categoria,
            franja_horaria=franja,
            score_compatibilidad=score
        )
        
        for pareja in parejas:
            grupo.agregar_pareja(pareja)
        
        grupo.generar_partidos()
        return grupo
    
    def _generar_calendario(self, grupos_por_categoria: Dict[str, List[Grupo]]) -> Dict[str, List[Dict]]:
        calendario = defaultdict(list)
        
        # Mapeo de franjas a horas (para detectar solapamientos)
        franjas_a_horas = {
            'Viernes 18:00': ['Viernes 18:00', 'Viernes 19:00', 'Viernes 20:00'],
            'Viernes 21:00': ['Viernes 21:00', 'Viernes 22:00', 'Viernes 23:00'],
            'Sábado 09:00': ['Sábado 09:00', 'Sábado 10:00', 'Sábado 11:00'],
            'Sábado 12:00': ['Sábado 12:00', 'Sábado 13:00', 'Sábado 14:00'],
            'Sábado 16:00': ['Sábado 16:00', 'Sábado 17:00', 'Sábado 18:00'],
            'Sábado 19:00': ['Sábado 19:00', 'Sábado 20:00', 'Sábado 21:00'],
        }
        
        # Recopilar todos los grupos con su información
        grupos_con_info = []
        for categoria, grupos in grupos_por_categoria.items():
            for grupo in grupos:
                if grupo.franja_horaria:
                    grupos_con_info.append({
                        'grupo': grupo,
                        'franja': grupo.franja_horaria,
                        'categoria': categoria,
                        'horas': franjas_a_horas.get(grupo.franja_horaria, [grupo.franja_horaria])
                    })
        
        # Asignar canchas a cada grupo evitando solapamientos
        canchas_ocupadas = {}  # {cancha: [lista de horas ocupadas]}
        asignaciones = {}  # {grupo.id: cancha}
        
        for info in grupos_con_info:
            grupo = info['grupo']
            horas_franja = info['horas']
            cancha_asignada = None
            
            # Buscar una cancha disponible sin solapamientos
            for cancha_num in range(1, self.num_canchas + 1):
                if cancha_num not in canchas_ocupadas:
                    canchas_ocupadas[cancha_num] = []
                
                # Verificar si hay solapamiento de horas
                horas_ocupadas = canchas_ocupadas[cancha_num]
                solapamiento = any(hora in horas_ocupadas for hora in horas_franja)
                
                if not solapamiento:
                    cancha_asignada = cancha_num
                    # Marcar las horas como ocupadas
                    canchas_ocupadas[cancha_num].extend(horas_franja)
                    break
            
            # Si no se encontró cancha disponible, buscar la cancha con menos conflictos
            if cancha_asignada is None:
                mejor_cancha = 1
                menor_conflictos = float('inf')
                for cancha_num in range(1, self.num_canchas + 1):
                    if cancha_num not in canchas_ocupadas:
                        canchas_ocupadas[cancha_num] = []
                    conflictos = sum(1 for hora in horas_franja if hora in canchas_ocupadas[cancha_num])
                    if conflictos < menor_conflictos:
                        menor_conflictos = conflictos
                        mejor_cancha = cancha_num
                cancha_asignada = mejor_cancha
                canchas_ocupadas[cancha_asignada].extend(horas_franja)
            
            asignaciones[grupo.id] = cancha_asignada
        
        # Generar el calendario con las canchas asignadas
        for info in grupos_con_info:
            grupo = info['grupo']
            franja = info['franja']
            cancha_asignada = asignaciones[grupo.id]
            
            for idx_partido, (pareja1, pareja2) in enumerate(grupo.partidos):
                calendario[franja].append({
                    "franja": franja,
                    "categoria": info['categoria'],
                    "color": EMOJI_CATEGORIA.get(info['categoria'], "⚪"),
                    "grupo_id": grupo.id,
                    "cancha": cancha_asignada,
                    "partido_num": idx_partido + 1,
                    "pareja1": pareja1.nombre,
                    "pareja2": pareja2.nombre,
                    "score_compatibilidad": grupo.score_compatibilidad
                })
        
        return dict(calendario)
    
    def _calcular_estadisticas(self, grupos_por_categoria: Dict[str, List[Grupo]], 
                               parejas_sin_asignar: List[Pareja]) -> Dict:
        total_parejas = len(self.parejas)
        total_asignadas = total_parejas - len(parejas_sin_asignar)
        total_grupos = sum(len(grupos) for grupos in grupos_por_categoria.values())
        
        grupos_por_cat = {cat: len(grupos) for cat, grupos in grupos_por_categoria.items()}
        parejas_por_cat = defaultdict(int)
        
        for grupo_list in grupos_por_categoria.values():
            for grupo in grupo_list:
                parejas_por_cat[grupo.categoria] += len(grupo.parejas)
        
        todos_scores = []
        for grupos in grupos_por_categoria.values():
            for grupo in grupos:
                todos_scores.append(grupo.score_compatibilidad)
        
        score_promedio = sum(todos_scores) / len(todos_scores) if todos_scores else 0
        
        return {
            "total_parejas": total_parejas,
            "parejas_asignadas": total_asignadas,
            "parejas_sin_asignar": len(parejas_sin_asignar),
            "porcentaje_asignacion": (total_asignadas / total_parejas * 100) if total_parejas > 0 else 0,
            "total_grupos": total_grupos,
            "grupos_por_categoria": dict(grupos_por_cat),
            "parejas_por_categoria": dict(parejas_por_cat),
            "score_compatibilidad_promedio": score_promedio,
            "grupos_compatibilidad_perfecta": sum(1 for s in todos_scores if s >= 3.0),
            "grupos_compatibilidad_parcial": sum(1 for s in todos_scores if 2.0 <= s < 3.0)
        }
