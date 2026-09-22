from django.shortcuts import render, redirect, get_object_or_404
from .models import Route, Stop, RouteStop, BusSchedule
from .forms import RouteForm, RouteStopForm, BusScheduleForm
from datetime import date, datetime, timedelta
from django.contrib import messages
from django.db import transaction
from django.contrib.auth.decorators import user_passes_test
from accounts.models import FavouriteRoute, FavouriteStop
from django.db.models import Prefetch


def admin_required(view_func):

    return user_passes_test(
        lambda user: user.is_authenticated and user.is_superuser
    )(view_func)

def calculate_route_duration(route_stop_list, source_name, destination_name):
    """
    Calculate travel time between the requested source and destination.

    travel_time_minutes on a RouteStop represents the time taken
    from the previous stop to that stop.
    """

    source_index = None
    destination_index = None

    for index, route_stop in enumerate(route_stop_list):

        stop_name = route_stop.stop.name.strip().lower()

        if stop_name == source_name.strip().lower():
            source_index = index

        if stop_name == destination_name.strip().lower():
            destination_index = index

    if source_index is None or destination_index is None:
        return None

    # Destination must occur after source in this route direction.
    if source_index >= destination_index:
        return None

    total_minutes = 0

    for route_stop in route_stop_list[
        source_index + 1 : destination_index + 1
    ]:

        total_minutes += (
            route_stop.travel_time_minutes or 0
        )

    return total_minutes

def format_duration(total_minutes):
    """
    Convert minutes into a readable duration.
    """

    if total_minutes is None:
        return "—"

    hours, minutes = divmod(total_minutes, 60)

    if hours and minutes:
        return f"{hours} hr {minutes} min"

    if hours:
        return f"{hours} hr"

    return f"{minutes} min"

def calculate_arrival_time(departure_time, duration_minutes):
    """
    Calculate arrival time by adding route duration
    to the bus departure time.
    """

    if not departure_time or duration_minutes is None:
        return None

    departure_datetime = datetime.combine(
        datetime.today(),
        departure_time
    )

    arrival_datetime = (
        departure_datetime +
        timedelta(minutes=duration_minutes)
    )

    return arrival_datetime.time()

def format_duration(total_minutes):
    """
    Convert minutes into a readable duration.
    """

    if total_minutes is None:
        return "—"

    hours = total_minutes // 60
    minutes = total_minutes % 60

    if hours and minutes:
        return f"{hours} hr {minutes} min"

    if hours:
        return f"{hours} hr"

    return f"{minutes} min"


def calculate_arrival_time(departure_time, duration_minutes):
    """
    Calculate the arrival time by adding the searched
    source-to-destination duration to the departure time.
    """

    if not departure_time or duration_minutes is None:
        return None

    departure_datetime = datetime.combine(
        date.today(),
        departure_time
    )

    arrival_datetime = (
        departure_datetime +
        timedelta(minutes=duration_minutes)
    )

    return arrival_datetime.time()


