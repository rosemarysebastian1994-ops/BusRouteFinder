from django.shortcuts import render, get_object_or_404, redirect
import json
import math
import urllib.request
import razorpay
from django.core.cache import cache
# Create your views here.
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from routes.models import Route, RouteStop, BusSchedule
from math import radians, sin, cos, sqrt, atan2
from decimal import Decimal
import uuid
from datetime import datetime
from django.utils import timezone
from django.core.exceptions import ValidationError
from .models import Bus, BusLocation, BusStopVisit, Ticket, Payment

from django.contrib.admin.views.decorators import staff_member_required

from django.contrib.auth.models import Group
from django.contrib import messages
from django.conf import settings
from django.db import transaction

from .forms import TicketBookingForm

from .services import complete_past_tickets, get_available_seats

STOP_ARRIVAL_DISTANCE_KM = 0.08
STOP_DEPARTURE_DISTANCE_KM = 0.15

def bus_detail(request, bus_id):

    bus = get_object_or_404(
        Bus,
        id=bus_id
    )

    routes = (
        bus.routes
        .all()
        .order_by('route_name')
    )

    return render(
        request,
        'buses/bus_detail.html',
        {
            'bus': bus,
            'routes': routes,
        }
    )

def bus_timings(request, bus_id):

    bus = get_object_or_404(
        Bus,
        id=bus_id
    )

    schedules = (
        BusSchedule.objects
        .filter(
            route__bus=bus,
            is_active=True
        )
        .select_related('route')
        .order_by(
            'day_order',
            'departure_time'
        )
    )

    return render(
        request,
        'buses/bus_timings.html',
        {
            'bus': bus,
            'schedules': schedules,
        }
    )

@login_required
def driver_tracking(request):

    bus = (
        Bus.objects
        .select_related('current_route')
        .prefetch_related(
            'routes__route_stops__stop'
        )
        .filter(driver=request.user)
        .first()
    )

    route_data = {}

    if bus:

        route_data[str(bus.id)] = {}

        for route in bus.routes.all():

            route_data[str(bus.id)][str(route.id)] = {
                'routeName': route.route_name,
                'stops': [
                    {
                        'name': route_stop.stop.name,
                        'latitude': (
                            float(route_stop.stop.latitude)
                            if route_stop.stop.latitude is not None
                            else None
                        ),
                        'longitude': (
                            float(route_stop.stop.longitude)
                            if route_stop.stop.longitude is not None
                            else None
                        ),
                        'order': route_stop.stop_order,
                    }
                    for route_stop in route.route_stops.all()
                ],
            }

    return render(
        request,
        'buses/driver_tracking.html',
        {
            'bus': bus,
            'route_data': route_data,
        },
    )

@login_required
def update_bus_location(request):

    if request.method != 'POST':
        return JsonResponse(
            {
                'success': False,
                'message': 'POST request required.'
            },
            status=405
        )

    # --------------------------------------------------
    # DRIVER AUTHORIZATION
    # --------------------------------------------------

    if not request.user.groups.filter(
        name='Drivers'
    ).exists():

        return JsonResponse(
            {
                'success': False,
                'message': 'You are not authorized to update bus location.'
            },
            status=403
        )

    bus_id = request.POST.get('bus_id')
    latitude = request.POST.get('latitude')
    longitude = request.POST.get('longitude')
    speed = request.POST.get('speed')
    heading = request.POST.get('heading')
    accuracy = request.POST.get('accuracy')

    if not bus_id or not latitude or not longitude:
        return JsonResponse(
            {
                'success': False,
                'message': 'Bus and GPS coordinates are required.'
            },
            status=400
        )

    # --------------------------------------------------
    # ONLY THE DRIVER'S ASSIGNED BUS
    # --------------------------------------------------

    bus = get_object_or_404(
        Bus,
        id=bus_id,
        driver=request.user
    )

    location = (
        BusLocation.objects
        .filter(bus=bus)
        .first()
    )

    # --------------------------------------------------
    # START A NEW TRACKING SESSION
    # --------------------------------------------------

    if location and not location.is_tracking:

        location.tracking_session_id = uuid.uuid4()

        location.current_route_stop = None

        location.stop_status = 'TRAVELLING'

        location.stop_arrived_at = None
        location.stop_departed_at = None

    # --------------------------------------------------
    # CREATE / UPDATE LOCATION
    # --------------------------------------------------

    if location:

        location.latitude = latitude
        location.longitude = longitude
        location.speed = speed or None
        location.heading = heading or None
        location.accuracy = accuracy or None
        location.is_tracking = True

        location.save()

    else:

        location = BusLocation.objects.create(
            bus=bus,
            latitude=latitude,
            longitude=longitude,
            speed=speed or None,
            heading=heading or None,
            accuracy=accuracy or None,
            is_tracking=True
        )

    # --------------------------------------------------
    # STOP ARRIVAL / DEPARTURE DETECTION
    # --------------------------------------------------

    stop_event = None

    route = bus.current_route

    if route:

        stop_event = detect_stop_arrival_departure(
            location,
            route,
            float(latitude),
            float(longitude)
        )

    return JsonResponse({
        'success': True,
        'message': 'Location updated successfully.',
        'latitude': float(location.latitude),
        'longitude': float(location.longitude),
        'is_tracking': location.is_tracking,

        'stop_event': (
            {
                'type': stop_event['event'],
                'stop_name': (
                    stop_event['stop'].stop.name
                ),
                'arrival_time': (
                    stop_event['arrival_time'].isoformat()
                    if stop_event['arrival_time']
                    else None
                ),
                'departure_time': (
                    stop_event['departure_time'].isoformat()
                    if stop_event['departure_time']
                    else None
                ),
            }
            if stop_event
            else None
        ),
    })

@login_required
def stop_bus_tracking(request):

    if request.method != 'POST':
        return JsonResponse(
            {
                'success': False,
                'message': 'POST request required.'
            },
            status=405
        )

    # --------------------------------------------------
    # DRIVER AUTHORIZATION
    # --------------------------------------------------

    if not request.user.groups.filter(
        name='Drivers'
    ).exists():

        return JsonResponse(
            {
                'success': False,
                'message': 'You are not authorized to stop bus tracking.'
            },
            status=403
        )

    bus_id = request.POST.get('bus_id')

    if not bus_id:
        return JsonResponse(
            {
                'success': False,
                'message': 'Bus is required.'
            },
            status=400
        )

    # --------------------------------------------------
    # ONLY THE DRIVER'S ASSIGNED BUS
    # --------------------------------------------------

    bus = get_object_or_404(
        Bus,
        id=bus_id,
        driver=request.user
    )

    location = BusLocation.objects.filter(
        bus=bus
    ).first()

    if not location:
        return JsonResponse(
            {
                'success': False,
                'message': 'No GPS location exists for this bus.'
            },
            status=404
        )

    location.is_tracking = False

    location.save(
        update_fields=['is_tracking']
    )

    return JsonResponse(
        {
            'success': True,
            'message': 'GPS tracking stopped.',
            'bus_id': bus.id,
            'is_tracking': False,
        }
    )

@login_required
def live_buses(request):

    buses = Bus.objects.order_by(
        'bus_number'
    )

    return render(
        request,
        'buses/live_buses.html',
        {
            'buses': buses,
        }
    )

def calculate_distance_km(
    latitude1,
    longitude1,
    latitude2,
    longitude2
):
    """
    Calculate the approximate distance between
    two GPS coordinates using the Haversine formula.
    """

    earth_radius_km = 6371.0

    lat1 = radians(float(latitude1))
    lat2 = radians(float(latitude2))

    delta_lat = radians(
        float(latitude2) - float(latitude1)
    )

    delta_lon = radians(
        float(longitude2) - float(longitude1)
    )

    a = (
        sin(delta_lat / 2) ** 2
        +
        cos(lat1)
        * cos(lat2)
        * sin(delta_lon / 2) ** 2
    )

    c = 2 * atan2(
        sqrt(a),
        sqrt(1 - a)
    )

    return earth_radius_km * c


from routes.models import RouteStop


