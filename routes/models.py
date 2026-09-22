from django.db import models

# Create your models here.
from django.db import models
from buses.models import Bus

class Route(models.Model):
    bus = models.ForeignKey(
        Bus,
        on_delete=models.CASCADE,
        related_name='routes'
    )

    route_name = models.CharField(
        max_length=150
    )

    description = models.TextField(
        blank=True
    )

    duration_minutes = models.PositiveIntegerField(
        default=60,
        help_text="Estimated journey duration in minutes"
    )

    @property
    def duration_display(self):
        hours = self.duration_minutes // 60

        minutes = self.duration_minutes % 60
        if hours and minutes:
            return f"{hours} hr {minutes} min"
        if hours:
            return f"{hours} hr"
        return f"{minutes} min"

    def __str__(self):
        return self.route_name


class Stop(models.Model):
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=200, blank=True)

    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True
    )

    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True
    )

    def __str__(self):
        return self.name


class RouteStop(models.Model):
    route = models.ForeignKey(
        Route,
        on_delete=models.CASCADE,
        related_name='route_stops'
    )

    stop = models.ForeignKey(
        Stop,
        on_delete=models.CASCADE,
        related_name='route_stops'
    )

    stop_order = models.PositiveIntegerField()

    travel_time_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Travel time from the previous stop in minutes"
    )

    class Meta:
        ordering = ['stop_order']
        unique_together = ['route', 'stop']
        constraints = [
            models.UniqueConstraint(
                fields=['route', 'stop_order'],
                name='unique_route_stop_order'
            )
        ]

    def __str__(self):
        return f"{self.route} - {self.stop} ({self.stop_order})"

class BusSchedule(models.Model):

    DAY_CHOICES = [
        ('MON', 'Monday'),
        ('TUE', 'Tuesday'),
        ('WED', 'Wednesday'),
        ('THU', 'Thursday'),
        ('FRI', 'Friday'),
        ('SAT', 'Saturday'),
        ('SUN', 'Sunday'),
    ]

    route = models.ForeignKey(
        Route,
        on_delete=models.CASCADE,
        related_name='schedules'
    )

    day = models.CharField(
        max_length=3,
        choices=DAY_CHOICES
    )

    day_order = models.PositiveSmallIntegerField(
        default=1,
        editable=False
    )

    departure_time = models.TimeField()

    arrival_time = models.TimeField(
        blank=True,
        null=True
    )

    is_active = models.BooleanField(
        default=True
    )

    class Meta:
        ordering = [
            'day_order',
            'departure_time'
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    'route',
                    'day',
                    'departure_time'
                ],
                name='unique_route_day_departure'
            )
        ]

    def save(self, *args, **kwargs):

        day_order_map = {
            'MON': 1,
            'TUE': 2,
            'WED': 3,
            'THU': 4,
            'FRI': 5,
            'SAT': 6,
            'SUN': 7,
        }

        self.day_order = day_order_map.get(
            self.day,
            1
        )

        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.route.route_name} - "
            f"{self.get_day_display()} "
            f"{self.departure_time}"
        )