def route_search(request):

    source = request.GET.get(
        'source',
        ''
    ).strip()

    destination = request.GET.get(
        'destination',
        ''
    ).strip()

    travel_date = request.GET.get(
        'travel_date',
        ''
    )

    departure_time = request.GET.get(
        'departure_time',
        ''
    ).strip()

    departure_filter = request.GET.get(
        'departure_filter',
        'any'
    ).strip()

    modify = request.GET.get('modify')

    if departure_filter != 'after':
        departure_time = ''

    # ---------------------------------------------------------
    # DEFAULT TRAVEL DATE
    # ---------------------------------------------------------

    if not travel_date:

        travel_date = date.today().strftime(
            '%Y-%m-%d'
        )


    stops = Stop.objects.order_by('name')


    # ---------------------------------------------------------
    # MODIFY SEARCH
    # ---------------------------------------------------------

    if modify == '1':

        return render(
            request,
            'routes/search.html',
            {
                'source': source,
                'destination': destination,
                'travel_date': travel_date,
                'departure_time': departure_time,
                'departure_filter': departure_filter,
                'stops': stops,
            }
        )


    # ---------------------------------------------------------
    # FIRST VISIT / EMPTY SEARCH
    # ---------------------------------------------------------

    if not source or not destination:

        return render(
            request,
            'routes/search.html',
            {
                'source': source,
                'destination': destination,
                'travel_date': travel_date,
                'departure_time': departure_time,
                'departure_filter': departure_filter,
                'stops': stops,
            }
        )


    # ---------------------------------------------------------
    # PARSE DEPARTURE TIME FILTER
    # ---------------------------------------------------------

    selected_departure_time = None

    if departure_time:

        try:

            selected_departure_time = datetime.strptime(
                departure_time,
                '%H:%M'
            ).time()

        except ValueError:

            selected_departure_time = None


    # ---------------------------------------------------------
    # FIND POSSIBLE SOURCE / DESTINATION STOPS
    # ---------------------------------------------------------

    source_stops = Stop.objects.filter(
        name__icontains=source
    )

    destination_stops = Stop.objects.filter(
        name__icontains=destination
    )


    # ---------------------------------------------------------
    # FIND ROUTES CONTAINING BOTH STOPS
    # ---------------------------------------------------------

    matching_routes = (
        Route.objects
        .filter(
            route_stops__stop__in=source_stops
        )
        .filter(
            route_stops__stop__in=destination_stops
        )
        .select_related(
            'bus'
        )
        .prefetch_related(
            'route_stops__stop',
            'schedules'
        )
        .distinct()
    )


    # ---------------------------------------------------------
    # DETERMINE SELECTED DAY
    # ---------------------------------------------------------

    day_code = None

    try:

        selected_date = datetime.strptime(
            travel_date,
            '%Y-%m-%d'
        ).date()

        day_codes = [
            'MON',
            'TUE',
            'WED',
            'THU',
            'FRI',
            'SAT',
            'SUN',
        ]

        day_code = day_codes[
            selected_date.weekday()
        ]

    except ValueError:

        day_code = None


    routes = []


    # ---------------------------------------------------------
    # PROCESS EACH MATCHING ROUTE
    # ---------------------------------------------------------

    for route in matching_routes:

        route_stops = list(
            route.route_stops.all()
        )


        # -----------------------------------------------------
        # FIND SOURCE STOP(S) ON THIS ROUTE
        # -----------------------------------------------------

        source_stops_for_route = [

            route_stop

            for route_stop in route_stops

            if route_stop.stop in source_stops

        ]


        # -----------------------------------------------------
        # FIND DESTINATION STOP(S) ON THIS ROUTE
        # -----------------------------------------------------

        destination_stops_for_route = [

            route_stop

            for route_stop in route_stops

            if route_stop.stop in destination_stops

        ]


        # -----------------------------------------------------
        # FIND VALID SOURCE → DESTINATION PAIR
        # -----------------------------------------------------

        valid_pairs = [

            (source_stop, destination_stop)

            for source_stop in source_stops_for_route

            for destination_stop in destination_stops_for_route

            if (
                source_stop.stop_order
                <
                destination_stop.stop_order
            )

        ]


        if not valid_pairs:

            continue


        source_stop, destination_stop = valid_pairs[0]


        # -----------------------------------------------------
        # SAVE SEARCH START / END
        # -----------------------------------------------------

        route.search_source = (
            source_stop.stop
        )

        route.search_destination = (
            destination_stop.stop
        )


        # -----------------------------------------------------
        # STOPS BETWEEN SOURCE AND DESTINATION
        # -----------------------------------------------------

        route.stops_between = [

            route_stop

            for route_stop in route_stops

            if (
                source_stop.stop_order
                <=
                route_stop.stop_order
                <=
                destination_stop.stop_order
            )

        ]


        # -----------------------------------------------------
        # CALCULATE SEGMENT DURATION
        # -----------------------------------------------------

        duration_minutes = 0

        for route_stop in route.stops_between:

            if (
                route_stop.stop_order
                >
                source_stop.stop_order
            ):

                duration_minutes += (
                    route_stop.travel_time_minutes
                    or 0
                )


        route.search_duration_minutes = (
            duration_minutes
        )

        route.search_duration_display = (
            format_duration(
                duration_minutes
            )
        )


        # -----------------------------------------------------
        # GET SCHEDULES FOR SELECTED DAY
        # -----------------------------------------------------

        if day_code:

            schedules = route.schedules.filter(
                day=day_code,
                is_active=True
            ).order_by(
                'departure_time'
            )

        else:

            schedules = route.schedules.filter(
                is_active=True
            ).order_by(
                'day_order',
                'departure_time'
            )


        # -----------------------------------------------------
        # CALCULATE ELAPSED TIME FROM ROUTE ORIGIN
        # TO SEARCHED SOURCE STOP
        # -----------------------------------------------------

        source_elapsed_minutes = 0

        for route_stop in route_stops:

            if (
                route_stop.stop_order
                <=
                source_stop.stop_order
            ):

                if route_stop.stop_order > 1:

                    source_elapsed_minutes += (
                        route_stop.travel_time_minutes
                        or 0
                    )


        # -----------------------------------------------------
        # PROCESS EACH BUS SCHEDULE
        # -----------------------------------------------------

        search_schedules = []

        for schedule in schedules:


            # -------------------------------------------------
            # ACTUAL DEPARTURE FROM SEARCHED SOURCE
            # -------------------------------------------------

            search_departure_time = (
                calculate_arrival_time(
                    schedule.departure_time,
                    source_elapsed_minutes
                )
            )


            # -------------------------------------------------
            # DEPARTURE-TIME FILTER
            #
            # Filter using the actual departure time from
            # the searched source stop.
            #
            # Example:
            #
            # Route origin       6:30 AM
            # Tripunithura       7:00 AM
            #
            # If user selects 7:00 AM,
            # this schedule is INCLUDED.
            # -------------------------------------------------

            if (
                selected_departure_time
                and
                search_departure_time
                <
                selected_departure_time
            ):

                continue


            # -------------------------------------------------
            # CREATE SCHEDULE-SPECIFIC STOP TIMELINE
            # -------------------------------------------------

            schedule_stops = []

            elapsed_from_source = 0


            for route_stop in route.stops_between:

                # ---------------------------------------------
                # SEARCH SOURCE STOP
                # ---------------------------------------------

                if (
                    route_stop.stop_order
                    ==
                    source_stop.stop_order
                ):

                    stop_time = (
                        search_departure_time
                    )


                # ---------------------------------------------
                # FOLLOWING STOPS
                # ---------------------------------------------

                else:

                    elapsed_from_source += (
                        route_stop.travel_time_minutes
                        or 0
                    )

                    stop_time = (
                        calculate_arrival_time(
                            search_departure_time,
                            elapsed_from_source
                        )
                    )


                # ---------------------------------------------
                # SAVE STOP INFORMATION
                # ---------------------------------------------

                schedule_stops.append({

                    'route_stop': route_stop,

                    'time': stop_time,

                    'travel_time': (
                        route_stop.travel_time_minutes
                        if (
                            route_stop.stop_order
                            >
                            source_stop.stop_order
                        )
                        else 0
                    ),

                })


            # -------------------------------------------------
            # ACTUAL ARRIVAL AT SEARCHED DESTINATION
            # -------------------------------------------------

            search_arrival_time = (
                calculate_arrival_time(
                    search_departure_time,
                    duration_minutes
                )
            )


            # -------------------------------------------------
            # ATTACH CALCULATED VALUES TO SCHEDULE
            # -------------------------------------------------

            schedule.search_departure_time = (
                search_departure_time
            )

            schedule.search_arrival_time = (
                search_arrival_time
            )

            schedule.search_stops = (
                schedule_stops
            )


            # -------------------------------------------------
            # ADD SCHEDULE TO RESULTS
            # -------------------------------------------------

            search_schedules.append(
                schedule
            )


        # -----------------------------------------------------
        # SAVE FILTERED SCHEDULES TO ROUTE
        # -----------------------------------------------------

        route.search_schedules = (
            search_schedules
        )


        # -----------------------------------------------------
        # IMPORTANT:
        # Only add the route if it still has at least one
        # schedule after departure-time filtering.
        # -----------------------------------------------------

        if not search_schedules:

            continue


        # -----------------------------------------------------
        # ADD ROUTE TO RESULTS
        # -----------------------------------------------------

        routes.append(
            route
        )


    # ---------------------------------------------------------
    # CONTEXT
    # ---------------------------------------------------------

    context = {

        'source': source,

        'destination': destination,

        'travel_date': travel_date,

        'departure_time': departure_time,

        'departure_filter': departure_filter,

        'routes': routes,

        'stops': stops,

    }


    # ---------------------------------------------------------
    # RENDER RESULTS
    # ---------------------------------------------------------

    return render(
        request,
        'routes/results.html',
        context
    )