def detect_stop_arrival_departure(
    location,
    route,
    latitude,
    longitude
):

    route_stops = list(
        route.route_stops
        .select_related('stop')
        .order_by('stop_order')
    )

    route_stops = [
        route_stop
        for route_stop in route_stops
        if (
            route_stop.stop.latitude is not None
            and
            route_stop.stop.longitude is not None
        )
    ]

    if not route_stops:
        return None

    now = timezone.now()

    current_route_stop = location.current_route_stop

    # ==================================================
    # NO CURRENT STOP
    # ==================================================
    #
    # IMPORTANT:
    # Do NOT search for the nearest stop.
    #
    # The bus must always follow the route order.
    #
    # The first expected stop is route_stops[0].
    # ==================================================

    if current_route_stop is None:

        current_route_stop = route_stops[0]

        location.current_route_stop = current_route_stop
        location.stop_status = 'TRAVELLING'
        location.stop_arrived_at = None
        location.stop_departed_at = None

        location.save(
            update_fields=[
                'current_route_stop',
                'stop_status',
                'stop_arrived_at',
                'stop_departed_at',
            ]
        )

    # ==================================================
    # FIND CURRENT EXPECTED STOP IN ROUTE
    # ==================================================

    try:

        current_index = next(
            index
            for index, route_stop
            in enumerate(route_stops)
            if route_stop.id == current_route_stop.id
        )

    except StopIteration:

        # Current stop does not belong to this route.
        # Restart from the first stop.

        current_route_stop = route_stops[0]

        location.current_route_stop = current_route_stop
        location.stop_status = 'TRAVELLING'
        location.stop_arrived_at = None
        location.stop_departed_at = None

        location.save(
            update_fields=[
                'current_route_stop',
                'stop_status',
                'stop_arrived_at',
                'stop_departed_at',
            ]
        )

        current_index = 0

    # ==================================================
    # DISTANCE FROM CURRENT EXPECTED STOP
    # ==================================================

    current_distance = calculate_distance_km(
        latitude,
        longitude,
        current_route_stop.stop.latitude,
        current_route_stop.stop.longitude
    )

    # ==================================================
    # TRAVELLING TOWARD CURRENT STOP
    # ==================================================

    if location.stop_status == 'TRAVELLING':

        if current_distance <= STOP_ARRIVAL_DISTANCE_KM:

            visit = BusStopVisit.objects.create(
                bus=location.bus,
                route=route,
                route_stop=current_route_stop,
                tracking_session_id=(
                    location.tracking_session_id
                ),
                arrival_time=now
            )

            location.stop_status = 'ARRIVED'
            location.stop_arrived_at = now
            location.stop_departed_at = None

            location.save(
                update_fields=[
                    'stop_status',
                    'stop_arrived_at',
                    'stop_departed_at',
                ]
            )

            return {
                'event': 'ARRIVAL',
                'stop': current_route_stop,
                'arrival_time': now,
                'departure_time': None,
            }

        # Still travelling toward the expected stop.
        return None

    # ==================================================
    # BUS HAS ARRIVED — CHECK FOR DEPARTURE
    # ==================================================

    if location.stop_status == 'ARRIVED':

        if current_distance > STOP_DEPARTURE_DISTANCE_KM:

            visit = (
                BusStopVisit.objects
                .filter(
                    bus=location.bus,
                    route=route,
                    route_stop=current_route_stop,
                    tracking_session_id=(
                        location.tracking_session_id
                    ),
                    departure_time__isnull=True
                )
                .order_by('-arrival_time')
                .first()
            )

            if visit:
                visit.departure_time = now

                visit.save(
                    update_fields=[
                        'departure_time'
                    ]
                )

            # ------------------------------------------
            # FIND THE NEXT STOP
            # ------------------------------------------

            next_index = current_index + 1

            # ------------------------------------------
            # FINAL STOP
            # ------------------------------------------

            if next_index >= len(route_stops):
                location.stop_status = 'DEPARTED'
                location.stop_departed_at = now

                location.last_departure_stop = (
                    current_route_stop
                )

                location.last_departure_at = now

                location.save(
                    update_fields=[
                        'stop_status',
                        'stop_departed_at',
                        'last_departure_stop',
                        'last_departure_at',
                    ]
                )

                return {
                    'event': 'DEPARTURE',
                    'stop': current_route_stop,
                    'next_stop': None,
                    'arrival_time': (
                        visit.arrival_time
                        if visit
                        else location.stop_arrived_at
                    ),
                    'departure_time': now,
                }

            # ------------------------------------------
            # NEXT STOP EXISTS
            # ------------------------------------------

            next_route_stop = route_stops[next_index]

            # ------------------------------------------
            # Remember the stop we just departed from
            # ------------------------------------------

            location.last_departure_stop = (
                current_route_stop
            )

            location.last_departure_at = now

            # ------------------------------------------
            # The current route stop now becomes the
            # stop we are travelling toward.
            # ------------------------------------------

            location.current_route_stop = next_route_stop

            location.stop_status = 'TRAVELLING'

            location.stop_departed_at = now

            location.save(
                update_fields=[
                    'current_route_stop',
                    'stop_status',
                    'stop_departed_at',
                    'last_departure_stop',
                    'last_departure_at',
                ]
            )

            return {
                'event': 'DEPARTURE',

                'stop': current_route_stop,

                'next_stop': next_route_stop,

                'arrival_time': (
                    visit.arrival_time
                    if visit
                    else location.stop_arrived_at
                ),

                'departure_time': now,
            }

        # Still at the stop.
        return None

    return None

def get_osrm_segment_geometry(
    from_stop,
    to_stop
):
    """
    Get the driving-road geometry between two stops
    from OSRM.

    The result is cached so that we do not request
    the same road segment from OSRM on every GPS update.

    Returns:
        List of [longitude, latitude] coordinates
        or None if OSRM cannot provide a route.
    """

    if not from_stop or not to_stop:
        return None

    if (
        from_stop.latitude is None
        or from_stop.longitude is None
        or to_stop.latitude is None
        or to_stop.longitude is None
    ):
        return None

    cache_key = (
        f"osrm_segment_"
        f"{from_stop.id}_"
        f"{to_stop.id}"
    )

    cached_geometry = cache.get(
        cache_key
    )

    if cached_geometry:
        return cached_geometry

    coordinates = (
        f"{from_stop.longitude},{from_stop.latitude};"
        f"{to_stop.longitude},{to_stop.latitude}"
    )

    url = (
        "https://router.project-osrm.org/"
        "route/v1/driving/"
        f"{coordinates}"
        "?overview=full"
        "&geometries=geojson"
    )

    try:

        with urllib.request.urlopen(
            url,
            timeout=10
        ) as response:

            data = json.loads(
                response.read().decode("utf-8")
            )

    except Exception as error:

        print(
            "OSRM request failed:",
            error
        )

        return None

    if (
        data.get("code") != "Ok"
        or not data.get("routes")
    ):
        return None

    geometry = (
        data["routes"][0]
        .get("geometry")
        .get("coordinates")
    )

    if not geometry:
        return None

    # Cache for 24 hours.
    cache.set(
        cache_key,
        geometry,
        60 * 60 * 24
    )

    return geometry

def get_osrm_segment_distance(
    from_stop,
    to_stop
):
    """
    Get the driving-road distance between two stops
    from OSRM.

    Returns:
        Distance in kilometers, or None if OSRM cannot
        provide a route.
    """

    if not from_stop or not to_stop:
        return None

    if (
        from_stop.latitude is None
        or from_stop.longitude is None
        or to_stop.latitude is None
        or to_stop.longitude is None
    ):
        return None

    cache_key = (
        f"osrm_distance_"
        f"{from_stop.id}_"
        f"{to_stop.id}"
    )

    cached_distance = cache.get(
        cache_key
    )

    if cached_distance is not None:
        return cached_distance

    coordinates = (
        f"{from_stop.longitude},{from_stop.latitude};"
        f"{to_stop.longitude},{to_stop.latitude}"
    )

    url = (
        "https://router.project-osrm.org/"
        "route/v1/driving/"
        f"{coordinates}"
        "?overview=false"
    )

    try:

        with urllib.request.urlopen(
            url,
            timeout=10
        ) as response:

            data = json.loads(
                response.read().decode("utf-8")
            )

    except Exception as error:

        print(
            "OSRM distance request failed:",
            error
        )

        return None

    if (
        data.get("code") != "Ok"
        or not data.get("routes")
    ):
        return None

    distance_meters = (
        data["routes"][0].get("distance")
    )

    if distance_meters is None:
        return None

    distance_km = (
        distance_meters / 1000
    )

    # Cache for 24 hours.
    cache.set(
        cache_key,
        distance_km,
        60 * 60 * 24
    )

    return distance_km

