---
name: frontend-torneos
description: >
  Patrones frontend del proyecto: Jinja2 + Bootstrap 5, JWT helper para fetch, Toast notifications y mobile-first CSS.
  Trigger: Al modificar templates en web/templates/ o scripts en web/static/js/.
license: MIT
metadata:
  author: eljav
  version: "1.0"
  scope: [root, web]
  auto_invoke: "Modifying Jinja2 templates or frontend JS"
allowed-tools: Read, Edit, Write, Glob, Grep, Bash
---

## Fetch con JWT (REQUIRED)

Todas las llamadas a `/api/*` desde el frontend deben usar `JWTHelper.fetchWithToken()`, nunca `fetch()` directamente.

```javascript
// ✅ CORRECTO: maneja token refresh y redirect a login en 401
const response = await JWTHelper.fetchWithToken('/api/parejas', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
});
const result = await response.json();

// ❌ NUNCA usar fetch() directo para endpoints protegidos
const response = await fetch('/api/parejas', { ... });
// no maneja 401, no refresca token
```

## Toast Notifications

Usar el sistema global `Toast` para feedback al usuario. No usar `alert()` ni manipular DOM directamente.

```javascript
// ✅ Tipos disponibles
Toast.show('Grupos generados correctamente', 'success');
Toast.show('Error al guardar resultado', 'error');
Toast.show('Faltan campos obligatorios', 'warning');
Toast.show('Cargando datos...', 'info');

// Duraciones por defecto: success=3s, error=5s, warning=4s, info=3s

// ❌ NUNCA usar alert() o console.log como feedback de usuario
alert('Guardado');
```

## Jinja2 — Pasar Datos a JS

Usar el filtro `tojson` para serializar datos de Python a JS de forma segura.

```html
<!-- ✅ Seguro: escapa caracteres especiales -->
<script>
  const grupos = {{ grupos_por_categoria | tojson }};
  const categorias = {{ categorias | tojson }};
</script>

<!-- ❌ NUNCA interpolar dicts Python directamente -->
<script>
  const grupos = {{ grupos_por_categoria }};  <!-- puede romper JS o generar XSS -->
</script>
```

## Bootstrap 5 — Componentes Usados

El proyecto usa Bootstrap 5 via CDN. Preferir clases utilitarias sobre CSS custom.

```html
<!-- ✅ Grid responsive con auto-fit -->
<div class="row row-cols-1 row-cols-md-2 row-cols-lg-3 g-3">
  {% for grupo in grupos %}
  <div class="col">
    <div class="card h-100 shadow-sm">...</div>
  </div>
  {% endfor %}
</div>

<!-- ✅ Colores de categoría desde config -->
<span class="badge" style="background-color: {{ color_categoria }}">
  {{ emoji_categoria }} {{ categoria }}
</span>
```

## Mobile-First CSS

Los estilos custom están en `web/static/css/style.css` y `mobile.css`. Escribir mobile-first y usar breakpoints de Bootstrap.

```css
/* ✅ Mobile-first */
.grupo-card {
  padding: 1rem;
}

@media (min-width: 768px) {
  .grupo-card {
    padding: 1.5rem;
  }
}

/* ❌ NUNCA desktop-first */
.grupo-card {
  padding: 1.5rem;
}
@media (max-width: 767px) {
  .grupo-card { padding: 1rem; }
}
```

## Templates Grandes — Cuidado con resultados.html

`resultados.html` pesa ~215KB y embebe lógica significativa. Al modificarlo:
- Buscar el bloque exacto con Grep antes de editar
- No duplicar lógica que ya existe en otro bloque del mismo template

## Ejemplo Real del Proyecto

En `web/static/js/jwt-helper.js`, el wrapper de fetch que maneja el ciclo de vida del token:

```javascript
fetchWithToken: async function(url, options = {}) {
    const token = this.getToken();
    const defaultOptions = {
        credentials: 'same-origin',
        headers: {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        }
    };
    const mergedOptions = { ...defaultOptions, ...options,
        headers: { ...defaultOptions.headers, ...(options.headers || {}) }
    };
    const response = await fetch(url, mergedOptions);
    if (response.status === 401) {
        window.location.href = '/login';
        return;
    }
    // Extraer nuevo token si viene en la respuesta
    const cloned = response.clone();
    try {
        const data = await cloned.json();
        if (data.token) this.setToken(data.token);
    } catch {}
    return response;
}
```

## Referencias

- `web/static/js/jwt-helper.js` — `JWTHelper.fetchWithToken()`, `getToken()`, `setToken()`
- `web/static/js/toast.js` — `Toast.show(message, type, duration)`
- `web/templates/base.html` — estructura base, navbar, bloque de toasts
- `web/static/css/style.css` — estilos globales
- `config/__init__.py` — `COLORES_CATEGORIA`, `EMOJI_CATEGORIA` (disponibles en templates vía contexto)