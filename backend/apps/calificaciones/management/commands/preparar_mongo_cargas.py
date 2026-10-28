from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from apps.calificaciones.mongodb_schema import preparar_esquema_cargas


class Command(BaseCommand):
    help = "Crea y valida las colecciones e índices de las cargas en MongoDB."

    def handle(self, *args, **options):
        cliente = MongoClient(
            settings.MONGO_URI,
            connectTimeoutMS=5000,
            serverSelectionTimeoutMS=5000,
        )
        try:
            cliente.admin.command("ping")
            preparar_esquema_cargas(cliente[settings.MONGO_DB])
        except PyMongoError as error:
            raise CommandError(
                f"No se pudo preparar el esquema MongoDB: {error}"
            ) from error
        finally:
            cliente.close()
        self.stdout.write(
            self.style.SUCCESS(
                f"Esquema de cargas preparado en MongoDB: {settings.MONGO_DB}"
            )
        )
