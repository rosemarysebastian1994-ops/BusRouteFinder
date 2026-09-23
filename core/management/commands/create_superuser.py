import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Create a Django superuser from environment variables'

    def handle(self, *args, **options):
        User = get_user_model()

        username = os.environ.get('DJANGO_SUPERUSER_USERNAME')
        email = os.environ.get('DJANGO_SUPERUSER_EMAIL')
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')

        if not username or not password:
            self.stdout.write(
                self.style.ERROR(
                    'DJANGO_SUPERUSER_USERNAME and '
                    'DJANGO_SUPERUSER_PASSWORD must be set.'
                )
            )
            return

        if User.objects.filter(username=username).exists():
            self.stdout.write(
                self.style.WARNING(
                    f'Superuser "{username}" already exists.'
                )
            )
            return

        user = User.objects.create_superuser(
            username=username,
            email=email or '',
            password=password,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f'Superuser "{user.username}" created successfully.'
            )
        )