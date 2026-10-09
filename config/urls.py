from django.contrib import admin
from django.urls import include, path
from studio.discovery import sitemap, robots
from studio.csrf import token

urlpatterns = [path("csrf-token/", token, name="csrf-token"), path("sitemap.xml", sitemap, name="sitemap"), path("robots.txt", robots, name="robots"), path("admin/", admin.site.urls), path("", include("studio.urls"))]
admin.site.site_header = "Venastella studio"
admin.site.site_title = "Venastella"
