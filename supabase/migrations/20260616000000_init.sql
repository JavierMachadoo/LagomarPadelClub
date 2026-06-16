


SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;


COMMENT ON SCHEMA "public" IS 'standard public schema';



CREATE EXTENSION IF NOT EXISTS "pg_stat_statements" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "pgcrypto" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "supabase_vault" WITH SCHEMA "vault";






CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA "extensions";






CREATE OR REPLACE FUNCTION "public"."expirar_invitaciones"("p_torneo_id" "uuid") RETURNS "void"
    LANGUAGE "sql"
    AS $$
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
$$;


ALTER FUNCTION "public"."expirar_invitaciones"("p_torneo_id" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."guardar_torneo_con_version"("p_datos" "jsonb", "p_expected_version" integer) RETURNS boolean
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
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
$$;


ALTER FUNCTION "public"."guardar_torneo_con_version"("p_datos" "jsonb", "p_expected_version" integer) OWNER TO "postgres";

SET default_tablespace = '';

SET default_table_access_method = "heap";


CREATE TABLE IF NOT EXISTS "public"."grupos" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "torneo_id" "uuid",
    "categoria" "text" NOT NULL,
    "franja" "text",
    "cancha" integer,
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."grupos" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."inscripciones" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "torneo_id" "uuid",
    "jugador_id" "uuid",
    "integrante1" "text" NOT NULL,
    "integrante2" "text",
    "telefono" "text",
    "categoria" "text" NOT NULL,
    "franjas_disponibles" "jsonb" DEFAULT '[]'::"jsonb" NOT NULL,
    "estado" "text" DEFAULT 'confirmado'::"text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "jugador2_id" "uuid",
    CONSTRAINT "inscripciones_estado_check" CHECK (("estado" = ANY (ARRAY['pendiente'::"text", 'confirmado'::"text", 'rechazado'::"text", 'pendiente_companero'::"text", 'cancelada'::"text"])))
);


ALTER TABLE "public"."inscripciones" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."invitacion_tokens" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "inscripcion_id" "uuid" NOT NULL,
    "token" "text" NOT NULL,
    "expira_at" timestamp with time zone NOT NULL,
    "usado" boolean DEFAULT false,
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."invitacion_tokens" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."jugadores" (
    "id" "uuid" NOT NULL,
    "nombre" "text" NOT NULL,
    "apellido" "text" NOT NULL,
    "telefono" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "usuario_id" "uuid",
    "email" "text",
    "activo" boolean DEFAULT true,
    "telefono_verificado" boolean DEFAULT false,
    "telefono_verificado_at" timestamp with time zone
);


ALTER TABLE "public"."jugadores" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."parejas_grupo" (
    "grupo_id" "uuid" NOT NULL,
    "nombre" "text" NOT NULL,
    "posicion" integer
);


ALTER TABLE "public"."parejas_grupo" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."partidos" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "grupo_id" "uuid",
    "pareja1" "text" NOT NULL,
    "pareja2" "text" NOT NULL,
    "resultado" "jsonb"
);


ALTER TABLE "public"."partidos" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."partidos_finales" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "torneo_id" "uuid",
    "categoria" "text" NOT NULL,
    "fase" "text" NOT NULL,
    "pareja1" "text",
    "pareja2" "text",
    "ganador" "text"
);


ALTER TABLE "public"."partidos_finales" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."puntos_jugador" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "jugador_id" "uuid" NOT NULL,
    "torneo_id" "uuid" NOT NULL,
    "categoria" "text" NOT NULL,
    "puntos" integer DEFAULT 0 NOT NULL,
    "concepto" "text" DEFAULT 'serie'::"text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."puntos_jugador" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."rechazos_vinculacion" (
    "catalogo_id" "uuid" NOT NULL,
    "registrado_id" "uuid" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."rechazos_vinculacion" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."torneo_actual" (
    "id" integer DEFAULT 1 NOT NULL,
    "datos" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    CONSTRAINT "single_row" CHECK (("id" = 1))
);


ALTER TABLE "public"."torneo_actual" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."torneos" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "nombre" "text" DEFAULT 'Torneo'::"text" NOT NULL,
    "tipo" "text" DEFAULT 'fin1'::"text" NOT NULL,
    "estado" "text" DEFAULT 'inscripcion'::"text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "datos_blob" "jsonb",
    "drive_folder_id" "text",
    CONSTRAINT "torneos_estado_check" CHECK (("estado" = ANY (ARRAY['inscripcion'::"text", 'torneo'::"text", 'finalizado'::"text"])))
);


ALTER TABLE "public"."torneos" OWNER TO "postgres";


ALTER TABLE ONLY "public"."grupos"
    ADD CONSTRAINT "grupos_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."inscripciones"
    ADD CONSTRAINT "inscripciones_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."inscripciones"
    ADD CONSTRAINT "inscripciones_torneo_id_jugador_id_key" UNIQUE ("torneo_id", "jugador_id");



