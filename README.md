# Algoritmo-Torneos 🎾

Aplicación web Flask para generar grupos y calendario de partidos de pádel según disponibilidad horaria y categoría.

## ¿Qué hace?

- 📋 Administra parejas por categoría y franjas horarias
- 🎯 Genera grupos optimizados (tripletas) según compatibilidad de horarios  
- 📅 Crea calendario de partidos asignando franjas y canchas automáticamente
- 🏆 Gestiona fixture de finales y resultados

## Tecnologías

- **Backend:** Python 3.13, Flask 3.1
- **Autenticación:** JWT (stateless, compatible con serverless)
- **Storage:** JSON (sistema de archivos)
- **Frontend:** HTML5, Bootstrap 5, JavaScript vanilla
- **Diseño:** Mobile-first, 100% responsive

## Estructura del proyecto

```
├── main.py                 # App Flask y rutas principales
├── api/routes/            # Endpoints REST API
│   ├── parejas.py         # Gestión de parejas y grupos
│   └── finales.py         # Fixture de finales
├── core/                  # Lógica de negocio
│   ├── algoritmo.py       # Algoritmo de generación de grupos
│   └── models.py          # Modelos de datos
├── utils/                 # Utilidades
│   ├── jwt_handler.py     # Manejo de tokens JWT
│   ├── api_helpers.py     # Helpers para API
│   └── torneo_storage.py  # Persistencia en JSON
├── web/                   # Frontend
│   ├── templates/         # HTML templates
│   └── static/            # CSS, JS, imágenes
└── data/torneos/          # Almacenamiento de datos
```

## Instalación

1. **Clonar repositorio:**
```bash
git clone <tu-repo>
cd Algoritmo-Torneos
```

2. **Crear entorno virtual:**
```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac
```

3. **Instalar dependencias:**
```bash
pip install -r requirements.txt
```

4. **Configurar seguridad (IMPORTANTE):**
```bash
# Copiar archivo de ejemplo
cp .env.example .env

# Editar .env y cambiar las credenciales
# Especialmente para producción:
# - SECRET_KEY: Usa una clave fuerte y aleatoria
# - ADMIN_USERNAME: Usuario personalizado
# - ADMIN_PASSWORD: Contraseña segura
```

5. **Ejecutar aplicación:**
```bash
python main.py
```

5. **Abrir en navegador:** http://127.0.0.1:5000

## Uso

1. **Cargar datos:** Sube un CSV con parejas desde la página inicio
2. **Ver grupos:** Los grupos se generan automáticamente al cargar el CSV
3. **Gestionar:** Drag & drop para reorganizar, crear grupos manuales
4. **Finales:** Accede a la sección de finales para el fixture del domingo

### Formato CSV requerido

```csv
Nombre,Teléfono,Categoría,Jueves 18:00,Jueves 20:00,Viernes 18:00,...
Juan/Pedro,099123456,Cuarta,Sí,No,Sí,...
```

## Cómo funciona el algoritmo

1. **Separación por categoría:** Agrupa parejas por nivel
2. **Generación de grupos:** Crea tripletas optimizadas
   - **Score 3.0:** Las 3 parejas comparten una franja (ideal)
   - **Score 2.0:** Al menos 2 parejas tienen intersección
   - **Score 0.0:** Sin compatibilidad horaria
3. **Asignación de canchas:** Round-robin por franja horaria
4. **Calendario:** Genera partidos automáticamente

## Deployment en Vercel

La aplicación usa JWT stateless con autenticación, perfecta para serverless:

1. Instala Vercel CLI: `npm i -g vercel`
2. Crea `vercel.json` en la raíz
3. Configura variables de entorno en Vercel:
   - `SECRET_KEY`: Clave fuerte para firmar tokens JWT
   - `ADMIN_USERNAME`: Usuario de administrador
   - `ADMIN_PASSWORD`: Contraseña segura
   - `DEBUG`: False
4. Despliega: `vercel --prod`

**⚠️ IMPORTANTE:** Cambia las credenciales antes de subir a producción

## Seguridad

- 🔐 **Autenticación JWT:** Login obligatorio antes de acceder
- 🔒 **Sesiones seguras:** Tokens con expiración de 2 horas
- 🛡️ **Rutas protegidas:** Todas las rutas y APIs requieren autenticación
- 🚫 **HttpOnly cookies:** Tokens no accesibles desde JavaScript
- ⚙️ **Variables de entorno:** Credenciales configurables

## Características técnicas

- ✅ **Stateless:** Sin sesiones de servidor, compatible con serverless
- ✅ **JWT tokens:** Autenticación segura con expiración
- ✅ **Login protegido:** Sistema de credenciales con hash seguro
- ✅ **Storage JSON:** Persistencia simple en archivos
- ✅ **Sin dependencias externas:** No requiere DB ni Redis
- ✅ **Drag & drop:** Interfaz intuitiva para reorganizar grupos
- ✅ **100% Mobile:** Diseño responsive optimizado para smartphones

## 📱 Diseño Mobile-First

La aplicación está completamente optimizada para dispositivos móviles:

- **Calendario adaptativo:** Vista de cards en móvil, tablas en desktop
- **Navegación touch-friendly:** Botones y áreas táctiles optimizadas
- **Responsive en todo:** Todas las páginas se adaptan perfectamente
- **PWA-ready:** Configuración para instalar como app móvil
- **Optimizado iOS/Android:** Funciona perfecto en ambos sistemas

### Breakpoints:
- 📱 **< 768px:** Vista móvil completa
- 📱 **< 375px:** Móviles pequeños
- 💻 **769px - 1024px:** Tablets
- 🖥️ **> 1024px:** Desktop

## Troubleshooting

**No se generan grupos:**
- Verifica que el CSV tenga al menos 3 parejas
- Revisa que las franjas horarias coincidan

**Errores de permisos:**
- Asegúrate que `data/torneos/` sea escribible

**Token muy grande:**
- El JWT solo almacena validación de sesión
- Los datos vienen de `torneo_actual.json`

## Licencia

Proyecto personal - Código educativo

---

**¡Listo para generar torneos! 🎾**
