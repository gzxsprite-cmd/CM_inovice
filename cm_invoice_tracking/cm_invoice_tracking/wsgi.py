import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cm_invoice_tracking.settings")

application = get_wsgi_application()
