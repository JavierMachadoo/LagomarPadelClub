# Activar horarios de Fases Finales (público)

Los horarios y el tab de Fases Finales están **temporalmente ocultos** al usuario público.
Para volver a mostrarlos, revertir los dos cambios detallados abajo.

---

## 1. `web/templates/grupos_publico.html` — Cancha/horario en cards del bracket

**Línea ~13 (macro `render_partido`).**

Está comentado con `{# TEMP: ... #}`. Reemplazar esto:

```jinja
{# TEMP: cancha/horario oculto hasta publicar horarios de fases finales
{% if info %}
<div class="bk-match-head">
    <span class="bk-match-cancha"><i class="bi bi-geo-alt-fill"></i> Cancha {{ info.cancha }}</span>
    <span class="bk-match-hora"><i class="bi bi-clock"></i> {{ info.hora_inicio }}</span>
</div>
{% endif %}
#}
```

Por esto (sin el comentario exterior):

```jinja
{% if info %}
<div class="bk-match-head">
    <span class="bk-match-cancha"><i class="bi bi-geo-alt-fill"></i> Cancha {{ info.cancha }}</span>
    <span class="bk-match-hora"><i class="bi bi-clock"></i> {{ info.hora_inicio }}</span>
</div>
{% endif %}
```

---

## 2. `web/templates/calendario_publico.html` — Tab "Fases Finales"

### 2a. Botón del tab (~línea 357)

Quitar el `style="display:none"` del `<li>`:

```html
{# TEMP: tab Fases Finales oculto hasta publicar horarios #}
<li class="nav-item" role="presentation" style="display:none">
```

Debe quedar:

```html
<li class="nav-item" role="presentation">
```

También borrar el comentario `{# TEMP: ... #}` de la línea anterior si se quiere dejar limpio.

### 2b. Panel del tab (~línea 484)

Quitar el `style="display:none !important"` del div:

```html
<div class="tab-pane fade {% if not dias_fase_grupos %}show active{% endif %}"
     id="panel-finales" role="tabpanel" style="display:none !important">
```

Debe quedar:

```html
<div class="tab-pane fade {% if not dias_fase_grupos %}show active{% endif %}"
     id="panel-finales" role="tabpanel">
```

---

## Verificación post-cambio

1. Entrar como usuario público a `/calendario` — debe aparecer el tab **Fases Finales**
2. Entrar a `/grupos` — las cards del bracket de octavos en adelante deben mostrar cancha y horario arriba
