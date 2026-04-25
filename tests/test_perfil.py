"""
Tests para los endpoints GET/PUT /api/auth/perfil y helpers relacionados.

Cubre:
- GET /api/auth/perfil: éxito, sin auth, error Supabase
- PUT /api/auth/perfil: éxito, validaciones, desverificación de teléfono, reemisión JWT
- validar_telefono: formatos válidos e inválidos
- Role fix (T-09): tokens sin role ya no se tratan como admin
"""

import pytest
import time
from unittest.mock import MagicMock, patch, PropertyMock

from utils.input_validation import validar_telefono


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def jugador_token(app):
    """JWT válido para un jugador."""
    with app.app_context():
        token = app.jwt_handler.generar_token({
            'authenticated': True,
            'role': 'jugador',
            'user_id': 'uuid-jugador-1',
            'nombre': 'Juan',
            'apellido': 'Perez',
            'telefono': '600000000',
            'timestamp': int(time.time()),
        })
    return token


@pytest.fixture
def cookie_jugador(client, jugador_token):
    """Test client con cookie de jugador seteada."""
    client.set_cookie('token', jugador_token)
    return client


@pytest.fixture
def mock_sb_admin():
    """Mock del cliente Supabase admin."""
    mock = MagicMock()
    # Perfil por defecto
    perfil_data = MagicMock()
    perfil_data.data = {
        'nombre': 'Juan',
        'apellido': 'Perez',
        'telefono': '600000000',
        'telefono_verificado': False,
    }
    mock.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = perfil_data

    # Auth user por defecto
    user_mock = MagicMock()
    user_mock.user.email = 'juan@test.com'
    mock.auth.admin.get_user_by_id.return_value = user_mock

    return mock


# ── validar_telefono ──────────────────────────────────────────────────────────

class TestValidarTelefono:

    @pytest.mark.parametrize("telefono", [
        '600123456',
        '+54 9 11 1234-5678',
        '(011) 4444-5555',
        '+1-800-555-0199',
        '123456',          # mínimo 6 chars
    ])
    def test_telefonos_validos(self, telefono):
        ok, msg = validar_telefono(telefono)
        assert ok is True
        assert msg == ''

    @pytest.mark.parametrize("telefono", [
        '123',                          # muy corto
        'abcdefg',                      # letras
        '123456789012345678901',        # demasiado largo (>20)
        'tel: 600-123',                 # contiene "tel:"
    ])
    def test_telefonos_invalidos(self, telefono):
        ok, msg = validar_telefono(telefono)
        assert ok is False
        assert msg != ''

    def test_telefono_vacio_es_valido(self):
        """Teléfono es opcional — vacío debe pasar."""
        ok, msg = validar_telefono('')
        assert ok is True

    def test_telefono_none_es_valido(self):
        ok, msg = validar_telefono(None)
        assert ok is True


# ── GET /api/auth/perfil ──────────────────────────────────────────────────────

class TestGetPerfil:

    def test_sin_autenticacion_devuelve_401(self, client):
        res = client.get('/api/auth/perfil')
        assert res.status_code == 401

    def test_con_token_admin_devuelve_401(self, admin_cookie):
        """El admin no es jugador — no puede ver el perfil de jugador."""
        res = admin_cookie.get('/api/auth/perfil')
        assert res.status_code == 401

    def test_jugador_autenticado_devuelve_perfil(self, cookie_jugador, mock_sb_admin):
        with patch('api.routes.auth_jugador._get_supabase_admin', return_value=mock_sb_admin):
            res = cookie_jugador.get('/api/auth/perfil')
        assert res.status_code == 200
        data = res.get_json()
        assert data['nombre'] == 'Juan'
        assert data['apellido'] == 'Perez'
        assert data['email'] == 'juan@test.com'
        assert 'telefono' in data
        assert 'telefono_verificado' in data

    def test_error_supabase_devuelve_500(self, cookie_jugador):
        mock_err = MagicMock()
        mock_err.table.side_effect = Exception('Supabase caído')
        with patch('api.routes.auth_jugador._get_supabase_admin', return_value=mock_err):
            res = cookie_jugador.get('/api/auth/perfil')
        assert res.status_code == 500
        assert 'error' in res.get_json()


# ── PUT /api/auth/perfil ──────────────────────────────────────────────────────

