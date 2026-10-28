import logging
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from apps.calificaciones.outbox import procesar_siguiente_carga

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Procesa de forma idempotente el outbox de cargas masivas."

    def add_arguments(self, parser):
        parser.add_argument(
            "--intervalo",
            type=float,
            default=2.0,
            help="Segundos entre consultas cuando no hay cargas pendientes.",
        )
        parser.add_argument(
            "--una-vez",
            action="store_true",
            help="Procesa como máximo una carga y termina.",
        )

    def handle(self, *args, **options):
        intervalo = max(options["intervalo"], 0.1)
        cliente_mongo = MongoClient(
            settings.MONGO_URI,
            connectTimeoutMS=5000,
            serverSelectionTimeoutMS=5000,
        )
        self.stdout.write("Worker de cargas outbox iniciado.")
        try:
            try:
                cliente_mongo.admin.command("ping")
            except PyMongoError as error:
                raise CommandError(
                    f"No se pudo conectar a MongoDB: {error}"
                ) from error
            while True:
                try:
                    procesada = procesar_siguiente_carga(cliente_mongo)
                except DatabaseError:
                    logger.exception(
                        "No se pudo consultar o confirmar el outbox en PostgreSQL."
                    )
                    if options["una_vez"]:
                        raise
                    time.sleep(intervalo)
                    continue
                if options["una_vez"]:
                    return
                if not procesada:
                    time.sleep(intervalo)
        finally:
            cliente_mongo.close()
