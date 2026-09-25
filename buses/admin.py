from django.contrib import admin

# Register your models here.

from .models import Bus, BusLocation

@admin.register(Bus)
class BusAdmin(admin.ModelAdmin):

    list_display = (
        'bus_name',
        'id',
        'bus_number',
        'bus_type',
        'operator',
        'fare',
        'driver',
        'current_route',
    )

    list_display_links = (
        'bus_name',
    )

    list_filter = (
        'bus_type',
        'operator',
    )

    search_fields = (
        'bus_number',
        'bus_name',
        'operator',
    )

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