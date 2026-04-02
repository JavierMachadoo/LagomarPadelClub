"""
Tests unitarios para AlgoritmoGrupos.

Cubre: formación de grupos, asignación de franjas, casos borde.
Tests PUROS — sin Flask ni Supabase.
"""

import pytest
from core.algoritmo import AlgoritmoGrupos
from core.models import Pareja
from config import CATEGORIAS, FRANJAS_HORARIAS
from tests.conftest import crear_pareja


# ── Helpers locales ───────────────────────────────────────────────────────────

def parejas_categoria(n: int, categoria: str = "Cuarta", franja: str = "Sábado 09:00") -> list:
    return [crear_pareja(id=i + 1, categoria=categoria, franjas=[franja]) for i in range(n)]


# ── Formación de grupos ───────────────────────────────────────────────────────

class TestFormacionGrupos:

    def test_6_parejas_forman_2_grupos_completos(self):
        parejas = parejas_categoria(6)
        resultado = AlgoritmoGrupos(parejas).ejecutar()

        grupos = resultado.grupos_por_categoria.get("Cuarta", [])
        assert len(grupos) == 2
        assert all(g.esta_completo() for g in grupos)
        assert resultado.parejas_sin_asignar == []

    def test_9_parejas_con_3_canchas_forman_3_grupos_completos(self):
        """
        Con num_canchas=3 se pueden asignar 3 grupos a la misma franja.
        La restricción de canchas es el límite real, no el número de parejas.
        """
        parejas = parejas_categoria(9)
        resultado = AlgoritmoGrupos(parejas, num_canchas=3).ejecutar()

        grupos = resultado.grupos_por_categoria.get("Cuarta", [])
        assert len(grupos) == 3
        assert all(g.esta_completo() for g in grupos)
        assert resultado.parejas_sin_asignar == []

    def test_9_parejas_con_2_canchas_limita_a_2_grupos_por_franja(self):
        """
        Con num_canchas=2 (default) y 9 parejas en la misma franja,
        solo se forman 2 grupos completos (3 parejas quedan sin asignar).
        Esto documenta la restricción de capacidad por cancha.
        """
        parejas = parejas_categoria(9)
        resultado = AlgoritmoGrupos(parejas, num_canchas=2).ejecutar()

        sin_asignar_cuarta = [p for p in resultado.parejas_sin_asignar if p.categoria == "Cuarta"]
        grupos = resultado.grupos_por_categoria.get("Cuarta", [])
        # No más grupos que canchas disponibles en la misma franja
        assert len(grupos) <= 2
        assert len(sin_asignar_cuarta) >= 3

    def test_7_parejas_quedan_1_sin_asignar(self):
        parejas = parejas_categoria(7)
        resultado = AlgoritmoGrupos(parejas).ejecutar()

        grupos = resultado.grupos_por_categoria.get("Cuarta", [])
        sin_asignar_cuarta = [p for p in resultado.parejas_sin_asignar if p.categoria == "Cuarta"]
        # 7 // 3 = 2 grupos completos (6 parejas), 1 sin asignar
        assert len(grupos) == 2
        assert len(sin_asignar_cuarta) == 1

    def test_2_parejas_no_forman_grupos(self):
        parejas = parejas_categoria(2)
        resultado = AlgoritmoGrupos(parejas).ejecutar()

        grupos = resultado.grupos_por_categoria.get("Cuarta", [])
        assert len(grupos) == 0
        assert len(resultado.parejas_sin_asignar) == 2

    def test_lista_vacia_devuelve_resultado_vacio(self):
        resultado = AlgoritmoGrupos([]).ejecutar()
        assert resultado.grupos_por_categoria == {}
        assert resultado.parejas_sin_asignar == []

    def test_categorias_separadas(self):
        cuartas = parejas_categoria(3, "Cuarta", "Sábado 09:00")
        quintas = parejas_categoria(3, "Quinta", "Viernes 18:00")
        resultado = AlgoritmoGrupos(cuartas + quintas).ejecutar()

        assert "Cuarta" in resultado.grupos_por_categoria
        assert "Quinta" in resultado.grupos_por_categoria
        assert len(resultado.grupos_por_categoria["Cuarta"]) == 1
        assert len(resultado.grupos_por_categoria["Quinta"]) == 1

    def test_categorias_no_reconocidas_se_descartan(self):
        """Parejas con categoría fuera de CATEGORIAS no deben generar grupos."""
        parejas = [
            crear_pareja(id=i, categoria="Décima", franjas=["Sábado 09:00"])
            for i in range(6)
        ]
        resultado = AlgoritmoGrupos(parejas).ejecutar()
        assert "Décima" not in resultado.grupos_por_categoria


# ── Compatibilidad y scoring ──────────────────────────────────────────────────

class TestCompatibilidad:

    def test_3_parejas_misma_franja_score_mayor_0(self):
        """Grupo con franja compartida debe tener score > 0."""
        parejas = parejas_categoria(3, franja="Viernes 18:00")
        resultado = AlgoritmoGrupos(parejas).ejecutar()

        grupos = resultado.grupos_por_categoria.get("Cuarta", [])
        assert len(grupos) == 1
        assert grupos[0].score_compatibilidad > 0

    def test_parejas_sin_franja_comun_son_asignadas_de_todas_formas(self):
        """El algoritmo no debe dejar parejas sin asignar solo por incompatibilidad horaria."""
        parejas = [
            crear_pareja(id=1, franjas=["Viernes 18:00"]),
            crear_pareja(id=2, franjas=["Sábado 12:00"]),
            crear_pareja(id=3, franjas=["Sábado 19:00"]),
        ]
        resultado = AlgoritmoGrupos(parejas).ejecutar()
        total_asignadas = sum(len(g.parejas) for gs in resultado.grupos_por_categoria.values() for g in gs)
        assert total_asignadas == 3

    @pytest.mark.parametrize("franja", FRANJAS_HORARIAS)
    def test_franja_asignada_viene_de_franjas_horarias(self, franja):
        """La franja asignada a un grupo debe ser una franja válida del sistema."""
        parejas = [crear_pareja(id=i, franjas=[franja]) for i in range(1, 4)]
        resultado = AlgoritmoGrupos(parejas).ejecutar()

        for gs in resultado.grupos_por_categoria.values():
            for g in gs:
                assert g.franja_horaria in FRANJAS_HORARIAS or g.franja_horaria is None


# ── Estadísticas ──────────────────────────────────────────────────────────────

class TestEstadisticasAlgoritmo:

    def test_estadisticas_porcentaje_100_sin_sin_asignar(self):
        parejas = parejas_categoria(6)
        resultado = AlgoritmoGrupos(parejas).ejecutar()

        assert resultado.estadisticas["porcentaje_asignacion"] == 100.0
        assert resultado.estadisticas["parejas_sin_asignar"] == 0

    def test_estadisticas_total_correcto(self):
        parejas = parejas_categoria(7)
        resultado = AlgoritmoGrupos(parejas).ejecutar()

        assert resultado.estadisticas["total_parejas"] == 7
        assert resultado.estadisticas["parejas_asignadas"] == 6

    def test_estadisticas_total_grupos(self):
        parejas = parejas_categoria(6)
        resultado = AlgoritmoGrupos(parejas).ejecutar()

        assert resultado.estadisticas["total_grupos"] == 2
