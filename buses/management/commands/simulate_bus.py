import math
import time
import uuid

from django.core.management.base import (
    BaseCommand,
    CommandError,
)

from buses.models import (
    Bus,
    BusLocation,
)

from buses.views import (
    get_osrm_segment_geometry,
    calculate_distance_km,
    detect_stop_arrival_departure,
)


# ==========================================================
# SIMULATION SETTINGS
# ==========================================================

SIMULATION_SPEED_KMH = 30

SIMULATION_INTERVAL = 2

SIMULATION_ACCURACY = 5


# ==========================================================
# GEOMETRY DISTANCE
# ==========================================================

def calculate_geometry_distance_km(
    geometry
):
    """
    Calculate total road distance of an OSRM geometry.
    """

    if not geometry or len(geometry) < 2:
        return 0

    total_distance = 0

    for index in range(
        len(geometry) - 1
    ):

        point_a = geometry[index]
        point_b = geometry[index + 1]

        total_distance += calculate_distance_km(
            point_a[1],
            point_a[0],
            point_b[1],
            point_b[0]
        )

    return total_distance


# ==========================================================
# POINT ALONG OSRM GEOMETRY
# ==========================================================

def get_point_along_geometry(
    geometry,
    progress
):
    """
    Return a point along an OSRM geometry.

    OSRM geometry format:

        [longitude, latitude]
    """

    if not geometry:
        return None

    if len(geometry) == 1:
        return geometry[0]

    progress = max(
        0,
        min(
            1,
            progress
        )
    )

    total_distance = (
        calculate_geometry_distance_km(
            geometry
        )
    )

    if total_distance <= 0:
        return geometry[0]

    target_distance = (
        total_distance *
        progress
    )

    travelled_distance = 0

    for index in range(
        len(geometry) - 1
    ):

        point_a = geometry[index]
        point_b = geometry[index + 1]

        segment_distance = (
            calculate_distance_km(
                point_a[1],
                point_a[0],
                point_b[1],
                point_b[0]
            )
        )

        if (
            travelled_distance
            +
            segment_distance
            >=
            target_distance
        ):

            remaining_distance = (
                target_distance
                -
                travelled_distance
            )

            if segment_distance > 0:

                local_progress = (
                    remaining_distance
                    /
                    segment_distance
                )

            else:

                local_progress = 0

            longitude = (
                point_a[0]
                +
                (
                    point_b[0]
                    -
                    point_a[0]
                )
                *
                local_progress
            )

            latitude = (
                point_a[1]
                +
                (
                    point_b[1]
                    -
                    point_a[1]
                )
                *
                local_progress
            )

            return (
                latitude,
                longitude
            )

        travelled_distance += (
            segment_distance
        )

    last_point = geometry[-1]

    return (
        last_point[1],
        last_point[0]
    )


# ==========================================================
# HEADING ALONG OSRM GEOMETRY
# ==========================================================

def get_heading_along_geometry(
    geometry,
    progress
):
    """
    Calculate approximate heading along
    the OSRM road geometry.
    """

    if not geometry or len(geometry) < 2:
        return 0

    progress = max(
        0,
        min(
            1,
            progress
        )
    )

    total_distance = (
        calculate_geometry_distance_km(
            geometry
        )
    )

    if total_distance <= 0:
        return 0

    target_distance = (
        total_distance *
        progress
    )

    travelled_distance = 0

    for index in range(
        len(geometry) - 1
    ):

        point_a = geometry[index]
        point_b = geometry[index + 1]

        segment_distance = (
            calculate_distance_km(
                point_a[1],
                point_a[0],
                point_b[1],
                point_b[0]
            )
        )

        if (
            travelled_distance
            +
            segment_distance
            >=
            target_distance
        ):

            return calculate_bearing(
                point_a[1],
                point_a[0],
                point_b[1],
                point_b[0]
            )

        travelled_distance += (
            segment_distance
        )

    last = len(geometry) - 1

    return calculate_bearing(
        geometry[last - 1][1],
        geometry[last - 1][0],
        geometry[last][1],
        geometry[last][0]
    )


# ==========================================================
# BEARING
# ==========================================================

def calculate_bearing(
    latitude1,
    longitude1,
    latitude2,
    longitude2
):
    """
    Calculate compass bearing between two coordinates.
    """

    lat1 = math.radians(
        latitude1
    )

    lat2 = math.radians(
        latitude2
    )

    delta_longitude = math.radians(
        longitude2 -
        longitude1
    )

    x = (
        math.sin(delta_longitude)
        *
        math.cos(lat2)
    )

    y = (
        math.cos(lat1)
        *
        math.sin(lat2)
        -
        math.sin(lat1)
        *
        math.cos(lat2)
        *
        math.cos(delta_longitude)
    )

    bearing = math.degrees(
        math.atan2(
            x,
            y
        )
    )

    return (
        bearing + 360
    ) % 360


# ==========================================================
# MANAGEMENT COMMAND
# ==========================================================

