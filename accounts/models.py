from django.db import models
from django.contrib.auth.models import User

class Profile(models.Model):

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )

    profile_picture = models.ImageField(
        upload_to='profile_pictures/',
        blank=True,
        null=True
    )

    phone = models.CharField(
        max_length=20,
        blank=True
    )

    location = models.CharField(
        max_length=150,
        blank=True
    )

    def __str__(self):
        return f"{self.user.username}'s Profile"

from routes.models import Route, Stop


class FavouriteRoute(models.Model):

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='favourite_routes'
    )

    route = models.ForeignKey(
        Route,
        on_delete=models.CASCADE,
        related_name='favourited_by'
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'route'],
                name='unique_user_favourite_route'
            )
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.route.route_name}"


class FavouriteStop(models.Model):

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='favourite_stops'
    )

    stop = models.ForeignKey(
        Stop,
        on_delete=models.CASCADE,
        related_name='favourited_by'
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'stop'],
                name='unique_user_favourite_stop'
            )
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.stop.name}"