def calculate_point_to_segment_distance(
    point_latitude,
    point_longitude,
    start_latitude,
    start_longitude,
    end_latitude,
    end_longitude
):
    """
    Calculate the approximate distance from a GPS point
    to a line segment.

    Returns:
        distance in kilometres
    """

    # Convert all coordinates to float.
    #
    # Django DecimalField values are Decimal objects,
    # while our calculations below use Python floats.

    point_latitude = float(point_latitude)
    point_longitude = float(point_longitude)

    start_latitude = float(start_latitude)
    start_longitude = float(start_longitude)

    end_latitude = float(end_latitude)
    end_longitude = float(end_longitude)

    # Convert latitude/longitude into a local
    # approximate Cartesian coordinate system.

    latitude_scale = 111.32

    longitude_scale = (
        111.32 *
        math.cos(
            math.radians(point_latitude)
        )
    )

    px = (
        point_longitude *
        longitude_scale
    )

    py = (
        point_latitude *
        latitude_scale
    )

    ax = (
        start_longitude *
        longitude_scale
    )

    ay = (
        start_latitude *
        latitude_scale
    )

    bx = (
        end_longitude *
        longitude_scale
    )

    by = (
        end_latitude *
        latitude_scale
    )

    ab_x = bx - ax
    ab_y = by - ay

    ap_x = px - ax
    ap_y = py - ay

    ab_length_squared = (
        ab_x * ab_x
        +
        ab_y * ab_y
    )

    if ab_length_squared == 0:

        return math.sqrt(
            ap_x * ap_x
            +
            ap_y * ap_y
        )

    projection = (
        ap_x * ab_x
        +
        ap_y * ab_y
    ) / ab_length_squared

    projection = max(
        0,
        min(1, projection)
    )

    nearest_x = (
        ax +
        projection * ab_x
    )

    nearest_y = (
        ay +
        projection * ab_y
    )

    distance_km = math.sqrt(
        (
            px - nearest_x
        ) ** 2
        +
        (
            py - nearest_y
        ) ** 2
    )

    return distance_km

def calculate_road_position(
    bus_latitude,
    bus_longitude,
    geometry
):
    """
    Find the bus position along an OSRM road geometry.

    Returns:

        distance_from_start_km
        distance_to_end_km
        total_road_distance_km

    or:

        None, None, None

    if the geometry is invalid.
    """

    bus_latitude = float(
        bus_latitude
    )

    bus_longitude = float(
        bus_longitude
    )

    if (
        not geometry
        or len(geometry) < 2
    ):
        return None, None, None

    total_distance = 0

    nearest_distance = float("inf")

    nearest_distance_from_start = 0

    travelled_distance = 0

    for index in range(
        len(geometry) - 1
    ):

        point_a = geometry[index]
        point_b = geometry[index + 1]

        start_longitude = point_a[0]
        start_latitude = point_a[1]

        end_longitude = point_b[0]
        end_latitude = point_b[1]

        segment_distance = calculate_distance_km(
            start_latitude,
            start_longitude,
            end_latitude,
            end_longitude
        )

        if segment_distance <= 0:
            continue

        distance_to_segment = (
            calculate_point_to_segment_distance(
                bus_latitude,
                bus_longitude,
                start_latitude,
                start_longitude,
                end_latitude,
                end_longitude
            )
        )

        if (
            distance_to_segment
            <
            nearest_distance
        ):

            nearest_distance = (
                distance_to_segment
            )

            # Determine approximately where
            # the bus lies on this road segment.

            latitude_scale = 111.32

            longitude_scale = (
                111.32 *
                math.cos(
                    math.radians(
                        bus_latitude
                    )
                )
            )

            px = (
                bus_longitude *
                longitude_scale
            )

            py = (
                bus_latitude *
                latitude_scale
            )

            ax = (
                start_longitude *
                longitude_scale
            )

            ay = (
                start_latitude *
                latitude_scale
            )

            bx = (
                end_longitude *
                longitude_scale
            )

            by = (
                end_latitude *
                latitude_scale
            )

            ab_x = bx - ax
            ab_y = by - ay

            ap_x = px - ax
            ap_y = py - ay

            denominator = (
                ab_x * ab_x
                +
                ab_y * ab_y
            )

            if denominator > 0:

                projection = (
                    (
                        ap_x * ab_x
                        +
                        ap_y * ab_y
                    )
                    /
                    denominator
                )

                projection = max(
                    0,
                    min(1, projection)
                )

            else:

                projection = 0

            distance_along_segment = (
                segment_distance *
                projection
            )

            nearest_distance_from_start = (
                travelled_distance
                +
                distance_along_segment
            )

        travelled_distance += (
            segment_distance
        )

    total_distance = travelled_distance

    if total_distance <= 0:
        return None, None, None

    distance_to_end = (
        total_distance
        -
        nearest_distance_from_start
    )

    return (
        round(
            nearest_distance_from_start,
            3
        ),
        round(
            max(
                0,
                distance_to_end
            ),
            3
        ),
        round(
            total_distance,
            3
        )
    )

def calculate_route_progress(
    bus_latitude,
    bus_longitude,
    current_stop,
    next_stop
):
    """
    Calculate road-aware progress between two
    consecutive route stops.

    Returns:

        progress_percentage
        distance_from_current_km
        distance_to_next_km
    """

    if not current_stop or not next_stop:
        return 0, None, None

    if (
        current_stop.latitude is None
        or current_stop.longitude is None
        or next_stop.latitude is None
        or next_stop.longitude is None
    ):
        return 0, None, None

    # --------------------------------------------------
    # GET OSRM ROAD GEOMETRY
    # --------------------------------------------------

    geometry = get_osrm_segment_geometry(
        current_stop,
        next_stop
    )

    # --------------------------------------------------
    # FALLBACK
    # --------------------------------------------------

    if not geometry:

        distance_from_current = (
            calculate_distance_km(
                bus_latitude,
                bus_longitude,
                current_stop.latitude,
                current_stop.longitude
            )
        )

        distance_to_next = (
            calculate_distance_km(
                bus_latitude,
                bus_longitude,
                next_stop.latitude,
                next_stop.longitude
            )
        )

        total_distance = (
            calculate_distance_km(
                current_stop.latitude,
                current_stop.longitude,
                next_stop.latitude,
                next_stop.longitude
            )
        )

        if total_distance <= 0:

            return (
                0,
                round(
                    distance_from_current,
                    2
                ),
                round(
                    distance_to_next,
                    2
                )
            )

        progress = (
            distance_from_current
            /
            (
                distance_from_current
                +
                distance_to_next
            )
        ) * 100

        progress = max(
            0,
            min(
                100,
                progress
            )
        )

        return (
            round(
                progress,
                1
            ),
            round(
                distance_from_current,
                2
            ),
            round(
                distance_to_next,
                2
            )
        )

    # --------------------------------------------------
    # ROAD POSITION
    # --------------------------------------------------

    (
        distance_from_current,
        distance_to_next,
        total_road_distance
    ) = calculate_road_position(
        bus_latitude,
        bus_longitude,
        geometry
    )

    if (
        distance_from_current is None
        or distance_to_next is None
        or total_road_distance is None
        or total_road_distance <= 0
    ):

        return (
            0,
            None,
            None
        )

    # --------------------------------------------------
    # ROAD-AWARE PROGRESS
    # --------------------------------------------------

    progress = (
        distance_from_current
        /
        total_road_distance
    ) * 100

    progress = max(
        0,
        min(
            100,
            progress
        )
    )

    return (
        round(
            progress,
            1
        ),
        round(
            distance_from_current,
            2
        ),
        round(
            distance_to_next,
            2
        )
    )

