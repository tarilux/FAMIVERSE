import getpass
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Account
from core.models import Family


class Command(BaseCommand):
    help = "Create the first family and parent account."

    def handle(self, *args, **options):
        if Family.objects.exists():
            raise CommandError("A family is already configured.")

        family_name = input("Family name: ").strip()
        username = input("Parent login: ").strip()
        pin = getpass.getpass("Parent code (4 to 6 digits): ")
        confirmation = getpass.getpass("Confirm parent code: ")

        if not family_name or not username:
            raise CommandError("Family name and parent login are required.")
        if not re.fullmatch(r"\d{4,6}", pin):
            raise CommandError("The parent code must contain 4 to 6 digits.")
        if pin != confirmation:
            raise CommandError("The codes do not match.")
        if Account.objects.filter(username__iexact=username).exists():
            raise CommandError("That login is already in use.")

        with transaction.atomic():
            family = Family.objects.create(name=family_name)
            Account.objects.create_user(
                username=username,
                password=pin,
                role=Account.Role.PARENT,
                family=family,
            )

        self.stdout.write(self.style.SUCCESS("Family and parent account created."))
