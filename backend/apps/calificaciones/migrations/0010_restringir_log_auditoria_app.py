from django.db import migrations


SQL_RESTRINGIR_APP = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nuam_app') THEN
        EXECUTE
            'REVOKE UPDATE, DELETE ON TABLE calificaciones_logauditoria '
            'FROM nuam_app';
    END IF;
END;
$$;
"""

SQL_RESTAURAR_APP = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nuam_app') THEN
        EXECUTE
            'GRANT UPDATE, DELETE ON TABLE calificaciones_logauditoria '
            'TO nuam_app';
    END IF;
END;
$$;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("calificaciones", "0009_detallecarga_datos_normalizados"),
    ]

    operations = [
        migrations.RunSQL(
            sql=SQL_RESTRINGIR_APP,
            reverse_sql=SQL_RESTAURAR_APP,
        ),
    ]
