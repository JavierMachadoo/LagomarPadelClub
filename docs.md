## Integración de fotos de torneos archivados (Google Drive)

### Objetivo
Incorporar una sección de **fotos** dentro de cada torneo archivado en el sistema, de forma que junto a los **resultados** y el **cuadro del torneo**, también se puedan visualizar las imágenes correspondientes al evento.

### Enfoque
Las fotos de cada torneo estarán almacenadas en una **carpeta de Google Drive**. Cada torneo archivado tendrá asociada una carpeta específica mediante su `folderId`.

### Estructura
Se agregará un nuevo campo al modelo de torneo:

Torneo {
  id,
  nombre,
  categoria,
  resultados,
  driveFolderId
}

### Funcionamiento
1. Para cada torneo archivado, se guarda el `driveFolderId` correspondiente.
2. El backend consulta la **Google Drive API** para obtener los archivos dentro de esa carpeta.
3. Se retorna una lista de imágenes (id, nombre, etc.).
4. El frontend renderiza estas imágenes en formato de galería.

### Visualización en el sistema
Dentro de la vista del torneo archivado se agregará una nueva sección:

- Resultados
- Cuadro del torneo
- Fotos

Las fotos se mostrarán en una grilla (tipo galería), permitiendo:
- Visualización rápida
- Ampliación al hacer click
- Navegación entre imágenes

### Beneficios
- Centralización de información del torneo (resultados + imágenes)
- No es necesario almacenar imágenes en el sistema
- Escalable: cada torneo solo necesita su `folderId`
- Mejora la experiencia del usuario

### Consideraciones
- Las carpetas de Google Drive deben tener permisos públicos o accesibles mediante API
- Se debe configurar autenticación para consumir la Google Drive API
- Se recomienda optimizar la carga de imágenes (lazy loading)