def calculate_overall_route_progress(
    bus_latitude,
    bus_longitude,
    route_stops,
):
    """
    Calculate the bus's overall route progress using
    OSRM road geometry.

    The route consists of consecutive road segments:

        Stop 1 -> Stop 2
        Stop 2 -> Stop 3
        Stop 3 -> Stop 4
        ...

    The bus position is projected onto the appropriate
    OSRM road segment.

    Returns:
        Overall route progress percentage.
    """

    if len(route_stops) < 2:
        return 0

    # -------------------------------------------------
    # Calculate OSRM geometry and distance for
    # every route segment
    # -------------------------------------------------

    segments = []

    total_route_distance = 0

    for index in range(
        len(route_stops) - 1
    ):

        start_stop = route_stops[index].stop
        end_stop = route_stops[index + 1].stop

        if (
            start_stop.latitude is None
            or start_stop.longitude is None
            or end_stop.latitude is None
            or end_stop.longitude is None
        ):
            continue

        geometry = get_osrm_segment_geometry(
            start_stop,
            end_stop
        )

        if not geometry:
            continue

        (
            distance_from_start,
            distance_to_end,
            segment_distance
        ) = calculate_road_position(
            start_stop.latitude,
            start_stop.longitude,
            geometry
        )

        if (
            segment_distance is None
            or segment_distance <= 0
        ):
            continue

        segments.append({
            'index': index,
            'start_stop': start_stop,
            'end_stop': end_stop,
            'geometry': geometry,
            'distance': segment_distance,
        })

        total_route_distance += segment_distance

    # -------------------------------------------------
    # If OSRM could not provide any usable segments,
    # fall back to the old straight-line calculation.
    # -------------------------------------------------

    if (
        not segments
        or total_route_distance <= 0
    ):

        return calculate_overall_route_progress_fallback(
            bus_latitude,
            bus_longitude,
            route_stops
        )

    # -------------------------------------------------
    # Find the OSRM segment closest to the bus
    # -------------------------------------------------

    closest_segment = None
    closest_segment_distance = float("inf")

    closest_distance_from_segment_start = 0

    for segment in segments:

        (
            distance_from_start,
            distance_to_end,
            segment_distance
        ) = calculate_road_position(
            bus_latitude,
            bus_longitude,
            segment['geometry']
        )

        if (
            distance_from_start is None
            or distance_to_end is None
            or segment_distance is None
        ):
            continue

        # The distance from the bus to the road itself
        # is not returned by calculate_road_position().
        #
        # Therefore calculate it by finding the closest
        # point on each geometry segment.

        geometry = segment['geometry']

        minimum_distance_to_road = float("inf")

        for geometry_index in range(
            len(geometry) - 1
        ):

            point_a = geometry[geometry_index]
            point_b = geometry[geometry_index + 1]

            distance_to_road_segment = (
                calculate_point_to_segment_distance(
                    bus_latitude,
                    bus_longitude,
                    point_a[1],
                    point_a[0],
                    point_b[1],
                    point_b[0]
                )
            )

            if (
                distance_to_road_segment
                <
                minimum_distance_to_road
            ):
                minimum_distance_to_road = (
                    distance_to_road_segment
                )

        if (
            minimum_distance_to_road
            <
            closest_segment_distance
        ):

            closest_segment_distance = (
                minimum_distance_to_road
            )

            closest_segment = segment

            closest_distance_from_segment_start = (
                distance_from_start
            )

    # -------------------------------------------------
    # If no segment could be matched
    # -------------------------------------------------

    if closest_segment is None:

        return calculate_overall_route_progress_fallback(
            bus_latitude,
            bus_longitude,
            route_stops
        )

    # -------------------------------------------------
    # Calculate distance travelled before the current
    # segment
    # -------------------------------------------------

    distance_before_current_segment = 0

    for segment in segments:

        if (
            segment['index']
            >=
            closest_segment['index']
        ):
            break

        distance_before_current_segment += (
            segment['distance']
        )

    # -------------------------------------------------
    # Add distance travelled on current OSRM segment
    # -------------------------------------------------

    travelled_distance = (
        distance_before_current_segment
        +
        closest_distance_from_segment_start
    )

    # -------------------------------------------------
    # Overall route progress
    # -------------------------------------------------

    progress = (
        travelled_distance
        /
        total_route_distance
    ) * 100

    return round(
        max(
            0,
            min(
                100,
                progress
            )
        ),
        1
    )

def calculate_overall_route_progress_fallback(
    bus_latitude,
    bus_longitude,
    route_stops,
):
    """
    Fallback overall route progress calculation.

    Used only when OSRM road geometry is unavailable.
    """

    if len(route_stops) < 2:
        return 0

    closest_index = None
    closest_distance = None

    for index, route_stop in enumerate(
        route_stops
    ):

        stop = route_stop.stop

        if (
            stop.latitude is None
            or stop.longitude is None
        ):
            continue

        distance = calculate_distance_km(
            bus_latitude,
            bus_longitude,
            stop.latitude,
            stop.longitude
        )

        if (
            closest_distance is None
            or distance < closest_distance
        ):

            closest_distance = distance
            closest_index = index

    if closest_index is None:
        return 0

    segment_distances = []

    total_route_distance = 0

    for index in range(
        len(route_stops) - 1
    ):

        start_stop = route_stops[index].stop
        end_stop = route_stops[index + 1].stop

        if (
            start_stop.latitude is None
            or start_stop.longitude is None
            or end_stop.latitude is None
            or end_stop.longitude is None
        ):

            segment_distances.append(None)

            continue

        segment_distance = (
            calculate_distance_km(
                start_stop.latitude,
                start_stop.longitude,
                end_stop.latitude,
                end_stop.longitude
            )
        )

        segment_distances.append(
            segment_distance
        )

        total_route_distance += (
            segment_distance
        )

    if total_route_distance <= 0:
        return 0

    distance_before_current = 0

    for index in range(
        closest_index
    ):

        if (
            index >=
            len(segment_distances)
        ):
            break

        segment_distance = (
            segment_distances[index]
        )

        if segment_distance is not None:
            distance_before_current += (
                segment_distance
            )

    distance_on_current_segment = 0

    if (
        closest_index
        <
        len(route_stops) - 1
    ):

        current_stop = (
            route_stops[
                closest_index
            ].stop
        )

        next_stop = (
            route_stops[
                closest_index + 1
            ].stop
        )

        if (
            current_stop.latitude is not None
            and current_stop.longitude is not None
            and next_stop.latitude is not None
            and next_stop.longitude is not None
        ):

            current_to_next_distance = (
                calculate_distance_km(
                    current_stop.latitude,
                    current_stop.longitude,
                    next_stop.latitude,
                    next_stop.longitude
                )
            )

            distance_from_current = (
                calculate_distance_km(
                    bus_latitude,
                    bus_longitude,
                    current_stop.latitude,
                    current_stop.longitude
                )
            )

            distance_to_next = (
                calculate_distance_km(
                    bus_latitude,
                    bus_longitude,
                    next_stop.latitude,
                    next_stop.longitude
                )
            )

            if (
                distance_from_current
                +
                distance_to_next
                > 0
            ):

                segment_progress = (
                    distance_from_current
                    /
                    (
                        distance_from_current
                        +
                        distance_to_next
                    )
                )

                segment_progress = max(
                    0,
                    min(
                        1,
                        segment_progress
                    )
                )

                distance_on_current_segment = (
                    current_to_next_distance
                    *
                    segment_progress
                )

    travelled_distance = (
        distance_before_current
        +
        distance_on_current_segment
    )

    progress = (
        travelled_distance
        /
        total_route_distance
    ) * 100

    return round(
        max(
            0,
            min(
                100,
                progress
            )
        ),
        1
    )

@login_required
def live_buses(request):

    buses = Bus.objects.order_by(
        'bus_number'
    )

    return render(
        request,
        'buses/live_buses.html',
        {
            'buses': buses,
        }
    )

