-- Migration 001: agregar columnas de verificación de teléfono
-- Tabla: jugadores (Supabase)
-- Ejecutar en: LagomarPadelDB-Dev y LagomarPadelDB prod
-- Rollback: ALTER TABLE jugadores DROP COLUMN telefono_verificado; ALTER TABLE jugadores DROP COLUMN telefono_verificado_at;

ALTER TABLE jugadores ADD COLUMN IF NOT EXISTS telefono_verificado BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE jugadores ADD COLUMN IF NOT EXISTS telefono_verificado_at TIMESTAMPTZ NULL;