def routes_list(request):
    routes = (
        Route.objects
        .select_related('bus')
        .prefetch_related(
            'route_stops__stop',
            'schedules'
        )
        .order_by('route_name')
    )

    favourite_route_ids = set()

    if request.user.is_authenticated:
        favourite_route_ids = set(
            FavouriteRoute.objects
            .filter(user=request.user)
            .values_list('route_id', flat=True)
        )

    day_order = [
        ('MON', 'Monday'),
        ('TUE', 'Tuesday'),
        ('WED', 'Wednesday'),
        ('THU', 'Thursday'),
        ('FRI', 'Friday'),
        ('SAT', 'Saturday'),
        ('SUN', 'Sunday'),
    ]

    for route in routes:

        # All active schedules for this route
        schedules = [
            schedule
            for schedule in route.schedules.all()
            if schedule.is_active
        ]

        # Group schedules by day
        weekly_schedules = []

        for day_code, day_name in day_order:

            day_schedules = [
                schedule
                for schedule in schedules
                if schedule.day == day_code
            ]

            day_schedules.sort(
                key=lambda schedule: schedule.departure_time
            )

            weekly_schedules.append({
                'code': day_code,
                'name': day_name,
                'schedules': day_schedules,
            })

        route.weekly_schedules = weekly_schedules

    return render(
        request,
        'routes/list.html',
        {
            'routes': routes,
            'favourite_route_ids': favourite_route_ids,
        }
    )

