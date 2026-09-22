"""
URL configuration for brf project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import path
from . import views

app_name = 'routes'
urlpatterns = [
    # Public route pages
    path('', views.routes_list, name='routes'),
    path('search/', views.route_search, name='route_search'),
    path('stops/', views.stops_list, name='stops'),
    path('stops/<int:stop_id>/', views.stop_detail, name='stop_detail'),
    path( '<int:route_id>/', views.route_detail, name='route_detail' ),
    path('search/', views.route_search, name='route_search'),

    # Route Management
    path('management/', views.route_management, name='route_management'),
    path('management/add/', views.route_create, name='route_create'),
    path('management/<int:route_id>/edit/', views.route_edit, name='route_edit'),
    path('management/<int:route_id>/delete/', views.route_delete, name='route_delete'),

    path('management/<int:route_id>/stops/', views.manage_route_stops, name='manage_route_stops'),
    path('management/<int:route_id>/stops/add/', views.add_route_stop, name='add_route_stop'),
    path('management/<int:route_id>/stops/<int:route_stop_id>/edit/', views.edit_route_stop, name='edit_route_stop'),
    path('management/<int:route_id>/stops/<int:route_stop_id>/delete/', views.delete_route_stop, name='delete_route_stop'),
    path('management/<int:route_id>/stops/<int:route_stop_id>/up/', views.move_route_stop_up, name='move_route_stop_up'),
    path('management/<int:route_id>/stops/<int:route_stop_id>/down/', views.move_route_stop_down, name='move_route_stop_down'),

    # Schedule Management

    path('management/schedules/', views.schedule_management, name='schedule_management'),
    path('management/schedules/add/', views.schedule_create, name='schedule_create'),
    path('management/schedules/<int:schedule_id>/edit/', views.schedule_edit, name='schedule_edit'),
    path('management/schedules/<int:schedule_id>/delete/', views.schedule_delete, name='schedule_delete'),
]
