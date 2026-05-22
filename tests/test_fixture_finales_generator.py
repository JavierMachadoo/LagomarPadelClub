"""
Tests unitarios para GeneradorFixtureFinales._generar_5_grupos().

Con 5 grupos el bracket es fijo por letra de grupo:
  OF.1: 2°C vs 2°D  →  ganador alimenta C.2
  OF.2: 2°A vs 2°B  →  ganador alimenta C.3
  C.1:  1°A vs 2°E
  C.2:  1°B vs Ganador OF.1
  C.3:  1°C vs Ganador OF.2
  C.4:  1°D vs 1°E
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
    Crea un grupo (A=1, B=2, C=3, D=4, E=5) con resultados completos:
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
    """Grupos A–E con stats variadas para detectar si se usa ranking (no debería)."""
    return [
        _crear_grupo(idx=1, diff_2do=(6, 0)),  # A: 2°A diff +12 (el mejor segundo por stats)
        _crear_grupo(idx=2, diff_2do=(6, 3)),  # B
        _crear_grupo(idx=3, diff_2do=(6, 3)),  # C
        _crear_grupo(idx=4, diff_2do=(6, 3)),  # D
        _crear_grupo(idx=5, diff_2do=(6, 5)),  # E: 2°E diff +2  (el peor segundo por stats)
    ]


class TestGenerar5GruposBracketFijo:

    # ── Octavos ────────────────────────────────────────────────────────────────

    def test_of1_es_segundo_c_vs_segundo_d(self):
        """OF.1 siempre enfrenta el 2do de C contra el 2do de D."""
        grupos = _cinco_grupos()
        id_2do_c = grupos[2].parejas[1].id  # grupo C = índice 2
        id_2do_d = grupos[3].parejas[1].id  # grupo D = índice 3

        fixture = GeneradorFixtureFinales.generar_fixture(CATEGORIA, grupos)

        of1 = fixture.octavos[0]
        assert {of1.pareja1.id, of1.pareja2.id} == {id_2do_c, id_2do_d}

    def test_of2_es_segundo_a_vs_segundo_b(self):
        """OF.2 siempre enfrenta el 2do de A contra el 2do de B."""
        grupos = _cinco_grupos()
        id_2do_a = grupos[0].parejas[1].id
        id_2do_b = grupos[1].parejas[1].id

        fixture = GeneradorFixtureFinales.generar_fixture(CATEGORIA, grupos)

        of2 = fixture.octavos[1]
        assert {of2.pareja1.id, of2.pareja2.id} == {id_2do_a, id_2do_b}

    def test_of1_slot_info(self):
        grupos = _cinco_grupos()
        fixture = GeneradorFixtureFinales.generar_fixture(CATEGORIA, grupos)
        of1 = fixture.octavos[0]
        assert of1.slot1_info == "2° C"
        assert of1.slot2_info == "2° D"

    def test_of2_slot_info(self):
        grupos = _cinco_grupos()
        fixture = GeneradorFixtureFinales.generar_fixture(CATEGORIA, grupos)
        of2 = fixture.octavos[1]
        assert of2.slot1_info == "2° A"
        assert of2.slot2_info == "2° B"

    # ── Cuartos ────────────────────────────────────────────────────────────────

    def test_c1_es_primero_a_vs_segundo_e(self):
        """C.1 enfrenta el 1° de A contra el 2° de E, sin importar el ranking."""
        grupos = _cinco_grupos()
        id_1ro_a = grupos[0].parejas[0].id   # 1°A
        id_2do_e = grupos[4].parejas[1].id   # 2°E (el peor segundo por stats)

        fixture = GeneradorFixtureFinales.generar_fixture(CATEGORIA, grupos)

        c1 = fixture.cuartos[0]
        assert c1.pareja1.id == id_1ro_a
        assert c1.pareja2.id == id_2do_e

    def test_c1_slot_info(self):
        grupos = _cinco_grupos()
        fixture = GeneradorFixtureFinales.generar_fixture(CATEGORIA, grupos)
        c1 = fixture.cuartos[0]
        assert c1.slot1_info == "1° A"
        assert c1.slot2_info == "2° E"

    def test_c2_es_primero_b_vs_ganador_of1(self):
        """C.2 tiene al 1°B como pareja1; pareja2 llega del ganador de OF.1."""
        grupos = _cinco_grupos()
        id_1ro_b = grupos[1].parejas[0].id

        fixture = GeneradorFixtureFinales.generar_fixture(CATEGORIA, grupos)

        c2 = fixture.cuartos[1]
        assert c2.pareja1.id == id_1ro_b
        assert c2.pareja2 is None           # se rellena al propagar OF.1
        assert c2.slot2_info == "Ganador OF.1"

    def test_c3_es_primero_c_vs_ganador_of2(self):
        """C.3 tiene al 1°C como pareja1; pareja2 llega del ganador de OF.2."""
        grupos = _cinco_grupos()
        id_1ro_c = grupos[2].parejas[0].id

        fixture = GeneradorFixtureFinales.generar_fixture(CATEGORIA, grupos)

        c3 = fixture.cuartos[2]
        assert c3.pareja1.id == id_1ro_c
        assert c3.pareja2 is None
        assert c3.slot2_info == "Ganador OF.2"

    def test_c4_es_primero_d_vs_primero_e(self):
        """C.4 enfrenta los primeros de D y E entre sí."""
        grupos = _cinco_grupos()
        id_1ro_d = grupos[3].parejas[0].id
        id_1ro_e = grupos[4].parejas[0].id

        fixture = GeneradorFixtureFinales.generar_fixture(CATEGORIA, grupos)

        c4 = fixture.cuartos[3]
        assert {c4.pareja1.id, c4.pareja2.id} == {id_1ro_d, id_1ro_e}

    def test_c4_slot_info(self):
        grupos = _cinco_grupos()
        fixture = GeneradorFixtureFinales.generar_fixture(CATEGORIA, grupos)
        c4 = fixture.cuartos[3]
        assert c4.slot1_info == "1° D"
        assert c4.slot2_info == "1° E"

    def test_segundo_e_no_esta_en_octavos(self):
        """2°E no aparece en ningún partido de octavos."""
        grupos = _cinco_grupos()
        id_2do_e = grupos[4].parejas[1].id

        fixture = GeneradorFixtureFinales.generar_fixture(CATEGORIA, grupos)

        ids_en_octavos = {
            p.id
            for partido in fixture.octavos
            for p in [partido.pareja1, partido.pareja2]
            if p is not None
        }
        assert id_2do_e not in ids_en_octavos

    # ── Estructura general ─────────────────────────────────────────────────────

    def test_estructura_5_grupos(self):
        """5 grupos → 2 octavos, 4 cuartos, 2 semis, 1 final."""
        grupos = _cinco_grupos()
        fixture = GeneradorFixtureFinales.generar_fixture(CATEGORIA, grupos)

        assert len(fixture.octavos) == 2
        assert len(fixture.cuartos) == 4
        assert len(fixture.semifinales) == 2
        assert fixture.final is not None