@login_required
def live_bus_locations(request):

    locations = (
        BusLocation.objects
        .select_related(
            'bus',
            'bus__current_route',
            'current_route_stop',
            'last_departure_stop',
        )
        .prefetch_related(
            'bus__current_route__route_stops__stop'
        )
        .order_by('bus__bus_number')
    )

    ARRIVING_SOON_DISTANCE_KM = 0.15
    ARRIVED_DISTANCE_KM = 0.05

    data = []

    for location in locations:

        bus = location.bus
        route = bus.current_route

        current_stop = None
        next_stop = None

        route_progress = 0

        distance_from_current_km = None
        distance_to_next_km = None

        eta_minutes = None
        eta_status = None

        stop_status = location.stop_status

        stop_arrived_at = (
            location.stop_arrived_at
        )

        stop_departed_at = (
            location.stop_departed_at
        )

        last_departure_stop = (
            location.last_departure_stop
        )

        last_departure_at = (
            location.last_departure_at
        )

        route_stop_data = []

        # =================================================
        # ROUTE
        # =================================================

        if route:

            route_stops = list(
                route.route_stops.all()
            )

            route_stop_data = [
                {
                    'name': route_stop.stop.name,

                    'latitude': float(
                        route_stop.stop.latitude
                    ),

                    'longitude': float(
                        route_stop.stop.longitude
                    ),

                    'order': route_stop.stop_order,
                }

                for route_stop in route_stops

                if (
                    route_stop.stop.latitude is not None
                    and
                    route_stop.stop.longitude is not None
                )
            ]

            if route_stops:

                # =================================================
                # OVERALL ROUTE PROGRESS
                # =================================================

                route_progress = (
                    calculate_overall_route_progress(
                        location.latitude,
                        location.longitude,
                        route_stops
                    )
                )

                # =================================================
                # CURRENT ROUTE STOP
                # =================================================

                current_route_stop = (
                    location.current_route_stop
                )

                if current_route_stop:

                    current_stop = (
                        current_route_stop.stop.name
                    )

                    # =================================================
                    # FIND CURRENT STOP INDEX
                    # =================================================

                    try:

                        current_index = next(
                            index
                            for index, route_stop
                            in enumerate(route_stops)

                            if (
                                route_stop.id
                                ==
                                current_route_stop.id
                            )
                        )

                    except StopIteration:

                        current_index = None

                    # =================================================
                    # VALID CURRENT STOP
                    # =================================================

                    if current_index is not None:

                        # =================================================
                        # TRAVELLING
                        #
                        # current_route_stop is the destination
                        # the bus is travelling toward.
                        # =================================================

                        if stop_status == 'TRAVELLING':

                            if current_index > 0:

                                previous_route_stop = (
                                    route_stops[current_index - 1]
                                )

                                current_stop = (
                                    previous_route_stop.stop.name
                                )

                                next_stop = (
                                    current_route_stop.stop.name
                                )

                                (
                                    segment_progress,
                                    distance_from_current_km,
                                    distance_to_next_km
                                ) = calculate_route_progress(
                                    location.latitude,
                                    location.longitude,
                                    previous_route_stop.stop,
                                    current_route_stop.stop
                                )

                                # ---------------------------------------------
                                # ETA TO CURRENT DESTINATION STOP
                                # ---------------------------------------------

                                if distance_to_next_km is not None:

                                    # -----------------------------------------
                                    # ARRIVED
                                    # -----------------------------------------

                                    if (
                                            distance_to_next_km
                                            <= ARRIVED_DISTANCE_KM
                                    ):

                                        eta_status = "ARRIVED"

                                    # -----------------------------------------
                                    # ARRIVING SOON
                                    # -----------------------------------------

                                    elif (
                                            distance_to_next_km
                                            <= ARRIVING_SOON_DISTANCE_KM
                                    ):

                                        eta_status = "ARRIVING_SOON"

                                    # -----------------------------------------
                                    # MOVING
                                    # -----------------------------------------

                                    elif (
                                            location.speed is not None
                                            and location.speed > 1
                                    ):

                                        eta_minutes = round(
                                            (
                                                    distance_to_next_km
                                                    /
                                                    location.speed
                                            ) * 60
                                        )

                                        eta_minutes = max(
                                            1,
                                            eta_minutes
                                        )

                                        eta_status = "ETA"

                                    # -----------------------------------------
                                    # STATIONARY
                                    # -----------------------------------------

                                    else:

                                        eta_status = "UNKNOWN"


                        # =================================================
                        # ARRIVED
                        #
                        # Bus is currently at current_route_stop.
                        # =================================================

                        elif stop_status == 'ARRIVED':

                            # ---------------------------------------------
                            # The bus has arrived.
                            # Keep the passenger ETA as "Arrived".
                            # ---------------------------------------------

                            eta_minutes = None
                            eta_status = "ARRIVED"

                            current_stop = (
                                current_route_stop.stop.name
                            )

                            # ---------------------------------------------
                            # Get the following stop.
                            # This is still useful for route information.
                            # ---------------------------------------------

                            if (
                                    current_index + 1
                                    <
                                    len(route_stops)
                            ):
                                next_route_stop = (
                                    route_stops[
                                        current_index + 1
                                        ]
                                )

                                next_stop = (
                                    next_route_stop.stop.name
                                )

                                # -----------------------------------------
                                # Calculate progress toward next stop.
                                #
                                # We keep this calculation for distance/
                                # route information, but we DO NOT use it
                                # to overwrite eta_status.
                                # -----------------------------------------

                                (
                                    segment_progress,
                                    distance_from_current_km,
                                    distance_to_next_km
                                ) = calculate_route_progress(

                                    location.latitude,
                                    location.longitude,

                                    current_route_stop.stop,
                                    next_route_stop.stop
                                )

        # =================================================
        # BUS DATA
        # =================================================

        data.append({

            'bus_id': bus.id,

            'bus_number': (
                bus.bus_number
            ),

            'bus_name': (
                bus.bus_name
            ),

            'bus_type': (
                bus.get_bus_type_display()
            ),

            # ---------------------------------------------
            # ROUTE
            # ---------------------------------------------

            'route_id': (
                route.id
                if route
                else None
            ),

            'route_name': (
                route.route_name
                if route
                else None
            ),

            'route_stops': (
                route_stop_data
            ),

            # ---------------------------------------------
            # STOPS
            # ---------------------------------------------

            'current_stop': (
                current_stop
            ),

            'next_stop': (
                next_stop
            ),

            # ---------------------------------------------
            # STOP STATUS
            # ---------------------------------------------

            'stop_status': (
                stop_status
            ),

            'stop_arrived_at': (

                stop_arrived_at.isoformat()

                if stop_arrived_at

                else None
            ),

            'stop_departed_at': (

                stop_departed_at.isoformat()

                if stop_departed_at

                else None
            ),

            # ---------------------------------------------
            # LAST DEPARTURE
            # ---------------------------------------------

            'last_departure_stop': (

                last_departure_stop.stop.name

                if last_departure_stop

                else None
            ),

            'last_departure_at': (

                last_departure_at.isoformat()

                if last_departure_at

                else None
            ),

            # ---------------------------------------------
            # ROUTE PROGRESS
            # ---------------------------------------------

            'route_progress': (
                route_progress
            ),

            # ---------------------------------------------
            # DISTANCES
            # ---------------------------------------------

            'distance_from_current_km': (

                distance_from_current_km
            ),

            'distance_to_next_km': (

                distance_to_next_km
            ),

            # ---------------------------------------------
            # ETA
            # ---------------------------------------------

            'eta_minutes': (
                eta_minutes
            ),
            'eta_status': (
                eta_status
            ),

            # ---------------------------------------------
            # GPS
            # ---------------------------------------------

            'latitude': float(
                location.latitude
            ),

            'longitude': float(
                location.longitude
            ),

            'speed': (

                float(location.speed)

                if location.speed is not None

                else None
            ),

            'heading': (

                float(location.heading)

                if location.heading is not None

                else None
            ),

            'accuracy': (

                float(location.accuracy)

                if location.accuracy is not None

                else None
            ),

            # ---------------------------------------------
            # TRACKING
            # ---------------------------------------------

            'is_tracking': (
                location.is_tracking
            ),

            'updated_at': (
                location.updated_at.isoformat()
            ),
        })

    return JsonResponse({
        'success': True,
        'locations': data,
    })

@login_required
def set_bus_route(request):

    if request.method != 'POST':
        return JsonResponse(
            {
                'success': False,
                'message': 'POST request required.'
            },
            status=405
        )

    # --------------------------------------------------
    # DRIVER AUTHORIZATION
    # --------------------------------------------------

    if not request.user.groups.filter(
        name='Drivers'
    ).exists():

        return JsonResponse(
            {
                'success': False,
                'message': 'You are not authorized to control a bus.'
            },
            status=403
        )

    bus_id = request.POST.get('bus_id')
    route_id = request.POST.get('route_id')

    if not bus_id or not route_id:
        return JsonResponse(
            {
                'success': False,
                'message': 'Bus and route are required.'
            },
            status=400
        )

    # --------------------------------------------------
    # ONLY THE DRIVER'S ASSIGNED BUS
    # --------------------------------------------------

    bus = get_object_or_404(
        Bus,
        id=bus_id,
        driver=request.user
    )

    route = get_object_or_404(
        Route,
        id=route_id,
        bus=bus
    )

    bus.current_route = route

    bus.save(
        update_fields=['current_route']
    )

    return JsonResponse(
        {
            'success': True,
            'message': 'Current route updated successfully.',
            'route_id': route.id,
            'route_name': route.route_name,
        }
    )

