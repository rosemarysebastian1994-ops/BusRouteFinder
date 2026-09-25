from django.db import models
from django.contrib.auth.models import User
import uuid

# Create your models here.


class Bus(models.Model):
    BUS_TYPE_CHOICES = [
        ('ORDINARY', 'Ordinary'),
        ('FAST', 'Fast Passenger'),
        ('SUPER_FAST', 'Super Fast'),
        ('EXPRESS', 'Express'),
        ('AC', 'AC'),
    ]

    bus_number = models.CharField(max_length=20, unique=True)
    bus_name = models.CharField(max_length=100)
    bus_type = models.CharField(
        max_length=20,
        choices=BUS_TYPE_CHOICES,
        default='ORDINARY'
    )
    operator = models.CharField(max_length=100, blank=True)

    photo = models.ImageField(
        upload_to='buses/',
        blank=True,
        null=True
    )

    fare = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0
    )

    driver = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_bus',
        limit_choices_to={
            'groups__name': 'Drivers'
        }
    )

    current_route = models.ForeignKey(
        'routes.Route',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='currently_assigned_buses'
    )

    def __str__(self):
        return f"{self.bus_number} - {self.bus_name}"

class BusLocation(models.Model):
    bus = models.OneToOneField(
        Bus,
        on_delete=models.CASCADE,
        related_name='current_location'
    )

    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6
    )

    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6
    )

    speed = models.FloatField(
        null=True,
        blank=True,
        help_text="Speed in km/h"
    )

    heading = models.FloatField(
        null=True,
        blank=True,
        help_text="Direction of travel in degrees"
    )

    accuracy = models.FloatField(
        null=True,
        blank=True,
        help_text="GPS accuracy in metres"
    )

    is_tracking = models.BooleanField(
        default=False
    )

    current_route_stop = models.ForeignKey(
        'routes.RouteStop',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='current_bus_locations'
    )

    stop_status = models.CharField(
        max_length=20,
        choices=[
            ('TRAVELLING', 'Travelling'),
            ('ARRIVED', 'Arrived'),
            ('DEPARTED', 'Departed'),
        ],
        default='TRAVELLING'
    )

    stop_arrived_at = models.DateTimeField(
        null=True,
        blank=True
    )

    stop_departed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    last_departure_stop = models.ForeignKey(
        'routes.RouteStop',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='last_departure_bus_locations'
    )

    last_departure_at = models.DateTimeField(
        null=True,
        blank=True
    )

    tracking_session_id = models.UUIDField(
        default=uuid.uuid4,
        editable=False
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return (
            f"{self.bus.bus_number} - "
            f"{self.latitude}, {self.longitude}"
        )

class BusStopVisit(models.Model):

    bus = models.ForeignKey(
        Bus,
        on_delete=models.CASCADE,
        related_name='stop_visits'
    )

    route = models.ForeignKey(
        'routes.Route',
        on_delete=models.CASCADE,
        related_name='bus_stop_visits'
    )

    route_stop = models.ForeignKey(
        'routes.RouteStop',
        on_delete=models.CASCADE,
        related_name='bus_visits'
    )

    tracking_session_id = models.UUIDField(
        default=uuid.uuid4,
        editable=False
    )

    arrival_time = models.DateTimeField(
        null=True,
        blank=True
    )

    departure_time = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ['-arrival_time']

        indexes = [
            models.Index(
                fields=[
                    'bus',
                    'route',
                    'tracking_session_id'
                ]
            ),
        ]

    def __str__(self):
        return (
            f"{self.bus.bus_number} - "
            f"{self.route_stop.stop.name}"
        )