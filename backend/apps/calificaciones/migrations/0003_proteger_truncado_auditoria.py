from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("calificaciones", "0002_log_auditoria_inmutable"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE TRIGGER log_auditoria_no_truncar
                BEFORE TRUNCATE ON calificaciones_logauditoria
                FOR EACH STATEMENT
                EXECUTE FUNCTION impedir_cambio_log_auditoria();
            """,
            reverse_sql="""
                DROP TRIGGER IF EXISTS log_auditoria_no_truncar
                ON calificaciones_logauditoria;
            """,
        ),
    ]
