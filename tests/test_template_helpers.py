"""
Tests para utils/template_helpers.py — build_franjas_finales.

TDD: RED → GREEN → REFACTOR
"""
import pytest
from utils.template_helpers import build_franjas_finales


# ── Factories ────────────────────────────────────────────────────────────────

def _make_partido(pid, p1_id, p1_nombre, p2_id, p2_nombre, sets=None, ganador_id=None):
    """Construye un dict que simula PartidoFinal.to_dict() de finales."""
    return {
        'id': pid,
        'pareja1': {'id': p1_id, 'nombre': p1_nombre},
        'pareja2': {'id': p2_id, 'nombre': p2_nombre},
        'sets': sets or [],
        'ganador': {'id': ganador_id} if ganador_id is not None else None,
    }


def _make_slot(partido_id, hora='10:00', categoria='Tercera', fase='Final'):
    """Construye un dict que simula PartidoCalendarizado.to_dict()."""
    return {
        'partido_id': partido_id,
        'categoria': categoria,
        'fase': fase,
        'numero_partido': 1,
        'pareja1': None,
        'pareja2': None,
        'hora_inicio': hora,
        'hora_fin': f"{int(hora[:2]) + 1:02d}:00",
        'cancha': 1,
    }


def _make_calendario(slots_c1=None, slots_c2=None):
    """Construye un calendario mínimo para los tests."""
    return {
        'cancha_1': slots_c1 or [],
        'cancha_2': slots_c2 or [],
        'sin_asignar': [],
    }


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestBuildFranjasFinalesCalendarioVacio:
    def test_calendario_vacio_devuelve_lista_vacia(self):
        result = build_franjas_finales({})
        assert result == []

    def test_calendario_none_devuelve_lista_vacia(self):
        result = build_franjas_finales(None)
        assert result == []

    def test_calendario_sin_partidos_devuelve_lista_vacia(self):
        cal = _make_calendario()
        result = build_franjas_finales(cal)
        assert result == []


class TestBuildFranjasFinalesSinFixtures:
    """Sin fixtures, los slots se devuelven sin enriquecer (backward-compat)."""

    def test_sin_fixtures_no_agrega_sets(self):
        slot = _make_slot('cuartos_1')
        cal = _make_calendario(slots_c1=[slot])

        result = build_franjas_finales(cal)

        assert len(result) == 1
        hora, c1, c2 = result[0]
        assert hora == '10:00'
        assert c1 is not None
        assert 'sets' not in c1

    def test_sin_fixtures_no_agrega_ganador_nombre(self):
        slot = _make_slot('cuartos_1')
        cal = _make_calendario(slots_c1=[slot])

        result = build_franjas_finales(cal)

        _, c1, c2 = result[0]
        assert 'ganador_nombre' not in c1

    def test_sin_fixtures_devuelve_ninguna_en_cancha2_cuando_no_hay(self):
        slot = _make_slot('cuartos_1', hora='10:00')
        cal = _make_calendario(slots_c1=[slot])

        result = build_franjas_finales(cal)

        hora, c1, c2 = result[0]
        assert c2 is None

    def test_fixtures_none_equivale_a_sin_fixtures(self):
        slot = _make_slot('cuartos_1')
        cal = _make_calendario(slots_c1=[slot])

        result = build_franjas_finales(cal, fixtures=None)

        _, c1, _ = result[0]
        assert 'sets' not in c1


