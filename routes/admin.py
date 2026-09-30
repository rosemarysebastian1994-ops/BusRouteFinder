from django.contrib import admin

# Register your models here.

from .models import Route, Stop, RouteStop, BusSchedule, Fare

@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = (
        'route_name',
        'id',
        'bus',
    )

    list_filter = (
        'bus',
    )

    search_fields = (
        'route_name',
        'bus__bus_number',
        'bus__bus_name',
    )


@admin.register(Stop)
class StopAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'location',
    )

    search_fields = (
        'name',
        'location',
    )


@admin.register(RouteStop)
class RouteStopAdmin(admin.ModelAdmin):
    list_display = (
        'route',
        'stop',
        'stop_order',
        'distance_from_start_km',
        'travel_time_minutes',
    )

    list_filter = (
        'route',
    )

    search_fields = (
        'route__route_name',
        'stop__name',
    )

    ordering = (
        'route',
        'stop_order',
    )

@admin.register(BusSchedule)
class BusScheduleAdmin(admin.ModelAdmin):

    list_display = (
        'route',
        'day',
        'departure_time',
        'arrival_time',
        'is_active',
    )

    list_filter = (
        'day',
        'is_active',
        'route',
    )

    search_fields = (
        'route__route_name',
    )

    ordering = (
        'day_order',
        'departure_time',
    )

@admin.register(Fare)
class FareAdmin(admin.ModelAdmin):

    list_display = (
        'route',
        'min_distance_km',
        'max_distance_km',
        'amount',
        'is_active',
    )

    list_filter = (
        'route',
        'is_active',
    )

    search_fields = (
        'route__route_name',
    )

    ordering = (
        'route',
        'min_distance_km',
    )