def stops_list(request):
    stops = Stop.objects.order_by('name')

    favourite_stop_ids = set()

    if request.user.is_authenticated:
        favourite_stop_ids = set(
            FavouriteStop.objects
            .filter(user=request.user)
            .values_list('stop_id', flat=True)
        )

    return render(
        request,
        'routes/stops.html',
        {
            'stops': stops,
            'favourite_stop_ids': favourite_stop_ids,
        }
    )

def stop_detail(request, stop_id):
    stop = get_object_or_404(
        Stop,
        id=stop_id
    )

    is_favourite = False

    if request.user.is_authenticated:
        is_favourite = FavouriteStop.objects.filter(
            user=request.user,
            stop=stop
        ).exists()

    return render(
        request,
        'routes/stop_detail.html',
        {
            'stop': stop,
            'is_favourite': is_favourite,
        }
    )

def route_detail(request, route_id):
    route = get_object_or_404(
        Route.objects
        .select_related('bus')
        .prefetch_related(
            'route_stops__stop',
            'schedules'
        ),
        id=route_id
    )

    # ---------------------------------------------------------
    # FAVOURITE STATUS
    # ---------------------------------------------------------

    is_favourite = False

    if request.user.is_authenticated:

        is_favourite = FavouriteRoute.objects.filter(
            user=request.user,
            route=route
        ).exists()


    # ---------------------------------------------------------
    # ACTIVE SCHEDULES
    # ---------------------------------------------------------

    schedules = [
        schedule
        for schedule in route.schedules.all()
        if schedule.is_active
    ]

    schedules.sort(
        key=lambda schedule: (
            schedule.day_order,
            schedule.departure_time
        )
    )


    # ---------------------------------------------------------
    # WEEKLY SCHEDULE
    # ---------------------------------------------------------

    day_order = [
        ('MON', 'Monday'),
        ('TUE', 'Tuesday'),
        ('WED', 'Wednesday'),
        ('THU', 'Thursday'),
        ('FRI', 'Friday'),
        ('SAT', 'Saturday'),
        ('SUN', 'Sunday'),
    ]

    weekly_schedules = []

    for day_code, day_name in day_order:

        day_schedules = [
            schedule
            for schedule in schedules
            if schedule.day == day_code
        ]

        day_schedules.sort(
            key=lambda schedule: schedule.departure_time
        )

        weekly_schedules.append({
            'code': day_code,
            'name': day_name,
            'schedules': day_schedules,
        })


    # Attach weekly schedules to the route object
    route.weekly_schedules = weekly_schedules


    # ---------------------------------------------------------
    # RENDER
    # ---------------------------------------------------------

    return render(
        request,
        'routes/detail.html',
        {
            'route': route,
            'is_favourite': is_favourite,
            'schedules': schedules,
        }
    )


@admin_required
def route_management(request):
    routes = Route.objects.select_related(
        'bus'
    ).prefetch_related(
        'route_stops__stop'
    ).order_by('route_name')

    return render(
        request,
        'routes/management/list.html',
        {
            'routes': routes,
        }
    )

@admin_required
def route_create(request):

    if request.method == 'POST':
        form = RouteForm(request.POST)

        if form.is_valid():
            form.save()

            messages.success(
                request,
                'Route added successfully.'
            )

            return redirect('routes:route_management')

    else:
        form = RouteForm()

    return render(
        request,
        'routes/management/form.html',
        {
            'form': form,
            'title': 'Add Route',
            'button_text': 'Add Route',
        }
    )

