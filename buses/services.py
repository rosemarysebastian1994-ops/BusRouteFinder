from django.utils import timezone
from .models import Payment, Ticket, Notification, TransferBooking
from django.db.models import Q

from datetime import datetime, timedelta


def get_ticket_journey_end(ticket):
    """
    Calculate the scheduled arrival time at the ticket's
    destination.

    RouteStop.travel_time_minutes represents travel time
    from the previous stop to the current stop.
    Returns an aware datetime, or None if unavailable.
    """
    schedule = ticket.schedule
    source = ticket.source_stop
    destination = ticket.destination_stop

    if not all([schedule, source, destination]):
        return None

    if not schedule.departure_time or not ticket.journey_date:
        return None

    # Ensure the stops and schedule belong to the same route.
    if (
        source.route_id != destination.route_id
        or source.route_id != schedule.route_id
        or source.stop_order >= destination.stop_order
    ):
        return None

    # Get the route segments up to and including the destination.
    route_stops = (
        source.route.route_stops
        .filter(stop_order__gt=source.stop_order,
                stop_order__lte=destination.stop_order)
        .order_by('stop_order')
    )

    elapsed_minutes = 0
    expected_order = source.stop_order + 1
    destination_found = False

    for route_stop in route_stops:
        # Missing stops or gaps make the arrival time unreliable.
        if route_stop.stop_order != expected_order:
            return None

        if route_stop.travel_time_minutes is None:
            return None

        elapsed_minutes += route_stop.travel_time_minutes
        expected_order += 1

        if route_stop.pk == destination.pk:
            destination_found = True
            break

    if not destination_found:
        return None

    # The schedule departure time is assumed to be the time
    # the bus leaves the route's first stop.
    departure = timezone.make_aware(
        datetime.combine(
            ticket.journey_date,
            schedule.departure_time,
        ),
        timezone.get_current_timezone(),
    )

    return departure + timedelta(minutes=elapsed_minutes)

def get_payment_journey_end(payment):
    """
    Calculate the expected arrival time at the destination
    for a pending payment.

    Returns:
        datetime: Expected destination arrival time.
        None: If the required journey information is invalid
              or incomplete.
    """

    schedule = payment.schedule
    source = payment.source_stop
    destination = payment.destination_stop
    journey_date = payment.journey_date

    # Check that all required information exists.
    if not all([schedule, source, destination, journey_date]):
        return None

    if schedule.departure_time is None:
        return None

    # Ensure both stops belong to the schedule's route.
    if (
        source.route_id != destination.route_id
        or source.route_id != schedule.route_id
    ):
        return None

    # The destination must come after the source.
    if source.stop_order >= destination.stop_order:
        return None

    # Get only the stops after the source and up to
    # and including the destination.
    route_stops = (
        source.route.route_stops
        .filter(
            stop_order__gt=source.stop_order,
            stop_order__lte=destination.stop_order,
        )
        .order_by('stop_order')
    )

    elapsed_minutes = 0
    destination_found = False

    for route_stop in route_stops:
        if route_stop.travel_time_minutes is None:
            return None

        elapsed_minutes += route_stop.travel_time_minutes

        if route_stop.pk == destination.pk:
            destination_found = True
            break

    # Do not calculate an expiry time if the destination
    # was not found on the route.
    if not destination_found:
        return None

    # Assumption: schedule.departure_time is the departure
    # time from the beginning of the route.
    departure_datetime = datetime.combine(
        journey_date,
        schedule.departure_time,
    )

    departure_datetime = timezone.make_aware(
        departure_datetime,
        timezone.get_current_timezone(),
    )

    return departure_datetime + timedelta(
        minutes=elapsed_minutes
    )

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
    exclude_transfer_booking_id=None,
):
    """
    Calculate the number of seats available for a journey
    segment on a particular schedule and date.
    """
    bus = schedule.bus

    if bus is None:
        return 0

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
    # ACTIVE DIRECT PAYMENT RESERVATIONS
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
            transfer_booking__isnull=True,
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
    # ACTIVE TRANSFER RESERVATIONS - FIRST LEG
    # ---------------------------------------------------------

    first_leg_reservations = (
        TransferBooking.objects
        .filter(
            first_schedule=schedule,
            first_journey_date=journey_date,
            status='CREATED',
            first_source_stop__stop_order__lt=(
                destination_stop.stop_order
            ),
            first_destination_stop__stop_order__gt=(
                source_stop.stop_order
            ),
        )
    )

    if exclude_transfer_booking_id is not None:
        first_leg_reservations = (
            first_leg_reservations.exclude(
                pk=exclude_transfer_booking_id
            )
        )

    first_leg_reserved_passengers = sum(
        booking.passenger_count
        for booking in first_leg_reservations
    )

    # ---------------------------------------------------------
    # ACTIVE TRANSFER RESERVATIONS - SECOND LEG
    # ---------------------------------------------------------

    second_leg_reservations = (
        TransferBooking.objects
        .filter(
            second_schedule=schedule,
            second_journey_date=journey_date,
            status='CREATED',
            second_source_stop__stop_order__lt=(
                destination_stop.stop_order
            ),
            second_destination_stop__stop_order__gt=(
                source_stop.stop_order
            ),
        )
    )

    if exclude_transfer_booking_id is not None:
        second_leg_reservations = (
            second_leg_reservations.exclude(
                pk=exclude_transfer_booking_id
            )
        )

    second_leg_reserved_passengers = sum(
        booking.passenger_count
        for booking in second_leg_reservations
    )

    # ---------------------------------------------------------
    # TOTAL OCCUPIED / RESERVED SEATS
    # ---------------------------------------------------------

    occupied_seats = (
        booked_passengers
        + reserved_passengers
        + first_leg_reserved_passengers
        + second_leg_reserved_passengers
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