# Plan de Seguridad — Pre-lanzamiento

Checklist de mejoras de seguridad antes de publicar la app para jugadores.

---

## Fixes Críticos (hacer antes de publicar)

- [x] **1. Flag `secure` en cookies**
  - **Qué**: Agregar `secure=not app.debug` a todos los `set_cookie()` en `main.py` y `api/routes/auth_jugador.py`
  - **Por qué**: Sin este flag, las cookies pueden viajar por HTTP plano. Render fuerza HTTPS pero es defensa en profundidad
  - **Archivos**: `main.py`, `api/routes/auth_jugador.py`

- [x] **2. Rate limiting en login y registro**
  - **Qué**: Instalar `flask-limiter` y aplicar límites a `/api/auth/login` (5/min) y `/api/auth/register` (3/min)
  - **Por qué**: Sin rate limiting, un atacante puede hacer fuerza bruta contra contraseñas indefinidamente
  - **Archivos**: `requirements.txt`, `main.py`, `api/routes/auth_jugador.py`

- [x] **3. Límite de tamaño en uploads**
  - **Qué**: Configurar `app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024` (5MB)
  - **Por qué**: Sin límite, un archivo enorme puede matar el servidor (DoS)
  - **Archivos**: `main.py`

- [x] **4. Validación de contraseña**
  - **Qué**: Validar mínimo 8 caracteres en el endpoint de registro
  - **Por qué**: Un jugador puede registrarse con password "1" actualmente
  - **Archivos**: `api/routes/auth_jugador.py`

- [x] **5. Eliminar localStorage en jwt-helper.js**
  - **Qué**: Quitar el fallback a `localStorage` para tokens JWT. El token ya viaja en HttpOnly cookie automáticamente
  - **Por qué**: Si un ataque XSS logra ejecutar JS, podría leer el token de localStorage. Con HttpOnly cookie pura eso es imposible
  - **Archivos**: `web/static/js/jwt-helper.js`

---

## Fixes Recomendados (no bloqueantes)

- [x] **6. Limitar longitud de inputs en formularios**
  - **Qué**: Validar longitud máxima en nombre (100 chars), teléfono (20 chars), etc.
  - **Por qué**: Evita que alguien envíe un payload de 10MB como nombre de pareja
  - **Archivos**: `api/routes/parejas.py`, `api/routes/auth_jugador.py`, `api/routes/inscripcion.py`

- [x] **7. No exponer errores internos en respuestas**
  - **Qué**: Reemplazar `f"Error al procesar CSV: {str(e)}"` por mensajes genéricos. Loggear el error real internamente
  - **Por qué**: `str(e)` puede filtrar rutas del servidor, versiones de librerías, o estructura interna
  - **Archivos**: `api/routes/parejas.py`

- [x] **8. Pinear versiones en requirements.txt**
  - **Qué**: Fijar todas las versiones exactas (ej: `pandas==2.2.3` en vez de `pandas>=2.2.0`)
  - **Por qué**: Una actualización automática de dependencia podría romper la app en producción
  - **Archivos**: `requirements.txt`

- [x] **9. Habilitar RLS en tablas de Supabase**
  - **Qué**: Activar Row Level Security en `torneo_actual`, `torneos`, `inscripciones`, `grupos`, `parejas_grupo`, `partidos`, `partidos_finales`
  - **Por qué**: Sin RLS, cualquiera con la anon key podría leer/escribir directamente a las tablas saltándose la app
  - **Archivos**: Migración SQL en Supabase
  - **Nota**: `jugadores` ya tiene RLS habilitado

- [x] **10. Logging de errores 5xx**
  - **Qué**: Agregar `app.logger.error(...)` en los handlers de error 500
  - **Por qué**: Actualmente los errores 500 son silenciosos — si algo falla en producción no te enterás
  - **Archivos**: `main.py`
