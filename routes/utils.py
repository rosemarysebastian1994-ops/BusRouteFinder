from decimal import Decimal

from django.core.exceptions import ValidationError

from .models import Fare

from datetime import datetime, timedelta

from django.utils import timezone


def calculate_route_fare(
    source_route_stop,
    destination_route_stop,
):
    """
    Calculate the fare for travelling between two
    RouteStop records on the same route.

    Returns:
        Decimal fare amount
    """

    if source_route_stop.route_id != destination_route_stop.route_id:
        raise ValidationError(
            'Source and destination must belong to the same route.'
        )

    if (
        source_route_stop.stop_order
        >= destination_route_stop.stop_order
    ):
        raise ValidationError(
            'Destination must come after the source stop.'
        )

    distance = (
        destination_route_stop.distance_from_start_km
        - source_route_stop.distance_from_start_km
    )

    if distance <= 0:
        raise ValidationError(
            'Travel distance must be greater than zero.'
        )

    fare = (
        Fare.objects
        .filter(
            route_id=source_route_stop.route_id,
            is_active=True,
            min_distance_km__lte=distance,
            max_distance_km__gt=distance,
        )
        .order_by('min_distance_km')
        .first()
    )

    if fare is None:
        raise ValidationError(
            f'No fare slab is configured for '
            f'{distance:.2f} km.'
        )

    return fare.amount

from datetime import datetime, timedelta

from django.core.exceptions import ValidationError

from routes.models import Fare, RouteStop


def calculate_stop_arrival_datetime(
    schedule,
    route_stop,
    journey_date,
):
    """
    Calculate the scheduled arrival datetime for a
    particular RouteStop.

    travel_time_minutes is the travel time from the
    previous stop, so the values are accumulated from
    the beginning of the route.
    """

    if route_stop.route_id != schedule.route_id:

        raise ValidationError(
            'The selected stop does not belong '
            'to the scheduled route.'
        )

    route_stops = (
        RouteStop.objects
        .filter(
            route=schedule.route,
            stop_order__lte=route_stop.stop_order,
        )
        .order_by('stop_order')
    )

    minutes_from_departure = sum(
        route_stop.travel_time_minutes
        for route_stop in route_stops
    )

    departure_datetime = datetime.combine(
        journey_date,
        schedule.departure_time,
    )

    departure_datetime = timezone.make_aware(
        departure_datetime,
        timezone.get_current_timezone(),
    )

    return (
        departure_datetime
        + timedelta(
            minutes=minutes_from_departure
        )
    )

def calculate_stop_departure_time(
    schedule,
    route_stop,
    journey_date
):
    """
    Calculate the scheduled time at which a bus
    reaches a particular route stop.

    Returns:
        datetime
    """

    if route_stop.route_id != schedule.route_id:

        raise ValidationError(
            'The selected stop does not belong '
            'to the scheduled route.'
        )

    route_stops = (
        RouteStop.objects
        .filter(
            route=schedule.route,
            stop_order__lte=route_stop.stop_order
        )
        .order_by('stop_order')
    )

    minutes_from_departure = sum(
        route_stop.travel_time_minutes
        for route_stop in route_stops
    )

    departure_datetime = datetime.combine(
        journey_date,
        schedule.departure_time
    )

    return (
        departure_datetime
        + timedelta(
            minutes=minutes_from_departure
        )
    )