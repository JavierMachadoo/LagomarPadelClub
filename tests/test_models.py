"""
Tests unitarios para los modelos del dominio.

Cubre: Pareja, Grupo, ResultadoPartido.
Son tests PUROS — sin Flask ni Supabase.
"""

import pytest
from core.models import Pareja, Grupo, ResultadoPartido, PosicionGrupo
from tests.conftest import crear_pareja, crear_grupo


# ── ResultadoPartido ──────────────────────────────────────────────────────────

class TestResultadoPartido:

    def test_esta_completo_sets_directos(self):
        r = ResultadoPartido(
            pareja1_id=1, pareja2_id=2,
            sets_pareja1=2, sets_pareja2=0,
            games_set1_pareja1=6, games_set1_pareja2=3,
            games_set2_pareja1=6, games_set2_pareja2=2,
        )
        assert r.esta_completo() is True

    def test_esta_incompleto_sin_sets(self):
        r = ResultadoPartido(pareja1_id=1, pareja2_id=2)
        assert r.esta_completo() is False

    def test_esta_incompleto_empate_sin_tiebreak(self):
        r = ResultadoPartido(
            pareja1_id=1, pareja2_id=2,
            sets_pareja1=1, sets_pareja2=1,
            games_set1_pareja1=6, games_set1_pareja2=3,
            games_set2_pareja1=3, games_set2_pareja2=6,
        )
        assert r.esta_completo() is False

    def test_esta_completo_empate_con_tiebreak(self):
        r = ResultadoPartido(
            pareja1_id=1, pareja2_id=2,
            sets_pareja1=1, sets_pareja2=1,
            games_set1_pareja1=6, games_set1_pareja2=3,
            games_set2_pareja1=3, games_set2_pareja2=6,
            tiebreak_pareja1=10, tiebreak_pareja2=7,
        )
        assert r.esta_completo() is True

    def test_ganador_pareja1_2_sets(self):
        r = ResultadoPartido(
            pareja1_id=1, pareja2_id=2,
            sets_pareja1=2, sets_pareja2=0,
            games_set1_pareja1=6, games_set1_pareja2=1,
            games_set2_pareja1=6, games_set2_pareja2=2,
        )
        assert r.calcular_ganador() == 1

    def test_ganador_pareja2_2_sets(self):
        r = ResultadoPartido(
            pareja1_id=1, pareja2_id=2,
            sets_pareja1=0, sets_pareja2=2,
            games_set1_pareja1=2, games_set1_pareja2=6,
            games_set2_pareja1=1, games_set2_pareja2=6,
        )
        assert r.calcular_ganador() == 2

    def test_ganador_por_tiebreak(self):
        r = ResultadoPartido(
            pareja1_id=1, pareja2_id=2,
            sets_pareja1=1, sets_pareja2=1,
            games_set1_pareja1=6, games_set1_pareja2=3,
            games_set2_pareja1=3, games_set2_pareja2=6,
            tiebreak_pareja1=10, tiebreak_pareja2=7,
        )
        assert r.calcular_ganador() == 1

    def test_tiebreak_empatado_lanza_error(self):
        r = ResultadoPartido(
            pareja1_id=1, pareja2_id=2,
            sets_pareja1=1, sets_pareja2=1,
            games_set1_pareja1=6, games_set1_pareja2=3,
            games_set2_pareja1=3, games_set2_pareja2=6,
            tiebreak_pareja1=10, tiebreak_pareja2=10,
        )
        with pytest.raises(ValueError, match="Tiebreak no puede terminar en empate"):
            r.calcular_ganador()

    def test_ganador_none_si_incompleto(self):
        r = ResultadoPartido(pareja1_id=1, pareja2_id=2)
        assert r.calcular_ganador() is None

    def test_total_games_pareja1(self):
        r = ResultadoPartido(
            pareja1_id=1, pareja2_id=2,
            games_set1_pareja1=6, games_set1_pareja2=3,
            games_set2_pareja1=4, games_set2_pareja2=6,
        )
        assert r.total_games_pareja(1) == 10

    def test_roundtrip_to_from_dict(self):
        r = ResultadoPartido(
            pareja1_id=1, pareja2_id=2,
            sets_pareja1=2, sets_pareja2=0,
            games_set1_pareja1=6, games_set1_pareja2=3,
            games_set2_pareja1=6, games_set2_pareja2=2,
        )
        r2 = ResultadoPartido.from_dict(r.to_dict())
        assert r2.pareja1_id == r.pareja1_id
        assert r2.sets_pareja1 == r.sets_pareja1


