-- ============================================================
-- Schema de Supabase para Algoritmo-Torneos
-- Ejecutar en: Supabase → SQL Editor → New query
-- ============================================================

-- Tabla principal: almacena el torneo activo como un blob JSONB.
-- Siempre hay exactamente UNA fila (id = 1).
CREATE TABLE IF NOT EXISTS torneo_actual (
    id      INTEGER PRIMARY KEY DEFAULT 1,
    datos   JSONB   NOT NULL DEFAULT '{}',
    CONSTRAINT single_row CHECK (id = 1)
);

-- Insertar la fila vacía inicial (solo si no existe)
INSERT INTO torneo_actual (id, datos)
VALUES (1, '{}')
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- Row Level Security (RLS)
-- Por ahora desactivado: la app usa su propio sistema JWT.
-- Activar cuando se implemente registro de usuarios (v2).
-- ============================================================
-- ALTER TABLE torneo_actual ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- Tabla de torneos archivados (historial)
-- Nota: ya existe en Supabase. CREATE IF NOT EXISTS es idempotente.
-- ============================================================
CREATE TABLE IF NOT EXISTS torneos (
    id          UUID        PRIMARY KEY,
    nombre      TEXT        NOT NULL,
    tipo        TEXT        NOT NULL DEFAULT 'fin1',
    estado      TEXT        NOT NULL DEFAULT 'inscripcion',
    datos_blob  JSONB,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- fotos-drive: asociar carpeta pública de Google Drive a torneos archivados
-- Ejecutar primero en dev (LagomarPadelDB-Dev) y luego en prod (LagomarPadelDB)
ALTER TABLE torneos ADD COLUMN IF NOT EXISTS drive_folder_id TEXT NULL;

-- ============================================================
-- Tablas relacionales — fuente de verdad para ranking
-- Pobladas al archivar un torneo; el blob sigue siendo
-- cache de lectura para el dashboard de historial.
-- ============================================================

-- Un grupo de 3 parejas dentro de un torneo
CREATE TABLE IF NOT EXISTS grupos (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    torneo_id   UUID        REFERENCES torneos(id) ON DELETE CASCADE,
    categoria   TEXT        NOT NULL,
    franja      TEXT,
    cancha      INTEGER,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Las 3 parejas que componen cada grupo, con su posición final
CREATE TABLE IF NOT EXISTS parejas_grupo (
    grupo_id    UUID        REFERENCES grupos(id) ON DELETE CASCADE,
    nombre      TEXT        NOT NULL,
    posicion    INTEGER,    -- 1°, 2°, 3° | NULL si se archivó sin clasificar
    PRIMARY KEY (grupo_id, nombre)
);

-- Los 3 partidos de grupo (round-robin entre las 3 parejas)
CREATE TABLE IF NOT EXISTS partidos (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    grupo_id    UUID        REFERENCES grupos(id) ON DELETE CASCADE,
    pareja1     TEXT        NOT NULL,
    pareja2     TEXT        NOT NULL,
    resultado   JSONB       -- NULL si el partido no se jugó
);

-- Los partidos de la fase de eliminación directa
CREATE TABLE IF NOT EXISTS partidos_finales (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    torneo_id   UUID        REFERENCES torneos(id) ON DELETE CASCADE,
    categoria   TEXT        NOT NULL,
    fase        TEXT        NOT NULL,   -- 'Octavos de Final', 'Cuartos de Final', 'Semifinal', 'Final'
    pareja1     TEXT,                   -- NULL si el bracket no está completo
    pareja2     TEXT,
    ganador     TEXT                    -- NULL si no se jugó
);

-- Índices para queries de ranking cross-torneo
CREATE INDEX IF NOT EXISTS idx_grupos_torneo_id   ON grupos(torneo_id);
CREATE INDEX IF NOT EXISTS idx_grupos_categoria    ON grupos(categoria);
CREATE INDEX IF NOT EXISTS idx_partidos_grupo_id   ON partidos(grupo_id);
CREATE INDEX IF NOT EXISTS idx_pf_torneo_cat       ON partidos_finales(torneo_id, categoria);
CREATE INDEX IF NOT EXISTS idx_pf_categoria_fase   ON partidos_finales(categoria, fase);

-- ============================================================
-- Sistema de invitación de compañero
-- Migración: vincular ambos jugadores por UUID de Supabase Auth
-- ============================================================

-- Columna para vincular al compañero (Player B) en la inscripción
ALTER TABLE inscripciones ADD COLUMN IF NOT EXISTS jugador2_id UUID REFERENCES jugadores(id);

-- integrante2 puede ser NULL cuando el jugador se inscribe sin compañero aún (estado pendiente_companero)
ALTER TABLE inscripciones ALTER COLUMN integrante2 DROP NOT NULL;

-- Un jugador no puede ser invitado por 2 personas distintas en el mismo torneo
-- Búsqueda de inscripción por Player A (jugador que crea la inscripción)
CREATE INDEX IF NOT EXISTS idx_inscripciones_jugador_torneo
  ON inscripciones(torneo_id, jugador_id);

-- Un jugador no puede ser invitado por 2 personas distintas en el mismo torneo
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_jugador2_torneo
  ON inscripciones(torneo_id, jugador2_id)
  WHERE jugador2_id IS NOT NULL;

-- Tokens de invitación para links compartibles
CREATE TABLE IF NOT EXISTS invitacion_tokens (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    inscripcion_id UUID        NOT NULL REFERENCES inscripciones(id) ON DELETE CASCADE,
    token          TEXT        NOT NULL UNIQUE,
    expira_at      TIMESTAMPTZ NOT NULL,
    usado          BOOLEAN     DEFAULT FALSE,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_invitacion_token ON invitacion_tokens(token);

-- Escritura condicional del torneo (optimistic locking).
-- Actualiza el blob solo si la versión en BD coincide con p_expected_version.
-- Devuelve TRUE si escribió, FALSE si hubo conflicto (otro proceso se adelantó).
CREATE OR REPLACE FUNCTION guardar_torneo_con_version(p_datos JSONB, p_expected_version INT)
RETURNS BOOLEAN AS $$
DECLARE
    rows_updated INT;
BEGIN
    UPDATE torneo_actual
    SET datos = p_datos
    WHERE id = 1
      AND COALESCE((datos->>'version')::INT, 0) = p_expected_version;
    GET DIAGNOSTICS rows_updated = ROW_COUNT;
    RETURN rows_updated > 0;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Función para expirar invitaciones vencidas (verificación lazy)
CREATE OR REPLACE FUNCTION expirar_invitaciones(p_torneo_id UUID)
RETURNS void AS $$
  UPDATE inscripciones i
  SET estado = 'cancelada'
  WHERE i.torneo_id = p_torneo_id
    AND i.estado = 'pendiente_companero'
    AND NOT EXISTS (
      SELECT 1 FROM invitacion_tokens t
      WHERE t.inscripcion_id = i.id
        AND t.expira_at > NOW()
        AND t.usado = FALSE
    );
$$ LANGUAGE sql;

-- ============================================================
-- Tabla de puntos por jugador por torneo (base del ranking anual)
-- Ejecutar en dev y luego en prod
-- ============================================================
CREATE TABLE IF NOT EXISTS puntos_jugador (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    jugador_id  UUID        NOT NULL REFERENCES jugadores(id) ON DELETE CASCADE,
    torneo_id   UUID        NOT NULL REFERENCES torneos(id) ON DELETE CASCADE,
    categoria   TEXT        NOT NULL,
    puntos      INTEGER     NOT NULL DEFAULT 0,
    concepto    TEXT        NOT NULL DEFAULT 'serie',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (jugador_id, torneo_id, categoria)
);

CREATE INDEX IF NOT EXISTS idx_pj_jugador   ON puntos_jugador(jugador_id);
CREATE INDEX IF NOT EXISTS idx_pj_torneo    ON puntos_jugador(torneo_id);
CREATE INDEX IF NOT EXISTS idx_pj_categoria ON puntos_jugador(categoria);
