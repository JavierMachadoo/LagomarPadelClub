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