# ── Pareja ────────────────────────────────────────────────────────────────────

class TestPareja:

    def test_creacion_basica(self):
        p = crear_pareja(id=5, categoria="Quinta", franjas=["Viernes 18:00"])
        assert p.id == 5
        assert p.categoria == "Quinta"
        assert p.franjas_disponibles == ["Viernes 18:00"]

    def test_hash_por_id(self):
        p1 = crear_pareja(id=1)
        p2 = crear_pareja(id=1, nombre="Otro nombre")
        assert p1 == p2
        assert hash(p1) == hash(p2)

    def test_parejas_distintos_id_no_iguales(self):
        p1 = crear_pareja(id=1)
        p2 = crear_pareja(id=2)
        assert p1 != p2

    def test_roundtrip_to_from_dict(self):
        p = Pareja(
            id=7, nombre="Test / Pareja", telefono="600111222",
            categoria="Tercera", franjas_disponibles=["Sábado 12:00"],
            jugador1="Test", jugador2="Pareja",
        )
        p2 = Pareja.from_dict(p.to_dict())
        assert p2.id == p.id
        assert p2.nombre == p.nombre
        assert p2.franjas_disponibles == p.franjas_disponibles

    def test_from_dict_franjas_como_string(self):
        data = {
            "id": 1, "nombre": "A / B", "telefono": "",
            "categoria": "Cuarta", "franjas_disponibles": "Sábado 09:00,Sábado 12:00",
        }
        p = Pareja.from_dict(data)
        assert p.franjas_disponibles == ["Sábado 09:00", "Sábado 12:00"]

    def test_from_dict_franjas_string_vacio(self):
        data = {
            "id": 1, "nombre": "A / B", "telefono": "",
            "categoria": "Cuarta", "franjas_disponibles": "",
        }
        p = Pareja.from_dict(data)
        assert p.franjas_disponibles == []


# ── Grupo ─────────────────────────────────────────────────────────────────────

class TestGrupo:

    def test_esta_completo_con_3_parejas(self):
        g = crear_grupo(num_parejas=3)
        assert g.esta_completo() is True

    def test_no_esta_completo_con_2_parejas(self):
        g = crear_grupo(num_parejas=2)
        assert g.esta_completo() is False

    def test_generar_partidos_crea_3_partidos(self):
        g = crear_grupo(num_parejas=3)
        assert len(g.partidos) == 3

    def test_generar_partidos_no_repite_pares(self):
        g = crear_grupo(num_parejas=3)
        pares = set()
        for p1, p2 in g.partidos:
            par = frozenset([p1.id, p2.id])
            assert par not in pares, f"Par duplicado: {par}"
            pares.add(par)

    def test_todos_resultados_completos_false_sin_resultados(self):
        g = crear_grupo(num_parejas=3)
        assert g.todos_resultados_completos() is False

    def test_todos_resultados_completos_true_con_3_resultados(self):
        g = crear_grupo(num_parejas=3)
        p1, p2, p3 = g.parejas
        for a, b in [(p1, p2), (p1, p3), (p2, p3)]:
            r = ResultadoPartido(
                pareja1_id=a.id, pareja2_id=b.id,
                sets_pareja1=2, sets_pareja2=0,
                games_set1_pareja1=6, games_set1_pareja2=3,
                games_set2_pareja1=6, games_set2_pareja2=2,
            )
            g.agregar_resultado(r)
        assert g.todos_resultados_completos() is True

    def test_resultado_key_es_deterministico(self):
        g = crear_grupo(num_parejas=3)
        key1 = g.get_resultado_key(1, 5)
        key2 = g.get_resultado_key(5, 1)
        assert key1 == key2

    def test_agregar_pareja_rechaza_si_lleno(self):
        g = crear_grupo(num_parejas=3)
        extra = crear_pareja(id=999)
        g.agregar_pareja(extra)
        assert len(g.parejas) == 3  # no se agregó

    def test_roundtrip_to_from_dict(self):
        g = crear_grupo(num_parejas=3)
        g2 = Grupo.from_dict(g.to_dict())
        assert g2.id == g.id
        assert g2.categoria == g.categoria
        assert len(g2.parejas) == 3
