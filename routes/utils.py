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


from datetime import datetime, timedelta

from .models import Route, RouteStop, BusSchedule


DAY_CODES = [
    "MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN",
]


def _day_code(day):
    return DAY_CODES[day.weekday()]


def _elapsed_from_origin(route_stops, target_stop):
    """
    Minutes from the route origin to target_stop.
    travel_time_minutes is the time from the previous stop.
    """
    return sum(
        rs.travel_time_minutes or 0
        for rs in route_stops
        if 1 < rs.stop_order <= target_stop.stop_order
    )


def _segment_duration(route_stops, start_stop, end_stop):
    """Minutes travelled from start_stop to end_stop."""
    return sum(
        rs.travel_time_minutes or 0
        for rs in route_stops
        if start_stop.stop_order < rs.stop_order <= end_stop.stop_order
    )


def _scheduled_time(schedule, stop, route_stops, origin_date):
    """
    Calculate the actual datetime at a stop for a schedule
    whose departure_time is the departure from the route origin.
    Return None if the schedule does not operate on origin_date.
    """
    if schedule.day != _day_code(origin_date):
        return None

    origin_departure = datetime.combine(
        origin_date,
        schedule.departure_time,
    )

    elapsed = _elapsed_from_origin(route_stops, stop)

    return origin_departure + timedelta(minutes=elapsed)


def find_routes_with_transfer(
    source_stops,
    destination_stops,
    travel_date,
    selected_departure_time=None,
    min_layover_minutes=30,
):
    """
    Find journeys with exactly one transfer.

    source_stops and destination_stops are querysets or collections
    of Stop objects matched by the search form.
    travel_date is a datetime.date object.
    """
    source_ids = {stop.pk for stop in source_stops}
    destination_ids = {stop.pk for stop in destination_stops}

    if not source_ids or not destination_ids:
        return []

    routes = list(
        Route.objects
        .filter(
            route_stops__stop_id__in=source_ids | destination_ids
        )
        .prefetch_related(
            "route_stops__stop",
            "schedules__bus",
        )
        .distinct()
    )

    route_data = {}

    for route in routes:
        stops = list(route.route_stops.all())
        route_data[route.pk] = {
            "route": route,
            "stops": stops,
            "schedules": [
                schedule
                for schedule in route.schedules.all()
                if schedule.is_active and schedule.bus_id is not None
            ],
        }

    first_day = travel_date - timedelta(days=1)
    transfer_results = []
    seen = set()

    for first_data in route_data.values():
        first_route = first_data["route"]
        first_stops = first_data["stops"]

        source_options = [
            rs for rs in first_stops
            if rs.stop_id in source_ids
        ]

        for first_source in source_options:
            for first_transfer in first_stops:
                if not (
                    first_source.stop_order < first_transfer.stop_order
                ):
                    continue

                if first_transfer.stop_id in source_ids | destination_ids:
                    continue

                first_duration = _segment_duration(
                    first_stops,
                    first_source,
                    first_transfer,
                )

                for first_schedule in first_data["schedules"]:
                    # The bus can leave its route origin the previous
                    # day and reach the searched source after midnight.
                    first_departure = None

                    for origin_date in (
                        first_day,
                        travel_date,
                    ):
                        candidate = _scheduled_time(
                            first_schedule,
                            first_source,
                            first_stops,
                            origin_date,
                        )

                        if candidate and candidate.date() == travel_date:
                            first_departure = candidate
                            break

                    if first_departure is None:
                        continue

                    if (
                        selected_departure_time
                        and first_departure.time() < selected_departure_time
                    ):
                        continue

                    transfer_arrival = (
                        first_departure
                        + timedelta(minutes=first_duration)
                    )

                    for second_data in route_data.values():
                        second_route = second_data["route"]

                        if second_route.pk == first_route.pk:
                            continue

                        second_stops = second_data["stops"]

                        second_transfer_options = [
                            rs for rs in second_stops
                            if rs.stop_id == first_transfer.stop_id
                        ]

                        second_destination_options = [
                            rs for rs in second_stops
                            if rs.stop_id in destination_ids
                        ]

                        for second_transfer in second_transfer_options:
                            for second_destination in second_destination_options:
                                if not (
                                    second_transfer.stop_order
                                    < second_destination.stop_order
                                ):
                                    continue

                                second_duration = _segment_duration(
                                    second_stops,
                                    second_transfer,
                                    second_destination,
                                )

                                for second_schedule in second_data["schedules"]:
                                    second_departure = None

                                    # Include the previous, same, and next
                                    # origin dates to support overnight travel.
                                    for offset in (-1, 0, 1):
                                        origin_date = (
                                            transfer_arrival.date()
                                            + timedelta(days=offset)
                                        )

                                        candidate = _scheduled_time(
                                            second_schedule,
                                            second_transfer,
                                            second_stops,
                                            origin_date,
                                        )

                                        if (
                                            candidate
                                            and candidate
                                            >= transfer_arrival
                                            + timedelta(
                                                minutes=min_layover_minutes
                                            )
                                        ):
                                            if (
                                                second_departure is None
                                                or candidate < second_departure
                                            ):
                                                second_departure = candidate

                                    if second_departure is None:
                                        continue

                                    destination_arrival = (
                                        second_departure
                                        + timedelta(minutes=second_duration)
                                    )

                                    # Calculate fare for the first leg.
                                    try:
                                        first_fare = calculate_route_fare(
                                            first_source,
                                            first_transfer,
                                        )
                                    except ValidationError:
                                        first_fare = None

                                    # Calculate fare for the second leg.
                                    try:
                                        second_fare = calculate_route_fare(
                                            second_transfer,
                                            second_destination,
                                        )
                                    except ValidationError:
                                        second_fare = None

                                    # Calculate the combined fare only when both
                                    # individual fares are available.
                                    if first_fare is not None and second_fare is not None:
                                        total_fare = first_fare + second_fare
                                    else:
                                        total_fare = None

                                    key = (
                                        first_schedule.pk,
                                        first_source.pk,
                                        first_transfer.pk,
                                        second_schedule.pk,
                                        second_destination.pk,
                                        first_departure,
                                        second_departure,
                                    )

                                    if key in seen:
                                        continue

                                    seen.add(key)

                                    transfer_results.append({
                                        "first_schedule": first_schedule,
                                        "second_schedule": second_schedule,
                                        "first_route": first_route,
                                        "second_route": second_route,
                                        "first_fare": first_fare,
                                        "second_fare": second_fare,
                                        "total_fare": total_fare,
                                        "source_stop": first_source.stop,
                                        "transfer_stop": first_transfer.stop,
                                        "destination_stop": second_destination.stop,
                                        "first_departure": first_departure,
                                        "transfer_arrival": transfer_arrival,
                                        "second_departure": second_departure,
                                        "destination_arrival": destination_arrival,
                                        "layover_minutes": int(
                                            (
                                                second_departure
                                                - transfer_arrival
                                            ).total_seconds() // 60
                                        ),
                                        "total_minutes": int(
                                            (
                                                destination_arrival
                                                - first_departure
                                            ).total_seconds() // 60
                                        ),
                                    })

    return sorted(
        transfer_results,
        key=lambda journey: journey["first_departure"],
    )