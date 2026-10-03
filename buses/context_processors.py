from .models import Notification


def notification_count(request):

    unread_notification_count = 0

    if request.user.is_authenticated:

        if request.user.groups.filter(
            name='Passengers'
        ).exists():

            unread_notification_count = (
                Notification.objects
                .filter(
                    passenger=request.user,
                    is_read=False
                )
                .count()
            )

    return {
        'unread_notification_count':
            unread_notification_count
    }