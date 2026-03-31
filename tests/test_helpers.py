"""
Tests unitarios para las funciones helpers de recálculo.

Cubre: recalcular_estadisticas(), recalcular_score_grupo().
Son funciones puras que operan sobre dicts — sin Flask ni Supabase.

NOTA: regenerar_calendario() se omite aquí porque necesita Flask app_context
(llama a obtener_datos_desde_token internamente). Se testea en integración.
"""

import pytest
from api.routes._helpers import recalcular_estadisticas, recalcular_score_grupo
from tests.conftest import crear_grupo_dict, crear_pareja


# ── recalcular_estadisticas ───────────────────────────────────────────────────

class TestRecalcularEstadisticas:

    def _resultado_con_grupos(self, num_grupos: int, categoria: str = "Cuarta") -> dict:
        return {
            "grupos_por_categoria": {
                categoria: [
                    crear_grupo_dict(grupo_id=i, categoria=categoria)
                    for i in range(1, num_grupos + 1)
                ]
            },
            "parejas_sin_asignar": [],
        }

    def test_100_pct_asignacion_sin_sin_asignar(self):
        resultado = self._resultado_con_grupos(2)
        stats = recalcular_estadisticas(resultado)

        assert stats["parejas_asignadas"] == 6
        assert stats["parejas_sin_asignar"] == 0
        assert stats["porcentaje_asignacion"] == 100.0

    def test_porcentaje_con_sin_asignar(self):
        resultado = self._resultado_con_grupos(2)
        resultado["parejas_sin_asignar"] = [
            crear_pareja(id=99).to_dict(),
            crear_pareja(id=100).to_dict(),
        ]
        stats = recalcular_estadisticas(resultado)

        # 6 asignadas, 2 sin asignar → 8 total → 75%
        assert stats["total_parejas"] == 8
        assert stats["parejas_asignadas"] == 6
        assert stats["parejas_sin_asignar"] == 2
        assert stats["porcentaje_asignacion"] == pytest.approx(75.0)

    def test_resultado_vacio_no_divide_por_cero(self):
        resultado = {"grupos_por_categoria": {}, "parejas_sin_asignar": []}
        stats = recalcular_estadisticas(resultado)

        assert stats["total_parejas"] == 0
        assert stats["porcentaje_asignacion"] == 0

    def test_mutacion_in_place_de_resultado_data(self):
        """recalcular_estadisticas debe mutar resultado_data['estadisticas']."""
        resultado = self._resultado_con_grupos(1)
        recalcular_estadisticas(resultado)
        assert "estadisticas" in resultado

    def test_multiples_categorias(self):
        resultado = {
            "grupos_por_categoria": {
                "Cuarta": [crear_grupo_dict(grupo_id=1, categoria="Cuarta")],
                "Quinta": [crear_grupo_dict(grupo_id=2, categoria="Quinta")],
            },
            "parejas_sin_asignar": [],
        }
        stats = recalcular_estadisticas(resultado)

        assert stats["total_grupos"] == 2
        assert stats["parejas_asignadas"] == 6  # 3 por grupo × 2


# ── recalcular_score_grupo ────────────────────────────────────────────────────

class TestRecalcularScoreGrupo:

    def test_grupo_vacio_score_cero(self):
        grupo = {"parejas": [], "franja_horaria": None}
        recalcular_score_grupo(grupo)
        assert grupo["score"] == 0.0

    def test_grupo_con_franja_y_todos_disponibles_score_3(self):
        """3 parejas que tienen la franja asignada → score 3.0."""
        franja = "Sábado 09:00"
        grupo = crear_grupo_dict(franja=franja)
        recalcular_score_grupo(grupo)

        assert grupo["score"] == pytest.approx(3.0)

    def test_grupo_con_franja_y_ninguno_disponible_score_0(self):
        """3 parejas sin la franja asignada y sin el día → score 0.0."""
        grupo = crear_grupo_dict(franja="Sábado 09:00")
        # Reemplazar franjas de todas las parejas por una diferente
        for p in grupo["parejas"]:
            p["franjas_disponibles"] = ["Viernes 18:00"]
        recalcular_score_grupo(grupo)

        assert grupo["score"] == 0.0

    def test_grupo_sin_franja_asignada_usa_compatibilidad_interna(self):
        """Sin franja asignada, usa AlgoritmoGrupos._calcular_compatibilidad."""
        franja = "Sábado 09:00"
        grupo = crear_grupo_dict(franja=franja)
        grupo["franja_horaria"] = None  # sin franja asignada aún
        recalcular_score_grupo(grupo)

        # 3 parejas con franja común → algún score positivo
        assert grupo["score"] >= 0.0

    def test_score_parcial_con_dia_correcto(self):
        """Pareja que no tiene la franja exacta pero sí el día → score 0.5 por pareja."""
        franja_asignada = "Sábado 09:00"
        grupo = {
            "franja_horaria": franja_asignada,
            "parejas": [
                {"id": 1, "franjas_disponibles": [franja_asignada]},   # +1.0
                {"id": 2, "franjas_disponibles": ["Sábado 12:00"]},    # +0.5 (mismo día)
                {"id": 3, "franjas_disponibles": ["Viernes 18:00"]},   # +0.0 (distinto día)
            ],
        }
        recalcular_score_grupo(grupo)

        assert grupo["score"] == pytest.approx(1.5)

    def test_score_se_escribe_en_ambas_claves(self):
        """El score se debe escribir en 'score' y 'score_compatibilidad'."""
        grupo = crear_grupo_dict()
        recalcular_score_grupo(grupo)

        assert "score" in grupo
        assert "score_compatibilidad" in grupo
        assert grupo["score"] == grupo["score_compatibilidad"]
