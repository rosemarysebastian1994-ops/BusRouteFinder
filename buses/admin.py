from django.contrib import admin

# Register your models here.

from .models import Bus, BusLocation, Notification, Ticket, Payment
from django.contrib.auth.models import User

@admin.register(Bus)
class BusAdmin(admin.ModelAdmin):

    list_display = (
        'bus_name',
        'id',
        'bus_number',
        'bus_type',
        'operator',
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

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):

    list_display = (
        'ticket_number',
        'passenger',
        'schedule',
        'source_stop',
        'destination_stop',
        'journey_date',
        'passenger_count',
        'total_amount',
        'status',
        'created_at',
    )

    list_filter = (
        'status',
        'journey_date',
        'schedule__day',
    )

    search_fields = (
        'ticket_number',
        'passenger__username',
        'passenger__first_name',
        'passenger__last_name',
        'source_stop__stop__name',
        'destination_stop__stop__name',
    )

    readonly_fields = (
        'ticket_number',
        'total_amount',
        'created_at',
        'updated_at',
    )

    ordering = (
        '-created_at',
    )

    def formfield_for_foreignkey(
        self,
        db_field,
        request,
        **kwargs
    ):

        if db_field.name == 'passenger':

            kwargs['queryset'] = (
                User.objects
                .filter(
                    groups__name='Passengers'
                )
                .distinct()
                .order_by('username')
            )

        return super().formfield_for_foreignkey(
            db_field,
            request,
            **kwargs
        )

    class Media:
        js = (
            'buses/js/ticket_admin.js',
        )

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):

    list_display = (
        'razorpay_order_id',
        'passenger',
        'ticket',
        'amount',
        'currency',
        'status',
        'created_at',
    )

    list_filter = (
        'status',
        'currency',
        'created_at',
    )

    search_fields = (
        'razorpay_order_id',
        'razorpay_payment_id',
        'passenger__username',
        'passenger__first_name',
        'passenger__last_name',
        'ticket__ticket_number',
    )

    readonly_fields = (
        'razorpay_order_id',
        'razorpay_payment_id',
        'razorpay_signature',
        'created_at',
        'updated_at',
    )

    ordering = (
        '-created_at',
    )

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):

    list_display = (
        'passenger',
        'notification_type',
        'title',
        'is_read',
        'created_at',
    )

    list_filter = (
        'notification_type',
        'is_read',
        'created_at',
    )

    search_fields = (
        'passenger__username',
        'title',
        'message',
    )

    readonly_fields = (
        'created_at',
    )

    ordering = (
        '-created_at',
    )