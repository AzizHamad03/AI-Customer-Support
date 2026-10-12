from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

from support.services.tickets import dashboard_summary


def home(request):
    return render(request, "support/home.html")


@staff_member_required
def staff_dashboard(request):
    return render(
        request,
        "support/staff.html",
        {"summary": dashboard_summary()},
    )