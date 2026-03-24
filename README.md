# Algoritmo-Torneos

Sistema de gestión integral de torneos de pádel para el Club Lagomar.

---

## El Problema

Un club de pádel organiza torneos recurrentes con decenas de parejas distribuidas en 5 niveles de habilidad. El mayor dolor operativo es **agrupar parejas que puedan jugar en el mismo horario**. Hacerlo manualmente implica:

- Cruzar disponibilidades de 40-60 parejas a mano
- Conflictos de horarios descubiertos a último momento
- Horas de trabajo administrativo cada torneo
- Errores humanos en standings y brackets de finales

---

## Para quién está dirigido

| Rol | Necesidad |
|-----|-----------|
| **Administrador del club** | Organizar el torneo de punta a punta: cargar parejas, generar grupos, ingresar resultados, armar finales y archivar |
| **Jugador inscrito** | Registrarse, inscribir su pareja, ver su grupo, seguir resultados y bracket de finales |
| **Público general** | Consultar grupos, calendario de partidos, bracket de finales e historial de torneos anteriores |

---

## Conceptos clave del dominio

**Categorías de nivel:** Tercera, Cuarta, Quinta, Sexta y Séptima. Cada pareja compite solo contra parejas de su mismo nivel. Los torneos se dividen en dos fines de semana alternos:

- **Fin de semana 1:** Tercera, Quinta, Séptima
- **Fin de semana 2:** Cuarta, Sexta

**Franjas horarias:** Los jugadores indican cuándo pueden jugar (Viernes 18:00, Viernes 21:00, Sábado 09:00, 12:00, 16:00, 19:00). Esta disponibilidad es la base de todo el sistema.

**Grupo:** Exactamente 3 parejas que juegan entre sí (3 partidos por grupo: A vs B, A vs C, B vs C). Cada grupo tiene una franja horaria y cancha asignada.

---

## Ciclo de vida de un torneo

### 1. Inscripción

Las parejas llegan al sistema por dos vías:

- **Auto-inscripción con invitación:** el jugador se registra (email o Google), busca a su compañero por teléfono e lo invita directamente. Si el compañero no tiene cuenta, se genera un link compartible (WhatsApp) para que se registre y acepte. Ambos jugadores quedan vinculados por cuenta — no por nombre de texto — lo que garantiza identidad confiable para el ranking.
- **Carga masiva:** el admin sube un archivo CSV con todas las parejas y sus disponibilidades

### 2. Generación de grupos (el corazón del sistema)

El admin ejecuta el algoritmo que agrupa automáticamente las parejas. El sistema:

1. **Separa por categoría** (cada nivel se agrupa independientemente)
2. **Calcula compatibilidad** entre cada combinación posible de 3 parejas, basándose en cuántas franjas horarias comparten:
   - Las 3 comparten exactamente la misma franja → compatibilidad perfecta (3.0)
   - 2 comparten franja exacta, la tercera comparte solo el día → compatibilidad parcial (~2.5)
   - Sin coincidencias → incompatibles
3. **Optimiza la distribución** buscando la combinación de grupos que maximice la compatibilidad total (explora combinaciones con poda inteligente para no tardar eternamente)
4. **Asigna canchas** evitando solapamientos

**Resultado:** grupos óptimos donde las 3 parejas pueden jugar en el mismo horario, con estadísticas de calidad (% de asignación, score promedio de compatibilidad).

El admin puede refinar manualmente: intercambiar parejas entre grupos, mover parejas sin asignar, ajustar horarios o canchas.

### 3. Fase de juego

Se cierran inscripciones y comienzan los partidos. Cada partido tiene:

- **2 sets** (gana quien lleve más games, ej: 6-4)
- Si quedan 1-1 en sets → **super tiebreak** (primero a 10 puntos)

El admin ingresa resultados partido por partido. El sistema calcula automáticamente las posiciones de cada grupo usando: partidos ganados > diferencia de sets > diferencia de games.

### 4. Finales (eliminación directa)

Los mejores de cada categoría avanzan a un bracket de eliminación:

- **Octavos → Cuartos → Semifinal → Final**
- El seeding es justo: el 1° del grupo A enfrenta al 8°, el 2° al 7°, etc.
- Se mantiene una "burbuja" para evitar que parejas del mismo grupo se crucen antes de la final
- El sistema genera automáticamente el calendario de finales (típicamente domingo)

### 5. Archivado

Al terminar, el admin archiva el torneo con nombre (ej: "Torneo Marzo 2026"). Todos los datos quedan guardados permanentemente: grupos, resultados de fase de grupos, bracket completo de finales. El sistema se resetea y queda listo para el siguiente torneo.

