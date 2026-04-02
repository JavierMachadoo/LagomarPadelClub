# Plan de Despliegue a Producción

Resumen de decisiones y tareas para publicar la app a ~60 jugadores del torneo.
Fecha de objetivo: ~1 mes (abril 2026).

---

## 1. Arquitectura decidida

```
torneos.lagomarpadelclub.uy
         │
         ▼
┌─────────────────────┐       ┌─────────────────────┐
│  Railway Hobby      │       │  Supabase Free       │
│  São Paulo ($5/mes) │◄─────►│  São Paulo (sa-east-1)│
│                     │ ~1ms  │                      │
│  Flask + Gunicorn   │       │  PostgreSQL + Auth   │
│  2-3 workers        │       │  Google OAuth        │
│  Siempre activo     │       │  Nunca se pausa*     │
└─────────────────────┘       └──────────────────────┘

* Railway mantiene Supabase viva con queries cada 5 seg (cache TTL)
```

### Por qué esta combinación
- **Railway São Paulo**: $5/mes, deploy automático desde GitHub, sin cold starts, SSL y dominio custom incluidos
- **Supabase Free São Paulo**: Auth nativa (email/password + Google OAuth), 500MB BD, 50K auth users — de sobra para 60 jugadores
- **Latencia**: Servidor↔BD ~1ms (mismo datacenter), usuario en Uruguay↔servidor ~30-50ms
- **Supabase no se pausa**: Railway está siempre activo haciendo queries cada 5 seg por el cache refresh → Supabase detecta actividad constante

### Sitio del club (no se toca)
```
lagomarpadelclub.uy → WordPress + Elementor (hosting existente del club)
```
Son dos sistemas independientes. Solo se agrega un registro CNAME en el DNS del club para el subdominio.

---

## 2. Alternativas evaluadas y descartadas

### Hosting

| Plataforma | Precio | Región Brasil | Por qué no |
|------------|--------|---------------|------------|
| **Render Free** | $0 | No | Cold starts de 30-50 seg, se duerme tras 15 min |
| **Render Starter** | $7/mes | No | Más caro que Railway, sin región Sudamérica |
| **Vercel** | Variable | Sí | Serverless — la caché en memoria no funciona, habría que reescribir la app |
| **Netlify** | Variable | No | Mismo problema, diseñado para sitios estáticos |
| **Fly.io** | ~$2-3/mes | Sí | Sin free tier para cuentas nuevas, setup por CLI más complejo |
| **AWS Lightsail** | $3.50/mes | Sí | VPS crudo — instalar/mantener Python, Nginx, SSL, firewall manualmente |

### Base de datos

| Opción | Precio | Por qué no |
|--------|--------|------------|
| **Supabase Pro** | $25/mes | 5x el costo del hosting, innecesario si Railway mantiene la BD activa |
| **Railway Postgres** | Incluido en $5 | Perdemos Supabase Auth (login, Google OAuth, registro) — reimplementar auth es mucho trabajo |

---

## 3. Migración de infraestructura

### Paso 1: Crear Supabase en São Paulo
- Crear nuevo proyecto Supabase en región `sa-east-1` (São Paulo)
- Replicar schema de tablas desde `supabase_schema.sql`
- Configurar Auth: habilitar email/password + Google OAuth provider
- Hacer lo mismo para un proyecto Dev en São Paulo
- Los proyectos actuales en Ohio se pueden mantener como referencia y eliminar después

### Paso 2: Deploy en Railway
- Crear cuenta en Railway, conectar repositorio de GitHub
- Seleccionar región São Paulo
- Configurar variables de entorno:
  - `SECRET_KEY` — generar nueva key segura
  - `ADMIN_USERNAME` / `ADMIN_PASSWORD`
  - `SUPABASE_URL` / `SUPABASE_ANON_KEY` — del nuevo proyecto São Paulo
  - `SUPABASE_SERVICE_ROLE_KEY` — del nuevo proyecto São Paulo
  - `DEBUG=False`
