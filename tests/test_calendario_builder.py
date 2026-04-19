"""
Tests unitarios para utils/calendario_builder.py

Cubre: _crear_mapeo_grupos_a_letras() respeta orden de lista, no orden de id.
"""

from utils.calendario_builder import CalendarioBuilder
from core.models import Grupo, ResultadoAlgoritmo


def _grupo(id: int, categoria: str = "Cuarta") -> Grupo:
    return Grupo(id=id, categoria=categoria)


def _resultado_con_grupos(grupos_por_cat: dict) -> ResultadoAlgoritmo:
    return ResultadoAlgoritmo(
        grupos_por_categoria=grupos_por_cat,
        parejas_sin_asignar=[],
        calendario={},
        estadisticas={},
    )


class TestCrearMapeoGruposALetras:

    def _mapeo(self, grupos_lista: list) -> dict:
        builder = CalendarioBuilder(num_canchas=2)
        resultado = _resultado_con_grupos({"Cuarta": grupos_lista})
        return builder._crear_mapeo_grupos_a_letras(resultado)

    def test_primer_grupo_de_lista_es_A_independientemente_del_id(self):
        grupos = [_grupo(id=3), _grupo(id=1), _grupo(id=2)]
        mapeo = self._mapeo(grupos)
        assert mapeo[3] == "A"
        assert mapeo[1] == "B"
        assert mapeo[2] == "C"

    def test_orden_natural_mantiene_A_B_C(self):
        grupos = [_grupo(id=1), _grupo(id=2), _grupo(id=3)]
        mapeo = self._mapeo(grupos)
        assert mapeo[1] == "A"
        assert mapeo[2] == "B"
        assert mapeo[3] == "C"

    def test_reorden_cambia_letras(self):
        grupos_original = [_grupo(id=1), _grupo(id=2), _grupo(id=3)]
        grupos_reordenado = [_grupo(id=3), _grupo(id=2), _grupo(id=1)]

        mapeo_orig = self._mapeo(grupos_original)
        mapeo_reo = self._mapeo(grupos_reordenado)

        assert mapeo_orig[1] == "A"
        assert mapeo_reo[3] == "A"
        assert mapeo_reo[1] == "C"
