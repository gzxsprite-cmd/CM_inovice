from datetime import timedelta
import calendar

from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import GroupAdmin, UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group
from django.db.models import Q
from django.template.response import TemplateResponse
from django.urls import reverse
from django.urls import path
from django.utils import timezone

from invoice.models import Customer
from invoice.models import CustomerStepRule
from invoice.models import SystemSetting
from invoice.models import STEP_LABELS
from invoice.models import User
from invoice.models import Work
from invoice.models import WorkStep
from invoice.services import bulk_ensure_work_for_month


class WorkStepForm(forms.ModelForm):
    class Meta:
        model = WorkStep
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("planned_due_date") is None:
            raise forms.ValidationError("planned_due_date is required.")
        return cleaned_data


class CustomerStepRuleInlineForm(forms.ModelForm):
    step_no = forms.ChoiceField(disabled=True, required=False, choices=CustomerStepRule.STEP_CHOICES)

    class Meta:
        model = CustomerStepRule
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        step_value = self.initial.get("step_no") or getattr(self.instance, "step_no", None)
        if step_value:
            self.fields["step_no"].label = STEP_LABELS.get(int(step_value), f"Step {step_value}")

    def clean_step_no(self):
        if self.instance and self.instance.pk:
            return self.instance.step_no
        initial_no = self.initial.get("step_no")
        if isinstance(initial_no, str) and initial_no.isdigit():
            return int(initial_no)
        return initial_no


class CustomerStepRuleInlineFormSet(forms.BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for index, form in enumerate(self.extra_forms, start=1):
            form.initial.setdefault("step_no", index)
            form.fields["step_no"].label = STEP_LABELS.get(index, f"Step {index}")


class WorkStepInline(admin.TabularInline):
    model = WorkStep
    form = WorkStepForm
    extra = 0

    def has_add_permission(self, request, obj=None):
        return False


class CustomerStepRuleInline(admin.TabularInline):
    model = CustomerStepRule
    form = CustomerStepRuleInlineForm
    formset = CustomerStepRuleInlineFormSet
    extra = 4
    max_num = 4
    can_delete = False
    ordering = ("step_no",)

    def get_extra(self, request, obj=None, **kwargs):
        if obj is None:
            return 4
        return 0


class LcmScnxFilter(admin.SimpleListFilter):
    title = "LCM SCNx"
    parameter_name = "lcm_scnx"

    def lookups(self, request, model_admin):
        return [
            (User.Scnx.SCN1, "SCN1"),
            (User.Scnx.SCN2, "SCN2"),
            ("__none__", "Empty"),
        ]

    def queryset(self, request, queryset):
        value = self.value()
        if value == "__none__":
            return queryset.filter(
                Q(responsible_lcm__scnx__isnull=True) | Q(responsible_lcm__scnx="")
            )
        if value in {User.Scnx.SCN1, User.Scnx.SCN2}:
            return queryset.filter(responsible_lcm__scnx=value)
        return queryset


class UserAdmin(DjangoUserAdmin):
    list_display = ("english_name", "role", "scnx")
    list_filter = ("english_name", "role", "scnx")
    search_fields = ("username", "english_name")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("CM Invoice", {"fields": ("english_name", "role", "scnx")}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("CM Invoice", {"fields": ("english_name", "role", "scnx")}),
    )


class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        "customer_label",
        "region",
        "responsible_cm",
        "responsible_lcm",
        "lcm_scnx",
        "rules_summary",
    )
    list_display_links = ("customer_label",)
    list_filter = ("ile", "region", "responsible_cm", "responsible_lcm", LcmScnxFilter)
    search_fields = ("ile", "round_location")
    readonly_fields = ("lcm_scnx",)
    fields = ("ile", "round_location", "region", "responsible_cm", "responsible_lcm", "lcm_scnx")
    inlines = [CustomerStepRuleInline]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name in {"responsible_cm", "responsible_lcm"}:
            kwargs["queryset"] = User.objects.order_by("english_name")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def customer_label(self, obj):
        return "{} / {}".format(obj.ile, obj.round_location)

    customer_label.short_description = "ILE / Round"

    def lcm_scnx(self, obj):
        if obj.responsible_lcm:
            return obj.responsible_lcm.scnx
        return ""

    lcm_scnx.short_description = "LCM SCNx"

    def rules_summary(self, obj):
        rules = CustomerStepRule.objects.filter(customer=obj).order_by("step_no")
        weekday_map = list(calendar.day_abbr)
        parts = []
        for rule in rules:
            if rule.rule_type == CustomerStepRule.RuleType.NO_RULE:
                label = "NoRule"
            elif rule.rule_type == CustomerStepRule.RuleType.THIS_MONTH_DAY:
                label = "ThisMonthDay({})".format(rule.day_of_month)
            elif rule.rule_type == CustomerStepRule.RuleType.NEXT_MONTH_DAY:
                label = "NextMonthDay({})".format(rule.day_of_month)
            elif rule.rule_type == CustomerStepRule.RuleType.THIS_MONTH_NTH_WEEKDAY:
                weekday_label = weekday_map[rule.weekday] if rule.weekday is not None else ""
                label = "NthWeekday({}, {})".format(rule.nth, weekday_label)
            elif rule.rule_type == CustomerStepRule.RuleType.THIS_MONTH_LAST_NTH_DAY:
                label = "LastNthDay({})".format(rule.last_nth)
            else:
                label = rule.rule_type
            step_label = CustomerStepRule.get_step_label(rule.step_no)
            parts.append("{}:{}".format(step_label, label))
        return ", ".join(parts)

    rules_summary.short_description = "Step Rules"

