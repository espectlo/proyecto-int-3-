#!/bin/sh
set -eu

POSTGRES_ADMIN_USER="${POSTGRES_ADMIN_USER:-$POSTGRES_USER}"

PGPASSWORD="$POSTGRES_PASSWORD" psql \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set ON_ERROR_STOP=1 \
  --set db_name="$POSTGRES_DB" \
  --set admin_user="$POSTGRES_ADMIN_USER" \
  --set app_password="$POSTGRES_APP_PASSWORD" \
  --set migration_password="$POSTGRES_MIGRATION_PASSWORD" \
  --set report_password="$POSTGRES_REPORT_PASSWORD" \
  --set backup_password="$POSTGRES_BACKUP_PASSWORD" <<'SQL'
SELECT 'ALTER ROLE nuam_app RENAME TO nuam_bootstrap'
WHERE EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'nuam_app' AND rolsuper
)
\gexec
SELECT 'ALTER ROLE nuam_bootstrap NOLOGIN'
WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nuam_bootstrap')
\gexec

SELECT format(
    'CREATE ROLE nuam_app LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION',
    :'app_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nuam_app')
\gexec
ALTER ROLE nuam_app WITH LOGIN PASSWORD :'app_password'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;

SELECT format(
    'CREATE ROLE nuam_migrator LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION',
    :'migration_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nuam_migrator')
\gexec
ALTER ROLE nuam_migrator WITH LOGIN PASSWORD :'migration_password'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;

SELECT format(
    'CREATE ROLE nuam_report LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION',
    :'report_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nuam_report')
\gexec
ALTER ROLE nuam_report WITH LOGIN PASSWORD :'report_password'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;

SELECT format(
    'CREATE ROLE nuam_backup LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION',
    :'backup_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nuam_backup')
\gexec
ALTER ROLE nuam_backup WITH LOGIN PASSWORD :'backup_password'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;

ALTER DATABASE :"db_name" OWNER TO nuam_migrator;
REASSIGN OWNED BY nuam_app TO nuam_migrator;
DO $$
DECLARE
    object_record record;
BEGIN
    FOR object_record IN
        SELECT c.relname, c.relkind, n.nspname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relowner = (SELECT oid FROM pg_roles WHERE rolname = 'nuam_bootstrap')
          AND c.relkind IN ('r', 'p', 'f', 'v', 'm', 'S')
        ORDER BY CASE c.relkind WHEN 'S' THEN 1 ELSE 0 END, c.relname
    LOOP
        EXECUTE format(
            'ALTER %s %I.%I OWNER TO nuam_migrator',
            CASE object_record.relkind
                WHEN 'S' THEN 'SEQUENCE'
                WHEN 'v' THEN 'VIEW'
                WHEN 'm' THEN 'MATERIALIZED VIEW'
                WHEN 'f' THEN 'FOREIGN TABLE'
                ELSE 'TABLE'
            END,
            object_record.nspname,
            object_record.relname
        );
    END LOOP;

    FOR object_record IN
        SELECT p.proname, p.prokind,
               pg_get_function_identity_arguments(p.oid) AS arguments
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public'
          AND p.proowner = (SELECT oid FROM pg_roles WHERE rolname = 'nuam_bootstrap')
          AND p.prokind IN ('f', 'p')
    LOOP
        EXECUTE format(
            'ALTER %s public.%I(%s) OWNER TO nuam_migrator',
            CASE object_record.prokind
                WHEN 'p' THEN 'PROCEDURE'
                ELSE 'FUNCTION'
            END,
            object_record.proname,
            object_record.arguments
        );
    END LOOP;
END
$$;
ALTER SCHEMA public OWNER TO nuam_migrator;
REVOKE ALL ON DATABASE :"db_name" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db_name"
    TO :"admin_user", nuam_app, nuam_migrator, nuam_report, nuam_backup;
GRANT TEMP ON DATABASE :"db_name"
    TO nuam_app, nuam_migrator, nuam_report;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO nuam_app, nuam_report, nuam_backup;
GRANT USAGE, CREATE ON SCHEMA public TO nuam_migrator;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO nuam_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO nuam_app;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO nuam_report, nuam_backup;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO nuam_report, nuam_backup;
GRANT pg_read_all_data TO nuam_backup;
DO $$
BEGIN
    IF to_regclass('public.calificaciones_logauditoria') IS NOT NULL THEN
        EXECUTE
            'REVOKE UPDATE, DELETE ON TABLE public.calificaciones_logauditoria '
            'FROM nuam_app';
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS public.registro_cambios_ddl (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    creado_en timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario text NOT NULL,
    comando text NOT NULL,
    tipo_objeto text,
    esquema text,
    identidad text
);
ALTER TABLE public.registro_cambios_ddl OWNER TO nuam_migrator;
GRANT SELECT ON public.registro_cambios_ddl TO nuam_report, nuam_backup;
REVOKE ALL ON public.registro_cambios_ddl FROM nuam_app;

CREATE OR REPLACE FUNCTION public.registrar_cambio_ddl()
RETURNS event_trigger
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $function$
DECLARE
    command_record record;
BEGIN
    FOR command_record IN SELECT * FROM pg_event_trigger_ddl_commands()
    LOOP
        INSERT INTO public.registro_cambios_ddl
            (usuario, comando, tipo_objeto, esquema, identidad)
        VALUES (
            current_user,
            TG_TAG,
            command_record.object_type,
            command_record.schema_name,
            command_record.object_identity
        );
    END LOOP;
END
$function$;
ALTER FUNCTION public.registrar_cambio_ddl() OWNER TO nuam_migrator;
SELECT 'CREATE EVENT TRIGGER nuam_auditoria_ddl ON ddl_command_end EXECUTE FUNCTION public.registrar_cambio_ddl()'
WHERE NOT EXISTS (
    SELECT 1 FROM pg_event_trigger WHERE evtname = 'nuam_auditoria_ddl'
)
\gexec

ALTER DEFAULT PRIVILEGES FOR ROLE nuam_migrator IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO nuam_app;
ALTER DEFAULT PRIVILEGES FOR ROLE nuam_migrator IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO nuam_app;
ALTER DEFAULT PRIVILEGES FOR ROLE nuam_migrator IN SCHEMA public
    GRANT SELECT ON TABLES TO nuam_report, nuam_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE nuam_migrator IN SCHEMA public
    GRANT SELECT ON SEQUENCES TO nuam_report, nuam_backup;

SQL
