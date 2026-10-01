from datetime import datetime

from django.utils import timezone
from .models import Payment
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

from django.db.models import Q

from .models import Ticket


def get_available_seats(
    schedule,
    journey_date,
    source_stop,
    destination_stop,
):
    """
    Calculate the number of seats available for a journey
    segment on a particular schedule and date.

    Capacity is reserved by:

    1. Confirmed tickets.
    2. Active payment reservations that do not yet
       have a ticket.

    CANCELLED and COMPLETED tickets do not reserve capacity.

    REFUNDED payments do not reserve capacity.
    """

    bus = schedule.route.bus

    # ---------------------------------------------------------
    # CONFIRMED TICKETS
    # ---------------------------------------------------------

    overlapping_tickets = (
        Ticket.objects
        .filter(
            schedule=schedule,
            journey_date=journey_date,
            status='CONFIRMED',
            source_stop__stop_order__lt=(
                destination_stop.stop_order
            ),
            destination_stop__stop_order__gt=(
                source_stop.stop_order
            ),
        )
    )

    booked_passengers = sum(
        ticket.passenger_count
        for ticket in overlapping_tickets
    )

    # ---------------------------------------------------------
    # ACTIVE PAYMENT RESERVATIONS
    # ---------------------------------------------------------

    active_payment_reservations = (
        Payment.objects
        .filter(
            schedule=schedule,
            journey_date=journey_date,
            status__in=[
                'CREATED',
                'FAILED',
            ],
            ticket__isnull=True,
            source_stop__stop_order__lt=(
                destination_stop.stop_order
            ),
            destination_stop__stop_order__gt=(
                source_stop.stop_order
            ),
        )
    )

    reserved_passengers = sum(
        payment.passenger_count
        for payment in active_payment_reservations
    )

    # ---------------------------------------------------------
    # TOTAL OCCUPIED / RESERVED SEATS
    # ---------------------------------------------------------

    occupied_seats = (
        booked_passengers
        + reserved_passengers
    )

    return max(
        bus.capacity - occupied_seats,
        0
    )