class TestBuildFranjasFinalesConFixtures:
    """Con fixtures, cada slot cuyo partido_id matchea se enriquece."""

    def test_enriquece_sets_cuando_partido_tiene_resultado(self):
        partido = _make_partido(
            'cuartos_1', 10, 'Pareja A', 20, 'Pareja B',
            sets=[{'pareja1': 6, 'pareja2': 3}, {'pareja1': 7, 'pareja2': 5}],
            ganador_id=10,
        )
        fixtures = {'Tercera': {'cuartos': [partido]}}
        slot = _make_slot('cuartos_1', hora='10:00', categoria='Tercera', fase='Cuartos de Final')
        cal = _make_calendario(slots_c1=[slot])

        result = build_franjas_finales(cal, fixtures=fixtures)

        _, c1, _ = result[0]
        assert c1['sets'] == [{'pareja1': 6, 'pareja2': 3}, {'pareja1': 7, 'pareja2': 5}]

    def test_enriquece_ganador_nombre_cuando_partido_tiene_resultado(self):
        partido = _make_partido(
            'cuartos_1', 10, 'Pareja A', 20, 'Pareja B',
            sets=[{'pareja1': 6, 'pareja2': 3}],
            ganador_id=10,
        )
        fixtures = {'Tercera': {'cuartos': [partido]}}
        slot = _make_slot('cuartos_1', hora='10:00', categoria='Tercera', fase='Cuartos de Final')
        cal = _make_calendario(slots_c1=[slot])

        result = build_franjas_finales(cal, fixtures=fixtures)

        _, c1, _ = result[0]
        assert c1['ganador_nombre'] == 'Pareja A'

    def test_ganador_nombre_resuelve_pareja2_cuando_gana_pareja2(self):
        partido = _make_partido(
            'semis_1', 10, 'Pareja A', 20, 'Pareja B',
            sets=[{'pareja1': 3, 'pareja2': 6}],
            ganador_id=20,
        )
        fixtures = {'Cuarta': {'semifinales': [partido]}}
        slot = _make_slot('semis_1', hora='12:00', categoria='Cuarta', fase='Semifinal')
        cal = _make_calendario(slots_c1=[slot])

        result = build_franjas_finales(cal, fixtures=fixtures)

        _, c1, _ = result[0]
        assert c1['ganador_nombre'] == 'Pareja B'

    def test_slots_sin_partido_id_matcheante_no_se_enriquecen(self):
        partido = _make_partido(
            'cuartos_1', 10, 'Pareja A', 20, 'Pareja B',
            sets=[{'pareja1': 6, 'pareja2': 3}],
            ganador_id=10,
        )
        fixtures = {'Tercera': {'cuartos': [partido]}}
        # slot con partido_id diferente
        slot = _make_slot('cuartos_99', hora='10:00')
        cal = _make_calendario(slots_c1=[slot])

        result = build_franjas_finales(cal, fixtures=fixtures)

        _, c1, _ = result[0]
        assert 'sets' not in c1
        assert 'ganador_nombre' not in c1

    def test_enriquece_final_en_clave_final(self):
        """La fase 'final' en fixtures es un dict directo (no lista)."""
        partido = _make_partido(
            'final_1', 10, 'Pareja A', 20, 'Pareja B',
            sets=[{'pareja1': 6, 'pareja2': 4}, {'pareja1': 6, 'pareja2': 3}],
            ganador_id=10,
        )
        fixtures = {'Tercera': {'final': partido}}
        slot = _make_slot('final_1', hora='20:00', categoria='Tercera', fase='Final')
        cal = _make_calendario(slots_c1=[slot])

        result = build_franjas_finales(cal, fixtures=fixtures)

        _, c1, _ = result[0]
        assert c1['sets'] == [{'pareja1': 6, 'pareja2': 4}, {'pareja1': 6, 'pareja2': 3}]
        assert c1['ganador_nombre'] == 'Pareja A'

    def test_orden_cronologico_correcto(self):
        slot_10 = _make_slot('p1', hora='10:00')
        slot_12 = _make_slot('p2', hora='12:00')
        cal = _make_calendario(slots_c1=[slot_12, slot_10])  # desordenados intencionalmente

        result = build_franjas_finales(cal)

        horas = [r[0] for r in result]
        assert horas == sorted(horas)

    def test_ganador_none_cuando_sin_resultado(self):
        partido = _make_partido('cuartos_1', 10, 'Pareja A', 20, 'Pareja B')
        fixtures = {'Tercera': {'cuartos': [partido]}}
        slot = _make_slot('cuartos_1')
        cal = _make_calendario(slots_c1=[slot])

        result = build_franjas_finales(cal, fixtures=fixtures)

        _, c1, _ = result[0]
        assert c1['sets'] == []
        assert c1['ganador_nombre'] is None
