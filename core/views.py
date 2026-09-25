from django.shortcuts import render
from buses.models import Bus

# Create your views here.

def home(request):

    buses = (
        Bus.objects
        .all()
        .order_by('bus_number')
    )

    return render(
        request,
        'core/home.html',
        {
            'buses': buses,
        }
    )

def about(request):
    return render(request, 'core/about.html')

def contact(request):
    return render(request, 'core/contact.html')