@staff_member_required
def schedule_stops(request):

    schedule_id = request.GET.get('schedule_id')

    if not schedule_id:
        return JsonResponse(
            {
                'success': False,
                'message': 'Schedule ID is required.'
            },
            status=400
        )

    schedule = get_object_or_404(
        BusSchedule.objects.select_related('route'),
        id=schedule_id
    )

    route_stops = (
        RouteStop.objects
        .filter(route=schedule.route)
        .select_related('stop')
        .order_by('stop_order')
    )

    stops = [
        {
            'id': route_stop.id,
            'name': route_stop.stop.name,
            'order': route_stop.stop_order,
        }
        for route_stop in route_stops
    ]

    return JsonResponse(
        {
            'success': True,
            'stops': stops,
        }
    )

from routes.utils import calculate_route_fare

@login_required
def book_ticket(request):

    if not request.user.groups.filter(
        name='Passengers'
    ).exists():

        messages.error(
            request,
            'Only passengers can book tickets.'
        )

        return redirect(
            'core:home'
        )

    if request.method == 'POST':

        form = TicketBookingForm(
            request.POST
        )

        if form.is_valid():

            schedule = (
                form.cleaned_data['schedule']
            )

            source_stop = (
                form.cleaned_data['source_stop']
            )

            destination_stop = (
                form.cleaned_data['destination_stop']
            )

            journey_date = (
                form.cleaned_data['journey_date']
            )

            passenger_count = (
                form.cleaned_data['passenger_count']
            )

            # -----------------------------------------
            # CALCULATE FARE
            # -----------------------------------------

            try:

                fare_per_passenger = (
                    calculate_route_fare(
                        source_stop,
                        destination_stop,
                    )
                )

            except ValidationError as error:

                form.add_error(
                    None,
                    str(error)
                )

                return render(
                    request,
                    'buses/book_ticket.html',
                    {
                        'form': form
                    }
                )

            total_amount = (
                fare_per_passenger
                * Decimal(passenger_count)
            )

            amount_paise = int(
                total_amount * 100
            )

            # -----------------------------------------
            # CREATE RAZORPAY ORDER
            # -----------------------------------------

            client = razorpay.Client(
                auth=(
                    settings.RAZORPAY_KEY_ID,
                    settings.RAZORPAY_KEY_SECRET,
                )
            )

            try:

                razorpay_order = client.order.create(
                    {
                        'amount': amount_paise,
                        'currency': 'INR',
                        'receipt': (
                            f'BRF-{uuid.uuid4().hex[:10].upper()}'
                        ),
                        'notes': {
                            'passenger_id': str(
                                request.user.id
                            ),
                            'schedule_id': str(
                                schedule.id
                            ),
                            'source_stop_id': str(
                                source_stop.id
                            ),
                            'destination_stop_id': str(
                                destination_stop.id
                            ),
                            'journey_date': str(
                                journey_date
                            ),
                            'passenger_count': str(
                                passenger_count
                            ),
                        },
                    }
                )

            except Exception:

                messages.error(
                    request,
                    'Unable to start the payment. '
                    'Please try again.'
                )

                return redirect(
                    'buses:book_ticket'
                )

            # -----------------------------------------
            # CREATE PAYMENT RESERVATION
            # -----------------------------------------

            payment = Payment.objects.create(

                passenger=request.user,

                schedule=schedule,

                source_stop=source_stop,

                destination_stop=destination_stop,

                journey_date=journey_date,

                passenger_count=passenger_count,

                fare_per_passenger=(
                    fare_per_passenger
                ),

                total_amount=total_amount,

                razorpay_order_id=(
                    razorpay_order['id']
                ),

                amount=total_amount,

                currency='INR',

                status='CREATED',
            )

            return render(
                request,
                'buses/payment.html',
                {
                    'payment': payment,
                    'razorpay_key_id': (
                        settings.RAZORPAY_KEY_ID
                    ),
                }
            )

    else:

        form = TicketBookingForm()

    return render(
        request,
        'buses/book_ticket.html',
        {
            'form': form
        }
    )

@login_required
def calculate_booking_fare(request):

    if not request.user.groups.filter(
        name='Passengers'
    ).exists():

        return JsonResponse(
            {
                'success': False,
                'message': 'Passenger access required.'
            },
            status=403
        )

    schedule_id = request.GET.get(
        'schedule_id'
    )

    source_stop_id = request.GET.get(
        'source_stop_id'
    )

    destination_stop_id = request.GET.get(
        'destination_stop_id'
    )

    if not all([
        schedule_id,
        source_stop_id,
        destination_stop_id,
    ]):

        return JsonResponse(
            {
                'success': False,
                'message': (
                    'Schedule, source and destination '
                    'are required.'
                )
            },
            status=400
        )

    schedule = get_object_or_404(
        BusSchedule.objects.select_related(
            'route'
        ),
        id=schedule_id,
        is_active=True
    )

    source_stop = get_object_or_404(
        RouteStop,
        id=source_stop_id
    )

    destination_stop = get_object_or_404(
        RouteStop,
        id=destination_stop_id
    )

    if source_stop.route_id != schedule.route_id:

        return JsonResponse(
            {
                'success': False,
                'message': (
                    'Source stop does not belong '
                    'to the selected route.'
                )
            },
            status=400
        )

    if destination_stop.route_id != schedule.route_id:

        return JsonResponse(
            {
                'success': False,
                'message': (
                    'Destination stop does not belong '
                    'to the selected route.'
                )
            },
            status=400
        )

    if destination_stop.stop_order <= source_stop.stop_order:
        return JsonResponse(
            {
                'success': False,
                'message': (
                    'Destination stop must come after '
                    'the source stop.'
                )
            },
            status=400
        )

    try:

        fare = calculate_route_fare(
            source_stop,
            destination_stop
        )

    except ValidationError as error:

        return JsonResponse(
            {
                'success': False,
                'message': str(error)
            },
            status=400
        )

    return JsonResponse(
        {
            'success': True,
            'fare': float(fare),
        }
    )

@login_required
def booking_schedule_stops(request):

    if not request.user.groups.filter(
        name='Passengers'
    ).exists():

        return JsonResponse(
            {
                'success': False,
                'message': 'Passenger access required.'
            },
            status=403
        )

    schedule_id = request.GET.get(
        'schedule_id'
    )

    if not schedule_id:

        return JsonResponse(
            {
                'success': False,
                'message': 'Schedule ID is required.'
            },
            status=400
        )

    schedule = get_object_or_404(
        BusSchedule.objects.select_related(
            'route',
            'route__bus'
        ),
        id=schedule_id,
        is_active=True
    )

    route_stops = (
        RouteStop.objects
        .filter(
            route=schedule.route
        )
        .select_related('stop')
        .order_by('stop_order')
    )

    stops = [
        {
            'id': route_stop.id,
            'name': route_stop.stop.name,
            'order': route_stop.stop_order,
            'distance_from_start_km': float(
                route_stop.distance_from_start_km
            ),
        }
        for route_stop in route_stops
    ]

    return JsonResponse(
        {
            'success': True,
            'stops': stops,
        }
    )

    return JsonResponse(
        {
            'success': True,
            'stops': stops,
        }
    )

@login_required
def ticket_payment(request, ticket_id):

    ticket = get_object_or_404(
        Ticket.objects.select_related(
            'schedule',
            'schedule__route',
            'schedule__route__bus',
        ),
        id=ticket_id,
        passenger=request.user
    )

    payment = get_object_or_404(
        Payment,
        ticket=ticket,
        passenger=request.user
    )

    if payment.status == 'PAID':

        messages.info(
            request,
            'This ticket has already been paid.'
        )

        return redirect(
            'buses:ticket_detail',
            ticket_id=ticket.id
        )

    return render(
        request,
        'buses/payment.html',
        {
            'ticket': ticket,
            'payment': payment,
            'razorpay_key_id': (
                settings.RAZORPAY_KEY_ID
            ),
        }
    )

@login_required
def ticket_detail(request, ticket_id):

    complete_past_tickets()

    ticket = get_object_or_404(
        Ticket.objects.select_related(
            'schedule',
            'schedule__route',
            'schedule__route__bus',
            'source_stop__stop',
            'destination_stop__stop',
            'payment',
        ),
        id=ticket_id,
        passenger=request.user
    )

    return render(
        request,
        'buses/ticket_detail.html',
        {
            'ticket': ticket,
        }
    )

