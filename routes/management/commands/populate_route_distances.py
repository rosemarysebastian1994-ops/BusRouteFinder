from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import (
    BaseCommand,
    CommandError,
)

from routes.models import Route, RouteStop
from buses.views import get_osrm_segment_distance


class Command(BaseCommand):

    help = (
        'Populate cumulative road distances for RouteStop '
        'records using OSRM.'
    )

    def handle(self, *args, **options):

        routes = Route.objects.all().order_by('id')

        if not routes.exists():
            raise CommandError(
                'No routes found.'
            )

        for route in routes:

            route_stops = list(
                RouteStop.objects
                .filter(route=route)
                .select_related('stop')
                .order_by('stop_order')
            )

            if not route_stops:
                self.stdout.write(
                    self.style.WARNING(
                        f'No stops found for route: '
                        f'{route.route_name}'
                    )
                )
                continue

            cumulative_distance = Decimal('0.00')

            # First stop is always 0 km.
            first_route_stop = route_stops[0]

            first_route_stop.distance_from_start_km = (
                Decimal('0.00')
            )

            first_route_stop.save(
                update_fields=[
                    'distance_from_start_km'
                ]
            )

            self.stdout.write(
                f'\nRoute: {route.route_name}'
            )

            self.stdout.write(
                f'  {first_route_stop.stop.name}: '
                f'0.00 km'
            )

            previous_stop = (
                first_route_stop.stop
            )

            for route_stop in route_stops[1:]:

                current_stop = route_stop.stop

                segment_distance = (
                    get_osrm_segment_distance(
                        previous_stop,
                        current_stop
                    )
                )

                if segment_distance is None:

                    self.stdout.write(
                        self.style.ERROR(
                            f'  Unable to calculate distance: '
                            f'{previous_stop.name} → '
                            f'{current_stop.name}'
                        )
                    )

                    continue

                segment_distance = Decimal(
                    str(segment_distance)
                ).quantize(
                    Decimal('0.01'),
                    rounding=ROUND_HALF_UP
                )

                cumulative_distance += (
                    segment_distance
                )

                route_stop.distance_from_start_km = (
                    cumulative_distance
                )

                route_stop.save(
                    update_fields=[
                        'distance_from_start_km'
                    ]
                )

                self.stdout.write(
                    f'  {current_stop.name}: '
                    f'{cumulative_distance:.2f} km '
                    f'(+{segment_distance:.2f} km)'
                )

                previous_stop = current_stop

        self.stdout.write(
            self.style.SUCCESS(
                '\nRoute distances populated successfully.'
            )
        )