@admin_required
def route_edit(request, route_id):

    route = get_object_or_404(
        Route,
        id=route_id
    )

    if request.method == 'POST':
        form = RouteForm(
            request.POST,
            instance=route
        )

        if form.is_valid():
            form.save()

            messages.success(
                request,
                'Route updated successfully.'
            )

            return redirect('routes:route_management')

    else:
        form = RouteForm(instance=route)

    return render(
        request,
        'routes/management/form.html',
        {
            'form': form,
            'title': 'Edit Route',
            'button_text': 'Update Route',
        }
    )

@admin_required
def route_delete(request, route_id):

    route = get_object_or_404(
        Route,
        id=route_id
    )

    if request.method == 'POST':
        route.delete()

        messages.success(
            request,
            'Route deleted successfully.'
        )

        return redirect('routes:route_management')

    return render(
        request,
        'routes/management/delete.html',
        {
            'route': route,
        }
    )

@admin_required
def manage_route_stops(request, route_id):

    route = get_object_or_404(
        Route.objects.select_related('bus'),
        id=route_id
    )

    route_stops = route.route_stops.select_related(
        'stop'
    ).order_by(
        'stop_order'
    )

    return render(
        request,
        'routes/management/stops.html',
        {
            'route': route,
            'route_stops': route_stops,
        }
    )

@admin_required
def add_route_stop(request, route_id):

    route = get_object_or_404(
        Route,
        id=route_id
    )

    if request.method == 'POST':

        form = RouteStopForm(request.POST)

        if form.is_valid():

            stop = form.cleaned_data['stop']

            # Prevent duplicate stop
            if RouteStop.objects.filter(
                route=route,
                stop=stop
            ).exists():

                form.add_error(
                    'stop',
                    'This stop is already part of this route.'
                )

            else:

                with transaction.atomic():

                    last_stop = RouteStop.objects.filter(
                        route=route
                    ).order_by(
                        '-stop_order'
                    ).first()

                    if last_stop:
                        new_order = last_stop.stop_order + 1
                    else:
                        new_order = 1

                    route_stop = form.save(
                        commit=False
                    )

                    route_stop.route = route
                    route_stop.stop_order = new_order
                    route_stop.save()

                messages.success(
                    request,
                    'Stop added to the route successfully.'
                )

                return redirect(
                    'routes:manage_route_stops',
                    route_id=route.id
                )

    else:

        form = RouteStopForm()

    return render(
        request,
        'routes/management/stop_form.html',
        {
            'route': route,
            'form': form,
            'title': 'Add Stop',
            'button_text': 'Add Stop',
        }
    )

@admin_required
def edit_route_stop(
    request,
    route_id,
    route_stop_id
):

    route = get_object_or_404(
        Route,
        id=route_id
    )

    route_stop = get_object_or_404(
        RouteStop,
        id=route_stop_id,
        route=route
    )

    if request.method == 'POST':

        form = RouteStopForm(
            request.POST,
            instance=route_stop
        )

        if form.is_valid():

            new_stop = form.cleaned_data['stop']

            if RouteStop.objects.filter(
                route=route,
                stop=new_stop
            ).exclude(
                id=route_stop.id
            ).exists():

                form.add_error(
                    'stop',
                    'This stop is already part of this route.'
                )

            else:

                form.save()

                messages.success(
                    request,
                    'Route stop updated successfully.'
                )

                return redirect(
                    'routes:manage_route_stops',
                    route_id=route.id
                )

    else:

        form = RouteStopForm(
            instance=route_stop
        )

    return render(
        request,
        'routes/management/stop_form.html',
        {
            'route': route,
            'route_stop': route_stop,
            'form': form,
            'title': 'Edit Stop',
            'button_text': 'Update Stop',
        }
    )

@admin_required
def delete_route_stop(
    request,
    route_id,
    route_stop_id
):

    route = get_object_or_404(
        Route,
        id=route_id
    )

    route_stop = get_object_or_404(
        RouteStop,
        id=route_stop_id,
        route=route
    )

    if request.method == 'POST':

        with transaction.atomic():

            route_stop.delete()

            route_stops = list(
                RouteStop.objects.filter(
                    route=route
                ).order_by('stop_order')
            )

            # Temporarily move to safe positive values
            temporary_base = 1000000

            for index, item in enumerate(
                route_stops,
                start=1
            ):

                item.stop_order = temporary_base + index

                item.save(
                    update_fields=['stop_order']
                )

            # Re-number from 1
            for index, item in enumerate(
                route_stops,
                start=1
            ):

                item.stop_order = index

                item.save(
                    update_fields=['stop_order']
                )

        messages.success(
            request,
            'Stop removed from the route successfully.'
        )

        return redirect(
            'routes:manage_route_stops',
            route_id=route.id
        )

    return render(
        request,
        'routes/management/stop_delete.html',
        {
            'route': route,
            'route_stop': route_stop,
        }
    )

