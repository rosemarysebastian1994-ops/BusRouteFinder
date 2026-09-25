from django.urls import path
from . import views

app_name = 'buses'

urlpatterns = [
    path(
        'driver/tracking/',
        views.driver_tracking,
        name='driver_tracking'
    ),

    path(
        'driver/update-location/',
        views.update_bus_location,
        name='update_bus_location'
    ),

    path(
        'driver/stop-tracking/',
        views.stop_bus_tracking,
        name='stop_bus_tracking'
    ),

    path(
        'driver/set-route/',
        views.set_bus_route,
        name='set_bus_route'
    ),

    path(
        'live/',
        views.live_buses,
        name='live_buses'
    ),

    path(
        'live/locations/',
        views.live_bus_locations,
        name='live_bus_locations'
    ),

    path(
        '<int:bus_id>/',
        views.bus_detail,
        name='bus_detail'
    ),

    path(
        '<int:bus_id>/timings/',
        views.bus_timings,
        name='bus_timings'
    ),
]