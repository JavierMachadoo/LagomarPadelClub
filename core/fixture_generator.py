"""
Generador de fixtures para las fases finales del torneo.
Maneja la lógica de clasificación según cantidad de grupos y posiciones.
"""

from typing import List, Dict, Optional
from core.models import Pareja, Grupo, PartidoFinal, FixtureFinales, FaseFinal, PosicionGrupo


class FixtureGenerator:
    """
    Genera el fixture de finales basado en las posiciones de los grupos.
    
    Reglas:
    - 3 grupos: Los 2 primeros de cada grupo van a semifinales (diferentes llaves).
               El 3er primero + los 3 segundos juegan cuartos de final.
    - 4 grupos: Todos juegan cuartos de final. 1° vs 2° de otro grupo (no del suyo).
    """
    
    def __init__(self, grupos: List[Grupo]):
        self.grupos = grupos
        self.num_grupos = len(grupos)
    
    def generar_fixture(self) -> FixtureFinales:
        """Genera el fixture completo según la cantidad de grupos"""
        if not self.grupos:
            return FixtureFinales(categoria=self.grupos[0].categoria if self.grupos else "")
        
        categoria = self.grupos[0].categoria
        
        # Obtener parejas clasificadas por posición
        primeros, segundos, terceros = self._clasificar_parejas()
        
        if self.num_grupos == 3:
            return self._generar_fixture_3_grupos(categoria, primeros, segundos, terceros)
        elif self.num_grupos == 4:
            return self._generar_fixture_4_grupos(categoria, primeros, segundos)
        else:
            # Para 2 grupos o casos especiales
            return self._generar_fixture_simple(categoria, primeros, segundos)
    
    def _clasificar_parejas(self) -> tuple[List[Pareja], List[Pareja], List[Pareja]]:
        """Clasifica parejas por posición en sus grupos"""
        primeros = []
        segundos = []
        terceros = []
        
        for grupo in self.grupos:
            for pareja in grupo.parejas:
                if pareja.posicion_grupo == PosicionGrupo.PRIMERO:
                    primeros.append(pareja)
                elif pareja.posicion_grupo == PosicionGrupo.SEGUNDO:
                    segundos.append(pareja)
                elif pareja.posicion_grupo == PosicionGrupo.TERCERO:
                    terceros.append(pareja)
        
        return primeros, segundos, terceros
    
    def _generar_fixture_3_grupos(
        self, 
        categoria: str, 
        primeros: List[Pareja], 
        segundos: List[Pareja],
        terceros: List[Pareja]
    ) -> FixtureFinales:
        """
        Fixture para 3 grupos:
        - 2 primeros van directo a semifinales (en diferentes llaves)
        - 1 tercer primero + 3 segundos juegan cuartos (4 parejas -> 2 partidos)
        """
        fixture = FixtureFinales(categoria=categoria)
        
        # Verificar que tenemos suficientes parejas
        if len(primeros) < 2:
            return fixture  # No hay suficientes datos aún
        
        # CUARTOS DE FINAL (si hay 3er primero y segundos)
        if len(primeros) >= 3 and len(segundos) >= 3:
            # El 3er primero juega contra uno de los segundos
            cuarto_1 = PartidoFinal(
                id="cuartos_1",
                fase=FaseFinal.CUARTOS,
                pareja1=primeros[2],  # 3er primero
                pareja2=segundos[0],  # 1er segundo
                numero_partido=1
            )
            
            # Los otros 2 segundos juegan entre sí
            cuarto_2 = PartidoFinal(
                id="cuartos_2",
                fase=FaseFinal.CUARTOS,
                pareja1=segundos[1],
                pareja2=segundos[2],
                numero_partido=2
            )
            
            fixture.cuartos = [cuarto_1, cuarto_2]
        
        # SEMIFINALES
        # Los 2 primeros primeros van directo a semi (en llaves separadas)
        semi_1 = PartidoFinal(
            id="semi_1",
            fase=FaseFinal.SEMIFINAL,
            pareja1=primeros[0],  # 1er primero (directo)
            pareja2=None,  # Ganador de cuartos_1
            numero_partido=1
        )
        
        semi_2 = PartidoFinal(
            id="semi_2",
            fase=FaseFinal.SEMIFINAL,
            pareja1=primeros[1],  # 2do primero (directo)
            pareja2=None,  # Ganador de cuartos_2
            numero_partido=2
        )
        
        fixture.semifinales = [semi_1, semi_2]
        
        # FINAL
        fixture.final = PartidoFinal(
            id="final",
            fase=FaseFinal.FINAL,
            pareja1=None,  # Ganador semi_1
            pareja2=None,  # Ganador semi_2
            numero_partido=1
        )
        
        return fixture
    
    def _generar_fixture_4_grupos(
        self,
        categoria: str,
        primeros: List[Pareja],
        segundos: List[Pareja]
    ) -> FixtureFinales:
        """
        Fixture para 4 grupos:
        - 4 cuartos de final: 1° vs 2° de otro grupo (no del suyo)
        - 2 semifinales
        - 1 final
        """
        fixture = FixtureFinales(categoria=categoria)
        
        # Verificar que tenemos 4 primeros y 4 segundos
        if len(primeros) < 4 or len(segundos) < 4:
            return fixture  # No hay suficientes datos aún
        
        # CUARTOS DE FINAL
        # Emparejar 1° vs 2° asegurando que no sean del mismo grupo
        cuartos = []
        
        # Crear emparejamientos cruzados
        # Grupo A (primero[0]) vs Grupo B (segundo[1])
        # Grupo B (primero[1]) vs Grupo C (segundo[2])
        # Grupo C (primero[2]) vs Grupo D (segundo[3])
        # Grupo D (primero[3]) vs Grupo A (segundo[0])
        
        emparejamientos = [
            (primeros[0], segundos[1]),  # A vs B
            (primeros[1], segundos[2]),  # B vs C
            (primeros[2], segundos[3]),  # C vs D
            (primeros[3], segundos[0])   # D vs A
        ]
        
        for idx, (p1, p2) in enumerate(emparejamientos, 1):
            # Validar que no son del mismo grupo
            if p1.grupo_asignado != p2.grupo_asignado:
                cuarto = PartidoFinal(
                    id=f"cuartos_{idx}",
                    fase=FaseFinal.CUARTOS,
                    pareja1=p1,
                    pareja2=p2,
                    numero_partido=idx
                )
                cuartos.append(cuarto)
        
        fixture.cuartos = cuartos
        
        # SEMIFINALES
        semi_1 = PartidoFinal(
            id="semi_1",
            fase=FaseFinal.SEMIFINAL,
            pareja1=None,  # Ganador cuartos_1
            pareja2=None,  # Ganador cuartos_2
            numero_partido=1
        )
        
        semi_2 = PartidoFinal(
            id="semi_2",
            fase=FaseFinal.SEMIFINAL,
            pareja1=None,  # Ganador cuartos_3
            pareja2=None,  # Ganador cuartos_4
            numero_partido=2
        )
        
        fixture.semifinales = [semi_1, semi_2]
        
        # FINAL
        fixture.final = PartidoFinal(
            id="final",
            fase=FaseFinal.FINAL,
            pareja1=None,  # Ganador semi_1
            pareja2=None,  # Ganador semi_2
            numero_partido=1
        )
        
        return fixture
    
    def _generar_fixture_simple(
        self,
        categoria: str,
        primeros: List[Pareja],
        segundos: List[Pareja]
    ) -> FixtureFinales:
        """
        Fixture simple para 2 grupos o casos especiales:
        - Semifinales directas
        - Final
        """
        fixture = FixtureFinales(categoria=categoria)
        
        # Con 2 grupos: 1° vs 2° del otro grupo
        if len(primeros) >= 2 and len(segundos) >= 2:
            semi_1 = PartidoFinal(
                id="semi_1",
                fase=FaseFinal.SEMIFINAL,
                pareja1=primeros[0],
                pareja2=segundos[1],
                numero_partido=1
            )
            
            semi_2 = PartidoFinal(
                id="semi_2",
                fase=FaseFinal.SEMIFINAL,
                pareja1=primeros[1],
                pareja2=segundos[0],
                numero_partido=2
            )
            
            fixture.semifinales = [semi_1, semi_2]
        
        # FINAL
        fixture.final = PartidoFinal(
            id="final",
            fase=FaseFinal.FINAL,
            pareja1=None,
            pareja2=None,
            numero_partido=1
        )
        
        return fixture
    
    @staticmethod
    def actualizar_fixture_con_ganador(
        fixture: FixtureFinales,
        partido_id: str,
        ganador_id: int
    ) -> FixtureFinales:
        """
        Actualiza el fixture cuando se marca un ganador.
        Propaga el ganador a la siguiente fase.
        """
        # Buscar el partido en todas las fases
        partido_encontrado = None
        fase_actual = None
        
        for partido in fixture.cuartos + fixture.semifinales + ([fixture.final] if fixture.final else []):
            if partido.id == partido_id:
                partido_encontrado = partido
                fase_actual = partido.fase
                break
        
        if not partido_encontrado:
            return fixture
        
        # Determinar quién es el ganador
        if partido_encontrado.pareja1 and partido_encontrado.pareja1.id == ganador_id:
            partido_encontrado.ganador = partido_encontrado.pareja1
        elif partido_encontrado.pareja2 and partido_encontrado.pareja2.id == ganador_id:
            partido_encontrado.ganador = partido_encontrado.pareja2
        else:
            return fixture
        
        # Propagar ganador a la siguiente fase
        if fase_actual == FaseFinal.CUARTOS:
            FixtureGenerator._propagar_a_semifinal(fixture, partido_id, partido_encontrado.ganador)
        elif fase_actual == FaseFinal.SEMIFINAL:
            FixtureGenerator._propagar_a_final(fixture, partido_id, partido_encontrado.ganador)
        
        return fixture
    
    @staticmethod
    def _propagar_a_semifinal(fixture: FixtureFinales, cuarto_id: str, ganador: Pareja):
        """Propaga el ganador de cuartos a la semifinal correspondiente"""
        # La lógica depende de cuántos cuartos hay (2 para 3 grupos, 4 para 4 grupos)
        num_cuartos = len(fixture.cuartos)
        
        if num_cuartos == 2:
            # Caso de 3 grupos: primeros van directo a semi en pareja1, ganadores de cuartos en pareja2
            if cuarto_id == "cuartos_1":
                # Ganador va a semi_1 pareja2
                if len(fixture.semifinales) > 0:
                    fixture.semifinales[0].pareja2 = ganador
            elif cuarto_id == "cuartos_2":
                # Ganador va a semi_2 pareja2
                if len(fixture.semifinales) > 1:
                    fixture.semifinales[1].pareja2 = ganador
        
        elif num_cuartos == 4:
            # Caso de 4 grupos: todos vienen de cuartos
            if cuarto_id == "cuartos_1":
                # Ganador va a semi_1 pareja1
                if len(fixture.semifinales) > 0:
                    fixture.semifinales[0].pareja1 = ganador
            elif cuarto_id == "cuartos_2":
                # Ganador va a semi_1 pareja2
                if len(fixture.semifinales) > 0:
                    fixture.semifinales[0].pareja2 = ganador
            elif cuarto_id == "cuartos_3":
                # Ganador va a semi_2 pareja1
                if len(fixture.semifinales) > 1:
                    fixture.semifinales[1].pareja1 = ganador
            elif cuarto_id == "cuartos_4":
                # Ganador va a semi_2 pareja2
                if len(fixture.semifinales) > 1:
                    fixture.semifinales[1].pareja2 = ganador
    
    @staticmethod
    def _propagar_a_final(fixture: FixtureFinales, semi_id: str, ganador: Pareja):
        """Propaga el ganador de semifinal a la final"""
        if not fixture.final:
            return
        
        if semi_id == "semi_1":
            fixture.final.pareja1 = ganador
        elif semi_id == "semi_2":
            fixture.final.pareja2 = ganador
