from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    class Scnx(models.TextChoices):
        SCN1 = "SCN1", "SCN1"
        SCN2 = "SCN2", "SCN2"

    class Role(models.TextChoices):
        CM = "CM", "CM"
        LCM = "LCM", "LCM"
        HOD = "HOD", "HoD"

    english_name = models.CharField(max_length=150, blank=True)
    scnx = models.CharField(max_length=10, choices=Scnx.choices, blank=True, null=True)
    role = models.CharField(max_length=10, choices=Role.choices, blank=True, null=True)

    def __str__(self):
        return self.username


class Customer(models.Model):
    class Region(models.TextChoices):
        CCN1 = "CCN1", "CCN1"
        CCN2 = "CCN2", "CCN2"
        CCN3 = "CCN3", "CCN3"
        CCN4 = "CCN4", "CCN4"

    ile = models.CharField(max_length=100)
    round_location = models.CharField(max_length=100)
    region = models.CharField(max_length=10, choices=Region.choices, blank=True, null=True)
    responsible_cm = models.ForeignKey(
        User,
        related_name="customers_as_cm",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    responsible_lcm = models.ForeignKey(
        User,
        related_name="customers_as_lcm",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["ile", "round_location"], name="unique_customer")
        ]

    def __str__(self):
        return "{} / {}".format(self.ile, self.round_location)


class CustomerStepRule(models.Model):
    class RuleType(models.TextChoices):
        NO_RULE = "NO_RULE", "No Rule"
        THIS_MONTH_DAY = "THIS_MONTH_DAY", "This Month Day"
        NEXT_MONTH_DAY = "NEXT_MONTH_DAY", "Next Month Day"
        THIS_MONTH_NTH_WEEKDAY = "THIS_MONTH_NTH_WEEKDAY", "This Month Nth Weekday"
        THIS_MONTH_LAST_NTH_DAY = "THIS_MONTH_LAST_NTH_DAY", "This Month Last Nth Day"

    STEP_CHOICES = [(1, "Step 1"), (2, "Step 2"), (3, "Step 3"), (4, "Step 4")]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    step_no = models.IntegerField(choices=STEP_CHOICES)
    rule_type = models.CharField(max_length=40, choices=RuleType.choices)
    day_of_month = models.IntegerField(
        blank=True,
        null=True,
        help_text="For THIS_MONTH_DAY / NEXT_MONTH_DAY: set day 1-31.",
    )
    nth = models.IntegerField(
        blank=True,
        null=True,
        help_text="For THIS_MONTH_NTH_WEEKDAY: set nth (1-5).",
    )
    weekday = models.IntegerField(
        blank=True,
        null=True,
        help_text="For THIS_MONTH_NTH_WEEKDAY: set weekday 0-6 (0=Mon).",
    )
    last_nth = models.IntegerField(
        blank=True,
        null=True,
        help_text="For THIS_MONTH_LAST_NTH_DAY: set last_nth (1=last day).",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "step_no"], name="unique_customer_step_rule"
            )
        ]

    def clean(self):
        errors = {}
        if self.rule_type == self.RuleType.NO_RULE:
            return
        if self.rule_type in [self.RuleType.THIS_MONTH_DAY, self.RuleType.NEXT_MONTH_DAY]:
            if self.day_of_month is None:
                errors["day_of_month"] = "day_of_month is required."
            elif not 1 <= self.day_of_month <= 31:
                errors["day_of_month"] = "day_of_month must be between 1 and 31."
        if self.rule_type == self.RuleType.THIS_MONTH_NTH_WEEKDAY:
            if self.nth is None:
                errors["nth"] = "nth is required."
            elif not 1 <= self.nth <= 5:
                errors["nth"] = "nth must be between 1 and 5."
            if self.weekday is None:
                errors["weekday"] = "weekday is required."
            elif not 0 <= self.weekday <= 6:
                errors["weekday"] = "weekday must be between 0 and 6."
        if self.rule_type == self.RuleType.THIS_MONTH_LAST_NTH_DAY:
            if self.last_nth is None:
                errors["last_nth"] = "last_nth is required."
            elif not 1 <= self.last_nth <= 31:
                errors["last_nth"] = "last_nth must be between 1 and 31."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return "{} Step {}".format(self.customer, self.step_no)


class Work(models.Model):
    class BNReleaseStatus(models.TextChoices):
        OPEN = "OPEN", "Open"
        FULL = "FULL", "Full"
        PARTIAL = "PARTIAL", "Partial"
        NONE = "NONE", "None"

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    work_month = models.CharField(max_length=7)
    bn_release_status = models.CharField(
        max_length=20, choices=BNReleaseStatus.choices, default=BNReleaseStatus.OPEN
    )
    comment = models.TextField(blank=True)
    customer_region = models.CharField(max_length=10, blank=True, null=True)
    assigned_cm = models.ForeignKey(
        User,
        related_name="assigned_cm_works",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    assigned_lcm = models.ForeignKey(
        User,
        related_name="assigned_lcm_works",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    assigned_lcm_scnx = models.CharField(max_length=10, blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "work_month"],
                name="uniq_work_customer_month",
            )
        ]

    def __str__(self):
        return "{} {}".format(self.customer, self.work_month)

    def save(self, *args, **kwargs):
        if self.customer_id:
            self.customer_region = self.customer.region
            self.assigned_cm = self.customer.responsible_cm
            self.assigned_lcm = self.customer.responsible_lcm
            self.assigned_lcm_scnx = getattr(self.assigned_lcm, "scnx", None)
        super().save(*args, **kwargs)
        from invoice.services import ensure_steps_for_work

        ensure_steps_for_work(self)


class WorkStep(models.Model):
    class StepStatus(models.TextChoices):
        OPEN = "OPEN", "Open"
        CLOSED = "CLOSED", "Closed"

    STEP_CHOICES = [(1, "Step 1"), (2, "Step 2"), (3, "Step 3"), (4, "Step 4")]

    work = models.ForeignKey(Work, on_delete=models.CASCADE)
    step_no = models.IntegerField(choices=STEP_CHOICES)
    planned_due_date = models.DateField(blank=True, null=True)
    actual_closed_date = models.DateField(blank=True, null=True)
    step_status = models.CharField(
        max_length=10, choices=StepStatus.choices, default=StepStatus.OPEN
    )
    step_comment = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["work", "step_no"], name="unique_work_step")
        ]

    def save(self, *args, **kwargs):
        if self.step_status == self.StepStatus.CLOSED and self.actual_closed_date is None:
            self.actual_closed_date = timezone.localdate()
        super().save(*args, **kwargs)

    def __str__(self):
        return "{} Step {}".format(self.work, self.step_no)


class SystemSetting(models.Model):
    auto_generation_enabled = models.BooleanField(default=False)

    def __str__(self):
        return "System Settings"