class TestPutPerfil:

    def _mock_put(self, mock_sb_admin, telefono_actual='600000000', verificado=False):
        """Configura el mock para el flujo PUT: primera query SELECT, luego UPDATE."""
        perfil_actual = MagicMock()
        perfil_actual.data = {
            'telefono': telefono_actual,
            'telefono_verificado': verificado,
        }
        # Primera llamada: SELECT telefono,telefono_verificado (para comparar)
        # Segunda llamada: UPDATE
        call_count = {'n': 0}

        def select_side_effect(*args, **kwargs):
            call_count['n'] += 1
            chain = MagicMock()
            chain.eq.return_value.single.return_value.execute.return_value = perfil_actual
            return chain

        mock_sb_admin.table.return_value.select = select_side_effect
        mock_sb_admin.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
        return mock_sb_admin

    def test_sin_autenticacion_devuelve_401(self, client):
        res = client.put('/api/auth/perfil', json={'nombre': 'X', 'apellido': 'Y'})
        assert res.status_code == 401

    def test_nombre_vacio_devuelve_400(self, cookie_jugador, mock_sb_admin):
        with patch('api.routes.auth_jugador._get_supabase_admin', return_value=mock_sb_admin):
            res = cookie_jugador.put('/api/auth/perfil', json={'nombre': '', 'apellido': 'Perez'})
        assert res.status_code == 400
        assert 'error' in res.get_json()

    def test_apellido_vacio_devuelve_400(self, cookie_jugador, mock_sb_admin):
        with patch('api.routes.auth_jugador._get_supabase_admin', return_value=mock_sb_admin):
            res = cookie_jugador.put('/api/auth/perfil', json={'nombre': 'Juan', 'apellido': ''})
        assert res.status_code == 400

    def test_telefono_invalido_devuelve_400(self, cookie_jugador, mock_sb_admin):
        with patch('api.routes.auth_jugador._get_supabase_admin', return_value=mock_sb_admin):
            res = cookie_jugador.put('/api/auth/perfil', json={
                'nombre': 'Juan', 'apellido': 'Perez', 'telefono': 'abc'
            })
        assert res.status_code == 400

    def test_actualizacion_exitosa_devuelve_200_y_nuevas_cookie(self, cookie_jugador, mock_sb_admin):
        self._mock_put(mock_sb_admin)
        with patch('api.routes.auth_jugador._get_supabase_admin', return_value=mock_sb_admin):
            res = cookie_jugador.put('/api/auth/perfil', json={
                'nombre': 'Juan', 'apellido': 'Perez', 'telefono': '600000000'
            })
        assert res.status_code == 200
        data = res.get_json()
        assert data['ok'] is True
        # JWT debe reemitirse en cookie
        assert 'token' in res.headers.get('Set-Cookie', '')

    def test_cambio_telefono_desverifica(self, cookie_jugador, mock_sb_admin):
        """Si el teléfono cambia, telefono_verificado debe ponerse en False."""
        self._mock_put(mock_sb_admin, telefono_actual='600000000', verificado=True)
        captured = {}

        def capture_update(data):
            captured['data'] = data
            chain = MagicMock()
            chain.eq.return_value.execute.return_value = MagicMock()
            return chain

        mock_sb_admin.table.return_value.update = capture_update

        with patch('api.routes.auth_jugador._get_supabase_admin', return_value=mock_sb_admin):
            res = cookie_jugador.put('/api/auth/perfil', json={
                'nombre': 'Juan', 'apellido': 'Perez', 'telefono': '700000000'
            })
        # El update debe incluir telefono_verificado=False
        assert captured.get('data', {}).get('telefono_verificado') is False

    def test_telefono_igual_no_desverifica(self, cookie_jugador, mock_sb_admin):
        """Si el teléfono no cambia, no se toca telefono_verificado."""
        self._mock_put(mock_sb_admin, telefono_actual='600000000', verificado=True)
        captured = {}

        def capture_update(data):
            captured['data'] = data
            chain = MagicMock()
            chain.eq.return_value.execute.return_value = MagicMock()
            return chain

        mock_sb_admin.table.return_value.update = capture_update

        with patch('api.routes.auth_jugador._get_supabase_admin', return_value=mock_sb_admin):
            res = cookie_jugador.put('/api/auth/perfil', json={
                'nombre': 'Juan', 'apellido': 'Perez', 'telefono': '600000000'
            })
        assert 'telefono_verificado' not in captured.get('data', {})

    def test_error_supabase_devuelve_500(self, cookie_jugador):
        mock_err = MagicMock()
        mock_err.table.side_effect = Exception('timeout')
        with patch('api.routes.auth_jugador._get_supabase_admin', return_value=mock_err):
            res = cookie_jugador.put('/api/auth/perfil', json={
                'nombre': 'Juan', 'apellido': 'Perez'
            })
        assert res.status_code == 500


# ── Role fix (T-09) ───────────────────────────────────────────────────────────

class TestRoleFix:

    def test_token_sin_role_no_es_admin(self, app, client):
        """Tokens legacy sin campo 'role' ya NO deben tener acceso de admin."""
        with app.app_context():
            token = app.jwt_handler.generar_token({
                'authenticated': True,
                # Sin campo 'role' — antes esto daba acceso admin
            })
        client.set_cookie('token', token)
        # /admin requiere admin — debe redirigir a login
        res = client.get('/admin')
        assert res.status_code in (302, 401)

    def test_token_role_admin_da_acceso(self, app, admin_cookie):
        """Token con role='admin' explícito sigue funcionando."""
        res = admin_cookie.get('/admin', follow_redirects=False)
        # Si hay datos de torneo: 200; si no: puede redirigir.
        # Lo importante es que NO es 401 por falta de auth.
        assert res.status_code != 401


# ── /mi-cuenta ────────────────────────────────────────────────────────────────

class TestMiCuenta:

    def test_sin_auth_redirige_a_login(self, client):
        res = client.get('/mi-cuenta')
        assert res.status_code == 302
        assert '/login' in res.headers.get('Location', '')

    def test_jugador_autenticado_puede_acceder(self, cookie_jugador):
        res = cookie_jugador.get('/mi-cuenta')
        # 200 o redirección interna (sin redirect a login)
        assert res.status_code == 200

    def test_admin_no_puede_acceder(self, admin_cookie):
        """El admin no tiene rol jugador — debe redirigir."""
        res = admin_cookie.get('/mi-cuenta', follow_redirects=False)
        assert res.status_code == 302
