from django.urls import path

from invoice.admin import admin_site

urlpatterns = [
    path("admin/", admin_site.urls),
]
