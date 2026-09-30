from django import forms
from django.core.exceptions import ValidationError

from .models import Ticket
from routes.models import BusSchedule, RouteStop

from django.utils import timezone
from datetime import datetime, timedelta

from routes.utils import (
    calculate_stop_departure_time,
)

from routes.utils import (
    calculate_stop_arrival_datetime,
)

class TicketBookingForm(forms.ModelForm):

    class Meta:
        model = Ticket

        fields = [
            'schedule',
            'source_stop',
            'destination_stop',
            'journey_date',
            'passenger_count',
        ]

        widgets = {
            'schedule': forms.Select(
                attrs={
                    'class': 'form-control',
                    'id': 'id_schedule',
                }
            ),

            'source_stop': forms.Select(
                attrs={
                    'class': 'form-control',
                    'id': 'id_source_stop',
                }
            ),

            'destination_stop': forms.Select(
                attrs={
                    'class': 'form-control',
                    'id': 'id_destination_stop',
                }
            ),

            'journey_date': forms.DateInput(
                attrs={
                    'class': 'form-control',
                    'type': 'date',
                    'min': timezone.localdate().isoformat(),
                }
            ),

            'passenger_count': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'min': 1,
                    'max': 10,
                    'value': 1,
                }
            ),
        }

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.fields['schedule'].queryset = (
            BusSchedule.objects
            .filter(is_active=True)
            .select_related(
                'route',
                'route__bus'
            )
            .order_by(
                'day_order',
                'departure_time'
            )
        )

        # Initially empty.
        self.fields['source_stop'].queryset = (
            RouteStop.objects.none()
        )

        self.fields['destination_stop'].queryset = (
            RouteStop.objects.none()
        )

        if not self.is_bound:
            self.initial['journey_date'] = timezone.localdate()

        # When the form is submitted, load the stops
        # belonging to the selected schedule.
        if self.is_bound:

            schedule_id = self.data.get('schedule')

            if schedule_id:

                try:
                    schedule = BusSchedule.objects.get(
                        id=schedule_id,
                        is_active=True
                    )

                    route_stops = (
                        RouteStop.objects
                        .filter(route=schedule.route)
                        .select_related('stop')
                        .order_by('stop_order')
                    )

                    self.fields['source_stop'].queryset = (
                        route_stops
                    )

                    self.fields['destination_stop'].queryset = (
                        route_stops
                    )

                except BusSchedule.DoesNotExist:
                    pass

    def clean(self):

        cleaned_data = super().clean()

        schedule = cleaned_data.get('schedule')
        source_stop = cleaned_data.get('source_stop')
        destination_stop = cleaned_data.get('destination_stop')
        journey_date = cleaned_data.get('journey_date')
        passenger_count = cleaned_data.get('passenger_count')

        if (
            schedule
            and source_stop
            and destination_stop
        ):

            if source_stop.route_id != schedule.route_id:

                raise ValidationError(
                    'Source stop does not belong to the selected route.'
                )

            if destination_stop.route_id != schedule.route_id:

                raise ValidationError(
                    'Destination stop does not belong to the selected route.'
                )

            if (
                source_stop.stop_order
                >= destination_stop.stop_order
            ):

                raise ValidationError(
                    'Destination stop must come after the source stop.'
                )

        if journey_date:

            today = timezone.localdate()

            if journey_date < today:
                raise ValidationError(
                    'Journey date cannot be before today.'
                )

            if (
                    journey_date == today
                    and schedule
                    and source_stop
            ):

                current_datetime = timezone.localtime()

                source_stop_datetime = (
                    calculate_stop_arrival_datetime(
                        schedule,
                        source_stop,
                        journey_date,
                    )
                )

                if current_datetime >= source_stop_datetime:
                    raise ValidationError(
                        'The bus has already reached or passed '
                        'your selected source stop. '
                        'Please select a later journey.'
                    )

        if journey_date and schedule:

            day_map = {
                0: 'MON',
                1: 'TUE',
                2: 'WED',
                3: 'THU',
                4: 'FRI',
                5: 'SAT',
                6: 'SUN',
            }

            expected_day = day_map[
                journey_date.weekday()
            ]

            if schedule.day != expected_day:

                raise ValidationError(
                    f'This schedule operates on '
                    f'{schedule.get_day_display()}. '
                    f'Please select a matching journey date.'
                )

        if passenger_count and passenger_count > 10:

            raise ValidationError(
                'Maximum 10 passengers can be booked at once.'
            )

        return cleaned_data