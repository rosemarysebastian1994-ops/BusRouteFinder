from django.urls import path, reverse_lazy
from . import views
from django.contrib.auth import views as auth_views

from django.contrib.auth.views import (
    PasswordChangeView,
    PasswordChangeDoneView,
)

app_name = 'accounts'

urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    path('profile/', views.profile, name='profile'),
    path('favourites/', views.favourites, name='favourites'),
    path('favourites/route/<int:route_id>/', views.toggle_favourite_route, name='toggle_favourite_route'),
    path('favourites/stop/<int:stop_id>/', views.toggle_favourite_stop, name='toggle_favourite_stop'),

    # Forgot Password
    path(
        'password-reset/',
        auth_views.PasswordResetView.as_view(
            template_name='accounts/password_reset_form.html',
            email_template_name='accounts/password_reset_email.html',
            subject_template_name='accounts/password_reset_subject.txt',
            success_url=reverse_lazy(
                'accounts:password_reset_done'
            ),
        ),
        name='password_reset',
    ),

    path(
        'password-reset/done/',
        auth_views.PasswordResetDoneView.as_view(
            template_name='accounts/password_reset_done.html',
        ),
        name='password_reset_done',
    ),

    path(
        'reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(
            template_name='accounts/password_reset_confirm.html',
            success_url=reverse_lazy(
                'accounts:password_reset_complete'
            ),
        ),
        name='password_reset_confirm',
    ),

    path(
        'reset/done/',
        auth_views.PasswordResetCompleteView.as_view(
            template_name='accounts/password_reset_complete.html',
        ),
        name='password_reset_complete',
    ),

    path(
        'change-password/',
        PasswordChangeView.as_view(
            template_name='accounts/change_password.html',
            success_url=reverse_lazy(
                'accounts:password_change_done'
            ),
        ),
        name='password_change',
    ),

    path(
        'change-password/done/',
        PasswordChangeDoneView.as_view(
            template_name='accounts/change_password_done.html',
        ),
        name='password_change_done',
    ),
]