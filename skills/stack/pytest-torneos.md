---
name: pytest-torneos
description: >
  Patrones de testing con pytest para este proyecto Flask: fixtures de storage, mocking de Supabase, parametrize por categoría.
  Trigger: Al escribir o modificar tests en este proyecto.
license: MIT
metadata:
  author: eljav
  version: "1.0"
  scope: [root]
  auto_invoke: "Writing or modifying tests"
allowed-tools: Read, Edit, Write, Glob, Grep, Bash
---

## Fixture del Cliente Flask (REQUIRED)

Usar `app.test_client()` con `TESTING=True`. No levantar el servidor real.

```python
# ✅ conftest.py
import pytest
from main import app as flask_app

@pytest.fixture
def app():
    flask_app.config['TESTING'] = True
    flask_app.config['SECRET_KEY'] = 'test-secret'
    yield flask_app

@pytest.fixture
def client(app):
    return app.test_client()
```

## Mockear el Storage

Parchear la instancia global `storage` de `utils.torneo_storage`. No tocar archivos JSON ni Supabase en tests.

```python
# ✅ Parchear storage completo
from unittest.mock import MagicMock, patch

@pytest.fixture
def mock_storage():
    torneo_base = {
        "parejas": [],
        "resultado_algoritmo": {},
        "num_canchas": 3,
        "estado": "activo",
        "tipo_torneo": "fin1",
        "fixtures_finales": {},
        "nombre": "Torneo Test"
    }
    with patch('utils.torneo_storage.storage') as mock:
        mock.cargar.return_value = torneo_base.copy()
        mock.guardar.return_value = None
        yield mock

# ✅ Uso en test
def test_listar_parejas_vacio(client, mock_storage):
    response = client.get('/api/parejas',
        headers={'Authorization': 'Bearer ' + generar_token_test()})
    assert response.status_code == 200
    assert response.json['data'] == []
```

## JWT en Tests

Generar tokens de prueba con la misma función del proyecto. No hardcodear tokens.

```python
# ✅ conftest.py
from utils.jwt_handler import JWTHandler

@pytest.fixture
def jwt_handler():
    return JWTHandler('test-secret')

@pytest.fixture
def auth_headers(jwt_handler):
    token = jwt_handler.crear_token('admin')
    return {'Authorization': f'Bearer {token}'}

# ✅ Uso
def test_ruta_protegida(client, auth_headers):
    response = client.get('/api/parejas', headers=auth_headers)
    assert response.status_code == 200

# ❌ NUNCA hardcodear un token JWT en el test
headers = {'Authorization': 'Bearer eyJ...'}  # expirará y es ilegible
```

## Parametrize por Categoría y Franja

Las categorías y franjas horarias vienen de `config`. Importarlas, no hardcodearlas en tests.

```python
# ✅ Parametrize con valores reales del proyecto
from config import CATEGORIAS, FRANJAS_HORARIAS

@pytest.mark.parametrize("categoria", CATEGORIAS)
def test_algoritmo_por_categoria(categoria):
    parejas = generar_parejas_test(categoria, cantidad=6)
    algo = AlgoritmoGrupos(parejas)
    resultado = algo.ejecutar()
    assert categoria in resultado.grupos_por_categoria
    assert len(resultado.grupos_por_categoria[categoria]) == 2

@pytest.mark.parametrize("franja", FRANJAS_HORARIAS)
def test_compatibilidad_misma_franja(franja):
    p1 = Pareja(id="1", nombre="A", categoria="Tercera",
                telefono="", franjas_disponibles=[franja])
    p2 = Pareja(id="2", nombre="B", categoria="Tercera",
                telefono="", franjas_disponibles=[franja])
    p3 = Pareja(id="3", nombre="C", categoria="Tercera",
                telefono="", franjas_disponibles=[franja])
    algo = AlgoritmoGrupos([])
    score = algo._calcular_compatibilidad(p1, p2, p3)
    assert score == 3.0
```

## Helpers de Test

Centralizar la creación de objetos de prueba en `conftest.py` o helpers dedicados.

```python
# ✅ conftest.py — factories reutilizables
def crear_pareja(id="1", categoria="Tercera", franjas=None):
    return Pareja(
        id=id,
        nombre=f"Pareja {id}",
        categoria=categoria,
        telefono="600000000",
        franjas_disponibles=franjas or ["Viernes 18:00"]
    )

def crear_grupo_completo(categoria="Tercera"):
    parejas = [crear_pareja(str(i), categoria) for i in range(3)]
    grupo = Grupo(id="g1", categoria=categoria, parejas=parejas)
    return grupo
```

## Ejemplo Real del Proyecto

Test del algoritmo con 6 parejas en una categoría — verifica que se forman 2 grupos completos:

```python
def test_formar_dos_grupos_completos():
    parejas = [
        Pareja(id=str(i), nombre=f"Pareja {i}", categoria="Cuarta",
               telefono="", franjas_disponibles=["Sábado 09:00"])
        for i in range(6)
    ]
    algo = AlgoritmoGrupos(parejas)
    resultado = algo.ejecutar()

    grupos_cuarta = resultado.grupos_por_categoria.get("Cuarta", [])
    assert len(grupos_cuarta) == 2
    assert all(g.esta_completo() for g in grupos_cuarta)
    assert resultado.parejas_sin_asignar == []
```

## Referencias

- `core/algoritmo.py` — `AlgoritmoGrupos` (principal objeto a testear)
- `core/models.py` — `Pareja`, `Grupo`, `ResultadoPartido`
- `utils/torneo_storage.py` — instancia global `storage` (a mockear)
- `utils/jwt_handler.py` — `JWTHandler` para generar tokens en tests
- `config/__init__.py` — `CATEGORIAS`, `FRANJAS_HORARIAS`