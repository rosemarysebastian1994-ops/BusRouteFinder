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

    path(
        'ajax/schedule-stops/',
        views.schedule_stops,
        name='schedule_stops'
    ),

    path(
        'book/',
        views.book_ticket,
        name='book_ticket'
    ),

    path(
        'calculate-booking-fare/',
        views.calculate_booking_fare,
        name='calculate_booking_fare'
    ),

    path(
        'book/schedule-stops/',
        views.booking_schedule_stops,
        name='booking_schedule_stops'
    ),

    path(
        'payment/verify/',
        views.verify_payment,
        name='verify_payment'
    ),

    path(
        'payment/failure/',
        views.payment_failure,
        name='payment_failure'
    ),

    path(
        'tickets/',
        views.my_tickets,
        name='my_tickets'
    ),

    path(
        'tickets/<int:ticket_id>/payment/',
        views.ticket_payment,
        name='ticket_payment'
    ),

    path(
        'tickets/<int:ticket_id>/',
        views.ticket_detail,
        name='ticket_detail'
    ),

    path(
        'tickets/<int:ticket_id>/cancel/',
        views.cancel_ticket,
        name='cancel_ticket'
    ),

    path(
        'tickets/<int:ticket_id>/download/',
        views.download_ticket,
        name='download_ticket'
    ),
]