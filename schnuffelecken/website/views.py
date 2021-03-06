from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, reverse, render_to_response
from django.template import RequestContext
from django.db import transaction, IntegrityError

from datetime import datetime

from website.viewmodels import *
from website.models import BookingPeriod, Booking
from schnuffelecken.settings import STATUS_PAGE_REFRESH_RATE_IN_SECONDS, URL


def index(request):
    """Redirect to proper page if base URL is requested."""
    if request.user.is_authenticated:
        return redirect(reverse('bookings', kwargs={'facility': 'g'}))
    else:
        return redirect(reverse('login'))


def login(request):
    """View for login page."""
    if request.user.is_authenticated:
        return redirect(reverse('bookings', kwargs={'facility': 'g'}))

    if request.POST:
        username = request.POST["username"]
        password = request.POST["password"]

        if not is_allowed(username):
            return HttpResponseForbidden(render(request, 'website/login.html', context={'error': 'Aktuell nur für Studenten'}))

        user = authenticate(username=username, password=password)

        if user is not None:
            auth_login(request, user)
            return redirect('/buchungen/g/')
        else:
            return HttpResponseForbidden(render(request, 'website/login.html', context={'error': 'Konto nicht gefunden'}))

    return HttpResponse(render(request, 'website/login.html'))


def is_allowed(username):
    """
    Until some legal concerns are clarified, staff should not be able to
    log in. If the username starts with a digit, the user
    is identified as student.
    """
    is_student = username[0].isdigit()

    return settings.STAFF_ACCESS or is_student


def handle_booking(request, facility):
    """Handle a booking request"""
    date = datetime.fromtimestamp(float(request.POST["book"]))
    booking = Booking(date=date, user=request.user.username, facility=facility)

    if booking.lies_in_past():
        return NotAllowedAlert()

    try:
        with transaction.atomic():
            booking.save()

    except IntegrityError:
        return NotAllowedAlert()

    except ValidationError as error:
        if "quota" in error.message_dict:
            return QuotaExceededAlert()
        else:
            return NotAllowedAlert()

    return BookingSuccessfulAlert(date)


def handle_cancellation(request, facility):
    """Handle a cancellation request"""
    date = datetime.fromtimestamp(float(request.POST["cancel"]))
    username = request.user.username
    booking = Booking.objects.filter(
        date=date, user=username, facility=facility).first()

    if not booking or booking.lies_in_past():
        return CancellationNotAllowedAlert()

    with transaction.atomic():
        booking.delete()

    return CancellationAlert(date)


@login_required(login_url='/login/')
def bookings(request, facility):
    """View for display of bookings as well as booking and cancel actions.
    """
    info = AllOk()

    if request.POST and "cancel" in request.POST:
        info = handle_cancellation(request, facility)
    elif request.POST and "book" in request.POST:
        info = handle_booking(request, facility)

    quota = Booking.get_user_quota(request.user.username)

    booking_period = BookingPeriod(datetime.now())
    weeks = [WeekViewModel(week, facility, request.user)
             for week in booking_period.weeks]

    context = {
        'username': request.user,
        'bookings': weeks,
        'quota': quota,
        'info': info,
        'display_first_week': not request.POST,
        'is_g': facility == "g",
    }

    response = HttpResponse(
        render(request, 'website/bookings.html', context=context))
    response.status_code = info.status_code

    return response


def logout(request):
    """View for logout requests.
    This just redirects and renders nothing itself.
    """
    auth_logout(request)
    return redirect(reverse('login') + '#logout-success')


def handler404(request):
    """View for customized 404 website"""
    response = render_to_response(
        'website/404.html', {}, context_instance=RequestContext(request))
    response.status_code = 404
    return response


def status(request, facility):
    """View for status website"""
    week = WeekViewModel(BookingPeriod(datetime.now()).weeks[
                         0], facility, request.user)

    context = {
        "week": week,
        "facility": facility.upper(),
        "refresh_rate": STATUS_PAGE_REFRESH_RATE_IN_SECONDS,
        "url": URL}

    return HttpResponse(render(request, 'website/status.html', context))
