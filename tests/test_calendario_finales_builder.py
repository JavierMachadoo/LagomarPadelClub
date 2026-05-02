"""
Tests para utils/calendario_finales_builder.py — sincronizar_parejas + _resolver_ganador_nombre.

TDD: RED → GREEN → REFACTOR
"""
import pytest
from utils.calendario_finales_builder import (
    GeneradorCalendarioFinales,
    _resolver_ganador_nombre,
)


# ── Factories ────────────────────────────────────────────────────────────────

def _make_partido_fixture(pid, p1_id, p1_nombre, p2_id, p2_nombre, sets=None, ganador_id=None):
    """Simula PartidoFinal.to_dict() con campos relevantes para el builder."""
    return {
        'id': pid,
        'pareja1': {'id': p1_id, 'nombre': p1_nombre},
        'pareja2': {'id': p2_id, 'nombre': p2_nombre},
        'sets': sets or [],
        'ganador': {'id': ganador_id} if ganador_id is not None else None,
    }


def _make_slot_cal(partido_id, hora='10:00', categoria='Tercera', fase='Cuartos de Final'):
    """Simula un entry del calendario (cancha_1 / cancha_2)."""
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


def _make_fixtures(categoria, fase_key, partidos):
    """Construye fixtures_finales mínimo para los tests."""
    return {categoria: {fase_key: partidos}}


def _make_fixtures_con_final(categoria, partido):
    """Construye fixtures_finales con un partido final (dict directo, no lista)."""
    return {categoria: {'final': partido}}


# ── Tests: _resolver_ganador_nombre ──────────────────────────────────────────

class TestResolverGanadorNombre:
    def test_devuelve_pareja1_cuando_id_match(self):
        partido = _make_partido_fixture('c1', 10, 'Pérez/López', 20, 'Martín/Ruiz')
        ganador = {'id': 10}
        assert _resolver_ganador_nombre(partido, ganador) == 'Pérez/López'

    def test_devuelve_pareja2_cuando_id_match(self):
        partido = _make_partido_fixture('c1', 10, 'Pérez/López', 20, 'Martín/Ruiz')
        ganador = {'id': 20}
        assert _resolver_ganador_nombre(partido, ganador) == 'Martín/Ruiz'

    def test_devuelve_none_cuando_ganador_es_none(self):
        partido = _make_partido_fixture('c1', 10, 'Pérez/López', 20, 'Martín/Ruiz')
        assert _resolver_ganador_nombre(partido, None) is None

    def test_devuelve_none_cuando_id_no_matchea_ninguna_pareja(self):
        """Defensa ante fixture inconsistente (ganador.id no coincide con ninguna pareja)."""
        partido = _make_partido_fixture('c1', 10, 'Pérez/López', 20, 'Martín/Ruiz')
        ganador = {'id': 99}  # ID fantasma
        assert _resolver_ganador_nombre(partido, ganador) is None

    def test_devuelve_none_cuando_ganador_sin_id(self):
        partido = _make_partido_fixture('c1', 10, 'Pérez/López', 20, 'Martín/Ruiz')
        ganador = {}  # sin clave 'id'
        assert _resolver_ganador_nombre(partido, ganador) is None

    def test_maneja_pareja1_none_en_partido(self):
        partido = {'id': 'c1', 'pareja1': None, 'pareja2': {'id': 20, 'nombre': 'Martín/Ruiz'}}
        ganador = {'id': 20}
        assert _resolver_ganador_nombre(partido, ganador) == 'Martín/Ruiz'


# ── Tests: sincronizar_parejas ────────────────────────────────────────────────

class TestSincronizarParejas:
    def test_copia_sets_cuando_partido_tiene_resultado(self):
        sets = [{'pareja1': 6, 'pareja2': 3}, {'pareja1': 6, 'pareja2': 4}]
        partido = _make_partido_fixture('cuartos_1', 10, 'Pérez/López', 20, 'Martín/Ruiz',
                                        sets=sets, ganador_id=10)
        fixtures = _make_fixtures('Tercera', 'cuartos', [partido])
        slot = _make_slot_cal('cuartos_1')
        calendario = {'cancha_1': [slot], 'cancha_2': [], 'sin_asignar': []}

        result = GeneradorCalendarioFinales.sincronizar_parejas(calendario, fixtures)

        entry = result['cancha_1'][0]
        assert entry['sets'] == sets

    def test_copia_ganador_nombre_cuando_partido_tiene_resultado(self):
        sets = [{'pareja1': 6, 'pareja2': 3}]
        partido = _make_partido_fixture('cuartos_1', 10, 'Pérez/López', 20, 'Martín/Ruiz',
                                        sets=sets, ganador_id=10)
        fixtures = _make_fixtures('Tercera', 'cuartos', [partido])
        slot = _make_slot_cal('cuartos_1')
        calendario = {'cancha_1': [slot], 'cancha_2': [], 'sin_asignar': []}

        result = GeneradorCalendarioFinales.sincronizar_parejas(calendario, fixtures)

        entry = result['cancha_1'][0]
        assert entry['ganador_nombre'] == 'Pérez/López'

    def test_no_falla_cuando_partido_sin_resultado(self):
        partido = _make_partido_fixture('cuartos_1', 10, 'Pérez/López', 20, 'Martín/Ruiz')
        fixtures = _make_fixtures('Tercera', 'cuartos', [partido])
        slot = _make_slot_cal('cuartos_1')
        calendario = {'cancha_1': [slot], 'cancha_2': [], 'sin_asignar': []}

        result = GeneradorCalendarioFinales.sincronizar_parejas(calendario, fixtures)

        entry = result['cancha_1'][0]
        assert entry['sets'] == []
        assert entry['ganador'] is None
        assert entry['ganador_nombre'] is None

    def test_no_modifica_slots_sin_partido_id_matcheante(self):
        partido = _make_partido_fixture('cuartos_1', 10, 'Pérez/López', 20, 'Martín/Ruiz',
                                        sets=[{'pareja1': 6, 'pareja2': 3}], ganador_id=10)
        fixtures = _make_fixtures('Tercera', 'cuartos', [partido])
        # Slot con partido_id distinto — no debe recibir sets/ganador
        slot = _make_slot_cal('cuartos_99')
        calendario = {'cancha_1': [slot], 'cancha_2': [], 'sin_asignar': []}

        result = GeneradorCalendarioFinales.sincronizar_parejas(calendario, fixtures)

        entry = result['cancha_1'][0]
        assert 'sets' not in entry
        assert 'ganador_nombre' not in entry

    def test_enriquece_en_cancha_2_tambien(self):
        sets = [{'pareja1': 7, 'pareja2': 5}]
        partido = _make_partido_fixture('semis_1', 30, 'Alpha', 40, 'Beta',
                                        sets=sets, ganador_id=40)
        fixtures = _make_fixtures('Cuarta', 'semifinales', [partido])
        slot = _make_slot_cal('semis_1', hora='14:00', categoria='Cuarta', fase='Semifinal')
        calendario = {'cancha_1': [], 'cancha_2': [slot], 'sin_asignar': []}

        result = GeneradorCalendarioFinales.sincronizar_parejas(calendario, fixtures)

        entry = result['cancha_2'][0]
        assert entry['sets'] == sets
        assert entry['ganador_nombre'] == 'Beta'
