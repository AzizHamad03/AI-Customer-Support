from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Customer Support Administration"
admin.site.site_title = "Support Administration"
urlpatterns = [path("admin/", admin.site.urls), path("", include("support.urls"))]