- Verificar que el deploy funciona y la app conecta a Supabase

### Paso 3: Dominio personalizado
- En Railway: agregar custom domain `torneos.lagomarpadelclub.uy`
- En el DNS del club: agregar registro CNAME apuntando el subdominio a Railway
- Railway genera SSL automáticamente

### Paso 4: Verificación
- Testear login admin, registro de jugador, Google OAuth
- Testear flujo completo: inscripción → grupos → calendario → finales
- Verificar que UptimeRobot apunte al nuevo dominio

---

## 4. Ajustes técnicos

### Gunicorn — Subir a 2-3 workers
- **Antes**: 1 worker (para evitar inconsistencias con múltiples admins escribiendo)
- **Ahora**: 2-3 workers — los jugadores son mayormente lectura, 1 solo admin escribe
- Escritura segura: upsert atómico en Supabase + 1 admin
- Railway tiene suficiente RAM para 3 workers (~200MB)

### Cache in-memory (TTL 5 segundos)
- **Se mantiene en 5 segundos** — buen balance entre frescura y rendimiento
- Bonus: el refresh constante mantiene Supabase Free activa (nunca se pausa)

---

## 5. Plan de seguridad

Detallado en [PLAN_SEGURIDAD.md](PLAN_SEGURIDAD.md). Resumen:

### Críticos (antes de publicar)
| # | Fix | Esfuerzo |
|---|-----|----------|
| 1 | Flag `secure` en cookies (forzar HTTPS) | 5 min |
| 2 | Rate limiting en login/registro (`flask-limiter`) | 15 min |
| 3 | Límite de tamaño en uploads (5MB) | 1 min |
| 4 | Validación de contraseña (min 8 chars) | 5 min |
| 5 | Eliminar localStorage de jwt-helper.js | 10 min |

### Recomendados (no bloqueantes)
| # | Fix | Esfuerzo |
|---|-----|----------|
| 6 | Limitar longitud de inputs en formularios | 10 min |
| 7 | No exponer errores internos (`str(e)`) en respuestas | 5 min |
| 8 | Pinear versiones en requirements.txt | 5 min |
| 9 | Habilitar RLS en tablas de Supabase sin RLS | 30 min |
| 10 | Logging de errores 5xx | 5 min |

### Lo que ya está bien
- JWT en HttpOnly cookie (XSS no puede robar el token)
- SameSite=Lax en cookies (protección CSRF)
- Whitelist de rutas públicas (ruta nueva = privada por defecto)
- Service Role Key nunca expuesta al cliente
- Google OAuth con PKCE (flujo seguro)
- Health check con query real a BD

---

## 6. Costos

| Servicio | Costo mensual |
|----------|---------------|
| Railway Hobby (hosting) | $5 |
| Supabase Free (BD + Auth) | $0 |
| Dominio `lagomarpadelclub.uy` | Ya lo tienen |
| UptimeRobot | $0 |
| **Total** | **$5/mes** |

---

## 7. Checklist pre-lanzamiento

### Infraestructura
- [ ] Crear proyecto Supabase prod en São Paulo + replicar schema y Auth
- [ ] Crear proyecto Supabase dev en São Paulo
- [ ] Crear cuenta Railway + conectar repo GitHub + deploy en São Paulo
- [ ] Configurar variables de entorno en Railway
- [ ] Agregar subdominio `torneos.lagomarpadelclub.uy` (Railway + DNS del club)
- [ ] Apuntar UptimeRobot al nuevo dominio

### Ajustes técnicos
- [ ] Subir Gunicorn a 2-3 workers en `gunicorn.conf.py`
- [ ] Implementar los 5 fixes críticos de seguridad
- [ ] Implementar los fixes recomendados de seguridad

### Verificación
- [ ] Test login admin + registro jugador + Google OAuth
- [ ] Test flujo completo: inscripción → grupos → calendario → bracket
- [ ] Test de carga básico (simular 10-20 requests concurrentes)
- [ ] Verificar que Supabase se mantiene activa (no se pausa)