ALTER TABLE ONLY "public"."invitacion_tokens"
    ADD CONSTRAINT "invitacion_tokens_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."invitacion_tokens"
    ADD CONSTRAINT "invitacion_tokens_token_key" UNIQUE ("token");



ALTER TABLE ONLY "public"."jugadores"
    ADD CONSTRAINT "jugadores_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."parejas_grupo"
    ADD CONSTRAINT "parejas_grupo_pkey" PRIMARY KEY ("grupo_id", "nombre");



ALTER TABLE ONLY "public"."partidos_finales"
    ADD CONSTRAINT "partidos_finales_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."partidos"
    ADD CONSTRAINT "partidos_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."puntos_jugador"
    ADD CONSTRAINT "puntos_jugador_jugador_id_torneo_id_categoria_key" UNIQUE ("jugador_id", "torneo_id", "categoria");



ALTER TABLE ONLY "public"."puntos_jugador"
    ADD CONSTRAINT "puntos_jugador_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."rechazos_vinculacion"
    ADD CONSTRAINT "rechazos_vinculacion_pkey" PRIMARY KEY ("catalogo_id", "registrado_id");



ALTER TABLE ONLY "public"."torneo_actual"
    ADD CONSTRAINT "torneo_actual_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."torneos"
    ADD CONSTRAINT "torneos_pkey" PRIMARY KEY ("id");



CREATE INDEX "idx_grupos_categoria" ON "public"."grupos" USING "btree" ("categoria");



CREATE INDEX "idx_grupos_torneo_id" ON "public"."grupos" USING "btree" ("torneo_id");



CREATE INDEX "idx_inscripciones_jugador" ON "public"."inscripciones" USING "btree" ("jugador_id", "torneo_id");



CREATE INDEX "idx_inscripciones_torneo" ON "public"."inscripciones" USING "btree" ("torneo_id", "estado");



CREATE INDEX "idx_invitacion_token" ON "public"."invitacion_tokens" USING "btree" ("token");



CREATE INDEX "idx_invitacion_tokens_inscripcion" ON "public"."invitacion_tokens" USING "btree" ("inscripcion_id");



CREATE INDEX "idx_partidos_grupo_id" ON "public"."partidos" USING "btree" ("grupo_id");



CREATE INDEX "idx_pf_categoria_fase" ON "public"."partidos_finales" USING "btree" ("categoria", "fase");



CREATE INDEX "idx_pf_torneo_cat" ON "public"."partidos_finales" USING "btree" ("torneo_id", "categoria");



CREATE INDEX "idx_pj_categoria" ON "public"."puntos_jugador" USING "btree" ("categoria");



CREATE INDEX "idx_pj_jugador" ON "public"."puntos_jugador" USING "btree" ("jugador_id");



CREATE INDEX "idx_pj_torneo" ON "public"."puntos_jugador" USING "btree" ("torneo_id");



CREATE UNIQUE INDEX "idx_unique_jugador2_torneo" ON "public"."inscripciones" USING "btree" ("torneo_id", "jugador2_id") WHERE ("jugador2_id" IS NOT NULL);



ALTER TABLE ONLY "public"."grupos"
    ADD CONSTRAINT "grupos_torneo_id_fkey" FOREIGN KEY ("torneo_id") REFERENCES "public"."torneos"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."inscripciones"
    ADD CONSTRAINT "inscripciones_jugador2_id_fkey" FOREIGN KEY ("jugador2_id") REFERENCES "public"."jugadores"("id");



ALTER TABLE ONLY "public"."inscripciones"
    ADD CONSTRAINT "inscripciones_jugador_id_fkey" FOREIGN KEY ("jugador_id") REFERENCES "public"."jugadores"("id");



ALTER TABLE ONLY "public"."inscripciones"
    ADD CONSTRAINT "inscripciones_torneo_id_fkey" FOREIGN KEY ("torneo_id") REFERENCES "public"."torneos"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."invitacion_tokens"
    ADD CONSTRAINT "invitacion_tokens_inscripcion_id_fkey" FOREIGN KEY ("inscripcion_id") REFERENCES "public"."inscripciones"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."jugadores"
    ADD CONSTRAINT "jugadores_usuario_id_fkey" FOREIGN KEY ("usuario_id") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."parejas_grupo"
    ADD CONSTRAINT "parejas_grupo_grupo_id_fkey" FOREIGN KEY ("grupo_id") REFERENCES "public"."grupos"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."partidos_finales"
    ADD CONSTRAINT "partidos_finales_torneo_id_fkey" FOREIGN KEY ("torneo_id") REFERENCES "public"."torneos"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."partidos"
    ADD CONSTRAINT "partidos_grupo_id_fkey" FOREIGN KEY ("grupo_id") REFERENCES "public"."grupos"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."puntos_jugador"
    ADD CONSTRAINT "puntos_jugador_jugador_id_fkey" FOREIGN KEY ("jugador_id") REFERENCES "public"."jugadores"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."puntos_jugador"
    ADD CONSTRAINT "puntos_jugador_torneo_id_fkey" FOREIGN KEY ("torneo_id") REFERENCES "public"."torneos"("id") ON DELETE CASCADE;



