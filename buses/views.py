from django.shortcuts import render, get_object_or_404

import json
import math
import urllib.request

from django.core.cache import cache

# Create your views here.
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

from routes.models import Route, RouteStop, BusSchedule

from math import radians, sin, cos, sqrt, atan2

import uuid

from django.utils import timezone

from .models import (
    Bus,
    BusLocation,
    BusStopVisit
)

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

from django.utils import timezone
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