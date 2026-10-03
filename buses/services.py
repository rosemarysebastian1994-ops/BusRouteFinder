from datetime import datetime

from django.utils import timezone
from .models import Payment, Ticket, Notification
from django.db.models import Q


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

def create_notification(
    passenger,
    title,
    message,
    notification_type='GENERAL',
    ticket=None,
):
    """
    Create an in-app notification for a passenger.

    Args:
        passenger: User receiving the notification.
        title: Short notification title.
        message: Notification message.
        notification_type: Notification category.
        ticket: Optional ticket associated with the notification.

    Returns:
        Notification: The newly created notification.
    """

    return Notification.objects.create(
        passenger=passenger,
        ticket=ticket,
        notification_type=notification_type,
        title=title,
        message=message,
    )

def notify_passengers_of_departure(
    bus,
    route,
    route_stop,
    departure_time,
):
    """
    Notify passengers whose confirmed journey starts
    from the stop the bus has just departed.
    """

    today = timezone.localtime(
        departure_time
    ).date()

    tickets = Ticket.objects.filter(
        schedule__route=route,
        source_stop=route_stop,
        journey_date=today,
        status='CONFIRMED',
    ).select_related(
        'passenger',
        'destination_stop__stop',
    )

    for ticket in tickets:

        already_notified = Notification.objects.filter(
            ticket=ticket,
            notification_type='DEPARTURE',
        ).exists()

        if already_notified:
            continue

        create_notification(
            passenger=ticket.passenger,
            title='Bus Departed',
            message=(
                f'Your bus {bus.bus_number} has departed '
                f'from {route_stop.stop.name}. '
                f'Your journey to '
                f'{ticket.destination_stop.stop.name} '
                f'has started.'
            ),
            notification_type='DEPARTURE',
            ticket=ticket,
        )

def notify_passengers_of_approaching(
    bus,
    route,
    route_stop,
    current_time,
):
    """
    Notify passengers when their bus is approaching
    their source stop.
    """

    today = timezone.localtime(
        current_time
    ).date()

    tickets = Ticket.objects.filter(
        schedule__route=route,
        source_stop=route_stop,
        journey_date=today,
        status='CONFIRMED',
    ).select_related(
        'passenger',
        'destination_stop__stop',
    )

    for ticket in tickets:

        already_notified = Notification.objects.filter(
            ticket=ticket,
            notification_type='APPROACHING',
        ).exists()

        if already_notified:
            continue

        create_notification(
            passenger=ticket.passenger,
            title='Bus Approaching',
            message=(
                f'Your bus {bus.bus_number} is approaching '
                f'{route_stop.stop.name}. '
                f'Please be ready to board.'
            ),
            notification_type='APPROACHING',
            ticket=ticket,
        )

def notify_passengers_of_arrival(
    bus,
    route,
    route_stop,
    arrival_time,
):
    """
    Notify passengers when their bus arrives
    at their source stop.
    """

    today = timezone.localtime(
        arrival_time
    ).date()

    tickets = Ticket.objects.filter(
        schedule__route=route,
        source_stop=route_stop,
        journey_date=today,
        status='CONFIRMED',
    ).select_related(
        'passenger',
        'destination_stop__stop',
    )

    for ticket in tickets:

        already_notified = Notification.objects.filter(
            ticket=ticket,
            notification_type='ARRIVED',
        ).exists()

        if already_notified:
            continue

        create_notification(
            passenger=ticket.passenger,
            title='Bus Arrived',
            message=(
                f'Your bus {bus.bus_number} has arrived '
                f'at {route_stop.stop.name}. '
                f'Please board the bus.'
            ),
            notification_type='ARRIVED',
            ticket=ticket,
        )

def notify_passengers_of_journey_completion(
    bus,
    route,
    route_stop,
    arrival_time,
):
    """
    Notify passengers when their bus arrives at
    their destination stop.
    """

    today = timezone.localtime(
        arrival_time
    ).date()

    tickets = Ticket.objects.filter(
        schedule__route=route,
        destination_stop=route_stop,
        journey_date=today,
        status='CONFIRMED',
    ).select_related(
        'passenger',
        'source_stop__stop',
    )

    for ticket in tickets:

        already_notified = Notification.objects.filter(
            ticket=ticket,
            notification_type='COMPLETED',
        ).exists()

        if already_notified:
            continue

        create_notification(
            passenger=ticket.passenger,
            title='Journey Completed',
            message=(
                f'Your bus {bus.bus_number} has arrived '
                f'at your destination, '
                f'{route_stop.stop.name}. '
                f'Your journey is complete.'
            ),
            notification_type='COMPLETED',
            ticket=ticket,
        )