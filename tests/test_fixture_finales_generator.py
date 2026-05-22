"""
Tests unitarios para GeneradorFixtureFinales._generar_5_grupos().

Verifica que con 5 grupos el 2do del grupo E pasa directo a cuartos,
y los 2dos de A, B, C, D van a octavos — independientemente del ranking cross-grupo.
"""

import pytest
from core.models import Grupo, Pareja, ResultadoPartido
from core.fixture_finales_generator import GeneradorFixtureFinales

CATEGORIA = "Cuarta"


def _pareja(id: int) -> Pareja:
    return Pareja(
        id=id,
        nombre=f"Pareja {id}",
        telefono="600000000",
        categoria=CATEGORIA,
        franjas_disponibles=["Sábado 09:00"],
    )


def _resultado(p1_id: int, p2_id: int, g1_p1: int, g1_p2: int, g2_p1: int, g2_p2: int) -> ResultadoPartido:
    sets_p1 = (1 if g1_p1 > g1_p2 else 0) + (1 if g2_p1 > g2_p2 else 0)
    sets_p2 = 2 - sets_p1
    return ResultadoPartido(
        pareja1_id=p1_id, pareja2_id=p2_id,
        sets_pareja1=sets_p1, sets_pareja2=sets_p2,
        games_set1_pareja1=g1_p1, games_set1_pareja2=g1_p2,
        games_set2_pareja1=g2_p1, games_set2_pareja2=g2_p2,
    )


def _crear_grupo(idx: int, diff_2do: tuple = (6, 3)) -> Grupo:
    """
    Crea un grupo (idx A=1, B=2, ... E=5) con resultados completos:
      - pareja (idx*10+1): 1er puesto — gana todo con 6-0, 6-0
      - pareja (idx*10+2): 2do puesto — gana al 3ro con scores diff_2do
      - pareja (idx*10+3): 3er puesto — pierde todo
    """
    base = idx * 10
    p1 = _pareja(base + 1)
    p2 = _pareja(base + 2)
    p3 = _pareja(base + 3)

    grupo = Grupo(id=idx, categoria=CATEGORIA)
    grupo.agregar_pareja(p1)
    grupo.agregar_pareja(p2)
    grupo.agregar_pareja(p3)
    grupo.generar_partidos()

    d1, d2 = diff_2do
    grupo.agregar_resultado(_resultado(p1.id, p2.id, 6, 0, 6, 0))
    grupo.agregar_resultado(_resultado(p1.id, p3.id, 6, 0, 6, 0))
    grupo.agregar_resultado(_resultado(p2.id, p3.id, d1, d2, d1, d2))

    return grupo


def _cinco_grupos() -> list:
    """
    Grupos A-D con un 2do estadísticamente fuerte; grupo E con 2do débil.
    Esto garantiza RED con la implementación anterior (ranking cross-grupo elegía
    al mejor 2do, que era de A) y GREEN tras el fix (2°E siempre pasa directo).
    """
    return [
        _crear_grupo(idx=1, diff_2do=(6, 0)),  # A: 2°A diff +12 (mejor segundo por stats)
        _crear_grupo(idx=2, diff_2do=(6, 3)),  # B
        _crear_grupo(idx=3, diff_2do=(6, 3)),  # C
        _crear_grupo(idx=4, diff_2do=(6, 3)),  # D
        _crear_grupo(idx=5, diff_2do=(6, 5)),  # E: 2°E diff +2 (peor segundo por stats)
    ]


class TestGenerar5GruposSegundoE:

    def test_segundo_grupo_e_pasa_directo_a_cuartos(self):
        """El 2do del grupo E (posición 4 en la lista) va siempre a cuartos[0].pareja2."""
        grupos = _cinco_grupos()
        pareja_2do_e_id = grupos[4].parejas[1].id  # id=52

        fixture = GeneradorFixtureFinales.generar_fixture(CATEGORIA, grupos)

        assert fixture.cuartos[0].pareja2 is not None
        assert fixture.cuartos[0].pareja2.id == pareja_2do_e_id

    def test_slot2_info_cuartos_1_indica_grupo_e(self):
        grupos = _cinco_grupos()
        fixture = GeneradorFixtureFinales.generar_fixture(CATEGORIA, grupos)
        assert fixture.cuartos[0].slot2_info == "2° Grupo E"

    def test_segundo_grupo_e_no_esta_en_octavos(self):
        """Ninguna pareja del grupo E aparece en los partidos de octavos."""
        grupos = _cinco_grupos()
        pareja_2do_e_id = grupos[4].parejas[1].id

        fixture = GeneradorFixtureFinales.generar_fixture(CATEGORIA, grupos)

        ids_en_octavos = {
            p.id
            for partido in fixture.octavos
            for p in [partido.pareja1, partido.pareja2]
            if p is not None
        }
        assert pareja_2do_e_id not in ids_en_octavos

    def test_segundos_de_a_d_van_a_octavos(self):
        """Las 4 parejas en octavos provienen únicamente de grupos A-D."""
        grupos = _cinco_grupos()
        ids_2do_a_d = {grupos[i].parejas[1].id for i in range(4)}  # ids 12, 22, 32, 42

        fixture = GeneradorFixtureFinales.generar_fixture(CATEGORIA, grupos)

        ids_en_octavos = {
            p.id
            for partido in fixture.octavos
            for p in [partido.pareja1, partido.pareja2]
            if p is not None
        }
        assert ids_en_octavos == ids_2do_a_d

    def test_estructura_5_grupos_intacta(self):
        """5 grupos → 2 octavos, 4 cuartos, 2 semis, 1 final."""
        grupos = _cinco_grupos()
        fixture = GeneradorFixtureFinales.generar_fixture(CATEGORIA, grupos)

        assert len(fixture.octavos) == 2
        assert len(fixture.cuartos) == 4
        assert len(fixture.semifinales) == 2
        assert fixture.final is not None
