"""
Módulo para generar el fixture de finales basado en las posiciones de grupo.

Escenarios soportados en producción:
  - 3 grupos: 2 cuartos + 2 semis + final  (6 parejas)
  - 4 grupos: 4 cuartos + 2 semis + final  (8 parejas)
  - 5 grupos: 2 octavos + 4 cuartos + 2 semis + final  (10 parejas)
"""

from typing import List, Dict, Optional
from core.models import Grupo, FixtureFinales, PartidoFinal, FaseFinal
import logging

logger = logging.getLogger(__name__)


class GeneradorFixtureFinales:
    """Genera el fixture de finales para una categoría basándose en las posiciones de los grupos"""

    # ------------------------------------------------------------------
    # Helpers de consulta
    # ------------------------------------------------------------------

    @staticmethod
    def contar_grupos_completos(grupos: List[Grupo]) -> int:
        """Cuenta cuántos grupos tienen todos sus resultados completos"""
        return sum(1 for grupo in grupos if grupo.todos_resultados_completos())

    @staticmethod
    def obtener_clasificados_por_posicion(grupos: List[Grupo]) -> Dict[int, List]:
        """
        Obtiene las parejas clasificadas agrupadas por posición.

        Retorna: {1: [primeros], 2: [segundos], 3: [terceros]}
        Cada entrada es un dict con:
          - 'pareja': objeto Pareja
          - 'grupo_id': id del grupo
          - 'estadisticas': EstadisticasPareja (para ranking cross-grupo)

        Solo incluye parejas de grupos con resultados completos.
        El orden dentro de cada lista sigue el orden de los grupos (A, B, C…).
        """
        from core.clasificacion import CalculadorClasificacion

        clasificados = {1: [], 2: [], 3: []}

        for grupo in grupos:
            if not grupo.todos_resultados_completos():
                continue

            posiciones = CalculadorClasificacion.asignar_posiciones(grupo)
            estadisticas_lista = CalculadorClasificacion.calcular_estadisticas_grupo(grupo)
            # Convertir a dict por id para búsqueda O(1)
            stats_por_id = {e.pareja_id: e for e in estadisticas_lista}

            for pareja in grupo.parejas:
                if pareja.id not in posiciones:
                    continue
                posicion = posiciones[pareja.id].value
                pareja.posicion_grupo = posiciones[pareja.id]
                clasificados[posicion].append({
                    'pareja': pareja,
                    'grupo_id': grupo.id,
                    'estadisticas': stats_por_id[pareja.id],
                })

        return clasificados

    # ------------------------------------------------------------------
    # Punto de entrada principal
    # ------------------------------------------------------------------

    @staticmethod
    def generar_fixture(categoria: str, grupos: List[Grupo]) -> Optional[FixtureFinales]:
        """
        Genera el fixture de finales para una categoría.

        IMPORTANTE: genera SIEMPRE la estructura de llaves, incluso si los grupos
        aún no tienen resultados completos.  Las llaves se rellenan automáticamente
        conforme se van completando los grupos.

        Casos soportados (únicos en producción):
          - 5 grupos → 2 octavos + 4 cuartos + 2 semis + final
          - 4 grupos → 4 cuartos + 2 semis + final
          - 3 grupos → 2 cuartos + 2 semis + final
        """
        if not grupos:
            logger.warning(f"No hay grupos para la categoría {categoria}")
            return GeneradorFixtureFinales._generar_4_grupos(categoria, {1: [], 2: [], 3: []})

        grupos_categoria = [g for g in grupos if g.categoria == categoria]
        num_grupos = len(grupos_categoria)
        grupos_completos = GeneradorFixtureFinales.contar_grupos_completos(grupos_categoria)

        logger.info(
            f"Generando fixture para {categoria}: {num_grupos} grupos, {grupos_completos} completos"
        )

        clasificados = GeneradorFixtureFinales.obtener_clasificados_por_posicion(grupos_categoria)

        if num_grupos == 5:
            return GeneradorFixtureFinales._generar_5_grupos(categoria, clasificados)
        elif num_grupos == 3:
            return GeneradorFixtureFinales._generar_3_grupos(categoria, clasificados)
        else:
            # 4 grupos (o cualquier otro número fuera del rango esperado)
            return GeneradorFixtureFinales._generar_4_grupos(categoria, clasificados)

    # ------------------------------------------------------------------
    # 5 grupos: 2 octavos → 4 cuartos → 2 semis → final
    # ------------------------------------------------------------------
    #
    # Estructura:
    #
    #   OF.1: 2°[idx2] vs 2°[idx3]          (2 peores segundos por adyacencia)
    #   OF.2: 2°[idx0] vs 2°[idx1]          (2 peores segundos por adyacencia)
    #
    #   C.1:  1°[mejor] vs 2°[mejor_seg]    (mejor 1° vs mejor 2° directo)
    #   C.2:  1°[2do]   vs Ganador OF.1
    #   C.3:  1°[3ro]   vs Ganador OF.2
    #   C.4:  1°[4to]   vs 1°[5to]          (2 peores primeros entre sí)
    #
    #   S.1:  Ganador C.1 vs Ganador C.2
    #   S.2:  Ganador C.3 vs Ganador C.4
    #
    #   F:    Ganador S.1 vs Ganador S.2

    @staticmethod
    def _generar_5_grupos(categoria: str, clasificados: Dict) -> FixtureFinales:
        from core.clasificacion import CalculadorClasificacion

        fixture = FixtureFinales(categoria=categoria)

        primeros = clasificados[1]   # en orden de grupo
        segundos = clasificados[2]   # en orden de grupo

        # --- Rankear cross-grupo ---
        primeros_rankeados = CalculadorClasificacion.rankear_clasificados(primeros) if primeros else primeros
        segundos_rankeados = CalculadorClasificacion.rankear_clasificados(segundos) if segundos else segundos

        # Mejor segundo → pasa directo a cuartos
        mejor_segundo = segundos_rankeados[0] if len(segundos_rankeados) > 0 else None
        # Los 4 peores segundos van a octavos (en orden de ranking: peores primero para cruces por adyacencia)
        segundos_octavos = segundos_rankeados[1:] if len(segundos_rankeados) > 1 else []

        # 3 mejores primeros → esperan en C.1, C.2, C.3
        # 2 peores primeros → se enfrentan en C.4
        top3_primeros = primeros_rankeados[:3] if len(primeros_rankeados) >= 3 else primeros_rankeados
        bottom2_primeros = primeros_rankeados[3:5] if len(primeros_rankeados) >= 5 else primeros_rankeados[3:]

        # --- Octavos (2 partidos) ---
        # Cruces por adyacencia: los 4 segundos que van a octavos se enfrentan de a pares
        # OF.1: pos 0 vs pos 1 (de los 4 que van a octavos, los peores)
        # OF.2: pos 2 vs pos 3
        def _pareja_o_none(lista, idx):
            return lista[idx]['pareja'] if idx < len(lista) else None

        def _info_o_vacio(lista, idx, label):
            if idx < len(lista):
                return f"{label} (2° {lista[idx]['grupo_id']})"
            return label

        of1 = PartidoFinal(id=f"{categoria}_octavos_1", fase=FaseFinal.OCTAVOS, numero_partido=1)
        of1.pareja1 = _pareja_o_none(segundos_octavos, 0)
        of1.pareja2 = _pareja_o_none(segundos_octavos, 1)
        of1.slot1_info = _info_o_vacio(segundos_octavos, 0, "2° Grupo (OF.1)")
        of1.slot2_info = _info_o_vacio(segundos_octavos, 1, "2° Grupo (OF.1)")
        fixture.octavos.append(of1)

        of2 = PartidoFinal(id=f"{categoria}_octavos_2", fase=FaseFinal.OCTAVOS, numero_partido=2)
        of2.pareja1 = _pareja_o_none(segundos_octavos, 2)
        of2.pareja2 = _pareja_o_none(segundos_octavos, 3)
        of2.slot1_info = _info_o_vacio(segundos_octavos, 2, "2° Grupo (OF.2)")
        of2.slot2_info = _info_o_vacio(segundos_octavos, 3, "2° Grupo (OF.2)")
        fixture.octavos.append(of2)

        # --- Cuartos (4 partidos) ---
        # C.1: mejor 1° vs mejor 2° (directo)
        c1 = PartidoFinal(id=f"{categoria}_cuartos_1", fase=FaseFinal.CUARTOS, numero_partido=1)
        c1.pareja1 = _pareja_o_none(top3_primeros, 0)
        c1.pareja2 = mejor_segundo['pareja'] if mejor_segundo else None
        c1.slot1_info = (
            f"1° {top3_primeros[0]['grupo_id']}" if top3_primeros else "1° Grupo (C.1)"
        )
        c1.slot2_info = (
            f"Mejor 2° ({mejor_segundo['grupo_id']})" if mejor_segundo else "Mejor 2° (directo)"
        )
        fixture.cuartos.append(c1)

        # C.2: 2do mejor 1° vs Ganador OF.1
        c2 = PartidoFinal(id=f"{categoria}_cuartos_2", fase=FaseFinal.CUARTOS, numero_partido=2)
        c2.pareja1 = _pareja_o_none(top3_primeros, 1)
        c2.slot1_info = (
            f"1° {top3_primeros[1]['grupo_id']}" if len(top3_primeros) > 1 else "1° Grupo (C.2)"
        )
        c2.slot2_info = "Ganador OF.1"
        fixture.cuartos.append(c2)

        # C.3: 3er mejor 1° vs Ganador OF.2
        c3 = PartidoFinal(id=f"{categoria}_cuartos_3", fase=FaseFinal.CUARTOS, numero_partido=3)
        c3.pareja1 = _pareja_o_none(top3_primeros, 2)
        c3.slot1_info = (
            f"1° {top3_primeros[2]['grupo_id']}" if len(top3_primeros) > 2 else "1° Grupo (C.3)"
        )
        c3.slot2_info = "Ganador OF.2"
        fixture.cuartos.append(c3)

        # C.4: 4to mejor 1° vs 5to mejor 1° (2 peores primeros entre sí)
        c4 = PartidoFinal(id=f"{categoria}_cuartos_4", fase=FaseFinal.CUARTOS, numero_partido=4)
        c4.pareja1 = _pareja_o_none(bottom2_primeros, 0)
        c4.pareja2 = _pareja_o_none(bottom2_primeros, 1)
        c4.slot1_info = (
            f"1° {bottom2_primeros[0]['grupo_id']}" if bottom2_primeros else "1° Grupo (C.4)"
        )
        c4.slot2_info = (
            f"1° {bottom2_primeros[1]['grupo_id']}" if len(bottom2_primeros) > 1 else "1° Grupo (C.4)"
        )
        fixture.cuartos.append(c4)

        # --- Semifinales ---
        for i in range(2):
            fixture.semifinales.append(PartidoFinal(
                id=f"{categoria}_semi_{i+1}",
                fase=FaseFinal.SEMIFINAL,
                numero_partido=i + 1,
            ))

        # --- Final ---
        fixture.final = PartidoFinal(
            id=f"{categoria}_final",
            fase=FaseFinal.FINAL,
            numero_partido=1,
        )

        return fixture

    # ------------------------------------------------------------------
    # 4 grupos: 4 cuartos → 2 semis → final
    # ------------------------------------------------------------------
    #
    # Cruces clásicos evitando mismo grupo hasta la final:
    #   C.1: 1°A vs 2°D
    #   C.2: 1°B vs 2°C
    #   C.3: 1°C vs 2°B
    #   C.4: 1°D vs 2°A

    @staticmethod
    def _generar_4_grupos(categoria: str, clasificados: Dict) -> FixtureFinales:
        fixture = FixtureFinales(categoria=categoria)

        primeros = clasificados[1]
        segundos = clasificados[2]

        # PARCHE torneo actual: Séptima usa cruces distintos — sacar cuando se defina regla general
        if categoria.lower().replace('é', 'e') == 'septima':
            slots = [
                {'p1': (primeros, 0), 'p2': (segundos, 2), 'info1': '1° Grupo A', 'info2': '2° Grupo C'},
                {'p1': (primeros, 3), 'p2': (segundos, 1), 'info1': '1° Grupo D', 'info2': '2° Grupo B'},
                {'p1': (primeros, 1), 'p2': (segundos, 3), 'info1': '1° Grupo B', 'info2': '2° Grupo D'},
                {'p1': (primeros, 2), 'p2': (segundos, 0), 'info1': '1° Grupo C', 'info2': '2° Grupo A'},
            ]
        else:
            slots = [
                {'p1': (primeros, 0), 'p2': (segundos, 3), 'info1': '1° Grupo A', 'info2': '2° Grupo D'},
                {'p1': (primeros, 1), 'p2': (segundos, 2), 'info1': '1° Grupo B', 'info2': '2° Grupo C'},
                {'p1': (primeros, 2), 'p2': (segundos, 1), 'info1': '1° Grupo C', 'info2': '2° Grupo B'},
                {'p1': (primeros, 3), 'p2': (segundos, 0), 'info1': '1° Grupo D', 'info2': '2° Grupo A'},
            ]

        for i, s in enumerate(slots):
            partido = PartidoFinal(
                id=f"{categoria}_cuartos_{i+1}",
                fase=FaseFinal.CUARTOS,
                numero_partido=i + 1,
            )
            lista1, idx1 = s['p1']
            lista2, idx2 = s['p2']
            partido.pareja1 = lista1[idx1]['pareja'] if idx1 < len(lista1) else None
            partido.pareja2 = lista2[idx2]['pareja'] if idx2 < len(lista2) else None
            partido.slot1_info = s['info1']
            partido.slot2_info = s['info2']
            fixture.cuartos.append(partido)

        for i in range(2):
            fixture.semifinales.append(PartidoFinal(
                id=f"{categoria}_semi_{i+1}",
                fase=FaseFinal.SEMIFINAL,
                numero_partido=i + 1,
            ))

        fixture.final = PartidoFinal(
            id=f"{categoria}_final",
            fase=FaseFinal.FINAL,
            numero_partido=1,
        )

        return fixture

    # ------------------------------------------------------------------
    # 3 grupos: 2 cuartos → 2 semis → final
    # ------------------------------------------------------------------
    #
    # Estructura:
    #   C.1: 2°A vs 2°B
    #   C.2: 3er mejor 1° vs 2°C
    #   S.1: Mejor 1° (directo) vs Ganador C.1
    #   S.2: 2do mejor 1° (directo) vs Ganador C.2
    #   F:   Ganador S.1 vs Ganador S.2

    @staticmethod
    def _generar_3_grupos(categoria: str, clasificados: Dict) -> FixtureFinales:
        from core.clasificacion import CalculadorClasificacion

        fixture = FixtureFinales(categoria=categoria)

        primeros = clasificados[1]   # en orden de grupo (A, B, C)
        segundos = clasificados[2]   # en orden de grupo

        # Rankear primeros cross-grupo
        primeros_rankeados = CalculadorClasificacion.rankear_clasificados(primeros) if primeros else primeros

        mejor1 = primeros_rankeados[0] if len(primeros_rankeados) > 0 else None
        segundo1 = primeros_rankeados[1] if len(primeros_rankeados) > 1 else None
        tercer1 = primeros_rankeados[2] if len(primeros_rankeados) > 2 else None

        def _pareja_o_none(entry):
            return entry['pareja'] if entry else None

        # --- Cuartos (2 partidos) ---
        # C.1: 2°A vs 2°B (primeros dos segundos por orden de grupo)
        c1 = PartidoFinal(id=f"{categoria}_cuartos_1", fase=FaseFinal.CUARTOS, numero_partido=1)
        c1.pareja1 = segundos[0]['pareja'] if len(segundos) > 0 else None
        c1.pareja2 = segundos[1]['pareja'] if len(segundos) > 1 else None
        c1.slot1_info = f"2° {segundos[0]['grupo_id']}" if len(segundos) > 0 else "2° Grupo A"
        c1.slot2_info = f"2° {segundos[1]['grupo_id']}" if len(segundos) > 1 else "2° Grupo B"
        fixture.cuartos.append(c1)

        # C.2: 3er mejor 1° vs 2°C (tercer segundo por orden de grupo)
        c2 = PartidoFinal(id=f"{categoria}_cuartos_2", fase=FaseFinal.CUARTOS, numero_partido=2)
        c2.pareja1 = _pareja_o_none(tercer1)
        c2.pareja2 = segundos[2]['pareja'] if len(segundos) > 2 else None
        c2.slot1_info = (
            f"3er mejor 1° ({tercer1['grupo_id']})" if tercer1 else "3er mejor 1°"
        )
        c2.slot2_info = (
            f"2° {segundos[2]['grupo_id']}" if len(segundos) > 2 else "2° Grupo C"
        )
        fixture.cuartos.append(c2)

        # --- Semifinales (los 2 mejores primeros esperan directo) ---
        s1 = PartidoFinal(id=f"{categoria}_semi_1", fase=FaseFinal.SEMIFINAL, numero_partido=1)
        s1.pareja1 = _pareja_o_none(mejor1)
        s1.slot1_info = (
            f"Mejor 1° ({mejor1['grupo_id']}) — pasa directo" if mejor1 else "Mejor 1° (directo)"
        )
        s1.slot2_info = "Ganador Cuartos 1"
        fixture.semifinales.append(s1)

        s2 = PartidoFinal(id=f"{categoria}_semi_2", fase=FaseFinal.SEMIFINAL, numero_partido=2)
        s2.pareja1 = _pareja_o_none(segundo1)
        s2.slot1_info = (
            f"2° mejor 1° ({segundo1['grupo_id']}) — pasa directo" if segundo1 else "2° mejor 1° (directo)"
        )
        s2.slot2_info = "Ganador Cuartos 2"
        fixture.semifinales.append(s2)

        # --- Final ---
        fixture.final = PartidoFinal(
            id=f"{categoria}_final",
            fase=FaseFinal.FINAL,
            numero_partido=1,
        )

        return fixture

    # ------------------------------------------------------------------
    # Actualización de ganadores y propagación
    # ------------------------------------------------------------------

    @staticmethod
    def actualizar_ganador_partido(fixture: FixtureFinales, partido_id: str, ganador_id: int):
        """
        Actualiza el ganador de un partido y lo propaga al siguiente nivel.
        """
        partido_encontrado = None
        fase_actual = None

        for partido in fixture.octavos:
            if partido.id == partido_id:
                partido_encontrado = partido
                fase_actual = FaseFinal.OCTAVOS
                break

        if not partido_encontrado:
            for partido in fixture.cuartos:
                if partido.id == partido_id:
                    partido_encontrado = partido
                    fase_actual = FaseFinal.CUARTOS
                    break

        if not partido_encontrado:
            for partido in fixture.semifinales:
                if partido.id == partido_id:
                    partido_encontrado = partido
                    fase_actual = FaseFinal.SEMIFINAL
                    break

        if not partido_encontrado and fixture.final and fixture.final.id == partido_id:
            partido_encontrado = fixture.final
            fase_actual = FaseFinal.FINAL

        if not partido_encontrado:
            logger.error(f"Partido {partido_id} no encontrado en el fixture")
            return False

        if partido_encontrado.pareja1 and partido_encontrado.pareja1.id == ganador_id:
            partido_encontrado.ganador = partido_encontrado.pareja1
        elif partido_encontrado.pareja2 and partido_encontrado.pareja2.id == ganador_id:
            partido_encontrado.ganador = partido_encontrado.pareja2
        else:
            logger.error(f"Ganador ID {ganador_id} no es parte del partido {partido_id}")
            return False

        GeneradorFixtureFinales._propagar_ganador(fixture, partido_encontrado, fase_actual)
        return True

    @staticmethod
    def _propagar_ganador(fixture: FixtureFinales, partido: PartidoFinal, fase: FaseFinal):
        """Propaga el ganador de un partido al siguiente nivel."""
        if not partido.ganador:
            return

        num_partido = partido.numero_partido
        ganador = partido.ganador

        if fase == FaseFinal.OCTAVOS:
            if len(fixture.octavos) == 2:
                # Caso 5 grupos:
                #   OF.1 (num=1) → cuartos[1] (C.2) como pareja2
                #   OF.2 (num=2) → cuartos[2] (C.3) como pareja2
                idx_cuarto = num_partido  # 1→1, 2→2
                if idx_cuarto < len(fixture.cuartos):
                    fixture.cuartos[idx_cuarto].pareja2 = ganador
            else:
                # Caso genérico 8 octavos (por si se necesita en el futuro)
                idx_cuarto = (num_partido - 1) // 2
                if idx_cuarto < len(fixture.cuartos):
                    cuarto = fixture.cuartos[idx_cuarto]
                    if num_partido % 2 == 1:
                        cuarto.pareja1 = ganador
                    else:
                        cuarto.pareja2 = ganador

        elif fase == FaseFinal.CUARTOS:
            if len(fixture.cuartos) == 2:
                # Caso 3 grupos: pareja1 de cada semi ya tiene el 1° directo pre-poblado.
                # El ganador de cuartos siempre llena pareja2.
                #   C.1 (num=1) → S.1 como pareja2
                #   C.2 (num=2) → S.2 como pareja2
                idx_semi = num_partido - 1
                if idx_semi < len(fixture.semifinales):
                    fixture.semifinales[idx_semi].pareja2 = ganador
            else:
                # Caso genérico (4 grupos):
                #   C.1 (1) y C.2 (2) → S.1  |  C.3 (3) y C.4 (4) → S.2
                idx_semi = (num_partido - 1) // 2
                if idx_semi < len(fixture.semifinales):
                    semi = fixture.semifinales[idx_semi]
                    if num_partido % 2 == 1:
                        semi.pareja1 = ganador
                    else:
                        semi.pareja2 = ganador

        elif fase == FaseFinal.SEMIFINAL:
            if fixture.final:
                if num_partido == 1:
                    fixture.final.pareja1 = ganador
                else:
                    fixture.final.pareja2 = ganador
