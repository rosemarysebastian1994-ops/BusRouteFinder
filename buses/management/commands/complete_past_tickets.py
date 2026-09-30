from django.core.management.base import BaseCommand

from buses.services import complete_past_tickets


class Command(BaseCommand):

    help = (
        'Mark confirmed tickets as completed '
        'after their scheduled arrival time.'
    )

    def handle(self, *args, **options):

        completed_count = complete_past_tickets()

        self.stdout.write(
            self.style.SUCCESS(
                f'{completed_count} ticket(s) marked as completed.'
            )
        )