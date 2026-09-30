from django.db import models
from django.contrib.auth.models import User
import uuid

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError

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

class Ticket(models.Model):

    STATUS_CHOICES = [
        ('PAYMENT_PENDING', 'Payment Pending'),
        ('CONFIRMED', 'Confirmed'),
        ('CANCELLED', 'Cancelled'),
        ('COMPLETED', 'Completed'),
    ]

    ticket_number = models.CharField(
        max_length=20,
        unique=True,
        editable=False
    )

    passenger = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tickets'
    )

    schedule = models.ForeignKey(
        'routes.BusSchedule',
        on_delete=models.PROTECT,
        related_name='tickets'
    )

    source_stop = models.ForeignKey(
        'routes.RouteStop',
        on_delete=models.PROTECT,
        related_name='tickets_from'
    )

    destination_stop = models.ForeignKey(
        'routes.RouteStop',
        on_delete=models.PROTECT,
        related_name='tickets_to'
    )

    journey_date = models.DateField()

    passenger_count = models.PositiveSmallIntegerField(
        default=1
    )

    fare_per_passenger = models.DecimalField(
        max_digits=8,
        decimal_places=2
    )

    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PAYMENT_PENDING'
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ['-created_at']

    def clean(self):

        if (
            self.source_stop.route_id
            != self.destination_stop.route_id
        ):
            raise ValidationError(
                'Source and destination must belong '
                'to the same route.'
            )

        if (
            self.source_stop.stop_order
            >= self.destination_stop.stop_order
        ):
            raise ValidationError(
                'Destination stop must come after '
                'the source stop.'
            )

        if (
            self.schedule.route_id
            != self.source_stop.route_id
        ):
            raise ValidationError(
                'Selected stops must belong to '
                'the scheduled route.'
            )

        if self.passenger_count < 1:
            raise ValidationError(
                'Passenger count must be at least 1.'
            )

    def save(self, *args, **kwargs):

        if not self.ticket_number:
            self.ticket_number = (
                f"BRF-{uuid.uuid4().hex[:10].upper()}"
            )

        self.total_amount = (
            self.fare_per_passenger
            * Decimal(self.passenger_count)
        )

        super().save(*args, **kwargs)

    def __str__(self):
        return self.ticket_number

class Payment(models.Model):

    STATUS_CHOICES = [
        ('CREATED', 'Created'),
        ('PAID', 'Paid'),
        ('FAILED', 'Failed'),
        ('REFUNDED', 'Refunded'),
    ]

    ticket = models.OneToOneField(
        Ticket,
        on_delete=models.PROTECT,
        related_name='payment',
        null=True,
        blank=True,
    )

    passenger = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='payments',
    )

    razorpay_order_id = models.CharField(
        max_length=100,
        unique=True,
    )

    razorpay_payment_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    razorpay_refund_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    razorpay_signature = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    failure_reason = models.TextField(
        blank=True,
        null=True,
    )

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    currency = models.CharField(
        max_length=3,
        default='INR',
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='CREATED',
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return self.razorpay_order_id
