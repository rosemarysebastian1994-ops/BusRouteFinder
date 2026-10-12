from django import forms
from routes.models import BusSchedule, RouteStop
import datetime
from django.utils import timezone

class TicketBookingForm(forms.Form):
    schedule = forms.ModelChoiceField(
        queryset=BusSchedule.objects.filter(is_active=True).select_related('route', 'bus'),
        label="Select Bus / Schedule",
        empty_label="- Select a bus schedule -",
        widget=forms.Select(attrs={
            'class': 'form-control',
            'id': 'id_schedule'
        })
    )

    source_stop = forms.ModelChoiceField(
        queryset=RouteStop.objects.none(),  # Populated via AJAX
        label="Boarding Point (From)",
        empty_label="- Select boarding point -",
        widget=forms.Select(attrs={
            'class': 'form-control',
            'id': 'id_source_stop'
        })
    )

    destination_stop = forms.ModelChoiceField(
        queryset=RouteStop.objects.none(),
        label="Dropping Point (To)",
        empty_label="- Select dropping point -",
        widget=forms.Select(attrs={
            'class': 'form-control',
            'id': 'id_destination_stop'
        })
    )

    journey_date = forms.DateField(
        label="Journey Date",
        initial=datetime.date.today,  # <-- Today as default
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control',
            'id': 'id_journey_date',
            'min': str(datetime.date.today()),  # Prevent past dates
        })
    )

    passenger_count = forms.IntegerField(
        label="Passengers",
        min_value=1,
        max_value=6,
        initial=1,
        widget=forms.NumberInput(attrs={
            'class': 'form-control d-none',  # Hidden, we use seat map now
            'id': 'id_passenger_count'
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Set today's date if no data provided (GET request)
        if not self.data and not self.initial.get('journey_date'):
            self.initial['journey_date'] = datetime.date.today()

        # If editing with existing schedule, populate stops
        if 'schedule' in self.data:
            try:
                schedule_id = int(self.data.get('schedule'))
                schedule = BusSchedule.objects.get(id=schedule_id)
                self.fields['source_stop'].queryset = schedule.route.route_stops.all().select_related('stop')
                self.fields['destination_stop'].queryset = schedule.route.route_stops.all().select_related('stop')
            except (ValueError, TypeError, BusSchedule.DoesNotExist):
                pass
        elif self.initial.get('schedule'):
            schedule = self.initial['schedule']
            self.fields['source_stop'].queryset = schedule.route.route_stops.all()
            self.fields['destination_stop'].queryset = schedule.route.route_stops.all()

    def clean(self):
        cleaned = super().clean()
        source = cleaned.get('source_stop')
        dest = cleaned.get('destination_stop')

        if source and dest:
            if source.stop_order >= dest.stop_order:
                raise forms.ValidationError(
                    "Dropping point must be after boarding point. "
                    f"You selected {source.stop.name} (stop {source.stop_order}) "
                    f"and {dest.stop.name} (stop {dest.stop_order})"
                )
            # Also prevent same stop
            if source.id == dest.id:
                raise forms.ValidationError("Boarding and dropping points cannot be the same")

        return cleaned