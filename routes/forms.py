from django import forms
from .models import Route, Stop, RouteStop, BusSchedule


class RouteForm(forms.ModelForm):

    class Meta:
        model = Route
        fields = [
            'bus',
            'route_name',
            'description',
            'duration_minutes',
        ]

        widgets = {
            'bus': forms.Select(
                attrs={
                    'class': 'form-select'
                }
            ),

            'route_name': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Enter route name'
                }
            ),

            'description': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 3,
                    'placeholder': 'Enter route description'
                }
            ),

            'duration_minutes': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Duration in minutes',
                    'min': 1
                }
            ),
        }

        labels = {
            'bus': 'Bus',
            'route_name': 'Route Name',
            'description': 'Description',
            'duration_minutes': 'Estimated Duration (minutes)',
        }

class RouteStopForm(forms.ModelForm):

    class Meta:
        model = RouteStop

        fields = [
            'stop',
            'travel_time_minutes',
        ]

        widgets = {
            'stop': forms.Select(
                attrs={
                    'class': 'form-select'
                }
            ),

            'travel_time_minutes': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'min': 0,
                    'placeholder': 'Minutes from previous stop'
                }
            ),
        }

        labels = {
            'stop': 'Stop',
            'travel_time_minutes': 'Travel Time from Previous Stop (minutes)',
        }

class BusScheduleForm(forms.ModelForm):

    class Meta:
        model = BusSchedule

        fields = [
            'route',
            'day',
            'departure_time',
            'arrival_time',
            'is_active',
        ]

        widgets = {

            'route': forms.Select(
                attrs={
                    'class': 'form-select'
                }
            ),

            'day': forms.Select(
                attrs={
                    'class': 'form-select'
                }
            ),

            'departure_time': forms.TimeInput(
                attrs={
                    'type': 'time',
                    'class': 'form-control'
                }
            ),

            'arrival_time': forms.TimeInput(
                attrs={
                    'type': 'time',
                    'class': 'form-control'
                }
            ),

            'is_active': forms.CheckboxInput(
                attrs={
                    'class': 'form-check-input'
                }
            ),
        }

        labels = {
            'route': 'Route',
            'day': 'Day',
            'departure_time': 'Departure Time',
            'arrival_time': 'Arrival Time',
            'is_active': 'Active',
        }

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.fields['route'].queryset = (
            Route.objects
            .select_related('bus')
            .order_by('route_name')
        )