from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import Group

from .forms import RegisterForm, UserProfileForm, ProfileForm
from .models import Profile, FavouriteRoute, FavouriteStop
from routes.models import Route, Stop


def register(request):

    if request.user.is_authenticated:
        return redirect('core:home')

    if request.method == 'POST':

        form = RegisterForm(request.POST)

        if form.is_valid():

            user = form.save()

            role = form.cleaned_data['role']

            if role == 'driver':

                group, created = Group.objects.get_or_create(
                    name='Drivers'
                )

            else:

                group, created = Group.objects.get_or_create(
                    name='Passengers'
                )

            user.groups.add(group)

            login(request, user)

            messages.success(
                request,
                'Your account has been created successfully.'
            )

            return redirect('core:home')

    else:
        form = RegisterForm()

    return render(
        request,
        'accounts/register.html',
        {'form': form}
    )


def user_login(request):

    if request.user.is_authenticated:
        return redirect('core:home')

    if request.method == 'POST':

        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is not None:

            login(request, user)

            messages.success(
                request,
                f'Welcome back, {user.first_name or user.username}!'
            )

            return redirect('core:home')

        messages.error(
            request,
            'Invalid username or password.'
        )

    return render(
        request,
        'accounts/login.html'
    )


@login_required
def user_logout(request):

    logout(request)

    messages.success(
        request,
        'You have been logged out successfully.'
    )

    return redirect('core:home')

@login_required
def profile(request):
    profile, created = Profile.objects.get_or_create(
        user=request.user
    )

    if request.method == 'POST':
        user_form = UserProfileForm(
            request.POST,
            instance=request.user
        )

        profile_form = ProfileForm(
            request.POST,
            request.FILES,
            instance=profile
        )

        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()

            messages.success(
                request,
                'Your profile has been updated successfully.'
            )

            return redirect('accounts:profile')

    else:
        user_form = UserProfileForm(
            instance=request.user
        )

        profile_form = ProfileForm(
            instance=profile
        )

    return render(
        request,
        'accounts/profile.html',
        {
            'user_form': user_form,
            'profile_form': profile_form,
            'profile': profile,
        }
    )

@login_required
def toggle_favourite_route(request, route_id):

    if request.method != 'POST':
        return redirect('routes:routes')

    route = get_object_or_404(
        Route,
        id=route_id
    )

    favourite = FavouriteRoute.objects.filter(
        user=request.user,
        route=route
    ).first()

    if favourite:
        favourite.delete()
    else:
        FavouriteRoute.objects.create(
            user=request.user,
            route=route
        )

    return redirect(
        request.META.get(
            'HTTP_REFERER',
            '/routes/'
        )
    )

@login_required
def toggle_favourite_stop(request, stop_id):

    if request.method != 'POST':
        return redirect('routes:stops')

    stop = get_object_or_404(
        Stop,
        id=stop_id
    )

    favourite = FavouriteStop.objects.filter(
        user=request.user,
        stop=stop
    ).first()

    if favourite:
        favourite.delete()
    else:
        FavouriteStop.objects.create(
            user=request.user,
            stop=stop
        )

    return redirect(
        request.META.get(
            'HTTP_REFERER',
            '/routes/stops/'
        )
    )

@login_required
def favourites(request):

    favourite_routes = (
        FavouriteRoute.objects
        .filter(user=request.user)
        .select_related(
            'route',
            'route__bus'
        )
    )

    favourite_stops = (
        FavouriteStop.objects
        .filter(user=request.user)
        .select_related(
            'stop'
        )
    )

    return render(
        request,
        'accounts/favourites.html',
        {
            'favourite_routes': favourite_routes,
            'favourite_stops': favourite_stops,
        }
    )