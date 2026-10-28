from django.db import migrations


SQL_CREAR_PROTECCION = """
CREATE FUNCTION impedir_cambio_log_auditoria() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Los registros de auditoria son inmutables.';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER log_auditoria_inmutable
BEFORE UPDATE OR DELETE ON calificaciones_logauditoria
FOR EACH ROW EXECUTE FUNCTION impedir_cambio_log_auditoria();
"""

SQL_ELIMINAR_PROTECCION = """
DROP TRIGGER IF EXISTS log_auditoria_inmutable
ON calificaciones_logauditoria;
DROP FUNCTION IF EXISTS impedir_cambio_log_auditoria();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("calificaciones", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=SQL_CREAR_PROTECCION,
            reverse_sql=SQL_ELIMINAR_PROTECCION,
        ),
    ]