---

## Reglas de negocio principales

| Regla | Detalle |
|-------|---------|
| Mínimo de disponibilidad | Cada pareja debe tener al menos 2 franjas horarias |
| Tamaño de grupo | Exactamente 3 parejas (excepcionalmente 2 si no hay suficientes) |
| Inscripción tardía | Si alguien se inscribe después de generar grupos, se intenta ubicar en un grupo incompleto de su categoría; si no hay espacio, queda sin asignar para que el admin lo resuelva |
| Invitación de compañero | Al inscribirse, la pareja queda en estado `pendiente_companero` hasta que el segundo jugador acepte (in-app o vía link). Si rechaza, la inscripción se cancela. Las invitaciones expiran a las 48h. |
| Resultados editables | El admin puede corregir resultados antes de archivar; standings y bracket se recalculan automáticamente |
| Un torneo a la vez | Solo puede haber un torneo activo; para empezar otro hay que archivar el anterior |

---

## El algoritmo de agrupación

### Compatibilidad de horarios

Para cada combinación posible de 3 parejas, el sistema evalúa qué tan bien encajan sus disponibilidades:

- **Score 3.0 (perfecta):** las 3 parejas comparten exactamente la misma franja horaria
- **Score 2.0-2.9 (parcial):** al menos 2 parejas coinciden en franja exacta, la tercera coincide en el día
- **Score < 2.0 (baja):** poca o ninguna coincidencia horaria

### Optimización

El algoritmo busca la distribución de grupos que **maximice la suma total de compatibilidad**:

- Para 2-6 grupos: exploración exhaustiva con poda (descarta ramas que no pueden superar el mejor resultado encontrado)
- Para más grupos: selecciona iterativamente los mejores grupos disponibles (enfoque greedy)
- Limita la exploración según el tamaño del problema para garantizar respuesta en segundos

### Resultado

Tras ejecutar el algoritmo, el sistema entrega:

- Grupos formados con su franja horaria y cancha asignada
- Parejas sin asignar (si las hay)
- Calendario completo de partidos
- Estadísticas: total de parejas, % de asignación, score promedio, grupos con compatibilidad perfecta vs. parcial

---

## Ejemplo de flujo completo

**1. Carga de datos:** El admin sube un CSV con 20 parejas de categoría Tercera, cada una con sus franjas disponibles.

**2. Algoritmo:** El sistema genera 6 grupos de 3 parejas (18 asignadas, 2 sin asignar). Score promedio: 2.7/3.0.

**3. Refinamiento:** El admin mueve una pareja sin asignar a un grupo incompleto. La otra queda en espera.

**4. Cierre de inscripciones:** Se pasa a fase de torneo.

**5. Partidos de grupo:** Durante viernes y sábado se juegan los 3 partidos por grupo. El admin carga resultados (ej: 6-4, 5-7, tiebreak 10-12).

**6. Standings:** El sistema calcula automáticamente: 1° Pareja X (2 victorias), 2° Pareja Y (1 victoria), 3° Pareja Z (0 victorias).

**7. Finales:** Auto-seeding: 1° del Grupo 1 vs 8° del Grupo 6, etc. Bracket de octavos → cuartos → semis → final.

**8. Archivado:** "Torneo Marzo 2026" queda guardado permanentemente. Sistema limpio para el siguiente.

---

## Casos especiales

| Caso | Comportamiento |
|------|---------------|
| Pocas parejas en una categoría (< 3) | No se generan grupos; quedan sin asignar para resolución manual |
| Inscripción tardía | Se busca grupo incompleto en su categoría; si no hay, queda sin asignar |
| Corrección de resultados | El admin edita resultados y el sistema recalcula standings y bracket automáticamente |
| Finales con menos de 8 parejas | El seeding se ajusta al número real de clasificadas |

---

## Qué valor aporta vs. hacerlo a mano

- **Agrupación inteligente:** lo que a un humano le tomaría horas (cruzar disponibilidades de 60 parejas), el algoritmo lo resuelve en segundos sin conflictos de horario
- **Cero errores en standings:** el cálculo de posiciones y seeding de finales es automático y consistente
- **Autonomía del jugador:** se inscribe solo, ve su grupo y resultados sin depender del admin
- **Historial perpetuo:** cada torneo queda archivado y consultable, base para un futuro sistema de ranking
- **Identidad real de jugadores:** ambos integrantes de cada pareja tienen cuenta propia — elimina homónimos y permite ranking individual preciso
