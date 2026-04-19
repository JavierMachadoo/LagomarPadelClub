"""
Tests para reordenar_grupos: unitarios del service + integración de la ruta.
"""

import json
import pytest
from unittest.mock import patch
from services import grupo_service
from services.exceptions import ServiceError
from tests.conftest import crear_grupo_dict


def _resultado_con_grupos(ids: list[int], categoria: str = "Cuarta") -> dict:
    return {
        "grupos_por_categoria": {
            categoria: [
                {**crear_grupo_dict(grupo_id=gid, categoria=categoria), "id": gid}
                for gid in ids
            ]
        },
        "parejas_sin_asignar": [],
        "calendario": {},
    }


class TestReordenarGrupos:

    def test_reordena_lista_correctamente(self):
        resultado = _resultado_con_grupos([1, 2, 3])
        grupo_service.reordenar_grupos(resultado, "Cuarta", [3, 1, 2])
        ids_resultantes = [g["id"] for g in resultado["grupos_por_categoria"]["Cuarta"]]
        assert ids_resultantes == [3, 1, 2]

    def test_idempotente_con_mismo_orden(self):
        resultado = _resultado_con_grupos([1, 2, 3])
        grupo_service.reordenar_grupos(resultado, "Cuarta", [1, 2, 3])
        ids_resultantes = [g["id"] for g in resultado["grupos_por_categoria"]["Cuarta"]]
        assert ids_resultantes == [1, 2, 3]

    def test_preserva_datos_de_grupos(self):
        resultado = _resultado_con_grupos([1, 2, 3])
        parejas_grupo1_antes = resultado["grupos_por_categoria"]["Cuarta"][0]["parejas"]
        grupo_service.reordenar_grupos(resultado, "Cuarta", [2, 3, 1])
        grupo1_ahora = next(
            g for g in resultado["grupos_por_categoria"]["Cuarta"] if g["id"] == 1
        )
        assert grupo1_ahora["parejas"] == parejas_grupo1_antes

    def test_error_si_categoria_no_existe(self):
        resultado = _resultado_con_grupos([1, 2])
        with pytest.raises(ServiceError) as exc_info:
            grupo_service.reordenar_grupos(resultado, "Inexistente", [1, 2])
        assert exc_info.value.status_code == 404

    def test_error_si_lista_incompleta(self):
        resultado = _resultado_con_grupos([1, 2, 3])
        with pytest.raises(ServiceError) as exc_info:
            grupo_service.reordenar_grupos(resultado, "Cuarta", [1, 2])
        assert exc_info.value.status_code == 400

    def test_error_si_ids_desconocidos(self):
        resultado = _resultado_con_grupos([1, 2, 3])
        with pytest.raises(ServiceError) as exc_info:
            grupo_service.reordenar_grupos(resultado, "Cuarta", [1, 2, 99])
        assert exc_info.value.status_code == 400

    def test_error_si_ids_duplicados(self):
        resultado = _resultado_con_grupos([1, 2, 3])
        with pytest.raises(ServiceError) as exc_info:
            grupo_service.reordenar_grupos(resultado, "Cuarta", [1, 2, 2])
        assert exc_info.value.status_code == 400


# ── Integración: ruta POST /api/reordenar-grupos ──────────────────────────────
# El route importa storage con `from utils.torneo_storage import storage`, así
# que hay que parchear la referencia local del módulo de rutas.

class TestReordenarGruposRuta:

    def test_fase_torneo_retorna_403(self, admin_cookie):
        with patch("api.routes.grupos.storage") as mock_st:
            mock_st.get_fase.return_value = "torneo"
            resp = admin_cookie.post(
                "/api/reordenar-grupos",
                data=json.dumps({"categoria": "Cuarta", "orden_grupos": [1, 2]}),
                content_type="application/json",
            )
        assert resp.status_code == 403

    def test_payload_invalido_retorna_400(self, admin_cookie):
        with patch("api.routes.grupos.storage") as mock_st:
            mock_st.get_fase.return_value = "espera"
            resp = admin_cookie.post(
                "/api/reordenar-grupos",
                data=json.dumps({"categoria": "Cuarta"}),
                content_type="application/json",
            )
        assert resp.status_code == 400
