from django.contrib import admin
from .models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):

    list_display = (
        'user',
        'phone',
        'location',
    )

    search_fields = (
        'user__username',
        'user__first_name',
        'user__last_name',
        'user__email',
    )

from .models import FavouriteRoute, FavouriteStop

@admin.register(FavouriteRoute)
class FavouriteRouteAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'route',
        'created_at',
    )

    list_filter = (
        'created_at',
    )

    search_fields = (
        'user__username',
        'route__route_name',
    )

@admin.register(FavouriteStop)
class FavouriteStopAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'stop',
        'created_at',
    )

    list_filter = (
        'created_at',
    )

    search_fields = (
        'user__username',
        'stop__name',
    )