class CustomerStepRuleAdmin(admin.ModelAdmin):
    list_display = ("customer", "step_no", "rule_type")

    def has_view_permission(self, request, obj=None):
        return super().has_view_permission(request, obj=obj)

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser or request.user.role in [User.Role.LCM, User.Role.HOD]:
            return True
        return False

    def has_add_permission(self, request):
        if request.user.is_superuser or request.user.role in [User.Role.LCM, User.Role.HOD]:
            return True
        return False

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser or request.user.role in [User.Role.LCM, User.Role.HOD]:
            return True
        return False

class WorkAdmin(admin.ModelAdmin):
    list_display = (
        "customer",
        "work_period",
        "bn_release_status",
        "customer_region",
        "assigned_cm",
        "assigned_lcm",
        "assigned_lcm_scnx",
    )
    list_filter = (
        "customer",
        "work_year",
        "work_month",
        "customer_region",
        "assigned_cm",
        "assigned_lcm",
        "assigned_lcm_scnx",
        "bn_release_status",
    )
    search_fields = ("customer__ile", "customer__round_location")
    inlines = [WorkStepInline]
    readonly_fields = (
        "customer_region",
        "assigned_cm",
        "assigned_lcm",
        "assigned_lcm_scnx",
    )
    fields = (
        "customer",
        "work_year",
        "work_month",
        "bn_release_status",
        "comment",
    ) + readonly_fields

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return visible_works_for_user(queryset, request.user)

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser or request.user.role == User.Role.HOD:
            return True
        if request.user.role == User.Role.LCM:
            return True
        return False

    def work_period(self, obj):
        return "{}-{:02d}".format(obj.work_year, obj.work_month)

    work_period.short_description = "Work Period"

class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ("auto_generation_enabled",)


def visible_works_for_user(queryset, user):
    if user.is_superuser or user.role == User.Role.HOD:
        return queryset
    if user.role == User.Role.LCM:
        return queryset.filter(Q(assigned_lcm=user) | Q(assigned_cm=user))
    if user.role == User.Role.CM:
        return queryset.filter(assigned_cm=user)
    return queryset.none()


