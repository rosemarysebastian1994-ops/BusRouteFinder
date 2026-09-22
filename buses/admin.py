from django.contrib import admin

# Register your models here.

from .models import Bus, BusLocation

@admin.register(Bus)
class BusAdmin(admin.ModelAdmin):
    list_display = (
        'bus_number',
        'bus_name',
        'bus_type',
        'operator',
        'current_route',
    )

    list_filter = (
        'bus_type',
        'current_route',
    )

    search_fields = (
        'bus_number',
        'bus_name',
        'operator',
        'current_route__route_name',
    )

    ordering = ('bus_number',)

@admin.register(BusLocation)
class BusLocationAdmin(admin.ModelAdmin):

    list_display = (
        'bus',
        'latitude',
        'longitude',
        'speed',
        'accuracy',
        'updated_at',
    )

    list_filter = (
        'bus',
    )

    search_fields = (
        'bus__bus_number',
        'bus__bus_name',
    )

    readonly_fields = (
        'updated_at',
    )