@login_required
def my_tickets(request):

    if not request.user.groups.filter(
        name='Passengers'
    ).exists():

        messages.error(
            request,
            'Only passengers can view tickets.'
        )

        return redirect(
            'core:home'
        )

    complete_past_tickets()

    tickets = (
        Ticket.objects
        .filter(
            passenger=request.user
        )
        .select_related(
            'schedule',
            'schedule__route',
            'schedule__route__bus',
            'source_stop__stop',
            'destination_stop__stop',
        )
        .order_by('-created_at')
    )

    pending_payments = (
        Payment.objects
        .filter(
            passenger=request.user,
            status__in=[
                'CREATED',
                'FAILED',
            ],
            ticket__isnull=True,
        )
        .select_related(
            'schedule',
            'schedule__route',
            'schedule__route__bus',
            'source_stop__stop',
            'destination_stop__stop',
        )
        .order_by('-created_at')
    )

    return render(
        request,
        'buses/my_tickets.html',
        {
            'tickets': tickets,
            'pending_payments': pending_payments,
        }
    )

@login_required
@require_POST
def cancel_ticket(request, ticket_id):

    if not request.user.groups.filter(
        name='Passengers'
    ).exists():
        messages.error(
            request,
            'Only passengers can cancel tickets.'
        )
        return redirect('core:home')

    ticket = get_object_or_404(
        Ticket.objects.select_related(
            'schedule',
            'schedule__route',
            'schedule__route__bus',
            'payment',
        ),
        id=ticket_id,
        passenger=request.user
    )

    # ---------------------------------------------------------
    # TICKET STATUS CHECK
    # ---------------------------------------------------------

    if ticket.status == 'PAYMENT_PENDING':

        payment = ticket.payment

        # -----------------------------------------------------
        # PAYMENT PENDING - CREATED OR FAILED
        # -----------------------------------------------------

        if payment.status in [
            'CREATED',
            'FAILED',
        ]:

            ticket.status = 'CANCELLED'

            ticket.save(
                update_fields=[
                    'status',
                    'updated_at',
                ]
            )

            messages.success(
                request,
                f'Ticket {ticket.ticket_number} '
                f'has been cancelled.'
            )

            return redirect(
                'buses:ticket_detail',
                ticket_id=ticket.id
            )

        messages.error(
            request,
            'This ticket cannot be cancelled because '
            'its payment is currently being processed.'
        )

        return redirect(
            'buses:ticket_detail',
            ticket_id=ticket.id
        )


    if ticket.status != 'CONFIRMED':
        messages.error(
            request,
            'This ticket cannot be cancelled.'
        )
        return redirect(
            'buses:ticket_detail',
            ticket_id=ticket.id
        )


    # ---------------------------------------------------------
    # DEPARTURE TIME CHECK
    # ---------------------------------------------------------

    departure_datetime = timezone.make_aware(
        datetime.combine(
            ticket.journey_date,
            ticket.schedule.departure_time
        )
    )

    if timezone.now() >= departure_datetime:
        messages.error(
            request,
            'This ticket can no longer be cancelled because '
            'the scheduled departure time has passed.'
        )
        return redirect(
            'buses:ticket_detail',
            ticket_id=ticket.id
        )


    # ---------------------------------------------------------
    # PAYMENT CHECK
    # ---------------------------------------------------------

    payment = ticket.payment

    if payment.status == 'REFUNDED':
        messages.error(
            request,
            'This payment has already been refunded.'
        )
        return redirect(
            'buses:ticket_detail',
            ticket_id=ticket.id
        )

    if payment.status != 'PAID':
        messages.error(
            request,
            'This ticket does not have a refundable payment.'
        )
        return redirect(
            'buses:ticket_detail',
            ticket_id=ticket.id
        )

    if not payment.razorpay_payment_id:
        messages.error(
            request,
            'Refund cannot be processed because the '
            'payment ID is missing.'
        )
        return redirect(
            'buses:ticket_detail',
            ticket_id=ticket.id
        )

    if payment.razorpay_refund_id:
        messages.error(
            request,
            'A refund has already been processed for this payment.'
        )
        return redirect(
            'buses:ticket_detail',
            ticket_id=ticket.id
        )


    # ---------------------------------------------------------
    # RAZORPAY REFUND
    # ---------------------------------------------------------

    client = razorpay.Client(
        auth=(
            settings.RAZORPAY_KEY_ID,
            settings.RAZORPAY_KEY_SECRET,
        )
    )

    try:

        refund = client.payment.refund(
            payment.razorpay_payment_id,
            {
                'amount': int(
                    payment.amount * 100
                ),
            }
        )

    except Exception:

        messages.error(
            request,
            'The refund could not be processed. '
            'Your ticket has not been cancelled.'
        )

        return redirect(
            'buses:ticket_detail',
            ticket_id=ticket.id
        )


    # ---------------------------------------------------------
    # SAVE REFUND DETAILS
    # ---------------------------------------------------------

    payment.status = 'REFUNDED'
    payment.razorpay_refund_id = refund['id']

    payment.save(
        update_fields=[
            'status',
            'razorpay_refund_id',
            'updated_at',
        ]
    )


    # ---------------------------------------------------------
    # CANCEL TICKET
    # ---------------------------------------------------------

    ticket.status = 'CANCELLED'

    ticket.save(
        update_fields=[
            'status',
            'updated_at',
        ]
    )

    messages.success(
        request,
        f'Ticket {ticket.ticket_number} has been cancelled '
        f'and the payment has been refunded.'
    )

    return redirect(
        'buses:ticket_detail',
        ticket_id=ticket.id
    )

from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from django.http import FileResponse

@login_required
def download_ticket(request, ticket_id):

    ticket = get_object_or_404(
        Ticket.objects.select_related(
            'schedule',
            'schedule__route',
            'schedule__route__bus',
            'source_stop__stop',
            'destination_stop__stop',
            'payment',
        ),
        id=ticket_id,
        passenger=request.user
    )

    if ticket.status != 'CONFIRMED':

        messages.error(
            request,
            'Only confirmed tickets can be downloaded.'
        )

        return redirect(
            'buses:ticket_detail',
            ticket_id=ticket.id
        )

    if ticket.payment.status != 'PAID':

        messages.error(
            request,
            'A paid ticket is required to download the ticket.'
        )

        return redirect(
            'buses:ticket_detail',
            ticket_id=ticket.id
        )

    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=f"Bus Ticket - {ticket.ticket_number}",
    )

    styles = getSampleStyleSheet()

    title_style = styles['Title']
    heading_style = styles['Heading2']
    normal_style = styles['BodyText']

    story = []

    story.append(
        Paragraph(
            'BUS ROUTE FINDER',
            title_style
        )
    )

    story.append(
        Paragraph(
            'Bus Ticket',
            heading_style
        )
    )

    story.append(Spacer(1, 10))

    ticket_data = [
        ['Ticket Number', ticket.ticket_number],
        ['Status', ticket.get_status_display()],
        [
            'Bus',
            (
                f'{ticket.schedule.route.bus.bus_name} '
                f'({ticket.schedule.route.bus.bus_number})'
            )
        ],
        [
            'Route',
            ticket.schedule.route.route_name
        ],
        [
            'Journey Date',
            ticket.journey_date.strftime('%d-%m-%Y')
        ],
        [
            'Departure',
            ticket.schedule.departure_time.strftime('%I:%M %p')
        ],
        [
            'From',
            ticket.source_stop.stop.name
        ],
        [
            'To',
            ticket.destination_stop.stop.name
        ],
        [
            'Passengers',
            str(ticket.passenger_count)
        ],
        [
            'Fare per Passenger',
            f'Rs. {ticket.fare_per_passenger:.2f}'
        ],
        [
            'Total Fare',
            f'Rs. {ticket.total_amount:.2f}'
        ],
    ]

    table = Table(
        ticket_data,
        colWidths=[
            55 * mm,
            105 * mm,
        ]
    )

    table.setStyle(
        TableStyle([
            (
                'BACKGROUND',
                (0, 0),
                (0, -1),
                colors.lightgrey
            ),
            (
                'TEXTCOLOR',
                (0, 0),
                (0, -1),
                colors.black
            ),
            (
                'FONTNAME',
                (0, 0),
                (0, -1),
                'Helvetica-Bold'
            ),
            (
                'FONTNAME',
                (1, 0),
                (1, -1),
                'Helvetica'
            ),
            (
                'GRID',
                (0, 0),
                (-1, -1),
                0.5,
                colors.grey
            ),
            (
                'VALIGN',
                (0, 0),
                (-1, -1),
                'TOP'
            ),
            (
                'PADDING',
                (0, 0),
                (-1, -1),
                8
            ),
        ])
    )

    story.append(table)

    story.append(Spacer(1, 20))

    story.append(
        Paragraph(
            'Please carry this ticket while travelling.',
            normal_style
        )
    )

    story.append(
        Paragraph(
            'This ticket is issued by Bus Route Finder.',
            normal_style
        )
    )

    document.build(story)

    buffer.seek(0)

    return FileResponse(
        buffer,
        as_attachment=True,
        filename=f'{ticket.ticket_number}.pdf',
        content_type='application/pdf',
    )

