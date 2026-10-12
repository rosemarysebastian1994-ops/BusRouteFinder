from django.urls import path
from . import views

urlpatterns = [
    path('', views.bus_list_api, name='bus_list_api'),
]