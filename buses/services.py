from datetime import datetime

from django.utils import timezone

from .models import Ticket


def complete_past_tickets():
    """
    Mark confirmed tickets as COMPLETED after their
    scheduled journey has ended.

    Uses the ticket's journey date and schedule arrival time.
    """

    now = timezone.now()

    tickets = (
        Ticket.objects
        .filter(status='CONFIRMED')
        .select_related('schedule')
    )

    completed_count = 0

    for ticket in tickets:

        arrival_time = ticket.schedule.arrival_time

        # If no arrival time is configured, we cannot
        # determine when the journey ends.
        if arrival_time is None:
            continue

        journey_end = timezone.make_aware(
            datetime.combine(
                ticket.journey_date,
                arrival_time
            )
        )

        if now >= journey_end:

            ticket.status = 'COMPLETED'

            ticket.save(
                update_fields=[
                    'status',
                    'updated_at',
                ]
            )

            completed_count += 1

    return completed_count