"""Tests for torneo mixto config additions."""

from config.settings import TIPOS_TORNEO, COLORES_CATEGORIA, EMOJI_CATEGORIA, CATEGORIAS


class TestTiposTorneo:
    def test_mixto_tiene_categorias_abc(self):
        assert TIPOS_TORNEO['mixto'] == ['A', 'B', 'C']

    def test_fin1_sin_cambios(self):
        assert TIPOS_TORNEO['fin1'] == ['Tercera', 'Quinta', 'Séptima']

    def test_fin2_sin_cambios(self):
        assert TIPOS_TORNEO['fin2'] == ['Cuarta', 'Sexta', 'Octava']


class TestColoresCategoriaMixto:
    def test_color_A(self):
        assert COLORES_CATEGORIA.get('A') == '#28a745'

    def test_color_B(self):
        assert COLORES_CATEGORIA.get('B') == '#007bff'

    def test_color_C(self):
        assert COLORES_CATEGORIA.get('C') == '#dc3545'


class TestEmojiCategoriaMixto:
    def test_emoji_A(self):
        assert EMOJI_CATEGORIA.get('A') == '🟢'

    def test_emoji_B(self):
        assert EMOJI_CATEGORIA.get('B') == '🔵'

    def test_emoji_C(self):
        assert EMOJI_CATEGORIA.get('C') == '🔴'


class TestCategoriasRegresion:
    def test_categorias_sin_cambios(self):
        assert CATEGORIAS == ['Tercera', 'Cuarta', 'Quinta', 'Sexta', 'Séptima', 'Octava']