@login_required
@require_POST
def verify_payment(request):

    if not request.user.groups.filter(
        name='Passengers'
    ).exists():

        return JsonResponse(
            {
                'success': False,
                'message': 'Passenger access required.'
            },
            status=403
        )

    payment_id = request.POST.get(
        'razorpay_payment_id'
    )

    order_id = request.POST.get(
        'razorpay_order_id'
    )

    signature = request.POST.get(
        'razorpay_signature'
    )

    if not all([
        payment_id,
        order_id,
        signature,
    ]):

        return JsonResponse(
            {
                'success': False,
                'message': 'Incomplete payment response.'
            },
            status=400
        )

    payment = get_object_or_404(
        Payment.objects.select_related(
            'ticket',
            'schedule',
            'source_stop',
            'destination_stop',
        ),
        razorpay_order_id=order_id,
        passenger=request.user
    )

    # ALREADY PAID
    if payment.status == 'PAID':

        if payment.ticket:

            return JsonResponse(
                {
                    'success': True,
                    'ticket_id': payment.ticket.id
                }
            )

        return JsonResponse(
            {
                'success': False,
                'message': (
                    'Payment is already marked as paid, '
                    'but the ticket could not be found.'
                )
            },
            status=400
        )

    # PAYMENT MUST BE CREATED
    if payment.status != 'CREATED':

        return JsonResponse(
            {
                'success': False,
                'message': (
                    'This payment is no longer available '
                    'for verification.'
                )
            },
            status=400
        )

    # CHECK RESERVATION DATA
    if not all([
        payment.schedule,
        payment.source_stop,
        payment.destination_stop,
        payment.journey_date,
        payment.fare_per_passenger,
        payment.total_amount,
    ]):

        return JsonResponse(
            {
                'success': False,
                'message': (
                    'Payment reservation data is incomplete.'
                )
            },
            status=400
        )

    # VERIFY RAZORPAY SIGNATURE
    client = razorpay.Client(
        auth=(
            settings.RAZORPAY_KEY_ID,
            settings.RAZORPAY_KEY_SECRET,
        )
    )

    try:

        client.utility.verify_payment_signature(
            {
                'razorpay_order_id': order_id,
                'razorpay_payment_id': payment_id,
                'razorpay_signature': signature,
            }
        )

    except razorpay.errors.SignatureVerificationError:

        return JsonResponse(
            {
                'success': False,
                'message': (
                    'Payment verification failed.'
                )
            },
            status=400
        )

    # CREATE TICKET + UPDATE PAYMENT
    # AS ONE ATOMIC OPERATION

    with transaction.atomic():

        ticket = Ticket.objects.create(
            passenger=payment.passenger,
            schedule=payment.schedule,
            source_stop=payment.source_stop,
            destination_stop=payment.destination_stop,
            journey_date=payment.journey_date,
            passenger_count=payment.passenger_count,
            fare_per_passenger=(
                payment.fare_per_passenger
            ),
            status='CONFIRMED',
        )

        payment.ticket = ticket

        payment.razorpay_payment_id = (
            payment_id
        )

        payment.razorpay_signature = (
            signature
        )

        payment.status = 'PAID'

        payment.failure_reason = None

        payment.save(
            update_fields=[
                'ticket',
                'razorpay_payment_id',
                'razorpay_signature',
                'status',
                'failure_reason',
                'updated_at',
            ]
        )

    return JsonResponse(
        {
            'success': True,
            'ticket_id': ticket.id,
        }
    )

@login_required
@require_POST
def payment_failure(request):

    if not request.user.groups.filter(
        name='Passengers'
    ).exists():
        return JsonResponse(
            {
                'success': False,
                'message': 'Passenger access required.'
            },
            status=403
        )

    order_id = request.POST.get(
        'razorpay_order_id'
    )

    error_description = request.POST.get(
        'error_description',
        'Payment could not be completed.'
    )

    if not order_id:
        return JsonResponse(
            {
                'success': False,
                'message': 'Order ID is required.'
            },
            status=400
        )

    payment = get_object_or_404(
        Payment.objects.select_related('ticket'),
        razorpay_order_id=order_id,
        passenger=request.user
    )

    if payment.status == 'PAID':
        return JsonResponse(
            {
                'success': True,
                'message': 'Payment has already been completed.'
            }
        )

    payment.status = 'FAILED'

    payment.failure_reason = error_description

    payment.save(
        update_fields=[
            'status',
            'failure_reason',
            'updated_at',
        ]
    )

    return JsonResponse(
        {
            'success': True
        }
    )

@login_required
def payment_page(request, payment_id):

    if not request.user.groups.filter(
        name='Passengers'
    ).exists():

        messages.error(
            request,
            'Only passengers can make payments.'
        )

        return redirect(
            'core:home'
        )

    payment = get_object_or_404(
        Payment.objects.select_related(
            'schedule',
            'schedule__route',
            'schedule__route__bus',
            'source_stop__stop',
            'destination_stop__stop',
        ),
        id=payment_id,
        passenger=request.user,
    )

    # ---------------------------------------------------------
    # ALREADY PAID
    # ---------------------------------------------------------

    if payment.status == 'PAID':

        if payment.ticket:

            return redirect(
                'buses:ticket_detail',
                ticket_id=payment.ticket.id
            )

        messages.error(
            request,
            'This payment has already been completed.'
        )

        return redirect(
            'buses:my_tickets'
        )

    # ---------------------------------------------------------
    # PAYMENT MUST STILL BE AVAILABLE
    # ---------------------------------------------------------

    if payment.status not in [
        'CREATED',
        'FAILED',
    ]:

        messages.error(
            request,
            'This payment is no longer available.'
        )

        return redirect(
            'buses:my_tickets'
        )

    return render(
        request,
        'buses/payment.html',
        {
            'payment': payment,
            'razorpay_key_id': (
                settings.RAZORPAY_KEY_ID
            ),
        }
    )

@login_required
def check_seat_availability(request):

    if not request.user.groups.filter(
        name='Passengers'
    ).exists():

        return JsonResponse(
            {
                'success': False,
                'message': 'Passenger access required.'
            },
            status=403
        )

    schedule_id = request.GET.get(
        'schedule_id'
    )

    source_stop_id = request.GET.get(
        'source_stop_id'
    )

    destination_stop_id = request.GET.get(
        'destination_stop_id'
    )

    journey_date = request.GET.get(
        'journey_date'
    )

    if not all([
        schedule_id,
        source_stop_id,
        destination_stop_id,
        journey_date,
    ]):

        return JsonResponse(
            {
                'success': False,
                'message': 'Incomplete booking information.'
            },
            status=400
        )

    schedule = get_object_or_404(
        BusSchedule,
        id=schedule_id
    )

    source_stop = get_object_or_404(
        RouteStop,
        id=source_stop_id
    )

    destination_stop = get_object_or_404(
        RouteStop,
        id=destination_stop_id
    )

    try:

        journey_date = datetime.strptime(
            journey_date,
            '%Y-%m-%d'
        ).date()

    except ValueError:

        return JsonResponse(
            {
                'success': False,
                'message': 'Invalid journey date.'
            },
            status=400
        )

    if source_stop.route_id != schedule.route_id:

        return JsonResponse(
            {
                'success': False,
                'message': 'Invalid source stop.'
            },
            status=400
        )

    if destination_stop.route_id != schedule.route_id:

        return JsonResponse(
            {
                'success': False,
                'message': 'Invalid destination stop.'
            },
            status=400
        )

    if (
        source_stop.stop_order
        >=
        destination_stop.stop_order
    ):

        return JsonResponse(
            {
                'success': False,
                'message': (
                    'Destination must come after '
                    'the source.'
                )
            },
            status=400
        )

    available_seats = get_available_seats(
        schedule=schedule,
        journey_date=journey_date,
        source_stop=source_stop,
        destination_stop=destination_stop,
    )

    return JsonResponse(
        {
            'success': True,
            'available_seats': available_seats,
        }
    )