def overview_view(request, admin_site):
    today = timezone.localdate()
    visible_works = visible_works_for_user(
        Work.objects.select_related("customer", "assigned_cm", "assigned_lcm"),
        request.user,
    )

    overdue_steps = WorkStep.objects.filter(
        work__in=visible_works,
        step_status=WorkStep.StepStatus.OPEN,
        planned_due_date__lt=today,
    ).select_related("work", "work__customer")

    bn_issue_works = visible_works.exclude(bn_release_status=Work.BNReleaseStatus.FULL)

    exception_work_map = {}

    for work in bn_issue_works:
        exception_work_map[work.id] = {
            "work": work,
            "work_admin_url": reverse("admin:invoice_work_change", args=[work.id]),
            "customer_label": "{} / {}".format(
                work.customer.ile, work.customer.round_location
            ),
            "overdue_steps": [],
        }

    for step in overdue_steps:
        entry = exception_work_map.setdefault(
            step.work_id,
            {
                "work": step.work,
                "work_admin_url": reverse(
                    "admin:invoice_work_change", args=[step.work_id]
                ),
                "customer_label": "{} / {}".format(
                    step.work.customer.ile, step.work.customer.round_location
                ),
                "overdue_steps": [],
            },
        )
        entry["overdue_steps"].append(step)

    exception_works = list(exception_work_map.values())

    next_week = today + timedelta(days=7)
    upcoming_steps = WorkStep.objects.filter(
        work__in=visible_works,
        step_status=WorkStep.StepStatus.OPEN,
        planned_due_date__range=(today, next_week),
    ).select_related("work", "work__customer")
    upcoming_entries = [
        {
            "step": step,
            "work_admin_url": reverse("admin:invoice_work_change", args=[step.work_id]),
            "customer_label": "{} / {}".format(
                step.work.customer.ile, step.work.customer.round_location
            ),
        }
        for step in upcoming_steps
    ]

    if request.method == "POST":
        action = request.POST.get("action")
        if action in {"bulk_current", "bulk_next"}:
            target_year = today.year
            target_month = today.month
            if action == "bulk_next":
                if target_month == 12:
                    target_year += 1
                    target_month = 1
                else:
                    target_month += 1
            created, existed, steps_created = bulk_ensure_work_for_month(
                target_year, target_month
            )
            messages.success(
                request,
                "Bulk generation complete: created {}, existed {}, steps created {}.".format(
                    created, existed, steps_created
                ),
            )

    context = dict(
        admin_site.each_context(request),
        exception_works=exception_works,
        exception_count=len(exception_works),
        upcoming_entries=upcoming_entries,
    )
    return TemplateResponse(request, "admin/invoice/dashboard.html", context)

class InvoiceAdminSite(admin.AdminSite):
    site_header = "CM Invoice Tracking"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "invoice/overview/",
                self.admin_view(self.overview_view),
                name="invoice_dashboard",
            ),
            path(
                "invoice/dashboard/",
                self.admin_view(self.overview_view),
                name="invoice_dashboard_legacy",
            ),
            path(
                "admin-dashboard/",
                self.admin_view(self.admin_dashboard),
                name="admin_default_dashboard",
            ),
        ]
        return custom_urls + urls

    def overview_view(self, request):
        return overview_view(request, self)

    def index(self, request, extra_context=None):
        return overview_view(request, self)

    def admin_dashboard(self, request, extra_context=None):
        return super().index(request, extra_context)


admin_site = InvoiceAdminSite(name="invoice_admin")
admin_site.register(User, UserAdmin)
admin_site.register(Customer, CustomerAdmin)
admin_site.register(CustomerStepRule, CustomerStepRuleAdmin)
admin_site.register(Work, WorkAdmin)
admin_site.register(WorkStep)
admin_site.register(SystemSetting, SystemSettingAdmin)
admin_site.register(Group, GroupAdmin)
