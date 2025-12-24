import calendar
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from invoice.models import SystemSetting
from invoice.services import bulk_ensure_work_for_month


class Command(BaseCommand):
    help = "Generate work records for the next month when auto mode is enabled."

    def add_arguments(self, parser):
        parser.add_argument(
            "--auto",
            action="store_true",
            help="Run in auto mode with trigger day check.",
        )

    def handle(self, *args, **options):
        if options.get("auto"):
            setting = SystemSetting.objects.first()
            if not setting or not setting.auto_generation_enabled:
                self.stdout.write("Auto generation disabled.")
                return

            today = timezone.localdate()
            last_day = calendar.monthrange(today.year, today.month)[1]
            trigger_day = today.replace(day=last_day) - timedelta(days=6)
            if today != trigger_day:
                self.stdout.write("Not trigger day.")
                return

        today = timezone.localdate()
        next_year = today.year + 1 if today.month == 12 else today.year
        next_month = 1 if today.month == 12 else today.month + 1

        created, existed, steps_created = bulk_ensure_work_for_month(
            next_year, next_month
        )
        self.stdout.write(
            "Created {}, existed {}, steps created {}.".format(
                created, existed, steps_created
            )
        )