class Command(BaseCommand):

    help = (
        "Simulate a bus moving along its "
        "current route using OSRM road geometry."
    )

    def add_arguments(
        self,
        parser
    ):

        parser.add_argument(
            "bus_id",
            type=int
        )

    def handle(
        self,
        *args,
        **options
    ):

        bus_id = options["bus_id"]

        try:

            bus = (
                Bus.objects
                .select_related(
                    "current_route"
                )
                .get(
                    id=bus_id
                )
            )

        except Bus.DoesNotExist:

            raise CommandError(
                f"Bus with ID {bus_id} does not exist."
            )

        route = bus.current_route

        if not route:

            raise CommandError(
                "This bus does not have a current route."
            )

        route_stops = list(
            route.route_stops
            .select_related("stop")
            .order_by("stop_order")
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

        if len(route_stops) < 2:

            raise CommandError(
                "The route needs at least two stops "
                "with GPS coordinates."
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Starting simulation for "
                f"{bus.bus_number}"
            )
        )

        self.stdout.write(
            f"Route: {route.route_name}"
        )

        self.stdout.write(
            f"Stops: {len(route_stops)}"
        )

        # --------------------------------------------------
        # START TRACKING SESSION
        # --------------------------------------------------

        location = (
            BusLocation.objects
            .filter(
                bus=bus
            )
            .first()
        )

        if location:

            location.tracking_session_id = (
                uuid.uuid4()
            )

            location.current_route_stop = None

            location.stop_status = (
                "TRAVELLING"
            )

            location.stop_arrived_at = None
            location.stop_departed_at = None

            location.is_tracking = True

        else:

            location = BusLocation(
                bus=bus,
                tracking_session_id=uuid.uuid4(),
                stop_status="TRAVELLING",
                is_tracking=True
            )

        location.save()

        # --------------------------------------------------
        # SIMULATION
        # --------------------------------------------------

        try:

            for index in range(
                len(route_stops) - 1
            ):

                current_stop = (
                    route_stops[index]
                )

                next_stop = (
                    route_stops[index + 1]
                )

                self.stdout.write(
                    ""
                )

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Moving: "
                        f"{current_stop.stop.name}"
                        f" → "
                        f"{next_stop.stop.name}"
                    )
                )

                # ------------------------------------------
                # LOAD OSRM GEOMETRY
                # ------------------------------------------

                geometry = (
                    get_osrm_segment_geometry(
                        current_stop.stop,
                        next_stop.stop
                    )
                )

                if not geometry:

                    self.stdout.write(
                        self.style.WARNING(
                            "OSRM geometry unavailable. "
                            "Skipping segment."
                        )
                    )

                    continue

                segment_distance = (
                    calculate_geometry_distance_km(
                        geometry
                    )
                )

                if segment_distance <= 0:

                    continue

                # ------------------------------------------
                # SIMULATION PROGRESS
                # ------------------------------------------

                segment_progress = 0

                distance_per_step = (
                    SIMULATION_SPEED_KMH
                    *
                    (
                        SIMULATION_INTERVAL
                        /
                        3600
                    )
                )

                progress_per_step = (
                    distance_per_step
                    /
                    segment_distance
                )

                while segment_progress < 1:

                    (
                        latitude,
                        longitude
                    ) = get_point_along_geometry(
                        geometry,
                        segment_progress
                    )

                    heading = (
                        get_heading_along_geometry(
                            geometry,
                            segment_progress
                        )
                    )

                    # --------------------------------------
                    # UPDATE BUS LOCATION
                    # --------------------------------------

                    location.latitude = (
                        latitude
                    )

                    location.longitude = (
                        longitude
                    )

                    location.speed = (
                        SIMULATION_SPEED_KMH
                    )

                    location.heading = (
                        heading
                    )

                    location.accuracy = (
                        SIMULATION_ACCURACY
                    )

                    location.is_tracking = True

                    location.save()

                    # --------------------------------------
                    # ARRIVAL / DEPARTURE DETECTION
                    # --------------------------------------

                    detect_stop_arrival_departure(
                        location,
                        route,
                        latitude,
                        longitude
                    )

                    self.stdout.write(
                        f"\r"
                        f"{current_stop.stop.name}"
                        f" → "
                        f"{next_stop.stop.name}"
                        f"  "
                        f"{segment_progress * 100:5.1f}%",
                        ending=""
                    )

                    segment_progress += (
                        progress_per_step
                    )

                    time.sleep(
                        SIMULATION_INTERVAL
                    )

                self.stdout.write(
                    ""
                )

            # --------------------------------------------------
            # FINAL STOP
            # --------------------------------------------------

            final_stop = (
                route_stops[-1].stop
            )

            location.latitude = (
                final_stop.latitude
            )

            location.longitude = (
                final_stop.longitude
            )

            location.speed = 0

            location.save()

            detect_stop_arrival_departure(
                location,
                route,
                float(final_stop.latitude),
                float(final_stop.longitude)
            )

            self.stdout.write(
                ""
            )

            self.stdout.write(
                self.style.SUCCESS(
                    "Destination reached."
                )
            )

        except KeyboardInterrupt:

            self.stdout.write(
                ""
            )

            self.stdout.write(
                self.style.WARNING(
                    "Simulation stopped."
                )
            )

        finally:

            location.refresh_from_db()

            location.is_tracking = False

            location.speed = 0

            location.save()

            self.stdout.write(
                self.style.WARNING(
                    "Tracking stopped."
                )
            )