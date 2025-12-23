from datetime import timedelta
import re

from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.db.models import Q
from django.template.response import TemplateResponse
from django.urls import path
from django.utils import timezone

from invoice.models import Customer
from invoice.models import CustomerStepRule
from invoice.models import SystemSetting
from invoice.models import User
from invoice.models import Work
from invoice.models import WorkStep
from invoice.services import bulk_ensure_work_for_month, format_work_month


class WorkStepForm(forms.ModelForm):
    class Meta:
        model = WorkStep
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("planned_due_date") is None:
            raise forms.ValidationError("planned_due_date is required.")
        return cleaned_data


class WorkAdminForm(forms.ModelForm):
    class Meta:
        model = Work
        fields = "__all__"

    def clean_work_month(self):
        value = self.cleaned_data.get("work_month", "")
        if value is None:
            raise forms.ValidationError("work_month must be in YYYY-MM format (e.g. 2025-12).")
        normalized = (
            value.strip()
            .replace("–", "-")
            .replace("—", "-")
            .replace("−", "-")
            .replace("/", "-")
        )
        if not re.match(r"^\\d{4}-(0[1-9]|1[0-2])$", normalized):
            raise forms.ValidationError("work_month must be in YYYY-MM format (e.g. 2025-12).")
        return normalized


class WorkStepInline(admin.TabularInline):
    model = WorkStep
    form = WorkStepForm
    extra = 0

    def has_add_permission(self, request, obj=None):
        return False


class CustomerStepRuleInline(admin.TabularInline):
    model = CustomerStepRule
    extra = 0
    max_num = 4
    can_delete = False
    ordering = ("step_no",)


class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "english_name", "role", "scnx")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("CM Invoice", {"fields": ("english_name", "role", "scnx")}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("CM Invoice", {"fields": ("english_name", "role", "scnx")}),
    )


class CustomerAdmin(admin.ModelAdmin):
    list_display = ("ile", "round_location", "region", "responsible_cm", "responsible_lcm")
    inlines = [CustomerStepRuleInline]

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser or request.user.role == User.Role.HOD:
            return queryset
        if request.user.role == User.Role.LCM:
            return queryset.filter(
                Q(responsible_cm=request.user) | Q(responsible_lcm=request.user)
            )
        return queryset.filter(responsible_cm=request.user)

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
    form = WorkAdminForm
    list_display = (
        "customer",
        "work_month",
        "bn_release_status",
        "assigned_cm",
        "assigned_lcm",
    )
    list_filter = ("bn_release_status", "customer_region", "work_month")
    search_fields = ("customer__ile", "customer__round_location")
    inlines = [WorkStepInline]
    readonly_fields = (
        "customer_region",
        "assigned_cm",
        "assigned_lcm",
        "assigned_lcm_scnx",
    )
    fields = ("customer", "work_month", "bn_release_status", "comment") + readonly_fields

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser or request.user.role == User.Role.HOD:
            return queryset
        if request.user.role == User.Role.LCM:
            return queryset.filter(
                Q(customer__responsible_cm=request.user)
                | Q(customer__responsible_lcm=request.user)
            )
        return queryset.filter(customer__responsible_cm=request.user)

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser or request.user.role == User.Role.HOD:
            return True
        if request.user.role == User.Role.LCM:
            return True
        return False

class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ("auto_generation_enabled",)


def _filter_work_queryset_for_user(queryset, user):
    if user.is_superuser or user.role == User.Role.HOD:
        return queryset
    if user.role == User.Role.LCM:
        return queryset.filter(
            Q(customer__responsible_cm=user) | Q(customer__responsible_lcm=user)
        )
    return queryset.filter(customer__responsible_cm=user)


def dashboard_view(request, admin_site):
    today = timezone.localdate()
    visible_works = _filter_work_queryset_for_user(
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
            "overdue_steps": [],
        }

    for step in overdue_steps:
        entry = exception_work_map.setdefault(
            step.work_id, {"work": step.work, "overdue_steps": []}
        )
        entry["overdue_steps"].append(step)

    exception_works = list(exception_work_map.values())

    next_week = today + timedelta(days=7)
    upcoming_steps = WorkStep.objects.filter(
        work__in=visible_works,
        step_status=WorkStep.StepStatus.OPEN,
        planned_due_date__range=(today, next_week),
    ).select_related("work", "work__customer")

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
            work_month = format_work_month(target_year, target_month)
            created, existed, steps_created = bulk_ensure_work_for_month(work_month)
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
        upcoming_steps=upcoming_steps,
    )
    return TemplateResponse(request, "admin/invoice/dashboard.html", context)

class InvoiceAdminSite(admin.AdminSite):
    site_header = "CM Invoice Tracking"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "invoice/dashboard/",
                self.admin_view(self.dashboard_view),
                name="invoice_dashboard",
            )
        ]
        return custom_urls + urls

    def dashboard_view(self, request):
        return dashboard_view(request, self)

    def index(self, request, extra_context=None):
        return dashboard_view(request, self)


admin_site = InvoiceAdminSite(name="invoice_admin")
admin_site.register(User, UserAdmin)
admin_site.register(Customer, CustomerAdmin)
admin_site.register(CustomerStepRule, CustomerStepRuleAdmin)
admin_site.register(Work, WorkAdmin)
admin_site.register(WorkStep)
admin_site.register(SystemSetting, SystemSettingAdmin)
