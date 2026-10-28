from getpass import getpass

from django.contrib.auth import get_user_model, password_validation
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.cuentas.models import Rol, Usuario


class Command(BaseCommand):
    help = "Crea de forma interactiva el primer perfil administrador de NUAM."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="Correo del administrador.")

    @transaction.atomic
    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        if not email:
            raise CommandError("El correo electrónico es obligatorio.")
        if Usuario.objects.filter(email__iexact=email).exists():
            raise CommandError("Ya existe un perfil NUAM con ese correo.")

        try:
            rol = Rol.objects.get(codigo=Rol.Codigo.ADMINISTRADOR)
        except Rol.DoesNotExist as error:
            raise CommandError(
                "No existe el rol administrador; ejecuta primero sembrar_catalogos."
            ) from error

        password = getpass("Contraseña inicial (no se mostrará): ")
        password_confirmacion = getpass("Repite la contraseña: ")
        if password != password_confirmacion:
            raise CommandError("Las contraseñas no coinciden.")

        user_model = get_user_model()
        account = user_model()
        username_field = user_model.USERNAME_FIELD
        setattr(account, username_field, email)
        if any(field.name == "email" for field in user_model._meta.fields):
            account.email = email
        password_validation.validate_password(password, account)

        account = user_model._default_manager.create_user(
            **{username_field: email},
            password=password,
            email=email,
        )
        perfil = Usuario(
            cuenta=account,
            email=email,
            rol=rol,
        )
        perfil.full_clean()
        perfil.save()

        self.stdout.write(
            self.style.SUCCESS(f"Perfil administrador creado para {email}.")
        )