@admin_required
def move_route_stop_up(
    request,
    route_id,
    route_stop_id
):

    route = get_object_or_404(
        Route,
        id=route_id
    )

    route_stop = get_object_or_404(
        RouteStop,
        id=route_stop_id,
        route=route
    )

    if request.method == 'POST':

        current_order = route_stop.stop_order

        previous_stop = RouteStop.objects.filter(
            route=route,
            stop_order__lt=current_order
        ).order_by(
            '-stop_order'
        ).first()

        if previous_stop:

            previous_order = previous_stop.stop_order

            with transaction.atomic():

                # Move current stop to a safe temporary value
                route_stop.stop_order = 1000000
                route_stop.save(
                    update_fields=['stop_order']
                )

                # Move previous stop into current position
                previous_stop.stop_order = current_order
                previous_stop.save(
                    update_fields=['stop_order']
                )

                # Move current stop into previous position
                route_stop.stop_order = previous_order
                route_stop.save(
                    update_fields=['stop_order']
                )

            messages.success(
                request,
                'Stop moved up successfully.'
            )

    return redirect(
        'routes:manage_route_stops',
        route_id=route.id
    )

@admin_required
def move_route_stop_down(
    request,
    route_id,
    route_stop_id
):

    route = get_object_or_404(
        Route,
        id=route_id
    )

    route_stop = get_object_or_404(
        RouteStop,
        id=route_stop_id,
        route=route
    )

    if request.method == 'POST':

        current_order = route_stop.stop_order

        next_stop = RouteStop.objects.filter(
            route=route,
            stop_order__gt=current_order
        ).order_by(
            'stop_order'
        ).first()

        if next_stop:

            next_order = next_stop.stop_order

            with transaction.atomic():

                # Move current stop to a safe temporary value
                route_stop.stop_order = 1000000
                route_stop.save(
                    update_fields=['stop_order']
                )

                # Move next stop into current position
                next_stop.stop_order = current_order
                next_stop.save(
                    update_fields=['stop_order']
                )

                # Move current stop into next position
                route_stop.stop_order = next_order
                route_stop.save(
                    update_fields=['stop_order']
                )

            messages.success(
                request,
                'Stop moved down successfully.'
            )

    return redirect(
        'routes:manage_route_stops',
        route_id=route.id
    )

@admin_required
def schedule_management(request):

    schedules = BusSchedule.objects.select_related(
        'route',
        'route__bus'
    ).order_by(
        'day_order',
        'departure_time'
    )

    return render(
        request,
        'routes/management/schedules.html',
        {
            'schedules': schedules,
        }
    )

@admin_required
def schedule_create(request):

    if request.method == 'POST':

        form = BusScheduleForm(request.POST)

        if form.is_valid():

            form.save()

            messages.success(
                request,
                'Bus schedule added successfully.'
            )

            return redirect(
                'routes:schedule_management'
            )

    else:

        form = BusScheduleForm()

    return render(
        request,
        'routes/management/schedule_form.html',
        {
            'form': form,
            'title': 'Add Bus Schedule',
            'button_text': 'Add Schedule',
        }
    )

@admin_required
def schedule_edit(request, schedule_id):

    schedule = get_object_or_404(
        BusSchedule,
        id=schedule_id
    )

    if request.method == 'POST':

        form = BusScheduleForm(
            request.POST,
            instance=schedule
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                'Bus schedule updated successfully.'
            )

            return redirect(
                'routes:schedule_management'
            )

    else:

        form = BusScheduleForm(
            instance=schedule
        )

    return render(
        request,
        'routes/management/schedule_form.html',
        {
            'form': form,
            'schedule': schedule,
            'title': 'Edit Bus Schedule',
            'button_text': 'Update Schedule',
        }
    )

@admin_required
def schedule_delete(request, schedule_id):

    schedule = get_object_or_404(
        BusSchedule,
        id=schedule_id
    )

    if request.method == 'POST':

        schedule.delete()

        messages.success(
            request,
            'Bus schedule deleted successfully.'
        )

        return redirect(
            'routes:schedule_management'
        )

    return render(
        request,
        'routes/management/schedule_delete.html',
        {
            'schedule': schedule,
        }
    )