ALTER TABLE "public"."grupos" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."inscripciones" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."invitacion_tokens" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "jugador_puede_actualizar_su_perfil" ON "public"."jugadores" FOR UPDATE USING (("auth"."uid"() = "id"));



CREATE POLICY "jugador_puede_leer_su_perfil" ON "public"."jugadores" FOR SELECT USING (("auth"."uid"() = "id"));



ALTER TABLE "public"."jugadores" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."parejas_grupo" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."partidos" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."partidos_finales" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."puntos_jugador" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."rechazos_vinculacion" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "service_role_puede_insertar" ON "public"."jugadores" FOR INSERT WITH CHECK (true);



ALTER TABLE "public"."torneo_actual" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."torneos" ENABLE ROW LEVEL SECURITY;




ALTER PUBLICATION "supabase_realtime" OWNER TO "postgres";


GRANT USAGE ON SCHEMA "public" TO "postgres";
GRANT USAGE ON SCHEMA "public" TO "anon";
GRANT USAGE ON SCHEMA "public" TO "authenticated";
GRANT USAGE ON SCHEMA "public" TO "service_role";






















































































































































GRANT ALL ON FUNCTION "public"."expirar_invitaciones"("p_torneo_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."expirar_invitaciones"("p_torneo_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."expirar_invitaciones"("p_torneo_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."guardar_torneo_con_version"("p_datos" "jsonb", "p_expected_version" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."guardar_torneo_con_version"("p_datos" "jsonb", "p_expected_version" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."guardar_torneo_con_version"("p_datos" "jsonb", "p_expected_version" integer) TO "service_role";


















GRANT ALL ON TABLE "public"."grupos" TO "anon";
GRANT ALL ON TABLE "public"."grupos" TO "authenticated";
GRANT ALL ON TABLE "public"."grupos" TO "service_role";



GRANT ALL ON TABLE "public"."inscripciones" TO "anon";
GRANT ALL ON TABLE "public"."inscripciones" TO "authenticated";
GRANT ALL ON TABLE "public"."inscripciones" TO "service_role";



GRANT ALL ON TABLE "public"."invitacion_tokens" TO "anon";
GRANT ALL ON TABLE "public"."invitacion_tokens" TO "authenticated";
GRANT ALL ON TABLE "public"."invitacion_tokens" TO "service_role";



GRANT ALL ON TABLE "public"."jugadores" TO "anon";
GRANT ALL ON TABLE "public"."jugadores" TO "authenticated";
GRANT ALL ON TABLE "public"."jugadores" TO "service_role";



GRANT ALL ON TABLE "public"."parejas_grupo" TO "anon";
GRANT ALL ON TABLE "public"."parejas_grupo" TO "authenticated";
GRANT ALL ON TABLE "public"."parejas_grupo" TO "service_role";



GRANT ALL ON TABLE "public"."partidos" TO "anon";
GRANT ALL ON TABLE "public"."partidos" TO "authenticated";
GRANT ALL ON TABLE "public"."partidos" TO "service_role";



GRANT ALL ON TABLE "public"."partidos_finales" TO "anon";
GRANT ALL ON TABLE "public"."partidos_finales" TO "authenticated";
GRANT ALL ON TABLE "public"."partidos_finales" TO "service_role";



GRANT ALL ON TABLE "public"."puntos_jugador" TO "anon";
GRANT ALL ON TABLE "public"."puntos_jugador" TO "authenticated";
GRANT ALL ON TABLE "public"."puntos_jugador" TO "service_role";



GRANT ALL ON TABLE "public"."rechazos_vinculacion" TO "anon";
GRANT ALL ON TABLE "public"."rechazos_vinculacion" TO "authenticated";
GRANT ALL ON TABLE "public"."rechazos_vinculacion" TO "service_role";



GRANT ALL ON TABLE "public"."torneo_actual" TO "anon";
GRANT ALL ON TABLE "public"."torneo_actual" TO "authenticated";
GRANT ALL ON TABLE "public"."torneo_actual" TO "service_role";



GRANT ALL ON TABLE "public"."torneos" TO "anon";
GRANT ALL ON TABLE "public"."torneos" TO "authenticated";
GRANT ALL ON TABLE "public"."torneos" TO "service_role";









ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "service_role";































