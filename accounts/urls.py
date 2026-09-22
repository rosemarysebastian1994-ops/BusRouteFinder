from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    path('profile/', views.profile, name='profile'),
    path('favourites/', views.favourites, name='favourites'),
    path('favourites/route/<int:route_id>/', views.toggle_favourite_route, name='toggle_favourite_route'),
    path('favourites/stop/<int:stop_id>/', views.toggle_favourite_stop, name='toggle_favourite_stop'),
]