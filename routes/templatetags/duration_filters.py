from django import template

register = template.Library()


@register.filter
def minutes_to_hours(minutes):
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        return "0 hours 0 minutes"

    hours = minutes // 60
    remaining_minutes = minutes % 60

    return f"{hours} hours {remaining_minutes} minutes"